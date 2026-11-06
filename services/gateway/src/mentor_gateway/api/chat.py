"""WebSocket /api/ws/chat: relays TurnRequest -> sandbox SSE -> WS messages, approvals both ways."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from mentor_schemas import ApprovalDecision, Attachment, CardAction, SandboxEvent, TurnRequest, WorkspacePaths
from mentor_schemas.interaction import card_action_text, card_day, conversation_session_id
from pydantic import ValidationError

from mentor_gateway import cards
from mentor_gateway.api import conversations as convs
from mentor_gateway.api.deps import COOKIE_NAME, current_user, get_gw, provisioned_user, user_from_cookie
from mentor_gateway.context import Gateway
from mentor_gateway.db import ChatSession, User
from mentor_gateway.mirror import normalize_path
from mentor_gateway.sandbox import SandboxSpec
from mentor_gateway.security import new_id

log = logging.getLogger(__name__)
LEARNER_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
router = APIRouter()


def event_to_message(ev: SandboxEvent) -> dict | None:
    if ev.type == "text_delta":
        return {"type": "text_delta", "text": ev.text or ""}
    if ev.type in ("tool_started", "tool_finished"):
        return {"type": ev.type, "tool": ev.tool, "summary": ev.summary}
    if ev.type == "approval_request" and ev.approval is not None:
        return {"type": "approval_request", "approval": ev.approval.model_dump(mode="json")}
    if ev.type == "card" and ev.card:
        return {"type": "card", "card": ev.card}
    if ev.type == "error":
        return {"type": "error", "error": ev.error or "sandbox error"}
    return None


def session_id_for(now: datetime) -> str:
    """One chat session per learner per local day (CONTRACTS section 2, "Sessions and chat history")."""
    return "s-" + now.astimezone(LEARNER_TZ).strftime("%Y%m%d")


def touch_session(gw: Gateway, user_id: str, session_id: str, now: datetime) -> None:
    with gw.db.session() as s:
        row = s.get(ChatSession, (user_id, session_id))
        if row is None:
            s.add(ChatSession(user_id=user_id, id=session_id, started_at=now, last_active_at=now))
        else:
            row.last_active_at = now


@router.get("/chat/history")
async def chat_history(date: str | None = None, conversation_id: str | None = None,
                       limit: int = Query(convs.HISTORY_DEFAULT_LIMIT, ge=1, le=1000), user: User = Depends(provisioned_user),
                       gw: Gateway = Depends(get_gw)) -> list[dict]:
    """Visible messages and cards of one day's session, from sessions/<date>/<session_id>.jsonl in the mirror
    (shapes: mentor_gateway.cards.history_from_jsonl). With `conversation_id`: that named conversation's whole
    history across days (the newest `limit` items, default 300); 404 for an unknown or another learner's id."""
    if conversation_id is not None:
        if convs.get_row(gw, user.id, conversation_id) is None:
            raise HTTPException(404, "conversation not found")
        return await asyncio.to_thread(convs.conversation_history, gw, user.id, conversation_id, limit)
    if date is None:
        day = gw.clock().astimezone(LEARNER_TZ).date()
    else:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(422, "date must be YYYY-MM-DD") from exc
    path = f"{WorkspacePaths.SESSIONS_DIR}/{day.isoformat()}/s-{day.strftime('%Y%m%d')}.jsonl"
    text = await asyncio.to_thread(gw.mirror.read_text, user.id, path) or ""
    return cards.history_from_jsonl(text)


async def find_card(gw: Gateway, user_id: str, card_id: str, conversation_id: str | None = None) -> dict | None:
    """The newest version of a card in this learner's chat transcript (mirror), or None."""
    paths = cards.card_paths(card_id, gw.clock().astimezone(LEARNER_TZ).date(), conversation_id)
    texts = [await asyncio.to_thread(gw.mirror.read_text, user_id, p) for p in paths]
    return cards.latest_card(texts, card_id)


async def warm_sandbox(gw: Gateway, user: User) -> dict:
    """Start the learner's sandbox in the background (never waits for it). Only for active learners."""
    if gw.users.onboarding_state(user) != "active":
        return {"state": "sleeping", "warming": False, "result": "not_active"}
    spec = SandboxSpec(user_id=user.id, profile=gw.users.profile(user), workspace_dir=gw.sync.path(user.id))
    try:
        state, result = await gw.orchestrator.warm(spec)
    except Exception:  # e.g. the docker daemon is unreachable: opening the chat must still work
        log.exception("pre-warm failed for %s", user.id)
        return {"state": "sleeping", "warming": False, "result": "error"}
    return {"state": state, "warming": result in ("started", "starting"), "result": result}


@router.post("/sandbox/warm")
async def sandbox_warm(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    """Pre-warm on chat/pop-up focus so the first message skips the cold start (CONTRACTS section 5)."""
    return await warm_sandbox(gw, user)


class ChatConnection:
    def __init__(self, gw: Gateway, ws: WebSocket, user: User) -> None:
        self.gw = gw
        self.ws = ws
        self.user = user
        self.turn: asyncio.Task | None = None

    async def send(self, message: dict) -> None:
        await self.gw.hub.send_to(self.user.id, self.ws, message)

    def _attachments(self, raw: list) -> list[Attachment]:
        out = []
        for a in raw or []:
            att = Attachment.model_validate(a)
            path = normalize_path(att.path)
            if not path.startswith(WorkspacePaths.INBOX_DIR + "/"):
                raise ValueError(f"attachment outside inbox/: {path}")
            out.append(Attachment(path=path, mime_type=att.mime_type))
        return out

    async def run_turn(self, client_msg_id: str, text: str, attachments: list[Attachment],
                       card_action: CardAction | None = None, conversation_id: str | None = None) -> None:
        gw, uid = self.gw, self.user.id
        profile = gw.users.profile(self.user)
        now = gw.clock()
        session_id = conversation_session_id(conversation_id) if conversation_id else session_id_for(now)
        touch_session(gw, uid, session_id, now)
        req = TurnRequest(session_id=session_id, user_id=uid, profile=profile, text=text,
                          attachments=attachments, client_time=now, card_action=card_action,
                          crisis_hold=gw.hub.hold_active(uid))  # no celebrations during the 24 h crisis hold
        spec = SandboxSpec(user_id=uid, profile=profile, workspace_dir=gw.sync.path(uid))
        outbox = []
        try:
            async with gw.orchestrator.session(spec) as client:
                async for ev in client.turn(req):
                    if ev.type in ("done", "error"):
                        outbox = ev.outbox  # an error event may still carry e.g. a confirmed crisis alert
                    if ev.type == "done":
                        continue
                    if ev.type == "suggestions":
                        if ev.items:
                            await self.send({"type": "suggestions", "client_msg_id": client_msg_id, "items": ev.items})
                        continue
                    msg = event_to_message(ev)
                    if msg is not None:
                        await self.send(msg)
        except Exception as exc:
            log.exception("turn failed for %s", uid)
            await self.send({"type": "error", "error": f"Mentor đang gặp sự cố, thử lại sau nhé. ({type(exc).__name__})"})
        touch_session(gw, uid, session_id, gw.clock())
        if conversation_id:
            convs.touch_conversation(gw, uid, conversation_id, gw.clock(), None if card_action else text)
        if outbox:
            await gw.dispatcher.dispatch(uid, profile, outbox)
        await self.send({"type": "turn_done", "client_msg_id": client_msg_id})

    async def _conversation_id(self, msg: dict) -> str | None | bool:
        """The learner's named conversation a message belongs to: None = the daily chat, False = refused (sent)."""
        raw = msg.get("conversation_id")
        if raw in (None, ""):
            return None
        row = convs.get_row(self.gw, self.user.id, str(raw))
        if row is None:
            await self.send({"type": "error", "error": "Không tìm thấy cuộc trò chuyện này.",
                             "conversation_id": str(raw)})
            return False
        return row.id

    async def _card_action(self, msg: dict) -> None:
        """A click on a chat card: checked against this learner's transcript, then run as a normal turn."""
        card_id = str(msg.get("card_id") or "")
        action = str(msg.get("action") or "")
        client_msg_id = str(msg.get("client_msg_id") or new_id("m"))
        conversation_id = await self._conversation_id(msg)
        if conversation_id is False:
            return
        card = await find_card(self.gw, self.user.id, card_id, conversation_id) if card_day(card_id) else None
        if card is None:
            await self.send({"type": "error", "error": "Không tìm thấy thẻ này trong cuộc trò chuyện.",
                             "card_id": card_id})
            return
        try:
            value, echo = cards.resolve_action(card, action, msg.get("value"))
        except cards.CardActionError as exc:
            await self.send({"type": "error", "error": str(exc), "card_id": card_id})
            return
        kind = str(card["kind"])
        if kind == "focus":  # ended early or extended: the old wake-up must not fire; the harness schedules anew
            await asyncio.to_thread(cards.cancel_focus_jobs, self.gw.db, self.user.id, card_id, self.gw.clock())
        act = CardAction(card_id=card_id, kind=kind, action=action, value=value, echo=echo)
        await self.send({"type": "card_echo", "client_msg_id": client_msg_id, "card_id": card_id, "action": action,
                         "value": value, "text": echo})
        self.turn = asyncio.create_task(
            self.run_turn(client_msg_id, card_action_text(kind, action, value), [], act, conversation_id))

    async def on_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "card_action":
            if self.turn is not None and not self.turn.done():
                await self.send({"type": "error", "error": "Mentor vẫn đang trả lời tin trước."})
                return
            if self.gw.users.onboarding_state(self.gw.users.get(self.user.id)) != "active":
                await self.send({"type": "error", "error": "Tài khoản chưa được kích hoạt."})
                return
            await self._card_action(msg)
        elif kind == "user_message":
            client_msg_id = str(msg.get("client_msg_id") or new_id("m"))
            if self.turn is not None and not self.turn.done():
                await self.send({"type": "error", "error": "Mentor vẫn đang trả lời tin trước."})
                return
            if self.gw.users.onboarding_state(self.gw.users.get(self.user.id)) != "active":
                await self.send({"type": "error", "error": "Tài khoản chưa được kích hoạt."})
                return
            try:
                attachments = self._attachments(msg.get("attachments") or [])
            except (ValueError, ValidationError) as exc:
                await self.send({"type": "error", "error": str(exc)})
                return
            conversation_id = await self._conversation_id(msg)
            if conversation_id is False:
                return
            text = str(msg.get("text") or "")
            self.turn = asyncio.create_task(self.run_turn(client_msg_id, text, attachments, None, conversation_id))
        elif kind == "approval_decision":
            try:
                decision = ApprovalDecision.model_validate({k: v for k, v in msg.items() if k != "type"})
            except ValidationError as exc:
                await self.send({"type": "error", "error": str(exc)})
                return
            client = self.gw.orchestrator.active_client(self.user.id)
            if client is None:
                await self.send({"type": "error", "error": "Không có yêu cầu nào đang chờ duyệt."})
                return
            try:
                await client.approval(decision)
            except httpx.HTTPError as exc:
                await self.send({"type": "error", "error": f"approval failed: {exc}"})
        else:
            await self.send({"type": "error", "error": f"unknown message type: {kind}"})


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    gw: Gateway = ws.app.state.gw
    origin = ws.headers.get("origin")
    if origin and origin.rstrip("/") not in (*gw.settings.allowed_origins, gw.settings.public_base_url.rstrip("/")):
        # browsers always send Origin; refuse cross-site WebSocket hijacking with the learner's cookie
        await ws.close(code=4403)
        return
    user = user_from_cookie(gw, ws.cookies.get(COOKIE_NAME))
    await ws.accept()
    if user is None:
        await ws.send_json({"type": "error", "error": "not authenticated"})
        await ws.close(code=4401)
        return
    state = gw.users.onboarding_state(user)
    if state != "active":
        await ws.send_json({"type": "error", "error": f"account not active: {state}"})
        await ws.close(code=4403)
        return

    conn = ChatConnection(gw, ws, user)
    gw.hub.register(user.id, ws)
    try:
        # pre-warm before reporting the state, so a sleeping sandbox shows "waking" straight away, not
        # "sleeping" then "waking"
        state = (await warm_sandbox(gw, user))["state"]
        await conn.send({"type": "sandbox_status", "state": state})
        await gw.hub.flush(user.id)
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict):
                await conn.on_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        gw.hub.unregister(user.id, ws)
        # A turn in flight keeps running so its memory writes and push complete.
