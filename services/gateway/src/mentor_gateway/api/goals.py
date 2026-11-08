"""`/api/goals` (CONTRACTS section 12): inferred goals (one per enrolled course) and the student's own."""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import get_gw, student_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import User

router = APIRouter(tags=["goals"])


class GoalIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    deadline: date | None = None
    course_ids: list[str] = Field(default=[], max_length=20)


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    deadline: date | None = None
    course_ids: list[str] | None = Field(default=None, max_length=20)


@router.get("/goals")
async def list_goals(user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    return await asyncio.to_thread(gw.planner.goal_views, user)


@router.post("/goals", status_code=201)
async def create_goal(body: GoalIn, user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> dict:
    return await asyncio.to_thread(gw.planner.create_goal, user, body.title, body.deadline, body.course_ids)


@router.patch("/goals/{goal_id}")
async def patch_goal(goal_id: str, body: GoalPatch, user: User = Depends(student_user),
                     gw: Gateway = Depends(get_gw)) -> dict:
    out = await asyncio.to_thread(gw.planner.update_goal, user, goal_id, body.model_dump(exclude_unset=True))
    if out is None:
        raise HTTPException(404, {"error": "goal_not_found"})
    return out


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: str, user: User = Depends(student_user), gw: Gateway = Depends(get_gw)) -> Response:
    if not await asyncio.to_thread(gw.planner.delete_goal, user, goal_id):
        raise HTTPException(404, {"error": "goal_not_found"})
    return Response(status_code=204)
