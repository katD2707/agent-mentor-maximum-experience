"""Asta backend of /internal/papers/* (asta.py, PaperService): MCP over httpx.MockTransport, no network.

Fixtures in fixtures/asta/ are Asta responses recorded on 2026-10-30 without an API key, except
`snippet_search.synthetic.sse`: anonymous snippet_search never answered (SSE pings only), so that one follows
Semantic Scholar's documented /snippet/search shape.
"""

import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from mentor_schemas import Profile

from mentor_gateway.app import create_app
from mentor_gateway.asta import ASTA_ATTRIBUTION, AstaClient, AstaError, parse_sse, tool_result
from mentor_gateway.papers import PaperError, PaperService, asta_paper_id

FIXTURES = Path(__file__).parent / "fixtures" / "asta"
ASTA_URL = "https://asta-tools.allen.ai/mcp/v1"
TOOL_FIXTURES = {
    "search_papers_by_relevance": "search_papers_by_relevance.sse",
    "get_paper": "get_paper.sse",
    "get_citations": "get_citations.sse",
    "snippet_search": "snippet_search.synthetic.sse",
}
ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2401.00001v1</id>
<published>2024-01-01T00:00:00Z</published><title>Fallback paper</title><summary>s</summary>
<author><name>A B</name></author></entry></feed>"""


def _sse(name: str, rid: int) -> bytes:
    body = (FIXTURES / name).read_text(encoding="utf-8")
    return re.sub(r'"jsonrpc": ?"2.0", ?"id": ?\d+', f'"jsonrpc":"2.0","id":{rid}', body).encode()


class FakeAsta:
    """Plays the Asta MCP server (recorded responses) plus arXiv / S2 for the fallbacks."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []  # (tool, arguments)
        self.methods: list[str] = []
        self.headers: list[httpx.Headers] = []
        self.fail: dict = {}  # tool -> response, or a function of the request id
        self.session_id: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "export.arxiv.org":
            self.methods.append("arxiv")
            return httpx.Response(200, content=ARXIV_FEED)
        if request.url.host == "api.semanticscholar.org":
            self.methods.append("s2")
            return httpx.Response(200, json={"paperId": "f" * 40, "title": "From S2 REST"})
        msg = json.loads(request.content)
        self.methods.append(msg["method"])
        self.headers.append(request.headers)
        sse = {"content-type": "text/event-stream"}
        if self.session_id:
            sse["mcp-session-id"] = self.session_id
        if msg["method"] == "initialize":
            return httpx.Response(200, content=_sse("initialize.sse", msg["id"]), headers=sse)
        if msg["method"] == "notifications/initialized":
            return httpx.Response(202)
        name, args = msg["params"]["name"], msg["params"]["arguments"]
        self.calls.append((name, args))
        if name in self.fail:
            fail = self.fail[name]
            return fail(msg["id"]) if callable(fail) else fail
        return httpx.Response(200, content=_sse(TOOL_FIXTURES[name], msg["id"]), headers=sse)


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def asta() -> FakeAsta:
    return FakeAsta()


@pytest.fixture
def clock() -> FakeTime:
    return FakeTime()


@pytest.fixture
def service(asta: FakeAsta, clock: FakeTime) -> PaperService:
    return PaperService(
        asta_url=ASTA_URL,
        asta_api_key="k",
        transport=httpx.MockTransport(asta),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


# ---- MCP client ------------------------------------------------------------------------------


def test_parse_sse_skips_pings_and_tool_result_shapes() -> None:
    [msg] = parse_sse(_sse("get_citations.sse", 7))
    assert msg["id"] == 7 and tool_result(msg["result"])[0]["citingPaper"]["title"].startswith("Evaluation")
    [detail] = parse_sse(_sse("get_paper.sse", 1))  # get_paper: text content only, no structuredContent
    assert tool_result(detail["result"])["paperId"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    for text, status in [("Paper not found", 404), ("HTTP 429 Too Many Requests", 503), ("boom", 502)]:
        with pytest.raises(AstaError) as exc:
            tool_result({"isError": True, "content": [{"type": "text", "text": text}]})
        assert exc.value.status == status


async def test_client_initializes_once_and_keeps_session(asta: FakeAsta) -> None:
    asta.session_id = "sess-1"
    client = AstaClient(api_key="secret", transport=httpx.MockTransport(asta))
    await client.call_tool("get_citations", {"paper_id": "x"})
    await client.call_tool("get_citations", {"paper_id": "y"})
    assert asta.methods == ["initialize", "notifications/initialized", "tools/call", "tools/call"]
    assert "mcp-session-id" not in asta.headers[0] and asta.headers[-1]["mcp-session-id"] == "sess-1"
    assert all(h["x-api-key"] == "secret" for h in asta.headers)
    assert "text/event-stream" in asta.headers[0]["accept"]


async def test_client_errors(asta: FakeAsta) -> None:
    client = AstaClient(transport=httpx.MockTransport(asta))
    asta.fail["get_paper"] = httpx.Response(429)
    with pytest.raises(AstaError) as exc:
        await client.call_tool("get_paper", {})
    assert exc.value.status == 503
    asta.fail["get_paper"] = httpx.Response(
        200, json={"jsonrpc": "2.0", "id": 99, "result": {}}
    )  # reply for another request id
    with pytest.raises(AstaError) as exc:
        await client.call_tool("get_paper", {})
    assert exc.value.status == 502
    assert "x-api-key" not in asta.headers[0]
    with pytest.raises(ValueError):
        AstaClient("http://asta-tools.allen.ai/mcp/v1")


# ---- PaperService with Asta --------------------------------------------------------------------


async def test_asta_search(service: PaperService, asta: FakeAsta) -> None:
    assert service.default_source == "arxiv"  # Asta takes ~30 s per search, too slow to be the chat default
    found = await service.search_with_source("retrieval augmented generation evaluation", "asta", 3, 2023)
    [(tool, args)] = asta.calls
    assert tool == "search_papers_by_relevance" and args["limit"] == 3 and args["publication_date_range"] == "2023:"
    assert args["keyword"] == "retrieval augmented generation evaluation" and "abstract" in args["fields"]
    assert found["source"] == "asta" and "fallback_from" not in found
    first = found["results"][0]
    assert first["id"] == "s2:79e57387a664a5d7b128b2790a8f38f827e09124" and first["source"] == "asta"
    assert first["arxiv_id"] == "2504.14891" and first["year"] == 2025 and first["citation_count"] == 57
    assert len(first["authors"]) == 5 and first["author_count"] == 8 and len(first["abstract"]) <= 800
    await service.search("Retrieval augmented generation evaluation", "asta", 3, 2023)  # cached
    assert len(asta.calls) == 1


async def test_asta_search_falls_back_to_arxiv_then_cools_down(
    service: PaperService, asta: FakeAsta, clock: FakeTime
) -> None:
    asta.fail["search_papers_by_relevance"] = httpx.Response(503)
    found = await service.search_with_source("graph neural network", "asta", 2)
    assert found["source"] == "arxiv" and found["fallback_from"] == "asta"
    assert found["results"][0]["title"] == "Fallback paper"
    found = await service.search_with_source("another query", "asta", 2)  # Asta in cooldown: straight to arXiv
    assert found["source"] == "arxiv" and len(asta.calls) == 1
    clock.now += 121
    del asta.fail["search_papers_by_relevance"]
    assert (await service.search_with_source("third", "asta", 2))["source"] == "asta"


async def test_without_asta_default_is_arxiv(asta: FakeAsta, clock: FakeTime) -> None:
    svc = PaperService(
        asta_url="off", transport=httpx.MockTransport(asta), monotonic=clock.monotonic, sleep=clock.sleep
    )
    assert svc.asta is None and svc.default_source == "arxiv"
    anonymous = PaperService(asta_url=ASTA_URL)  # works, but slow: arXiv stays the default without a key
    assert anonymous.asta is not None and anonymous.default_source == "arxiv"
    found = await svc.search_with_source("x y", "asta", 2)
    assert found == {"source": "arxiv", "fallback_from": "asta", "results": found["results"]}
    with pytest.raises(PaperError) as exc:
        await svc.snippets("attention")
    assert exc.value.status == 503
    assert PaperService(asta_url="https://evil.example.com/mcp").asta is None  # not allowlisted


async def test_get_via_asta_with_s2_fallback(service: PaperService, asta: FakeAsta) -> None:
    paper = await service.get("s2:204e3073870fae3d05bcbc2f6a8e263d9b72e776")
    assert asta.calls[0] == (
        "get_paper",
        {"paper_id": "204e3073870fae3d05bcbc2f6a8e263d9b72e776", "fields": asta.calls[0][1]["fields"]},
    )
    assert paper["source"] == "asta" and paper["title"] == "Attention is All you Need"
    assert paper["tldr"].startswith("A new simple network") and paper["reference_count"] == 41
    assert len(paper["top_references"]) == 10 and paper["top_references"][0]["id"].startswith("s2:")
    assert paper["citation_count"] == 200409 and paper["publication_date"] == "2017-06-12"
    asta.fail["get_paper"] = httpx.Response(502)
    paper = await service.get("DOI:10.1/xyz")
    assert paper["title"] == "From S2 REST" and asta.methods[-1] == "s2"
    asta.fail["get_paper"] = lambda rid: httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"isError": True, "content": [{"type": "text", "text": "Error: Paper not found"}]},
        },
    )
    service._asta_down_until.clear()
    with pytest.raises(PaperError) as exc:
        await service.get("CorpusId:1")
    assert exc.value.status == 404 and asta.methods[-1] == "tools/call"  # no S2 retry for a missing paper


async def test_citations_sorted_and_unescaped(service: PaperService, asta: FakeAsta) -> None:
    cites = await service.citations("arxiv:1706.03762v7", limit=2, year_from=2024)
    tool, args = asta.calls[0]
    assert tool == "get_citations" and args["paper_id"] == "ARXIV:1706.03762" and args["limit"] == 10
    assert args["publication_date_range"] == "2024:"
    assert len(cites) == 2 and all(c["id"].startswith("s2:") and c["year"] == 2027 for c in cites)
    titles = [c["title"] for c in await service.citations("arxiv:1706.03762", limit=20)]
    assert "Physics-Informed Neural Networks for process systems: Estimating the unknown dynamics" in titles
    venues = [c["venue"] for c in await service.citations("arxiv:1706.03762", limit=20)]
    assert "Computers & Chemical Engineering" in venues


async def test_snippets(service: PaperService, asta: FakeAsta, clock: FakeTime) -> None:
    [snip] = await service.snippets("scaled dot-product attention", ["arxiv:1706.03762", "s2:" + "A" * 40], 3)
    tool, args = asta.calls[0]
    assert tool == "snippet_search" and args["limit"] == 3
    assert args["paper_ids"] == "ARXIV:1706.03762," + "a" * 40
    assert snip["paper_id"] == "CorpusId:13756489" and snip["paper_title"] == "Attention is All you Need"
    assert snip["url"] == "https://api.semanticscholar.org/CorpusId:13756489"
    assert snip["section"] == "Scaled Dot-Product Attention" and snip["score"] == 0.612
    assert snip["text"].startswith("3.2.1 Scaled") and snip["author_count"] == 6
    with pytest.raises(PaperError) as exc:
        await service.snippets("x", [f"CorpusId:{i}" for i in range(11)])
    assert exc.value.status == 400
    asta.fail["snippet_search"] = httpx.Response(504)
    with pytest.raises(PaperError) as exc:
        await service.snippets("new query")
    assert exc.value.status == 502  # HTTP 504 from Asta = bad gateway for us
    assert clock.sleeps == [pytest.approx(0.3)]  # Asta call starts are paced (0.3 s with a key)


def test_asta_paper_id() -> None:
    assert asta_paper_id("arxiv:2106.15928v2") == "ARXIV:2106.15928"
    assert asta_paper_id("doi:10.18653/v1/N18-3011") == "DOI:10.18653/v1/N18-3011"
    assert asta_paper_id("s2:" + "B" * 40) == "b" * 40


# ---- endpoints ---------------------------------------------------------------------------------


class IdleBackend:
    async def ensure_running(self, spec):  # pragma: no cover
        raise AssertionError

    async def stop(self, user_id):
        return None

    async def status(self, user_id):
        return "stopped"


@pytest.fixture
def client(settings, service: PaperService):
    app = create_app(settings, backend=IdleBackend())
    app.state.gw.papers = service
    with TestClient(app) as c:
        yield c


def _auth(client: TestClient, profile: Profile = Profile.NCS) -> dict:
    return {"Authorization": f"Bearer {client.app.state.gw.tokens.issue('u1', profile)}"}


def test_endpoints(client: TestClient, asta: FakeAsta) -> None:
    h = _auth(client)
    r = client.get("/internal/papers/search", params={"q": "rag evaluation", "source": "asta", "limit": 3}, headers=h)
    assert r.status_code == 200 and r.json()["source"] == "asta" and r.json()["attribution"] == ASTA_ATTRIBUTION
    r = client.get(
        "/internal/papers/snippets",
        headers=h,
        params=[("q", "attention"), ("paper_ids", "arxiv:1706.03762,CorpusId:5"), ("paper_ids", "s2:" + "c" * 40)],
    )
    assert r.status_code == 200 and r.json()["snippets"][0]["paper_id"] == "CorpusId:13756489"
    assert asta.calls[-1][1]["paper_ids"] == "ARXIV:1706.03762,CorpusId:5," + "c" * 40
    r = client.get("/internal/papers/citations", params={"id": "arxiv:1706.03762", "limit": 5}, headers=h)
    assert r.status_code == 200 and r.json()["attribution"] == ASTA_ATTRIBUTION and r.json()["citations"]
    assert client.get("/internal/papers/citations", params={"id": "x", "limit": 21}, headers=h).status_code == 422
    assert client.get("/internal/papers/snippets", params={"q": "x", "limit": 11}, headers=h).status_code == 422
    assert client.get("/internal/papers/citations", params={"id": "not an id"}, headers=h).status_code == 400
    r = client.get("/internal/papers/get", params={"id": "arxiv:2401.00001"}, headers=h)
    assert r.status_code == 200 and r.json()["source"] == "arxiv" and "attribution" not in r.json()
    thpt = _auth(client, Profile.THPT)
    assert client.get("/internal/papers/snippets", params={"q": "x"}, headers=thpt).status_code == 403
