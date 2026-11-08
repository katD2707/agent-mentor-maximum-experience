"""Notifications ("nudges"), their actions, engagement numbers and Web Push subscriptions (CONTRACTS section 9)."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from mentor_gateway.api.deps import current_user, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.push import PushSubscriptionError

log = logging.getLogger(__name__)
router = APIRouter(tags=["nudges"])


@router.get("/notifications")
def list_notifications(limit: int = Query(30, ge=1, le=100), user: User = Depends(current_user),
                       gw: Gateway = Depends(get_gw)) -> list[dict]:
    """Notifications the learner has received, newest first (the notification centre; push opens land here)."""
    return [i.view() for i in gw.hub.recent(user.id, limit)]


class ActionBody(BaseModel):
    action: str = Field(..., min_length=1, max_length=64)


@router.post("/notifications/{notification_id}/action")
async def notification_action(notification_id: int, body: ActionBody, user: User = Depends(current_user),
                              gw: Gateway = Depends(get_gw)) -> dict:
    try:
        result = await gw.nudges.apply(user, notification_id, body.action)
    except LookupError as exc:
        raise HTTPException(404, "notification not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    gw.engagement.forget(user.id)
    return result


@router.get("/engagement")
async def engagement(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    return await asyncio.to_thread(gw.engagement.summary, user)


# ---- Web Push --------------------------------------------------------------------------------------


@router.get("/push/vapid-public-key")
def vapid_public_key(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    """`public_key` is null (and `enabled` false) when push is not configured: the web app hides the switch."""
    return {"enabled": gw.push.enabled, "public_key": gw.push.public_key,
            "subscribed_devices": gw.push.count(user.id)}


class SubscribeBody(BaseModel):
    subscription: dict[str, Any]  # PushSubscription.toJSON(): {endpoint, expirationTime?, keys: {p256dh, auth}}
    device: str | None = Field(default=None, max_length=64)  # optional client-chosen device id / label


@router.post("/push/subscribe")
def push_subscribe(body: SubscribeBody, user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    if not gw.push.enabled:
        raise HTTPException(503, "push notifications are not configured")
    try:
        sub_id = gw.push.subscribe(user.id, body.subscription, body.device)
    except PushSubscriptionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "id": sub_id}


class UnsubscribeBody(BaseModel):
    endpoint: str | None = Field(default=None, max_length=2048)
    subscription: dict[str, Any] | None = None


@router.delete("/push/subscribe")
def push_unsubscribe(body: UnsubscribeBody | None = Body(default=None), endpoint: str | None = Query(None),
                     user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    """One device (`endpoint`, in the body, `subscription.endpoint`, or `?endpoint=`) or, with none, all devices."""
    ep = endpoint
    if body is not None:
        ep = body.endpoint or (str(body.subscription.get("endpoint") or "") if body.subscription else None) or ep
    return {"ok": True, "removed": gw.push.unsubscribe(user.id, ep or None)}
