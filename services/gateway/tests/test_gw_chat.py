import httpx
import pytest
from gateway_fakes import FAKE_HARNESS_TOKEN, harness_commit, recv_until
from mentor_schemas import OutboxItem, OutboxKind


def _turn(ws, text: str, msg_id: str = "c1", attachments=None) -> list[dict]:
    ws.send_json({"type": "user_message", "client_msg_id": msg_id, "text": text, "attachments": attachments or []})
    return recv_until(ws, "turn_done")


def test_chat_relay_and_mirror_push(client, ncs_user, gw, sandbox, backend):
    uid = ncs_user["user_id"]
    with client.websocket_connect("/api/ws/chat") as ws:
        assert ws.receive_json() == {"type": "sandbox_status", "state": "sleeping"}
        msgs = _turn(ws, "xin chào")
    types = [m["type"] for m in msgs]
    states = [m["state"] for m in msgs if m["type"] == "sandbox_status"]
    assert states == ["waking", "busy", "ready"]
    assert "".join(m["text"] for m in msgs if m["type"] == "text_delta") == "Chào bạn"
    assert {"type": "tool_started", "tool": "write_file", "summary": "Đang ghi nhật ký"} in msgs
    assert types[-1] == "turn_done" and msgs[-1]["client_msg_id"] == "c1"

    req = sandbox.turns[0]
    assert req.user_id == uid and req.profile.value == "ncs" and req.text == "xin chào"
    assert sandbox.auth_headers == [f"Bearer {FAKE_HARNESS_TOKEN}"]  # the backend's per-sandbox harness token
    # pushed after the turn: readable from the mirror and the REST API while the sandbox sleeps
    assert gw.mirror.read_text(uid, "me/journal/fake.md") == "- xin chào\n"
    assert gw.mirror.history(uid)[0].author == "mentor"
    backend.running.clear()
    r = client.get("/api/workspace/file", params={"path": "me/journal/fake.md"})
    assert r.json()["content"] == "- xin chào\n"


def test_second_turn_sees_web_edits(client, ncs_user, gw, sandbox):
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _turn(ws, "một")
        sha = client.get("/api/workspace/file", params={"path": "me/now.md"}).json()["sha"]
        assert client.put("/api/workspace/file",
                          json={"path": "me/now.md", "content": "sửa từ web\n", "base_sha": sha}).status_code == 200
        msgs = _turn(ws, "hai", "c2")
    assert [m["state"] for m in msgs if m["type"] == "sandbox_status"] == ["busy", "ready"]  # already awake
    assert sandbox.workspace_snapshots[1]["me/now.md"] == "sửa từ web\n"


def test_conflict_user_wins(client, ncs_user, gw, sandbox):
    """The working copy has an unpushed mentor change to me/now.md, the learner edits the same file on the web:
    the next turn merges with the learner's version winning, then pushes."""
    uid = ncs_user["user_id"]
    wd = gw.sync.path(uid)
    (wd / "me" / "now.md").write_text("# Bây giờ\nbản của mentor\n", encoding="utf-8", newline="\n")
    (wd / "research" / "thesis.md").write_text("mentor sửa\n", encoding="utf-8", newline="\n")
    (wd / "me" / "profile.md").write_text("mentor sửa hồ sơ\n", encoding="utf-8", newline="\n")
    harness_commit(wd, "unpushed mentor change")

    sha = client.get("/api/workspace/file", params={"path": "me/now.md"}).json()["sha"]
    client.put("/api/workspace/file", json={"path": "me/now.md", "content": "# Bây giờ\nbản của người học\n",
                                            "base_sha": sha})
    # modify/delete conflict: the learner deleted a file the mentor edited
    client.delete("/api/workspace/file", params={"path": "research/thesis.md"})

    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        msgs = _turn(ws, "ba")
    assert not [m for m in msgs if m["type"] == "error"]
    snap = sandbox.workspace_snapshots[-1]
    assert snap["me/now.md"] == "# Bây giờ\nbản của người học\n"
    assert "research/thesis.md" not in snap
    assert snap["me/profile.md"] == "mentor sửa hồ sơ\n"  # non-conflicting mentor change kept
    assert gw.mirror.read_text(uid, "me/now.md") == "# Bây giờ\nbản của người học\n"
    assert gw.mirror.read_text(uid, "research/thesis.md") is None
    assert gw.mirror.read_text(uid, "me/profile.md") == "mentor sửa hồ sơ\n"


def test_approval_round_trip(client, ncs_user, sandbox):
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "client_msg_id": "a1", "text": "please approve", "attachments": []})
        msgs = recv_until(ws, "approval_request")
        approval = msgs[-1]["approval"]
        assert approval["action"] == "calendar.create_event" and approval["summary"] == "Tạo lịch ôn tập"
        ws.send_json({"type": "approval_decision", "approval_id": approval["approval_id"], "decision": "approve",
                      "scope": "once"})
        rest = recv_until(ws, "turn_done")
    assert {"type": "text_delta", "text": "decision:approve"} in rest


def test_attachments_and_busy(client, ncs_user, sandbox):
    path = client.post("/api/uploads", files={"file": ("de.pdf", b"%PDF-1.4", "application/pdf")}).json()["path"]
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        _turn(ws, "xem đề", attachments=[{"path": path, "mime_type": "application/pdf"}])
        ws.send_json({"type": "user_message", "client_msg_id": "x", "text": "t",
                      "attachments": [{"path": "me/profile.md", "mime_type": "text/markdown"}]})
        err = ws.receive_json()
        assert err["type"] == "error" and "inbox" in err["error"]
        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["type"] == "error"
    assert sandbox.turns[0].attachments[0].path == path


def test_turn_outbox_notification_delivered(client, ncs_user, sandbox):
    sandbox.turn_outbox = [OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Nhớ ôn bài nhé"},
                                      dedupe_key="n1")]
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        msgs = _turn(ws, "hi")
    notes = [m for m in msgs if m["type"] == "notification"]
    assert len(notes) == 1 and notes[0]["text"] == "Nhớ ôn bài nhé" and notes[0]["created_at"]


def test_ws_requires_auth(client):
    with client.websocket_connect("/api/ws/chat") as ws:
        assert ws.receive_json() == {"type": "error", "error": "not authenticated"}


def test_error_event_outbox_is_delivered(client, thpt_user, gw):
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        msgs = _turn(ws, "crisis")
    assert {"type": "error", "error": "turn aborted"} in msgs
    assert gw.parent.service.alerts == [(thpt_user["user_id"], "self_harm")]
    assert not any("self_harm" in str(m) for m in msgs)


async def test_sandbox_client_sends_harness_token(sandbox, sandbox_server):
    from mentor_schemas import ApprovalDecision, JobKind, JobRequest, Profile, TurnRequest

    from mentor_gateway.sandbox import SandboxClient

    turn = TurnRequest(user_id="u1", profile=Profile.NCS, session_id="s-1", text="x")
    job = JobRequest(job_id="j1", user_id="u1", profile=Profile.NCS, kind=JobKind.INTAKE)
    anonymous = SandboxClient(sandbox_server.base_url)
    assert await anonymous.health()  # health needs no token
    events = [e async for e in anonymous.turn(turn)]
    assert events[-1].type == "error" and "HTTP 401" in events[-1].error
    wrong = SandboxClient(sandbox_server.base_url, token="nope")
    with pytest.raises(httpx.HTTPStatusError):
        await wrong.job(job)
    good = SandboxClient(sandbox_server.base_url, token=FAKE_HARNESS_TOKEN)
    assert (await good.job(job)).status == "ok"
    await good.approval(ApprovalDecision(approval_id="a1", decision="approve"))
    assert sandbox.auth_headers == [None, "Bearer nope", f"Bearer {FAKE_HARNESS_TOKEN}", f"Bearer {FAKE_HARNESS_TOKEN}"]
