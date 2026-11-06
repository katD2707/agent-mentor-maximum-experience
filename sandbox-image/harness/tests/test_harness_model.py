"""RouterModel against a mocked router (httpx.MockTransport); no network."""

import json

import httpx
import pytest
from mentor_harness.model import ModelError, RouterModel
from mentor_schemas import ModelAlias


def completion(message: dict, usage: dict | None = None) -> dict:
    return {"choices": [{"message": message, "finish_reason": "stop"}], "usage": usage or {"total_tokens": 42}}


async def test_router_parses_tool_calls_and_reasoning() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        assert request.headers["authorization"] == "Bearer k"
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "suy nghĩ",
                    "tool_calls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path": "me/now.md"}'},
                        }
                    ],
                }
            ),
        )

    model = RouterModel("http://router:4000/", "k", transport=httpx.MockTransport(handler))
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]
    resp = await model.complete(ModelAlias.CHAT, [{"role": "user", "content": "hi"}], tools, max_tokens=100)
    assert seen[0]["model"] == "mentor-chat" and seen[0]["tools"] == tools and seen[0]["max_tokens"] == 100
    assert resp.reasoning_content == "suy nghĩ" and resp.total_tokens == 42
    assert resp.tool_calls[0].parsed_arguments() == {"path": "me/now.md"}
    msg = resp.to_message(include_reasoning=True)
    assert msg["tool_calls"][0]["function"]["name"] == "read_file" and msg["reasoning_content"] == "suy nghĩ"
    assert "reasoning_content" not in resp.to_message()
    await model.aclose()


async def test_router_retries_then_succeeds() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=completion({"role": "assistant", "content": "ok"}))

    model = RouterModel("http://router", "", transport=httpx.MockTransport(handler))
    assert (await model.complete(ModelAlias.REASONING, [])).content == "ok"
    assert attempts["n"] == 2


async def test_router_errors_and_timeouts() -> None:
    def bad_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "unknown model"})

    model = RouterModel("http://router", "", transport=httpx.MockTransport(bad_request))
    with pytest.raises(ModelError, match="400"):
        await model.complete(ModelAlias.CHAT, [])

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    model = RouterModel("http://router", "", retries=0, transport=httpx.MockTransport(timeout))
    with pytest.raises(ModelError, match="timeout"):
        await model.complete(ModelAlias.CHAT, [])

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nothing": True})

    model = RouterModel("http://router", "", transport=httpx.MockTransport(garbage))
    with pytest.raises(ModelError, match="unexpected"):
        await model.complete(ModelAlias.CHAT, [])
