"""Chat cards on the gateway side (CONTRACTS section 9): history records, card lookup, card_action checks.

The harness writes cards into the chat transcript `sessions/<day>/s-<YYYYMMDD>.jsonl` (in order with the
messages around them, also for cards made by background jobs); the gateway reads that file from the mirror.
"""

import json
from datetime import date, datetime, timedelta

from mentor_schemas import JobKind
from mentor_schemas.interaction import (
    CARD_ACTIONS,
    FOCUS_DEFAULT_MINUTES,
    FOCUS_EXTEND_DEFAULT,
    FOCUS_EXTEND_MAX,
    FOCUS_MAX_MINUTES,
    FOCUS_MIN_MINUTES,
    MAX_ACTION_VALUE_CHARS,
    card_day,
    chat_path,
    conversation_path,
)
from sqlalchemy import select

from mentor_gateway.db import Database, JobRow

LETTERS = "ABCD"


class CardActionError(ValueError):
    """A card_action the gateway refuses; the message (Vietnamese) goes to the client as an error."""


def _records(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def history_from_jsonl(text: str) -> list[dict]:
    """GET /api/chat/history items, in transcript order.

    `{ts, role: "user", text, attachments, card_action?}`, `{ts, role: "mentor", text, attachments, suggestions?}`,
    `{ts, role: "card", card}`. A card that appears again (focus extended/ended) keeps its first position and takes
    the newest content.
    """
    out: list[dict] = []
    card_pos: dict[str, int] = {}
    for item in _records(text):
        role = item.get("role")
        if role == "card":
            card = item.get("card")
            if not isinstance(card, dict) or not isinstance(card.get("id"), str) or not isinstance(card.get("kind"), str):
                continue
            if card["id"] in card_pos:
                out[card_pos[card["id"]]]["card"] = card
                continue
            card_pos[card["id"]] = len(out)
            out.append({"ts": item.get("ts"), "role": "card", "card": card})
            continue
        if role not in ("user", "mentor"):
            continue
        rec = {"ts": item.get("ts"), "role": role, "text": str(item.get("text") or ""),
               "attachments": [str(a) for a in item.get("attachments") or []]}
        if role == "user" and isinstance(item.get("card_action"), dict):
            rec["card_action"] = item["card_action"]
        if role == "mentor" and isinstance(item.get("suggestions"), list):
            rec["suggestions"] = item["suggestions"]
        out.append(rec)
    return out


def card_paths(card_id: str, today: date, conversation_id: str | None = None) -> list[str]:
    """Transcript files that may hold the card: its own day's session (and the day before, for a turn that started
    just before midnight), then today's (a later update)."""
    day = card_day(card_id)
    if day is None:
        return []
    folder = chat_path(day).rsplit("/", 1)[0]
    prev = chat_path(day - timedelta(days=1)).rsplit("/", 1)[1]
    paths = [chat_path(day), f"{folder}/{prev}", chat_path(today)]
    if conversation_id:  # a card of a named conversation lives in that conversation's transcript
        paths = [conversation_path(day, conversation_id), conversation_path(day - timedelta(days=1), conversation_id),
                 conversation_path(today, conversation_id), *paths]
    return list(dict.fromkeys(paths))


def latest_card(texts: list[str | None], card_id: str) -> dict | None:
    found = None
    for text in texts:
        for item in _records(text or ""):
            card = item.get("card") if item.get("role") == "card" else None
            if isinstance(card, dict) and card.get("id") == card_id:
                found = card
    return found


def _minutes(value: str | None, default: int, lo: int, hi: int) -> int:
    if value in (None, ""):
        return default
    try:
        n = int(str(value).strip())
    except ValueError as exc:
        raise CardActionError(f"Số phút phải là số nguyên {lo}–{hi}.") from exc
    if not lo <= n <= hi:
        raise CardActionError(f"Số phút phải trong khoảng {lo}–{hi}.")
    return n


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def resolve_action(card: dict, action: str, value: object) -> tuple[str | None, str]:
    """(normalized value, Vietnamese echo for the history) or CardActionError."""
    kind = str(card.get("kind"))
    if action not in CARD_ACTIONS.get(kind, ()):
        allowed = ", ".join(CARD_ACTIONS.get(kind, ())) or "không có"
        raise CardActionError(f"Thẻ {kind} không có thao tác '{action}' (được: {allowed}).")
    raw = None if value is None else " ".join(str(value).split())
    if raw is not None and len(raw) > MAX_ACTION_VALUE_CHARS:
        raise CardActionError(f"Giá trị dài quá {MAX_ACTION_VALUE_CHARS} ký tự.")
    if kind == "flashcard":
        if action == "skip":
            return None, "Bỏ qua thẻ này"
        if not raw:
            raise CardActionError("Thiếu câu trả lời.")
        choices = card.get("choices") or []
        if not choices:
            return raw, f"Trả lời: {_short(raw, 200)}"
        letter = None
        if raw.upper() in LETTERS[: len(choices)]:
            letter = raw.upper()
        elif raw in choices:
            letter = LETTERS[choices.index(raw)]
        if letter is None:
            raise CardActionError("Lựa chọn không có trên thẻ.")
        return letter, f"Đã chọn: {letter}. {_short(str(choices[LETTERS.index(letter)]))}"
    if kind == "checkin":
        if not raw:
            raise CardActionError("Thiếu câu trả lời.")
        options = card.get("options") or []
        return raw, (f"Đã chọn: {_short(raw)}" if raw in options else f"Trả lời: {_short(raw, 200)}")
    if kind == "deadline":
        title = _short(str(card.get("title") or ""))
        if action == "done":
            return None, f"Đã xong: {title}"
        minutes = _minutes(raw, FOCUS_DEFAULT_MINUTES, FOCUS_MIN_MINUTES, FOCUS_MAX_MINUTES)
        return str(minutes), f"Bắt đầu tập trung {minutes} phút cho: {title}"
    # focus
    if action == "done":
        return None, "Đã xong phiên tập trung"
    minutes = _minutes(raw, FOCUS_EXTEND_DEFAULT, FOCUS_MIN_MINUTES, FOCUS_EXTEND_MAX)
    return str(minutes), f"Thêm {minutes} phút tập trung"


def cancel_focus_jobs(db: Database, user_id: str, card_id: str, now: datetime) -> int:
    """Pending focus_end wake-ups of a focus card (it ended early or was extended: the harness schedules anew)."""
    n = 0
    with db.session() as s:
        rows = s.scalars(select(JobRow).where(JobRow.user_id == user_id, JobRow.kind == JobKind.FOCUS_END.value,
                                              JobRow.status == "pending"))
        for row in rows:
            if (row.payload or {}).get("card_id") == card_id:
                row.status = "cancelled"
                row.finished_at = now
                row.summary = "Phiên tập trung đã kết thúc hoặc được gia hạn."
                n += 1
    return n
