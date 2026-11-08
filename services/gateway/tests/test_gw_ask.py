"""Q&A (`/api/ask`, SSE) and the Mực guide (`/api/guide`), offline: the models are mocked, content is the dev samples."""

import io
import json
import re
from pathlib import Path

import pytest
from gateway_fakes import login
from PIL import Image, ImageDraw

from mentor_gateway.ask import guide as guide_mod
from mentor_gateway.ask.llm import LLMError
from mentor_gateway.ask.service import AskService, route_text

REPO = Path(__file__).resolve().parents[3]
GUIDES_TS = REPO / "apps" / "app" / "src" / "lib" / "guides.ts"


class FakeLLM:
    """Scripted model: `script[alias]` is a str, a list (popped per call) or a callable(messages) -> str."""

    def __init__(self, **script) -> None:
        self.script = script
        self.calls: list[tuple[str, list]] = []

    async def complete(self, alias, messages, *, max_tokens=2000, temperature=0.3):
        self.calls.append((alias, messages))
        s = self.script.get(alias)
        if s is None:
            raise LLMError(f"no script for {alias}")
        if callable(s):
            s = s(messages)
        elif isinstance(s, list):
            s = s.pop(0)
        if isinstance(s, Exception):
            raise s
        return s

    def aliases(self) -> list[str]:
        return [a for a, _ in self.calls]


def j(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


SOLUTION = j(problem_md="Tính $S_{20}$ của cấp số cộng có $u_1=3$, $d=4$.", tip="Tính (n-1)d trước.", steps=[
    {"title": "Nhớ lại công thức tổng", "md": "$S_n = \\frac{n(2u_1+(n-1)d)}{2}$"},
    {"title": "Thay số", "md": "$S_{20} = \\frac{20(2\\cdot 3+19\\cdot 4)}{2}$"},
    {"title": "Tính kết quả", "md": "$S_{20} = 10 \\cdot 82 = 820$"}])
SIMPLER = j(problem_md="x", tip="Chia nhỏ.", steps=[{"title": "Ý chính", "md": "Cộng 20 số."}, {"title": "Kết quả", "md": "$820$"}])
SIMILAR = j(items=[{"problem_md": f"Bài {i}", "answer_md": f"${i}$"} for i in range(1, 4)])
OCR_TWO = j(problems=[{"id": "3", "label": "Bài 3", "text": "Cho cấp số cộng có $u_1=3$, $d=4$. Tính $S_{20}$."},
                      {"id": "4", "label": "Bài 4", "text": "Tìm $x$ biết $2, x, 18$ lập thành cấp số nhân."}], unreadable=[])
OCR_PARTIAL = j(problems=[{"id": "3", "label": "Bài 3", "text": "Cho cấp số cộng có $u_1=3$, $d=4$. Tính $S_{20}$."}],
                unreadable=[{"where": "nửa dưới ảnh", "what": "Bài 4", "reason": "quá tối"}])
OCR_ONE = j(problems=[{"id": "1", "label": "Bài 3", "text": "Tính $S_{20}$."}], unreadable=[])


def photo_bytes(brightness: int = 245, text: bool = True) -> bytes:
    img = Image.new("RGB", (1200, 1600), (brightness,) * 3)
    if text:
        d = ImageDraw.Draw(img)
        for i in range(12):
            d.text((80, 100 + i * 90), "Bai 3. Cho cap so cong u1 = 3, cong sai d = 4. Tinh tong 20 so hang dau." * 1, fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        ev = re.search(r"^event: (.+)$", block, re.MULTILINE)
        data = re.search(r"^data: (.+)$", block, re.MULTILINE)
        if ev and data:
            out.append((ev.group(1), json.loads(data.group(1))))
    return out


def events(r) -> dict[str, dict]:
    assert r.status_code == 200, r.text
    return {k: v for k, v in parse_sse(r.text)}


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"content_dir": REPO / "services" / "gateway" / "tests" / "fixtures"})  # fixtures/courses: the dev sample courses


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def ask(client, student, llm):
    client.app.state.ask = AskService(client.app.state.content, client.app.state.gw.db, client.app.state.gw.clock, llm)

    def post(**kw):
        files = kw.pop("files", None)
        if files:
            return client.post("/api/ask", data={k: v for k, v in kw.items() if v is not None}, files=files)
        return client.post("/api/ask", json=kw)

    return post


# ---------------------------------------------------------------- intent routing
@pytest.mark.parametrize("text,expected", [
    ("em muốn học điện trường lớp 11", ("learn", False)),
    ("Tôi muốn học toán lớp 1", ("learn", False)),
    ("khóa học về Bayes", ("learn", False)),
    ("I want to learn about electric fields", ("learn", False)),
    ("học điện trường là gì", ("learn", True)),
    ("tìm khóa học vật lí", ("learn", False)),
    ("Giải phương trình 2x + 3 = 7", ("solve", False)),
    ("tính 12 + 30", ("solve", False)),
    ("solve 3x^2 - 12 = 0", ("solve", False)),
    ("giải bài 3 trang 45", ("solve", False)),
    ("xin chào", ("other", False)),
    ("hello", ("other", False)),
    ("cảm ơn nhé", ("other", False)),
    ("điện trường", None),  # a bare topic: the model decides (search runs beside it)
    ("Đường sức điện là gì?", None),
    ("hôm nay trời đẹp nhỉ", None),
    ("tính chất của điện trường", None),
])
def test_route_text_rules(text, expected):
    assert route_text(text) == expected


def test_route_text_follow_up_with_an_active_problem_goes_to_the_model():
    assert route_text("x = 3 đúng không?", active_problem=True) is None
    assert route_text("em muốn học điện trường", active_problem=True) == ("learn", False)


def test_learn_rule_makes_no_model_call_and_cards_come_before_the_sentence(ask, llm):
    r = ask(text="em muốn học điện trường lớp 11", lang="vi")
    kinds = [k for k, _ in parse_sse(r.text)]
    assert kinds == ["thread", "intent", "courses", "answer", "done"]
    assert llm.calls == []


def test_solve_rule_skips_the_classifier(ask, llm):
    llm.script["mentor-reasoning"] = [SOLUTION]
    ev = events(ask(text="Giải giúp: cấp số cộng u1=3, d=4, tính S20", lang="vi"))
    assert ev["intent"]["intent"] == "solve" and "solution" in ev
    assert llm.aliases() == ["mentor-reasoning"]


def test_ambiguous_message_asks_the_model(ask, llm):
    llm.script["mentor-chat"] = [j(intent="other", query="", followup=False, reply="Em muốn học gì nhé?")]
    ev = events(ask(text="hôm nay trời đẹp nhỉ", lang="vi"))
    assert ev["intent"]["intent"] == "other" and llm.aliases() == ["mentor-chat"]


def test_greeting_is_answered_without_a_model(ask, llm):
    ev = events(ask(text="xin chào", lang="vi"))
    assert ev["intent"]["intent"] == "other" and "khóa học" in ev["answer"]["text"] and llm.calls == []


def test_only_relevant_courses_are_returned(ask, llm):
    ev = events(ask(text="em muốn học điện trường lớp 11", lang="vi"))
    assert [c["course_id"] for c in ev["courses"]["items"]] == ["dev-sample-dien-truong"]
    assert ev["answer"]["text"].startswith("Khóa này hợp") and "Có " not in ev["answer"]["text"]
    ev = events(ask(text="em muốn học lịch sử Việt Nam", lang="vi"))
    assert ev["courses"]["items"] == [] and "chưa có khóa" in ev["answer"]["text"]


def test_other_is_a_short_redirect_without_courses(ask, llm):
    llm.script["mentor-chat"] = [j(intent="other", query="", followup=False, reply="Em muốn học gì hôm nay nhé?")]
    ev = events(ask(text="hôm nay trời đẹp nhỉ", lang="vi"))
    assert ev["answer"]["text"] == "Em muốn học gì hôm nay nhé?" and "courses" not in ev and "solution" not in ev
    assert llm.aliases() == ["mentor-chat"]  # one call for routing and reply


def test_intent_falls_back_to_keywords_when_model_is_down(ask, llm):
    ev = events(ask(text="điện trường", lang="vi"))  # ambiguous, and every model call fails
    assert ev["intent"]["intent"] == "learn" and ev["courses"]["items"]
    assert ev["answer"]["text"].startswith("Khóa này hợp")  # template answer
    assert events(ask(text="hôm nay trời đẹp nhỉ", lang="vi"))["intent"]["intent"] == "other"


# ---------------------------------------------------------------- learn
def test_learn_returns_cards_tree_and_start(ask, llm, student):
    ev = events(ask(text="em muốn học về điện trường", lang="vi"))
    assert ev["answer"]["text"].startswith("Khóa này hợp") and "Điện trường" in ev["answer"]["text"]
    assert llm.aliases() == []  # no model call at all for a clear learn message
    c = ev["courses"]["items"][0]
    assert c["course_id"] == "dev-sample-dien-truong" and c["language"] == "vi" and not c["enrolled"]
    assert {"title", "cover_sha256", "description_short", "lessons_count", "est_minutes", "tree"} <= set(c)
    assert c["tree"][0]["lessons"][0]["title"]
    assert ev["courses"]["start_with"]["course_id"] == "dev-sample-dien-truong" and ev["courses"]["start_with"]["lesson_id"]
    assert ev["courses"]["suggested_all_ages"] is False


def test_learn_concept_question_gets_one_sentence_then_the_course(ask, llm):
    # "điện trường là gì" clearly matches a course: cards at once, then one model sentence (no classifier call)
    llm.script["mentor-chat"] = ["Đường sức điện là đường vẽ hướng của lực điện lên điện tích thử."]
    r = ask(text="Đường sức điện là gì?", lang="vi")
    assert [k for k, _ in parse_sse(r.text)].index("courses") < [k for k, _ in parse_sse(r.text)].index("answer")
    llm.script["mentor-chat"] = ["Đường sức điện là đường vẽ hướng của lực điện lên điện tích thử."]
    t = events(ask(text="Đường sức điện là gì?", lang="vi"))["answer"]["text"]
    assert t.startswith("Đường sức điện là") and "Khóa này hợp" in t


def test_learn_marks_enrolled_and_respects_age_band(client, ask, llm):
    client.post("/api/enrollments", json={"course_id": "dev-sample-dien-truong"})
    llm.script["mentor-chat"] = [j(intent="learn", query="điện trường", followup=False), "Em đang học khóa này rồi."]
    assert events(ask(text="điện trường", lang="vi"))["courses"]["items"][0]["enrolled"] is True
    llm.script["mentor-chat"] = [j(intent="learn", query="đếm táo", followup=False), "Khóa này dành cho lớp nhỏ hơn."]
    ev = events(ask(text="em muốn học đếm táo", lang="vi"))  # student is g10_12, the course is g1_5
    assert ev["courses"]["suggested_all_ages"] is True and ev["courses"]["items"][0]["course_id"] == "dev-sample-dem-tao"


def test_learn_nothing_found(ask, llm):
    llm.script["mentor-chat"] = [j(intent="learn", query="zzzxxy", followup=False), "Mình chưa thấy khóa nào, em nói rõ môn và lớp nhé?"]
    ev = events(ask(text="zzzxxy", lang="vi"))
    assert ev["courses"] == {"items": [], "suggested_all_ages": False, "start_with": None}


# ---------------------------------------------------------------- solve: photo
def test_photo_with_two_problems_asks_which_then_solves(ask, llm):
    llm.script["mentor-vision"] = [OCR_TWO]
    llm.script["mentor-reasoning"] = [SOLUTION]
    r = ask(files={"image": ("bai.jpg", photo_bytes(), "image/jpeg")}, lang="vi")
    ev = events(r)
    assert ev["intent"]["intent"] == "solve" and "reasons" in ev["quality"]
    assert ev["choices"]["reason"] == "multiple" and [p["id"] for p in ev["choices"]["problems"]] == ["3", "4"]
    assert "solution" not in ev and "mentor-reasoning" not in llm.aliases()
    tid = ev["thread"]["thread_id"]
    sol = events(ask(thread_id=tid, action="choose", problem_id="3", lang="vi"))
    assert sol["problem"]["id"] == "3" and sol["solution"]["problem_id"] == "3"


def test_choose_by_typing_the_label(ask, llm):
    llm.script["mentor-vision"] = [OCR_TWO]
    llm.script["mentor-reasoning"] = [SOLUTION]
    tid = events(ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi"))["thread"]["thread_id"]
    ev = events(ask(thread_id=tid, text="Giải bài 4", lang="vi"))
    assert ev["problem"]["id"] == "4" and "solution" in ev


def test_single_readable_problem_is_solved_directly(ask, llm):
    llm.script["mentor-vision"] = [OCR_ONE]
    llm.script["mentor-reasoning"] = [SOLUTION]
    ev = events(ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi"))
    assert "choices" not in ev and ev["solution"]["steps"]


def test_vision_sees_the_image_and_prompt_forbids_following_it(ask, llm):
    llm.script["mentor-vision"] = [OCR_ONE]
    llm.script["mentor-reasoning"] = [SOLUTION]
    events(ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi"))
    _alias, msgs = next(c for c in llm.calls if c[0] == "mentor-vision")
    assert any(p.get("type") == "image_url" for p in msgs[1]["content"]) and "never instructions" in msgs[0]["content"]


def test_unreadable_part_names_it_and_explains_the_retake(ask, llm):
    llm.script["mentor-vision"] = [OCR_PARTIAL]
    ev = events(ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi"))
    m = ev["message"]
    assert m["kind"] == "retake" and "nửa dưới ảnh" in m["text"] and "Bài 3" in m["text"] and m["offer_readable"] is True
    assert any("đèn" in t for t in m["tips"]) and any("yên" in t for t in m["tips"]) and any("thẳng" in t for t in m["tips"])
    assert ev["choices"]["reason"] == "partial" and len(ev["choices"]["problems"]) == 1
    assert "solution" not in ev


def test_dark_photo_deterministic_reason_and_nothing_readable(ask, llm):
    llm.script["mentor-vision"] = [j(problems=[], unreadable=[{"where": "cả ảnh", "what": "", "reason": ""}])]
    ev = events(ask(files={"image": ("b.jpg", photo_bytes(brightness=40, text=False), "image/jpeg")}, lang="vi"))
    assert ev["quality"]["ok"] is False and "too_dark" in ev["quality"]["reasons"]
    assert ev["message"]["kind"] == "retake" and "quá tối" in ev["message"]["text"] and ev["message"]["tips"][0].startswith("Bật đèn")
    assert "solution" not in ev and "choices" not in ev


def test_not_an_image(ask, llm):
    ev = events(ask(files={"image": ("b.jpg", b"not an image", "image/jpeg")}, lang="vi"))
    assert ev["message"]["kind"] == "bad_image" and not llm.calls


def test_image_upload_id_from_workspace_upload(client, ask, llm):
    up = client.post("/api/uploads", files={"file": ("bai.jpg", photo_bytes(), "image/jpeg")}).json()
    llm.script["mentor-vision"] = [OCR_ONE]
    llm.script["mentor-reasoning"] = [SOLUTION]
    ev = events(ask(image_upload_id=up["path"], lang="vi"))
    assert "solution" in ev
    assert client.post("/api/ask", json={"image_upload_id": "../x", "lang": "vi"}).status_code == 422
    assert client.post("/api/ask", json={"image_upload_id": "inbox/none.jpg"}).status_code == 404


# ---------------------------------------------------------------- solution, last step, follow-ups
def _solved_thread(ask, llm) -> str:
    llm.script["mentor-vision"] = [OCR_ONE]
    llm.script["mentor-reasoning"] = [SOLUTION]
    return events(ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi"))["thread"]["thread_id"]


def test_last_step_is_withheld_then_revealed(ask, llm):
    llm.script["mentor-vision"] = [OCR_ONE]
    llm.script["mentor-reasoning"] = [SOLUTION]
    r = ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi")
    sol = events(r)["solution"]
    assert [s["title"] for s in sol["steps"]] == ["Nhớ lại công thức tổng", "Thay số"] and sol["last_step_withheld"] is True
    assert "820" not in r.text and sol["tip"]
    tid = events(r)["thread"]["thread_id"]
    for kw in ({"action": "last_step"}, {"text": "Xem bước cuối"}):
        ev = events(ask(thread_id=tid, lang="vi", **kw))
        assert ev["last_step"]["step"]["md"].endswith("820$") and "mentor-reasoning" in llm.aliases()
    assert llm.aliases().count("mentor-reasoning") == 1  # revealing is free: no extra model call


def test_follow_up_simpler_resolves_with_previous_solution(ask, llm):
    tid = _solved_thread(ask, llm)
    llm.script["mentor-reasoning"] = [SIMPLER]
    ev = events(ask(thread_id=tid, text="Giải thích dễ hơn", lang="vi"))
    assert ev["solution"]["steps"] == [{"title": "Ý chính", "md": "Cộng 20 số."}] and ev["solution"]["last_step_withheld"] is True
    _, msgs = llm.calls[-1]
    assert "previous_solution" in msgs[1]["content"] and "more simply" in msgs[0]["content"]


def test_follow_up_three_similar(ask, llm):
    tid = _solved_thread(ask, llm)
    llm.script["mentor-reasoning"] = [SIMILAR]
    ev = events(ask(thread_id=tid, action="similar", lang="vi"))
    assert len(ev["similar"]["items"]) == 3 and ev["similar"]["items"][0]["answer_md"]
    llm.script["mentor-reasoning"] = [SIMILAR]
    assert len(events(ask(thread_id=tid, text="Làm 3 bài tương tự", lang="vi"))["similar"]["items"]) == 3


def test_follow_up_free_question_about_the_problem(ask, llm):
    tid = _solved_thread(ask, llm)
    llm.script["mentor-chat"] = [j(intent="solve", query="", followup=True), "Vì $d$ là công sai giữa hai số hạng liên tiếp."]
    ev = events(ask(thread_id=tid, text="d là gì vậy?", lang="vi"))
    assert "công sai" in ev["answer"]["text"] and "solution" not in ev


def test_follow_up_without_problem(ask, llm):
    tid = events(ask(text="x", lang="vi"))["thread"]["thread_id"]
    llm.script["mentor-chat"] = ["x"]
    assert events(ask(thread_id=tid, action="last_step", lang="vi"))["message"]["kind"] == "no_problem"


def test_thread_is_private_and_unknown_threads_404(client, ask, llm):
    tid = _solved_thread(ask, llm)
    assert client.post("/api/ask", json={"text": "hi", "thread_id": "a-nope"}).status_code == 404
    client.app.state.gw.users.create(username="other", password="123456", role="student", display_name="o", birth_year=2010,
                                     language="vi")
    login(client, "other")
    assert client.post("/api/ask", json={"action": "last_step", "thread_id": tid}).status_code == 404


def test_model_down_ends_with_error_event(ask, llm):
    r = ask(files={"image": ("b.jpg", photo_bytes(), "image/jpeg")}, lang="vi")  # no vision script -> LLMError
    kinds = [k for k, _ in parse_sse(r.text)]
    assert kinds[0] == "thread" and "error" in kinds and kinds[-1] == "done"


def test_english_user_language_is_passed_to_models(ask, llm):
    llm.script["mentor-chat"] = [j(intent="other", query="", followup=False, reply="What would you like to learn?")]
    events(ask(text="nice weather today", lang="en"))
    assert '"lang": "en"' in llm.calls[-1][1][1]["content"]


# ---------------------------------------------------------------- audio
def test_audio_is_transcribed_then_routed(ask, llm):
    llm.script["mentor-audio"] = ["Em muốn học về điện trường"]
    llm.script["mentor-chat"] = [j(intent="learn", query="điện trường", followup=False), "Có 1 khóa hợp với em."]
    r = ask(files={"audio": ("voice.wav", b"RIFFfake", "audio/wav")}, lang="vi")
    kinds = [k for k, _ in parse_sse(r.text)]
    assert kinds.index("transcript") < kinds.index("intent") < kinds.index("courses")
    assert events(r)["transcript"]["text"] == "Em muốn học về điện trường"
    _, msgs = llm.calls[0]
    assert msgs[0]["content"][1]["input_audio"]["format"] == "wav"


def test_silent_audio(ask, llm):
    llm.script["mentor-audio"] = ["NO_SPEECH"]
    ev = events(ask(files={"audio": ("v.wav", b"RIFFfake", "audio/wav")}, lang="vi"))
    assert ev["message"]["kind"] == "no_speech" and "transcript" not in ev and "intent" not in ev


# ---------------------------------------------------------------- access
def test_teacher_gets_403_and_anonymous_401(client, llm):
    client.app.state.ask = AskService(client.app.state.content, client.app.state.gw.db, client.app.state.gw.clock, llm)
    assert client.post("/api/ask", json={"text": "hi"}).status_code == 401
    login(client, "giaovien", role="teacher")
    r = client.post("/api/ask", json={"text": "hi"})
    assert r.status_code == 403 and r.json() == {"error": "role_mismatch"}


def test_empty_request_is_422(ask):
    assert ask().status_code == 422


# ---------------------------------------------------------------- guide
def test_guide_uses_the_map_as_context(client, student, llm):
    client.app.state.ask = AskService(client.app.state.content, client.app.state.gw.db, client.app.state.gw.clock, llm)
    llm.script["mentor-chat"] = ["Gõ tên khóa vào ô tìm kiếm. Mặc định chỉ hiện khóa hợp lớp em!"]
    r = client.post("/api/guide", json={"question": "Làm sao tìm khóa mới?", "lang": "vi", "screen": "courses",
                                        "visible_keys": ["course-search", "my-courses"]})
    assert r.status_code == 200 and r.json()["answer"].startswith("Gõ tên khóa") and "!" not in r.json()["answer"]
    _, msgs = llm.calls[0]
    ctx = json.loads(msgs[1]["content"])
    assert ctx["visible_keys"] == ["course-search", "my-courses"] and "course-search" in ctx["guide_map"]
    assert ctx["guide_map"]["ask"].startswith("Hỏi đáp") and "ONLY questions about how to use the app" in msgs[0]["content"].replace("\n", " ")


def test_guide_without_model_answers_from_the_visible_area(client, student):
    r = client.post("/api/guide", json={"question": "nút tìm kiếm là gì", "lang": "en", "visible_keys": ["my-courses", "course-search"]})
    assert r.json()["answer"].startswith("Type a course name")
    r = client.post("/api/guide", json={"question": "asdf", "lang": "vi"})
    assert "nhấn giữ" in r.json()["answer"]


def test_guide_model_failure_falls_back(client, student, llm):
    client.app.state.ask = AskService(client.app.state.content, client.app.state.gw.db, client.app.state.gw.clock, llm)
    r = client.post("/api/guide", json={"question": "settings", "lang": "en", "screen": "settings"})
    assert r.status_code == 200 and r.json()["answer"].startswith("Settings:")


def test_guide_validates_input_and_requires_login(client):
    assert client.post("/api/guide", json={"question": "hi"}).status_code == 401
    login(client)
    assert client.post("/api/guide", json={"question": ""}).status_code == 422


@pytest.mark.skipif(not GUIDES_TS.is_file(), reason="apps/app not checked out")
def test_guide_map_json_matches_guides_ts():
    body = GUIDES_TS.read_text(encoding="utf-8").split("export const GUIDES")[1].split("const strip")[0]
    ts = {m.group(1): {"vi": m.group(2), "en": m.group(3)}
          for m in re.finditer(r'"?([\w-]+)"?: \{\s*vi: "(.*?)",\s*en: "(.*?)",\s*\}', body, re.DOTALL)}
    assert ts and ts == guide_mod.guide_map(), "guide_map.json is out of date: run `pnpm run guides:export` in apps/app"


# ---------------------------------------------------------------- coming-soon placeholders in the reply text
def _card(title, status, score):
    return {"title": title, "status": status, "score": score}


def test_learn_text_never_starts_from_a_placeholder():
    t = AskService._learn_text
    assert t([_card("Vật lí 11", "live", 0.9)], "vi") == "Khóa này hợp với em: Vật lí 11."
    soon_only = t([_card("Toán 2", "coming_soon", 0.8)], "vi")
    assert "sắp có" in soon_only and "bắt đầu" not in soon_only.lower()
    better_soon = t([_card("Toán 1", "live", 0.48), _card("Toán 2", "coming_soon", 0.75)], "vi")
    assert better_soon.startswith("Khóa Toán 2 sắp có") and "Toán 1" in better_soon
    assert t([_card("A", "live", 0.9), _card("B", "live", 0.8)], "vi").startswith("Có 2 khóa")


def test_search_relevance_cut_drops_weak_and_far_behind_courses(tmp_path):
    from mentor_schemas.course import CatalogEntry

    from mentor_gateway.content.search import CourseSearch, Doc

    def doc(i, title, desc):
        e = CatalogEntry.model_construct(id=i, title=title, subject="", pack_sha256="x", cover_sha256="", age_band="g10_12")
        return Doc(e, {"title": title, "subject": "", "desc": desc, "lessons": "", "ideas": ""}, title, i)

    docs = [doc("p", "Vật lí 11: Điện trường", "điện tích và đường sức điện"), doc("m", "Toán 1: Các số đến 10", "đếm và so sánh"),
            doc("b", "Xác suất: Suy luận Bayes", "xác suất có điều kiện")]
    s = CourseSearch(tmp_path)  # no router: lexical only
    assert [e.id for e, _ in s.search("em muốn học điện trường lớp 11", docs)[0]] == ["p"]
    assert s.search("học lịch sử", docs)[0] == []
