"""POST /internal/web/search and WebSearchService: backends faked with httpx.MockTransport, no network."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from mentor_schemas import Profile

from mentor_gateway.app import create_app
from mentor_gateway.settings import Settings
from mentor_gateway.websearch import WebSearchError, WebSearchService, clean_text

TAVILY = {
    "query": "q",
    "results": [
        {"title": "Quy ch&eacute; <b>thi</b>", "url": "https://moet.gov.vn/a", "score": 0.9,
         "content": "<p>Thí sinh&nbsp;cần <script>alert(1)</script>mang <i>CCCD</i>.</p>" + "x" * 2000},
        {"title": "dup", "url": "https://moet.gov.vn/a", "content": "same url"},
        {"title": "bad scheme", "url": "javascript:alert(1)", "content": "dropped"},
        {"title": "News", "url": "http://news.example/b", "content": "c", "published_date": "2026-10-01"},
    ],
}
SEARXNG = {"query": "q", "results": [
    {"title": "Học bổng", "url": "https://scholarship.example/x", "content": "Hạn nộp 30/11",
     "publishedDate": "2026-09-30T00:00:00"},
]}


class Upstream:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.override: httpx.Response | Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.override, Exception):
            raise self.override
        if self.override is not None:
            return self.override
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json=TAVILY)
        return httpx.Response(200, json=SEARXNG)


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


def _service(upstream: Upstream, **kw) -> WebSearchService:
    return WebSearchService(transport=httpx.MockTransport(upstream), **kw)


# ---- service ----------------------------------------------------------------------------------


def test_clean_text_strips_html() -> None:
    assert clean_text("<p>a&amp;b&nbsp;<b>c</b></p>&lt;i&gt;d&lt;/i&gt;\u202e", 100) == "a&b c d"
    assert clean_text("x" * 50, 10) == "x" * 9 + "…"
    assert clean_text(None, 10) == ""


async def test_tavily_backend(upstream: Upstream) -> None:
    svc = _service(upstream, tavily_api_key="tvly-k", searxng_url="http://searx:8080")
    assert svc.backend == "tavily"
    results = await svc.search("  quy chế\nthi  ", 50)
    req = upstream.requests[0]
    assert req.method == "POST" and str(req.url) == "https://api.tavily.com/search"
    assert req.headers["authorization"] == "Bearer tvly-k"
    body = json.loads(req.content)
    assert body["query"] == "quy chế thi" and body["max_results"] == 8 and body["include_raw_content"] is False
    assert [r["url"] for r in results] == ["https://moet.gov.vn/a", "http://news.example/b"]
    first = results[0]
    assert first["title"] == "Quy ché thi" and "<" not in first["snippet"] and "alert" not in first["snippet"]
    assert first["snippet"].startswith("Thí sinh cần mang CCCD.") and len(first["snippet"]) <= 500
    assert "published" not in first and results[1]["published"] == "2026-10-01"
    assert set(first) == {"title", "url", "snippet"}
    await svc.search("quy chế thi", 8)  # cached
    assert len(upstream.requests) == 1


async def test_searxng_backend_posts_form(upstream: Upstream) -> None:
    svc = _service(upstream, searxng_url="http://searx:8080/")
    [row] = await svc.search("học bổng", 3, safesearch=2)
    req = upstream.requests[0]
    assert req.method == "POST" and str(req.url) == "http://searx:8080/search" and not req.url.query
    form = dict(httpx.QueryParams(req.content.decode()))
    assert form == {"q": "học bổng", "format": "json", "safesearch": "2", "pageno": "1"}
    assert row == {"title": "Học bổng", "url": "https://scholarship.example/x", "snippet": "Hạn nộp 30/11",
                   "published": "2026-09-30T00:00:00"}


async def test_not_configured_and_empty_query(upstream: Upstream) -> None:
    with pytest.raises(WebSearchError) as exc:
        await _service(upstream, searxng_url="ftp://nope").search("x")
    assert exc.value.status == 503 and exc.value.reason == "not_configured"
    with pytest.raises(WebSearchError) as exc:
        await _service(upstream, tavily_api_key="k").search("  \x00 ")
    assert exc.value.status == 400
    assert upstream.requests == []


@pytest.mark.parametrize(
    ("override", "status", "reason"),
    [
        (httpx.Response(429), 503, "rate_limited"),
        (httpx.Response(401), 502, "upstream"),
        (httpx.Response(500), 502, "upstream"),
        (httpx.Response(200, content=b"<html>not json"), 502, "upstream"),
        (httpx.Response(302, headers={"Location": "http://elsewhere/"}), 502, "upstream"),
        (httpx.ReadTimeout("slow"), 504, "timeout"),
        (httpx.ConnectError("down"), 502, "upstream"),
    ],
)
async def test_upstream_failures(upstream: Upstream, override, status, reason) -> None:
    upstream.override = override
    with pytest.raises(WebSearchError) as exc:
        await _service(upstream, tavily_api_key="k").search("x")
    assert (exc.value.status, exc.value.reason) == (status, reason)


def test_settings_from_env() -> None:
    s = Settings.from_env({"TAVILY_API_KEY": "tvly-x", "SEARXNG_URL": "http://localhost:8888",
                           "WEB_SEARCH_REQUESTS_PER_MINUTE": "4"})
    assert (s.tavily_api_key, s.searxng_url, s.web_search_requests_per_minute) == (
        "tvly-x", "http://localhost:8888", 4)
    assert WebSearchService.from_settings(Settings.from_env({})).backend is None


# ---- endpoint ---------------------------------------------------------------------------------


class IdleBackend:
    async def ensure_running(self, spec):  # pragma: no cover - not used here
        raise AssertionError

    async def stop(self, user_id):
        return None

    async def status(self, user_id):
        return "stopped"


@pytest.fixture
def web_client(settings, upstream: Upstream):
    settings = settings.model_copy(update={"web_search_requests_per_minute": 2})
    app = create_app(settings, backend=IdleBackend())
    app.state.gw.web = _service(upstream, searxng_url="http://searx:8080")
    with TestClient(app) as c:
        yield c


def _auth(client: TestClient, profile: Profile = Profile.THPT, user: str = "u1") -> dict:
    return {"Authorization": f"Bearer {client.app.state.gw.tokens.issue(user, profile)}"}


URL = "/internal/web/search"


def test_endpoint_auth_profiles_and_audit(web_client: TestClient, upstream: Upstream) -> None:
    assert web_client.post(URL, json={"query": "x"}).status_code == 401
    assert web_client.post(URL, json={"query": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert upstream.requests == []
    r = web_client.post(URL, json={"query": "học bổng bí mật", "max_results": 3}, headers=_auth(web_client))
    assert r.status_code == 200
    assert r.json() == {"backend": "searxng", "results": [{
        "title": "Học bổng", "url": "https://scholarship.example/x", "snippet": "Hạn nộp 30/11",
        "published": "2026-09-30T00:00:00"}]}
    assert dict(httpx.QueryParams(upstream.requests[0].content.decode()))["safesearch"] == "2"  # THPT: strict
    ncs = _auth(web_client, Profile.NCS, "u2")
    assert web_client.post(URL, json={"query": "x"}, headers=ncs).status_code == 200
    assert dict(httpx.QueryParams(upstream.requests[1].content.decode()))["safesearch"] == "1"
    store = web_client.app.state.gw.parent.store
    [(kind, detail, _)] = store.read_audit("u1")
    assert kind == "web_search" and detail == "backend=searxng; results=1"
    assert "bổng" not in detail  # never the query


def test_endpoint_limits_and_errors(web_client: TestClient, upstream: Upstream) -> None:
    h = _auth(web_client)
    assert web_client.post(URL, json={"query": "x", "max_results": 9}, headers=h).status_code == 422
    assert web_client.post(URL, json={"query": "a" * 401}, headers=h).status_code == 422
    r = web_client.post(URL, json={"query": "x"}, headers=_auth(web_client, user="u5"))
    assert r.status_code == 200
    r = web_client.post(URL, json={"query": "y"}, headers=_auth(web_client, user="u5"))
    assert r.status_code == 200
    r = web_client.post(URL, json={"query": "z"}, headers=_auth(web_client, user="u5"))
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    upstream.override = httpx.ReadTimeout("slow")
    r = web_client.post(URL, json={"query": "fresh"}, headers=_auth(web_client, user="u6"))
    assert r.status_code == 504 and r.json()["reason"] == "timeout"
    store = web_client.app.state.gw.parent.store
    assert [d for _, d, _ in store.read_audit("u6")] == ["backend=searxng; results=0; error=504"]


def test_endpoint_not_configured(web_client: TestClient) -> None:
    web_client.app.state.gw.web = WebSearchService()
    r = web_client.post(URL, json={"query": "x"}, headers=_auth(web_client, Profile.NCS))
    assert r.status_code == 503 and r.json()["reason"] == "not_configured"
