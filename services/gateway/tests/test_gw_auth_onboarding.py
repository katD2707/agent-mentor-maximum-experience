from urllib.parse import parse_qs, urlparse

from gateway_fakes import login, onboard, verify_parent

from mentor_gateway.gitrepo import run_git


def test_magic_link_flow(client, clock):
    assert client.get("/api/me").status_code == 401
    r = client.post("/api/auth/request-link", json={"email": "An@Example.com"})
    body = r.json()
    assert body["sent"] is True and body["dev_link"].startswith("http://testserver/api/auth/verify?token=")
    token = parse_qs(urlparse(body["dev_link"]).query)["token"][0]

    r = client.get("/api/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "http://web.test/onboarding"
    assert "mentor_session" in r.cookies or client.cookies.get("mentor_session")

    me = client.get("/api/me").json()
    assert me["email"] == "an@example.com"
    assert me["role"] is None and me["onboarding_state"] == "needs_role"
    assert me["inbound_email_address"] is None

    # one-time token
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).status_code == 400

    assert client.post("/api/auth/logout").json() == {"ok": True}
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401


def test_expired_link_rejected(client, clock):
    r = client.post("/api/auth/request-link", json={"email": "x@example.com"})
    token = parse_qs(urlparse(r.json()["dev_link"]).query)["token"][0]
    clock.advance(minutes=16)
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).status_code == 400


def test_invalid_email(client):
    assert client.post("/api/auth/request-link", json={"email": "nope"}).status_code == 422


def test_login_requests_rate_limited_per_email(client, clock):
    for _ in range(5):
        assert client.post("/api/auth/request-link", json={"email": "rl@example.com"}).status_code == 200
    r = client.post("/api/auth/request-link", json={"email": "RL@example.com"})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"
    assert client.post("/api/auth/request-link", json={"email": "other@example.com"}).status_code == 200
    clock.advance(minutes=61)
    assert client.post("/api/auth/request-link", json={"email": "rl@example.com"}).status_code == 200


def test_ncs_onboarding_provisions_workspace(client, gw):
    me = onboard(client, "ncs@example.com", "ncs", name="Bình")
    assert me["role"] == "ncs" and me["onboarding_state"] == "active"
    code, domain = me["inbound_email_address"].split("@")
    assert domain == "inbox.mentor.local" and len(code) == 10

    uid = me["user_id"]
    paths = {e.path for e in gw.mirror.ls_tree(uid)}
    assert "AGENTS.md" in paths
    assert ".mentor/skills/core/memory-keeper/SKILL.md" in paths
    assert ".mentor/skills/ncs/paper-reader/SKILL.md" in paths
    assert not any(p.startswith(".mentor/skills/thpt") for p in paths)
    assert not any(p.startswith(".mentor/curricula") for p in paths)
    assert "research/thesis.md" in paths
    assert "routines.yaml" in paths  # template had none: defaults written
    assert "Tên: Bình" in gw.mirror.read_text(uid, "me/profile.md")

    history = gw.mirror.history(uid)
    assert len(history) == 1 and history[0].author == "system"
    # the working copy exists and is in sync with the mirror
    wc_head = run_git(["rev-parse", "HEAD"], cwd=gw.sync.path(uid)).stdout.decode().strip()
    assert wc_head == gw.mirror.head(uid)

    # redirect goes to /chat once active
    client.cookies.clear()
    r = client.post("/api/auth/request-link", json={"email": "ncs@example.com"})
    token = parse_qs(urlparse(r.json()["dev_link"]).query)["token"][0]
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).headers["location"].endswith(
        "/chat"
    )


def test_onboarding_is_idempotent_but_role_is_fixed(client):
    onboard(client, "ncs@example.com", "ncs")
    r = client.post("/api/onboarding", json={"role": "ncs", "display_name": "Mới", "language": "en"})
    assert r.status_code == 200 and r.json()["display_name"] == "Mới" and r.json()["language"] == "en"
    assert client.post("/api/onboarding", json={"role": "thpt", "display_name": "x"}).status_code == 409


def test_thpt_gated_until_parent_verified(client, gw):
    me = onboard(client, "hs@example.com", "thpt")
    uid = me["user_id"]
    assert me["onboarding_state"] == "needs_parent"
    paths = {e.path for e in gw.mirror.ls_tree(uid)}
    assert ".mentor/curricula/math.yaml" in paths
    assert ".mentor/skills/thpt/math-tutor/SKILL.md" in paths

    assert client.get("/api/parent-link").json() == {"status": "none"}
    r = client.post("/api/parent-link")
    assert r.status_code == 200
    body = r.json()
    assert body["link_code"] == "123456" and "bot_name" in body and "expires_at" in body
    assert client.get("/api/parent-link").json()["status"] == "pending"

    # chat, uploads and edits are blocked
    with client.websocket_connect("/api/ws/chat") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and "needs_parent" in msg["error"]
    assert client.post("/api/uploads", files={"file": ("a.txt", b"x")}).status_code == 403
    assert client.put("/api/workspace/file", json={"path": "me/a.md", "content": "x"}).status_code == 403
    # reads of the (template) workspace still work
    assert client.get("/api/workspace/tree").status_code == 200

    gw.parent.service.verify(uid)
    assert client.get("/api/parent-link").json() == {"status": "verified"}
    assert client.get("/api/me").json()["onboarding_state"] == "active"
    assert client.post("/api/parent-link").status_code == 409


def test_parent_link_only_for_thpt(client):
    onboard(client, "ncs@example.com", "ncs")
    assert client.post("/api/parent-link").status_code == 400


def test_missing_content_is_tolerated(client, gw, tmp_path):
    gw.settings.content_dir = tmp_path / "nothing-here"
    me = onboard(client, "empty@example.com", "ncs")
    paths = {e.path for e in gw.mirror.ls_tree(me["user_id"])}
    assert "routines.yaml" in paths and ".mentor/activity.jsonl" in paths


def test_delete_account(client, gw):
    me = onboard(client, "hs@example.com", "thpt")
    verify_parent(client, me["user_id"])
    uid = me["user_id"]
    assert gw.mirror.exists(uid)
    assert client.delete("/api/account").json() == {"ok": True}
    assert not gw.mirror.exists(uid) and not gw.sync.path(uid).exists()
    assert gw.users.get(uid) is None
    assert gw.parent.get_link(uid) is None
    client.cookies.clear()
    login(client, "hs@example.com")
    assert client.get("/api/me").json()["user_id"] != uid


def _request_code(client, email: str) -> tuple[str, str]:
    body = client.post("/api/auth/request-link", json={"email": email}).json()
    token = parse_qs(urlparse(body["dev_link"]).query)["token"][0]
    return token, body["dev_code"]


def test_auth_login_code_sets_session_and_consumes_link(client):
    token, code = _request_code(client, "Code@Example.com")
    assert len(code) == 6 and code.isdigit()

    r = client.post("/api/auth/verify-code", json={"email": "code@example.com", "code": code})
    assert r.status_code == 200 and r.json() == {"ok": True, "next": "/onboarding"}
    assert client.cookies.get("mentor_session")
    assert client.get("/api/me").json()["email"] == "code@example.com"

    # one-time: the code and the link of the same login are both used up
    client.cookies.clear()
    assert client.post("/api/auth/verify-code", json={"email": "code@example.com", "code": code}).status_code == 400
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).status_code == 400


def test_auth_login_code_link_use_consumes_code(client):
    token, code = _request_code(client, "a@example.com")
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).status_code == 302
    client.cookies.clear()
    assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": code}).status_code == 400


def test_auth_login_code_expires(client, clock):
    _, code = _request_code(client, "a@example.com")
    clock.advance(minutes=16)
    assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": code}).status_code == 400
    assert client.get("/api/me").status_code == 401


def test_auth_login_code_wrong_attempts_invalidate(client):
    token, code = _request_code(client, "a@example.com")
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(4):
        assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": wrong}).status_code == 400
    # still valid after 4 misses
    r = client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": code})
    assert r.status_code == 200
    client.cookies.clear()

    token, code = _request_code(client, "a@example.com")
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(5):
        assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": wrong}).status_code == 400
    # the 5th miss killed this login: right code and its link no longer work
    assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": code}).status_code == 400
    assert client.get("/api/auth/verify", params={"token": token}, follow_redirects=False).status_code == 400
    assert client.get("/api/me").status_code == 401


def test_auth_login_code_newest_only_and_bound_to_email(client):
    _, old = _request_code(client, "a@example.com")
    _, new = _request_code(client, "a@example.com")
    _, other = _request_code(client, "b@example.com")
    if old != new:
        assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": old}).status_code == 400
    if other != new:
        assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": other}).status_code == 400
    assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": " " + new}).status_code == 200


def test_auth_login_code_validation(client):
    assert client.post("/api/auth/verify-code", json={"email": "a@example.com", "code": "12345"}).status_code == 422
    assert client.post("/api/auth/verify-code", json={"email": "nope", "code": "123456"}).status_code == 422
    # unknown email: same answer as a wrong code
    assert client.post("/api/auth/verify-code", json={"email": "z@example.com", "code": "123456"}).status_code == 400


def test_auth_login_code_redirect_target_active_user(client):
    onboard(client, "ncs@example.com", "ncs")
    client.cookies.clear()
    _, code = _request_code(client, "ncs@example.com")
    r = client.post("/api/auth/verify-code", json={"email": "ncs@example.com", "code": code})
    assert r.json() == {"ok": True, "next": "/chat"}


def test_signup_allowlist(client, gw):
    gw.settings.signup_allowlist = "a@example.com, @school.edu.vn"
    assert client.post("/api/auth/request-link", json={"email": "A@example.com"}).status_code == 200
    assert client.post("/api/auth/request-link", json={"email": "hs1@school.edu.vn"}).status_code == 200
    r = client.post("/api/auth/request-link", json={"email": "stranger@example.com"})
    assert r.status_code == 403 and "chưa được mời" in r.json()["detail"]
    gw.settings.signup_allowlist = ""
    assert client.post("/api/auth/request-link", json={"email": "stranger@example.com"}).status_code == 200
