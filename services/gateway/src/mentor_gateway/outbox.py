"""Deliver OutboxItems returned by the sandbox (turn `done` events and JobResults).

Idempotent on `dedupe_key` per user. Crisis alerts are recorded only in the ops audit table, never in
the workspace or anything the learner can read.

Parent reports: the sandbox drafts them in `.mentor/report-drafts/<name>.md` (hidden from the learner). The gateway
does not trust the sandbox's check_report: it re-runs the leak checks (mentor_parent_channel.find_leaks) on the
draft read from the mirror, refuses and audits on failure, and only after the parent channel delivered the report
moves it to `reports/<name>.md` (one system commit). So the learner sees a report exactly when it has been sent.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from mentor_parent_channel import find_leaks
from mentor_schemas import JobKind, OutboxItem, OutboxKind, Profile, RoutinesFile, WorkspacePaths
from sqlalchemy.exc import IntegrityError

from mentor_gateway.db import Database, JobRow, OutboxSeen, SentReport
from mentor_gateway.mirror import Mirror, normalize_path
from mentor_gateway.notifications import CRISIS_HOLD, NotificationHub, Nudge
from mentor_gateway.parent import ParentChannel
from mentor_gateway.security import new_id
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

CRISIS_CATEGORIES = {"self_harm", "abuse", "harm_others", "run_away"}


class OutboxDispatcher:
    def __init__(
        self,
        db: Database,
        mirror: Mirror,
        hub: NotificationHub,
        parent: ParentChannel,
        clock: Clock,
        routines_for: Callable[[str], RoutinesFile],
    ) -> None:
        self.db = db
        self.mirror = mirror
        self.hub = hub
        self.parent = parent
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

    async def dispatch(self, user_id: str, profile: Profile, items: list[OutboxItem]) -> list[str]:
        """Handle every item; one failure does not stop the others. Returns a status per item."""
        results = []
        crisis = any(i.kind == OutboxKind.CRISIS_ALERT for i in items)
        if crisis:  # no nudges in a crisis context (CONTRACTS section 9): hold proactive kinds for a day
            self.hub.set_hold(user_id, self.clock() + CRISIS_HOLD)
        for item in items:
            if crisis and item.kind == OutboxKind.NOTIFY_USER:
                results.append("suppressed")
                continue
            if not self._claim(user_id, item):
                results.append("duplicate")
                continue
            try:
                results.append(await self._handle(user_id, profile, item))
            except Exception as exc:
                log.exception("outbox %s for %s failed", item.kind, user_id)
                results.append(f"error: {exc}")
        return results

    async def _handle(self, user_id: str, profile: Profile, item: OutboxItem) -> str:
        if item.kind == OutboxKind.NOTIFY_USER:
            try:
                nudge = Nudge.from_payload(item.payload)
            except ValueError:
                return "ignored"
            return await self.hub.notify(user_id, nudge.text, nudge=nudge)

        if item.kind == OutboxKind.PARENT_REPORT:
            if profile != Profile.THPT:
                return "ignored"
            return await self._parent_report(user_id, str(item.payload.get("path", "")))

        if item.kind == OutboxKind.CRISIS_ALERT:
            category = str(item.payload.get("category", ""))
            store = self.parent.store
            if profile != Profile.THPT or category not in CRISIS_CATEGORIES:
                store.record_audit(user_id, "crisis_alert_rejected", f"profile={profile.value}; category={category}")
                return "ignored"
            sent = await self.parent.send_crisis_alert(user_id, category)
            store.record_audit(user_id, "crisis_alert_dispatch", f"category={category}; delivered={sent}")
            return "sent" if sent else "not_sent"

        if item.kind == OutboxKind.NEXT_WAKE:
            self.schedule_wake(user_id, item.payload)
            return "scheduled"

        return "ignored"

    async def _parent_report(self, user_id: str, raw_path: str) -> str:
        draft = normalize_path(raw_path)
        drafts_dir = WorkspacePaths.REPORT_DRAFTS_DIR + "/"
        name = draft[len(drafts_dir):] if draft.startswith(drafts_dir) else ""
        if not name or "/" in name or not name.endswith(".md") or name == ".md":
            raise ValueError(f"parent_report path is not a draft in {drafts_dir}: {draft}")
        text = self.mirror.read_text(user_id, draft)
        if text is None:
            raise FileNotFoundError(draft)
        leaks = find_leaks(text)
        if leaks:
            # never log or store the report content (it is about a minor): only the names of the failed checks
            log.warning("parent report %s of %s blocked by the gateway leak check: %s", draft, user_id, leaks)
            self.parent.store.record_audit(user_id, "parent_report_blocked", f"path={draft}; checks={','.join(leaks)}")
            return "blocked"
        if not await self.parent.send_report(user_id, text):
            return "not_sent"
        sent_path = f"{WorkspacePaths.REPORTS_DIR}/{name}"
        with self.db.session() as s:
            row = s.get(SentReport, (user_id, sent_path))
            if row is None:
                s.add(SentReport(user_id=user_id, path=sent_path, sent_at=self.clock()))
        try:  # now (and only now) the learner may see it
            self.mirror.commit_files(user_id, {sent_path: text.encode("utf-8"), draft: None}, author="system",
                                     message=f"Đã gửi báo cáo cho phụ huynh: {sent_path}")
        except Exception:
            log.exception("moving sent report %s of %s to %s failed", draft, user_id, sent_path)
        return "sent"

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
