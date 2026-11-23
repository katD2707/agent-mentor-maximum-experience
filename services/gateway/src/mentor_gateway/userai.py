"""Bring-your-own AI key (standalone desktop build): the gateway talks to the user's OpenAI-compatible provider directly.

Used when MODEL_ROUTER_URL is unset (`Settings.user_ai_enabled`). The user's config (base URL, key, optional model per
alias) lives in ONE file in the data dir, `user-ai.json`, written with owner-only permissions. It is outside the database,
outside every backup/snapshot and outside the workspace mirrors, so it never leaves the machine. The key is never put in
logs, errors or API responses (only `mask_key`).

`UserAIClient` is the single client every AI path uses: chat streaming/completion/vision/audio (inherits `RouterChatLLM`),
the planner (`plan`), course-search embeddings (`embed`/`available`) and rerank. Without a key it raises `NoAIKey`.
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from mentor_schemas import ModelAlias

from mentor_gateway.ask.llm import LLMError, NoAIKey, RouterChatLLM
from mentor_gateway.planner.llm import PlannerLLMError, PlannerNoAI

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://omniroute.ptatien.com/v1"
# Mirrors services/model-router/config.yaml: only ids that exist upstream (an unknown `fai/` id rate-limits every fai model).
DEFAULT_MODELS: dict[str, str] = {
    ModelAlias.CHAT.value: "fai/Alibaba:DeepSeek-V4.1-Flash",
    ModelAlias.REASONING.value: "fai/Alibaba:DeepSeek-V4.1-Flash",
    ModelAlias.VISION.value: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.AUDIO.value: "fai/Google:Gemini-3.5-Flash",
    ModelAlias.EMBED.value: "azure-ai/Cohere-Embed-V5-Fast",
    ModelAlias.RERANK.value: "azure-ai/Cohere-rerank-v4.0-fast",
}
FILE_NAME = "user-ai.json"


class AIConfigError(ValueError):
    """A rejected value; the message is safe to show (never contains the key)."""


def mask_key(key: str) -> str:
    return "••••" + key[-4:] if len(key) >= 12 else "••••"


def clean_base(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    u = urlparse(base)
    if u.scheme not in ("http", "https") or not u.netloc or any(c.isspace() for c in base):
        raise AIConfigError("bad_base")
    return base


def clean_key(key: str) -> str:
    key = (key or "").strip()
    if not (8 <= len(key) <= 400) or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key):
        raise AIConfigError("bad_key")
    return key


def clean_models(models: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(models, dict):
        return out
    for alias, name in models.items():
        if alias not in DEFAULT_MODELS:
            raise AIConfigError("bad_alias")
        name = str(name or "").strip()
        if name and name != DEFAULT_MODELS[alias]:
            if len(name) > 200 or any(c.isspace() for c in name):
                raise AIConfigError("bad_model")
            out[alias] = name
    return out


@dataclass
class UserAIConfig:
    base: str = DEFAULT_BASE
    key: str = ""
    models: dict[str, str] = field(default_factory=dict)  # overrides only

    def model(self, alias: str) -> str:
        return self.models.get(alias) or DEFAULT_MODELS[alias]

    def all_models(self) -> dict[str, str]:
        return {a: self.model(a) for a in DEFAULT_MODELS}


class UserAIStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / FILE_NAME
        self._lock = threading.Lock()
        self._cache: tuple[tuple[int, int], UserAIConfig | None] | None = None

    def get(self) -> UserAIConfig | None:
        try:
            st = self.path.stat()
        except OSError:
            self._cache = None
            return None
        sig = (st.st_mtime_ns, st.st_size)
        c = self._cache
        if c is not None and c[0] == sig:
            return c[1]
        try:
            raw = json.loads(self.path.read_text("utf-8"))
            cfg = UserAIConfig(clean_base(raw.get("base") or DEFAULT_BASE), clean_key(raw.get("key") or ""),
                               clean_models(raw.get("models")))
        except (OSError, ValueError, AttributeError):  # corrupt file = not configured
            cfg = None
        self._cache = (sig, cfg)
        return cfg

    def save(self, cfg: UserAIConfig) -> None:
        body = json.dumps({"base": cfg.base, "key": cfg.key, "models": cfg.models}, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(FILE_NAME + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            _owner_only(tmp)
            os.replace(tmp, self.path)
            self._cache = None

    def clear(self) -> None:
        with self._lock:
            for p in (self.path, self.path.with_name(FILE_NAME + ".tmp")):
                try:
                    p.unlink()
                except OSError:
                    pass
            self._cache = None


def builder_env(store: UserAIStore) -> dict[str, str]:
    """Env for the course-builder subprocess (it has its own direct mode): the key goes only into that child's environment."""
    cfg = store.get()
    if cfg is None:
        return {}
    env = {"COURSE_BUILDER_DIRECT": "1", "FPT_API_BASE": cfg.base, "FPT_API_KEY": cfg.key}
    for alias, name in cfg.models.items():
        env["MENTOR_MODEL_" + ModelAlias(alias).name] = name
    return env


def _owner_only(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name == "nt":  # POSIX modes mean little on Windows: drop inherited ACLs, grant the current user only
        user = os.environ.get("USERNAME")
        if user:
            try:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W,D)"],
                               capture_output=True, timeout=10, check=False)
            except (OSError, subprocess.SubprocessError):
                pass


def status(store: UserAIStore, *, router: bool = False) -> dict[str, Any]:
    """The API view: never contains the key, only a masked tail."""
    cfg = store.get()
    return {"mode": "router" if router else "direct", "configured": router or cfg is not None,
            "masked_key": mask_key(cfg.key) if cfg else None, "base": cfg.base if cfg else DEFAULT_BASE,
            "default_base": DEFAULT_BASE, "models": cfg.all_models() if cfg else dict(DEFAULT_MODELS),
            "default_models": dict(DEFAULT_MODELS)}


_MESSAGES = {
    "bad_key": "Khóa AI chưa đúng. Em kiểm tra lại khóa rồi thử nhé.",
    "model_not_found": "Không tìm thấy mô hình hoặc địa chỉ. Em kiểm tra lại địa chỉ nhé.",
    "rate_limited": "Khóa đang bị giới hạn lượt dùng. Em đợi một chút rồi thử lại nhé.",
    "network": "Chưa kết nối được tới địa chỉ này. Em kiểm tra mạng và địa chỉ nhé.",
    "provider_error": "Nhà cung cấp đang gặp sự cố. Em thử lại sau nhé.",
}


def probe(cfg: UserAIConfig, timeout: float = 25.0) -> dict[str, Any]:
    """One tiny chat call. Never raises, never echoes the key or the provider's body."""
    body = {"model": cfg.model(ModelAlias.CHAT.value), "messages": [{"role": "user", "content": "Chào"}],
            "max_tokens": 8, "stream": False}
    try:
        r = httpx.post(f"{cfg.base}/chat/completions", json=body, headers={"Authorization": f"Bearer {cfg.key}"},
                       timeout=httpx.Timeout(timeout, connect=10.0))
    except httpx.HTTPError:
        return _fail("network")
    if r.status_code in (401, 403):
        return _fail("bad_key")
    if r.status_code in (400, 404):
        return _fail("model_not_found")
    if r.status_code == 429:
        return _fail("rate_limited")
    if r.status_code >= 400:
        return _fail("provider_error")
    return {"ok": True, "code": "ok", "message": "Khóa dùng được."}


def _fail(code: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": _MESSAGES[code]}


class UserAIClient(RouterChatLLM):
    """The one client behind every alias in direct mode. Re-reads the user's config on each call, so saving or deleting
    the key takes effect at once without rebuilding any service."""

    def __init__(self, store: UserAIStore) -> None:
        super().__init__("", None, direct=True)
        self.store = store
        self._down_until = 0.0
        self._http: httpx.Client | None = None

    # --- chat / vision / audio / reasoning (RouterChatLLM paths)
    def _cfg(self) -> UserAIConfig:
        cfg = self.store.get()
        if cfg is None:
            raise NoAIKey("ai_not_configured")
        return cfg

    def _target(self, alias: str) -> tuple[str, str, dict[str, str]]:
        cfg = self._cfg()
        if alias not in DEFAULT_MODELS:
            raise LLMError(f"no model for alias {alias}")
        return f"{cfg.base}/chat/completions", cfg.model(alias), {"Authorization": f"Bearer {cfg.key}"}

    def _scrub(self, e: LLMError) -> LLMError:
        cfg = self.store.get()
        msg = str(e)
        if cfg and cfg.key:
            msg = msg.replace(cfg.key, "***")
        return type(e)(msg)

    async def stream(self, alias: str, messages: list[dict[str, Any]], **kw: Any):  # type: ignore[override]
        try:
            async for piece in super().stream(alias, messages, **kw):
                yield piece
        except NoAIKey:
            raise
        except LLMError as e:
            raise self._scrub(e) from None

    async def complete(self, alias: str, messages: list[dict[str, Any]], **kw: Any) -> str:  # type: ignore[override]
        try:
            return await super().complete(alias, messages, **kw)
        except NoAIKey:
            raise
        except LLMError as e:
            raise self._scrub(e) from None

    # --- planner
    async def plan(self, system: str, user: str) -> str:
        try:
            return await self.complete(ModelAlias.REASONING.value,
                                       [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       max_tokens=8000, temperature=0.2)
        except NoAIKey as e:
            raise PlannerNoAI(str(e)) from None
        except LLMError as e:
            raise PlannerLLMError(str(e)) from None

    # --- embeddings (course search): `available` False without a key, and for 60 s after a failure
    @property
    def available(self) -> bool:
        return self.store.get() is not None and time.monotonic() >= self._down_until

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        cfg = self.store.get()
        if cfg is None or not texts or not self.available:
            return None
        try:
            if self._http is None:
                self._http = httpx.Client(timeout=6.0)
            r = self._http.post(f"{cfg.base}/embeddings", json={"model": cfg.model(ModelAlias.EMBED.value), "input": texts},
                                headers={"Authorization": f"Bearer {cfg.key}"})
            r.raise_for_status()
            vecs = [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
            if len(vecs) != len(texts):
                raise ValueError("embedding count mismatch")
            return vecs
        except Exception as e:  # noqa: BLE001 - provider without embeddings (or any failure): lexical search, silently
            log.info("embeddings unavailable in direct mode (%s); lexical search for 10 min", e.__class__.__name__)
            self._down_until = time.monotonic() + 600
            return None

    # --- rerank: scores in input order, or None (callers keep the retrieval order)
    def rerank(self, query: str, docs: list[str]) -> list[float] | None:
        cfg = self.store.get()
        if cfg is None or not docs:
            return None
        try:
            r = httpx.post(f"{cfg.base}/rerank", json={"model": cfg.model(ModelAlias.RERANK.value), "query": query,
                                                       "documents": docs},
                           headers={"Authorization": f"Bearer {cfg.key}"}, timeout=8.0)
            r.raise_for_status()
            scores = [0.0] * len(docs)
            for it in r.json()["results"]:
                scores[it["index"]] = float(it["relevance_score"])
            return scores
        except Exception:  # noqa: BLE001
            return None
