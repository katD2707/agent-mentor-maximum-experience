"""Outbound mail: the login email with the magic link and the 6-digit code (CONTRACTS.md section 5).

Plain SMTP for a local catcher (Mailpit, port 1025), or an authenticated relay such as Gmail:
SMTP_HOST=smtp.gmail.com SMTP_PORT=587 SMTP_STARTTLS=true SMTP_USERNAME=<address> SMTP_PASSWORD=<app password>
(or port 465 with SMTP_SSL=true). Credentials are never sent over an unencrypted connection.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from mentor_gateway.settings import Settings

log = logging.getLogger(__name__)


class MailConfigError(RuntimeError):
    pass


def login_message(settings: Settings, to: str, link: str, code: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = "Đăng nhập AI mentor"
    msg.set_content(
        f"Bấm vào liên kết sau để đăng nhập (hết hạn sau {settings.magic_link_minutes} phút):\n\n{link}\n\n"
        f"Hoặc nhập mã đăng nhập này trong ứng dụng: {code}\n\n"
        "Nếu bạn không yêu cầu đăng nhập, hãy bỏ qua email này.\n"
    )
    return msg


def _connect(s: Settings) -> smtplib.SMTP:
    if s.smtp_ssl and s.smtp_starttls:
        raise MailConfigError("set SMTP_SSL or SMTP_STARTTLS, not both")
    if s.smtp_username and not (s.smtp_ssl or s.smtp_starttls):
        raise MailConfigError("SMTP_USERNAME needs SMTP_STARTTLS=true (port 587) or SMTP_SSL=true (port 465)")
    assert s.smtp_host
    if s.smtp_ssl:
        return smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context())
    smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
    if s.smtp_starttls:
        try:
            smtp.starttls(context=ssl.create_default_context())
        except BaseException:
            smtp.close()
            raise
    return smtp


def send_login_mail(settings: Settings, to: str, link: str, code: str) -> bool:
    """Send the login email; False when SMTP_HOST is unset (nothing sent). Raises on SMTP/config errors."""
    if not settings.smtp_host:
        log.warning("SMTP_HOST not set; login email for %s not sent", to)
        return False
    msg = login_message(settings, to, link, code)
    with _connect(settings) as smtp:
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(msg)
    return True
