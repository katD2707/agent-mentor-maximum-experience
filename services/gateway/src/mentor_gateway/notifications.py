"""Live WebSocket connections, Web Push fallback and the notification ("nudge") policy (plan 7.5, CONTRACTS 9).

Proactivity (`routines.yaml`):
- `off`: notifications are dropped (jobs still run). Exception: `focus_end`, a timer the learner started.
- `normal`: at most one delivered notification per local day; anything else waits in the pending list and is
  bundled into a single message the next time delivery is allowed. `deadline` (AGENTS.md: always report deadlines
  within 48 h), `focus_end` and a snoozed notification coming back do not count against that cap.
- `high`: delivered as soon as the learner is reachable.
Quiet hours (learner timezone) hold everything in the pending list. Jobs are never affected.

Delivery: over the learner's open WebSockets; with none open, over Web Push (push.py) when it is configured and
the learner subscribed a device. Otherwise the notification waits until the learner connects.

Safety: nothing is sent in a crisis context. A crisis alert in an outbox puts a 24 h hold on proactive kinds
(`outbox.py`), and a notification whose text touches crisis topics is suppressed outright. Pushes never show the
agent's text on a lock screen (push.py uses a generic text per kind).
"""

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mentor_schemas import NotifyPayload, ProactivityLevel, RoutinesFile
from pydantic import ValidationError
from sqlalchemy import select

from mentor_gateway.db import Database, NotificationMeta, NotificationRow, NudgeHold, PushSubscription
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

NotifyResult = Literal["delivered", "pending", "dropped", "suppressed"]

KINDS = ("checkin", "deadline", "review", "focus_end", "celebration", "report", "nudge")
DEFAULT_MASCOT = {"checkin": "wave", "deadline": "idle", "review": "happy", "focus_end": "happy",
                  "celebration": "celebrate", "report": "idle", "nudge": "idle"}
# A nudge that could not be delivered in time is dropped instead of arriving stale ("top 3 for today" tomorrow).
DEFAULT_TTL = {"checkin": timedelta(hours=6), "review": timedelta(hours=12), "focus_end": timedelta(hours=2),
               "celebration": timedelta(hours=24)}
CAP_EXEMPT_KINDS = frozenset({"deadline", "focus_end"})
OFF_EXEMPT_KINDS = frozenset({"focus_end"})
# kinds held back while a crisis hold is active; deadline and focus_end stay (neutral, practical)
HOLD_SUPPRESSED_KINDS = frozenset({"checkin", "review", "celebration", "report", "nudge"})
CRISIS_HOLD = timedelta(hours=24)
KIND_PRIORITY = {k: i for i, k in enumerate(("deadline", "checkin", "review", "focus_end", "report", "celebration",
                                              "nudge"))}

# Nudges never touch crisis topics (CONTRACTS section 9). Deliberately broad: a false positive only drops a nudge.
_CRISIS_TEXT = re.compile(
    r"tự\s*tử|tự\s*sát|tự\s*hại|tự\s*làm\s*(đau|hại)|kết\s*liễu|muốn\s*chết|không\s*muốn\s*sống|bạo\s*hành|"
    r"xâm\s*hại|bỏ\s*nhà|khủng\s*hoảng|\b111\b|\b113\b|\b115\b|suicid|self[\s-]*harm|kill\s+(my|your)self|abuse",
    re.IGNORECASE,
)


def mentions_crisis(*texts: str | None) -> bool:
    return any(t and _CRISIS_TEXT.search(t) for t in texts)


class Connection(Protocol):
    async def send_json(self, data: Any) -> None: ...


class _Conn:
    def __init__(self, ws: Connection) -> None:
        self.ws = ws
        self.lock = asyncio.Lock()

    async def send(self, message: dict) -> bool:
        try:
            async with self.lock:
                await self.ws.send_json(message)
            return True
        except Exception:  # noqa: BLE001 - a dead socket must not break delivery to the others
            return False


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def in_quiet_hours(routines: RoutinesFile, now: datetime) -> bool:
    try:
        start, end = (_parse_hhmm(x) for x in routines.quiet_hours)
        local = now.astimezone(ZoneInfo(routines.timezone)).time()
    except (ValueError, ZoneInfoNotFoundError):
        return False
    if start == end:
        return False
    if start < end:
        return start <= local < end
    return local >= start or local < end


@dataclass
class Nudge:
    """A notification to create. `text` is the message (and the old `text` field); body defaults to it."""

    text: str
    kind: str = "nudge"
    title: str = ""
    body: str | None = None
    actions: list[dict] = field(default_factory=list)
    mascot: str | None = None
    prefill: str | None = None
    expires_at: datetime | None = None
    source: str = "agent"
    push_safe: bool = False  # title/body are fixed gateway templates, fine on a lock screen
    focus: dict | None = None  # focus_end: {card_id, task, minutes}

    @classmethod
    def from_payload(cls, payload: dict) -> "Nudge":
        """From an OutboxItem(notify_user) payload. Invalid rich fields degrade to a plain text nudge."""
        text = str(payload.get("text") or payload.get("body") or "").strip()
        if not text:
            raise ValueError("notify_user without text")
        try:
            p = NotifyPayload.model_validate({**payload, "text": text[:500]})
        except ValidationError:
            log.warning("notify_user payload with invalid rich fields; delivering the text only")
            return cls(text=text)
        actions = [a.model_dump() for a in p.actions]
        if len({a["id"] for a in actions}) != len(actions):
            actions = []
        return cls(text=p.text, kind=p.kind, title=p.title, body=p.body, actions=actions, mascot=p.mascot,
                   prefill=p.prefill, expires_at=p.expires_at, focus=p.focus)


@dataclass
class Item:
    """A notification row joined with its rich fields (defaults for rows written before notification_meta)."""

    id: int
    user_id: str
    text: str
    created_at: datetime
    status: str
    delivered_at: datetime | None
    kind: str = "nudge"
    title: str = ""
    body: str = ""
    actions: list[dict] = field(default_factory=list)
    mascot: str = "idle"
    prefill: str | None = None
    source: str = "agent"
    push_safe: bool = False
    expires_at: datetime | None = None
    not_before: datetime | None = None
    cap_exempt: bool = False
    deliveries: int = 0
    read_at: datetime | None = None
    answer: str | None = None
    focus: dict | None = None

    @classmethod
    def of(cls, row: NotificationRow, meta: NotificationMeta | None) -> "Item":
        item = cls(id=row.id, user_id=row.user_id, text=row.text, created_at=row.created_at, status=row.status,
                   delivered_at=row.delivered_at, body=row.text)
        if meta is not None:
            item.kind, item.title, item.body = meta.kind, meta.title or "", meta.body or row.text
            item.actions = list(meta.actions or [])
            item.mascot = meta.mascot or DEFAULT_MASCOT.get(meta.kind, "idle")
            item.prefill, item.source, item.push_safe = meta.prefill, meta.source, bool(meta.push_safe)
            item.expires_at, item.not_before = meta.expires_at, meta.not_before
            item.cap_exempt, item.deliveries = bool(meta.cap_exempt), meta.deliveries or 0
            item.read_at, item.answer, item.focus = meta.read_at, meta.answer, meta.focus
        elif row.status == "delivered":
            item.deliveries = 1
        return item

    def view(self) -> dict:
        """The JSON shape of `GET /api/notifications` items and (with `type`) of the WebSocket event."""
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "body": self.body, "actions": self.actions,
            "mascot": self.mascot, "prefill": self.prefill, "text": self.text,
            "created_at": self.created_at.isoformat(), "status": self.status,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None, "answer": self.answer,
        }


def ws_message(batch: list[Item]) -> dict:
    """`{type: "notification", ...}`. A bundle (normal proactivity) carries the most important item's fields, all
    texts joined in `text` (old clients) and the other ids in `bundled_ids`."""
    primary = primary_item(batch)
    msg = {"type": "notification", "id": primary.id, "kind": primary.kind, "title": primary.title,
           "body": primary.body, "actions": primary.actions, "mascot": primary.mascot, "prefill": primary.prefill,
           "text": "\n".join(i.text for i in batch), "created_at": primary.created_at.isoformat()}
    if len(batch) > 1:
        msg["bundled_ids"] = [i.id for i in batch if i is not primary]
    return msg


def primary_item(batch: list[Item]) -> Item:
    return min(batch, key=lambda i: (KIND_PRIORITY.get(i.kind, 99), -i.id))


class NotificationHub:
    def __init__(self, db: Database, clock: Clock, routines_for: Callable[[str], RoutinesFile],
                 push: Any = None) -> None:
        self.db = db
        self.clock = clock
        self.routines_for = routines_for
        self.push = push  # push.PushService, set by context
        self._conns: dict[str, dict[int, _Conn]] = {}

    # ---- connections -------------------------------------------------------------------------

    def register(self, user_id: str, ws: Connection) -> None:
        self._conns.setdefault(user_id, {})[id(ws)] = _Conn(ws)

    def unregister(self, user_id: str, ws: Connection) -> None:
        conns = self._conns.get(user_id, {})
        conns.pop(id(ws), None)
        if not conns:
            self._conns.pop(user_id, None)

    def is_connected(self, user_id: str) -> bool:
        return bool(self._conns.get(user_id))

    async def send(self, user_id: str, message: dict) -> int:
        conns = list(self._conns.get(user_id, {}).values())
        results = await asyncio.gather(*(c.send(message) for c in conns))
        return sum(results)

    async def send_to(self, user_id: str, ws: Connection, message: dict) -> bool:
        conn = self._conns.get(user_id, {}).get(id(ws))
        if conn is None:
            conn = _Conn(ws)
        return await conn.send(message)

    async def sandbox_status(self, user_id: str, state: str) -> None:
        await self.send(user_id, {"type": "sandbox_status", "state": state})

    # ---- crisis hold -------------------------------------------------------------------------

    def hold_active(self, user_id: str, now: datetime | None = None) -> bool:
        now = now or self.clock()
        with self.db.session() as s:
            row = s.get(NudgeHold, user_id)
            return row is not None and row.until > now

    def set_hold(self, user_id: str, until: datetime) -> None:
        with self.db.session() as s:
            row = s.get(NudgeHold, user_id)
            if row is None:
                s.add(NudgeHold(user_id=user_id, until=until))
            elif row.until < until:
                row.until = until

    # ---- notifications -----------------------------------------------------------------------

    async def notify(self, user_id: str, text: str, nudge: Nudge | None = None) -> NotifyResult:
        now = self.clock()
        nudge = nudge or Nudge(text=text)
        kind = nudge.kind if nudge.kind in KINDS else "nudge"
        routines = self.routines_for(user_id)
        status = "pending"
        if routines.proactivity == ProactivityLevel.OFF and kind not in OFF_EXEMPT_KINDS:
            status = "dropped"
        else:
            crisis_text = mentions_crisis(nudge.text, nudge.title, nudge.body, nudge.prefill,
                                          *(str(a.get("label", "")) for a in nudge.actions))
            if crisis_text or (kind in HOLD_SUPPRESSED_KINDS and self.hold_active(user_id, now)):
                status = "suppressed"
        ttl = DEFAULT_TTL.get(kind)
        with self.db.session() as s:
            row = NotificationRow(user_id=user_id, text=nudge.text, created_at=now, status=status)
            s.add(row)
            s.flush()
            row_id = row.id
            s.add(NotificationMeta(
                notification_id=row_id, user_id=user_id, kind=kind, title=nudge.title[:200],
                body=(nudge.body or nudge.text), actions=nudge.actions[:3],
                mascot=nudge.mascot or DEFAULT_MASCOT[kind], prefill=nudge.prefill, source=nudge.source,
                push_safe=nudge.push_safe, expires_at=nudge.expires_at or (now + ttl if ttl else None),
                cap_exempt=kind in CAP_EXEMPT_KINDS, deliveries=0, focus=nudge.focus,
            ))
        if status != "pending":
            if status == "suppressed":
                log.info("notification %s of %s suppressed (crisis context)", row_id, user_id)
            return status  # type: ignore[return-value]
        await self.flush(user_id, routines=routines)
        with self.db.session() as s:
            return "delivered" if s.get(NotificationRow, row_id).status == "delivered" else "pending"

    def get(self, user_id: str, notification_id: int) -> Item | None:
        with self.db.session() as s:
            row = s.get(NotificationRow, notification_id)
            if row is None or row.user_id != user_id:
                return None
            return Item.of(row, s.get(NotificationMeta, notification_id))

    def recent(self, user_id: str, limit: int = 30) -> list[Item]:
        """Notifications the learner has seen (delivered, or snoozed after a delivery), newest first."""
        with self.db.session() as s:
            pairs = s.execute(
                select(NotificationRow, NotificationMeta)
                .outerjoin(NotificationMeta, NotificationMeta.notification_id == NotificationRow.id)
                .where(NotificationRow.user_id == user_id,
                       NotificationRow.status.in_(("delivered", "pending", "dismissed")))
                .order_by(NotificationRow.id.desc())
                .limit(limit * 3)
            ).all()
        items = [Item.of(r, m) for r, m in pairs]
        return [i for i in items if i.deliveries > 0 or i.status == "delivered"][:limit]

    def pending(self, user_id: str) -> list[NotificationRow]:
        with self.db.session() as s:
            return list(
                s.scalars(
                    select(NotificationRow)
                    .where(NotificationRow.user_id == user_id, NotificationRow.status == "pending")
                    .order_by(NotificationRow.id)
                )
            )

    def _due(self, user_id: str, now: datetime) -> list[Item]:
        """Pending items that may go out now (snooze over); expired ones are marked `expired`."""
        with self.db.session() as s:
            pairs = s.execute(
                select(NotificationRow, NotificationMeta)
                .outerjoin(NotificationMeta, NotificationMeta.notification_id == NotificationRow.id)
                .where(NotificationRow.user_id == user_id, NotificationRow.status == "pending")
                .order_by(NotificationRow.id)
            ).all()
            due = []
            for row, meta in pairs:
                item = Item.of(row, meta)
                if item.expires_at is not None and item.expires_at <= now:
                    row.status = "expired"
                    continue
                if item.not_before is not None and item.not_before > now:
                    continue
                due.append(item)
            return due

    def _delivered_today(self, user_id: str, routines: RoutinesFile, now: datetime) -> int:
        """Deliveries today that count against the `normal` cap (cap-exempt kinds and snoozes do not)."""
        tz = ZoneInfo(routines.timezone)
        day = now.astimezone(tz).date()
        with self.db.session() as s:
            rows = s.execute(
                select(NotificationRow.delivered_at, NotificationMeta.cap_exempt)
                .outerjoin(NotificationMeta, NotificationMeta.notification_id == NotificationRow.id)
                .where(NotificationRow.user_id == user_id, NotificationRow.status.in_(("delivered", "dismissed")))
            ).all()
        return sum(1 for ts, exempt in rows if ts and not exempt and ts.astimezone(tz).date() == day)

    def _mark_delivered(self, batch: list[Item], now: datetime, channel: str) -> None:
        with self.db.session() as s:
            for item in batch:
                row = s.get(NotificationRow, item.id)
                row.status = "delivered"
                row.delivered_at = now
                meta = s.get(NotificationMeta, item.id)
                if meta is not None:
                    meta.deliveries = (meta.deliveries or 0) + 1
                    meta.channel = channel
                    meta.not_before = None

    def _suppress(self, items: list[Item]) -> None:
        with self.db.session() as s:
            for item in items:
                s.get(NotificationRow, item.id).status = "suppressed"

    def _can_push(self, user_id: str) -> bool:
        return self.push is not None and self.push.enabled and self.push.has_subscriptions(user_id)

    async def flush(self, user_id: str, routines: RoutinesFile | None = None) -> int:
        """Deliver pending notifications if policy allows. Returns the number of messages sent."""
        connected = self.is_connected(user_id)
        if not connected and not self._can_push(user_id):
            return 0
        now = self.clock()
        routines = routines or self.routines_for(user_id)
        if in_quiet_hours(routines, now):
            return 0
        items = self._due(user_id, now)
        if routines.proactivity == ProactivityLevel.OFF:
            items = [i for i in items if i.kind in OFF_EXEMPT_KINDS]
        if items and self.hold_active(user_id, now):
            held = [i for i in items if i.kind in HOLD_SUPPRESSED_KINDS]
            self._suppress(held)
            items = [i for i in items if i.kind not in HOLD_SUPPRESSED_KINDS]
        if not items:
            return 0
        batches = [[i] for i in items if i.cap_exempt]
        rest = [i for i in items if not i.cap_exempt]
        if routines.proactivity == ProactivityLevel.NORMAL:
            if rest and self._delivered_today(user_id, routines, now) < 1:
                batches.append(rest)  # bundle everything into one notification
        else:
            batches += [[i] for i in rest]
        sent = 0
        for batch in batches:
            if connected:
                ok = await self.send(user_id, ws_message(batch)) > 0
            else:
                ok = await self.push.send_batch(user_id, batch, now) > 0
            if not ok:
                break
            self._mark_delivered(batch, now, "ws" if connected else "push")
            sent += 1
        return sent

    def _push_users_with_pending(self) -> set[str]:
        with self.db.session() as s:
            return set(s.scalars(
                select(NotificationRow.user_id).distinct()
                .where(NotificationRow.status == "pending",
                       NotificationRow.user_id.in_(select(PushSubscription.user_id)))
            ))

    async def flush_all(self) -> None:
        users = set(self._conns)
        if self.push is not None and self.push.enabled:
            users |= self._push_users_with_pending()
        for user_id in users:
            try:
                await self.flush(user_id)
            except Exception:
                log.exception("flushing notifications for %s", user_id)
