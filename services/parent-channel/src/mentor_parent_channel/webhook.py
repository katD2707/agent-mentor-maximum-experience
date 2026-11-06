"""FastAPI router for Zalo Bot webhooks.

Zalo POSTs `application/json` events to the URL registered with setWebhook and sends the registered
secret in the `X-Bot-Api-Secret-Token` header (https://bot.zapps.me/docs/webhook/). Requests without
the right secret get 403, as in Zalo's sample handler.
"""

import hmac
import logging
from typing import Any, Protocol

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from mentor_parent_channel.client import SECRET_TOKEN_MAX, SECRET_TOKEN_MIN

log = logging.getLogger(__name__)

SECRET_HEADER = "X-Bot-Api-Secret-Token"
WEBHOOK_PATH = "/webhooks/zalo"


class UpdateHandler(Protocol):
    def handle_update(self, update: dict[str, Any]) -> None: ...


def create_webhook_router(
    service: UpdateHandler,
    secret_token: str,
    *,
    header_name: str = SECRET_HEADER,
    path: str = WEBHOOK_PATH,
) -> APIRouter:
    if not SECRET_TOKEN_MIN <= len(secret_token) <= SECRET_TOKEN_MAX:
        raise ValueError(
            f"secret_token must be {SECRET_TOKEN_MIN}-{SECRET_TOKEN_MAX} characters (Zalo setWebhook rule)"
        )
    expected = secret_token.encode()
    router = APIRouter()

    @router.post(path)
    async def zalo_webhook(request: Request) -> JSONResponse:
        given = request.headers.get(header_name, "").encode()
        if not hmac.compare_digest(given, expected):
            log.warning("zalo webhook: bad or missing %s", header_name)
            return JSONResponse({"message": "Unauthorized"}, status_code=403)
        try:
            update = await request.json()
        except ValueError:
            return JSONResponse({"message": "invalid JSON"}, status_code=400)
        if not isinstance(update, dict):
            return JSONResponse({"message": "expected a JSON object"}, status_code=400)
        # The service and the gateway's store are synchronous; keep them off the event loop.
        await run_in_threadpool(service.handle_update, update)
        return JSONResponse({"ok": True})

    return router
