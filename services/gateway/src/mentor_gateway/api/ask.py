"""`/api/ask`: Q&A as a Server-Sent Events stream (CONTRACTS "Q&A and guide"). Students only (teachers get 403 role_mismatch)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from mentor_gateway.api.deps import get_gw, student_user
from mentor_gateway.ask.llm import RouterChatLLM
from mentor_gateway.ask.service import AskInput, AskService
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.mirror import normalize_path

router = APIRouter(tags=["ask"])

MAX_IMAGE_BYTES = 15_000_000
MAX_AUDIO_BYTES = 10_000_000
AUDIO_FORMATS = {"wav", "mp3", "webm", "ogg", "m4a", "mp4", "aac", "flac"}


def build_llm(gw: Gateway) -> RouterChatLLM | None:
    s = gw.settings
    return RouterChatLLM(s.model_router_url, s.model_router_key) if s.model_router_url else None


def ask_service(request: Request, gw: Gateway = Depends(get_gw)) -> AskService:
    """Built on first use from the settings; tests replace `app.state.ask`."""
    svc = getattr(request.app.state, "ask", None)
    if svc is None:
        svc = request.app.state.ask = AskService(request.app.state.content, gw.db, gw.clock, build_llm(gw))
    return svc


def _audio_format(name: str | None, mime: str | None) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if name and "." in name else ""
    if ext in AUDIO_FORMATS:
        return ext
    sub = (mime or "").split(";")[0].split("/")[-1].lower().replace("x-", "").replace("mpeg", "mp3").replace("wave", "wav")
    return sub if sub in AUDIO_FORMATS else "wav"


async def _read_input(request: Request, user: User, gw: Gateway) -> AskInput:
    ctype = request.headers.get("content-type", "")
    inp = AskInput(lang=user.language or "vi")
    if ctype.startswith(("multipart/", "application/x-www-form-urlencoded")):
        form = await request.form()
        data: dict[str, Any] = {k: form.get(k) for k in ("text", "thread_id", "lang", "action", "problem_id", "image_upload_id")}
        image, audio = form.get("image"), form.get("audio")
        if image is not None and hasattr(image, "read"):
            inp.image = await image.read(MAX_IMAGE_BYTES + 1)
        if audio is not None and hasattr(audio, "read"):
            inp.audio = await audio.read(MAX_AUDIO_BYTES + 1)
            inp.audio_format = _audio_format(getattr(audio, "filename", None), getattr(audio, "content_type", None))
    else:
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(422, {"error": "bad_request"}) from None
        if not isinstance(data, dict):
            raise HTTPException(422, {"error": "bad_request"})
    inp.text = str(data.get("text") or "")[:4000]
    inp.thread_id = data.get("thread_id") or None
    inp.lang = str(data.get("lang") or inp.lang)
    inp.action = data.get("action") or None
    inp.problem_id = data.get("problem_id") or None
    upload = data.get("image_upload_id")
    if upload and inp.image is None:  # the `path` returned by POST /api/uploads
        try:
            p = normalize_path(str(upload))
        except ValueError:
            raise HTTPException(422, {"error": "bad_upload_id"}) from None
        got = await asyncio.to_thread(gw.mirror.read, user.id, p)
        if got is None:
            raise HTTPException(404, {"error": "upload_not_found"})
        inp.image = got[0]
    if (inp.image and len(inp.image) > MAX_IMAGE_BYTES) or (inp.audio and len(inp.audio) > MAX_AUDIO_BYTES):
        raise HTTPException(413, {"error": "file_too_large"})
    return inp


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/ask")
async def ask(request: Request, user: User = Depends(student_user), gw: Gateway = Depends(get_gw),
              svc: AskService = Depends(ask_service)) -> StreamingResponse:
    inp = await _read_input(request, user, gw)
    if inp.thread_id and await asyncio.to_thread(svc.load_thread, user.id, inp.thread_id) is None:
        raise HTTPException(404, {"error": "thread_not_found"})
    if not (inp.text.strip() or inp.image or inp.audio or inp.action):
        raise HTTPException(422, {"error": "empty_question"})

    async def gen() -> AsyncIterator[bytes]:
        async for event, data in svc.stream(user, inp):
            yield sse(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
