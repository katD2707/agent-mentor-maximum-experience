"""Inbound learner email for production: Cloudflare Email Routing -> Email Worker -> `POST /webhooks/email/inbound`.

The Worker (infra/cloudflare/email-worker.js) POSTs the raw RFC 822 message as the body with three headers:

    X-Mentor-Rcpt:       envelope recipient (RCPT TO), e.g. k7p2...@inbox.example.vn
    X-Mentor-Timestamp:  unix seconds when the Worker signed the request
    X-Mentor-Signature:  v1=<hex HMAC-SHA256(EMAIL_WEBHOOK_SECRET, "v1\\n<timestamp>\\n<rcpt>\\n" + body)>

Rules (CONTRACTS.md section 5):
- EMAIL_WEBHOOK_SECRET unset -> 404 (the endpoint does not exist).
- Body over INBOUND_EMAIL_MAX_BYTES -> 413; the Worker turns that into a permanent bounce.
- Timestamp more than 5 minutes from the gateway clock, missing headers or a wrong signature -> 401 (constant-time
  compare). An identical signed request seen again within the window is answered 202 and not stored twice.
- More than EMAIL_WEBHOOK_PER_RCPT_PER_HOUR messages for one recipient -> 429 + Retry-After (checked before the
  recipient is looked up, so it says nothing about whether the address exists).
- Known and unknown recipients both get 202 `{"ok": true}`: the Worker accepts the mail either way, so senders
  cannot probe which addresses exist.
Parsing, storage under `inbox/email/` and the intake job are the existing InboundHandler (email_ingest.handle_raw).

The recipient travels in a header, not the query string, because access logs record URLs; Caddy drops the
X-Mentor-Rcpt and X-Mentor-Signature headers from its log. This module logs only the first characters of the
address code and the size, never addresses, subjects or content.
"""

import hashlib
import hmac
import logging
import re
import time
from collections import deque
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from mentor_gateway.api.deps import get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.email_ingest import handle_raw

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/email", include_in_schema=False)

SIGNATURE_VERSION = "v1"
MAX_SKEW_SECONDS = 300
MAX_RCPT_CHARS = 320
_RCPT = re.compile(r"^[\x21-\x7e]+@[\x21-\x7e]+$")  # printable ASCII, one address; learner codes are ASCII
_TIMESTAMP = re.compile(r"^\d{1,12}$")


def signing_payload_prefix(timestamp: str, rcpt: str) -> bytes:
    """What precedes the body in the signed payload; newlines cannot occur in either header value."""
    return f"{SIGNATURE_VERSION}\n{timestamp}\n{rcpt}\n".encode("ascii")


def sign(secret: str, timestamp: str, rcpt: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), signing_payload_prefix(timestamp, rcpt), hashlib.sha256)
    mac.update(body)
    return f"{SIGNATURE_VERSION}={mac.hexdigest()}"


def _code(rcpt: str) -> str:
    """Rate-limit key: the local part without +tag, lower-cased (the handler resolves addresses the same way)."""
    local = rcpt.strip().strip("<>").lower().rsplit("@", 1)[0]
    return local.split("+", 1)[0]


def _masked(rcpt: str) -> str:
    return f"{_code(rcpt)[:3]}…"


class EmailWebhookGuard:
    """Per-recipient sliding one-hour window plus a short-lived memory of signatures already used (replays)."""

    WINDOW = 3600.0
    MAX_KEYS = 10_000

    def __init__(self, per_hour: int, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.per_hour = per_hour
        self.monotonic = monotonic
        self._calls: dict[str, deque[float]] = {}
        self._seen: dict[str, float] = {}  # signature -> monotonic expiry

    def first_use(self, signature: str) -> bool:
        now = self.monotonic()
        for sig in [s for s, exp in self._seen.items() if exp <= now]:
            del self._seen[sig]
        if signature in self._seen:
            return False
        self._seen[signature] = now + 2 * MAX_SKEW_SECONDS + 60  # longer than any timestamp stays acceptable
        return True

    def check(self, key: str) -> float | None:
        """Record one message for `key`; None if allowed, else seconds until the next slot."""
        now = self.monotonic()
        if len(self._calls) > self.MAX_KEYS:  # random unknown addresses must not grow this forever
            for k in [k for k, q in self._calls.items() if not q or now - q[-1] >= self.WINDOW]:
                del self._calls[k]
        calls = self._calls.setdefault(key, deque())
        while calls and now - calls[0] >= self.WINDOW:
            calls.popleft()
        if len(calls) >= self.per_hour:
            return self.WINDOW - (now - calls[0])
        calls.append(now)
        return None


async def _read_capped(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "message too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _guard(gw: Gateway) -> EmailWebhookGuard:
    if gw.email_guard is None:
        gw.email_guard = EmailWebhookGuard(gw.settings.email_webhook_per_rcpt_per_hour)
    return gw.email_guard


@router.post("/inbound", status_code=202)
async def inbound(
    request: Request,
    x_mentor_rcpt: str | None = Header(None),
    x_mentor_timestamp: str | None = Header(None),
    x_mentor_signature: str | None = Header(None),
    gw: Gateway = Depends(get_gw),
):
    secret = gw.settings.email_webhook_secret
    if not secret:
        raise HTTPException(404)
    limit = gw.settings.inbound_email_max_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        log.info("email webhook: refused %s bytes (max %d)", declared, limit)
        raise HTTPException(413, "message too large")

    # cheap checks before reading up to `limit` bytes
    if not x_mentor_timestamp or not _TIMESTAMP.match(x_mentor_timestamp) or not x_mentor_signature:
        raise HTTPException(401, "missing or malformed signature headers")
    if abs(gw.clock().timestamp() - int(x_mentor_timestamp)) > MAX_SKEW_SECONDS:
        raise HTTPException(401, "stale timestamp")
    rcpt = (x_mentor_rcpt or "").strip()
    if len(rcpt) > MAX_RCPT_CHARS or not _RCPT.match(rcpt):
        raise HTTPException(400, "missing or malformed X-Mentor-Rcpt")

    body = await _read_capped(request, limit)
    expected = sign(secret, x_mentor_timestamp, rcpt, body)
    if not hmac.compare_digest(x_mentor_signature.strip().encode("ascii", "replace"), expected.encode("ascii")):
        log.warning("email webhook: bad signature (rcpt %s, %d bytes)", _masked(rcpt), len(body))
        raise HTTPException(401, "bad signature")

    guard = _guard(gw)
    if not guard.first_use(expected):
        log.info("email webhook: replayed request ignored (rcpt %s)", _masked(rcpt))
        return {"ok": True}
    retry = guard.check(_code(rcpt))
    if retry is not None:
        log.warning("email webhook: rate limit for rcpt %s (%d bytes)", _masked(rcpt), len(body))
        return JSONResponse({"detail": "too many messages for this recipient"}, status_code=429,
                            headers={"Retry-After": str(int(retry) + 1)})
    if gw.inbound is None:
        raise HTTPException(503, "email ingest unavailable")

    try:
        path = await handle_raw(gw.inbound, body, [rcpt])
    except Exception as exc:  # noqa: BLE001 -- any failure is a 500 (Worker retries); no traceback: it may quote the mail
        log.error("email webhook: processing failed for rcpt %s (%d bytes): %s", _masked(rcpt), len(body),
                  type(exc).__name__)
        raise HTTPException(500, "processing failed") from None
    log.info("email webhook: rcpt %s, %d bytes, %s", _masked(rcpt), len(body),
             "stored" if path else "dropped (no learner with this address)")
    return {"ok": True}
