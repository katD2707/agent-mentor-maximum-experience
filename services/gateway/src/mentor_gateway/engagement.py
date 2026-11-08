"""`GET /api/engagement` (CONTRACTS section 9): streak and focus/progress numbers, from data that already exists.

Days are local days in Asia/Ho_Chi_Minh; `week` = the last 7 local days including today.
- Learner-initiated activity on a day: a workspace commit by author `user` (practice evidence, web edits, uploads) or
  a tap on a notification action.
- `streak_days`: consecutive active days ending today, or ending yesterday while today has no activity yet (the
  streak never "breaks" during the day; no penalties, no grace logic beyond that).
- `focus_minutes`: focus sessions from `focus_end` jobs (start_focus schedules one per session, payload
  {card_id, task, minutes}; several jobs with the same card_id = an extended session). A session runs from
  scheduled_for - minutes to its last scheduled_for, cut at now and at the time a cancelled job finished; it
  counts on the local day it started.
- `today.done` / `week.milestones_done`: checkboxes `[x]` that were not checked at the start of the period:
  today in goals/goals.md + goals/plans/*.md, the week in goals/goals.md (milestones). Compared by item text.
- `week.mistakes_fixed`: new lines under "## Đã khắc phục" in learning/*/mistakes.md since the week started
  Cached per learner for a minute.
"""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from mentor_gateway.db import Database, JobRow, NotificationActionRow, User
from mentor_gateway.mirror import Mirror
from mentor_gateway.settings import Clock

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CACHE_SECONDS = 60
STREAK_LOOKBACK_DAYS = 400
HISTORY_COMMITS = 500

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CHECKBOX = re.compile(r"\[( |x|X)\]\s*([^\[\]·|\n]+)")
_GOAL_FILES = re.compile(r"^goals/(goals\.md|plans/[^/]+\.md)$")
_MISTAKES = re.compile(r"^learning/[^/]+/mistakes\.md$")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .;,-").lower()


def checked_items(md: str | None) -> set[str]:
    if not md:
        return set()
    return {_norm(t) for state, t in _CHECKBOX.findall(_COMMENT.sub("", md)) if state in "xX" and _norm(t)}


def fixed_mistakes(md: str | None) -> set[str]:
    """Bullet lines under the "## Đã khắc phục" heading."""
    if not md:
        return set()
    out, inside = set(), False
    for line in _COMMENT.sub("", md).splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("đã khắc phục")
        elif inside and line.lstrip().startswith(("- ", "* ")):
            out.add(_norm(line.lstrip()[2:]))
    return out


def streak(active: set[date], today: date) -> int:
    day = today if today in active else today - timedelta(days=1)
    n = 0
    while day in active:
        n += 1
        day -= timedelta(days=1)
    return n


class EngagementService:
    def __init__(self, db: Database, mirror: Mirror, clock: Clock) -> None:
        self.db = db
        self.mirror = mirror
        self.clock = clock
        self._cache: dict[str, tuple[datetime, dict]] = {}

    def summary(self, user: User) -> dict:
        now = self.clock()
        hit = self._cache.get(user.id)
        if hit is not None and hit[0] > now:
            return hit[1]
        data = self.compute(user.id, now)
        self._cache[user.id] = (now + timedelta(seconds=CACHE_SECONDS), data)
        return data

    def forget(self, user_id: str) -> None:
        self._cache.pop(user_id, None)

    # ---- sources -----------------------------------------------------------------------------

    def _active_days(self, user_id: str, today: date) -> set[date]:
        since = datetime.combine(today - timedelta(days=STREAK_LOOKBACK_DAYS), time.min, TZ)
        days: set[date] = set()
        with self.db.session() as s:
            for ts in s.scalars(select(NotificationActionRow.created_at).where(
                    NotificationActionRow.user_id == user_id, NotificationActionRow.created_at >= since)):
                days.add(ts.astimezone(TZ).date())
        for c in self.mirror.history(user_id, limit=HISTORY_COMMITS):
            if c.author == "user":
                days.add(c.ts.astimezone(TZ).date())
        return days

    def _focus_minutes(self, user_id: str, now: datetime, today: date, week_start: date) -> tuple[int, int]:
        since = datetime.combine(week_start, time.min, TZ)
        with self.db.session() as s:
            rows = s.scalars(select(JobRow).where(JobRow.user_id == user_id, JobRow.kind == "focus_end",
                                                  JobRow.scheduled_for >= since - timedelta(hours=3))).all()
        sessions: dict[str, list[datetime]] = {}  # card id -> [start, end]
        for r in rows:
            payload = r.payload or {}
            try:
                minutes = max(0, min(int(payload.get("minutes") or 0), 240))
            except (TypeError, ValueError):
                minutes = 0
            start, end = r.scheduled_for - timedelta(minutes=minutes), r.scheduled_for
            if r.status in ("cancelled", "canceled") and r.finished_at is not None:
                end = min(end, r.finished_at)
            key = str(payload.get("card_id") or r.id)
            if key in sessions:
                sessions[key][0] = min(sessions[key][0], start)
                sessions[key][1] = max(sessions[key][1], end)
            else:
                sessions[key] = [start, end]
        today_min = week_min = 0
        for start, end in sessions.values():
            mins = int(max(0.0, (min(end, now) - start).total_seconds()) // 60)
            day = start.astimezone(TZ).date()
            if week_start <= day <= today:
                week_min += mins
                if day == today:
                    today_min += mins
        return today_min, week_min

    def _progress(self, user_id: str, today: date, week_start: date) -> tuple[int, int, int]:
        paths = [e.path for e in self.mirror.ls_tree(user_id) if e.type == "file"]
        goal_paths = [p for p in paths if _GOAL_FILES.match(p)]
        mistake_paths = [p for p in paths if _MISTAKES.match(p)]
        day_rev = self.mirror.rev_before(user_id, datetime.combine(today, time.min, TZ))
        week_rev = self.mirror.rev_before(user_id, datetime.combine(week_start, time.min, TZ))
        files = goal_paths + mistake_paths
        # one slot per (point in time, file); a point before the first commit reads as empty
        specs = [f"{rev}:{p}" if rev else None for rev in ("refs/heads/main", day_rev, week_rev) for p in files]
        real = [x for x in specs if x]
        got = iter(self.mirror.read_batch(user_id, real))
        texts = [next(got) if x else None for x in specs]
        n = len(files)
        now_t, day_t, week_t = texts[:n], texts[n:2 * n], texts[2 * n:]
        idx = {p: i for i, p in enumerate(files)}
        done_today = sum(len(checked_items(now_t[idx[p]]) - checked_items(day_t[idx[p]])) for p in goal_paths)
        milestones = 0
        if "goals/goals.md" in idx:
            i = idx["goals/goals.md"]
            milestones = len(checked_items(now_t[i]) - checked_items(week_t[i]))
        mistakes = sum(len(fixed_mistakes(now_t[idx[p]]) - fixed_mistakes(week_t[idx[p]])) for p in mistake_paths)
        return done_today, milestones, mistakes

    # ---- summary -----------------------------------------------------------------------------

    def compute(self, user_id: str, now: datetime) -> dict:
        today = now.astimezone(TZ).date()
        week_start = today - timedelta(days=6)
        active = self._active_days(user_id, today)
        focus_today, focus_week = self._focus_minutes(user_id, now, today, week_start)
        done_today, milestones, mistakes = self._progress(user_id, today, week_start)
        return {
            "streak_days": streak(active, today),
            "today": {"focus_minutes": focus_today, "done": done_today},
            "week": {"focus_minutes": focus_week, "milestones_done": milestones, "mistakes_fixed": mistakes,
                     "active_days": sum(1 for d in active if week_start <= d <= today)},
        }
