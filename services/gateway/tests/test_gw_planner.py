"""Planner: profile math, FSRS due items, validator, fallback, LLM interplay, API (offline; the model is mocked)."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from gateway_fakes import login
from mentor_schemas.course import Chapter, CourseMeta, CoursePack, Lesson, QuizBlock, QuizItem, QuizOption, TextBlock
from planner_fixtures import NOW, TZ, ev, goal_for, local_dt, make_courses, make_ctx, simulate, study_session

from mentor_gateway.content import ContentStore, asset_ref_for
from mentor_gateway.planner import events as plan_events
from mentor_gateway.planner import llm as plan_llm
from mentor_gateway.planner.bands import band_for
from mentor_gateway.planner.fallback import plan_fallback
from mentor_gateway.planner.fsrs_items import due_items
from mentor_gateway.planner.profile import compute_profile, effective_minutes, sessions
from mentor_gateway.planner.validator import validate

TODAY = NOW.astimezone(TZ).date()


def at_iso(day_offset: int, hhmm: str, base=TODAY) -> str:
    return local_dt(base + timedelta(days=day_offset), hhmm).astimezone(TZ).isoformat()


def item(day_offset=1, start="19:30", minutes=20, kind="lesson", cid="c1", lid="l1", base=TODAY, **kw):
    return {"date": (base + timedelta(days=day_offset)).isoformat(), "start": start, "minutes": minutes, "kind": kind,
            "course_id": cid, "lesson_id": lid, "reason_vi": "Học tiếp bài này nhé.", "reason_en": "Continue this lesson.", **kw}


def rem(day_offset=1, hhmm="19:30", kind="study", text="20 phút nhé?", base=TODAY):
    return {"at": at_iso(day_offset, hhmm, base), "kind": kind, "text_vi": text, "text_en": "20 minutes?", "deep_link": "/khoa-hoc/c1"}


# ------------------------------------------------------------------ profile math
def test_window_weights_halve_every_14_days():
    habit_old = local_dt(TODAY - timedelta(days=14), "19:30")  # Monday 14 days ago, same weekday as today
    events = study_session(habit_old, 10, tag="a") + study_session(local_dt(TODAY - timedelta(days=7), "20:00"), 10, tag="b")
    p = compute_profile(sorted(events, key=lambda e: e["ts"]), NOW, band_for("g10_12"))
    w = {x["start"]: x["weight"] for x in p["windows"]}
    exact = lambda t: 0.5 ** ((NOW - t).total_seconds() / 86400 / 14)
    assert w["19:30"] == pytest.approx(exact(habit_old), abs=0.002)
    assert w["20:00"] == pytest.approx(exact(local_dt(TODAY - timedelta(days=7), "20:00")), abs=0.002)
    assert w["19:30"] / w["20:00"] == pytest.approx(0.5 ** 0.5, abs=0.05)  # a week older = 1/sqrt(2) lighter


def test_windows_follow_the_habit_and_cadence():
    p = compute_profile(simulate(NOW, "22:30", {0, 1, 3, 4, 5}), NOW, band_for("uni"))
    assert p["windows"][0]["start"] in ("22:00", "22:30")
    assert p["cadence_days_per_week"] == 5
    assert not p["cold_start"] and p["sessions_seen"] >= 15


def test_effective_session_minutes_found_where_accuracy_and_speed_drop():
    ev_list = simulate(NOW, "19:30", {0, 1, 2, 3, 4}, minutes=40, drop_after=20)
    eff = effective_minutes(sessions(ev_list))
    assert eff is not None and 18 <= eff <= 26
    p = compute_profile(ev_list, NOW, band_for("g10_12"))
    assert p["session_minutes"] == 20 or p["session_minutes"] == 25  # rounded to 5 and inside the 15-30 band


def test_cold_start_uses_age_defaults():
    for band, minutes in (("g1_5", 10), ("g6_9", 20), ("g10_12", 20), ("uni", 30)):
        p = compute_profile([], NOW, band_for(band))
        assert p["cold_start"] and p["session_minutes"] == minutes
    plan = plan_fallback(make_ctx([], "g1_5"))
    assert {i["start"] for i in plan["items"]} == {"18:00"} or all(i["start"] >= "18:00" for i in plan["items"])


def test_reminder_response_and_avoid_after_three_ignored():
    outs = [ev("reminder_outcome", NOW - timedelta(days=d), reminder_id=f"r{d}", outcome="ignored", at=at_iso(-d, "19:30"))
            for d in (5, 4, 3)]
    p = compute_profile(outs, NOW, band_for("g10_12"))
    assert p["reminder_response"]["19:30"]["ignored_streak"] == 3 and p["avoid_slots"] == ["19:30"]
    opened = outs[:2] + [ev("reminder_outcome", NOW, reminder_id="r1", outcome="opened", at=at_iso(-1, "19:30"))]
    p = compute_profile(opened, NOW, band_for("g10_12"))
    assert p["avoid_slots"] == [] and p["reminder_response"]["19:30"]["open_rate"] == 0.33


# ------------------------------------------------------------------ FSRS
def test_fsrs_due_items():
    t0 = NOW - timedelta(days=3)
    events = [ev("quiz_answer", t0, item="a", course_id="c1", correct=True, seconds=5),
              ev("quiz_answer", t0 + timedelta(minutes=1), item="b", course_id="c1", correct=False, seconds=9)]
    due = due_items(events, NOW)
    assert {d["item"] for d in due} == {"a", "b"}  # new cards come due within minutes or a day, 3 days later both are due
    soon = due_items(events, t0 + timedelta(minutes=5))
    assert "b" in {d["item"] for d in soon} or soon == []  # a miss is due again almost at once
    # a card reviewed correctly many times gets a long interval
    many = [ev("quiz_answer", t0 + timedelta(days=i * 3), item="z", course_id="c1", correct=True, seconds=4) for i in range(5)]
    assert due_items(many, many[-1]["ts"] + timedelta(days=1)) == []


# ------------------------------------------------------------------ validator
def ctx_for_validation(**kw):
    return make_ctx(simulate(NOW, "19:30", {0, 1, 3, 4}), **kw)


def test_validator_clamps_minutes_and_drops_bad_items():
    ctx = ctx_for_validation()
    plan = {"items": [item(1, minutes=90), item(2, minutes=2, lid="l2"), item(3, cid="nope"), item(4, start="23:30"),
                      item(30), item(5, lid="l3", kind="lesson", start="05:00")], "reminders": []}
    ok, fixed, notes = validate(plan, ctx)
    assert ok
    assert [i["minutes"] for i in fixed["items"]] == [30, 15]  # clamped into the g10_12 band (15-30)
    assert len(fixed["items"]) == 2 and len(notes) >= 4


def test_validator_reminder_rules():
    ctx = make_ctx(simulate(NOW, "19:30", {0, 1, 3, 4, 6}), quiet_until=local_dt(TODAY + timedelta(days=1), "21:00"))
    ctx.profile["today_starts"] = ["10:00"]
    ctx.profile["avoid_slots"] = ["20:00"]
    plan = {"items": [item(1), item(2, lid="l2")], "reminders": [
        rem(2, "19:30"), rem(2, "19:45"), rem(2, "20:15"),  # 3 on day 2: only 2 kept (20:00 slot is avoided anyway)
        rem(1, "19:30"),  # before quiet_until (day 1 21:00)
        rem(2, "23:00"),  # after the g10_12 bedtime 22:30
        rem(2, "05:00"),  # before 06:30
        rem(0, "10:15"),  # today, the student already studied at 10:00
        rem(-1, "19:30"),  # past
        rem(3, "19:30", kind="nudge"),  # the student studied yesterday: nudge not allowed
    ]}
    ok, fixed, notes = validate(plan, ctx)
    assert ok
    assert [r["at"][:16] for r in fixed["reminders"]] == [at_iso(2, "19:30")[:16], at_iso(2, "19:45")[:16]]
    assert any("quiet" in n for n in notes) and any("bedtime" in n or "age-band" in n for n in notes)


def test_validator_at_most_two_reminders_a_day():
    ctx = ctx_for_validation()
    plan = {"items": [item(1)], "reminders": [rem(2, "19:00"), rem(2, "19:30"), rem(2, "20:00"), rem(2, "21:00")]}
    ok, fixed, _ = validate(plan, ctx)
    assert ok and len(fixed["reminders"]) == 2


def test_validator_nudge_only_after_two_idle_days():
    events = simulate(NOW, "19:30", {0, 1, 3, 4})
    events = [e for e in events if e["ts"] < NOW - timedelta(days=3)]  # last study 3+ days ago
    ctx = make_ctx(events)
    assert (ctx.profile["days_since_study"] or 0) >= 2
    ok, fixed, _ = validate({"items": [item(1)], "reminders": [rem(1, "19:30", "nudge"), rem(2, "19:30", "nudge")]}, ctx)
    assert ok and [r["kind"] for r in fixed["reminders"]] == ["nudge"]  # one only


def test_validator_trims_pace_far_above_actual():
    ctx = ctx_for_validation()  # actual ~ 20 min x 4 days/week
    plan = {"items": [item(i, start="19:30", minutes=30, lid=f"l{i}") for i in range(1, 7)], "reminders": []}
    ok, fixed, notes = validate(plan, ctx)
    from mentor_gateway.planner.fallback import weekly_cap

    assert ok and sum(i["minutes"] for i in fixed["items"]) <= weekly_cap(ctx) and any("trimmed" in n for n in notes)


def test_validator_overlaps_and_unfixable():
    ctx = ctx_for_validation()
    ok, fixed, _ = validate({"items": [item(1, start="19:30", minutes=30), item(1, start="19:45", minutes=20, lid="l2")],
                             "reminders": []}, ctx)
    assert ok and len(fixed["items"]) == 1
    assert validate({"nope": 1}, ctx)[0] is False
    assert validate({"items": [item(1, cid="zzz")], "reminders": []}, ctx)[0] is False  # nothing usable left
    seven = {"items": [item(i, minutes=15, lid=f"l{i + 1}") for i in range(7)], "reminders": []}
    assert validate(seven, ctx)[0] is False  # 7 study days in a row


def test_validator_goal_statuses_default_to_codes_own():
    ctx = ctx_for_validation()
    ok, fixed, _ = validate({"items": [item(1)], "reminders": [], "goals": [
        {"goal_id": "unknown", "status": "behind", "line_vi": "x", "line_en": "x"}]}, ctx)
    assert ok and [g["goal_id"] for g in fixed["goals"]] == ["g-c1"]


def test_text_rules_applied_to_model_output():
    ctx = ctx_for_validation()
    it = item(1, reason_vi="Hãy học nhé!!! — bài này quan trọng 🎉")
    ok, fixed, _ = validate({"items": [it], "reminders": []}, ctx)
    r = fixed["items"][0]["reason_vi"]
    assert ok and "!" not in r and "—" not in r and "🎉" not in r and not r.startswith("Hãy")


# ------------------------------------------------------------------ fallback
def reasons(plan):
    return [i["code"] for i in plan["items"]]


def test_fallback_priorities_unfinished_then_review_then_behind_then_next():
    c1 = make_courses(6, done=1, partial=1)  # l2 unfinished
    events = simulate(NOW, "19:30", {0, 1, 3, 4, 5})
    plan = plan_fallback(make_ctx(events, courses=[c1], goals=[goal_for(c1, status="behind")]))
    codes = reasons(plan)
    assert codes[0] == "UNFINISHED_LESSON" and plan["items"][0]["lesson_id"] == "l2"
    assert "DUE_REVIEW" in codes or "BEHIND_GOAL" in codes or "NEXT_LESSON" in codes
    assert set(codes) <= {"UNFINISHED_LESSON", "DUE_REVIEW", "BEHIND_GOAL", "NEXT_LESSON"}
    lessons = [i["lesson_id"] for i in plan["items"] if i["kind"] == "lesson"]
    assert len(lessons) == len(set(lessons))  # a lesson is planned once


def test_fallback_due_review_when_nothing_unfinished():
    c1 = make_courses(4, done=4)
    events = simulate(NOW, "19:30", {0, 2, 4}) + [ev("quiz_answer", NOW - timedelta(days=2), item="miss", course_id="c1",
                                                    correct=False, seconds=30)]
    plan = plan_fallback(make_ctx(events, courses=[c1], goals=[goal_for(c1)]))
    assert plan["items"] and plan["items"][0]["kind"] in ("review", "practice") and plan["items"][0]["code"] == "DUE_REVIEW"
    assert "câu" in plan["items"][0]["reason_vi"]


def test_fallback_plan_passes_the_validator_and_is_deterministic():
    for band in ("g1_5", "g6_9", "g10_12", "uni"):
        ctx = make_ctx(simulate(NOW, "18:00", {0, 1, 2, 3}), band)
        plan = plan_fallback(ctx)
        ok, _fixed, notes = validate(plan, ctx)
        assert ok and not notes, (band, notes)
        assert plan == plan_fallback(ctx)
        lo, hi = band_for(band).min_minutes, band_for(band).max_minutes
        assert all(lo <= i["minutes"] <= hi for i in plan["items"])


def test_fallback_skips_self_start_slots_and_stays_quiet_in_quiet_mode():
    events = simulate(NOW, "19:30", {0, 1, 3, 4})
    ctx = make_ctx(events, quiet_until=NOW + timedelta(days=2))
    plan = plan_fallback(ctx)
    ok, fixed, _ = validate(plan, ctx)
    assert ok and all(datetime.fromisoformat(r["at"]) >= ctx.quiet_until for r in fixed["reminders"])
    assert fixed["items"]  # the plan itself still moves on during quiet mode


# ------------------------------------------------------------------ LLM interplay (mocked router)
class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def plan(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise plan_llm.PlannerLLMError(self.error)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def test_prompt_carries_the_skills_and_the_profile():
    ctx = make_ctx(simulate(NOW, "19:30", {0, 1, 3}))
    system = plan_llm.system_prompt("weekly_review")
    for skill in ("Spaced practice scheduler", "Individual spacing", "Study strategy selector", "Interleaving across the week",
                  "Flow conditions", "If-then reminders", "Many missed sessions", "Weekly pattern review"):
        assert skill in system
    assert "weekly review" in system and "CC BY-SA 4.0" in system and "No em dashes" in system
    payload = plan_llm.user_payload(ctx)
    assert {"profile", "goals_input", "courses", "due_items", "current_week_plan", "moves", "age_band"} <= set(payload)
    assert payload["courses"][0]["lessons"][0]["minutes"] == 15


def test_parse_is_strict():
    assert plan_llm.parse('<think>x</think>```json\n{"items": []}\n```') == {"items": []}
    for bad in ("", "not json", "[1]"):
        with pytest.raises(plan_llm.PlannerLLMError):
            plan_llm.parse(bad)


def run_generate(gw, user, llm, trigger="nightly"):
    gw.planner.llm = llm
    return asyncio.run(gw.planner.generate(user, trigger))


# ------------------------------------------------------------------ API
ASSET = asset_ref_for("a.png", b"png", "image/png")


def publish(store: ContentStore, cid: str, title: str, lessons: int = 3, band="g10_12", subject="Vật lí"):
    meta = CourseMeta(id=cid, title=title, subject=subject, age_band=band, language="vi", teacher_id="giaovien",
                      teacher_name="Thầy Minh", description_short="Mô tả ngắn.", outcomes=["x"], cover="cover.png")
    store.create_draft(meta)
    (store.course_dir(cid) / "cover.png").write_bytes(b"cover" + cid.encode())
    chapters = [Chapter(id="ch1", title="Chương 1", lessons=[Lesson(
        id=f"l{i}", title=f"Bài {i}", est_minutes=15, blocks=[
            TextBlock(id=f"l{i}t", md="Nội dung"),
            QuizBlock(id=f"l{i}q", items=[QuizItem(id=f"q{i}", type="SINGLE_CHOICE", stem="?", options=[
                QuizOption(id="A", text="x"), QuizOption(id="B", text="y")], answer_key={"correct_option_id": "A"},
                explanation="vì")])]) for i in range(1, lessons + 1)])]
    store.write_pack(cid, 1, CoursePack(course_id=cid, version=1, language="vi", age_band=band, title=title,
                                        chapters=chapters), {})
    store.publish(cid, 1)


@pytest.fixture
def store(client, tmp_path):
    s = ContentStore(tmp_path / "courses", client.app.state.gw.clock)
    client.app.state.content.store = s
    return s


@pytest.fixture
def enrolled(client, store, student):
    publish(store, "dien-truong", "Vật lí 11: Điện trường")
    publish(store, "cap-so-cong", "Toán 11: Cấp số cộng", subject="Toán")
    for cid in ("dien-truong", "cap-so-cong"):
        assert client.post("/api/enrollments", json={"course_id": cid}).status_code in (200, 201)
    return student


def auth(client):
    return client.headers


def test_api_requires_a_student(client, teacher):
    for method, path, body in (("post", "/api/events", {"events": []}), ("get", "/api/today", None),
                               ("get", "/api/plan/week", None), ("get", "/api/reminders", None),
                               ("post", "/api/reminders/r-x/outcome", {"outcome": "opened"}), ("get", "/api/goals", None),
                               ("post", "/api/goals", {"title": "x"}), ("delete", "/api/goals/g-x", None)):
        r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and r.json() == {"error": "role_mismatch"}, path
    anon = client.__class__(client.app)
    assert anon.get("/api/today").status_code == 401


def test_events_are_idempotent_and_validated(client, student, clock):
    now = clock().isoformat()
    batch = {"events": [
        {"id": "e1", "kind": "app_open", "ts": now},
        {"id": "e2", "kind": "quiz_answer", "ts": now, "data": {"item": "q1", "correct": True, "seconds": 5, "evil": "x"}},
        {"id": "e3", "kind": "quiz_answer", "ts": now, "data": {"item": "q1"}},  # correct is required
        {"id": "e4", "kind": "app_open", "ts": (clock() + timedelta(days=9)).isoformat()},  # from the future
    ]}
    assert client.post("/api/events", json=batch).json() == {"accepted": 2, "duplicates": 0, "rejected": 2}
    assert client.post("/api/events", json=batch).json() == {"accepted": 0, "duplicates": 2, "rejected": 2}
    assert client.post("/api/events", json={"events": [{"id": "x", "kind": "nope", "ts": now}]}).status_code == 422


def test_ask_events_are_stored_and_summed_in_the_profile(client, student, clock):
    now = clock().isoformat()
    batch = {"events": [
        {"id": "a1", "kind": "ask_question", "ts": now, "data": {"intent": "solve", "input": "photo", "text": "never kept"}},
        {"id": "a2", "kind": "ask_question", "ts": now, "data": {"intent": "learn", "input": "text"}},
        {"id": "a3", "kind": "ask_question", "ts": now, "data": {"intent": "chat", "input": "text"}},  # unknown intent
        {"id": "a4", "kind": "ask_course_open", "ts": now, "data": {"course_id": "dien-truong"}},
        {"id": "a5", "kind": "ask_course_open", "ts": now, "data": {}},  # no course
    ]}
    assert client.post("/api/events", json=batch).json() == {"accepted": 3, "duplicates": 0, "rejected": 2}
    gw = client.app.state.gw
    evs = plan_events.load(gw.db, student["user_id"], clock())
    assert [e["data"] for e in evs if e["kind"] == "ask_question"][0] == {"intent": "solve", "input": "photo"}
    profile = compute_profile(evs, clock(), band_for("g10_12"))
    assert profile["ask_14d"] == {"learn": 1, "solve": 1, "other": 0, "courses_opened": 1}


def test_today_week_and_reminders_cold_start(client, enrolled):
    t = client.get("/api/today").json()
    assert t["today"] and t["today"]["deep_link"].startswith("/khoa-hoc/") and t["today"]["reason_vi"]
    assert set(t["hub"]) == {"courses", "practice", "ask", "progress"} and "mục tiêu" in t["hub"]["progress"]["line_vi"]
    w = client.get("/api/plan/week").json()
    assert w["source"] == "fallback" and w["items"] and len(w["days"]) == 9
    assert all(set(i) >= {"date", "start", "minutes", "kind", "course_id", "reason_vi", "reason_en", "label"} for i in w["items"])
    assert {g["goal_id"] for g in w["goals"]} == {"inf-dien-truong", "inf-cap-so-cong"}
    r = client.get("/api/reminders").json()
    assert r["quiet_until"] is None and r["break_after_minutes"] == 50
    assert r["reminders"] and all(x["status"] == "scheduled" and x["deep_link"].startswith("/") for x in r["reminders"])
    rid = r["reminders"][0]["id"]
    assert client.post(f"/api/reminders/{rid}/outcome", json={"outcome": "opened"}).json() == {"ok": True}
    assert client.post("/api/reminders/r-nope/outcome", json={"outcome": "opened"}).status_code == 404
    assert client.get("/api/reminders", params={"since": (datetime.now(UTC) + timedelta(days=1)).isoformat()}).json()["reminders"] == []
    assert client.get("/api/reminders").json()["reminders"][0]["outcome"] == "opened"


def test_week_keeps_past_days_and_flags_done_items(client, enrolled, clock):
    first = client.get("/api/plan/week").json()
    assert first["days"][0] == "2026-10-26" and first["days"][-1] == "2026-11-03"  # Monday of this week .. today + 6
    assert len(first["days"]) == 9 and not any(i["done"] for i in first["items"])
    it = next(i for i in first["items"] if i["kind"] != "break")
    begin = datetime.fromisoformat(f"{it['date']}T{it['start']}:00").replace(tzinfo=TZ)
    ends = begin + timedelta(minutes=it["minutes"])
    sess = {"session": "s1"}
    events = [{"id": "w1", "kind": "session_start", "ts": begin.isoformat(), "data": sess},
              {"id": "w2", "kind": "focus_tick", "ts": (begin + timedelta(minutes=5)).isoformat(), "data": {**sess, "seconds": 300}},
              {"id": "w3", "kind": "session_end", "ts": ends.isoformat(), "data": {**sess, "seconds": it["minutes"] * 60}}]
    assert client.post("/api/events", json={"events": events}).json()["accepted"] == 3
    clock.now = ends + timedelta(hours=14)
    gw = client.app.state.gw
    gw.planner.generate_now(gw.users.get(enrolled["id"]), "nightly")
    later = client.get("/api/plan/week").json()
    past = [i for i in later["items"] if i["date"] == it["date"] and i["start"] == it["start"]]
    assert later["today"] > it["date"] and len(past) == 1 and past[0]["done"] is True
    assert it["date"] in later["days"]


def test_quiet_until_is_reported_and_reminders_respect_it(client, enrolled, clock):
    until = (clock() + timedelta(days=2)).isoformat()
    assert client.put("/api/me/quiet", json={"until": until}).status_code == 200
    gw = client.app.state.gw
    user = gw.users.get(enrolled["id"])
    gw.planner.generate_now(user, "test")
    out = client.get("/api/reminders").json()
    assert out["quiet_until"] is not None
    assert all(datetime.fromisoformat(r["at"]) >= clock() + timedelta(days=2) for r in out["reminders"] if r["status"] == "scheduled")


def test_goals_crud_inferred_and_student(client, enrolled):
    goals = client.get("/api/goals").json()
    assert {g["id"] for g in goals} == {"inf-dien-truong", "inf-cap-so-cong"} and all(g["kind"] == "inferred" for g in goals)
    g0 = goals[0]
    assert set(g0) >= {"id", "title", "deadline", "progress_pct", "status", "line_vi", "line_en", "course_ids", "courses"}
    r = client.post("/api/goals", json={"title": "Thi giữa kỳ Toán", "deadline": "2026-12-20"})
    assert r.status_code == 201
    mine = r.json()
    assert mine["kind"] == "student" and mine["course_ids"] == ["cap-so-cong"] and mine["deadline"] == "2026-12-20"
    assert mine["status"] in ("new", "on_track", "slightly_behind", "behind")
    p = client.patch(f"/api/goals/{mine['id']}", json={"title": "Thi giữa kỳ Vật lí", "deadline": None, "course_ids": ["dien-truong"]})
    assert p.status_code == 200 and p.json()["course_ids"] == ["dien-truong"] and p.json()["deadline"] is None
    assert client.delete(f"/api/goals/{mine['id']}").status_code == 204
    assert client.delete(f"/api/goals/{mine['id']}").status_code == 404
    assert client.patch("/api/goals/g-nope", json={"title": "x"}).status_code == 404
    assert client.delete("/api/goals/inf-cap-so-cong").status_code == 204  # hides the inferred goal for good
    assert {g["id"] for g in client.get("/api/goals").json()} == {"inf-dien-truong"}
    assert client.post("/api/goals", json={"title": ""}).status_code == 422


def test_goals_are_per_student(client, enrolled, gw):
    mine = client.post("/api/goals", json={"title": "Của em"}).json()
    other = login(client, "giaovien", "123456", "teacher")
    assert other and client.patch(f"/api/goals/{mine['id']}", json={"title": "x"}).status_code == 403


def test_llm_plan_is_used_when_valid_and_repaired_when_not(client, enrolled, clock):
    gw = client.app.state.gw
    user = gw.users.get(enrolled["id"])
    base = clock().astimezone(TZ).date()
    good = {"items": [item(1, cid="dien-truong", lid="l1", start="19:30", minutes=20, base=base)],
            "reminders": [rem(1, "19:30", base=base)], "goals": [], "week_note_vi": "Tuần nhẹ.", "week_note_en": "Light week."}
    plan = run_generate(gw, user, FakeLLM(good))
    assert gw.planner._record(user.id).source == "llm", gw.planner._record(user.id).note
    assert plan["items"][0]["lesson_id"] == "l1"
    assert client.get("/api/plan/week").json()["note_vi"] == "Tuần nhẹ."

    bad = {"items": [item(1, cid="dien-truong", lid="l1", start="19:30", minutes=200, base=base)],
           "reminders": [rem(1, "19:00", base=base), rem(1, "19:30", base=base), rem(1, "20:00", base=base)]}
    plan = run_generate(gw, user, FakeLLM(bad))
    rec = gw.planner._record(user.id)
    assert rec.source == "llm" and plan["items"][0]["minutes"] == 30 and len(plan["reminders"]) == 2 and rec.note

    for llm in (FakeLLM(error="router down"), FakeLLM(reply="not json at all"),
                FakeLLM(reply={"items": [item(1, cid="ghost", base=base)], "reminders": []})):
        plan = run_generate(gw, user, llm)
        rec = gw.planner._record(user.id)
        assert rec.source == "fallback" and plan["items"] and rec.note
    assert len([r for r in client.get("/api/reminders").json()["reminders"] if r["status"] == "scheduled"]) >= 1


def test_tick_triggers_nightly_new_enrollment_and_missed_session(client, enrolled, store, clock):
    gw = client.app.state.gw
    user = gw.users.get(enrolled["id"])
    llm = FakeLLM(error="off")
    gw.planner.llm = llm
    assert [t for _, t in asyncio.run(gw.planner.tick(force=True))] == ["first"]
    assert asyncio.run(gw.planner.tick(force=True)) == []  # nothing changed
    publish(store, "tieng-anh", "Tiếng Anh 11: Unit 4", subject="Tiếng Anh")
    assert client.post("/api/enrollments", json={"course_id": "tieng-anh"}).status_code in (200, 201)
    clock.advance(minutes=30)
    assert [t for _, t in asyncio.run(gw.planner.tick(force=True))] == ["new_enrollment"]
    client.post("/api/goals", json={"title": "Thi cuối kỳ"})
    assert [t for _, t in asyncio.run(gw.planner.tick(force=True))] == ["goal_change"]
    # a planned session today that is not attended -> missed_session (once)
    rec = gw.planner._record(user.id)
    today = clock().astimezone(TZ).date().isoformat()
    with gw.db.session() as s:
        from mentor_gateway.planner.tables import PlanRecord

        r = s.get(PlanRecord, user.id)
        r.plan = {**r.plan, "items": [{**item(0, start="10:00", minutes=20, cid="dien-truong", lid="l1"), "date": today}]}
    clock.advance(hours=1, minutes=45)  # 10:00 + 20 min + 30 min grace is long gone
    assert rec and [t for _, t in asyncio.run(gw.planner.tick(force=True))] == ["missed_session"]
    assert asyncio.run(gw.planner.tick(force=True)) == []
    clock.advance(days=1)  # next local day, after 03:00
    assert next(t for _, t in asyncio.run(gw.planner.tick(force=True))) in ("nightly", "weekly_review")


def test_weekly_review_runs_on_monday(client, enrolled, clock):
    gw = client.app.state.gw
    gw.planner.llm = None
    asyncio.run(gw.planner.tick(force=True))
    while clock().astimezone(TZ).weekday() != 0:
        clock.advance(days=1)
    ran = asyncio.run(gw.planner.tick(force=True))
    assert ran and ran[0][1] == "weekly_review"
