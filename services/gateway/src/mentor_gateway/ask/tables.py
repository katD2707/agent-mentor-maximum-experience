"""ops.db table of the Q&A: one compact row per thread (no long-term chat memory; old rows are pruned)."""

from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class AskThread(Base):
    __tablename__ = "ask_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # a-<hex>
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # {history: [{role, text}] (last 8), problems: [...], problem: {...}|None, solution: {...}|None, revealed: bool}
    state: Mapped[dict] = mapped_column(JSON, default=dict)
