"""Bring-your-own AI key: direct mode against a mocked OpenAI-compatible provider. The key must never reach logs or responses."""

import asyncio
import json
import logging
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from gateway_fakes import login

from mentor_gateway import userai
from mentor_gateway.api.ask import build_llm
from mentor_gateway.app import create_app
from mentor_gateway.ask.llm import LLMError, NoAIKey, RouterChatLLM
from mentor_gateway.content.search import CourseSearch
from mentor_gateway.planner.llm import PlannerNoAI

KEY = "sk-secret-abcdef-1234"
BASE = "https://provider.test/v1"


class Provider:
    """A fake OpenAI-compatible provider. `embeddings`: HTTP status for /embeddings."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.embeddings = 200
        self.chat_status = 200
        self.down = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.down:
            raise httpx.ConnectError("no route")
        if req.headers.get("authorization") != f"Bearer {KEY}":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        body = json.loads(req.content)
        if req.url.path.endswith("/chat/completions"):
            if self.chat_status != 200:
                return httpx.Response(self.chat_status, text=f"failed for Bearer {KEY}")
            if body.get("stream"):
                sse = 'data: {"choices":[{"delta":{"content":"Xin "}}]}\n\ndata: {"choices":[{"delta":{"content":"chào"}}]}\n\ndata: [DONE]\n\n'
                return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        if req.url.path.endswith("/embeddings"):
            if self.embeddings != 200:
                return httpx.Response(self.embeddings, json={"error": "no such model"})
            data = [{"index": i, "embedding": [1.0, 0.0]} for i, _ in enumerate(body["input"])]
            return httpx.Response(200, json={"data": data})
        return httpx.Response(404)


@pytest.fixture
def provider(monkeypatch) -> Provider:
    p = Provider()
    transport = httpx.MockTransport(p)
    real_async, real_client = httpx.AsyncClient, httpx.Client
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_async(*a, transport=transport, **k))
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real_client(*a, transport=transport, **k))

    def post(url, **k):
        with real_client(transport=transport) as c:
            return c.post(url, **k)

    monkeypatch.setattr(httpx, "post", post)
    return p


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"user_ai": True})


@pytest.fixture
def store(tmp_path) -> userai.UserAIStore:
    return userai.UserAIStore(tmp_path / "data")


def configured(store) -> userai.UserAIClient:
    store.save(userai.UserAIConfig(BASE, KEY, {}))
    return userai.UserAIClient(store)


def test_status_masks_and_never_returns_the_key(client, student, provider):
    s = client.get("/api/ai-key").json()
    assert (s["mode"], s["configured"], s["masked_key"], s["base"]) == ("direct", False, None, userai.DEFAULT_BASE)
    assert s["models"]["mentor-chat"] == "fai/Alibaba:DeepSeek-V4.1-Flash"
    assert s["models"]["mentor-vision"] == "fai/Google:Gemini-3.5-Flash"
    r = client.put("/api/ai-key", json={"base": BASE, "key": KEY, "models": {"mentor-chat": "fai/Qwen3.8-27B"}})
    assert r.status_code == 200, r.text
    assert KEY not in r.text and KEY not in client.get("/api/ai-key").text
    s = client.get("/api/ai-key").json()
    assert s["configured"] is True and s["masked_key"] == "••••1234" and s["base"] == BASE
    assert s["models"]["mentor-chat"] == "fai/Qwen3.8-27B" and s["models"]["mentor-reasoning"].startswith("fai/")


def test_key_file_is_in_the_data_dir_only(client, student, gw):
    client.put("/api/ai-key", json={"key": KEY})
    f = gw.settings.data_dir / "user-ai.json"
    assert json.loads(f.read_text("utf-8"))["key"] == KEY
    if os.name != "nt":
        assert f.stat().st_mode & 0o077 == 0
    # not in the ops database file
    assert KEY.encode() not in (gw.settings.data_dir / "ops.db").read_bytes()
    # the key can be kept while the address changes
    client.put("/api/ai-key", json={"base": "https://other.test/v1"})
    assert json.loads(f.read_text("utf-8"))["key"] == KEY
    assert client.delete("/api/ai-key").json()["configured"] is False and not f.exists()


def test_save_validates(client, student):
    assert client.put("/api/ai-key", json={"key": "short"}).json() == {"error": "bad_key"}
    assert client.put("/api/ai-key", json={"key": KEY, "base": "ftp://x"}).json() == {"error": "bad_base"}
    assert client.put("/api/ai-key", json={"key": KEY, "models": {"nope": "x"}}).json() == {"error": "bad_alias"}
    assert client.put("/api/ai-key", json={"base": BASE}).json() == {"error": "bad_key"}  # nothing saved yet
    assert client.get("/api/ai-key").json()["configured"] is False


def test_requires_login(client):
    assert client.get("/api/ai-key").status_code == 401
    assert client.put("/api/ai-key", json={"key": KEY}).status_code == 401


def test_teacher_can_set_it_too(client, teacher):
    assert client.put("/api/ai-key", json={"key": KEY}).status_code == 200


def test_probe_results(client, student, provider):
    ok = client.post("/api/ai-key/test", json={"base": BASE, "key": KEY}).json()
    assert ok["ok"] is True
    sent = provider.requests[-1]
    assert str(sent.url) == f"{BASE}/chat/completions" and json.loads(sent.content)["max_tokens"] == 8
    assert json.loads(sent.content)["model"] == "fai/Alibaba:DeepSeek-V4.1-Flash"

    bad = client.post("/api/ai-key/test", json={"base": BASE, "key": "sk-wrong-key-0000"}).json()
    assert bad["code"] == "bad_key" and "Khóa" in bad["message"]

    provider.chat_status = 404
    nf = client.post("/api/ai-key/test", json={"base": BASE, "key": KEY}).json()
    assert nf["code"] == "model_not_found" and KEY not in json.dumps(nf)

    provider.down = True
    net = client.post("/api/ai-key/test", json={"base": BASE, "key": KEY}).json()
    assert net["code"] == "network" and net["ok"] is False
    assert client.get("/api/ai-key").json()["configured"] is False  # a test saves nothing

    client.put("/api/ai-key", json={"base": BASE, "key": KEY})
    provider.down = False
    provider.chat_status = 200
    assert client.post("/api/ai-key/test").json()["ok"] is True  # no body: the saved config


def test_direct_client_uses_user_key_and_models(store, provider):
    store.save(userai.UserAIConfig(BASE, KEY, {"mentor-chat": "custom/model"}))
    llm = userai.UserAIClient(store)
    assert asyncio.run(llm.complete("mentor-chat", [{"role": "user", "content": "hi"}])) == "Xin chào"
    body = json.loads(provider.requests[-1].content)
    assert body["model"] == "custom/model" and str(provider.requests[-1].url) == f"{BASE}/chat/completions"

    async def gather() -> str:
        return "".join([p async for p in llm.stream("mentor-vision", [{"role": "user", "content": "hi"}])])

    assert asyncio.run(gather()) == "Xin chào"
    assert json.loads(provider.requests[-1].content)["model"] == "fai/Google:Gemini-3.5-Flash"
    assert asyncio.run(llm.plan("sys", "user")) == "Xin chào"  # the planner goes through the same client
    assert json.loads(provider.requests[-1].content)["model"] == "fai/Alibaba:DeepSeek-V4.1-Flash"


def test_key_never_in_logs_or_errors(store, provider, caplog):
    llm = configured(store)
    provider.chat_status = 500  # the provider echoes the key in its error body
    caplog.set_level(logging.DEBUG)
    with pytest.raises(LLMError) as ei:
        asyncio.run(llm.complete("mentor-chat", [{"role": "user", "content": "hi"}]))
    assert KEY not in str(ei.value) and "***" in str(ei.value)
    assert KEY not in caplog.text
    store.save(userai.UserAIConfig(BASE, "sk-wrong-key-0000", {}))
    with pytest.raises(LLMError) as ei:  # 401 is not retried
        asyncio.run(llm.complete("mentor-chat", [{"role": "user", "content": "hi"}]))
    assert "HTTP 401" in str(ei.value) and KEY not in caplog.text and "sk-wrong-key-0000" not in caplog.text


def test_not_configured_is_not_retried(store):
    llm = userai.UserAIClient(store)
    with pytest.raises(NoAIKey):
        asyncio.run(llm.complete("mentor-chat", []))
    with pytest.raises(PlannerNoAI):
        asyncio.run(llm.plan("s", "u"))
    assert llm.available is False and llm.embed(["x"]) is None


def test_embeddings_work_then_fall_back_to_lexical(store, provider, tmp_path):
    llm = configured(store)
    assert llm.embed(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    assert json.loads(provider.requests[-1].content)["model"] == "azure-ai/Cohere-Embed-V5-Fast"
    assert str(provider.requests[-1].url) == f"{BASE}/embeddings"

    provider.embeddings = 404  # the provider has no embeddings model
    llm2 = userai.UserAIClient(store)
    search = CourseSearch(tmp_path / "emb", llm2)
    assert llm2.embed(["a"]) is None and llm2.available is False
    assert search._query_vector("toán") is None
    assert llm2.rerank("q", ["a"]) is None  # no rerank endpoint either: the retrieval order stays


def test_gateway_without_key_says_so_and_search_stays_lexical(client, student, gw, provider):
    assert gw.ai is not None and client.app.state.content.search.embedder is gw.ai
    r = client.post("/api/ask", json={"text": "2 + 2 bằng mấy?"})
    assert r.status_code == 200
    assert '"code": "ai_not_configured"' in r.text and "Cài đặt" in r.text
    assert client.get("/api/catalog").status_code == 200  # non-AI features keep working


def test_router_mode_is_untouched(settings, clock, executor, tmp_path):
    s = settings.model_copy(update={"model_router_url": "http://router.test", "model_router_key": "rk", "user_ai": None,
                                    "data_dir": tmp_path / "r"})
    app = create_app(s, clock=clock, executor=executor)
    with TestClient(app) as c:
        gw = app.state.gw
        assert gw.ai is None and gw.ai_store is None
        llm = build_llm(gw)
        assert isinstance(llm, RouterChatLLM) and not isinstance(llm, userai.UserAIClient)
        assert llm._endpoint_and_model("mentor-chat") == ("http://router.test/v1/chat/completions", "mentor-chat")
        assert llm._target("mentor-chat")[2] == {"Authorization": "Bearer rk"}
        assert gw.planner.llm.model == "mentor-reasoning"
        login(c)
        st = c.get("/api/ai-key").json()
        assert st["mode"] == "router" and st["configured"] is True
        assert c.put("/api/ai-key", json={"key": KEY}).status_code == 409
        assert not (s.data_dir / "user-ai.json").exists()


def test_user_ai_off_in_tests_by_default(settings):
    assert settings.model_copy(update={"user_ai": None}).user_ai_enabled is False
    assert settings.model_copy(update={"user_ai": None, "env": "standalone"}).user_ai_enabled is True
    assert settings.model_copy(update={"user_ai": None, "env": "standalone", "model_router_url": "http://x"}).user_ai_enabled is False


def test_course_builder_gets_the_key_only_in_its_own_env(store):
    assert userai.builder_env(store) == {}
    store.save(userai.UserAIConfig(BASE, KEY, {"mentor-chat": "custom/model"}))
    env = userai.builder_env(store)
    assert env["COURSE_BUILDER_DIRECT"] == "1" and env["FPT_API_BASE"] == BASE and env["FPT_API_KEY"] == KEY
    assert env["MENTOR_MODEL_CHAT"] == "custom/model"
    from mentor_gateway.teacher import SubprocessRunner

    r = SubprocessRunner()
    assert r.extra_env is None  # off unless the app wires it (direct mode only)
