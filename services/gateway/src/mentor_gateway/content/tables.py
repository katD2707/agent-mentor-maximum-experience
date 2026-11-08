"""ops.db table for course enrollments (new table only; `create_all` picks it up)."""

from datetime import datetime

from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class Enrollment(Base):
    """A student's enrollment, pinned to a published version (CONTRACTS "Courses and content")."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    course_id: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)  # pinned published version
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_lesson_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_block_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    completed_block_ids: Mapped[list] = mapped_column(JSON, default=list)
    quiz: Mapped[dict] = mapped_column(JSON, default=dict)  # item_id -> {correct, seconds, attempts}
