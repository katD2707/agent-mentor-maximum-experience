"""Model access for the course builder: OpenAI-compatible chat completions, streamed, with retry.

Two modes:
- router (default): `MODEL_ROUTER_URL` + `MODEL_ROUTER_KEY`; the model name is the `ModelAlias` value.
- direct (`COURSE_BUILDER_DIRECT=1`): `FPT_API_BASE` + `FPT_API_KEY` (env, or `.env.dev.local` found by walking up from
  the cwd / `COURSE_BUILDER_ENV_FILE`), with the real model names of `DIRECT_MODELS`.

Keys are never logged or put in error messages. Only model names listed in `DIRECT_MODELS` are ever sent in direct mode:
one call to a non-existent `fai/` model locks every fai model for ~2 minutes.
"""

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from mentor_schemas import ModelAlias

log = logging.getLogger("mentor_course_builder")

DIRECT_MODELS: dict[ModelAlias, str] = {
    ModelAlias.VISION: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.AUDIO: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.REASONING: "fai/Alibaba:DeepSeek-V4.1-Flash",
    ModelAlias.CHAT: "fai/Alibaba:DeepSeek-V4.1-Flash",
}


class ModelError(Exception):
    """The model endpoint failed, timed out or returned something unusable."""


def _read_env_file(path: Path, keys: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() in keys:
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _find_env_file() -> Path | None:
    explicit = os.environ.get("COURSE_BUILDER_ENV_FILE")
    if explicit:
        return Path(explicit)
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for d in (start, *start.parents):
            f = d / ".env.dev.local"
            if f.is_file():
                return f
    return None


def image_part(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}


def audio_part(data: bytes, fmt: str = "mp3") -> dict[str, Any]:
    return {"type": "input_audio", "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt}}


class ModelClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        direct: bool = False,
        timeout_s: float = 180.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.direct = direct
        self._retries = retries
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> "ModelClient":
        if os.environ.get("COURSE_BUILDER_DIRECT") == "1":
            base, key = os.environ.get("FPT_API_BASE", ""), os.environ.get("FPT_API_KEY", "")
            if not (base and key):
                f = _find_env_file()
                if f and f.is_file():
                    vals = _read_env_file(f, {"FPT_API_BASE", "FPT_API_KEY"})
                    base, key = base or vals.get("FPT_API_BASE", ""), key or vals.get("FPT_API_KEY", "")
            if not (base and key):
                raise ModelError("direct mode needs FPT_API_BASE and FPT_API_KEY (env or .env.dev.local)")
            return cls(base, key, direct=True)
        url = os.environ.get("MODEL_ROUTER_URL", "")
        if not url:
            raise ModelError("set MODEL_ROUTER_URL (+ MODEL_ROUTER_KEY), or COURSE_BUILDER_DIRECT=1 for direct mode")
        return cls(url, os.environ.get("MODEL_ROUTER_KEY", ""))

    def close(self) -> None:
        self._client.close()

    def model_name(self, alias: ModelAlias) -> str:
        if not self.direct:
            return alias.value
        try:
            return DIRECT_MODELS[alias]
        except KeyError:
            raise ModelError(f"no direct model for alias {alias.value}") from None

    def complete(
        self, alias: ModelAlias, messages: list[dict[str, Any]], *, max_tokens: int = 8000, temperature: float = 0.0
    ) -> str:
        """Return the assistant text. Streams (avoids gateway 524 on long calls); retries transient failures."""
        alias = ModelAlias(alias)
        body = {
            "model": self.model_name(alias),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        last = "unknown error"
        for attempt in range(self._retries + 1):
            try:
                return self._stream(body)
            except _Retryable as exc:
                last = str(exc)
                if not exc.retry:
                    break
            except httpx.TimeoutException:
                last = f"timeout calling {alias.value}"
            except httpx.HTTPError as exc:
                last = f"model endpoint unreachable: {exc.__class__.__name__}"
            if attempt < self._retries:
                time.sleep(min(4.0 * 3**attempt, 45.0))
        raise ModelError(last)

    def _stream(self, body: dict[str, Any]) -> str:
        parts: list[str] = []
        with self._client.stream("POST", "/chat/completions", json=body) as resp:
            if resp.status_code != 200:
                text = resp.read().decode("utf-8", "replace")[:300]
                raise _Retryable(f"model endpoint returned {resp.status_code}: {text}", resp.status_code, _retryable(resp.status_code))
            if resp.headers.get("content-type", "").startswith("application/json"):
                return _plain_content(json.loads(resp.read()))
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise _Retryable(f"stream error: {str(chunk['error'])[:200]}", 502, True)
                for ch in chunk.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        parts.append(piece)
        text = "".join(parts)
        if not text.strip():
            raise _Retryable("empty model reply", 502, True)
        return text


def _retryable(status: int) -> bool:
    return status in (408, 409, 429, 524) or status >= 500


def _plain_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("unexpected completion shape") from exc
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


class _Retryable(Exception):
    def __init__(self, msg: str, status: int, retry: bool = True) -> None:
        super().__init__(msg)
        self.status = status
        self.retry = retry
