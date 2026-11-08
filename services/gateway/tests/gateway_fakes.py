"""Test doubles: a job executor, a fake notification connection, login helpers."""

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from mentor_schemas import JobRequest, JobResult, OutboxItem

from mentor_gateway.gitrepo import run_git


class FrozenClock:
    def __init__(self, now) -> None:
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw: float) -> None:
        self.now = self.now + timedelta(**kw)


def harness_commit(workspace: Path, message: str) -> None:
    """What the real harness does after each job: commit as mentor <mentor@local>."""
    run_git(["add", "-A"], cwd=workspace)
    if run_git(["status", "--porcelain"], cwd=workspace).stdout.strip():
        run_git(["commit", "-q", "-m", message], cwd=workspace, author="mentor")


class FakeExecutor:
    """JobExecutor double: records every job it is given and returns `job_outbox` once."""

    def __init__(self) -> None:
        self.jobs: list[JobRequest] = []
        self.job_outbox: list[OutboxItem] = []

    async def __call__(self, req: JobRequest, workspace_dir: Path) -> JobResult:
        self.jobs.append(req)
        outbox, self.job_outbox = self.job_outbox, []
        return JobResult(job_id=req.job_id, status="ok", summary=f"Đã chạy {req.kind.value}", outbox=outbox)


class FakeWS:
    """A notification connection (what the hub delivers to)."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data) -> None:
        self.sent.append(data)


def login(client: TestClient, username: str = "hocsinh", password: str = "123456", role: str = "student") -> dict:
    """Logs in and sets the bearer header on the client; returns the user."""
    r = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return r.json()["user"]


# birth years that fall in each band on the fixture clock (2026-10-28: school year 2026)
BAND_YEAR = {"g1_5": 2018, "g6_9": 2013, "g10_12": 2010, "uni": 2007, None: None}


def set_band(client: TestClient, band: str | None) -> None:
    """Puts the logged-in user in an age band by setting a birth year (the band is derived; PATCH /me is set-once)."""
    uid = client.get("/api/me").json()["id"]
    client.app.state.gw.users.update(uid, birth_year=BAND_YEAR[band])


def new_student(client: TestClient, username: str, age_band: str | None = "g10_12") -> dict:
    """Creates another student account and logs in as it."""
    client.app.state.gw.users.create(username=username, password="123456", role="student", display_name=username,
                                     birth_year=BAND_YEAR[age_band], language="vi")
    return login(client, username)
