"""Courses on Google Drive: upload on publish, push-all, catalog sync, lazy pack download. Drive is faked in-process."""

import json
import re
import shutil
import urllib.parse
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from gateway_fakes import FakeExecutor, login
from test_gw_courses import publish_course

from mentor_gateway.app import create_app
from mentor_gateway.content import ContentStore
from mentor_gateway.content.drive import DriveClient, DrivePublisher, DriveSync, pack_zip
from mentor_gateway.content.remote import BadDownload, NeedsNetwork, RemoteCourses
from mentor_gateway.settings import Settings

NOW = lambda: datetime(2026, 10, 28, 3, 0, tzinfo=UTC)


class FakeDrive:
    """Just enough of Drive v3 (files.list/create/update, permissions) and the public download endpoint."""

    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.uploads = 0
        self.fail = False
        self.offline = False
        self.confirm_page = False
        self._n = 0
        self.pending: dict[str, tuple[str | None, dict]] = {}

    def _id(self) -> str:
        self._n += 1
        return f"FILEID{self._n:06d}abc"

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("offline")
        u, m = req.url, req.method
        if u.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        if u.host == "drive.usercontent.google.com":
            return self._download(req)
        if self.fail:
            return httpx.Response(503)
        if u.host == "upload.test":
            fid, meta = self.pending.pop(u.path)
            fid = fid or self._id()
            old = self.files.get(fid, {})
            self.files[fid] = {**old, **meta, "id": fid, "content": req.content}
            self.uploads += 1
            return httpx.Response(200, json={"id": fid})
        path = u.path
        if path.startswith("/upload/drive/v3/files"):
            fid = path.rsplit("/", 1)[-1] if path.count("/") > 4 else None
            tok = f"/{len(self.pending) + self.uploads}x"
            self.pending[tok] = (fid, json.loads(req.content))
            return httpx.Response(200, headers={"Location": "https://upload.test" + tok})
        if path.endswith("/permissions"):
            fid = path.split("/")[-2]
            self.files[fid]["public"] = True
            return httpx.Response(200, json={})
        if m == "GET" and path == "/drive/v3/files":
            q = urllib.parse.unquote(u.params["q"])
            name = re.search(r"name = '(.*?)'", q).group(1)
            parent = (re.search(r"'([^']+)' in parents", q) or [None, None])[1]
            folder = "mimeType = " in q
            hits = [{"id": f["id"], "name": f["name"], "appProperties": f.get("appProperties")} for f in self.files.values()
                    if f["name"] == name and f.get("parents", [None])[0] == parent and bool(f.get("folder")) == folder]
            return httpx.Response(200, json={"files": hits})
        if m == "POST" and path == "/drive/v3/files":
            meta = json.loads(req.content)
            fid = self._id()
            self.files[fid] = {**meta, "id": fid, "folder": True}
            return httpx.Response(200, json={"id": fid})
        raise AssertionError(f"unexpected {m} {u}")

    def _download(self, req: httpx.Request) -> httpx.Response:
        p = dict(req.url.params)
        f = self.files.get(p.get("id", ""))
        if not f or not f.get("public"):
            return httpx.Response(404)
        if self.confirm_page and "uuid" not in p:
            page = ('<html><form action="https://drive.usercontent.google.com/download" method="get">'
                    f'<input type="hidden" name="id" value="{p["id"]}"><input type="hidden" name="confirm" value="t">'
                    '<input type="hidden" name="uuid" value="u-1"></form>Google Drive can\'t scan this file</html>')
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=page)
        return httpx.Response(200, content=f["content"], headers={"content-type": "application/octet-stream", "etag": '"e1"'})


@pytest.fixture
def drive():
    return FakeDrive()


def secrets_settings(tmp_path, **kw) -> Settings:
    d = tmp_path / ".secrets"
    d.mkdir(exist_ok=True)
    (d / "oc.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))
    (d / "tok.json").write_text(json.dumps({"refresh_token": "r"}))
    return Settings(env="test", data_dir=tmp_path / "var", drive_client_file=d / "oc.json", drive_token_file=d / "tok.json",
                    background_tasks=False, **kw)


@pytest.fixture
def owner(tmp_path, drive):
    st = secrets_settings(tmp_path)
    store = ContentStore(tmp_path / "owner" / "courses", NOW)
    pub = DrivePublisher(store, st, DriveClient(st, httpx.MockTransport(drive)))
    return store, pub


def catalog_doc(drive: FakeDrive, pub: DrivePublisher) -> dict:
    return json.loads(drive.files[pub._load()["catalog_id"]]["content"])


# ---------------------------------------------------------------- upload side
def test_push_all_uploads_public_files_and_catalog_then_is_idempotent(owner, drive):
    store, pub = owner
    publish_course(store, "dien-truong")
    publish_course(store, "dem-tao", band="g1_5", title="Toán 1: Đếm táo")
    out: list[str] = []
    fid = pub.push_all(out.append)
    first = drive.uploads
    assert first == 2 * 3 + 1  # pack, course.json, cover per course + catalog
    assert all(f.get("public") for f in drive.files.values() if not f.get("folder"))
    assert any(fid in line for line in out)
    doc = catalog_doc(drive, pub)
    assert {c["id"] for c in doc["courses"]} == {"dien-truong", "dem-tao"}
    r = doc["remote"]["dien-truong"]
    assert r["pack_id"] in drive.files and r["meta"]["id"] == "dien-truong"
    entry = next(c for c in doc["courses"] if c["id"] == "dien-truong")
    assert entry["pack_sha256"] and entry["pack_bytes"] and entry["version"] == 1
    assert "Authorization" not in json.dumps(doc)

    pub.push_all(lambda s: None)
    assert drive.uploads == first  # nothing changed: nothing sent
    assert pub.status()["not_synced"] == []


def test_changed_pack_is_updated_in_place(owner, drive):
    store, pub = owner
    publish_course(store, "dien-truong")
    pub.push_all(lambda s: None)
    n = len(drive.files)
    store.set_labels("dien-truong", 1, topics=["điện"])  # latest published: catalog + course.json change, pack does not
    pub.push_course("dien-truong")
    pub.push_catalog()
    assert len(drive.files) == n  # updated, not duplicated
    assert catalog_doc(drive, pub)["remote"]["dien-truong"]["meta"]["topics"] == ["điện"]


def test_publish_uploads_in_the_background(tmp_path, drive):
    st = secrets_settings(tmp_path)
    store = ContentStore(tmp_path / "owner" / "courses", NOW)
    pub = DrivePublisher(store, st, DriveClient(st, httpx.MockTransport(drive)))
    sync = DriveSync(pub, sleep=lambda s: None)
    store.on_published = sync.notify
    publish_course(store, "dien-truong")
    assert sync.wait_idle()
    assert not sync.unsynced("dien-truong")
    assert [c["id"] for c in catalog_doc(drive, pub)["courses"]] == ["dien-truong"]


def test_keeps_failing_marks_course_unsynced_then_recovers(tmp_path, drive):
    st = secrets_settings(tmp_path)
    store = ContentStore(tmp_path / "owner" / "courses", NOW)
    pub = DrivePublisher(store, st, DriveClient(st, httpx.MockTransport(drive)))
    sleeps: list[float] = []
    sync = DriveSync(pub, sleep=sleeps.append, base_delay=1)
    store.on_published = sync.notify
    drive.fail = True
    publish_course(store, "dien-truong")  # returns at once even though Drive is down
    assert sync.wait_idle()
    assert sync.unsynced("dien-truong")
    assert sleeps[:3] == [1, 2, 4]  # backoff
    drive.fail = False
    sync.notify("dien-truong")
    assert sync.wait_idle()
    assert not sync.unsynced("dien-truong")


def test_pack_zip_is_deterministic_and_has_no_sources(owner):
    store, _ = owner
    publish_course(store, "dien-truong")
    src = store.version_dir("dien-truong", 1) / "sources"
    src.mkdir()
    (src / "secret.txt").write_text("teacher only")
    a = pack_zip(store, "dien-truong", 1)
    assert a == pack_zip(store, "dien-truong", 1)
    assert b"teacher only" not in a


# ---------------------------------------------------------------- download side
@pytest.fixture
def published(owner, drive):
    store, pub = owner
    publish_course(store, "dien-truong")
    fid = pub.push_all(lambda s: None)
    return store, fid


def installed(tmp_path, drive, fid, name="app") -> RemoteCourses:
    st = Settings(env="test", data_dir=tmp_path / name / "var", content_dir=tmp_path / name / "content",
                  remote_catalog_url=f"https://drive.google.com/file/d/{fid}/view?usp=sharing")
    return RemoteCourses(st, ContentStore(st.courses_dir, NOW), httpx.MockTransport(drive))


def test_catalog_sync_then_lazy_verified_pack_download(tmp_path, drive, published):
    store, fid = published
    rc = installed(tmp_path, drive, fid)
    assert rc.sync_catalog() is True
    cat = rc.store.load_catalog()
    assert [c.id for c in cat.courses] == ["dien-truong"]
    assert not rc.has_pack("dien-truong", 1)  # catalog only: nothing downloaded yet
    assert rc.store.load_meta("dien-truong").latest_published == 1
    assert rc.sync_catalog() is False  # unchanged: cheap

    rc.ensure_pack("dien-truong", 1)
    assert rc.store.pack_bytes_raw("dien-truong", 1) == store.pack_bytes_raw("dien-truong", 1)
    assert rc.store.asset_path("dien-truong", 1, "l1/v.mp4").stat().st_size > 0
    rc.ensure_cover("dien-truong")
    assert rc.store.cover_path("dien-truong").is_file()


def test_corrupt_download_is_rejected_and_not_installed(tmp_path, drive, published):
    _, fid = published
    rc = installed(tmp_path, drive, fid)
    rc.sync_catalog()
    pack_id = rc.info("dien-truong")["pack_id"]
    drive.files[pack_id]["content"] = drive.files[pack_id]["content"][:-50] + b"x" * 50
    with pytest.raises(BadDownload):
        rc.ensure_pack("dien-truong", 1)
    assert not rc.has_pack("dien-truong", 1)
    assert not list((rc.store.root / "dien-truong").glob(".dl-*"))


def test_inner_pack_sha_mismatch_is_rejected(tmp_path, drive, published):
    """A zip the catalog vouches for but whose pack.json is not the published one."""
    store, fid = published
    rc = installed(tmp_path, drive, fid)
    rc.sync_catalog()
    info = rc.info("dien-truong")
    bad = rc.store.course_dir("dien-truong") / "x"
    shutil.copytree(store.version_dir("dien-truong", 1), bad)
    (bad / "pack.json").write_bytes((bad / "pack.json").read_bytes().replace("Nội dung".encode(), "Nội dunG".encode()))
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in bad.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(bad).as_posix())
    shutil.rmtree(bad)
    drive.files[info["pack_id"]]["content"] = buf.getvalue()
    from mentor_gateway.content.store import sha256_bytes

    info_state = rc._state()
    info_state["courses"]["dien-truong"]["zip_sha256"] = sha256_bytes(buf.getvalue())
    rc.state_path.write_text(json.dumps(info_state))
    with pytest.raises(BadDownload):
        rc.ensure_pack("dien-truong", 1)


def test_virus_scan_confirm_page_is_followed(tmp_path, drive, published):
    _, fid = published
    drive.confirm_page = True
    rc = installed(tmp_path, drive, fid)
    assert rc.sync_catalog() is True
    rc.ensure_pack("dien-truong", 1)
    assert rc.has_pack("dien-truong", 1)


def test_offline_keeps_cached_courses_and_refuses_uncached(tmp_path, drive, owner):
    store, pub = owner
    publish_course(store, "dien-truong")
    publish_course(store, "dem-tao", band="g1_5", title="Toán 1: Đếm táo")
    fid = pub.push_all(lambda s: None)
    rc = installed(tmp_path, drive, fid)
    rc.sync_catalog()
    rc.ensure_pack("dien-truong", 1)
    drive.offline = True
    assert rc.sync_catalog() is False  # offline: local catalog stays
    assert len(rc.store.load_catalog().courses) == 2
    rc2 = RemoteCourses(rc.settings, rc.store, httpx.MockTransport(drive))
    rc2.ensure_pack("dien-truong", 1)  # cached: no network needed
    with pytest.raises(NeedsNetwork):
        rc2.ensure_pack("dem-tao", 1)


def test_api_serves_cached_downloads_lazily_and_says_needs_network_offline(tmp_path, drive, owner):
    store, pub = owner
    publish_course(store, "dien-truong")
    fid = pub.push_all(lambda s: None)
    st = Settings(env="test", data_dir=tmp_path / "ivar", content_dir=tmp_path / "icontent", public_base_url="http://testserver",
                  web_origin="http://web.test", background_tasks=False, seed_dev_accounts=True,
                  remote_catalog_url=fid)
    app = create_app(st, clock=NOW, executor=FakeExecutor())
    with TestClient(app) as c:
        remote = app.state.content.remote
        remote.http = httpx.Client(transport=httpx.MockTransport(drive), follow_redirects=True)
        remote.sync_catalog()
        login(c)
        c.patch("/api/me", json={"language": "vi"})
        assert c.get("/api/catalog").json()["courses"][0]["id"] == "dien-truong"
        drive.offline = True
        r = c.get("/api/courses/dien-truong/versions/1/pack")
        assert r.status_code == 503 and r.json()["error"] == "needs_network"
        assert c.get("/api/courses/dien-truong").json()["needs_network"] is True
        drive.offline = False
        r = c.get("/api/courses/dien-truong/versions/1/pack")
        assert r.status_code == 200
        assert r.content == store.pack_bytes_raw("dien-truong", 1)
        drive.offline = True  # now cached: works without a network
        assert c.get("/api/courses/dien-truong/versions/1/pack").status_code == 200
        assert c.get("/api/courses/dien-truong/versions/1/assets/l1/a.png").status_code == 200
        assert c.get("/api/courses/dien-truong").json()["tree"]
        assert c.get("/api/courses/dien-truong/cover").status_code in (200, 503)


def test_local_content_unchanged_without_remote_catalog(client):
    assert client.app.state.content.remote is None
    assert client.app.state.content.drive_sync is None
