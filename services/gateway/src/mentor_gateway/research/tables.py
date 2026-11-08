"""ops.db tables of the Nghiên cứu feature (CONTRACTS section 15.10). Imported by `context.py` so `create_all` sees them.

Every row is scoped by `user_id`. The two source keys live in `research_profile` sealed with the master key
(`crypto.SecretBox`, aad `research-key:<user>:<source>`); no endpoint, log line or model prompt ever carries them.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.db import Base, UTCDateTime


class ResearchProfileRow(Base):
    __tablename__ = "research_profile"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    question: Mapped[str] = mapped_column(String(300), default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    advisor_name: Mapped[str] = mapped_column(String(100), default="")
    asta_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # sealed, write-only
    s2_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # sealed, write-only
    discovery_last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    discovery_last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class PaperRow(Base):
    __tablename__ = "paper"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(200))  # arxiv:<id> | doi:<doi> | s2:<id> | up:<hash> (uploads)
    arxiv_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    s2_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str] = mapped_column(Text, default="")
    tldr: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    upload_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fulltext_state: Mapped[str] = mapped_column(String(10), default="none")  # none | indexing | ready
    source: Mapped[str] = mapped_column(String(8), default="arxiv")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ReadingEntryRow(Base):
    __tablename__ = "reading_entry"

    paper_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(8), default="new")  # new | reading | read
    reason: Mapped[str] = mapped_column(String(400), default="")
    origin: Mapped[str] = mapped_column(String(12), default="search")
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0)
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class PaperNoteRow(Base):
    __tablename__ = "paper_note"

    paper_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    thesis_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)


class PaperQARow(Base):
    __tablename__ = "paper_qa"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    not_found_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    course_hint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ExperimentRow(Base):
    __tablename__ = "experiment"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # EXP-yyyy-mm-dd-a: unique per user, so the key is (user_id, id)
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="done")
    aim: Mapped[str] = mapped_column(Text, default="")
    setup: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    user_note: Mapped[str] = mapped_column(Text, default="")
    next: Mapped[str] = mapped_column(Text, default="")
    commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MeetingRow(Base):
    __tablename__ = "meeting"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    title: Mapped[str] = mapped_column(String(100), default="Họp GVHD")
    status: Mapped[str] = mapped_column(String(10), default="scheduled")
    agenda: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SuggestionRow(Base):
    __tablename__ = "suggestion"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    paper_id: Mapped[str] = mapped_column(String(32), index=True)
    week_of: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(400), default="")
    query: Mapped[str] = mapped_column(String(300), default="")
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted | dismissed
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
