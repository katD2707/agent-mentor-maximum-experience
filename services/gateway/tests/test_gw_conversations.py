"""Named conversations (CONTRACTS section 10.5): CRUD, search, history, WebSocket conversation_id."""

import json

from gateway_fakes import recv_until

DAY = "2026-10-28"  # conftest clock: 2026-10-28 10:00 Asia/Ho_Chi_Minh


def _write(gw, user, files: dict[str, list[dict]]) -> None:
    gw.mirror.commit_files(
        user["user_id"],
        {p: "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs).encode() for p, recs in files.items()},
        author="mentor", message="seed")


def _rec(role, text, ts=f"{DAY}T10:00:00+07:00"):
    return {"ts": ts, "role": role, "text": text, "attachments": []}


def test_crud_and_validation(client, thpt_user):
    made = client.post("/api/conversations", json={"title": "  Ôn   hàm số ", "subject": "math"}).json()
    assert made["title"] == "Ôn hàm số" and made["subject"] == "math" and made["session_id"] == f"c-{made['id']}"
    assert len(made["id"]) == 12 and made["archived"] is False
    blank = client.post("/api/conversations", json={}).json()
    assert blank["title"] == "Cuộc trò chuyện mới" and blank["subject"] is None
    assert client.post("/api/conversations", json={"title": "x" * 81}).status_code == 422
    assert client.post("/api/conversations", json={"subject": "Bad Subject"}).status_code == 422

    r = client.patch(f"/api/conversations/{made['id']}", json={"title": "Đạo hàm", "subject": None, "archived": True})
    assert r.json()["title"] == "Đạo hàm" and r.json()["subject"] is None and r.json()["archived"] is True
    assert [c["id"] for c in client.get("/api/conversations").json()] == [blank["id"]]
    assert [c["id"] for c in client.get("/api/conversations", params={"archived": "true"}).json()] == [made["id"]]
    assert len(client.get("/api/conversations", params={"archived": "all"}).json()) == 2
    assert client.patch(f"/api/conversations/{made['id']}", json={}).status_code == 422
    assert client.patch("/api/conversations/ffffffffffff", json={"title": "a"}).status_code == 404
    assert client.delete("/api/conversations/ffffffffffff").status_code == 404


def test_other_learner_cannot_touch(client, thpt_user, ncs_user):
    # the fixtures log in one after another; the cookie belongs to the last login (thpt)
    mine = client.post("/api/conversations", json={}).json()
    from conftest import onboard  # noqa: PLC0415

    onboard(client, "other@example.com", "ncs")
    assert client.get("/api/conversations").json() == []
    assert client.patch(f"/api/conversations/{mine['id']}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/conversations/{mine['id']}").status_code == 404
    assert client.get("/api/chat/history", params={"conversation_id": mine["id"]}).status_code == 404


def test_search_ignores_diacritics_newest_first_and_caps(client, gw, thpt_user):
    conv = client.post("/api/conversations", json={"title": "Hàm số"}).json()
    cid = conv["id"]
    _write(gw, thpt_user, {
        "sessions/2026-10-20/s-20261020.jsonl": [_rec("user", "Hôm nay mình học Đạo hàm của hàm số"),
                                                 {"ts": "x", "role": "card", "card": {"id": "card-20261020-aaaaaaaaaaaa",
                                                                                      "kind": "deadline", "title": "đạo hàm"}}],
        f"sessions/2026-10-27/c-{cid}.jsonl": [_rec("user", "Giải thích dao ham giúp mình"),
                                               _rec("mentor", "Đạo hàm là tốc độ thay đổi " + "x" * 200 + " ĐẠO HÀM")],
    })
    hits = client.get("/api/conversations/search", params={"q": "DAO ham"}).json()
    assert [(h["date"], h["role"]) for h in hits] == [("2026-10-27", "mentor"), ("2026-10-27", "user"),
                                                      ("2026-10-20", "user")]
    assert hits[0]["conversation_id"] == cid and hits[0]["session_id"] == f"c-{cid}" and hits[0]["title"] == "Hàm số"
    assert hits[2]["conversation_id"] is None and hits[2]["session_id"] == "s-20261020"
    assert "Đạo hàm" in hits[0]["snippet"] and hits[0]["snippet"].startswith("Đạo hàm")
    assert "dao ham" in hits[1]["snippet"]
    assert len(client.get("/api/conversations/search", params={"q": "ham", "limit": 2}).json()) == 2
    assert client.get("/api/conversations/search", params={"q": "không có gì"}).json() == []
    assert client.get("/api/conversations/search", params={"q": ""}).status_code == 422


def test_history_across_days_and_delete_removes_transcripts(client, gw, thpt_user):
    cid = client.post("/api/conversations", json={}).json()["id"]
    _write(gw, thpt_user, {
        f"sessions/2026-10-26/c-{cid}.jsonl": [_rec("user", "một"), _rec("mentor", "hai")],
        f"sessions/2026-10-27/c-{cid}.jsonl": [_rec("user", "ba")],
        f"sessions/2026-10-27/c-{cid}.md": [],
        "sessions/2026-10-27/s-20261027.jsonl": [_rec("user", "daily")],
    })
    hist = client.get("/api/chat/history", params={"conversation_id": cid}).json()
    assert [h["text"] for h in hist] == ["một", "hai", "ba"]
    assert [h["text"] for h in client.get("/api/chat/history", params={"conversation_id": cid, "limit": 2}).json()] == [
        "hai", "ba"]
    assert client.delete(f"/api/conversations/{cid}").json() == {"ok": True}
    assert client.get("/api/conversations", params={"archived": "all"}).json() == []
    paths = {e.path for e in gw.mirror.ls_tree(thpt_user["user_id"])}
    assert not any(f"c-{cid}" in p for p in paths) and "sessions/2026-10-27/s-20261027.jsonl" in paths


def test_ws_conversation_id_session_title_and_unknown(client, gw, thpt_user, sandbox):
    conv = client.post("/api/conversations", json={}).json()
    cid = conv["id"]
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "client_msg_id": "m0", "text": "bình thường", "attachments": []})
        recv_until(ws, "turn_done")
        ws.send_json({"type": "user_message", "client_msg_id": "m1", "conversation_id": cid,
                      "text": "Giải phương trình bậc hai giúp mình nhé", "attachments": []})
        recv_until(ws, "turn_done")
        ws.send_json({"type": "user_message", "client_msg_id": "m2", "conversation_id": "ffffffffffff",
                      "text": "x", "attachments": []})
        err = ws.receive_json()
    assert [t.session_id for t in sandbox.turns] == ["s-20261028", f"c-{cid}"]
    assert err["type"] == "error" and err["conversation_id"] == "ffffffffffff" and len(sandbox.turns) == 2
    after = client.get("/api/conversations").json()[0]
    assert after["title"] == "Giải phương trình bậc hai giúp mình nhé"
    # an archived conversation that gets a message comes back
    client.patch(f"/api/conversations/{cid}", json={"archived": True})
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "client_msg_id": "m3", "conversation_id": cid, "text": "tiếp",
                      "attachments": []})
        recv_until(ws, "turn_done")
    assert client.get("/api/conversations").json()[0]["archived"] is False
    assert client.get("/api/conversations").json()[0]["title"] == after["title"]
