# Source: https://github.com/HKUDS/DeepTutor/blob/60fb3bdfddb30b7740c7ce3bd9b28d908f2af6db/deeptutor/tools/paper_search_tool.py
# Version: DeepTutor v1.7.2 (commit 60fb3bdfddb30b7740c7ce3bd9b28d908f2af6db)
# Copyright (c) HKUDS and the DeepTutor authors. Licensed under the Apache License 2.0 (see LICENSE in this folder).
# Modified by Mentor: removed the __main__ demo and the PaperSearchTool compatibility alias; search logic and network limits (3 s delay, 2 retries, 30 s timeout, one 429 retry) unchanged.
"""
ArXiv search tool for preprint discovery.

This utility searches arXiv and returns lightweight metadata suitable for
tool usage in chat flows.
"""

import asyncio
from datetime import datetime
import logging
import re

import arxiv

logger = logging.getLogger(__name__)

_FETCH_MULTIPLIER = 2
_MAX_FETCH_CAP = 30
_REQUEST_TIMEOUT_S = 30
_MAX_RETRIES = 2
_RETRY_DELAY_S = 3.0


class ArxivSearchTool:
    """Search arXiv preprints and return normalized metadata."""

    def __init__(self):
        """Initialize search tool"""
        self.client = arxiv.Client(
            page_size=20,
            delay_seconds=3.0,
            num_retries=_MAX_RETRIES,
        )

    async def search_papers(
        self,
        query: str,
        max_results: int = 3,
        years_limit: int | None = 3,
        sort_by: str = "relevance",
    ) -> list[dict]:
        """
        Search ArXiv papers

        Args:
            query: Search query keywords
            max_results: Number of papers to return
            years_limit: Paper year limit (last N years), None means no limit
            sort_by: Sort method - "relevance" or "date"

        Returns:
            List of papers, each paper contains:
                - title: Title
                - authors: Author list
                - year: Publication year
                - abstract: Abstract
                - url: Paper URL
                - arxiv_id: ArXiv ID
                - published: Publication date (ISO format)
        """
        query = (query or "").strip()
        if not query:
            return []

        max_results = max(1, min(int(max_results), 20))

        if sort_by == "date":
            sort_criterion = arxiv.SortCriterion.SubmittedDate
        else:
            sort_criterion = arxiv.SortCriterion.Relevance

        fetch_count = min(max_results * _FETCH_MULTIPLIER, _MAX_FETCH_CAP)

        search = arxiv.Search(
            query=query,
            max_results=fetch_count,
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[dict] = []
        current_year = datetime.now().year

        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(lambda: list(self.client.results(search))),
                timeout=_REQUEST_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "arXiv search timed out after %ss for query: %s", _REQUEST_TIMEOUT_S, query
            )
            return []
        except arxiv.HTTPError as exc:
            logger.warning("arXiv HTTP error (status %s) for query: %s", exc.status, query)
            if exc.status == 429:
                await asyncio.sleep(_RETRY_DELAY_S)
                try:
                    results = await asyncio.wait_for(
                        asyncio.to_thread(lambda: list(self.client.results(search))),
                        timeout=_REQUEST_TIMEOUT_S,
                    )
                except Exception:
                    logger.warning("arXiv retry also failed for query: %s", query)
                    return []
            else:
                return []
        except Exception:
            logger.exception("Unexpected error during arXiv search for query: %s", query)
            return []

        for result in results:
            published_date = result.published
            paper_year = published_date.year

            if years_limit and (current_year - paper_year) > years_limit:
                continue

            arxiv_id = result.entry_id.split("/")[-1]
            if "v" in arxiv_id:
                arxiv_id = arxiv_id.split("v")[0]

            authors = [author.name for author in result.authors]

            paper_info = {
                "title": result.title,
                "authors": authors,
                "year": paper_year,
                "abstract": " ".join((result.summary or "").split()),
                "url": result.entry_id,
                "arxiv_id": arxiv_id,
                "published": published_date.isoformat(),
            }

            papers.append(paper_info)

            if len(papers) >= max_results:
                break

        return papers

    def format_paper_citation(self, paper: dict) -> str:
        """
        Format paper citation

        Args:
            paper: Paper information dictionary

        Returns:
            Citation string: (FirstAuthor et al., Year)
        """
        if not paper["authors"]:
            return f"(Unknown, {paper['year']})"

        first_author = paper["authors"][0].split()[-1]  # Extract surname

        if len(paper["authors"]) > 1:
            return f"({first_author} et al., {paper['year']})"
        return f"({first_author}, {paper['year']})"

    def extract_arxiv_id_from_url(self, url: str) -> str | None:
        """
        Extract ArXiv ID from URL

        Args:
            url: ArXiv URL

        Returns:
            ArXiv ID or None
        """
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", url)
        if match:
            return match.group(1)
        return None
