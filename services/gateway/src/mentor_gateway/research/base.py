"""Shared plumbing of the research service: dependencies, model calls, rate limits, paper storage, reading-list views.

`ResearchBase` holds everything the feature modules (profile, search, reading, jobs, lab, meetings, deadlines, overview)
share. The feature modules are mixins over it; `service.ResearchService` puts them together. All network and model access
is an attribute a test can replace (`llm`, `transport`, `arxiv_search`, `lit_client`, `frontier`, `fetch_arxiv_feed`,
`fetch_pdf`): the tests never reach the network or the model.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException
from mentor_schemas import ModelAlias
from mentor_schemas.research import PaperCard, ReadingEntry
from sqlalchemy import select

from mentor_gateway.ask.jsonparse import parse_model_json
from mentor_gateway.ask.llm import ChatLLM
from mentor_gateway.db import User
from mentor_gateway.planner import events as ev
from mentor_gateway.planner.bands import TZ
from mentor_gateway.research import papers
from mentor_gateway.research.fulltext import MAX_PDF_BYTES, TextCache
from mentor_gateway.research.sources import AstaSource, S2Client, excerpt
from mentor_gateway.research.tables import (
    PaperNoteRow,
    PaperRow,
    ReadingEntryRow,
    ResearchProfileRow,
)
from mentor_gateway.research.vendor.deeptutor import research_primitives as prim

log = logging.getLogger(__name__)

NEW_THIS_WEEK = timedelta(days=7)
READ_KEPT = timedelta(days=14)
JOB_TTL = timedelta(hours=1)


class ModelUnavailable(Exception):
    """No model configured, the call failed or timed out, or the reply was not the JSON asked for."""


def fail(status: int, code: str, *, headers: dict[str, str] | None = None, **extra: Any) -> HTTPException:
    """`{"error": code, ...}` with the status (the app's HTTPException handler writes the body as is)."""
    return HTTPException(status, {"error": code, **extra}, headers=headers)


class Limiter:
    """Per-user sliding windows on the gateway clock: search 30/min, key validation 5/min, review 10/hour, discovery 1/6 h."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self._calls: dict[tuple[str, str], deque[datetime]] = {}

    def check(self, user_id: str, name: str, limit: int, window: timedelta) -> int | None:
        """Records a call and returns None, or returns the seconds until a slot frees (the call is not recorded)."""
        now = self.clock()
        calls = self._calls.setdefault((user_id, name), deque())
        while calls and now - calls[0] >= window:
            calls.popleft()
        if len(calls) >= limit:
            return max(1, int((window - (now - calls[0])).total_seconds()) + 1)
        calls.append(now)
        return None

    def require(self, user_id: str, name: str, limit: int, window: timedelta) -> None:
        retry = self.check(user_id, name, limit, window)
        if retry is not None:
            raise fail(429, "rate_limited", headers={"Retry-After": str(retry)}, retry_after=retry)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(TZ).isoformat(timespec="seconds") if dt else None


def new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(5)


def surname_line(authors: list[str], year: int | None) -> str:
    names = ", ".join(a.split()[-1] for a in authors[:3] if a.split())
    return f"{names} · {year}" if names and year else names or (str(year) if year else "")


class ResearchBase:
    def __init__(self, gw: Any, content: Any, llm: ChatLLM | None, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.gw = gw
        self.db = gw.db
        self.clock = gw.clock
        self.box = gw.box
        self.users = gw.users
        self.planner = gw.planner
        self.mirror = gw.mirror
        self.settings = gw.settings
        self.content = content
        self.llm = llm
        self.transport = transport  # for the S2 and Asta clients (tests pass an httpx.MockTransport)
        self.llm_timeout = 90.0
        self.limiter = Limiter(self.clock)
        self.texts = TextCache(gw.settings.data_dir / "research")
        self.jobs: dict[str, dict[str, Any]] = {}  # job id -> row, 1 hour TTL
        self.related_cache: dict[tuple[str, str], tuple[datetime, Any, tuple[bool, bool]]] = {}  # (user, paper) -> (at, value, keys)
        self.hero_cache: dict[tuple[str, str, str, str], str] = {}
        self.tasks: set[asyncio.Task] = set()
        self._checked: dict[str, datetime] = {}  # per-user throttle of the scheduler hook
        self._asta: dict[str, AstaSource] = {}
        # replaceable edges ------------------------------------------------------------------------------------------
        self.arxiv_search = papers.search_arxiv  # async (query, max_results, years_limit, sort, *, searcher=None)
        self.arxiv_searcher = None  # an ArxivSearchTool for discover_frontier (tests inject a fake)
        self.lit_client: prim.ResearchClient | None = None  # literature_pass's client
        self.frontier = papers.discover_frontier
        self.literature = papers.literature_pass
        self.fetch_arxiv_feed = self._fetch_arxiv_feed
        self.fetch_pdf = self._fetch_pdf
        self.replan = self._replan

    # ---- model --------------------------------------------------------------------------------------------------------
    async def llm_json(self, system: str, user: str, *, alias: str = ModelAlias.CHAT.value, max_tokens: int = 1500,
                       timeout: float | None = None) -> dict[str, Any]:
        if self.llm is None:
            raise ModelUnavailable("no model configured")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            raw = await asyncio.wait_for(self.llm.complete(alias, messages, max_tokens=max_tokens, temperature=0.2),
                                         timeout or self.llm_timeout)
        except Exception as exc:
            raise ModelUnavailable(f"{exc.__class__.__name__}: {str(exc)[:160]}") from exc
        try:
            return parse_model_json(raw)
        except ValueError as exc:
            raise ModelUnavailable("the model did not return JSON") from exc

    def bg(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    # ---- network edges ------------------------------------------------------------------------------------------------
    async def _fetch_arxiv_feed(self, arxiv_id: str) -> list[dict]:
        client = self.lit_client or prim.ResearchClient()
        raw = await client.fetch(f"https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1",
                                 limit=2 * 1024 * 1024, accept="application/atom+xml")
        return prim.parse_feed(raw)

    async def _fetch_pdf(self, url: str) -> bytes:
        return await (self.lit_client or prim.ResearchClient()).fetch(url, limit=MAX_PDF_BYTES, accept="application/pdf")

    # ---- keys ---------------------------------------------------------------------------------------------------------
    @staticmethod
    def _aad(user_id: str, source: str) -> str:
        return f"research-key:{user_id}:{source}"

    def user_key(self, user_id: str, source: str) -> str | None:
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user_id)
            sealed = None if row is None else (row.asta_key_enc if source == "asta" else row.s2_key_enc)
        if not sealed:
            return None
        try:
            return self.box.unseal_str(sealed, aad=self._aad(user_id, source))
        except Exception:  # noqa: BLE001 - a blob that no longer opens counts as no key
            log.warning("research key of %s (%s) does not open; ignored", user_id, source)
            return None

    def s2_client(self, key: str) -> S2Client:
        return S2Client(key, transport=self.transport)

    def asta_source(self, user_id: str, key: str) -> AstaSource:
        """One Asta MCP session per user and key (the handshake is a round trip); never shared between users."""
        cache_key = f"{user_id}:{hash(key)}"
        src = self._asta.get(cache_key)
        if src is None:
            if len(self._asta) > 64:
                self._asta.clear()
            src = self._asta[cache_key] = AstaSource(key, transport=self.transport)
        return src

    # ---- profile ------------------------------------------------------------------------------------------------------
    def profile_row(self, user_id: str) -> ResearchProfileRow | None:
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user_id)
            if row is not None:
                s.expunge(row)
            return row

    def topic(self, user_id: str) -> tuple[str, str, list[str]]:
        row = self.profile_row(user_id)
        return (row.title, row.question, list(row.keywords or [])) if row else ("", "", [])

    # ---- papers -------------------------------------------------------------------------------------------------------
    @staticmethod
    def card_of(p: PaperRow, in_list: bool = True) -> PaperCard:
        return PaperCard(key=p.key, source=p.source, title=p.title, authors=list(p.authors or [])[:5], year=p.year,
                         venue=p.venue, arxiv_id=p.arxiv_id, doi=p.doi, s2_id=p.s2_id, url=p.url,
                         excerpt=excerpt(p.abstract), tldr=p.tldr, snippet=None, citation_count=p.citation_count,
                         has_pdf=p.has_pdf, in_reading_list=in_list, paper_id=p.id)

    def upsert_paper(self, user_id: str, f: dict[str, Any]) -> str:
        """Stores a paper by its key (one row per user and key) and returns our id. Empty fields of an old row are filled."""
        now = self.clock()
        with self.db.session() as s:
            row = s.scalar(select(PaperRow).where(PaperRow.user_id == user_id, PaperRow.key == f["key"]))
            if row is None:
                row = PaperRow(id=new_id("p-"), user_id=user_id, key=f["key"], created_at=now, fulltext_state="none")
                s.add(row)
            for name in ("arxiv_id", "doi", "s2_id", "venue", "pdf_url", "tldr", "citation_count", "year", "upload_path"):
                if f.get(name) is not None and getattr(row, name) in (None, ""):
                    setattr(row, name, f[name])
            if f.get("title") and not row.title:
                row.title = f["title"]
            if f.get("url") and not row.url:
                row.url = f["url"]
            if f.get("authors") and not row.authors:
                row.authors = list(f["authors"])[:12]
            abstract = f.get("abstract") or ""
            if abstract and len(abstract) > len(row.abstract or ""):
                row.abstract = abstract
            row.has_pdf = bool(row.has_pdf or f.get("has_pdf") or row.arxiv_id)
            if row.arxiv_id and not row.pdf_url:
                row.pdf_url = f"https://arxiv.org/pdf/{row.arxiv_id}"
            row.source = f.get("source") or row.source or "arxiv"
            s.flush()
            return row.id

    @staticmethod
    def fields_of_arxiv(p: papers.Paper) -> dict[str, Any]:
        """An arXiv `Paper` -> the field dict `upsert_paper` takes."""
        aid = re.sub(r"v\d+$", "", p.arxiv_id)
        return {"key": f"arxiv:{aid}", "source": "arxiv", "title": p.title, "authors": p.authors, "year": p.year,
                "arxiv_id": aid, "url": f"https://arxiv.org/abs/{aid}", "abstract": p.abstract, "has_pdf": True,
                "pdf_url": f"https://arxiv.org/pdf/{aid}"}

    def card_of_arxiv(self, p: papers.Paper) -> PaperCard:
        f = self.fields_of_arxiv(p)
        return PaperCard(key=f["key"], source="arxiv", title=p.title, authors=p.authors[:5], year=p.year, arxiv_id=f["arxiv_id"],
                         url=f["url"], excerpt=excerpt(p.abstract), has_pdf=True)

    # ---- reading list views -------------------------------------------------------------------------------------------
    def minutes_map(self, user_id: str, now: datetime) -> dict[str, int]:
        """Minutes per paper from `focus_tick` seconds of the sessions that start with `paper_opened` (CONTRACTS 15.9)."""
        events = [e for e in ev.stored(self.db, user_id, now - timedelta(days=90))
                  if e["kind"] in ("paper_opened", "focus_tick")]
        seconds: dict[str, int] = {}
        cur, last = None, None
        for e in events:
            if e["kind"] == "paper_opened":
                cur, last = e["data"].get("paper_id"), e["ts"]
            elif cur is not None and last is not None and e["ts"] - last <= timedelta(minutes=30):
                seconds[cur] = seconds.get(cur, 0) + int(e["data"].get("seconds") or 0)
                last = e["ts"]
            else:
                cur = None
        return {k: round(v / 60) for k, v in seconds.items()}

    def entry_model(self, p: PaperRow, e: ReadingEntryRow, now: datetime, minutes: dict[str, int]) -> ReadingEntry:
        return ReadingEntry(
            id=p.id, paper=self.card_of(p, True), status=e.status, reason=e.reason or "", origin=e.origin,
            new_this_week=e.status == "new" and now - e.added_at <= NEW_THIS_WEEK, minutes_spent=minutes.get(p.id, 0),
            added_at=iso(e.added_at), opened_at=iso(e.opened_at), read_at=iso(e.read_at))

    def entry_for(self, user_id: str, paper_id: str, *, allow_removed: bool = False) -> tuple[PaperRow, ReadingEntryRow] | None:
        with self.db.session() as s:
            p = s.get(PaperRow, paper_id)
            e = s.get(ReadingEntryRow, paper_id)
            if p is None or e is None or p.user_id != user_id or e.user_id != user_id:
                return None
            if e.removed_at is not None and not allow_removed:
                return None
            s.expunge_all()
            return p, e

    def entry_view(self, user_id: str, paper_id: str) -> ReadingEntry | None:
        got = self.entry_for(user_id, paper_id)
        if got is None:
            return None
        return self.entry_model(got[0], got[1], self.clock(), self.minutes_map(user_id, self.clock()))

    def active_count(self, user_id: str) -> int:
        with self.db.session() as s:
            return len(s.scalars(select(ReadingEntryRow.paper_id).where(
                ReadingEntryRow.user_id == user_id, ReadingEntryRow.removed_at.is_(None),
                ReadingEntryRow.status.in_(("new", "reading")))).all())

    def note_row(self, paper_id: str) -> PaperNoteRow | None:
        with self.db.session() as s:
            n = s.get(PaperNoteRow, paper_id)
            if n is not None:
                s.expunge(n)
            return n

    # ---- planner ------------------------------------------------------------------------------------------------------
    def _replan(self, user_id: str, trigger: str) -> None:
        """A research change that the plan should show: the scheduler's next pass replans (like a goal change)."""
        try:
            self.planner.mark_dirty(user_id, trigger)
        except Exception:
            log.exception("research replan trigger %s", trigger)

    def event(self, user: User, kind: str, ident: str, data: dict[str, Any]) -> None:
        """Records a behaviour event server-side; one per kind, id and local day (client id `res-<kind>-<id>-<date>`)."""
        now = self.clock()
        day = now.astimezone(TZ).date().isoformat()
        ev.record(self.db, user.id, f"res-{kind}-{ident}-{day}"[:64], kind, now, data)
