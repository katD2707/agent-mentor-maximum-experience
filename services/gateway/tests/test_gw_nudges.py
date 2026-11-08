"""Interaction layer, owner N (CONTRACTS section 9): rich notifications, actions, proactive routines, engagement,
Web Push."""

import base64
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from gateway_fakes import FakeWS, new_student
from mentor_schemas import OutboxItem, OutboxKind
from pywebpush import WebPushException
from sqlalchemy import select

from mentor_gateway import push as push_mod
from mentor_gateway.notifications import PLANNER_SOURCE, Nudge
from mentor_gateway.planner.tables import Reminder
from mentor_gateway.db import AuditRow, JobRow, NotificationActionRow, NotificationRow, PushSubscription

CHECKIN = {
    "text": "3 việc hôm nay: ôn hàm số, đọc 1 bài, ngủ sớm.", "kind": "checkin", "title": "Chào buổi sáng",
    "actions": [{"id": "answer:ok", "label": "Chốt vậy"}, {"id": "start_focus", "label": "Bắt đầu 25 phút"},
                {"id": "snooze_1h", "label": "Để sau"}],
    "mascot": "wave", "prefill": "Mình muốn đổi kế hoạch hôm nay",
}


def _dispatch(client, gw, uid, payloads, extra=()):
    items = [*extra, *(OutboxItem(kind=OutboxKind.NOTIFY_USER, payload=p) for p in payloads)]
    return client.portal.call(gw.dispatcher.dispatch, uid, items)


def _tick(client, gw, now):
    client.portal.call(gw.scheduler.tick, now)
    client.portal.call(gw.runner.drain)


def _ids(gw, uid):
    with gw.db.session() as s:
        return list(s.scalars(select(NotificationRow.id).where(NotificationRow.user_id == uid)
                              .order_by(NotificationRow.id)))


def _set_routines(gw, uid, body: str) -> None:
    gw.mirror.commit_files(uid, {"routines.yaml": body.encode()}, author="user", message="routines")


def test_rich_fields_round_trip_and_actions(client, gw, student, executor, clock):
    uid = student["user_id"]
    gw.settings.vapid_public_key = None  # push off: delivery over the WebSocket only
    assert _dispatch(client, gw, uid, [CHECKIN, {"text": "Tin cũ chỉ có text"}]) == ["pending", "pending"]
    nid, old_id = _ids(gw, uid)
    ws = FakeWS()
    gw.hub.register(uid, ws)
    client.portal.call(gw.hub.flush, uid)
    (note,) = ws.sent  # normal proactivity: both bundled into one message
    assert note["type"] == "notification" and note["id"] == nid and note["kind"] == "checkin"
    assert note["title"] == "Chào buổi sáng" and note["body"] == CHECKIN["text"] and note["mascot"] == "wave"
    assert note["actions"] == CHECKIN["actions"] and note["prefill"] == CHECKIN["prefill"]
    assert note["text"] == CHECKIN["text"] + "\nTin cũ chỉ có text" and note["bundled_ids"] == [old_id]

    listed = client.get("/api/notifications").json()
    assert [n["id"] for n in listed] == [old_id, nid]
    assert listed[0]["kind"] == "nudge" and listed[0]["body"] == "Tin cũ chỉ có text" and listed[0]["actions"] == []
    assert listed[1]["actions"] == CHECKIN["actions"] and listed[1]["read_at"] is None

    act = lambda a, i=nid: client.post(f"/api/notifications/{i}/action", json={"action": a})
    r = act("open")
    assert r.status_code == 200 and r.json()["prefill"] == CHECKIN["prefill"]
    assert act("answer:nope").status_code == 422  # not offered
    assert act("rm -rf").status_code == 422
    assert act("start_focus", old_id).status_code == 422  # the old row offers no start_focus

    # answer: stored + a short agent job (started at once, not on the next tick); idempotent on a double tap
    first = act("answer:ok").json()
    assert act("answer:ok").json() == first
    client.portal.call(gw.runner.drain)
    answer_jobs = [j for j in executor.jobs if j.job_id == first["job_id"]]
    assert len(answer_jobs) == 1 and "daily-checkin" in answer_jobs[0].prompt and "Chốt vậy" in answer_jobs[0].prompt
    assert client.get("/api/notifications").json()[1]["answer"] == "ok"

    focus = act("start_focus").json()
    client.portal.call(gw.runner.drain)
    assert any(j.job_id == focus["job_id"] and "start_focus" in j.prompt for j in executor.jobs)

    # snooze: comes back after an hour even though today's `normal` slot is used
    snoozed = act("snooze_1h").json()
    assert snoozed["snoozed_until"] == (clock() + timedelta(hours=1)).isoformat()
    clock.advance(minutes=61)
    client.portal.call(gw.hub.flush_all)
    again = ws.sent[-1]
    assert again["type"] == "notification" and again["id"] == nid and "bundled_ids" not in again
    assert act("done").json()["ok"]
    assert client.get("/api/notifications").json()[1]["read_at"]

    with gw.db.session() as db:
        audit = [(r.kind, r.detail) for r in db.scalars(select(AuditRow).where(AuditRow.student_user_id == uid))]
    audit = [(k, d) for k, d in audit if k == "notification_action"]
    assert len(audit) == 5  # open, answer (once), start_focus, snooze, done; no content
    assert all("Chốt" not in d and "hàm số" not in d for _, d in audit)

    new_student(client, "other")  # another learner cannot act on it
    assert client.post(f"/api/notifications/{nid}/action", json={"action": "done"}).status_code == 404


ROUTINES = """timezone: Asia/Ho_Chi_Minh
proactivity: "{proactivity}"
quiet_hours: [{quiet}]
routines:
  - id: morning_checkin
    cron: "30 7 * * 1-5"
    job_kind: routine
    prompt: "Dùng skill daily-checkin, phần A (check-in buổi sáng)."
  - id: review_due
    cron: "0 8 * * *"
    job_kind: routine
"""
QUEUE = """# Lịch ôn tập — math

## Đến hạn hôm nay hoặc quá hạn

| skill_id | Tên | Mastery | Đến hạn | Ghi chú |
|---|---|---|---|---|
| algebra.linear | Phương trình bậc nhất | 0.30 | 2026-10-27 | lần gần nhất làm sai |

## Sắp tới

| skill_id | Tên | Mastery | Đến hạn | Ghi chú |
|---|---|---|---|---|
| algebra.quadratic | Bậc hai | 0.85 | 2026-10-29 | — |
"""


def test_routines_follow_proactivity_and_quiet_hours(client, gw, student, executor, clock):
    uid = student["user_id"]
    gw.mirror.commit_files(uid, {"learning/math/review-queue.md": QUEUE.encode()}, author="mentor", message="q")
    _set_routines(gw, uid, ROUTINES.format(proactivity="high", quiet='"22:00", "07:00"'))
    clock.now = datetime(2026, 10, 28, 0, 0, tzinfo=UTC)  # Wed 07:00 local: schedules computed
    _tick(client, gw, clock())
    clock.now = datetime(2026, 10, 28, 1, 1, tzinfo=UTC)  # 08:01 local: both due
    _tick(client, gw, clock())
    assert [j.prompt for j in executor.jobs] == ["Dùng skill daily-checkin, phần A (check-in buổi sáng)."]
    items = [gw.hub.get(uid, i) for i in _ids(gw, uid)]
    assert [(i.kind, i.status, i.push_safe) for i in items] == [("review", "pending", True)]
    assert "1 kỹ năng" in items[0].body  # the overdue one; tomorrow's row is not due yet
    # at most once a day
    assert client.portal.call(gw.nudges.review_due, gw.users.get(uid), "Asia/Ho_Chi_Minh")[0] == "skipped"

    def jobs(rid):
        with gw.db.session() as s:
            return list(s.scalars(select(JobRow).where(JobRow.source == f"routine:{rid}").order_by(JobRow.id)))

    _set_routines(gw, uid, ROUTINES.format(proactivity="off", quiet='"22:00", "07:00"'))
    clock.now = datetime(2026, 10, 29, 1, 1, tzinfo=UTC)  # Thu 08:01: off -> nothing proactive
    _tick(client, gw, clock())
    assert len(executor.jobs) == 1 and len(_ids(gw, uid)) == 1
    assert [j.error for j in jobs("morning_checkin")][-1] == "proactivity off"

    _set_routines(gw, uid, ROUTINES.format(proactivity="high", quiet='"21:00", "08:30"'))
    clock.now = datetime(2026, 10, 30, 1, 1, tzinfo=UTC)  # Fri 08:01, inside the new quiet hours
    _tick(client, gw, clock())
    assert len(executor.jobs) == 1 and len(_ids(gw, uid)) == 1
    assert [j.error for j in jobs("review_due")][-1] == "quiet hours"

    # the learner's own "quiet until" also skips proactive routines
    _set_routines(gw, uid, ROUTINES.format(proactivity="high", quiet='"22:00", "07:00"'))
    client.put("/api/me/quiet", json={"until": "2026-10-31T00:00:00Z"})
    clock.now = datetime(2026, 10, 31, 1, 1, tzinfo=UTC)  # Sat 08:01 local, quiet_until just passed
    gw.users.update(uid, quiet_until=datetime(2026, 10, 31, 2, 0, tzinfo=UTC))
    _tick(client, gw, clock())
    assert len(executor.jobs) == 1 and [j.error for j in jobs("review_due")][-1] == "quiet until"


def test_engagement_summary(client, gw, student, clock):
    uid = student["user_id"]
    clock.now = datetime.now(UTC).replace(microsecond=0)  # git commit times are real time
    with gw.db.session() as s:
        for d in (1, 2, 4):  # active yesterday and the day before, a gap, then 4 days ago (notification taps)
            day = clock.now - timedelta(days=d)
            s.add(NotificationActionRow(notification_id=d, action="open", delivery=1, user_id=uid, created_at=day,
                                        result={}))
        s.add(JobRow(id="f1", user_id=uid, kind="focus_end", payload={"card_id": "c1", "task": "x", "minutes": 25},
                     source="next_wake", scheduled_for=clock.now + timedelta(minutes=5), status="pending",
                     created_at=clock.now))
    e = client.get("/api/engagement").json()
    assert e["streak_days"] == 2  # today not active yet: yesterday's streak still shows
    assert e["today"] == {"focus_minutes": 20, "done": 0}
    assert e["week"]["focus_minutes"] == 20 and e["week"]["active_days"] == 3

    goals = "# Mục tiêu\n- Mốc: [x] 01/11 đọc chương 2 · [ ] 05/11 viết dàn ý\n<!-- [x] mẫu -->\n"
    mistakes = "# Lỗi\n## Đang gặp\n- nhầm dấu\n## Đã khắc phục\n- quên điều kiện xác định\n"
    gw.mirror.commit_files(uid, {"goals/goals.md": goals.encode(), "learning/math/mistakes.md": mistakes.encode()},
                           author="user", message="tick")
    assert client.get("/api/engagement").json() == e  # cached for a minute
    clock.advance(seconds=61)
    e = client.get("/api/engagement").json()
    assert e["streak_days"] == 3  # the web edit makes today active
    assert e["today"]["done"] == 1 and e["week"]["milestones_done"] == 1 and e["week"]["mistakes_fixed"] == 1


# ---- Web Push -----------------------------------------------------------------------------------


def _vapid(gw) -> None:
    k = ec.generate_private_key(ec.SECP256R1())
    gw.settings.vapid_private_key = base64.urlsafe_b64encode(
        k.private_numbers().private_value.to_bytes(32, "big")).rstrip(b"=").decode()
    gw.settings.vapid_public_key = base64.urlsafe_b64encode(k.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).rstrip(b"=").decode()
    gw.settings.vapid_subject = "mailto:ops@example.com"


def _subscription(endpoint="https://fcm.googleapis.com/fcm/send/abc123") -> dict:
    pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return {"endpoint": endpoint, "expirationTime": None, "keys": {"p256dh": b64(pub), "auth": b64(os.urandom(16))}}


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""
        self.reason = ""


@pytest.fixture
def pushes(monkeypatch):
    sent: list[dict] = []
    state = {"status": 201}

    def fake_webpush(subscription_info, data=None, **kw):
        sent.append({"sub": subscription_info, "data": json.loads(data), "ttl": kw.get("ttl")})
        if state["status"] >= 300:
            raise WebPushException("push failed", response=FakeResponse(state["status"]))
        return FakeResponse(state["status"])

    monkeypatch.setattr(push_mod, "webpush", fake_webpush)
    return sent, state


def test_planner_reminder_push_carries_reminder_id_and_deep_link(client, gw, student, pushes, clock):
    uid = student["user_id"]
    sent, _ = pushes
    _vapid(gw)
    gw.push.subscribe(uid, _subscription())
    now = clock()
    with gw.db.session() as s:
        s.add(Reminder(id="r-abc", user_id=uid, at=now, kind="study", text_vi="20 phút nhé?", text_en="20 minutes?",
                       deep_link="/khoa-hoc/dien-truong?lesson=l1", created_at=now, updated_at=now))
    client.portal.call(gw.hub.notify, uid, "20 phút nhé?", Nudge(text="20 phút nhé?", source=PLANNER_SOURCE + "r-abc"))
    assert sent[-1]["data"]["reminder_id"] == "r-abc" and sent[-1]["data"]["deep_link"] == "/khoa-hoc/dien-truong?lesson=l1"
    assert sent[-1]["data"]["body"] == "20 phút nhé?" and sent[-1]["data"]["title"] == "Mentor"  # the real reminder text
    assert push_mod.push_payload([gw.hub.get(uid, _ids(gw, uid)[0])]).keys() & {"reminder_id", "deep_link"} == set()


def test_push_subscribe_send_and_prune(client, gw, student, pushes, clock):
    uid = student["user_id"]
    sent, state = pushes
    assert client.get("/api/push/vapid-public-key").json() == {"enabled": False, "public_key": None,
                                                               "subscribed_devices": 0}
    assert client.post("/api/push/subscribe", json={"subscription": _subscription()}).status_code == 503
    _vapid(gw)
    assert client.get("/api/push/vapid-public-key").json()["public_key"] == gw.settings.vapid_public_key
    for bad in ("http://fcm.googleapis.com/x", "https://127.0.0.1/x", "https://evil.example/fcm.googleapis.com",
                "https://fcm.googleapis.com:8443/x"):
        assert client.post("/api/push/subscribe", json={"subscription": _subscription(bad)}).status_code == 422, bad
    sub = _subscription()
    assert client.post("/api/push/subscribe", json={"subscription": sub, "device": "laptop"}).json()["ok"]
    assert client.post("/api/push/subscribe", json={"subscription": sub}).json()["ok"]  # same device: one row
    with gw.db.session() as s:
        rows = s.scalars(select(PushSubscription)).all()
    assert len(rows) == 1 and "fcm.googleapis.com" not in rows[0].sealed and sub["keys"]["auth"] not in rows[0].sealed

    # not connected -> push, with the notification's own title, text and actions (no lock-screen privacy handling)
    assert _dispatch(client, gw, uid, [CHECKIN]) == ["delivered"]
    assert len(sent) == 1 and sent[0]["sub"]["endpoint"] == sub["endpoint"]
    data = sent[0]["data"]
    assert data["kind"] == "checkin" and data["title"] == "Chào buổi sáng" and data["body"] == CHECKIN["text"]
    assert [a["id"] for a in data["actions"]] == ["answer:ok", "start_focus", "snooze_1h"]

    # connected -> the live connection only
    _set_routines(gw, uid, ROUTINES.format(proactivity="high", quiet='"22:00", "07:00"'))
    ws = FakeWS()
    gw.hub.register(uid, ws)
    assert _dispatch(client, gw, uid, [{"text": "Ôn nhé", "kind": "review"}]) == ["delivered"]
    assert ws.sent[-1]["kind"] == "review"
    gw.hub.unregister(uid, ws)
    assert len(sent) == 1

    # quiet hours: nothing is pushed
    clock.now = datetime(2026, 10, 28, 16, 0, tzinfo=UTC)  # 23:00 local
    assert _dispatch(client, gw, uid, [{"text": "Khuya rồi", "kind": "nudge"}]) == ["pending"]
    assert len(sent) == 1

    # 410 Gone from the push service: the subscription is deleted, the notification keeps waiting
    clock.now = datetime(2026, 10, 29, 2, 0, tzinfo=UTC)  # 09:00 local
    state["status"] = 410
    client.portal.call(gw.hub.flush_all)
    assert len(sent) == 2 and gw.push.count(uid) == 0
    assert gw.hub.get(uid, _ids(gw, uid)[-1]).status == "pending"

    state["status"] = 201
    assert client.post("/api/push/subscribe", json={"subscription": sub}).json()["ok"]
    # master-key rotation re-seals and re-indexes the subscription
    from mentor_gateway.crypto import SecretBox

    new_box = SecretBox(os.urandom(32))
    with gw.db.session() as s:
        assert push_mod.rotate_subscriptions(s, gw.box, new_box) == 1
    gw.push.box = new_box
    assert [sub_["endpoint"] for _, sub_ in gw.push._subscriptions(uid)] == [sub["endpoint"]]
    r = client.request("DELETE", "/api/push/subscribe", json={"endpoint": sub["endpoint"]})
    assert r.json() == {"ok": True, "removed": 1} and gw.push.count(uid) == 0
    with gw.db.session() as s:
        assert not s.scalars(select(AuditRow).where(AuditRow.kind.like("push%"))).all()
