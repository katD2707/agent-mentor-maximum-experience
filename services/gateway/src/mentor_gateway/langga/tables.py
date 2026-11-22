"""ops.db tables of Làng gà (new tables only; `create_all` picks them up). Imported by `context.py`."""

from datetime import datetime

from sqlalchemy import JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class UserChicken(Base):
    """A chicken the student took. Letting it go keeps the row (`let_go_at`) and the XP in the ledger."""

    __tablename__ = "user_chickens"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chicken: Mapped[str] = mapped_column(String(16), primary_key=True)
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime)
    let_go_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LanggaState(Base):
    """Per-student one-off flags (the first-/village migration from enrollments)."""

    __tablename__ = "langga_state"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    migrated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class XpEvent(Base):
    """The XP ledger. UNIQUE(user_id, source, ref) makes every award idempotent."""

    __tablename__ = "xp_events"
    __table_args__ = (UniqueConstraint("user_id", "source", "ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    chicken: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class FocusSession(Base):
    """A study-room session (lg-06)."""

    __tablename__ = "focus_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # f-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    chicken: Mapped[str] = mapped_column(String(16))
    minutes: Mapped[int] = mapped_column(Integer)  # planned
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | finished | abandoned
    minutes_done: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ChatTurn(Base):
    """One message of the chat with a chicken; the last 30 per (user, chicken) are kept."""

    __tablename__ = "chat_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    chicken: Mapped[str] = mapped_column(String(16), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
