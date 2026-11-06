"""ops.db tables of the practice engine (CONTRACTS 10.2). Imported by `context.py` before `create_all`.

New tables only (no migrations). A session stores a copy of the questions it serves (`items`), so it can be resumed
and reviewed after the bank changes. The learner's evidence itself lives in the workspace (`events.jsonl`); these rows
hold the session mechanics and the mastery history used for trend lines.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # p-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # practice | mock | diagnostic
    subject: Mapped[str] = mapped_column(String(32), index=True)
    # active | finished | expired (auto-finished at the deadline) | abandoned (no answers) | skipped (diagnostic)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # minutes, goal, topics, versions (assembler, scoring)
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{position, doc, topic, level, part, points_each, ...}]
    parts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    # events.jsonl + skills.md written to the mirror; false after a git failure so the next finish call retries
    evidence_done: Mapped[bool] = mapped_column(Boolean, default=False)


class PracticeAnswer(Base):
    __tablename__ = "practice_answers"

    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("practice_sessions.id", ondelete="CASCADE"),
                                            primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # checked answer (practice) or final (finished)
    draft: Mapped[str | None] = mapped_column(Text, nullable=True)  # mock/diagnostic: editable until finish
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)  # practice: answered and shown
    hints_seen: Mapped[int] = mapped_column(Integer, default=0)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent_sec: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = blank
    points: Mapped[float] = mapped_column(Float, default=0.0)
    statement_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class MasterySnapshot(Base):
    __tablename__ = "mastery_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(32), index=True)
    skill_id: Mapped[str] = mapped_column(String(128))
    mastery: Mapped[float] = mapped_column(Float)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ItemReport(Base):
    __tablename__ = "item_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | reviewed | fixed | dismissed
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
