"""CONTRACTS 16.3-16.5: step quiz types in practice + fix wrong answers, class notes -> review questions, teacher review by
step. Offline: the vision model is a stub, the builder runner is the teacher tests' FakeRunner."""

import io
import json
import shutil

import pytest
from gateway_fakes import login, set_band
from mentor_schemas.course import (
    Chapter, CourseMeta, CoursePack, Lesson, QuizBlock, QuizItem, QuizOption, QuizPart, TextBlock,
)
from PIL import Image
from test_gw_ask import FakeLLM, j, photo_bytes
from test_gw_practice_courses import SAMPLES, enroll, practice_content, settings  # noqa: F401  (fixtures)
from test_gw_teacher import FakeRunner, built_course  # noqa: F401
from test_gw_teacher import runner as runner  # noqa: F401

from mentor_gateway.ask.service import AskService
from mentor_gateway.content import ContentStore
from mentor_gateway.practice import scoring

P = "/api/practice"
CID = "toan-buoc"


def step_items() -> list[QuizItem]:
    return [
        QuizItem(id="f1", type="FILL_TILES", stem="Diện tích = {{gap}} x rộng", parts=[QuizPart(id="p1", text="dài"), QuizPart(id="p2", text="cao")],
                 answer_key={"gaps": ["p1"]}, explanation="Dài nhân rộng.", difficulty=1),
        QuizItem(id="m1", type="MATCH_PAIRS", stem="Nối", parts=[QuizPart(id="l1", text="m", side="left"), QuizPart(id="l2", text="s", side="left"),
                 QuizPart(id="r1", text="mét", side="right"), QuizPart(id="r2", text="giây", side="right")],
                 answer_key={"pairs": {"l1": "r1", "l2": "r2"}}, explanation="Đơn vị.", difficulty=1),
        QuizItem(id="o1", type="ORDER_STEPS", stem="Sắp xếp", parts=[QuizPart(id="s1", text="a"), QuizPart(id="s2", text="b"), QuizPart(id="s3", text="c")],
                 answer_key={"order": ["s1", "s2", "s3"]}, explanation="Theo thứ tự.", difficulty=2),
        QuizItem(id="c1", type="SINGLE_CHOICE", stem="1+1?", options=[QuizOption(id="A", text="2"), QuizOption(id="B", text="3")],
                 answer_key={"correct_option_id": "A"}, explanation="Hai.", option_feedback={"B": "Đếm thừa."}, difficulty=1),
    ]


def pack(version=1) -> CoursePack:
    return CoursePack(course_id=CID, version=version, language="vi", age_band="g6_9", title="Toán bước", chapters=[
        Chapter(id="ch1", title="Chương", lessons=[Lesson(id="bai-1", title="Bài 1", est_minutes=5, blocks=[
            TextBlock(id="t1", md="Chào"), QuizBlock(id="quiz1", items=step_items())])])])


@pytest.fixture
def store(client, tmp_path) -> ContentStore:
    root = tmp_path / "courses"
    shutil.copytree(SAMPLES, root)
    s = ContentStore(root, client.app.state.gw.clock)
    s.create_draft(CourseMeta(id=CID, title="Toán bước", subject="Toán", age_band="g6_9", language="vi", teacher_id="gv",
                              teacher_name="Cô Lan", description_short="Từng bước.", cover="cover.png"))
    (s.course_dir(CID) / "cover.png").write_bytes(b"\x89PNG cover")
    s.write_pack(CID, 1, pack(), {})
    s.publish(CID, 1)
    client.app.state.content.store = s
    return s


# ------------------------------------------------------------------ 16.3
def test_step_scoring():
    fill = {"type": "FILL_TILES", "answer_key": {"gaps": ["p1", "p2"]}}
    assert scoring.score_item(fill, json.dumps({"gaps": ["p1", "p2"]})).correct
    assert scoring.score_item(fill, json.dumps({"gaps": ["p2", "p1"]})).correct is False
    assert scoring.score_item(fill, json.dumps({"gaps": []})).correct is False and scoring.score_item(fill, None).correct is None
    assert scoring.score_item(fill, "not json").correct is False
    pairs = {"type": "MATCH_PAIRS", "answer_key": {"pairs": {"l1": "r1"}}}
    assert scoring.score_item(pairs, '{"pairs": {"l1": "r1"}}').correct and not scoring.score_item(pairs, '{"pairs": {"l1": "r2"}}').correct
    order = {"type": "ORDER_STEPS", "answer_key": {"order": ["a", "b"]}}
    assert scoring.score_item(order, '{"order": ["a","b"]}').correct and not scoring.score_item(order, '{"order": ["b","a"]}').correct
    assert json.loads(scoring.correct_answer_text(order)) == {"order": ["a", "b"]}


def test_fix_wrong_answers_after_the_session(client, gw, student, store):
    set_band(client, "g6_9")
    enroll(client, CID, "bai-1")
    r = client.post(f"{P}/sessions", json={"source": f"course:{CID}", "seed": 1})
    assert r.status_code == 200, r.text
    s = r.json()
    by_type = {i["type"]: i for i in s["items"]}
    assert set(by_type) == {"FILL_TILES", "MATCH_PAIRS", "ORDER_STEPS", "SINGLE_CHOICE"}
    assert {p["id"] for p in by_type["FILL_TILES"]["parts"]} == {"p1", "p2"} and "answer_key" not in json.dumps(s)
    wrong = {"FILL_TILES": {"gaps": ["p2"]}, "MATCH_PAIRS": {"pairs": {"l1": "r2", "l2": "r1"}},
             "ORDER_STEPS": {"order": ["s3", "s2", "s1"]}, "SINGLE_CHOICE": "B"}
    sid = s["id"]
    for it in s["items"]:
        a = wrong[it["type"]]
        res = client.post(f"{P}/sessions/{sid}/answer", json={"position": it["position"], "answer": a, "time_spent_sec": 3})
        assert res.status_code == 200, res.text
        assert res.json()["correct"] is False
    assert client.post(f"{P}/sessions/{sid}/fix", json={"item_id": "x", "answer": "A"}).status_code == 409  # not finished yet
    report = client.post(f"{P}/sessions/{sid}/finish").json()
    chosen = {w["type"]: w["chosen"] for w in report["wrong"]}
    assert len(report["wrong"]) == 4 and json.loads(chosen["FILL_TILES"]) == {"gaps": ["p2"]} and chosen["SINGLE_CHOICE"] == "B"

    ids = {w["type"]: w["item_id"] for w in report["wrong"]}
    ok = client.post(f"{P}/sessions/{sid}/fix", json={"item_id": ids["ORDER_STEPS"], "answer": {"order": ["s1", "s2", "s3"]}})
    assert ok.status_code == 200 and ok.json() == {"correct": True}
    assert client.post(f"{P}/sessions/{sid}/fix", json={"item_id": ids["ORDER_STEPS"], "answer": "x"}).json()["code"] == "already_fixed"
    bad = client.post(f"{P}/sessions/{sid}/fix", json={"item_id": ids["SINGLE_CHOICE"], "answer": "B"}).json()
    assert bad["correct"] is False and bad["right"] == "A" and bad["explanation"] == "Hai." and bad["note"] == "Đếm thừa."
    bad = client.post(f"{P}/sessions/{sid}/fix", json={"item_id": ids["FILL_TILES"], "answer": {"gaps": ["p2"]}}).json()
    assert json.loads(bad["right"]) == {"gaps": ["p1"]}
    assert client.post(f"{P}/sessions/{sid}/fix", json={"item_id": "nope", "answer": "A"}).json()["code"] == "not_wrong"
    # the evidence still says wrong: those items stay in review
    text = gw.mirror.read_text(student["user_id"], "events.jsonl")
    assert text.count('"correct":false') + text.count('"correct": false') == 4


# ------------------------------------------------------------------ 16.4
NOTES = j(readable=True, title="Chuyển động", subject="Lí", items=[
    {"type": "SINGLE_CHOICE", "stem": f"Câu {i}", "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
     "answer_key": {"correct_option_id": "A"}, "explanation": "vì", "option_feedback": {"B": "sai"}} for i in range(5)]
    + [{"type": "bogus"}])


@pytest.fixture
def notes_llm(client, student):
    llm = FakeLLM(**{"mentor-vision": NOTES})
    client.app.state.ask = AskService(client.app.state.content, client.app.state.gw.db, client.app.state.gw.clock, llm)
    return llm


def post_notes(client, n=1):
    return client.post("/api/ask/notes", files=[("images", (f"p{i}.jpg", photo_bytes(), "image/jpeg")) for i in range(n)])


def test_notes_become_review_questions_and_reminders(client, gw, student, notes_llm):
    set_band(client, "g6_9")
    r = post_notes(client, 2)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pages"] == 2 and d["items"] == 5 and d["title"] == "Chuyển động" and d["notes_id"].startswith("n-")
    assert d["first_review_at"] < d["next_review_at"]
    assert notes_llm.aliases() == ["mentor-vision"]
    rem = client.get("/api/reminders").json()["reminders"]
    assert [x["at"] for x in rem if x["kind"] == "later"] == [d["first_review_at"], d["next_review_at"]]
    s = client.post(f"{P}/sessions", json={"source": f"notes:{d['notes_id']}"})
    assert s.status_code == 200, s.text
    assert len(s.json()["items"]) == 5 and "answer_key" not in json.dumps(s.json())
    assert client.post(f"{P}/sessions", json={"source": "notes:n-zzz"}).json()["code"] == "notes_not_found"


def test_notes_unreadable_and_band(client, student, notes_llm):
    set_band(client, "g6_9")
    notes_llm.script["mentor-vision"] = j(readable=False, title="", subject="", items=[])
    r = post_notes(client)
    assert r.status_code == 422 and r.json()["error"] == "unreadable"
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1600), (10, 10, 10)).save(buf, "JPEG")  # black: no model call
    n = len(notes_llm.calls)
    r = client.post("/api/ask/notes", files=[("images", ("b.jpg", buf.getvalue(), "image/jpeg"))])
    assert r.status_code == 422 and len(notes_llm.calls) == n
    set_band(client, "g1_5")
    assert post_notes(client).status_code == 403


# ------------------------------------------------------------------ 16.5
FakeRunner.do_retts_block = lambda self, job, args: {}
FakeRunner.do_recap = lambda self, job, args: {}

def wait_for(runner, kind, timeout=8):
    import time
    end = time.time() + timeout
    while time.time() < end and not [c for c in runner.calls if c[0] == kind]:
        time.sleep(0.05)


def vers(cid):
    return f"/api/teacher/courses/{cid}/versions/1"


def test_teacher_patch_block_recap_gloss_review(client, teacher, runner, store, gw):  # noqa: F811
    cid = built_course(client, runner, store, teacher["id"])
    r = client.patch(f"{vers(cid)}/blocks/b2", json={"md": "Viết lại"})
    assert r.status_code == 200 and r.json()["block"]["md"] == "Viết lại"
    assert store.load_pack(cid, 1).chapters[0].lessons[0].blocks[1].md == "Viết lại"
    assert not [c for c in runner.calls if c[0] == "retts_block"]  # no read-aloud on this block
    r = client.patch(f"{vers(cid)}/blocks/b4", json={"items": [{"id": "q1", "stem": "Câu mới?"}]})
    assert r.status_code == 200 and store.load_pack(cid, 1).chapters[0].lessons[0].blocks[3].items[0].stem == "Câu mới?"
    bad = client.patch(f"{vers(cid)}/blocks/b4", json={"items": [{"id": "q1", "answer_key": {"correct_option_id": "Z"}}]})
    assert bad.status_code == 422 and bad.json()["error"] == "invalid_block"
    assert client.patch(f"{vers(cid)}/blocks/nope", json={"md": "x"}).status_code == 404

    # read-aloud text: its audio is redone by a builder job
    pk = store.load_pack(cid, 1)
    pk.chapters[0].lessons[0].blocks[1].audio = pk.chapters[0].lessons[0].blocks[2].image
    store.write_pack(cid, 1, pk)
    assert client.patch(f"{vers(cid)}/blocks/b2", json={"md": "Đọc to"}).status_code == 200
    import time
    wait_for(runner, "retts_block")
    kind, args = [c for c in runner.calls if c[0] == "retts_block"][-1]
    assert args["version"] == 1 and args["block_id"] == "b2"

    chap = pk.chapters[0].id
    r = client.put(f"{vers(cid)}/chapters/{chap}/recap", json={"script": ["Một.", "Hai."]})
    assert r.status_code == 200 and r.json()["job_id"]
    wait_for(runner, "recap")
    assert [c for c in runner.calls if c[0] == "recap"][-1][1]["script"] == ["Một.", "Hai."]
    assert client.put(f"{vers(cid)}/chapters/zz/recap", json={"script": ["a"]}).status_code == 404

    assert client.put(f"{vers(cid)}/gloss", json={"gloss_start": 40}).json() == {"gloss_start": 40}
    assert store.load_pack(cid, 1).gloss_start == 40
    assert client.put(f"{vers(cid)}/gloss", json={"gloss_start": 140}).status_code == 422

    assert client.get(f"{vers(cid)}/review").json() == {"unsure": []}
    f = gw.settings.builder_dir / cid / "versions" / "1"
    f.mkdir(parents=True, exist_ok=True)
    (f / "review.json").write_text(json.dumps({"unsure": [{"block_id": "b2", "reason_vi": "a", "reason_en": "a"},
                                                         {"block_id": "b4", "item_id": "q1", "reason_vi": "b", "reason_en": "b"}]}))
    assert len(client.get(f"{vers(cid)}/review").json()["unsure"]) == 2
    assert [x["block_id"] for x in client.post(f"{vers(cid)}/review/b2/seen").json()["unsure"]] == ["b4"]

    client.put(f"{vers(cid)}/level", json={"level": "basic"})
    assert client.post(f"{vers(cid)}/publish").status_code == 200
    assert client.patch(f"{vers(cid)}/blocks/b2", json={"md": "x"}).json()["error"] == "version_published"
    assert client.put(f"{vers(cid)}/gloss", json={"gloss_start": 10}).status_code == 409


def test_course_test_size_is_reflected_in_levels(client, teacher, runner, store, gw, monkeypatch):  # noqa: F811
    cid = built_course(client, runner, store, teacher["id"])
    bank = gw.practice.bank
    pid = next(iter(bank.profiles))
    assert client.put(f"/api/teacher/courses/{cid}/tests/{pid}", json={"items": 12, "minutes": 30}).json() == {"items": 12, "minutes": 30}
    assert client.put(f"/api/teacher/courses/{cid}/tests/zzz", json={"items": 12, "minutes": 30}).status_code == 404
    assert gw.practice.course_tests(cid)[pid] == {"items": 12, "minutes": 30}
    card = {"profile_id": pid, "title": "t", "subject": "s", "minutes": 90, "items": 40, "last_score": None}
    monkeypatch.setattr(type(gw.practice), "_mock_cards", lambda self, uid: [dict(card)])
    monkeypatch.setattr(type(gw.practice), "_matching_bank_subjects", lambda self, b: {"s"})
    login(client)
    set_band(client, "g10_12")
    from test_gw_practice_courses import enroll as enr  # noqa: F401
    store.publish(cid, 1) if False else None
    # the student sees the course only once published; call the mixin directly with a stub bundle instead
    monkeypatch.setattr(type(gw.practice), "bundles", lambda self, uid, only=None: [type("B", (), {
        "course_id": cid, "title": "T", "items": [], "studied_items": lambda s: []})()])
    out = gw.practice.course_levels("u", cid)
    assert out["mocks"][0]["items"] == 12 and out["mocks"][0]["minutes"] == 30
