"""Paper search and related papers (CONTRACTS 15.2, 15.3). No model is used here: cards show what the sources say.

Order: Asta (the learner's key), then Semantic Scholar (their key), then arXiv (no key). A source without a key is
`not_connected` and not called; a refused key, a rate limit or an outage is `failed` and skipped. Duplicates are found by
arXiv id, DOI or S2 id and the earlier source's card wins. The TL;DR is S2's own `tldr` field, else the card has only an
abstract excerpt; nothing is summarised or translated.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from mentor_schemas.research import (
    SEARCH_PAGE_SIZE,
    PaperCard,
    RelatedList,
    RelatedPapers,
    SearchResponse,
    SearchSourceStatus,
)
from sqlalchemy import select

from mentor_gateway.db import User
from mentor_gateway.research.base import ResearchBase, fail
from mentor_gateway.research.sources import excerpt, s2_ref
from mentor_gateway.research.tables import PaperRow, ReadingEntryRow

CARD_FIELDS = set(PaperCard.model_fields)
RELATED_TTL = timedelta(hours=24)
RELATED_MAX = 20


def identifiers(c: dict[str, Any]) -> set[str]:
    ids = {c["key"]}
    if c.get("arxiv_id"):
        ids.add(f"arxiv:{c['arxiv_id']}")
    if c.get("doi"):
        ids.add(f"doi:{c['doi']}")
    if c.get("s2_id"):
        ids.add(f"s2:{c['s2_id']}")
    return ids


def merge(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concatenates in the order given, dropping a card whose arXiv id, DOI or S2 id was seen already."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for cards in lists:
        for c in cards:
            ids = identifiers(c)
            if ids & seen:
                continue
            seen |= ids
            out.append(c)
    return out


class SearchMixin(ResearchBase):
    def decorate(self, user_id: str, cards: list[dict[str, Any]]) -> list[PaperCard]:
        """Card dicts -> PaperCard with `in_reading_list` and `paper_id` filled for papers the learner already stored."""
        keys = [c["key"] for c in cards]
        stored: dict[str, tuple[str, bool]] = {}
        if keys:
            with self.db.session() as s:
                for pid, key in s.execute(select(PaperRow.id, PaperRow.key).where(PaperRow.user_id == user_id,
                                                                                  PaperRow.key.in_(keys))):
                    e = s.get(ReadingEntryRow, pid)
                    stored[key] = (pid, bool(e is not None and e.removed_at is None))
        out = []
        for c in cards:
            pid, in_list = stored.get(c["key"], (None, False))
            fields = {k: v for k, v in c.items() if k in CARD_FIELDS - {"paper_id", "in_reading_list", "authors"}}
            out.append(PaperCard(**fields, authors=list(c.get("authors") or [])[:5], in_reading_list=in_list, paper_id=pid))
        return out

    # ---- search -------------------------------------------------------------------------------------------------------
    async def _asta_search(self, user: User, key: str, q: str, want: int, year_min: int | None) -> tuple[list[dict], bool]:
        src = self.asta_source(user.id, key)
        found, snippets = await asyncio.gather(src.search(q, limit=want, year_min=year_min), src.snippets(q, limit=10),
                                               return_exceptions=True)
        if isinstance(found, BaseException):
            raise found
        if not isinstance(snippets, BaseException):
            best: dict[str, dict] = {}
            for sn in snippets:
                if sn["corpus_id"] and (sn["corpus_id"] not in best or sn["score"] > best[sn["corpus_id"]]["score"]):
                    best[sn["corpus_id"]] = sn
            for c in found:
                hit = best.get(c.get("corpus_id") or "")
                if hit is not None:
                    c["snippet"] = hit["text"][:600]
        return found, len(found) >= want

    async def _arxiv_search(self, q: str, want: int) -> tuple[list[dict], bool]:
        n = max(1, min(want, 20))
        rows = await self.arxiv_search(q, n, None, "relevance")
        return [{**self.fields_of_arxiv(p), "excerpt": excerpt(p.abstract), "tldr": None, "snippet": None,
                 "citation_count": None, "venue": None, "doi": None, "s2_id": None} for p in rows], len(rows) >= n and n < 20

    async def search(self, user: User, q: str, year_min: int | None, pdf: bool, page: int,
                     depth: str | None = None) -> SearchResponse:
        """depth: quick = arXiv; thorough = + Semantic Scholar; deep = + Asta. None = every source with a key."""
        q = " ".join(q.split())
        if not q:
            raise fail(422, "empty_query")
        self.limiter.require(user.id, "search", 30, timedelta(minutes=1))
        page = max(1, page)
        want = page * SEARCH_PAGE_SIZE
        asta_key, s2_key = self.user_key(user.id, "asta"), self.user_key(user.id, "s2")
        allowed = {"quick": set(), "thorough": {"s2"}, "deep": {"s2", "asta"}}.get(depth or "", {"s2", "asta"})
        left_out = {n for n, k in (("asta", asta_key), ("s2", s2_key)) if k and n not in allowed}

        async def asta() -> tuple[list[dict], bool]:
            return await self._asta_search(user, asta_key, q, want, year_min)  # type: ignore[arg-type]

        async def s2() -> tuple[list[dict], bool]:
            return await self.s2_client(s2_key).search(q, limit=min(100, want), year_min=year_min)  # type: ignore[arg-type]

        jobs = {"asta": asta() if asta_key and "asta" in allowed else None, "s2": s2() if s2_key and "s2" in allowed else None,
                "arxiv": self._arxiv_search(q, want)}
        names = [n for n, j in jobs.items() if j is not None]
        done = await asyncio.gather(*(jobs[n] for n in names), return_exceptions=True)  # type: ignore[arg-type]
        got = dict(zip(names, done, strict=True))
        statuses, per_source, more = [], {}, False
        for name in ("asta", "s2", "arxiv"):
            res = got.get(name)
            if res is None:
                statuses.append(SearchSourceStatus(source=name, status="skipped" if name in left_out else "not_connected"))
            elif isinstance(res, BaseException):
                statuses.append(SearchSourceStatus(source=name, status="failed"))
            else:
                statuses.append(SearchSourceStatus(source=name, status="ok"))
                cards, has_more = res
                per_source[name] = [c for c in cards if (year_min is None or c.get("year") is None or c["year"] >= year_min)
                                    and (not pdf or c.get("has_pdf"))]
                more = more or has_more
        merged = merge(per_source.get("asta", []), per_source.get("s2", []), per_source.get("arxiv", []))
        start = (page - 1) * SEARCH_PAGE_SIZE
        more = more or len(merged) > start + SEARCH_PAGE_SIZE
        return SearchResponse(query=q, page=page, page_size=SEARCH_PAGE_SIZE, has_more=more, sources=statuses,
                              results=self.decorate(user.id, merged[start:start + SEARCH_PAGE_SIZE]))

    # ---- related ------------------------------------------------------------------------------------------------------
    async def related(self, user: User, paper_id: str) -> RelatedPapers:
        with self.db.session() as s:
            p = s.get(PaperRow, paper_id)
            if p is None or p.user_id != user.id:
                raise fail(404, "paper_not_found")
            s.expunge(p)
        self.limiter.require(user.id, "search", 30, timedelta(minutes=1))
        asta_key, s2_key = self.user_key(user.id, "asta"), self.user_key(user.id, "s2")
        if not asta_key and not s2_key:
            return RelatedPapers(available=False, reason="no_source_key", sources=[], partial=False,
                                 citing=RelatedList(count=0, items=[]), cited=RelatedList(count=0, items=[]))
        now = self.clock()
        cached = self.related_cache.get((user.id, paper_id))
        if cached and now - cached[0] < RELATED_TTL and cached[2] == (bool(asta_key), bool(s2_key)):
            return cached[1]
        ref = s2_ref(p.arxiv_id, p.doi, p.s2_id)
        used: list[str] = []
        partial = False
        citing_lists: list[list[dict]] = []
        cited: list[dict] = []
        totals = {"citing": 0, "cited": 0}
        if ref is None:
            partial = True  # nothing to look the paper up by
        else:
            calls = {}
            if s2_key:
                calls["s2"] = self.s2_client(s2_key).related(ref)
            if asta_key:
                calls["asta"] = self.asta_source(user.id, asta_key).citations(ref, limit=RELATED_MAX)
            res = dict(zip(calls, await asyncio.gather(*calls.values(), return_exceptions=True), strict=True))
            if "s2" in res:
                if isinstance(res["s2"], BaseException):
                    partial = True
                else:
                    used.append("s2")
                    citing_lists.append(res["s2"]["citing"])
                    cited = res["s2"]["cited"]
                    totals["citing"] = res["s2"]["citing_total"] or len(res["s2"]["citing"])
                    totals["cited"] = res["s2"]["cited_total"] or len(cited)
            if "asta" in res:
                if isinstance(res["asta"], BaseException):
                    partial = True
                else:
                    used.append("asta")
                    citing_lists.append(res["asta"])
        citing = merge(*citing_lists)
        out = RelatedPapers(
            available=True, sources=[x for x in ("asta", "s2") if x in used], partial=partial,
            citing=RelatedList(count=max(totals["citing"], len(citing)), items=self.decorate(user.id, citing[:RELATED_MAX])),
            cited=RelatedList(count=max(totals["cited"], len(cited)), items=self.decorate(user.id, merge(cited)[:RELATED_MAX])))
        if not partial:
            self.related_cache[(user.id, paper_id)] = (now, out, (bool(asta_key), bool(s2_key)))
        return out
