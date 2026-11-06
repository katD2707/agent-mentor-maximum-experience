"""Model backends for evals and a recorder that captures every tool call the harness makes.

- `scripted`: `EvalScriptedModel` replays the `scripted` steps written in each scenario turn/job. It is an
  offline, CI-safe smoke of the plumbing and the graders (the steps act like an ideal mentor), not a model eval.
- `router`: the harness's own `RouterModel` against `MODEL_ROUTER_URL` / `MODEL_ROUTER_KEY` (LiteLLM aliases).

Both are wrapped by `RecordingModel`, which implements the harness `ModelClient` protocol.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from mentor_harness.model import ModelResponse, ToolCall
from mentor_schemas import ModelAlias

from mentor_evals.spec import ScriptedStep

SCRIPT_EXHAUSTED = "(eval scripted) Hết kịch bản cho lượt này."


class EvalScriptedModel:
    """Replays scripted steps for chat/reasoning calls; answers mentor-safety-b from a per-turn flag."""

    def __init__(self) -> None:
        self.queue: list[ScriptedStep] = []
        self.safety_confirms = False
        self.exhausted = 0
        self._n = 0

    def load(self, steps: list[ScriptedStep], *, safety_confirms: bool = False) -> None:
        self.queue = list(steps)
        self.safety_confirms = safety_confirms

    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,  # forward-compatible with new ModelClient options (e.g. on_delta streaming)
    ) -> ModelResponse:
        alias = ModelAlias(alias)
        usage = {"total_tokens": 1}
        if alias in (ModelAlias.SAFETY_CONFIRM, ModelAlias.SAFETY_DETECT):
            verdict = {"confirmed": self.safety_confirms, "reason": "eval scripted"}
            return ModelResponse(content=json.dumps(verdict), usage=usage)
        if alias == ModelAlias.VISION:
            return ModelResponse(content="(eval scripted) Ảnh không đọc được trong chế độ scripted.", usage=usage)
        if not self.queue:
            self.exhausted += 1
            if kwargs.get("on_delta") is not None:
                await kwargs["on_delta"](SCRIPT_EXHAUSTED)
            return ModelResponse(content=SCRIPT_EXHAUSTED, usage=usage)
        step = self.queue.pop(0)
        calls = []
        if tool_choice != "none":
            for c in step.calls:
                self._n += 1
                calls.append(ToolCall(f"call_{self._n}", c.name, json.dumps(c.args, ensure_ascii=False)))
        on_delta = kwargs.get("on_delta")
        if on_delta is not None and step.text:
            await on_delta(step.text)  # a non-streaming client calls on_delta once with the whole content
        return ModelResponse(content=step.text, tool_calls=calls, usage=usage)


@dataclass
class ToolCallRecord:
    id: str
    name: str
    args: dict[str, Any] | None
    raw_args: str
    alias: str
    result: str | None = None

    @property
    def is_error(self) -> bool:
        return bool(self.result and self.result.startswith("LỖI"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "args": self.args if self.args is not None else self.raw_args,
            "result": (self.result or "")[:600],
            "is_error": self.is_error,
        }


@dataclass
class SafetyReview:
    alias: str
    content: str

    @property
    def confirmed(self) -> bool:
        m = re.search(r"\{.*\}", self.content or "", re.DOTALL)
        if not m:
            return False
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and data.get("confirmed") is True


@dataclass
class RecordingModel:
    """Wraps a ModelClient; keeps tool calls (with results), safety reviews and token usage."""

    inner: Any
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    safety_reviews: list[SafetyReview] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    offered: list[str] = field(default_factory=list)  # tool names offered to the model, one entry per call
    calls: int = 0
    _results: dict[str, str] = field(default_factory=dict)

    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,  # forward-compatible with new ModelClient options (e.g. on_delta streaming)
    ) -> ModelResponse:
        alias = ModelAlias(alias)
        for m in messages:  # tool results of earlier rounds are visible in later prompts
            if m.get("role") == "tool" and isinstance(m.get("tool_call_id"), str):
                self._results[m["tool_call_id"]] = str(m.get("content") or "")
        if tools:
            self.offered.append(",".join(sorted(str((t.get("function") or {}).get("name")) for t in tools)))
        resp = await self.inner.complete(
            alias, messages, tools, tool_choice=tool_choice, max_tokens=max_tokens, **kwargs
        )
        self.calls += 1
        self.usage[alias.value] = self.usage.get(alias.value, 0) + resp.total_tokens
        if alias in (ModelAlias.SAFETY_CONFIRM, ModelAlias.SAFETY_DETECT):
            self.safety_reviews.append(SafetyReview(alias.value, resp.content))
        if tool_choice != "none":
            for c in resp.tool_calls:
                try:
                    args: dict[str, Any] | None = c.parsed_arguments()
                except (ValueError, TypeError):
                    args = None
                self.tool_calls.append(ToolCallRecord(c.id, c.name, args, c.arguments, alias.value))
        return resp

    def resolve_results(self) -> None:
        for rec in self.tool_calls:
            if rec.result is None and rec.id in self._results:
                rec.result = self._results[rec.id]

    async def aclose(self) -> None:
        close = getattr(self.inner, "aclose", None)
        if close is not None:
            await close()


def router_model_from_env() -> Any:
    """The harness RouterModel against the LiteLLM router (needs MODEL_ROUTER_URL and MODEL_ROUTER_KEY)."""
    from mentor_harness.model import RouterModel

    url = os.environ.get("MODEL_ROUTER_URL")
    if not url:
        raise SystemExit("--model router needs MODEL_ROUTER_URL (and usually MODEL_ROUTER_KEY)")
    timeout = float(os.environ.get("MENTOR_EVAL_MODEL_TIMEOUT_S", "180"))
    return RouterModel(url, os.environ.get("MODEL_ROUTER_KEY", ""), timeout_s=timeout)
