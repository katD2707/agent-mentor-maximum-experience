"""Chat interaction layer (CONTRACTS section 9): quick replies, cards, focus sessions, celebrations."""

import json
from pathlib import Path

from harness_helpers import collect, turn_request
from mentor_harness.config import now_local
from mentor_harness.model import ScriptedModel, ToolCall
from mentor_harness.tools import TURN_ONLY_TOOLS, tool_specs
from mentor_schemas import CardAction, JobKind, JobRequest, OutboxKind, Profile, TurnRequest
from mentor_schemas.interaction import chat_path

QUEUE = """# Lịch ôn tập — math

## Đến hạn hôm nay hoặc quá hạn

| skill_id | Tên | Mastery | Đến hạn | Ghi chú |
|---|---|---|---|---|
| algebra.quadratic.formula | Công thức nghiệm | 0.40 | 2026-11-01 | lần gần nhất làm sai |
"""
FLASH = {"skill": "algebra.quadratic.formula", "front": "Nghiệm của x**2 - 5*x + 6 = 0?",
         "choices": ["x = 1; x = 6", "x = 2; x = 3", "x = -2; x = -3"], "reveal": "B. x = 2; x = 3"}


def chat_records(root: Path, session: str = "s1") -> list[dict]:
    path = root / "sessions" / now_local().date().isoformat() / f"{session}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tool_results(model: ScriptedModel, call: int = -1) -> list[str]:
    return [m["content"] for m in model.calls[call].messages if m.get("role") == "tool"]


def write_queue(root: Path) -> None:
    (root / "learning/math").mkdir(parents=True, exist_ok=True)
    (root / "learning/math/review-queue.md").write_text(QUEUE, encoding="utf-8")


def test_specs_turn_only_and_jobs() -> None:
    assert {"suggest_replies", "start_focus", "celebrate"} <= TURN_ONLY_TOOLS
    for profile in Profile:
        turn = {s["function"]["name"] for s in tool_specs(profile, is_turn=True)}
        job = {s["function"]["name"] for s in tool_specs(profile, is_turn=False)}
        assert {"suggest_replies", "show_card", "start_focus", "celebrate"} <= turn
        assert "show_card" in job and not {"suggest_replies", "start_focus", "celebrate"} & job
    wake = next(s for s in tool_specs(Profile.STUDENT, is_turn=True) if s["function"]["name"] == "schedule_wake")
    assert "focus_end" not in wake["function"]["parameters"]["properties"]["job_kind"]["enum"]


async def test_suggestions_sent_before_done_and_kept_on_message(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([
        ScriptedModel.call("suggest_replies", items=[{"label": "a" * 41}]),
        ScriptedModel.call("suggest_replies", items=[{"label": "Có", "text": "Có, mình muốn"}, {"label": "Để sau"}]),
        "Em muốn ôn tiếp không?",
    ])
    events = await collect(make_harness(model), turn_request())
    assert tool_results(model)[0].startswith("LỖI")  # label too long
    types = [e.type for e in events]
    assert types[-2:] == ["suggestions", "done"] and "tool_started" not in types
    assert events[-2].items == [{"label": "Có", "text": "Có, mình muốn"}, {"label": "Để sau", "text": "Để sau"}]
    mentor = chat_records(ws_root)[-1]
    assert mentor["role"] == "mentor" and mentor["suggestions"] == events[-2].items


async def test_flashcard_validation_order_and_card_action(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([ScriptedModel.call("show_card", kind="flashcard", data=FLASH), "Hỏi bằng chữ vậy."])
    harness = make_harness(model)
    await collect(harness, turn_request())  # no review queue yet
    assert "review-queue" in tool_results(model)[0]

    write_queue(ws_root)
    show = ToolCall("c1", "show_card", json.dumps({"kind": "flashcard", "data": FLASH}))
    model.push(
        ScriptedModel.call("show_card", kind="flashcard", data={**FLASH, "choices": ["1", "2", "3", "4", "5"]}),
        ScriptedModel.call("show_card", kind="focus", data={"task": "x"}),
        ScriptedModel.call("show_card", kind="flashcard", data={**FLASH, "extra": 1}),
        ScriptedModel.multi(show, content="Câu hỏi nhanh:"),  # text, then the card, then more text
        "Chọn một đáp án nhé.",
    )
    events = await collect(harness, turn_request("ôn nhanh"))
    errors = tool_results(model)[-4:-1]  # this turn's three refused calls
    assert all(e.startswith("LỖI") for e in errors) and "start_focus" in errors[1]
    card_events = [e for e in events if e.type == "card"]
    assert len(card_events) == 1
    card = card_events[0].card
    assert card["kind"] == "flashcard" and card["id"].startswith(f"card-{now_local():%Y%m%d}-")
    assert card["choices"] == FLASH["choices"] and card["created_at"]
    records = chat_records(ws_root)[-4:]
    assert [r["role"] for r in records] == ["user", "mentor", "card", "mentor"]
    assert records[1]["text"] == "Câu hỏi nhanh:" and records[3]["text"] == "Chọn một đáp án nhé."
    assert records[2]["card"] == card

    # the learner clicks B: the model sees the [card:...] line plus the card, history stores the echo
    model.push("Đúng rồi!")
    act = CardAction(card_id=card["id"], kind="flashcard", action="answer", value="B", echo="Đã chọn: B. x = 2; x = 3")
    req = TurnRequest(session_id="s1", user_id="u1", profile=Profile.STUDENT, text="[card:flashcard answer B]",
                      card_action=act)
    await collect(harness, req)
    seen = model.calls[-1].messages[-1]["content"]
    assert seen.startswith("[card:flashcard answer B]") and "B. x = 2; x = 3" in seen and "record_event" in seen
    user = chat_records(ws_root)[-2]
    assert user["text"] == "Đã chọn: B. x = 2; x = 3" and user["card_action"]["card_id"] == card["id"]

    # after a restart the reloaded history has the card note and the [card:...] text, not the echo
    fresh = make_harness(ScriptedModel(["ok"]))
    await collect(fresh, turn_request("tiếp"))
    history = "\n".join(m["content"] for m in fresh.model.calls[0].messages[1:])
    assert "[đã hiện thẻ flashcard" in history and "[card:flashcard answer B]" in history


async def test_celebrate_once_per_turn(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([
        ScriptedModel.call("celebrate", title="Xong chương 1"),
        ScriptedModel.call("celebrate", title="Lần hai"),
        "Giỏi lắm.",
    ])
    events = await collect(make_harness(model), turn_request())
    assert "một lần" in tool_results(model)[1]  # max 1 per turn
    assert len([e for e in events if e.type == "card"]) == 1


async def test_celebration_shown_last(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([ScriptedModel.call("celebrate", title="Nộp xong bài báo", detail="Sau 3 tháng"), "Chúc mừng!"])
    events = await collect(make_harness(model), turn_request(profile=Profile.STUDENT))
    cards = [e.card for e in events if e.type == "card"]
    assert cards and cards[0]["kind"] == "celebration" and cards[0]["detail"] == "Sau 3 tháng"
    assert [r["role"] for r in chat_records(ws_root)][-2:] == ["mentor", "card"]


async def test_start_focus_extend_done(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([
        ScriptedModel.call("start_focus", task="Ôn hàm số", minutes=3),
        ScriptedModel.call("start_focus", task="Ôn hàm số", minutes=25),
        "Bắt đầu nhé!",
    ])
    harness = make_harness(model)
    events = await collect(harness, turn_request())
    assert tool_results(model)[0].startswith("LỖI")
    card = next(e.card for e in events if e.type == "card")
    assert card["kind"] == "focus" and card["minutes"] == 25 and card["task"] == "Ôn hàm số"
    wake = events[-1].outbox[0]
    assert wake.kind == OutboxKind.NEXT_WAKE and wake.payload["job_kind"] == "focus_end"
    assert wake.payload["at"] == card["ends_at"] and wake.payload["card_id"] == card["id"]
    assert '"action":"start_focus"' in (ws_root / ".mentor/activity.jsonl").read_text(encoding="utf-8")

    def click(action: str, value: str | None = None) -> TurnRequest:
        act = CardAction(card_id=card["id"], kind="focus", action=action, value=value, echo=action)
        return TurnRequest(session_id="s1", user_id="u1", profile=Profile.STUDENT, text=f"[card:focus {action}]",
                           card_action=act)

    model.push("Thêm 10 phút nhé.")
    events = await collect(harness, click("extend", "10"))
    updated = next(e.card for e in events if e.type == "card")
    assert updated["id"] == card["id"] and updated["minutes"] == 35 and updated["ends_at"] > card["ends_at"]
    assert events[-1].outbox[0].payload["at"] == updated["ends_at"]
    model.push("Giỏi lắm!")
    events = await collect(harness, click("done"))
    ended = next(e.card for e in events if e.type == "card")
    assert ended["ended_at"] and ended["minutes"] == 35
    assert "kết thúc phiên" in model.calls[-1].messages[-1]["content"]

    # the stale wake finds the session ended and skips without calling the model
    calls = len(model.calls)
    res = await harness.run_job(JobRequest(job_id="f1", user_id="u1", profile=Profile.STUDENT, kind=JobKind.FOCUS_END,
                                           payload={"card_id": card["id"]}))
    assert res.status == "skipped" and len(model.calls) == calls


async def test_focus_end_job_notifies(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([ScriptedModel.call("start_focus", task="Đọc paper", minutes=5), "Bắt đầu!"])
    harness = make_harness(model)
    events = await collect(harness, turn_request(profile=Profile.STUDENT))
    card = next(e.card for e in events if e.type == "card")
    # pretend the session has run out
    path = ws_root / "sessions" / now_local().date().isoformat() / "s1.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace(card["ends_at"], now_local().isoformat()),
                    encoding="utf-8")
    model.push(ScriptedModel.call("notify_user", text="Hết giờ rồi, đọc tới đâu rồi?"), "Đã hỏi thăm.")
    job = JobRequest(job_id="f2", user_id="u1", profile=Profile.STUDENT, kind=JobKind.FOCUS_END,
                     payload={"card_id": card["id"], "task": "Đọc paper", "minutes": 5})
    res = await harness.run_job(job)
    assert res.status == "ok" and "Đọc paper" in model.calls[-1].messages[1]["content"]
    nudges = [o for o in res.outbox if o.kind == OutboxKind.NOTIFY_USER]
    assert len(nudges) == 1 and nudges[0].payload["kind"] == "focus_end"
    assert [a["id"] for a in nudges[0].payload["actions"]] == ["done", "start_focus", "snooze_1h"]
    assert nudges[0].payload["focus"]["card_id"] == card["id"]
    # the model forgot to notify: the harness adds the check-in itself
    model.push("Xong.")
    res = await harness.run_job(job.model_copy(update={"job_id": "f3"}))
    nudges = [o for o in res.outbox if o.kind == OutboxKind.NOTIFY_USER]
    assert len(nudges) == 1 and nudges[0].payload["kind"] == "focus_end" and "Đọc paper" in nudges[0].payload["text"]


async def test_job_cards_go_to_todays_chat(make_harness, ws_root: Path) -> None:
    write_queue(ws_root)
    model = ScriptedModel([
        ScriptedModel.call("show_card", kind="flashcard", data=FLASH),
        ScriptedModel.call("show_card", kind="checkin", data={"prompt": "Hôm nay ưu tiên gì?", "options": ["Toán", "Văn"]}),
        ScriptedModel.call("show_card", kind="weekly", data={"milestones_done": 2, "mistakes_fixed": 1,
                                                             "highlight": "Tự giải được dạng khó"}),
        "Đã gửi tổng kết tuần.",
    ])
    res = await make_harness(model).run_job(
        JobRequest(job_id="w1", user_id="u1", profile=Profile.STUDENT, kind=JobKind.ROUTINE, prompt="weekly-review"))
    assert "Trong job nền" in tool_results(model)[0]
    assert [c["kind"] for c in res.cards] == ["checkin", "weekly"]
    weekly = res.cards[1]
    assert weekly["focus_minutes"] == 0 and weekly["streak_days"] == 0 and weekly["milestones_done"] == 2
    day = now_local().date()
    records = [json.loads(line) for line in (ws_root / chat_path(day)).read_text(encoding="utf-8").splitlines()]
    assert [r["card"] for r in records] == res.cards and all(r["role"] == "card" for r in records)


def _routine(job_id: str, payload: dict | None = None, **kw) -> JobRequest:
    return JobRequest(job_id=job_id, user_id="u1", profile=Profile.STUDENT, kind=JobKind.ROUTINE, prompt="x",
                      payload=payload or {}, **kw)


NOTIFICATION_JOB = {"source": "notification_action", "action": "start_focus", "notification_id": 7,
                    "notification_kind": "focus_end"}


async def test_start_focus_only_in_learner_started_jobs(make_harness, ws_root: Path) -> None:
    model = ScriptedModel([
        ScriptedModel.call("start_focus", task="Ôn hàm số", minutes=25),
        ScriptedModel.call("show_card", kind="celebration", data={"title": "Xong 3 việc"}),
        "Đã bắt đầu.",
    ])
    harness = make_harness(model)
    res = await harness.run_job(_routine("n7", NOTIFICATION_JOB))
    names = {t["function"]["name"] for t in model.calls[0].tools}
    assert {"start_focus", "celebrate"} <= names and "suggest_replies" not in names
    assert [c["kind"] for c in res.cards] == ["focus", "celebration"]  # celebration last
    wake = next(o for o in res.outbox if o.kind == OutboxKind.NEXT_WAKE)
    assert wake.payload["job_kind"] == "focus_end" and wake.payload["card_id"] == res.cards[0]["id"]
    saved = (ws_root / chat_path(now_local().date())).read_text(encoding="utf-8")
    assert res.cards[0]["id"] in saved and res.cards[1]["id"] in saved

    # any other unattended job: not offered, and refused if called anyway
    model.push(
        ScriptedModel.call("start_focus", task="Ôn hàm số", minutes=25),
        ScriptedModel.call("show_card", kind="celebration", data={"title": "Xong"}),
        "Xong.",
    )
    other = _routine("r1", {"source": "routine", "action": "start_focus"})
    res = await harness.run_job(other)
    assert "start_focus" not in {t["function"]["name"] for t in model.calls[-3].tools}
    assert all(r.startswith("LỖI") for r in tool_results(model)[-2:]) and res.cards == []
    res = await harness.run_job(JobRequest(job_id="w9", user_id="u1", profile=Profile.STUDENT,
                                           kind=JobKind.NIGHTLY_REFLECTION, payload=NOTIFICATION_JOB))
    assert "start_focus" not in {t["function"]["name"] for t in model.calls[-1].tools}


async def test_job_checkin_card_keeps_line_breaks(make_harness) -> None:
    model = ScriptedModel([
        ScriptedModel.call("show_card", kind="checkin",
                           data={"prompt": "3 việc hôm nay:\n1) Ôn   toán\n2) Đọc", "options": ["Chốt", "Đổi"]}),
        "Xong.",
    ])
    res = await make_harness(model).run_job(_routine("w1"))
    assert [c["kind"] for c in res.cards] == ["checkin"]
    assert res.cards[0]["prompt"] == "3 việc hôm nay:\n1) Ôn toán\n2) Đọc"  # line breaks kept