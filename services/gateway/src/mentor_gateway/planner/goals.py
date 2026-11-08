"""Goals (REQUIREMENTS-PLAN 3.6): inferred from enrollments (one per course, auto-maintained) plus the student's own
(a title and an optional deadline). Progress, required pace and the one-line status are computed here, by code."""

import secrets
from datetime import date, datetime

from sqlalchemy import select

from mentor_gateway.db import Database
from mentor_gateway.planner.bands import TZ, Band
from mentor_gateway.planner.tables import StudyGoal
from mentor_gateway.planner.text import tokens
from mentor_gateway.planner.types import CourseInfo, GoalInfo

NEW_DAYS = 3  # a goal this young is "new"


def new_goal_id() -> str:
    return "g-" + secrets.token_hex(6)


def sync_inferred(db: Database, user_id: str, courses: list[CourseInfo], language: str, now: datetime) -> None:
    """One inferred goal per enrolled course; removed with the enrollment; a goal the student deleted stays dismissed."""
    wanted = {f"inf-{c.id}"[:64]: c for c in courses}
    with db.session() as s:
        rows = {r.id: r for r in s.scalars(select(StudyGoal).where(StudyGoal.user_id == user_id,
                                                                   StudyGoal.kind == "inferred"))}
        for gid, row in rows.items():
            if gid not in wanted:
                s.delete(row)
        for gid, c in wanted.items():
            if gid in rows:
                continue
            title = f"Học xong {c.title}" if language != "en" else f"Finish {c.title}"
            s.add(StudyGoal(id=gid, user_id=user_id, kind="inferred", title=title[:200], deadline=None,
                            course_ids=[c.id], dismissed=False, created_at=c.enrolled_at or now, updated_at=now))


def link_courses(row: StudyGoal, courses: list[CourseInfo]) -> list[str]:
    """Explicit links win; otherwise a student goal links the courses that share a word (diacritics ignored) with it."""
    known = {c.id for c in courses}
    if row.course_ids:
        return [cid for cid in row.course_ids if cid in known]
    if row.kind == "inferred":
        return []
    want = tokens(row.title)
    return [c.id for c in courses if want & tokens(f"{c.title} {c.subject}")]


def _status(g: GoalInfo, courses: list[CourseInfo], profile: dict, band: Band, today: date, now: datetime) -> str:
    linked = [c for c in courses if c.id in g.course_ids]
    age_days = (now - g.created_at).days if g.created_at else 99
    if not linked or (age_days < NEW_DAYS and not profile.get("sessions_seen")):
        return "new"
    if g.remaining_minutes <= 0:
        return "on_track"
    if g.deadline is not None:
        days_left = max(1, (g.deadline - today).days)
        required = g.remaining_minutes / days_left
        g.required_min_per_day = round(required, 1)
        actual = float(profile.get("actual_minutes_per_day_14d") or 0)
        if actual <= 0 and profile.get("sessions_seen"):  # events without durations (derived): estimate from cadence
            actual = band.minutes * (profile.get("cadence_days_per_week") or band.sessions_per_week) / 7
        if profile.get("cold_start") and age_days < 7:
            return "new"
        ratio = actual / required if required else 1.0
        return "on_track" if ratio >= 0.9 else "slightly_behind" if ratio >= 0.6 else "behind"
    last = max((c.updated_at for c in linked if c.updated_at), default=None)
    if age_days < NEW_DAYS:
        return "new"
    idle = (now - last).days if last else 99
    return "on_track" if idle <= 7 else "slightly_behind" if idle <= 14 else "behind"


def _lessons_left(g: GoalInfo, courses: list[CourseInfo]) -> int:
    return sum(1 for c in courses if c.id in g.course_ids for ls in c.lessons if not ls.done)


def status_lines(g: GoalInfo, courses: list[CourseInfo]) -> tuple[str, str]:
    n = _lessons_left(g, courses)
    left_vi = f"Còn {n} bài." if n else "Xong phần bài học."
    left_en = f"{n} lessons left." if n else "All lessons done."
    if g.status == "new":
        return "Mới đặt. Mentor sẽ xếp buổi học vào lịch tuần.", "Just set. Mentor will fit sessions into your week."
    if g.status == "on_track":
        return f"Đúng nhịp. {left_vi}", f"On track. {left_en}"
    if g.status == "slightly_behind":
        return f"Hơi chậm. {left_vi} Mentor thêm một buổi ngắn trong tuần.", \
            f"A bit behind. {left_en} Mentor added a short session this week."
    return f"Cần bắt kịp. {left_vi} Mentor chia nhỏ thành các buổi ngắn.", \
        f"Needs catching up. {left_en} Mentor split it into short sessions."


def research_info(r: StudyGoal, profile: dict, today: date, now: datetime) -> GoalInfo:
    """The research goal (Nghiên cứu, CONTRACTS 15.8): no courses; progress, deadline and status come from its milestones."""
    from mentor_gateway.research import milestones as ms

    pct, status, vi, en = ms.goal_numbers(list(r.milestones or []), today, profile.get("days_since_study"), r.created_at, now)
    g = GoalInfo(id=ms.GOAL_ID, title=r.title, kind="student", deadline=r.deadline, course_ids=[], progress_pct=pct,
                 remaining_minutes=0, created_at=r.created_at)
    g.status, g.line_vi, g.line_en = status, vi, en
    return g


def build_infos(rows: list[StudyGoal], courses: list[CourseInfo], profile: dict, band: Band, now: datetime) -> list[GoalInfo]:
    today = now.astimezone(TZ).date()
    out = []
    for r in rows:
        if r.dismissed:
            continue
        if getattr(r, "source", "learning") == "research":
            out.append(research_info(r, profile, today, now))
            continue
        ids = link_courses(r, courses)
        linked = [c for c in courses if c.id in ids]
        g = GoalInfo(id=r.id, title=r.title, kind=r.kind, deadline=r.deadline, course_ids=ids,
                     progress_pct=round(sum(c.progress_pct for c in linked) / len(linked), 1) if linked else 0.0,
                     remaining_minutes=sum(c.remaining_minutes() for c in linked), created_at=r.created_at)
        g.status = _status(g, courses, profile, band, today, now)
        g.line_vi, g.line_en = status_lines(g, courses)
        out.append(g)
    out.sort(key=lambda g: (g.deadline is None, g.deadline or date.max, g.created_at or now))
    return out
