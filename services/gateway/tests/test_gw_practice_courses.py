"""Luyện tập from course quizzes (P5-A): item mapping, scoring of the new types, the default session for a g1_5 student,
pinned versions, per-course practice, `/practice/home`, evidence and the planner feedback. Offline, no LLM.

Courses come from a temp copy of the dev sample courses (`tests/fixtures/courses`, never modified) plus a synthetic g1_5
course with enough items for a session.
"""

import json
import shutil
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from gateway_fakes import set_band
from mentor_schemas import LearningEvent
from mentor_schemas.course import (
    Chapter,
    CourseMeta,
    CoursePack,
    Lesson,
    QuizBlock,
    QuizItem,
    QuizOption,
    TapTarget,
    TextBlock,
)
from practice_fixtures import build_content

from mentor_gateway.content import ContentStore, asset_ref_for
from mentor_gateway.planner import events as planner_events
from mentor_gateway.practice import scoring
from mentor_gateway.practice.mixed import KID_TYPES

REPO = Path(__file__).resolve().parents[3]
SAMPLES = Path(__file__).parent / "fixtures" / "courses"
FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"
P = "/api/practice"
APPLE = b"\x89PNG apple"
PEAR = b"\x89PNG pear"
KID = "dem-nhieu"


@pytest.fixture(scope="session")
def practice_content(tmp_path_factory) -> Path:
    return build_content(FIXTURE_CONTENT, tmp_path_factory.mktemp("pc") / "mentor-content")


@pytest.fixture
def settings(settings, practice_content):
    return settings.model_copy(update={"content_dir": practice_content})


# ---------------------------------------------------------------- course fixtures
def kid_items(flip: bool = False) -> list[list[QuizItem]]:
    """Two lessons, g1_5: picture choice, tap count, single choice (4 + 4 items). `flip` moves every key (a v2)."""
    apple, pear = asset_ref_for("a.png", APPLE, "image/png"), asset_ref_for("p.png", PEAR, "image/png")
    lessons = []
    for lesson in (1, 2):
        items = []
        for i in range(1, 5):
            qid = f"l{lesson}-q{i}"
            if i == 1 or i == 4 and lesson == 2:
                key = "B" if flip else "A"
                items.append(QuizItem(id=qid, type="PICTURE_CHOICE", stem=f"Chọn quả táo {qid}",
                                      options=[QuizOption(id="A", image=apple), QuizOption(id="B", image=pear)],
                                      answer_key={"correct_option_id": key}, explanation="Quả táo tròn.", difficulty=1))
            elif i == 2:
                items.append(QuizItem(id=qid, type="TAP_COUNT", stem=f"Đếm {qid}", tap=TapTarget(image=apple, total=9),
                                      answer_key={"count": 3}, explanation="Có 3 quả.", difficulty=1))
            else:
                items.append(QuizItem(id=qid, type="SINGLE_CHOICE", stem=f"1 + {i} = ?",
                                      options=[QuizOption(id="A", text="2"), QuizOption(id="B", text="3"),
                                               QuizOption(id="C", text=str(i + 1))],
                                      answer_key={"correct_option_id": "C"}, explanation="Cộng hai số.",
                                      option_feedback={"A": "Em đếm thiếu một."}, difficulty=2))
        lessons.append(items)
    return lessons


def kid_pack(version: int, flip: bool = False) -> CoursePack:
    return CoursePack(course_id=KID, version=version, language="vi", age_band="g1_5", title="Toán 1: Đếm nhiều", chapters=[
        Chapter(id="ch1", title="Đếm", lessons=[
            Lesson(id=f"bai-{n}", title=f"Bài {n}: Đếm {n}", est_minutes=5, blocks=[
                TextBlock(id=f"t{n}", md="Đếm cùng Cún"), QuizBlock(id=f"quiz{n}", items=items)])
            for n, items in enumerate(kid_items(flip), start=1)])])


KID_META = CourseMeta(id=KID, title="Toán 1: Đếm nhiều", subject="Toán", age_band="g1_5", language="vi", teacher_id="gv",
                      teacher_name="Cô Lan", description_short="Đếm đến 10.", cover="cover.png")


@pytest.fixture
def store(client, tmp_path) -> ContentStore:
    root = tmp_path / "courses"
    shutil.copytree(SAMPLES, root)  # the dev samples are read-only fixtures: only the copy is used
    s = ContentStore(root, client.app.state.gw.clock)
    s.create_draft(KID_META)
    (s.course_dir(KID) / "cover.png").write_bytes(APPLE + b"cover")
    s.write_pack(KID, 1, kid_pack(1), {"a.png": APPLE, "p.png": PEAR})
    s.publish(KID, 1)
    client.app.state.content.store = s
    return s


def enroll(client, course_id: str, lesson_id: str | None = None) -> None:
    assert client.post("/api/enrollments", json={"course_id": course_id}).status_code in (200, 201)
    if lesson_id:
        r = client.put(f"/api/enrollments/{course_id}/progress", json={"lesson_id": lesson_id})
        assert r.status_code == 200, r.text


def session_doc(gw, sid: str, pos: int) -> dict:
    from mentor_gateway.practice.tables import PracticeSession

    with gw.db.session() as s:
        return dict(s.get(PracticeSession, sid).items[pos]["doc"])


def right_answer(gw, sid: str, pos: int) -> str:
    return scoring.correct_answer_text(session_doc(gw, sid, pos))


def wrong_answer(item: dict) -> str:
    if item["type"] in ("SINGLE_CHOICE", "PICTURE_CHOICE"):
        return next(o["id"] for o in item["options"] if o["id"] != "C" and o["id"] != "A") if item["type"] == "SINGLE_CHOICE" else "B"
    return "9"


def start(client, **kw):
    r = client.post(f"{P}/sessions", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 1. mapping
def test_every_quiz_type_maps_to_an_engine_item(client, gw, student, store):
    enroll(client, "dev-sample-dien-truong", "bai-4-dien-truong-deu")
    enroll(client, "dev-sample-dem-tao", "bai-1-dem-tao")
    by_id = {i.id: i for b in gw.practice.bundles(student["user_id"]) for i in b.items}
    assert set(by_id) == {"dev-sample-dien-truong:q-chieu-duong-suc", "dev-sample-dien-truong:q-nhan-dinh", "dev-sample-dien-truong:q-tinh-e", "dev-sample-dien-truong:q-deu",
                          "dev-sample-dem-tao:q-cham-dem", "dev-sample-dem-tao:q-chon-hinh"}

    single = by_id["dev-sample-dien-truong:q-chieu-duong-suc"]
    assert single.type == "SINGLE_CHOICE" and single.level == 1 and single.estimate == 0.18  # difficulty 1 -> level 1 midpoint
    assert single.subject == "vat-li" and single.topic == "dev-sample-dien-truong/bai-3-duong-suc-dien"  # lesson is the topic
    assert single.skill_ids == ("vatli.dien-truong.duong-suc",) and single.doc["course"]["lesson_title"]
    assert [o["id"] for o in single.doc["options"]] and single.doc["answer_key"]["correct_option_id"]

    tf = by_id["dev-sample-dien-truong:q-nhan-dinh"]
    assert [s["id"] for s in tf.doc["statements"]] == ["a", "b", "c", "d"]
    assert [s["truth"] for s in tf.doc["statements"]] == [False, True, False, True]
    assert tf.level == 2 and tf.seconds > single.seconds

    short = by_id["dev-sample-dien-truong:q-tinh-e"]
    assert short.doc["short_answer"]["accepted"][0] == "4e5" and short.doc["short_answer"]["tolerance"] == 0.01
    assert short.level == 3 and short.estimate == 0.65

    tap = by_id["dev-sample-dem-tao:q-cham-dem"]
    assert tap.type == "TAP_COUNT" and tap.doc["tap"]["total"] >= 1 and tap.doc["tap"]["image"]["url"].startswith(
        "/api/courses/dev-sample-dem-tao/versions/1/assets/")
    assert tap.skill_ids == ("dev-sample-dem-tao.bai-1-dem-tao",)  # no author skill ids: one lesson-level skill

    pic = by_id["dev-sample-dem-tao:q-chon-hinh"]
    assert pic.type == "PICTURE_CHOICE" and all(o["image"]["url"] for o in pic.doc["options"])


# ---------------------------------------------------------------- 2. scoring
def test_scoring_of_new_types():
    pic = {"type": "PICTURE_CHOICE", "answer_key": {"correct_option_id": "B"}, "options": []}
    assert scoring.score_item(pic, "b").correct and not scoring.score_item(pic, "A").correct
    assert scoring.score_item(pic, "").correct is None and scoring.correct_answer_text(pic) == "B"

    tap = {"type": "TAP_COUNT", "answer_key": {"count": 7}}
    assert scoring.score_item(tap, "7").correct and not scoring.score_item(tap, "6").correct
    assert not scoring.score_item(tap, "bảy").correct and scoring.score_item(tap, None).correct is None
    assert scoring.correct_answer_text(tap) == "7"

    short = {"type": "SHORT_ANSWER", "short_answer": {"accepted": ["4e5", "400000", "4.10^5"], "tolerance": 0.01}}
    for good in ("4e5", "400 000", "4×10^5", "4,0e5", "399000", "4.10^5"):
        assert scoring.score_item(short, good).correct, good
    for bad in ("4e4", "380000", "xyz"):
        assert scoring.score_item(short, bad).correct is False, bad
    assert scoring.correct_answer_text(short) == "4e5"
    exact = {"type": "SHORT_ANSWER", "short_answer": {"accepted": ["0,5"]}}
    assert scoring.score_item(exact, "0.5").correct and not scoring.score_item(exact, "0,51").correct

    tf3 = {"type": "TRUE_FALSE_GROUP", "statements": [{"id": "a", "truth": True}, {"id": "b", "truth": False}, {"id": "c", "truth": True}]}
    assert scoring.score_item(tf3, "TFT").correct and scoring.score_item(tf3, "TFT").points == 1.0
    two = scoring.score_item(tf3, "TFF")
    assert two.correct is False and abs(two.points - 2 / 3) < 1e-3 and two.statement_correct == [True, True, False]
    assert scoring.score_item(tf3, "---").correct is None and scoring.correct_answer_text(tf3) == "TFT"
    tf4 = {"type": "TRUE_FALSE_GROUP", "statements": [{"id": c, "truth": t} for c, t in zip("abcd", (True, True, False, False), strict=True)]}
    assert scoring.score_item(tf4, "TTFT").points == 0.5  # four statements keep the official shares


# ---------------------------------------------------------------- 3. g1_5 default session
def test_g1_5_student_gets_a_session_from_course_items(client, gw, student):
    set_band(client, "g1_5")
    # the bank is grade 10-12 content: bank practice stays insufficient_content for a g1_5 learner
    r = client.post(f"{P}/sessions", json={"kind": "practice", "subject": "math", "minutes": 10})
    assert r.status_code == 422 and r.json()["code"] == "insufficient_content"
    # and so does the default session before any course is studied
    assert client.post(f"{P}/sessions", json={"source": "quick"}).json()["code"] == "insufficient_content"
    assert client.get(f"{P}/home").json()["quick"]["count"] == 0


def test_g1_5_quick_session_end_to_end(client, gw, student, store):
    set_band(client, "g1_5")
    enroll(client, KID, "bai-2")  # on lesson 2: lesson 1 counts as studied too
    home = client.get(f"{P}/home").json()
    q = home["quick"]
    assert q["count"] == 5 and q["minutes"] == 6  # g1_5: shorter
    assert q["from"] == [{"course_id": KID, "label": "Đếm nhiều", "n": 5}]
    s = start(client, source="quick", seed=q["seed"])
    assert s["kind"] == "practice" and s["subject"] == "quick" and len(s["items"]) == 5
    assert {i["type"] for i in s["items"]} <= set(KID_TYPES)
    assert [i["id"] for i in s["items"]] == [i["id"] for i in client.post(f"{P}/sessions", json={"source": "quick", "seed": q["seed"]}).json()["items"]]
    s = start(client, source="quick", seed=q["seed"])  # the previous (unanswered) one was replaced

    raw = json.dumps(s)
    for leak in ("answer_key", "correct_option_id", "explanation", "option_feedback", '"count": 3', "truth"):
        assert leak not in raw
    pics = [i for i in s["items"] if i["type"] == "PICTURE_CHOICE"]
    taps = [i for i in s["items"] if i["type"] == "TAP_COUNT"]
    assert all(o["image"]["url"].startswith(f"/api/courses/{KID}/versions/1/assets/") for i in pics for o in i["options"])
    assert all(i["tap"]["total"] == 9 and i["tap"]["image"]["url"] for i in taps)
    assert all(i["source"]["course_id"] == KID and i["topic_title"].startswith("Bài ") for i in s["items"])

    sid = s["id"]
    for pos, item in enumerate(s["items"]):
        ans = right_answer(gw, sid, pos) if pos < 3 else wrong_answer(item)
        res = client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": ans, "time_spent_sec": 9}).json()
        assert res["correct"] is (pos < 3)
        if pos >= 3:
            assert res["correct_answer"] == right_answer(gw, sid, pos)
    report = client.post(f"{P}/sessions/{sid}/finish").json()
    assert report["correct"] == 3 and report["total"] == 5 and report["recommendations"] == []
    assert report["takeaway"]["line_vi"] and report["takeaway"]["line_en"]
    assert {t["title"] for t in report["per_topic"]} <= {"Bài 1: Đếm 1", "Bài 2: Đếm 2"}

    # evidence: one event per answered item and skill, in the workspace under the course subject
    text = gw.mirror.read_text(student["user_id"], "events.jsonl")
    events = [LearningEvent.model_validate_json(line) for line in text.splitlines() if line.strip()]
    assert len(events) == 5 and {e.subject for e in events} == {"toan"} and all(e.grader == "bank" for e in events)
    assert sorted(e.correct for e in events) == [False, False, True, True, True]
    assert gw.mirror.read_text(student["user_id"], "learning/toan/skills.md")
    assert "luyện tập từ khóa học" in gw.mirror.read_text(student["user_id"], "learning/toan/practice-log.md")
    assert client.get(f"{P}/sessions/{sid}/review").json()[0]["source"]["course_id"] == KID


# ---------------------------------------------------------------- 4. pinned version
def test_items_come_from_the_pinned_version(client, gw, student, store):
    set_band(client, "g1_5")
    enroll(client, KID, "bai-2")
    store.create_draft(KID_META)  # v2: every picture key flipped
    store.write_pack(KID, 2, kid_pack(2, flip=True), {"a.png": APPLE, "p.png": PEAR})
    store.publish(KID, 2)
    assert client.get("/api/enrollments").json()[0]["update_available"] is True

    s = start(client, source=f"course:{KID}", seed=1)
    ids = [i["id"] for i in s["items"]]
    docs = [session_doc(gw, s["id"], p) for p in range(len(ids))]
    assert all(d["revision"] == 1 and d["course"]["version"] == 1 for d in docs)
    assert all(i["source"]["version"] == 1 for i in s["items"])
    pic = next(d for d in docs if d["type"] == "PICTURE_CHOICE")
    assert pic["answer_key"]["correct_option_id"] == "A"  # v1 key, not the flipped v2
    assert all(o["image"]["url"].startswith(f"/api/courses/{KID}/versions/1/") for d in docs if d["type"] == "PICTURE_CHOICE"
               for o in d["options"])


# ---------------------------------------------------------------- 5. per-course practice
def test_course_practice_covers_only_studied_lessons(client, gw, student, store):
    set_band(client, "g1_5")
    assert client.post(f"{P}/sessions", json={"source": f"course:{KID}"}).json()["code"] == "course_not_found"  # not enrolled
    enroll(client, KID)  # enrolled, nothing studied
    assert client.get(f"{P}/home").json()["by_course"] == []
    assert client.post(f"{P}/sessions", json={"source": f"course:{KID}"}).json()["code"] == "insufficient_content"

    client.put(f"/api/enrollments/{KID}/progress", json={"lesson_id": "bai-1"})
    by = client.get(f"{P}/home").json()["by_course"]
    assert by == [{"course_id": KID, "title": "Toán 1: Đếm nhiều", "cover_sha256": by[0]["cover_sha256"],
                   "lessons_range": "Bài 1", "lessons_from": 1, "lessons_to": 1, "items": 4}]
    assert len(by[0]["cover_sha256"]) == 64
    s = start(client, source=f"course:{KID}")
    assert len(s["items"]) == 4 and {i["source"]["lesson_id"] for i in s["items"]} == {"bai-1"}
    assert s["subject"] == f"c:{KID}"

    client.put(f"/api/enrollments/{KID}/progress", json={"lesson_id": "bai-2"})
    by = client.get(f"{P}/home").json()["by_course"][0]
    assert by["lessons_range"] == "Bài 1–2" and by["items"] == 8
    assert len(start(client, source=f"course:{KID}")["items"]) == 5


# ---------------------------------------------------------------- 6. home payload and the bank
def test_home_payload_for_a_g10_12_student(client, gw, student, store):
    enroll(client, "dev-sample-dien-truong", "bai-4-dien-truong-deu")
    home = client.get(f"{P}/home").json()
    assert set(home) == {"quick", "mocks", "by_course"}
    quick = home["quick"]
    assert quick["count"] == 4 and quick["minutes"] == 5 and quick["from"] == [
        {"course_id": "dev-sample-dien-truong", "label": "Điện trường (bản mẫu dev)", "n": 4}]  # fewer than 10 items exist: never padded
    assert [m["profile_id"] for m in home["mocks"]] == ["math.mcq.t", "math.parts.t"]
    mcq = home["mocks"][0]
    assert mcq["title"] == "Thi thử trắc nghiệm" and mcq["minutes"] == 10 and mcq["items"] == 9 and mcq["last_score"] is None
    assert home["by_course"][0]["lessons_range"] == "Bài 1–2" and home["by_course"][0]["items"] == 4

    # a mock started from its card (mock:<profile>) stays bank based and timed; its score shows up as last_score
    m = start(client, source="mock:math.mcq.t", seed=2)
    assert m["kind"] == "mock" and m["profile_id"] == "math.mcq.t" and m["deadline"] and len(m["items"]) == 9
    assert client.post(f"{P}/sessions/{m['id']}/finish").status_code == 200
    assert client.get(f"{P}/home").json()["mocks"][0]["last_score"] == 0.0
    assert client.get(f"{P}/sessions/active").json() is None


def test_quick_session_brings_back_wrong_items_and_the_bank_fills_weak_skills(client, gw, student, store, clock):
    enroll(client, "dev-sample-dien-truong", "bai-4-dien-truong-deu")
    s = start(client, source="quick", seed=3)
    sid = s["id"]
    wrong_ids = []
    for pos, item in enumerate(s["items"]):
        good = right_answer(gw, sid, pos)
        bad = (next(o["id"] for o in item["options"] if o["id"] != good) if item["type"] == "SINGLE_CHOICE"
               else "FFFF" if item["type"] == "TRUE_FALSE_GROUP" else "1")
        client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": bad if pos < 2 else good, "time_spent_sec": 8})
        if pos < 2:
            wrong_ids.append(item["id"])
    report = client.post(f"{P}/sessions/{sid}/finish").json()
    assert report["correct"] == 2 and report["total"] == 4 and report["per_topic"]

    # the planner sees the answers as quiz_answer events with the lesson quiz's own ids (FSRS due items)
    now = clock()
    evs = [e for e in planner_events.load(gw.db, student["user_id"], now) if e["kind"] == "quiz_answer"]
    assert {(e["data"]["item"], e["data"]["course_id"]) for e in evs} == {(i.split(":", 1)[1], "dev-sample-dien-truong") for i in
                                                                          [x["id"] for x in s["items"]]}
    assert not any(e["data"]["item"].startswith("p:") for e in evs)

    clock.advance(days=2)  # the two wrong ones are due now
    plan = gw.practice._plan_mixed(student["user_id"], "quick", 7, "g10_12")
    reasons = {sel.item.id: sel.reasons for sel in plan.assembly.items}
    for wid in wrong_ids:
        assert "PREVIOUSLY_WRONG" in reasons[wid] and "DUE_REVIEW" in reasons[wid]
    # the weak skills' mastery came from the answers (independent evidence, BKT)
    sig = gw.practice.signals(student["user_id"], {"vat-li"})
    assert any(st.mastery_attempts for st in sig.states["vat-li"].values())


def test_result_lines_takeaway_and_redo(gw):
    take = gw.practice.takeaway
    assert take([]) is None
    assert take([(True, "A")] * 3)["line_vi"].startswith("Em làm đúng hết")
    assert "Hàm số" in take([(True, "Tích phân")] * 9 + [(False, "Hàm số")])["line_vi"]
    assert "Hàm số" in take([(False, "Hàm số"), (True, "Tích phân")])["line_vi"]

    # the redo line comes from the next `review` item of the planner's stored plan (nothing is generated here)
    day = gw.practice.clock().astimezone(__import__("zoneinfo").ZoneInfo("Asia/Ho_Chi_Minh")).date()
    plan = {"items": [{"kind": "lesson", "date": day.isoformat(), "start": "09:00"},
                      {"kind": "review", "date": (day + timedelta(days=1)).isoformat(), "start": "19:30"}]}
    gw.practice.planner = SimpleNamespace(_record=lambda uid: SimpleNamespace(plan=plan))
    line = gw.practice.redo_line("u", 2)
    assert line["line_vi"] == "Mentor sẽ cho em làm lại 2 câu sai vào thứ Năm, giờ em hay học."  # 2026-10-29 is a Thursday
    assert gw.practice.redo_line("u", 0) is None
    gw.practice.planner = SimpleNamespace(_record=lambda uid: None)
    assert gw.practice.redo_line("u", 2) is None


def test_students_only_and_existing_start_still_validates(client, teacher):
    assert client.get(f"{P}/home").status_code == 403
    assert client.post(f"{P}/sessions", json={"source": "quick"}).status_code == 403


def test_bad_source_and_missing_kind(client, student):
    assert client.post(f"{P}/sessions", json={"source": "nonsense"}).json()["code"] == "bad_source"
    assert client.post(f"{P}/sessions", json={"source": "mock:nope"}).json()["code"] == "unknown_profile"
    assert client.post(f"{P}/sessions", json={"kind": "practice"}).json()["code"] == "bad_request"
