"""Layer 1 (3.7): behaviour events. Stored compactly in `behaviour_events`; also derived from enrollment progress and
practice answers so a learner who never sent an event still has signals.

An event is `{"id", "kind", "ts", "data"}`; `data` keeps only the fields listed in FIELDS (anything else is dropped).
Readers get plain dicts `{"kind", "ts" (aware UTC), "data", "derived"}`.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mentor_gateway.content.tables import Enrollment
from mentor_gateway.db import Database
from mentor_gateway.planner.tables import BehaviourEvent
from mentor_gateway.practice.tables import PracticeAnswer, PracticeSession

log = logging.getLogger(__name__)

MAX_BATCH = 500
FUTURE_SLACK = timedelta(hours=24)
OUTCOMES = ("opened", "ignored", "snoozed")
ASK_INTENTS = ("learn", "solve", "other")
ASK_INPUTS = ("text", "photo", "voice")
# kind -> {field: (type, max)}; numbers are clamped, strings cut
FIELDS: dict[str, dict[str, tuple[type, float]]] = {
    "app_open": {},
    "session_start": {"session": (str, 64)},
    "session_end": {"session": (str, 64), "seconds": (int, 6 * 3600)},
    "focus_tick": {"session": (str, 64), "seconds": (int, 600)},  # active seconds since the previous tick
    "lesson_progress": {"course_id": (str, 80), "lesson_id": (str, 80), "pct": (float, 100)},
    "video_watch": {"course_id": (str, 80), "lesson_id": (str, 80), "block_id": (str, 80), "pct": (float, 100)},
    "quiz_answer": {"item": (str, 80), "course_id": (str, 80), "correct": (bool, 1), "seconds": (float, 3600),
                    "session": (str, 64)},
    "reminder_outcome": {"reminder_id": (str, 32), "outcome": (str, 10), "at": (str, 40)},
    "ask_question": {"intent": (str, 8), "input": (str, 8)},  # Hỏi đáp: a new question (never its text)
    "ask_course_open": {"course_id": (str, 80)},  # a course card of an answer was opened
    # Nghiên cứu (CONTRACTS 15.9): recorded by the research endpoints themselves, `POST /events` rejects them
    "paper_opened": {"paper_id": (str, 64)},
    "paper_read": {"paper_id": (str, 64)},
    "summary_written": {"paper_id": (str, 64), "chars": (int, 4000)},
    "experiment_logged": {"experiment_id": (str, 40), "status": (str, 12)},
}
KINDS = tuple(FIELDS)


def clean_data(kind: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Whitelisted, clamped fields; None when a required field is missing or invalid."""
    out: dict[str, Any] = {}
    for name, (typ, cap) in FIELDS[kind].items():
        if name not in data or data[name] is None:
            continue
        v = data[name]
        try:
            if typ is str:
                out[name] = str(v)[: int(cap)]
            elif typ is bool:
                out[name] = bool(v)
            elif typ is int:
                out[name] = max(0, min(int(v), int(cap)))
            else:
                out[name] = max(0.0, min(float(v), cap))
        except (TypeError, ValueError):
            return None
    if kind == "quiz_answer" and not ("item" in out and "correct" in out):
        return None
    if kind == "reminder_outcome" and out.get("outcome") not in OUTCOMES:
        return None
    if kind == "ask_question" and not (out.get("intent") in ASK_INTENTS and out.get("input") in ASK_INPUTS):
        return None
    if kind in ("lesson_progress", "video_watch", "ask_course_open") and "course_id" not in out:
        return None
    if kind == "focus_tick" and "seconds" not in out:
        return None
    if kind in ("paper_opened", "paper_read", "summary_written") and "paper_id" not in out:
        return None
    if kind == "experiment_logged" and "experiment_id" not in out:
        return None
    return out


def _aware(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def ingest(db: Database, user_id: str, events: list[dict[str, Any]], now: datetime) -> dict[str, int]:
    """Idempotent by (user, client id). Returns {accepted, duplicates, rejected}."""
    clean: dict[str, tuple[str, datetime, dict]] = {}
    rejected = max(0, len(events) - MAX_BATCH)
    for e in events[:MAX_BATCH]:
        try:
            kind, cid = e["kind"], str(e["id"])[:64]
            ts = _aware(e["ts"] if isinstance(e["ts"], datetime) else datetime.fromisoformat(str(e["ts"])))
            data = clean_data(kind, dict(e.get("data") or {})) if kind in FIELDS else None
        except (KeyError, ValueError, TypeError):
            rejected += 1
            continue
        if data is None or not cid or ts > now + FUTURE_SLACK:
            rejected += 1
            continue
        clean.setdefault(cid, (kind, ts, data))
    accepted = 0
    with db.session() as s:
        have = set(s.scalars(select(BehaviourEvent.client_id).where(
            BehaviourEvent.user_id == user_id, BehaviourEvent.client_id.in_(list(clean)))))
        for cid, (kind, ts, data) in clean.items():
            if cid in have:
                continue
            try:  # two windows of one student can flush the same queue at once: the loser is a duplicate, not a 500
                with s.begin_nested():
                    s.add(BehaviourEvent(user_id=user_id, client_id=cid, kind=kind, ts=ts, data=data))
                    s.flush()
            except IntegrityError:
                continue
            accepted += 1
    return {"accepted": accepted, "duplicates": len(clean) - accepted, "rejected": rejected}


def record(db: Database, user_id: str, client_id: str, kind: str, ts: datetime, data: dict) -> None:
    ingest(db, user_id, [{"id": client_id, "kind": kind, "ts": ts, "data": data}], ts)


def stored(db: Database, user_id: str, since: datetime) -> list[dict]:
    with db.session() as s:
        rows = s.scalars(select(BehaviourEvent).where(BehaviourEvent.user_id == user_id, BehaviourEvent.ts >= since)
                         .order_by(BehaviourEvent.ts, BehaviourEvent.id)).all()
        return [{"kind": r.kind, "ts": r.ts, "data": dict(r.data or {}), "derived": False} for r in rows]


def derived(db: Database, user_id: str, since: datetime, have_real_lessons: bool, real_items: set[str]) -> list[dict]:
    """Events reconstructed from tables that already exist: practice answers (always) and enrollment progress /
    quiz state (only when the app sent no lesson_progress/quiz_answer itself)."""
    out: list[dict] = []
    with db.session() as s:
        rows = s.execute(
            select(PracticeAnswer, PracticeSession.items)
            .join(PracticeSession, PracticeSession.id == PracticeAnswer.session_id)
            .where(PracticeAnswer.user_id == user_id, PracticeAnswer.answered_at.is_not(None),
                   PracticeAnswer.answered_at >= since, PracticeAnswer.correct.is_not(None))).all()
        for ans, items in rows:
            doc = next((i.get("doc") or {} for i in items or [] if i.get("position") == ans.position), {})
            course = doc.get("course") if isinstance(doc, dict) else None
            if course:  # a course quiz item answered in Luyện tập: the same item/course ids as a lesson quiz (FSRS + lesson)
                out.append({"kind": "quiz_answer", "ts": ans.answered_at, "derived": True,
                            "data": {"item": course["item_id"], "course_id": course["course_id"], "correct": bool(ans.correct),
                                     "seconds": float(ans.time_spent_sec or 0)}})
                continue
            item = str((doc.get("id") if isinstance(doc, dict) else doc) or f"{ans.session_id}:{ans.position}")
            out.append({"kind": "quiz_answer", "ts": ans.answered_at, "derived": True,
                        "data": {"item": "p:" + item, "correct": bool(ans.correct),
                                 "seconds": float(ans.time_spent_sec or 0)}})
        if not have_real_lessons:
            for en in s.scalars(select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.updated_at >= since)):
                if en.completed_block_ids or en.last_lesson_id:
                    out.append({"kind": "lesson_progress", "ts": en.updated_at, "derived": True,
                                "data": {"course_id": en.course_id, "lesson_id": en.last_lesson_id or ""}})
                for item, q in (en.quiz or {}).items():
                    if item not in real_items:
                        out.append({"kind": "quiz_answer", "ts": en.updated_at, "derived": True,
                                    "data": {"item": item, "course_id": en.course_id, "correct": bool(q.get("correct")),
                                             "seconds": float(q.get("seconds") or 0)}})
    return out


def load(db: Database, user_id: str, now: datetime, days: int = 60) -> list[dict]:
    since = now - timedelta(days=days)
    real = stored(db, user_id, since)
    has_lessons = any(e["kind"] in ("lesson_progress", "video_watch", "session_start", "focus_tick") for e in real)
    items = {e["data"].get("item") for e in real if e["kind"] == "quiz_answer"}
    both = real + derived(db, user_id, since, has_lessons, items)
    both.sort(key=lambda e: e["ts"])
    return both
