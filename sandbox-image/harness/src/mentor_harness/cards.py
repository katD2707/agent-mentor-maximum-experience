"""Chat cards (CONTRACTS.md section 9): validation of `show_card` data, ids, transcript lookup, model context.

A card is `{id, kind, created_at, ...data}`. It is written to the chat transcript
`sessions/<day>/<session>.jsonl` as `{"ts", "role": "card", "card": {...}}`, in order with the messages around it.
A later record with the same id updates that card (focus extended or ended).
"""

import json
import math
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from mentor_schemas import WorkspacePaths
from mentor_schemas.interaction import (
    CARD_KINDS,
    PRACTICE_GOALS,
    PRACTICE_MINUTES,
    PRACTICE_SUBJECTS,
    card_day,
    chat_path,
)

from mentor_harness.config import LOCAL_TZ
from mentor_harness.workspace import Workspace

MAX_CARDS_PER_RUN = 3  # show_card calls per turn or job
FLASHCARD_MIN_CHOICES = 2
FLASHCARD_MAX_CHOICES = 4
CHECKIN_MIN_OPTIONS = 2
CHECKIN_MAX_OPTIONS = 4
LETTERS = "ABCD"
# Shape only: the harness cannot call the gateway's /practice API in every backend, so the web app and the
# practice API reject topics and profiles they do not know (CONTRACTS section 10.5).
TOPIC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,58}$")
PROFILE_ID_RE = re.compile(r"^[a-z]+\.[a-z0-9][a-z0-9._-]{0,70}$")
FOCUS_ACTIVITY_RE = re.compile(r"(\d+) phút")
WEEK_DAYS = 7


class CardError(ValueError):
    """Invalid card data; the Vietnamese message goes back to the model."""


def new_card_id(day: date) -> str:
    return f"card-{day:%Y%m%d}-{secrets.token_hex(6)}"


def _text(data: dict[str, Any], key: str, limit: int, *, required: bool = True, lines: int = 1) -> str | None:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip() and not required):
        if required:
            raise CardError(f"Thiếu '{key}' (chuỗi).")
        return None
    if not isinstance(value, str) or not value.strip():
        raise CardError(f"'{key}' phải là chuỗi không rỗng.")
    if lines > 1:  # keep line breaks (e.g. a numbered list), spaces collapsed within each line
        kept = [" ".join(line.split()) for line in value.strip().splitlines()]
        kept = [line for line in kept if line]
        if len(kept) > lines:
            raise CardError(f"'{key}' tối đa {lines} dòng.")
        value = "\n".join(kept)
    else:
        value = " ".join(value.split())
    if len(value) > limit:
        raise CardError(f"'{key}' dài quá {limit} ký tự.")
    return value


def _str_list(data: dict[str, Any], key: str, lo: int, hi: int, limit: int, *, required: bool) -> list[str] | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, list) or not lo <= len(value) <= hi:
        raise CardError(f"'{key}' phải là danh sách {lo}–{hi} chuỗi.")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CardError(f"'{key}[{i}]' phải là chuỗi không rỗng.")
        item = " ".join(item.split())
        if len(item) > limit:
            raise CardError(f"'{key}[{i}]' dài quá {limit} ký tự.")
        if item in out:
            raise CardError(f"'{key}' có hai mục trùng nhau: {item}.")
        out.append(item)
    return out


def _int(data: dict[str, Any], key: str, hi: int) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= hi:
        raise CardError(f"'{key}' phải là số nguyên 0..{hi}.")
    return value


def _check_keys(data: dict[str, Any], allowed: set[str], kind: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise CardError(f"Thẻ {kind} không có trường {', '.join(extra)} (chỉ: {', '.join(sorted(allowed))}).")


def _subject(data: dict[str, Any]) -> str:
    subject = data.get("subject")
    if subject not in PRACTICE_SUBJECTS:
        raise CardError(f"'subject' phải là một trong: {', '.join(PRACTICE_SUBJECTS)}.")
    return subject


def review_queue_skills(ws: Workspace) -> set[str]:
    """Skill ids listed in learning/**/review-queue.md (tables written by bkt_update)."""
    out: set[str] = set()
    base = ws.root / WorkspacePaths.LEARNING_DIR
    if not base.is_dir():
        return out
    for path in base.rglob("review-queue.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) > 1 and re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)+", cells[0]):
                out.add(cells[0])
    return out


def parse_due(raw: str) -> datetime:
    try:
        when = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise CardError(f"'due_at' phải là ngày giờ ISO 8601, ví dụ 2026-11-07T23:59:00+07:00 (nhận: {raw}).") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=LOCAL_TZ)
    return when.astimezone(LOCAL_TZ)


def validate(kind: str, data: Any, ws: Workspace) -> dict[str, Any]:
    """Cleaned card fields for `kind` (without id/kind/created_at), or CardError."""
    if kind not in CARD_KINDS:
        raise CardError(f"kind phải là một trong: {', '.join(CARD_KINDS)}.")
    if not isinstance(data, dict):
        raise CardError("'data' phải là một JSON object.")
    if kind == "flashcard":
        _check_keys(data, {"skill", "front", "choices", "reveal"}, kind)
        skill = _text(data, "skill", 80)
        queue = review_queue_skills(ws)
        if skill not in queue:
            raise CardError(
                f"Kỹ năng {skill} không có trong learning/<môn>/review-queue.md. Flashcard chỉ dùng cho kỹ năng trong "
                "hàng đợi ôn (do bkt_update sinh); câu khác thì hỏi bằng chữ."
            )
        out: dict[str, Any] = {"skill": skill, "front": _text(data, "front", 300)}
        choices = _str_list(data, "choices", FLASHCARD_MIN_CHOICES, FLASHCARD_MAX_CHOICES, 120, required=False)
        if choices:
            out["choices"] = choices
        if reveal := _text(data, "reveal", 300, required=False):
            out["reveal"] = reveal
        return out
    if kind == "deadline":
        _check_keys(data, {"title", "due_at", "source"}, kind)
        out = {"title": _text(data, "title", 120), "due_at": parse_due(_text(data, "due_at", 40) or "").isoformat()}
        if source := _text(data, "source", 120, required=False):
            out["source"] = source
        return out
    if kind == "celebration":
        _check_keys(data, {"title", "detail"}, kind)
        out = {"title": _text(data, "title", 80)}
        if detail := _text(data, "detail", 200, required=False):
            out["detail"] = detail
        return out
    if kind == "weekly":
        _check_keys(data, {"focus_minutes", "milestones_done", "mistakes_fixed", "streak_days", "highlight"}, kind)
        out = {
            "focus_minutes": _int(data, "focus_minutes", 7 * 24 * 60),
            "milestones_done": _int(data, "milestones_done", 999) or 0,
            "mistakes_fixed": _int(data, "mistakes_fixed", 999) or 0,
            "streak_days": _int(data, "streak_days", 3650),
        }
        if highlight := _text(data, "highlight", 200, required=False):
            out["highlight"] = highlight
        return out
    if kind == "checkin":
        _check_keys(data, {"prompt", "options"}, kind)
        return {
            "prompt": _text(data, "prompt", 300, lines=6),
            "options": _str_list(data, "options", CHECKIN_MIN_OPTIONS, CHECKIN_MAX_OPTIONS, 60, required=True),
        }
    if kind == "practice":
        _check_keys(data, {"subject", "minutes", "goal", "topics", "title", "reason"}, kind)
        subject = _subject(data)
        minutes = data.get("minutes")
        if isinstance(minutes, float) and minutes.is_integer():
            minutes = int(minutes)
        if isinstance(minutes, bool) or minutes not in PRACTICE_MINUTES:
            raise CardError(f"'minutes' phải là một trong {', '.join(map(str, PRACTICE_MINUTES))}.")
        goal = data.get("goal") or "balanced"
        if goal not in PRACTICE_GOALS:
            raise CardError(f"'goal' phải là một trong: {', '.join(PRACTICE_GOALS)}.")
        out = {"subject": subject, "minutes": minutes, "goal": goal}
        topics = _str_list(data, "topics", 1, 6, 60, required=False)
        if topics:
            for t in topics:
                if not TOPIC_ID_RE.fullmatch(t):
                    raise CardError(f"topics: id chủ đề không hợp lệ: {t} (dạng như exp-log; lấy từ danh sách chủ đề).")
            out["topics"] = topics
        out["title"] = _text(data, "title", 80)
        out["reason"] = _text(data, "reason", 200)
        return out
    if kind == "mock":
        _check_keys(data, {"subject", "profile_id", "title"}, kind)
        subject = _subject(data)
        profile = _text(data, "profile_id", 80)
        if not PROFILE_ID_RE.fullmatch(profile) or profile.split(".", 1)[0] != subject:
            raise CardError(f"'profile_id' phải có dạng {subject}.<tên>, ví dụ {subject}.mcq-mock.2026.")
        return {"subject": subject, "profile_id": profile, "title": _text(data, "title", 80)}
    # focus: built by start_focus only
    raise CardError("Thẻ focus chỉ tạo bằng start_focus (để hệ thống hẹn giờ kết thúc).")


def make_card(kind: str, fields: dict[str, Any], now: datetime, day: date) -> dict[str, Any]:
    return {"id": new_card_id(day), "kind": kind, "created_at": now.isoformat(timespec="seconds"), **fields}


def card_record(card: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {"ts": now.isoformat(), "role": "card", "card": card}


# ---- weekly stats the model may leave out ------------------------------------------------------


def _activity(ws: Workspace) -> list[dict[str, Any]]:
    text = ws.read_text(WorkspacePaths.ACTIVITY) or ""
    out = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _local_day(raw: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(raw)).astimezone(LOCAL_TZ).date()
    except (TypeError, ValueError):
        return None


def focus_minutes_since(ws: Workspace, start: date) -> int:
    """Planned minutes of focus sessions started since `start` (activity `start_focus` and `focus_extend`)."""
    total = 0
    for item in _activity(ws):
        if item.get("action") not in ("start_focus", "focus_extend"):
            continue
        day = _local_day(item.get("ts"))
        m = FOCUS_ACTIVITY_RE.search(str(item.get("summary") or ""))
        if day and day >= start and m:
            total += int(m.group(1))
    return total


def active_streak(ws: Workspace, today: date) -> int:
    """Consecutive days up to today (or yesterday) on which the learner wrote in the chat."""
    sessions = ws.root / WorkspacePaths.SESSIONS_DIR
    days: set[date] = set()
    if sessions.is_dir():
        for path in sessions.glob("*/*.jsonl"):
            try:
                day = date.fromisoformat(path.parent.name)
            except ValueError:
                continue
            if day > today - timedelta(days=400) and '"role": "user"' in path.read_text(encoding="utf-8", errors="replace"):
                days.add(day)
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def fill_weekly(ws: Workspace, fields: dict[str, Any], today: date) -> dict[str, Any]:
    if fields.get("focus_minutes") is None:
        fields["focus_minutes"] = focus_minutes_since(ws, today - timedelta(days=WEEK_DAYS - 1))
    if fields.get("streak_days") is None:
        fields["streak_days"] = active_streak(ws, today)
    return fields


# ---- lookup and model context ----------------------------------------------------------------


def find_card(ws: Workspace, card_id: str, also: list[str] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Latest version of a card and the transcript file it was first written to (from its id's day)."""
    day = card_day(card_id)
    if day is None:
        return None, None
    home = chat_path(day)
    paths = [home]
    folder = ws.root / WorkspacePaths.SESSIONS_DIR / day.isoformat()
    if folder.is_dir():  # other session names of that day (tests, older ids)
        paths += sorted(ws.rel(p) for p in folder.glob("*.jsonl") if ws.rel(p) != home)
    paths += [p for p in also or [] if p not in paths]
    found: dict[str, Any] | None = None
    first: str | None = None
    for rel in paths:
        for line in (ws.read_text(rel) or "").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            card = record.get("card") if isinstance(record, dict) and record.get("role") == "card" else None
            if isinstance(card, dict) and card.get("id") == card_id:
                found = card
                first = first or rel
    return found, first


def describe(card: dict[str, Any]) -> str:
    """One line about a card, for the model (history reload and card actions)."""
    kind = card.get("kind")
    if kind == "flashcard":
        parts = [f"kỹ năng {card.get('skill')}", f"câu hỏi: {card.get('front')}"]
        if card.get("choices"):
            parts.append("lựa chọn: " + "; ".join(f"{LETTERS[i]}. {c}" for i, c in enumerate(card["choices"])))
        if card.get("reveal"):
            parts.append(f"đáp án/giải thích đã ghi: {card['reveal']}")
        return "flashcard (" + ", ".join(parts) + ")"
    if kind == "deadline":
        return f"deadline ({card.get('title')}, hạn {card.get('due_at')})"
    if kind == "focus":
        ended = f", đã kết thúc {card['ended_at']}" if card.get("ended_at") else ""
        return f"focus ({card.get('task')}, {card.get('minutes')} phút, hết giờ {card.get('ends_at')}{ended})"
    if kind == "celebration":
        return f"celebration ({card.get('title')})"
    if kind == "weekly":
        return "weekly (" + ", ".join(f"{k}={card.get(k)}" for k in (
            "focus_minutes", "milestones_done", "mistakes_fixed", "streak_days")) + ")"
    if kind == "practice":
        topics = f", chủ đề {', '.join(card['topics'])}" if card.get("topics") else ""
        return (f"practice ({card.get('title')}: {card.get('subject')}, {card.get('minutes')} phút, "
                f"mục tiêu {card.get('goal')}{topics})")
    if kind == "mock":
        return f"mock ({card.get('title')}: {card.get('subject')}, hồ sơ {card.get('profile_id')})"
    if kind == "checkin":
        return f"checkin ({card.get('prompt')}; lựa chọn: {'; '.join(card.get('options') or [])})"
    return str(kind)


def focus_end_skip_reason(card: dict[str, Any] | None, now: datetime) -> str | None:
    """Why a focus_end job should not check in (card gone, ended early, or extended past this wake)."""
    if card is None or card.get("kind") != "focus":
        return "không tìm thấy phiên tập trung."
    if card.get("ended_at"):
        return "người học đã kết thúc phiên trước khi hết giờ."
    try:
        ends = datetime.fromisoformat(str(card.get("ends_at")))
    except ValueError:
        return "phiên tập trung không có giờ kết thúc hợp lệ."
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=LOCAL_TZ)
    if ends > now + timedelta(minutes=2):
        return "phiên đã được gia hạn; sẽ hỏi thăm khi hết giờ mới."
    return None


def focus_minutes_between(start: datetime, end: datetime) -> int:
    return max(0, math.ceil((end - start).total_seconds() / 60))
