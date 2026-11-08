import io
import json
import zipfile

import pytest
from gateway_fakes import FakeWS
from mentor_schemas import Profile, Routine

from mentor_gateway.routine_policy import routine_violation


def test_tree_hides_internals(client, student, gw):
    uid = student["user_id"]
    gw.mirror.commit_files(uid, {".mentor/activity.jsonl": b'{"x":1}\n', ".mentor/state.json": b"{}"},
                           author="mentor", message="t")
    tree = client.get("/api/workspace/tree").json()
    paths = {e["path"] for e in tree}
    assert ".mentor/activity.jsonl" in paths
    assert not any(p.startswith(".mentor/skills") or p == ".mentor/state.json" for p in paths)
    assert not any(p.startswith(".git") for p in paths)
    me = next(e for e in tree if e["path"] == "me")
    assert me["type"] == "dir" and me["modified_at"]
    f = next(e for e in tree if e["path"] == "me/profile.md")
    assert f["type"] == "file" and f["size"] > 0
    only_me = client.get("/api/workspace/tree", params={"prefix": "me/"}).json()
    assert {e["path"] for e in only_me} >= {"me", "me/profile.md"}
    assert all(e["path"] == "me" or e["path"].startswith("me/") for e in only_me)
    assert client.get("/api/workspace/file", params={"path": ".mentor/skills/core/memory-keeper/SKILL.md"}).status_code \
        == 404


def test_read_write_conflict_and_history(client, student, gw):
    uid = student["user_id"]
    r = client.get("/api/workspace/file", params={"path": "me/now.md"}).json()
    assert r["content"].startswith("# Bây giờ")
    base = r["sha"]

    r = client.put("/api/workspace/file", json={"path": "me/now.md", "content": "# Mới\n", "base_sha": base})
    assert r.status_code == 200
    new_sha = r.json()["sha"]
    assert new_sha != base
    assert gw.mirror.read_text(uid, "me/now.md") == "# Mới\n"

    # stale base -> 409 and nothing changes
    r = client.put("/api/workspace/file", json={"path": "me/now.md", "content": "lost", "base_sha": base})
    assert r.status_code == 409
    assert r.json()["current_sha"] == new_sha and isinstance(r.json()["detail"], str)
    assert gw.mirror.read_text(uid, "me/now.md") == "# Mới\n"

    # creating a file that already exists without base_sha is a conflict too
    assert client.put("/api/workspace/file", json={"path": "me/now.md", "content": "x"}).status_code == 409
    assert client.put("/api/workspace/file", json={"path": "goals/new.md", "content": "g"}).status_code == 200

    hist = client.get("/api/workspace/history", params={"path": "me/now.md"}).json()
    assert [h["author"] for h in hist] == ["user", "system"]
    commit = gw.mirror.history(uid, "me/now.md")[0]
    assert commit.author == "user"

    assert client.delete("/api/workspace/file", params={"path": "goals/new.md"}).json() == {"ok": True}
    assert client.get("/api/workspace/file", params={"path": "goals/new.md"}).status_code == 404
    assert client.delete("/api/workspace/file", params={"path": "goals/new.md"}).status_code == 404


@pytest.mark.parametrize(
    "path,status",
    [
        ("routines.yaml", 403),
        ("AGENTS.md", 403),
        ("reports/2026-11-01.md", 403),
        (".mentor/activity.jsonl", 403),
        ("events.jsonl", 403),
        ("inbox/x.md", 403),
        ("sessions/2026-10-28/s.md", 403),
        ("me", 403),
        ("../escape.md", 400),
        ("/abs.md", 400),
        (".git/config", 400),
        ("me/ok.md", 200),
        ("learning/math/mistakes.md", 200),
        ("research/papers/a.md", 403),
    ],
)
def test_user_edit_rules(client, student, path, status):
    r = client.put("/api/workspace/file", json={"path": path, "content": "x"})
    assert r.status_code == status, r.text
    if status != 200:
        assert client.delete("/api/workspace/file", params={"path": path}).status_code == status


def test_export_zip(client, student):
    r = client.get("/api/workspace/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "AGENTS.md" in names and "me/profile.md" in names


def test_uploads_and_mobile_token(client, student, gw, clock):
    uid = student["user_id"]
    r = client.post("/api/uploads", files={"file": ("Bài kiểm tra 15p.png", b"\x89PNG\r\n\x1a\n\x00", "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["path"].startswith("inbox/2026-10-28-") and body["path"].endswith(".png")
    assert body["mime_type"] == "image/png"
    assert gw.mirror.read(uid, body["path"])[0] == b"\x89PNG\r\n\x1a\n\x00"
    assert client.get("/api/workspace/file", params={"path": body["path"]}).status_code == 415
    assert client.get("/api/workspace/raw", params={"path": body["path"]}).content == b"\x89PNG\r\n\x1a\n\x00"

    tok = client.post("/api/uploads/mobile-token").json()
    url = tok["upload_url"]
    assert url.startswith("http://web.test/m/")  # the web app's phone page
    path = "/api/m/" + url.rsplit("/", 1)[1]  # what that page posts to
    ws = FakeWS()
    gw.hub.register(uid, ws)
    token = client.headers.pop("Authorization")  # the phone has no session
    assert "<form" in client.get(path).text
    r = client.post(path, files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")})
    assert r.status_code == 200 and r.json()["path"].startswith("inbox/")
    assert ws.sent == [{"type": "upload_received", "path": r.json()["path"], "mime_type": "image/jpeg"}]
    client.headers["Authorization"] = token
    clock.advance(minutes=16)
    assert client.post(path, files={"file": ("photo.jpg", b"x", "image/jpeg")}).status_code == 404


def test_activity_newest_first(client, student, gw):
    uid = student["user_id"]
    lines = [
        {"ts": f"2026-10-2{i}T10:00:00+07:00", "actor": "mentor", "action": "write_file", "target": "me/now.md",
         "summary": f"Cập nhật {i}"}
        for i in range(1, 6)
    ]
    data = "\n".join(json.dumps(x) for x in lines) + "\nnot json\n"
    gw.mirror.commit_files(uid, {".mentor/activity.jsonl": data.encode()}, author="mentor", message="a")
    r = client.get("/api/activity", params={"limit": 2}).json()
    assert [e["summary"] for e in r] == ["Cập nhật 5", "Cập nhật 4"]
    r = client.get("/api/activity", params={"before": "2026-10-23T10:00:00+07:00"}).json()
    assert [e["summary"] for e in r] == ["Cập nhật 2", "Cập nhật 1"]


@pytest.mark.parametrize("routine,why", [
    ({"id": "nr", "cron": "0 22 * * *", "job_kind": "nightly_reflection"}, "do hệ thống tự lên lịch"),
    ({"id": "spam", "cron": "* * * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
    ({"id": "spam", "cron": "*/30 * * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
    ({"id": "spam", "cron": "0,30 8 * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
])
def test_routine_policy_rejects_platform_jobs_and_frequent_routines(routine, why):
    assert why in routine_violation(Routine(**routine), from_user=True)
    ok = Routine(**dict(routine, job_kind="routine", cron="0 * * * *"))  # hourly is the minimum and is fine
    assert routine_violation(ok, from_user=True) is None


def test_scheduler_skips_policy_breaking_routines_written_by_agent(client, student, gw, executor, clock):
    from datetime import UTC, datetime

    uid = student["user_id"]
    rf = gw.users.routines(gw.users.get(uid))
    extra = [
        Routine(id="sneaky", cron="* * * * *", job_kind="routine", prompt="x"),
        Routine(id="extra_reflection", cron="0 * * * *", job_kind="nightly_reflection", user_editable=False),
        Routine(id="hourly", cron="0 * * * *", job_kind="routine", prompt="ok"),
    ]
    rf = rf.model_copy(update={"routines": [*rf.routines, *extra]})
    gw.mirror.commit_files(uid, {"routines.yaml": rf.to_yaml().encode()}, author="mentor", message="agent")
    clock.now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
    client.portal.call(gw.scheduler.tick, clock())
    clock.now = datetime(2026, 10, 28, 5, 0, 30, tzinfo=UTC)
    client.portal.call(gw.scheduler.tick, clock())
    client.portal.call(gw.runner.drain)
    sources = {j.prompt for j in executor.jobs}
    assert "ok" in sources and "x" not in sources
    assert [j.kind.value for j in executor.jobs].count("nightly_reflection") == 0  # the extra platform routine is skipped


def test_refresh_content_updates_only_platform_files(client, student, gw, settings, tmp_path):
    import shutil

    from mentor_gateway.provisioning import refresh_content

    uid = student["user_id"]
    content = tmp_path / "content"
    shutil.copytree(settings.content_dir, content)
    assert refresh_content(content, gw.mirror, uid, Profile.STUDENT) == []

    gw.mirror.commit_files(uid, {"me/now.md": b"# learner text\n"}, author="user", message="t")
    (content / "AGENTS.md").write_bytes(b"# new rules\n")
    (content / "skills" / "student" / "spaced-review").mkdir()
    (content / "skills" / "student" / "spaced-review" / "SKILL.md").write_bytes(b"---\nname: spaced-review\n---\n")
    shutil.rmtree(content / "skills" / "core" / "memory-keeper")
    head = gw.mirror.head(uid)

    changed = refresh_content(content, gw.mirror, uid, Profile.STUDENT)
    assert changed == [".mentor/skills/core/memory-keeper/SKILL.md", ".mentor/skills/student/spaced-review/SKILL.md",
                       "AGENTS.md"]
    assert gw.mirror.read_text(uid, "AGENTS.md") == "# new rules\n"
    assert gw.mirror.blob_sha(uid, ".mentor/skills/core/memory-keeper/SKILL.md") is None
    assert gw.mirror.read_text(uid, "me/now.md") == "# learner text\n"
    assert gw.mirror.history(uid, limit=2)[1].sha == head
    assert refresh_content(content, gw.mirror, uid, Profile.STUDENT) == []
