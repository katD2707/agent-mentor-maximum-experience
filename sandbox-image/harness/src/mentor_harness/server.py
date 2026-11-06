"""Sandbox HTTP API (CONTRACTS.md section 2). Run: `uvicorn mentor_harness.server:app --port 8080`.

Every endpoint except `GET /v1/health` requires `Authorization: Bearer $MENTOR_HARNESS_TOKEN` (a random token
the gateway issues at each sandbox start). Without a token the API is open, which is refused inside the isolated
container (MENTOR_SANDBOX_ISOLATED=1: every protected request gets 503) and meant only for tests and local dev.
"""

import ctypes
import hmac
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from mentor_schemas import ApprovalDecision, JobRequest, JobResult, TurnRequest

from mentor_harness.agent import Harness
from mentor_harness.config import Settings
from mentor_harness.model import DevScriptedModel, ModelClient, RouterModel
from mentor_harness.scripts import ScriptRunner, run_mentor_script
from mentor_harness.workspace import ensure_git_safe_directory

log = logging.getLogger("mentor_harness")

HEALTH_PATH = "/v1/health"
Scope = MutableMapping[str, Any]
ASGIApp = Callable[[Scope, Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]]


class BearerTokenAuth:
    """Pure ASGI middleware (keeps SSE streaming intact): default-deny for every path but the health check."""

    def __init__(self, app: ASGIApp, token: str | None, fail_closed: bool) -> None:
        self.app = app
        self.token = token.encode("utf-8") if token else None
        self.fail_closed = fail_closed

    def _allowed(self, scope: Scope) -> tuple[bool, int, str]:
        if self.token is None:
            if self.fail_closed:
                return False, 503, "harness token not configured"
            return True, 200, ""
        header = b""
        for name, value in scope.get("headers") or []:
            if name.lower() == b"authorization":
                header = value
                break
        scheme, _, presented = header.partition(b" ")
        if scheme.lower() == b"bearer" and hmac.compare_digest(presented.strip(), self.token):
            return True, 200, ""
        return False, 401, "missing or invalid harness token"

    async def __call__(self, scope: Scope, receive: Callable[[], Awaitable[Any]],
                       send: Callable[[Any], Awaitable[None]]) -> None:
        if scope["type"] not in ("http", "websocket") or (scope["type"] == "http" and scope["path"] == HEALTH_PATH):
            await self.app(scope, receive, send)
            return
        ok, status, detail = self._allowed(scope)
        if ok:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        resp = JSONResponse({"detail": detail}, status_code=status, headers={"WWW-Authenticate": "Bearer"})
        await resp(scope, receive, send)


def make_undumpable() -> bool:
    """prctl(PR_SET_DUMPABLE, 0): /proc/<harness pid>/environ and /mem become root-only, so learner code run by
    run_python under the same uid cannot read MENTOR_HARNESS_TOKEN, MODEL_ROUTER_KEY or MENTOR_GATEWAY_TOKEN.
    Children reset this on execve. Linux only; best effort."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        return ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) == 0  # 4 = PR_SET_DUMPABLE
    except (OSError, AttributeError):
        return False


def make_model(settings: Settings) -> ModelClient:
    if settings.model_mode == "scripted":
        return DevScriptedModel(chunk_delay_s=0.02)  # visibly streamed in the dev UI
    return RouterModel(settings.model_router_url, settings.model_router_key, timeout_s=settings.model_timeout_s)


def create_app(
    settings: Settings | None = None,
    model: ModelClient | None = None,
    script_runner: ScriptRunner = run_mentor_script,
) -> FastAPI:
    settings = settings or Settings.from_env()
    harness = Harness(settings, model or make_model(settings), script_runner=script_runner)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        if settings.sandbox_isolated and not make_undumpable():
            log.warning("could not mark the harness process non-dumpable")
        if settings.harness_token is None:
            if settings.sandbox_isolated:
                log.error("MENTOR_HARNESS_TOKEN is not set: refusing every request except %s", HEALTH_PATH)
            else:
                log.warning("MENTOR_HARNESS_TOKEN is not set: sandbox API is unauthenticated (dev/tests only)")
        try:
            ensure_git_safe_directory()  # arbitrary uid: mounted /workspace may belong to another user
            harness.ws.ensure_repo()  # dev convenience; provisioned workspaces already have one
        except Exception:
            logging.getLogger("mentor_harness").exception("could not initialize the workspace repo")
        yield
        if isinstance(harness.model, RouterModel):
            await harness.model.aclose()

    # no /docs, /redoc or /openapi.json: nothing but the CONTRACTS section 2 endpoints is served
    app = FastAPI(title="mentor-harness", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.harness = harness
    app.add_middleware(BearerTokenAuth, token=settings.harness_token, fail_closed=settings.sandbox_isolated)

    @app.get(HEALTH_PATH)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/turn")
    async def turn(req: TurnRequest) -> StreamingResponse:
        async def sse() -> AsyncIterator[str]:
            async for event in harness.stream_turn(req):
                yield f"data: {event.model_dump_json()}\n\n"

        return StreamingResponse(
            sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/jobs")
    async def run_job(req: JobRequest) -> JobResult:
        return await harness.run_job(req)

    @app.post("/v1/approvals")
    async def approvals(decision: ApprovalDecision) -> dict[str, bool]:
        if not harness.approvals.resolve(decision):
            raise HTTPException(status_code=404, detail="approval not pending")
        return {"ok": True}

    return app


app = create_app()
