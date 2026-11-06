"""Email magic-link auth plus a 6-digit login code for the desktop pop-up (CONTRACTS.md section 5)."""

import asyncio
import hmac
import logging
import re
import secrets
import smtplib
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from mentor_gateway.api.deps import COOKIE_NAME, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import LoginCode, MagicLink, User, WebSession
from mentor_gateway.mailer import MailConfigError, send_login_mail
from mentor_gateway.security import hash_token, new_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_RE = re.compile(r"^\d{6}$")
MAX_CODE_ATTEMPTS = 5


class LinkRequest(BaseModel):
    email: str


class CodeRequest(BaseModel):
    email: str
    code: str


def _new_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(token_hash: str, code: str) -> str:
    # Salted with the link's token hash so equal codes of different logins hash differently.
    return hash_token(f"{token_hash}:{code}")


def _send_mail(gw: Gateway, to: str, link: str, code: str) -> None:
    send_login_mail(gw.settings, to, link, code)


def _allowed(email: str, allowlist: str) -> bool:
    """Empty allowlist = open signup; entries are full emails or "@domain"."""
    entries = {e.strip().lower() for e in allowlist.split(",") if e.strip()}
    return not entries or email in entries or "@" + email.rsplit("@", 1)[1] in entries


@router.post("/request-link")
async def request_link(body: LinkRequest, gw: Gateway = Depends(get_gw)) -> dict:
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "invalid email")
    if not _allowed(email, gw.settings.signup_allowlist):
        raise HTTPException(403, "Email này chưa được mời dùng thử Mentor. Liên hệ người quản lý để được thêm vào danh sách.")
    token = new_token()
    token_hash = hash_token(token)
    code = _new_login_code()
    now = gw.clock()
    with gw.db.session() as s:
        # Each request brings fresh code guesses, so cap requests per email: a link issued within the last hour
        # expires after now + 1h - link lifetime.
        lifetime = timedelta(minutes=gw.settings.magic_link_minutes)
        recent = s.query(MagicLink).filter(MagicLink.email == email,
                                           MagicLink.expires_at > now - timedelta(hours=1) + lifetime).count()
        # Dev only: logins are scripted and repeated all day; test and prod keep the cap.
        if gw.settings.env != "dev" and recent >= gw.settings.login_requests_per_hour:
            raise HTTPException(429, "Bạn đã yêu cầu đăng nhập quá nhiều lần, thử lại sau 1 giờ.",
                                headers={"Retry-After": "3600"})
        # A new request supersedes older codes for this email (their links keep working until they expire).
        s.query(LoginCode).filter(LoginCode.email == email).delete(synchronize_session=False)
        s.add(MagicLink(token_hash=token_hash, email=email,
                        expires_at=now + timedelta(minutes=gw.settings.magic_link_minutes)))
        s.flush()
        s.add(LoginCode(token_hash=token_hash, email=email, code_hash=_hash_code(token_hash, code), created_at=now))
    link = f"{gw.settings.public_base_url.rstrip('/')}/api/auth/verify?token={token}"
    if gw.settings.env in ("dev", "test"):
        return {"sent": True, "dev_link": link, "dev_code": code}
    try:
        await asyncio.to_thread(_send_mail, gw, email, link, code)
    except (OSError, smtplib.SMTPException, MailConfigError) as exc:  # SMTP down, wrong app password, ...
        # the link and code themselves are never logged
        log.error("login email to %s failed: %s: %s", email, type(exc).__name__, exc)
        raise HTTPException(502, "Không gửi được email đăng nhập, vui lòng thử lại sau.") from None
    return {"sent": True}


def _start_session(gw: Gateway, email: str) -> tuple[str, str]:
    """Create a web session for `email`; returns (session token, path to land on)."""
    now = gw.clock()
    user: User = gw.users.get_or_create(email)
    session_token = new_token()
    with gw.db.session() as s:
        s.add(WebSession(token_hash=hash_token(session_token), user_id=user.id, created_at=now,
                         expires_at=now + timedelta(days=gw.settings.session_days)))
    target = "/chat" if gw.users.onboarding_state(user) == "active" else "/onboarding"
    return session_token, target


def _set_session_cookie(gw: Gateway, resp: Response, session_token: str) -> None:
    resp.set_cookie(COOKIE_NAME, session_token, max_age=gw.settings.session_days * 86400, httponly=True,
                    samesite="lax", secure=gw.settings.cookie_secure, path="/")


@router.get("/verify")
def verify(token: str, gw: Gateway = Depends(get_gw)) -> Response:
    now = gw.clock()
    with gw.db.session() as s:
        ml = s.get(MagicLink, hash_token(token))
        if ml is None or ml.used_at is not None or ml.expires_at <= now:
            raise HTTPException(400, "link invalid or expired")
        ml.used_at = now
        email = ml.email
    session_token, target = _start_session(gw, email)
    resp = RedirectResponse(gw.settings.web_url + target, status_code=302)
    _set_session_cookie(gw, resp, session_token)
    return resp


@router.post("/verify-code")
def verify_code(body: CodeRequest, gw: Gateway = Depends(get_gw)) -> Response:
    """Sign in with the 6-digit code from the login email (same pending login as the link).

    Only the newest code requested for the email exists (request-link deletes older ones).
    5 wrong codes invalidate that login, link included.
    """
    email = body.email.strip().lower()
    code = re.sub(r"\s+", "", body.code)
    if not _EMAIL_RE.match(email) or not _CODE_RE.match(code):
        raise HTTPException(422, "invalid email or code")
    now = gw.clock()
    ok = False
    with gw.db.session() as s:
        lc = s.query(LoginCode).filter(LoginCode.email == email).order_by(LoginCode.created_at.desc()).first()
        ml = s.get(MagicLink, lc.token_hash) if lc is not None else None
        if lc is not None and ml is not None and ml.used_at is None and ml.expires_at > now:
            if hmac.compare_digest(lc.code_hash, _hash_code(lc.token_hash, code)):
                ml.used_at = now
                ok = True
            else:
                lc.failed_attempts += 1
                if lc.failed_attempts >= MAX_CODE_ATTEMPTS:
                    ml.used_at = now  # too many wrong codes: this login (code and link) is dead
                    log.warning("login code for %s invalidated after %d wrong attempts", email, lc.failed_attempts)
    if not ok:
        raise HTTPException(400, "code invalid or expired")
    session_token, target = _start_session(gw, email)
    resp = JSONResponse({"ok": True, "next": target})
    _set_session_cookie(gw, resp, session_token)
    return resp


@router.post("/logout")
def logout(request: Request, gw: Gateway = Depends(get_gw)) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with gw.db.session() as s:
            sess = s.get(WebSession, hash_token(token))
            if sess is not None:
                s.delete(sess)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
