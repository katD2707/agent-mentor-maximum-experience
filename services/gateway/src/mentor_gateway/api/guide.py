"""`/api/guide`: Mực's chat about using the app (any signed-in user; the guide map is not private)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mentor_gateway.api.ask import ask_service
from mentor_gateway.api.deps import current_user
from mentor_gateway.ask import guide
from mentor_gateway.ask.service import AskService
from mentor_gateway.db import User

router = APIRouter(tags=["guide"])


class GuideBody(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    lang: str | None = None
    screen: str | None = Field(default=None, max_length=64)
    visible_keys: list[str] = Field(default_factory=list, max_length=40)


@router.post("/guide")
async def guide_chat(body: GuideBody, user: User = Depends(current_user), svc: AskService = Depends(ask_service)) -> dict:
    lang = body.lang or user.language or "vi"
    return {"answer": await guide.answer(svc.llm, body.question, lang, body.screen, [k[:40] for k in body.visible_keys])}
