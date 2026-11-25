"""Central hub integration (CONTRACTS-HUB.md section 3): the gateway proxies accounts and course submits to the hub and keeps
a local mirror. The hub is faked in-process with an httpx MockTransport."""

import hashlib
import io
import json
import zipfile
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from fastapi.testclient import TestClient
from gateway_fakes import login
from test_gw_drive import FakeDrive, secrets_settings
from test_gw_courses import publish_course
from test_gw_teacher import FakeRunner, built_course, confirm

from mentor_gateway.age import grade_for
from mentor_gateway.app import create_app
from mentor_gateway.content import ContentStore
from mentor_gateway.content.drive import DriveClient, DrivePublisher
from mentor_gateway.hub import HubClient
from mentor_gateway.security import hash_password

HUB = "https://hub.test"


def parse_multipart(req: httpx.Request) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + req.headers["content-type"].encode() + b"\r\n\r\n" + req.content)
    out = {}
    for part in msg.iter_parts():
        out[part.get_param("name", header="content-disposition")] = {
            "filename": part.get_filename(), "body": part.get_payload(decode=True)}
    return out


class FakeHub:
    def __init__(self) -> None:
        self.accounts: dict[str, dict] = {}  # username -> {"account": {...}, "password": str}
        self.tokens: dict[str, str] = {}
        self.offline = False
        self.calls: list[tuple[str, str]] = []
        self.submits: list[dict] = []
        self.courses: dict[str, dict] = {}
        self.code = "123456"
        self.reset_codes: dict[str, str] = {}
        self.submit_error: tuple[int, str] | None = None

    def _find(self, login_: str) -> dict | None:
        for a in self.accounts.values():
            if login_ in (a["account"]["username"], a["account"].get("email")):
                return a
        return None

    def _who(self, req: httpx.Request) -> dict | None:
        tok = req.headers.get("authorization", "").removeprefix("Bearer ")
        return self.accounts.get(self.tokens.get(tok, ""))

    def _issue(self, a: dict, status: int = 200) -> httpx.Response:
        tok = f"tok-{len(self.tokens) + 1}"
        self.tokens[tok] = a["account"]["username"]
        return httpx.Response(status, json={"token": tok, "account": a["account"]})

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("offline")
        path, m = req.url.path, req.method
        self.calls.append((m, path))
        is_multipart = req.headers.get("content-type", "").startswith("multipart/")
        body = json.loads(req.content) if req.content and not is_multipart else {}
        if path == "/api/register":
            if body["username"] in self.accounts:
                return httpx.Response(409, json={"error": "username_taken"})
            if body["role"] == "teacher" and not body.get("email"):
                return httpx.Response(422, json={"error": "bad_request"})
            acc = {"id": f"a_{len(self.accounts) + 1}", "username": body["username"], "display_name": body["display_name"],
                   "role": body["role"], "email": body.get("email"), "grade": body.get("grade"),
                   "parent_email": body.get("parent_email"),
                   "teacher_status": "chua_nop" if body["role"] == "teacher" else None, "reject_reason": None}
            self.accounts[body["username"]] = {"account": acc, "password": body["password"]}
            return self._issue(self.accounts[body["username"]], 201)
        if path == "/api/login":
            a = self._find(body["login"])
            if a is None or a["password"] != body["password"]:
                return httpx.Response(401, json={"error": "invalid_credentials"})
            return self._issue(a)
        if path == "/api/forgot":
            a = self._find(body["login"])
            if a is None or not a["account"]["email"]:
                return httpx.Response(200, json={"via": "none"})
            self.reset_codes[a["account"]["username"]] = "654321"
            return httpx.Response(200, json={"via": "email", "to": "n•••@gmail.com"})
        if path == "/api/forgot/request":
            return httpx.Response(204)
        if path == "/api/reset":
            a = self._find(body["login"])
            if a is None or self.reset_codes.get(a["account"]["username"]) != body["code"]:
                return httpx.Response(400, json={"error": "wrong_code"})
            a["password"] = body["password"]
            return httpx.Response(204)
        me = self._who(req)
        if me is None:
            return httpx.Response(401, json={"error": "unauthorized"})
        acc = me["account"]
        if path == "/api/me":
            return httpx.Response(200, json={"account": acc})
        if path == "/api/teacher/verify":
            if body["code"] != self.code:
                return httpx.Response(400, json={"error": "wrong_code"})
            acc["teacher_status"] = "xac_minh"
            return httpx.Response(200, json={"account": acc})
        if path in ("/api/teacher/resend-form", "/api/teacher/resend-code"):
            ok = acc["teacher_status"] in (("chua_nop", "tu_choi") if path.endswith("form") else ("da_duyet",))
            return httpx.Response(204) if ok else httpx.Response(409, json={"error": "bad_state"})
        if acc["teacher_status"] != "xac_minh" and path.startswith("/api/courses"):
            return httpx.Response(403, json={"error": "teacher_unverified"})
        if path == "/api/courses/submit":
            if self.submit_error:
                return httpx.Response(self.submit_error[0], json={"error": self.submit_error[1]})
            form = parse_multipart(req)
            f = {k: v["body"].decode() if v["filename"] is None else v["body"] for k, v in form.items()}
            self.submits.append({**f, "pack_name": form["pack"]["filename"], "cover_filename": form["cover"]["filename"]})
            c = {"course_id": f["course_id"], "title": f["title"], "version": int(f["version"]), "kind": "new",
                 "state": "cho_duyet", "live_version": None, "reason": None, "updated_at": "2026-11-25T00:00:00Z"}
            self.courses[f["course_id"]] = c
            return httpx.Response(200, json={"course": c})
        if path == "/api/courses/mine":
            return httpx.Response(200, json={"courses": list(self.courses.values())})
        if path.endswith("/withdraw") or path.endswith("/remove"):
            cid = path.split("/")[3]
            c = self.courses[cid]
            c["state"] = "rut_lai" if path.endswith("withdraw") else "da_go"
            return httpx.Response(200, json={"course": c})
        raise AssertionError(f"unexpected {m} {path}")


@pytest.fixture
def hub():
    return FakeHub()


@pytest.fixture
def client(settings, clock, executor, hub):
    app = create_app(settings.model_copy(update={"hub_url": HUB, "seed_dev_accounts": True}), clock=clock, executor=executor)
    app.state.gw.hub_client = HubClient(HUB, httpx.MockTransport(hub))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def gw(client):
    return client.app.state.gw


@pytest.fixture
def store(client, tmp_path) -> ContentStore:
    s = ContentStore(tmp_path / "courses", client.app.state.gw.clock)
    client.app.state.content.store = s
    return s


@pytest.fixture
def runner(client, store) -> FakeRunner:
    r = FakeRunner(store)
    client.app.state.builder.runner = r
    return r


def register(client, **kw):
    body = {"role": "student", "username": "lan.nguyen", "password": "secret1", "display_name": "Lan", **kw}
    return client.post("/api/auth/register", json=body)


def teacher_login(client, hub, status="xac_minh"):
    r = register(client, role="teacher", username="thay.hoa", email="hoa@gmail.com", display_name="Cô Hoa")
    assert r.status_code == 200, r.text
    hub.accounts["thay.hoa"]["account"]["teacher_status"] = status
    r = client.post("/api/auth/login", json={"username": "thay.hoa", "password": "secret1", "role": "teacher"})
    assert r.status_code == 200, r.text
    client.headers["authorization"] = "Bearer " + r.json()["token"]
    return r.json()["user"]


# ---------------------------------------------------------------- config, register, login
def test_config_says_hub(client):
    assert client.get("/api/auth/config").json() == {"signup": True, "hub": True}


def test_register_and_login_through_the_hub(client, hub, gw):
    r = register(client, grade="10", email="lan@gmail.com")
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["username"] == "lan.nguyen" and u["email"] == "lan@gmail.com" and u["teacher_status"] is None
    assert grade_for(u["birth_year"], gw.clock().date()) == 10 and u["age_band"] == "g10_12"
    assert ("POST", "/api/register") in hub.calls
    row = gw.users.by_username("lan.nguyen")
    assert row.hub_id == "a_1" and row.hub_token == "tok-1" and row.email == "lan@gmail.com"
    # login by email, username optional role
    r = client.post("/api/auth/login", json={"username": "lan@gmail.com", "password": "secret1"})
    assert r.status_code == 200 and r.json()["user"]["id"] == u["id"]
    assert client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "nope"}).json() == {"error": "invalid_credentials"}
    r = client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "secret1", "role": "teacher"})
    assert r.status_code == 403 and r.json() == {"error": "role_mismatch"}


def test_university_grade_and_hub_errors_pass_through(client, hub, gw):
    u = register(client, username="sv.an", grade="dh").json()["user"]
    assert u["age_band"] == "uni"
    r = register(client, username="sv.an")
    assert r.status_code == 409 and r.json() == {"error": "username_taken"}
    r = register(client, role="teacher", username="thay.b")  # a teacher needs an email
    assert r.status_code == 422 and r.json() == {"error": "bad_request"}


def test_offline_hub_is_503_but_login_falls_back_to_the_mirror(client, hub):
    register(client)
    hub.offline = True
    r = register(client, username="other.one")
    assert r.status_code == 503 and r.json() == {"error": "hub_offline"}
    r = client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "secret1", "role": "student"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "stranger", "password": "secret1"})
    assert r.status_code == 503 and r.json() == {"error": "hub_offline"}


def test_legacy_local_account_is_migrated_to_the_hub(client, hub, gw):
    legacy = gw.users.by_username("hocsinh")  # seeded before the hub existed
    assert legacy.hub_id is None
    r = client.post("/api/auth/login", json={"username": "hocsinh", "password": "123456", "role": "student"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == legacy.id  # same local user (workspace kept)
    assert hub.accounts["hocsinh"]["password"] == "123456" and hub.accounts["hocsinh"]["account"]["role"] == "student"
    assert gw.users.by_username("hocsinh").hub_id == "a_1"
    # a wrong password on a legacy account never reaches register
    assert client.post("/api/auth/login", json={"username": "giaovien", "password": "bad"}).status_code == 401
    assert "giaovien" not in hub.accounts


# ---------------------------------------------------------------- teacher gate and verify
def test_teacher_gate_then_verify(client, hub, gw):
    teacher_login(client, hub, status="da_duyet")
    r = client.get("/api/teacher/courses")
    assert r.status_code == 403 and r.json() == {"error": "teacher_unverified"}
    assert client.get("/api/me").json()["teacher_status"] == "da_duyet"
    acc = client.get("/api/teacher/account").json()
    assert acc == {"teacher_status": "da_duyet", "reject_reason": None, "email": "hoa@gmail.com"}
    r = client.post("/api/teacher/account/verify", json={"code": "000000"})
    assert r.status_code == 400 and r.json() == {"error": "wrong_code"}
    r = client.post("/api/teacher/account/verify", json={"code": "123456"})
    assert r.status_code == 200 and r.json()["teacher_status"] == "xac_minh"
    assert client.get("/api/teacher/courses").status_code == 200
    assert client.post("/api/teacher/account/resend-code").json() == {"error": "bad_state"}  # hub: only while da_duyet


def test_account_refresh_resend_and_reject_reason(client, hub):
    teacher_login(client, hub, status="chua_nop")
    assert client.post("/api/teacher/account/resend-form").status_code == 204
    hub.accounts["thay.hoa"]["account"].update(teacher_status="tu_choi", reject_reason="Ảnh mờ")
    assert client.get("/api/teacher/account").json()["reject_reason"] == "Ảnh mờ"
    assert client.get("/api/me").json()["teacher_status"] == "tu_choi"
    assert client.post("/api/teacher/account/resend-form").status_code == 204


# ---------------------------------------------------------------- submit, list, withdraw, remove
def test_submit_sends_multipart_with_zip_sha_and_lists_hub_state(client, hub, runner, store):
    teacher_login(client, hub)
    cid = built_course(client, runner, store, None)
    confirm(client, cid, 1)
    rows = client.get("/api/teacher/courses").json()
    assert rows[0]["hub"] is None
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/submit")
    assert r.status_code == 200, r.text
    assert r.json()["hub"]["state"] == "cho_duyet"
    sent = hub.submits[0]
    assert sent["course_id"] == cid and sent["version"] == "1" and sent["title"] and sent["cover_name"].startswith("cover.")
    assert sent["pack_name"] == "pack-v1.zip"
    assert hashlib.sha256(sent["pack"]).hexdigest() == sent["zip_sha256"]
    assert "pack.json" in zipfile.ZipFile(io.BytesIO(sent["pack"])).namelist()
    entry, meta = json.loads(sent["entry"]), json.loads(sent["meta"])
    assert entry["id"] == cid and entry["version"] == 1 and entry["pack_sha256"] and entry["status"] == "live"
    assert meta["id"] == cid and sent["cover"]
    # still a draft locally, and the list now carries the hub state
    assert store.load_meta(cid).latest_published is None
    hubstate = {c["id"]: c["hub"] for c in client.get("/api/teacher/courses").json()}
    assert hubstate[cid]["state"] == "cho_duyet"
    # withdraw / remove proxy to the hub and refresh the cached list
    assert client.post(f"/api/teacher/courses/{cid}/withdraw").json()["hub"]["state"] == "rut_lai"
    assert client.get("/api/teacher/courses").json()[0]["hub"]["state"] == "rut_lai"
    assert client.post(f"/api/teacher/courses/{cid}/remove").json()["hub"]["state"] == "da_go"


def test_submit_runs_the_publish_checks_and_passes_hub_errors(client, hub, runner, store):
    teacher_login(client, hub)
    cid = built_course(client, runner, store, None)
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/submit")
    assert r.status_code == 409 and r.json()["error"] == "level_unconfirmed"
    confirm(client, cid, 1)
    for status, code in ((422, "hash_mismatch"), (413, "too_big"), (409, "not_owner"), (502, "script_failed")):
        hub.submit_error = (status, code)
        r = client.post(f"/api/teacher/courses/{cid}/versions/1/submit")
        assert (r.status_code, r.json()) == (status, {"error": code})
    hub.submit_error = None
    hub.offline = True
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/submit")
    assert r.status_code == 503 and r.json() == {"error": "hub_offline"}
    assert client.get("/api/teacher/courses").json()[0]["hub"] is None  # offline: null, not an error


# ---------------------------------------------------------------- forgot and reset
def test_forgot_and_reset_update_the_mirror_hash(client, hub, gw):
    register(client, email="lan@gmail.com")
    r = client.post("/api/auth/forgot", json={"login": "lan.nguyen"})
    assert r.json() == {"via": "email", "to": "n•••@gmail.com"}
    assert client.post("/api/auth/forgot", json={"login": "ghost"}).json() == {"via": "none"}
    assert client.post("/api/auth/forgot/request", json={"login": "ghost", "phone": "0900"}).status_code == 204
    r = client.post("/api/auth/reset", json={"login": "lan.nguyen", "code": "111111", "password": "newpass1"})
    assert r.status_code == 400 and r.json() == {"error": "wrong_code"}
    r = client.post("/api/auth/reset", json={"login": "lan.nguyen", "code": "654321", "password": "newpass1"})
    assert r.status_code == 204
    hub.offline = True  # the offline login uses the new hash
    ok = client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "newpass1"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "secret1"}).status_code == 401


def test_hub_off_keeps_the_old_behaviour(settings, clock, executor):
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        assert c.get("/api/auth/config").json() == {"signup": False}
        assert c.post("/api/auth/forgot", json={"login": "x"}).status_code == 404
        user = login(c, "giaovien", "123456", "teacher")
        assert "teacher_status" not in user and "email" not in user
        assert c.get("/api/teacher/account").json() == {"teacher_status": None, "reject_reason": None, "email": None}
        assert c.get("/api/teacher/courses").status_code == 200


# ---------------------------------------------------------------- owner push-all keeps the hub's courses
def test_push_catalog_keeps_courses_published_through_the_hub(tmp_path):
    drive = FakeDrive()
    st = secrets_settings(tmp_path)
    store = ContentStore(tmp_path / "owner" / "courses", lambda: __import__("datetime").datetime(2026, 10, 28, 3, tzinfo=__import__("datetime").UTC))
    pub = DrivePublisher(store, st, DriveClient(st, httpx.MockTransport(drive)))
    publish_course(store, "dien-truong")
    pub.push_all(lambda s: None)
    cat_id = pub._load()["catalog_id"]
    # the hub (Apps Script) adds a teacher course to the public catalog in place
    doc = json.loads(drive.files[cat_id]["content"])
    foreign = {**doc["courses"][0], "id": "toan-co-hoa", "title": "Toán của cô Hoa"}
    doc["courses"].append(foreign)
    doc["remote"]["toan-co-hoa"] = {"pack_id": "PACKX", "zip_sha256": "ab", "zip_bytes": 5, "cover_id": "COVX",
                                    "cover_name": "cover.png", "meta": {"id": "toan-co-hoa"}}
    drive.files[cat_id]["content"] = json.dumps(doc).encode()
    publish_course(store, "dem-tao", band="g1_5", title="Toán 1: Đếm táo")
    pub.push_all(lambda s: None)
    merged = json.loads(drive.files[pub._load()["catalog_id"]]["content"])
    ids = {c["id"] for c in merged["courses"]}
    assert ids == {"dien-truong", "dem-tao", "toan-co-hoa"}
    assert merged["remote"]["toan-co-hoa"]["pack_id"] == "PACKX" and "dem-tao" in merged["remote"]
    assert drive.files[pub._load()["catalog_id"]]["id"] == cat_id  # updated in place
