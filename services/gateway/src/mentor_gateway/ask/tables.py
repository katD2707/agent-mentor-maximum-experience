"""ops.db table of the Q&A: one compact row per thread (no long-term chat memory; old rows are pruned)."""

from datetime import datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class AskThread(Base):
    __tablename__ = "ask_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # a-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # {history: [{role, text}] (last 8), problems: [...], problem: {...}|None, solution: {...}|None, revealed: bool}
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class NotesSet(Base):
    """Review questions written from a learner's photographed class notes (CONTRACTS 16.4)."""

    __tablename__ = "ask_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # n-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(80), default="")
    pages: Mapped[int] = mapped_column(Integer, default=1)
    items: Mapped[list] = mapped_column(JSON, default=list)  # QuizItem dicts (with the answer keys; never sent as is)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
