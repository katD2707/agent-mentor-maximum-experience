"""The hub line of Nghiên cứu (CONTRACTS 15.8): `GET /today` `hub.research` and `ResearchOverview.status_line`. Built by code,
no model. Present only for `uni` users (the caller checks the band)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from mentor_gateway.db import Database
from mentor_gateway.planner.bands import TZ
from mentor_gateway.research import milestones
from mentor_gateway.research.tables import ReadingEntryRow, ResearchProfileRow, SuggestionRow

NEW_DAYS = 7


def _deadline_part(kind: str, n: int) -> tuple[str, str]:
    if kind == "submission":
        if n <= 0:
            return "Hạn nộp bài hôm nay", "Paper due today"
        if n == 1:
            return "Hạn nộp bài ngày mai", "Paper due tomorrow"
        return f"Hạn nộp bài còn {n} ngày", f"Paper due in {n} days"
    if n <= 0:
        return "Hạn gần nhất hôm nay", "Next deadline today"
    if n == 1:
        return "Hạn gần nhất ngày mai", "Next deadline tomorrow"
    return f"Hạn gần nhất còn {n} ngày", f"Next deadline in {n} days"


def new_papers_count(db: Database, user_id: str, now: datetime) -> int:
    """Featured pending suggestions plus `new` entries added in the last 7 days."""
    with db.session() as s:
        sug = s.scalar(select(func.count()).select_from(SuggestionRow).where(
            SuggestionRow.user_id == user_id, SuggestionRow.status == "pending", SuggestionRow.featured.is_(True))) or 0
        new = s.scalar(select(func.count()).select_from(ReadingEntryRow).where(
            ReadingEntryRow.user_id == user_id, ReadingEntryRow.removed_at.is_(None), ReadingEntryRow.status == "new",
            ReadingEntryRow.added_at >= now - timedelta(days=NEW_DAYS))) or 0
    return int(sug + new)


def status_line(db: Database, user_id: str, now: datetime) -> dict[str, str]:
    today: date = now.astimezone(TZ).date()
    with db.session() as s:
        prof = s.get(ResearchProfileRow, user_id)
        has_topic = bool(prof and prof.title)
    if not has_topic:
        return {"line_vi": "Đặt đề tài của bạn", "line_en": "Set your topic"}
    parts_vi: list[str] = []
    parts_en: list[str] = []
    near = [m for m in milestones.open_deadlines(db, user_id, today, horizon_days=30)
            if m.get("confirmed") and (date.fromisoformat(m["due_date"]) - today).days >= 0]
    if near:
        m = near[0]
        vi, en = _deadline_part(m.get("kind") or "other", (date.fromisoformat(m["due_date"]) - today).days)
        parts_vi.append(vi)
        parts_en.append(en)
    k = new_papers_count(db, user_id, now)
    if k:
        parts_vi.append(f"{k} paper mới")
        parts_en.append(f"{k} new paper" + ("" if k == 1 else "s"))
    if not parts_vi:
        return {"line_vi": "Chưa có gì mới", "line_en": "Nothing new"}
    return {"line_vi": ", ".join(parts_vi), "line_en": ", ".join(parts_en)}
