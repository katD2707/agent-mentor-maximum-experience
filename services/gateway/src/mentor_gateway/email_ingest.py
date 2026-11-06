"""Inbound email wiring (CONTRACTS.md section 7): adapters for Track E's InboundHandler.

Mail reaches the handler either through the in-process SMTP server (INBOUND_SMTP_PORT, aiosmtpd, envelope
recipients passed through) or through `POST /internal/email/inbound?rcpt=<addr>` (raw RFC 822 body, header
`X-Internal-Token`), or in production through the HMAC-signed `POST /webhooks/email/inbound` that the Cloudflare
Email Worker calls (api/email_webhook.py). Envelope recipients matter: auto-forwarded mail keeps the learner's own address in To:.
"""

import asyncio
import inspect
import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from mentor_schemas import Profile, WorkspacePaths

from mentor_gateway.jobs import JobStore
from mentor_gateway.mirror import Mirror, StaleBaseError, normalize_path
from mentor_gateway.users import UserService

log = logging.getLogger(__name__)


class MirrorWorkspaceWriter:
    """WorkspaceWriter: commits inbox files into the mirror; the sandbox pulls them before the intake job.

    Never overwrites: an existing path raises FileExistsError (the handler then picks another name).
    """

    def __init__(self, mirror: Mirror) -> None:
        self.mirror = mirror

    def write_inbox_file(self, user_id: str, relative_name: str, data: bytes) -> str:
        rel = normalize_path(relative_name)
        if not rel.startswith(WorkspacePaths.INBOX_DIR + "/"):
            rel = f"{WorkspacePaths.INBOX_DIR}/{rel}"
        try:
            self.mirror.commit_files(user_id, {rel: data}, author="system", message=f"Email chuyển tiếp: {rel}",
                                     expected={rel: None})
        except StaleBaseError as exc:
            raise FileExistsError(rel) from exc
        return rel


def build_inbound_handler(users: UserService, mirror: Mirror, jobs: JobStore, domain: str,
                          clock: Callable[[], datetime], *, max_bytes: int = 10_000_000) -> Any | None:
    try:
        from mentor_email_ingest import InboundHandler
    except ImportError as exc:
        log.warning("mentor_email_ingest unavailable (%s); inbound email disabled", exc)
        return None

    def profile_for(user_id: str) -> Profile:
        user = users.get(user_id)
        return (users.profile(user) if user else None) or Profile.NCS

    return InboundHandler(users, MirrorWorkspaceWriter(mirror), jobs, max_bytes, inbound_domain=domain,
                          profile_for=profile_for, now=clock)


async def handle_raw(handler: Any, raw: bytes, recipients: Iterable[str] | None = None) -> str | None:
    rcpts = list(recipients) if recipients else None
    result = await asyncio.to_thread(handler.handle, raw, recipients=rcpts)
    if inspect.isawaitable(result):
        result = await result
    return result


def start_smtp_server(handler: Any, port: int, host: str = "127.0.0.1") -> Any | None:
    """Start an aiosmtpd controller feeding the handler (with envelope recipients); returns it (call .stop())."""
    try:
        from aiosmtpd.controller import Controller
        from mentor_email_ingest.dev_smtp import SMTPHandler
    except ImportError:
        log.warning("aiosmtpd / mentor_email_ingest.dev_smtp unavailable; INBOUND_SMTP_PORT ignored")
        return None
    controller = Controller(SMTPHandler(handler), hostname=host, port=port)
    try:
        controller.start()
    except OSError:
        log.exception("inbound SMTP could not start on %s:%d; continuing without it", host, port)
        return None
    log.info("inbound SMTP listening on %s:%d", host, port)
    return controller
