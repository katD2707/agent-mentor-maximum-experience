"""Named conversations (CONTRACTS section 10.5): list/create/rename/archive/delete, search over the transcripts.

A conversation is a label in the ops DB (`conversations`); its messages live in the learner's workspace as
`sessions/<day>/c-<id>.jsonl` (session_id `c-<id>`), exactly like the daily chat's `s-YYYYMMDD.jsonl`.
"""

import asyncio
import re
import unicodedata
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from mentor_schemas import WorkspacePaths
from mentor_schemas.interaction import CONVERSATION_ID_RE, conversation_session_id
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mentor_gateway import cards
from mentor_gateway.api.deps import get_gw, provisioned_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import ChatSession, Conversation, User
from mentor_gateway.mirror import REF
from mentor_gateway.security import new_id

router = APIRouter()

DEFAULT_TITLE = "Cuộc trò chuyện mới"
TITLE_MAX = 80
AUTO_TITLE_CHARS = 50
SUBJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SEARCH_DEFAULT_LIMIT = 30
SEARCH_MAX_LIMIT = 50
SNIPPET_CONTEXT = 60
HISTORY_DEFAULT_LIMIT = 300
TRANSCRIPT_RE = re.compile(r"^sessions/(\d{4}-\d{2}-\d{2})/((?:s-\d{8})|(?:c-[0-9a-f]{12}))\.jsonl$")
CONVERSATION_FILE_RE = re.compile(r"^sessions/\d{4}-\d{2}-\d{2}/c-([0-9a-f]{12})\.(?:jsonl|md)$")


# ---- text folding ----------------------------------------------------------------------------------


def fold(text: str) -> tuple[str, list[int]]:
    """Lower-case text without diacritics (đ -> d) and, for each folded char, the index in `text` it came from."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        base = "d" if ch in "đĐ" else "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
        for c in base.casefold():
            chars.append(c)
            index.append(i)
    return "".join(chars), index


def fold_query(q: str) -> str:
    return " ".join(fold(q)[0].split())


def snippet(text: str, folded: str, index: list[int], pos: int, length: int) -> str:
    start = index[pos]
    end = index[min(pos + length, len(index)) - 1] + 1
    a, b = max(0, start - SNIPPET_CONTEXT), min(len(text), end + SNIPPET_CONTEXT)
    out = " ".join(text[a:b].split())
    return ("…" if a > 0 else "") + out + ("…" if b < len(text) else "")


# ---- shapes ----------------------------------------------------------------------------------------


def conversation_json(row: Conversation) -> dict[str, Any]:
    return {"id": row.id, "session_id": conversation_session_id(row.id), "title": row.title, "subject": row.subject,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
            "archived": row.archived_at is not None}


def get_row(gw: Gateway, user_id: str, conversation_id: str) -> Conversation | None:
    if not CONVERSATION_ID_RE.fullmatch(conversation_id or ""):
        return None
    with gw.db.session() as s:
        return s.get(Conversation, (user_id, conversation_id))


def touch_conversation(gw: Gateway, user_id: str, conversation_id: str, now: datetime, first_text: str | None = None) -> None:
    """After a turn: bump updated_at, un-archive, and name a still-untitled conversation after the first message."""
    with gw.db.session() as s:
        row = s.get(Conversation, (user_id, conversation_id))
        if row is None:
            return
        row.updated_at = now
        row.archived_at = None
        text = " ".join((first_text or "").split())
        if row.auto_title and text and not text.startswith("[card:"):
            row.title = text if len(text) <= AUTO_TITLE_CHARS else text[: AUTO_TITLE_CHARS - 1] + "…"
            row.auto_title = False


def conversation_files(gw: Gateway, user_id: str, conversation_id: str) -> list[str]:
    """`.jsonl` transcripts of one conversation in the mirror, oldest day first."""
    suffix = f"/c-{conversation_id}.jsonl"
    return sorted(e.path for e in gw.mirror.ls_tree(user_id)
                  if e.type == "file" and e.path.startswith(WorkspacePaths.SESSIONS_DIR + "/") and e.path.endswith(suffix))


def conversation_history(gw: Gateway, user_id: str, conversation_id: str, limit: int = HISTORY_DEFAULT_LIMIT) -> list[dict]:
    paths = conversation_files(gw, user_id, conversation_id)
    texts = gw.mirror.read_batch(user_id, [f"{REF}:{p}" for p in paths])
    items = cards.history_from_jsonl("\n".join(t for t in texts if t))
    return items[-limit:] if limit > 0 else items


# ---- requests --------------------------------------------------------------------------------------


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationCreate(_Body):
    title: str | None = None
    subject: str | None = None


class ConversationPatch(_Body):
    title: str | None = None
    subject: str | None = None
    archived: bool | None = None


def _clean_title(title: str) -> str:
    title = " ".join(title.split())
    if not title:
        raise HTTPException(422, "Tên cuộc trò chuyện không được để trống.")
    if len(title) > TITLE_MAX:
        raise HTTPException(422, f"Tên cuộc trò chuyện tối đa {TITLE_MAX} ký tự.")
    return title


def _clean_subject(subject: str | None) -> str | None:
    if subject is None or subject == "":
        return None
    if not SUBJECT_RE.fullmatch(subject):
        raise HTTPException(422, "subject không hợp lệ (chữ thường, số, '-' hoặc '_', tối đa 32 ký tự).")
    return subject


# ---- endpoints -------------------------------------------------------------------------------------


@router.get("/conversations")
async def list_conversations(archived: str = Query("false", pattern="^(true|false|all)$"),
                             user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    """The learner's conversations, most recently active first. `archived`: false (default), true or all."""
    with gw.db.session() as s:
        q = select(Conversation).where(Conversation.user_id == user.id)
        if archived == "false":
            q = q.where(Conversation.archived_at.is_(None))
        elif archived == "true":
            q = q.where(Conversation.archived_at.is_not(None))
        rows = s.scalars(q.order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())).all()
    return [conversation_json(r) for r in rows]


@router.post("/conversations")
async def create_conversation(body: ConversationCreate, user: User = Depends(provisioned_user),
                              gw: Gateway = Depends(get_gw)) -> dict:
    title = _clean_title(body.title) if body.title is not None and body.title.strip() else DEFAULT_TITLE
    explicit = title != DEFAULT_TITLE
    subject = _clean_subject(body.subject)
    now = gw.clock()
    row = Conversation(user_id=user.id, id=new_id()[:12], title=title, auto_title=not explicit, subject=subject,
                       created_at=now, updated_at=now)
    with gw.db.session() as s:
        s.add(row)
    return conversation_json(row)


@router.patch("/conversations/{conversation_id}")
async def patch_conversation(conversation_id: str, body: ConversationPatch, user: User = Depends(provisioned_user),
                             gw: Gateway = Depends(get_gw)) -> dict:
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(422, "Không có gì để đổi.")
    if not CONVERSATION_ID_RE.fullmatch(conversation_id):
        raise HTTPException(404, "not found")
    title = _clean_title(body.title) if "title" in fields and body.title is not None else None
    if "title" in fields and body.title is None:
        raise HTTPException(422, "Tên cuộc trò chuyện không được để trống.")
    subject = _clean_subject(body.subject) if "subject" in fields else None
    with gw.db.session() as s:
        row = s.get(Conversation, (user.id, conversation_id))
        if row is None:
            raise HTTPException(404, "not found")
        if title is not None:
            row.title, row.auto_title = title, False
        if "subject" in fields:
            row.subject = subject
        if "archived" in fields and body.archived is not None:
            row.archived_at = gw.clock() if body.archived else None
        out = conversation_json(row)
    return out


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, user: User = Depends(provisioned_user),
                              gw: Gateway = Depends(get_gw)) -> dict:
    """Removes the conversation and its transcripts (`sessions/*/c-<id>.jsonl` and `.md`) from the workspace; the
    mentor's notes elsewhere (journal, memory) stay. Messages already sent to the model are not recalled."""
    if get_row(gw, user.id, conversation_id) is None:
        raise HTTPException(404, "not found")
    entries = await asyncio.to_thread(gw.mirror.ls_tree, user.id)
    doomed = {e.path: None for e in entries if e.type == "file"
              and (m := CONVERSATION_FILE_RE.match(e.path)) and m.group(1) == conversation_id}
    if doomed:
        await asyncio.to_thread(gw.mirror.commit_files, user.id, doomed, author="user",
                                message=f"Người học xóa cuộc trò chuyện {conversation_id}")
    with gw.db.session() as s:
        row = s.get(Conversation, (user.id, conversation_id))
        if row is not None:
            s.delete(row)
        session_row = s.get(ChatSession, (user.id, conversation_session_id(conversation_id)))
        if session_row is not None:
            s.delete(session_row)
    return {"ok": True}


def search_transcripts(gw: Gateway, user_id: str, q: str, limit: int) -> list[dict]:
    needle = fold_query(q)
    if not needle:
        return []
    with gw.db.session() as s:
        titles = {r.id: r.title for r in s.scalars(select(Conversation).where(Conversation.user_id == user_id))}
    files = []
    for e in gw.mirror.ls_tree(user_id):
        m = TRANSCRIPT_RE.match(e.path) if e.type == "file" else None
        if m:
            files.append((m.group(1), m.group(2), e.path))
    files.sort(reverse=True)  # newest day first; within a day c-* before s-* by name, fine
    results: list[dict] = []
    for day, sid, path in files:
        if len(results) >= limit:
            break
        text = gw.mirror.read_text(user_id, path) or ""
        if needle not in fold(text)[0]:
            continue  # cheap reject before parsing the file
        conv = sid[2:] if sid.startswith("c-") else None
        for rec in reversed(cards.history_from_jsonl(text)):
            if rec.get("role") not in ("user", "mentor"):
                continue
            body = str(rec.get("text") or "")
            folded, index = fold(body)
            pos = folded.find(needle)
            if pos < 0:
                continue
            results.append({"conversation_id": conv, "session_id": sid, "date": day, "ts": rec.get("ts"),
                            "role": rec["role"], "snippet": snippet(body, folded, index, pos, len(needle)),
                            "title": titles.get(conv) if conv else None})
            if len(results) >= limit:
                break
    return results


@router.get("/conversations/search")
async def search_conversations(q: str = Query(..., min_length=1, max_length=200),
                               limit: int = Query(SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
                               user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> list[dict]:
    """Messages of the learner's chats (daily and named) containing `q`, ignoring case and diacritics, newest first.
    `[{conversation_id|null, session_id, date, ts, role: "user"|"mentor", snippet, title|null}]`."""
    return await asyncio.to_thread(search_transcripts, gw, user.id, q, limit)
