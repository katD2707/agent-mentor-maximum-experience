"""Grade filter: topics, practice, mock, diagnostic and recommendations follow the learner's grade (CONTRACTS 10.11)."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from practice_fixtures import TOPICS, build_content

from mentor_gateway.practice.grade import parse_grade

FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"
P = "/api/practice"
GRADES = {"math.exp-log": 10, "math.function": 11, "math.integral": 12}


@pytest.fixture(scope="session")
def grade_content(tmp_path_factory) -> Path:
    target = build_content(FIXTURE_CONTENT, tmp_path_factory.mktemp("grade-content") / "mentor-content")
    skills = [{"id": f"{t}.s{n}", "title": t, "grade": GRADES[t], "prerequisites": [], "topic": t}
              for t in TOPICS for n in (1, 2)]
    skills.append({"id": "math.function.s3", "title": "x", "grade": 12, "prerequisites": [], "topic": "math.function"})
    (target / "curricula" / "math.yaml").write_text(
        yaml.safe_dump({"subject": "math", "skills": skills}, allow_unicode=True), encoding="utf-8")
    return target


@pytest.fixture
def settings(settings, grade_content):
    return settings.model_copy(update={"content_dir": grade_content})


def set_profile(gw, uid, text):
    gw.mirror.commit_files(uid, {"me/profile.md": text.encode()}, author="mentor", message="profile")


def math_of(client):
    return client.get(f"{P}/subjects").json()[0]


@pytest.mark.parametrize("text,grade", [
    ("- Tên gọi Minh Anh, học lớp 11A2. (chat 1/10)\n- ôn kiến thức lớp 10", 11),
    ("Lớp: 12", 12), ("- lớp: 10", 10), ("<!-- ví dụ: Học lớp 10A1. -->\n- Hồ sơ", None),
    ("- Lớp 11 đang học lượng giác", None), ("", None), ("học lớp 7", None), (None, None)])
def test_parse_grade(text, grade):
    assert parse_grade(text) == grade


def test_unknown_grade_filters_nothing(client, gw, thpt_user):
    m = math_of(client)
    assert m["learner_grade"] is None and not any(t["above_grade"] for t in m["topics"])
    assert all(not p["above_grade"] and p["note"] is None for p in m["mock_profiles"])


def test_subjects_mark_above_grade_topics_and_mocks(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "- Tên gọi An, học lớp 11A2.\n")
    m = math_of(client)
    assert m["learner_grade"] == 11
    by = {t["id"]: t for t in m["topics"]}
    assert (by["math.exp-log"]["grade"], by["math.exp-log"]["above_grade"]) == (10, False)
    assert (by["math.function"]["grade"], by["math.function"]["above_grade"]) == (11, False)  # min over skills (11,12)
    assert (by["math.integral"]["grade"], by["math.integral"]["above_grade"]) == (12, True)
    assert m["mock_profiles"] and all(p["above_grade"] and "lớp 12" in p["note"] for p in m["mock_profiles"])
    set_profile(gw, thpt_user["user_id"], "Lớp: 12")
    assert not any(t["above_grade"] for t in math_of(client)["topics"])
    assert not any(p["above_grade"] for p in math_of(client)["mock_profiles"])


def test_practice_defaults_to_in_grade_topics_and_opt_in_adds_the_rest(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "Lớp: 11")
    body = {"subject": "math", "minutes": 45, "goal": "balanced", "seed": 3}
    pv = client.post(f"{P}/preview", json=body).json()
    assert {t["topic"] for t in pv["per_topic"]} <= {"math.exp-log", "math.function"}
    s = client.post(f"{P}/sessions", json={"kind": "practice", **body}).json()
    assert {i["topic"] for i in s["items"]} <= {"math.exp-log", "math.function"}
    r = client.post(f"{P}/preview", json={**body, "topics": ["math.integral"]})
    assert r.status_code == 422 and r.json()["code"] == "above_grade_topic" and r.json()["topics"] == ["math.integral"]
    pv2 = client.post(f"{P}/preview", json={**body, "include_above_grade": True}).json()
    assert "math.integral" in {t["topic"] for t in pv2["per_topic"]}
    pv3 = client.post(f"{P}/preview", json={**body, "topics": ["math.integral"], "include_above_grade": True})
    assert pv3.status_code == 200


def test_mock_above_grade_needs_opt_in(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "Lớp: 11")
    r = client.post(f"{P}/sessions", json={"kind": "mock", "subject": "math", "profile_id": "math.mcq.t"})
    assert r.status_code == 422 and r.json()["code"] == "above_grade" and "lớp 12" in r.json()["detail"]
    assert client.post(f"{P}/sessions", json={"kind": "mock", "subject": "math"}).json()["code"] == "unknown_profile"
    ok = client.post(f"{P}/sessions", json={"kind": "mock", "subject": "math", "profile_id": "math.mcq.t",
                                            "include_above_grade": True})
    assert ok.status_code == 200 and len(ok.json()["items"]) == 9


def test_diagnostic_covers_in_grade_topics_only(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "Lớp: 11")
    s = client.post(f"{P}/sessions", json={"kind": "diagnostic", "subject": "math"}).json()
    assert {i["topic"] for i in s["items"]} == {"math.exp-log", "math.function"}


def test_nothing_for_the_grade_gives_a_friendly_insufficient_content(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "Lớp: 10")  # every topic is made grade 11+ below
    gw.practice.bank.skills["math"] = {k: replace(v, grade=11) for k, v in gw.practice.bank.skills["math"].items()}
    for kind, extra in (("diagnostic", {}), ("practice", {"minutes": 20})):
        r = client.post(f"{P}/sessions", json={"kind": kind, "subject": "math", **extra})
        assert r.status_code == 422 and r.json()["code"] == "insufficient_content", r.text
        assert "lớp 10" in r.json()["detail"]


def test_recommendations_skip_above_grade_topics(client, gw, thpt_user):
    set_profile(gw, thpt_user["user_id"], "Lớp: 11")
    recs = client.get(f"{P}/recommendations", params={"subject": "math"}).json()
    for r in recs:
        assert "math.integral" not in r["action"]["params"].get("topics", [])
        assert r["action"]["kind"] != "mock"
