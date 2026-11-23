"""Chat with a chicken: persona, memory, actions, streaming, the Ask pipeline for photos, no-router failure. Fake model."""

import io
import json

import pytest
from gateway_fakes import set_band
from langga_fixtures import KID, content_with_papers, kid_store
from PIL import Image
from test_gw_practice_courses import enroll

from mentor_gateway.ask.llm import LLMError
from mentor_gateway.ask.service import AskService


@pytest.fixture(scope="session")
def lg_content(tmp_path_factory):
    return content_with_papers(tmp_path_factory.mktemp("lgc"))


@pytest.fixture
def settings(settings, lg_content):
    return settings.model_copy(update={"content_dir": lg_content})


class FakeLLM:
    """`script[alias]`: a str, a list (popped per call) or callable(messages) -> str. No `stream` method."""

    def __init__(self, **script) -> None:
        self.script, self.calls = script, []

    async def complete(self, alias, messages, *, max_tokens=2000, temperature=0.3):
        self.calls.append((alias, messages))
        s = self.script.get(alias)
        if s is None:
            raise LLMError(f"no script for {alias}")
        s = s(messages) if callable(s) else s.pop(0) if isinstance(s, list) else s
        if isinstance(s, Exception):
            raise s
        return s


class StreamingLLM(FakeLLM):
    def __init__(self, pieces) -> None:
        super().__init__()
        self.pieces = pieces

    async def stream(self, alias, messages, *, max_tokens=2000, temperature=0.3, timeout=None, attempts=None):
        self.calls.append((alias, messages))
        for p in self.pieces:
            yield p


def use_llm(client, llm):
    gw = client.app.state.gw
    client.app.state.ask = AskService(client.app.state.content, gw.db, gw.clock, llm)
    return llm


def sse(resp) -> list[tuple[str, dict]]:
    out = []
    for block in resp.text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return out


def names(events):
    return [e for e, _ in events]


def chat(client, chicken="toan", **body):
    r = client.post(f"/api/chat/{chicken}", json={"lang": "vi", **body})
    assert r.status_code == 200, r.text
    return sse(r)


def test_chat_text_persona_actions_and_memory(client, student):
    llm = use_llm(client, FakeLLM(**{"mentor-chat": "Chào em, hôm nay mình ôn hàm số nhé! [[actions: practice, lesson, nope]]"}))
    ev = chat(client, text="Em nên học gì?")
    assert names(ev)[0] == "thread" and names(ev)[-1] == "done" and "status" in names(ev)
    assert names(ev).index("delta") < names(ev).index("message") < names(ev).index("actions")
    streamed = "".join(d["text"] for e, d in ev if e == "delta")
    message = next(d for e, d in ev if e == "message")
    assert message["kind"] == "chat" and "[[" not in streamed and "actions" not in message["text"]
    assert streamed.strip().startswith("Chào em")
    actions = next(d for e, d in ev if e == "actions")["actions"]
    # no course yet: the lesson action is dropped, unknown keys never become links
    assert actions == [{"key": "practice", "label_vi": "Luyện tập", "label_en": "Practice", "deep_link": "/luyen-tap"}]
    alias, messages = llm.calls[0]
    assert alias == "mentor-chat" and messages[0]["role"] == "system" and "Gà Toán" in messages[0]["content"]
    assert "ONE subject only" in messages[0]["content"] and "upper secondary" in messages[0]["content"]  # one subject, grade-appropriate
    assert messages[-1] == {"role": "user", "content": "Em nên học gì?"}

    chat(client, text="Còn hàm số thì sao?")
    sent = llm.calls[1][1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]  # the first exchange is remembered
    hist = client.get("/api/chat/toan/history").json()
    assert [(t["role"], t["text"][:8]) for t in hist] == [("user", "Em nên h"), ("assistant", "Chào em,"), ("user", "Còn hàm "),
                                                           ("assistant", "Chào em,")]
    assert hist[1]["actions"][0]["deep_link"] == "/luyen-tap"
    assert client.get("/api/chat/van/history").json() == []  # memory is per chicken


def test_chat_keeps_the_last_30_turns_and_knows_the_course(client, student, tmp_path):
    set_band(client, "g1_5")
    client.app.state.content.store = kid_store(client.app.state.gw.clock, tmp_path / "courses")
    client.app.state.chicken_resolver.clear()
    enroll(client, KID)
    llm = use_llm(client, FakeLLM(**{"mentor-chat": "Ok em. [[actions: lesson, test]]"}))
    for i in range(17):
        ev = chat(client, text=f"câu {i}")
    hist = client.get("/api/chat/toan/history").json()
    assert len(hist) == 30 and hist[-2]["text"] == "câu 16" and hist[0]["text"] == "câu 2"
    assert len(client.get("/api/chat/toan/history", params={"limit": 4}).json()) == 4
    actions = next(d for e, d in ev if e == "actions")["actions"]
    assert [a["deep_link"] for a in actions] == [f"/khoa-hoc/{KID}/hoc", f"/kiem-tra/{KID}"]
    system = llm.calls[-1][1][0]["content"]
    assert "primary school" in system and "Toán 1" in system  # age band style and the current course
    assert len(llm.calls[-1][1]) == 1 + 30 + 1


def test_chat_streams_and_hides_think_blocks(client, student):
    use_llm(client, StreamingLLM(["<thi", "nk>secret</think>Xin ", "chào em. [", "[actions: arena]]"]))
    ev = chat(client, text="hi")
    deltas = [d["text"] for e, d in ev if e == "delta"]
    assert "".join(deltas) == "Xin chào em. " and len(deltas) >= 2
    assert next(d for e, d in ev if e == "message")["text"] == "Xin chào em."
    assert next(d for e, d in ev if e == "actions")["actions"][0]["deep_link"] == "/dau-truong"


def test_chat_without_a_router_fails_gracefully(client, student):
    use_llm(client, None)
    ev = chat(client, text="hi")
    assert names(ev) == ["thread", "status", "error", "done"] and ev[2][1]["code"] == "model_unavailable"
    assert client.get("/api/chat/toan/history").json() == []  # a failed turn is not remembered
    assert client.post("/api/chat/khmt", json={"text": "hi"}).status_code == 404  # not a chicken of this stage
    assert client.post("/api/chat/toan", json={}).status_code == 422
    use_llm(client, FakeLLM(**{"mentor-chat": LLMError("down")}))
    assert chat(client, text="hi")[-2][1]["code"] == "model_unavailable"


def test_chat_audio_is_transcribed_and_answered(client, student):
    llm = use_llm(client, FakeLLM(**{"mentor-audio": "Giải thích đạo hàm", "mentor-chat": "Đạo hàm là tốc độ thay đổi."}))
    r = client.post("/api/chat/toan", data={"lang": "vi"}, files={"audio": ("a.wav", b"RIFFfake", "audio/wav")})
    ev = sse(r)
    assert ("transcript", {"text": "Giải thích đạo hàm"}) in ev
    assert any(e == "message" and d["text"].startswith("Đạo hàm") for e, d in ev)
    assert llm.calls[-1][1][-1]["content"] == "Giải thích đạo hàm"


def test_chat_photo_goes_through_the_ask_pipeline(client, student):
    use_llm(client, FakeLLM())
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, "PNG")  # a blank page: the Ask photo check asks for a retake, no model
    r = client.post("/api/chat/toan", data={"lang": "vi"}, files={"image": ("p.png", buf.getvalue(), "image/png")})
    ev = sse(r)
    assert names(ev)[0] == "thread" and names(ev)[-1] == "done" and names(ev).count("thread") == 1 and names(ev).count("done") == 1
    assert "status" in names(ev) and "quality" in names(ev) and "error" not in names(ev)
    assert next(d for e, d in ev if e == "message")["kind"] == "retake"
    hist = client.get("/api/chat/toan/history").json()
    assert hist[0] == {**hist[0], "role": "user", "text": "[ảnh bài tập]"} and hist[1]["role"] == "assistant"
    # an Ask follow-up needs a thread that has a problem
    ev = chat(client, action="last_step")
    assert any(e == "message" and d["kind"] == "no_problem" for e, d in ev)


def test_chat_follow_up_turn_with_the_issued_thread_id(client, student):
    llm = use_llm(client, FakeLLM(**{"mentor-chat": ["Một mảng nằm liền nhau trong bộ nhớ.", "Danh sách liên kết thì không."]}))
    first = chat(client, text="Mảng là gì?")
    tid = next(d for e, d in first if e == "thread")["thread_id"]
    second = chat(client, text="Còn danh sách liên kết?", thread_id=tid)  # was 404 thread_not_found
    assert names(second)[-1] == "done" and "error" not in names(second)
    sent = llm.calls[1][1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[2]["content"].startswith("Một mảng")  # the chicken remembers the earlier turn
    assert "never say" in sent[0]["content"]  # no invented "nhầm" on a first message
