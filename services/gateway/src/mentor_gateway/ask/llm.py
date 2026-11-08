"""Model calls for Q&A and the guide: router aliases (`mentor-chat|vision|audio|reasoning`), streamed, retried.

Router mode: POST {MODEL_ROUTER_URL}/v1/chat/completions with the alias as the model name (the planner does the same).
Direct mode (dev/live tests only): POST {FPT_API_BASE}/chat/completions with the real name from DIRECT_MODELS; no other
`fai/` name is ever sent (an unknown name locks the whole group for ~2 minutes, P0).
"""

import base64
import json
import logging
from typing import Any, Protocol

import httpx
from mentor_schemas import ModelAlias

log = logging.getLogger(__name__)

DIRECT_MODELS: dict[str, str] = {
    ModelAlias.VISION.value: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.AUDIO.value: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.REASONING.value: "fai/Alibaba:DeepSeek-V4.1-Flash",
    ModelAlias.CHAT.value: "fai/Alibaba:DeepSeek-V4.1-Flash",
}


class LLMError(Exception):
    pass


class ChatLLM(Protocol):
    async def complete(self, alias: str, messages: list[dict[str, Any]], *, max_tokens: int = 2000,
                       temperature: float = 0.3) -> str: ...
    # RouterChatLLM also takes `effort=` (reasoning_effort) and sets `supports_effort = True`; callers check the flag.


def image_part(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}


def audio_part(data: bytes, fmt: str = "wav") -> dict[str, Any]:
    return {"type": "input_audio", "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt}}


class RouterChatLLM:
    supports_effort = True  # router mode only: LiteLLM passes a per-request reasoning_effort over the alias default

    def __init__(self, url: str, key: str | None, *, direct: bool = False, timeout: float = 240.0, attempts: int = 3) -> None:
        self.url, self.key, self.direct, self.timeout, self.attempts = url.rstrip("/"), key or "", direct, timeout, attempts

    def _endpoint_and_model(self, alias: str) -> tuple[str, str]:
        if not self.direct:
            return f"{self.url}/v1/chat/completions", alias
        try:
            return f"{self.url}/chat/completions", DIRECT_MODELS[alias]
        except KeyError:
            raise LLMError(f"no direct model for alias {alias}") from None

    async def _once(self, alias: str, messages: list[dict[str, Any]], max_tokens: int, temperature: float,
                    effort: str | None = None) -> str:
        endpoint, model = self._endpoint_and_model(alias)
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True}
        if effort and not self.direct:
            body["reasoning_effort"] = effort
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        parts: list[str] = []
        client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=15.0))
        async with client, client.stream("POST", endpoint, json=body, headers=headers) as r:
            if r.status_code >= 400:
                raise LLMError(f"model HTTP {r.status_code}: {(await r.aread())[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta") or {}
                except (ValueError, KeyError, IndexError):
                    continue
                parts.append(delta.get("content") or "")
        text = "".join(parts)
        if not text.strip():
            raise LLMError("empty reply")
        return text

    async def complete(self, alias: str, messages: list[dict[str, Any]], *, max_tokens: int = 2000,
                       temperature: float = 0.3, effort: str | None = None) -> str:
        import asyncio

        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return await self._once(alias, messages, max_tokens, temperature, effort)
            except (LLMError, httpx.HTTPError) as e:
                last = e
                if isinstance(e, LLMError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e) and "HTTP 408" not in str(e):
                    break  # a client error will not get better
                if attempt + 1 < self.attempts:
                    await asyncio.sleep(1.5 * (attempt + 1))
        raise LLMError(f"model call failed ({alias}): {last.__class__.__name__}: {str(last)[:200]}") from last


def direct_from_env() -> RouterChatLLM | None:
    """Direct mode from FPT_API_BASE + FPT_API_KEY (env or the repo's .env.dev.local). For live tests, never in prod."""
    import os
    from pathlib import Path

    vals = {k: os.environ[k] for k in ("FPT_API_BASE", "FPT_API_KEY") if os.environ.get(k)}
    if len(vals) < 2:
        for d in Path(__file__).resolve().parents:
            f = d / ".env.dev.local"
            if f.is_file():
                for line in f.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    k, _, v = line.partition("=")
                    if k.strip() in ("FPT_API_BASE", "FPT_API_KEY") and k.strip() not in vals and v.strip():
                        vals[k.strip()] = v.strip().strip('"')
                break
    if len(vals) < 2:
        return None
    return RouterChatLLM(vals["FPT_API_BASE"], vals["FPT_API_KEY"], direct=True)
