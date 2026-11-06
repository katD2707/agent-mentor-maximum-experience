"""/internal/papers/* and PaperService: recorded upstream responses via httpx.MockTransport, no network."""

import httpx
import pytest
from fastapi.testclient import TestClient
from mentor_schemas import Profile

from mentor_gateway.app import create_app
from mentor_gateway.papers import MAX_RESPONSE_BYTES, PaperError, PaperService, RateLimiter, parse_paper_id
from mentor_gateway.sandbox.backends import LocalProcessBackend, SandboxSpec, sandbox_env
from mentor_gateway.sandbox.tokens import SandboxTokens
from mentor_gateway.settings import Settings

ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">ArXiv Query: search_query=all:attention</title>
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <updated>2023-08-02T00:41:18Z</updated>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
      You Need</title>
    <summary>  The dominant sequence transduction models are based on complex recurrent or
convolutional neural networks. """ + b"x" * 1200 + b"""</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <author><name>Jakob Uszkoreit</name></author>
    <author><name>Llion Jones</name></author>
    <author><name>Aidan N. Gomez</name></author>
    <arxiv:comment>15 pages, 5 figures</arxiv:comment>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""

ARXIV_ERROR = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_x</id><title>Error</title>
  <summary>incorrect id format for x</summary></entry>
</feed>"""

S2_SEARCH = {
    "total": 2, "offset": 0, "next": 2,
    "data": [
        {"paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776", "title": "Attention is All you Need",
         "authors": [{"authorId": "1", "name": "Ashish Vaswani"}], "year": 2017,
         "venue": "Neural Information Processing Systems", "abstract": None,
         "url": "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
         "citationCount": 120000, "externalIds": {"ArXiv": "1706.03762", "DOI": None}},
        {"paperId": None, "title": "broken row"},
    ],
}  # fmt: skip

S2_DETAIL = {
    **S2_SEARCH["data"][0],
    "referenceCount": 3,
    "tldr": {"model": "tldr@v2.0.0", "text": "A new simple network architecture, the Transformer."},
    "references": [
        {"paperId": "a" * 40, "title": "Low cited", "year": 2010, "citationCount": 5},
        {"paperId": "b" * 40, "title": "Highly cited", "year": 2014, "citationCount": 9000},
        {"paperId": None, "title": "no id"},
    ],
}


class Upstream:
    """Routes requests to recorded responses and records what was asked."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.override: httpx.Response | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override is not None:
            return self.override
        if request.url.host == "export.arxiv.org":
            if request.url.params.get("id_list") == "9999.99999":
                return httpx.Response(200, content=b'<feed xmlns="http://www.w3.org/2005/Atom"/>')
            return httpx.Response(200, content=ARXIV_FEED)
        if request.url.path.endswith("/paper/search"):
            return httpx.Response(200, json=S2_SEARCH)
        return httpx.Response(200, json=S2_DETAIL)


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
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def service(upstream: Upstream, fake_time: FakeTime) -> PaperService:
    return PaperService(s2_api_key="k", transport=httpx.MockTransport(upstream), monotonic=fake_time.monotonic,
                        sleep=fake_time.sleep)


# ---- PaperService ----------------------------------------------------------------------------


async def test_arxiv_search_parses_atom(service: PaperService, upstream: Upstream) -> None:
    [paper] = await service.search('attention "machine translation"', "arxiv", limit=3, year_from=2017)
    params = upstream.requests[0].url.params
    assert upstream.requests[0].url.host == "export.arxiv.org" and params["max_results"] == "3"
    assert params["search_query"] == ('(all:attention AND all:"machine translation") AND '
                                      "submittedDate:[201701010000 TO 299912312359]")
    assert paper["id"] == "arxiv:1706.03762v7" and paper["title"] == "Attention Is All You Need"
    assert paper["authors"] == ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones"]
    assert paper["author_count"] == 6 and paper["year"] == 2017 and paper["venue"] == "arXiv"
    assert paper["abstract"].startswith("The dominant sequence") and len(paper["abstract"]) <= 800
    assert paper["url"] == "https://arxiv.org/abs/1706.03762v7" and paper["category"] == "cs.CL"


async def test_s2_search_and_detail(service: PaperService, upstream: Upstream) -> None:
    [paper] = await service.search("graph-neural network", "semantic_scholar", limit=5, year_from=2015)
    req = upstream.requests[0]
    assert req.url.path == "/graph/v1/paper/search" and req.headers["x-api-key"] == "k"
    assert req.url.params["query"] == "graph neural network" and req.url.params["year"] == "2015-"
    assert paper["id"] == "s2:204e3073870fae3d05bcbc2f6a8e263d9b72e776" and paper["citation_count"] == 120000
    assert paper["arxiv_id"] == "1706.03762" and paper["abstract"] == ""
    detail = await service.get(paper["id"])
    assert upstream.requests[1].url.path == "/graph/v1/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    assert detail["reference_count"] == 3 and detail["tldr"].startswith("A new simple")
    assert [r["title"] for r in detail["top_references"]] == ["Highly cited", "Low cited"]


async def test_arxiv_get_and_not_found(service: PaperService, upstream: Upstream) -> None:
    paper = await service.get("https://arxiv.org/abs/1706.03762v7")
    assert upstream.requests[0].url.params["id_list"] == "1706.03762v7" and paper["title"]
    with pytest.raises(PaperError) as exc:
        await service.get("arxiv:9999.99999")
    assert exc.value.status == 404


async def test_cache_and_arxiv_pacing(service: PaperService, upstream: Upstream, fake_time: FakeTime) -> None:
    await service.search("attention", "arxiv")
    await service.search("Attention", "arxiv")  # cached (case-insensitive key)
    assert len(upstream.requests) == 1 and fake_time.sleeps == []
    fake_time.now += 1.0
    await service.search("transformer", "arxiv")
    assert len(upstream.requests) == 2 and fake_time.sleeps == [pytest.approx(2.0)]
    fake_time.now += 601  # cache expired
    await service.search("attention", "arxiv")
    assert len(upstream.requests) == 3


@pytest.mark.parametrize(
    "response,status",
    [(httpx.Response(429), 503), (httpx.Response(500), 502), (httpx.Response(404), 404),
     (httpx.Response(200, content=ARXIV_ERROR), 400), (httpx.Response(200, content=b"<not xml"), 502),
     (httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)), 502)],
)  # fmt: skip
async def test_upstream_failures(service: PaperService, upstream: Upstream, response, status) -> None:
    upstream.override = response
    with pytest.raises(PaperError) as exc:
        await service.search("attention", "arxiv")
    assert exc.value.status == status


async def test_timeout_maps_to_504(fake_time: FakeTime) -> None:
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    svc = PaperService(transport=httpx.MockTransport(boom), monotonic=fake_time.monotonic, sleep=fake_time.sleep)
    with pytest.raises(PaperError) as exc:
        await svc.get("s2:" + "c" * 40)
    assert exc.value.status == 504


async def test_only_allowlisted_hosts(service: PaperService, upstream: Upstream) -> None:
    with pytest.raises(PaperError):
        await service._fetch("https://evil.example.com/x", {})
    with pytest.raises(PaperError):
        await service._fetch("http://export.arxiv.org/api/query", {})
    assert upstream.requests == []


@pytest.mark.parametrize(
    "raw,expected",
    [("arxiv:2401.01234v2", ("arxiv", "2401.01234v2")), ("hep-th/9901001", ("arxiv", "hep-th/9901001")),
     ("s2:" + "A" * 40, ("semantic_scholar", "a" * 40)), ("doi:10.1145/3292500.3330919",
     ("semantic_scholar", "DOI:10.1145/3292500.3330919")), ("CorpusId:13756489", ("semantic_scholar", "CorpusId:13756489"))],
)  # fmt: skip
def test_parse_paper_id(raw, expected) -> None:
    assert parse_paper_id(raw) == expected


@pytest.mark.parametrize("raw", ["arxiv:1234; DROP", "hello world", "arxiv:../../x"])
def test_parse_paper_id_rejects(raw) -> None:
    with pytest.raises(PaperError):
        parse_paper_id(raw)


def test_rate_limiter_window(fake_time: FakeTime) -> None:
    rl = RateLimiter(2, monotonic=fake_time.monotonic)
    assert rl.check("u") is None and rl.check("u") is None and rl.check("other") is None
    assert rl.check("u") == pytest.approx(60)
    fake_time.now += 60
    assert rl.check("u") is None


# ---- tokens and backends ------------------------------------------------------------------------


def test_tokens_issue_verify_revoke() -> None:
    tokens = SandboxTokens()
    first = tokens.issue("u1", Profile.NCS)
    second = tokens.issue("u1", Profile.NCS)  # restart replaces the old token
    assert tokens.verify(first) is None and tokens.verify(second).user_id == "u1"
    tokens.revoke("u1")
    assert tokens.verify(second) is None and tokens.verify(None) is None


async def test_local_backend_passes_token_and_revokes(tmp_path, monkeypatch) -> None:
    import subprocess

    from mentor_gateway.sandbox import backends

    captured = {}

    class Proc:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, env, cwd, stdout, stderr):
        captured.update(env=env)
        return Proc()

    async def healthy(url, timeout, alive=lambda: True):
        return None

    monkeypatch.setenv("S2_API_KEY", "secret")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(backends, "wait_healthy", healthy)
    settings = Settings(env="test", data_dir=tmp_path, public_base_url="http://localhost:8000/")
    b = LocalProcessBackend(settings, tokens=SandboxTokens())
    await b.ensure_running(SandboxSpec(user_id="u1", profile=Profile.NCS, workspace_dir=tmp_path))
    env = captured["env"]
    assert env["MENTOR_GATEWAY_URL"] == "http://localhost:8000" and "S2_API_KEY" not in env
    assert b.tokens.verify(env["MENTOR_GATEWAY_TOKEN"]).profile == Profile.NCS
    assert env["MENTOR_HARNESS_TOKEN"] == b.harness_token("u1") != env["MENTOR_GATEWAY_TOKEN"]
    await b.stop("u1")
    assert b.tokens.verify(env["MENTOR_GATEWAY_TOKEN"]) is None


def test_sandbox_gateway_url_override(tmp_path) -> None:
    s = Settings.from_env({"SANDBOX_GATEWAY_URL": "http://gateway:8000", "S2_API_KEY": "k"})
    env = sandbox_env(s, SandboxSpec("u", Profile.NCS, tmp_path), "/workspace", "t")
    assert env["MENTOR_GATEWAY_URL"] == "http://gateway:8000" and env["MENTOR_GATEWAY_TOKEN"] == "t"
    assert s.s2_api_key == "k"


# ---- endpoints ---------------------------------------------------------------------------------


class IdleBackend:
    async def ensure_running(self, spec):  # pragma: no cover - not used here
        raise AssertionError

    async def stop(self, user_id):
        return None

    async def status(self, user_id):
        return "stopped"


@pytest.fixture
def papers_client(settings, upstream: Upstream, service: PaperService):
    settings = settings.model_copy(update={"paper_requests_per_minute": 3})
    app = create_app(settings, backend=IdleBackend())
    app.state.gw.papers = service
    with TestClient(app) as c:
        yield c


def _auth(client: TestClient, profile: Profile = Profile.NCS, user: str = "u1") -> dict:
    return {"Authorization": f"Bearer {client.app.state.gw.tokens.issue(user, profile)}"}


def test_endpoint_auth(papers_client: TestClient, upstream: Upstream) -> None:
    assert papers_client.get("/internal/papers/search", params={"q": "x"}).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert papers_client.get("/internal/papers/search", params={"q": "x"}, headers=bad).status_code == 401
    thpt = _auth(papers_client, Profile.THPT, "u2")
    assert papers_client.get("/internal/papers/search", params={"q": "x"}, headers=thpt).status_code == 403
    assert upstream.requests == []


def test_endpoint_search_get_and_rate_limit(papers_client: TestClient, upstream: Upstream) -> None:
    h = _auth(papers_client)
    r = papers_client.get("/internal/papers/search", params={"q": "attention", "limit": 2}, headers=h)
    assert r.status_code == 200 and r.json()["results"][0]["id"] == "arxiv:1706.03762v7"
    r = papers_client.get("/internal/papers/get", params={"id": "s2:" + "d" * 40}, headers=h)
    assert r.status_code == 200 and r.json()["paper"]["top_references"]
    r = papers_client.get("/internal/papers/get", params={"id": "nonsense id"}, headers=h)
    assert r.status_code == 400
    r = papers_client.get("/internal/papers/get", params={"id": "arxiv:1706.03762"}, headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    other = _auth(papers_client, user="u3")  # the limit is per learner
    assert papers_client.get("/internal/papers/search", params={"q": "attention"}, headers=other).status_code == 200
    assert papers_client.get("/internal/papers/search", params={"q": "x", "limit": 50}, headers=other).status_code == 422
