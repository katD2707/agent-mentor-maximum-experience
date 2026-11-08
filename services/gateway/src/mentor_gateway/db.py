"""Ops database: accounts, login tokens, audit, schedules, outbox, notifications, practice tables.

No learner content lives here; the workspace is the source of truth about the learner.
SQLite in dev; the schema avoids SQLite-only features so Postgres works with the same models.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

log = logging.getLogger(__name__)


# Columns added after first release (Nghiên cứu, CONTRACTS 15.8): study_goals.source / milestones
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "study_goals": [("source", "VARCHAR(10) NOT NULL DEFAULT 'learning'"), ("milestones", "JSON")],
}


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetimes stored as UTC (SQLite drops tzinfo; Postgres keeps it)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Seeded accounts only (no sign-up). Roles: student | teacher (CONTRACTS section 4)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # student | teacher
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))  # "scrypt$n$r$p$salt$hash" (security.hash_password)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    # Legacy cache of the band (column kept so old databases stay valid); never read. `age_band` below is derived.
    age_band_cache: Mapped[str | None] = mapped_column("age_band", String(8), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set once at first run (admin CLI fixes it)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)  # vi | en
    theme: Mapped[str] = mapped_column(String(8), default="system")  # light | dark | system
    quiet_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # no notifications before this
    provisioned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # learner workspace created
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @property
    def age_band(self) -> str | None:
        """g1_5 | g6_9 | g10_12 | uni, derived from `birth_year` and today's date (September school year)."""
        from mentor_gateway.age import band_for_birth_year

        return band_for_birth_year(self.birth_year)


class WebSession(Base):
    """A login token (only its hash is stored). Table name kept from the cookie era."""

    __tablename__ = "web_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AuditRow(Base):
    """Content-free audit trail (e.g. which notification action was applied). Never exposed through any endpoint."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")  # no learner content
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class UserDataKey(Base):
    """Per-user 32-byte data key (encrypts that user's backups), sealed with the master key (aad "user-key:<id>").

    Deleting the row on account deletion crypto-shreds every backup of the user.
    """

    __tablename__ = "user_keys"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sealed_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class BackupState(Base):
    """Mirror head at the last snapshot, so unchanged mirrors are skipped."""

    __tablename__ = "backup_state"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_head: Mapped[str] = mapped_column(String(64))
    last_snapshot: Mapped[str] = mapped_column(String(64))


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(128), default="")  # routine:<id> | next_wake | email | api
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|running|ok|error|skipped
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RoutineSchedule(Base):
    __tablename__ = "routine_schedule"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    routine_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cron: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64))
    next_run_at: Mapped[datetime] = mapped_column(UTCDateTime)


class NotificationRow(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | delivered | dropped
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class NotificationMeta(Base):
    """Rich fields of a notification ("nudge", CONTRACTS section 9), 1:1 with `notifications`.

    A separate table (not columns on `notifications`) so existing databases pick it up via `create_all`. Rows written
    before it existed have no meta: they read as kind "nudge" with body = text and no actions.
    """

    __tablename__ = "notification_meta"

    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="nudge")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSON, default=list)  # [{id, label}], at most 3
    mascot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prefill: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="agent")  # agent | gateway:<routine id>
    push_safe: Mapped[bool] = mapped_column(Boolean, default=False)  # title/body are fixed templates (lock screen ok)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # snooze
    cap_exempt: Mapped[bool] = mapped_column(Boolean, default=False)  # deadline, focus_end, snoozed re-delivery
    deliveries: Mapped[int] = mapped_column(Integer, default=0)
    channel: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ws | push (last delivery)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    answer: Mapped[str | None] = mapped_column(String(64), nullable=True)  # x of the last answer:<x>
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    focus: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # focus_end: {card_id, task, minutes}


class NotificationActionRow(Base):
    """One applied `POST /api/notifications/{id}/action` (idempotency key: id, action, delivery number)."""

    __tablename__ = "notification_actions"

    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class PushSubscription(Base):
    """A Web Push subscription (one per browser/device). The endpoint URL and keys are personal data: sealed with
    the master key (aad "push-sub:<user_id>:<endpoint_bidx>"); `endpoint_bidx` is an HMAC blind index for lookups."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "endpoint_bidx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    endpoint_bidx: Mapped[str] = mapped_column(String(64), index=True)
    sealed: Mapped[str] = mapped_column(Text)
    device: Mapped[str | None] = mapped_column(String(64), nullable=True)  # client-chosen device id/label
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class OutboxSeen(Base):
    __tablename__ = "outbox_seen"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class UploadToken(Base):
    __tablename__ = "upload_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    # WAL lets readers and the writer proceed together; NORMAL sync is safe with WAL and avoids an fsync per commit.
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA secure_delete=ON")  # deleted rows (e.g. shredded data keys) are zeroed, not left in free pages
    cur.close()


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_pragmas)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        self._reset_pre_redesign_schema()
        Base.metadata.create_all(self.engine)
        self._add_birth_year()
        self._add_columns(_ADDED_COLUMNS)

    def _add_columns(self, wanted: dict[str, list[tuple[str, str]]]) -> None:
        """Idempotent `ALTER TABLE ... ADD COLUMN` for columns added to a table after databases already had it
        (create_all never alters). Only tables that exist and lack the column are touched."""
        from sqlalchemy import text

        insp = inspect(self.engine)
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    with self.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))

    def _add_birth_year(self) -> None:
        """`users.birth_year` replaced the stored age band. Add the column to an older database and give rows that
        only had a band a birth year in the middle of it (the band is derived from now on)."""
        from sqlalchemy import text

        from mentor_gateway.age import birth_year_for_band

        if "birth_year" in {c["name"] for c in inspect(self.engine).get_columns("users")}:
            return
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN birth_year INTEGER"))
            for uid, band in conn.execute(text("SELECT id, age_band FROM users WHERE age_band IS NOT NULL")).all():
                year = birth_year_for_band(band)
                if year is not None:
                    conn.execute(text("UPDATE users SET birth_year = :y WHERE id = :i"), {"y": year, "i": uid})

    def _reset_pre_redesign_schema(self) -> None:
        """Before the redesign `users` had `email` and no `username`; create_all cannot alter tables. Dev data is
        disposable, so such a database is dropped and recreated (a prod one raises: migrate it by hand)."""
        insp = inspect(self.engine)
        if not insp.has_table("users"):
            return
        cols = {c["name"] for c in insp.get_columns("users")}
        if "username" in cols:
            return
        if not self.engine.url.drivername.startswith("sqlite"):
            raise RuntimeError("ops database has the pre-redesign users table; migrate or recreate it")
        log.warning("ops database has the pre-redesign schema; dropping all tables (dev data is disposable)")
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for name in insp.get_table_names():
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}"')
            conn.commit()
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._factory()
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()
