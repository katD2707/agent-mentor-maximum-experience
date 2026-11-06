"""Shared FastAPI dependencies: the Gateway container and the session user."""

from fastapi import Depends, HTTPException, Request
from starlette.requests import HTTPConnection

from mentor_gateway.context import Gateway
from mentor_gateway.db import User, WebSession
from mentor_gateway.security import hash_token

COOKIE_NAME = "mentor_session"


def get_gw(conn: HTTPConnection) -> Gateway:
    return conn.app.state.gw


def user_from_cookie(gw: Gateway, token: str | None) -> User | None:
    if not token:
        return None
    with gw.db.session() as s:
        sess = s.get(WebSession, hash_token(token))
        if sess is None or sess.expires_at <= gw.clock():
            return None
        return s.get(User, sess.user_id)


def current_user(request: Request, gw: Gateway = Depends(get_gw)) -> User:
    user = user_from_cookie(gw, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, "not authenticated")
    return user


def provisioned_user(user: User = Depends(current_user)) -> User:
    if user.provisioned_at is None or not user.role:
        raise HTTPException(409, "onboarding not finished")
    return user


def active_user(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> User:
    state = gw.users.onboarding_state(user)
    if state != "active":
        raise HTTPException(403, f"account not active: {state}")
    return user
