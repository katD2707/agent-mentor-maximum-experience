"""Workspace, uploads, activity and reports. Every read comes from the mirror (works while the sandbox sleeps)."""

import asyncio
import io
import json
import mimetypes
import re
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from mentor_schemas import ActivityEntry, Profile, WorkspacePaths
from pydantic import BaseModel

from mentor_gateway.api.deps import active_user, get_gw, provisioned_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import SentReport, UploadToken, User
from mentor_gateway.mirror import StaleBaseError, normalize_path
from mentor_gateway.security import hash_token, new_token

router = APIRouter(tags=["workspace"])

USER_EDITABLE_DIRS = ("me", "goals", "learning", "research")
MAX_UPLOAD_BYTES = 25_000_000


def _norm(path: str) -> str:
    try:
        return normalize_path(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def is_user_editable(path: str) -> bool:
    """Web edits are allowed only under me/, goals/, learning/, research/ (CONTRACTS.md section 5)."""
    parts = path.split("/")
    return len(parts) >= 2 and parts[0] in USER_EDITABLE_DIRS


def is_visible(path: str) -> bool:
    """`.mentor/` (skills, wellbeing, parent-report drafts...) is hidden from the viewer except the activity log."""
    if path == WorkspacePaths.MENTOR_DIR or path == WorkspacePaths.ACTIVITY:
        return True
    return not path.startswith((".mentor/", ".git"))


def _exportable(path: str) -> bool:
    """The export zip has the whole workspace except unsent parent-report drafts (learners see reports once sent)."""
    return not (path == WorkspacePaths.REPORT_DRAFTS_DIR or path.startswith(WorkspacePaths.REPORT_DRAFTS_DIR + "/"))


def _filter_zip(data: bytes) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if _exportable(info.filename.rstrip("/")):
                dst.writestr(info, src.read(info))
    return buf.getvalue()


# ---- tree / file / history / export --------------------------------------------------------------


@router.get("/workspace/tree")
async def tree(prefix: str = "", user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    pre = _norm(prefix.rstrip("/")) if prefix.strip("/") else ""
    entries, modified = await asyncio.gather(
        asyncio.to_thread(gw.mirror.ls_tree, user.id), asyncio.to_thread(gw.mirror.last_modified, user.id)
    )
    dir_mtime: dict[str, datetime] = {}
    for path, ts in modified.items():
        parts = path.split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d not in dir_mtime or ts > dir_mtime[d]:
                dir_mtime[d] = ts
    out = []
    for e in entries:
        if not is_visible(e.path):
            continue
        if pre and not (e.path == pre or e.path.startswith(pre + "/")):
            continue
        ts = modified.get(e.path) if e.type == "file" else dir_mtime.get(e.path)
        out.append({"path": e.path, "type": e.type, "size": e.size, "modified_at": ts.isoformat() if ts else None})
    return out


@router.get("/workspace/file")
async def read_file(path: str, user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> dict:
    p = _norm(path)
    if not is_visible(p):
        raise HTTPException(404, "not found")
    got = await asyncio.to_thread(gw.mirror.read, user.id, p)
    if got is None:
        raise HTTPException(404, "not found")
    data, sha = got
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "binary file; use /workspace/raw") from exc
    return {"path": p, "content": content, "sha": sha}


@router.get("/workspace/raw")
async def read_raw(path: str, user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> Response:
    p = _norm(path)
    if not is_visible(p):
        raise HTTPException(404, "not found")
    got = await asyncio.to_thread(gw.mirror.read, user.id, p)
    if got is None:
        raise HTTPException(404, "not found")
    mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
    return Response(got[0], media_type=mime)


class FileWrite(BaseModel):
    path: str
    content: str
    base_sha: str | None = None


def _conflict(exc: StaleBaseError) -> JSONResponse:
    return JSONResponse({"detail": "Tệp đã thay đổi kể từ lúc bạn mở. Hãy tải lại.", "current_sha": exc.current_sha},
                        status_code=409)


def _check_editable(p: str) -> None:
    if not is_user_editable(p):
        raise HTTPException(403, "only me/, goals/, learning/ and research/ can be edited")


@router.put("/workspace/file", response_model=None)
async def write_file(body: FileWrite, user: User = Depends(active_user),
                     gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    p = _norm(body.path)
    _check_editable(p)
    data = body.content.encode("utf-8")
    try:
        await asyncio.to_thread(
            gw.mirror.commit_files, user.id, {p: data}, author="user", message=f"Người học sửa {p}",
            expected={p: body.base_sha},
        )
    except StaleBaseError as exc:
        return _conflict(exc)
    sha = await asyncio.to_thread(gw.mirror.blob_sha, user.id, p)
    return {"sha": sha}


@router.delete("/workspace/file", response_model=None)
async def delete_file(path: str, base_sha: str | None = None, user: User = Depends(active_user),
                      gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    p = _norm(path)
    _check_editable(p)
    current = await asyncio.to_thread(gw.mirror.blob_sha, user.id, p)
    if current is None:
        raise HTTPException(404, "not found")
    try:
        await asyncio.to_thread(
            gw.mirror.commit_files, user.id, {p: None}, author="user", message=f"Người học xóa {p}",
            expected={p: base_sha or current},
        )
    except StaleBaseError as exc:
        return _conflict(exc)
    return {"ok": True}


@router.get("/workspace/history")
async def history(path: str | None = None, limit: int = Query(100, le=500), user: User = Depends(provisioned_user),
                  gw: Gateway = Depends(get_gw)) -> list[dict]:
    p = _norm(path) if path else None
    if p is not None and not is_visible(p):
        raise HTTPException(404, "not found")
    commits = await asyncio.to_thread(gw.mirror.history, user.id, p, limit)
    return [{"sha": c.sha, "author": c.author, "ts": c.ts.isoformat(), "message": c.message} for c in commits]


@router.get("/workspace/export")
async def export(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> Response:
    data = await asyncio.to_thread(lambda: _filter_zip(gw.mirror.archive_zip(user.id)))
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="mentor-workspace.zip"'})


# ---- activity / reports --------------------------------------------------------------------------


@router.get("/activity")
async def activity(limit: int = Query(50, ge=1, le=500), before: datetime | None = None,
                   user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    text = await asyncio.to_thread(gw.mirror.read_text, user.id, WorkspacePaths.ACTIVITY) or ""
    entries: list[ActivityEntry] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entries.append(ActivityEntry.model_validate(json.loads(line)))
        except ValueError:
            continue
    if before is not None:
        b = before if before.tzinfo else before.replace(tzinfo=ZoneInfo("UTC"))
        entries = [e for e in entries if _aware(e.ts) < b]
    entries.sort(key=lambda e: _aware(e.ts), reverse=True)
    return [e.model_dump(mode="json") for e in entries[:limit]]


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=ZoneInfo("UTC"))


@router.get("/reports")
async def reports(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    if user.role != Profile.THPT.value:
        return []
    entries = await asyncio.to_thread(gw.mirror.ls_tree, user.id)
    with gw.db.session() as s:
        sent = {r.path: r.sent_at for r in s.query(SentReport).filter(SentReport.user_id == user.id)}
    out = []
    for e in entries:
        # only reports the gateway actually delivered (drafts live hidden in .mentor/report-drafts/)
        if e.type != "file" or not re.fullmatch(r"reports/[^/]+\.md", e.path) or e.path not in sent:
            continue
        text = await asyncio.to_thread(gw.mirror.read_text, user.id, e.path) or ""
        fm: dict = {}
        if text.startswith("---"):
            try:
                fm = yaml.safe_load(text.split("---", 2)[1]) or {}
            except (yaml.YAMLError, IndexError):
                fm = {}
        sent_at = sent.get(e.path)
        out.append({
            "path": e.path,
            "period_start": str(fm.get("period_start")) if fm.get("period_start") else None,
            "period_end": str(fm.get("period_end")) if fm.get("period_end") else None,
            "sent_at": sent_at.isoformat() if sent_at else None,
        })
    out.sort(key=lambda r: r["path"], reverse=True)
    return out


# ---- uploads -------------------------------------------------------------------------------------


def _safe_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.") or "file"
    return base[:100]


async def _save_upload(gw: Gateway, user: User, file: UploadFile) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large")
    stamp = gw.clock().astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d-%H%M%S")
    path = f"{WorkspacePaths.INBOX_DIR}/{stamp}-{_safe_name(file.filename or 'file')}"
    mime = file.content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    await asyncio.to_thread(gw.mirror.commit_files, user.id, {path: data}, author="user",
                            message=f"Tải lên {path}")
    return {"path": path, "mime_type": mime}


@router.post("/uploads")
async def upload(file: UploadFile = File(...), user: User = Depends(active_user), gw: Gateway = Depends(get_gw)) -> dict:
    return await _save_upload(gw, user, file)


@router.post("/uploads/mobile-token")
def mobile_token(user: User = Depends(active_user), gw: Gateway = Depends(get_gw)) -> dict:
    token = new_token()
    expires = gw.clock() + timedelta(minutes=gw.settings.mobile_token_minutes)
    with gw.db.session() as s:
        s.add(UploadToken(token_hash=hash_token(token), user_id=user.id, expires_at=expires))
    # the web app's /m/{token} page (no session) posts the file to POST /api/m/{token}
    return {"upload_url": f"{gw.settings.web_url}/m/{token}", "expires_at": expires.isoformat()}


def _token_user(gw: Gateway, token: str) -> User:
    with gw.db.session() as s:
        row = s.get(UploadToken, hash_token(token))
        if row is None or row.expires_at <= gw.clock():
            raise HTTPException(404, "link expired")
        user = s.get(User, row.user_id)
    if user is None or gw.users.onboarding_state(user) != "active":
        raise HTTPException(404, "link expired")
    return user


_MOBILE_PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Gửi ảnh cho mentor</title>
<style>body{font-family:system-ui,sans-serif;margin:24px;max-width:480px}button{font-size:1.1em;padding:10px 18px}</style>
</head><body><h2>Gửi ảnh cho mentor</h2>
<form method="post" enctype="multipart/form-data"><p><input type="file" name="file" accept="image/*,application/pdf"
capture="environment" required></p><p><button type="submit">Gửi</button></p></form></body></html>"""


@router.get("/m/{token}", response_class=HTMLResponse)
def mobile_page(token: str, gw: Gateway = Depends(get_gw)) -> str:
    _token_user(gw, token)
    return _MOBILE_PAGE


@router.post("/m/{token}")
async def mobile_upload(token: str, file: UploadFile = File(...), gw: Gateway = Depends(get_gw)) -> dict:
    user = _token_user(gw, token)
    saved = await _save_upload(gw, user, file)
    await gw.hub.send(user.id, {"type": "upload_received", "path": saved["path"], "mime_type": saved["mime_type"]})
    return {"path": saved["path"]}
