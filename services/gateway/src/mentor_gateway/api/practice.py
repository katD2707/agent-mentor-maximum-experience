"""`/api/practice`: practice, mock exams, diagnostics, progress (CONTRACTS section 10.3). THPT learners only.

Handlers are plain `def`: the engine reads git and SQLite, so FastAPI runs them in its thread pool. Errors are
`{detail, code, ...}` (`PracticeError`); NCS learners get 403.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import get_gw, provisioned_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.practice import PracticeError, PracticeService


def thpt_user(user: User = Depends(provisioned_user)) -> User:
    if user.role != "thpt":
        raise HTTPException(403, "Luyện tập và thi thử hiện chỉ dành cho học sinh THPT.")
    return user


def svc(gw: Gateway = Depends(get_gw)) -> PracticeService:
    if gw.practice is None:
        raise HTTPException(503, "practice unavailable")
    return gw.practice


router = APIRouter(prefix="/practice", tags=["practice"], dependencies=[Depends(thpt_user)])


class PreviewBody(BaseModel):
    subject: str
    minutes: int = 20
    goal: Literal["balanced", "weak", "challenge"] = "balanced"
    topics: list[str] | None = None
    seed: int | None = None
    include_above_grade: bool = False  # the learner opts in to topics above their grade


class StartBody(PreviewBody):
    kind: Literal["practice", "mock", "diagnostic"]
    profile_id: str | None = None


class SubjectBody(BaseModel):
    subject: str


class AnswerBody(BaseModel):
    position: int = Field(ge=0)
    answer: str | None = Field(default=None, max_length=200)
    time_spent_sec: int = Field(default=0, ge=0)


class PositionBody(BaseModel):
    position: int = Field(ge=0)


class FlagBody(PositionBody):
    flagged: bool


class TickBody(PositionBody):
    elapsed_sec: int = Field(default=0, ge=0)


class ReportBody(BaseModel):
    session_id: str
    reason: Literal["wrong_key", "wrong_solution", "unclear", "typo", "other"]
    note: str | None = Field(default=None, max_length=500)


def error_response(exc: PracticeError) -> JSONResponse:
    return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status)


@router.get("/subjects")
def subjects(user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> list[dict]:
    return p.subjects(user.id)


@router.post("/preview")
def preview(body: PreviewBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.preview(user.id, body.subject, body.minutes, body.goal, body.topics, body.seed, body.include_above_grade)


@router.post("/sessions")
def start(body: StartBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.start(user.id, body.model_dump())


@router.post("/diagnostic/skip")
def skip_diagnostic(body: SubjectBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    p.skip_diagnostic(user.id, body.subject)
    return {"ok": True}


@router.get("/sessions/active")
def active(subject: str | None = None, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict | None:
    return p.active(user.id, subject)


@router.get("/sessions")
def sessions(subject: str | None = None, limit: int = Query(30, ge=1, le=100), user: User = Depends(thpt_user),
             p: PracticeService = Depends(svc)) -> list[dict]:
    return p.history(user.id, subject, limit)


@router.get("/sessions/{sid}")
def get_session(sid: str, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.get(user.id, sid)


@router.post("/sessions/{sid}/answer")
def answer(sid: str, body: AnswerBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.answer(user.id, sid, body.position, body.answer, body.time_spent_sec)


@router.post("/sessions/{sid}/hint")
def hint(sid: str, body: PositionBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.hint(user.id, sid, body.position)


@router.post("/sessions/{sid}/reveal")
def reveal(sid: str, body: PositionBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.reveal(user.id, sid, body.position)


@router.post("/sessions/{sid}/flag")
def flag(sid: str, body: FlagBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.flag(user.id, sid, body.position, body.flagged)


@router.post("/sessions/{sid}/tick")
def tick(sid: str, body: TickBody, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.tick(user.id, sid, body.position, body.elapsed_sec)


@router.post("/sessions/{sid}/finish")
def finish(sid: str, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.finish(user.id, sid)


@router.get("/sessions/{sid}/review")
def review(sid: str, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> list[dict]:
    return p.review(user.id, sid)


@router.get("/progress")
def progress(subject: str | None = None, user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> dict:
    return p.progress(user.id, subject)


@router.get("/recommendations")
def recommendations(subject: str | None = None, user: User = Depends(thpt_user),
                    p: PracticeService = Depends(svc)) -> list[dict]:
    return p.recommendations(user.id, subject)


@router.get("/items/reports")
def item_reports(user: User = Depends(thpt_user), p: PracticeService = Depends(svc)) -> list[dict]:
    return p.list_reports(user.id)


@router.post("/items/{item_id}/report")
def report_item(item_id: str, body: ReportBody, user: User = Depends(thpt_user),
                p: PracticeService = Depends(svc)) -> dict:
    return p.report_item(user.id, item_id, body.session_id, body.reason, body.note)
