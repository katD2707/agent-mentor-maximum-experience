"""What the real web app (apps/web) relies on: CORS, cookie auth, error shape, sessions and chat history."""

import json

import pytest
from gateway_fakes import recv_until
from starlette.websockets import WebSocketDisconnect


def test_cors_for_web_origin(client):
    pre = client.options("/api/me", headers={"Origin": "http://web.test", "Access-Control-Request-Method": "PUT",
                                             "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "http://web.test"
    assert pre.headers["access-control-allow-credentials"] == "true"
    assert "PUT" in pre.headers["access-control-allow-methods"]
    r = client.get("/api/me", headers={"Origin": "http://web.test"})
    assert r.headers["access-control-allow-origin"] == "http://web.test"
    evil = client.options("/api/me", headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


def test_errors_have_detail(client, ncs_user):
    client.cookies.clear()
    r = client.get("/api/me")
    assert r.status_code == 401 and isinstance(r.json()["detail"], str)
    assert client.get("/api/nope").json() == {"detail": "Not Found"}


def test_ws_origin_check(client, ncs_user):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(
        "/api/ws/chat", headers={"Origin": "http://evil.test"}
    ) as ws:
        ws.receive_json()
    with client.websocket_connect("/api/ws/chat", headers={"Origin": "http://web.test"}) as ws:
        assert ws.receive_json()["type"] == "sandbox_status"


def test_history_for_directory(client, ncs_user):
    sha = client.get("/api/workspace/file", params={"path": "me/now.md"}).json()["sha"]
    client.put("/api/workspace/file", json={"path": "me/now.md", "content": "x\n", "base_sha": sha})
    client.put("/api/workspace/file", json={"path": "me/people.md", "content": "y\n", "base_sha": ""})
    for p in ("me", "me/"):
        hist = client.get("/api/workspace/history", params={"path": p}).json()
        assert [h["author"] for h in hist] == ["user", "user", "system"]
    assert client.get("/api/workspace/history", params={"path": "research"}).json()[0]["author"] == "system"


def test_delete_account_clears_cookie(client, ncs_user):
    r = client.delete("/api/account")
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"]
    assert "mentor_session=" in set_cookie and ("Max-Age=0" in set_cookie or "expires=" in set_cookie.lower())
    assert client.get("/api/me").status_code == 401


def test_session_id_per_local_day(client, ncs_user, sandbox, clock):
    from datetime import UTC, datetime

    clock.now = datetime(2026, 10, 28, 16, 59, tzinfo=UTC)  # 23:59 local
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        for i in range(2):
            ws.send_json({"type": "user_message", "client_msg_id": f"c{i}", "text": "hi", "attachments": []})
            recv_until(ws, "turn_done")
        clock.now = datetime(2026, 10, 28, 17, 1, tzinfo=UTC)  # 00:01 next day, same connection
        ws.send_json({"type": "user_message", "client_msg_id": "c3", "text": "hi", "attachments": []})
        recv_until(ws, "turn_done")
    assert [t.session_id for t in sandbox.turns] == ["s-20261028", "s-20261028", "s-20261029"]


def test_chat_history(client, ncs_user, gw, clock):
    uid = ncs_user["user_id"]
    lines = [
        {"ts": "2026-10-28T09:00:00+07:00", "role": "user", "text": "Chào", "attachments": ["inbox/a.png"]},
        {"ts": "2026-10-28T09:00:05+07:00", "role": "mentor", "text": "Chào em"},
        {"ts": "2026-10-28T09:00:06+07:00", "role": "tool", "text": "hidden"},
    ]
    data = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n{broken\n"
    gw.mirror.commit_files(uid, {"sessions/2026-10-28/s-20261028.jsonl": data.encode()}, author="mentor", message="s")
    expected = [
        {"ts": "2026-10-28T09:00:00+07:00", "role": "user", "text": "Chào", "attachments": ["inbox/a.png"]},
        {"ts": "2026-10-28T09:00:05+07:00", "role": "mentor", "text": "Chào em", "attachments": []},
    ]
    assert client.get("/api/chat/history", params={"date": "2026-10-28"}).json() == expected
    assert client.get("/api/chat/history").json() == expected  # default: today in Asia/Ho_Chi_Minh
    assert client.get("/api/chat/history", params={"date": "2026-10-27"}).json() == []
    assert client.get("/api/chat/history", params={"date": "28/10/2026"}).status_code == 422
