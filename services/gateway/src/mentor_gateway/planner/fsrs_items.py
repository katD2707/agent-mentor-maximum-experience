"""Due review items with FSRS (`py-fsrs`, MIT). Each quiz answer is one review: correct = Good, wrong = Again.

Cards are rebuilt by replaying the (bounded) event log, so there is no second store to keep in sync. Items answered
correctly many times drift out to long intervals; a wrong answer brings an item back within minutes or days.
"""

from datetime import datetime

from fsrs import Card, Rating, Scheduler

_SCHED = Scheduler(enable_fuzzing=False)  # deterministic: the same events always give the same due dates


def replay(events: list[dict]) -> dict[str, Card]:
    cards: dict[str, Card] = {}
    for e in events:
        if e["kind"] != "quiz_answer":
            continue
        item = e["data"].get("item")
        if not item:
            continue
        card = cards.get(item) or Card()
        rating = Rating.Good if e["data"].get("correct") else Rating.Again
        cards[item] = _SCHED.review_card(card, rating, e["ts"])[0]
    return cards


def due_items(events: list[dict], now: datetime, limit: int = 30) -> list[dict]:
    """[{item, course_id, due, overdue_days, retrievability, stability}], most overdue first. Practice items ("p:...")
    have no course and are counted but not placed into a lesson."""
    course_of = {e["data"]["item"]: e["data"].get("course_id") for e in events
                 if e["kind"] == "quiz_answer" and e["data"].get("item")}
    out = []
    for item, card in replay(events).items():
        if card.due > now:
            continue
        try:
            r = round(float(_SCHED.get_card_retrievability(card, now)), 3)
        except Exception:  # noqa: BLE001 - informational only
            r = None
        out.append({"item": item, "course_id": course_of.get(item), "due": card.due.isoformat(),
                    "overdue_days": round((now - card.due).total_seconds() / 86400, 2),
                    "retrievability": r, "stability": round(card.stability or 0.0, 2)})
    out.sort(key=lambda d: -d["overdue_days"])
    return out[:limit]
