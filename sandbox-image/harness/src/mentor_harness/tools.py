"""Harness tools (CONTRACTS.md section 3). Names and arguments are part of the contract."""

import base64
import hashlib
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from mentor_schemas import (
    JobKind,
    ModelAlias,
    OutboxItem,
    OutboxKind,
    Profile,
    SandboxEvent,
    WorkspacePaths,
    is_agent_writable,
)
from mentor_schemas.interaction import (
    FOCUS_MAX_MINUTES,
    FOCUS_MIN_MINUTES,
    JOB_CARD_KINDS,
    MAX_SUGGESTIONS,
    SUGGESTION_LABEL_CHARS,
    SUGGESTION_TEXT_CHARS,
)

from mentor_harness import cards, hooks
from mentor_harness.approvals import ApprovalBroker, Outcome
from mentor_harness.config import LOCAL_TZ, Settings, now_local
from mentor_harness.model import ModelClient, ModelError
from mentor_harness.scripts import ScriptError, ScriptRunner, script_allowed
from mentor_harness.workspace import PathError, Workspace

MAX_READ_CHARS = 60_000
DEFAULT_READ_LINES = 500
MAX_READ_BYTES = 5_000_000
MAX_WRITE_CHARS = 500_000
MAX_GREP_MATCHES = 200
MAX_GREP_CHARS = 30_000
MAX_GREP_FILE_BYTES = 2_000_000
MAX_LIST_ENTRIES = 500
MAX_IMAGE_BYTES = 10_000_000
MAX_TOOL_RESULT_CHARS = 60_000
MAX_PYTHON_OUTPUT = 20_000  # per stream
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

Emit = Callable[[SandboxEvent], Awaitable[None]]


class ToolError(Exception):
    """Raised by a tool handler; the message (Vietnamese) goes back to the model as an error."""


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    summary: str = ""  # one short Vietnamese line for the UI


@dataclass
class ToolContext:
    ws: Workspace
    profile: Profile
    model: ModelClient
    settings: Settings
    script_runner: ScriptRunner
    outbox: list[OutboxItem] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    session_id: str | None = None
    job_id: str | None = None
    emit: Emit | None = None  # set for turns only
    approvals: ApprovalBroker | None = None  # set for turns only
    conversation: list[dict[str, Any]] = field(default_factory=list)  # live messages
    # chat interaction layer (CONTRACTS section 9)
    chat_day: date | None = None  # day of the chat transcript cards go to (encoded in card ids)
    job_kind: JobKind | None = None
    cards: list[dict[str, Any]] = field(default_factory=list)  # cards shown (or updated) in this turn/job, in order
    held_cards: list[dict[str, Any]] = field(default_factory=list)  # celebrations: shown at turn end
    suggestions: list[dict[str, str]] | None = None  # quick replies, sent just before `done`
    job_tools: frozenset[str] = frozenset()  # turn-only tools allowed in this job (learner-started notification jobs)

    @property
    def is_turn(self) -> bool:
        return self.emit is not None and self.approvals is not None

    async def show_card(self, card: dict[str, Any]) -> None:
        """Emit a card (turns) and remember it for the transcript / JobResult."""
        self.cards.append(card)
        if self.emit:
            await self.emit(SandboxEvent(type="card", card=card))

    def add_usage(self, alias: ModelAlias, tokens: int) -> None:
        self.usage[alias.value] = self.usage.get(alias.value, 0) + tokens

    def log(self, action: str, summary: str, target: str | None = None) -> None:
        self.ws.log_activity(action, summary, target=target, session_id=self.session_id, job_id=self.job_id)


Handler = Callable[[ToolContext, dict[str, Any]], Awaitable[ToolResult | str]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    started: Callable[[dict[str, Any]], str]
    profiles: frozenset[Profile] = frozenset(Profile)
    silent: bool = False  # no UI events and no transcript line
    exposed: bool = True  # included in the tool list the model sees
    ui: bool = True  # tool_started/tool_finished events (off for tools whose result is itself UI: cards, chips)

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _str(desc: str) -> dict[str, Any]:
    return {"type": "string", "description": desc}


def _resolve(ctx: ToolContext, path: str) -> tuple[str, Path]:
    try:
        return ctx.ws.resolve(path)
    except PathError as exc:
        raise ToolError(str(exc)) from exc


def _require_str(args: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = args.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ToolError(f"Thiếu tham số '{key}' (chuỗi).")
    return value


def _writable(ctx: ToolContext, path: str) -> tuple[str, Path]:
    try:
        rel = ctx.ws.normalize(path)
    except PathError as exc:
        raise ToolError(str(exc)) from exc
    if not is_agent_writable(rel):
        raise ToolError(
            f"Không có quyền ghi {rel}. Mentor chỉ được ghi vào me/, goals/, learning/, inbox/ và routines.yaml."
        )
    rel, p = _resolve(ctx, rel)
    if p != ctx.ws.root and not is_agent_writable(ctx.ws.rel(p)):  # a symlink pointing somewhere read-only
        raise ToolError(f"Không có quyền ghi {rel} (liên kết tới vùng chỉ đọc).")
    return rel, p


# ---- file tools --------------------------------------------------------------------


async def read_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _resolve(ctx, _require_str(args, "path"))
    if not p.is_file():
        raise ToolError(f"Không tìm thấy file {rel}.")
    if p.stat().st_size > MAX_READ_BYTES:
        raise ToolError(f"{rel} quá lớn để đọc trực tiếp; dùng grep hoặc run_script pdf_extract.")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{rel} là file nhị phân; dùng look_at_image (ảnh) hoặc run_script pdf_extract (PDF).") from exc
    offset = max(int(args.get("offset") or 1), 1)
    limit = max(int(args.get("limit") or DEFAULT_READ_LINES), 1)
    lines = text.splitlines()
    chunk = lines[offset - 1 : offset - 1 + limit]
    body = "\n".join(chunk)
    end = offset - 1 + len(chunk)
    if len(body) > MAX_READ_CHARS:
        body = body[:MAX_READ_CHARS]
        end = offset - 1 + body.count("\n") + 1
        body += "\n[... đã cắt vì quá dài]"
    if end < len(lines):
        body += f"\n[... còn {len(lines) - end} dòng; đọc tiếp với offset={end + 1}]"
    return ToolResult(body or "(file trống)", summary=f"Đã đọc {rel}")


async def list_dir(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _resolve(ctx, args.get("path") or ".")
    if not p.is_dir():
        raise ToolError(f"Không tìm thấy thư mục {rel}.")
    entries = []
    for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name)):
        if child.name == ".git":
            continue
        entries.append(f"{child.name}/" if child.is_dir() else f"{child.name} ({child.stat().st_size} B)")
    more = len(entries) - MAX_LIST_ENTRIES
    text = "\n".join(entries[:MAX_LIST_ENTRIES]) or "(thư mục trống)"
    if more > 0:
        text += f"\n[... còn {more} mục]"
    return ToolResult(text, summary=f"Đã xem {rel}")


async def grep(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    pattern = _require_str(args, "pattern")
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"Regex không hợp lệ: {exc}") from exc
    rel, base = _resolve(ctx, args.get("path") or ".")
    files = [base] if base.is_file() else []
    if base.is_dir():
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            files.extend(Path(dirpath) / f for f in sorted(filenames))
    elif not base.is_file():
        raise ToolError(f"Không tìm thấy {rel}.")
    out: list[str] = []
    size = 0
    truncated = False
    for f in files:
        try:
            if f.stat().st_size > MAX_GREP_FILE_BYTES:
                continue
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        frel = ctx.ws.rel(f)
        for n, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                entry = f"{frel}:{n}: {line[:300]}"
                if len(out) >= MAX_GREP_MATCHES or size + len(entry) > MAX_GREP_CHARS:
                    truncated = True
                    break
                out.append(entry)
                size += len(entry) + 1
        if truncated:
            break
    text = "\n".join(out) or "(không có kết quả)"
    if truncated:
        text += "\n[... kết quả đã bị cắt; thu hẹp pattern hoặc path]"
    return ToolResult(text, summary=f"Tìm thấy {len(out)} dòng")


async def write_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _writable(ctx, _require_str(args, "path"))
    content = _require_str(args, "content", allow_empty=True)
    if len(content) > MAX_WRITE_CHARS:
        raise ToolError(f"Nội dung quá dài ({len(content)} ký tự, tối đa {MAX_WRITE_CHARS}).")
    if error := hooks.validate_write(rel, content):
        raise ToolError(f"Không ghi {rel}: {error}")
    if p.is_dir():
        raise ToolError(f"{rel} là thư mục.")
    created = not p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    ctx.log("write_file", hooks.write_summary(rel, created), target=rel)
    return ToolResult(f"Đã ghi {rel} ({len(content)} ký tự).", summary=f"Đã ghi {rel}")


MAX_EDITS_PER_CALL = 50


def _edit_pairs(args: dict[str, Any]) -> list[tuple[str, str]]:
    """(old, new) pairs: the single `old`/`new` form, or the `edits` list (applied in order)."""
    raw = args.get("edits")
    if raw is None:
        return [(_require_str(args, "old"), _require_str(args, "new", allow_empty=True))]
    if "old" in args or "new" in args:
        raise ToolError("Dùng hoặc 'old'/'new', hoặc 'edits', không dùng cả hai.")
    if not isinstance(raw, list) or not raw:
        raise ToolError("'edits' phải là danh sách không rỗng các {old, new}.")
    if len(raw) > MAX_EDITS_PER_CALL:
        raise ToolError(f"Tối đa {MAX_EDITS_PER_CALL} sửa đổi mỗi lần gọi.")
    pairs = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ToolError(f"edits[{i}] phải là object {{old, new}}.")
        try:
            pairs.append((_require_str(item, "old"), _require_str(item, "new", allow_empty=True)))
        except ToolError as exc:
            raise ToolError(f"edits[{i}]: {exc}") from exc
    return pairs


async def edit_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _writable(ctx, _require_str(args, "path"))
    pairs = _edit_pairs(args)
    if not p.is_file():
        raise ToolError(f"Không tìm thấy file {rel}.")
    text = p.read_text(encoding="utf-8")
    multi = len(pairs) > 1
    for i, (old, new) in enumerate(pairs, 1):
        # Each edit applies to the text left by the previous ones; any failure writes nothing.
        where = f"edits[{i}]: " if multi else ""
        undone = " Chưa ghi gì vào file." if multi else ""
        count = text.count(old)
        if count == 0:
            raise ToolError(f"{where}Không tìm thấy đoạn 'old' trong {rel}.{undone} Đọc lại file rồi thử lại.")
        if count > 1:
            raise ToolError(
                f"{where}Đoạn 'old' xuất hiện {count} lần trong {rel}; thêm ngữ cảnh để nó là duy nhất.{undone}"
            )
        text = text.replace(old, new, 1)
    if error := hooks.validate_write(rel, text):
        raise ToolError(f"Không sửa {rel}: {error}")
    p.write_text(text, encoding="utf-8", newline="\n")
    ctx.log("edit_file", hooks.edit_summary(rel), target=rel)
    done = f"Đã sửa {rel} ({len(pairs)} chỗ)." if multi else f"Đã sửa {rel}."
    return ToolResult(done, summary=f"Đã sửa {rel}")


async def delete_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _writable(ctx, _require_str(args, "path"))
    if not p.is_file():
        raise ToolError(f"Không tìm thấy file {rel}.")
    p.unlink()
    ctx.log("delete_file", hooks.delete_summary(rel), target=rel)
    return ToolResult(f"Đã xóa {rel}.", summary=f"Đã xóa {rel}")


async def move_file(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    src_rel, src = _writable(ctx, _require_str(args, "src"))
    dst_rel, dst = _writable(ctx, _require_str(args, "dst"))
    if not src.is_file():
        raise ToolError(f"Không tìm thấy file {src_rel}.")
    if dst.exists():
        raise ToolError(f"{dst_rel} đã tồn tại; chọn tên khác hoặc xóa file đó trước.")
    if dst_rel == WorkspacePaths.ROUTINES:
        try:
            text = src.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"Không chuyển {src_rel} thành {dst_rel}: file nhị phân.") from exc
        if error := hooks.validate_write(dst_rel, text):
            raise ToolError(f"Không chuyển tới {dst_rel}: {error}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)  # same filesystem; bytes untouched
    ctx.log("move_file", hooks.move_summary(src_rel, dst_rel), target=dst_rel)
    return ToolResult(f"Đã chuyển {src_rel} → {dst_rel}.", summary=f"Đã chuyển tới {dst_rel}")


# ---- scripts, code and models ---------------------------------------------------------


async def run_script(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    name = _require_str(args, "name")
    payload = args.get("input") or {}
    if not isinstance(payload, dict):
        raise ToolError("'input' phải là một JSON object.")
    if not script_allowed(name, ctx.profile):
        raise ToolError(f"Script không được phép: {name}.")
    try:
        result = await ctx.script_runner(name, payload, ctx.ws.root, ctx.settings.script_timeout_s)
    except ScriptError as exc:
        raise ToolError(f"Script {name} lỗi: {exc}") from exc
    # Passed through unchanged: scripts may add fields beyond CONTRACTS section 4.
    return ToolResult(json.dumps(result, ensure_ascii=False), summary=f"Đã chạy {name}")


def _cap(text: str) -> str:
    return text if len(text) <= MAX_PYTHON_OUTPUT else text[:MAX_PYTHON_OUTPUT] + "\n[... đã cắt]"


async def look_at_image(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    rel, p = _resolve(ctx, _require_str(args, "path"))
    question = _require_str(args, "question")
    mime = IMAGE_TYPES.get(p.suffix.lower())
    if mime is None:
        raise ToolError(f"{rel} không phải ảnh được hỗ trợ (png, jpg, webp, gif).")
    if not p.is_file():
        raise ToolError(f"Không tìm thấy file {rel}.")
    data = p.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        raise ToolError(f"Ảnh {rel} quá lớn ({len(data)} byte).")
    url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": url}}],
        }
    ]
    try:
        resp = await ctx.model.complete(ModelAlias.VISION, messages, max_tokens=ctx.settings.max_output_tokens)
    except ModelError as exc:
        raise ToolError(f"Chưa xem được ảnh lúc này (mentor-vision lỗi: {exc}). File vẫn nằm trong inbox.") from exc
    ctx.add_usage(ModelAlias.VISION, resp.total_tokens)
    return ToolResult(resp.content or "(model không trả lời)", summary=f"Đã xem ảnh {rel}")


# ---- outbox tools ------------------------------------------------------------------------


def _dedupe(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


async def notify_user(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Rich notification ("nudge", CONTRACTS section 9). Only `text` is required; the payload is NotifyPayload."""
    from mentor_schemas import NotifyPayload
    from pydantic import ValidationError

    text = _require_str(args, "text").strip()
    if len(text) > 500:
        raise ToolError("Thông báo quá dài (tối đa 500 ký tự).")
    raw: dict[str, Any] = {"text": text}
    for key in ("kind", "title", "actions", "mascot", "prefill"):
        if args.get(key) not in (None, "", []):
            raw[key] = args[key].strip() if isinstance(args[key], str) else args[key]
    try:
        payload = NotifyPayload.model_validate(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(p) for p in err.get("loc", ())) or "?"
        raise ToolError(
            f"Thông báo không hợp lệ ở '{where}': {err.get('msg')}. actions tối đa 3, id là open, snooze_1h, done, "
            "start_focus hoặc answer:<id ngắn>; label tối đa 40 ký tự; title tối đa 80 ký tự."
        ) from exc
    if len({a.id for a in payload.actions}) != len(payload.actions):
        raise ToolError("Các actions phải có id khác nhau.")
    day = now_local().date().isoformat()
    ctx.outbox.append(
        OutboxItem(kind=OutboxKind.NOTIFY_USER, payload=payload.model_dump(mode="json", exclude_defaults=True),
                   dedupe_key=f"notify:{_dedupe(day, payload.kind, payload.title, text)}")
    )
    ctx.log("notify_user", f"Mentor đã gửi thông báo: {(payload.title + ': ' if payload.title else '') + text[:150]}")
    return ToolResult("Đã xếp thông báo để gửi cho người học.", summary="Đã tạo thông báo")


async def schedule_wake(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    raw_at = _require_str(args, "at")
    try:
        at = datetime.fromisoformat(raw_at)
    except ValueError as exc:
        raise ToolError(f"'at' phải là thời điểm ISO 8601, ví dụ 2026-10-29T07:30:00+07:00 (nhận: {raw_at}).") from exc
    if at.tzinfo is None:
        at = at.replace(tzinfo=LOCAL_TZ)
    if at < now_local():
        raise ToolError("'at' đã ở trong quá khứ.")
    try:
        kind = JobKind(_require_str(args, "job_kind"))
    except ValueError as exc:
        raise ToolError(f"job_kind phải là một trong: {', '.join(k.value for k in WAKE_JOB_KINDS)}.") from exc
    if kind not in WAKE_JOB_KINDS:
        raise ToolError("focus_end chỉ do start_focus hẹn; muốn bắt đầu phiên tập trung thì gọi start_focus.")
    payload: dict[str, Any] = {"at": at.isoformat(), "job_kind": kind.value}
    if isinstance(args.get("prompt"), str) and args["prompt"].strip():
        payload["prompt"] = args["prompt"].strip()
    ctx.outbox.append(
        OutboxItem(kind=OutboxKind.NEXT_WAKE, payload=payload, dedupe_key=f"wake:{_dedupe(payload['at'], kind.value)}")
    )
    local = at.astimezone(LOCAL_TZ)
    ctx.log("schedule_wake", f"Mentor đã hẹn chạy {kind.value} lúc {local:%H:%M %d/%m/%Y}.")
    return ToolResult(f"Đã hẹn {kind.value} lúc {local.isoformat()}.", summary="Đã hẹn lịch")


async def _ask_approval(ctx: ToolContext, action: str, summary: str, details: dict[str, Any]) -> Outcome:
    """Show an approval card in the chat and wait for the learner (turns only). Honors scope=session grants."""
    assert ctx.approvals is not None and ctx.emit is not None and ctx.session_id is not None
    if ctx.approvals.is_granted(ctx.session_id, action):
        return "approve"
    timeout = ctx.settings.approval_timeout_s
    req = ctx.approvals.create(ctx.session_id, action, summary, details, timeout)
    await ctx.emit(SandboxEvent(type="approval_request", approval=req, summary=summary))
    return await ctx.approvals.wait(req.approval_id, timeout)


async def request_approval(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not ctx.is_turn or ctx.session_id is None:
        raise ToolError("request_approval chỉ dùng được trong cuộc trò chuyện, không dùng trong job nền.")
    action = _require_str(args, "action")
    summary = _require_str(args, "summary")
    details = args.get("details") or {}
    if not isinstance(details, dict):
        raise ToolError("'details' phải là một JSON object.")
    assert ctx.approvals is not None
    if ctx.approvals.is_granted(ctx.session_id, action):
        return ToolResult("approve: người học đã cho phép hành động này trong phiên.", summary="Đã được cho phép")
    outcome = await _ask_approval(ctx, action, summary, details)
    text = {
        "approve": "approve: người học đã đồng ý.",
        "deny": "deny: người học từ chối. Không thực hiện hành động này.",
        "timeout": "timeout: người học chưa trả lời. Không thực hiện hành động này.",
    }[outcome]
    label = {"approve": "Đã được duyệt", "deny": "Bị từ chối", "timeout": "Hết thời gian chờ duyệt"}[outcome]
    return ToolResult(text, summary=label)


# ---- chat interaction layer (CONTRACTS section 9) ----------------------------------------------

WAKE_JOB_KINDS = tuple(k for k in JobKind if k != JobKind.FOCUS_END)  # focus_end is scheduled by start_focus only
TOO_MANY_CARDS = f"Mỗi lượt tối đa {cards.MAX_CARDS_PER_RUN} thẻ."
FOCUS_TASK_CHARS = 120
FOCUS_TOTAL_MAX_MINUTES = 180  # a session extended again and again
FOCUS_END_ACTIONS = [
    {"id": "done", "label": "Xong rồi"},
    {"id": "start_focus", "label": "Thêm một phiên"},
    {"id": "snooze_1h", "label": "Nhắc sau 1 giờ"},
]
# A job the learner started by tapping a notification button (gateway marks payload.source): like a turn for these.
NOTIFICATION_ACTION_SOURCE = "notification_action"
LEARNER_JOB_TOOLS = frozenset({"start_focus", "celebrate"})


def learner_job_tools(kind: JobKind, payload: dict[str, Any]) -> frozenset[str]:
    """Turn-only tools a background job may use: only a routine job started by a notification action."""
    if kind == JobKind.ROUTINE and payload.get("source") == NOTIFICATION_ACTION_SOURCE:
        return LEARNER_JOB_TOOLS
    return frozenset()


def _turn_only(ctx: ToolContext, name: str) -> None:
    if not ctx.is_turn and name not in ctx.job_tools:
        raise ToolError(f"{name} chỉ dùng trong cuộc trò chuyện với người học, không dùng trong job nền.")


def _card_slots(ctx: ToolContext) -> None:
    if len(ctx.cards) + len(ctx.held_cards) >= cards.MAX_CARDS_PER_RUN:
        raise ToolError(TOO_MANY_CARDS)


def _chat_day(ctx: ToolContext) -> date:
    return ctx.chat_day or now_local().date()


async def suggest_replies(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _turn_only(ctx, "suggest_replies")
    items = args.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SUGGESTIONS:
        raise ToolError(f"'items' phải là danh sách 1–{MAX_SUGGESTIONS} mục {{label, text}}.")
    out: list[dict[str, str]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ToolError(f"items[{i}] phải là object {{label, text}}.")
        label = item.get("label")
        text = item.get("text") if item.get("text") not in (None, "") else label
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > SUGGESTION_LABEL_CHARS:
            raise ToolError(f"items[{i}].label phải có 1–{SUGGESTION_LABEL_CHARS} ký tự.")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > SUGGESTION_TEXT_CHARS:
            raise ToolError(f"items[{i}].text phải có 1–{SUGGESTION_TEXT_CHARS} ký tự.")
        label, text = " ".join(label.split()), text.strip()
        if any(o["label"] == label for o in out):
            raise ToolError(f"Hai gợi ý trùng nhãn: {label}.")
        out.append({"label": label, "text": text})
    ctx.suggestions = out  # the last call of the turn wins
    return ToolResult(
        f"Sẽ hiện {len(out)} nút trả lời nhanh dưới câu trả lời. Không cần liệt kê lại chúng trong câu trả lời.",
        summary="Đã gợi ý trả lời nhanh",
    )


async def _add_card(ctx: ToolContext, kind: str, data: Any) -> dict[str, Any]:
    if not ctx.is_turn and kind not in JOB_CARD_KINDS and not (ctx.job_tools and kind != "focus"):
        raise ToolError(f"Trong job nền chỉ tạo được thẻ {', '.join(sorted(JOB_CARD_KINDS))}.")
    if kind == "celebration" and any(c.get("kind") == "celebration" for c in ctx.held_cards):
        raise ToolError("Mỗi lượt chỉ chúc mừng một lần.")
    _card_slots(ctx)
    try:
        fields = cards.validate(kind, data, ctx.ws)
    except cards.CardError as exc:
        raise ToolError(str(exc)) from exc
    now = now_local()
    if kind == "weekly":
        fields = cards.fill_weekly(ctx.ws, fields, now.date())
    card = cards.make_card(kind, fields, now, _chat_day(ctx))
    if kind == "celebration":
        ctx.held_cards.append(card)  # shown at the end of the turn
    else:
        await ctx.show_card(card)
    return card


async def show_card(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    kind = _require_str(args, "kind").strip()
    card = await _add_card(ctx, kind, args.get("data"))
    where = "trong khung chat" if ctx.is_turn else "trong khung chat khi người học mở lại"
    extra = ""
    if kind == "flashcard":
        extra = " Chờ người học chọn; câu trả lời đến dưới dạng [card:flashcard answer <chữ cái>]. Đừng nói đáp án."
    elif kind == "checkin":
        extra = " Câu trả lời đến dưới dạng [card:checkin answer <lựa chọn>]."
    elif kind in ("practice", "mock"):
        extra = " Thẻ chỉ mở màn hình luyện tập khi người học bấm; không tự bắt đầu, không nói trước kết quả."
    return ToolResult(f"Thẻ {kind} (id {card['id']}) sẽ hiện {where}.{extra}", summary=f"Đã tạo thẻ {kind}")


async def celebrate(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _turn_only(ctx, "celebrate")
    data = {"title": args.get("title"), "detail": args.get("detail")}
    await _add_card(ctx, "celebration", {k: v for k, v in data.items() if v is not None})
    return ToolResult("Thẻ chúc mừng sẽ hiện cuối câu trả lời. Khen cụ thể nỗ lực, ngắn gọn.", summary="Chúc mừng")


def schedule_focus_end(ctx: ToolContext, card: dict[str, Any]) -> None:
    """next_wake for the focus_end job; the gateway keeps card_id/task/minutes as the job payload."""
    payload = {"at": card["ends_at"], "job_kind": JobKind.FOCUS_END.value, "card_id": card["id"],
               "task": card["task"], "minutes": card["minutes"]}
    ctx.outbox.append(OutboxItem(kind=OutboxKind.NEXT_WAKE, payload=payload,
                                 dedupe_key=f"focus:{card['id']}:{card['ends_at']}"))


async def start_focus(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _turn_only(ctx, "start_focus")
    task = " ".join(_require_str(args, "task").split())
    if len(task) > FOCUS_TASK_CHARS:
        raise ToolError(f"'task' dài quá {FOCUS_TASK_CHARS} ký tự.")
    minutes = args.get("minutes")
    if isinstance(minutes, float) and minutes.is_integer():
        minutes = int(minutes)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not FOCUS_MIN_MINUTES <= minutes <= FOCUS_MAX_MINUTES:
        raise ToolError(f"'minutes' phải là số nguyên {FOCUS_MIN_MINUTES}..{FOCUS_MAX_MINUTES}.")
    if any(c.get("kind") == "focus" for c in ctx.cards):
        raise ToolError("Lượt này đã có một phiên tập trung.")
    _card_slots(ctx)
    now = now_local().replace(microsecond=0)
    ends = now + timedelta(minutes=minutes)
    card = cards.make_card("focus", {"task": task, "minutes": minutes, "ends_at": ends.isoformat()}, now,
                           _chat_day(ctx))
    await ctx.show_card(card)
    schedule_focus_end(ctx, card)
    ctx.log("start_focus", f"Bắt đầu tập trung {minutes} phút: {task}", target=card["id"])
    return ToolResult(
        f"Đã bắt đầu phiên tập trung {minutes} phút (đến {ends:%H:%M}); thẻ đếm giờ đang hiện. Hết giờ mentor sẽ hỏi "
        "thăm qua thông báo. Trả lời thật ngắn để người học bắt tay vào việc ngay.",
        summary=f"Bắt đầu tập trung {minutes} phút",
    )


def _when_iso(raw: Any, default: datetime) -> datetime:
    try:
        value = datetime.fromisoformat(str(raw))
    except ValueError:
        return default
    return value if value.tzinfo else value.replace(tzinfo=LOCAL_TZ)


async def _focus_action(ctx: ToolContext, card: dict[str, Any], action: str, value: str | None) -> str:
    """focus done / extend, applied by the harness itself (not left to the model)."""
    now = now_local().replace(microsecond=0)
    start = _when_iso(card.get("created_at"), now)
    ends = _when_iso(card.get("ends_at"), now)
    task = str(card.get("task") or "")
    if action == "done":
        if card.get("ended_at"):
            return "Phiên này đã kết thúc từ trước; không cần làm gì thêm."
        await ctx.show_card({**card, "ended_at": now.isoformat()})
        spent = cards.focus_minutes_between(start, min(now, ends))
        ctx.log("focus_done", f"Xong phiên tập trung sau {spent} phút: {task}", target=card.get("id"))
        return (f"Hệ thống đã kết thúc phiên tập trung (khoảng {spent} phút). Khen cụ thể nỗ lực, hỏi ngắn một câu "
                "về kết quả.")
    try:
        extra = int(value or 0) or 10
    except ValueError:
        extra = 10
    extra = max(FOCUS_MIN_MINUTES, min(extra, 60))
    new_ends = max(ends, now) + timedelta(minutes=extra)
    total = cards.focus_minutes_between(start, new_ends)
    if total > FOCUS_TOTAL_MAX_MINUTES:
        return (f"Không gia hạn: phiên đã gần {FOCUS_TOTAL_MAX_MINUTES // 60} giờ. Gợi ý nghỉ 5–10 phút rồi bắt đầu "
                "phiên mới (start_focus) nếu người học muốn.")
    updated = {k: v for k, v in card.items() if k != "ended_at"} | {"minutes": total, "ends_at": new_ends.isoformat()}
    await ctx.show_card(updated)
    schedule_focus_end(ctx, updated)
    ctx.log("focus_extend", f"Thêm {extra} phút tập trung: {task}", target=card.get("id"))
    return f"Hệ thống đã gia hạn phiên thêm {extra} phút, đến {new_ends:%H:%M}. Trả lời thật ngắn."


async def card_action_note(ctx: ToolContext, card_id: str, kind: str, action: str, value: str | None,
                           also: list[str] | None = None) -> str:
    """What the model is told about a card click (after the `[card:...]` line); applies focus done/extend."""
    card, home = cards.find_card(ctx.ws, card_id, also)
    lines = [f"(Người học bấm trên thẻ {kind} trong khung chat, không gõ chữ.)"]
    if card is None:
        lines.append("Không tìm thấy nội dung thẻ trong lịch sử chat; hỏi lại người học nếu cần.")
        return "\n".join(lines)
    lines.append(f"Thẻ: {cards.describe(card)}.")
    if kind == "flashcard" and action == "answer":
        lines.append(
            "Chấm câu trả lời này như khi người học trả lời bằng chữ (skill spaced-review: không gợi ý thì mode "
            f"independent), ghi run_script record_event với source_ref {home}, rồi bkt_update."
        )
    elif kind == "flashcard":
        lines.append("Người học bỏ qua thẻ: không ghi record_event, không nói đáp án trừ khi được hỏi.")
    elif kind == "focus":
        lines.append(await _focus_action(ctx, card, action, value))
    elif kind == "deadline" and action == "start_focus":
        lines.append(f"Người học muốn bắt đầu làm việc này ngay: gọi start_focus (task theo tên deadline, minutes "
                     f"{value or 25}).")
    elif kind == "deadline":
        lines.append("Người học báo đã xong việc này: cập nhật file mục tiêu/deadline tương ứng nếu có.")
    return "\n".join(lines)


def finish_focus_end_job(ctx: ToolContext, card: dict[str, Any]) -> None:
    """A focus_end job always ends with one focus_end notification (actions done / start_focus / snooze_1h)."""
    focus = {"card_id": card.get("id"), "task": card.get("task"), "minutes": card.get("minutes")}
    nudges = [o for o in ctx.outbox if o.kind == OutboxKind.NOTIFY_USER]
    if not nudges:
        text = f"Hết {card.get('minutes')} phút tập trung cho “{card.get('task')}”. Xong chưa, hay cần thêm chút thời gian?"
        nudges.append(OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": text},
                                 dedupe_key=f"focus_end:{card.get('id')}:{card.get('ends_at')}"))
        ctx.outbox.append(nudges[-1])
        ctx.log("notify_user", f"Mentor đã gửi thông báo: Hết giờ tập trung: {text[:150]}")
    for item in nudges[:1]:
        item.payload.update(kind="focus_end", actions=FOCUS_END_ACTIONS, focus=focus)
        item.payload["title"] = item.payload.get("title") or "Hết giờ tập trung"
    for item in nudges[1:]:
        ctx.outbox.remove(item)  # one check-in per session


# ---- registry ------------------------------------------------------------------------------

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "read_file",
            "Read a UTF-8 text file in the workspace. Lines are 1-based; use offset/limit for long files.",
            _obj(
                {
                    "path": _str("Workspace-relative path, e.g. me/now.md"),
                    "offset": {"type": "integer", "description": "First line to read (1-based)", "minimum": 1},
                    "limit": {"type": "integer", "description": "Max number of lines", "minimum": 1},
                },
                ["path"],
            ),
            read_file,
            lambda a: f"Đang đọc {a.get('path', '')}",
        ),
        Tool(
            "list_dir",
            "List files and folders in a workspace directory.",
            _obj({"path": _str("Workspace-relative directory, '.' for the root")}, ["path"]),
            list_dir,
            lambda a: f"Đang xem thư mục {a.get('path') or '.'}",
        ),
        Tool(
            "grep",
            "Search workspace text files with a Python regex. Returns 'path:line: text', capped.",
            _obj(
                {"pattern": _str("Regular expression"), "path": _str("File or directory to search, default '.'")},
                ["pattern"],
            ),
            grep,
            lambda a: f"Đang tìm '{a.get('pattern', '')}'",
        ),
        Tool(
            "write_file",
            "Create or overwrite a file. Allowed only in me/, goals/, learning/, inbox/ and "
            "routines.yaml.",
            _obj(
                {"path": _str("Workspace-relative path"), "content": _str("Full new file content")},
                ["path", "content"],
            ),
            write_file,
            lambda a: f"Đang ghi {a.get('path', '')}",
        ),
        Tool(
            "edit_file",
            "Replace exact, unique text in a writable file. Either one change with 'old'/'new', or several "
            "changes to the same file in ONE call with 'edits' (applied in order; all or nothing). Files shown "
            "in the system prompt (core memory) are current: copy 'old' from there without read_file.",
            _obj(
                {
                    "path": _str("Workspace-relative path"),
                    "old": _str("Exact existing text (must be unique). Omit when using 'edits'"),
                    "new": _str("Replacement text. Omit when using 'edits'"),
                    "edits": {
                        "type": "array",
                        "description": "Several changes to this file, applied in order",
                        "items": _obj(
                            {
                                "old": _str("Exact existing text (unique at that point)"),
                                "new": _str("Replacement text"),
                            },
                            ["old", "new"],
                        ),
                        "minItems": 1,
                    },
                },
                ["path"],
            ),
            edit_file,
            lambda a: f"Đang sửa {a.get('path', '')}",
        ),
        Tool(
            "delete_file",
            "Delete a writable file (used to forget things on request and to clear processed inbox files).",
            _obj({"path": _str("Workspace-relative path")}, ["path"]),
            delete_file,
            lambda a: f"Đang xóa {a.get('path', '')}",
        ),
        Tool(
            "move_file",
            "Move or rename a file (binary-safe). Both paths must be writable, "
            "e.g. inbox/x.jpg -> learning/evidence/scans/x.jpg.",
            _obj(
                {"src": _str("Current workspace-relative path"), "dst": _str("New workspace-relative path")},
                ["src", "dst"],
            ),
            move_file,
            lambda a: f"Đang chuyển {a.get('src', '')} tới {a.get('dst', '')}",
        ),
        Tool(
            "run_script",
            "Run a platform script with a JSON input object. Names: record_event, "
            "bkt_update, sympy_check ({kind, problem, answer} or {checks: [up to 10 of those]} to check several in one call), pdf_extract ({path, start_page?, end_page?, max_chars?}), pdf_render ({path, "
            "pages?: up to 5 page numbers}: PNG images of PDF pages next to the file, for look_at_image).",
            _obj(
                {"name": _str("Script name"), "input": {"type": "object", "description": "Script input"}},
                ["name", "input"],
            ),
            run_script,
            lambda a: f"Đang chạy {a.get('name', '')}",
        ),
        Tool(
            "look_at_image",
            "Ask the vision model a question about an image file in the workspace.",
            _obj(
                {"path": _str("Workspace-relative image path"), "question": _str("What to look for")},
                ["path", "question"],
            ),
            look_at_image,
            lambda a: f"Đang xem ảnh {a.get('path', '')}",
        ),
        Tool(
            "notify_user",
            "Queue a notification (nudge) for the learner. The control plane applies proactivity, quiet hours and "
            "the daily cap. Optional: kind, a short title, up to 3 action buttons, a mascot state and chat text "
            "for 'open'. Lock-screen pushes show a generic text, never yours.",
            _obj(
                {
                    "text": _str("Vietnamese message, max 500 chars"),
                    "kind": {"type": "string", "enum": ["checkin", "deadline", "review", "focus_end", "celebration",
                                                        "nudge"]},
                    "title": _str("Short Vietnamese title, max 80 chars"),
                    "actions": {
                        "type": "array",
                        "maxItems": 3,
                        "description": "Buttons: id open | snooze_1h | done | start_focus | answer:<short ascii id>",
                        "items": _obj({"id": _str("Action id"), "label": _str("Vietnamese label, max 40 chars")},
                                      ["id", "label"]),
                    },
                    "mascot": {"type": "string", "enum": ["idle", "happy", "celebrate", "calm", "wave", "sleepy"]},
                    "prefill": _str("Chat text put in the composer when the learner taps 'open'"),
                },
                ["text"],
            ),
            notify_user,
            lambda a: "Đang tạo thông báo",
        ),
        Tool(
            "schedule_wake",
            "Ask the control plane to wake the mentor for a background job at a given time.",
            _obj(
                {
                    "at": _str("ISO 8601 datetime, e.g. 2026-10-29T07:30:00+07:00"),
                    "job_kind": {"type": "string", "enum": [k.value for k in WAKE_JOB_KINDS]},
                    "prompt": _str("Optional extra instruction for the job"),
                },
                ["at", "job_kind"],
            ),
            schedule_wake,
            lambda a: "Đang hẹn lịch",
        ),
        Tool(
            "request_approval",
            "Ask the learner to approve an external action that has no tool of its own. Waits for the answer.",
            _obj(
                {
                    "action": _str("Action id, e.g. zotero.add_item"),
                    "summary": _str("Vietnamese one-line summary shown on the approval card"),
                    "details": {"type": "object", "description": "Structured details"},
                },
                ["action", "summary", "details"],
            ),
            request_approval,
            lambda a: "Đang chờ bạn duyệt",
        ),
        Tool(
            "suggest_replies",
            "Show up to 3 quick-reply buttons under your answer (clicking sends `text` as the learner's message). Use "
            "only after a question with 2-3 natural short answers, not every turn. The last call of a turn wins.",
            _obj(
                {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_SUGGESTIONS,
                        "items": _obj(
                            {
                                "label": _str(f"Button text, max {SUGGESTION_LABEL_CHARS} chars"),
                                "text": _str("Message sent when clicked (default: label)"),
                            },
                            ["label"],
                        ),
                    }
                },
                ["items"],
            ),
            suggest_replies,
            lambda a: "",
            ui=False,
        ),
        Tool(
            "show_card",
            "Show an interactive card in the chat. kind/data: flashcard {skill (an id from learning/<subject>/"
            "review-queue.md), front, choices? (3-4 strings), reveal? (correct answer + short reason, shown after "
            "answering)}; deadline {title, due_at (ISO datetime), source?}; checkin {prompt, options (2-4 short "
            "strings)}; weekly {milestones_done, mistakes_fixed, highlight?, focus_minutes?, streak_days?} (missing "
            "numbers are computed); celebration {title, detail?} (prefer celebrate); practice {subject (math|physics|"
            "english), minutes (10|20|30|45), goal? (balanced|weak|challenge, default balanced), topics? (topic ids), "
            "title, reason (why now, from practice-log.md/skills.md)} and mock {subject, profile_id (e.g. "
            "math.mcq-mock.2026), title}: a suggestion with one button that opens the practice setup / mock confirm "
            "screen; nothing starts until the learner clicks. Focus cards: use start_focus. "
            "Background jobs may show weekly, checkin and deadline cards (shown when the learner next opens the chat). "
            f"Max {cards.MAX_CARDS_PER_RUN} cards per turn.",
            _obj(
                {
                    "kind": {"type": "string",
                             "enum": ["flashcard", "deadline", "checkin", "weekly", "celebration", "practice",
                                      "mock"]},
                    "data": {"type": "object", "description": "Fields for the kind, see the tool description"},
                },
                ["kind", "data"],
            ),
            show_card,
            lambda a: "",
            ui=False,
        ),
        Tool(
            "start_focus",
            "Start a focus session: shows a countdown card and schedules a check-in notification when it ends. Use "
            "when the learner asks for it or is about to start a concrete piece of work and agrees.",
            _obj(
                {
                    "task": _str(f"What the learner will work on, max {FOCUS_TASK_CHARS} chars"),
                    "minutes": {"type": "integer", "minimum": FOCUS_MIN_MINUTES, "maximum": FOCUS_MAX_MINUTES},
                },
                ["task", "minutes"],
            ),
            start_focus,
            lambda a: "",
            ui=False,
        ),
        Tool(
            "celebrate",
            "Show a celebration card for a real milestone (finished goal, mastered skill, submitted paper). At most "
            "once per turn.",
            _obj({"title": _str("Short Vietnamese title, max 80 chars"), "detail": _str("Optional, max 200 chars")},
                 ["title"]),
            celebrate,
            lambda a: "",
            ui=False,
        ),
    ]
}

TURN_ONLY_TOOLS = frozenset(
    {"request_approval", "suggest_replies", "start_focus", "celebrate"}
)  # need a learner in the chat to approve or see them


# Read-only tools without approval cards: when the model asks for several in one response, the loop runs
# consecutive ones concurrently. Everything else (writes, scripts, approvals) runs one by one, in order.
CONCURRENT_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "grep",
        "look_at_image",
    }
)


def tool_specs(profile: Profile, *, is_turn: bool, job_tools: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Tool definitions the model sees for this profile (`job_tools`: turn-only tools this job may use)."""
    return [
        t.spec()
        for t in TOOLS.values()
        if t.exposed and profile in t.profiles and (is_turn or t.name not in TURN_ONLY_TOOLS or t.name in job_tools)
    ]


async def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolResult:
    """Run one tool call; every failure becomes an error ToolResult for the model."""
    tool = TOOLS.get(name)
    if tool is None or ctx.profile not in tool.profiles:
        return ToolResult(f"LỖI: Không có công cụ '{name}'.", is_error=True, summary="Công cụ không tồn tại")
    try:
        result = await tool.handler(ctx, args)
    except ToolError as exc:
        return ToolResult(f"LỖI: {exc}", is_error=True, summary=f"Lỗi: {str(exc)[:80]}")
    except (OSError, ValueError, TypeError) as exc:
        return ToolResult(f"LỖI: {exc.__class__.__name__}: {exc}", is_error=True, summary="Lỗi khi chạy công cụ")
    if isinstance(result, str):
        result = ToolResult(result)
    if result.is_error and not result.content.startswith("LỖI"):
        result.content = f"LỖI: {result.content}"
    if len(result.content) > MAX_TOOL_RESULT_CHARS:
        result.content = result.content[:MAX_TOOL_RESULT_CHARS] + "\n[... đã cắt]"
    return result
