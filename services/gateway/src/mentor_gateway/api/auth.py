"""`/api/auth/login` and `/api/auth/logout` (CONTRACTS section 4). Accounts are seeded; there is no sign-up, except in the
single-machine standalone package (`Settings.signup`), where `/auth/register` makes a local account.

With the central hub on (`Settings.hub_url`, CONTRACTS-HUB.md section 3) register, login, forgot and reset go to the hub and
the local `User` row is a mirror of the hub account (password hash for offline login, hub token, teacher status, email)."""

import asyncio
import logging
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import bearer_token, current_user, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import User, WebSession
from mentor_gateway.hub import HubError, HubOffline
from mentor_gateway.provisioning import provision_workspace
from mentor_gateway.security import hash_password, hash_token, new_token, verify_password
from mentor_gateway.users import Role

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Checked against when the username is unknown, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 43 + "="


class LoginBody(BaseModel):
    username: str = Field(max_length=200)  # a username, or (hub) an email
    password: str = Field(max_length=200)
    role: Role | None = None  # optional; when sent and different from the account's role the answer is role_mismatch


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


async def _open_session(gw: Gateway, user: User) -> dict:
    if user.role == "student" and user.provisioned_at is None:
        # the learner workspace (practice evidence lives in it) is created on the first login
        warnings = await asyncio.to_thread(
            provision_workspace, gw.settings.content_dir, gw.sync, user.id, gw.users.profile(user),
            user.display_name, user.language or "vi",
        )
        for w in warnings:
            log.warning("provisioning %s: %s", user.id, w)
        user = gw.users.update(user.id, provisioned_at=gw.clock())
    token = new_token()
    now = gw.clock()
    with gw.db.session() as s:
        s.add(WebSession(token_hash=hash_token(token), user_id=user.id, created_at=now,
                         expires_at=now + timedelta(days=gw.settings.session_days)))
    return {"token": token, "user": gw.users.view(user).model_dump(mode="json", exclude_unset=True)}


async def _local_login(gw: Gateway, body: LoginBody, user: User | None) -> dict | JSONResponse:
    ok = await asyncio.to_thread(verify_password, body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok:
        return _error(401, "invalid_credentials")
    if body.role and user.role != body.role:
        return _error(403, "role_mismatch")
    return await _open_session(gw, user)


async def _hub_login(gw: Gateway, body: LoginBody) -> dict | JSONResponse:
    hub = gw.hub_client
    assert hub is not None
    ident = body.username.strip().lower()
    try:
        res = await asyncio.to_thread(hub.call, "POST", "/api/login", json={"login": ident, "password": body.password})
    except HubOffline:  # the hub cannot be reached: the last known password (mirror hash) still works
        local = await asyncio.to_thread(gw.users.by_login, ident)
        if local is None:
            raise
        return await _local_login(gw, body, local)
    except HubError as e:
        if e.code != "invalid_credentials":
            raise
        # an account made before the hub existed (0.2.x PCs): register it on the hub silently, then log in
        local = await asyncio.to_thread(gw.users.by_login, ident)
        ok = local is not None and local.hub_id is None and await asyncio.to_thread(
            verify_password, body.password, local.password_hash)
        if not ok:
            return _error(401, "invalid_credentials")
        if body.role and local.role != body.role:
            return _error(403, "role_mismatch")
        payload = {"role": local.role, "username": local.username, "password": body.password,
                   "display_name": local.display_name or local.username}
        if local.email:
            payload["email"] = local.email
        try:
            res = await asyncio.to_thread(hub.call, "POST", "/api/register", json=payload)
        except HubError as e2:
            if e2.code in ("username_taken", "email_taken"):  # someone else owns the name on the hub
                return _error(401, "invalid_credentials")
            raise
    assert res is not None
    account = res["account"]
    if body.role and account.get("role") != body.role:
        return _error(403, "role_mismatch")
    user = await asyncio.to_thread(gw.users.mirror_hub, account, res.get("token"), body.password)
    return await _open_session(gw, user)


@router.post("/login", response_model=None)
async def login(body: LoginBody, gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    if gw.hub_client is not None:
        return await _hub_login(gw, body)
    return await _local_login(gw, body, await asyncio.to_thread(gw.users.by_username, body.username))


_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")


class RegisterBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)
    role: Role
    display_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=200)  # hub: required for teachers
    grade: str | None = Field(default=None, max_length=4)  # "1".."12" or "dh"; sets birth_year
    parent_email: str | None = Field(default=None, max_length=200)  # hub only


@router.get("/config")
def auth_config(gw: Gateway = Depends(get_gw)) -> dict:
    """What the login screen may offer: local sign-up exists only in the standalone package, or with the hub on.
    `hub` is present (true) only when the hub is on; absent means off."""
    if gw.hub_client is not None:
        return {"signup": True, "hub": True}
    return {"signup": gw.settings.signup}


@router.post("/register", response_model=None)
async def register(body: RegisterBody, gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    """Sign-up: a new account for the person using this PC, signed in at once (the hub makes it when it is on)."""
    if gw.hub_client is not None:
        return await _hub_register(gw, body)
    if not gw.settings.signup:
        return _error(404, "not_found")
    username = body.username.strip().lower()
    if not _USERNAME.match(username) or len(body.password) < 6:
        return _error(422, "bad_request")
    if await asyncio.to_thread(gw.users.by_username, username) is not None:
        return _error(409, "username_taken")
    user = await asyncio.to_thread(
        gw.users.create, username=username, password=body.password, role=body.role,
        display_name=(body.display_name or "").strip() or body.username.strip(), language="vi",
        birth_year=gw.users.birth_year_for_grade(body.grade),
    )
    return await _open_session(gw, user)


async def _hub_register(gw: Gateway, body: RegisterBody) -> dict | JSONResponse:
    payload = {"role": body.role, "username": body.username.strip().lower(), "password": body.password,
               "display_name": (body.display_name or "").strip() or body.username.strip()}
    for k in ("email", "grade", "parent_email"):
        if getattr(body, k):
            payload[k] = getattr(body, k).strip()
    res = await asyncio.to_thread(gw.hub_client.call, "POST", "/api/register", json=payload)
    assert res is not None
    user = await asyncio.to_thread(gw.users.mirror_hub, res["account"], res.get("token"), body.password)
    return await _open_session(gw, user)


class LoginRef(BaseModel):
    login: str = Field(max_length=200)


class ForgotRequest(LoginRef):
    phone: str | None = Field(default=None, max_length=40)


class ResetBody(LoginRef):
    code: str = Field(max_length=12)
    password: str = Field(max_length=200)


@router.post("/forgot", response_model=None)
async def forgot(body: LoginRef, gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    """Hub: emails a 6-digit code to the address on record. `{via: "email", to}` or `{via: "none"}`."""
    if gw.hub_client is None:
        return _error(404, "not_found")
    res = await asyncio.to_thread(gw.hub_client.call, "POST", "/api/forgot", json={"login": body.login.strip()})
    return res or {"via": "none"}


@router.post("/forgot/request", status_code=204, response_model=None)
async def forgot_request(body: ForgotRequest, gw: Gateway = Depends(get_gw)) -> Response:
    """Hub: adds a reset request to the owner's list (for a person with no email on record)."""
    if gw.hub_client is None:
        return _error(404, "not_found")
    payload = {"login": body.login.strip(), **({"phone": body.phone} if body.phone else {})}
    await asyncio.to_thread(gw.hub_client.call, "POST", "/api/forgot/request", json=payload)
    return Response(status_code=204)


@router.post("/reset", status_code=204, response_model=None)
async def reset(body: ResetBody, gw: Gateway = Depends(get_gw)) -> Response:
    """Hub: new password with the emailed code. The local mirror hash follows, so offline login uses the new one."""
    if gw.hub_client is None:
        return _error(404, "not_found")
    await asyncio.to_thread(gw.hub_client.call, "POST", "/api/reset",
                            json={"login": body.login.strip(), "code": body.code.strip(), "password": body.password})
    local = await asyncio.to_thread(gw.users.by_login, body.login)
    if local is not None:
        new_hash = await asyncio.to_thread(hash_password, body.password)
        await asyncio.to_thread(gw.users.update, local.id, password_hash=new_hash)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(request: Request, _user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> Response:
    token = bearer_token(request)
    with gw.db.session() as s:
        row = s.get(WebSession, hash_token(token)) if token else None
        if row is not None:
            s.delete(row)
    return Response(status_code=204)
