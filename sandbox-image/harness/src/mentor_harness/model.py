"""Model access through the model router (OpenAI-compatible chat completions + function calling).

The harness only names `ModelAlias` values; the router maps them to provider models.
`ScriptedModel` is a fake for tests; `DevScriptedModel` lets the server run end-to-end
without any model (MENTOR_MODEL_MODE=scripted).

Streaming: `complete(..., on_delta=cb)` asks for a streamed reply and awaits `cb(text)` for every
content fragment as it arrives; the returned ModelResponse is the fully assembled reply (content,
tool calls rebuilt from their streamed fragments, usage). Without `on_delta` the call is a plain
non-streaming request. A client that cannot stream simply calls `cb` once with the whole content.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from mentor_schemas import ModelAlias

log = logging.getLogger("mentor_harness")


class ModelError(Exception):
    """The router failed, timed out or returned something unusable."""


DeltaCallback = Callable[[str], Awaitable[None]]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string, as sent by the model

    def parsed_arguments(self) -> dict[str, Any]:
        """Decode the JSON arguments; raises ValueError/TypeError if they are not a JSON object."""
        if not self.arguments.strip():
            return {}
        value = json.loads(self.arguments)
        if not isinstance(value, dict):
            raise TypeError("tool arguments must be a JSON object")
        return value


@dataclass
class ModelResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning_content: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None

    @property
    def total_tokens(self) -> int:
        if "total_tokens" in self.usage:
            return self.usage["total_tokens"]
        return self.usage.get("prompt_tokens", 0) + self.usage.get("completion_tokens", 0)

    def to_message(self, include_reasoning: bool = False) -> dict[str, Any]:
        """The assistant message to append to the conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        if include_reasoning and self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        return msg


class ModelClient(Protocol):
    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ModelResponse: ...


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    return {k: int(v) for k, v in raw.items() if isinstance(v, int | float) and not isinstance(v, bool)}


def parse_completion(data: dict[str, Any]) -> ModelResponse:
    """Turn an OpenAI-style chat completion body into a ModelResponse."""
    try:
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError(f"unexpected completion body: {str(data)[:300]}") from exc
    calls = []
    for i, raw in enumerate(message.get("tool_calls") or []):
        fn = raw.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, dict):  # some providers return parsed objects
            args = json.dumps(args, ensure_ascii=False)
        calls.append(ToolCall(id=raw.get("id") or f"call_{i}", name=fn.get("name", ""), arguments=args or ""))
    reasoning = message.get("reasoning_content")
    if reasoning is None:
        reasoning = (message.get("provider_specific_fields") or {}).get("reasoning_content")
    usage = _usage(data.get("usage") or {})
    return ModelResponse(
        content=message.get("content") or "",
        tool_calls=calls,
        reasoning_content=reasoning,
        usage=usage,
        finish_reason=choice.get("finish_reason"),
    )


class _StreamUnavailable(Exception):
    """Streaming failed before any text reached the learner; the call can be redone without streaming."""

    def __init__(self, reason: str, *, rejected: bool) -> None:
        super().__init__(reason)
        self.rejected = rejected  # True: the router refused stream=True outright (HTTP 4xx)


class StreamAccumulator:
    """Rebuilds one ModelResponse from OpenAI-style `chat.completion.chunk`s.

    Tool calls arrive as fragments keyed by `index`: the first fragment carries the id and name,
    later ones only pieces of the JSON arguments. Some providers (e.g. Gemini via LiteLLM) give
    every parallel call index 0 but a distinct id, so a new id at a used index starts a new call.
    """

    def __init__(self) -> None:
        self.chunks = 0
        self._content: list[str] = []
        self._reasoning: list[str] = []
        self._calls: list[dict[str, str]] = []
        self._slot_by_index: dict[int, int] = {}
        self.usage: dict[str, int] = {}
        self.finish_reason: str | None = None

    def add(self, chunk: dict[str, Any]) -> str:
        """Fold one chunk in; returns its visible content fragment ('' if none)."""
        self.chunks += 1
        if isinstance(chunk.get("usage"), dict):
            self.usage = _usage(chunk["usage"])
        choices = chunk.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return ""  # e.g. the final usage-only chunk
        choice = choices[0]
        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]
        delta = choice.get("delta") or choice.get("message") or {}
        reasoning = delta.get("reasoning_content")
        if reasoning is None:
            reasoning = (delta.get("provider_specific_fields") or {}).get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            self._reasoning.append(reasoning)
        for pos, raw in enumerate(delta.get("tool_calls") or []):
            if isinstance(raw, dict):
                self._add_call(raw, pos)
        text = delta.get("content")
        if isinstance(text, str) and text:
            self._content.append(text)
            return text
        return ""

    def _add_call(self, raw: dict[str, Any], pos: int) -> None:
        index = raw.get("index")
        if not isinstance(index, int):
            index = pos
        call_id = raw.get("id") or ""
        slot = self._slot_by_index.get(index)
        if slot is None or (call_id and self._calls[slot]["id"] and call_id != self._calls[slot]["id"]):
            self._calls.append({"id": call_id, "name": "", "arguments": ""})
            slot = len(self._calls) - 1
            self._slot_by_index[index] = slot
        entry = self._calls[slot]
        if call_id and not entry["id"]:
            entry["id"] = call_id
        fn = raw.get("function") or {}
        name = fn.get("name")
        if isinstance(name, str) and name and name != entry["name"]:  # a repeated full name is kept once
            entry["name"] += name
        args = fn.get("arguments")
        if isinstance(args, dict):  # some providers send the parsed object in one go
            args = json.dumps(args, ensure_ascii=False)
        if isinstance(args, str):
            entry["arguments"] += args

    def result(self) -> ModelResponse:
        calls = [
            ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"])
            for i, c in enumerate(self._calls)
        ]
        return ModelResponse(
            content="".join(self._content),
            tool_calls=calls,
            reasoning_content="".join(self._reasoning) or None,
            usage=dict(self.usage),
            finish_reason=self.finish_reason,
        )


def _retryable(status: int) -> bool:
    return status in (408, 409, 429) or status >= 500


class RouterModel:
    """Calls `<MODEL_ROUTER_URL>/chat/completions` with the alias as the model name.

    With `on_delta` the request is sent with `stream: true` and content fragments are forwarded as
    they arrive. Fallback: if the router answers the streamed request with a 4xx, or the stream fails
    before any text was forwarded, the same call is redone without streaming (and `on_delta` gets
    the whole content once). An alias whose stream was refused with a 4xx while the plain call then
    worked is not streamed again by this client. Once text has been forwarded a broken stream is a
    ModelError: redoing the call would repeat text the learner already saw.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 120.0,
        retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )
        self._retries = retries
        self.no_stream: set[ModelAlias] = set()  # aliases whose route refused stream=True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ModelResponse:
        alias = ModelAlias(alias)
        body: dict[str, Any] = {"model": alias.value, "messages": messages}
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        if max_tokens:
            body["max_tokens"] = max_tokens
        if on_delta is not None and alias not in self.no_stream:
            try:
                resp = await self._complete_streaming(alias, body, on_delta)
            except _StreamUnavailable as exc:
                log.warning("streaming %s failed (%s); retrying without streaming", alias.value, exc)
                resp = await self._complete_plain(alias, body)
                if exc.rejected:
                    self.no_stream.add(alias)
            else:
                if not resp.usage:  # router sent no usage chunk: estimate so the token caps still work
                    resp.usage = _estimate_usage(messages, resp)
                return resp
        else:
            resp = await self._complete_plain(alias, body)
        if on_delta is not None and resp.content:
            await on_delta(resp.content)
        return resp

    async def _complete_plain(self, alias: ModelAlias, body: dict[str, Any]) -> ModelResponse:
        last_error = "unknown error"
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post("/chat/completions", json=body)
            except httpx.TimeoutException:
                last_error = f"timeout calling {alias.value}"
            except httpx.HTTPError as exc:
                last_error = f"router unreachable: {exc.__class__.__name__}"
            else:
                if resp.status_code == 200:
                    try:
                        return parse_completion(resp.json())
                    except ValueError as exc:
                        raise ModelError(f"invalid JSON from router: {exc}") from exc
                last_error = f"router returned {resp.status_code}: {resp.text[:300]}"
                if not _retryable(resp.status_code):
                    break  # client errors will not get better on retry
            if attempt < self._retries:
                await asyncio.sleep(0.5 * 2**attempt)
        raise ModelError(last_error)

    async def _complete_streaming(
        self, alias: ModelAlias, body: dict[str, Any], on_delta: DeltaCallback
    ) -> ModelResponse:
        body = {**body, "stream": True, "stream_options": {"include_usage": True}}
        last_error = "unknown error"
        for attempt in range(self._retries + 1):
            acc = StreamAccumulator()
            emitted = False
            try:
                async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                    if resp.status_code != 200:
                        text = (await resp.aread()).decode("utf-8", "replace")
                        last_error = f"router returned {resp.status_code}: {text[:300]}"
                        if not _retryable(resp.status_code):
                            raise _StreamUnavailable(last_error, rejected=True)
                    elif resp.headers.get("content-type", "").startswith("application/json"):
                        # The router ignored stream=True and sent a plain completion.
                        try:
                            plain = parse_completion(json.loads(await resp.aread()))
                        except ValueError as exc:
                            raise ModelError(f"invalid JSON from router: {exc}") from exc
                        if plain.content:
                            await on_delta(plain.content)
                        return plain
                    else:
                        async for chunk in _sse_chunks(resp.aiter_lines()):
                            if chunk.get("error"):
                                last_error = f"error in stream: {str(chunk['error'])[:300]}"
                                if emitted:
                                    raise ModelError(last_error)
                                raise _StreamUnavailable(last_error, rejected=False)
                            text = acc.add(chunk)
                            if text:
                                emitted = True
                                await on_delta(text)
                        if acc.chunks:
                            return acc.result()
                        last_error = "empty stream from router"
            except httpx.TimeoutException:
                last_error = f"timeout calling {alias.value}"
            except httpx.HTTPError as exc:
                last_error = f"router unreachable: {exc.__class__.__name__}"
            if emitted:
                raise ModelError(f"stream from {alias.value} broke mid-reply: {last_error}")
            if attempt < self._retries:
                await asyncio.sleep(0.5 * 2**attempt)
        raise ModelError(last_error)


async def _sse_chunks(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    """JSON objects from the `data:` lines of an SSE body, up to `data: [DONE]`."""
    async for raw in lines:
        line = raw.strip()
        if not line.startswith("data:"):
            continue  # blank separators, `: keep-alive` comments, `event:` lines
        data = line[5:].strip()
        if not data:
            continue
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except ValueError as exc:
            raise ModelError(f"invalid stream chunk from router: {data[:200]}") from exc
        if isinstance(chunk, dict):
            yield chunk


def _estimate_usage(messages: list[dict[str, Any]], resp: ModelResponse) -> dict[str, int]:
    """Rough token count (~4 characters per token) for streams that carry no usage."""
    prompt = len(json.dumps(messages, ensure_ascii=False)) // 4
    completion = (len(resp.content) + sum(len(c.arguments) + len(c.name) for c in resp.tool_calls)) // 4
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


@dataclass
class RecordedCall:
    alias: ModelAlias
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    tool_choice: str | None


class ScriptedModel:
    """Test fake: returns queued responses in order and records every call.

    Queue items are ModelResponse objects, plain strings (assistant text), or
    exceptions (raised). Use `ScriptedModel.call(name, **args)` for a tool call.
    With `on_delta` the content is delivered in three chunks, like a streamed reply.
    """

    def __init__(self, responses: Iterable[ModelResponse | str | Exception] = ()) -> None:
        self.queue: list[ModelResponse | str | Exception] = list(responses)
        self.calls: list[RecordedCall] = []

    @staticmethod
    def call(name: str, _id: str | None = None, **arguments: Any) -> ModelResponse:
        """A response containing one tool call."""
        return ScriptedModel.multi(ToolCall(_id or f"call_{name}", name, json.dumps(arguments, ensure_ascii=False)))

    @staticmethod
    def multi(*calls: ToolCall, content: str = "") -> ModelResponse:
        return ModelResponse(content=content, tool_calls=list(calls), usage={"total_tokens": 10})

    def push(self, *items: ModelResponse | str | Exception) -> None:
        self.queue.extend(items)

    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ModelResponse:
        self.calls.append(RecordedCall(ModelAlias(alias), json.loads(json.dumps(messages)), tools, tool_choice))
        if not self.queue:
            raise ModelError("ScriptedModel queue is empty")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        resp = ModelResponse(content=item, usage={"total_tokens": 10}) if isinstance(item, str) else item
        if on_delta is not None and resp.content:
            await stream_text(resp.content, on_delta, pieces=3)
        return resp


async def stream_text(
    text: str, on_delta: DeltaCallback, *, pieces: int | None = None, delay_s: float = 0.0
) -> None:
    """Deliver `text` through `on_delta` in word-boundary chunks (`pieces` of them, or one per word)."""
    words = [w for w in re.split(r"(?<=\s)(?=\S)", text) if w]
    if pieces is not None and len(words) > pieces:
        size = -(-len(words) // pieces)
        words = ["".join(words[i : i + size]) for i in range(0, len(words), size)]
    for i, chunk in enumerate(words):
        if i:
            await asyncio.sleep(delay_s)  # also yields to the event loop, as a real stream would
        await on_delta(chunk)


_TOOL_COMMAND = re.compile(r"^/tool\s+(\w+)\s*(\{.*\})?\s*$", re.DOTALL)


class DevScriptedModel:
    """Deterministic stand-in for the router so the server runs without any model.

    - User text `/tool <name> {json args}` makes one tool call, then the result is echoed.
    - Safety confirmation (mentor-safety-b) answers `{"confirmed": false}`.
    - Vision answers with a fixed sentence.
    - Anything else gets a short Vietnamese echo.
    With `on_delta` the reply is streamed word by word, `chunk_delay_s` apart.
    """

    def __init__(self, chunk_delay_s: float = 0.0) -> None:
        self.chunk_delay_s = chunk_delay_s

    async def complete(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ModelResponse:
        resp = self._reply(ModelAlias(alias), messages, tools, tool_choice)
        if on_delta is not None and resp.content:
            # at most ~0.4 s per reply so scripted end-to-end tests stay fast
            delay = min(self.chunk_delay_s, 0.4 / max(1, len(resp.content.split())))
            await stream_text(resp.content, on_delta, delay_s=delay)
        return resp

    def _reply(
        self,
        alias: ModelAlias,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
    ) -> ModelResponse:
        usage = {"total_tokens": 1}
        if alias == ModelAlias.SAFETY_CONFIRM:
            return ModelResponse(content='{"confirmed": false, "reason": "scripted mode"}', usage=usage)
        if alias == ModelAlias.VISION:
            return ModelResponse(content="(chế độ scripted) Mình chưa xem được ảnh thật.", usage=usage)
        last = messages[-1] if messages else {}
        if last.get("role") == "tool":
            text = str(last.get("content") or "")
            return ModelResponse(content=f"(chế độ scripted) Kết quả công cụ:\n{text[:500]}", usage=usage)
        user_text = _last_user_text(messages)
        match = _TOOL_COMMAND.match(user_text.strip())
        if match and tools and tool_choice != "none":
            name, args = match.group(1), match.group(2) or "{}"
            return ModelResponse(tool_calls=[ToolCall("call_dev_1", name, args)], usage=usage)
        if (
            any(m.get("role") == "system" and "[JOB]" in str(m.get("content")) for m in messages)
            or "[JOB]" in user_text
        ):
            return ModelResponse(content="(chế độ scripted) Đã chạy job, không có thay đổi.", usage=usage)
        return ModelResponse(content=f"(chế độ scripted) Mình đã nhận: {user_text[:200]}", usage=usage)


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return str(content or "")
    return ""
