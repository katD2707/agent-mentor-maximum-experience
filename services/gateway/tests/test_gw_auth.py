"""Role-based login, /api/me, quiet (CONTRACTS section 4)."""

import sqlite3
from datetime import timedelta

from gateway_fakes import FakeWS, login
from mentor_schemas import OutboxItem, OutboxKind
from sqlalchemy import select

from mentor_gateway.app import create_app
from mentor_gateway.db import Database, User
from mentor_gateway.security import hash_password, verify_password


def _login(client, username="hocsinh", password="123456", role="student"):
    return client.post("/api/auth/login", json={"username": username, "password": password, "role": role})


def test_dev_accounts_are_seeded(gw):
    with gw.db.session() as s:
        users = {u.username: (u.role, u.display_name) for u in s.scalars(select(User))}
    assert users == {"hocsinh": ("student", "Lan"), "giaovien": ("teacher", "Thầy Minh")}


def test_not_seeded_outside_dev(tmp_path, settings):
    s = settings.model_copy(update={"seed_dev_accounts": False, "data_dir": tmp_path / "other"})
    gw = create_app(s).state.gw
    assert gw.users.by_username("hocsinh") is None


def test_login_ok_returns_token_and_user(client):
    r = _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["user"] == {"id": body["user"]["id"], "role": "student", "username": "hocsinh",
                            "display_name": "Lan", "age_band": "g10_12", "birth_year": 2010, "language": None, "theme": "system",
                            "quiet_until": None}
    teacher = _login(client, "giaovien", role="teacher").json()["user"]
    assert teacher["role"] == "teacher" and teacher["display_name"] == "Thầy Minh"


def test_login_username_is_case_insensitive_password_is_not(client):
    assert _login(client, "HocSinh").status_code == 200
    assert _login(client, "hocsinh", "123456 ").status_code == 401


def test_invalid_credentials(client):
    for username, password in (("hocsinh", "wrong"), ("nobody", "123456")):
        r = _login(client, username, password)
        assert r.status_code == 401 and r.json() == {"error": "invalid_credentials"}


def test_wrong_role_is_403_role_mismatch(client):
    r = _login(client, "hocsinh", role="teacher")
    assert r.status_code == 403 and r.json() == {"error": "role_mismatch"}
    r = _login(client, "giaovien", role="student")
    assert r.status_code == 403 and r.json() == {"error": "role_mismatch"}
    # a wrong password is reported as such even when the role is wrong too
    assert _login(client, "hocsinh", "wrong", "teacher").status_code == 401


def test_unknown_role_value_is_rejected(client):
    assert _login(client, role="thpt").status_code == 422


def test_me_requires_a_token(client):
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json() == {"error": "unauthorized"}
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_me_and_logout(client):
    user = login(client)
    assert client.get("/api/me").json() == user
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 401


def test_tokens_are_per_login(client):
    first = _login(client).json()["token"]
    second = _login(client).json()["token"]
    assert first != second
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {first}"})
    assert client.get("/api/me", headers={"Authorization": f"Bearer {second}"}).status_code == 200


def test_token_expires(client, clock):
    login(client)
    clock.advance(days=366)
    assert client.get("/api/me").status_code == 401


def test_patch_me(client):
    login(client)
    r = client.patch("/api/me", json={"language": "en", "theme": "dark", "display_name": " Lan A "})
    assert r.status_code == 200
    assert r.json() | {"id": "x"} == {"id": "x", "role": "student", "username": "hocsinh", "display_name": "Lan A",
                                      "age_band": "g10_12", "birth_year": 2010, "language": "en", "theme": "dark",
                                      "quiet_until": None}
    # a partial update leaves the rest alone; language can be cleared
    r = client.patch("/api/me", json={"theme": "light"}).json()
    assert r["theme"] == "light" and r["age_band"] == "g10_12" and r["language"] == "en"
    r = client.patch("/api/me", json={"language": None}).json()
    assert r["language"] is None and r["theme"] == "light"
    assert client.patch("/api/me", json={}).status_code == 200
    # the age band is derived: a client cannot send one
    assert client.patch("/api/me", json={"age_band": "uni"}).json()["age_band"] == "g10_12"


def test_patch_me_validates(client):
    login(client)
    for bad in ({"language": "fr"}, {"theme": "blue"}, {"display_name": "  "}, {"birth_year": 1800}):
        assert client.patch("/api/me", json=bad).status_code == 422
    # role and username cannot be changed through /me
    r = client.patch("/api/me", json={"role": "teacher", "username": "x"}).json()
    assert r["role"] == "student" and r["username"] == "hocsinh"


def test_quiet_until(client, clock):
    login(client)
    until = (clock() + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    r = client.put("/api/me/quiet", json={"until": until})
    assert r.status_code == 200 and r.json() == {"until": until}
    assert client.get("/api/me").json()["quiet_until"].startswith(until[:19])
    # an offset is normalised to UTC; null clears
    r = client.put("/api/me/quiet", json={"until": "2026-10-28T20:00:00+07:00"})
    assert r.json() == {"until": "2026-10-28T13:00:00Z"}
    assert client.put("/api/me/quiet", json={"until": None}).json() == {"until": None}
    assert client.get("/api/me").json()["quiet_until"] is None
    assert client.put("/api/me/quiet", json={"until": "tomorrow"}).status_code == 422


def test_quiet_until_holds_notifications_back(client, gw, clock):
    user = login(client)
    ws = FakeWS()
    gw.hub.register(user["id"], ws)
    client.put("/api/me/quiet", json={"until": (clock() + timedelta(hours=1)).isoformat()})
    item = OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Ôn 10 phút nhé", "kind": "review"})
    assert client.portal.call(gw.dispatcher.dispatch, user["id"], [item]) == ["pending"]
    assert ws.sent == []
    clock.advance(hours=2)
    client.portal.call(gw.hub.flush_all)
    assert [m["type"] for m in ws.sent] == ["notification"]


def test_password_hashing():
    h = hash_password("123456")
    assert h.startswith("scrypt$") and "123456" not in h and h != hash_password("123456")
    assert verify_password("123456", h) and not verify_password("1234567", h)
    assert not verify_password("123456", "garbage") and not verify_password("x", "md5$1$2$3$4$5")


def test_cors_allows_the_app_origins(client):
    for origin in ("http://localhost:5173", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"):
        r = client.options("/api/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                       "Access-Control-Request-Headers": "authorization,content-type"})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin, origin
        assert "authorization" in r.headers["access-control-allow-headers"].lower()
    r = client.options("/api/auth/login", headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_conditional_and_range_requests_and_exposes_etag(client):
    """The app revalidates /catalog with If-None-Match and reads ETag; <video crossorigin> sends Range."""
    r = client.options("/api/catalog", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "authorization,if-none-match,range"})
    assert r.status_code == 200
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "if-none-match" in allowed and "range" in allowed
    r = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert "etag" in r.headers["access-control-expose-headers"].lower()


def test_pre_redesign_dev_db_is_reset(tmp_path):
    path = tmp_path / "ops.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, role TEXT)")
    con.execute("CREATE TABLE magic_links (token_hash TEXT PRIMARY KEY)")
    con.execute("INSERT INTO users VALUES ('u1', 'a@b.c', 'thpt')")
    con.commit()
    con.close()
    db = Database(f"sqlite:///{path.as_posix()}")
    db.create_all()
    with db.session() as s:
        assert s.scalars(select(User)).all() == []
    db.dispose()
    con = sqlite3.connect(path)
    assert not con.execute("SELECT name FROM sqlite_master WHERE name = 'magic_links'").fetchall()
    con.close()
