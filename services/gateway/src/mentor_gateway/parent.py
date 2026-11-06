"""Parent channel wiring (CONTRACTS.md section 6).

The gateway owns the database (SqlParentLinkStore) and wraps Track E's `ParentLinkService` behind
`ParentChannel`. E's package is imported lazily; when it is missing (or incomplete) a small in-process
`DevParentService` keeps the THPT flow usable in dev. Without ZALO_BOT_TOKEN a logging Zalo client is used,
so nothing leaves the machine.
"""

import asyncio
import inspect
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Protocol

from fastapi import APIRouter
from mentor_schemas import ParentLink
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mentor_gateway.crypto import SecretBox
from mentor_gateway.db import AuditRow, Database, OutboxSeen, ParentContact, ParentLinkRow
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)


ZALO_CHAT_BIDX = "zalo-chat"  # blind-index purpose for parent_contacts.zalo_chat_bidx
AUDIT_PREFIX = "enc1:"


def zalo_chat_aad(student_user_id: str) -> str:
    return f"parent_contacts:zalo_chat_id:{student_user_id}"


def audit_aad(student_user_id: str, kind: str) -> str:
    return f"audit_log:detail:{student_user_id}:{kind}"


class SqlParentLinkStore:
    """ParentLinkStore backed by the ops DB. Safe to call from any thread.

    The parent's Zalo chat id lives sealed in `parent_contacts` (with an HMAC blind index for `get_by_chat`), and
    audit details (consent records carry the chat id and the parent's Zalo display name) are sealed too.
    """

    def __init__(self, db: Database, clock: Clock, box: SecretBox) -> None:
        self.db = db
        self.clock = clock
        self.box = box

    def _to_model(self, s: Session, row: ParentLinkRow | None) -> ParentLink | None:
        if row is None:
            return None
        contact = s.get(ParentContact, row.student_user_id)
        chat_id = (self.box.unseal_str(contact.zalo_chat_enc, aad=zalo_chat_aad(row.student_user_id))
                   if contact is not None else row.zalo_chat_id)  # row.zalo_chat_id: plaintext from older dev DBs
        return ParentLink(
            student_user_id=row.student_user_id,
            link_code=row.link_code,
            code_expires_at=row.code_expires_at,
            zalo_chat_id=chat_id,
            status=row.status,
            verified_at=row.verified_at,
        )

    def get_by_code(self, link_code: str) -> ParentLink | None:
        with self.db.session() as s:
            row = s.scalars(
                select(ParentLinkRow).where(ParentLinkRow.link_code == link_code, ParentLinkRow.status == "pending")
            ).first()
            return self._to_model(s, row)

    def get_by_chat(self, zalo_chat_id: str) -> ParentLink | None:
        bidx = self.box.blind_index(zalo_chat_id, purpose=ZALO_CHAT_BIDX)
        with self.db.session() as s:
            row = s.scalars(
                select(ParentLinkRow)
                .join(ParentContact, ParentContact.student_user_id == ParentLinkRow.student_user_id)
                .where(ParentContact.zalo_chat_bidx == bidx, ParentLinkRow.status != "revoked")
                .order_by(ParentLinkRow.code_expires_at.desc())
            ).first()
            return self._to_model(s, row)

    def get_by_student(self, student_user_id: str) -> ParentLink | None:
        with self.db.session() as s:
            return self._to_model(s, s.get(ParentLinkRow, student_user_id))

    def save(self, link: ParentLink) -> None:
        uid = link.student_user_id
        with self.db.session() as s:
            row = s.get(ParentLinkRow, uid)
            if row is None:
                row = ParentLinkRow(student_user_id=uid)
                s.add(row)
            row.link_code = link.link_code
            row.code_expires_at = link.code_expires_at
            row.zalo_chat_id = None  # never stored in plaintext; see ParentContact
            row.status = link.status
            row.verified_at = link.verified_at
            contact = s.get(ParentContact, uid)
            if link.zalo_chat_id is None:
                if contact is not None:
                    s.delete(contact)
            else:
                if contact is None:
                    contact = ParentContact(student_user_id=uid)
                    s.add(contact)
                contact.zalo_chat_enc = self.box.seal_str(link.zalo_chat_id, aad=zalo_chat_aad(uid))
                contact.zalo_chat_bidx = self.box.blind_index(link.zalo_chat_id, purpose=ZALO_CHAT_BIDX)

    def record_audit(self, student_user_id: str, kind: str, detail: str) -> None:
        sealed = AUDIT_PREFIX + self.box.seal_str(detail, aad=audit_aad(student_user_id, kind))
        with self.db.session() as s:
            s.add(AuditRow(student_user_id=student_user_id, kind=kind, detail=sealed, created_at=self.clock()))

    def read_audit(self, student_user_id: str) -> list[tuple[str, str, datetime]]:
        """Operator use (legal record): decrypted (kind, detail, created_at), oldest first."""
        with self.db.session() as s:
            rows = s.scalars(
                select(AuditRow).where(AuditRow.student_user_id == student_user_id).order_by(AuditRow.id)
            ).all()
            return [(r.kind, self.open_audit_detail(r), r.created_at) for r in rows]

    def open_audit_detail(self, row: AuditRow) -> str:
        if not row.detail.startswith(AUDIT_PREFIX):
            return row.detail  # written before encryption (older dev DBs)
        return self.box.unseal_str(row.detail[len(AUDIT_PREFIX):], aad=audit_aad(row.student_user_id, row.kind))

    def delete_student(self, student_user_id: str) -> None:
        with self.db.session() as s:
            for model in (ParentLinkRow, ParentContact):
                row = s.get(model, student_user_id)
                if row is not None:
                    s.delete(row)


class ParentService(Protocol):
    """The subset of E's ParentLinkService the gateway calls. Methods may be sync or async."""

    def start_link(self, student_user_id: str) -> Any: ...
    def send_report(self, student_user_id: str, report_text: str) -> Any: ...
    def send_crisis_alert(self, student_user_id: str, category: str) -> Any: ...


class LoggingZaloClient:
    """Stands in for ZaloBotClient when ZALO_BOT_TOKEN is not set (dev): logs instead of sending."""

    def send_message(self, chat_id: str, text: str) -> list[str]:
        log.info("[zalo dev] to %s: %s", chat_id, text[:200])
        return []

    def set_webhook(self, url: str, secret_token: str) -> dict:
        log.info("[zalo dev] set_webhook %s", url)
        return {}


class AlreadyVerifiedError(Exception):
    """start_link on a student whose parent is already verified (HTTP 409)."""


class DedupedUpdates:
    """Backs the webhook's update idempotency with the ops DB, so redeliveries survive a gateway restart.

    The key matches mentor_parent_channel's in-memory one: message_id, else `<chat_id>:<date>`.
    """

    def __init__(self, service: Any, db: Database, clock: Clock) -> None:
        self.service = service
        self.db = db
        self.clock = clock

    @staticmethod
    def update_key(update: dict) -> str | None:
        if "event_name" not in update and isinstance(update.get("result"), dict):
            update = update["result"]
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        chat_id = str((message.get("chat") or {}).get("id") or "")
        mid = message.get("message_id")
        return f"zalo:{mid}" if mid else (f"zalo:{chat_id}:{message.get('date')}" if chat_id else None)

    def handle_update(self, update: dict) -> None:
        key = self.update_key(update)
        if key is not None:
            try:
                with self.db.session() as s:
                    s.add(OutboxSeen(user_id="_zalo", dedupe_key=key, kind="zalo_update", created_at=self.clock()))
            except IntegrityError:
                log.info("zalo update %s already processed", key)
                return
        try:
            self.service.handle_update(update)
        except Exception:
            if key is not None:  # let a redelivery retry
                with self.db.session() as s:
                    row = s.get(OutboxSeen, ("_zalo", key))
                    if row is not None:
                        s.delete(row)
            raise


class DevParentService:
    """Fallback when mentor_parent_channel is unavailable: links without Zalo; reports are only logged."""

    def __init__(self, store: SqlParentLinkStore, clock: Clock) -> None:
        self.store = store
        self.clock = clock

    def start_link(self, student_user_id: str) -> ParentLink:
        link = ParentLink(
            student_user_id=student_user_id,
            link_code=f"{secrets.randbelow(1_000_000):06d}",
            code_expires_at=self.clock() + timedelta(hours=24),
        )
        self.store.save(link)
        return link

    def send_report(self, student_user_id: str, report_text: str) -> bool:
        link = self.store.get_by_student(student_user_id)
        if not link or link.status != "verified":
            return False
        log.info("[parent dev] report for %s (%d chars)", student_user_id, len(report_text))
        return True

    def send_crisis_alert(self, student_user_id: str, category: str) -> bool:
        link = self.store.get_by_student(student_user_id)
        if not link or link.status != "verified":
            return False
        self.store.record_audit(student_user_id, "crisis_alert", f"category={category}; channel=dev-log")
        return True


async def _call(fn: Any, *args: Any) -> Any:
    result = await asyncio.to_thread(fn, *args)
    if inspect.isawaitable(result):
        result = await result
    return result


class ParentChannel:
    def __init__(self, service: ParentService, store: SqlParentLinkStore, router: APIRouter | None, clock: Clock,
                 using_library: bool) -> None:
        self.service = service
        self.store = store
        self.router = router
        self.clock = clock
        self.using_library = using_library

    async def start_link(self, student_user_id: str) -> ParentLink:
        if self.is_verified(student_user_id):
            raise AlreadyVerifiedError(student_user_id)
        try:
            link = await _call(self.service.start_link, student_user_id)
        except Exception as exc:
            if type(exc).__name__ == "ParentLinkError" and self.is_verified(student_user_id):
                raise AlreadyVerifiedError(student_user_id) from exc
            raise
        return link if isinstance(link, ParentLink) else ParentLink.model_validate(link, from_attributes=True)

    def get_link(self, student_user_id: str) -> ParentLink | None:
        return self.store.get_by_student(student_user_id)

    def is_verified(self, student_user_id: str) -> bool:
        link = self.get_link(student_user_id)
        return bool(link and link.status == "verified")

    async def send_report(self, student_user_id: str, report_text: str) -> bool:
        return bool(await _call(self.service.send_report, student_user_id, report_text))

    async def send_crisis_alert(self, student_user_id: str, category: str) -> bool:
        return bool(await _call(self.service.send_crisis_alert, student_user_id, category))

    def dev_verify(self, student_user_id: str, chat_id: str = "dev-chat") -> ParentLink:
        """MENTOR_ENV=dev only: mark the link verified as if the parent had consented on Zalo."""
        link = self.get_link(student_user_id) or ParentLink(
            student_user_id=student_user_id, link_code="000000", code_expires_at=self.clock()
        )
        link = link.model_copy(update={"status": "verified", "verified_at": self.clock(), "zalo_chat_id": chat_id})
        self.store.save(link)
        self.store.record_audit(student_user_id, "consent", "dev verification (MENTOR_ENV=dev)")
        return link


def build_parent_channel(settings: Settings, store: SqlParentLinkStore, clock: Clock) -> ParentChannel:
    """Use mentor_parent_channel when importable; mount its webhook behind DB-backed dedupe."""
    try:
        from mentor_parent_channel import ParentLinkService, create_webhook_router  # type: ignore[attr-defined]
    except ImportError as exc:
        log.warning("mentor_parent_channel unavailable (%s); using DevParentService", exc)
        return ParentChannel(DevParentService(store, clock), store, None, clock, using_library=False)

    if settings.zalo_bot_token:
        from mentor_parent_channel import ZaloBotClient  # type: ignore[attr-defined]

        client: Any = ZaloBotClient(settings.zalo_bot_token)
    else:
        client = LoggingZaloClient()
    service = ParentLinkService(store, client, settings.zalo_bot_name, now=clock)
    router = create_webhook_router(DedupedUpdates(service, store.db, clock), settings.zalo_webhook_secret)
    return ParentChannel(service, store, router, clock, using_library=True)
