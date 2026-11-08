"""Rule-based planner: used when the LLM is off, fails, or its plan breaks a hard constraint (3.7).

Ported from agent-mentor `Recommender.kt` (explainable rules, reason codes, supportive wording). Priority per session:
UNFINISHED_LESSON, then DUE_REVIEW (FSRS), then BEHIND_GOAL (next lesson of a goal that is slow), then NEXT_LESSON.
Pure function of the PlanContext: same input, same plan.
"""

from datetime import datetime, timedelta

from mentor_gateway.planner.bands import EARLIEST_MIN, TZ, hhmm, to_min
from mentor_gateway.planner.text import clean
from mentor_gateway.planner.types import WEEKDAYS_EN, WEEKDAYS_VI, CourseInfo, LessonInfo, PlanContext

LEAD_MIN = 15  # a session today must start at least this long from now
MAX_STUDY_DAYS = 6


def deep_link(course_id: str | None, lesson_id: str | None = None, kind: str = "lesson") -> str:
    if kind == "practice" or not course_id:
        return "/luyen-tap"
    return f"/khoa-hoc/{course_id}" + (f"?lesson={lesson_id}" if lesson_id else "")


def sessions_wanted(ctx: PlanContext) -> int:
    p = ctx.profile
    n = round(p.get("cadence_days_per_week") or ctx.band.sessions_per_week)
    if any(g.status in ("behind", "slightly_behind") for g in ctx.goals):
        n += 1
    if ctx.missed_recent >= 3:  # motivation: smaller plan, not more nagging
        n -= 1
    return max(2, min(MAX_STUDY_DAYS, n))


def weekly_cap(ctx: PlanContext) -> int:
    """Minutes per week the plan may hold: at most 1.5x what the student really did, never below 3 default sessions."""
    actual_week = float(ctx.profile.get("actual_minutes_per_day_14d") or 0) * 7
    return int(max(1.5 * actual_week, 3 * ctx.band.minutes))


def pick_slot(ctx: PlanContext, weekday: int) -> int:
    """Start minute for a weekday: the heaviest habit window of that weekday, else the overall one, else the age default.
    Slots the student ignored 3 times are skipped."""
    p, band = ctx.profile, ctx.band
    avoid = set(p.get("avoid_slots") or [])
    cells = [w for w in p.get("windows") or [] if w["start"] not in avoid]
    top = max((w["weight"] for w in cells), default=0)
    mine = [w for w in cells if w["weekday"] == weekday and w["weight"] >= 0.3 * top]
    if mine:
        return to_min(max(mine, key=lambda w: w["weight"])["start"])
    overall = [o for o in p.get("overall_slots") or [] if o["start"] not in avoid]
    if overall:
        return to_min(overall[0]["start"])
    start = band.start_min
    return start + 30 if hhmm(start) in avoid else start


def _choose_days(ctx: PlanContext, days: list, n: int) -> list:
    p = ctx.profile
    skip = set(p.get("skip_weekdays") or [])
    cand = [d for d in days if d.weekday() not in skip] or days
    n = min(n, len(cand))
    if p.get("cold_start") or not p.get("weekday_activity"):
        idx = sorted({round(i * (len(cand) - 1) / max(1, n - 1)) for i in range(n)}) if n > 1 else [0]
        return [cand[i] for i in idx]
    rate = {int(k): v for k, v in p["weekday_activity"].items()}
    ranked = sorted(cand, key=lambda d: (-rate.get(d.weekday(), 0), d))
    return sorted(ranked[:n])


class _Tasks:
    """Hands out the next thing to do, consuming lessons so a later session gets the following one."""

    def __init__(self, ctx: PlanContext) -> None:
        self.ctx = ctx
        self.used: set[tuple[str, str]] = set()
        self.reviews_left = {}
        for d in ctx.due_items:
            self.reviews_left[d.get("course_id")] = self.reviews_left.get(d.get("course_id"), 0) + 1
        self.rr = 0
        self.last_course: str | None = None

    def _unused(self, c: CourseInfo, started_only: bool) -> LessonInfo | None:
        for ls in c.lessons:
            if ls.done or (c.id, ls.id) in self.used:
                continue
            if started_only and not ls.started:
                continue
            return ls
        return None

    def _order(self) -> list[CourseInfo]:
        cs = list(self.ctx.courses)
        dl = {}
        for g in self.ctx.goals:
            for cid in g.course_ids:
                if g.deadline:
                    dl[cid] = min(dl.get(cid, g.deadline), g.deadline)
        cs.sort(key=lambda c: (c.id == self.last_course, str(dl.get(c.id) or "9999")))
        return cs

    def next(self, allow_review: bool) -> dict | None:
        ctx = self.ctx
        order = self._order()
        for c in order:  # 1. unfinished lesson
            ls = self._unused(c, True)
            if ls:
                return self._lesson(c, ls, "UNFINISHED_LESSON")
        if allow_review and sum(self.reviews_left.values()) > 0:  # 2. due review
            cid = max(self.reviews_left, key=lambda k: self.reviews_left[k])
            n = self.reviews_left.pop(cid)
            c = ctx.course(cid)
            return {"kind": "review" if c else "practice", "course": c, "lesson": None, "n": n, "code": "DUE_REVIEW"}
        behind = [g for g in ctx.goals if g.status in ("behind", "slightly_behind")]
        for g in behind:  # 3. behind goal
            for cid in g.course_ids:
                c = ctx.course(cid)
                ls = self._unused(c, False) if c else None
                if ls:
                    return self._lesson(c, ls, "BEHIND_GOAL", goal=g.title)
        for c in order:  # 4. next lesson
            ls = self._unused(c, False)
            if ls:
                return self._lesson(c, ls, "NEXT_LESSON")
        if sum(self.reviews_left.values()) > 0:
            return self.next(True)
        return None

    def _lesson(self, c: CourseInfo, ls: LessonInfo, code: str, goal: str = "") -> dict:
        self.used.add((c.id, ls.id))
        self.last_course = c.id
        return {"kind": "lesson", "course": c, "lesson": ls, "code": code, "goal": goal}


def _reason(task: dict, minutes: int) -> tuple[str, str]:
    _c, ls, code = task["course"], task["lesson"], task["code"]
    if code == "UNFINISHED_LESSON":
        return f"Em đang dở {ls.title}. Học nốt bài này nhé.", f"You are partway through {ls.title}. Finish it today."
    if code == "DUE_REVIEW":
        n = task["n"]
        return (f"Có {n} câu đến hạn ôn. Làm lại lúc này sẽ nhớ lâu hơn.",
                f"{n} questions are due for review. Doing them now helps you remember longer.")
    if code == "BEHIND_GOAL":
        return (f"Mục tiêu \"{task['goal']}\" đang hơi chậm, buổi này giúp bắt kịp.",
                f"Your goal \"{task['goal']}\" is a bit slow, this session helps catch up.")
    return f"Tiếp theo là {ls.title}, khoảng {minutes} phút.", f"Next up is {ls.title}, about {minutes} minutes."


def plan_fallback(ctx: PlanContext) -> dict:
    band, profile = ctx.band, ctx.profile
    now = ctx.now.astimezone(TZ)
    today = now.date()
    days = [today + timedelta(days=i) for i in range(7)]
    studied_today = bool(profile.get("today_starts"))
    sm = int(profile.get("session_minutes") or band.minutes)
    if ctx.missed_recent >= 3:
        sm = max(band.min_minutes, round(sm * 0.75 / 5) * 5)

    def viable(d) -> int | None:  # start minute, or None when no slot fits that day
        start = pick_slot(ctx, d.weekday())
        if d == today:
            if studied_today:
                return None
            start = max(start, ((now.hour * 60 + now.minute + LEAD_MIN + 4) // 5) * 5)
        start = max(EARLIEST_MIN, start)
        return start if start < band.bedtime_min else None

    eligible = [d for d in days if viable(d) is not None]
    chosen = _choose_days(ctx, eligible, sessions_wanted(ctx))
    tasks = _Tasks(ctx)
    items, total, cap = [], 0, weekly_cap(ctx)
    reviews_used, review_cap = 0, max(1, (len(chosen) + 1) // 2)
    for d in chosen:
        task = tasks.next(allow_review=reviews_used < review_cap)
        if task is None:
            break
        c, ls = task["course"], task["lesson"]
        if task["kind"] == "lesson":
            minutes = max(band.min_minutes, min(band.max_minutes, min(ls.minutes, sm)))
        else:
            minutes = max(band.min_minutes, min(sm, 5 + int(task["n"])))
        if total + minutes > cap and items:
            break
        total += minutes
        reviews_used += task["kind"] != "lesson"
        rv, re_ = _reason(task, minutes)
        items.append({"date": d.isoformat(), "start": hhmm(viable(d)), "minutes": minutes, "kind": task["kind"],
                      "course_id": c.id if c else None, "lesson_id": ls.id if ls else None,
                      "reason_vi": clean(rv), "reason_en": clean(re_), "code": task["code"]})
    reminders = _reminders(ctx, items)
    goals = [{"goal_id": g.id, "status": g.status, "line_vi": clean(g.line_vi, 160), "line_en": clean(g.line_en, 160)}
             for g in ctx.goals]
    n = len(items)
    return {"items": items, "reminders": reminders, "goals": goals,
            "week_note_vi": clean(f"Mentor xếp {n} buổi trong 7 ngày tới, vào khung giờ em hay học.") if n else "",
            "week_note_en": clean(f"Mentor planned {n} sessions for the next 7 days, in the slots you usually study.") if n else ""}


def _reminders(ctx: PlanContext, items: list[dict]) -> list[dict]:
    p = ctx.profile
    self_start = set(p.get("self_start_slots") or [])
    out = []
    for it in items:
        slot = hhmm(to_min(it["start"]) // 30 * 30)
        at = datetime.fromisoformat(f"{it['date']}T{it['start']}:00").replace(tzinfo=TZ)
        if slot in self_start or at <= ctx.now:
            continue  # the student starts here on their own, or it is already past: a reminder adds nothing
        c, ls = ctx.course(it["course_id"]), None
        if c:
            ls = c.lesson(it["lesson_id"])
        what_vi = ls.title if ls else (c.title if c else "ôn tập")
        what_en = ls.title if ls else (c.title if c else "practice")
        out.append({"at": at.isoformat(), "kind": "study",
                    "text_vi": clean(f"{it['minutes']} phút {what_vi} nhé?", 90),
                    "text_en": clean(f"{it['minutes']} minutes of {what_en}?", 90),
                    "deep_link": deep_link(it["course_id"], it["lesson_id"], it["kind"])})
    d = p.get("days_since_study")
    if d is not None and d >= 2 and not (ctx.last_nudge_at and p.get("last_study_date")
                                         and ctx.last_nudge_at.astimezone(TZ).date().isoformat() >= p["last_study_date"]):
        soon = [r for r in out if datetime.fromisoformat(r["at"]) < ctx.now + timedelta(hours=24)]
        if not soon and items:
            first = items[0]
            at = datetime.fromisoformat(f"{first['date']}T{first['start']}:00").replace(tzinfo=TZ)
            if at > ctx.now:
                out.append({"at": at.isoformat(), "kind": "nudge",
                            "text_vi": clean("Mấy hôm nay em chưa học. Mở bài lên 10 phút thôi cũng được."),
                            "text_en": clean("It has been a couple of days. Even 10 minutes helps."),
                            "deep_link": deep_link(first["course_id"], first["lesson_id"], first["kind"])})
    out.sort(key=lambda r: r["at"])
    return out


def explain_moves(old: list[dict], new: list[dict], trigger: str) -> list[dict]:
    """One sentence per item that moved to another day (same course, lesson and kind)."""
    prev = {(i.get("course_id"), i.get("lesson_id"), i.get("kind")): i for i in old if i.get("kind") != "research"}
    moves = []
    for it in new:
        if it.get("kind") == "research":
            continue
        o = prev.get((it.get("course_id"), it.get("lesson_id"), it.get("kind")))
        if not o or o["date"] == it["date"]:
            continue
        wd = datetime.fromisoformat(it["date"]).weekday()
        if trigger == "missed_session":
            vi, en = f"Em bỏ buổi vừa rồi, nên Mentor dời sang {WEEKDAYS_VI[wd]}.", \
                f"You missed the last session, so Mentor moved it to {WEEKDAYS_EN[wd]}."
        else:
            vi, en = f"Mentor dời sang {WEEKDAYS_VI[wd]} cho hợp lịch em.", f"Mentor moved it to {WEEKDAYS_EN[wd]} to fit your week."
        moves.append({"date": it["date"], "course_id": it.get("course_id"), "lesson_id": it.get("lesson_id"),
                      "reason_vi": clean(vi), "reason_en": clean(en)})
    return moves
