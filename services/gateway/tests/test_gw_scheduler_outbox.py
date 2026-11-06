import io
import zipfile
from datetime import UTC, datetime

import pytest
from gateway_fakes import recv_until
from mentor_schemas import OutboxItem, OutboxKind, Profile
from sqlalchemy import select

from mentor_gateway.db import AuditRow, JobRow, NotificationRow


def _tick(client, gw, now):
    started = client.portal.call(gw.scheduler.tick, now)
    client.portal.call(gw.runner.drain)
    return started


def _dispatch(client, gw, uid, items, profile=Profile.THPT):
    return client.portal.call(gw.dispatcher.dispatch, uid, profile, items)


def test_scheduler_fires_routine_with_frozen_clock(client, gw, thpt_user, sandbox, clock):
    uid = thpt_user["user_id"]
    # 10:00 local: schedules are computed, nothing is due yet
    assert _tick(client, gw, clock()) == []
    assert sandbox.jobs == []

    clock.now = datetime(2026, 10, 28, 13, 0, 30, tzinfo=UTC)  # 20:00:30 Asia/Ho_Chi_Minh
    started = _tick(client, gw, clock())
    assert started == [f"r-{uid}-evening_review-202610281300"]
    job = sandbox.jobs[-1]
    assert job.kind.value == "routine" and job.prompt == "Ôn tập buổi tối" and job.profile == Profile.THPT
    assert gw.jobs.get(started[0]).status == "ok"
    assert gw.jobs.get(started[0]).summary == "Đã chạy routine"

    # same minute again: no duplicate
    assert _tick(client, gw, clock()) == []

    # quiet hours do not hold jobs back: nightly reflection at 23:30 local
    clock.now = datetime(2026, 10, 28, 16, 31, tzinfo=UTC)
    _tick(client, gw, clock())
    assert sandbox.jobs[-1].kind.value == "nightly_reflection"
    assert len(sandbox.jobs) == 2


def test_disabled_routine_and_inactive_users_skipped(client, gw, sandbox, clock):
    from gateway_fakes import onboard

    onboard(client, "pending@example.com", "thpt")  # needs_parent: no jobs
    clock.now = datetime(2026, 10, 28, 2, 0, tzinfo=UTC)
    _tick(client, gw, clock())
    clock.now = datetime(2026, 10, 28, 13, 1, tzinfo=UTC)
    _tick(client, gw, clock())
    assert sandbox.jobs == []


def test_next_wake_and_job_outbox(client, gw, ncs_user, sandbox, clock):
    uid = ncs_user["user_id"]
    sandbox.job_outbox = [OutboxItem(kind=OutboxKind.NEXT_WAKE,
                                     payload={"at": "2026-10-28T15:00:00+07:00", "job_kind": "intake",
                                              "prompt": "Xử lý inbox"}, dedupe_key="wake-1")]
    from mentor_schemas import JobKind, JobRequest

    gw.jobs.enqueue(JobRequest(job_id="j-now", user_id=uid, profile=Profile.NCS, kind=JobKind.ROUTINE), source="api")
    _tick(client, gw, clock())
    assert [j.job_id for j in sandbox.jobs] == ["j-now"]
    with gw.db.session() as s:
        wake = s.scalars(select(JobRow).where(JobRow.source == "next_wake")).one()
    assert wake.scheduled_for == datetime(2026, 10, 28, 8, 0, tzinfo=UTC) and wake.status == "pending"

    clock.now = datetime(2026, 10, 28, 8, 0, 1, tzinfo=UTC)
    _tick(client, gw, clock())
    assert sandbox.jobs[-1].kind.value == "intake" and sandbox.jobs[-1].prompt == "Xử lý inbox"


def test_outbox_dedupe_and_notification_policy(client, gw, ncs_user, clock):
    uid = ncs_user["user_id"]
    item = OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Một"}, dedupe_key="k1")
    assert _dispatch(client, gw, uid, [item], Profile.NCS) == ["pending"]  # nobody connected
    assert _dispatch(client, gw, uid, [item], Profile.NCS) == ["duplicate"]

    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()  # sandbox_status
        note = ws.receive_json()  # pending flushed on connect
        assert note["type"] == "notification" and note["text"] == "Một"
        # normal proactivity: at most one per day, the rest waits
        assert _dispatch(client, gw, uid, [OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Hai"})],
                         Profile.NCS) == ["pending"]
        # next day, after quiet hours: bundled delivery
        clock.now = datetime(2026, 10, 29, 2, 0, tzinfo=UTC)  # 09:00 local
        client.portal.call(gw.hub.flush_all)
        assert ws.receive_json()["text"] == "Hai"

    # quiet hours hold notifications even with a live connection
    clock.now = datetime(2026, 10, 29, 16, 0, tzinfo=UTC)  # 23:00 local
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        assert _dispatch(client, gw, uid, [OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Khuya"})],
                         Profile.NCS) == ["pending"]


def test_proactivity_off_drops(client, gw, ncs_user):
    uid = ncs_user["user_id"]
    s = client.get("/api/settings").json()
    client.put("/api/settings", json=dict(s, proactivity="off"))
    assert _dispatch(client, gw, uid, [OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "x"})],
                     Profile.NCS) == ["dropped"]
    with gw.db.session() as db:
        assert db.scalars(select(NotificationRow.status)).all() == ["dropped"]


def test_parent_report_dispatch(client, gw, thpt_user):
    uid = thpt_user["user_id"]
    body = "---\nperiod_start: 2026-10-14\nperiod_end: 2026-10-27\n---\nCon học đều đặn.\n"
    draft = ".mentor/report-drafts/2026-10-28.md"
    gw.mirror.commit_files(uid, {draft: body.encode()}, author="mentor", message="r")
    items = [OutboxItem(kind=OutboxKind.PARENT_REPORT, payload={"path": draft}, dedupe_key="r1")]
    assert _dispatch(client, gw, uid, items) == ["sent"]
    assert _dispatch(client, gw, uid, items) == ["duplicate"]
    assert gw.parent.service.reports == [(uid, body)]
    assert client.get("/api/reports").json()[0]["sent_at"]
    assert gw.mirror.read_text(uid, "reports/2026-10-28.md") == body and gw.mirror.read_text(uid, draft) is None

    for path in ("me/profile.md", "reports/2026-10-28.md", ".mentor/wellbeing.jsonl", ".mentor/report-drafts/a/b.md"):
        bad = [OutboxItem(kind=OutboxKind.PARENT_REPORT, payload={"path": path})]
        assert _dispatch(client, gw, uid, bad)[0].startswith("error"), path
    assert len(gw.parent.service.reports) == 1


@pytest.mark.parametrize("leak,check", [
    ("Liên hệ cô giáo: co.lan@truong.edu.vn.", "email"),
    ("Số của bạn ấy là 0912.345.678.", "phone"),
    ("Chi tiết trong me/now.md và sessions/2026-10-20/s-1.md.", "workspace_path"),
    ("Bài 15 phút được 5/10.", "forbidden:0"),
    ("Con nói “mệt quá”.", "forbidden:2"),
])
def test_gateway_rechecks_report_before_sending(client, gw, thpt_user, leak, check):
    """The sandbox's check_report is not trusted: a report that slipped past it is refused and audited."""
    uid = thpt_user["user_id"]
    body = f"---\nperiod_start: 2026-10-14\nperiod_end: 2026-10-27\n---\nCon học đều đặn. {leak}\n"
    draft = ".mentor/report-drafts/2026-10-28.md"
    gw.mirror.commit_files(uid, {draft: body.encode()}, author="mentor", message="r")
    items = [OutboxItem(kind=OutboxKind.PARENT_REPORT, payload={"path": draft}, dedupe_key="r-leak")]
    assert _dispatch(client, gw, uid, items) == ["blocked"]
    assert gw.parent.service.reports == []
    assert client.get("/api/reports").json() == [] and gw.mirror.read_text(uid, "reports/2026-10-28.md") is None
    audit = [(k, d) for k, d, _ in gw.parent.store.read_audit(uid) if k == "parent_report_blocked"]
    assert len(audit) == 1 and check in audit[0][1] and leak not in audit[0][1]  # check names only, no content


def test_crisis_alert_audited_and_invisible(client, gw, thpt_user):
    uid = thpt_user["user_id"]
    items = [OutboxItem(kind=OutboxKind.CRISIS_ALERT, payload={"category": "self_harm"}, dedupe_key="c1")]
    assert _dispatch(client, gw, uid, items) == ["sent"]
    assert _dispatch(client, gw, uid, items) == ["duplicate"]
    assert gw.parent.service.alerts == [(uid, "self_harm")]
    with gw.db.session() as s:
        kinds = s.scalars(select(AuditRow.kind).where(AuditRow.student_user_id == uid)).all()
    assert "crisis_alert" in kinds and "crisis_alert_dispatch" in kinds

    # nothing about it is reachable through any learner-facing endpoint
    needles = ("crisis", "self_harm", "khủng hoảng")
    blobs = [client.get("/api/workspace/tree").text, client.get("/api/activity").text,
             client.get("/api/workspace/history").text, client.get("/api/reports").text, client.get("/api/me").text]
    for e in client.get("/api/workspace/tree").json():
        if e["type"] == "file":
            r = client.get("/api/workspace/file", params={"path": e["path"]})
            if r.status_code == 200:
                blobs.append(r.text)
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/workspace/export").content))
    blobs += [z.read(n).decode("utf-8", "replace") for n in z.namelist()]
    for blob in blobs:
        assert not any(n in blob.lower() for n in needles)


def test_crisis_alert_ignored_for_ncs(client, gw, ncs_user):
    uid = ncs_user["user_id"]
    items = [OutboxItem(kind=OutboxKind.CRISIS_ALERT, payload={"category": "self_harm"})]
    assert _dispatch(client, gw, uid, items, Profile.NCS) == ["ignored"]
    assert gw.parent.service.alerts == []


def test_idle_sandbox_goes_to_sleep(client, gw, ncs_user, backend, clock):
    with client.websocket_connect("/api/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "client_msg_id": "c", "text": "hi", "attachments": []})
        recv_until(ws, "turn_done")
        assert backend.running
        clock.advance(minutes=14)
        _tick(client, gw, clock())
        assert backend.running
        clock.advance(minutes=2)
        _tick(client, gw, clock())
        assert not backend.running
        assert recv_until(ws, "sandbox_status")[-1]["state"] == "sleeping"
