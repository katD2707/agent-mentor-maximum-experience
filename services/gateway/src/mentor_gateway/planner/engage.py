"""Keeping a learner coming back, the way Duolingo does it, on top of the plan (CONTRACTS 12.1).

- **Streak**: consecutive local days with a study session, counted up to today (or yesterday while today is still open).
- **Mực's voice**: reminder texts come from small sets of lines, picked per day so they do not repeat word for word, and
  they carry the lesson, the minutes and the streak.
- **Streak saver**: with a streak of 2+ days and nothing done today, one reminder an hour before the age band's bedtime.
  It is cancelled as soon as the learner studies.
- **Remind me later**: a one-off reminder the learner asks for (the Today screen's "Để sau"), delivered like any other:
  scheduled by the device, pushed to the web. Never cancelled by a replan.
- **Backing off**: after 4 reminders in a row went unanswered since the last study session, only every other day keeps
  a reminder; studying again resets it.
No model: plain code, deterministic for a given day.
"""

import hashlib
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import select

from mentor_gateway.db import Database, User
from mentor_gateway.planner import events as ev
from mentor_gateway.planner.bands import TZ, band_for
from mentor_gateway.planner.profile import local, sessions
from mentor_gateway.planner.tables import Reminder
from mentor_gateway.planner.text import clean

OWN_KINDS = ("later", "streak")  # reminders that are not part of a plan: a replan never cancels them
BACKOFF_AFTER = 4  # reminders ignored in a row (since the last study session) before Mực reminds less
SAVER_BEFORE_BED = 60  # the streak saver fires this many minutes before bedtime
EARLIEST_MIN = 6 * 60 + 30  # no reminder before 06:30
LATER_MIN_AHEAD = timedelta(minutes=5)
LATER_MAX_AHEAD = timedelta(hours=48)
LATER_MAX_ACTIVE = 2
DAY_CAP = 3  # plan reminders (<= 2) plus the streak saver


class EngageError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


# ---- streak ------------------------------------------------------------------------------------------

def study_days(evs: list[dict]) -> set[date]:
    return {local(s["start"]).date() for s in sessions(evs)}


def streak(days: set[date], today: date) -> tuple[int, bool]:
    """(days in a row, studied today). A streak still counts on a day not studied yet: it ends at yesterday."""
    done = today in days
    d, n = (today if done else today - timedelta(days=1)), 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n, done


# ---- Mực's lines -------------------------------------------------------------------------------------

_STUDY = [
    ("Mực đây! {min} phút {what} nhé?", "Mực here! {min} minutes of {what}?"),
    ("Tới giờ {what} rồi. {min} phút thôi, Mực để sẵn bài cho {you}.", "Time for {what}. Just {min} minutes, your lesson is ready."),
    ("{what} đang chờ {you}. {min} phút là xong một phần.", "{what} is waiting. {min} minutes gets a part done."),
]
_STUDY_STREAK = [
    ("Chuỗi {n} ngày của {you} vẫn đang giữ. {min} phút {what} nhé?", "Your {n}-day streak is going strong. {min} minutes of {what}?"),
    ("Ngày thứ {next} liên tiếp nào! {min} phút {what}.", "Day {next} in a row! {min} minutes of {what}."),
]
_SAVER = [
    ("Hôm nay {you} chưa học. 5 phút thôi là giữ được chuỗi {n} ngày.", "Nothing done today yet. 5 minutes keeps your {n}-day streak."),
    ("Chuỗi {n} ngày sắp mất rồi! Mực để sẵn một bài ngắn cho {you}.", "Your {n}-day streak is about to end! A short lesson is ready."),
    ("Còn kịp giữ chuỗi {n} ngày đấy. Một bài ngắn trước khi ngủ nhé?", "There's still time to keep your {n}-day streak. One short lesson before bed?"),
]
_LATER = ("Tới giờ hẹn rồi: {what}. Mực để sẵn bài cho {you}.", "It's the time you picked: {what}. Your lesson is ready.")


def _pick(lines: list, *key: object):
    h = int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:8], 16)
    return lines[h % len(lines)]


def _you(band: str | None) -> str:
    return "bạn" if band == "uni" else "em"


def study_text(what_vi: str, what_en: str, minutes: int, streak_days: int, key: str, band: str | None) -> tuple[str, str]:
    """A study reminder in Mực's voice, one line of a small set chosen by `key` (the reminder's date and slot)."""
    lines = _STUDY_STREAK if streak_days >= 2 else _STUDY
    vi, en = _pick(lines, key)
    args = {"min": minutes, "n": streak_days, "next": streak_days + 1, "you": _you(band)}
    return (clean(vi.format(what=what_vi, **args), 120), clean(en.format(what=what_en, **args), 120))


def saver_text(streak_days: int, key: str, band: str | None) -> tuple[str, str]:
    vi, en = _pick(_SAVER, key)
    return clean(vi.format(n=streak_days, you=_you(band)), 120), clean(en.format(n=streak_days), 120)


# ---- backing off -------------------------------------------------------------------------------------

def ignored_in_a_row(db: Database, user_id: str, now: datetime, since: datetime | None) -> int:
    """Past reminders since `since` (the last study session) that got `ignored`, counted back from the newest."""
    with db.session() as s:
        q = select(Reminder).where(Reminder.user_id == user_id, Reminder.at <= now,
                                   Reminder.status.in_(("scheduled", "pushed"))).order_by(Reminder.at.desc()).limit(20)
        rows = list(s.scalars(q))
    n = 0
    for r in rows:
        if since and r.at <= since:
            break
        if r.outcome == "ignored":
            n += 1
        elif r.outcome in ("opened", "snoozed"):
            break
    return n


def thin(reminders: list[dict]) -> list[dict]:
    """Backing off: one reminder on every other day, starting with the first day that has one."""
    out, first = [], None
    for r in sorted(reminders, key=lambda x: x["at"]):
        d = datetime.fromisoformat(r["at"]).astimezone(TZ).date()
        first = first or d
        if (d - first).days % 2 == 0 and not any(datetime.fromisoformat(o["at"]).astimezone(TZ).date() == d for o in out):
            out.append(r)
    return out


# ---- the learner's state for Today -------------------------------------------------------------------

def state(db: Database, user: User, now: datetime, evs: list[dict] | None = None) -> dict:
    evs = evs if evs is not None else ev.load(db, user.id, now, days=60)
    days = study_days(evs)
    n, done = streak(days, local(now).date())
    starts = [s["start"] for s in sessions(evs)]
    backoff = ignored_in_a_row(db, user.id, now, max(starts) if starts else None) >= BACKOFF_AFTER
    return {"streak": {"days": n, "today_done": done}, "reminders_backoff": backoff}


# ---- the scheduler's pass ----------------------------------------------------------------------------

def maintain(db: Database, user: User, now: datetime) -> None:
    """Run by the planner tick: drop own reminders made pointless by studying, and keep tonight's streak saver."""
    evs = ev.load(db, user.id, now, days=60)
    loc = local(now)
    today = loc.date()
    days = study_days(evs)
    n, done = streak(days, today)
    starts = [s["start"] for s in sessions(evs)]
    last = max(starts) if starts else None
    band = band_for(user.age_band)
    saver_id = f"r-s-{today.isoformat()}-{hashlib.sha256(user.id.encode()).hexdigest()[:10]}"
    with db.session() as s:
        for r in s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.status == "scheduled",
                                                  Reminder.kind.in_(OWN_KINDS), Reminder.at > now)):
            if last and last > r.created_at and local(r.at).date() == today:
                r.status, r.updated_at = "cancelled", now  # studied since it was set up: no need to remind today
        if done or n < 2 or s.get(Reminder, saver_id) is not None:
            return
        at_min = band.bedtime_min - SAVER_BEFORE_BED
        at = datetime(today.year, today.month, today.day, at_min // 60, at_min % 60, tzinfo=TZ)
        if at <= now + timedelta(minutes=10) or at_min < EARLIEST_MIN:
            return
        start = datetime(today.year, today.month, today.day, tzinfo=TZ)
        count = len(list(s.scalars(select(Reminder.id).where(
            Reminder.user_id == user.id, Reminder.at >= start, Reminder.at < start + timedelta(days=1),
            Reminder.status.in_(("scheduled", "pushed"))))))
        if count >= DAY_CAP:
            return
        vi, en = saver_text(n, today.isoformat(), user.age_band)
        s.add(Reminder(id=saver_id, user_id=user.id, at=at, kind="streak", text_vi=vi, text_en=en, deep_link="/",
                       status="scheduled", created_at=now, updated_at=now))


# ---- remind me later ---------------------------------------------------------------------------------

def create_later(db: Database, user: User, now: datetime, at: datetime, title_vi: str, title_en: str,
                 deep_link: str, quiet_until: datetime | None) -> Reminder:
    if at.tzinfo is None:
        at = at.replace(tzinfo=TZ)
    if at < now + LATER_MIN_AHEAD or at > now + LATER_MAX_AHEAD:
        raise EngageError("bad_time", "Chọn một giờ trong 2 ngày tới.")
    loc = local(at)
    minute = loc.hour * 60 + loc.minute
    if minute >= band_for(user.age_band).bedtime_min or minute < EARLIEST_MIN:
        raise EngageError("bedtime", "Giờ đó muộn quá, Mực không nhắc lúc đi ngủ.")
    if quiet_until and at < quiet_until:
        raise EngageError("quiet", "Em đang bật tạm im lặng tới giờ đó.")
    link = deep_link if deep_link.startswith("/") else "/"
    what_vi, what_en = clean(title_vi or "bài học", 60), clean(title_en or title_vi or "your lesson", 60)
    vi, en = _LATER
    row = Reminder(id="r-" + secrets.token_hex(8), user_id=user.id, at=at, kind="later",
                   text_vi=clean(vi.format(what=what_vi, you=_you(user.age_band)), 140), text_en=clean(en.format(what=what_en), 140),
                   deep_link=link[:300], status="scheduled", created_at=now, updated_at=now)
    with db.session() as s:
        active = list(s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.kind == "later",
                                                       Reminder.status == "scheduled", Reminder.at > now)
                                .order_by(Reminder.created_at)))
        for old in active[: max(0, len(active) - LATER_MAX_ACTIVE + 1)]:
            old.status, old.updated_at = "cancelled", now  # the newest ask wins
        s.add(row)
        s.flush()
        s.expunge(row)
    return row
