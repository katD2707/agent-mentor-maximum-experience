"""Google Calendar endpoints (CONTRACTS.md section 5). NCS learners only.

Web app (cookie session, under /api): connect (redirect to Google), callback (back from Google, then redirect to
the web settings page), status and disconnect.

Sandbox (`Authorization: Bearer <MENTOR_GATEWAY_TOKEN>`, no /api prefix): /internal/calendar/* used by the
harness tools calendar_*. The sandbox never sees Google tokens.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from mentor_schemas import Profile
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import COOKIE_NAME, get_gw, provisioned_user, user_from_cookie
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.gcal import CalendarError
from mentor_gateway.sandbox.tokens import SandboxIdentity

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/google-calendar", tags=["integrations"])
internal_router = APIRouter(prefix="/internal/calendar", include_in_schema=False)


def _error(exc: CalendarError) -> JSONResponse:
    return JSONResponse({"detail": str(exc), "reason": exc.reason}, status_code=exc.status)


# ---- web app --------------------------------------------------------------------------------------


def ncs_user(user: User = Depends(provisioned_user)) -> User:
    if user.role != Profile.NCS.value:
        raise HTTPException(403, "Google Calendar is only for NCS learners")
    return user


def _back_to_settings(gw: Gateway, outcome: str, reason: str | None = None) -> RedirectResponse:
    url = f"{gw.settings.web_url}/settings?calendar={outcome}"
    if reason:
        url += f"&reason={reason}"
    return RedirectResponse(url, status_code=302)


@router.get("")
def calendar_status(user: User = Depends(ncs_user), gw: Gateway = Depends(get_gw)) -> dict:
    return gw.gcal.status(user.id)


@router.get("/connect")
def connect(request: Request, user: User = Depends(ncs_user), gw: Gateway = Depends(get_gw)) -> RedirectResponse:
    try:
        url = gw.gcal.authorization_url(user.id, request.cookies.get(COOKIE_NAME) or "")
    except CalendarError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(None, max_length=2048),
    state: str | None = Query(None, max_length=512),
    error: str | None = Query(None, max_length=200),
    gw: Gateway = Depends(get_gw),
) -> RedirectResponse:
    session_token = request.cookies.get(COOKIE_NAME)
    user = user_from_cookie(gw, session_token)
    if user is None or user.role != Profile.NCS.value or not session_token:
        return _back_to_settings(gw, "error", "session")
    if not state:
        return _back_to_settings(gw, "error", "state")
    if error or not code:
        try:  # consume the state anyway
            gw.gcal.consume_state(state, user.id, session_token)
        except CalendarError:
            pass
        return _back_to_settings(gw, "error", "denied" if error == "access_denied" else "google")
    try:
        await gw.gcal.finish(user.id, session_token, state, code)
    except CalendarError as exc:
        log.info("google calendar connect failed for %s: %s", user.id, exc)
        return _back_to_settings(gw, "error", exc.reason)
    return _back_to_settings(gw, "connected")


@router.delete("")
async def disconnect(user: User = Depends(ncs_user), gw: Gateway = Depends(get_gw)) -> dict:
    await gw.gcal.disconnect(user.id)
    return {"ok": True}


# ---- sandbox ---------------------------------------------------------------------------------------


def calendar_identity(authorization: str | None = Header(None), gw: Gateway = Depends(get_gw)) -> SandboxIdentity:
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    ident = gw.tokens.verify(token)
    if ident is None:
        raise HTTPException(401, "invalid sandbox token")
    if ident.profile != Profile.NCS:
        raise HTTPException(403, "calendar tools are for NCS learners only")
    retry = gw.gcal.limiter.check(ident.user_id)
    if retry is not None:
        raise HTTPException(429, "too many calendar requests", headers={"Retry-After": str(int(retry) + 1)})
    return ident


class EventCreate(BaseModel):
    title: str = Field(..., max_length=1000)
    start: str = Field(..., max_length=64)
    end: str | None = Field(None, max_length=64)
    description: str | None = Field(None, max_length=10_000)
    location: str | None = Field(None, max_length=1000)


class EventUpdate(BaseModel):
    title: str | None = Field(None, max_length=1000)
    start: str | None = Field(None, max_length=64)
    end: str | None = Field(None, max_length=64)
    description: str | None = Field(None, max_length=10_000)
    location: str | None = Field(None, max_length=1000)


async def _run(gw: Gateway, coro_fn, *args: Any, **kwargs: Any) -> Any:
    if not gw.gcal.available:
        return _error(CalendarError(503, "google calendar is not configured on this server", "unavailable"))
    try:
        return await coro_fn(*args, **kwargs)
    except CalendarError as exc:
        return _error(exc)


@internal_router.get("/status")
def sandbox_status(ident: SandboxIdentity = Depends(calendar_identity), gw: Gateway = Depends(get_gw)) -> dict:
    st = gw.gcal.status(ident.user_id)
    return {"available": st["available"], "connected": st["connected"], "email": st["email"]}


@internal_router.get("/events")
async def list_events(
    start: str | None = Query(None, max_length=64),
    end: str | None = Query(None, max_length=64),
    ident: SandboxIdentity = Depends(calendar_identity),
    gw: Gateway = Depends(get_gw),
):
    return await _run(gw, gw.gcal.list_events, ident.user_id, start, end)


@internal_router.get("/events/{event_id}")
async def get_event(event_id: str, ident: SandboxIdentity = Depends(calendar_identity),
                    gw: Gateway = Depends(get_gw)):
    result = await _run(gw, gw.gcal.get_event, ident.user_id, event_id)
    return result if isinstance(result, JSONResponse) else {"event": result}


@internal_router.post("/events")
async def create_event(body: EventCreate, ident: SandboxIdentity = Depends(calendar_identity),
                       gw: Gateway = Depends(get_gw)):
    result = await _run(gw, gw.gcal.create_event, ident.user_id, **body.model_dump())
    return result if isinstance(result, JSONResponse) else {"event": result}


@internal_router.patch("/events/{event_id}")
async def update_event(event_id: str, body: EventUpdate, ident: SandboxIdentity = Depends(calendar_identity),
                       gw: Gateway = Depends(get_gw)):
    result = await _run(gw, gw.gcal.update_event, ident.user_id, event_id, **body.model_dump())
    return result if isinstance(result, JSONResponse) else {"event": result}


@internal_router.delete("/events/{event_id}")
async def delete_event(event_id: str, ident: SandboxIdentity = Depends(calendar_identity),
                       gw: Gateway = Depends(get_gw)):
    result = await _run(gw, gw.gcal.delete_event, ident.user_id, event_id)
    return result if isinstance(result, JSONResponse) else {"ok": True, "event": result}
