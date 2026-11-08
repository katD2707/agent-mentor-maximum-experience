"""Deliver OutboxItems returned by an agent job (JobResult.outbox): notifications and `next_wake` jobs.

Idempotent on `dedupe_key` per user.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from mentor_schemas import JobKind, OutboxItem, OutboxKind, RoutinesFile
from sqlalchemy.exc import IntegrityError

from mentor_gateway.db import Database, JobRow, OutboxSeen
from mentor_gateway.notifications import NotificationHub, Nudge
from mentor_gateway.security import new_id
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)


class OutboxDispatcher:
    def __init__(self, db: Database, hub: NotificationHub, clock: Clock,
                 routines_for: Callable[[str], RoutinesFile]) -> None:
        self.db = db
        self.hub = hub
        self.clock = clock
        self.routines_for = routines_for

    def _claim(self, user_id: str, item: OutboxItem) -> bool:
        """Record the dedupe key; False if this item was already handled."""
        if not item.dedupe_key:
            return True
        try:
            with self.db.session() as s:
                s.add(OutboxSeen(user_id=user_id, dedupe_key=item.dedupe_key, kind=item.kind.value,
                                 created_at=self.clock()))
            return True
        except IntegrityError:
            log.info("outbox: duplicate %s/%s dropped", user_id, item.dedupe_key)
            return False

    async def dispatch(self, user_id: str, items: list[OutboxItem]) -> list[str]:
        """Handle every item; one failure does not stop the others. Returns a status per item."""
        results = []
        for item in items:
            if not self._claim(user_id, item):
                results.append("duplicate")
                continue
            try:
                results.append(await self._handle(user_id, item))
            except Exception as exc:
                log.exception("outbox %s for %s failed", item.kind, user_id)
                results.append(f"error: {exc}")
        return results

    async def _handle(self, user_id: str, item: OutboxItem) -> str:
        if item.kind == OutboxKind.NOTIFY_USER:
            try:
                nudge = Nudge.from_payload(item.payload)
            except ValueError:
                return "ignored"
            return await self.hub.notify(user_id, nudge.text, nudge=nudge)

        if item.kind == OutboxKind.NEXT_WAKE:
            self.schedule_wake(user_id, item.payload)
            return "scheduled"

        return "ignored"

    def schedule_wake(self, user_id: str, payload: dict) -> str:
        kind = JobKind(str(payload.get("job_kind", JobKind.ROUTINE.value)))
        at_raw = payload.get("at")
        at = at_raw if isinstance(at_raw, datetime) else datetime.fromisoformat(str(at_raw))
        if at.tzinfo is None:
            at = at.replace(tzinfo=ZoneInfo(self.routines_for(user_id).timezone))
        job_id = new_id("w")
        with self.db.session() as s:
            s.add(
                JobRow(id=job_id, user_id=user_id, kind=kind.value, prompt=payload.get("prompt"),
                       payload={k: v for k, v in payload.items() if k not in ("at", "job_kind", "prompt")},
                       source="next_wake", scheduled_for=at, status="pending", created_at=self.clock())
            )
        return job_id
