"""Milestones: the deadlines and thesis milestones of CONTRACTS 15.8, kept in `study_goals.milestones` of the learner's one
research goal (section 12, `source: "research"`). Pure helpers over the table, shared by the research service and the planner.

The goal row is the storage. It is *visible* (appears in GET /goals and Tiến độ) only while at least one `thesis: true`
milestone exists: with none left the row stays hidden (`dismissed`) so plain external deadlines keep their home, and it is
deleted with the last milestone. The API id is `res-thesis`; the row id carries the user id so two learners never collide.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from mentor_gateway.db import Database
from mentor_gateway.planner.bands import TZ
from mentor_gateway.planner.tables import PlanRecord, StudyGoal
from mentor_gateway.planner.text import clean

GOAL_ID = "res-thesis"


def row_id(user_id: str) -> str:
    return f"{GOAL_ID}:{user_id}"[:64]


def load(db: Database, user_id: str) -> tuple[StudyGoal | None, list[dict[str, Any]]]:
    with db.session() as s:
        row = s.get(StudyGoal, row_id(user_id))
        if row is None:
            return None, []
        s.expunge(row)
        return row, [dict(m) for m in (row.milestones or [])]


def save(db: Database, user_id: str, items: list[dict[str, Any]], title: str, now: datetime) -> None:
    """Write the list back; creates, hides or deletes the goal row as described in the module docstring."""
    rid = row_id(user_id)
    with db.session() as s:
        row = s.get(StudyGoal, rid)
        if not items:
            if row is not None:
                s.delete(row)
            return
        thesis = [m for m in items if m.get("thesis")]
        if row is None:
            row = StudyGoal(id=rid, user_id=user_id, kind="student", title=title[:200] or "Luận văn", deadline=None,
                            course_ids=[], dismissed=True, created_at=now, updated_at=now, source="research", milestones=[])
            s.add(row)
        row.title = (title or row.title or "Luận văn")[:200]
        row.milestones = sorted(items, key=lambda m: (m["due_date"], m.get("due_time") or "99:99", m["id"]))
        row.deadline = max((date.fromisoformat(m["due_date"]) for m in thesis), default=None)
        row.dismissed = not thesis
        row.updated_at = now


def next_id(items: list[dict[str, Any]]) -> str:
    n = max((int(m["id"].split("-")[1]) for m in items if m["id"].startswith("ms-") and m["id"][3:].isdigit()), default=0)
    return f"ms-{n + 1}"


def due_at(m: dict[str, Any]) -> datetime | None:
    """The instant of a confirmed milestone with a time (Vietnam time), else None."""
    if not m.get("confirmed") or not m.get("due_time"):
        return None
    return datetime.fromisoformat(f"{m['due_date']}T{m['due_time']}:00").replace(tzinfo=TZ)


def planned_counts(db: Database, user_id: str) -> dict[str, int]:
    """milestone id -> research plan items the planner placed for it (items carry `ref: {kind, id}`)."""
    with db.session() as s:
        rec = s.get(PlanRecord, user_id)
        items = list((rec.plan or {}).get("items", [])) if rec else []
    out: dict[str, int] = {}
    for it in items:
        ref = it.get("ref") or {}
        if it.get("kind") == "research" and ref.get("kind") == "deadline":
            out[ref["id"]] = out.get(ref["id"], 0) + 1
    return out


def view(m: dict[str, Any], today: date, planned: dict[str, int] | None = None) -> dict[str, Any]:
    """A stored milestone as the `Milestone` wire shape."""
    return {"id": m["id"], "title": m["title"], "due_date": m["due_date"], "due_time": m.get("due_time"),
            "original_text": m.get("original_text"), "confirmed": bool(m.get("confirmed")), "kind": m.get("kind") or "other",
            "thesis": bool(m.get("thesis")), "done": bool(m.get("done")),
            "days_left": (date.fromisoformat(m["due_date"]) - today).days,
            "planned_sessions": (planned or {}).get(m["id"], 0), "created_at": m["created_at"]}


def days_phrase(n: int, lang: str) -> str:
    if lang == "en":
        return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"
    return "hôm nay" if n == 0 else "ngày mai" if n == 1 else f"còn {n} ngày"


def goal_numbers(milestones: list[dict[str, Any]], today: date, days_since_study: int | None, created: datetime,
                 now: datetime) -> tuple[float, str, str, str]:
    """-> (progress_pct, status, line_vi, line_en) of the research goal, by code, from the milestone dates.

    progress = done thesis milestones / all thesis milestones. status: an open milestone past its date = behind; the next one
    within 3 days and no study for 2 days or more = slightly_behind; a goal made in the last 3 days = new; else on_track."""
    thesis = [m for m in milestones if m.get("thesis")]
    done = [m for m in thesis if m.get("done")]
    openm = sorted((m for m in thesis if not m.get("done")), key=lambda m: m["due_date"])
    pct = round(100.0 * len(done) / len(thesis), 1) if thesis else 0.0
    if not openm:
        return pct, "on_track", "Xong các mốc luận văn.", "All thesis milestones done."
    nxt = openm[0]
    left = (date.fromisoformat(nxt["due_date"]) - today).days
    title = nxt["title"]
    if left < 0:
        status = "behind"
        vi, en = f"Mốc \"{title}\" đã quá hạn {-left} ngày.", f"\"{title}\" is {-left} days overdue."
    elif left <= 3 and (days_since_study is None or days_since_study >= 2):
        status = "slightly_behind"
        vi, en = f"Mốc \"{title}\" {days_phrase(left, 'vi')}. Mentor xếp thêm buổi ngắn.", \
            f"\"{title}\" is due {days_phrase(left, 'en')}. Mentor added a short session."
    elif (now - created).days < 3:
        status = "new"
        vi, en = f"Mốc gần nhất: {title}, {days_phrase(left, 'vi')}.", f"Next milestone: {title}, {days_phrase(left, 'en')}."
    else:
        status = "on_track"
        vi, en = f"Đúng nhịp. Mốc gần nhất: {title}, {days_phrase(left, 'vi')}.", \
            f"On track. Next milestone: {title}, {days_phrase(left, 'en')}."
    return pct, status, clean(vi, 160), clean(en, 160)


def open_deadlines(db: Database, user_id: str, today: date, horizon_days: int = 30) -> list[dict[str, Any]]:
    """Open milestones up to `horizon_days` ahead (and overdue ones of the last 7 days), by date."""
    _, items = load(db, user_id)
    lo, hi = today - timedelta(days=7), today + timedelta(days=horizon_days)
    return sorted((m for m in items if not m.get("done") and lo <= date.fromisoformat(m["due_date"]) <= hi),
                  key=lambda m: (m["due_date"], m.get("due_time") or "99:99"))


def all_goal_ids(db: Database, user_id: str) -> list[str]:
    with db.session() as s:
        return list(s.scalars(select(StudyGoal.id).where(StudyGoal.user_id == user_id, StudyGoal.source == "research")))
