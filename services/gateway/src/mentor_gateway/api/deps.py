"""Shared FastAPI dependencies: the Gateway container and the bearer-token user."""

from fastapi import Depends, HTTPException, Request
from starlette.requests import HTTPConnection

from mentor_gateway.context import Gateway
from mentor_gateway.db import User, WebSession
from mentor_gateway.security import hash_token


def get_gw(conn: HTTPConnection) -> Gateway:
    return conn.app.state.gw


def bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def user_from_token(gw: Gateway, token: str | None) -> User | None:
    if not token:
        return None
    with gw.db.session() as s:
        sess = s.get(WebSession, hash_token(token))
        if sess is None or sess.expires_at <= gw.clock():
            return None
        return s.get(User, sess.user_id)


def current_user(request: Request, gw: Gateway = Depends(get_gw)) -> User:
    user = user_from_token(gw, bearer_token(request))
    if user is None:
        raise HTTPException(401, {"error": "unauthorized"}, headers={"WWW-Authenticate": "Bearer"})
    return user


def student_user(user: User = Depends(current_user)) -> User:
    if user.role != "student":
        raise HTTPException(403, {"error": "role_mismatch"})
    return user
