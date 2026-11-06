"""FastAPI app: `uvicorn mentor_gateway.app:app --port 8000`.

`app` is built lazily from the environment on first access so importing this module has no side
effects; tests call `create_app(settings, backend=..., parent=...)` directly.
"""

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from mentor_gateway.api import (
    account,
    auth,
    calendar,
    chat,
    conversations,
    email_webhook,
    nudges,
    papers,
    web,
    workspace,
)
from mentor_gateway.api import practice as practice_api
from mentor_gateway.api.deps import get_gw
from mentor_gateway.context import Gateway, build_gateway
from mentor_gateway.email_ingest import handle_raw, start_smtp_server
from mentor_gateway.parent import ParentChannel
from mentor_gateway.practice import PracticeError
from mentor_gateway.sandbox import SandboxBackend
from mentor_gateway.settings import Clock, Settings, utc_now

log = logging.getLogger(__name__)


internal = APIRouter(prefix="/internal", include_in_schema=False)


@internal.post("/email/inbound")
async def inbound_email(request: Request, rcpt: list[str] = Query(default_factory=list),
                        x_internal_token: str | None = Header(None), gw: Gateway = Depends(get_gw)) -> dict:
    """Raw RFC 822 message in the body; `rcpt` = SMTP envelope recipients (repeatable)."""
    expected = gw.settings.internal_token
    if expected:
        if not hmac.compare_digest((x_internal_token or "").encode(), expected.encode()):
            raise HTTPException(403)
    elif gw.settings.env == "prod" or gw.settings.sandbox_backend == "docker":
        # sandbox containers can reach the gateway (/internal/papers, /internal/calendar), so this endpoint must
        # never be open to them: without GATEWAY_INTERNAL_TOKEN it is closed in prod and with the docker backend
        raise HTTPException(403)
    if gw.inbound is None:
        raise HTTPException(503, "email ingest unavailable")
    path = await handle_raw(gw.inbound, await request.body(), rcpt)
    return {"accepted": path is not None, "path": path}


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock = utc_now,
    backend: SandboxBackend | None = None,
    parent: ParentChannel | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    gw = build_gateway(settings, clock=clock, backend=backend, parent=parent)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task] = []
        smtp: Any = None
        if settings.background_tasks:
            tasks.append(asyncio.create_task(gw.scheduler.run_forever()))
            if settings.inbound_smtp_port and gw.inbound is not None:
                smtp = start_smtp_server(gw.inbound, settings.inbound_smtp_port, settings.inbound_smtp_host)
        try:
            yield
        finally:
            gw.scheduler.stop()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if smtp is not None:
                smtp.stop()
            await gw.runner.drain()
            await gw.orchestrator.shutdown()
            gw.db.dispose()

    app = FastAPI(title="mentor-gateway", lifespan=lifespan)
    app.state.gw = gw
    app.add_exception_handler(PracticeError, lambda _req, exc: practice_api.error_response(exc))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
    )

    api = APIRouter(prefix="/api")
    api.include_router(auth.router)
    api.include_router(account.router)
    api.include_router(workspace.router)
    api.include_router(chat.router)
    api.include_router(conversations.router)  # /api/conversations (section 10.5)
    api.include_router(calendar.router)  # /api/integrations/google-calendar (NCS)
    api.include_router(practice_api.router)  # /api/practice (THPT)
    api.include_router(nudges.router)  # /api/notifications, /api/engagement, /api/push/*
    app.include_router(api)
    app.include_router(internal)
    app.include_router(papers.router)  # GET /internal/papers/* (sandbox token, NCS only)
    app.include_router(calendar.internal_router)  # /internal/calendar/* (sandbox token, NCS only)
    app.include_router(web.router)  # POST /internal/web/search and /internal/web/fetch (sandbox token, THPT and NCS)
    if gw.parent.router is not None:
        app.include_router(gw.parent.router)  # POST /webhooks/zalo
    app.include_router(email_webhook.router)  # POST /webhooks/email/inbound (Cloudflare Email Worker, HMAC)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "parent_channel": "library" if gw.parent.using_library else "dev",
                "email_ingest": gw.inbound is not None}

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _app
    if name == "app":
        if _app is None:
            logging.basicConfig(level=logging.INFO)
            _app = create_app()
        return _app
    raise AttributeError(name)
