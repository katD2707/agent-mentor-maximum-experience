"""Sandbox -> gateway web access, used by the harness tools web_search and web_fetch (THPT and NCS).

Auth: `Authorization: Bearer <MENTOR_GATEWAY_TOKEN>`, the per-sandbox token (sandbox/tokens.py), same as
/internal/papers. The query / URL is in the POST body so it never appears in access logs. The audit log records
only that a search happened (backend, number of results) or, for a fetch / download, the host and the status,
never the URL path or query (they may carry personal data). SSRF checks for fetches live in webfetch.py.

PDFs: /fetch answers 415 `pdf`; the harness then calls /download, which returns the raw bytes
(`application/pdf`, metadata in `X-Final-Url` / `X-Content-Sha256`) instead of base64 inside JSON. The gateway
never parses them; the learner's sandbox saves and parses the file.
"""

import hashlib
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from mentor_schemas import Profile
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.papers import RateLimiter
from mentor_gateway.sandbox.tokens import SandboxIdentity
from mentor_gateway.webfetch import MAX_URL_CHARS, WebFetchError, host_of
from mentor_gateway.websearch import DEFAULT_RESULTS, MAX_RESULTS, WebSearchError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/web", include_in_schema=False)

MAX_QUERY_FIELD = 400  # longer -> 422; the service also trims to websearch.MAX_QUERY_CHARS


def _identity(authorization: str | None, gw: Gateway, limiter: RateLimiter, what: str) -> SandboxIdentity:
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    ident = gw.tokens.verify(token)
    if ident is None:
        raise HTTPException(401, "invalid sandbox token")
    retry = limiter.check(ident.user_id)
    if retry is not None:
        raise HTTPException(429, f"too many {what}", headers={"Retry-After": str(int(retry) + 1)})
    return ident


def web_identity(authorization: str | None = Header(None), gw: Gateway = Depends(get_gw)) -> SandboxIdentity:
    return _identity(authorization, gw, gw.web_limiter, "web searches")


def fetch_identity(authorization: str | None = Header(None), gw: Gateway = Depends(get_gw)) -> SandboxIdentity:
    return _identity(authorization, gw, gw.fetch_limiter, "web page fetches")


class WebSearchBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_FIELD)
    max_results: int = Field(DEFAULT_RESULTS, ge=1, le=MAX_RESULTS)


class WebFetchBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=MAX_URL_CHARS)


def _audit(gw: Gateway, user_id: str, detail: str, kind: str = "web_search") -> None:
    try:
        gw.parent.store.record_audit(user_id, kind, detail)
    except Exception:  # auditing must not break the search / fetch
        log.warning("could not write the %s audit row", kind, exc_info=True)


@router.post("/search")
async def web_search(body: WebSearchBody, ident: SandboxIdentity = Depends(web_identity),
                     gw: Gateway = Depends(get_gw)):
    """`{query, max_results<=8}` -> `{backend, results: [{title, url, snippet, published?}]}`."""
    safesearch = 2 if ident.profile == Profile.THPT else 1  # SearXNG only; strict for school students
    try:
        results = await gw.web.search(body.query, body.max_results, safesearch=safesearch)
    except WebSearchError as exc:
        if exc.reason != "not_configured":
            _audit(gw, ident.user_id, f"backend={gw.web.backend}; results=0; error={exc.status}")
        return JSONResponse({"detail": str(exc), "reason": exc.reason}, status_code=exc.status)
    _audit(gw, ident.user_id, f"backend={gw.web.backend}; results={len(results)}")
    return {"backend": gw.web.backend, "results": results}


def _fetch_error(gw: Gateway, ident: SandboxIdentity, url: str, exc: WebFetchError) -> JSONResponse:
    if exc.reason != "disabled":
        status = f"error={exc.status} {exc.reason}"
        if exc.upstream_status is not None:
            status += f" (upstream {exc.upstream_status})"
        _audit(gw, ident.user_id, f"host={host_of(url)}; {status}", "web_fetch")
    return JSONResponse({"detail": str(exc), "reason": exc.reason, "upstream_status": exc.upstream_status},
                        status_code=exc.status)


def _hosts(url: str, final_url: str) -> str:
    final_host = host_of(final_url)
    return host_of(url) + (f" -> {final_host}" if final_host != host_of(url) else "")


@router.post("/fetch")
async def web_fetch(body: WebFetchBody, ident: SandboxIdentity = Depends(fetch_identity),
                    gw: Gateway = Depends(get_gw)):
    """`{url}` -> `{url, final_url, title, text, truncated, content_type}` (public http(s) pages only)."""
    try:
        page = await gw.fetch.fetch(body.url)
    except WebFetchError as exc:
        return _fetch_error(gw, ident, body.url, exc)
    _audit(gw, ident.user_id, f"host={_hosts(body.url, page['final_url'])}; status=200; chars={len(page['text'])}",
           "web_fetch")
    return page


@router.post("/download")
async def web_download(body: WebFetchBody, ident: SandboxIdentity = Depends(fetch_identity),
                       gw: Gateway = Depends(get_gw)):
    """`{url}` -> the PDF bytes (`application/pdf`), headers `X-Final-Url` (percent-encoded) and
    `X-Content-Sha256`. Same SSRF rules and rate limit as /fetch; cap WEB_FETCH_PDF_MAX_MB; PDFs only."""
    try:
        pdf = await gw.fetch.download_pdf(body.url)
    except WebFetchError as exc:
        return _fetch_error(gw, ident, body.url, exc)
    data: bytes = pdf["data"]
    _audit(gw, ident.user_id, f"host={_hosts(body.url, pdf['final_url'])}; status=200; pdf_bytes={len(data)}",
           "web_fetch")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "X-Final-Url": quote(pdf["final_url"], safe="/:?#[]@!$&'()*+,;=%~"),
            "X-Content-Sha256": hashlib.sha256(data).hexdigest(),
            "Content-Disposition": "attachment",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
