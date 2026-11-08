"""GET /research: everything hs-11 shows in one call (CONTRACTS 15.1, 15.8)."""

from __future__ import annotations

import logging

from mentor_schemas.research import (
    EXPERIMENTS_IN_OVERVIEW,
    SUGGESTIONS_FEATURED,
    UPCOMING_MAX_ITEMS,
    LiveLine,
    ReadingEntry,
    ReadingList,
    ReadNext,
    ResearchOverview,
    UpcomingItem,
)
from sqlalchemy import select

from mentor_gateway.db import User
from mentor_gateway.planner.bands import TZ
from mentor_gateway.planner.text import clean
from mentor_gateway.research import milestones, prompts, status
from mentor_gateway.research.base import ModelUnavailable, surname_line
from mentor_gateway.research.deadlines import DeadlinesMixin
from mentor_gateway.research.lab import LabMixin
from mentor_gateway.research.meetings import MeetingsMixin
from mentor_gateway.research.reading import ReadingMixin
from mentor_gateway.research.tables import MeetingRow

log = logging.getLogger(__name__)

HERO_DEADLINE_DAYS = 14


class OverviewMixin(DeadlinesMixin, MeetingsMixin, LabMixin, ReadingMixin):
    def status_line(self, user_id: str) -> LiveLine:
        return LiveLine(**status.status_line(self.db, user_id, self.clock()))

    async def _hero(self, user: User, rl: ReadingList) -> ReadNext | None:
        """The "Đọc tiếp" entry: the reading one opened last, else the oldest new one whose reason mentions a deadline, else the
        newest new one. Its reason is tied to a deadline within 14 days by one model sentence (cached per day)."""
        active = [e for e in rl.items if e.status in ("new", "reading")]
        if not active:
            return None
        reading = [e for e in active if e.status == "reading"]
        new = [e for e in active if e.status == "new"]
        pick: ReadingEntry | None = None
        if reading:
            pick = max(reading, key=lambda e: e.opened_at or e.added_at)
        elif new:
            due = sorted((e for e in new if any(w in e.reason.lower() for w in ("hạn", "deadline", "due"))), key=lambda e: e.added_at)
            pick = due[0] if due else max(new, key=lambda e: e.added_at)
        if pick is None:
            return None
        reason = await self._hero_reason(user, pick)
        return ReadNext(paper_id=pick.id, title=pick.paper.title, authors_line=surname_line(pick.paper.authors, pick.paper.year),
                        status=pick.status, minutes_spent=pick.minutes_spent, reason=reason, deep_link=f"/nghien-cuu/paper/{pick.id}")

    async def _hero_reason(self, user: User, e: ReadingEntry) -> str:
        today = self.clock().astimezone(TZ).date()
        near = [m for m in self.list_deadlines(user.id) if m.confirmed and 0 <= m.days_left <= HERO_DEADLINE_DAYS]
        if not near:
            return e.reason
        m = near[0]
        lang = user.language or "vi"
        key = (user.id, today.isoformat(), e.id, f"{m.id}:{m.due_date}:{lang}")
        if key not in self.hero_cache:
            title, _q, _k = self.topic(user.id)
            line = e.reason
            try:
                d = await self.llm_json(
                    prompts.fill(prompts.HERO, lang=prompts.lang_name(lang)),
                    f"Deadline: {m.title}, {m.days_left} days left\nThesis: {title}\nPaper: {e.paper.title}\nWhy it matters: {e.reason}",
                    timeout=10)
                if isinstance(d.get("line"), str) and d["line"].strip():
                    line = clean(d["line"], 200)
            except ModelUnavailable:
                pass
            self.hero_cache[key] = line
        return self.hero_cache[key]

    def upcoming(self, user_id: str) -> list[UpcomingItem]:
        now = self.clock()
        today = now.astimezone(TZ).date()
        items: list[UpcomingItem] = []
        for m in self.list_deadlines(user_id):
            if m.days_left >= 0:
                items.append(UpcomingItem(kind="deadline", id=m.id, title=m.title, date=m.due_date, time=m.due_time,
                                          days_left=m.days_left, confirmed=m.confirmed, original_text=m.original_text,
                                          planned_sessions=m.planned_sessions))
        with self.db.session() as s:
            rows = list(s.scalars(select(MeetingRow).where(MeetingRow.user_id == user_id, MeetingRow.status == "scheduled",
                                                           MeetingRow.at > now).order_by(MeetingRow.at)))
            s.expunge_all()
        for r in rows:
            loc = r.at.astimezone(TZ)
            items.append(UpcomingItem(kind="meeting", id=r.id, title=r.title, date=loc.date().isoformat(), time=loc.strftime("%H:%M"),
                                      days_left=(loc.date() - today).days, confirmed=True,
                                      agenda_ready=bool((r.agenda or {}).get("drafted_at"))))
        items.sort(key=lambda i: (i.date, i.time or "99:99"))
        return items[:UPCOMING_MAX_ITEMS]

    async def overview(self, user: User) -> ResearchOverview:
        rl = self.reading_list(user.id)
        thesis = self.thesis_milestones(user.id)
        return ResearchOverview(
            profile=self.profile_view(user.id), status_line=self.status_line(user.id), hero=await self._hero(user, rl),
            upcoming=self.upcoming(user.id), reading_list=rl, suggestions=self.suggestions(user.id, featured_only=True)[:SUGGESTIONS_FEATURED],
            milestones=thesis, goal_id=milestones.GOAL_ID if thesis else None,  # the goal is visible while a thesis milestone exists
            experiments=self.list_experiments(user.id, EXPERIMENTS_IN_OVERVIEW).items, discovery=self.discovery_status(user.id))

