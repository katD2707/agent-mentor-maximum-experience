"""Test doubles: an in-process sandbox serving the CONTRACTS section 2 HTTP API, its backend, a parent service."""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from mentor_schemas import (
    ApprovalDecision,
    ApprovalRequest,
    JobRequest,
    JobResult,
    OutboxItem,
    OutboxKind,
    ParentLink,
    SandboxEvent,
    TurnRequest,
)

from mentor_gateway.gitrepo import run_git
from mentor_gateway.sandbox.backends import SandboxSpec, free_port

FAKE_HARNESS_TOKEN = "fake-harness-token"


class FrozenClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now = self.now + timedelta(**kw)


def harness_commit(workspace: Path, message: str) -> None:
    """What the real harness does after each turn/job: commit as mentor <mentor@local>."""
    run_git(["add", "-A"], cwd=workspace)
    if run_git(["status", "--porcelain"], cwd=workspace).stdout.strip():
        run_git(["commit", "-q", "-m", message], cwd=workspace, author="mentor")


class FakeSandbox:
    """Behaviour by turn text: contains "approve" -> asks for approval first; otherwise appends the text to
    me/journal/fake.md, commits, streams two text deltas and a tool event, returns `turn_outbox`."""

    def __init__(self) -> None:
        self.app = FastAPI()
        self.workspaces: dict[str, Path] = {}
        self.reset()
        self._waiters: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, ApprovalDecision] = {}
        app = self.app

        @app.middleware("http")
        async def require_token(request, call_next):  # like the real harness: bearer token on all but health
            if request.url.path != "/v1/health":
                self.auth_headers.append(request.headers.get("authorization"))
                if request.headers.get("authorization") != f"Bearer {FAKE_HARNESS_TOKEN}":
                    return JSONResponse({"detail": "missing or invalid harness token"}, status_code=401)
            return await call_next(request)

        @app.get("/v1/health")
        def health() -> dict:
            return {"status": "ok"}

        @app.post("/v1/turn")
        async def turn(req: TurnRequest) -> StreamingResponse:
            self.turns.append(req)
            return StreamingResponse(self._turn_events(req), media_type="text/event-stream")

        @app.post("/v1/jobs")
        async def jobs(req: JobRequest) -> JobResult:
            self.jobs.append(req)
            ws = self.workspaces.get(req.user_id)
            if ws is not None:
                self.seen_files.append(sorted(p.relative_to(ws).as_posix() for p in ws.rglob("*") if ".git" not in p.parts))
            outbox, self.job_outbox = self.job_outbox, []
            return JobResult(job_id=req.job_id, status="ok", summary=f"Đã chạy {req.kind.value}", outbox=outbox)

        @app.post("/v1/approvals")
        async def approvals(dec: ApprovalDecision) -> dict:
            self._decisions[dec.approval_id] = dec
            ev = self._waiters.get(dec.approval_id)
            if ev is not None:
                ev.set()
            return {"ok": True}

    def reset(self) -> None:
        self.auth_headers: list[str | None] = []
        self.turns: list[TurnRequest] = []
        self.jobs: list[JobRequest] = []
        self.turn_outbox: list[OutboxItem] = []
        self.job_outbox: list[OutboxItem] = []
        self.seen_files: list[list[str]] = []
        self.workspace_snapshots: list[dict[str, str]] = []

    @staticmethod
    def _sse(ev: SandboxEvent) -> str:
        return f"data: {json.dumps(ev.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    async def _turn_events(self, req: TurnRequest):
        ws = self.workspaces[req.user_id]
        self.workspace_snapshots.append(
            {p.relative_to(ws).as_posix(): p.read_text(encoding="utf-8", errors="replace")
             for p in ws.rglob("*.md") if ".git" not in p.parts}
        )
        if "crisis" in req.text:  # the harness ends a turn with an error event that still carries the outbox
            yield self._sse(SandboxEvent(type="error", error="turn aborted", outbox=[
                OutboxItem(kind=OutboxKind.CRISIS_ALERT, payload={"category": "self_harm"}, dedupe_key="crisis-1")]))
            return
        if "approve" in req.text:
            aid = f"ap-{len(self.turns)}"
            waiter = asyncio.Event()
            self._waiters[aid] = waiter
            yield self._sse(SandboxEvent(type="approval_request", approval=ApprovalRequest(
                approval_id=aid, action="calendar.create_event", summary="Tạo lịch ôn tập",
                expires_at=datetime.now(UTC) + timedelta(minutes=5))))
            try:
                await asyncio.wait_for(waiter.wait(), timeout=10)
                decision = self._decisions[aid].decision
            except TimeoutError:
                decision = "timeout"
            yield self._sse(SandboxEvent(type="text_delta", text=f"decision:{decision}"))
            yield self._sse(SandboxEvent(type="done"))
            return
        journal = ws / "me" / "journal" / "fake.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"- {req.text}\n")
        yield self._sse(SandboxEvent(type="tool_started", tool="write_file", summary="Đang ghi nhật ký"))
        yield self._sse(SandboxEvent(type="tool_finished", tool="write_file", summary="Đã ghi nhật ký"))
        yield self._sse(SandboxEvent(type="text_delta", text="Chào "))
        yield self._sse(SandboxEvent(type="text_delta", text="bạn"))
        harness_commit(ws, f"turn {req.session_id}")
        outbox, self.turn_outbox = self.turn_outbox, []
        yield self._sse(SandboxEvent(type="done", outbox=outbox))


class FakeSandboxServer:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(sandbox.app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("fake sandbox did not start")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


class FakeBackend:
    def __init__(self, server: FakeSandboxServer) -> None:
        self.server = server
        self.running: set[str] = set()
        self.starts = 0

    async def ensure_running(self, spec: SandboxSpec) -> str:
        self.server.sandbox.workspaces[spec.user_id] = spec.workspace_dir
        if spec.user_id not in self.running:
            self.starts += 1
            self.running.add(spec.user_id)
        return self.server.base_url

    def harness_token(self, user_id: str) -> str | None:
        return FAKE_HARNESS_TOKEN if user_id in self.running else None

    async def stop(self, user_id: str) -> None:
        self.running.discard(user_id)

    async def status(self, user_id: str) -> str:
        return "running" if user_id in self.running else "stopped"


class FakeParentService:
    """Stands in for mentor_parent_channel.ParentLinkService; records what would be sent to Zalo."""

    def __init__(self, store, clock) -> None:
        self.store = store
        self.clock = clock
        self.reports: list[tuple[str, str]] = []
        self.alerts: list[tuple[str, str]] = []

    def start_link(self, student_user_id: str) -> ParentLink:
        link = ParentLink(student_user_id=student_user_id, link_code="123456",
                          code_expires_at=self.clock() + timedelta(hours=24))
        self.store.save(link)
        return link

    def verify(self, student_user_id: str) -> None:
        """What happens when the parent sends the code and replies ĐỒNG Ý."""
        link = self.store.get_by_student(student_user_id)
        self.store.save(link.model_copy(update={"status": "verified", "zalo_chat_id": "chat-1",
                                                "verified_at": self.clock()}))
        self.store.record_audit(student_user_id, "consent", "parent consented")

    async def send_report(self, student_user_id: str, report_text: str) -> bool:
        self.reports.append((student_user_id, report_text))
        return True

    def send_crisis_alert(self, student_user_id: str, category: str) -> bool:
        self.alerts.append((student_user_id, category))
        self.store.record_audit(student_user_id, "crisis_alert", f"category={category}")
        return True


def login(client: TestClient, email: str) -> None:
    r = client.post("/api/auth/request-link", json={"email": email})
    assert r.status_code == 200, r.text
    token = parse_qs(urlparse(r.json()["dev_link"]).query)["token"][0]
    r = client.get("/api/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 302, r.text


def onboard(client: TestClient, email: str, role: str, name: str = "An") -> dict:
    login(client, email)
    r = client.post("/api/onboarding", json={"role": role, "display_name": name, "language": "vi"})
    assert r.status_code == 200, r.text
    return r.json()


def verify_parent(client: TestClient, user_id: str) -> None:
    gw = client.app.state.gw
    client.post("/api/parent-link")
    gw.parent.service.verify(user_id)


def recv_until(ws, kind: str, limit: int = 50) -> list[dict]:
    msgs = []
    for _ in range(limit):
        m = ws.receive_json()
        msgs.append(m)
        if m["type"] == kind:
            return msgs
    raise AssertionError(f"no {kind} in {msgs}")
