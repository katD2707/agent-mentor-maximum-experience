import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

from gateway_fakes import (
    FakeBackend,
    FakeParentService,
    FakeSandbox,
    FakeSandboxServer,
    FrozenClock,
    onboard,
    verify_parent,
)

from mentor_gateway.app import create_app
from mentor_gateway.context import Gateway
from mentor_gateway.settings import Settings

FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"


@pytest.fixture(scope="session", autouse=True)
def provisioning_cache(tmp_path_factory):
    """Provision each (content, profile, name, language) once per session, then copy the repos.

    Provisioning spawns ~10 git processes, which is slow on Windows; copying the resulting mirror and
    working copy is equivalent (the user id appears only in paths, not in the repos' content).
    The first call per key still runs the real provisioning code.
    """
    import shutil

    from mentor_gateway.api import account
    from mentor_gateway.gitrepo import UserLocks, run_git
    from mentor_gateway.mirror import Mirror, WorkspaceSync

    real = account.provision_workspace
    root = tmp_path_factory.mktemp("provision-cache")
    locks = UserLocks()
    template_sync = WorkspaceSync(root / "workspaces", Mirror(root / "mirrors", locks), locks)
    cache: dict[tuple, tuple[str, list[str]]] = {}

    def cached(content_dir, sync, user_id, profile, display_name, language):
        key = (str(content_dir), profile, display_name, language)
        if key not in cache:
            tpl = f"tpl{len(cache)}"
            cache[key] = (tpl, real(content_dir, template_sync, tpl, profile, display_name, language))
        tpl, warnings = cache[key]
        sync.mirror.root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template_sync.mirror.path(tpl), sync.mirror.path(user_id))
        shutil.copytree(template_sync.path(tpl), sync.path(user_id))
        run_git(["remote", "set-url", WorkspaceSync.REMOTE, sync.mirror.path(user_id).as_posix()], cwd=sync.path(user_id))
        return list(warnings)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(account, "provision_workspace", cached)
        yield


@pytest.fixture(scope="session")
def sandbox_server():
    server = FakeSandboxServer(FakeSandbox())
    server.start()
    yield server
    server.stop()


@pytest.fixture
def sandbox(sandbox_server) -> FakeSandbox:
    sandbox_server.sandbox.reset()
    return sandbox_server.sandbox


@pytest.fixture
def clock() -> FrozenClock:
    # 2026-10-28 10:00 in Asia/Ho_Chi_Minh (UTC+7): outside quiet hours
    return FrozenClock(datetime(2026, 10, 28, 3, 0, tzinfo=UTC))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        env="test",
        data_dir=tmp_path / "var",
        content_dir=FIXTURE_CONTENT,
        public_base_url="http://testserver",
        web_origin="http://web.test",
        background_tasks=False,
        inbound_email_domain="inbox.mentor.local",
        sandbox_prewarm=False,  # on by default; test_gw_prewarm.py turns it on (keeps status sequences exact)
    )


@pytest.fixture
def backend(sandbox_server) -> FakeBackend:
    return FakeBackend(sandbox_server)


@pytest.fixture
def client(settings, clock, backend, sandbox):
    app = create_app(settings, clock=clock, backend=backend)
    gw: Gateway = app.state.gw
    gw.parent.service = FakeParentService(gw.parent.store, clock)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def gw(client) -> Gateway:
    return client.app.state.gw


@pytest.fixture
def ncs_user(client) -> dict:
    return onboard(client, "ncs@example.com", "ncs")


@pytest.fixture
def thpt_user(client) -> dict:
    me = onboard(client, "hs@example.com", "thpt")
    verify_parent(client, me["user_id"])
    return client.get("/api/me").json()
