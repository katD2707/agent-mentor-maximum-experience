"""Token-level streaming: RouterModel against fake SSE bodies (httpx.MockTransport), and a turn end to end."""

import json
from pathlib import Path

import httpx
import pytest
from harness_helpers import collect, turn_request
from mentor_harness.model import ModelError, RouterModel, ScriptedModel
from mentor_schemas import ModelAlias


def completion(message: dict) -> dict:
    return {"choices": [{"message": message, "finish_reason": "stop"}], "usage": {"total_tokens": 42}}


def chunk(content: str | None = None, tool_calls: list | None = None, finish: str | None = None, **extra) -> dict:
    delta: dict = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    delta.update(extra)
    return {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def sse_body(*chunks: dict, usage: dict | None = None, done: bool = True) -> bytes:
    events = list(chunks)
    if usage is not None:
        events.append({"object": "chat.completion.chunk", "choices": [], "usage": usage})
    text = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in events)
    return (": keep-alive\n\n" + text + ("data: [DONE]\n\n" if done else "")).encode()


def sse(*chunks: dict, usage: dict | None = None) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(*chunks, usage=usage))


class Deltas(list):
    async def __call__(self, text: str) -> None:
        self.append(text)


async def test_stream_forwards_content_deltas_and_usage() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return sse(
            chunk(role="assistant", content=""),
            chunk(reasoning_content="nghĩ "),
            chunk(reasoning_content="đã"),
            chunk("Chào "),
            chunk("em"),
            chunk("!", finish="stop"),
            usage={"prompt_tokens": 30, "completion_tokens": 3, "total_tokens": 33},
        )

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    deltas = Deltas()
    resp = await model.complete(ModelAlias.CHAT, [{"role": "user", "content": "hi"}], on_delta=deltas)
    assert seen[0]["stream"] is True and seen[0]["stream_options"] == {"include_usage": True}
    assert deltas == ["Chào ", "em", "!"]
    assert resp.content == "Chào em!" and resp.tool_calls == []
    assert resp.reasoning_content == "nghĩ đã" and resp.total_tokens == 33 and resp.finish_reason == "stop"
    # Without on_delta (jobs, vision, safety) the request is a plain one.
    seen.clear()
    with pytest.raises(ModelError):  # this handler only speaks SSE, which a plain call cannot parse
        await model.complete(ModelAlias.CHAT, [])
    assert "stream" not in seen[0]


async def test_stream_assembles_tool_calls_split_across_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return sse(
            chunk("Để mình xem."),
            chunk(tool_calls=[{"index": 0, "id": "call_a", "type": "function",
                               "function": {"name": "read_file", "arguments": ""}}]),
            chunk(tool_calls=[{"index": 0, "function": {"arguments": '{"pa'}}]),
            chunk(tool_calls=[{"index": 1, "id": "call_b", "type": "function",
                               "function": {"name": "list_dir", "arguments": '{"path"'}}]),
            chunk(tool_calls=[{"index": 0, "function": {"arguments": 'th": "me/no'}}]),
            chunk(tool_calls=[{"index": 1, "function": {"arguments": ': "goals"}'}}]),
            chunk(tool_calls=[{"index": 0, "function": {"arguments": 'w.md"}'}}], finish="tool_calls"),
        )  # no usage chunk -> estimated

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    deltas = Deltas()
    resp = await model.complete(ModelAlias.CHAT, [{"role": "user", "content": "x" * 400}], on_delta=deltas)
    assert deltas == ["Để mình xem."]
    assert [(c.id, c.name) for c in resp.tool_calls] == [("call_a", "read_file"), ("call_b", "list_dir")]
    assert resp.tool_calls[0].parsed_arguments() == {"path": "me/now.md"}
    assert resp.tool_calls[1].parsed_arguments() == {"path": "goals"}
    assert resp.finish_reason == "tool_calls" and resp.total_tokens > 100  # estimated from the prompt size
    msg = resp.to_message()
    assert msg["content"] == "Để mình xem." and msg["tool_calls"][1]["function"]["arguments"] == '{"path": "goals"}'


async def test_stream_parallel_calls_sharing_index_zero() -> None:
    # Some providers (Gemini via LiteLLM) send each whole call at index 0 with its own id.
    def handler(request: httpx.Request) -> httpx.Response:
        return sse(
            chunk(tool_calls=[{"index": 0, "id": "g1", "function": {"name": "read_file", "arguments": {"path": "a"}}}]),
            chunk(tool_calls=[{"index": 0, "id": "g2", "function": {"name": "read_file", "arguments": {"path": "b"}}}]),
            usage={"total_tokens": 5},
        )

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    resp = await model.complete(ModelAlias.CHAT, [], on_delta=Deltas())
    assert [(c.id, c.parsed_arguments()) for c in resp.tool_calls] == [("g1", {"path": "a"}), ("g2", {"path": "b"})]


async def test_stream_rejected_falls_back_to_plain_and_remembers() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx.Response(400, json={"error": "streaming not supported for this model"})
        return httpx.Response(200, json=completion({"role": "assistant", "content": "Trả lời đầy đủ."}))

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    deltas = Deltas()
    resp = await model.complete(ModelAlias.CHAT, [], on_delta=deltas)
    assert resp.content == "Trả lời đầy đủ." and deltas == ["Trả lời đầy đủ."]
    assert [b.get("stream", False) for b in bodies] == [True, False]
    assert ModelAlias.CHAT in model.no_stream
    await model.complete(ModelAlias.CHAT, [], on_delta=deltas)  # not streamed again
    assert [b.get("stream", False) for b in bodies] == [True, False, False]


async def test_stream_fallbacks_for_json_reply_and_in_stream_error() -> None:
    def ignores_stream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion({"role": "assistant", "content": "JSON thường"}))

    model = RouterModel("http://router", "", transport=httpx.MockTransport(ignores_stream))
    deltas = Deltas()
    assert (await model.complete(ModelAlias.CHAT, [], on_delta=deltas)).content == "JSON thường"
    assert deltas == ["JSON thường"]

    calls = {"n": 0}

    def in_stream_error(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if json.loads(request.content).get("stream"):
            return sse(chunk(role="assistant"), {"error": {"message": "provider hiccup"}})
        return httpx.Response(200, json=completion({"role": "assistant", "content": "ok"}))

    model = RouterModel("http://router", "", transport=httpx.MockTransport(in_stream_error))
    deltas = Deltas()
    assert (await model.complete(ModelAlias.CHAT, [], on_delta=deltas)).content == "ok"
    assert deltas == ["ok"] and calls["n"] == 2
    assert ModelAlias.CHAT not in model.no_stream  # a transient error does not disable streaming


async def test_stream_broken_after_text_is_an_error_not_a_retry() -> None:
    calls = {"n": 0}

    async def broken_body():
        yield sse_body(chunk("Một nửa "), done=False)
        raise httpx.ReadError("connection reset")

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=broken_body())

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    deltas = Deltas()
    with pytest.raises(ModelError, match="mid-reply"):
        await model.complete(ModelAlias.CHAT, [], on_delta=deltas)
    assert deltas == ["Một nửa "] and calls["n"] == 1  # never re-sent: the learner already saw that text


async def test_scripted_model_streams_in_chunks() -> None:
    deltas = Deltas()
    resp = await ScriptedModel(["Một hai ba bốn năm sáu"]).complete(ModelAlias.CHAT, [], on_delta=deltas)
    assert len(deltas) == 3 and "".join(deltas) == resp.content == "Một hai ba bốn năm sáu"


async def test_turn_streams_router_deltas_end_to_end(make_harness, ws_root: Path) -> None:
    replies = iter(
        [
            sse(
                chunk("Để mình "),
                chunk("xem."),
                chunk(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "list_dir", "arguments": '{"pa'}}]),
                chunk(tool_calls=[{"index": 0, "function": {"arguments": 'th": "me"}'}}]),
                usage={"total_tokens": 10},
            ),
            sse(chunk("Xong "), chunk("rồi."), usage={"total_tokens": 10}),
        ]
    )
    model = RouterModel("http://router", "", transport=httpx.MockTransport(lambda request: next(replies)))
    events = await collect(make_harness(model), turn_request())
    assert [e.text for e in events if e.type == "text_delta"] == ["Để mình ", "xem.", "\n\nXong ", "rồi."]
    assert [e.type for e in events][2:] == ["tool_started", "tool_finished", "text_delta", "text_delta", "done"]
    chat = [
        json.loads(line)
        for p in (ws_root / "sessions").glob("*/s1.jsonl")
        for line in p.read_text(encoding="utf-8").splitlines()
    ]
    assert chat[-1]["role"] == "mentor" and chat[-1]["text"] == "Để mình xem.\n\nXong rồi."
    await model.aclose()
