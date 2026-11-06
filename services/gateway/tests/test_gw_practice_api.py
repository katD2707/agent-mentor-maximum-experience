"""/api/practice flows: practice rules, mock with flags and deadline, diagnostic, evidence and mastery, item reports."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from mentor_schemas import LearningEvent
from practice_fixtures import build_content

from mentor_gateway.practice import scoring

FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"
P = "/api/practice"


@pytest.fixture(scope="session")
def practice_content(tmp_path_factory) -> Path:
    return build_content(FIXTURE_CONTENT, tmp_path_factory.mktemp("practice-content") / "mentor-content")


@pytest.fixture
def settings(settings, practice_content):
    return settings.model_copy(update={"content_dir": practice_content})


def key_of(gw, item_id: str) -> str:
    return scoring.correct_answer_text(gw.practice.bank.items[item_id].doc)


def wrong_of(gw, item) -> str:
    if item["type"] == "SINGLE_CHOICE":
        key = key_of(gw, item["id"])
        return next(o["id"] for o in item["options"] if o["id"] != key)
    return "FFTT" if item["type"] == "TRUE_FALSE_GROUP" else "9"


def start(client, **kw):
    r = client.post(f"{P}/sessions", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def events_in_mirror(gw, uid) -> list[LearningEvent]:
    text = gw.mirror.read_text(uid, "events.jsonl") or ""
    return [LearningEvent.model_validate_json(line) for line in text.splitlines() if line.strip()]


def test_thpt_only_and_catalogue(client, thpt_user, ncs_user):
    assert client.get(f"{P}/subjects").status_code == 403  # logged in as the NCS learner last
    client.post("/api/auth/logout")
    from gateway_fakes import login

    login(client, "hs@example.com")
    subs = client.get(f"{P}/subjects").json()
    assert [s["id"] for s in subs] == ["math"]
    math = subs[0]
    assert math["diagnostic"] == "none" and {t["id"] for t in math["topics"]} == {"math.function", "math.exp-log", "math.integral"}
    assert all(t["item_count"] == 14 for t in math["topics"])
    # a profile the bank cannot satisfy (4 TF, bank has 3) is not offered
    assert {p["id"] for p in math["mock_profiles"]} == {"math.mcq.t", "math.parts.t"}
    assert math["mock_profiles"][0]["disclaimer"] and math["mock_profiles"][0]["time_limit_sec"] == 600


def test_unauthenticated_is_401(client):
    assert client.get(f"{P}/subjects").status_code == 401


def test_preview_equals_started_set_and_never_leaks_keys(client, gw, thpt_user):
    body = {"subject": "math", "minutes": 20, "goal": "balanced", "seed": 5}
    pv = client.post(f"{P}/preview", json=body).json()
    s = start(client, kind="practice", **body)
    assert pv["item_count"] == len(s["items"]) and sum(pv["level_mix"]) == pv["item_count"]
    assert sum(t["count"] for t in pv["per_topic"]) == pv["item_count"]
    assert pv["level_mix"] == [sum(1 for i in s["items"] if i["level"] == lv) for lv in (1, 2, 3, 4)]
    assert {t["topic"]: t["count"] for t in pv["per_topic"]} == {
        t: sum(1 for i in s["items"] if i["topic"] == t) for t in {i["topic"] for i in s["items"]}}
    raw = json.dumps(s)
    for leak in ("answer_key", "correct_option_id", "explanation", "option_feedback", '"hint"', "truth"):
        assert leak not in raw
    assert s["status"] == "active" and s["deadline"] is None and s["answers"] == {}
    bad = client.post(f"{P}/preview", json={"subject": "math", "minutes": 7})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_minutes"
    assert client.post(f"{P}/preview", json={"subject": "chem"}).json()["code"] == "unknown_subject"
    tiny = client.post(f"{P}/preview", json={"subject": "math", "minutes": 10, "topics": ["nope"]})
    assert tiny.json()["code"] == "unknown_topic"


def test_practice_hint_reveal_and_answer_rules(client, gw, thpt_user):
    s = start(client, kind="practice", subject="math", minutes=20, goal="balanced", seed=1)
    sid, items = s["id"], s["items"]
    # reveal is locked until the item is answered
    assert client.post(f"{P}/sessions/{sid}/reveal", json={"position": 0}).status_code == 409
    h = client.post(f"{P}/sessions/{sid}/hint", json={"position": 0}).json()
    assert h["hint"].startswith("Gợi ý")
    wrong = client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": wrong_of(gw, items[0]), "time_spent_sec": 20})
    res = wrong.json()
    assert res["correct"] is False and res["points"] == 0 and res["correct_answer"] == key_of(gw, items[0]["id"])
    assert "option_feedback" in res
    # idempotent: replaying (or changing) the answer returns the stored result and scores nothing twice
    again = client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": key_of(gw, items[0]["id"]), "time_spent_sec": 5})
    assert again.json()["correct"] is False
    # a hint after the answer was checked is refused
    assert client.post(f"{P}/sessions/{sid}/hint", json={"position": 0}).status_code == 409
    rev = client.post(f"{P}/sessions/{sid}/reveal", json={"position": 0}).json()
    assert rev["explanation"].startswith("Lời giải") and rev["tip"].startswith("Mẹo")
    ok = client.post(f"{P}/sessions/{sid}/answer", json={"position": 1, "answer": key_of(gw, items[1]["id"]), "time_spent_sec": 30}).json()
    assert ok["correct"] is True and ok["points"] == 1
    assert client.post(f"{P}/sessions/{sid}/flag", json={"position": 0, "flagged": True}).status_code == 403
    assert client.post(f"{P}/sessions/{sid}/answer", json={"position": 99, "answer": "A"}).status_code == 422
    # resume: first unanswered position, checked results restored, the hint stays attached to its item
    back = client.get(f"{P}/sessions/active", params={"subject": "math"}).json()
    assert back["id"] == sid and back["position"] == 2
    assert back["answers"]["0"]["checked"] and back["answers"]["0"]["hints_seen"] == 1
    assert back["answers"]["1"]["result"]["correct"] is True


def test_practice_true_false_and_short_answer_feedback(client, gw, thpt_user):
    from mentor_gateway.practice import assembler as asm

    def types(seed):
        a = asm.assemble_practice(gw.practice.bank, "math", {}, asm.Constraints(time_budget_sec=45 * 60), seed)
        return {x.item.type for x in a.items}

    seed = next((n for n in range(200) if {"TRUE_FALSE_GROUP", "SHORT_ANSWER"} <= types(n)), None)
    assert seed is not None
    s = start(client, kind="practice", subject="math", minutes=45, goal="balanced", seed=seed)
    items = s["items"]
    tf = next(i for i in items if i["type"] == "TRUE_FALSE_GROUP")
    sa = next(i for i in items if i["type"] == "SHORT_ANSWER")
    r = client.post(f"{P}/sessions/{s['id']}/answer", json={"position": tf["position"], "answer": "TTTF"}).json()
    assert r["correct"] is False and r["points"] == 0.5 and r["correct_answer"] == "TTFF"
    assert [x["correct"] for x in r["statement_results"]] == [True, True, False, True]
    assert tf["statements"][0].keys() == {"id", "text"}
    assert sa["short_answer"]["max_chars"] == 4
    r = client.post(f"{P}/sessions/{s['id']}/answer", json={"position": sa["position"], "answer": "-0.5"}).json()
    assert r["correct"] is True


def test_finish_writes_evidence_mastery_log_and_snapshots_once(client, gw, thpt_user):
    uid = thpt_user["user_id"]
    s = start(client, kind="practice", subject="math", minutes=10, goal="balanced", seed=2)
    sid, items = s["id"], s["items"]
    client.post(f"{P}/sessions/{sid}/hint", json={"position": 0})
    client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": key_of(gw, items[0]["id"]), "time_spent_sec": 20})
    for i in (1, 2, 3):
        ans = key_of(gw, items[i]["id"]) if i != 3 else wrong_of(gw, items[i])
        client.post(f"{P}/sessions/{sid}/answer", json={"position": i, "answer": ans, "time_spent_sec": 30})
    assert events_in_mirror(gw, uid) == []  # nothing is written before finish
    rep = client.post(f"{P}/sessions/{sid}/finish").json()
    assert (rep["correct"], rep["total"], rep["answered"], rep["hints"]) == (3, 4, 4, 1)
    assert rep["score_10"] is None and rep["minutes"] >= 1
    assert rep["per_topic"] and all({"topic", "title", "right", "total", "mastery_before", "mastery_after", "label"} <= set(t)
                                    for t in rep["per_topic"])
    assert rep["session"]["id"] == sid and rep["recommendations"]

    evs = events_in_mirror(gw, uid)
    assert len(evs) == 4 and {e.source_ref for e in evs} == {f"practice:{sid}"}
    assert {e.type for e in evs} == {"practice_item"} and {e.grader for e in evs} == {"bank"}
    by_pos = {e.event_id.split("-")[3]: e for e in evs}
    assert by_pos["0"].mode.value == "guided" and by_pos["0"].hint_count == 1  # a hint makes it process-only
    assert by_pos["1"].mode.value == "independent" and by_pos["3"].correct is False
    assert gw.mirror.history(uid, "events.jsonl", 1)[0].author == "system"

    # mastery files = what the sandbox script would write for the same events
    skills_md = gw.mirror.read_text(uid, "learning/math/skills.md")
    review_md = gw.mirror.read_text(uid, "learning/math/review-queue.md")
    assert skills_md and "| skill_id | Tên | Mastery | Bằng chứng | Lần cuối |" in skills_md and review_md
    work = Path(client.app.state.gw.settings.data_dir) / "bkt-check"
    work.mkdir(exist_ok=True)
    (work / "events.jsonl").write_text(gw.mirror.read_text(uid, "events.jsonl"), encoding="utf-8")
    cur = work / ".mentor" / "curricula"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "math.yaml").write_text((gw.settings.content_dir / "curricula" / "math.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    today = datetime.fromisoformat(rep["session"]["finished_at"]).astimezone().date()
    from mentor_gateway.practice.service import VN

    today = datetime.fromisoformat(rep["session"]["finished_at"]).astimezone(VN).date().isoformat()
    out = subprocess.run([sys.executable, "-m", "mentor_scripts.bkt_update"], input=json.dumps({"subject": "math", "today": today}),
                         cwd=work, capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["skills_updated"] >= 1
    assert (work / "learning" / "math" / "skills.md").read_text(encoding="utf-8") == skills_md
    assert (work / "learning" / "math" / "review-queue.md").read_text(encoding="utf-8") == review_md

    log = gw.mirror.read_text(uid, "learning/math/practice-log.md")
    line = [x for x in log.splitlines() if x.startswith("- ")][-1]
    assert "luyện tập 10 phút · 3/4 đúng · 1 gợi ý · chủ đề: " in line and line.endswith(f"session {sid}")

    from sqlalchemy import select

    from mentor_gateway.practice.tables import MasterySnapshot

    with gw.db.session() as db:
        snaps = db.scalars(select(MasterySnapshot).where(MasterySnapshot.user_id == uid)).all()
    assert snaps and {x.session_id for x in snaps} == {sid}

    # idempotent: finishing again returns the stored report and adds no evidence
    assert client.post(f"{P}/sessions/{sid}/finish").json() == rep
    assert len(events_in_mirror(gw, uid)) == 4
    assert [x["id"] for x in client.get(f"{P}/sessions").json()] == [sid]

    prog = client.get(f"{P}/progress", params={"subject": "math"}).json()
    touched = [k for k in prog["skills"] if k["evidence"]]
    assert touched and all(k["mastery"] is not None and k["trend"] for k in touched)
    assert all(k["label"] == "Chưa có dữ liệu" for k in prog["skills"] if not k["evidence"] and not k["guided"])
    assert {t["topic"] for t in prog["topics"]} == {"math.function", "math.exp-log", "math.integral"}
    review = client.get(f"{P}/sessions/{sid}/review").json()
    assert review[0]["explanation"] and review[0]["correct_answer"] and review[0]["hints_seen"] == 1


def test_finish_survives_a_concurrent_sandbox_commit(client, gw, thpt_user):
    """The mirror moves between our read and our commit (a sandbox push): the step is redone on a fresh read."""
    uid = thpt_user["user_id"]
    s = start(client, kind="practice", subject="math", minutes=10, seed=2)
    client.post(f"{P}/sessions/{s['id']}/answer", json={"position": 0, "answer": key_of(gw, s["items"][0]["id"])})
    real = gw.mirror.commit_files
    calls = {"n": 0}

    def racing(user_id, changes, **kw):
        if calls["n"] == 0:  # someone else commits first; our `expected` events.jsonl sha is now stale
            real(user_id, {"events.jsonl": b'{"event_id":"other"}\n'}, author="mentor", message="sandbox")
        calls["n"] += 1
        return real(user_id, changes, **kw)

    gw.mirror.commit_files = racing
    try:
        assert client.post(f"{P}/sessions/{s['id']}/finish").status_code == 200
    finally:
        gw.mirror.commit_files = real
    text = gw.mirror.read_text(uid, "events.jsonl")
    assert '"event_id":"other"' in text and f"practice-{s['id']}-0-" in text and calls["n"] == 2


def test_starting_a_new_practice_finishes_the_old_one_scored(client, gw, thpt_user):
    a = start(client, kind="practice", subject="math", minutes=10, seed=1)
    client.post(f"{P}/sessions/{a['id']}/answer", json={"position": 0, "answer": key_of(gw, a["items"][0]["id"])})
    b = start(client, kind="practice", subject="math", minutes=10, seed=1)
    assert b["id"] != a["id"]
    assert client.get(f"{P}/sessions/{a['id']}").json()["status"] == "finished"
    assert {i["id"] for i in a["items"]}.isdisjoint({i["id"] for i in b["items"]})  # replaced items are left out
    assert len(events_in_mirror(gw, thpt_user["user_id"])) >= 1
    # an unanswered practice is abandoned, not scored
    c = start(client, kind="practice", subject="math", minutes=10, seed=4)
    assert client.get(f"{P}/sessions/{b['id']}").json()["status"] == "abandoned"
    assert c["id"] != b["id"]


def test_mock_flow_drafts_flags_and_no_feedback(client, gw, thpt_user):
    s = start(client, kind="mock", subject="math", profile_id="math.mcq.t", seed=1)
    sid, items = s["id"], s["items"]
    assert len(items) == 9 and s["deadline"] and 590 <= s["remaining_sec"] <= 600 and s["disclaimer"]
    for i, it in enumerate(items):
        ans = key_of(gw, it["id"]) if i < 6 else wrong_of(gw, it)
        r = client.post(f"{P}/sessions/{sid}/answer", json={"position": i, "answer": ans, "time_spent_sec": 10})
        assert r.json() == {"saved": True}
    # answers are editable until finish
    client.post(f"{P}/sessions/{sid}/answer", json={"position": 8, "answer": key_of(gw, items[8]["id"])})
    assert client.post(f"{P}/sessions/{sid}/flag", json={"position": 2, "flagged": True}).json() == {"ok": True}
    assert client.post(f"{P}/sessions/{sid}/hint", json={"position": 0}).status_code == 403
    assert client.post(f"{P}/sessions/{sid}/reveal", json={"position": 0}).status_code == 403
    assert client.post(f"{P}/sessions/{sid}/tick", json={"position": 2, "elapsed_sec": 12}).json()["remaining_sec"] > 0
    back = client.get(f"{P}/sessions/{sid}").json()
    assert back["answers"]["2"]["flagged"] and back["answers"]["0"]["draft"] and "correct" not in back["answers"]["0"]
    assert client.get(f"{P}/sessions/{sid}/review").status_code == 409  # not before finish
    assert events_in_mirror(gw, thpt_user["user_id"]) == []  # the mentor never sees an unfinished mock
    rep = client.post(f"{P}/sessions/{sid}/finish").json()
    assert (rep["correct"], rep["total"]) == (7, 9) and rep["score_10"] == 7.78
    assert "thi thử · 7,78/10 · 7/9 đúng" in gw.mirror.read_text(thpt_user["user_id"], "learning/math/practice-log.md")
    assert all(e.mode.value == "independent" for e in events_in_mirror(gw, thpt_user["user_id"]))
    assert client.post(f"{P}/sessions/{sid}/answer", json={"position": 0, "answer": "A"}).status_code == 409


def test_mock_deadline_auto_finishes_on_next_request_and_by_sweep(client, gw, clock, thpt_user):
    s = start(client, kind="mock", subject="math", profile_id="math.mcq.t", seed=1)
    sid, items = s["id"], s["items"]
    for i in range(3):
        client.post(f"{P}/sessions/{sid}/answer", json={"position": i, "answer": key_of(gw, items[i]["id"])})
    clock.advance(seconds=603)
    late = client.post(f"{P}/sessions/{sid}/answer", json={"position": 4, "answer": key_of(gw, items[4]["id"])})
    assert late.status_code == 409 and late.json()["code"] == "expired"
    done = client.get(f"{P}/sessions/{sid}").json()
    assert done["status"] == "expired" and done["remaining_sec"] is None
    rep = client.post(f"{P}/sessions/{sid}/finish").json()
    assert (rep["correct"], rep["answered"], rep["total"]) == (3, 3, 9) and rep["score_10"] == 3.33  # blanks count 0
    assert client.get(f"{P}/sessions/active").json() is None

    # periodic sweep (scheduler hook) finishes it without any request
    s2 = start(client, kind="mock", subject="math", profile_id="math.mcq.t", seed=2)
    client.post(f"{P}/sessions/{s2['id']}/answer", json={"position": 0, "answer": key_of(gw, s2["items"][0]["id"])})
    clock.advance(seconds=700)
    assert gw.practice.sweep() == 1
    with gw.db.session() as db:
        from mentor_gateway.practice.tables import PracticeSession

        assert db.get(PracticeSession, s2["id"]).status == "expired"
    assert client.post(f"{P}/sessions/{s2['id']}/tick", json={"position": 0, "elapsed_sec": 1}).json() == {"remaining_sec": 0, "expired": True}


def test_a_running_mock_blocks_other_sessions_in_that_subject_and_survives_restart(client, gw, thpt_user):
    s = start(client, kind="mock", subject="math", profile_id="math.mcq.t", seed=1)
    client.post(f"{P}/sessions/{s['id']}/answer", json={"position": 0, "answer": "A"})
    r = client.post(f"{P}/sessions", json={"kind": "practice", "subject": "math", "minutes": 10})
    assert r.status_code == 409 and r.json()["code"] == "active_session" and r.json()["session_id"] == s["id"]
    from mentor_gateway.practice import PracticeService
    from mentor_gateway.practice.bank import Bank

    fresh = PracticeService(gw.db, gw.mirror, Bank(gw.settings.content_dir), gw.clock)  # a restarted gateway
    resumed = fresh.active(thpt_user["user_id"], "math")
    assert resumed["id"] == s["id"] and resumed["answers"]["0"]["draft"] == "A" and resumed["remaining_sec"] > 0


def test_three_part_mock_scores_parts_with_true_false_partial_credit(client, gw, thpt_user):
    s = start(client, kind="mock", subject="math", profile_id="math.parts.t", seed=1)
    sid = s["id"]
    assert [p["label"] for p in s["parts"]] == ["Phần I", "Phần II", "Phần III"]
    assert [len(p["positions"]) for p in s["parts"]] == [6, 3, 3] and s["parts"][1]["points_each"] == 1.0
    for it in s["items"]:
        ans = "TTTF" if it["type"] == "TRUE_FALSE_GROUP" else key_of(gw, it["id"])  # 3 of 4 statements: 0.5
        client.post(f"{P}/sessions/{sid}/answer", json={"position": it["position"], "answer": ans})
    rep = client.post(f"{P}/sessions/{sid}/finish").json()
    parts = {p["part"]: p for p in rep["per_part"]}
    assert (parts[1]["points"], parts[2]["points"], parts[3]["points"]) == (1.5, 1.5, 1.5)
    assert parts[2]["correct"] == 0 and parts[2]["answered"] == 3 and rep["score_10"] == 7.5
    assert rep["disclaimer"] == "Đề 3 phần luyện tập."


def test_diagnostic_and_skip(client, gw, thpt_user):
    d = start(client, kind="diagnostic", subject="math", seed=1)
    assert len(d["items"]) == 6 and d["deadline"] and all(i["type"] == "SINGLE_CHOICE" for i in d["items"])
    r = client.post(f"{P}/sessions/{d['id']}/answer", json={"position": 0, "answer": key_of(gw, d["items"][0]["id"])})
    assert r.json() == {"saved": True}
    assert client.post(f"{P}/sessions/{d['id']}/hint", json={"position": 0}).status_code == 403
    rep = client.post(f"{P}/sessions/{d['id']}/finish").json()
    assert rep["answered"] == 1 and rep["score_10"] is None
    assert client.get(f"{P}/subjects").json()[0]["diagnostic"] == "done"
    assert "đánh giá nhanh · 1/1 đúng" in gw.mirror.read_text(thpt_user["user_id"], "learning/math/practice-log.md")


def test_skip_diagnostic_and_recommendations(client, gw, thpt_user):
    recs = client.get(f"{P}/recommendations", params={"subject": "math"}).json()
    assert [r["code"] for r in recs] == ["TAKE_DIAGNOSTIC"] and recs[0]["reason"].startswith("Vì sao:")
    assert client.post(f"{P}/diagnostic/skip", json={"subject": "math"}).json() == {"ok": True}
    assert client.get(f"{P}/subjects").json()[0]["diagnostic"] == "skipped"
    assert [r["code"] for r in client.get(f"{P}/recommendations", params={"subject": "math"}).json()] == ["PROBE_UNKNOWN"]


def test_take_a_break_after_two_hours_of_practice_today(client, gw, thpt_user):
    for seed in (1, 2):
        s = start(client, kind="practice", subject="math", minutes=10, seed=seed)
        client.post(f"{P}/sessions/{s['id']}/answer",
                    json={"position": 0, "answer": key_of(gw, s["items"][0]["id"]), "time_spent_sec": 3600})
        client.post(f"{P}/sessions/{s['id']}/finish")
    recs = client.get(f"{P}/recommendations").json()
    assert recs[0]["code"] == "TAKE_A_BREAK" and recs[0]["action"]["kind"] == "break"


def test_item_reports_only_after_the_answer_was_shown_and_capped_per_day(client, gw, clock, thpt_user):
    s = start(client, kind="practice", subject="math", minutes=20, seed=1)
    sid, items = s["id"], s["items"]
    url = f"{P}/items/{items[0]['id']}/report"
    r = client.post(url, json={"session_id": sid, "reason": "typo"})
    assert r.status_code == 409 and r.json()["code"] == "answer_not_shown"
    for i in range(3):
        client.post(f"{P}/sessions/{sid}/answer", json={"position": i, "answer": key_of(gw, items[i]["id"])})
    ok = client.post(url, json={"session_id": sid, "reason": "typo", "note": "sai chính tả"})
    assert ok.status_code == 200 and ok.json()["status"] == "open"
    assert client.post(url, json={"session_id": sid, "reason": "typo"}).json()["id"] == ok.json()["id"]  # same report twice
    assert client.post(url, json={"session_id": sid, "reason": "bogus"}).status_code == 422
    other = client.post(f"{P}/items/math.nope.001/report", json={"session_id": sid, "reason": "typo"})
    assert other.status_code == 404
    reasons = ["wrong_key", "wrong_solution", "unclear", "other"]
    n = 1
    for it in items[:3]:
        for reason in ["typo", *reasons]:
            if (it is items[0] and reason == "typo"):
                continue
            r = client.post(f"{P}/items/{it['id']}/report", json={"session_id": sid, "reason": reason})
            if n < 10:
                assert r.status_code == 200, (n, r.text)
            n += 1
            if n > 10:
                break
        if n > 10:
            break
    assert r.status_code == 429 and r.json()["code"] == "report_limit"
    assert len(client.get(f"{P}/items/reports").json()) == 10
    clock.advance(days=1)  # the limit is per calendar day
    assert client.post(f"{P}/items/{items[2]['id']}/report", json={"session_id": sid, "reason": "typo"}).status_code == 200


def test_reports_after_a_finished_mock_and_other_learners_sessions_are_private(client, gw, thpt_user):
    s = start(client, kind="mock", subject="math", profile_id="math.mcq.t", seed=1)
    item = s["items"][0]["id"]
    assert client.post(f"{P}/items/{item}/report", json={"session_id": s["id"], "reason": "unclear"}).status_code == 409
    client.post(f"{P}/sessions/{s['id']}/finish")
    assert client.post(f"{P}/items/{item}/report", json={"session_id": s["id"], "reason": "unclear"}).status_code == 200
    client.post("/api/auth/logout")
    from gateway_fakes import onboard, verify_parent

    me = onboard(client, "other@example.com", "thpt")
    verify_parent(client, me["user_id"])
    assert client.get(f"{P}/sessions/{s['id']}").status_code == 404
    assert client.get(f"{P}/items/reports").json() == []


def test_account_deletion_removes_practice_rows(client, gw, thpt_user):
    s = start(client, kind="practice", subject="math", minutes=10, seed=1)
    client.post(f"{P}/sessions/{s['id']}/answer", json={"position": 0, "answer": "A"})
    client.post(f"{P}/sessions/{s['id']}/finish")
    assert client.delete("/api/account").status_code == 200
    from sqlalchemy import func, select

    from mentor_gateway.practice.tables import PracticeAnswer, PracticeSession

    with gw.db.session() as db:
        assert db.scalar(select(func.count()).select_from(PracticeSession)) == 0
        assert db.scalar(select(func.count()).select_from(PracticeAnswer)) == 0
