"""Fakes for the Nghiên cứu tests: a scripted model, S2 and Asta over httpx.MockTransport, arXiv rows. No network, no model.

The model is never called for search cards: tests assert `llm.calls` stays empty after a search.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from mentor_gateway.research import papers

FIXTURES = Path(__file__).parent / "fixtures" / "asta"
SYSTEM_MARKERS = {  # first match in the system prompt -> reply key
    "set up a thesis topic": "profile",
    "quick literature review": "review",
    "NEW arXiv paper": "reasons",
    "adds a paper to a reading list": "entry_reason",
    "reading coach": "feedback",
    "answer ONE question": "qa",
    "structure a researcher": "experiment",
    "Read one deadline": "deadline",
    "date and time of a meeting": "meeting_when",
    "Draft the list": "agenda",
    "Split a student": "notes",
    "One sentence, in": "hero",
    "deep reasoning engine": "frontier",
}


class FakeLLM:
    """Scripted ChatLLM. `replies[key]` is a dict (sent as JSON), a string (sent as is), an Exception (raised) or a callable
    (messages -> any of those). Missing key: raises, as an unavailable model does."""

    def __init__(self, **replies: Any) -> None:
        self.replies: dict[str, Any] = replies
        self.calls: list[tuple[str, str, list[dict]]] = []  # (key, alias, messages)

    async def complete(self, alias: str, messages: list[dict[str, Any]], *, max_tokens: int = 2000, temperature: float = 0.3) -> str:
        system = messages[0]["content"] if isinstance(messages[0]["content"], str) else ""
        key = next((k for marker, k in SYSTEM_MARKERS.items() if marker in system), alias)
        self.calls.append((key, alias, messages))
        reply = self.replies.get(key)
        if callable(reply):
            reply = reply(messages)
        if reply is None:
            raise RuntimeError(f"no scripted reply for {key}")
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)

    def user_text(self, key: str, n: int = -1) -> str:
        calls = [c for c in self.calls if c[0] == key]
        return calls[n][2][-1]["content"]

    def count(self, key: str) -> int:
        return sum(1 for c in self.calls if c[0] == key)


def arxiv_paper(aid: str, title: str, year: int = 2026, abstract: str = "We study a thing. It works on 3,000 samples with 7% accuracy.",
                authors: tuple[str, ...] = ("Ada Lovelace", "Alan Turing")) -> papers.Paper:
    return papers.Paper(arxiv_id=aid, title=title, authors=list(authors), year=year, abstract=abstract,
                        url=f"http://arxiv.org/abs/{aid}v1", published=f"{year}-05-01T00:00:00+00:00")


def feed_row(aid: str, title: str, year: int = 2026, abstract: str = "We study a thing. It works.") -> dict:
    """A row as the vendored `parse_feed` makes it."""
    return {"arxiv_id": aid, "title": title, "authors": ["Ada Lovelace", "Alan Turing"], "abstract": abstract,
            "published": f"{year}-05-01T00:00:00+00:00", "updated": "", "url": f"https://arxiv.org/abs/{aid}",
            "pdf_url": f"https://arxiv.org/pdf/{aid}", "evidence_level": "primary_abstract"}


class FakeArxiv:
    """Stands in for `search_arxiv`, `literature_pass` clients and the abs/pdf fetches. Records every query."""

    def __init__(self, by_query: dict[str, list[papers.Paper]] | None = None, default: list[papers.Paper] | None = None) -> None:
        self.by_query = by_query or {}
        self.default = default or []
        self.queries: list[str] = []
        self.fail = False

    async def search(self, query: str, max_results: int = 5, years_limit: int | None = 3, sort: str = "relevance", *, searcher: Any = None):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("arxiv down")
        return list(self.by_query.get(query, self.default))[:max_results]

    # the vendored ResearchClient.search shape (literature_pass)
    async def lit_search(self, query: str, *, limit: int = 6) -> list[dict]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("arxiv down")
        return [feed_row(p.arxiv_id, p.title, p.year or 2026, p.abstract) for p in list(self.by_query.get(query, self.default))[:limit]]


class FakeLitClient:
    """`research_primitives.ResearchClient` double: `.search` for literature_pass, `.fetch` for abs and PDF downloads."""

    def __init__(self, arxiv: FakeArxiv) -> None:
        self.arxiv = arxiv
        self.fetched: list[str] = []

    async def search(self, query: str, *, limit: int = 6) -> list[dict]:
        return await self.arxiv.lit_search(query, limit=limit)


class FakeSearcher:
    """`ArxivSearchTool` double for discover_frontier: `search_papers` returns the vendored dict rows."""

    def __init__(self, arxiv: FakeArxiv) -> None:
        self.arxiv = arxiv

    async def search_papers(self, query: str, max_results: int, years_limit: int | None, sort_by: str) -> list[dict]:
        self.arxiv.queries.append(query)
        if self.arxiv.fail:
            raise RuntimeError("arxiv down")
        return [{"arxiv_id": p.arxiv_id, "title": p.title, "authors": p.authors, "year": p.year, "abstract": p.abstract,
                 "url": p.url, "published": p.published} for p in list(self.arxiv.by_query.get(query, self.arxiv.default))[:max_results]]


def _sse(name: str, rid: int) -> bytes:
    body = (FIXTURES / name).read_text(encoding="utf-8")
    return re.sub(r'"jsonrpc": ?"2.0", ?"id": ?\d+', f'"jsonrpc":"2.0","id":{rid}', body).encode()


ASTA_TOOL_FIXTURES = {"search_papers_by_relevance": "search_papers_by_relevance.sse", "get_paper": "get_paper.sse",
                      "get_citations": "get_citations.sse", "snippet_search": "snippet_search.synthetic.sse"}


def s2_item(pid: str, title: str, *, arxiv: str | None = None, doi: str | None = None, year: int = 2025, cites: int = 12,
            tldr: str | None = "A one line S2 summary.", pdf: bool = True, abstract: str = "Abstract of the paper. Second sentence.") -> dict:
    ext: dict[str, str] = {}
    if arxiv:
        ext["ArXiv"] = arxiv
    if doi:
        ext["DOI"] = doi
    return {"paperId": pid, "title": title, "year": year, "venue": "ICML", "abstract": abstract, "citationCount": cites,
            "authors": [{"name": f"Author {i}"} for i in range(7)], "externalIds": ext,
            "tldr": {"text": tldr} if tldr else None,
            "openAccessPdf": {"url": f"https://example.org/{pid}.pdf"} if pdf else None,
            "url": f"https://www.semanticscholar.org/paper/{pid}"}


class FakeSources:
    """S2 REST and Asta MCP over one MockTransport. Configure `s2_items`, `asta_fail`, `s2_status` ... per test; `seen` records
    (host, key header present, path/tool) and `keys` the key values seen, so tests can assert where a key was sent."""

    def __init__(self) -> None:
        self.s2_items: list[dict] = []
        self.s2_status = 200
        self.s2_related: dict | None = None
        self.valid_keys: set[str] = set()  # empty = any key is valid
        self.asta_status = 200
        self.asta_fail: dict[str, httpx.Response] = {}
        self.seen: list[tuple[str, str, str]] = []
        self.keys: list[str] = []
        self.asta_calls: list[tuple[str, dict]] = []
        self.asta_search_items: list[dict] | None = None  # custom search_papers_by_relevance results (S2 paper objects)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("x-api-key", "")
        if key:
            self.keys.append(key)
        if request.url.host == "api.semanticscholar.org":
            self.seen.append(("s2", key, request.url.path))
            if self.valid_keys and key not in self.valid_keys:
                return httpx.Response(401)
            if self.s2_status != 200:
                return httpx.Response(self.s2_status)
            if request.url.path.endswith("/paper/search"):
                return httpx.Response(200, json={"total": len(self.s2_items) + 5, "offset": 0, "data": self.s2_items})
            return httpx.Response(200, json=self.s2_related or {"paperId": "x", "title": "x", "citationCount": 0, "referenceCount": 0})
        # Asta MCP
        msg = json.loads(request.content)
        sse = {"content-type": "text/event-stream"}
        if msg["method"] == "initialize":
            return httpx.Response(200, content=_sse("initialize.sse", msg["id"]), headers=sse)
        if msg["method"] == "notifications/initialized":
            return httpx.Response(202)
        name, args = msg["params"]["name"], msg["params"]["arguments"]
        self.seen.append(("asta", key, name))
        self.asta_calls.append((name, args))
        if self.valid_keys and key not in self.valid_keys:
            return httpx.Response(403)
        if self.asta_status != 200:
            return httpx.Response(self.asta_status)
        if name in self.asta_fail:
            return self.asta_fail[name]
        if name == "search_papers_by_relevance" and self.asta_search_items is not None:
            body = {"jsonrpc": "2.0", "id": msg["id"], "result": {"isError": False, "content": [
                {"type": "text", "text": json.dumps(i)} for i in self.asta_search_items]}}
            return httpx.Response(200, json=body)
        return httpx.Response(200, content=_sse(ASTA_TOOL_FIXTURES[name], msg["id"]), headers=sse)


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)
