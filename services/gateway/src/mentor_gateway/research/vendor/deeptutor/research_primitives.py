# Source: https://github.com/HKUDS/DeepTutor/blob/60fb3bdfddb30b7740c7ce3bd9b28d908f2af6db/deeptutor/services/research/primitives.py
# Version: DeepTutor v1.7.2 (commit 60fb3bdfddb30b7740c7ce3bd9b28d908f2af6db)
# Copyright (c) HKUDS and the DeepTutor authors. Licensed under the Apache License 2.0 (see LICENSE in this folder).
# Modified by Mentor: kept only arxiv_id, the arXiv pacing, ResearchClient.fetch/search, parse_feed and `literature`.
#   Dropped the GitHub repository audit, PDF reading (PyMuPDF), alphaXiv hosts, the MCP URL validator
#   (deeptutor.services.mcp.network), the cache/GitHub-token constructor arguments and the paper() lookup.
#   fetch() now only allows arxiv.org / export.arxiv.org over https (host check, 45 s budget, byte limit and redirect
#   budget unchanged); the User-Agent says Mentor; `literature` also returns the `caveat` text that DeepTutor
#   kept only in the tool description. Network limits are unchanged (3 s arXiv interval, 30 s timeout).
"""Bounded primary-source evidence for scientific research (#1629).

These primitives read arXiv metadata. They do not infer experimental reproduction.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from urllib.parse import quote, urljoin, urlsplit

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
import httpx

_ATOM = "{http://www.w3.org/2005/Atom}"
_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z][a-z.-]+/\d{7})(?:v[1-9]\d*)?")
_HOSTS = {"arxiv.org", "export.arxiv.org"}
_API_LOCK = threading.Lock()
_NEXT_API = 0.0
ARXIV_INTERVAL = 3.0

LITERATURE_CAVEAT = "Abstracts alone do not establish consensus or contention."


class ResearchError(ValueError):
    pass


def arxiv_id(value: str) -> str:
    value = re.sub(r"^arxiv:\s*", "", value.strip(), flags=re.I)
    if "://" in value:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"arxiv.org", "www.arxiv.org"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ResearchError("Use an arXiv identifier or canonical arXiv paper URL.")
        value = re.sub(r"^/(?:abs|pdf)/", "", parsed.path)
    value = value.removesuffix(".pdf")
    if not _ID.fullmatch(value):
        raise ResearchError(
            "Invalid arXiv identifier; versions and legacy archive IDs are supported."
        )
    return value


async def _pace_arxiv():
    global _NEXT_API
    with _API_LOCK:
        now = time.monotonic()
        delay = max(0, _NEXT_API - now)
        _NEXT_API = max(now, _NEXT_API) + ARXIV_INTERVAL
    if delay:
        await asyncio.sleep(delay)


class ResearchClient:
    def __init__(self, *, client_factory=None):
        self.client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)
        )

    async def fetch(self, url: str, *, limit: int, accept: str = "application/json") -> bytes:
        async with asyncio.timeout(45):
            async with self.client_factory() as client:
                for _ in range(4):
                    parsed = urlsplit(url)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname not in _HOSTS
                        or parsed.username
                        or parsed.password
                    ):
                        raise ResearchError(
                            "Research downloads are restricted to primary-source hosts."
                        )
                    headers = {"User-Agent": "Mentor-Research/1", "Accept": accept}
                    async with client.stream("GET", url, headers=headers) as response:
                        if response.is_redirect:
                            url = urljoin(url, response.headers.get("location", ""))
                            continue
                        if response.status_code != 200:
                            raise ResearchError(
                                f"Primary source returned HTTP {response.status_code}; evidence was not retrieved."
                            )
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(data) + len(chunk) > limit:
                                raise ResearchError(
                                    "Primary source exceeded the configured byte budget."
                                )
                            data.extend(chunk)
                        return bytes(data)
                raise ResearchError("Primary source exceeded the redirect budget.")

    async def search(self, query: str, *, limit: int = 6) -> list[dict]:
        if not query.strip() or len(query) > 1000 or not 1 <= limit <= 8:
            raise ResearchError(
                "Use a nonempty query up to 1000 characters and at most eight papers."
            )
        await _pace_arxiv()
        raw = await self.fetch(
            "https://export.arxiv.org/api/query?search_query="
            + quote(query, safe="")
            + f"&max_results={limit}&sortBy=relevance",
            limit=2 * 1024 * 1024,
            accept="application/atom+xml",
        )
        return parse_feed(raw)


def parse_feed(raw: bytes) -> list[dict]:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ResearchError("Unexpected XML declarations in primary-source response.")
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ResearchError("Primary-source metadata was not a usable Atom feed.") from exc
    if root.tag != _ATOM + "feed":
        raise ResearchError("Primary-source metadata was not an Atom feed.")
    rows = []
    for entry in root.findall(_ATOM + "entry")[:8]:
        identifier = arxiv_id(entry.findtext(_ATOM + "id", ""))
        rows.append(
            {
                "arxiv_id": identifier,
                "title": " ".join(entry.findtext(_ATOM + "title", "").split()),
                "authors": [
                    author.findtext(_ATOM + "name", "")
                    for author in entry.findall(_ATOM + "author")
                ],
                "abstract": " ".join(entry.findtext(_ATOM + "summary", "").split())[:12000],
                "published": entry.findtext(_ATOM + "published", ""),
                "updated": entry.findtext(_ATOM + "updated", ""),
                "url": f"https://arxiv.org/abs/{identifier}",
                "pdf_url": f"https://arxiv.org/pdf/{identifier}",
                "evidence_level": "primary_abstract",
            }
        )
    return rows


async def literature(client: ResearchClient, topic: str, followups: list[str]) -> dict:
    if len(followups) > 3:
        raise ResearchError("Use at most three recursive follow-up queries per literature pass.")
    papers, searches = {}, []
    for query in [topic, *followups]:
        rows = await client.search(query, limit=6)
        searches.append({"query": query, "count": len(rows)})
        for paper in rows:
            identity = re.sub(r"v\d+$", "", paper["arxiv_id"])
            papers[identity] = paper
    return {
        "searches": searches,
        "papers": list(papers.values()),
        "comparative_matrix": [
            {
                "source": paper["arxiv_id"],
                "authors": paper["authors"],
                "claim_evidence": paper["abstract"],
                "url": paper["url"],
                "evidence_level": "primary_abstract",
                "agreement": "requires_full_text_comparison",
                "contention": "requires_full_text_comparison",
            }
            for paper in papers.values()
        ],
        "caveat": LITERATURE_CAVEAT,
        "coverage": "bounded arXiv discovery, not an exhaustive systematic review",
        "next_step": "Read full primary papers with preprint; compare claim, method, dataset, metric, result and limitations. Recurse with explicit follow-up queries; classify consensus/contention only with cited evidence.",
    }
