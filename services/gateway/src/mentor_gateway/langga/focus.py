"""Study room (lg-06): timed focus sessions that pay XP to a chicken. Server-trusted rules:
- +1 XP per minute done (never more than the planned minutes nor the time that really passed, +1 minute of slack), and +5
  more when the planned session is completed in full (`focus_full`);
- a quiet cap of 120 focus XP a day;
- each session starts and ends a behaviour session (`session_start` / `session_end`) so the planner sees it.
"""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from mentor_gateway.db import Database, User
from mentor_gateway.langga import subjects
from mentor_gateway.langga import xp as xpm
from mentor_gateway.langga.tables import FocusSession
from mentor_gateway.planner import events as planner_events
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

MIN_MINUTES, MAX_MINUTES = 5, 120
STALE_AFTER = timedelta(hours=3)  # an unfinished session this long after its end is dropped
SLACK_MINUTES = 1


def _err(status: int, code: str) -> HTTPException:
    return HTTPException(status, {"error": code})


def _view(f: FocusSession, now: datetime) -> dict:
    return {"id": f.id, "chicken": f.chicken, "minutes": f.minutes, "started_at": f.started_at.isoformat(),
            "ends_at": f.ends_at.isoformat(), "remaining_sec": max(0, int((f.ends_at - now).total_seconds())),
            "status": f.status}


class FocusService:
    def __init__(self, db: Database, clock: Clock, xp: xpm.XpService, village) -> None:
        self.db, self.clock, self.xp, self.village = db, clock, xp, village

    def _event(self, user_id: str, focus_id: str, kind: str, ts: datetime, data: dict) -> None:
        try:
            planner_events.record(self.db, user_id, f"focus-{focus_id}-{kind}", kind, ts, {"session": focus_id, **data})
        except Exception:
            log.warning("focus: behaviour event failed", exc_info=True)

    def start(self, user: User, minutes: int, chicken: str) -> dict:
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            raise _err(422, "bad_minutes")
        if chicken not in subjects.CHICKENS or not subjects.valid_for_band(chicken, user.age_band):
            raise _err(400, "not_in_stage")
        now = self.clock()
        stale: list[FocusSession] = []
        with self.db.session() as s:
            for old in s.scalars(select(FocusSession).where(FocusSession.user_id == user.id, FocusSession.status == "active")):
                old.status = "abandoned"  # a new session replaces one that was never finished
                old.finished_at = now
                stale.append(old)
            f = FocusSession(id=f"f-{secrets.token_hex(6)}", user_id=user.id, chicken=chicken, minutes=minutes,
                             started_at=now, ends_at=now + timedelta(minutes=minutes), status="active")
            s.add(f)
            s.flush()
            out = {"id": f.id, "ends_at": f.ends_at.isoformat(), "chicken": chicken, "minutes": minutes}
        for old in stale:
            self._event(user.id, old.id, "session_end", now, {"seconds": max(0, int((now - old.started_at).total_seconds()))})
        self._event(user.id, out["id"], "session_start", now, {})
        return out

    def active(self, user: User) -> dict | None:
        now = self.clock()
        with self.db.session() as s:
            for f in s.scalars(select(FocusSession).where(FocusSession.user_id == user.id, FocusSession.status == "active")
                               .order_by(FocusSession.started_at.desc())):
                if now > f.ends_at + STALE_AFTER:
                    f.status, f.finished_at = "abandoned", now
                    continue
                return _view(f, now)
        return None

    def finish(self, user: User, focus_id: str, minutes_done: int) -> dict:
        now = self.clock()
        with self.db.session() as s:
            f = s.get(FocusSession, focus_id)
            if f is None or f.user_id != user.id:
                raise _err(404, "not_found")
            if f.status == "finished":  # idempotent: the same answer again
                done, gained, chicken = f.minutes_done, f.xp, f.chicken
                replay = True
            else:
                replay = False
                elapsed = int((now - f.started_at).total_seconds() // 60) + SLACK_MINUTES
                done = max(0, min(int(minutes_done), f.minutes, elapsed))
                chicken, planned = f.chicken, f.minutes
                f.status, f.finished_at, f.minutes_done = "finished", now, done
                gained = 0
        xp_rows: list[dict] = []
        if not replay:
            day = self.xp.today()
            room = max(0, xpm.FOCUS_DAILY_CAP - self.xp.sum_on_day(user.id, xpm.FOCUS_SOURCES, day))
            base = min(done * xpm.FOCUS_PER_MINUTE, room)
            full = min(xpm.AMOUNTS["focus_full"], room - base) if done >= planned else 0  # the whole planned session
            gained = base + full
            xp_rows = self.xp.award_many(user.id, [(chicken, "focus", focus_id, base), (chicken, "focus_full", focus_id, full)])
            with self.db.session() as s:
                s.get(FocusSession, focus_id).xp = gained
            self._event(user.id, focus_id, "session_end", now, {"seconds": min(done * 60, 6 * 3600)})
        return {"xp": xp_rows, "gained": gained, "minutes_done": done, "daily_cap": xpm.FOCUS_DAILY_CAP,
                "chicken": self.village.chicken_view(user, chicken)}
