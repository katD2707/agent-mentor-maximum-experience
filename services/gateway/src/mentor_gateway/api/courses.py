"""`/api` course content: catalog, course page, pack and assets, enrollments, search (CONTRACTS "Courses and content").

Students see published versions only; teachers read everything (authoring endpoints come in P3). Media routes (cover and
assets) also accept `?t=<media token>` because <video>/<img>/<audio> cannot send a Bearer header.
"""

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import bearer_token, current_user, get_gw, user_from_token
from mentor_gateway.content import catalog_query as cq
from mentor_gateway.content.service import ContentService
from mentor_gateway.content.store import ComingSoon, ContentError, Immutable, NotFound, sha256_bytes
from mentor_gateway.context import Gateway
from mentor_gateway.db import User

router = APIRouter(tags=["courses"])

AgeBandQ = Query(pattern="^(g1_5|g6_9|g10_12|uni)$")
IMMUTABLE = "public, max-age=31536000, immutable"
MIME_FIX = {".vtt": "text/vtt", ".webp": "image/webp", ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".svg": "image/svg+xml", ".m4a": "audio/mp4", ".webm": "video/webm"}


def content_error_response(exc: ContentError) -> JSONResponse:
    status = 404 if isinstance(exc, NotFound) else 409 if isinstance(exc, (Immutable, ComingSoon)) else 422
    return JSONResponse({"error": exc.code, "detail": str(exc)}, status_code=status)


def svc(request: Request) -> ContentService:
    return request.app.state.content


def student_only(user: User = Depends(current_user)) -> User:
    if user.role != "student":
        raise HTTPException(403, {"error": "role_mismatch"})
    return user


def media_user(request: Request, t: str | None = None, gw: Gateway = Depends(get_gw),
               content: ContentService = Depends(svc)) -> User:
    """Bearer header, or `?t=` media token (asset and cover routes only)."""
    user = user_from_token(gw, bearer_token(request))
    if user is None and t:
        uid = content.verify_media_token(t)
        user = gw.users.get(uid) if uid else None
    if user is None:
        raise HTTPException(401, {"error": "unauthorized"}, headers={"WWW-Authenticate": "Bearer"})
    return user


def _etag_matches(request: Request, etag: str) -> bool:
    header = request.headers.get("if-none-match", "")
    return any(p.strip().removeprefix("W/").strip('"') == etag for p in header.split(",")) or header.strip() == "*"


def _cached(request: Request, body: bytes, media_type: str, etag: str, cache_control: str) -> Response:
    headers = {"ETag": f'"{etag}"', "Cache-Control": cache_control}
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type=media_type, headers=headers)


def _band(user: User, age_band: str | None, all_: bool) -> str | None:
    if all_ or user.role == "teacher":
        return age_band if not all_ else None
    return age_band or user.age_band


# ---------------------------------------------------------------- catalog and course page
@router.get("/catalog")
def catalog(request: Request, age_band: Annotated[str | None, AgeBandQ] = None, all_: int = Query(0, alias="all"),
            user: User = Depends(current_user), content: ContentService = Depends(svc)) -> Response:
    """Catalog filtered to the student's age band (or `age_band=`); `all=1` disables the filter."""
    cat = content.store.load_catalog()
    band = _band(user, age_band, bool(all_))
    cat = cat.model_copy(update={"courses": [c for c in cat.courses if band is None or c.age_band == band]})
    body = cat.model_dump_json().encode()
    return _cached(request, body, "application/json", sha256_bytes(body), "private, no-cache")


@router.get("/courses/{course_id}")
def course(course_id: str, user: User = Depends(current_user), content: ContentService = Depends(svc)) -> dict:
    return content.course_detail(course_id, teacher=content.is_teacher(user))


def _check_version(content: ContentService, user: User, course_id: str, version: int) -> None:
    content.ensure_available(course_id)  # 409 coming_soon for a placeholder
    meta = content.store.load_meta(course_id)
    info = content.store.version_info(meta, version)
    if info.status != "published" and not content.is_teacher(user):
        raise NotFound("version_not_found")  # 404, not 403: drafts are not revealed to students


@router.get("/courses/{course_id}/cover")
def cover(request: Request, course_id: str, v: str | None = None, user: User = Depends(media_user),
          content: ContentService = Depends(svc)) -> Response:
    """Cover image. `?v=<cover_sha256>` (from the catalog) makes the response cacheable for a year."""
    meta = content.store.load_meta(course_id)
    if meta.latest_published is None and meta.status == "live" and not content.is_teacher(user):
        raise NotFound("course_not_found")
    path = content.store.cover_path(course_id)
    data = path.read_bytes()
    sha = sha256_bytes(data)
    mime = MIME_FIX.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return _cached(request, data, mime, sha, IMMUTABLE if v == sha else "public, max-age=3600")


@router.get("/courses/{course_id}/versions/{version}/pack")
def pack(request: Request, course_id: str, version: int, user: User = Depends(current_user),
         content: ContentService = Depends(svc)) -> Response:
    _check_version(content, user, course_id, version)
    meta = content.store.load_meta(course_id)
    info = content.store.version_info(meta, version)
    raw = content.store.pack_bytes_raw(course_id, version)
    published = info.status == "published"
    return _cached(request, raw, "application/json", info.pack_sha256 or sha256_bytes(raw),
                   IMMUTABLE if published else "private, no-store")


@router.get("/courses/{course_id}/versions/{version}/assets/{path:path}")
def asset(request: Request, course_id: str, version: int, path: str, user: User = Depends(media_user),
          content: ContentService = Depends(svc)) -> Response:
    """The file with its mime type; `Range` is supported (video seeking)."""
    _check_version(content, user, course_id, version)
    file = content.store.asset_path(course_id, version, path)
    mime = MIME_FIX.get(file.suffix.lower()) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    published = content.published_version(course_id, version)
    return FileResponse(file, media_type=mime, headers={"Cache-Control": IMMUTABLE if published else "private, no-store",
                                                         "Accept-Ranges": "bytes",
                                                         "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post("/media-token")
def media_token(user: User = Depends(current_user), content: ContentService = Depends(svc)) -> dict:
    """Short-lived token for `?t=` on cover/asset URLs (use it in <video src>, <img src>, <audio src>)."""
    token, exp = content.mint_media_token(user)
    return {"token": token, "expires_at": exp.isoformat()}


# ---------------------------------------------------------------- search
@router.get("/search")
def search(q: str = Query(min_length=1, max_length=200), age_band: Annotated[str | None, AgeBandQ] = None,
           all_: int = Query(0, alias="all"),
           user: User = Depends(current_user), content: ContentService = Depends(svc)) -> dict:
    return content.search_courses(q, _band(user, age_band, bool(all_)))


@router.get("/search/suggest")
def search_suggest(q: str = Query(min_length=1, max_length=100), user: User = Depends(current_user),
                   content: ContentService = Depends(svc)) -> dict:
    """Autocomplete: courses, subjects and teachers whose name contains every word of `q` (accent-insensitive)."""
    return content.suggest(q)


# ---------------------------------------------------------------- catalog query (hs-03)
@router.get("/catalog/query")
def catalog_query(
    q: str = Query("", max_length=200),
    band: list[str] = Query(default=[]), subject: list[str] = Query(default=[]), language: list[str] = Query(default=[]),
    level: list[str] = Query(default=[]), duration: list[str] = Query(default=[]), media: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]), teacher: list[str] = Query(default=[]),
    sort: str = Query("rel", pattern="^(rel|new|pop|dur)$"), dir: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1, le=10000), page_size: int = Query(cq.PAGE_SIZE, ge=1, le=cq.MAX_PAGE_SIZE),
    user: User = Depends(current_user), content: ContentService = Depends(svc),
) -> dict:
    """Course catalog with search, filters, facet counts, sort and paging. A filter with several values matches any of
    them; different filters all have to match. `band` is not defaulted (the app sends the student's band)."""
    filters = {"band": set(band), "subject": set(subject), "language": set(language), "level": set(level),
               "duration": set(duration), "media": set(media), "status": set(status), "teacher": set(teacher)}
    return content.query_catalog(cq.Query(q=q.strip(), filters=filters, sort=sort, dir=dir, page=page, page_size=page_size))


# ---------------------------------------------------------------- enrollments
class EnrollBody(BaseModel):
    course_id: str


class QuizResult(BaseModel):
    item_id: str
    correct: bool
    seconds: float = Field(default=0, ge=0, le=36000)


class ProgressBody(BaseModel):
    lesson_id: str | None = None
    block_id: str | None = None
    completed_block_ids: list[str] = Field(default_factory=list, max_length=2000)
    quiz: QuizResult | None = None


@router.post("/enrollments")
def enroll(body: EnrollBody, user: User = Depends(student_only), content: ContentService = Depends(svc)) -> JSONResponse:
    view, created = content.enroll(user.id, body.course_id)
    return JSONResponse(view, status_code=201 if created else 200)


@router.get("/enrollments")
def enrollments(user: User = Depends(student_only), content: ContentService = Depends(svc)) -> list[dict]:
    return content.list_enrollments(user.id)


@router.put("/enrollments/{course_id}/progress")
def progress(course_id: str, body: ProgressBody, user: User = Depends(student_only),
             content: ContentService = Depends(svc)) -> dict:
    return content.update_progress(user.id, course_id, lesson_id=body.lesson_id, block_id=body.block_id,
                                   completed=body.completed_block_ids,
                                   quiz=body.quiz.model_dump() if body.quiz else None)


@router.delete("/enrollments/{course_id}", status_code=204)
def unenroll(course_id: str, user: User = Depends(student_only), content: ContentService = Depends(svc)) -> Response:
    if not content.delete_enrollment(user.id, course_id):
        raise NotFound("not_enrolled")
    return Response(status_code=204)
