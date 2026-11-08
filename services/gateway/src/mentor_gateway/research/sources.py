"""Optional paper sources that need the learner's own key: Semantic Scholar (REST) and Asta (MCP, asta.py).

Adapted from the old gateway `papers.py` (git HEAD): the parsers and field lists are kept, the app-wide key and the
`PaperService` cache are gone. One client per request is built from the key of the user who asks, so nothing is shared
between learners and nothing is cached across keys. Only keywords and paper ids leave the gateway. Keys go in headers
and are never put in a URL, a log line, an exception message or a response.

arXiv is not here: `research/papers.py` (vendored DeepTutor) does it with no key.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from typing import Any

import httpx

from .asta import ASTA_MCP_URL, AstaClient, AstaError

S2_API = "https://api.semanticscholar.org/graph/v1"
USER_AGENT = "mentor-gateway/0.1 (literature search for a learner's thesis)"
MAX_RESPONSE_BYTES = 2_000_000
S2_FIELDS = "paperId,title,authors,year,venue,abstract,url,citationCount,externalIds,tldr,openAccessPdf"
S2_RELATED_FIELDS = ",".join(f"{side}.{f}" for side in ("citations", "references")
                             for f in ("paperId", "title", "authors", "year", "venue", "abstract", "url", "citationCount",
                                       "externalIds", "openAccessPdf"))
ASTA_FIELDS = "title,authors,year,venue,abstract,url,externalIds,citationCount,publicationDate,openAccessPdf,corpusId"
ASTA_CITATION_FIELDS = "title,authors,year,venue,url,externalIds,citationCount,openAccessPdf,abstract"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_VERSION = re.compile(r"v\d+$")


class SourceError(Exception):
    """kind: invalid_key (401/403), unreachable (down, timeout, rate limit), not_found, bad (the source refused the request)."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind


def clean_text(text: Any, limit: int | None = None) -> str:
    text = " ".join(_CONTROL.sub("", unicodedata.normalize("NFC", str(text or ""))).split())
    if limit is not None and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def unescape(item: Any) -> Any:
    """Asta returns some strings HTML-escaped (`Computers &amp; Chemical Engineering`)."""
    if isinstance(item, str):
        return html.unescape(item)
    if isinstance(item, list):
        return [unescape(x) for x in item]
    if isinstance(item, dict):
        return {k: unescape(v) for k, v in item.items()}
    return item


def strip_version(arxiv_id: str) -> str:
    return _VERSION.sub("", arxiv_id.strip())


def paper_key(arxiv_id: str | None, doi: str | None, s2_id: str | None) -> str | None:
    if arxiv_id:
        return f"arxiv:{strip_version(arxiv_id)}"
    if doi:
        return f"doi:{doi.strip().lower()}"
    if s2_id:
        return f"s2:{s2_id}"
    return None


def excerpt(abstract: str | None, limit: int = 240) -> str:
    """First sentences of an abstract, at most `limit` characters (cut at a word boundary with an ellipsis when one
    sentence is longer)."""
    text = clean_text(abstract)
    if not text:
        return ""
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + 1 + len(sentence) > limit:
            break
        out = f"{out} {sentence}".strip()
        if len(out) >= limit:
            break
    if len(out) > limit:
        out = out[: limit - 1].rsplit(" ", 1)[0].rstrip(",;: ") + "…"
    return out


def item_to_card(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    """An S2 paper object (from S2 REST or Asta) -> PaperCard fields. `source` is "s2" or "asta".

    tldr is S2's own field and only on S2 cards; Asta cards carry a `snippet` instead (added by the search)."""
    inner = item["citingPaper"] if isinstance(item.get("citingPaper"), dict) else item
    title = clean_text(inner.get("title"))
    pid = inner.get("paperId")
    if not title or not (pid or inner.get("externalIds")):
        return None
    ext = inner.get("externalIds") or {}
    arxiv_id = strip_version(str(ext["ArXiv"])) if ext.get("ArXiv") else None
    doi = str(ext["DOI"]).lower() if ext.get("DOI") else None
    key = paper_key(arxiv_id, doi, pid)
    if key is None:
        return None
    names = [a.get("name") if isinstance(a, dict) else a for a in inner.get("authors") or []]
    authors = [clean_text(n) for n in names if isinstance(n, str) and clean_text(n)][:5]
    oa = inner.get("openAccessPdf")
    tldr = inner.get("tldr")
    abstract = clean_text(inner.get("abstract"), 4000)
    return {
        "key": key, "source": source, "title": title, "authors": authors,
        "year": inner.get("year") if isinstance(inner.get("year"), int) else None,
        "venue": clean_text(inner.get("venue")) or None, "arxiv_id": arxiv_id, "doi": doi, "s2_id": pid,
        "url": inner.get("url") or (f"https://www.semanticscholar.org/paper/{pid}" if pid else ""),
        "excerpt": excerpt(abstract), "abstract": abstract,
        "tldr": (clean_text(tldr.get("text")) or None) if source == "s2" and isinstance(tldr, dict) else None,
        "snippet": None,
        "citation_count": inner.get("citationCount") if isinstance(inner.get("citationCount"), int) else None,
        "has_pdf": bool(isinstance(oa, dict) and oa.get("url")),
        "pdf_url": oa.get("url") if isinstance(oa, dict) and oa.get("url") else None,
        "corpus_id": str(ext.get("CorpusId") or inner.get("corpusId") or "") or None,
    }


def asta_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data["data"] if isinstance(data.get("data"), list) else [data]
    return [unescape(i) for i in data or [] if isinstance(i, dict)]


def parse_snippets(data: Any) -> list[dict[str, Any]]:
    """snippet_search result -> [{corpus_id, paper_id, title, section, text, url, score}] (empty texts dropped)."""
    out = []
    for item in asta_items(data):
        snip = item["snippet"] if isinstance(item.get("snippet"), dict) else item
        paper = item["paper"] if isinstance(item.get("paper"), dict) else {}
        text = clean_text(snip.get("text"), 2500)
        if not text:
            continue
        corpus = str(paper.get("corpusId") or paper.get("corpus_id") or "") or None
        pid = paper.get("paperId")
        url = (f"https://www.semanticscholar.org/paper/{pid}" if pid
               else f"https://api.semanticscholar.org/CorpusId:{corpus}" if corpus else None)
        score = item.get("score")
        out.append({"corpus_id": corpus, "paper_id": pid, "title": clean_text(paper.get("title")) or None,
                    "section": clean_text(snip.get("section")) or None, "text": text, "url": url,
                    "score": float(score) if isinstance(score, int | float) else 0.0})
    return out


def s2_ref(arxiv_id: str | None, doi: str | None, s2_id: str | None) -> str | None:
    """The id form S2 and Asta take for one paper."""
    if s2_id:
        return s2_id
    if arxiv_id:
        return "ARXIV:" + strip_version(arxiv_id)
    if doi:
        return "DOI:" + doi
    return None


class S2Client:
    """Semantic Scholar Graph API with the learner's own key (`x-api-key`)."""

    def __init__(self, key: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = 20.0) -> None:
        self._key = key
        self.transport = transport
        self.timeout_s = timeout_s

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        headers = {"User-Agent": USER_AGENT, "x-api-key": self._key}
        try:
            async with (httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s, follow_redirects=False) as client,
                        client.stream("GET", f"{S2_API}{path}", params=params, headers=headers) as resp):
                if resp.status_code in (401, 403):
                    raise SourceError("invalid_key")
                if resp.status_code == 404:
                    raise SourceError("not_found")
                if resp.status_code == 400:
                    raise SourceError("bad", "Semantic Scholar rejected the request")
                if resp.status_code != 200:  # 429 and 5xx: down for now
                    raise SourceError("unreachable", f"Semantic Scholar HTTP {resp.status_code}")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise SourceError("unreachable", "Semantic Scholar response too large")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise SourceError("unreachable", f"Semantic Scholar unreachable: {exc.__class__.__name__}") from exc
        try:
            return json.loads(b"".join(chunks))
        except ValueError as exc:
            raise SourceError("unreachable", "Semantic Scholar sent invalid JSON") from exc

    async def search(self, query: str, *, limit: int = 10, offset: int = 0, year_min: int | None = None
                     ) -> tuple[list[dict[str, Any]], bool]:
        """-> (cards, has_more). S2 search handles hyphens badly (documented), spaces work."""
        params = {"query": query.replace("-", " "), "limit": str(limit), "offset": str(offset), "fields": S2_FIELDS}
        if year_min:
            params["year"] = f"{year_min}-"
        data = await self._get("/paper/search", params)
        items = data.get("data") if isinstance(data, dict) else None
        cards = [c for i in items or [] if isinstance(i, dict) and (c := item_to_card(i, "s2"))]
        total = data.get("total") if isinstance(data, dict) else None
        more = bool(isinstance(data, dict) and data.get("next") is not None) or (
            isinstance(total, int) and total > offset + len(items or []))
        return cards, more

    async def related(self, ref: str) -> dict[str, Any]:
        """-> {citing_total, cited_total, citing: [cards], cited: [cards]} for one paper (S2 order: most cited first)."""
        from urllib.parse import quote

        data = await self._get(f"/paper/{quote(ref, safe=':/.-_')}",
                               {"fields": f"citationCount,referenceCount,{S2_RELATED_FIELDS}"})
        if not isinstance(data, dict):
            raise SourceError("unreachable", "Semantic Scholar sent an unexpected reply")

        def cards(side: str) -> list[dict[str, Any]]:
            out = [c for i in data.get(side) or [] if isinstance(i, dict) and (c := item_to_card(i, "s2"))]
            out.sort(key=lambda c: c["citation_count"] or 0, reverse=True)
            return out

        return {"citing_total": data.get("citationCount") if isinstance(data.get("citationCount"), int) else None,
                "cited_total": data.get("referenceCount") if isinstance(data.get("referenceCount"), int) else None,
                "citing": cards("citations"), "cited": cards("references")}

    async def get_paper(self, ref: str) -> dict[str, Any] | None:
        from urllib.parse import quote

        try:
            data = await self._get(f"/paper/{quote(ref, safe=':/.-_')}", {"fields": S2_FIELDS})
        except SourceError as exc:
            if exc.kind == "not_found":
                return None
            raise
        return item_to_card(data, "s2") if isinstance(data, dict) else None

    async def validate(self) -> None:
        """One cheap call: raises SourceError(invalid_key | unreachable)."""
        await self._get("/paper/search", {"query": "attention", "limit": "1", "fields": "paperId"})


class AstaSource:
    """Asta Scientific Corpus Tool (MCP) with the learner's own key. Wraps `AstaClient` and maps its errors."""

    def __init__(self, key: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = 40.0) -> None:
        self.client = AstaClient(ASTA_MCP_URL, api_key=key, transport=transport, timeout_s=timeout_s,
                                 max_bytes=MAX_RESPONSE_BYTES, user_agent=USER_AGENT)

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        try:
            return await self.client.call_tool(tool, args)
        except AstaError as exc:
            if exc.status == 401:
                raise SourceError("invalid_key") from None
            if exc.status == 404:
                raise SourceError("not_found") from None
            if exc.status == 400:
                raise SourceError("bad", "Asta rejected the request") from None
            raise SourceError("unreachable", f"Asta unavailable ({exc.status})") from None

    async def search(self, query: str, *, limit: int = 10, year_min: int | None = None) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"keyword": query, "fields": ASTA_FIELDS, "limit": max(1, min(limit, 100))}
        if year_min:
            args["publication_date_range"] = f"{year_min}:"
        data = await self._call("search_papers_by_relevance", args)
        return [c for i in asta_items(data) if (c := item_to_card(i, "asta"))]

    async def snippets(self, query: str, *, limit: int = 10, paper_ids: list[str] | None = None) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"query": query, "limit": max(1, min(limit, 10))}
        if paper_ids:
            args["paper_ids"] = ",".join(paper_ids)
        return parse_snippets(await self._call("snippet_search", args))

    async def citations(self, ref: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Papers citing `ref`, most cited first (Asta's own order is arbitrary, so a wider page is cut)."""
        args = {"paper_id": ref, "fields": ASTA_CITATION_FIELDS, "limit": min(100, limit * 5)}
        cards = [c for i in asta_items(await self._call("get_citations", args)) if (c := item_to_card(i, "asta"))]
        cards.sort(key=lambda c: c["citation_count"] or 0, reverse=True)
        return cards[:limit]

    async def get_paper(self, ref: str) -> dict[str, Any] | None:
        try:
            data = await self._call("get_paper", {"paper_id": ref, "fields": ASTA_FIELDS})
        except SourceError as exc:
            if exc.kind == "not_found":
                return None
            raise
        items = asta_items(data)
        return item_to_card(items[0], "asta") if items else None

    async def validate(self) -> None:
        await self._call("search_papers_by_relevance", {"keyword": "attention", "fields": "title", "limit": 1})
