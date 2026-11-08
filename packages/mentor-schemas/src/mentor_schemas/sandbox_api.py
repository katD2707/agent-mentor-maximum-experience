"""HTTP API between the control plane (gateway) and the harness inside a sandbox.

The sandbox has no network except the model router. It never sends anything to
the learner or the internet directly: everything leaving the sandbox is
an OutboxItem in a turn's `done` event or in a JobResult, and the control plane
delivers it.

Endpoints served by the harness (port 8080 inside the container):
  GET  /v1/health                    -> {"status": "ok"}
  POST /v1/turn      TurnRequest     -> text/event-stream of SandboxEvent (one JSON per `data:` line)
  POST /v1/jobs      JobRequest      -> JobResult (synchronous, up to 10 minutes)
  POST /v1/approvals ApprovalDecision -> {"ok": true}; resumes the waiting turn

After every turn and job the harness commits the workspace (`git commit`, author
"mentor <mentor@local>"). Pushing to the mirror is the control plane's job.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from mentor_schemas.workspace import Profile


class Attachment(BaseModel):
    path: str  # workspace-relative, already written to inbox/ by the control plane
    mime_type: str


class CardAction(BaseModel):
    """A click on a chat card (CONTRACTS section 9), checked by the gateway against the transcript."""

    card_id: str
    kind: str
    action: str
    value: str | None = None  # normalized by the gateway (flashcard choice letter, minutes, option text)
    echo: str  # short Vietnamese line stored in the chat history instead of the `[card:...]` text


class TurnRequest(BaseModel):
    session_id: str
    user_id: str
    profile: Profile
    text: str  # for a card action: `[card:<kind> <action> <value>]`
    attachments: list[Attachment] = []
    client_time: datetime | None = None
    card_action: CardAction | None = None


class OutboxKind(str, Enum):
    NOTIFY_USER = "notify_user"  # learner notification ("nudge"); payload: NotifyPayload (only `text` required)
    NEXT_WAKE = "next_wake"  # payload: {"at": iso datetime, "job_kind": ...}


class OutboxItem(BaseModel):
    kind: OutboxKind
    payload: dict[str, Any] = {}
    dedupe_key: str | None = None  # control plane drops duplicates (idempotency)


# ---- rich notifications ("nudges", CONTRACTS section 9) ---------------------------------------

NotificationKind = Literal["checkin", "deadline", "review", "focus_end", "celebration", "report", "nudge"]
MascotState = Literal["idle", "listening", "thinking", "talking", "happy", "celebrate", "sleepy", "calm", "wave"]
# open | snooze_1h | done | start_focus | answer:<x> (x: short ascii id the agent chose, e.g. answer:ok)
NOTIFICATION_ACTION_PATTERN = r"^(open|snooze_1h|done|start_focus|answer:[A-Za-z0-9_.-]{1,32})$"


class NotificationAction(BaseModel):
    id: str = Field(pattern=NOTIFICATION_ACTION_PATTERN)
    label: str = Field(min_length=1, max_length=40)  # Vietnamese button text


class NotifyPayload(BaseModel):
    """Payload of OutboxItem(notify_user). Older harnesses send only `text`; everything else is optional.

    `text` is the message (also the old WebSocket `text` field); `body` defaults to it. Title and body may be
    shown in the app only: push notifications on a lock screen use a generic per-kind text (the gateway decides).
    """

    text: str = Field(min_length=1, max_length=500)
    kind: NotificationKind = "nudge"
    title: str = Field(default="", max_length=80)
    body: str | None = Field(default=None, max_length=500)
    actions: list[NotificationAction] = Field(default_factory=list, max_length=3)
    mascot: MascotState | None = None  # state hint for the mascot; the gateway picks one per kind when unset
    prefill: str | None = Field(default=None, max_length=500)  # chat text the `open` action puts in the composer
    expires_at: datetime | None = None  # not delivered after this; the gateway sets a per-kind default when unset
    focus: dict[str, Any] | None = None  # focus_end: {card_id, task, minutes} of the session (start_focus repeats it)


class ApprovalRequest(BaseModel):
    approval_id: str
    action: str  # e.g. "calendar.create_event"
    summary: str  # Vietnamese, shown on the approval card
    details: dict[str, Any] = {}
    expires_at: datetime


class ApprovalDecision(BaseModel):
    approval_id: str
    decision: Literal["approve", "deny"]
    scope: Literal["once", "session"] = "once"


class SandboxEvent(BaseModel):
    """One server-sent event from POST /v1/turn."""

    type: Literal[
        "text_delta", "tool_started", "tool_finished", "approval_request", "suggestions", "card", "done", "error"
    ]
    text: str | None = None  # text_delta
    tool: str | None = None  # tool_started / tool_finished
    summary: str | None = None  # tool_*: one short line for the UI ("Đang đọc me/now.md")
    approval: ApprovalRequest | None = None
    items: list[dict[str, str]] | None = None  # suggestions: [{label, text}], at most 3, sent just before `done`
    card: dict[str, Any] | None = None  # card: {id, kind, created_at, ...} (a known id = update of that card)
    outbox: list[OutboxItem] = []  # done
    error: str | None = None


class JobKind(str, Enum):
    NIGHTLY_REFLECTION = "nightly_reflection"
    INTAKE = "intake"  # process new files in inbox/
    ROUTINE = "routine"  # generic routine from routines.yaml, uses JobRequest.prompt
    FOCUS_END = "focus_end"  # scheduled by start_focus; payload {card_id, task, minutes}


class JobRequest(BaseModel):
    job_id: str
    user_id: str
    profile: Profile
    kind: JobKind
    prompt: str | None = None
    payload: dict[str, Any] = {}  # notification-action jobs: {"source": "notification_action", "action", ...}
    scheduled_for: datetime | None = None


class JobResult(BaseModel):
    job_id: str
    status: Literal["ok", "error", "skipped"]
    summary: str  # Vietnamese, goes to activity.jsonl
    outbox: list[OutboxItem] = []
    usage: dict[str, int] = Field(default_factory=dict)  # tokens per model alias
    error: str | None = None
    cards: list[dict[str, Any]] = []  # chat cards the job wrote into today's transcript (gateway relays them live)
