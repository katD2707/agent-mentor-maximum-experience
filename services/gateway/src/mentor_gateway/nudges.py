"""Proactive routines and notification actions (CONTRACTS section 9, owner N).

Routines (`routines.yaml`, defaults in mentor-content/workspace-templates): a routine that is not in the file is
off, so existing workspaces keep what they have and only new workspaces get the defaults.
- `morning_checkin` (07:30 weekdays) and `evening_wrapup` (21:00): agent jobs (skill daily-checkin) that send a
  `checkin` notification with answer actions and a `checkin` card into the chat.
- `review_due`: handled by the gateway alone (no sandbox, no model call; the routine's prompt is ignored): when a
  `learning/<subject>/review-queue.md` has rows due today or overdue, one `review` notification, at most one per
  local day (none if the agent already sent a `review` notification that day).
All three are proactive: skipped when proactivity is `off`, when the run time is in quiet hours, and during a
crisis hold. Other routines (nightly reflection, reports, ...) are jobs and never affected.

Actions (`POST /api/notifications/{id}/action`): open, done, snooze_1h (always allowed) and start_focus,
answer:<x> (only when the notification offers them). Idempotent per (id, action, delivery number); audited
without content.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from mentor_schemas import JobKind, JobRequest, ProactivityLevel
from mentor_schemas.sandbox_api import NOTIFICATION_ACTION_PATTERN
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mentor_gateway.db import (
    Database,
    JobRow,
    NotificationActionRow,
    NotificationMeta,
    NotificationRow,
    OutboxSeen,
    User,
)
from mentor_gateway.jobs import JobStore
from mentor_gateway.mirror import Mirror
from mentor_gateway.notifications import NotificationHub, Nudge, in_quiet_hours
from mentor_gateway.settings import Clock
from mentor_gateway.users import UserService

log = logging.getLogger(__name__)

PROACTIVE_ROUTINES = frozenset({"morning_checkin", "evening_wrapup", "review_due"})
ALWAYS_ALLOWED_ACTIONS = frozenset({"open", "done", "snooze_1h"})
ACTION_RE = re.compile(NOTIFICATION_ACTION_PATTERN)
SNOOZE = timedelta(hours=1)

_REVIEW_QUEUE = re.compile(r"^learning/[^/]+/review-queue\.md$")
# | skill_id | Tên | Mastery | Đến hạn | Ghi chú |  (bkt_update output)
_REVIEW_ROW = re.compile(r"^\|\s*([^|\s][^|]*?)\s*\|[^|]*\|\s*[0-9.]+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|")


def count_due_reviews(mirror: Mirror, user_id: str, today: date) -> int:
    """Skills due today or overdue across `learning/*/review-queue.md` (read from the mirror)."""
    due: set[str] = set()
    for entry in mirror.ls_tree(user_id):
        if entry.type != "file" or not _REVIEW_QUEUE.match(entry.path):
            continue
        for line in (mirror.read_text(user_id, entry.path) or "").splitlines():
            m = _REVIEW_ROW.match(line.strip())
            if m and m.group(1) != "skill_id":
                try:
                    if date.fromisoformat(m.group(2)) <= today:
                        due.add(f"{entry.path}:{m.group(1)}")
                except ValueError:
                    continue
    return len(due)


class NudgeService:
    def __init__(self, db: Database, hub: NotificationHub, jobs: JobStore, users: UserService, mirror: Mirror,
                 clock: Clock, audit: Callable[[str, str, str], None], kick: Callable[[datetime], object]) -> None:
        self.db = db
        self.hub = hub
        self.jobs = jobs
        self.users = users
        self.mirror = mirror
        self.clock = clock
        self.audit = audit  # (user_id, kind, detail) -> audit_log row, detail without content
        self.kick = kick  # runs due jobs now (JobRunner.run_due), so a tapped action does not wait for the tick

    # ---- routines ----------------------------------------------------------------------------

    async def before_job(self, user: User, row: JobRow) -> tuple[str, str | None, str | None] | None:
        """Called by the JobRunner before a job runs. Returns (status, summary, error) when the gateway handled or
        skipped it, None when the sandbox should run it."""
        rid = row.source.split(":", 1)[1] if row.source.startswith("routine:") else None
        if rid not in PROACTIVE_ROUTINES:
            return None
        routines = await asyncio.to_thread(self.users.routines, user)
        if routines.proactivity == ProactivityLevel.OFF:
            return "skipped", None, "proactivity off"
        if in_quiet_hours(routines, row.scheduled_for):
            return "skipped", None, "quiet hours"
        if self.hub.hold_active(user.id):
            return "skipped", None, "nudge hold"
        if rid == "review_due":
            return await self.review_due(user, routines.timezone)
        return None

    def _review_nudged_on(self, user_id: str, day: date, tz: ZoneInfo) -> bool:
        start = datetime.combine(day, datetime.min.time(), tz)
        with self.db.session() as s:
            n = s.scalars(
                select(NotificationRow.id)
                .join(NotificationMeta, NotificationMeta.notification_id == NotificationRow.id)
                .where(NotificationRow.user_id == user_id, NotificationMeta.kind == "review",
                       NotificationRow.created_at >= start, NotificationRow.created_at < start + timedelta(days=1))
            ).first()
        return n is not None

    async def review_due(self, user: User, timezone: str) -> tuple[str, str | None, str | None]:
        tz = ZoneInfo(timezone)
        now = self.clock()
        today = now.astimezone(tz).date()
        if self._review_nudged_on(user.id, today, tz):
            return "skipped", None, "already nudged today"
        n = await asyncio.to_thread(count_due_reviews, self.mirror, user.id, today)
        if n == 0:
            return "skipped", None, "nothing due"
        try:
            with self.db.session() as s:
                s.add(OutboxSeen(user_id=user.id, dedupe_key=f"review_due:{today.isoformat()}", kind="review_due",
                                 created_at=now))
        except IntegrityError:
            return "skipped", None, "already nudged today"
        end_of_day = datetime.combine(today + timedelta(days=1), datetime.min.time(), tz)
        nudge = Nudge(
            text=f"Có {n} kỹ năng đến hạn ôn hôm nay. Khoảng 10 phút là đủ.", kind="review",
            title="Đến giờ ôn nhanh",
            actions=[{"id": "open", "label": "Ôn ngay"}, {"id": "snooze_1h", "label": "Nhắc lại sau 1 giờ"},
                     {"id": "done", "label": "Hôm nay thôi"}],
            mascot="happy", prefill="Mình ôn nhanh các kỹ năng đến hạn nhé.", expires_at=end_of_day,
            source="gateway:review_due", push_safe=True,
        )
        result = await self.hub.notify(user.id, nudge.text, nudge=nudge)
        return "ok", f"Nhắc ôn: {n} kỹ năng đến hạn ({result})", None

    # ---- actions -----------------------------------------------------------------------------

    async def apply(self, user: User, notification_id: int, action: str) -> dict:
        """Raises LookupError (not found / not the owner) or ValueError (invalid or not offered)."""
        item = self.hub.get(user.id, notification_id)
        if item is None:
            raise LookupError(notification_id)
        if not ACTION_RE.match(action):
            raise ValueError("unknown action")
        offered = {a.get("id") for a in item.actions}
        if action not in ALWAYS_ALLOWED_ACTIONS and action not in offered:
            raise ValueError("action not offered by this notification")
        verb = action.split(":", 1)[0]
        now = self.clock()
        key = (notification_id, action, item.deliveries)
        try:  # claim first: a double tap (or a retry) never repeats the side effects
            with self.db.session() as s:
                s.add(NotificationActionRow(notification_id=key[0], action=key[1], delivery=key[2], user_id=user.id,
                                            created_at=now, result={}))
        except IntegrityError:
            with self.db.session() as s:
                done = s.get(NotificationActionRow, key)
                return dict(done.result or {"ok": True, "action": action})
        result: dict = {"ok": True, "action": action, "id": notification_id}
        if verb == "open":
            self._update(notification_id, read=now)
            result["prefill"] = item.prefill
        elif verb == "done":
            self._update(notification_id, read=now, dismiss=True)
        elif verb == "snooze_1h":
            until = now + SNOOZE
            self._update(notification_id, snooze_until=until)
            result["snoozed_until"] = until.isoformat()
        elif verb == "start_focus":
            self._update(notification_id, read=now)
            result["job_id"] = self._enqueue(user, item, f"n{notification_id}-focus-{item.deliveries}",
                                             self._focus_prompt(item), verb)
        else:  # answer:<x>
            x = action.split(":", 1)[1]
            label = next((str(a.get("label", "")) for a in item.actions if a.get("id") == action), x)
            self._update(notification_id, read=now, answer=x)
            result["job_id"] = self._enqueue(user, item, f"n{notification_id}-answer-{item.deliveries}-{x}",
                                             self._answer_prompt(item, x, label), action)
        with self.db.session() as s:
            s.get(NotificationActionRow, key).result = result
        try:
            self.audit(user.id, "notification_action", f"id={notification_id}; kind={item.kind}; action={verb}")
        except Exception:  # auditing must not break the action
            log.warning("could not write the notification_action audit row", exc_info=True)
        return result  # a snoozed notification goes out again on the first scheduler tick after `snoozed_until`

    def _update(self, nid: int, *, read: datetime | None = None, dismiss: bool = False,
                snooze_until: datetime | None = None, answer: str | None = None) -> None:
        with self.db.session() as s:
            row = s.get(NotificationRow, nid)
            meta = s.get(NotificationMeta, nid)
            if meta is None:  # a row from before notification_meta existed
                meta = NotificationMeta(notification_id=nid, user_id=row.user_id, kind="nudge", title="",
                                        body=row.text, actions=[], deliveries=1 if row.status == "delivered" else 0)
                s.add(meta)
            if read is not None and meta.read_at is None:
                meta.read_at = read
            if dismiss and row.status == "pending":
                row.status = "dismissed"
            if snooze_until is not None and row.status in ("pending", "delivered"):
                row.status = "pending"
                meta.not_before = snooze_until
                meta.cap_exempt = True  # the learner asked for it again: not a new interruption
                meta.read_at = None
                if meta.expires_at is not None and meta.expires_at < snooze_until + SNOOZE:
                    meta.expires_at = snooze_until + SNOOZE
            if answer is not None:
                meta.answer = answer
                meta.answered_at = read

    def _enqueue(self, user: User, item, job_id: str, prompt: str, action: str) -> str:
        profile = self.users.profile(user)
        # `source` tells the harness the learner started this job (start_focus/celebrate allowed, CONTRACTS 9)
        payload = {"source": "notification_action", "action": action, "notification_id": item.id,
                   "notification_kind": item.kind}
        self.jobs.enqueue(JobRequest(job_id=job_id, user_id=user.id, profile=profile, kind=JobKind.ROUTINE,
                                     prompt=prompt, payload=payload, scheduled_for=self.clock()),
                          source=f"notification:{item.id}")
        try:
            self.kick(self.clock())
        except Exception:
            log.exception("starting job %s", job_id)
        return job_id

    @staticmethod
    def _context(item) -> str:
        title = f"“{item.title}”: " if item.title else ""
        return f"lời nhắn ({item.kind}) {title}{item.body}"

    def _answer_prompt(self, item, x: str, label: str) -> str:
        return (f"Dùng skill daily-checkin, phần C. Người học vừa trả lời {self._context(item)} "
                f"— chọn “{label}” (answer:{x}).")

    def _focus_prompt(self, item) -> str:
        focus = item.focus or {}
        task, minutes = str(focus.get("task") or "").strip()[:200], focus.get("minutes")
        if task and isinstance(minutes, int) and 5 <= minutes <= 90:  # a focus_end nudge: one more session
            return (f"Người học bấm “Thêm một phiên” sau phiên tập trung “{task}”. Gọi start_focus ngay với task "
                    f"“{task}” và minutes {minutes}. Không gọi notify_user. Tóm tắt 1 câu.")
        return (f"Người học bấm “Bắt đầu tập trung” trên {self._context(item)}. Gọi start_focus ngay: task ngắn lấy "
                "từ lời nhắn (không rõ thì lấy việc đầu tiên chưa xong hôm nay trong goals/plans/this-week.md), "
                "minutes 25 trừ khi lời nhắn nêu số phút. Không gọi notify_user. Tóm tắt 1 câu.")
