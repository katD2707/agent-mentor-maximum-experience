"""Parent link, consent, reports and crisis alerts over the Zalo bot (plan 7.6, 8.3, 9.3).

Link flow:
  student app -> start_link() -> 6-digit code (24 h)            status: pending
  parent sends the code to the bot -> consent request            status: awaiting_consent
  parent replies "ĐỒNG Ý" -> confirmation + audit("consent")    status: verified

The service holds no state of its own except a bounded in-memory set of processed Zalo message ids
(idempotency for webhook redeliveries) and a per-chat counter of wrong codes (brute-force guard).
"""

import logging
import re
import secrets
import threading
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from mentor_schemas.protocols import ParentLink, ParentLinkStore
from mentor_schemas.reports import (
    AI_DISCLAIMER,
    REPORT_EMAIL_PATTERN,
    REPORT_FORBIDDEN_PATTERNS,
    REPORT_PHONE_PATTERN,
    REPORT_PRIVATE_PATH_PATTERN,
    ParentReport,
)

from mentor_parent_channel import messages
from mentor_parent_channel.client import ZaloError
from mentor_parent_channel.text import markdown_to_plain

log = logging.getLogger(__name__)

CODE_TTL = timedelta(hours=24)
MAX_FAILED_CODES = 5
FAILED_CODE_WINDOW = timedelta(hours=1)
TEXT_EVENT = "message.text.received"
UNSUPPORTED_EVENT = "message.unsupported.received"  # sender is a protected account; content withheld

_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


class MessageSender(Protocol):
    """The part of ZaloBotClient the service uses (lets tests and the gateway substitute it)."""

    def send_message(self, chat_id: str, text: str) -> list[str]: ...


class ParentLinkError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    # Stores backed by SQLite often hand back naive datetimes; treat them as UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _fold(text: str) -> str:
    """Lowercase, strip Vietnamese diacritics and punctuation: 'Đồng ý!' -> 'dong y'."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    bare = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", bare).split())


def is_consent_reply(text: str) -> bool:
    return _fold(text) in {"dong y", "dongy"}


def find_forbidden(text: str) -> list[str]:
    """Return the REPORT_FORBIDDEN_PATTERNS the text matches (case-insensitive, NFC-normalised)."""
    normalized = unicodedata.normalize("NFC", text)
    return [p for p in REPORT_FORBIDDEN_PATTERNS if re.search(p, normalized, re.IGNORECASE)]


_LEAK_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(REPORT_EMAIL_PATTERN)),
    ("phone", re.compile(REPORT_PHONE_PATTERN)),
    ("workspace_path", re.compile(REPORT_PRIVATE_PATH_PATTERN, re.IGNORECASE)),
)


def find_leaks(report_text: str) -> list[str]:
    """Names of the leak checks a report fails (empty = may be sent). Accepts a full report file or a bare body.

    The same checks as the sandbox's check_report, re-run outside the sandbox: REPORT_FORBIDDEN_PATTERNS (scores,
    quotes, "em nói..."), email addresses, phone numbers and private workspace paths (me/, sessions/, inbox/,
    .mentor/). Only check names are returned, never the matched text (it is about a minor).
    """
    body = unicodedata.normalize("NFC", report_body(report_text))
    names = [f"forbidden:{i}" for i, p in enumerate(REPORT_FORBIDDEN_PATTERNS) if re.search(p, body, re.IGNORECASE)]
    names += [name for name, rx in _LEAK_CHECKS if rx.search(body)]
    return names


def report_body(report_text: str) -> str:
    """Accept either a full reports/*.md file (with frontmatter) or a bare markdown body."""
    if report_text.lstrip().startswith("---"):
        try:
            return ParentReport.parse(report_text.lstrip()).body_markdown
        except Exception:  # noqa: BLE001 - malformed frontmatter: drop it textually, still check the rest
            return _FRONTMATTER_RE.sub("", report_text.lstrip(), count=1)
    return report_text


def has_disclaimer(text: str) -> bool:
    """True if AI_DISCLAIMER is already in the text (ignoring case, diacritics, punctuation, emphasis)."""
    return _fold(AI_DISCLAIMER) in _fold(text)


class ParentLinkService:
    def __init__(
        self,
        store: ParentLinkStore,
        client: MessageSender,
        bot_name: str,
        now: Callable[[], datetime] = _utcnow,
        *,
        code_ttl: timedelta = CODE_TTL,
        dedupe_size: int = 4096,
    ) -> None:
        self._store = store
        self._client = client
        self._bot_name = bot_name
        self._now = now
        self._code_ttl = code_ttl
        self._dedupe_size = dedupe_size
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._failed: dict[str, list[datetime]] = {}
        self._lock = threading.RLock()

    # ---- student side ---------------------------------------------------------------------------

    def start_link(self, student_user_id: str) -> ParentLink:
        """Issue a fresh 6-digit code valid for 24 h, replacing any unfinished link for this student."""
        with self._lock:
            existing = self._store.get_by_student(student_user_id)
            if existing is not None and existing.status == "verified":
                raise ParentLinkError("parent link is already verified")
            link = ParentLink(
                student_user_id=student_user_id,
                link_code=self._new_code(student_user_id),
                code_expires_at=self._now() + self._code_ttl,
            )
            self._store.save(link)
            return link

    def _new_code(self, student_user_id: str) -> str:
        for _ in range(50):
            code = f"{secrets.randbelow(1_000_000):06d}"
            other = self._store.get_by_code(code)
            if other is None or other.student_user_id == student_user_id:
                return code
        raise ParentLinkError("could not allocate a unique link code")

    # ---- webhook side ---------------------------------------------------------------------------

    def handle_update(self, update: dict[str, Any]) -> None:
        """Process one Zalo webhook event. Duplicate deliveries (same message_id) are ignored."""
        if "event_name" not in update and isinstance(update.get("result"), dict):
            update = update["result"]  # getUpdates-style envelope
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        if not chat_id or chat.get("chat_type", "PRIVATE") != "PRIVATE":
            return  # groups never link: reports must reach one parent only
        sender = message.get("from") or {}
        if sender.get("is_bot"):
            return
        key = str(message.get("message_id") or f"{chat_id}:{message.get('date')}")

        with self._lock:
            if key in self._seen:
                log.info("zalo update %s already processed, ignoring", key)
                return
            self._seen[key] = None
            while len(self._seen) > self._dedupe_size:
                self._seen.popitem(last=False)
            try:
                reply = self._dispatch(str(update.get("event_name") or ""), chat_id, message)
            except Exception:
                self._seen.pop(key, None)  # let a redelivery retry
                raise
        if reply:
            self._reply(chat_id, reply)

    def _dispatch(self, event_name: str, chat_id: str, message: dict[str, Any]) -> str | None:
        if event_name == UNSUPPORTED_EVENT:
            return None
        chat_link = self._store.get_by_chat(chat_id)
        text = message.get("text") if event_name == TEXT_EVENT else None
        if not isinstance(text, str):
            return self._help(chat_link)
        match = _CODE_RE.search(text)
        if match:
            return self._handle_code(chat_id, match.group(1), chat_link)
        if chat_link is not None and chat_link.status == "awaiting_consent" and is_consent_reply(text):
            display_name = str((message.get("from") or {}).get("display_name") or "")
            return self._handle_consent(chat_link, chat_id, display_name)
        return self._help(chat_link)

    def _handle_code(self, chat_id: str, code: str, chat_link: ParentLink | None) -> str:
        if self._too_many_failures(chat_id):
            return messages.too_many_attempts()
        link = self._store.get_by_code(code)
        usable = (
            link is not None
            and link.status != "revoked"
            and (link.zalo_chat_id is None or link.zalo_chat_id == chat_id)
        )
        if not usable:
            if chat_link is not None and chat_link.status == "verified":
                return messages.help_verified(self._bot_name)  # stray digits from a linked parent
            self._failed.setdefault(chat_id, []).append(self._now())
            return messages.invalid_code()
        assert link is not None
        if link.status == "verified":
            return messages.help_verified(self._bot_name)
        if self._now() > _as_utc(link.code_expires_at):
            return messages.expired_code()
        if chat_link is not None and chat_link.student_user_id != link.student_user_id:
            if chat_link.status == "verified":
                return messages.already_linked_other()
            # Unfinished link to another student: release it so this chat maps to exactly one link.
            self._store.save(chat_link.model_copy(update={"zalo_chat_id": None, "status": "pending"}))
        self._store.save(link.model_copy(update={"zalo_chat_id": chat_id, "status": "awaiting_consent"}))
        self._failed.pop(chat_id, None)
        return messages.consent_request(self._bot_name)

    def _handle_consent(self, link: ParentLink, chat_id: str, display_name: str) -> str:
        now = self._now()
        if now > _as_utc(link.code_expires_at):
            return messages.expired_code()
        self._store.save(link.model_copy(update={"status": "verified", "verified_at": now}))
        self._store.record_audit(
            link.student_user_id,
            "consent",
            f"zalo_chat_id={chat_id}; display_name={display_name}; at={now.isoformat()}; via=zalo_bot",
        )
        return messages.confirmation(self._bot_name)

    def _help(self, chat_link: ParentLink | None) -> str:
        if chat_link is None or chat_link.status in ("pending", "revoked"):
            return messages.help_unlinked(self._bot_name)
        if chat_link.status == "awaiting_consent":
            return messages.help_awaiting_consent()
        return messages.help_verified(self._bot_name)

    def _too_many_failures(self, chat_id: str) -> bool:
        cutoff = self._now() - FAILED_CODE_WINDOW
        recent = [t for t in self._failed.get(chat_id, []) if t > cutoff]
        if recent:
            self._failed[chat_id] = recent
        else:
            self._failed.pop(chat_id, None)
        return len(recent) >= MAX_FAILED_CODES

    def _reply(self, chat_id: str, text: str) -> None:
        try:
            self._client.send_message(chat_id, text)
        except ZaloError as exc:
            log.warning("zalo reply to chat failed: %s", exc)

    # ---- outbound -------------------------------------------------------------------------------

    def _verified_link(self, student_user_id: str) -> ParentLink | None:
        link = self._store.get_by_student(student_user_id)
        if link is None or link.status != "verified" or not link.zalo_chat_id:
            return None
        return link

    def send_report(self, student_user_id: str, report_text: str) -> bool:
        """Send a parent report. Refuses (False) unless verified and free of REPORT_FORBIDDEN_PATTERNS."""
        link = self._verified_link(student_user_id)
        if link is None:
            log.info("report for %s not sent: no verified parent link", student_user_id)
            return False
        body = report_body(report_text)
        plain = markdown_to_plain(body)
        # check_report requires the disclaimer, so it is normally already there: append only if missing.
        text = messages.report(self._bot_name, plain, append_disclaimer=not has_disclaimer(plain))
        violations = find_leaks(body) or find_forbidden(text)
        if violations:
            # Do not log the report content: it is about a minor.
            log.warning("report for %s blocked: %d forbidden pattern(s)", student_user_id, len(violations))
            return False
        if not plain:
            log.warning("report for %s not sent: empty body", student_user_id)
            return False
        try:
            self._client.send_message(link.zalo_chat_id or "", text)
        except ZaloError as exc:
            log.warning("report for %s not delivered: %s", student_user_id, exc)
            return False
        return True

    def send_crisis_alert(self, student_user_id: str, category: str) -> bool:
        """Send the fixed tier-3 alert (no details) and audit the attempt either way."""
        link = self._verified_link(student_user_id)
        if link is None:
            self._store.record_audit(
                student_user_id, "crisis_alert", f"category={category}; delivered=false; reason=no_verified_link"
            )
            return False
        try:
            self._client.send_message(link.zalo_chat_id or "", messages.CRISIS_ALERT)
        except ZaloError as exc:
            self._store.record_audit(
                student_user_id, "crisis_alert", f"category={category}; delivered=false; reason={type(exc).__name__}"
            )
            return False
        self._store.record_audit(student_user_id, "crisis_alert", f"category={category}; delivered=true")
        return True
