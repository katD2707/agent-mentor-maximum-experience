"""Practice and mock chat cards (CONTRACTS 10.5) and named-conversation (c-*) history reload."""

import json
from pathlib import Path

import pytest
from harness_helpers import collect, turn_request
from mentor_harness import cards
from mentor_harness.model import ScriptedModel
from mentor_harness.workspace import Workspace
from mentor_schemas import JobKind, JobRequest, Profile

PRACTICE = {"subject": "math", "minutes": 20, "goal": "weak", "topics": ["exp-log"], "title": "Ôn mũ - log",
            "reason": "Tuần trước đúng 4/10 câu mũ - log."}
MOCK = {"subject": "math", "profile_id": "math.mcq-mock.2026", "title": "Thi thử Toán 50 phút"}


def results(model: ScriptedModel, n: int = 1) -> list[str]:
    return [m["content"] for m in model.calls[-1].messages if m["role"] == "tool"][-n:]


def test_validate_practice_and_mock(ws: Workspace) -> None:
    ok = cards.validate("practice", PRACTICE, ws)
    assert ok == PRACTICE
    default = cards.validate("practice", {k: v for k, v in PRACTICE.items() if k not in ("goal", "topics")}, ws)
    assert default["goal"] == "balanced" and "topics" not in default
    assert cards.validate("mock", MOCK, ws) == MOCK
    bad = [
        ("practice", {**PRACTICE, "subject": "chemistry"}), ("practice", {**PRACTICE, "minutes": 15}),
        ("practice", {**PRACTICE, "minutes": True}), ("practice", {**PRACTICE, "goal": "easy"}),
        ("practice", {**PRACTICE, "topics": ["Hàm số"]}), ("practice", {**PRACTICE, "extra": 1}),
        ("practice", {**PRACTICE, "title": ""}), ("practice", {**PRACTICE, "reason": "x" * 201}),
        ("mock", {**MOCK, "profile_id": "physics.mcq-mock.2026"}), ("mock", {**MOCK, "profile_id": "../x"}),
        ("mock", {**MOCK, "subject": "art"}), ("mock", {"subject": "math", "title": "a"}),
    ]
    for kind, data in bad:
        with pytest.raises(cards.CardError):
            cards.validate(kind, data, ws)
    assert cards.describe({"kind": "mock", **MOCK}).startswith("mock (Thi thử Toán")


async def test_show_card_practice_in_turn_and_history_note(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([ScriptedModel.call("show_card", kind="practice", data=PRACTICE),
                           ScriptedModel.call("show_card", kind="mock", data=MOCK), "Bạn bấm vào thẻ nhé."])
    events = await collect(make_harness(model), turn_request(session_id="c-0123456789ab"))
    shown = [e.card for e in events if e.type == "card"]
    assert [c["kind"] for c in shown] == ["practice", "mock"] and shown[0]["goal"] == "weak"
    assert "không tự bắt đầu" in results(model, 1)[0]
    ws = Workspace(ws_root)
    saved = ws.load_chat("c-0123456789ab", 10)
    assert [r["role"] for r in saved] == ["user", "card", "card", "mentor"]


async def test_notification_action_job_may_show_practice_card(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([ScriptedModel.call("show_card", kind="mock", data=MOCK), "Xong."])
    req = JobRequest(job_id="j1", user_id="u1", kind=JobKind.ROUTINE, profile=Profile.STUDENT, prompt="x",
                     payload={"source": "notification_action", "action": "answer:A"})
    result = await make_harness(model).run_job(req)
    assert [c["kind"] for c in result.cards] == ["mock"]
    plain = ScriptedModel([ScriptedModel.call("show_card", kind="mock", data=MOCK), "Xong."])
    plain_result = await make_harness(plain).run_job(JobRequest(job_id="j2", user_id="u1", kind=JobKind.ROUTINE, profile=Profile.STUDENT,
                                                                prompt="x", payload={}))
    assert plain_result.cards == [] and "job nền" in results(plain)[0]


async def test_conversation_history_reloads_across_days_and_restart(make_harness, ws_root: Path) -> None:
    sid = "c-0123456789ab"
    ws = Workspace(ws_root)
    day = lambda d: ws.root / f"sessions/2026-10-{d}"
    for d, rows in (("20", [("user", "một"), ("mentor", "hai")]), ("21", [("user", "ba"), ("mentor", "bốn")])):
        day(d).mkdir(parents=True)
        (day(d) / f"{sid}.jsonl").write_text(
            "".join(json.dumps({"ts": f"2026-10-{d}T10:00:00+07:00", "role": r, "text": t, "attachments": []},
                               ensure_ascii=False) + "\n" for r, t in rows), encoding="utf-8")
    other = day("21") / "c-ffffffffffff.jsonl"
    other.write_text(json.dumps({"ts": "x", "role": "user", "text": "khác", "attachments": []}) + "\n", encoding="utf-8")
    model = ScriptedModel(["Ok."])
    await collect(make_harness(model), turn_request("năm", session_id=sid))  # a fresh harness = after a restart
    history = [(m["role"], m["content"]) for m in model.calls[0].messages[1:]]
    assert history == [("user", "một"), ("assistant", "hai"), ("user", "ba"), ("assistant", "bốn"), ("user", "năm")]
