"""Paper research library: offline tests with fakes (no network, no model), plus one opt-in live arXiv call.

Live: MENTOR_LIVE_ARXIV=1 pytest -s services/gateway/tests/test_gw_research_papers.py -k live
"""

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mentor_gateway.research import papers
from mentor_gateway.research.vendor.deeptutor import research_primitives as prim
from mentor_gateway.research.vendor.deeptutor.paper_search_tool import ArxivSearchTool

YEAR = datetime.now().year


def result(arxiv_id: str, title: str, year: int, *, version: str = "v1", summary: str = "An  abstract\nover lines."):
    return SimpleNamespace(
        entry_id=f"http://arxiv.org/abs/{arxiv_id}{version}", title=title, summary=summary,
        published=datetime(year, 5, 1, tzinfo=UTC), authors=[SimpleNamespace(name="Ada Lovelace"), SimpleNamespace(name="Alan Turing")])


class FakeArxivClient:
    def __init__(self, rows):
        self.rows = rows

    def results(self, search):
        return iter(self.rows)


def tool(rows) -> ArxivSearchTool:
    t = ArxivSearchTool()
    t.client = FakeArxivClient(rows)
    return t


class FakeSearcher:
    """Stands in for ArxivSearchTool in frontier discovery; records queries."""

    def __init__(self, by_query=None, fail_on=()):
        self.by_query, self.fail_on, self.queries = by_query or {}, set(fail_on), []

    async def search_papers(self, query, max_results, years_limit, sort_by):
        self.queries.append(query)
        if query in self.fail_on:
            raise RuntimeError("boom")
        return self.by_query.get(query, [])


def raw(arxiv_id, title, year=YEAR):
    return {"arxiv_id": arxiv_id, "title": title, "authors": ["A"], "year": year, "abstract": "abs",
            "url": f"http://arxiv.org/abs/{arxiv_id}v1", "published": f"{year}-05-01T00:00:00+00:00"}


# ---- search_arxiv -------------------------------------------------------------------------------------------------

async def test_search_normalises_results():
    out = await papers.search_arxiv("graph neural nets", 5, 3, "relevance", searcher=tool([result("2401.00001", "Paper A", YEAR)]))
    assert len(out) == 1
    p = out[0]
    assert p.arxiv_id == "2401.00001"  # version stripped
    assert p.title == "Paper A" and p.year == YEAR
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.abstract == "An abstract over lines."  # whitespace collapsed
    assert p.url == "http://arxiv.org/abs/2401.00001v1" and p.published.startswith(f"{YEAR}-05-01")


async def test_search_dedupes_versions():
    rows = [result("2401.00001", "Paper A", YEAR, version="v1"), result("2401.00001", "Paper A", YEAR, version="v2"),
            result("2401.00002", "Paper B", YEAR)]
    out = await papers.search_arxiv("x y", 5, 3, searcher=tool(rows))
    assert [p.arxiv_id for p in out] == ["2401.00001", "2401.00002"]


async def test_search_year_filter_and_limit():
    rows = [result("2001.00001", "Old", YEAR - 10), result("2401.00001", "New", YEAR), result("2401.00002", "Newer", YEAR - 1),
            result("2401.00003", "Third", YEAR)]
    assert [p.title for p in await papers.search_arxiv("q", 5, 3, searcher=tool(rows))] == ["New", "Newer", "Third"]
    assert (await papers.search_arxiv("q", 5, None, searcher=tool(rows)))[0].title == "Old"
    assert len(await papers.search_arxiv("q", 2, 3, searcher=tool(rows))) == 2


async def test_search_empty_query_and_errors_are_empty():
    assert await papers.search_arxiv("   ", searcher=tool([])) == []

    class Broken:
        def results(self, search):
            raise ValueError("unexpected")

    t = ArxivSearchTool()
    t.client = Broken()
    assert await papers.search_arxiv("q", searcher=t) == []


# ---- discover_frontier --------------------------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    async def complete(self, alias, messages, *, max_tokens=2000, temperature=0.3):
        self.calls.append((alias, messages))
        if self.exc:
            raise self.exc
        return self.reply


async def test_frontier_parses_llm_queries_and_dedupes():
    llm = FakeLLM('Sure:\n{"queries": ["sparse attention methods", "sparse attention methods", "long context memory", "x", 7]}')
    s = FakeSearcher({"sparse attention methods": [raw("2401.00001", "A"), raw("2401.00002", "B")],
                      "long context memory": [raw("2401.00001", "A"), raw("2401.00003", "C")]})
    out = await papers.discover_frontier("Transformers\nmy notes on attention and memory", "efficiency", 5, 3, llm=llm, searcher=s)
    assert out.query_source == "llm"
    assert out.queries == ["sparse attention methods", "long context memory"]  # dup, one-word and non-string dropped
    assert [p.arxiv_id for p in out.papers] == ["2401.00001", "2401.00002", "2401.00003"]
    assert out.papers[0].source_query == "sparse attention methods"
    assert out.status == "papers_found" and "Transformers" in out.report
    alias, messages = llm.calls[0]
    assert alias == "mentor-chat" and messages[0]["role"] == "system"
    assert "Learner focus: efficiency" in messages[1]["content"] and "my notes on attention" in messages[1]["content"]


@pytest.mark.parametrize("llm", [FakeLLM("I cannot do that."), FakeLLM("[1, 2]"), FakeLLM("[oops"),
                                 FakeLLM(exc=RuntimeError("quota")), None])
async def test_frontier_falls_back_when_llm_output_is_bad(llm):
    s = FakeSearcher()
    out = await papers.discover_frontier("reinforcement learning", "", 3, 3, llm=llm, searcher=s)
    assert out.query_source == "fallback"
    assert out.queries == ["reinforcement learning", "recent advances reinforcement learning",
                           "open challenges reinforcement learning"]
    assert s.queries == out.queries
    assert out.status == "papers_not_found"


async def test_frontier_fallback_prefers_focus_then_keywords_and_records_search_errors():
    s = FakeSearcher({"safe rl": [raw("2401.00001", "A")]}, fail_on=["recent advances safe rl"])
    out = await papers.discover_frontier("RL", "safe rl", 3, 3, llm=None, searcher=s)
    assert out.queries[0] == "safe rl"
    assert out.query_errors == ["recent advances safe rl: boom"]
    assert [p.arxiv_id for p in out.papers] == ["2401.00001"]
    kw = await papers.discover_frontier("RL", "", 3, 3, keywords=["bandit-theory.pdf"], llm=None, searcher=FakeSearcher())
    assert kw.queries[0] == "bandit theory"


async def test_frontier_max_papers_is_clamped_to_10():
    s = FakeSearcher({"a b": [raw(f"2401.{i:05d}", f"T{i}") for i in range(1, 16)]})
    out = await papers.discover_frontier("t", "", 99, 3, llm=FakeLLM('{"queries": ["a b"]}'), searcher=s)
    assert len(out.papers) == 10


# ---- literature_pass ----------------------------------------------------------------------------------------------

def feed(entries):
    items = "".join(
        f"<entry><id>http://arxiv.org/abs/{i}</id><title> {t}\n x </title><summary> Sum  {t} </summary>"
        f"<published>2025-03-01T00:00:00Z</published><updated>2025-03-02T00:00:00Z</updated>"
        f"<author><name>Ada</name></author><author><name>Alan</name></author></entry>" for i, t in entries)
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{items}</feed>'.encode()


@pytest.fixture
def research_client(monkeypatch):
    monkeypatch.setattr(prim, "ARXIV_INTERVAL", 0.0)
    monkeypatch.setattr(prim, "_NEXT_API", 0.0)
    seen: list[str] = []
    answers = {"topic": [("2501.00001v1", "One"), ("2501.00002v1", "Two")], "f1": [("2501.00001v2", "One"), ("2501.00003v1", "Three")]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "export.arxiv.org"
        q = parse_qs(urlsplit(str(request.url)).query)["search_query"][0]
        seen.append(q)
        return httpx.Response(200, content=feed(answers.get(q, [])))

    client = prim.ResearchClient(client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client.seen = seen
    return client


async def test_literature_pass_matrix_shape_and_caveat(research_client):
    out = await papers.literature_pass("topic", ["f1"], client=research_client)
    assert research_client.seen == ["topic", "f1"]
    assert [(s.query, s.count) for s in out.searches] == [("topic", 2), ("f1", 2)]
    assert [p.arxiv_id for p in out.papers] == ["2501.00001v2", "2501.00002v1", "2501.00003v1"]  # deduped across versions
    assert out.papers[0].year == 2025 and out.papers[0].title == "One x"
    assert len(out.matrix) == len(out.papers) == 3
    row = out.matrix[1]
    assert row.source == "2501.00002v1" and row.authors == ["Ada", "Alan"] and row.claim_evidence == "Sum Two"
    assert row.url == "https://arxiv.org/abs/2501.00002v1"
    assert row.evidence_level == "primary_abstract"
    assert row.agreement == row.contention == "requires_full_text_comparison"
    assert "Abstracts alone do not establish consensus" in out.caveat
    assert "not an exhaustive systematic review" in out.coverage


async def test_literature_pass_followup_limit(research_client):
    out = await papers.literature_pass("topic", ["a", "b", "c"], client=research_client)
    assert len(out.searches) == 4  # topic + 3 follow-ups is allowed
    with pytest.raises(papers.ResearchError, match="at most three"):
        await papers.literature_pass("topic", ["a", "b", "c", "d"], client=research_client)
    assert len(research_client.seen) == 4  # the refused pass made no request


def test_feed_parser_rejects_entities_and_foreign_hosts():
    bomb = b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "x">]><feed xmlns="http://www.w3.org/2005/Atom"/>'
    with pytest.raises(prim.ResearchError):
        prim.parse_feed(bomb)
    with pytest.raises(prim.ResearchError):
        prim.arxiv_id("https://evil.example/abs/2401.00001")


# ---- live: real arXiv API, no key ----------------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.skipif(os.environ.get("MENTOR_LIVE_ARXIV") != "1", reason="set MENTOR_LIVE_ARXIV=1 to call the real arXiv API")
async def test_live_arxiv_search():
    out = await papers.search_arxiv("attention is all you need transformer", max_results=3, years_limit=None)
    print([(p.arxiv_id, p.year, p.title[:60]) for p in out])
    assert out, "arXiv returned nothing (rate limited?)"
    assert all(p.arxiv_id and p.title and p.url.startswith("http") and p.year for p in out)
