"""Course mock exams (`course-mock:<id>`) and Arena papers (`paper:<id>`): sizes, timing, scoring, boss report, XP."""

import json

import pytest
from gateway_fakes import set_band
from langga_fixtures import KID, content_with_papers, kid_store
from test_gw_practice_courses import enroll, right_answer, start

from mentor_gateway.langga import papers as papers_mod

P = "/api/practice"


@pytest.fixture(scope="session")
def lg_content(tmp_path_factory):
    return content_with_papers(tmp_path_factory.mktemp("lgx"))


@pytest.fixture
def settings(settings, lg_content):
    return settings.model_copy(update={"content_dir": lg_content})


@pytest.fixture
def store(client, tmp_path):
    s = kid_store(client.app.state.gw.clock, tmp_path / "courses")
    client.app.state.content.store = s
    client.app.state.chicken_resolver.clear()
    return s


def finish_all_right(client, gw, sid, n):
    for pos in range(n):
        got = client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": right_answer(gw, sid, pos)}).json()
        assert got == {"saved": True}
    return client.post(f"{P}/sessions/{sid}/finish").json()


# ---------------------------------------------------------------- course mock
def test_course_mock_runs_like_a_mock_exam(client, gw, clock, student, store):
    set_band(client, "g1_5")
    assert client.post(f"{P}/sessions", json={"source": f"course-mock:{KID}"}).json()["code"] == "course_not_found"
    enroll(client, KID)
    s = start(client, source=f"course-mock:{KID}")
    assert s["kind"] == "mock" and s["source"] == f"course-mock:{KID}" and len(s["items"]) == 8  # all items: fewer than 22
    assert s["remaining_sec"] == 16 * 60 and s["deadline"] and {i["level"] for i in s["items"]} >= {1, 2}
    assert all("answer_key" not in i for i in s["items"])
    sid = s["id"]
    assert client.post(f"{P}/sessions", json={"source": f"course-mock:{KID}"}).json()["code"] == "active_session"
    assert client.post(f"{P}/sessions/{sid}/flag", json={"position": 1, "flagged": True}).json() == {"ok": True}
    for pos in range(6):  # six of eight answered, all right
        client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": right_answer(gw, sid, pos)})
    r = client.post(f"{P}/sessions/{sid}/finish").json()
    assert r["score_10"] == 7.5 and r["correct"] == 6 and r["total"] == 8
    assert r["xp"] == [{"chicken": "toan", "source": "mock_submit", "amount": 40, "level_up": False}]
    assert client.post(f"{P}/sessions/{sid}/finish").json() == r  # idempotent, XP not paid twice
    assert gw.xp.total(student["user_id"], "toan") == 40


def test_course_mock_auto_finishes_at_the_deadline(client, gw, clock, student, store):
    set_band(client, "g1_5")
    enroll(client, KID)
    sid = start(client, source=f"course-mock:{KID}")["id"]
    client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": right_answer(gw, sid, 0)})
    clock.advance(minutes=17)
    assert client.get(f"{P}/sessions/{sid}").json()["status"] == "expired"
    rep = client.post(f"{P}/sessions/{sid}/finish").json()
    assert rep["answered"] == 1 and rep["xp"][0]["source"] == "mock_submit"


def test_course_mock_needs_enough_items(client, student, store):
    enroll(client, "dev-sample-dien-truong")  # 4 quiz items
    r = client.post(f"{P}/sessions", json={"source": "course-mock:dev-sample-dien-truong"})
    assert r.status_code == 422 and r.json()["code"] == "insufficient_content" and r.json()["required"] == 6


# ---------------------------------------------------------------- papers: files
def test_placeholder_papers_have_the_right_structures(lg_content):
    papers, errors = papers_mod.validate_dir(lg_content / "papers")
    assert errors == [] and set(papers) == {"thpt-toan-2025-mau", "dgnl-toan-mau", "thpt-ly-2025-mau", "thpt-anh-2025-mau",
                                            "cuoi-ky-xstk-mau"}
    assert all(p.placeholder for p in papers.values())
    toan = papers["thpt-toan-2025-mau"]
    assert [(p.type, len(p.items)) for p in toan.parts] == [("SINGLE_CHOICE", 12), ("TRUE_FALSE_GROUP", 4), ("SHORT_ANSWER", 6)]
    assert toan.minutes == 90 and sum(toan.points_of(p) * len(p.items) for p in toan.parts) == 10.0
    ly = papers["thpt-ly-2025-mau"]
    assert ly.minutes == 50 and len(ly.parts[0].items) == 18 and "rút gọn" in ly.title_vi
    anh = papers["thpt-anh-2025-mau"]
    assert anh.minutes == 50 and anh.item_count == 40
    assert papers["cuoi-ky-xstk-mau"].band == "uni" and papers["cuoi-ky-xstk-mau"].chicken == "khdl"


def test_validator_names_the_problems(tmp_path, lg_content, capsys):
    d = tmp_path / "in"
    d.mkdir()
    good = json.loads((lg_content / "papers" / "thpt-anh-2025-mau.json").read_text(encoding="utf-8"))
    (d / "thpt-anh-2025-mau.json").write_text(json.dumps(good), encoding="utf-8")
    assert papers_mod.main(["validate", str(d)]) == 0
    (d / "wrong-chicken.json").write_text(json.dumps({**good, "id": "wrong-chicken", "chicken": "khmt"}), encoding="utf-8")
    bad_item = {**good["parts"][0]["items"][0], "answer_key": {"correct_option_id": "Z"}}
    (d / "bad-key.json").write_text(json.dumps({**good, "id": "bad-key", "parts": [{**good["parts"][0], "items": [bad_item]}]}),
                                    encoding="utf-8")
    (d / "broken.json").write_text("{nope", encoding="utf-8")
    (d / "named-wrong.json").write_text(json.dumps({**good, "id": "other-id"}), encoding="utf-8")
    assert papers_mod.main(["validate", str(d)]) == 1
    err = capsys.readouterr().err
    for needle in ("wrong-chicken.json", "not a chicken of band", "bad-key.json", "broken.json", "named-wrong.json"):
        assert needle in err
    content = tmp_path / "content"
    assert papers_mod.main(["import", str(d), "--content-dir", str(content)]) == 1 and not (content / "papers").exists()
    for f in ("wrong-chicken", "bad-key", "broken", "named-wrong"):
        (d / f"{f}.json").unlink()
    assert papers_mod.main(["import", str(d), "--content-dir", str(content)]) == 0
    assert (content / "papers" / "thpt-anh-2025-mau.json").is_file()
    assert set(papers_mod.PaperStore(content).all()) == {"thpt-anh-2025-mau"}


# ---------------------------------------------------------------- papers: arena and the boss
def test_arena_list_is_filtered_by_band(client, student):
    rows = client.get("/api/arena/papers").json()
    assert {r["id"] for r in rows} == {"thpt-toan-2025-mau", "dgnl-toan-mau", "thpt-ly-2025-mau", "thpt-anh-2025-mau"}
    toan = next(r for r in rows if r["id"] == "thpt-toan-2025-mau")
    assert toan["items"] == 22 and toan["minutes"] == 90 and toan["placeholder"] is True and toan["best_score"] is None
    assert toan["boss"]["name_vi"] == "Quái Sai Số" and toan["beaten"] is False and toan["chicken"] == "toan"
    assert next(r for r in rows if r["id"] == "thpt-anh-2025-mau")["boss"]["name_vi"] == "Quái Lỗi Ngữ Pháp"
    assert next(r for r in rows if r["id"] == "thpt-ly-2025-mau")["boss"]["name_vi"] == "Quái Sai Số"  # closest boss
    assert [r["id"] for r in client.get("/api/arena/papers", params={"chicken": "anh"}).json()] == ["thpt-anh-2025-mau"]
    assert client.get("/api/arena/papers", params={"year": 2030}).json() == []
    set_band(client, "uni")
    assert [r["id"] for r in client.get("/api/arena/papers").json()] == ["cuoi-ky-xstk-mau"]
    set_band(client, "g6_9")
    assert client.get("/api/arena/papers").json() == []
    assert client.post(f"{P}/sessions", json={"source": "paper:thpt-toan-2025-mau"}).json()["code"] == "band_mismatch"


def test_paper_session_boss_report_and_xp(client, gw, clock, student):
    assert client.post(f"{P}/sessions", json={"source": "paper:nope"}).json()["code"] == "unknown_paper"
    s = start(client, source="paper:thpt-toan-2025-mau")
    sid = s["id"]
    assert s["kind"] == "mock" and len(s["items"]) == 22 and s["remaining_sec"] == 90 * 60
    assert [len(p["positions"]) for p in s["parts"]] == [12, 4, 6] and [p["points_each"] for p in s["parts"]] == [0.25, 1.0, 0.5]
    assert s["paper"]["boss"]["name_vi"] == "Quái Sai Số" and s["paper"]["placeholder"] is True
    assert not any("truth" in st for i in s["items"] for st in i.get("statements", []))
    r = finish_all_right(client, gw, sid, 22)
    assert r["score_10"] == 10.0 and r["correct"] == 22
    assert r["boss"]["name"] == "Quái Sai Số" and r["boss"]["hp"] == 22 and r["boss"]["damage"] == 22 and r["boss"]["beaten"] is True
    assert {x["source"]: x["amount"] for x in r["xp"]} == {"paper_submit": 40, "boss_beaten": 50}
    assert [p["correct"] for p in r["per_part"]] == [12, 4, 6]
    assert client.post(f"{P}/sessions/{sid}/finish").json() == r
    paper = next(p for p in client.get("/api/arena/papers").json() if p["id"] == "thpt-toan-2025-mau")
    assert paper["best_score"] == 10.0 and paper["beaten"] is True
    # a second go the same day pays nothing more; the next day the submit pays again, the boss only the first time
    s2 = start(client, source="paper:thpt-toan-2025-mau")
    r2 = finish_all_right(client, gw, s2["id"], 22)
    assert r2["xp"] == [] and r2["boss"]["beaten"] is True
    clock.advance(days=1)
    s3 = start(client, source="paper:thpt-toan-2025-mau")
    r3 = finish_all_right(client, gw, s3["id"], 22)
    assert [x["source"] for x in r3["xp"]] == ["paper_submit"]
    assert gw.xp.total(student["user_id"], "toan") == 40 + 50 + 40


def test_paper_submit_needs_half_the_paper_answered(client, gw, clock, student):
    sid = start(client, source="paper:thpt-toan-2025-mau")["id"]
    client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": right_answer(gw, sid, 0)})
    r = client.post(f"{P}/sessions/{sid}/finish").json()
    assert r["xp"] == [] and r["answered"] == 1
    assert gw.xp.total(student["user_id"], "toan") == 0
    assert all(t["label"] != "Vững" for t in r["per_topic"])


def test_paper_auto_submits_and_a_low_score_leaves_the_boss_standing(client, gw, clock, student):
    sid = start(client, source="paper:thpt-anh-2025-mau")["id"]
    client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": right_answer(gw, sid, 0)})
    clock.advance(minutes=51)
    assert client.get(f"{P}/sessions/{sid}").json()["status"] == "expired"
    r = client.post(f"{P}/sessions/{sid}/finish").json()
    boss = r["boss"]
    assert boss["beaten"] is False and boss["damage"] == 1 and boss["hp"] == 40 and boss["name"] == "Quái Lỗi Ngữ Pháp"
    assert r["xp"] == []  # one answer out of 40: no submit XP


def test_generic_research_keywords_are_not_used_to_match_papers():
    from mentor_gateway.research.profile_keys import specific_keywords, title_keywords
    from mentor_gateway.research.reading import ReadingMixin

    assert specific_keywords(["paper", "graph neural network", "Study"]) == ["graph neural network"]
    assert specific_keywords(["paper"]) == ["paper"]  # nothing else left: kept
    assert "paper" not in title_keywords("Paper recommendation with graph networks")
    f = {"title": "Paper Recommendation for Moebius Bands", "abstract": "x"}
    g = {"title": "Graph neural network potentials", "abstract": "formation energy"}
    assert ReadingMixin.fallback_reason(g, ["paper", "graph neural network"], "vi") == "Khớp từ khóa graph neural network."
    assert ReadingMixin.fallback_reason({"title": "Nanopaper tests", "abstract": ""}, ["paper"], "vi").startswith("Bạn đã thêm")
