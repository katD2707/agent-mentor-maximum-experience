"""XP ledger and level math (CONTRACTS-LANGGA section 1). Every award is idempotent on (user, source, ref).

Awards run in their own transaction. Call them after the caller's own transaction has committed (SQLite allows one
writer at a time, so a nested write from inside another open write would wait for it).
"""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mentor_gateway.db import Database
from mentor_gateway.langga.tables import XpEvent
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
XP_PER_LEVEL = 100
# source -> XP; the rules shown in lg-09
AMOUNTS = {
    "lesson_done": 20, "lesson_perfect": 5, "practice_right": 2, "fix_right": 3, "mock_submit": 40, "paper_submit": 40,
    "boss_beaten": 50, "notes_review": 2, "focus_full": 5,
}
FOCUS_PER_MINUTE = 1  # source `focus`: +1 per minute done
FOCUS_SOURCES = ("focus", "focus_full")
FOCUS_DAILY_CAP = 120  # quiet cap on both focus sources together
SOURCES = (*AMOUNTS, "focus")


def level_of(xp: int) -> int:
    return 1 + max(0, xp) // XP_PER_LEVEL


def stage_of_level(level: int) -> int:
    """Growth stage for the art: 1 Gà con (lv 1), 2 Gà choai (lv 2-4), 3 Trưởng thành (lv 5-9), 4 Cao thủ (lv 10+)."""
    return 1 if level <= 1 else 2 if level <= 4 else 3 if level <= 9 else 4


def level_info(xp: int) -> dict:
    lv = level_of(xp)
    return {"level": lv, "xp": xp, "xp_in_level": xp % XP_PER_LEVEL, "stage": stage_of_level(lv)}


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, VN)
    return start, start + timedelta(days=1)


class XpService:
    def __init__(self, db: Database, clock: Clock) -> None:
        self.db, self.clock = db, clock

    def award_many(self, user_id: str, awards: list[tuple[str, str, str, int]]) -> list[dict]:
        """`awards` = [(chicken, source, ref, amount)]. Returns the awards that were new, summed per (chicken, source):
        `[{chicken, source, amount, level_up}]`. Duplicates (same source and ref) are skipped silently."""
        awards = [a for a in awards if a[3] > 0]
        if not awards:
            return []
        now = self.clock()
        out: dict[tuple[str, str], dict] = {}
        with self.db.session() as s:
            totals: dict[str, int] = {}
            for chicken, source, ref, amount in awards:
                if chicken not in totals:
                    totals[chicken] = int(s.scalar(select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
                        XpEvent.user_id == user_id, XpEvent.chicken == chicken)) or 0)
                try:
                    with s.begin_nested():
                        s.add(XpEvent(user_id=user_id, chicken=chicken, source=source, ref=ref[:200], amount=amount,
                                      created_at=now))
                        s.flush()
                except IntegrityError:
                    continue
                before = level_of(totals[chicken])
                totals[chicken] += amount
                row = out.setdefault((chicken, source), {"chicken": chicken, "source": source, "amount": 0, "level_up": False})
                row["amount"] += amount
                row["level_up"] = row["level_up"] or level_of(totals[chicken]) > before
        return list(out.values())

    def award(self, user_id: str, chicken: str, source: str, ref: str, amount: int | None = None) -> list[dict]:
        return self.award_many(user_id, [(chicken, source, ref, AMOUNTS[source] if amount is None else amount)])

    # ---- reads -------------------------------------------------------------------------------------------

    def totals(self, user_id: str) -> dict[str, int]:
        with self.db.session() as s:
            rows = s.execute(select(XpEvent.chicken, func.sum(XpEvent.amount)).where(XpEvent.user_id == user_id)
                             .group_by(XpEvent.chicken)).all()
        return {c: int(n or 0) for c, n in rows}

    def total(self, user_id: str, chicken: str) -> int:
        return self.totals(user_id).get(chicken, 0)

    def existing_refs(self, user_id: str, source: str, refs: list[str]) -> set[str]:
        if not refs:
            return set()
        with self.db.session() as s:
            return set(s.scalars(select(XpEvent.ref).where(XpEvent.user_id == user_id, XpEvent.source == source,
                                                           XpEvent.ref.in_(refs))))

    def sum_on_day(self, user_id: str, source: str | tuple[str, ...], day: date) -> int:
        sources = (source,) if isinstance(source, str) else source
        start, end = day_bounds(day)
        with self.db.session() as s:
            return int(s.scalar(select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
                XpEvent.user_id == user_id, XpEvent.source.in_(sources), XpEvent.created_at >= start,
                XpEvent.created_at < end)) or 0)

    def today(self) -> date:
        return self.clock().astimezone(VN).date()

    def active_days(self, user_id: str, since: date) -> set[date]:
        start, _ = day_bounds(since)
        with self.db.session() as s:
            return {ts.astimezone(VN).date() for ts in s.scalars(select(XpEvent.created_at).where(
                XpEvent.user_id == user_id, XpEvent.created_at >= start))}

    def chickens_active_on(self, user_id: str, day: date) -> set[str]:
        start, end = day_bounds(day)
        with self.db.session() as s:
            return set(s.scalars(select(XpEvent.chicken).where(
                XpEvent.user_id == user_id, XpEvent.created_at >= start, XpEvent.created_at < end).distinct()))

    def last_active(self, user_id: str) -> dict[str, datetime]:
        with self.db.session() as s:
            rows = s.execute(select(XpEvent.chicken, func.max(XpEvent.created_at)).where(XpEvent.user_id == user_id)
                             .group_by(XpEvent.chicken)).all()
        return {c: ts for c, ts in rows}

    def week(self, user_id: str) -> dict[str, list[int]]:
        """Per chicken, XP of the last 7 local days, oldest first (the last number is today)."""
        today = self.today()
        first = today - timedelta(days=6)
        start, _ = day_bounds(first)
        out: dict[str, list[int]] = defaultdict(lambda: [0] * 7)
        with self.db.session() as s:
            for chicken, ts, amount in s.execute(select(XpEvent.chicken, XpEvent.created_at, XpEvent.amount).where(
                    XpEvent.user_id == user_id, XpEvent.created_at >= start)):
                idx = (ts.astimezone(VN).date() - first).days
                if 0 <= idx < 7:
                    out[chicken][idx] += amount
        return dict(out)

    def week_breakdown(self, user_id: str, chicken: str | None = None) -> dict[str, dict[str, int]]:
        """Per chicken, XP of the last 7 days by source (lg-09 rows)."""
        start, _ = day_bounds(self.today() - timedelta(days=6))
        out: dict[str, dict[str, int]] = defaultdict(dict)
        with self.db.session() as s:
            q = select(XpEvent.chicken, XpEvent.source, func.sum(XpEvent.amount)).where(
                XpEvent.user_id == user_id, XpEvent.created_at >= start).group_by(XpEvent.chicken, XpEvent.source)
            if chicken:
                q = q.where(XpEvent.chicken == chicken)
            for c, src, n in s.execute(q):
                out[c][src] = int(n or 0)
        return dict(out)

    def forget(self, s, user_id: str) -> None:
        """Delete every Làng gà row of a learner (ledger, chickens, flags, study sessions, chat turns). Practice /
        paper / course-mock sessions are `PracticeService.forget`'s."""
        from sqlalchemy import delete

        from mentor_gateway.langga.tables import ChatTurn, FocusSession, LanggaState, UserChicken

        for model in (XpEvent, UserChicken, LanggaState, FocusSession, ChatTurn):
            s.execute(delete(model).where(model.user_id == user_id))
