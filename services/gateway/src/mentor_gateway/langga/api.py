"""Làng gà endpoints (CONTRACTS-LANGGA section 2). Students only; errors are `{"error": code}`."""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from mentor_gateway.api.ask import _read_input, ask_service, sse
from mentor_gateway.api.deps import get_gw, student_user
from mentor_gateway.ask.service import AskService
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.langga import subjects
from mentor_gateway.langga.chat import MEMORY_TURNS, ChatService
from mentor_gateway.langga.focus import FocusService
from mentor_gateway.langga.service import LanggaService

router = APIRouter(tags=["langga"], dependencies=[Depends(student_user)])


def village_svc(request: Request) -> LanggaService:
    return request.app.state.langga


def focus_svc(request: Request) -> FocusService:
    return request.app.state.focus


def chat_svc(request: Request) -> ChatService:
    return request.app.state.chat


class TakeBody(BaseModel):
    chicken: str = Field(max_length=16)


class FocusBody(BaseModel):
    minutes: int
    chicken: str = Field(max_length=16)


class FocusFinishBody(BaseModel):
    minutes_done: int = Field(ge=0, le=600)


@router.get("/village")
def village(user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> dict:
    return svc.village(user)


@router.get("/market")
def market(user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> dict:
    return svc.market(user)


@router.post("/chickens", status_code=201)
def take(body: TakeBody, user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> dict:
    return svc.take(user, body.chicken)


@router.delete("/chickens/{chicken}", status_code=204)
def let_go(chicken: str, user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> Response:
    svc.let_go(user, chicken)
    return Response(status_code=204)


@router.get("/chickens/{chicken}")
def chicken_page(chicken: str, user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> dict:
    return svc.chicken_page(user, chicken)


@router.get("/xp/week")
def xp_week(user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> dict:
    return svc.xp_week(user)


@router.get("/arena/papers")
def arena_papers(chicken: str | None = Query(None, max_length=16), year: int | None = Query(None, ge=1990, le=2100),
                 user: User = Depends(student_user), svc: LanggaService = Depends(village_svc)) -> list[dict]:
    return svc.arena(user, chicken, year)


@router.post("/focus")
def focus_start(body: FocusBody, user: User = Depends(student_user), svc: FocusService = Depends(focus_svc)) -> dict:
    return svc.start(user, body.minutes, body.chicken)


@router.get("/focus/active")
def focus_active(user: User = Depends(student_user), svc: FocusService = Depends(focus_svc)) -> dict | None:
    return svc.active(user)


class FocusPauseBody(BaseModel):
    ago_sec: int = Field(0, ge=0, le=3 * 3600)  # the tab went away this long ago (dates the pause back)


@router.post("/focus/{focus_id}/pause")
def focus_pause(focus_id: str, body: FocusPauseBody | None = None, user: User = Depends(student_user),
                svc: FocusService = Depends(focus_svc)) -> dict:
    return svc.pause(user, focus_id, body.ago_sec if body else 0)


@router.post("/focus/{focus_id}/resume")
def focus_resume(focus_id: str, user: User = Depends(student_user), svc: FocusService = Depends(focus_svc)) -> dict:
    return svc.resume(user, focus_id)


@router.post("/focus/{focus_id}/finish")
def focus_finish(focus_id: str, body: FocusFinishBody, user: User = Depends(student_user),
                 svc: FocusService = Depends(focus_svc)) -> dict:
    return svc.finish(user, focus_id, body.minutes_done)


def _check_chat_chicken(user: User, chicken: str) -> None:
    if chicken not in subjects.CHICKENS or not subjects.valid_for_band(chicken, user.age_band):
        raise HTTPException(404, {"error": "unknown_chicken"})


@router.post("/chat/{chicken}")
async def chat(chicken: str, request: Request, user: User = Depends(student_user), gw: Gateway = Depends(get_gw),
               svc: ChatService = Depends(chat_svc), ask: AskService = Depends(ask_service)) -> StreamingResponse:
    _check_chat_chicken(user, chicken)
    inp = await _read_input(request, user, gw)
    # A chicken chat keeps its memory per (user, chicken) in chat_turns; the thread id is only a label for the client, and the
    # Ask pipeline starts a fresh state for an id it does not know (so an id issued by a text turn is always accepted).
    if not (inp.text.strip() or inp.image or inp.audio or inp.action):
        raise HTTPException(422, {"error": "empty_question"})

    async def gen() -> AsyncIterator[bytes]:
        async for event, data in svc.stream(user, chicken, inp, ask):
            yield sse(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/chat/{chicken}/history")
def chat_history(chicken: str, limit: int = Query(MEMORY_TURNS, ge=1, le=MEMORY_TURNS),
                 user: User = Depends(student_user), svc: ChatService = Depends(chat_svc)) -> list[dict]:
    _check_chat_chicken(user, chicken)
    return svc.history(user.id, chicken, limit)
