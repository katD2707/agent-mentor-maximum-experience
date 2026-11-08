"""`/api/events`, `/api/today`, `/api/plan/week`, `/api/reminders` (CONTRACTS section 12). Students only."""

import asyncio
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import get_gw, student_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.planner import events as ev

router = APIRouter(tags=["planner"])


class EventIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)  # client event id: the batch is idempotent on it
    kind: Literal["app_open", "session_start", "session_end", "focus_tick", "lesson_progress", "video_watch",
                  "quiz_answer", "reminder_outcome", "ask_question", "ask_course_open"]
    ts: datetime
    data: dict[str, Any] = {}


class EventsBody(BaseModel):
    events: list[EventIn] = Field(..., max_length=ev.MAX_BATCH)


@router.post("/events")
def post_events(body: EventsBody, user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> dict:
    return ev.ingest(gw.db, user.id, [e.model_dump() for e in body.events], gw.clock())


@router.get("/today")
async def today(user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> dict:
    return await asyncio.to_thread(gw.planner.today_view, user)


@router.get("/plan/week")
async def plan_week(user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> dict:
    return await asyncio.to_thread(gw.planner.week_view, user)


@router.get("/reminders")
async def reminders(since: datetime | None = Query(None), user: User = Depends(student_user),
                    gw: Gateway = Depends(get_gw)) -> dict:
    return await asyncio.to_thread(gw.planner.reminders_view, user, since)


class OutcomeBody(BaseModel):
    outcome: Literal["opened", "ignored", "snoozed"]


@router.post("/reminders/{reminder_id}/outcome")
def reminder_outcome(reminder_id: str, body: OutcomeBody, user: User = Depends(student_user),
                     gw: Gateway = Depends(get_gw)) -> dict:
    if not gw.planner.record_outcome(user, reminder_id, body.outcome):
        raise HTTPException(404, {"error": "reminder_not_found"})
    return {"ok": True}
