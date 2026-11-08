"""Paper research library for the "Nghiên cứu" feature: arXiv search, frontier discovery, literature pass.

Thin async wrapper over the vendored DeepTutor code (see `vendor/deeptutor/NOTICE`). No API endpoints use it yet.
Network: arXiv only, no key needed; the vendored 3 s pacing, retries and timeouts apply. The one model call
(`discover_frontier`) goes through the model router with `ModelAlias.CHAT`; without an `llm` it falls back to
deterministic queries built from the focus, keywords and topic.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from mentor_schemas import ModelAlias
from pydantic import BaseModel, Field

from mentor_gateway.ask.llm import ChatLLM

from .vendor.deeptutor import knowledge_frontier as _frontier
from .vendor.deeptutor import research_primitives as _prim
from .vendor.deeptutor.paper_search_tool import ArxivSearchTool

ResearchError = _prim.ResearchError
LITERATURE_CAVEAT = _prim.LITERATURE_CAVEAT
MAX_FOLLOWUPS = 3


class Paper(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    url: str = ""
    published: str = ""
    source_query: str | None = None  # frontier discovery: the query that found it


class FrontierResult(BaseModel):
    status: Literal["papers_found", "papers_not_found"]
    queries: list[str]
    query_source: Literal["llm", "fallback"]
    query_errors: list[str] = Field(default_factory=list)
    papers: list[Paper]
    report: str  # DeepTutor's plain-text frontier report


class MatrixRow(BaseModel):
    source: str  # arXiv id
    authors: list[str]
    claim_evidence: str  # the abstract
    url: str
    evidence_level: str
    agreement: str
    contention: str


class SearchRun(BaseModel):
    query: str
    count: int


class LiteratureResult(BaseModel):
    papers: list[Paper]
    matrix: list[MatrixRow]
    caveat: str
    searches: list[SearchRun]
    coverage: str


def _paper(d: dict[str, Any]) -> Paper:
    year = d.get("year")
    if year is None and str(d.get("published", ""))[:4].isdigit():
        year = int(str(d["published"])[:4])
    return Paper(
        arxiv_id=d["arxiv_id"], title=d.get("title", ""), authors=list(d.get("authors") or []), year=year,
        abstract=d.get("abstract", ""), url=d.get("url", ""), published=d.get("published", ""),
        source_query=d.get("source_query"),
    )


def _dedupe(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        key = re.sub(r"v\d+$", "", p.arxiv_id.lower())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


async def search_arxiv(query: str, max_results: int = 5, years_limit: int | None = 3,
                       sort: Literal["relevance", "date"] = "relevance", *,
                       searcher: ArxivSearchTool | None = None) -> list[Paper]:
    """Search arXiv (Python `arxiv` library). Failures and timeouts yield an empty list, as in DeepTutor."""
    rows = await (searcher or ArxivSearchTool()).search_papers(
        query=query, max_results=max_results, years_limit=years_limit, sort_by=sort)
    return _dedupe([_paper(r) for r in rows])


def _llm_call(llm: ChatLLM | None):
    if llm is None:
        async def _none(system: str, user: str) -> str:
            raise RuntimeError("no model configured")
        return _none

    async def call(system: str, user: str) -> str:
        return await llm.complete(ModelAlias.CHAT.value, [{"role": "system", "content": system},
                                                          {"role": "user", "content": user}], max_tokens=1200, temperature=0.0)
    return call


async def discover_frontier(kb_text_or_topic: str, focus: str = "", max_papers: int = 5, years_limit: int | None = 3, *,
                            keywords: list[str] | None = None, llm: ChatLLM | None = None,
                            searcher: ArxivSearchTool | None = None) -> FrontierResult:
    """The learner's topic (one short line) or their notes text -> up to 3 arXiv queries -> deduped recent papers.

    A one-line input is the topic; a longer input is notes (the first line names the topic). `keywords` seed the
    fallback queries when the model's answer is unusable.
    """
    text = (kb_text_or_topic or "").strip()
    first = text.splitlines()[0] if text else ""
    short = len(text) <= 120 and "\n" not in text
    out = await _frontier.discover_frontier(
        topic=text if short else first[:120], kb_text="" if short else text, keywords=keywords, focus=focus,
        max_papers=max_papers, years_limit=years_limit, llm=_llm_call(llm), searcher=searcher)
    meta = out["metadata"]
    return FrontierResult(
        status=meta["status"], queries=meta["queries"], query_source=meta["query_plan"]["source"],
        query_errors=meta["query_errors"], papers=[_paper(p) for p in meta["papers"]], report=out["content"])


async def literature_pass(topic: str, followups: list[str] | None = None, *,
                          client: _prim.ResearchClient | None = None) -> LiteratureResult:
    """arXiv search on the topic plus at most 3 follow-up queries, and a comparative matrix built from abstracts.

    More than 3 follow-ups raises `ResearchError`. The matrix never claims consensus: see `caveat`.
    """
    followups = list(followups or [])
    if len(followups) > MAX_FOLLOWUPS:
        raise ResearchError("Use at most three recursive follow-up queries per literature pass.")
    out = await _prim.literature(client or _prim.ResearchClient(), topic, followups)
    return LiteratureResult(
        papers=[_paper(p) for p in out["papers"]], matrix=[MatrixRow(**m) for m in out["comparative_matrix"]],
        caveat=out["caveat"], searches=[SearchRun(**s) for s in out["searches"]], coverage=out["coverage"])
