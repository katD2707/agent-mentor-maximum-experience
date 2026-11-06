import io
import json
import zipfile

import pytest
import yaml
from mentor_schemas import OutboxItem, OutboxKind, Profile, Routine


def test_tree_hides_internals(client, ncs_user, gw):
    uid = ncs_user["user_id"]
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


def test_read_write_conflict_and_history(client, ncs_user, gw):
    uid = ncs_user["user_id"]
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
        ("research/papers/a.md", 200),
    ],
)
def test_user_edit_rules(client, ncs_user, path, status):
    r = client.put("/api/workspace/file", json={"path": path, "content": "x"})
    assert r.status_code == status, r.text
    if status != 200:
        assert client.delete("/api/workspace/file", params={"path": path}).status_code == status


def test_export_zip(client, ncs_user):
    r = client.get("/api/workspace/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "AGENTS.md" in names and "me/profile.md" in names


def test_uploads_and_mobile_token(client, ncs_user, gw, clock):
    uid = ncs_user["user_id"]
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
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()  # sandbox_status
        cookies = dict(client.cookies)
        client.cookies.clear()  # the phone has no session
        assert "<form" in client.get(path).text
        r = client.post(path, files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")})
        assert r.status_code == 200 and r.json()["path"].startswith("inbox/")
        event = ws.receive_json()
        assert event == {"type": "upload_received", "path": r.json()["path"], "mime_type": "image/jpeg"}
        client.cookies.update(cookies)
    clock.advance(minutes=16)
    assert client.post(path, files={"file": ("photo.jpg", b"x", "image/jpeg")}).status_code == 404


def test_activity_newest_first(client, ncs_user, gw):
    uid = ncs_user["user_id"]
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


REPORT = "---\nperiod_start: 2026-10-14\nperiod_end: 2026-10-27\nincludes_wellbeing_nudge: false\n---\nNội dung\n"


def test_reports_list_only_sent(client, thpt_user, gw):
    uid = thpt_user["user_id"]
    draft = ".mentor/report-drafts/2026-10-28.md"
    # an unsent draft (and a legacy unsent file in reports/) is invisible to the learner everywhere
    gw.mirror.commit_files(uid, {draft: REPORT.encode(), "reports/2026-10-14.md": REPORT.encode()},
                           author="mentor", message="r")
    assert client.get("/api/reports").json() == []
    tree = [e["path"] for e in client.get("/api/workspace/tree").json()]
    assert not any("report-drafts" in p for p in tree)
    assert client.get("/api/workspace/file", params={"path": draft}).status_code == 404
    assert client.get("/api/workspace/raw", params={"path": draft}).status_code == 404
    assert client.get("/api/workspace/history", params={"path": draft}).status_code == 404
    names = zipfile.ZipFile(io.BytesIO(client.get("/api/workspace/export").content)).namelist()
    assert not any("report-drafts" in n for n in names) and "me/profile.md" in names

    status = client.portal.call(gw.dispatcher.dispatch, uid, Profile.THPT, [
        OutboxItem(kind=OutboxKind.PARENT_REPORT, payload={"path": draft}, dedupe_key="r1")])
    assert status == ["sent"]
    r = client.get("/api/reports").json()
    assert len(r) == 1 and r[0]["path"] == "reports/2026-10-28.md" and r[0]["sent_at"]
    assert r[0]["period_start"] == "2026-10-14" and r[0]["period_end"] == "2026-10-27"
    assert client.get("/api/workspace/file", params={"path": "reports/2026-10-28.md"}).json()["content"] == REPORT
    assert gw.mirror.read_text(uid, draft) is None  # moved, not copied
    assert gw.mirror.history(uid, "reports/2026-10-28.md")[0].author == "system"


def test_settings_roundtrip(client, thpt_user, gw):
    uid = thpt_user["user_id"]
    s = client.get("/api/settings").json()
    assert s["proactivity"] == "normal" and s["quiet_hours"] == ["22:00", "07:00"] and s["language"] == "vi"
    ids = {r["id"] for r in s["routines"]}
    assert {"nightly_reflection", "parent_report", "evening_review"} <= ids

    body = {
        "proactivity": "high",
        "quiet_hours": ["23:00", "06:30"],
        "language": "en",
        "routines": [
            # platform routines are echoed back unchanged
            *[x for x in s["routines"] if not x["user_editable"]],
            {"id": "evening_review", "enabled": False, "cron": "0 21 * * *", "job_kind": "routine"},
            {"id": "morning", "cron": "0 7 * * 1-5", "job_kind": "routine", "prompt": "Chào buổi sáng"},
        ],
    }
    r = client.put("/api/settings", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["proactivity"] == "high" and out["language"] == "en"
    by_id = {x["id"]: x for x in out["routines"]}
    assert by_id["nightly_reflection"]["enabled"] is True and by_id["nightly_reflection"]["cron"] == "30 23 * * *"
    assert "parent_report" in by_id
    assert by_id["evening_review"]["enabled"] is False
    assert by_id["morning"]["cron"] == "0 7 * * 1-5"
    saved = yaml.safe_load(gw.mirror.read_text(uid, "routines.yaml"))
    assert saved["proactivity"] == "high"
    assert gw.mirror.history(uid, "routines.yaml")[0].author == "user"

    # changing or dropping a platform routine is rejected
    locked = [x for x in s["routines"] if not x["user_editable"]]
    changed = [dict(x, enabled=False) if x["id"] == "nightly_reflection" else x for x in locked]
    r = client.put("/api/settings", json=dict(body, routines=changed))
    assert r.status_code == 422 and "nightly_reflection" in r.json()["detail"]
    r = client.put("/api/settings", json=dict(body, routines=locked[1:]))
    assert r.status_code == 422
    bad = dict(body, routines=[*locked, {"id": "x", "cron": "not a cron", "job_kind": "routine"}])
    assert client.put("/api/settings", json=bad).status_code == 422
    bad = dict(body, quiet_hours=["25:00", "07:00"])
    assert client.put("/api/settings", json=bad).status_code == 422


@pytest.mark.parametrize("routine,why", [
    ({"id": "pr", "cron": "0 19 * * 5", "job_kind": "parent_report"}, "do hệ thống tự lên lịch"),
    ({"id": "nr", "cron": "0 22 * * *", "job_kind": "nightly_reflection"}, "do hệ thống tự lên lịch"),
    ({"id": "parent_report2", "cron": "0 8 1 * *", "job_kind": "parent_report"}, "do hệ thống tự lên lịch"),
    ({"id": "spam", "cron": "* * * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
    ({"id": "spam", "cron": "*/30 * * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
    ({"id": "spam", "cron": "0,30 8 * * *", "job_kind": "routine"}, "tối đa 1 lần mỗi giờ"),
    ({"id": "spam", "cron": "* 7 * * 1", "job_kind": "routine", "enabled": False}, "tối đa 1 lần mỗi giờ"),
])
def test_settings_reject_platform_jobs_and_frequent_routines(client, thpt_user, gw, routine, why):
    uid = thpt_user["user_id"]
    s = client.get("/api/settings").json()
    before = gw.mirror.read_text(uid, "routines.yaml")
    r = client.put("/api/settings", json=dict(s, routines=[*s["routines"], routine]))
    assert r.status_code == 422 and why in r.json()["detail"], r.text
    assert gw.mirror.read_text(uid, "routines.yaml") == before
    # hourly is the minimum and is fine; platform routines are still echoed back unchanged
    ok = dict(routine, job_kind="routine", cron="0 * * * *")
    assert client.put("/api/settings", json=dict(s, routines=[*s["routines"], ok])).status_code == 200


def test_scheduler_skips_policy_breaking_routines_written_by_agent(client, thpt_user, gw, sandbox, clock):
    from datetime import UTC, datetime

    uid = thpt_user["user_id"]
    rf = gw.users.routines(gw.users.get(uid))
    extra = [
        Routine(id="sneaky", cron="* * * * *", job_kind="routine", prompt="x"),
        Routine(id="extra_report", cron="0 * * * *", job_kind="parent_report", user_editable=False),
        Routine(id="hourly", cron="0 * * * *", job_kind="routine", prompt="ok"),
    ]
    rf = rf.model_copy(update={"routines": [*rf.routines, *extra]})
    gw.mirror.commit_files(uid, {"routines.yaml": rf.to_yaml().encode()}, author="mentor", message="agent")
    clock.now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
    client.portal.call(gw.scheduler.tick, clock())
    clock.now = datetime(2026, 10, 28, 5, 0, 30, tzinfo=UTC)
    client.portal.call(gw.scheduler.tick, clock())
    client.portal.call(gw.runner.drain)
    sources = {j.prompt for j in sandbox.jobs}
    assert "ok" in sources and "x" not in sources
    assert not any(j.kind.value == "parent_report" for j in sandbox.jobs)


def test_refresh_content_updates_only_platform_files(client, thpt_user, gw, settings, tmp_path):
    import shutil

    from mentor_gateway.provisioning import refresh_content

    uid = thpt_user["user_id"]
    content = tmp_path / "content"
    shutil.copytree(settings.content_dir, content)
    assert refresh_content(content, gw.mirror, uid, Profile.THPT) == []

    gw.mirror.commit_files(uid, {"me/now.md": b"# learner text\n"}, author="user", message="t")
    (content / "AGENTS.md").write_bytes(b"# new rules\n")
    (content / "skills" / "thpt" / "spaced-review").mkdir()
    (content / "skills" / "thpt" / "spaced-review" / "SKILL.md").write_bytes(b"---\nname: spaced-review\n---\n")
    shutil.rmtree(content / "skills" / "core" / "memory-keeper")
    head = gw.mirror.head(uid)

    changed = refresh_content(content, gw.mirror, uid, Profile.THPT)
    assert changed == [".mentor/skills/core/memory-keeper/SKILL.md", ".mentor/skills/thpt/spaced-review/SKILL.md",
                       "AGENTS.md"]
    assert gw.mirror.read_text(uid, "AGENTS.md") == "# new rules\n"
    assert gw.mirror.blob_sha(uid, ".mentor/skills/core/memory-keeper/SKILL.md") is None
    assert gw.mirror.read_text(uid, "me/now.md") == "# learner text\n"
    assert gw.mirror.history(uid, limit=2)[1].sha == head
    assert refresh_content(content, gw.mirror, uid, Profile.THPT) == []
