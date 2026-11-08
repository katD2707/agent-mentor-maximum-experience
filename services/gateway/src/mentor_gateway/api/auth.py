"""`/api/auth/login` and `/api/auth/logout` (CONTRACTS section 4). Accounts are seeded; there is no sign-up."""

import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import bearer_token, current_user, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import User, WebSession
from mentor_gateway.provisioning import provision_workspace
from mentor_gateway.security import hash_token, new_token, verify_password
from mentor_gateway.users import Role

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Checked against when the username is unknown, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + "A" * 43 + "="


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)
    role: Role


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


@router.post("/login", response_model=None)
async def login(body: LoginBody, gw: Gateway = Depends(get_gw)) -> dict | JSONResponse:
    user = await asyncio.to_thread(gw.users.by_username, body.username)
    ok = await asyncio.to_thread(verify_password, body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok:
        return _error(401, "invalid_credentials")
    if user.role != body.role:
        return _error(403, "role_mismatch")
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
    return {"token": token, "user": gw.users.view(user).model_dump(mode="json")}


@router.post("/logout", status_code=204)
def logout(request: Request, _user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> Response:
    token = bearer_token(request)
    with gw.db.session() as s:
        row = s.get(WebSession, hash_token(token)) if token else None
        if row is not None:
            s.delete(row)
    return Response(status_code=204)
