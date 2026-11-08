"""Hard-constraint layer (3.7, code, runs after the LLM). `validate` returns the repaired plan plus what it had to fix, or
`ok=False` when the plan cannot be repaired (the caller then uses the rule-based fallback).

Rules:
- shape: items {date, start, minutes, kind, course_id, lesson_id?, reason_vi, reason_en}; reminders {at, kind, text_vi,
  text_en, deep_link}; goal statuses; dates inside the 7-day window; known course/lesson ids.
- session length inside the age band's bounds (clamped); no session before 06:30 or at/after bedtime; no overlaps; at most
  6 study days; weekly minutes not far above what the student really does (trimmed from the end).
- reminders: at most 2 a day, only one `nudge` and only after 2 idle days, none in the past, none before `quiet_until`,
  none before 06:30 or from bedtime, none in a slot where the student already started studying today, none in a slot
  they ignored three times in a row.
"""

from datetime import datetime, timedelta

from mentor_gateway.planner.bands import EARLIEST_MIN, TZ, hhmm, to_min
from mentor_gateway.planner.fallback import deep_link, weekly_cap
from mentor_gateway.planner.text import clean
from mentor_gateway.planner.types import KINDS, REMINDER_KINDS, STATUSES, PlanContext

MAX_REMINDERS_PER_DAY = 2
MAX_STUDY_DAYS = 6
BREAK_BOUNDS = (1, 15)
MAX_ITEMS = 28


class Invalid(Exception):
    pass


def _slot(minute: int) -> str:
    return hhmm(minute // 30 * 30)


def validate(plan: dict, ctx: PlanContext) -> tuple[bool, dict, list[str]]:
    """-> (ok, repaired plan, notes). Notes list every fix (and the reason when ok is False)."""
    notes: list[str] = []
    try:
        fixed = _validate(plan, ctx, notes)
    except Invalid as e:
        return False, {}, [*notes, f"unfixable: {e}"]
    return True, fixed, notes


def _validate(plan: dict, ctx: PlanContext, notes: list[str]) -> dict:
    if not isinstance(plan, dict) or not isinstance(plan.get("items"), list):
        raise Invalid("plan.items missing")
    band, now = ctx.band, ctx.now.astimezone(TZ)
    today = now.date()
    window = {(today + timedelta(days=i)).isoformat() for i in range(7)}
    items = []
    for raw in plan["items"][:MAX_ITEMS]:
        try:
            kind = raw["kind"]
            if kind not in KINDS:
                raise ValueError(kind)
            d, start, minutes = str(raw["date"]), to_min(str(raw["start"])), int(raw["minutes"])
        except (KeyError, ValueError, TypeError, AttributeError):
            notes.append("dropped an item with bad fields")
            continue
        if d not in window:
            notes.append(f"dropped item outside the 7 day window ({d})")
            continue
        cid, lid = raw.get("course_id"), raw.get("lesson_id")
        course = ctx.course(cid)
        if kind in ("lesson", "review") and course is None:
            notes.append(f"dropped {kind} with unknown course {cid}")
            continue
        if kind == "practice" and cid and course is None:
            cid = None
        if lid and (course is None or course.lesson(lid) is None):
            lid = None
        if kind == "lesson" and not lid:
            notes.append("dropped lesson item without a valid lesson_id")
            continue
        lo, hi = BREAK_BOUNDS if kind == "break" else (band.min_minutes, band.max_minutes)
        if not lo <= minutes <= hi:
            minutes = max(lo, min(hi, minutes))
            notes.append(f"clamped minutes of {d} {raw['start']}")
        if kind != "break" and (start < EARLIEST_MIN or start >= band.bedtime_min):
            notes.append(f"dropped session at {raw['start']} outside the age-band hours")
            continue
        if d == today.isoformat() and start < now.hour * 60 + now.minute:
            notes.append("dropped a session that already started")
            continue
        items.append({"date": d, "start": hhmm(start), "minutes": minutes, "kind": kind, "course_id": cid,
                      "lesson_id": lid, "reason_vi": clean(raw.get("reason_vi")), "reason_en": clean(raw.get("reason_en")),
                      **({"code": raw["code"]} if raw.get("code") else {})})
    if not items and plan["items"]:
        raise Invalid("no usable item left")
    items.sort(key=lambda i: (i["date"], i["start"]))
    kept: list[dict] = []
    for it in items:  # no overlaps
        prev = kept[-1] if kept else None
        if prev and prev["date"] == it["date"] and to_min(it["start"]) < to_min(prev["start"]) + prev["minutes"]:
            notes.append(f"dropped overlapping item {it['date']} {it['start']}")
            continue
        kept.append(it)
    items = kept
    if len({i["date"] for i in items if i["kind"] != "break"}) > MAX_STUDY_DAYS:
        raise Invalid("7 study days in a row")
    items = _trim_pace(items, ctx, notes)

    reminders = _reminders(plan.get("reminders") or [], items, ctx, notes)
    goals = []
    known = {g.id: g for g in ctx.goals}
    for g in plan.get("goals") or []:
        gid = g.get("goal_id") if isinstance(g, dict) else None
        if gid in known and g.get("status") in STATUSES:
            goals.append({"goal_id": gid, "status": g["status"], "line_vi": clean(g.get("line_vi"), 160),
                          "line_en": clean(g.get("line_en"), 160)})
    have = {g["goal_id"] for g in goals}
    for gid, g in known.items():  # every goal gets a status; code's own when the model skipped it
        if gid not in have:
            goals.append({"goal_id": gid, "status": g.status, "line_vi": clean(g.line_vi, 160),
                          "line_en": clean(g.line_en, 160)})
    return {"items": items, "reminders": reminders, "goals": goals,
            "week_note_vi": clean(plan.get("week_note_vi"), 220), "week_note_en": clean(plan.get("week_note_en"), 220)}


def _trim_pace(items: list[dict], ctx: PlanContext, notes: list[str]) -> list[dict]:
    cap = weekly_cap(ctx)
    total = sum(i["minutes"] for i in items if i["kind"] != "break")
    while total > cap and len([i for i in items if i["kind"] != "break"]) > 1:
        last = max((i for i in items if i["kind"] != "break"), key=lambda i: (i["date"], i["start"]))
        items.remove(last)
        total -= last["minutes"]
        notes.append(f"trimmed {last['date']} to keep the week within {cap} minutes")
    return items


def _reminders(raw: list, items: list[dict], ctx: PlanContext, notes: list[str]) -> list[dict]:
    band, now, p = ctx.band, ctx.now, ctx.profile
    today = now.astimezone(TZ).date()
    started_today = [to_min(s) for s in p.get("today_starts") or []]
    avoid = set(p.get("avoid_slots") or [])
    out: list[dict] = []
    nudges = 0
    for r in sorted((r for r in raw if isinstance(r, dict)), key=lambda r: str(r.get("at"))):
        try:
            at = datetime.fromisoformat(str(r["at"]))
            at = at.replace(tzinfo=TZ) if at.tzinfo is None else at.astimezone(TZ)
            kind = r["kind"]
            if kind not in REMINDER_KINDS or not str(r.get("text_vi") or "").strip():
                raise ValueError(kind)
        except (KeyError, ValueError, TypeError):
            notes.append("dropped a malformed reminder")
            continue
        minute = at.hour * 60 + at.minute
        why = None
        if at <= now:
            why = "in the past"
        elif ctx.quiet_until and at < ctx.quiet_until:
            why = "during quiet mode"
        elif minute < EARLIEST_MIN or minute >= band.bedtime_min:
            why = "outside the age-band hours"
        elif at.date() == today and any(abs(minute - s) < 30 for s in started_today):
            why = "student already studied in that slot"
        elif _slot(minute) in avoid:
            why = "slot ignored 3 times"
        elif kind == "nudge" and ((p.get("days_since_study") or 0) < 2 or nudges >= 1
                                  or (ctx.last_nudge_at and p.get("last_study_date")
                                      and ctx.last_nudge_at.astimezone(TZ).date().isoformat() >= p["last_study_date"])):
            why = "nudge not allowed"
        elif sum(1 for o in out if datetime.fromisoformat(o["at"]).astimezone(TZ).date() == at.date()) >= MAX_REMINDERS_PER_DAY:
            why = "more than 2 reminders that day"
        if why:
            notes.append(f"dropped reminder at {at.isoformat()}: {why}")
            continue
        nudges += kind == "nudge"
        link = str(r.get("deep_link") or "")
        if not link.startswith("/"):
            link = deep_link(None) if kind == "nudge" else "/khoa-hoc"
        out.append({"at": at.isoformat(), "kind": kind, "text_vi": clean(r.get("text_vi"), 90),
                    "text_en": clean(r.get("text_en") or r.get("text_vi"), 90), "deep_link": link[:300]})
    return out
