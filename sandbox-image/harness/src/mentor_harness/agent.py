"""The agent loop: model -> tool calls -> tool results -> model, for chat turns and background jobs."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from mentor_schemas import JobKind, JobRequest, JobResult, ModelAlias, Profile, SandboxEvent, TurnRequest
from mentor_schemas.interaction import card_action_text, chat_path

from mentor_harness import cards, jobs
from mentor_harness.approvals import ApprovalBroker
from mentor_harness.config import Settings, now_local
from mentor_harness.context import build_context
from mentor_harness.model import ModelClient, ModelError, ToolCall
from mentor_harness.scripts import ScriptRunner, run_mentor_script
from mentor_harness.tools import (
    CONCURRENT_TOOLS,
    TOOLS,
    Emit,
    Tool,
    ToolContext,
    card_action_note,
    execute,
    finish_focus_end_job,
    learner_job_tools,
    tool_specs,
)
from mentor_harness.workspace import Workspace

log = logging.getLogger("mentor_harness")

CHAT_ALIAS = ModelAlias.CHAT  # one alias for the whole session (prefix cache, consistent voice)
JOB_TIMEOUT_S = 570.0  # JobResult must come back within 10 minutes
FORCE_FINAL_NOTE = "[HARNESS] Đã dùng hết số bước công cụ cho lượt này. Hãy trả lời ngay, không gọi thêm công cụ."
TOKEN_CAP_NOTE = "(Mình tạm dừng ở đây vì lượt này đã quá dài. Bạn nhắn tiếp để mình làm nốt nhé.)"
MODEL_DOWN_NOTE = "Mentor tạm thời không kết nối được với mô hình. Bạn thử lại sau ít phút nhé."
CHAT_RELOAD_MESSAGES = 40  # visible messages restored from sessions/*/<session_id>.jsonl after a restart
ATTACHMENT_NOTE = "[Tệp đính kèm, đã lưu trong workspace; ảnh thì dùng look_at_image]"


def _user_content(text: str, attachments: list[tuple[str, str | None]]) -> str:
    """The user message the model sees: the learner's text plus a list of attached workspace files."""
    if not attachments:
        return text
    files = "\n".join(f"- {path} ({mime})" if mime else f"- {path}" for path, mime in attachments)
    return f"{text}\n\n{ATTACHMENT_NOTE}\n{files}"


def _history_from_chat(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Model messages rebuilt from saved chat records; starts at a user message.

    Cards become a short assistant note; a card click comes back as its `[card:...]` text; consecutive messages of
    one role (text split around a card) are joined.
    """
    history: list[dict[str, Any]] = []

    def add(role: str, content: str) -> None:
        if history and history[-1]["role"] == role:
            history[-1]["content"] += "\n\n" + content
        else:
            history.append({"role": role, "content": content})

    for record in records:
        role = record.get("role")
        if role == "card" and isinstance(record.get("card"), dict):
            add("assistant", f"[đã hiện thẻ {cards.describe(record['card'])}]")
            continue
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if role == "user":
            action = record.get("card_action")
            if isinstance(action, dict):
                text = card_action_text(str(action.get("kind")), str(action.get("action")), action.get("value"))
            paths = [p for p in record.get("attachments") or [] if isinstance(p, str)]
            add("user", _user_content(text, [(p, None) for p in paths]))
        elif role == "mentor":
            add("assistant", text)
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


@dataclass
class SessionState:
    history: list[dict[str, Any]] = field(default_factory=list)  # messages after the system prompt
    crisis: bool = False  # flag_crisis ran or the safety skill was read in this session: no celebrations


@dataclass
class LoopOutcome:
    final_text: str = ""
    hit_token_cap: bool = False


def _strip_reasoning(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop reasoning_content once a turn is over (only needed between tool rounds of one turn)."""
    return [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]


def _trim_history(history: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    """Keep the newest messages, cutting only at a user message so tool calls stay paired."""
    if len(history) <= max_messages:
        return history
    start = len(history) - max_messages
    for i in range(start, len(history)):
        if history[i].get("role") == "user":
            return history[i:]
    return []


def _summarize_args(args: dict[str, Any]) -> str:
    keep = {k: v for k, v in args.items() if k not in ("content", "new", "old", "edits", "input")}
    if isinstance(args.get("edits"), list):
        keep["edits"] = len(args["edits"])  # how many changes, not their text
    return json.dumps(keep, ensure_ascii=False)[:200]


def _batches(calls: list[ToolCall]) -> list[list[ToolCall]]:
    """Group the calls of one model response: consecutive read-only calls run together, others alone, in order."""
    out: list[list[ToolCall]] = []
    for call in calls:
        if call.name in CONCURRENT_TOOLS and out and out[-1][0].name in CONCURRENT_TOOLS:
            out[-1].append(call)
        else:
            out.append([call])
    return out


class Harness:
    def __init__(
        self,
        settings: Settings,
        model: ModelClient,
        *,
        script_runner: ScriptRunner = run_mentor_script,
        approvals: ApprovalBroker | None = None,
    ) -> None:
        self.settings = settings
        self.model = model
        self.ws = Workspace(settings.workspace_root)
        self.script_runner = script_runner
        self.approvals = approvals or ApprovalBroker()
        self.sessions: dict[str, SessionState] = {}
        self.lock = asyncio.Lock()  # one turn or job touches the workspace at a time
        self._tasks: set[asyncio.Task[None]] = set()  # strong refs so detached turns are not GC'd

    def profile_for(self, requested: Profile) -> Profile:
        """The sandbox's own profile (env) wins over the request."""
        return self.settings.profile or requested

    # ---- shared loop ------------------------------------------------------------------

    async def _loop(
        self,
        ctx: ToolContext,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        *,
        token_cap: int,
        transcript: list[str],
    ) -> LoopOutcome:
        specs = tool_specs(ctx.profile, is_turn=ctx.is_turn, job_tools=ctx.job_tools)
        rounds = 0
        tokens = 0
        said_text = False  # some text of this turn has reached the learner
        reply_open = False  # the current model reply has started streaming

        async def say(text: str) -> None:
            """Emit a text_delta; separate model replies of one turn by a blank line (as the chat log does)."""
            nonlocal said_text, reply_open
            if not reply_open:
                reply_open = True
                if said_text:
                    text = "\n\n" + text
            said_text = True
            if ctx.emit:
                await ctx.emit(SandboxEvent(type="text_delta", text=text))

        while True:
            force_final = rounds >= self.settings.max_tool_rounds
            if force_final:
                messages.append({"role": "user", "content": FORCE_FINAL_NOTE})
            reply_open = False
            resp = await self.model.complete(
                alias,
                messages,
                specs,
                tool_choice="none" if force_final else None,
                max_tokens=self.settings.max_output_tokens,
                on_delta=say if ctx.emit else None,  # token-level text_delta events during turns
            )
            tokens += resp.total_tokens
            ctx.add_usage(alias, resp.total_tokens)
            calls = [] if force_final else resp.tool_calls
            msg = resp.to_message(include_reasoning=bool(calls))
            if not calls:
                msg.pop("tool_calls", None)
            messages.append(msg)
            if resp.content:
                transcript.append(f"**Mentor:** {resp.content.strip()}")
                if ctx.emit and not reply_open:  # a client that did not stream: emit the reply whole
                    await say(resp.content)
            if not calls:
                return LoopOutcome(final_text=resp.content)
            for batch in _batches(calls):
                messages.extend(await self._run_calls(ctx, batch, transcript))
            rounds += 1
            if tokens >= token_cap:
                transcript.append(f"**Mentor:** {TOKEN_CAP_NOTE}")
                reply_open = False
                await say(TOKEN_CAP_NOTE)
                return LoopOutcome(final_text=TOKEN_CAP_NOTE, hit_token_cap=True)

    async def _run_calls(self, ctx: ToolContext, batch: list[ToolCall], transcript: list[str]) -> list[dict[str, Any]]:
        """Run one batch of tool calls (concurrently when it has several) and return their tool messages in order."""
        prepared: list[tuple[ToolCall, Tool | None, dict[str, Any] | None, str]] = []
        for call in batch:
            tool = TOOLS.get(call.name)
            try:
                prepared.append((call, tool, call.parsed_arguments(), ""))
            except (ValueError, TypeError) as exc:
                prepared.append(
                    (call, tool, None, f"LỖI: arguments của {call.name} không phải JSON object hợp lệ: {exc}")
                )

        def shown(tool: Tool | None) -> bool:
            return bool(ctx.emit and tool and not tool.silent and tool.ui)

        for call, tool, args, _ in prepared:
            if args is not None and shown(tool):
                await ctx.emit(SandboxEvent(type="tool_started", tool=call.name, summary=tool.started(args)))
        runnable = [(call, args) for call, _, args, _ in prepared if args is not None]
        results = iter(await asyncio.gather(*(execute(ctx, call.name, args) for call, args in runnable)))
        out: list[dict[str, Any]] = []
        for call, tool, args, error in prepared:
            if args is None:
                out.append({"role": "tool", "tool_call_id": call.id, "content": error})
                continue
            result = next(results)
            if shown(tool):
                await ctx.emit(SandboxEvent(type="tool_finished", tool=call.name, summary=result.summary or "Xong"))
            if not (tool and tool.silent):
                transcript.append(f"> công cụ `{call.name}` {_summarize_args(args)} → {result.summary or 'xong'}")
            out.append({"role": "tool", "tool_call_id": call.id, "content": result.content})
        return out

    def _commit(self, message: str) -> None:
        try:
            self.ws.commit(message)
        except Exception:  # never fail a turn because git is unhappy; the next commit picks it up
            log.exception("git commit failed")

    # ---- turns ---------------------------------------------------------------------------

    async def run_turn(self, req: TurnRequest, emit: Emit) -> None:
        """Run one chat turn, emitting SandboxEvents. Always ends with a `done` or `error` event."""
        async with self.lock:
            profile = self.profile_for(req.profile)
            session = self.sessions.get(req.session_id)
            if session is None:
                # First turn of this session since process start: continue from the saved chat log.
                saved = self.ws.load_chat(req.session_id, CHAT_RELOAD_MESSAGES)
                session = SessionState(history=_history_from_chat(saved))
                self.sessions[req.session_id] = session
            now = now_local()
            act = req.card_action
            user_record: dict[str, Any] = {
                "ts": now.isoformat(),
                "role": "user",
                "text": act.echo if act else req.text,
                "attachments": [a.path for a in req.attachments],
            }
            if act:
                user_record["card_action"] = {"card_id": act.card_id, "kind": act.kind, "action": act.action,
                                              "value": act.value}
            chat: list[dict[str, Any]] = [user_record]  # visible records in order: text split around cards
            replies: list[str] = []

            def flush_reply(**extra: Any) -> None:
                text = "".join(replies)
                if chat[-1]["role"] == "card":
                    text = text.lstrip("\n")
                replies.clear()
                if text.strip():
                    chat.append({"ts": now_local().isoformat(), "role": "mentor", "text": text, "attachments": [],
                                 **extra})

            async def emit_visible(event: SandboxEvent) -> None:
                if event.type == "text_delta" and event.text:
                    replies.append(event.text)
                elif event.type == "card" and event.card:
                    flush_reply()
                    chat.append(cards.card_record(event.card, now_local()))
                await emit(event)

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_context(self.ws, profile, now)},
                *session.history,
            ]
            ctx = ToolContext(
                ws=self.ws,
                profile=profile,
                model=self.model,
                settings=self.settings,
                script_runner=self.script_runner,
                session_id=req.session_id,
                emit=emit_visible,
                approvals=self.approvals,
                conversation=messages,
                chat_day=now.date(),
                crisis_context=session.crisis or req.crisis_hold,
            )
            error: str | None = None
            user_content = _user_content(req.text, [(a.path, a.mime_type) for a in req.attachments])
            transcript = [f"### {now:%H:%M}\n**Người học:** {user_content.strip()}"]
            try:
                if act:  # a click on a card: context for the model; focus done/extend are applied here
                    note = await card_action_note(ctx, act.card_id, act.kind, act.action, act.value,
                                                  also=[self.ws.transcript_path(req.session_id, now, ".jsonl")])
                    user_content = f"{user_content}\n{note}"
                    transcript[0] = f"### {now:%H:%M}\n**Người học:** {user_content.strip()}"
                messages.append({"role": "user", "content": user_content})
                await self._loop(
                    ctx, CHAT_ALIAS, messages, token_cap=self.settings.turn_token_cap, transcript=transcript
                )
                if not ctx.crisis_context:
                    for card in ctx.held_cards:  # celebrations go out last, never in a crisis context
                        await ctx.show_card(card)
                if ctx.suggestions:
                    await emit(SandboxEvent(type="suggestions", items=ctx.suggestions))
            except ModelError as exc:
                log.warning("model error in turn %s: %s", req.session_id, exc)
                error = MODEL_DOWN_NOTE
            except Exception:
                log.exception("turn %s failed", req.session_id)
                error = "Có lỗi nội bộ khi xử lý tin nhắn. Bạn thử lại nhé."
            finally:
                session.history = _trim_history(_strip_reasoning(messages[1:]), self.settings.session_history_messages)
                session.crisis = session.crisis or ctx.crisis_context
                if error:
                    transcript.append(f"> lỗi: {error}")
                # deltas already carry the reply separators; quick replies stay on the last mentor message
                flush_reply(**({"suggestions": ctx.suggestions} if ctx.suggestions and not error else {}))
                try:
                    self.ws.append_transcript(req.session_id, "\n\n".join(transcript), now)
                    self.ws.append_chat(req.session_id, chat, now)
                except OSError:
                    log.exception("could not write transcript")
                self._commit(f"mentor: turn {req.session_id}")
            # Outbox goes out on error too: a confirmed crisis alert must never be lost.
            if error:
                await emit(SandboxEvent(type="error", error=error, outbox=ctx.outbox))
            else:
                await emit(SandboxEvent(type="done", outbox=ctx.outbox))

    async def stream_turn(self, req: TurnRequest) -> AsyncIterator[SandboxEvent]:
        """Run a turn in a background task and yield its events as they happen."""
        queue: asyncio.Queue[SandboxEvent | None] = asyncio.Queue()

        async def emit(event: SandboxEvent) -> None:
            await queue.put(event)

        async def runner() -> None:
            try:
                await self.run_turn(req, emit)
            except Exception as exc:  # run_turn already reports; this is a last resort
                log.exception("turn crashed")
                await queue.put(SandboxEvent(type="error", error=str(exc)))
            finally:
                await queue.put(None)

        # If the client goes away the task keeps running, so the turn still finishes and commits.
        task = asyncio.create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        while (event := await queue.get()) is not None:
            yield event

    # ---- jobs -------------------------------------------------------------------------------

    async def run_job(self, req: JobRequest) -> JobResult:
        profile = self.profile_for(req.profile)
        title = jobs.JOB_TITLES_VI[req.kind]
        if not jobs.job_applies(req.kind, profile):
            return JobResult(
                job_id=req.job_id,
                status="skipped",
                summary=f"Bỏ qua {title}: không áp dụng cho profile {profile.value}.",
            )
        focus_card: dict[str, Any] | None = None
        if req.kind == JobKind.FOCUS_END:
            focus_card, _ = cards.find_card(self.ws, str(req.payload.get("card_id") or ""))
            reason = cards.focus_end_skip_reason(focus_card, now_local())
            if reason:
                return JobResult(job_id=req.job_id, status="skipped", summary=f"Bỏ qua {title}: {reason}")
        async with self.lock:
            now = now_local()
            alias = jobs.job_alias(req.kind)
            prompt = jobs.focus_end_prompt(req, focus_card) if focus_card else jobs.job_prompt(req)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_context(self.ws, profile, now)},
                {"role": "user", "content": prompt},
            ]
            ctx = ToolContext(
                ws=self.ws,
                profile=profile,
                model=self.model,
                settings=self.settings,
                script_runner=self.script_runner,
                job_id=req.job_id,
                conversation=messages,
                chat_day=now.date(),
                job_kind=req.kind,
                job_tools=learner_job_tools(req.kind, req.payload),
                crisis_context=req.crisis_hold,
            )
            transcript = [f"### {now:%H:%M} job {req.kind.value}\n{prompt}"]
            status = "ok"
            error: str | None = None
            try:
                outcome = await asyncio.wait_for(
                    self._loop(ctx, alias, messages, token_cap=self.settings.job_token_cap, transcript=transcript),
                    JOB_TIMEOUT_S,
                )
                final = " ".join(outcome.final_text.split())
                if final.upper().startswith(jobs.SKIP_PREFIX):
                    status = "skipped"
                summary = final[:300] or f"Đã chạy {title}."
            except (TimeoutError, ModelError) as exc:
                status, error = "error", str(exc) or exc.__class__.__name__
                summary = f"Chưa chạy xong {title} vì lỗi kết nối mô hình hoặc quá thời gian."
            except Exception as exc:
                log.exception("job %s failed", req.job_id)
                status, error = "error", f"{exc.__class__.__name__}: {exc}"
                summary = f"Chưa chạy xong {title} vì lỗi nội bộ."
            if focus_card and status != "skipped":
                finish_focus_end_job(ctx, focus_card)
            if not ctx.crisis_context:  # celebrations (learner-started jobs only) go last, never in a crisis
                ctx.cards.extend(ctx.held_cards)
            self._save_job_cards(ctx.cards, now)
            self.ws.log_activity(f"job:{req.kind.value}", summary, target=req.job_id, job_id=req.job_id)
            try:
                self.ws.append_transcript(f"job-{req.job_id}", "\n\n".join(transcript), now)
            except OSError:
                log.exception("could not write job transcript")
            self._commit(f"mentor: job {req.kind.value} {req.job_id}")
        return JobResult(
            job_id=req.job_id, status=status, summary=summary, outbox=ctx.outbox, usage=ctx.usage, error=error,
            cards=ctx.cards,
        )

    def _save_job_cards(self, shown: list[dict[str, Any]], now: Any) -> None:
        """Cards a job made go into today's chat transcript (the gateway's daily session), shown at next open."""
        if not shown:
            return
        name = chat_path(now.date()).rsplit("/", 1)[1].removesuffix(".jsonl")
        try:
            self.ws.append_chat(name, [cards.card_record(c, now_local()) for c in shown], now)
        except OSError:
            log.exception("could not write job cards")
