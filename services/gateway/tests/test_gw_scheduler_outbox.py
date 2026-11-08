from datetime import UTC, datetime

from gateway_fakes import FakeWS
from mentor_schemas import JobKind, JobRequest, OutboxItem, OutboxKind, Profile
from sqlalchemy import select

from mentor_gateway.db import JobRow, NotificationRow


def _tick(client, gw, now):
    started = client.portal.call(gw.scheduler.tick, now)
    client.portal.call(gw.runner.drain)
    return started


def _dispatch(client, gw, uid, items):
    return client.portal.call(gw.dispatcher.dispatch, uid, items)


def _notify(text, **kw):
    return OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": text, **kw})


def test_scheduler_fires_routine_with_frozen_clock(client, gw, student, executor, clock):
    uid = student["user_id"]
    # 10:00 local: schedules are computed, nothing is due yet
    assert _tick(client, gw, clock()) == []
    assert executor.jobs == []

    clock.now = datetime(2026, 10, 28, 13, 0, 30, tzinfo=UTC)  # 20:00:30 Asia/Ho_Chi_Minh
    started = _tick(client, gw, clock())
    assert started == [f"r-{uid}-evening_review-202610281300"]
    job = executor.jobs[-1]
    assert job.kind.value == "routine" and job.prompt == "Ôn tập buổi tối" and job.profile == Profile.STUDENT
    assert gw.jobs.get(started[0]).status == "ok"
    assert gw.jobs.get(started[0]).summary == "Đã chạy routine"

    # same minute again: no duplicate
    assert _tick(client, gw, clock()) == []

    # quiet hours do not hold jobs back: nightly reflection at 23:30 local
    clock.now = datetime(2026, 10, 28, 16, 31, tzinfo=UTC)
    _tick(client, gw, clock())
    assert executor.jobs[-1].kind.value == "nightly_reflection"
    assert len(executor.jobs) == 2


def test_teachers_and_unprovisioned_users_get_no_jobs(client, gw, executor, clock):
    # `hocsinh` never logged in (no workspace yet) and teachers have none: nothing to schedule
    clock.now = datetime(2026, 10, 28, 2, 0, tzinfo=UTC)
    _tick(client, gw, clock())
    clock.now = datetime(2026, 10, 28, 13, 1, tzinfo=UTC)
    _tick(client, gw, clock())
    assert executor.jobs == []


def test_without_an_executor_jobs_are_skipped(client, gw, student, clock):
    gw.runner.executor = None
    gw.jobs.enqueue(JobRequest(job_id="j-none", user_id=student["user_id"], profile=Profile.STUDENT,
                               kind=JobKind.ROUTINE), source="api")
    _tick(client, gw, clock())
    row = gw.jobs.get("j-none")
    assert row.status == "skipped" and row.error == "no job executor configured"


def test_next_wake_and_job_outbox(client, gw, student, executor, clock):
    uid = student["user_id"]
    executor.job_outbox = [OutboxItem(kind=OutboxKind.NEXT_WAKE,
                                      payload={"at": "2026-10-28T15:00:00+07:00", "job_kind": "intake",
                                               "prompt": "Xử lý inbox"}, dedupe_key="wake-1")]
    gw.jobs.enqueue(JobRequest(job_id="j-now", user_id=uid, profile=Profile.STUDENT, kind=JobKind.ROUTINE),
                    source="api")
    _tick(client, gw, clock())
    assert [j.job_id for j in executor.jobs] == ["j-now"]
    with gw.db.session() as s:
        wake = s.scalars(select(JobRow).where(JobRow.source == "next_wake")).one()
    assert wake.scheduled_for == datetime(2026, 10, 28, 8, 0, tzinfo=UTC) and wake.status == "pending"

    clock.now = datetime(2026, 10, 28, 8, 0, 1, tzinfo=UTC)
    _tick(client, gw, clock())
    assert executor.jobs[-1].kind.value == "intake" and executor.jobs[-1].prompt == "Xử lý inbox"


def test_outbox_dedupe_and_notification_policy(client, gw, student, clock):
    uid = student["user_id"]
    item = OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={"text": "Một"}, dedupe_key="k1")
    assert _dispatch(client, gw, uid, [item]) == ["pending"]  # nobody connected
    assert _dispatch(client, gw, uid, [item]) == ["duplicate"]

    ws = FakeWS()
    gw.hub.register(uid, ws)
    client.portal.call(gw.hub.flush, uid)  # pending flushed on connect
    assert ws.sent[-1]["type"] == "notification" and ws.sent[-1]["text"] == "Một"
    # normal proactivity: at most one per day, the rest waits
    assert _dispatch(client, gw, uid, [_notify("Hai")]) == ["pending"]
    assert len(ws.sent) == 1
    # next day, after quiet hours: bundled delivery
    clock.now = datetime(2026, 10, 29, 2, 0, tzinfo=UTC)  # 09:00 local
    client.portal.call(gw.hub.flush_all)
    assert ws.sent[-1]["text"] == "Hai"

    # quiet hours hold notifications even with a live connection
    clock.now = datetime(2026, 10, 29, 16, 0, tzinfo=UTC)  # 23:00 local
    assert _dispatch(client, gw, uid, [_notify("Khuya")]) == ["pending"]
    assert len(ws.sent) == 2


def test_proactivity_off_drops(client, gw, student):
    uid = student["user_id"]
    text = gw.mirror.read_text(uid, "routines.yaml").replace("proactivity: normal", "proactivity: \"off\"")
    gw.mirror.commit_files(uid, {"routines.yaml": text.encode()}, author="user", message="off")
    assert _dispatch(client, gw, uid, [_notify("x")]) == ["dropped"]
    with gw.db.session() as db:
        assert db.scalars(select(NotificationRow.status)).all() == ["dropped"]


def test_notify_without_text_is_ignored(client, gw, student):
    uid = student["user_id"]
    assert _dispatch(client, gw, uid, [OutboxItem(kind=OutboxKind.NOTIFY_USER, payload={})]) == ["ignored"]
