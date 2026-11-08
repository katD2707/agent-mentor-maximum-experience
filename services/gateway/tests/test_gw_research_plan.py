"""Nghiên cứu: deadlines, meetings, goal milestones, planner items and reminders, hub line, server-side events, scheduler.
Fakes only (no network, no model)."""

from datetime import UTC, datetime, timedelta

import pytest
from gateway_fakes import FrozenClock, new_student
from research_fakes import FakeArxiv, FakeLitClient, FakeLLM, FakeSearcher, arxiv_paper

from mentor_gateway.planner import events as ev
from mentor_gateway.planner.tables import PlanRecord, Reminder
from mentor_gateway.research import fulltext
from mentor_gateway.research.tables import MeetingRow


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 11, 7, 2, 0, tzinfo=UTC))  # Saturday 09:00 in Vietnam


@pytest.fixture
def svc(client):
    s = client.app.state.research
    s.arx = FakeArxiv()
    s.arxiv_search, s.lit_client, s.arxiv_searcher = s.arx.search, FakeLitClient(s.arx), FakeSearcher(s.arx)
    s.llm = None  # no model unless a test scripts one

    async def none(*a, **k):
        return []

    s.fetch_arxiv_feed = none
    return s


@pytest.fixture
def uni(client, svc):
    return new_student(client, "uni1", "uni")


def tick(client, svc, now) -> list[str]:
    async def go() -> list[str]:
        return await svc.tick(now, force=True)

    return client.portal.call(go)


def uid(client) -> str:
    return client.get("/api/me").json()["id"]


def deadline(client, text: str, **kw):
    r = client.post("/api/research/deadlines", json={"text": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ---- deadlines --------------------------------------------------------------------------------------------------------

def test_deadline_aoe_conversion_unconfirmed_and_errors(client, svc, uni):
    d = deadline(client, "nộp full paper 15/11, 23:59 AoE")
    assert d["id"] == "ms-1" and d["due_date"] == "2026-11-16" and d["due_time"] == "18:59"  # AoE is UTC-12: 23:59 on 15/11 = 18:59 on 16/11 in Vietnam
    assert d["original_text"] == "23:59 AoE 15/11" and d["confirmed"] is True and d["kind"] == "submission" and d["thesis"] is True
    assert d["days_left"] == 9 and d["done"] is False and d["planned_sessions"] == 0 and d["created_at"].startswith("2026-11-07T09:00:00")
    unclear = deadline(client, "báo cáo tiến độ cho khoa 1/12")  # a date and no time: "Chưa xác nhận"
    assert unclear["id"] == "ms-2" and unclear["confirmed"] is False and unclear["due_time"] is None and unclear["due_date"] == "2026-12-01"
    vague = deadline(client, "nộp báo cáo cuối tháng 12")
    assert vague["confirmed"] is False and vague["due_date"] == "2026-12-31"
    local = deadline(client, "hạn đăng ký 20/11 17:00")
    assert local["due_time"] == "17:00" and local["original_text"] is None and local["confirmed"] is True and local["kind"] == "other"
    assert [m["id"] for m in client.get("/api/research/deadlines").json()] == ["ms-1", "ms-4", "ms-2", "ms-3"]  # by date
    r = client.post("/api/research/deadlines", json={"text": "một ngày nào đó"})
    assert r.status_code == 422 and r.json() == {"error": "deadline_unparsed"}
    structured = client.post("/api/research/deadlines", json={"title": "Camera ready", "due_date": "2026-12-05", "due_time": "23:59", "tz": "AoE", "thesis": False})
    assert structured.status_code == 201 and structured.json()["due_date"] == "2026-12-06" and structured.json()["due_time"] == "18:59"
    assert structured.json()["thesis"] is False
    assert client.post("/api/research/deadlines", json={"text": "x", "title": "y", "due_date": "2026-12-05"}).status_code == 422
    fixed = client.patch("/api/research/deadlines/ms-2", json={"due_time": "09:00"})
    assert fixed.json()["confirmed"] is True and fixed.json()["due_time"] == "09:00"
    assert client.patch("/api/research/deadlines/ms-2", json={"done": True}).json()["done"] is True
    assert "ms-2" not in [m["id"] for m in client.get("/api/research/deadlines").json()]
    assert "ms-2" in [m["id"] for m in client.get("/api/research/deadlines", params={"include_done": "true"}).json()]
    assert client.patch("/api/research/deadlines/nope", json={"done": True}).json() == {"error": "deadline_not_found"}
    assert client.delete("/api/research/deadlines/ms-3").status_code == 204
    assert client.delete("/api/research/deadlines/ms-3").json() == {"error": "deadline_not_found"}


def test_deadline_model_names_it_and_reads_a_date_the_code_cannot(client, svc, uni):
    svc.llm = FakeLLM(deadline={"title": "Nộp bản thảo", "kind": "submission", "date": "2026-12-20", "time": "10:00", "tz": "UTC", "certain": True})
    d = deadline(client, "hạn chót là ngày hội nghị bế mạc")
    assert d["title"] == "Nộp bản thảo" and d["due_date"] == "2026-12-20" and d["due_time"] == "17:00" and d["kind"] == "submission"


# ---- goal milestones --------------------------------------------------------------------------------------------------

def test_research_goal_milestones_progress_and_removal(client, svc, uni):
    client.put("/api/research/profile", json={"title": "Học máy cho vật liệu", "question": "Q?", "keywords": ["a b"]})
    plain = deadline(client, "hạn đăng ký 20/11 17:00")  # not a thesis milestone: no goal is shown
    assert [g["id"] for g in client.get("/api/goals").json()] == []
    assert client.get("/api/research").json()["goal_id"] is None
    a = deadline(client, "nộp full paper 15/11, 23:59 AoE")
    b = client.post("/api/research/deadlines", json={"title": "Viết xong chương 3", "due_date": "2026-12-10", "thesis": True}).json()
    goals = client.get("/api/goals").json()
    g = next(x for x in goals if x["id"] == "res-thesis")
    assert g["source"] == "research" and g["title"] == "Học máy cho vật liệu" and g["kind"] == "student" and g["course_ids"] == []
    assert g["deadline"] == "2026-12-10"  # the last thesis milestone
    assert [m["id"] for m in g["milestones"]] == [a["id"], b["id"]] and g["progress_pct"] == 0.0
    assert all(x["source"] == "learning" and x["milestones"] == [] for x in goals if x["id"] != "res-thesis")
    assert client.get("/api/research").json()["goal_id"] == "res-thesis"
    client.patch(f"/api/research/deadlines/{a['id']}", json={"done": True})
    g = next(x for x in client.get("/api/goals").json() if x["id"] == "res-thesis")
    assert g["progress_pct"] == 50.0 and g["status"] in ("new", "on_track", "slightly_behind")
    client.patch(f"/api/research/deadlines/{b['id']}", json={"due_date": "2026-11-01"})  # open and overdue
    g = next(x for x in client.get("/api/goals").json() if x["id"] == "res-thesis")
    assert g["status"] == "behind"
    over = client.patch("/api/goals/res-thesis", json={"title": "other"})
    assert over.status_code == 200 and over.json()["title"] == "Học máy cho vật liệu"  # follows the profile, not editable here
    ov = client.get("/api/research").json()
    assert [m["id"] for m in ov["milestones"]] == [b["id"], a["id"]] and all(m["thesis"] for m in ov["milestones"])
    client.delete(f"/api/research/deadlines/{a['id']}")
    client.delete(f"/api/research/deadlines/{b['id']}")  # the last thesis milestone: the goal goes, the plain deadline stays
    assert "res-thesis" not in [x["id"] for x in client.get("/api/goals").json()]
    assert [m["id"] for m in client.get("/api/research/deadlines").json()] == [plain["id"]]
    client.delete(f"/api/research/deadlines/{plain['id']}")
    client.post("/api/research/deadlines", json={"title": "again", "due_date": "2026-12-10", "thesis": True})
    assert client.delete("/api/goals/res-thesis").status_code == 204  # leaves Tiến độ, the milestone stays as a deadline
    assert "res-thesis" not in [x["id"] for x in client.get("/api/goals").json()] and len(client.get("/api/research/deadlines").json()) == 1


# ---- meetings ---------------------------------------------------------------------------------------------------------

def test_meeting_title_rules_without_a_model():
    from mentor_gateway.research.meetings import meeting_title as t

    assert t("họp nhóm thứ Năm 15:00") == "Họp nhóm"
    assert t("họp lab thứ Sáu 9h") == "Họp lab"
    assert t("seminar thứ Ba 14:00") == "Seminar"
    assert t("gặp thầy Nam thứ Tư 10:00") == "Gặp thầy Nam"
    assert t("gặp cô Lan Anh chiều mai") == "Gặp cô Lan Anh"
    assert t("họp GVHD thứ Tư 11/11 14:00") == "Họp GVHD"
    assert t("gặp thầy hướng dẫn thứ Hai") == "Họp GVHD"
    assert t("lab meeting on Friday 3pm") == "Lab meeting"
    assert t("meeting with Prof Smith tomorrow") == "Meeting with Prof Smith"
    assert t("advisor meeting Monday") == "Họp GVHD"
    assert t("thứ Năm 15:00") == "Họp GVHD"


def test_meetings_agenda_notes_and_actions(client, svc, uni):
    m = client.post("/api/research/meetings", json={"text": "họp GVHD thứ Tư 11/11 14:00"})
    assert m.status_code == 201
    m = m.json()
    assert m["at"] == "2026-11-11T14:00:00+07:00" and m["title"] == "Họp GVHD" and m["status"] == "scheduled" and m["agenda"] is None
    assert client.post("/api/research/meetings", json={"text": "họp sớm nhé"}).json() == {"error": "meeting_unparsed"}
    assert client.post("/api/research/meetings", json={"text": "x", "at": "2026-11-12T09:00:00+07:00"}).status_code == 422
    other = client.post("/api/research/meetings", json={"at": "2026-12-01T09:30:00+07:00", "title": "Họp nhóm"}).json()
    assert [x["id"] for x in client.get("/api/research/meetings").json()] == [m["id"], other["id"]]  # soonest first
    assert client.get("/api/research/meetings/next").json()["id"] == m["id"]
    mid = m["id"]
    ag = client.put(f"/api/research/meetings/{mid}/agenda", json={"new_results": "Baseline 71%", "open_questions": "Có cần thêm seed?"}).json()["agenda"]
    assert ag["new_results"] == "Baseline 71%" and ag["promised"] == [] and ag["drafted_at"] is None and ag["edited_at"]
    down = client.post(f"/api/research/meetings/{mid}/agenda/draft")
    assert down.status_code == 503 and down.json() == {"error": "model_unavailable"}
    # notes: no model, bullet lines are the tasks; a date in the line is its due date
    notes = "- Thêm thí nghiệm ablation, hạn 2026-11-18\n- Đọc lại paper của Haddad\n- Viết mục 3 trước thứ Sáu"
    done = client.put(f"/api/research/meetings/{mid}/notes", json={"notes_md": notes})
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "done" and body["notes_md"] == notes and len(body["action_items"]) == 3
    a1, a2, a3 = body["action_items"]
    assert a1["due_date"] == "2026-11-18" and a1["in_plan"] is True and a2["due_date"] is None and a2["in_plan"] is False
    assert a3["due_date"] == "2026-11-13" and a3["in_plan"] is True  # "trước thứ Sáu"
    assert a1["id"] != a2["id"] and a1["done"] is False
    patched = client.patch(f"/api/research/meetings/{mid}/actions/{a2['id']}", json={"due_date": "2026-11-12", "done": False})
    assert [a["in_plan"] for a in patched.json()["action_items"]] == [True, True, True]
    assert client.patch(f"/api/research/meetings/{mid}/actions/zz", json={"done": True}).json() == {"error": "action_not_found"}
    assert [x["id"] for x in client.get("/api/research/meetings", params={"status": "done"}).json()] == [mid]
    assert [x["id"] for x in client.get("/api/research/meetings", params={"status": "all"}).json()] == [other["id"], mid]
    assert client.patch("/api/research/meetings/mt-nope", json={"title": "x"}).json() == {"error": "meeting_not_found"}
    assert client.delete(f"/api/research/meetings/{other['id']}").status_code == 204
    assert client.delete(f"/api/research/meetings/{other['id']}").status_code == 404
    assert client.get("/api/research/meetings/next").json() is None


def test_notes_split_by_model_and_agenda_draft(client, svc, uni):
    svc.llm = FakeLLM(notes={"actions": [{"text": "Chạy ablation", "due_date": "2026-11-18"}, {"text": "Gửi bản nháp", "due_date": None}, {"text": "  ", "due_date": None}]},
                      agenda={"promised": [{"text": "Chạy lại baseline (EXP-2026-11-05-a, xong)", "done": True}, {"text": "Viết mục 3.2!", "done": False}]})
    first = client.post("/api/research/meetings", json={"at": "2026-11-01T09:00:00+07:00"}).json()
    notes = client.put(f"/api/research/meetings/{first['id']}/notes", json={"notes_md": "Họp chốt: chạy ablation trước 18/11, gửi bản nháp."}).json()
    assert [(a["text"], a["due_date"], a["in_plan"]) for a in notes["action_items"]] == [("Chạy ablation", "2026-11-18", True), ("Gửi bản nháp", None, False)]
    client.post("/api/research/experiments", json={"text": "run"})
    nxt = client.post("/api/research/meetings", json={"at": "2026-11-12T14:00:00+07:00"}).json()
    client.put(f"/api/research/meetings/{nxt['id']}/agenda", json={"open_questions": "Câu hỏi của tôi"})
    drafted = client.post(f"/api/research/meetings/{nxt['id']}/agenda/draft")
    assert drafted.status_code == 200
    ag = drafted.json()["agenda"]
    assert [i["done"] for i in ag["promised"]] == [True, False] and "!" not in str(ag["promised"])  # cleaned
    assert ag["open_questions"] == "Câu hỏi của tôi" and ag["drafted_at"]  # the learner's boxes are kept
    facts = svc.llm.user_text("agenda")
    assert "[open] Chạy ablation" in facts and "[done] Gửi bản nháp" not in facts  # last meeting's items with their done flags
    assert "EXP-2026-11-07-a" in facts


def test_agenda_auto_draft_two_days_before_and_move(client, svc, uni, clock):
    m = client.post("/api/research/meetings", json={"at": "2026-11-10T10:00:00+07:00"}).json()
    ran = tick(client, svc, clock())
    assert ran == []  # 2026-11-07 09:00 is more than 48 h before 2026-11-10 10:00
    clock.advance(hours=26)  # 2026-11-08 11:00: inside the 48 h window
    ran = tick(client, svc, clock())
    assert ran == [f"agenda:{m['id']}"]
    got = client.get("/api/research/meetings").json()[0]
    assert got["agenda"]["drafted_at"] and got["agenda"]["promised"] == []
    assert tick(client, svc, clock()) == []  # drafted once
    moved = client.patch(f"/api/research/meetings/{m['id']}", json={"at": "2026-11-20T10:00:00+07:00"}).json()
    assert moved["agenda"]["drafted_at"] is None  # the draft follows the meeting: redone 2 days before the new time
    assert tick(client, svc, clock()) == []
    clock.advance(days=10)
    assert tick(client, svc, clock()) == [f"agenda:{m['id']}"]


def test_monday_discovery_once(client, svc, uni, clock):
    svc.llm = FakeLLM(profile={"question": "Q?", "keywords": ["alpha beta"]})
    client.put("/api/research/profile", json={"title": "Chủ đề"})
    svc.arx.default = [arxiv_paper("2611.00001", "Monday paper")]
    for _ in range(100):
        if not svc._running(uid(client), "discovery"):
            break
        client.get("/api/research/profile")
    clock.now = datetime(2026, 11, 8, 22, 30, tzinfo=UTC)  # Sunday 22:30 UTC = Monday 05:30 in Vietnam
    assert tick(client, svc, clock()) == []
    clock.now = datetime(2026, 11, 8, 23, 30, tzinfo=UTC)  # Monday 06:30
    assert tick(client, svc, clock()) == [f"discovery:{uid(client)}"]
    assert tick(client, svc, clock()) == []  # once per Monday
    from mentor_gateway.db import JobRow

    with svc.db.session() as s:
        row = s.get(JobRow, f"lw-{uid(client)}-2026-11-09")
        assert row is not None and row.kind == "literature_watch"


# ---- planner: items, reminders, quiet mode, triggers -------------------------------------------------------------------

def research_items(client) -> list[dict]:
    return [i for i in client.get("/api/plan/week").json()["items"] if i["kind"] == "research"]


def test_planner_research_items_reminders_and_triggers(client, svc, uni, gw, clock):
    client.put("/api/research/profile", json={"title": "Học máy cho vật liệu", "question": "Q?", "keywords": ["a b"]})
    d1 = client.post("/api/research/deadlines", json={"title": "Nộp full paper", "due_date": "2026-11-12", "due_time": "18:00", "kind": "submission"}).json()
    d2 = client.post("/api/research/deadlines", json={"title": "Nộp poster", "due_date": "2026-11-14", "due_time": "18:00"}).json()
    meeting = client.post("/api/research/meetings", json={"at": "2026-11-09T14:00:00+07:00"}).json()
    client.put(f"/api/research/meetings/{meeting['id']}/notes", json={"notes_md": "- Chạy ablation, hạn 2026-11-10"})
    user = gw.users.get(uid(client))
    client.get("/api/today")  # first request makes the plan (rule-based: no planner model in tests)
    gw.planner.generate_now(user, "research_deadline_changed")
    items = research_items(client)
    assert items and all(i["deep_link"].startswith("/nghien-cuu") and i["course_id"] is None and i["lesson_id"] is None for i in items)
    assert all(20 <= i["minutes"] <= 45 and "06:30" <= i["start"] < "23:30" for i in items)  # the uni band limits
    deadline_sessions = [i for i in items if i["code"] == "RESEARCH_DEADLINE"]
    assert deadline_sessions and all(i["date"] <= "2026-11-12" for i in deadline_sessions if i["ref"]["id"] == d1["id"])
    assert any("Hai hạn gần nhau" in i["reason_vi"] for i in deadline_sessions)  # two deadlines within 3 days: one earlier heads-up
    action = [i for i in items if i["code"] == "RESEARCH_ACTION"]
    assert len(action) == 1 and action[0]["date"] < "2026-11-10"  # placed before the date
    assert len([i for i in items if i["code"] == "RESEARCH_READING"]) >= 1
    assert len({i["date"] for i in client.get("/api/plan/week").json()["items"] if i["kind"] != "break"}) <= 6
    ms = {m["id"]: m for m in client.get("/api/research/deadlines").json()}
    assert ms[d1["id"]]["planned_sessions"] >= 1  # the milestone shows what the planner placed
    # reminders: kind research, <= 2 a day, only for confirmed deadlines with a time, none in the past
    rems = client.get("/api/reminders", params={"since": "2026-11-01T00:00:00+07:00"}).json()["reminders"]
    research = [r for r in rems if r["kind"] == "research"]
    assert research and all(r["deep_link"].startswith("/nghien-cuu") for r in research)
    per_day: dict[str, int] = {}
    for r in rems:
        per_day[r["at"][:10]] = per_day.get(r["at"][:10], 0) + 1
    assert max(per_day.values()) <= 2 and all(r["at"] > "2026-11-07T09:00" for r in research)
    assert any("Còn 2 ngày" in r["text_vi"] for r in research)  # 48 hours before 2026-11-12 18:00
    # a deadline within 48 hours always gets one
    clock.now = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)  # 10:00 on 11/11, 32 hours before the paper deadline
    client.post("/api/research/deadlines", json={"title": "Nộp gấp", "due_date": "2026-11-12", "due_time": "17:00"})
    gw.planner.generate_now(user, "nightly")
    rems = client.get("/api/reminders", params={"since": "2026-11-01T00:00:00+07:00"}).json()["reminders"]
    soon = [r for r in rems if r["kind"] == "research" and r["status"] == "scheduled" and r["at"] > "2026-11-11T10:00"]
    assert any("giờ" in r["text_vi"] for r in soon)
    # an unconfirmed deadline never gets a time-based reminder
    client.patch(f"/api/research/deadlines/{d1['id']}", json={"due_time": None})
    assert next(m for m in client.get("/api/research/deadlines").json() if m["id"] == d1["id"])["confirmed"] is False
    # triggers: changes mark the plan dirty with the research trigger names
    client.patch(f"/api/research/deadlines/{d2['id']}", json={"title": "Nộp poster 2"})
    with gw.db.session() as s:
        assert s.get(PlanRecord, uid(client)).dirty == "research_deadline_changed"
        s.get(PlanRecord, uid(client)).dirty = None
    client.put(f"/api/research/meetings/{meeting['id']}/notes", json={"notes_md": "- Việc mới"})
    with gw.db.session() as s:
        assert s.get(PlanRecord, uid(client)).dirty == "research_meeting_notes"


def test_planner_research_quiet_mode_and_other_bands(client, svc, uni, gw, clock):
    client.put("/api/research/profile", json={"title": "Chủ đề", "question": "Q?", "keywords": ["a b"]})
    client.post("/api/research/deadlines", json={"title": "Nộp bài", "due_date": "2026-11-12", "due_time": "18:00"})
    user = gw.users.get(uid(client))
    gw.users.update(user.id, quiet_until=clock() + timedelta(days=30))
    gw.planner.generate_now(gw.users.get(user.id), "nightly")
    with gw.db.session() as s:
        from sqlalchemy import select

        research = list(s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.kind == "research", Reminder.status == "scheduled")))
    assert research == []  # quiet mode: nothing is scheduled inside it
    assert research_items(client)  # the plan items themselves are not notifications


def test_no_research_in_other_bands_plan(client, svc, student, gw):
    gw.planner.generate_now(gw.users.get(student["id"]), "nightly")
    assert [i for i in client.get("/api/plan/week").json()["items"] if i["kind"] == "research"] == []
    assert "research" not in client.get("/api/today").json()["hub"]  # omitted, not null, for other bands


# ---- hub line ---------------------------------------------------------------------------------------------------------

def hub_line(client) -> dict:
    hub = client.get("/api/today").json()["hub"]["research"]
    assert client.get("/api/research").json()["status_line"] == hub  # ResearchOverview.status_line is the same value
    return hub


def test_hub_research_line(client, svc, uni):
    assert hub_line(client) == {"line_vi": "Đặt đề tài của bạn", "line_en": "Set your topic"}
    client.put("/api/research/profile", json={"title": "Chủ đề", "question": "Q?", "keywords": ["a b"]})
    assert hub_line(client) == {"line_vi": "Chưa có gì mới", "line_en": "Nothing new"}
    deadline(client, "nộp full paper 20/11, 17:00")
    assert hub_line(client) == {"line_vi": "Hạn nộp bài còn 13 ngày", "line_en": "Paper due in 13 days"}
    client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00001", "source": "arxiv", "title": "P", "arxiv_id": "2603.00001", "has_pdf": True}})
    assert hub_line(client) == {"line_vi": "Hạn nộp bài còn 13 ngày, 1 paper mới", "line_en": "Paper due in 13 days, 1 new paper"}
    client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00002", "source": "arxiv", "title": "P2", "arxiv_id": "2603.00002", "has_pdf": True}})
    assert hub_line(client)["line_en"] == "Paper due in 13 days, 2 new papers"
    client.delete("/api/research/deadlines/ms-1")
    other = deadline(client, "hạn đăng ký 8/11 17:00")  # tomorrow, not a submission
    assert hub_line(client)["line_vi"] == "Hạn gần nhất ngày mai, 2 paper mới"
    client.patch(f"/api/research/deadlines/{other['id']}", json={"due_date": "2026-11-07"})
    assert hub_line(client)["line_en"].startswith("Next deadline today")
    client.patch(f"/api/research/deadlines/{other['id']}", json={"due_time": None})  # unconfirmed deadlines do not count
    assert hub_line(client)["line_en"] == "2 new papers"
    client.patch(f"/api/research/deadlines/{other['id']}", json={"due_date": "2026-12-30", "due_time": "10:00"})  # beyond 30 days
    assert hub_line(client)["line_en"] == "2 new papers"


def test_overview_hero_upcoming_and_featured(client, svc, uni):
    ov = client.get("/api/research").json()
    assert ov["hero"] is None and ov["reading_list"]["items"] == [] and ov["discovery"]["state"] == "idle" and ov["goal_id"] is None
    svc.llm = FakeLLM(profile={"question": "Q?", "keywords": ["a b"]}, hero={"line": "Bài còn 9 ngày nữa đến hạn!"})
    client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00001", "source": "arxiv", "title": "Old", "arxiv_id": "2603.00001",
                                                              "authors": ["Pham Tuan", "Okafor"], "year": 2026, "has_pdf": True}, "reason": "Cần cho hạn nộp bài"})
    new = client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00002", "source": "arxiv", "title": "Newer", "arxiv_id": "2603.00002",
                                                                    "has_pdf": True}, "reason": "Khác"}).json()
    hero = client.get("/api/research").json()["hero"]
    assert hero["title"] == "Old" and hero["reason"] == "Cần cho hạn nộp bài" and hero["authors_line"] == "Tuan, Okafor · 2026"  # the one whose reason names a deadline
    assert hero["deep_link"].startswith("/nghien-cuu/paper/") and hero["status"] == "new"
    client.get(f"/api/research/papers/{new['id']}")  # opening it makes it `reading`: the one opened last wins
    assert client.get("/api/research").json()["hero"]["paper_id"] == new["id"]
    deadline(client, "nộp full paper 15/11, 23:59 AoE")  # a confirmed deadline within 14 days: one model sentence, cached per day
    h1 = client.get("/api/research").json()["hero"]
    assert h1["reason"] == "Bài còn 9 ngày nữa đến hạn." and svc.llm.count("hero") == 1
    client.get("/api/research")
    assert svc.llm.count("hero") == 1
    svc.hero_cache.clear()
    svc.llm.replies["hero"] = RuntimeError("down")
    assert client.get("/api/research").json()["hero"]["reason"] == "Khác"  # the entry's own reason on model failure
    client.post("/api/research/meetings", json={"at": "2026-11-09T14:00:00+07:00", "title": "Họp"})
    up = client.get("/api/research").json()["upcoming"]
    assert [(u["kind"], u["title"]) for u in up] == [("meeting", "Họp"), ("deadline", "Nộp full paper")] or up[0]["kind"] == "meeting"
    assert up[0]["time"] == "14:00" and up[0]["agenda_ready"] is False and up[0]["days_left"] == 2
    assert up[1]["original_text"] == "23:59 AoE 15/11" and up[1]["days_left"] == 9


# ---- events, uploads --------------------------------------------------------------------------------------------------

def test_events_recorded_server_side_and_rejected_from_the_app(client, svc, uni):
    for kind in ("paper_opened", "paper_read", "summary_written", "experiment_logged"):
        r = client.post("/api/events", json={"events": [{"id": "x1", "kind": kind, "ts": "2026-11-07T09:00:00+07:00", "data": {"paper_id": "p"}}]})
        assert r.status_code == 422  # the app never sends them
    pid = client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00001", "source": "arxiv", "title": "P", "arxiv_id": "2603.00001", "has_pdf": True}}).json()["id"]
    client.get(f"/api/research/papers/{pid}")
    client.get(f"/api/research/papers/{pid}")  # same day: one event
    client.put(f"/api/research/papers/{pid}/summary", json={"text": "Một bản tóm tắt đủ dài để tính."})
    client.put(f"/api/research/papers/{pid}/status", json={"status": "read"})
    got = ev.stored(svc.db, uid(client), datetime(2026, 1, 1, tzinfo=UTC))
    by = {e["kind"]: e for e in got}
    assert [e["kind"] for e in got].count("paper_opened") == 1
    assert by["paper_opened"]["data"] == {"paper_id": pid} and by["paper_read"]["data"] == {"paper_id": pid}
    assert by["summary_written"]["data"] == {"paper_id": pid, "chars": len("Một bản tóm tắt đủ dài để tính.")}
    # they are study activity: a session exists and the learner is not idle
    from mentor_gateway.planner.profile import sessions

    assert sessions(ev.load(svc.db, uid(client), svc.clock()))
    # minutes_spent sums the focus ticks that follow paper_opened
    ev.record(svc.db, uid(client), "tick1", "focus_tick", svc.clock() + timedelta(minutes=5), {"session": "s", "seconds": 300})
    ev.record(svc.db, uid(client), "tick2", "focus_tick", svc.clock() + timedelta(minutes=10), {"session": "s", "seconds": 240})
    assert client.get("/api/research/reading-list").json()["items"][0]["minutes_spent"] == 9


def test_add_uploaded_pdf(client, svc, uni, gw, monkeypatch):
    from mentor_gateway.mirror import normalize_path

    path = normalize_path("inbox/2026-11-07-090000-my-paper.pdf")
    gw.mirror.commit_files(uid(client), {path: b"%PDF-1.4 fake"}, author="user", message="upload")
    text = "A Study of Kernels\nAbstract: We study kernels in depth and show that they work well on small data sets of molecules.\n\n1 Introduction\nKernels are old. " * 3
    monkeypatch.setattr(fulltext, "extract_pdf_text", lambda data: text)
    r = client.post("/api/research/reading-list", json={"upload_path": path})
    assert r.status_code == 201 and r.json()["origin"] == "pdf" and r.json()["paper"]["title"] == "A Study of Kernels"
    pid = r.json()["id"]
    d = client.get(f"/api/research/papers/{pid}").json()
    assert d["fulltext"] == "ready" and d["entry"]["id"] == pid  # the entry id is the paper id used in every /papers/{id} path
    again = client.post("/api/research/reading-list", json={"upload_path": path})
    assert again.status_code == 200 and again.json()["id"] == pid
    gw.mirror.commit_files(uid(client), {normalize_path("inbox/not.pdf"): b"hello"}, author="user", message="x")
    assert client.post("/api/research/reading-list", json={"upload_path": "inbox/not.pdf"}).json() == {"error": "bad_paper_ref"}


def test_ledger_isolation_between_learners(client, svc, uni):
    pid = client.post("/api/research/reading-list", json={"card": {"key": "arxiv:2603.00001", "source": "arxiv", "title": "P", "arxiv_id": "2603.00001", "has_pdf": True}}).json()["id"]
    deadline(client, "nộp 15/11 23:59 AoE")
    new_student(client, "uni2", "uni")
    assert client.get(f"/api/research/papers/{pid}").json() == {"error": "paper_not_found"}
    assert client.get("/api/research/reading-list").json()["items"] == [] and client.get("/api/research/deadlines").json() == []
    with svc.db.session() as s:
        assert s.query(MeetingRow).count() == 0
