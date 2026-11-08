"""Append-only learning evidence (plan sections 6.1, 7.3)."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceMode(str, Enum):
    INDEPENDENT = "independent"  # no hints; counts toward mastery
    GUIDED = "guided"  # with hints; recorded as process only, not mastery
    CLASSROOM_GRADED = "classroom_graded"  # scanned test graded by a teacher; counts toward mastery


class LearningEvent(BaseModel):
    """One line of events.jsonl."""

    event_id: str
    ts: datetime
    type: Literal["problem_attempt", "graded_work_ingested", "practice_item"]
    subject: str = Field(examples=["math"])
    skill_ids: list[str] = Field(examples=[["algebra.quadratic.formula"]])
    correct: bool
    mode: EvidenceMode
    hint_count: int = 0
    source_ref: str = Field(description="Workspace path of the evidence, e.g. learning/evidence/2026-10-25-kiem-tra-15p.md")
    grader: Literal["sympy", "teacher", "model", "bank"] = "model"
    schema_version: int = 1
