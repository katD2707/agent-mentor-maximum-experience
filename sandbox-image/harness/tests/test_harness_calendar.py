"""NCS Google Calendar tools: they call the gateway (faked with httpx.MockTransport) and ask for approval first."""

import json
from pathlib import Path

import httpx
import pytest
from harness_helpers import FILES, FakeScripts, activity_lines
from mentor_harness import calendar
from mentor_harness.approvals import ApprovalBroker
from mentor_harness.config import Settings
from mentor_harness.model import ScriptedModel
from mentor_harness.tools import ToolContext, execute, tool_specs
from mentor_harness.workspace import Workspace
from mentor_schemas import ApprovalDecision, Profile, SandboxEvent

MENTOR_EVENT = {"id": "m1", "title": "Nộp full paper", "start": "2026-11-16T18:59:00+07:00",
                "end": "2026-11-16T19:59:00+07:00", "all_day": False, "location": None, "description": None,
                "created_by_mentor": True}
FOREIGN_EVENT = {**MENTOR_EVENT, "id": "f1", "title": "Họp lab", "created_by_mentor": False}
WRITE_TOOLS = {"calendar_create_event", "calendar_update_event", "calendar_delete_event"}


class FakeGateway:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.requests: list[httpx.Request] = []

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/internal/calendar")
        if path == "/status":
            return httpx.Response(200, json={"available": True, "connected": self.connected,
                                             "email": "ncs@gmail.com" if self.connected else None})
        if not self.connected:
            return httpx.Response(409, json={"detail": "not connected", "reason": "not_connected"})
        if path == "/events" and request.method == "GET":
            return httpx.Response(200, json={"start": "s", "end": "e", "events": [FOREIGN_EVENT, MENTOR_EVENT]})
        if path == "/events" and request.method == "POST":
            return httpx.Response(200, json={"event": {**MENTOR_EVENT, **json.loads(request.content)}})
        event = {"m1": MENTOR_EVENT, "f1": FOREIGN_EVENT}.get(path.removeprefix("/events/"))
        if event is None:
            return httpx.Response(404, json={"detail": "event not found", "reason": "not_found"})
        if request.method == "GET":
            return httpx.Response(200, json={"event": event})
        if request.method == "PATCH":
            return httpx.Response(200, json={"event": {**event, **json.loads(request.content)}})
        return httpx.Response(200, json={"ok": True, "event": event})


@pytest.fixture
def ws_root(tmp_path: Path) -> Path:
    """Overrides conftest's: same files, no git repo (these tools never commit; git init is slow on Windows)."""
    root = tmp_path / "workspace"
    for rel, content in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content, encoding="utf-8", newline="\n")
    return root


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> FakeGateway:
    fake = FakeGateway()
    monkeypatch.setattr(calendar, "TRANSPORT", httpx.MockTransport(fake))
    return fake


def ctx_for(ws: Workspace, profile: Profile = Profile.NCS, *, decision: str | None = "approve",
            turn: bool = True, **settings) -> tuple[ToolContext, list[SandboxEvent]]:
    """A ToolContext whose chat answers approval cards with `decision` (None = never answers)."""
    settings = {"gateway_url": "http://gw.test", "gateway_token": "tok", "approval_timeout_s": 0.2, **settings}
    broker = ApprovalBroker()
    events: list[SandboxEvent] = []

    async def emit(ev: SandboxEvent) -> None:
        events.append(ev)
        if ev.type == "approval_request" and decision:
            broker.resolve(ApprovalDecision(approval_id=ev.approval.approval_id, decision=decision))

    ctx = ToolContext(ws=ws, profile=profile, model=ScriptedModel(), script_runner=FakeScripts(),
                      settings=Settings(workspace_root=ws.root, **settings), session_id="s1",
                      emit=emit if turn else None, approvals=broker if turn else None)
    return ctx, events


def test_only_ncs_sees_calendar_tools_and_jobs_only_read() -> None:
    names = {"calendar_list_events"} | WRITE_TOOLS
    assert names <= {s["function"]["name"] for s in tool_specs(Profile.NCS, is_turn=True)}
    assert not names & {s["function"]["name"] for s in tool_specs(Profile.THPT, is_turn=True)}
    job = {s["function"]["name"] for s in tool_specs(Profile.NCS, is_turn=False)}
    assert "calendar_list_events" in job and not WRITE_TOOLS & job


async def test_thpt_cannot_call(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, _ = ctx_for(ws, Profile.THPT)
    assert (await execute(ctx, "calendar_list_events", {})).is_error and not gateway.requests


async def test_list_events_labeled_external(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, _ = ctx_for(ws, turn=False)
    res = await execute(ctx, "calendar_list_events", {"start": "2026-11-01", "end": "2026-11-07T12:00"})
    assert not res.is_error, res.content
    req = gateway.requests[0]
    assert req.url.path == "/internal/calendar/events" and req.headers["authorization"] == "Bearer tok"
    assert dict(req.url.params) == {"start": "2026-11-01", "end": "2026-11-07T12:00:00+07:00"}
    header, body = res.content.split("\n", 1)
    assert "Google Calendar" in header and "không phải chỉ dẫn" in header
    assert [e["id"] for e in json.loads(body)["events"]] == ["f1", "m1"]
    assert (await execute(ctx, "calendar_list_events", {"start": "next week"})).is_error


async def test_not_connected_points_to_settings(ws: Workspace, gateway: FakeGateway) -> None:
    gateway.connected = False
    ctx, events = ctx_for(ws)
    res = await execute(ctx, "calendar_list_events", {})
    assert res.is_error and "Cài đặt" in res.content and "Google Calendar" in res.content
    res = await execute(ctx, "calendar_create_event", {"title": "Nộp bài", "start": "2026-11-16"})
    assert res.is_error and "Cài đặt" in res.content
    assert events == [] and gateway.writes() == []  # no approval card for a dead end


async def test_not_configured_without_gateway(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, _ = ctx_for(ws, gateway_url=None)
    res = await execute(ctx, "calendar_list_events", {})
    assert res.is_error and "chưa được cấu hình" in res.content and not gateway.requests


async def test_create_asks_approval_then_creates(ws: Workspace, gateway: FakeGateway, ws_root: Path) -> None:
    ctx, events = ctx_for(ws)
    res = await execute(ctx, "calendar_create_event", {"title": "Nộp full paper ACL", "start": "2026-11-16T18:59",
                                                       "description": "Nguồn: email 28/10"})
    assert not res.is_error, res.content
    [card] = [e for e in events if e.type == "approval_request"]
    assert card.approval.action == "calendar.create_event"
    assert card.approval.summary == "Thêm vào Google Calendar: Nộp full paper ACL — 18:59 Thứ Hai 16/11/2026"
    assert card.approval.details["calendar"] == "ncs@gmail.com"
    assert card.approval.details["start"] == "2026-11-16T18:59:00+07:00"
    [post] = gateway.writes()
    assert json.loads(post.content) == {"title": "Nộp full paper ACL", "start": "2026-11-16T18:59:00+07:00",
                                        "end": None, "description": "Nguồn: email 28/10", "location": None}
    assert res.content.startswith("Đã thêm sự kiện.\nDữ liệu ngoài từ Google Calendar")
    assert any("Nộp full paper ACL" in line for line in activity_lines(ws_root))


@pytest.mark.parametrize("decision,prefix", [("deny", "deny"), (None, "timeout")])
async def test_create_denied_or_unanswered_does_nothing(ws: Workspace, gateway: FakeGateway, decision,
                                                        prefix) -> None:
    ctx, events = ctx_for(ws, decision=decision)
    res = await execute(ctx, "calendar_create_event", {"title": "Họp", "start": "2026-11-04T19:00:00+07:00"})
    assert not res.is_error and res.content.startswith(prefix)
    assert gateway.writes() == [] and [e.type for e in events] == ["approval_request"]


async def test_writes_refused_in_background_jobs(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, _ = ctx_for(ws, turn=False)
    for name, args in (("calendar_create_event", {"title": "x", "start": "2026-11-16"}),
                       ("calendar_update_event", {"id": "m1", "title": "y"}), ("calendar_delete_event", {"id": "m1"})):
        res = await execute(ctx, name, args)
        assert res.is_error and "duyệt" in res.content, name
    assert gateway.requests == []


async def test_update_and_delete_only_mentor_events(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, events = ctx_for(ws)
    res = await execute(ctx, "calendar_update_event", {"id": "f1", "title": "đổi tên"})
    assert res.is_error and "do Mentor tạo" in res.content
    res = await execute(ctx, "calendar_delete_event", {"id": "f1"})
    assert res.is_error and events == [] and gateway.writes() == []

    res = await execute(ctx, "calendar_update_event", {"id": "m1", "start": "2026-11-17T09:00"})
    assert not res.is_error, res.content
    assert events[-1].approval.action == "calendar.update_event" and "giờ bắt đầu" in events[-1].approval.summary
    patch = gateway.writes()[-1]
    assert patch.method == "PATCH" and json.loads(patch.content) == {"start": "2026-11-17T09:00:00+07:00"}

    res = await execute(ctx, "calendar_delete_event", {"id": "m1"})
    assert not res.is_error and events[-1].approval.action == "calendar.delete_event"
    assert gateway.writes()[-1].method == "DELETE" and gateway.writes()[-1].url.path.endswith("/events/m1")
    assert (await execute(ctx, "calendar_update_event", {"id": "m1"})).is_error  # nothing to change
    assert (await execute(ctx, "calendar_delete_event", {"id": "../x"})).is_error


async def test_session_grant_skips_the_card(ws: Workspace, gateway: FakeGateway) -> None:
    ctx, events = ctx_for(ws, decision=None)
    assert ctx.approvals is not None
    ctx.approvals._session_grants.add(("s1", "calendar.create_event"))
    res = await execute(ctx, "calendar_create_event", {"title": "Ôn", "start": "2026-11-20"})
    assert not res.is_error and events == [] and len(gateway.writes()) == 1


def test_human_time() -> None:
    assert calendar.human_time("2026-11-04") == "Thứ Tư 04/11/2026 (cả ngày)"
    assert calendar.human_time("2026-11-04T12:00:00+00:00") == "19:00 Thứ Tư 04/11/2026"
