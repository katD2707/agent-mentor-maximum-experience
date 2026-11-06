"""Sandbox -> gateway literature endpoints (CONTRACTS.md section 5), used by the harness tools paper_*.

Auth: `Authorization: Bearer <MENTOR_GATEWAY_TOKEN>`, the per-sandbox token issued when the sandbox
started (sandbox/tokens.py). NCS sandboxes only. Responses with Asta data carry `attribution` (license term).
"""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from mentor_schemas import Profile

from mentor_gateway.api.deps import get_gw
from mentor_gateway.asta import ASTA_ATTRIBUTION
from mentor_gateway.context import Gateway
from mentor_gateway.papers import MAX_CITATIONS, MAX_LIMIT, MAX_SNIPPET_PAPERS, MAX_SNIPPETS, PaperError
from mentor_gateway.sandbox.tokens import SandboxIdentity

router = APIRouter(prefix="/internal/papers", include_in_schema=False)


def sandbox_identity(authorization: str | None = Header(None), gw: Gateway = Depends(get_gw)) -> SandboxIdentity:
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    ident = gw.tokens.verify(token)
    if ident is None:
        raise HTTPException(401, "invalid sandbox token")
    if ident.profile != Profile.NCS:
        raise HTTPException(403, "paper tools are for NCS learners only")
    retry = gw.paper_limiter.check(ident.user_id)
    if retry is not None:
        raise HTTPException(429, "too many paper requests", headers={"Retry-After": str(int(retry) + 1)})
    return ident


def _error(exc: PaperError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


@router.get("/search")
async def search_papers(
    q: str = Query(..., min_length=1, max_length=500),
    source: Literal["asta", "arxiv", "semantic_scholar"] | None = None,  # default: asta if configured, else arxiv
    limit: int = Query(5, ge=1, le=MAX_LIMIT),
    year_from: int | None = Query(None, ge=1900, le=2100),
    ident: SandboxIdentity = Depends(sandbox_identity),
    gw: Gateway = Depends(get_gw),
):
    try:
        found = await gw.papers.search_with_source(q, source, limit, year_from)
    except PaperError as exc:
        return _error(exc)
    return _attributed({**found, "query": q})


@router.get("/get")
async def get_paper(
    id: str = Query(..., min_length=1, max_length=300),
    ident: SandboxIdentity = Depends(sandbox_identity),
    gw: Gateway = Depends(get_gw),
):
    try:
        paper = await gw.papers.get(id)
    except PaperError as exc:
        return _error(exc)
    return _attributed({"source": paper.get("source"), "paper": paper})


@router.get("/snippets")
async def paper_snippets(
    q: str = Query(..., min_length=1, max_length=500),
    paper_ids: list[str] = Query([], max_length=MAX_SNIPPET_PAPERS),
    limit: int = Query(5, ge=1, le=MAX_SNIPPETS),
    ident: SandboxIdentity = Depends(sandbox_identity),
    gw: Gateway = Depends(get_gw),
):
    """Asta snippet_search. `paper_ids` repeats (`?paper_ids=a&paper_ids=b`) or is comma-separated."""
    ids = [p.strip() for raw in paper_ids for p in raw.split(",") if p.strip()]
    try:
        snippets = await gw.papers.snippets(q, ids, limit)
    except PaperError as exc:
        return _error(exc)
    return _attributed({"source": "asta", "query": q, "snippets": snippets})


@router.get("/citations")
async def paper_citations(
    id: str = Query(..., min_length=1, max_length=300),
    limit: int = Query(10, ge=1, le=MAX_CITATIONS),
    year_from: int | None = Query(None, ge=1900, le=2100),
    ident: SandboxIdentity = Depends(sandbox_identity),
    gw: Gateway = Depends(get_gw),
):
    """Asta get_citations: papers citing `id`, most-cited first."""
    try:
        citing = await gw.papers.citations(id, limit, year_from)
    except PaperError as exc:
        return _error(exc)
    return _attributed({"source": "asta", "id": id, "citations": citing})


def _attributed(body: dict) -> dict:
    if body.get("source") == "asta":
        body["attribution"] = ASTA_ATTRIBUTION
    return body
