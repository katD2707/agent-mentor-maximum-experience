"""Literature lookups for the NCS harness tools paper_* (CONTRACTS.md sections 3 and 5).

Sandboxes have no internet access, so the gateway makes these upstream calls for them, only to a fixed
allowlist of hosts, with timeouts, a response size cap, upstream pacing (arXiv asks for ~1 request / 3 s),
a short in-memory cache and a per-learner rate limit.

Backends: arXiv (Atom API), Semantic Scholar (REST) and Ai2's Asta Scientific Corpus Tool (MCP, asta.py; the
default search source when ASTA_API_KEY is set, falling back to arXiv; first choice for non-arXiv ids in `get`,
with S2 REST as fallback; the only source of snippets and citations).
Asta is licensed for academic / non-commercial use and Ai2 may use the inputs: only search terms and paper ids
are sent, and Asta results carry `ASTA_ATTRIBUTION`.
"""

import asyncio
import html
import json
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx

from mentor_gateway.asta import AstaClient, AstaError

log = logging.getLogger(__name__)

Source = Literal["asta", "arxiv", "semantic_scholar"]
SOURCES: tuple[Source, ...] = ("asta", "arxiv", "semantic_scholar")

ARXIV_API = "https://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1"
ALLOWED_HOSTS = frozenset({"export.arxiv.org", "api.semanticscholar.org", "asta-tools.allen.ai"})
MAX_RESPONSE_BYTES = 2_000_000
MAX_LIMIT = 10
MAX_AUTHORS = 5
SEARCH_ABSTRACT_CHARS = 800
GET_ABSTRACT_CHARS = 4000
MAX_REFERENCES = 10
MAX_QUERY_CHARS = 300
USER_AGENT = "mentor-gateway/0.1 (literature lookup for an AI mentoring app)"
MAX_SNIPPETS = 10
MAX_SNIPPET_PAPERS = 10
SNIPPET_CHARS = 2500
MAX_CITATIONS = 20
ASTA_COOLDOWN_S = 120.0  # after an upstream failure, skip that Asta tool for this long (search -> arXiv at once)
ASTA_DISABLED = {"", "off", "none", "disabled", "false", "0"}

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_ARXIV_NEW_ID = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_ARXIV_OLD_ID = re.compile(r"^[a-z][a-z\-]*(\.[A-Z]{2})?/\d{7}(v\d+)?$")
_ARXIV_ABS = re.compile(r"arxiv\.org/abs/(.+)$")
_S2_PAPER_ID = re.compile(r"^[0-9a-f]{40}$")
_S2_PREFIXED = re.compile(r"^(DOI|CorpusId|MAG|ACL|PMID|PMCID|URL):\S{1,300}$", re.IGNORECASE)
_S2_PREFIX_CASE = {p.lower(): p for p in ("DOI", "CorpusId", "MAG", "ACL", "PMID", "PMCID", "URL")}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

S2_FIELDS = "paperId,title,authors,year,venue,abstract,url,citationCount,externalIds"
S2_GET_FIELDS = (
    f"{S2_FIELDS},referenceCount,tldr,references.paperId,references.title,references.year,references.citationCount"
)
ASTA_FIELDS = "title,authors,year,venue,abstract,url,externalIds,citationCount,publicationDate"
ASTA_GET_FIELDS = f"{ASTA_FIELDS},tldr,references"
ASTA_CITATION_FIELDS = "title,authors,year,venue,url,externalIds,citationCount"


class PaperError(Exception):
    """Upstream or input problem; `status` is the HTTP status the endpoint returns."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _clean(text: str | None, limit: int | None = None) -> str:
    text = " ".join(_CONTROL.sub("", unicodedata.normalize("NFC", text or "")).split())
    if limit is not None and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


# ---- ids -----------------------------------------------------------------------------------


def parse_paper_id(raw: str) -> tuple[Source, str]:
    """`arxiv:<id>`, a bare arXiv id or abs URL -> arXiv; `s2:<sha>`, a 40-hex id or `DOI:`/`CorpusId:`... -> S2."""
    value = raw.strip()
    if m := _ARXIV_ABS.search(value):
        value = f"arxiv:{m.group(1)}"
    low = value.lower()
    if low.startswith("arxiv:"):
        ident = value[6:].strip()
        if _ARXIV_NEW_ID.match(ident) or _ARXIV_OLD_ID.match(ident):
            return "arxiv", ident
        raise PaperError(400, f"not an arXiv id: {ident!r}")
    if low.startswith("s2:"):
        value = value[3:].strip()
    if _S2_PAPER_ID.match(value.lower()):
        return "semantic_scholar", value.lower()
    if _S2_PREFIXED.match(value):
        prefix, rest = value.split(":", 1)
        return "semantic_scholar", f"{_S2_PREFIX_CASE[prefix.lower()]}:{rest}"
    if _ARXIV_NEW_ID.match(value) or _ARXIV_OLD_ID.match(value):
        return "arxiv", value
    raise PaperError(400, "unknown paper id; use arxiv:<id>, s2:<paperId>, DOI:<doi> or CorpusId:<n>")


def asta_paper_id(raw: str) -> str:
    """Our id -> the id form Asta's tools take (`<sha>`, `ARXIV:<id>` without version, `DOI:...`, ...)."""
    source, ident = parse_paper_id(raw)
    if source == "arxiv":
        return "ARXIV:" + re.sub(r"v\d+$", "", ident)
    return ident


# ---- parsing ---------------------------------------------------------------------------------


def _authors(names: list[str]) -> tuple[list[str], int]:
    names = [n for n in (_clean(x) for x in names) if n]
    return names[:MAX_AUTHORS], len(names)


def parse_arxiv_feed(xml_bytes: bytes, abstract_chars: int) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise PaperError(502, f"arXiv returned invalid XML: {exc}") from exc
    papers = []
    for entry in root.findall(f"{_ATOM}entry"):
        raw_id = _clean(entry.findtext(f"{_ATOM}id"))
        title = _clean(entry.findtext(f"{_ATOM}title"))
        if "arxiv.org/api/errors" in raw_id or (title == "Error" and "/abs/" not in raw_id):
            raise PaperError(400, f"arXiv rejected the query: {_clean(entry.findtext(f'{_ATOM}summary'), 300)}")
        m = _ARXIV_ABS.search(raw_id)
        if not m or not title:
            continue
        arxiv_id = m.group(1)
        authors, count = _authors([a.findtext(f"{_ATOM}name") or "" for a in entry.findall(f"{_ATOM}author")])
        published = entry.findtext(f"{_ATOM}published") or ""
        pdf = next((ln.get("href") for ln in entry.findall(f"{_ATOM}link") if ln.get("title") == "pdf"), None)
        category = entry.find(f"{_ARXIV}primary_category")
        papers.append(
            {
                "id": f"arxiv:{arxiv_id}",
                "source": "arxiv",
                "title": title,
                "authors": authors,
                "author_count": count,
                "year": int(published[:4]) if published[:4].isdigit() else None,
                "venue": _clean(entry.findtext(f"{_ARXIV}journal_ref")) or "arXiv",
                "abstract": _clean(entry.findtext(f"{_ATOM}summary"), abstract_chars),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": pdf,
                "doi": _clean(entry.findtext(f"{_ARXIV}doi")) or None,
                "category": category.get("term") if category is not None else None,
                "citation_count": None,
            }
        )
    return papers


def _s2_paper(item: dict[str, Any], abstract_chars: int, source: str = "semantic_scholar") -> dict[str, Any] | None:
    pid = item.get("paperId")
    title = _clean(item.get("title"))
    if not pid or not title:
        return None
    authors, count = _authors([a.get("name") or "" for a in item.get("authors") or [] if isinstance(a, dict)])
    ext = item.get("externalIds") or {}
    return {
        "id": f"s2:{pid}",
        "source": source,
        "title": title,
        "authors": authors,
        "author_count": count,
        "year": item.get("year") if isinstance(item.get("year"), int) else None,
        "venue": _clean(item.get("venue")) or None,
        "abstract": _clean(item.get("abstract"), abstract_chars),
        "url": item.get("url") or f"https://www.semanticscholar.org/paper/{pid}",
        "doi": ext.get("DOI"),
        "arxiv_id": ext.get("ArXiv"),
        "citation_count": item.get("citationCount"),
    }


def parse_s2_search(data: Any) -> list[dict[str, Any]]:
    items = data.get("data") if isinstance(data, dict) else None
    papers = [_s2_paper(i, SEARCH_ABSTRACT_CHARS) for i in items or [] if isinstance(i, dict)]
    return [p for p in papers if p]


def parse_s2_detail(data: Any) -> dict[str, Any]:
    paper = _s2_paper(data, GET_ABSTRACT_CHARS) if isinstance(data, dict) else None
    if paper is None:
        raise PaperError(404, "paper not found")
    refs = [r for r in data.get("references") or [] if isinstance(r, dict) and r.get("paperId") and r.get("title")]
    refs.sort(key=lambda r: r.get("citationCount") or 0, reverse=True)
    tldr = data.get("tldr")
    paper.update(
        reference_count=data.get("referenceCount"),
        tldr=(_clean(tldr.get("text")) or None) if isinstance(tldr, dict) else None,
        top_references=[
            {
                "id": f"s2:{r['paperId']}",
                "title": _clean(r["title"]),
                "year": r.get("year"),
                "citation_count": r.get("citationCount"),
            }
            for r in refs[:MAX_REFERENCES]
        ],
    )
    return paper


def _unescape(item: Any) -> Any:
    """Asta returns some strings HTML-escaped (`Computers &amp; Chemical Engineering`)."""
    if isinstance(item, str):
        return html.unescape(item)
    if isinstance(item, list):
        return [_unescape(x) for x in item]
    if isinstance(item, dict):
        return {k: _unescape(v) for k, v in item.items()}
    return item


def _asta_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data["data"] if isinstance(data.get("data"), list) else [data]
    return [_unescape(i) for i in data or [] if isinstance(i, dict)]


def parse_asta_papers(data: Any, abstract_chars: int = SEARCH_ABSTRACT_CHARS) -> list[dict[str, Any]]:
    """search_papers_by_relevance / get_citations results (S2 paper objects, maybe wrapped in `citingPaper`)."""
    papers = []
    for item in _asta_items(data):
        inner = item["citingPaper"] if isinstance(item.get("citingPaper"), dict) else item
        if paper := _s2_paper(inner, abstract_chars, "asta"):
            paper["publication_date"] = inner.get("publicationDate")
            papers.append(paper)
    return papers


def parse_asta_detail(data: Any) -> dict[str, Any]:
    items = _asta_items(data)
    paper = _s2_paper(items[0], GET_ABSTRACT_CHARS, "asta") if items else None
    if paper is None:
        raise PaperError(404, "paper not found")
    item = items[0]
    raw_refs = item.get("references") if isinstance(item.get("references"), list) else None
    refs = [r for r in raw_refs or [] if isinstance(r, dict) and r.get("paperId") and r.get("title")]
    tldr = item.get("tldr")
    paper.update(
        publication_date=item.get("publicationDate"),
        reference_count=len(raw_refs) if raw_refs is not None else None,
        tldr=(_clean(tldr.get("text")) or None) if isinstance(tldr, dict) else None,
        top_references=[{"id": f"s2:{r['paperId']}", "title": _clean(r["title"])} for r in refs[:MAX_REFERENCES]],
    )
    return paper


def parse_asta_snippets(data: Any) -> list[dict[str, Any]]:
    """snippet_search result: `{data: [{snippet: {text, section, snippetKind}, score, paper: {...}}]}`."""
    snippets = []
    for item in _asta_items(data):
        snip = item["snippet"] if isinstance(item.get("snippet"), dict) else item
        paper = item["paper"] if isinstance(item.get("paper"), dict) else {}
        text = _clean(snip.get("text"), SNIPPET_CHARS)
        if not text:
            continue
        corpus = paper.get("corpusId") or paper.get("corpus_id")
        if paper.get("paperId"):
            pid, url = f"s2:{paper['paperId']}", f"https://www.semanticscholar.org/paper/{paper['paperId']}"
        elif corpus:
            pid, url = f"CorpusId:{corpus}", f"https://api.semanticscholar.org/CorpusId:{corpus}"
        else:
            pid, url = None, None
        names = [a.get("name") if isinstance(a, dict) else a for a in paper.get("authors") or []]
        authors, count = _authors([n for n in names if isinstance(n, str)])
        score = item.get("score")
        snippets.append(
            {
                "paper_id": pid,
                "paper_title": _clean(paper.get("title")) or None,
                "authors": authors,
                "author_count": count,
                "year": paper.get("year") if isinstance(paper.get("year"), int) else None,
                "url": url,
                "section": _clean(snip.get("section")) or None,
                "kind": snip.get("snippetKind") or snip.get("kind"),
                "text": text,
                "score": round(score, 3) if isinstance(score, int | float) else None,
            }
        )
    return snippets


def arxiv_search_query(query: str, year_from: int | None) -> str:
    """Terms are ANDed over all fields; "quoted phrases" stay phrases."""
    terms = []
    for tok in re.findall(r'"[^"]+"|\S+', query):
        words = re.findall(r"[\w\-.]+", tok)
        if not words:
            continue
        terms.append(f'all:"{" ".join(words)}"' if tok.startswith('"') and len(words) > 1 else f"all:{words[0]}")
    if not terms:
        raise PaperError(400, "query has no searchable words")
    q = " AND ".join(terms[:12])
    if year_from:
        q = f"({q}) AND submittedDate:[{year_from}01010000 TO 299912312359]"
    return q


# ---- service ---------------------------------------------------------------------------------


class RateLimiter:
    """Sliding one-minute window per key."""

    def __init__(self, per_minute: int, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self.monotonic = monotonic
        self._calls: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Record a call; return None if allowed, else seconds until the next slot."""
        now = self.monotonic()
        calls = self._calls.setdefault(key, deque())
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) >= self.per_minute:
            return 60 - (now - calls[0])
        calls.append(now)
        return None


class PaperService:
    def __init__(
        self,
        *,
        s2_api_key: str | None = None,
        asta_url: str | None = None,
        asta_api_key: str | None = None,
        asta_timeout_s: float = 40.0,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 15.0,
        arxiv_interval_s: float = 3.0,
        s2_interval_s: float = 1.0,
        asta_interval_s: float | None = None,
        cache_ttl_s: float = 600.0,
        cache_size: int = 256,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self.s2_api_key = s2_api_key
        self.transport = transport
        self.timeout_s = timeout_s
        self.intervals = {"export.arxiv.org": arxiv_interval_s, "api.semanticscholar.org": s2_interval_s}
        self.cache_ttl_s = cache_ttl_s
        self.cache_size = cache_size
        self.monotonic = monotonic
        self.sleep = sleep
        self._cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_call: dict[str, float] = {}
        self.asta: AstaClient | None = None
        self._asta_down_until: dict[str, float] = {}
        if asta_url and asta_url.strip().lower() not in ASTA_DISABLED:
            host = urlsplit(asta_url).hostname or ""
            if urlsplit(asta_url).scheme != "https" or host not in ALLOWED_HOSTS:
                log.warning("ASTA_MCP_URL %s is not an allowlisted https host; Asta disabled", asta_url)
            else:
                self.asta = AstaClient(asta_url, api_key=asta_api_key, transport=transport, timeout_s=asta_timeout_s,
                                       max_bytes=MAX_RESPONSE_BYTES, user_agent=USER_AGENT)
                # keyed Asta allows ~4 requests/s; anonymous access is slower and stricter
                self.intervals[host] = asta_interval_s if asta_interval_s is not None else (
                    0.3 if asta_api_key else 1.0)

    @classmethod
    def from_settings(cls, settings: Any) -> "PaperService":
        return cls(s2_api_key=settings.s2_api_key, asta_url=settings.asta_mcp_url,
                   asta_api_key=settings.asta_api_key, asta_timeout_s=settings.asta_timeout_seconds)

    @property
    def default_source(self) -> Source:
        """arXiv. Asta search takes ~30 s server-side even with a key (measured 2026-10-30), too slow for a chat
        turn, so callers ask for `source="asta"` explicitly (background literature-watch, broader coverage)."""
        return "arxiv"

    # -- public API --

    async def search(self, query: str, source: Source | None = None, limit: int = 5,
                     year_from: int | None = None) -> list[dict[str, Any]]:
        return (await self.search_with_source(query, source, limit, year_from))["results"]

    async def search_with_source(self, query: str, source: Source | None = None, limit: int = 5,
                                 year_from: int | None = None) -> dict[str, Any]:
        """`{source, results}` plus `fallback_from: "asta"` when Asta failed (or is off) and arXiv answered."""
        source = source or self.default_source
        if source == "asta":
            if self.asta is None:
                return {"source": "arxiv", "fallback_from": "asta",
                        "results": await self._search(query, "arxiv", limit, year_from)}
            try:
                return {"source": "asta", "results": await self._search(query, "asta", limit, year_from)}
            except PaperError as exc:
                if exc.status == 400 and not str(exc).startswith("Asta"):
                    raise  # our own input check (e.g. empty query): arXiv would refuse it too
                log.warning("Asta search failed (%s %s); falling back to arXiv", exc.status, exc)
                return {"source": "arxiv", "fallback_from": "asta",
                        "results": await self._search(query, "arxiv", limit, year_from)}
        return {"source": source, "results": await self._search(query, source, limit, year_from)}

    async def _search(self, query: str, source: Source, limit: int, year_from: int | None) -> list[dict[str, Any]]:
        query = _clean(query)
        if not query:
            raise PaperError(400, "empty query")
        query = query[:MAX_QUERY_CHARS]
        limit = max(1, min(int(limit), MAX_LIMIT))
        key = ("search", source, query.lower(), limit, year_from)
        if (hit := self._cache_get(key)) is not None:
            return hit
        if source == "arxiv":
            params = {"search_query": arxiv_search_query(query, year_from), "start": "0",
                      "max_results": str(limit), "sortBy": "relevance", "sortOrder": "descending"}
            papers = parse_arxiv_feed(await self._fetch(ARXIV_API, params), SEARCH_ABSTRACT_CHARS)
        elif source == "semantic_scholar":
            # S2 search treats hyphenated words badly (documented); spaces work.
            params = {"query": query.replace("-", " "), "limit": str(limit), "fields": S2_FIELDS}
            if year_from:
                params["year"] = f"{year_from}-"
            papers = parse_s2_search(_json(await self._fetch(f"{S2_API}/paper/search", params, s2=True)))
        elif source == "asta":
            args: dict[str, Any] = {"keyword": query, "fields": ASTA_FIELDS, "limit": limit}
            if year_from:
                args["publication_date_range"] = f"{year_from}:"
            papers = parse_asta_papers(await self._asta_call("search_papers_by_relevance", args))
        else:
            raise PaperError(400, f"unknown source {source!r}")
        if year_from:
            papers = [p for p in papers if p["year"] is None or p["year"] >= year_from]
        papers = papers[:limit]
        self._cache_put(key, papers)
        return papers

    async def get(self, paper_id: str) -> dict[str, Any]:
        """arXiv ids -> arXiv; other ids -> Asta get_paper when configured, Semantic Scholar REST as fallback."""
        source, ident = parse_paper_id(paper_id)
        key = ("get", source, ident)
        if (hit := self._cache_get(key)) is not None:
            return hit
        if source == "arxiv":
            found = parse_arxiv_feed(await self._fetch(ARXIV_API, {"id_list": ident, "max_results": "1"}),
                                     GET_ABSTRACT_CHARS)
            if not found:
                raise PaperError(404, f"arXiv has no paper {ident}")
            paper = found[0]
        else:
            paper = None
            if self.asta is not None:
                try:
                    paper = parse_asta_detail(
                        await self._asta_call("get_paper", {"paper_id": ident, "fields": ASTA_GET_FIELDS}))
                except PaperError as exc:
                    if exc.status in (400, 404):
                        raise
                    log.warning("Asta get_paper failed (%s %s); falling back to Semantic Scholar", exc.status, exc)
            if paper is None:
                url = f"{S2_API}/paper/{quote(ident, safe=':/.-_')}"
                paper = parse_s2_detail(_json(await self._fetch(url, {"fields": S2_GET_FIELDS}, s2=True)))
        self._cache_put(key, paper)
        return paper

    async def snippets(self, query: str, paper_ids: list[str] | None = None,
                       limit: int = 5) -> list[dict[str, Any]]:
        """~500-word passages (title, abstract, body text) best matching `query`, optionally within given papers."""
        query = _clean(query)[:MAX_QUERY_CHARS]
        if not query:
            raise PaperError(400, "empty query")
        limit = max(1, min(int(limit), MAX_SNIPPETS))
        ids = [i for i in (x.strip() for x in paper_ids or []) if i]
        if len(ids) > MAX_SNIPPET_PAPERS:
            raise PaperError(400, f"at most {MAX_SNIPPET_PAPERS} paper ids")
        asta_ids = sorted({asta_paper_id(i) for i in ids})
        key = ("snippets", query.lower(), tuple(asta_ids), limit)
        if (hit := self._cache_get(key)) is not None:
            return hit
        args: dict[str, Any] = {"query": query, "limit": limit}
        if asta_ids:
            args["paper_ids"] = ",".join(asta_ids)
        snippets = parse_asta_snippets(await self._asta_call("snippet_search", args))[:limit]
        self._cache_put(key, snippets)
        return snippets

    async def citations(self, paper_id: str, limit: int = 10, year_from: int | None = None) -> list[dict[str, Any]]:
        """Papers citing `paper_id`, most-cited first (from a wider page, since Asta's order is arbitrary)."""
        ident = asta_paper_id(paper_id)
        limit = max(1, min(int(limit), MAX_CITATIONS))
        key = ("citations", ident, limit, year_from)
        if (hit := self._cache_get(key)) is not None:
            return hit
        args: dict[str, Any] = {"paper_id": ident, "fields": ASTA_CITATION_FIELDS, "limit": min(100, limit * 5)}
        if year_from:
            args["publication_date_range"] = f"{year_from}:"
        papers = parse_asta_papers(await self._asta_call("get_citations", args))
        papers.sort(key=lambda p: p.get("citation_count") or 0, reverse=True)
        papers = papers[:limit]
        self._cache_put(key, papers)
        return papers

    async def _asta_call(self, tool: str, args: dict[str, Any]) -> Any:
        """Asta tool call: paced starts (no lock held while a slow call runs), per-tool cooldown after failures."""
        if self.asta is None:
            raise PaperError(503, "Asta is not configured on this gateway")
        if self.monotonic() < self._asta_down_until.get(tool, 0.0):
            raise PaperError(503, "Asta is temporarily unavailable (recent errors); try again in a few minutes")
        host = self.asta.host
        async with self._host_locks.setdefault(host, asyncio.Lock()):
            wait = self.intervals.get(host, 1.0) - (self.monotonic() - self._last_call.get(host, -1e9))
            if wait > 0:
                await self.sleep(wait)
            self._last_call[host] = self.monotonic()
        try:
            return await self.asta.call_tool(tool, args)
        except AstaError as exc:
            if exc.status >= 500:
                self._asta_down_until[tool] = self.monotonic() + ASTA_COOLDOWN_S
            raise PaperError(exc.status, f"Asta: {exc}") from exc

    # -- internals --

    def _cache_get(self, key: tuple) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if self.monotonic() - entry[0] > self.cache_ttl_s:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return entry[1]

    def _cache_put(self, key: tuple, value: Any) -> None:
        self._cache[key] = (self.monotonic(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    async def _fetch(self, url: str, params: dict[str, str], *, s2: bool = False) -> bytes:
        host = urlsplit(url).hostname or ""
        if urlsplit(url).scheme != "https" or host not in ALLOWED_HOSTS:
            raise PaperError(500, f"host not allowed: {host}")
        headers = {"User-Agent": USER_AGENT}
        if s2 and self.s2_api_key:
            headers["x-api-key"] = self.s2_api_key
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:  # one request at a time per host, spaced by the host's interval
            wait = self.intervals.get(host, 1.0) - (self.monotonic() - self._last_call.get(host, -1e9))
            if wait > 0:
                await self.sleep(wait)
            try:
                return await self._download(url, params, headers, host)
            finally:
                self._last_call[host] = self.monotonic()

    async def _download(self, url: str, params: dict[str, str], headers: dict[str, str], host: str) -> bytes:
        try:
            async with (
                httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s, follow_redirects=False) as client,
                client.stream("GET", url, params=params, headers=headers) as resp,
            ):
                if resp.status_code == 404:
                    raise PaperError(404, "paper not found")
                if resp.status_code == 429:
                    raise PaperError(503, f"{host} is rate limiting; try again in a minute")
                if resp.status_code == 400:
                    body = (await resp.aread())[:300].decode("utf-8", "replace")
                    raise PaperError(400, f"{host} rejected the request: {body}")
                if resp.status_code != 200:
                    raise PaperError(502, f"{host} returned HTTP {resp.status_code}")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise PaperError(502, f"{host} response larger than {MAX_RESPONSE_BYTES} bytes")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise PaperError(504, f"{host} timed out") from exc
        except httpx.HTTPError as exc:
            raise PaperError(502, f"{host} unreachable: {exc.__class__.__name__}") from exc


def _json(body: bytes) -> Any:
    try:
        return json.loads(body)
    except ValueError as exc:
        raise PaperError(502, "upstream returned invalid JSON") from exc
