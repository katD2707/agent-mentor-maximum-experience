"""Development SMTP server that feeds an InboundHandler.

    uv run python -m mentor_email_ingest.dev_smtp --port 2525 [--root var/dev-email] [--domain inbox.mentor.local]

Standalone it uses simple adapters: any `<code>@<domain>` maps to user id `<code>`, files go to
`<root>/<user_id>/inbox/...`, jobs are printed. The gateway calls `serve()` with its real adapters.

Try it:  python -c "import smtplib; smtplib.SMTP('127.0.0.1', 2525).sendmail('a@b.vn', ['abc123@inbox.mentor.local'],
         b'Subject: test\\r\\n\\r\\nhello')"
"""

import argparse
import asyncio
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from aiosmtpd.controller import Controller
from mentor_schemas.sandbox_api import JobRequest

from mentor_email_ingest.handler import InboundHandler

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "inbox.mentor.local"


class SMTPHandler:
    """aiosmtpd handler: passes DATA (with envelope recipients) to an InboundHandler."""

    def __init__(self, inbound: InboundHandler) -> None:
        self.inbound = inbound

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        raw = envelope.original_content or envelope.content
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        try:
            path = await asyncio.to_thread(self.inbound.handle, raw, recipients=list(envelope.rcpt_tos))
        except Exception:
            log.exception("inbound handler failed")
            return "451 4.3.0 Temporary failure, try again later"
        if path is None:
            return "550 5.1.1 Message rejected: unknown recipient or too large"
        return "250 2.0.0 Message accepted"


def serve(
    inbound: InboundHandler, host: str = "127.0.0.1", port: int = 2525, max_bytes: int = 10_000_000
) -> Controller:
    """Start an SMTP server in a background thread and return its controller (call .stop() to end)."""
    controller = Controller(
        SMTPHandler(inbound),
        hostname=host,
        port=port,
        data_size_limit=max_bytes,
        enable_SMTPUTF8=True,
    )
    controller.start()
    return controller


# ---- standalone dev adapters --------------------------------------------------------------------


class AnyCodeDirectory:
    """`<code>@<domain>` -> user id `<code>` for any code of 3-64 chars [a-z0-9-]."""

    def __init__(self, domain: str = DEFAULT_DOMAIN) -> None:
        self.domain = domain.lower()

    def user_id_for_inbound_address(self, address: str) -> str | None:
        local, _, domain = address.lower().rpartition("@")
        if domain == self.domain and re.fullmatch(r"[a-z0-9-]{3,64}", local):
            return local
        return None


class DirectoryWorkspaceWriter:
    """Writes `<root>/<user_id>/inbox/<relative_name>`; refuses to overwrite (FileExistsError)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write_inbox_file(self, user_id: str, relative_name: str, data: bytes) -> str:
        parts = Path(relative_name).parts
        if Path(relative_name).is_absolute() or ".." in parts or not parts:
            raise ValueError(f"bad inbox path: {relative_name!r}")
        target = self.root / user_id / "inbox" / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "xb") as fh:
            fh.write(data)
        return f"inbox/{Path(relative_name).as_posix()}"


class PrintingJobQueue:
    def __init__(self) -> None:
        self.jobs: list[JobRequest] = []

    def enqueue(self, job: JobRequest) -> None:
        self.jobs.append(job)
        print(f"[job] {job.model_dump_json()}", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dev SMTP server for mentor inbound email")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2525)
    parser.add_argument("--root", default=os.environ.get("MENTOR_DATA_DIR", "var") + "/dev-email")
    parser.add_argument("--domain", default=os.environ.get("INBOUND_EMAIL_DOMAIN", DEFAULT_DOMAIN))
    parser.add_argument("--max-bytes", type=int, default=10_000_000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    inbound = InboundHandler(
        AnyCodeDirectory(args.domain),
        DirectoryWorkspaceWriter(Path(args.root)),
        PrintingJobQueue(),
        max_bytes=args.max_bytes,
        inbound_domain=args.domain,
    )
    controller = serve(inbound, args.host, args.port, args.max_bytes)
    print(f"dev SMTP on {args.host}:{args.port}, domain {args.domain}, files under {Path(args.root).resolve()}")
    stop = threading.Event()
    try:
        while not stop.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
