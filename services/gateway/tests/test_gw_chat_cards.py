"""Chat interaction layer on the gateway (CONTRACTS section 9): card/suggestion relay, cards in the history,
card_action -> turn, focus wake-ups cancelled."""

import json
from datetime import timedelta

from gateway_fakes import FakeSandbox, harness_commit, recv_until
from mentor_schemas import SandboxEvent

from mentor_gateway.db import JobRow

DAY = "2026-10-28"  # conftest clock: 2026-10-28 10:00 Asia/Ho_Chi_Minh
CHAT = f"sessions/{DAY}/s-20261028.jsonl"
CARD = {"id": "card-20261028-a1b2c3d4e5f6", "kind": "flashcard", "created_at": f"{DAY}T10:00:05+07:00",
        "skill": "algebra.quadratic.formula", "front": "Nghiệm của x**2 - 5*x + 6 = 0?",
        "choices": ["x = 1; x = 6", "x = 2; x = 3", "x = -2; x = -3"], "reveal": "B"}
FOCUS = {"id": "card-20261028-0123456789ab", "kind": "focus", "created_at": f"{DAY}T10:00:05+07:00",
         "task": "Ôn hàm số", "minutes": 25, "ends_at": f"{DAY}T10:25:05+07:00"}
SUGGESTIONS = [{"label": "Có", "text": "Có, mình muốn ôn tiếp"}]


def install_turn(sandbox: FakeSandbox, monkeypatch, cards: list[dict]) -> None:
    """The fake harness: text, the cards, more text, quick replies; writes the transcript like the real one."""

    async def turn_events(req):
        ws = sandbox.workspaces[req.user_id]
        path = ws / CHAT
        path.parent.mkdir(parents=True, exist_ok=True)
        user_text = req.card_action.echo if req.card_action else req.text
        records = [{"ts": f"{DAY}T10:00:00+07:00", "role": "user", "text": user_text, "attachments": []},
                   {"ts": f"{DAY}T10:00:04+07:00", "role": "mentor", "text": "Câu hỏi:", "attachments": []}]
        records += [{"ts": c["created_at"], "role": "card", "card": c} for c in cards]
        records.append({"ts": f"{DAY}T10:00:09+07:00", "role": "mentor", "text": "Chọn nhé", "attachments": [],
                        "suggestions": SUGGESTIONS})
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        yield FakeSandbox._sse(SandboxEvent(type="text_delta", text="Câu hỏi:"))
        for c in cards:
            yield FakeSandbox._sse(SandboxEvent(type="card", card=c))
        yield FakeSandbox._sse(SandboxEvent(type="text_delta", text="\n\nChọn nhé"))
        yield FakeSandbox._sse(SandboxEvent(type="suggestions", items=SUGGESTIONS))
        harness_commit(ws, f"turn {req.session_id}")
        yield FakeSandbox._sse(SandboxEvent(type="done"))

    monkeypatch.setattr(sandbox, "_turn_events", turn_events)


def _send(ws, msg: dict) -> list[dict]:
    ws.send_json(msg)
    return recv_until(ws, "turn_done")


def test_cards_relayed_and_in_history(client, thpt_user, sandbox, monkeypatch):
    install_turn(sandbox, monkeypatch, [CARD])
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        msgs = _send(ws, {"type": "user_message", "client_msg_id": "c1", "text": "ôn nhanh", "attachments": []})
    types = [m["type"] for m in msgs if m["type"] != "sandbox_status"]
    assert types == ["text_delta", "card", "text_delta", "suggestions", "turn_done"]
    assert msgs[[m["type"] for m in msgs].index("card")]["card"] == CARD
    assert {"type": "suggestions", "client_msg_id": "c1", "items": SUGGESTIONS} in msgs

    hist = client.get("/api/chat/history", params={"date": DAY}).json()
    assert [h["role"] for h in hist] == ["user", "mentor", "card", "mentor"]
    assert hist[2] == {"ts": CARD["created_at"], "role": "card", "card": CARD}
    assert hist[3]["suggestions"] == SUGGESTIONS and "suggestions" not in hist[1]


def test_card_action_runs_a_turn(client, thpt_user, sandbox, monkeypatch):
    install_turn(sandbox, monkeypatch, [CARD])
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _send(ws, {"type": "user_message", "client_msg_id": "c1", "text": "ôn nhanh", "attachments": []})
        msgs = _send(ws, {"type": "card_action", "card_id": CARD["id"], "action": "answer", "value": "b",
                          "client_msg_id": "c2"})
    echo = next(m for m in msgs if m["type"] == "card_echo")
    assert echo == {"type": "card_echo", "client_msg_id": "c2", "card_id": CARD["id"], "action": "answer",
                    "value": "B", "text": "Đã chọn: B. x = 2; x = 3"}
    assert msgs[-1] == {"type": "turn_done", "client_msg_id": "c2"}
    req = sandbox.turns[-1]
    assert req.text == "[card:flashcard answer B]"
    assert req.card_action.card_id == CARD["id"] and req.card_action.echo == "Đã chọn: B. x = 2; x = 3"
    hist = client.get("/api/chat/history", params={"date": DAY}).json()
    clicked = [h for h in hist if h["role"] == "user"][-1]
    assert clicked["text"] == "Đã chọn: B. x = 2; x = 3"
    assert [h["card"]["id"] for h in hist if h["role"] == "card"] == [CARD["id"]]  # the repeat is one card


def test_unknown_card_or_action_rejected(client, thpt_user, sandbox, monkeypatch):
    install_turn(sandbox, monkeypatch, [CARD])
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _send(ws, {"type": "user_message", "client_msg_id": "c1", "text": "ôn nhanh", "attachments": []})
        turns = len(sandbox.turns)
        for bad in ({"card_id": "card-20261028-ffffffffffff", "action": "answer", "value": "A"},
                    {"card_id": "../../etc/passwd", "action": "answer", "value": "A"},
                    {"card_id": CARD["id"], "action": "extend"},
                    {"card_id": CARD["id"], "action": "answer", "value": "E"}):
            ws.send_json({"type": "card_action", **bad})
            err = ws.receive_json()
            assert err["type"] == "error" and err["card_id"] == bad["card_id"], bad
    assert len(sandbox.turns) == turns


def test_unknown_card_message(client, thpt_user, sandbox):
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "card_action", "card_id": "card-20261028-ffffffffffff", "action": "answer"})
        err = ws.receive_json()
    assert err == {"type": "error", "error": "Không tìm thấy thẻ này trong cuộc trò chuyện.",
                   "card_id": "card-20261028-ffffffffffff"}
    assert sandbox.turns == []


def test_focus_done_cancels_wake(client, thpt_user, sandbox, monkeypatch, gw, clock):
    uid = thpt_user["user_id"]
    install_turn(sandbox, monkeypatch, [FOCUS])
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _send(ws, {"type": "user_message", "client_msg_id": "c1", "text": "tập trung 25 phút", "attachments": []})
        gw.dispatcher.schedule_wake(uid, {"at": FOCUS["ends_at"], "job_kind": "focus_end", "card_id": FOCUS["id"],
                                          "task": FOCUS["task"], "minutes": 25})
        gw.dispatcher.schedule_wake(uid, {"at": FOCUS["ends_at"], "job_kind": "focus_end",
                                          "card_id": "card-20261028-999999999999", "task": "khác", "minutes": 5})
        msgs = _send(ws, {"type": "card_action", "card_id": FOCUS["id"], "action": "done"})
    assert next(m for m in msgs if m["type"] == "card_echo")["text"] == "Đã xong phiên tập trung"
    assert sandbox.turns[-1].text == "[card:focus done]"
    with gw.db.session() as s:
        rows = {r.payload["card_id"]: r.status for r in s.query(JobRow).filter(JobRow.kind == "focus_end")}
    assert rows == {FOCUS["id"]: "cancelled", "card-20261028-999999999999": "pending"}


def test_notification_action_job_is_marked(client, gw, ncs_user, sandbox):
    """start_focus on a notification enqueues a job the harness recognizes as learner-started."""
    from mentor_schemas import OutboxItem, OutboxKind, Profile

    uid = ncs_user["user_id"]
    nudge = {"text": "Hết 25 phút tập trung", "kind": "focus_end", "title": "Hết giờ tập trung",
             "actions": [{"id": "done", "label": "Xong rồi"}, {"id": "start_focus", "label": "Thêm một phiên"}],
             "focus": {"card_id": FOCUS["id"], "task": "Ôn hàm số", "minutes": 25}}
    gw.settings.vapid_public_key = None  # push off: delivered over the WebSocket only
    client.portal.call(gw.dispatcher.dispatch, uid, Profile.NCS, [OutboxItem(kind=OutboxKind.NOTIFY_USER,
                                                                              payload=nudge)])
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()  # sandbox_status
        nid = ws.receive_json()["id"]  # the notification
    job_id = client.post(f"/api/notifications/{nid}/action", json={"action": "start_focus"}).json()["job_id"]
    client.portal.call(gw.runner.drain)
    job = next(j for j in sandbox.jobs if j.job_id == job_id)
    assert job.payload["source"] == "notification_action" and job.payload["action"] == "start_focus"
    assert job.crisis_hold is False


def test_crisis_hold_reaches_sandbox_and_filters_job_cards(client, gw, thpt_user, sandbox, monkeypatch):
    from mentor_schemas import JobKind, JobRequest, JobResult

    from mentor_gateway.sandbox import SandboxClient

    uid = thpt_user["user_id"]
    gw.hub.set_hold(uid, gw.clock() + timedelta(hours=24))
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _send(ws, {"type": "user_message", "client_msg_id": "c1", "text": "chào", "attachments": []})
    assert sandbox.turns[-1].crisis_hold is True

    weekly = {"id": "card-20261028-bbbbbbbbbbbb", "kind": "weekly", "created_at": f"{DAY}T10:00:05+07:00",
              "focus_minutes": 0, "milestones_done": 1, "mistakes_fixed": 0, "streak_days": 2}
    checkin = {"id": "card-20261028-cccccccccccc", "kind": "checkin", "created_at": f"{DAY}T10:00:05+07:00",
               "prompt": "Hôm nay thế nào?", "options": ["Ổn", "Mệt"]}
    seen: list[JobRequest] = []

    async def fake_job(self, req):
        seen.append(req)
        return JobResult(job_id=req.job_id, status="ok", summary="ok", cards=[checkin, weekly])

    sent: list[dict] = []

    async def record(user_id, message):
        sent.append(message)
        return 1

    monkeypatch.setattr(SandboxClient, "job", fake_job)
    monkeypatch.setattr(gw.dispatcher.hub, "send", record)
    gw.runner.store.enqueue(JobRequest(job_id="j-hold", user_id=uid, profile=thpt_user["role"], kind=JobKind.ROUTINE,
                                       prompt="weekly-review"))
    client.portal.call(gw.runner.run, gw.runner.store.get("j-hold"))
    assert seen[0].crisis_hold is True
    assert [m["card"]["kind"] for m in sent if m.get("type") == "card"] == ["checkin"]
