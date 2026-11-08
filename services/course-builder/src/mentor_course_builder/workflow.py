"""Teacher-flow stages that the gateway runs as subprocesses (REQUIREMENTS-PLAN §4).

    mcb job <kind> --dir <builder dir of the course> --args <args.json> --result <result.json>

Every stage reads and writes plain JSON under the course's builder directory, so the gateway can restart between stages:

    <dir>/uploads/<batch>/...             raw teacher files (written by the gateway)
    <dir>/intake/pages.json, checks.json  merged intake of every batch (retaken pages replace the old ones)
    <dir>/outline.json                    CourseOutline
    <dir>/build/progress.json             per-lesson state while a build runs
    <dir>/versions/<v>/media.json         {request id: {request, files, source_dir (relative), duration_s, timeline}}
    <dir>/versions/<v>/media/             media files and editable sources (source_dir is relative to this folder)

Kinds: intake (intake + merge + outline), outline_chat (free-text outline edit), build (content, media, cover, store),
revise_text (one block), revise_media (video at a time, image at a point), revise_all (course-wide instruction).
The result file is {"ok": bool, "message_vi", "message_en", ...}; a failed stage exits 1 with {"ok": false, "error"}.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from mentor_schemas import ModelAlias
from mentor_schemas.course import AssetRef, CalloutBlock, CoursePack, ImageBlock, QuizBlock, QuizItem, TextBlock, VideoBlock

from mentor_course_builder import humanize, verify
from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name, load_intake, source_pages
from mentor_course_builder.intake import IntakeOptions, IntakeResult, intake, write_outputs
from mentor_course_builder.llm import ModelClient, ModelError
from mentor_course_builder.models import KIND_IMAGE, Material
from mentor_course_builder.outline import CourseOutline, build_outline, outline_to_json, revise_outline
from mentor_course_builder.quality import build_messages

log = logging.getLogger("mentor_course_builder")


class JobError(Exception):
    pass


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text("utf-8")) if path.is_file() else default


def _base(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


# ---------------------------------------------------------------- intake merge (add / retake pages)
def merge_intake(old: IntakeResult | None, new: IntakeResult, replace: list[str] | None = None) -> IntakeResult:
    """Fold the intake of a new upload batch into the course's intake.

    `replace` = ["<file>#<page>", ...]: the i-th photo of the batch takes the place of that page (same source file and
    page number, so outline lessons that cite it keep working). Other new materials are appended; new photo numbers
    continue after the existing ones.
    """
    from mentor_course_builder.quality import page_label

    res = IntakeResult(materials=copy.deepcopy(old.materials) if old else [], checks=copy.deepcopy(old.checks) if old else [])
    mats: list[Material] = copy.deepcopy(new.materials)
    cks = copy.deepcopy(new.checks)
    by_page = {id(p): next((c for c in cks if (c.source_file, c.page, c.kind) == (p.source_file, p.index, p.kind)), None)
               for m in mats for p in m.pages}  # pair each new page with its check before anything is renamed
    offset = sum(1 for m in res.materials for p in m.pages if p.kind == KIND_IMAGE)
    fresh = [p for m in mats for p in m.pages if p.kind == KIND_IMAGE]
    for p in fresh:  # photo numbers continue ("Ảnh 3"); the check's message carries the label
        c = by_page[id(p)]
        was = page_label(p, "vi"), page_label(p, "en")
        p.index += offset
        if c is not None:
            c.page = p.index
            c.message_vi = c.message_vi.replace(was[0], page_label(p, "vi"), 1)
            c.message_en = c.message_en.replace(was[1], page_label(p, "en"), 1)
    consumed: set[int] = set()
    for ref in replace or []:
        name, _, idx = ref.rpartition("#")
        target = next(((m, i, p) for m in res.materials for i, p in enumerate(m.pages)
                       if _base(p.source_file) == name and str(p.index) == idx), None)
        newp = next((p for p in fresh if id(p) not in consumed), None)
        if target is None or newp is None:
            continue
        m, pos, oldp = target
        consumed.add(id(newp))
        newc = by_page[id(newp)]
        slot = next((k for k, c in enumerate(res.checks) if (c.source_file, c.page) == (oldp.source_file, oldp.index)), None)
        if slot is not None:
            del res.checks[slot]
        newp.source_file, newp.index = oldp.source_file, oldp.index
        if newc is not None:
            newc.source_file, newc.page = oldp.source_file, oldp.index
            if newc.reasons:
                newc.message_vi, newc.message_en = build_messages(newp, newc.reasons)
            res.checks.insert(slot if slot is not None else len(res.checks), newc)
        m.pages[pos] = newp
    for m in mats:
        keep = [p for p in m.pages if id(p) not in consumed]
        res.checks += [by_page[id(p)] for p in keep if by_page[id(p)] is not None]
        m.pages = keep
        if keep or m.notes:
            res.materials.append(m)
    return res


# ---------------------------------------------------------------- progress (build)
class Progress:
    def __init__(self, path: Path, lessons: list[tuple[str, str]]) -> None:
        self.path, self._lock = path, threading.Lock()
        self.data = {"stage": "content", "cover": "waiting",
                     "lessons": [{"id": i, "title": t, "state": "waiting"} for i, t in lessons]}
        self._save()

    def _save(self) -> None:
        _write_json(self.path, self.data)

    def set(self, lesson_id: str | None, state: str, note: str | None = None) -> None:
        with self._lock:
            if lesson_id is None:
                self.data["cover"] = state
            else:
                for ls in self.data["lessons"]:
                    if ls["id"] == lesson_id:
                        ls["state"] = state
                        if note:
                            ls["note"] = note
            self._save()

    def stage(self, stage: str) -> None:
        with self._lock:
            self.data["stage"] = stage
            self._save()


# ---------------------------------------------------------------- helpers
def _outline(base: Path) -> CourseOutline:
    f = base / "outline.json"
    if not f.is_file():
        raise JobError("no outline yet")
    return CourseOutline.model_validate_json(f.read_text("utf-8"))


def _msg(vi: str, en: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "message_vi": vi, "message_en": en, **extra}


def _opts(args: dict) -> IntakeOptions:
    return IntakeOptions(workers=int(args.get("workers") or 3))


# ---------------------------------------------------------------- stage: intake + outline
def job_intake(base: Path, args: dict, client: ModelClient | None) -> dict:
    if client is None:
        raise JobError("no model client: set MODEL_ROUTER_URL/MODEL_ROUTER_KEY, or COURSE_BUILDER_DIRECT=1 with FPT_API_BASE/FPT_API_KEY")
    batch = str(args["batch"])
    batch_dir = base / "uploads" / batch
    files = [batch_dir / n for n in args["files"]]
    intake_dir = base / "intake"
    marker = intake_dir / "batches.json"
    done = _read_json(marker, [])
    old = load_intake(intake_dir) if (intake_dir / "pages.json").is_file() else None
    new_pages: list[str] = []
    if batch not in done:  # a restart after the merge was written must not merge twice
        got = intake([str(f) for f in files], intake_dir / "_batches" / batch, client=client, options=_opts(args))
        merged = merge_intake(old, got, args.get("replace") or [])
        write_outputs(merged, intake_dir)
        _write_json(marker, done + [batch])
        new_pages = [f"{_base(p.source_file)}#{p.index}" for m in got.materials for p in m.pages]
        old = merged
    else:
        old = load_intake(intake_dir)
    retake = old.retake
    note = args.get("note")
    has_text = bool(source_pages(old))
    outline_f = base / "outline.json"
    replaced_only = bool(args.get("replace")) and len(args["replace"]) >= len(files)
    outline_msg = ""
    if not has_text:
        outline_msg = "no readable page"
    elif not outline_f.is_file() or not args.get("outline_edited"):
        if client is None:
            raise JobError("no model client for the outline")
        outline = build_outline(old, client, teacher_note=note, course_id=args["course_id"])
        outline_f.write_text(outline_to_json(outline), encoding="utf-8")
        outline_msg = "outline built"
    elif not replaced_only and client is not None:  # the teacher edited the outline: fold the new pages in
        cur = _outline(base)
        new, _ = revise_outline(cur, "Add the material pages " + ", ".join(new_pages[:40]) +
                                " as new lessons (or into the lesson they belong to). Change nothing else.", client)
        outline_f.write_text(outline_to_json(new), encoding="utf-8")
        outline_msg = "outline updated"
    n = len(retake)
    return _msg(f"Đã đọc xong tài liệu. {n} trang cần chụp lại." if n else "Đã đọc xong tài liệu.",
                f"Finished reading. {n} pages need a retake." if n else "Finished reading.",
                retake=n, outline=outline_msg, outline_ready=outline_f.is_file())


def job_outline_chat(base: Path, args: dict, client: ModelClient | None) -> dict:
    if client is None:
        raise JobError("no model client")
    cur = _outline(base)
    new, note = revise_outline(cur, str(args["instruction"]), client)
    (base / "outline.json").write_text(outline_to_json(new), encoding="utf-8")
    return _msg(note or "Đã sửa cấu trúc.", note or "Outline updated.", outline_ready=True)


# ---------------------------------------------------------------- stage: build
MEDIA_ORDER = {"tts": 0, "picture": 0, "illustration": 1, "diagram": 1, "video": 2, "cover": 3}


def _fallback_cover(title: str, dest: Path) -> None:
    import hashlib

    from PIL import Image, ImageDraw

    h = hashlib.sha256(title.encode()).digest()
    a, b = (h[0], h[1], h[2]), (h[3], h[4], h[5])
    img = Image.new("RGB", (1600, 1000))
    d = ImageDraw.Draw(img)
    for y in range(1000):
        t = y / 999
        d.line([(0, y), (1600, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "WEBP", quality=80)


def _file_dict(f: MediaFile, media_dir: Path) -> dict:
    return {"role": f.role, "path": f.path, "mime": f.mime, "file": os.path.relpath(f.file, media_dir).replace("\\", "/")}


def _result_dict(req: MediaRequest, r: MediaResult, media_dir: Path) -> dict:
    return {"request": req.model_dump(), "files": [_file_dict(f, media_dir) for f in r.files],
            "duration_s": r.duration_s, "timeline": r.timeline, "notes": r.notes, "meta": r.meta,
            "source_dir": os.path.relpath(r.source_dir, media_dir).replace("\\", "/") if r.source_dir else None}


def _load_results(media_dir: Path, rows: dict) -> dict[str, MediaResult]:
    out = {}
    for rid, row in rows.items():
        if not row.get("files"):
            continue
        out[rid] = MediaResult(
            id=rid, kind=row["request"]["kind"], duration_s=row.get("duration_s"), timeline=row.get("timeline"),
            source_dir=(media_dir / row["source_dir"]) if row.get("source_dir") else None, notes=row.get("notes") or [],
            meta=row.get("meta"),
            files=[MediaFile(role=f["role"], path=f["path"], mime=f["mime"], file=media_dir / f["file"]) for f in row["files"]])
    return out


def _target_version(store, course_id: str) -> int | None:
    try:
        meta = store.load_meta(course_id)
    except Exception:  # noqa: BLE001
        return None
    open_versions = [v.version for v in meta.versions if v.status != "published"]
    return max(open_versions) if open_versions else None



def _move_tree(src: Path, dst: Path) -> None:
    """Move a directory tree. On Windows a render process (Chrome, node) may still hold a file or folder inside `src`,
    so the rename and the delete after a copy can fail with PermissionError: retry, then copy and leave the
    undeletable leftovers behind (they are scratch). `dst` is always replaced as a whole."""
    for i in range(4):
        shutil.rmtree(dst, ignore_errors=True)
        try:
            os.rename(src, dst)
            return
        except OSError:
            time.sleep(0.5 * (i + 1))
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    shutil.rmtree(src, ignore_errors=True)

def _issue_lines(issues: list[dict], lang: str, limit: int = 8) -> str:
    return "\n".join("• " + (i["vi"] if lang == "vi" else i["en"]) for i in issues[:limit]) + \
        (f"\n• … +{len(issues) - limit}" if len(issues) > limit else "")


def job_build(base: Path, args: dict, client: ModelClient | None) -> dict:
    """Content, media and cover for the outline, then the verify-and-refine gate (refine.py), then a review draft.

    Time goes where the slow things overlap: lessons are written by `workers` threads; the moment a lesson is final its
    media is queued (read-aloud on a wide pool of fast jobs, video/diagram/picture on a narrow pool of heavy ones, longest
    first), so media of lesson 1 renders while lesson 6 is still being written; DeepTutor's quiz calls run next to them.
    """
    from mentor_gateway.content.store import ContentStore

    from mentor_course_builder import refine
    from mentor_course_builder.deeptutor import DeepTutor
    from mentor_course_builder.mediaplan import plan_media
    from mentor_course_builder.pipeline import build_course
    from mentor_course_builder.render_media import render_media
    from mentor_course_builder.tts import TtsService

    if client is None:
        raise JobError("no model client")
    outline = _outline(base)
    intake_res = load_intake(base / "intake") if (base / "intake" / "pages.json").is_file() else IntakeResult()
    store = ContentStore(Path(args["store"]))
    kinds = set(args.get("media_kinds") or ["tts", "video", "diagram", "illustration", "picture", "cover"])
    prog = Progress(base / "build" / "progress.json", [(ls.id, ls.title) for ls in outline.lessons()])
    media_dir = base / "build" / "media"
    shutil.rmtree(media_dir, ignore_errors=True)
    t0 = time.time()
    stamps: dict[str, float] = {}

    dt = DeepTutor.from_env() if args.get("deeptutor") else None
    plan = plan_media(outline, "\n".join(t for _, t in source_pages(intake_res))) if args.get("plan_media", True) else None

    tts = TtsService()
    rows: dict[str, dict] = {}
    results: dict[str, MediaResult] = {}
    lock = threading.Lock()
    notes: list[str] = []

    def render(req: MediaRequest) -> MediaResult | None:
        if req.kind not in kinds:
            return None
        try:
            r = render_media(req, media_dir, client=client, tts=tts)
        except Exception as exc:  # noqa: BLE001 - one missing picture must not stop the course
            with lock:
                notes.append(f"{req.id}: {req.kind} failed: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        with lock:
            results[req.id] = r
            rows[req.id] = _result_dict(req, r, media_dir)
        return r

    def forget(rid: str) -> None:
        with lock:
            results.pop(rid, None)
            rows.pop(rid, None)

    # two pools: many fast jobs (read-aloud, Edge TTS is limited inside TtsService) and a few heavy ones
    fast = ThreadPoolExecutor(max_workers=max(1, int(args.get("tts_workers") or 6)), thread_name_prefix="mcb-tts")
    heavy = ThreadPoolExecutor(max_workers=max(1, int(args.get("media_workers") or 2)), thread_name_prefix="mcb-media")
    futures: list = []
    remaining: dict[str, int] = {}

    def task(req: MediaRequest, lid: str | None) -> None:
        if lid and req.kind == "video":
            prog.set(lid, "video")
        stamps.setdefault(req.kind, time.time())
        render(req)
        if lid:
            with lock:
                remaining[lid] -= 1
                done = remaining[lid] == 0
            if done:
                prog.set(lid, "done")

    def on_draft(draft) -> None:
        lid = draft.lesson.id
        reqs = [m for m in draft.media if m.kind in kinds]
        with lock:
            remaining[lid] = len(reqs)
        if not reqs:
            prog.set(lid, "done")
            return
        prog.set(lid, "media")
        for req in sorted(reqs, key=lambda m: -MEDIA_ORDER.get(m.kind, 1)):  # longest jobs first
            futures.append((fast if req.kind == "tts" else heavy).submit(task, req, lid))

    cover_req = MediaRequest(id="cover", kind="cover", course_id=outline.course_id, age_band=outline.age_band,
                             language=outline.language,
                             spec={"title": outline.title, "subject": outline.subject,
                                   "idea": outline.description_short or outline.title})
    prog.set(None, "media")
    futures.append(heavy.submit(task, cover_req, None))

    try:
        res = build_course(intake_res, outline, client, dt=dt, quiz_items=args.get("quiz_items"),
                           workers=int(args.get("workers") or 2), teacher_name=args.get("teacher_name") or "Giáo viên",
                           log_fn=lambda s: log.warning("%s", s), on_lesson=lambda i, st: prog.set(i, st),
                           on_draft=on_draft, plan=plan)
        failed = {r.lesson_id: r.error for r in res.reports if r.error}
        for lid, err in failed.items():
            prog.set(lid, "failed", err)
        if not res.drafts:
            raise JobError("no lesson could be written: " + "; ".join(f"{k}: {v}" for k, v in failed.items())[:400])
        stamps["content"] = time.time()
        prog.stage("media")
        for f in futures:
            f.result()
        prog.set(None, "done")
        stamps["media"] = time.time()

        # ---- verify and refine: nothing reaches the teacher with a known hole in it
        prog.stage("verify")
        refiner = refine.Refiner(outline, res.drafts, results, client, write=res.writer.write, render=render, forget=forget,
                                 kinds=kinds, max_rounds=int(args.get("refine_rounds") or 3),
                                 teacher_id=args.get("teacher_id") or "teacher", teacher_name=args.get("teacher_name") or "Giáo viên",
                                 log_fn=lambda s: log.warning("%s", s))
        gate = refiner.run()
        stamps["verify"] = time.time()
    finally:
        fast.shutdown(wait=True, cancel_futures=True)
        heavy.shutdown(wait=True, cancel_futures=True)
    drafts = refiner.ordered()
    notes += res.notes
    # requests of lessons whose media we skipped are still recorded, so a later revise can find the spec
    for d in drafts:
        for m in d.media:
            rows.setdefault(m.id, {"request": m.model_dump(), "files": [], "source_dir": None})
    for lid in {ol.id for ol in outline.lessons()}:
        prog.set(lid, "done" if lid in refiner.drafts else "failed", None if lid in refiner.drafts else "not written")
    asm = gate.assembled
    notes += asm.notes
    version = _target_version(store, outline.course_id)
    if version is None:
        version = store.create_draft(asm.meta, note="draft by course-builder")
    else:
        store.refresh_meta(asm.meta)  # a re-run keeps the draft but the teacher may have renamed the course since
    if outline.level_suggested:  # the teacher confirms it in review; a level already confirmed is never overwritten
        store.set_level(outline.course_id, version, suggested=outline.level_suggested)
    pack = asm.pack.model_copy(update={"version": version})
    store.write_pack(outline.course_id, version, pack, assets=asm.assets)
    cover_dest = store.course_dir(outline.course_id) / asm.meta.cover
    cover = results.get("cover")
    if cover and cover.files and Path(cover.files[0].file).is_file():
        shutil.copyfile(cover.files[0].file, cover_dest)
    else:
        _fallback_cover(outline.title, cover_dest)
        notes.append("cover: placeholder used (generation failed)")
    store.set_status(outline.course_id, version, "review")
    vdir = base / "versions" / str(version)
    vdir.mkdir(parents=True, exist_ok=True)
    _move_tree(media_dir, vdir / "media")
    _write_json(vdir / "media.json", rows)
    report = gate.report()
    _write_json(vdir / "verify.json", {**report, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    prog.stage("done")
    seconds = round(time.time() - t0)
    n_ok, n_all = len(drafts), len(outline.lessons())
    hard = [i for i in report["hard"]]
    soft = [i for i in report["soft"]]
    n_fixed = len(report["fixed"])
    profile = {"content_s": round(stamps.get("content", t0) - t0), "media_done_s": round(stamps.get("media", t0) - t0),
               "verify_s": round(stamps.get("verify", t0) - stamps.get("media", t0)), "total_s": seconds}
    vi = f"Đã soạn xong {n_ok}/{n_all} bài ({seconds}s)."
    en = f"Built {n_ok}/{n_all} lessons in {seconds}s."
    if n_fixed:
        vi += f" Mình đã tự sửa {n_fixed} lỗi khi soát lại."
        en += f" I fixed {n_fixed} problems while checking."
    if hard:
        vi += f" Còn {len(hard)} lỗi cần xử lý trước khi xuất bản:\n" + _issue_lines(hard, "vi")
        en += f" {len(hard)} problems must be fixed before publishing:\n" + _issue_lines(hard, "en")
    if soft:
        vi += f"\nNgoài ra {len(soft)} điểm bạn nên xem:\n" + _issue_lines(soft, "vi", 6)
        en += f"\nAlso {len(soft)} things worth a look:\n" + _issue_lines(soft, "en", 6)
    if not hard:
        vi += " Đang chờ bạn duyệt."
        en += " Waiting for your review."
    return _msg(vi, en, version=version, seconds=seconds, failed={i.lesson_id: i.detail or i.code for i in gate.issues
                                                                  if i.code == "lesson_missing"},
                notes=notes[:30], issues=hard + soft, blocked=bool(hard), fixed=n_fixed, profile=profile)



# ---------------------------------------------------------------- revisions
REWRITE_SYSTEM = """You edit ONE block of a course lesson after a teacher's comment. Do exactly what the comment asks, change
nothing else, never ask a question back. Language: {lang}. Level: {band}. Keep every number, formula ($...$), name and
fact unless the comment asks to change it. Short, natural sentences like a good teacher. Markdown with KaTeX in $...$.
Reply with ONE JSON object {"md": str} holding the whole new text of the block."""

QUIZ_SYSTEM = """You edit ONE quiz block of a course after a teacher's comment. Do exactly what the comment asks, change nothing
else, never ask a question back. Language: {lang}. Level: {band}. Keep every item id and option id. Keep the answer key
consistent with the question. Reply with ONE JSON object {"items": [...]} with the same fields as the input items."""


def _pack_io(args: dict) -> tuple[Any, int, CoursePack, Path]:
    from mentor_gateway.content.store import ContentStore

    store = ContentStore(Path(args["store"]))
    cid, version = args["course_id"], int(args["version"])
    return store, version, store.load_pack(cid, version), store.version_dir(cid, version) / "assets"


def _find_block(pack: CoursePack, block_id: str):
    for ch in pack.chapters:
        for ls in ch.lessons:
            for i, b in enumerate(ls.blocks):
                if b.id == block_id:
                    return ls, i, b
    raise JobError(f"block {block_id} not found")


def _replace_block(pack: CoursePack, block_id: str, new) -> CoursePack:
    p = pack.model_copy(deep=True)
    ls, i, _ = _find_block(p, block_id)
    ls.blocks[i] = new
    return p


def _rewrite_md(md: str, comment: str, quote: str | None, client: ModelClient, pack: CoursePack, humanize_it: bool = True) -> str:
    system = REWRITE_SYSTEM.replace("{lang}", lang_name(pack.language)).replace("{band}", AGE_RULES[pack.age_band]["label"])
    user = f"BLOCK:\n{md}\n\n" + (f"The teacher selected this passage: «{quote}»\n" if quote else "") + f"COMMENT: {comment}"
    data = ask_json(client, system, user, max_tokens=3000, temperature=0.3)
    new = str(data.get("md") or "").strip()
    if not new:
        raise JobError("the model returned no text")
    if humanize_it:
        out, _ = humanize.humanize_texts({"b": new}, client, language=pack.language,
                                         age_band_label=AGE_RULES[pack.age_band]["label"])
        new = out.get("b", new)
    return new


def _retts(text: str, dest: Path, pack: CoursePack, rel: str) -> tuple[AssetRef, Path]:
    from mentor_course_builder.assemble import _ref
    from mentor_course_builder.tts import TtsService

    clip = TtsService().synthesize(text, lang=pack.language, age_band=pack.age_band, dest=dest)
    f = MediaFile(role="audio", path=rel, mime="audio/mpeg", file=clip.path)
    return _ref(f), clip.path


def _revise_block(pack: CoursePack, block_id: str, comment: str, quote: str | None, client: ModelClient,
                  assets_dir: Path) -> tuple[CoursePack, dict[str, Path], str]:
    """Rewrite one text/callout/quiz block. Returns (pack, new asset files, note)."""
    _, _, b = _find_block(pack, block_id)
    files: dict[str, Path] = {}
    if isinstance(b, (TextBlock, CalloutBlock)):
        new_md = _rewrite_md(b.md, comment, quote, client, pack)
        upd: dict[str, Any] = {"md": new_md}
        if b.audio:  # the read-aloud follows the text
            title = b.title + ". " if isinstance(b, CalloutBlock) and b.title else ""
            upd["audio"], path = _retts(title + new_md, assets_dir / b.audio.path, pack, b.audio.path)
            files[b.audio.path] = path
        return _replace_block(pack, block_id, b.model_copy(update=upd)), files, "text rewritten"
    if isinstance(b, QuizBlock):
        system = QUIZ_SYSTEM.replace("{lang}", lang_name(pack.language)).replace("{band}", AGE_RULES[pack.age_band]["label"])
        items_json = json.dumps([i.model_dump(mode="json") for i in b.items], ensure_ascii=False)
        user = f"ITEMS:\n{items_json}\n\n" + (f"The teacher selected: «{quote}»\n" if quote else "") + f"COMMENT: {comment}"
        last = ""
        for attempt in range(2):
            data = ask_json(client, system, user + (f"\nYour previous answer was rejected: {last}" if last else ""),
                            max_tokens=6000, temperature=0.2)
            try:
                items = [QuizItem.model_validate({**old.model_dump(mode="json"), **new})
                         for old, new in zip(b.items, data.get("items") or [])]
                if len(items) != len(b.items):
                    raise ValueError("item count changed")
            except Exception as exc:  # noqa: BLE001
                last = str(exc)[:200]
                continue
            bad = []
            for it, old in zip(items, b.items):
                if it.model_dump() != old.model_dump():
                    v = verify.check_item(it, client, pack.language)
                    if not v.ok:
                        bad.append(f"{it.id}: {v.reason}")
            if not bad:
                for it, old in zip(items, b.items):  # read-aloud of a changed stem follows the stem
                    if it.stem != old.stem and old.stem_audio:
                        ref, path = _retts(it.stem, assets_dir / old.stem_audio.path, pack, old.stem_audio.path)
                        items[items.index(it)] = it.model_copy(update={"stem_audio": ref})
                        files[old.stem_audio.path] = path
                return _replace_block(pack, block_id, b.model_copy(update={"items": items})), files, "quiz rewritten and re-checked"
            last = "answer check failed: " + "; ".join(bad)
        raise JobError(f"quiz edit rejected: {last}")
    raise JobError(f"block {block_id} has no text to edit")


def job_revise_text(base: Path, args: dict, client: ModelClient | None) -> dict:
    if client is None:
        raise JobError("no model client")
    store, version, pack, assets_dir = _pack_io(args)
    anchor = args.get("anchor") or {}
    new, files, note = _revise_block(pack, args["block_id"], args["comment"], anchor.get("quote"), client, assets_dir)
    store.write_pack(args["course_id"], version, new, assets=files)
    return _msg("Đã sửa khối được nhận xét.", "Fixed the commented block.", note=note, block_id=args["block_id"])


def job_revise_all(base: Path, args: dict, client: ModelClient | None) -> dict:
    if client is None:
        raise JobError("no model client")
    store, version, pack, assets_dir = _pack_io(args)
    todo = [b.id for ch in pack.chapters for ls in ch.lessons for b in ls.blocks if isinstance(b, (TextBlock, CalloutBlock))]
    changed: dict[str, Path] = {}
    errors: list[str] = []
    cur = pack
    for bid in todo:
        try:
            cur, files, _ = _revise_block(cur, bid, args["instruction"], None, client, assets_dir)
            changed.update(files)
        except (JobError, ModelError, ValueError) as exc:
            errors.append(f"{bid}: {str(exc)[:100]}")
    if len(errors) == len(todo) and todo:
        raise JobError("no block could be changed: " + "; ".join(errors[:3]))
    store.write_pack(args["course_id"], version, cur, assets=changed)
    n = len(todo) - len(errors)
    return _msg(f"Đã sửa {n} khối theo yêu cầu.", f"Changed {n} blocks as asked.", changed=n, errors=errors[:10])


def job_revise_media(base: Path, args: dict, client: ModelClient | None) -> dict:
    from mentor_course_builder.assemble import _ref
    from mentor_course_builder.render_media import render_media
    from mentor_course_builder.tts import TtsService

    if client is None:
        raise JobError("no model client")
    store, version, pack, _ = _pack_io(args)
    bid = args["block_id"]
    vdir = base / "versions" / str(version)
    rows = _read_json(vdir / "media.json", {})
    media_dir = vdir / "media"
    row = rows.get(bid)
    if row is None:
        raise JobError(f"no editable source for {bid} (not built by the course builder)")
    anchor = args.get("anchor") or {}
    req = MediaRequest.model_validate(row["request"])
    src = (media_dir / row["source_dir"]) if row.get("source_dir") else None
    if src is None or not src.is_dir():
        raise JobError(f"the editable source of {bid} is missing")
    rev: dict[str, Any] = {"comment": args["comment"], "source_dir": str(src)}
    if anchor.get("kind") == "time":
        rev["at_s"] = float(anchor["t"])
    else:
        rev["x"], rev["y"] = float(anchor["x"]), float(anchor["y"])
    req = req.model_copy(update={"revise": rev})
    out = render_media(req, media_dir, client=client, tts=TtsService())
    _, _, block = _find_block(pack, bid)
    assets: dict[str, Path] = {}

    def ref(role: str) -> AssetRef | None:
        f = next((x for x in out.files if x.role == role), None)
        if f is None:
            return None
        assets[f.path] = Path(f.file)
        return _ref(f)

    if isinstance(block, VideoBlock):
        upd = {"video": ref("main") or block.video, "poster": ref("poster") or block.poster,
               "captions": ref("captions") or block.captions, "duration_s": out.duration_s or block.duration_s}
    elif isinstance(block, ImageBlock):
        upd = {"image": ref("main") or block.image}
    else:
        raise JobError(f"block {bid} is not media")
    store.write_pack(args["course_id"], version, _replace_block(pack, bid, block.model_copy(update=upd)), assets=assets)
    rows[bid] = _result_dict(req.model_copy(update={"revise": None}), out, media_dir)
    _write_json(vdir / "media.json", rows)
    return _msg("Đã sửa phần được nhận xét.", "Fixed the commented part.", note="; ".join(out.notes)[:200], block_id=bid)


JOBS: dict[str, Callable[[Path, dict, ModelClient | None], dict]] = {
    "intake": job_intake, "outline_chat": job_outline_chat, "build": job_build, "revise_text": job_revise_text,
    "revise_media": job_revise_media, "revise_all": job_revise_all,
}


def run_job(kind: str, base: Path, args: dict, client_factory: Callable[[], ModelClient | None]) -> dict:
    if kind not in JOBS:
        raise JobError(f"unknown job kind {kind}")
    client = client_factory()
    try:
        return JOBS[kind](base, args, client)
    finally:
        if client is not None:
            client.close()


__all__ = ["JobError", "run_job", "merge_intake", "Progress", "JOBS", "ModelAlias"]
