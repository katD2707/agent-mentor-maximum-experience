"""Ops database (plan section 4.2): accounts, sessions, parent links, audit, schedules, outbox.

No learner content lives here; the workspace is the source of truth about the learner.
SQLite in dev; the schema avoids SQLite-only features so Postgres works with the same models.
"""

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
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


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
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # thpt | ncs
    display_name: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(8), default="vi")
    inbound_code: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MagicLink(Base):
    __tablename__ = "magic_links"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LoginCode(Base):
    """6-digit code sent with a magic link, for clients that cannot follow the link (the desktop pop-up).

    A separate table (not columns on `magic_links`) so existing dev databases pick it up via `create_all`.
    Using either the link or the code consumes the same `MagicLink` row.
    """

    __tablename__ = "login_codes"

    token_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("magic_links.token_hash", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)


class WebSession(Base):
    __tablename__ = "web_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ChatSession(Base):
    """session_id = "s-YYYYMMDD" per learner per local day, so the key is (user_id, id)."""

    __tablename__ = "chat_sessions"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_active_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Conversation(Base):
    """A named conversation (CONTRACTS section 10.5), session_id = "c-<id>". Only the label lives here; the messages
    are in the workspace transcripts `sessions/<day>/c-<id>.jsonl`. The title is typed by the learner (or the first
    words of their first message), so it is kept short (80 chars)."""

    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # 12 hex chars
    title: Mapped[str] = mapped_column(String(80), default="")
    auto_title: Mapped[bool] = mapped_column(Boolean, default=True)  # still the default: the first message names it
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ParentLinkRow(Base):
    __tablename__ = "parent_links"

    student_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    link_code: Mapped[str] = mapped_column(String(16), index=True)
    code_expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    zalo_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditRow(Base):
    """Crisis alerts and consent events. Never exposed through any workspace or activity endpoint."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")  # "enc1:" + sealed text (parent.AUDIT_AAD); see parent.py
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ParentContact(Base):
    """The parent's Zalo chat id, sealed with the master key (aad "parent_contacts:zalo_chat_id:<student>").

    `zalo_chat_bidx` is an HMAC blind index so the webhook can find a link by chat id without decrypting rows.
    A separate table (not columns on `parent_links`) so existing dev databases pick it up via `create_all`;
    `parent_links.zalo_chat_id` is no longer written.
    """

    __tablename__ = "parent_contacts"

    student_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    zalo_chat_enc: Mapped[str] = mapped_column(Text)
    zalo_chat_bidx: Mapped[str] = mapped_column(String(64), index=True)


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


class NudgeHold(Base):
    """No proactive nudges for this learner until `until` (set when a crisis alert came through the outbox)."""

    __tablename__ = "nudge_holds"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    until: Mapped[datetime] = mapped_column(UTCDateTime)


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


class SentReport(Base):
    __tablename__ = "sent_reports"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime)


class UserUiState(Base):
    """Per-user web UI flags that must follow the learner across devices (web, desktop pop-up).

    A separate table (not columns on `users`) so existing dev databases pick it up via `create_all`.
    """

    __tablename__ = "user_ui_state"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    setup_guide_dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class UserOnboarding(Base):
    """First-run tour progress and one-time tips, per learner (follows them across web and the desktop pop-up).

    A new table (not columns on `user_ui_state`) because `create_all` does not add columns to existing SQLite tables.
    """

    __tablename__ = "user_onboarding"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tour_step: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tour_completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    tour_skipped_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    tips_seen: Mapped[list] = mapped_column(JSON, default=list)


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
        Base.metadata.create_all(self.engine)

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
