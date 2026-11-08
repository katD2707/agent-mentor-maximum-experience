"""Synthetic learners and hand-built plan contexts for the planner tests (offline, deterministic)."""

import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mentor_gateway.planner.bands import band_for
from mentor_gateway.planner.fsrs_items import due_items
from mentor_gateway.planner.goals import status_lines
from mentor_gateway.planner.profile import compute_profile
from mentor_gateway.planner.types import CourseInfo, GoalInfo, LessonInfo, PlanContext

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=TZ).astimezone(UTC)  # Monday 09:00 local


def local_dt(d: date, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=TZ).astimezone(UTC)


def ev(kind: str, ts: datetime, **data) -> dict:
    return {"kind": kind, "ts": ts, "data": data, "derived": False}


def study_session(start: datetime, minutes: int = 20, drop_after: int | None = None, course="c1", n_items=5,
                  tag="s") -> list[dict]:
    """session_start, a focus tick per minute, one quiz answer every 2 minutes (accuracy and speed drop after
    `drop_after` minutes), lesson_progress."""
    out = [ev("session_start", start, session=tag)]
    for m in range(minutes):
        out.append(ev("focus_tick", start + timedelta(minutes=m), session=tag, seconds=60))
    for i in range(minutes // 2):
        t = (i + 1) * 2
        late = drop_after is not None and t > drop_after
        out.append(ev("quiz_answer", start + timedelta(minutes=t, seconds=5), item=f"q{i % n_items}", course_id=course,
                      correct=(i % 3 == 0) if late else True, seconds=22.0 if late else 8.0))
    out.append(ev("lesson_progress", start + timedelta(minutes=minutes), course_id=course, lesson_id="l1", pct=50.0))
    out.append(ev("session_end", start + timedelta(minutes=minutes), session=tag, seconds=minutes * 60))
    return out


def simulate(now: datetime, habit: str, weekdays: set[int], weeks: int = 4, minutes: int = 20, jitter: int = 8,
             drop_after: int | None = None, seed: int = 1) -> list[dict]:
    """`weeks` weeks of events up to yesterday: a session at `habit` (+- jitter minutes) on each weekday in `weekdays`."""
    rnd = random.Random(seed)
    today = now.astimezone(TZ).date()
    events: list[dict] = []
    for back in range(weeks * 7, 0, -1):
        d = today - timedelta(days=back)
        if d.weekday() in weekdays:
            start = local_dt(d, habit) + timedelta(minutes=rnd.randint(-jitter, jitter))
            events += study_session(start, minutes, drop_after, tag=f"s{back}")
    return sorted(events, key=lambda e: e["ts"])


def make_courses(n_lessons: int = 8, minutes: int = 15, done: int = 0, partial: int | None = None,
                 cid: str = "c1", title: str = "Vật lí 11: Điện trường", subject: str = "Vật lí") -> CourseInfo:
    lessons = [LessonInfo(id=f"l{i + 1}", title=f"Bài {i + 1}", minutes=minutes, done=i < done,
                          started=(i == partial)) for i in range(n_lessons)]
    pct = 100 * done / n_lessons
    return CourseInfo(id=cid, title=title, subject=subject, lessons=lessons, progress_pct=pct,
                      last_lesson_id=f"l{partial + 1}" if partial is not None else None,
                      enrolled_at=NOW - timedelta(days=30), updated_at=NOW - timedelta(days=1))


def goal_for(course: CourseInfo, deadline: date | None = None, status: str = "on_track", kind="inferred",
             title: str | None = None) -> GoalInfo:
    g = GoalInfo(id=f"g-{course.id}", title=title or f"Học xong {course.title}", kind=kind, deadline=deadline,
                 course_ids=[course.id], progress_pct=course.progress_pct, remaining_minutes=course.remaining_minutes(),
                 status=status, created_at=NOW - timedelta(days=30))
    g.line_vi, g.line_en = status_lines(g, [course])
    return g


def make_ctx(events: list[dict], age_band: str = "g10_12", courses: list[CourseInfo] | None = None,
             goals: list[GoalInfo] | None = None, now: datetime = NOW, **kw) -> PlanContext:
    band = band_for(age_band)
    courses = courses if courses is not None else [make_courses()]
    due = due_items(events, now)
    for d in due:
        d["lesson_id"] = "l1"
        if d.get("course_id") not in {c.id for c in courses}:
            d["course_id"] = None
    profile = compute_profile(events, now, band, due)
    profile["missed_recent"] = kw.get("missed_recent", 0)
    return PlanContext(now=now, band=band, courses=courses, goals=goals if goals is not None else [goal_for(courses[0])],
                       profile=profile, due_items=due, **kw)
