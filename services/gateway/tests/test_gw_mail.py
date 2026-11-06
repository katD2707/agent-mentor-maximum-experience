"""Outbound login mail: plain SMTP (Mailpit), STARTTLS/SSL + app-password auth (Gmail), and the prod request-link path."""

import base64
import re
import secrets
import socket
import ssl
from email import message_from_bytes, policy
from email.message import EmailMessage
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from mentor_gateway import mailer
from mentor_gateway.app import create_app
from mentor_gateway.settings import Settings

LINK = "https://mentor.example/api/auth/verify?token=abc"


class FakeSMTP:
    """Records the calls smtplib.SMTP / SMTP_SSL would make."""

    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.calls: list[tuple] = [("connect", host, port, type(self).__name__)]
        self.ssl_context = context
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send",))
        self.sent.append(msg)

    def close(self):
        self.calls.append(("close",))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTPSSL)
    return FakeSMTP.instances


def gmail_settings(**kw) -> Settings:
    base = {"env": "prod", "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_starttls": True,
            "smtp_username": "mentor.pilot@gmail.com", "smtp_password": "abcd efgh ijkl mnop",
            "mail_from": "AI Mentor <mentor.pilot@gmail.com>"}
    return Settings(**{**base, **kw})


def body_of(msg: EmailMessage) -> str:
    return msg.get_content()


def test_settings_read_smtp_env():
    s = Settings.from_env({"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "SMTP_STARTTLS": "true",
                           "SMTP_USERNAME": "a@gmail.com", "SMTP_PASSWORD": "pw", "MAIL_FROM": "a@gmail.com"})
    assert (s.smtp_host, s.smtp_port, s.smtp_starttls, s.smtp_ssl) == ("smtp.gmail.com", 587, True, False)
    assert (s.smtp_username, s.smtp_password, s.mail_from) == ("a@gmail.com", "pw", "a@gmail.com")
    assert Settings.from_env({"SMTP_SSL": "1"}).smtp_ssl is True
    assert Settings.from_env({}).smtp_starttls is False


def test_gmail_starttls_then_login_then_send(fake_smtp):
    assert mailer.send_login_mail(gmail_settings(), "hs@example.com", LINK, "042917") is True
    (smtp,) = fake_smtp
    assert smtp.calls == [("connect", "smtp.gmail.com", 587, "FakeSMTP"), ("starttls",),
                          ("login", "mentor.pilot@gmail.com", "abcd efgh ijkl mnop"), ("send",), ("quit",)]
    msg = smtp.sent[0]
    assert msg["To"] == "hs@example.com" and msg["From"] == "AI Mentor <mentor.pilot@gmail.com>"
    assert msg["Subject"] == "Đăng nhập AI mentor"
    body = body_of(msg)
    assert LINK in body and "042917" in body and "Bấm vào liên kết sau để đăng nhập" in body
    assert "hết hạn sau 15 phút" in body


def test_implicit_ssl_port_465(fake_smtp):
    mailer.send_login_mail(gmail_settings(smtp_port=465, smtp_starttls=False, smtp_ssl=True),
                           "a@b.vn", LINK, "000001")
    (smtp,) = fake_smtp
    assert smtp.calls[0] == ("connect", "smtp.gmail.com", 465, "FakeSMTPSSL")
    assert ("starttls",) not in smtp.calls
    assert isinstance(smtp.ssl_context, ssl.SSLContext) and smtp.ssl_context.check_hostname
    assert ("login", "mentor.pilot@gmail.com", "abcd efgh ijkl mnop") in smtp.calls


def test_credentials_never_go_over_plaintext(fake_smtp):
    with pytest.raises(mailer.MailConfigError, match="SMTP_STARTTLS"):
        mailer.send_login_mail(gmail_settings(smtp_starttls=False), "a@b.vn", LINK, "123456")
    with pytest.raises(mailer.MailConfigError, match="not both"):
        mailer.send_login_mail(gmail_settings(smtp_ssl=True), "a@b.vn", LINK, "123456")
    assert fake_smtp == []  # refused before connecting


def test_no_smtp_host_sends_nothing(fake_smtp):
    assert mailer.send_login_mail(Settings(env="prod"), "a@b.vn", LINK, "123456") is False
    assert fake_smtp == []


# ---- prod request-link against a real (local, plain) SMTP server ----------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Collect:
    def __init__(self):
        self.messages: list[bytes] = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope.content)
        return "250 OK"


@pytest.fixture
def prod_client(tmp_path, clock, backend, monkeypatch):
    monkeypatch.setenv("MENTOR_MASTER_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())

    def make(port: int):
        settings = Settings(env="prod", data_dir=tmp_path / "var", public_base_url="https://mentor.example",
                            web_origin="https://mentor.example", background_tasks=False, sandbox_prewarm=False,
                            smtp_host="127.0.0.1", smtp_port=port, mail_from="mentor.pilot@gmail.com")
        return TestClient(create_app(settings, clock=clock, backend=backend))

    return make


def test_prod_request_link_mails_link_and_code(prod_client):
    from aiosmtpd.controller import Controller

    port = _free_port()
    handler = Collect()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        with prod_client(port) as c:
            r = c.post("/api/auth/request-link", json={"email": "HS@Example.com"})
    finally:
        controller.stop()
    assert r.status_code == 200 and r.json() == {"sent": True}  # no dev_link / dev_code in prod
    (raw,) = handler.messages
    body = message_from_bytes(raw, policy=policy.default).get_content()
    link = re.search(r"https://mentor\.example/api/auth/verify\?token=\S+", body)
    code = re.search(r"mã đăng nhập này trong ứng dụng: (\d{6})", body)
    assert link and code


def test_prod_request_link_smtp_down_is_502(prod_client, caplog):
    with prod_client(_free_port()) as c:  # nothing listens there
        r = c.post("/api/auth/request-link", json={"email": "a@b.vn"})
    assert r.status_code == 502 and "Không gửi được email" in r.json()["detail"]
    assert "token=" not in caplog.text
