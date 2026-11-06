import subprocess

import pytest
from mentor_schemas import Profile

from mentor_gateway.sandbox import backends
from mentor_gateway.sandbox.backends import DockerBackend, LocalProcessBackend, SandboxSpec
from mentor_gateway.settings import Settings


async def test_docker_backend_command(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, sandbox_docker_network="mentor-sandbox", model_router_url="http://model-router:4000",
                        model_router_key="k", sandbox_docker_user="1000:1000")
    b = DockerBackend(settings)
    calls: list[tuple[str, ...]] = []

    async def fake_docker(*args, check=True):
        calls.append(args)
        running = "true" if args[0] == "inspect" and any(c[0] == "run" for c in calls) else "false"
        return subprocess.CompletedProcess(args, 0, stdout=running, stderr="")

    async def healthy(url, timeout, alive=lambda: True):
        return None

    monkeypatch.setattr(b, "_docker", fake_docker)
    monkeypatch.setattr(backends, "wait_healthy", healthy)
    ws = tmp_path / "workspaces" / "u1"
    ws.mkdir(parents=True)
    url = await b.ensure_running(SandboxSpec(user_id="u1", profile=Profile.THPT, workspace_dir=ws))
    assert url == "http://mentor-sbx-u1:8080"
    run = next(c for c in calls if c[0] == "run")
    joined = " ".join(run)
    assert f"{ws.resolve()}:/workspace" in joined
    assert "--network mentor-sandbox" in joined and "--user 1000:1000" in joined
    assert "MENTOR_SANDBOX_ISOLATED=1" in run and "MENTOR_PROFILE=thpt" in run and "MENTOR_USER_ID=u1" in run
    assert "WORKSPACE_ROOT=/workspace" in run and "MODEL_ROUTER_URL=http://model-router:4000" in run
    assert run[-1] == "mentor-sandbox:dev"
    # hardening: read-only root fs, sized noexec tmpfs, no capabilities, no privilege escalation
    assert "--read-only" in run and "--cap-drop ALL" in joined and "--security-opt no-new-privileges" in joined
    assert "--tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777" in joined
    token = next(a.split("=", 1)[1] for a in run if a.startswith("MENTOR_HARNESS_TOKEN="))
    assert len(token) >= 32 and b.harness_token("u1") == token
    assert await b.ensure_running(SandboxSpec(user_id="u1", profile=Profile.THPT, workspace_dir=ws)) == url
    assert sum(1 for c in calls if c[0] == "run") == 1
    await b.stop("u1")
    assert calls[-1][:2] == ("rm", "-f") and b.harness_token("u1") is None


def test_local_backend_env_not_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MENTOR_SANDBOX_ISOLATED", "1")
    captured = {}

    def fake_popen(cmd, env, cwd, stdout, stderr):
        captured.update(cmd=cmd, env=env, cwd=cwd)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    b = LocalProcessBackend(Settings(env="test", data_dir=tmp_path, model_mode="scripted"))
    b._spawn(SandboxSpec(user_id="u2", profile=Profile.NCS, workspace_dir=tmp_path), 12345, "gw-tok", "h-tok")
    assert "MENTOR_SANDBOX_ISOLATED" not in captured["env"]
    assert captured["env"]["MENTOR_HARNESS_TOKEN"] == "h-tok" and captured["env"]["MENTOR_GATEWAY_TOKEN"] == "gw-tok"
    assert captured["env"]["MENTOR_MODEL_MODE"] == "scripted" and captured["env"]["WORKSPACE_ROOT"] == str(tmp_path)
    assert captured["cmd"][-4:] == ["--host", "127.0.0.1", "--port", "12345"]
    assert "mentor_harness.server:app" in captured["cmd"]


async def test_docker_backend_without_network_is_not_isolated(tmp_path, monkeypatch):
    b = DockerBackend(Settings(data_dir=tmp_path, sandbox_docker_user="1000:1000"))
    calls: list[tuple[str, ...]] = []

    async def fake_docker(*args, check=True):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="false", stderr="")

    async def healthy(url, timeout, alive=lambda: True):
        return None

    monkeypatch.setattr(b, "_docker", fake_docker)
    monkeypatch.setattr(backends, "wait_healthy", healthy)
    url = await b.ensure_running(SandboxSpec(user_id="u3", profile=Profile.NCS, workspace_dir=tmp_path))
    run = next(c for c in calls if c[0] == "run")
    assert url.startswith("http://127.0.0.1:") and "--network" not in run
    # port-published container has internet: run_python must stay off (the image defaults it to 1)
    assert "MENTOR_SANDBOX_ISOLATED=0" in run and "MENTOR_SANDBOX_ISOLATED=1" not in run


def test_local_backend_refused_outside_dev_and_test(tmp_path):
    with pytest.raises(RuntimeError, match="only allowed when MENTOR_ENV is dev or test"):
        backends.make_backend(Settings(env="prod", data_dir=tmp_path, sandbox_backend="local"))
    assert isinstance(backends.make_backend(Settings(env="test", data_dir=tmp_path)), LocalProcessBackend)
    assert isinstance(backends.make_backend(Settings(env="prod", data_dir=tmp_path, sandbox_backend="docker")),
                      DockerBackend)


@pytest.mark.parametrize("env,expected", [({}, "local"), ({"SANDBOX_BACKEND": "docker"}, "docker")])
def test_settings_from_env(env, expected):
    s = Settings.from_env({"MENTOR_DATA_DIR": "x", **env})
    assert s.sandbox_backend == expected and str(s.data_dir) == "x"


def test_missing_mentor_env_is_prod_not_dev(tmp_path):
    assert Settings.from_env({}).env == "prod"
    assert Settings().env == "prod"
    assert Settings.from_env({"MENTOR_ENV": "dev"}).env == "dev"
    # prod refuses the unisolated local backend, so a forgotten MENTOR_ENV cannot silently run dev mode
    with pytest.raises(RuntimeError, match="only allowed when MENTOR_ENV is dev or test"):
        backends.make_backend(Settings.from_env({"MENTOR_DATA_DIR": str(tmp_path)}))


async def test_local_backend_issues_and_revokes_harness_token(tmp_path, monkeypatch):
    b = LocalProcessBackend(Settings(env="test", data_dir=tmp_path))
    spawned = {}

    class Proc:
        def poll(self):
            return None

        def terminate(self):
            spawned["terminated"] = True

        def wait(self, timeout=None):
            return 0

    def fake_spawn(spec, port, gateway_token="", harness_token=""):
        spawned.update(gateway_token=gateway_token, harness_token=harness_token)
        return Proc()

    async def healthy(url, timeout, alive=lambda: True):
        return None

    monkeypatch.setattr(b, "_spawn", fake_spawn)
    monkeypatch.setattr(backends, "wait_healthy", healthy)
    await b.ensure_running(SandboxSpec(user_id="u5", profile=Profile.NCS, workspace_dir=tmp_path))
    assert spawned["harness_token"] and b.harness_token("u5") == spawned["harness_token"]
    assert spawned["harness_token"] != spawned["gateway_token"]
    await b.stop("u5")
    assert b.harness_token("u5") is None and spawned["terminated"]


async def test_docker_backend_per_sandbox_network(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, sandbox_docker_user="4242:4242",
                        sandbox_network_attach="self:gateway, mentor-dev-model-router-1:model-router",
                        sandbox_docker_network="ignored-shared-net")
    b = DockerBackend(settings)
    calls: list[tuple[str, ...]] = []

    async def fake_docker(*args, check=True):
        calls.append(args)
        if args[:2] == ("network", "connect") and "model-router" in args:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="endpoint already exists in network")
        return subprocess.CompletedProcess(args, 0, stdout="false", stderr="")

    async def healthy(url, timeout, alive=lambda: True):
        return None

    monkeypatch.setattr(b, "_docker", fake_docker)
    monkeypatch.setattr(backends, "wait_healthy", healthy)
    monkeypatch.setattr(backends.socket, "gethostname", lambda: "gw123")
    url = await b.ensure_running(SandboxSpec(user_id="u6", profile=Profile.NCS, workspace_dir=tmp_path))
    assert url == "http://mentor-sbx-u6:8080"
    net = "mentor-sbx-net-u6"
    assert ("network", "create", "--internal", "--label", "mentor.sandbox=1", net) in calls
    assert ("network", "connect", "--alias", "gateway", net, "gw123") in calls  # `self` = own container
    assert ("network", "connect", "--alias", "model-router", net, "mentor-dev-model-router-1") in calls
    run = next(c for c in calls if c[0] == "run")
    assert run[run.index("--network") + 1] == net and "ignored-shared-net" not in run
    assert "MENTOR_SANDBOX_ISOLATED=1" in run and "--user" in run and run[run.index("--user") + 1] == "4242:4242"
    # the attachments happen before the sandbox starts, so it can reach the router from its first request
    assert calls.index(run) > max(i for i, c in enumerate(calls) if c[:2] == ("network", "connect"))
    calls.clear()
    await b.stop("u6")
    assert calls[0] == ("rm", "-f", "mentor-sbx-u6")
    assert ("network", "disconnect", "-f", net, "gw123") in calls and calls[-1] == ("network", "rm", net)


async def test_docker_backend_network_errors_and_root_user(tmp_path, monkeypatch):
    b = DockerBackend(Settings(data_dir=tmp_path, sandbox_network_attach="self", sandbox_docker_user="1:1"))

    async def failing(*args, check=True):
        if args[:2] == ("network", "connect"):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="No such container: gw")
        return subprocess.CompletedProcess(args, 0, stdout="false", stderr="")

    monkeypatch.setattr(b, "_docker", failing)
    with pytest.raises(RuntimeError, match="network connect"):
        await b.ensure_running(SandboxSpec(user_id="u7", profile=Profile.NCS, workspace_dir=tmp_path))
    for root in ("0:0", "root", "0"):
        with pytest.raises(RuntimeError, match="must not be root"):
            DockerBackend(Settings(data_dir=tmp_path, sandbox_docker_user=root)).sandbox_user()
    if hasattr(backends.os, "getuid"):
        monkeypatch.setattr(backends.os, "getuid", lambda: 0)
    else:
        monkeypatch.delattr(backends.os, "getuid", raising=False)
    assert DockerBackend(Settings(data_dir=tmp_path)).sandbox_user() == backends.SANDBOX_DEFAULT_USER
