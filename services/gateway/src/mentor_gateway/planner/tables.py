"""ops.db tables of the planner (new tables only; `create_all` picks them up). Imported by `context.py`."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class BehaviourEvent(Base):
    """Layer 1 (3.7): one compact row per client event; `client_id` makes batches idempotent."""

    __tablename__ = "behaviour_events"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class StudyGoal(Base):
    """A goal: `student` (typed by the student) or `inferred` (one per enrolled course, auto-maintained)."""

    __tablename__ = "study_goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # student | inferred
    title: Mapped[str] = mapped_column(String(200))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    course_ids: Mapped[list] = mapped_column(JSON, default=list)  # explicit links; student goals also match by text
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)  # inferred goal the student deleted
    source: Mapped[str] = mapped_column(String(10), default="learning")  # learning | research (CONTRACTS 15.8)
    milestones: Mapped[list] = mapped_column(JSON, default=list)  # research goal only: deadlines and thesis milestones
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class PlanRecord(Base):
    """The latest plan of a learner (one row), the history of moves and the scheduler's bookkeeping."""

    __tablename__ = "study_plans"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(12))  # llm | fallback
    trigger: Mapped[str] = mapped_column(String(32))
    plan: Mapped[dict] = mapped_column(JSON, default=dict)  # {items, reminders, goals, week_note_vi, week_note_en}
    moves: Mapped[list] = mapped_column(JSON, default=list)  # [{at, trigger, date, reason_vi, reason_en}], newest last
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # {course_ids, practice_sig, handled_missed: [..]}
    dirty: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pending trigger, run by the scheduler
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # why the LLM result was not used, if so


class Reminder(Base):
    """A reminder the device schedules locally (GET /api/reminders). Rows of an older plan are `cancelled`."""

    __tablename__ = "study_reminders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # r-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    kind: Mapped[str] = mapped_column(String(8))  # study | break | nudge | research
    text_vi: Mapped[str] = mapped_column(String(300))
    text_en: Mapped[str] = mapped_column(String(300))
    deep_link: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled | cancelled | skipped_quiet | pushed
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)  # opened | ignored | snoozed
    outcome_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
