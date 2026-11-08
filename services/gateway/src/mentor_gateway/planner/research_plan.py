"""Nghiên cứu in the planner (CONTRACTS 15.8): the `research` block of the study profile and the overlay that adds
`research` plan items and reminders to a plan the validator has already passed.

Code owns this part of the plan, the planner model never writes it (its input only carries counts): deadline preparation,
the default reading block (3 sessions x 30 minutes a week) and meeting action items become `kind: "research"` items placed
inside the section 12 limits (band minutes, 06:30 to bedtime, no overlap, at most 6 study days, nothing in the past);
confirmed deadlines, the agenda draft and the meeting day become `research` reminders that count in the 2 a day limit and
respect quiet mode, `quiet_until` and bedtime. A deadline within 48 hours always gets one if the limit allows.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from mentor_gateway.db import Database
from mentor_gateway.planner.bands import EARLIEST_MIN, TZ, hhmm, to_min
from mentor_gateway.planner.fallback import pick_slot
from mentor_gateway.planner.tables import Reminder
from mentor_gateway.planner.text import clean
from mentor_gateway.planner.types import PlanContext

READING_SESSIONS = 3
READING_MINUTES = 30
MAX_STUDY_DAYS = 6
MAX_REMINDERS_PER_DAY = 2
GAP_MIN = 10
LEAD_MIN = 15
CLOSE_DEADLINES = timedelta(days=3)


# ---- the profile block -----------------------------------------------------------------------------------------------

def research_block(db: Database, user_id: str, now: datetime) -> dict[str, Any]:
    """Open deadlines, the next meeting, open action items and the default reading block, from the research tables."""
    from mentor_gateway.research import milestones
    from mentor_gateway.research.tables import MeetingRow, ReadingEntryRow, ResearchProfileRow

    today = now.astimezone(TZ).date()
    deadlines = [{"id": m["id"], "title": m["title"], "due_date": m["due_date"], "due_time": m.get("due_time"),
                  "confirmed": bool(m.get("confirmed")), "kind": m.get("kind") or "other",
                  "days_left": (date.fromisoformat(m["due_date"]) - today).days}
                 for m in milestones.open_deadlines(db, user_id, today, horizon_days=45)]
    with db.session() as s:
        prof = s.get(ResearchProfileRow, user_id)
        meetings = list(s.scalars(select(MeetingRow).where(MeetingRow.user_id == user_id).order_by(MeetingRow.at)))
        hero = s.scalars(select(ReadingEntryRow.paper_id).where(
            ReadingEntryRow.user_id == user_id, ReadingEntryRow.removed_at.is_(None),
            ReadingEntryRow.status.in_(("new", "reading"))).order_by(ReadingEntryRow.added_at)).first()
        s.expunge_all()
    nxt = next((m for m in meetings if m.status == "scheduled" and m.at > now), None)
    actions = [{"id": a["id"], "meeting_id": m.id, "text": a["text"], "due_date": a.get("due_date")}
               for m in meetings if m.status != "cancelled" for a in m.action_items or [] if not a.get("done")]
    return {
        "has_topic": bool(prof and prof.title), "deadlines": deadlines,
        "next_meeting": ({"id": nxt.id, "at": nxt.at.astimezone(TZ).isoformat(), "title": nxt.title,
                          "agenda_drafted_at": (nxt.agenda or {}).get("drafted_at")} if nxt else None),
        "actions": actions, "reading_sessions_per_week": READING_SESSIONS, "reading_minutes": READING_MINUTES,
        "hero_paper_id": hero,
    }


def model_view(block: dict[str, Any]) -> dict[str, Any]:
    """What the planner model may see: numbers only, no titles or notes of the learner."""
    return {"open_deadlines": len(block["deadlines"]),
            "nearest_deadline_days": min((d["days_left"] for d in block["deadlines"]), default=None),
            "next_meeting": bool(block["next_meeting"]), "open_actions": len(block["actions"]),
            "reading_sessions_per_week": block["reading_sessions_per_week"], "added_by_code": True}


# ---- items --------------------------------------------------------------------------------------------------------------

def _days_text(n: int) -> tuple[str, str]:
    if n <= 0:
        return "hôm nay", "today"
    if n == 1:
        return "ngày mai", "tomorrow"
    return f"còn {n} ngày", f"in {n} days"


def _sessions_for(days_left: int) -> int:
    return 3 if days_left <= 3 else 2 if days_left <= 14 else 1 if days_left <= 21 else 0


class _Grid:
    """The week as it is being filled: items by day, study-day count, free-slot search."""

    def __init__(self, items: list[dict], ctx: PlanContext) -> None:
        self.ctx, self.items = ctx, items
        self.now = ctx.now.astimezone(TZ)
        self.today = self.now.date()
        self.days = [self.today + timedelta(days=i) for i in range(7)]

    def study_days(self) -> set[str]:
        return {i["date"] for i in self.items if i["kind"] != "break"}

    def on(self, day: date) -> list[dict]:
        return sorted((i for i in self.items if i["date"] == day.isoformat()), key=lambda i: i["start"])

    def has_research(self, day: date) -> bool:
        return any(i["kind"] == "research" for i in self.on(day))

    def slot(self, day: date, minutes: int, latest_end: int | None = None) -> int | None:
        """A start minute on `day`, near the learner's habit window, not overlapping, or None."""
        band = self.ctx.band
        if day.isoformat() not in self.study_days() and len(self.study_days()) >= MAX_STUDY_DAYS:
            return None
        want = pick_slot(self.ctx, day.weekday())
        lo = max(EARLIEST_MIN, band.start_min if want is None else want)
        if day == self.today:
            lo = max(lo, ((self.now.hour * 60 + self.now.minute + LEAD_MIN + 4) // 5) * 5)
        busy = [(to_min(i["start"]), to_min(i["start"]) + i["minutes"]) for i in self.on(day)]
        start = lo
        for _ in range(len(busy) + 1):
            clash = next(((a, b) for a, b in busy if start < b + GAP_MIN and start + minutes + GAP_MIN > a), None)
            if clash is None:
                break
            start = clash[1] + GAP_MIN
        else:
            return None
        if start < EARLIEST_MIN or start + minutes > band.bedtime_min or (latest_end is not None and start + minutes > latest_end):
            return None
        return (start + 4) // 5 * 5 if (start + 4) // 5 * 5 + minutes <= band.bedtime_min else start

    def add(self, day: date, start: int, minutes: int, code: str, title: tuple[str, str], reason: tuple[str, str],
            link: str, ref: dict[str, Any]) -> None:
        self.items.append({"date": day.isoformat(), "start": hhmm(start), "minutes": minutes, "kind": "research",
                           "course_id": None, "lesson_id": None, "reason_vi": clean(reason[0]), "reason_en": clean(reason[1]),
                           "code": code, "title_vi": title[0], "title_en": title[1], "deep_link": link, "ref": ref})


def _spread(days: list[date], n: int) -> list[date]:
    if not days or n <= 0:
        return []
    n = min(n, len(days))
    return [days[min(len(days) - 1, round(i * len(days) / n))] for i in range(n)]


def overlay(plan: dict[str, Any], ctx: PlanContext) -> dict[str, Any]:
    """`plan` (validated) plus research items and reminders. No research block in `ctx.profile` = unchanged."""
    block = ctx.profile.get("research")
    if not block:
        return plan
    band = ctx.band
    minutes = max(band.min_minutes, min(band.max_minutes, READING_MINUTES))
    items = [i for i in plan["items"] if i["kind"] != "research"]  # a model-written one is dropped: code owns these
    grid = _Grid(items, ctx)
    today = grid.today

    # 1. deadline preparation (nearest first); two deadlines within 3 days of each other share an earlier heads-up
    deadlines = sorted(block["deadlines"], key=lambda d: d["due_date"])
    close = {a["id"]: b for a, b in zip(deadlines, deadlines[1:], strict=False)
             if date.fromisoformat(b["due_date"]) - date.fromisoformat(a["due_date"]) <= CLOSE_DEADLINES
             and a["days_left"] <= 14}
    for d in deadlines:
        if d["days_left"] < 0:
            continue
        due = date.fromisoformat(d["due_date"])
        n = _sessions_for(d["days_left"])
        allowed = [x for x in grid.days if x < due or (x == due == today and d.get("due_time"))]
        vi_d, en_d = _days_text(d["days_left"])
        for k, day in enumerate(_spread(allowed, n)):
            latest = to_min(d["due_time"]) if (day == due and d.get("due_time")) else None
            start = grid.slot(day, minutes, latest) if not grid.has_research(day) else None
            if start is None:
                for alt in allowed:  # the chosen day had no room: any other allowed day
                    if not grid.has_research(alt) and (start := grid.slot(alt, minutes)) is not None:
                        day = alt
                        break
            if start is None:
                continue
            title = (f"Chuẩn bị: {d['title']}", f"Prepare: {d['title']}")
            other = close.get(d["id"])
            if k == 0 and other:
                reason = (f"Hai hạn gần nhau: {d['title']} và {other['title']}. Mentor chuẩn bị sớm cho cả hai.",
                          f"Two deadlines are close: {d['title']} and {other['title']}. Mentor starts early for both.")
            else:
                reason = (f"Hạn \"{d['title']}\" {vi_d}. Buổi này dành để chuẩn bị.",
                          f"\"{d['title']}\" is due {en_d}. This session is for preparing.")
            grid.add(day, start, minutes, "RESEARCH_DEADLINE", title, reason, "/nghien-cuu", {"kind": "deadline", "id": d["id"]})

    # 2. meeting action items with a date: one session before the date
    for a in block["actions"]:
        if not a.get("due_date"):
            continue
        due = date.fromisoformat(a["due_date"])
        if due < today:
            continue
        allowed = [x for x in grid.days if x < due] or ([today] if due == today else [])
        for day in [*(x for x in reversed(allowed) if not grid.has_research(x)), *(x for x in reversed(allowed) if grid.has_research(x))]:
            start = grid.slot(day, minutes)
            if start is not None:
                text = a["text"][:80]
                grid.add(day, start, minutes, "RESEARCH_ACTION", (f"Việc sau họp: {text}", f"After the meeting: {text}"),
                         (f"Việc từ buổi họp GVHD, hạn {due.day}/{due.month}: {text}.",
                          f"Task from the advisor meeting, due {due.day}/{due.month}: {text}."),
                         "/nghien-cuu", {"kind": "action", "id": a["id"], "meeting_id": a["meeting_id"]})
                break

    # 3. the default reading block: 3 sessions a week on days that have no research item yet
    if block.get("has_topic"):
        have = sum(1 for i in grid.items if i["kind"] == "research" and i.get("code") == "RESEARCH_READING")
        free = [x for x in grid.days if not grid.has_research(x)]
        link = f"/nghien-cuu/paper/{block['hero_paper_id']}" if block.get("hero_paper_id") else "/nghien-cuu"
        for day in _spread(free, block.get("reading_sessions_per_week", READING_SESSIONS) - have):
            start = grid.slot(day, minutes)
            if start is not None:
                grid.add(day, start, minutes, "RESEARCH_READING", ("Đọc paper", "Read a paper"),
                         ("Buổi đọc paper cho luận văn trong tuần.", "Weekly paper reading for your thesis."), link,
                         {"kind": "reading"})

    grid.items.sort(key=lambda i: (i["date"], i["start"]))
    out = {**plan, "items": grid.items}
    out["reminders"] = _reminders(plan.get("reminders") or [], block, ctx, block.get("_log") or {})
    return out


# ---- reminders ----------------------------------------------------------------------------------------------------------

def reminder_log(db: Database, user_id: str) -> dict[str, datetime]:
    """tag -> the first time a research reminder with that tag was ever scheduled (any status), so a replan neither
    repeats one that already fired nor pushes a pending one further away."""
    out: dict[str, datetime] = {}
    with db.session() as s:
        for r in s.scalars(select(Reminder).where(Reminder.user_id == user_id, Reminder.kind == "research")
                           .order_by(Reminder.created_at)):
            if "ref=" in r.deep_link:
                tag = r.deep_link.split("ref=", 1)[1]
                out.setdefault(tag, r.at)
    return out


def _fit(at: datetime, ctx: PlanContext) -> datetime | None:
    """Move `at` into the hours a reminder may fire (06:30 to bedtime, after quiet_until); None when it is in the past."""
    at = at.astimezone(TZ)
    minute = at.hour * 60 + at.minute
    if minute < EARLIEST_MIN:
        at = at.replace(hour=7, minute=30)
    elif minute >= ctx.band.bedtime_min:
        at = at.replace(hour=(ctx.band.bedtime_min - 30) // 60, minute=(ctx.band.bedtime_min - 30) % 60)
    if ctx.quiet_until and at < ctx.quiet_until.astimezone(TZ):
        return None  # quiet mode drops a reminder, it does not queue it for later
    return at if at > ctx.now else None


def _reminders(existing: list[dict], block: dict[str, Any], ctx: PlanContext, log: dict[str, datetime]) -> list[dict]:
    now = ctx.now.astimezone(TZ)
    out = [r for r in existing if r.get("kind") != "research"]
    per_day: dict[date, int] = {}
    for r in out:
        d = datetime.fromisoformat(r["at"]).astimezone(TZ).date()
        per_day[d] = per_day.get(d, 0) + 1
    cands: list[tuple[int, datetime, str, str, str]] = []  # (priority, at, tag, vi, en)

    def add(prio: int, tag: str, at: datetime | None, vi: str, en: str) -> None:
        first = log.get(tag)
        if first is not None:
            if first.astimezone(TZ) <= now:
                return  # fired already
            at = first.astimezone(TZ)  # keep the time it already has
        at = _fit(at, ctx) if at is not None else None
        if at is not None and at > now:
            cands.append((prio, at, tag, vi, en))

    for d in block["deadlines"]:
        if not d["confirmed"] or not d.get("due_time"):
            continue  # "Chưa xác nhận": no time-based reminder
        due = datetime.fromisoformat(f"{d['due_date']}T{d['due_time']}:00").replace(tzinfo=TZ)
        if due <= now:
            continue
        title, clock = d["title"], d["due_time"]
        stamp = f"{d['id']}-{due.strftime('%y%m%d%H%M')}"  # a moved deadline is a new reminder
        if now >= due - timedelta(hours=48):
            hours = max(1, int((due - now).total_seconds() // 3600))
            add(0, f"{stamp}-t48", now + timedelta(minutes=10),
                f"Hạn {title} còn khoảng {hours} giờ, lúc {clock}.", f"{title} is due in about {hours} hours, at {clock}.")
        else:
            add(1, f"{stamp}-t48", due - timedelta(hours=48),
                f"Còn 2 ngày đến hạn {title}, lúc {clock}.", f"{title} is due in 2 days, at {clock}.")
            add(2, f"{stamp}-t7", due - timedelta(days=7),
                f"Còn 7 ngày đến hạn {title}.", f"{title} is due in 7 days.")
    m = block.get("next_meeting")
    if m:
        at = datetime.fromisoformat(m["at"]).astimezone(TZ)
        mstamp = f"{m['id']}-{at.strftime('%y%m%d%H%M')}"
        if m.get("agenda_drafted_at"):
            drafted = datetime.fromisoformat(m["agenda_drafted_at"])
            if now - drafted < timedelta(hours=24):
                add(1, f"{mstamp}-agenda", now + timedelta(minutes=2),
                    "Mentor đã soạn khung agenda họp GVHD. Em điền kết quả mới và câu hỏi nhé.",
                    "Mentor drafted the advisor meeting agenda. Add your new results and questions.")
        day_at = max(at - timedelta(hours=2), at.replace(hour=7, minute=30))
        if day_at < at:
            add(2, f"{mstamp}-day", day_at, f"Hôm nay họp GVHD lúc {at.strftime('%H:%M')}. Xem lại agenda trước giờ họp.",
                f"Advisor meeting today at {at.strftime('%H:%M')}. Look over the agenda first.")
    for _prio, at, tag, vi, en in sorted(cands, key=lambda c: (c[0], c[1])):
        day = at.date()
        if per_day.get(day, 0) >= MAX_REMINDERS_PER_DAY:
            continue
        per_day[day] = per_day.get(day, 0) + 1
        out.append({"at": at.isoformat(), "kind": "research", "text_vi": clean(vi, 90), "text_en": clean(en, 90),
                    "deep_link": f"/nghien-cuu?ref={tag}"})
    out.sort(key=lambda r: r["at"])
    return out
