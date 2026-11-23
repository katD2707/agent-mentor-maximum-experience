"""`/api/ai-key`: the user's own AI key for this installation (direct mode, see `mentor_gateway.userai`).

Any logged-in user may read, set, test and delete it (the gateway runs on the user's own machine). The key is never
returned: only a masked tail. With a model router configured (dev, hosted) the key is not used and writes return 409.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from mentor_gateway import userai
from mentor_gateway.api.deps import current_user, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import User

router = APIRouter(prefix="/ai-key", tags=["ai-key"])


class AIKeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: str | None = None
    key: str | None = None  # blank/None keeps the saved key (edit the address or models without retyping it)
    models: dict[str, str] | None = None


def _store(gw: Gateway) -> userai.UserAIStore:
    if gw.ai_store is None:
        raise HTTPException(409, {"error": "router_mode"})
    return gw.ai_store


def _merge(gw: Gateway, body: AIKeyIn) -> userai.UserAIConfig:
    saved = _store(gw).get()
    try:
        base = userai.clean_base(body.base) if (body.base or "").strip() else (saved.base if saved else userai.DEFAULT_BASE)
        key = userai.clean_key(body.key) if (body.key or "").strip() else (saved.key if saved else "")
        models = userai.clean_models(body.models) if body.models is not None else (saved.models if saved else {})
    except userai.AIConfigError as e:
        raise HTTPException(422, {"error": str(e)}) from None
    if not key:
        raise HTTPException(422, {"error": "bad_key"})
    return userai.UserAIConfig(base, key, models)


@router.get("")
def get_status(_user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict[str, Any]:
    if gw.ai_store is None:
        return {**userai.status(userai.UserAIStore(gw.settings.data_dir), router=True), "configured": True}
    return userai.status(gw.ai_store)


@router.put("")
def save(body: AIKeyIn, _user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict[str, Any]:
    cfg = _merge(gw, body)
    _store(gw).save(cfg)
    return userai.status(_store(gw))


@router.post("/test")
async def test(body: AIKeyIn | None = None, _user: User = Depends(current_user),
               gw: Gateway = Depends(get_gw)) -> dict[str, Any]:
    """One tiny chat call with the form's values (or the saved ones). Always 200: `{ok, code, message}`."""
    cfg = _merge(gw, body or AIKeyIn())
    return await asyncio.to_thread(userai.probe, cfg)


@router.delete("")
def delete(_user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict[str, Any]:
    _store(gw).clear()
    return userai.status(_store(gw))
