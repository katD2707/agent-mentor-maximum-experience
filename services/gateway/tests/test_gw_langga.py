"""Làng gà: taxonomy, XP ledger, village / market / chickens, XP of lessons and practice, study room, notes list, labels."""

from datetime import timedelta

import pytest
from gateway_fakes import login, set_band
from langga_fixtures import KID, content_with_papers, kid_store
from test_gw_practice_courses import enroll, right_answer, start, wrong_answer

from mentor_gateway.langga import subjects
from mentor_gateway.langga import xp as xpm

P = "/api/practice"


@pytest.fixture(scope="session")
def lg_content(tmp_path_factory):
    return content_with_papers(tmp_path_factory.mktemp("lg"))


@pytest.fixture
def settings(settings, lg_content):
    return settings.model_copy(update={"content_dir": lg_content})


@pytest.fixture
def store(client, tmp_path):
    s = kid_store(client.app.state.gw.clock, tmp_path / "courses")
    client.app.state.content.store = s
    client.app.state.chicken_resolver.clear()
    return s


# ---------------------------------------------------------------- taxonomy
def test_chicken_of_follows_the_subj2ga_table():
    c = subjects.chicken_of
    assert c("Toán", "g1_5") == "toan" and c("Tiếng Việt", "g1_5") == "van" and c("Tự nhiên và Xã hội", "g1_5") == "khoahoc"
    assert c("Lịch sử và Địa lí", "g6_9") == "su" and c("Địa lí", "g6_9") == "dia" and c("Đạo đức", "g1_5") == "cd"
    assert c("Giáo dục công dân", "g6_9") == "cd" and c("Giáo dục kinh tế và pháp luật", "g10_12") == "cd"
    assert c("IELTS", "g10_12") == "anh" and c("English", "g6_9") == "anh" and c("Coding", "g1_5") == "tin"
    # physics, chemistry, biology: their own chickens only in grades 10-12
    assert [c(s, "g10_12") for s in ("Vật lí", "Hóa học", "Sinh học")] == ["li", "hoa", "sinh"]
    assert [c(s, "g6_9") for s in ("Vật lí", "Hóa học", "Sinh học")] == ["khoahoc"] * 3
    assert c("Khoa học tự nhiên", "g6_9") == "khoahoc"
    # university
    assert c("Giải tích", "uni") == "toanhoc" and c("Xác suất thống kê", "uni") == "khdl" and c("Cơ sở dữ liệu", "uni") == "httt"
    assert c("Hệ điều hành", "uni") == "ktmt" and c("Academic Writing", "uni") == "nna" and c("Hóa học", "uni") == "hoahoc"
    # unknown: kn (school) / daicuong (uni); a teacher label wins when it belongs to the band
    assert c("Làm vườn", "g6_9") == "kn" and c("Làm vườn", "uni") == "daicuong"
    assert c("Toán", "g6_9", explicit="kn") == "kn" and c("Toán", "g6_9", explicit="khmt") == "toan"
    assert len(subjects.LOW) == 11 and len(subjects.HIGH) == 13 and len(subjects.UNI) == 11
    assert subjects.CHICKENS["nt"].art == "nghethuat" and subjects.CHICKENS["toanhoc"].art == "toan"
    assert subjects.CHICKENS["toan"].name_vi == "Gà Toán" and subjects.CHICKENS["toan"].name_en == "Math chicken"


def test_catalog_entries_carry_a_chicken_and_the_query_has_a_facet(client, student, store):
    cat = client.get("/api/catalog?all=1").json()["courses"]
    assert cat and all(e["chicken"] for e in cat)
    kid = next(e for e in cat if e["id"] == KID)
    assert kid["chicken"] == "toan"
    r = client.get("/api/catalog/query", params={"chicken": "toan", "band": "g1_5"}).json()
    assert KID in {i["id"] for i in r["items"]} and all(i["chicken"] == "toan" for i in r["items"])
    assert any(f["v"] == "toan" for f in r["facets"]["chicken"])


# ---------------------------------------------------------------- xp ledger
def test_levels_and_stages():
    assert xpm.level_of(0) == 1 and xpm.level_of(99) == 1 and xpm.level_of(100) == 2 and xpm.level_of(250) == 3
    assert xpm.level_info(78) == {"level": 1, "xp": 78, "xp_in_level": 78, "stage": 1}
    assert [xpm.stage_of_level(n) for n in (1, 2, 4, 5, 9, 10, 25)] == [1, 2, 2, 3, 3, 4, 4]


def test_awards_are_idempotent_and_report_level_ups(gw, student):
    uid = student["user_id"]
    got = gw.xp.award(uid, "toan", "mock_submit", "s1")
    assert got == [{"chicken": "toan", "source": "mock_submit", "amount": 40, "level_up": False}]
    assert gw.xp.award(uid, "toan", "mock_submit", "s1") == []  # same (source, ref): nothing
    assert gw.xp.award(uid, "toan", "mock_submit", "s2")[0]["amount"] == 40
    up = gw.xp.award(uid, "toan", "boss_beaten", "paper-a")  # 80 + 50 = 130: level 2
    assert up[0]["level_up"] is True and gw.xp.total(uid, "toan") == 130
    both = gw.xp.award_many(uid, [("toan", "practice_right", "c:a", 2), ("toan", "practice_right", "c:b", 2), ("van", "practice_right", "c:c", 2)])
    assert sorted((r["chicken"], r["amount"]) for r in both) == [("toan", 4), ("van", 2)]


# ---------------------------------------------------------------- village, market, chickens
def test_market_take_let_go_and_restore(client, student):
    m = client.get("/api/market").json()
    assert m["stage"] == "g10_12" and [c["id"] for c in m["chickens"]] == list(subjects.HIGH)
    assert all(c["owned"] is False and c["art"] for c in m["chickens"])
    assert client.get("/api/village").json()["chickens"] == []  # no chickens yet: the app sends the student to choose

    r = client.post("/api/chickens", json={"chicken": "toan"})
    assert r.status_code == 201 and r.json()["id"] == "toan" and r.json()["level"] == 1 and r.json()["taken_at"]
    assert client.post("/api/chickens", json={"chicken": "toan"}).json() == {"error": "already_owned"}
    bad = client.post("/api/chickens", json={"chicken": "khmt"})  # a university chicken
    assert bad.status_code == 400 and bad.json() == {"error": "not_in_stage"}
    assert next(c for c in client.get("/api/market").json()["chickens"] if c["id"] == "toan")["owned"] is True

    uid = student["user_id"]
    client.app.state.gw.xp.award(uid, "toan", "mock_submit", "x")
    assert client.delete("/api/chickens/toan").status_code == 204
    assert client.delete("/api/chickens/toan").status_code == 404
    assert client.get("/api/village").json()["chickens"] == []
    assert client.post("/api/chickens", json={"chicken": "toan"}).json()["xp"] == 40  # XP kept in the ledger


def test_village_migrates_enrollments_once_and_speaks(client, student, store):
    set_band(client, "g1_5")
    enroll(client, KID, "bai-1")
    v = client.get("/api/village").json()
    assert [c["id"] for c in v["chickens"]] == ["toan"]
    toan = v["chickens"][0]
    assert toan["courses"] == 1 and toan["active_course"]["id"] == KID and toan["stage"] == 1
    assert v["speaker"]["chicken"] == "toan" and v["speaker"]["action"]["deep_link"].startswith("/")
    assert set(v["streak"]) == {"days", "today_done"} and set(v["week"]) == {"done", "planned"}
    client.delete("/api/chickens/toan")  # letting it go is not undone by the next visit
    assert client.get("/api/village").json()["chickens"] == []


def test_chicken_page(client, gw, student, store):
    set_band(client, "g1_5")
    enroll(client, KID, "bai-1")
    client.post("/api/chickens", json={"chicken": "toan"})
    gw.xp.award(student["user_id"], "toan", "mock_submit", "m")
    page = client.get("/api/chickens/toan").json()
    assert page["chicken"]["xp"] == 40 and page["courses"][0]["course_id"] == KID
    assert page["courses"][0]["last_lesson_title"] and len(page["week_xp"]) == 7 and page["week_xp"][-1] == 40
    assert page["suggested"] == [] or all(s["chicken"] == "toan" and s["id"] != KID for s in page["suggested"])
    assert any(t["profile_or_mock"] == f"course-mock:{KID}" and t["items"] == 8 and t["minutes"] == 16 and t["last_score"] is None
               for t in page["tests"])
    assert client.get("/api/chickens/li").status_code == 404  # not a chicken of the g1_5 stage


def test_chicken_page_lists_only_courses_for_the_students_stage(client, student, store):
    set_band(client, "uni")
    enroll(client, KID, "bai-1")  # a grade 1 course on a university account (an old enrollment or an old link)
    client.post("/api/chickens", json={"chicken": "toanhoc"})
    page = client.get("/api/chickens/toanhoc").json()
    assert page["courses"] == [] and page["chicken"]["courses"] == 0 and page["tests"] == []
    set_band(client, "g1_5")  # its own stage: it stays
    client.post("/api/chickens", json={"chicken": "toan"})
    assert [c["course_id"] for c in client.get("/api/chickens/toan").json()["courses"]] == [KID]


def test_xp_week(client, gw, student):
    uid = student["user_id"]
    gw.xp.award(uid, "toan", "practice_right", "a:1")
    gw.xp.award(uid, "toan", "mock_submit", "m")
    w = client.get("/api/xp/week").json()
    toan = next(c for c in w["chickens"] if c["chicken"] == "toan")
    assert toan["week_total"] == 42 and toan["week"][-1] == 42 and toan["by_source"] == {"practice_right": 2, "mock_submit": 40}
    assert len(w["days"]) == 7 and w["total"] == 42


# ---------------------------------------------------------------- XP of lessons
def test_progress_put_pays_lesson_done_and_a_perfect_bonus_once(client, student, store):
    set_band(client, "g1_5")
    enroll(client, KID)
    url = f"/api/enrollments/{KID}/progress"
    assert client.put(url, json={"lesson_id": "bai-1", "completed_block_ids": ["t1"]}).json()["xp"] == []  # a block pays nothing
    for i in range(1, 5):  # lesson 1: every quiz item right on the first try
        r = client.put(url, json={"quiz": {"item_id": f"l1-q{i}", "correct": True}}).json()
        assert r["xp"] == []  # a right answer in a lesson pays nothing by itself
    done = client.put(url, json={"completed_block_ids": ["t1", "quiz1"]}).json()
    assert done["xp"] == [{"chicken": "toan", "source": "lesson_done", "amount": 20, "level_up": False},
                          {"chicken": "toan", "source": "lesson_perfect", "amount": 5, "level_up": False}]
    assert client.put(url, json={"completed_block_ids": ["t1", "quiz1"]}).json()["xp"] == []  # once only
    # lesson 2: one item wrong first, then right: done, but not perfect
    for i, ok in ((1, False), (1, True), (2, True), (3, True), (4, True)):
        client.put(url, json={"quiz": {"item_id": f"l2-q{i}", "correct": ok}})
    r = client.put(url, json={"completed_block_ids": ["t2", "quiz2"]}).json()
    assert r["xp"] == [{"chicken": "toan", "source": "lesson_done", "amount": 20, "level_up": False}]


# ---------------------------------------------------------------- XP of practice
def test_practice_answers_and_fixes_pay_xp(client, gw, student, store):
    set_band(client, "g1_5")
    enroll(client, KID, "bai-2")
    s = start(client, source=f"course:{KID}")
    sid, items = s["id"], s["items"]
    gained, wrong_item = 0, None
    for it in items:
        pos = it["position"]
        if pos == 0:
            r = client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": wrong_answer(it)}).json()
            assert r["correct"] is False and r["xp"] == []
            wrong_item = it["id"]
        else:
            r = client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": right_answer(gw, sid, pos)}).json()
            assert r["xp"] == [{"chicken": "toan", "source": "practice_right", "amount": 2, "level_up": False}]
            gained += 2
            again = client.post(f"{P}/sessions/{sid}/answer", json={"position": pos, "answer": right_answer(gw, sid, pos)}).json()
            assert again["xp"] == []
    report = client.post(f"{P}/sessions/{sid}/finish").json()
    assert "boss" not in report
    assert gw.xp.total(student["user_id"], "toan") == gained
    fixed = client.post(f"{P}/sessions/{sid}/fix", json={"item_id": wrong_item, "answer": right_answer(gw, sid, 0)}).json()
    assert fixed["correct"] is True and fixed["xp"][0]["source"] == "fix_right" and fixed["xp"][0]["amount"] == 3
    assert gw.xp.total(student["user_id"], "toan") == gained + 3


# ---------------------------------------------------------------- study room
def test_focus_pays_a_point_a_minute_a_bonus_for_the_full_session_and_stops_at_120_a_day(client, gw, clock, student):
    assert client.get("/api/focus/active").json() is None
    r = client.post("/api/focus", json={"minutes": 20, "chicken": "toan"}).json()
    assert r["id"].startswith("f-") and r["ends_at"]
    assert client.post("/api/focus", json={"minutes": 3, "chicken": "toan"}).status_code == 422
    assert client.post("/api/focus", json={"minutes": 20, "chicken": "khmt"}).json() == {"error": "not_in_stage"}
    r = client.post("/api/focus", json={"minutes": 20, "chicken": "toan"}).json()  # replaces the first, never finished
    act = client.get("/api/focus/active").json()
    assert act["id"] == r["id"] and act["remaining_sec"] == 1200
    clock.advance(minutes=20)
    done = client.post(f"/api/focus/{r['id']}/finish", json={"minutes_done": 20}).json()
    assert done["xp"] == [{"chicken": "toan", "source": "focus", "amount": 20, "level_up": False},
                          {"chicken": "toan", "source": "focus_full", "amount": 5, "level_up": False}]
    assert done["chicken"]["xp"] == 25 and done["gained"] == 25
    assert client.post(f"/api/focus/{r['id']}/finish", json={"minutes_done": 20}).json()["xp"] == []  # replay: no second award
    assert client.get("/api/focus/active").json() is None
    # the server trusts the clock, not the client: 90 minutes claimed after 5 real ones pays for 6 (5 + 1 slack), no full bonus
    r2 = client.post("/api/focus", json={"minutes": 120, "chicken": "toan"}).json()
    clock.advance(minutes=5)
    out = client.post(f"/api/focus/{r2['id']}/finish", json={"minutes_done": 90}).json()
    assert out["gained"] == 6 and [x["source"] for x in out["xp"]] == ["focus"]
    # the quiet daily cap: 31 so far; a long session adds at most 89 more (and no bonus once the cap is reached)
    r3 = client.post("/api/focus", json={"minutes": 120, "chicken": "toan"}).json()
    clock.advance(minutes=119)
    last = client.post(f"/api/focus/{r3['id']}/finish", json={"minutes_done": 120}).json()
    assert last["gained"] == 89 and gw.xp.sum_on_day(student["user_id"], xpm.FOCUS_SOURCES, gw.xp.today()) == xpm.FOCUS_DAILY_CAP
    r4 = client.post("/api/focus", json={"minutes": 30, "chicken": "toan"}).json()
    clock.advance(minutes=30)
    assert client.post(f"/api/focus/{r4['id']}/finish", json={"minutes_done": 30}).json()["xp"] == []
    # behaviour events were recorded for the planner
    from mentor_gateway.planner import events as ev

    kinds = [e["kind"] for e in ev.stored(gw.db, student["user_id"], clock() - timedelta(days=1))]
    assert kinds.count("session_start") >= 4 and kinds.count("session_end") >= 4


def test_focus_pause_stops_the_clock_on_the_server(client, gw, clock, student):
    r = client.post("/api/focus", json={"minutes": 25, "chicken": "toan"}).json()
    clock.advance(minutes=5)
    p = client.post(f"/api/focus/{r['id']}/pause", json={}).json()
    assert p["status"] == "paused" and p["remaining_sec"] == 20 * 60
    clock.advance(minutes=60)  # an hour away: nothing counts, and a reload still shows the pause
    act = client.get("/api/focus/active").json()
    assert act["status"] == "paused" and act["remaining_sec"] == 20 * 60 and act["paused_at"]
    assert client.post(f"/api/focus/{r['id']}/pause", json={}).json()["remaining_sec"] == 20 * 60  # idempotent
    back = client.post(f"/api/focus/{r['id']}/resume").json()
    assert back["status"] == "active" and back["remaining_sec"] == 20 * 60
    assert client.post(f"/api/focus/{r['id']}/resume").json()["remaining_sec"] == 20 * 60
    clock.advance(minutes=20)
    done = client.post(f"/api/focus/{r['id']}/finish", json={"minutes_done": 25}).json()
    assert done["minutes_done"] == 25 and done["gained"] == 30  # the paused hour did not make it longer, nor shorter
    # stopping while paused ends where the clock stands; hidden time can be dated back
    r2 = client.post("/api/focus", json={"minutes": 45, "chicken": "toan"}).json()
    clock.advance(minutes=50)
    assert client.post(f"/api/focus/{r2['id']}/pause", json={"ago_sec": 40 * 60}).json()["remaining_sec"] == 35 * 60
    clock.advance(minutes=30)
    out = client.post(f"/api/focus/{r2['id']}/finish", json={"minutes_done": 45}).json()
    assert out["minutes_done"] == 11 and out["gained"] == 11  # 10 minutes seen + 1 slack, no full bonus
    assert client.post(f"/api/focus/{r2['id']}/pause", json={}).status_code == 409
    assert client.post("/api/focus/f-nope/pause", json={}).status_code == 404


# ---------------------------------------------------------------- avatar, notes list
def test_avatar_patch(client, student):
    assert client.get("/api/me").json()["avatar"] is None
    r = client.patch("/api/me", json={"avatar": "nu"})
    assert r.status_code == 200 and r.json()["avatar"] == "nu"
    assert client.patch("/api/me", json={"avatar": "robot"}).status_code == 422


def test_notes_list(client, gw, clock, student):
    from mentor_gateway.ask.tables import NotesSet
    from mentor_gateway.planner.tables import Reminder

    assert client.get("/api/ask/notes").json() == []
    now = clock()
    with gw.db.session() as s:
        s.add(NotesSet(id="n-abc", user_id=student["user_id"], title="Điện trường", subject="Lí", pages=2,
                       items=[{"id": "n1"}] * 4, created_at=now))
        s.add(Reminder(id="r-1", user_id=student["user_id"], at=now + timedelta(days=1), kind="later", text_vi="a", text_en="a",
                       deep_link="/luyen-tap?notes=n-abc", status="scheduled", created_at=now, updated_at=now))
    rows = client.get("/api/ask/notes").json()
    assert len(rows) == 1 and rows[0]["notes_id"] == "n-abc" and rows[0]["items"] == 4 and rows[0]["pages"] == 2
    assert rows[0]["next_review_at"].startswith((now + timedelta(days=1)).strftime("%Y-%m-%d"))
    login(client, "giaovien", "123456", "teacher")
    assert client.get("/api/ask/notes").status_code == 403


def test_forget_removes_every_langga_row(client, gw, student):
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    from mentor_gateway.langga.tables import ChatTurn, FocusSession, LanggaState, UserChicken, XpEvent

    uid, other = student["user_id"], "someone-else"
    now = datetime.now(UTC)
    with gw.db.session() as s:
        for u in (uid, other):
            s.add(UserChicken(user_id=u, chicken="toan", taken_at=now))
            s.add(LanggaState(user_id=u, migrated_at=now))
            s.add(FocusSession(id=f"f-{u[:10]}", user_id=u, chicken="toan", minutes=10, started_at=now, ends_at=now))
            s.add(ChatTurn(user_id=u, chicken="toan", role="user", text="hi", created_at=now))
    gw.xp.award(uid, "toan", "lesson", "x1", 5)
    gw.xp.award(other, "toan", "lesson", "x1", 5)
    with gw.db.session() as s:
        gw.xp.forget(s, uid)
    with gw.db.session() as s:
        for model in (XpEvent, UserChicken, LanggaState, FocusSession, ChatTurn):
            assert s.scalar(select(func.count()).select_from(model).where(model.user_id == uid)) == 0, model
            assert s.scalar(select(func.count()).select_from(model).where(model.user_id == other)) == 1, model


def test_course_level_practice_pays_xp_once(client, gw, student, store):
    """The ladder inside a course's Thi thu (`course:<id>` + level) pays practice_right like any practice, idempotently."""
    set_band(client, "g1_5")
    enroll(client, KID, "bai-2")
    s = start(client, source=f"course:{KID}", level=1)
    sid, it = s["id"], s["items"][0]
    ans = {"position": it["position"], "answer": right_answer(gw, sid, it["position"])}
    r = client.post(f"{P}/sessions/{sid}/answer", json=ans).json()
    assert r["xp"] == [{"chicken": "toan", "source": "practice_right", "amount": 2, "level_up": False}]
    assert client.post(f"{P}/sessions/{sid}/answer", json=ans).json()["xp"] == []
    assert gw.xp.total(student["user_id"], "toan") == 2
