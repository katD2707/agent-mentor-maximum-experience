"""POST /webhooks/email/inbound: HMAC-signed raw mail from the Cloudflare Email Worker (infra/cloudflare/)."""

import logging
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mentor_gateway.api.email_webhook import EmailWebhookGuard, sign
from mentor_gateway.app import create_app
from mentor_gateway.db import JobRow
from mentor_gateway.settings import Settings

SECRET = "test-email-webhook-secret"
URL = "/webhooks/email/inbound"


@pytest.fixture
def settings(settings):  # conftest's settings + the webhook secret and small limits
    return settings.model_copy(update={"email_webhook_secret": SECRET, "inbound_email_max_bytes": 64_000,
                                       "email_webhook_per_rcpt_per_hour": 3})


def _mail(subject: str = "Fwd: Hạn nộp báo cáo tiến độ") -> bytes:
    msg = EmailMessage()
    msg["From"] = "thay@uni.edu.vn"
    msg["To"] = "learner@gmail.com"  # auto-forward keeps the learner's own address; the envelope has ours
    msg["Subject"] = subject
    msg["Date"] = "Wed, 28 Oct 2026 09:00:00 +0700"
    msg.set_content("Hạn nộp báo cáo tiến độ: 15/11/2026.")
    msg.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="thong-bao.pdf")
    return msg.as_bytes()


def _post(client, rcpt: str, body: bytes, *, ts: int | None = None, secret: str = SECRET, sig: str | None = None):
    ts = int(client.app.state.gw.clock().timestamp()) if ts is None else ts
    headers = {"X-Mentor-Rcpt": rcpt, "X-Mentor-Timestamp": str(ts),
               "X-Mentor-Signature": sig or sign(secret, str(ts), rcpt, body)}
    return client.post(URL, content=body, headers=headers)


def _jobs(gw, uid: str) -> list[JobRow]:
    with gw.db.session() as s:
        return list(s.scalars(select(JobRow).where(JobRow.user_id == uid)))


def _inbox(gw, uid: str) -> list[str]:
    return [e.path for e in gw.mirror.ls_tree(uid) if e.path.startswith("inbox/email/")]


def test_signature_scheme_is_pinned():
    # infra/cloudflare/email-worker.js must produce exactly this (HMAC-SHA256 over "v1\n<ts>\n<rcpt>\n" + body)
    # the same vector is in the header comment of the Worker (checked against its JS with node)
    assert sign("s3cret", "1761620400", "abc@inbox.example.vn", b"Subject: x\r\n\r\nhi") == \
        "v1=6d57ef202c587f48a250e7a5c9de1776ee1c42da33167d90558f58c98d67da77"


def test_valid_mail_lands_in_inbox_and_enqueues_intake(client, gw, ncs_user, caplog):
    if gw.inbound is None:
        pytest.skip("mentor_email_ingest not available")
    uid, addr = ncs_user["user_id"], ncs_user["inbound_email_address"]
    caplog.set_level(logging.INFO)
    r = _post(client, addr, _mail())
    assert r.status_code == 202 and r.json() == {"ok": True}
    files = _inbox(gw, uid)
    md = next(p for p in files if p.endswith(".md"))
    assert md.startswith("inbox/email/2026-10-28-") and any(p.endswith("thong-bao.pdf") for p in files)
    assert "KHÔNG TIN CẬY" in gw.mirror.read_text(uid, md)
    (job,) = _jobs(gw, uid)
    assert job.kind == "intake" and job.payload["path"] == md and job.payload["source"] == "email"
    # logs: code prefix and size only, never the address, subject or body
    assert addr not in caplog.text and addr.split("@")[0] not in caplog.text
    assert "bao-cao" not in caplog.text and "Hạn nộp" not in caplog.text and "thay@uni" not in caplog.text
    assert f"{addr[:3]}…" in caplog.text


def test_bad_signature_is_401_and_stores_nothing(client, gw, ncs_user):
    uid, addr = ncs_user["user_id"], ncs_user["inbound_email_address"]
    assert _post(client, addr, _mail(), secret="wrong-secret").status_code == 401
    assert _post(client, addr, _mail(), sig="v1=" + "0" * 64).status_code == 401
    # signed for another recipient / body: rejected
    ts = int(gw.clock().timestamp())
    other = sign(SECRET, str(ts), "zzz@inbox.mentor.local", _mail())
    assert _post(client, addr, _mail(), ts=ts, sig=other).status_code == 401
    assert _post(client, addr, _mail(), ts=ts, sig=sign(SECRET, str(ts), addr, b"other body")).status_code == 401
    assert client.post(URL, content=_mail(), headers={"X-Mentor-Rcpt": addr}).status_code == 401  # no headers
    assert _inbox(gw, uid) == [] and _jobs(gw, uid) == []


def test_replay_old_timestamp_and_duplicate_request(client, gw, ncs_user):
    uid, addr = ncs_user["user_id"], ncs_user["inbound_email_address"]
    now = int(gw.clock().timestamp())
    assert _post(client, addr, _mail(), ts=now - 301).status_code == 401  # correctly signed, but too old
    assert _post(client, addr, _mail(), ts=now + 301).status_code == 401  # or too far in the future
    assert _jobs(gw, uid) == []
    if gw.inbound is None:
        pytest.skip("mentor_email_ingest not available")
    # the very same signed request twice (captured and replayed inside the window): stored once
    body = _mail()
    assert _post(client, addr, body, ts=now - 200).status_code == 202
    assert _post(client, addr, body, ts=now - 200).status_code == 202
    assert len(_jobs(gw, uid)) == 1


def test_oversize_is_413(client, gw, ncs_user):
    uid, addr = ncs_user["user_id"], ncs_user["inbound_email_address"]
    big = _mail() + b"x" * 64_000
    assert _post(client, addr, big).status_code == 413
    assert _inbox(gw, uid) == [] and _jobs(gw, uid) == []


def test_unknown_recipient_is_202_like_a_known_one(client, gw, ncs_user):
    r = _post(client, "zzzzzzzzzz@inbox.mentor.local", _mail())
    assert r.status_code == 202 and r.json() == {"ok": True}
    r = _post(client, "someone@other-domain.vn", _mail())
    assert r.status_code == 202 and r.json() == {"ok": True}
    assert _jobs(gw, ncs_user["user_id"]) == []


def test_rate_limit_per_recipient(client, gw, ncs_user):
    addr = ncs_user["inbound_email_address"]
    for i in range(3):
        assert _post(client, addr, _mail(f"thư {i}")).status_code == 202
    r = _post(client, addr, _mail("thư 4"))
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    tagged = addr.replace("@", "+gvhd@")  # +tags share the learner's bucket
    assert _post(client, tagged, _mail("thư 5")).status_code == 429
    assert _post(client, "khac@inbox.mentor.local", _mail("thư 6")).status_code == 202  # other buckets unaffected


def test_malformed_rcpt_is_400(client):
    assert _post(client, "no-at-sign", _mail()).status_code == 400


def test_closed_without_secret(settings, clock, backend):
    app = create_app(settings.model_copy(update={"email_webhook_secret": None}), clock=clock, backend=backend)
    with TestClient(app) as c:
        assert _post(c, "a@inbox.mentor.local", _mail()).status_code == 404


def test_guard_window_and_settings_env():
    t = [0.0]
    g = EmailWebhookGuard(2, monotonic=lambda: t[0])
    assert g.check("a") is None and g.check("a") is None and g.check("a") == pytest.approx(3600)
    t[0] = 3600.0
    assert g.check("a") is None
    assert g.first_use("sig") and not g.first_use("sig")
    t[0] += 10_000
    assert g.first_use("sig")  # forgotten after the window
    s = Settings.from_env({"EMAIL_WEBHOOK_SECRET": "x", "INBOUND_EMAIL_MAX_BYTES": "1000",
                           "EMAIL_WEBHOOK_PER_RCPT_PER_HOUR": "5"})
    assert (s.email_webhook_secret, s.inbound_email_max_bytes, s.email_webhook_per_rcpt_per_hour) == ("x", 1000, 5)
    assert Settings.from_env({}).email_webhook_secret is None
