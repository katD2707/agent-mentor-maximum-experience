"""`/api/teacher`: course authoring for teachers (CONTRACTS "Teacher authoring"). Role teacher only; every course is
visible to its owner only (403 `not_owner` for someone else's, 404 for none)."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from mentor_gateway.api.courses import IMMUTABLE, MIME_FIX, _cached, media_user
from mentor_gateway.api.deps import current_user
from mentor_gateway.content.store import ContentError, Immutable, NotFound, sha256_bytes
from mentor_gateway.db import User
from mentor_gateway.teacher.service import Busy, BuilderService, Forbidden

router = APIRouter(prefix="/teacher", tags=["teacher"])

MAX_UPLOAD_BYTES = 400_000_000


def teacher_only(user: User = Depends(current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(403, {"error": "role_mismatch"})
    return user


def media_teacher(user: User = Depends(media_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(403, {"error": "role_mismatch"})
    return user


def builder(request: Request) -> BuilderService:
    return request.app.state.builder


def _safe_name(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path((name or "file").replace("\\", "/")).name, flags=re.UNICODE).strip(" .") or "file"
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    cand, i = base, 2
    while cand.lower() in taken:
        cand = f"{stem}-{i}{'.' + ext if ext else ''}"
        i += 1
    taken.add(cand.lower())
    return cand


async def _save_files(svc: BuilderService, cid: str, request: Request) -> tuple[str, list[str], list[str], str | None]:
    """Multipart `files[]` (also `files`), optional `note` and repeated `replace` -> (batch, names, replace, note)."""
    form = await request.form()
    uploads = [f for k in ("files", "files[]") for f in form.getlist(k) if hasattr(f, "read")]
    if not uploads:
        raise ContentError("no_files", "send at least one file in `files`")
    base = svc.course_dir(cid) / "uploads"
    taken = {p.name.lower() for p in base.rglob("*") if p.is_file()} if base.is_dir() else set()
    batch = f"b{len(list(base.iterdir())) + 1:03d}" if base.is_dir() else "b001"
    dest = base / batch
    dest.mkdir(parents=True, exist_ok=True)
    names, total = [], 0
    for f in uploads:
        name = _safe_name(getattr(f, "filename", "") or "file", taken)
        with (dest / name).open("wb") as out:
            while chunk := await f.read(1 << 20):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise ContentError("too_large", "upload is larger than 400 MB")
                out.write(chunk)
        names.append(name)
    replace = [str(v) for v in form.getlist("replace") if str(v).strip()]
    note = form.get("note")
    return batch, names, replace, (str(note) if note else None)


# ---------------------------------------------------------------- upload and materials
@router.post("/uploads")
async def upload(request: Request, user: User = Depends(teacher_only), svc: BuilderService = Depends(builder)) -> dict:
    form = await request.form()  # cached: _save_files reads it again
    first = next((getattr(f, "filename", "") for k in ("files", "files[]") for f in form.getlist(k) if hasattr(f, "read")), "")
    # the title does not exist yet at upload: the first file's name (or the note) gives the readable id
    st = svc.create(user, None, Path((first or "").replace("\\", "/")).stem or str(form.get("note") or "")[:60])
    try:
        batch, names, _, note = await _save_files(svc, st["course_id"], request)
    except ContentError:
        import shutil

        svc._states.pop(st["course_id"], None)  # noqa: SLF001 - nothing was accepted: forget the empty draft
        shutil.rmtree(svc.course_dir(st["course_id"]), ignore_errors=True)
        raise
    st["note"] = note
    if note:
        svc.say(st, "teacher", "text", note)
    svc.say(st, "agent", "notice", "Mình nhận được tài liệu rồi và đang đọc. Bạn có thể đóng app, khi xong sẽ có thông báo.",
            "Got your material and I am reading it. You can close the app; you will be notified.")
    job = svc.enqueue(st, "intake", svc.intake_args(st, batch, names, []), kick=False)
    svc._save(st)  # noqa: SLF001
    svc.kick()
    return {"course_id": st["course_id"], "job_id": job["id"]}


@router.post("/courses/{course_id}/materials")
async def add_materials(course_id: str, request: Request, user: User = Depends(teacher_only),
                        svc: BuilderService = Depends(builder)) -> dict:
    st = svc.owned(user, course_id)
    if any(j["kind"] == "build" for j in svc.active_jobs(st)):
        raise Busy("busy", "a build is running")
    batch, names, replace, _ = await _save_files(svc, course_id, request)
    what = f"{len(replace)} trang chụp lại" if replace else f"{len(names)} tệp mới"
    svc.say(st, "teacher", "text", f"Gửi thêm: {what}.", f"Sent: {len(names)} file(s).")
    job = svc.enqueue(st, "intake", svc.intake_args(st, batch, names, replace), kick=False)
    svc._save(st)  # noqa: SLF001
    svc.kick()
    return {"job_id": job["id"]}


@router.get("/courses/{course_id}/thumb")
async def thumb(course_id: str, ref: str, user: User = Depends(media_teacher),
                svc: BuilderService = Depends(builder)) -> Response:
    """Thumbnail of an unreadable page (for <img>; Bearer or `?t=` media token)."""
    svc.owned(user, course_id)
    src = svc.page_image(course_id, ref)
    if src is None:
        raise NotFound("page_not_found")
    cache = svc.course_dir(course_id) / "thumbs" / (sha256_bytes(ref.encode())[:16] + ".jpg")
    if not cache.is_file():
        try:
            from PIL import Image

            cache.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im.thumbnail((480, 480))
                im.convert("RGB").save(cache, "JPEG", quality=80)
        except Exception:  # noqa: BLE001 - no Pillow or a broken file: serve the page itself
            cache = src
    return FileResponse(cache, headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- list, detail
@router.get("/courses")
async def courses(since: str | None = None, user: User = Depends(teacher_only),
                  svc: BuilderService = Depends(builder)) -> list[dict]:
    out = svc.list_for(user)
    if since:
        try:
            cut = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, {"error": "bad_since"}) from None
        out = [c for c in out if datetime.fromisoformat(c["updated_at"]) > cut]
    return out


@router.get("/courses/{course_id}")
async def course(course_id: str, user: User = Depends(teacher_only), svc: BuilderService = Depends(builder)) -> dict:
    return svc.detail(svc.owned(user, course_id))


# ---------------------------------------------------------------- chat and outline
class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/courses/{course_id}/chat")
async def chat(course_id: str, body: ChatBody, user: User = Depends(teacher_only),
               svc: BuilderService = Depends(builder)) -> list[dict]:
    """The agent applies the instruction without asking back: before a build it edits the outline, after it every text
    block of the draft (a new draft version is started when only published versions exist). Returns the new messages."""
    st = svc.owned(user, course_id)
    if any(j["kind"] == "build" for j in svc.active_jobs(st)):
        raise Busy("busy", "a build is running")
    store = svc.content.store
    meta = svc._store_meta(course_id)  # noqa: SLF001
    built = meta is not None and any(store.pack_path(course_id, v.version).is_file() for v in meta.versions)
    if not built and not svc.outline(course_id):
        raise Busy("outline_not_ready", "the outline does not exist yet")
    first = len(st["chat"])
    svc.say(st, "teacher", "text", body.text)
    if not built:
        job = svc.enqueue(st, "outline_chat", {"course_id": course_id, "instruction": body.text}, kick=False)
    else:
        unpublished = [v.version for v in meta.versions if v.status != "published"]
        version = max(unpublished) if unpublished else svc.new_version_from_published(st)
        job = svc.enqueue(st, "revise_all", {"course_id": course_id, "version": version, "instruction": body.text,
                                             "store": str(svc.content.store.root)}, kick=False)
    svc.say(st, "agent", "notice", "Mình đang sửa theo yêu cầu của bạn.", "Working on it.")
    svc._save(st)  # noqa: SLF001
    svc.kick()
    await svc.wait(job["id"], svc.settings.builder_chat_wait_s)
    return st["chat"][first:]


class OutlineBody(BaseModel):
    ops: list[dict] = Field(max_length=200)


@router.put("/courses/{course_id}/outline")
async def put_outline(course_id: str, body: OutlineBody, user: User = Depends(teacher_only),
                      svc: BuilderService = Depends(builder)) -> dict:
    """Structured edits (rename, update, reorder, delete, add_lesson, add_chapter, move_lesson, merge). Pure data, no
    model call, so it runs here instead of in a builder subprocess."""
    st = svc.owned(user, course_id)
    if svc.active_jobs(st):
        raise Busy("busy", "the agent is working on this course")
    if not svc.outline(course_id):
        raise Busy("outline_not_ready", "the outline does not exist yet")
    from mentor_course_builder.outline import CourseOutline, OutlineEditError, apply_outline_edits, outline_to_json

    cur = CourseOutline.model_validate(svc.outline(course_id))
    try:
        new = apply_outline_edits(cur, body.ops)
    except (OutlineEditError, KeyError, TypeError, ValueError) as exc:
        raise ContentError("bad_outline_edit", f"{type(exc).__name__}: {exc}") from None
    (svc.course_dir(course_id) / "outline.json").write_text(outline_to_json(new), encoding="utf-8")
    st["outline_edited"] = True
    svc._save(st)  # noqa: SLF001
    svc.emit(st)
    return new.model_dump()


@router.post("/courses/{course_id}/build")
async def build(course_id: str, user: User = Depends(teacher_only), svc: BuilderService = Depends(builder)) -> dict:
    st = svc.owned(user, course_id)
    if svc.active_jobs(st):
        raise Busy("busy", "the agent is working on this course")
    if not svc.outline(course_id):
        raise Busy("outline_not_ready", "the outline does not exist yet")
    meta = svc._store_meta(course_id)  # noqa: SLF001
    if meta is not None and all(v.status == "published" for v in meta.versions):
        raise Busy("use_new_version", "the course is published: POST /versions to edit it")
    svc.reset_progress(st)
    n = len(svc.build_lessons(course_id))
    svc.say(st, "teacher", "text", "Soạn theo cấu trúc này.", "Build from this outline.")
    svc.say(st, "agent", "notice", f"Mình bắt đầu soạn {n} bài. Bạn có thể đóng app, soạn xong sẽ có thông báo.",
            f"Started building {n} lessons. You can close the app.")
    job = svc.enqueue(st, "build", svc.build_args(st))
    return {"job_id": job["id"]}


# ---------------------------------------------------------------- versions: pack, assets, comments, publish
def _version(svc: BuilderService, user: User, course_id: str, version: int) -> dict:
    st = svc.owned(user, course_id)
    svc.content.store.version_info(svc.content.store.load_meta(course_id), version)
    return st


@router.get("/courses/{course_id}/versions/{version}/pack")
async def pack(request: Request, course_id: str, version: int, user: User = Depends(teacher_only),
               svc: BuilderService = Depends(builder)) -> Response:
    _version(svc, user, course_id, version)
    store = svc.content.store
    info = store.version_info(store.load_meta(course_id), version)
    raw = store.pack_bytes_raw(course_id, version)
    return _cached(request, raw, "application/json", info.pack_sha256 or sha256_bytes(raw),
                   IMMUTABLE if info.status == "published" else "private, no-store")


@router.get("/courses/{course_id}/versions/{version}/assets/{path:path}")
async def asset(course_id: str, version: int, path: str, user: User = Depends(media_teacher),
                svc: BuilderService = Depends(builder)) -> Response:
    _version(svc, user, course_id, version)
    store = svc.content.store
    file = store.asset_path(course_id, version, path)
    mime = MIME_FIX.get(file.suffix.lower()) or "application/octet-stream"
    published = store.version_info(store.load_meta(course_id), version).status == "published"
    return FileResponse(file, media_type=mime, headers={
        "Cache-Control": IMMUTABLE if published else "private, no-store", "Accept-Ranges": "bytes",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


class TextAnchor(BaseModel):
    kind: Literal["text"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    quote: str = Field(min_length=1, max_length=2000)


class TimeAnchor(BaseModel):
    kind: Literal["time"]
    t: float = Field(ge=0, le=36000)


class PointAnchor(BaseModel):
    kind: Literal["point"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class CommentBody(BaseModel):
    block_id: str = Field(min_length=1, max_length=120)
    anchor: Annotated[TextAnchor | TimeAnchor | PointAnchor, Field(discriminator="kind")]
    body: str = Field(min_length=1, max_length=2000)


def _comment_view(c: dict) -> dict:
    return {k: c[k] for k in ("id", "block_id", "anchor", "body", "status", "note", "version", "created_at", "updated_at")} | {"stale": bool(c.get("stale"))}


@router.post("/courses/{course_id}/versions/{version}/comments")
async def add_comment(course_id: str, version: int, body: CommentBody, user: User = Depends(teacher_only),
                      svc: BuilderService = Depends(builder)) -> dict:
    """Queues a revise job: a text anchor rewrites only that block (ids kept, humanized, quiz re-verified); a time
    anchor revises the video scene at `t`; a point anchor revises the image around (x, y). Never asks back."""
    st = _version(svc, user, course_id, version)
    c, _ = svc.add_comment(st, version, body.block_id, body.anchor.model_dump(exclude_none=True), body.body)
    out = _comment_view(c)
    svc.kick()
    return out


@router.get("/courses/{course_id}/versions/{version}/comments")
async def comments(course_id: str, version: int, stale: bool = False, user: User = Depends(teacher_only),
                   svc: BuilderService = Depends(builder)) -> list[dict]:
    """Comments written on this version. After a rebuild of the draft the earlier ones are `stale`: hidden unless `?stale=true`."""
    st = _version(svc, user, course_id, version)
    return [_comment_view(c) for c in st["comments"] if c["version"] == version and bool(c.get("stale")) == stale]


@router.get("/courses/{course_id}/versions/{version}/verify")
async def verify_version(course_id: str, version: int, user: User = Depends(teacher_only),
                         svc: BuilderService = Depends(builder)) -> dict:
    """What would stop `publish` right now: `{blocked, issues: [{code, severity, lesson_id, block_id, vi, en}]}`."""
    _version(svc, user, course_id, version)
    issues = await asyncio.to_thread(svc.publish_blockers, course_id, version)
    return {"blocked": bool(issues), "issues": issues}


class LevelBody(BaseModel):
    level: Literal["basic", "intermediate", "advanced"]


@router.put("/courses/{course_id}/versions/{version}/level")
async def put_level(course_id: str, version: int, body: LevelBody, user: User = Depends(teacher_only),
                    svc: BuilderService = Depends(builder)) -> dict:
    """Teacher confirms (or changes) the course level of a version. On a published version a different level creates
    (or reuses) the next draft and is stored there: `{version, new_version, level, level_suggested, level_confirmed}`."""
    st = _version(svc, user, course_id, version)
    return svc.set_level(st, version, body.level)


@router.post("/courses/{course_id}/versions/{version}/publish")
async def publish(course_id: str, version: int, user: User = Depends(teacher_only),
                  svc: BuilderService = Depends(builder)) -> dict:
    st = _version(svc, user, course_id, version)
    if svc.active_jobs(st):
        raise Busy("busy", "the agent is still working on this course")
    store = svc.content.store
    vinfo = store.version_info(store.load_meta(course_id), version)
    if vinfo.status != "published" and not vinfo.level_confirmed:
        raise HTTPException(409, {"error": "level_unconfirmed"})  # the agent only suggests; the teacher picks the level
    blockers = await asyncio.to_thread(svc.publish_blockers, course_id, version)
    if blockers:  # hard errors (missing lesson or quiz, broken formula, wrong answer key, damaged file...) stop publishing
        raise HTTPException(409, {"error": "verify_failed", "issues": blockers})
    info = svc.content.store.publish(course_id, version)
    svc.say(st, "agent", "notice", f"Đã xuất bản bản {version}.", f"Published v{version}.")
    svc._save(st)  # noqa: SLF001
    svc.emit(st)
    return {"version": info.model_dump(mode="json"), "course": svc.view(st)}


@router.post("/courses/{course_id}/versions", status_code=201)
async def new_version(course_id: str, user: User = Depends(teacher_only), svc: BuilderService = Depends(builder)) -> dict:
    """Draft v+1 copied from the latest published version; comments then apply to it, students keep their version."""
    st = svc.owned(user, course_id)
    if svc.active_jobs(st):
        raise Busy("busy", "the agent is working on this course")
    v = svc.new_version_from_published(st)
    return {"version": v, "status": "draft", "course": svc.view(st)}


# ---------------------------------------------------------------- events
@router.get("/events")
async def events(request: Request, limit: int | None = Query(default=None, ge=1, le=1000),
                 user: User = Depends(media_teacher), svc: BuilderService = Depends(builder)) -> StreamingResponse:
    """SSE: `event: course` with {course_id, status, status_line_vi/en, updated_at, build?} on every change.
    Reconnect with `Last-Event-ID` to replay what was missed (short buffer); `GET /courses?since=` is the fallback.
    `limit` closes the stream after that many events (tests)."""
    last = request.headers.get("last-event-id")
    q, replay = svc.bus.subscribe(user.id, int(last) if last and last.isdigit() else None)

    async def gen() -> AsyncIterator[str]:
        sent = 0
        try:
            yield ": ok\n\n"
            for i, data in replay[: limit or None]:
                yield f"id: {i}\nevent: course\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                sent += 1
            while limit is None or sent < limit:
                try:
                    i, tid, data = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    if await request.is_disconnected():
                        return
                    continue
                if tid != user.id:
                    continue
                yield f"id: {i}\nevent: course\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                sent += 1
        finally:
            svc.bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
