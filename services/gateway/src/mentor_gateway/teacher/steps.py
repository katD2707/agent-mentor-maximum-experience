"""Teacher review by step (CONTRACTS 16.5): edit one block, redo a chapter recap, set the English gloss, the review list of
steps Mentor is unsure about, and per-course test sizes. Drafts only. No model is called here: the teacher's words are kept
as written; audio is redone by builder jobs (`retts_block`, `recap`)."""

import json
from typing import Any

from mentor_schemas.course import CoursePack
from pydantic import ValidationError

from mentor_gateway.content.store import ContentError, Immutable, NotFound, atomic_write
from mentor_gateway.teacher.service import BuilderService

TEXT_FIELDS = ("md", "prompt", "caption", "title", "alt", "text")
LOCKED = ("id", "kind")


def _draft_pack(svc: BuilderService, cid: str, version: int) -> tuple[Any, CoursePack]:
    store = svc.content.store
    info = store.version_info(store.load_meta(cid), version)
    if info.status == "published":
        raise Immutable("version_published", "the version is published: create a new version to edit")
    return store, store.load_pack(cid, version)


def _invalid(reason: object) -> ContentError:
    return ContentError("invalid_block", str(reason)[:300])


def _merge(old: dict, fields: dict) -> dict:
    new = dict(old)
    for k, v in fields.items():
        if k in LOCKED:
            continue
        if k == "items" and isinstance(v, list) and isinstance(old.get("items"), list) and old.get("kind") == "quiz":
            items = [dict(i) for i in old["items"]]
            for part in v:
                if not isinstance(part, dict) or "id" not in part:
                    raise _invalid("each item needs its id")
                target = next((i for i in items if i["id"] == part["id"]), None)
                if target is None:
                    raise _invalid(f"unknown item {part['id']}")
                target.update({kk: vv for kk, vv in part.items() if kk != "id"})
            new["items"] = items
        else:
            new[k] = v
    return new


def patch_block(svc: BuilderService, st: dict, version: int, block_id: str, fields: dict) -> dict:
    cid = st["course_id"]
    store, pack = _draft_pack(svc, cid, version)
    data = pack.model_dump(mode="json")
    block = next((b for ch in data["chapters"] for ls in ch["lessons"] for b in ls["blocks"] if b["id"] == block_id), None)
    if block is None:
        raise NotFound("unknown_block")
    merged = _merge(block, fields)
    block.clear()
    block.update(merged)
    try:
        new_pack = CoursePack.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0] if e.errors() else {}
        raise _invalid(f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', e)}") from None
    store.write_pack(cid, version, new_pack)
    out = merged
    if block.get("audio") and any(k in fields for k in TEXT_FIELDS):  # a read-aloud: the voice is redone in the background
        svc.enqueue(st, "retts_block", _args(svc, st, version, block_id=block_id))
    return out


def _args(svc: BuilderService, st: dict, version: int, **extra: Any) -> dict:
    # `version` and the job's own keys as in the contract; the course and store are what every builder job carries
    return {"course_id": st["course_id"], "store": str(svc.content.store.root), "teacher_id": st["teacher_id"],
            "version": version, **extra}


def put_recap(svc: BuilderService, st: dict, version: int, chapter_id: str, script: list[str]) -> dict:
    script = [s.strip() for s in script if s and s.strip()]
    if not script:
        raise _invalid("the recap needs at least one paragraph")
    _, pack = _draft_pack(svc, st["course_id"], version)
    if not any(ch.id == chapter_id for ch in pack.chapters):
        raise NotFound("unknown_chapter")
    job = svc.enqueue(st, "recap", _args(svc, st, version, chapter_id=chapter_id, script=script))
    return {"job_id": job["id"]}


def put_gloss(svc: BuilderService, st: dict, version: int, gloss_start: int) -> dict:
    store, pack = _draft_pack(svc, st["course_id"], version)
    store.write_pack(st["course_id"], version, pack.model_copy(update={"gloss_start": int(gloss_start)}))
    return {"gloss_start": int(gloss_start)}


# ---- review list ---------------------------------------------------------------------------------------

def _seen_path(svc: BuilderService, cid: str, version: int):
    return svc.course_dir(cid) / "versions" / str(version) / "review.seen.json"


def review_list(svc: BuilderService, cid: str, version: int) -> dict:
    raw = svc._json(cid, f"versions/{version}/review.json", [])  # noqa: SLF001
    rows = raw.get("unsure", []) if isinstance(raw, dict) else raw
    seen = set(svc._json(cid, f"versions/{version}/review.seen.json", []) or [])  # noqa: SLF001
    return {"unsure": [r for r in rows if isinstance(r, dict) and r.get("block_id") not in seen]}


def mark_seen(svc: BuilderService, cid: str, version: int, block_id: str) -> dict:
    seen = set(svc._json(cid, f"versions/{version}/review.seen.json", []) or [])  # noqa: SLF001
    seen.add(block_id)
    path = _seen_path(svc, cid, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(sorted(seen)).encode("utf-8"))
    return review_list(svc, cid, version)


# ---- tests per course ----------------------------------------------------------------------------------

def course_tests(svc: BuilderService, cid: str) -> dict[str, dict]:
    data = svc._json(cid, "tests.json", {})  # noqa: SLF001
    return data if isinstance(data, dict) else {}


def put_test(svc: BuilderService, cid: str, profile_id: str, items: int, minutes: int) -> dict:
    data = course_tests(svc, cid)
    data[profile_id] = {"items": items, "minutes": minutes}
    path = svc.course_dir(cid) / "tests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    return data[profile_id]
