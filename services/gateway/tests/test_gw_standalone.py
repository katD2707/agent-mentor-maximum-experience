"""The self-contained desktop package: git-free mirror, local sign-up, standalone defaults, content seeding."""

import json
import os
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from practice_fixtures import build_content

from mentor_gateway import provisioning, standalone
from mentor_gateway.api import auth
from mentor_gateway.app import create_app
from mentor_gateway.context import use_file_mirror
from mentor_gateway.gitrepo import UserLocks
from mentor_gateway.mirror import StaleBaseError
from mentor_gateway.mirror_files import FileMirror, FileWorkspaceSync, blob_sha
from mentor_gateway.settings import Settings

FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"
P = "/api/practice"


# ---------------------------------------------------------------- the file mirror on its own


@pytest.fixture
def mirror(tmp_path) -> FileMirror:
    return FileMirror(tmp_path / "mirrors", UserLocks())


def test_commit_read_history_and_blob_ids_match_git(mirror):
    assert mirror.head("u1") is None and mirror.read("u1", "a.txt") is None and mirror.ls_tree("u1") == []
    c1 = mirror.commit_files("u1", {"a.txt": b"one", "d/b.txt": b"hai"}, author="system", message="first")
    c2 = mirror.commit_files("u1", {"a.txt": b"uno", "d/b.txt": None}, author="user", message="second")
    assert mirror.head("u1") == c2 != c1
    assert mirror.read("u1", "a.txt") == (b"uno", blob_sha(b"uno"))
    assert blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"  # git's empty blob
    assert mirror.read_text("u1", "d/b.txt") is None
    assert [e.path for e in mirror.ls_tree("u1")] == ["a.txt"]
    h = mirror.history("u1")
    assert [(c.sha, c.author, c.message) for c in h] == [(c2, "user", "second"), (c1, "system", "first")]
    assert [c.sha for c in mirror.history("u1", "d/b.txt")] == [c2, c1]
    assert [c.sha for c in mirror.history("u1", "a.txt", 1)] == [c2]


def test_tree_lists_folders_and_archive_has_files(mirror):
    mirror.commit_files("u1", {"x/y/z.md": b"zz", "top.md": b"t"}, author="mentor", message="m")
    assert [(e.path, e.type, e.size) for e in mirror.ls_tree("u1")] == [
        ("top.md", "file", 1), ("x", "dir", 0), ("x/y", "dir", 0), ("x/y/z.md", "file", 2)]
    z = zipfile.ZipFile(BytesIO(mirror.archive_zip("u1")))
    assert sorted(z.namelist()) == ["top.md", "x/y/z.md"] and z.read("x/y/z.md") == b"zz"
    assert zipfile.ZipFile(BytesIO(FileMirror(mirror.root, UserLocks()).archive_zip("nobody"))).namelist() == []


def test_stale_base_is_refused_and_nothing_is_written(mirror):
    mirror.commit_files("u1", {"f": b"1"}, author="user", message="m")
    sha = mirror.blob_sha("u1", "f")
    with pytest.raises(StaleBaseError) as e:
        mirror.commit_files("u1", {"f": b"2", "g": b"3"}, author="user", message="m", expected={"f": "0" * 40})
    assert e.value.current_sha == sha and mirror.read_text("u1", "g") is None
    mirror.commit_files("u1", {"f": b"2"}, author="user", message="m", expected={"f": sha})
    mirror.commit_files("u1", {"new": b"n"}, author="user", message="m", expected={"new": None})
    with pytest.raises(StaleBaseError):
        mirror.commit_files("u1", {"new": b"n2"}, author="user", message="m", expected={"new": None})


def test_rev_before_last_modified_and_batch_reads_by_revision(mirror):
    c1 = mirror.commit_files("u1", {"events.jsonl": b"a\n"}, author="system", message="1")
    mid = datetime.now(UTC) + timedelta(milliseconds=5)
    import time

    time.sleep(0.02)
    c2 = mirror.commit_files("u1", {"events.jsonl": b"a\nb\n", "other": b"o"}, author="system", message="2")
    assert mirror.rev_before("u1", mid) == c1 and mirror.rev_before("u1", mid - timedelta(days=1)) is None
    assert mirror.rev_before("u1", datetime.now(UTC) + timedelta(days=1)) == c2
    assert mirror.read_batch("u1", [f"{c1}:events.jsonl", f"{c2}:events.jsonl", f"{c1}:other", "main:other", f"{c1}:nope"]) == [
        "a\n", "a\nb\n", None, "o", None]
    lm = mirror.last_modified("u1")
    assert set(lm) == {"events.jsonl", "other"} and lm["events.jsonl"] >= lm["other"]


def test_log_survives_a_restart_and_a_torn_last_line(tmp_path):
    root, locks = tmp_path / "m", UserLocks()
    m = FileMirror(root, locks)
    c1 = m.commit_files("u1", {"f": b"1"}, author="user", message="m1")
    with (m.path("u1") / "log.jsonl").open("ab") as f:
        f.write(b'{"sha": "torn", "chang')  # the app was killed mid-write
    again = FileMirror(root, locks)
    assert again.head("u1") == c1 and again.read_text("u1", "f") == "1"
    c2 = again.commit_files("u1", {"f": b"2"}, author="user", message="m2")
    third = FileMirror(root, locks)
    assert third.head("u1") == c2 and third.read_text("u1", "f") == "2" and len(third.history("u1")) == 2


def test_delete_removes_the_learner(mirror):
    mirror.commit_files("u1", {"f": b"1"}, author="user", message="m")
    mirror.delete("u1")
    assert not mirror.exists("u1") and mirror.head("u1") is None


def test_workspace_sync_commits_the_staged_folder(tmp_path):
    locks = UserLocks()
    m = FileMirror(tmp_path / "mirrors", locks)
    sync = FileWorkspaceSync(tmp_path / "ws", m, locks)
    wd = sync.path("u1")
    (wd / "sub").mkdir(parents=True)
    (wd / "sub" / "a.md").write_text("x", encoding="utf-8")
    (wd / "b.md").write_text("y", encoding="utf-8")
    sync.init_from_dir("u1")
    assert m.read_text("u1", "sub/a.md") == "x" and m.history("u1")[0].message == "Khởi tạo workspace"
    assert sync.pull("u1") is None and sync.push("u1") == m.head("u1") and not sync.is_dirty("u1")


# ---------------------------------------------------------------- settings and selection


def test_standalone_env_defaults():
    s = Settings(env="standalone")
    assert s.signup and not s.seed_dev and not s.backups_scheduled and s.model_router_url is None
    assert Settings(env="prod").signup is False and Settings(env="prod", signup_enabled=True).signup
    assert use_file_mirror(s) and not use_file_mirror(Settings(env="dev", mirror_backend="git"))
    assert use_file_mirror(Settings(env="dev", mirror_backend="files"))
    assert Settings.from_env({"MENTOR_ENV": "standalone", "MENTOR_MIRROR": "files", "SIGNUP_ENABLED": "0"}).signup is False


def test_no_git_binary_selects_the_file_mirror(monkeypatch):
    monkeypatch.setattr("mentor_gateway.context.shutil.which", lambda _name: None)
    assert use_file_mirror(Settings(env="prod"))
    monkeypatch.setattr("mentor_gateway.context.shutil.which", lambda _name: "/usr/bin/git")
    assert not use_file_mirror(Settings(env="prod"))


def test_apply_defaults_for_the_sidecar(tmp_path):
    env = {"MENTOR_DATA_DIR": str(tmp_path / "d"), "MODEL_ROUTER_URL": "http://x", "MODEL_ROUTER_KEY": "k"}
    data = standalone.apply_defaults(env, 5123)
    assert data == tmp_path / "d" and env["MENTOR_ENV"] == "standalone"
    assert env["MENTOR_CONTENT_DIR"] == str(tmp_path / "d" / "content") and env["PUBLIC_BASE_URL"] == "http://127.0.0.1:5123"
    assert "MODEL_ROUTER_URL" not in env and "MODEL_ROUTER_KEY" not in env
    env2 = {"MENTOR_DATA_DIR": str(tmp_path), "MENTOR_ENV": "dev", "MENTOR_CONTENT_DIR": "elsewhere"}
    standalone.apply_defaults(env2, 1)
    assert env2["MENTOR_ENV"] == "dev" and env2["MENTOR_CONTENT_DIR"] == "elsewhere"  # explicit settings win


# ---------------------------------------------------------------- content seeding


@pytest.fixture
def sample(tmp_path) -> Path:
    s = tmp_path / "sample"
    (s / "skills").mkdir(parents=True)
    (s / "skills" / "core.md").write_text("v1", encoding="utf-8")
    (s / "AGENTS.md").write_text("agents", encoding="utf-8")
    (s / "courses" / "c1").mkdir(parents=True)
    (s / "courses" / "c1" / "course.json").write_text("{}", encoding="utf-8")
    (s / "courses" / "catalog.json").write_text('{"courses": []}', encoding="utf-8")
    (s / standalone.MARKER).write_text("stamp1\n", encoding="utf-8")
    return s


def test_seed_copies_base_and_sample_courses_into_an_empty_folder(tmp_path, sample):
    content = tmp_path / "data" / "content"
    done = standalone.seed_content(content, sample, remote_catalog=False)
    assert set(done) == {"AGENTS.md", "skills", "courses"}
    assert (content / "courses" / "c1" / "course.json").is_file() and (content / "courses" / "catalog.json").is_file()
    assert standalone.has_courses(content)


def test_seed_skips_courses_when_a_remote_catalog_is_configured_or_courses_exist(tmp_path, sample):
    remote = tmp_path / "r"
    assert "courses" not in standalone.seed_content(remote, sample, remote_catalog=True)
    assert (remote / "AGENTS.md").is_file() and not (remote / "courses").exists()
    have = tmp_path / "h"
    (have / "courses" / "mine").mkdir(parents=True)
    (have / "courses" / "mine" / "course.json").write_text("{}", encoding="utf-8")
    assert "courses" not in standalone.seed_content(have, sample, remote_catalog=False)
    assert not (have / "courses" / "c1").exists()


def test_seed_refreshes_base_files_only_when_the_sample_version_changes(tmp_path, sample):
    content = tmp_path / "content"
    standalone.seed_content(content, sample, remote_catalog=False)
    (content / "skills" / "core.md").write_text("edited", encoding="utf-8")
    assert standalone.seed_content(content, sample, remote_catalog=False) == []  # same version: left alone
    assert (content / "skills" / "core.md").read_text(encoding="utf-8") == "edited"
    (sample / standalone.MARKER).write_text("stamp2\n", encoding="utf-8")
    (sample / "skills" / "core.md").write_text("v2", encoding="utf-8")
    assert "skills" in standalone.seed_content(content, sample, remote_catalog=False)
    assert (content / "skills" / "core.md").read_text(encoding="utf-8") == "v2"


def test_seed_without_a_bundled_sample_is_harmless(tmp_path):
    assert standalone.seed_content(tmp_path / "c", None, remote_catalog=False) == []


def test_build_sample_script_filters_the_catalog(tmp_path):
    sys.path.insert(0, str(Path(__file__).parents[1] / "standalone"))
    try:
        import build_sample
    finally:
        sys.path.pop(0)
    src = tmp_path / "src"
    (src / "courses" / "a").mkdir(parents=True)
    (src / "courses" / "b").mkdir(parents=True)
    (src / "courses" / "a" / "course.json").write_text("{}", encoding="utf-8")
    (src / "courses" / "catalog.json").write_text(json.dumps({"courses": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
    (src / "AGENTS.md").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    build_sample.build(src, out, ("a",))
    assert [c["id"] for c in json.loads((out / "courses" / "catalog.json").read_text(encoding="utf-8"))["courses"]] == ["a"]
    assert not (out / "courses" / "b").exists() and (out / "AGENTS.md").is_file() and (out / standalone.MARKER).is_file()
    with pytest.raises(SystemExit):
        build_sample.build(src, out, ("nope",))


# ---------------------------------------------------------------- the whole app, no git, no dev accounts


@pytest.fixture(scope="module")
def practice_content(tmp_path_factory) -> Path:
    return build_content(FIXTURE_CONTENT, tmp_path_factory.mktemp("standalone-content") / "mentor-content")


@pytest.fixture
def no_git(monkeypatch):
    """Any call into git fails the test; the cached-git provisioning of conftest is replaced by the real code."""
    def boom(*a, **k):
        raise AssertionError(f"git was called: {a}")

    monkeypatch.setattr("mentor_gateway.mirror.run_git", boom)
    monkeypatch.setattr("mentor_gateway.gitrepo.run_git", boom)
    monkeypatch.setattr(auth, "provision_workspace", provisioning.provision_workspace)


@pytest.fixture
def app_client(tmp_path, practice_content, no_git):
    settings = Settings(env="standalone", data_dir=tmp_path / "var", content_dir=practice_content,
                        public_base_url="http://testserver", background_tasks=False)
    with TestClient(create_app(settings)) as c:
        yield c


def register(client, username="lan", password="matkhau", role="student", **extra) -> dict:
    r = client.post("/api/auth/register", json={"username": username, "password": password, "role": role, **extra})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return r.json()["user"]


def test_fresh_install_has_no_accounts_and_offers_signup(app_client):
    assert app_client.get("/api/auth/config").json() == {"signup": True}
    for dev in ("hocsinh", "giaovien"):
        r = app_client.post("/api/auth/login", json={"username": dev, "password": "123456", "role": "student"})
        assert r.status_code == 401
    assert app_client.get("/healthz").json() == {"status": "ok"}


def test_register_logs_in_and_rejects_bad_or_taken_names(app_client):
    user = register(app_client, "Lan.Nguyen", "matkhau", display_name="Lan")
    assert user["username"] == "lan.nguyen" and user["display_name"] == "Lan" and user["role"] == "student"
    assert app_client.get("/api/me").json()["id"] == user["id"]
    again = app_client.post("/api/auth/register", json={"username": "LAN.nguyen", "password": "khac123", "role": "student"})
    assert again.status_code == 409 and again.json() == {"error": "username_taken"}
    for bad in ({"username": "a", "password": "matkhau"}, {"username": "co dau cach", "password": "matkhau"},
                {"username": "binhthuong", "password": "12345"}):
        r = app_client.post("/api/auth/register", json={**bad, "role": "student"})
        assert r.status_code == 422 and r.json() == {"error": "bad_request"}
    ok = app_client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "matkhau", "role": "student"})
    assert ok.status_code == 200
    wrong_role = app_client.post("/api/auth/login", json={"username": "lan.nguyen", "password": "matkhau", "role": "teacher"})
    assert wrong_role.status_code == 403


def test_a_teacher_can_register_too_without_a_workspace(app_client):
    user = register(app_client, "thaygiao", "matkhau", role="teacher")
    assert user["role"] == "teacher"
    assert app_client.get("/api/catalog?all=1").status_code == 200


def test_register_is_not_available_outside_standalone(tmp_path, practice_content):
    settings = Settings(env="test", data_dir=tmp_path / "v", content_dir=practice_content, background_tasks=False)
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/auth/config").json() == {"signup": False}
        r = c.post("/api/auth/register", json={"username": "lan", "password": "matkhau", "role": "student"})
        assert r.status_code == 404


def test_standalone_uses_the_file_mirror_and_a_practice_session_leaves_evidence_without_git(app_client):
    user = register(app_client)
    gw = app_client.app.state.gw
    assert isinstance(gw.mirror, FileMirror) and isinstance(gw.sync, FileWorkspaceSync)
    assert gw.mirror.read_text(user["id"], "AGENTS.md") is not None  # provisioned from the content folder
    assert gw.mirror.history(user["id"])[0].message == "Khởi tạo workspace"
    app_client.patch("/api/me", json={"birth_year": 2010, "language": "vi"})
    subjects = app_client.get(f"{P}/subjects")
    assert subjects.status_code == 200 and subjects.json()
    s = app_client.post(f"{P}/sessions", json={"kind": "practice", "subject": "math", "minutes": 10, "goal": "balanced", "seed": 2})
    assert s.status_code == 200, s.text
    sid, items = s.json()["id"], s.json()["items"]
    from mentor_gateway.practice import scoring

    for i, it in enumerate(items[:3]):
        key = scoring.correct_answer_text(gw.practice.bank.items[it["id"]].doc)
        r = app_client.post(f"{P}/sessions/{sid}/answer", json={"position": i, "answer": key, "time_spent_sec": 20})
        assert r.status_code == 200, r.text
    rep = app_client.post(f"{P}/sessions/{sid}/finish")
    assert rep.status_code == 200, rep.text
    events = (gw.mirror.read_text(user["id"], "events.jsonl") or "").splitlines()
    assert len(events) == 3
    assert "| skill_id |" in (gw.mirror.read_text(user["id"], "learning/math/skills.md") or "")
    assert gw.mirror.history(user["id"], "events.jsonl", 1)[0].author == "system"
    # the web viewer's reads work on the same mirror
    tree = app_client.get("/api/workspace/tree")
    assert tree.status_code == 200
    assert os.path.isdir(gw.mirror.path(user["id"])) and not (gw.mirror.path(user["id"]) / "HEAD").exists()  # no git repo
