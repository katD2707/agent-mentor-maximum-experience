"""Chat interaction layer shared by the harness and the gateway (CONTRACTS.md section 9, owner H).

Cards live in the chat transcript `sessions/<YYYY-MM-DD>/s-<YYYYMMDD>.jsonl` as records
`{"ts", "role": "card", "card": {id, kind, created_at, ...}}`. The card id carries the day of the transcript file
it was first written to, so the gateway can find a card from its id alone. A later record with the same id is an
update of that card (focus extended or ended) and replaces it.
"""

import re
from datetime import date

CARD_KINDS: tuple[str, ...] = (
    "flashcard", "deadline", "focus", "celebration", "weekly", "checkin", "practice", "mock",
)

# Practice and mock suggestion cards (CONTRACTS section 10.5): the web card opens the practice UI; no card_action.
PRACTICE_SUBJECTS: tuple[str, ...] = ("math", "physics", "english")
PRACTICE_MINUTES: tuple[int, ...] = (10, 20, 30, 45)
PRACTICE_GOALS: tuple[str, ...] = ("balanced", "weak", "challenge")

# card_action actions per kind (client -> gateway). Kinds missing here take no actions.
CARD_ACTIONS: dict[str, tuple[str, ...]] = {
    "flashcard": ("answer", "skip"),
    "checkin": ("answer",),
    "deadline": ("done", "start_focus"),
    "focus": ("done", "extend"),
}

# Kinds a background job may put into the chat (shown the next time the learner opens it).
JOB_CARD_KINDS: frozenset[str] = frozenset({"weekly", "checkin", "deadline"})

MAX_SUGGESTIONS = 3
SUGGESTION_LABEL_CHARS = 40
SUGGESTION_TEXT_CHARS = 300
MAX_ACTION_VALUE_CHARS = 300
FOCUS_MIN_MINUTES = 5
FOCUS_MAX_MINUTES = 90
FOCUS_EXTEND_DEFAULT = 10
FOCUS_EXTEND_MAX = 60
FOCUS_DEFAULT_MINUTES = 25

CARD_ID_RE = re.compile(r"^card-(\d{8})-[0-9a-f]{12}$")


def card_day(card_id: str) -> date | None:
    """The transcript day encoded in a card id, or None if the id is malformed."""
    m = CARD_ID_RE.match(card_id or "")
    if not m:
        return None
    raw = m.group(1)
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


def chat_path(day: date) -> str:
    """Transcript file of the gateway's daily session for `day` (CONTRACTS section 2)."""
    return f"sessions/{day.isoformat()}/s-{day:%Y%m%d}.jsonl"


DAILY_SESSION_RE = re.compile(r"^s-(\d{8})$")
CONVERSATION_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def conversation_session_id(conversation_id: str) -> str:
    """Session id of a named conversation (CONTRACTS section 10.5): `c-<id>`, id = 12 hex chars."""
    return f"c-{conversation_id}"


def conversation_path(day: date, conversation_id: str) -> str:
    return f"sessions/{day.isoformat()}/{conversation_session_id(conversation_id)}.jsonl"


def card_action_text(kind: str, action: str, value: str | None) -> str:
    """What the agent sees as the user's message for a card_action: `[card:<kind> <action> <value>]`."""
    clean = " ".join((value or "").replace("]", ")").split())[:MAX_ACTION_VALUE_CHARS]
    return f"[card:{kind} {action}{' ' + clean if clean else ''}]"
