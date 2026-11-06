import smtplib
import socket
from pathlib import Path
from types import SimpleNamespace

from email_fakes import DOMAIN, vietnamese_html_email
from mentor_email_ingest import InboundHandler
from mentor_email_ingest.dev_smtp import (
    AnyCodeDirectory,
    DirectoryWorkspaceWriter,
    PrintingJobQueue,
    SMTPHandler,
    serve,
)


def dev_handler(root: Path) -> tuple[InboundHandler, PrintingJobQueue]:
    jobs = PrintingJobQueue()
    return InboundHandler(AnyCodeDirectory(DOMAIN), DirectoryWorkspaceWriter(root), jobs, inbound_domain=DOMAIN), jobs


async def test_smtp_handler_accepts_and_rejects(tmp_path: Path) -> None:
    inbound, jobs = dev_handler(tmp_path)
    smtp = SMTPHandler(inbound)
    raw = vietnamese_html_email(to="me@gmail.com")
    ok = SimpleNamespace(original_content=raw, content=raw, rcpt_tos=[f"abc123@{DOMAIN}"])
    assert (await smtp.handle_DATA(None, None, ok)).startswith("250")
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert len(files) == 2 and all(f.startswith("abc123/inbox/email/") for f in files)
    assert jobs.jobs[0].payload["path"].startswith("inbox/email/")

    bad = SimpleNamespace(original_content=raw, content=raw, rcpt_tos=["x@elsewhere.vn"])
    assert (await smtp.handle_DATA(None, None, bad)).startswith("550")


def test_directory_writer_refuses_escape_and_overwrite(tmp_path: Path) -> None:
    writer = DirectoryWorkspaceWriter(tmp_path)
    assert writer.write_inbox_file("u", "email/a.md", b"x") == "inbox/email/a.md"
    for bad in ["../x.md", "email/../../x.md"]:
        try:
            writer.write_inbox_file("u", bad, b"x")
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    try:
        writer.write_inbox_file("u", "email/a.md", b"y")
    except FileExistsError:
        pass
    else:
        raise AssertionError("overwrote")


def test_real_smtp_roundtrip_on_localhost(tmp_path: Path) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    inbound, jobs = dev_handler(tmp_path)
    controller = serve(inbound, "127.0.0.1", port)
    try:
        with smtplib.SMTP("127.0.0.1", port, timeout=10) as client:
            client.sendmail("a@b.vn", [f"abc123@{DOMAIN}"], vietnamese_html_email())
            try:
                client.sendmail("a@b.vn", [f"nobody!@{DOMAIN}"], vietnamese_html_email())
            except smtplib.SMTPDataError as exc:
                assert exc.smtp_code == 550
            else:
                raise AssertionError("unknown recipient accepted")
    finally:
        controller.stop()
    assert [j.user_id for j in jobs.jobs] == ["abc123"]
