"""Web search for the harness tool web_search (both profiles), proxied because sandboxes have no internet.

Backends, chosen by settings: Tavily (hosted, `TAVILY_API_KEY`; preferred when set) or SearXNG (self-hosted
JSON API, `SEARXNG_URL`, no key). Neither set -> `WebSearchError(503, reason="not_configured")`.

Privacy: queries go to a third party, so they travel only in POST bodies (never in a URL that httpx/uvicorn
would log), are never logged here, and are cached in memory only (10 min). Results are cleaned (HTML stripped,
lengths capped, only http(s) links) but remain untrusted web content; the harness frames them as such.
"""

import html
import json
import re
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

TAVILY_API = "https://api.tavily.com/search"
MAX_RESULTS = 8
DEFAULT_RESULTS = 5
MAX_QUERY_CHARS = 300
TITLE_CHARS = 200
SNIPPET_CHARS = 500
URL_CHARS = 500
TIMEOUT_S = 15.0
MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "mentor-gateway/0.1 (web search for an AI mentoring app)"

_TAG = re.compile(r"<[^>]{0,500}>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_SPACE_BEFORE_PUNCT = re.compile(r" ([.,;:!?)\]])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


class WebSearchError(Exception):
    """`status` = HTTP status the endpoint returns; `reason` = machine-readable cause for the harness."""

    def __init__(self, status: int, message: str, reason: str = "upstream") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


def clean_text(text: Any, limit: int) -> str:
    """Strip HTML tags/entities, control and bidi characters, collapse whitespace, cap length."""
    if not isinstance(text, str):
        return ""
    text = _SCRIPT.sub(" ", text)
    text = html.unescape(_TAG.sub(" ", text))
    text = _TAG.sub(" ", text)  # tags that were entity-escaped (&lt;b&gt;) in the source
    text = " ".join(_CONTROL.sub("", unicodedata.normalize("NFC", text)).split())
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)  # "<i>CCCD</i>." -> "CCCD ." -> "CCCD."
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def clean_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or len(url) > URL_CHARS:
        return None
    return url


def normalize_results(items: Any, max_results: int) -> list[dict[str, Any]]:
    """Backend rows -> `[{title, url, snippet, published?}]`, deduped by URL, at most `max_results`."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = clean_url(item.get("url"))
        if url is None or url in seen:
            continue
        title = clean_text(item.get("title"), TITLE_CHARS) or (urlsplit(url).hostname or url)
        row: dict[str, Any] = {"title": title, "url": url,
                               "snippet": clean_text(item.get("content") or item.get("snippet"), SNIPPET_CHARS)}
        published = item.get("published_date") or item.get("publishedDate")
        if isinstance(published, str) and published.strip():
            row["published"] = clean_text(published, 40)
        out.append(row)
        seen.add(url)
        if len(out) >= max_results:
            break
    return out


class WebSearchService:
    def __init__(
        self,
        *,
        tavily_api_key: str | None = None,
        searxng_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = TIMEOUT_S,
        cache_ttl_s: float = 600.0,
        cache_size: int = 128,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.tavily_api_key = (tavily_api_key or "").strip() or None
        self.searxng_url = None
        if searxng_url and searxng_url.strip():
            base = searxng_url.strip().rstrip("/")
            if urlsplit(base).scheme in ("http", "https") and urlsplit(base).hostname:
                self.searxng_url = base
        self.transport = transport
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self.cache_size = cache_size
        self.monotonic = monotonic
        self._cache: OrderedDict[tuple, tuple[float, list[dict[str, Any]]]] = OrderedDict()

    @classmethod
    def from_settings(cls, settings: Any) -> "WebSearchService":
        return cls(tavily_api_key=settings.tavily_api_key, searxng_url=settings.searxng_url)

    @property
    def backend(self) -> str | None:
        if self.tavily_api_key:
            return "tavily"
        if self.searxng_url:
            return "searxng"
        return None

    async def search(self, query: str, max_results: int = DEFAULT_RESULTS, *,
                     safesearch: int = 1) -> list[dict[str, Any]]:
        backend = self.backend
        if backend is None:
            raise WebSearchError(503, "web search is not configured on this gateway (TAVILY_API_KEY or SEARXNG_URL)",
                                 "not_configured")
        query = " ".join(_CONTROL.sub("", query or "").split())[:MAX_QUERY_CHARS]
        if not query:
            raise WebSearchError(400, "empty query", "bad_request")
        max_results = max(1, min(int(max_results), MAX_RESULTS))
        key = (backend, query.lower(), max_results, safesearch)
        if (hit := self._cache_get(key)) is not None:
            return hit
        if backend == "tavily":
            body = {"query": query, "max_results": max_results, "search_depth": "basic", "topic": "general",
                    "include_answer": False, "include_raw_content": False, "include_images": False}
            headers = {"Authorization": f"Bearer {self.tavily_api_key}"}
            data = await self._post(TAVILY_API, headers=headers, json_body=body)
        else:
            # POST form, so the query is not in a URL (SearXNG's default method is POST as well).
            form = {"q": query, "format": "json", "safesearch": str(safesearch), "pageno": "1"}
            data = await self._post(f"{self.searxng_url}/search", form=form)
        results = normalize_results(data.get("results") if isinstance(data, dict) else None, max_results)
        self._cache_put(key, results)
        return results

    async def _post(self, url: str, *, headers: dict[str, str] | None = None, json_body: Any = None,
                    form: dict[str, str] | None = None) -> Any:
        host = urlsplit(url).hostname or url
        hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        try:
            async with (
                httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s, follow_redirects=False) as client,
                client.stream("POST", url, headers=hdrs, json=json_body, data=form) as resp,
            ):
                if resp.status_code == 429:
                    raise WebSearchError(503, f"{host} is rate limiting; try again later", "rate_limited")
                if resp.status_code in (401, 403):
                    raise WebSearchError(502, f"{host} refused the request (HTTP {resp.status_code}; check the "
                                         "API key / that the SearXNG JSON format is enabled)")
                if resp.status_code != 200:
                    raise WebSearchError(502, f"{host} returned HTTP {resp.status_code}")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise WebSearchError(502, f"{host} response larger than {MAX_RESPONSE_BYTES} bytes")
                    chunks.append(chunk)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise WebSearchError(504, f"{host} timed out", "timeout") from exc
        except httpx.HTTPError as exc:
            raise WebSearchError(502, f"{host} unreachable: {exc.__class__.__name__}") from exc
        try:
            return json.loads(b"".join(chunks))
        except ValueError as exc:
            raise WebSearchError(502, f"{host} returned invalid JSON") from exc

    def _cache_get(self, key: tuple) -> list[dict[str, Any]] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if self.monotonic() - entry[0] > self.cache_ttl_s:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return entry[1]

    def _cache_put(self, key: tuple, value: list[dict[str, Any]]) -> None:
        self._cache[key] = (self.monotonic(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
