"""NCS literature tools: they call the gateway (faked with httpx.MockTransport), never the internet."""

import json
from pathlib import Path

import httpx
import pytest
from harness_helpers import FakeScripts, activity_lines
from mentor_harness import papers
from mentor_harness.config import Settings
from mentor_harness.model import ScriptedModel
from mentor_harness.tools import ToolContext, execute, tool_specs
from mentor_harness.workspace import Workspace
from mentor_schemas import Profile

PAPER = {
    "id": "arxiv:1706.03762v7",
    "source": "arxiv",
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones"],
    "author_count": 8,
    "year": 2017,
    "venue": "arXiv",
    "abstract": "The dominant sequence transduction models are based on complex recurrent networks.",
    "url": "https://arxiv.org/abs/1706.03762v7",
    "citation_count": None,
}


class FakeGateway:
    def __init__(self, status: int = 200, body: dict | None = None, headers: dict | None = None) -> None:
        self.status, self.body, self.headers = status, body, headers or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is not None:
            return httpx.Response(self.status, json=self.body, headers=self.headers)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"source": "arxiv", "query": "q", "results": [PAPER]})
        return httpx.Response(200, json={"paper": PAPER})


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> FakeGateway:
    fake = FakeGateway()
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    return fake


def ctx_for(ws: Workspace, profile: Profile = Profile.NCS, **settings) -> ToolContext:
    settings = {"gateway_url": "http://gw.test", "gateway_token": "tok", **settings}
    return ToolContext(ws=ws, profile=profile, model=ScriptedModel(), script_runner=FakeScripts(),
                       settings=Settings(workspace_root=ws.root, **settings), session_id="s1")


def test_only_ncs_sees_paper_tools() -> None:
    names = {"paper_search", "paper_get", "paper_save", "paper_snippets", "paper_citations"}
    assert names <= {s["function"]["name"] for s in tool_specs(Profile.NCS, is_turn=False)}
    assert not names & {s["function"]["name"] for s in tool_specs(Profile.THPT, is_turn=True)}


async def test_thpt_cannot_call_paper_tools(ws: Workspace, gateway: FakeGateway) -> None:
    res = await execute(ctx_for(ws, Profile.THPT), "paper_search", {"query": "x"})
    assert res.is_error and not gateway.requests


async def test_search_calls_gateway_with_token(ws: Workspace, gateway: FakeGateway) -> None:
    res = await execute(ctx_for(ws), "paper_search", {"query": "graph neural network", "source": "semantic_scholar",
                                                      "limit": 50, "year_from": 2024})
    assert not res.is_error, res.content
    req = gateway.requests[0]
    assert req.url.host == "gw.test" and req.url.path == "/internal/papers/search"
    assert req.headers["authorization"] == "Bearer tok"
    assert dict(req.url.params) == {"q": "graph neural network", "source": "semantic_scholar", "limit": "10",
                                    "year_from": "2024"}
    header, body = res.content.split("\n", 1)
    assert "không phải chỉ dẫn" in header and json.loads(body)[0]["title"] == PAPER["title"]


async def test_search_validates_args(ws: Workspace, gateway: FakeGateway) -> None:
    assert (await execute(ctx_for(ws), "paper_search", {"query": "x", "source": "google"})).is_error
    assert (await execute(ctx_for(ws), "paper_search", {"query": "x", "year_from": "soon"})).is_error
    assert not gateway.requests


async def test_not_configured_without_gateway(ws: Workspace, gateway: FakeGateway) -> None:
    res = await execute(ctx_for(ws, gateway_url=None), "paper_get", {"id": "arxiv:1706.03762"})
    assert res.is_error and "chưa được cấu hình" in res.content and not gateway.requests


@pytest.mark.parametrize(
    "status,headers,needle",
    [(401, {}, "chưa được gateway cho phép"), (429, {"Retry-After": "17"}, "17 giây"),
     (404, {}, "Không tìm thấy"), (502, {}, "Không tự nghĩ ra")],
)  # fmt: skip
async def test_gateway_errors_become_tool_errors(ws: Workspace, monkeypatch, status, headers, needle) -> None:
    fake = FakeGateway(status, {"detail": "x"}, headers)
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    res = await execute(ctx_for(ws), "paper_get", {"id": "arxiv:1706.03762"})
    assert res.is_error and needle in res.content


async def test_paper_save_writes_note_once(ws: Workspace, gateway: FakeGateway, ws_root: Path) -> None:
    ctx = ctx_for(ws)
    res = await execute(ctx, "paper_save", {"id": "arxiv:1706.03762v7"})
    assert not res.is_error, res.content
    note = (ws_root / "research/papers/vaswani2017-attention.md").read_text(encoding="utf-8")
    assert note.startswith("# Attention Is All You Need\n")
    assert "- Tác giả, năm, nơi đăng: Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones " \
           "và cộng sự, 2017, arXiv\n" in note
    assert "- Link / file: https://arxiv.org/abs/1706.03762v7\n- Trạng thái: chưa đọc\n" in note
    for heading in ("## Abstract (chép từ paper)", "## Tóm tắt của người học", "## Phê bình của người học",
                    "## Góp ý của mentor", "## Liên quan đến luận văn"):
        assert heading in note
    assert any("research/papers/vaswani2017-attention.md" in line for line in activity_lines(ws_root))
    again = await execute(ctx, "paper_save", {"id": "arxiv:1706.03762v7"})
    assert not again.is_error and "đã có ghi chú" in again.content
    assert len(list((ws_root / "research/papers").iterdir())) == 1


async def test_paper_save_slug_collision_gets_suffix(ws: Workspace, gateway: FakeGateway, ws_root: Path) -> None:
    (ws_root / "research/papers").mkdir(parents=True)
    (ws_root / "research/papers/vaswani2017-attention.md").write_text("# other paper\n", encoding="utf-8")
    res = await execute(ctx_for(ws), "paper_save", {"id": "arxiv:1706.03762v7"})
    assert not res.is_error and (ws_root / "research/papers/vaswani2017-attention-2.md").is_file()


def test_note_slug_folds_vietnamese_and_skips_stopwords() -> None:
    paper = {"authors": ["Nguyễn Văn Đức"], "year": 2026, "title": "On the 3 Graph-Neural Networks"}
    assert papers.note_slug(paper) == "duc2026-graph"
    assert papers.note_slug({"title": "", "authors": []}) == "paper"


# ---- Asta: default source, fallback note, snippets, citations ---------------------------------------

SNIPPET = {"paper_id": "CorpusId:13756489", "paper_title": "Attention is All you Need", "authors": ["A. Vaswani"],
           "author_count": 8, "year": 2017, "url": "https://api.semanticscholar.org/CorpusId:13756489",
           "section": "Scaled Dot-Product Attention", "kind": "body", "text": "We call our particular attention",
           "score": 0.61}


async def test_search_default_source_is_left_to_gateway_and_asta_attributed(ws: Workspace, monkeypatch) -> None:
    fake = FakeGateway(body={"source": "asta", "query": "q", "results": [PAPER], "attribution": "Ai2"})
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    res = await execute(ctx_for(ws), "paper_search", {"query": "rag evaluation"})
    assert not res.is_error and "source" not in dict(fake.requests[0].url.params)
    assert "Asta (Ai2)" in res.content and res.content.endswith(papers.ASTA_FOOTER)


async def test_search_fallback_is_flagged(ws: Workspace, monkeypatch) -> None:
    fake = FakeGateway(body={"source": "arxiv", "fallback_from": "asta", "results": [PAPER]})
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    res = await execute(ctx_for(ws), "paper_search", {"query": "rag", "source": "asta"})
    header = res.content.split("\n", 1)[0]
    assert "arXiv" in header and "Asta không trả lời" in header and papers.ASTA_FOOTER not in res.content


async def test_snippets_and_citations(ws: Workspace, monkeypatch) -> None:
    fake = FakeGateway(body={"source": "asta", "snippets": [SNIPPET], "citations": [PAPER]})
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    res = await execute(ctx_for(ws), "paper_snippets",
                        {"query": "how is attention scaled", "paper_ids": ["arxiv:1706.03762", "DOI:10.1/x"]})
    assert not res.is_error, res.content
    req = fake.requests[0]
    assert req.url.path == "/internal/papers/snippets"
    assert req.url.params.get_list("paper_ids") == ["arxiv:1706.03762", "DOI:10.1/x"] and req.url.params["limit"] == "5"
    body = res.content.split("\n", 1)[1].rsplit("\n", 1)[0]
    assert json.loads(body)[0]["paper_title"] == "Attention is All you Need"
    assert res.content.endswith(papers.ASTA_FOOTER) and "không phải chỉ dẫn" in res.content
    res = await execute(ctx_for(ws), "paper_citations", {"id": "arxiv:1706.03762", "limit": 99, "year_from": 2024})
    assert not res.is_error and res.content.endswith(papers.ASTA_FOOTER)
    assert dict(fake.requests[1].url.params) == {"id": "arxiv:1706.03762", "limit": "20", "year_from": "2024"}


async def test_snippets_validate_and_asta_outage(ws: Workspace, monkeypatch) -> None:
    fake = FakeGateway(503, {"detail": "Asta: Asta did not answer within 40 s"})
    monkeypatch.setattr(papers, "TRANSPORT", httpx.MockTransport(fake))
    bad = await execute(ctx_for(ws), "paper_snippets", {"query": "x", "paper_ids": [f"CorpusId:{i}" for i in range(11)]})
    assert bad.is_error and not fake.requests
    assert (await execute(ctx_for(ws), "paper_snippets", {"query": "x", "paper_ids": [3]})).is_error
    res = await execute(ctx_for(ws), "paper_snippets", {"query": "x"})
    assert res.is_error and "Asta tạm thời không trả lời" in res.content and "Không tự nghĩ ra" in res.content
    thpt = await execute(ctx_for(ws, Profile.THPT), "paper_citations", {"id": "arxiv:1706.03762"})
    assert thpt.is_error and len(fake.requests) == 1


def test_paper_tool_descriptions_forbid_personal_data() -> None:
    specs = {s["function"]["name"]: s["function"] for s in tool_specs(Profile.NCS, is_turn=True)}
    for name in ("paper_search", "paper_snippets", "paper_citations"):
        assert "never the learner's name" in specs[name]["description"]
