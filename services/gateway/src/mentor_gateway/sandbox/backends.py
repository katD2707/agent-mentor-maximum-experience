"""Sandbox backends: where a learner's harness runs.

- LocalProcessBackend: `python -m uvicorn mentor_harness.server:app` on a free localhost port (dev, no isolation).
- DockerBackend: one container per learner from `mentor-sandbox:dev`, workspace bind-mounted at /workspace,
  hardened (`--read-only`, sized `--tmpfs /tmp`, `--cap-drop ALL`, `no-new-privileges`, never root). Networking:
  * SANDBOX_NETWORK_ATTACH set (recommended): every sandbox gets its OWN internal network
    `mentor-sbx-net-<user>` (`docker network create --internal`), and the listed containers (the gateway itself
    and the model router, each with a DNS alias) are attached to it. A sandbox can reach only those, never
    another sandbox and never the internet.
  * only SANDBOX_DOCKER_NETWORK set (legacy): all sandboxes share that internal network, so they can reach each
    other's port 8080 and are kept apart only by the per-sandbox harness token below.
  * neither: the port is published on 127.0.0.1 (dev convenience; internet access, run_python disabled).
  Docker's `com.docker.network.bridge.enable_icc=false` on a shared network is not an option: it also cuts
  gateway -> sandbox and sandbox -> router traffic (they are containers on the same bridge), on Linux and on
  Docker Desktop alike (infra/README "Sandbox isolation").

Every start issues two fresh random tokens:
- MENTOR_HARNESS_TOKEN (gateway -> sandbox): the harness requires `Authorization: Bearer <it>` on every endpoint
  but /v1/health; the backend keeps it in memory for SandboxClient (`harness_token()`).
- MENTOR_GATEWAY_TOKEN (sandbox -> gateway, sandbox/tokens.py) with MENTOR_GATEWAY_URL (SANDBOX_GATEWAY_URL,
  default PUBLIC_BASE_URL) for /internal/papers/* and /internal/calendar/*.
Stopping a sandbox revokes both.
"""

import asyncio
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from mentor_schemas import Profile

from mentor_gateway.sandbox.client import SandboxClient
from mentor_gateway.sandbox.tokens import SandboxTokens
from mentor_gateway.settings import Settings

log = logging.getLogger(__name__)

BackendStatus = Literal["running", "stopped"]


@dataclass
class SandboxSpec:
    user_id: str
    profile: Profile
    workspace_dir: Path


# The sandbox image's USER. Used when the gateway itself runs as root (or on Windows, where it has no uid).
SANDBOX_DEFAULT_USER = "4242:4242"


class SandboxBackend(Protocol):
    async def ensure_running(self, spec: SandboxSpec) -> str:
        """Start the sandbox if needed, wait until healthy, return its base URL."""
        ...

    def harness_token(self, user_id: str) -> str | None:
        """Bearer token the running sandbox's harness expects (None: no auth, e.g. test doubles)."""
        ...

    async def stop(self, user_id: str) -> None: ...

    async def status(self, user_id: str) -> BackendStatus: ...


def new_harness_token() -> str:
    return secrets.token_urlsafe(32)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sandbox_env(settings: Settings, spec: SandboxSpec, workspace_root: str, gateway_token: str = "",
                harness_token: str = "") -> dict[str, str]:
    return {
        "WORKSPACE_ROOT": workspace_root,
        "MODEL_ROUTER_URL": settings.model_router_url,
        "MODEL_ROUTER_KEY": settings.model_router_key,
        "MENTOR_MODEL_MODE": settings.model_mode,
        "MENTOR_PROFILE": spec.profile.value,
        "MENTOR_USER_ID": spec.user_id,
        "MENTOR_GATEWAY_URL": settings.sandbox_gateway_base_url,
        "MENTOR_GATEWAY_TOKEN": gateway_token,
        "MENTOR_HARNESS_TOKEN": harness_token,
    }


async def wait_healthy(base_url: str, timeout: float, alive: callable = lambda: True) -> None:
    client = SandboxClient(base_url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive():
            raise RuntimeError(f"sandbox at {base_url} exited during start-up")
        if await client.health():
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"sandbox at {base_url} not healthy after {timeout}s")


class LocalProcessBackend:
    def __init__(self, settings: Settings, start_timeout: float = 60.0, tokens: SandboxTokens | None = None) -> None:
        if settings.env not in ("dev", "test"):
            # a host process has no network or filesystem isolation: never run it outside dev/test
            raise RuntimeError(f"SANDBOX_BACKEND=local is only allowed when MENTOR_ENV is dev or test, not {settings.env}")
        self.settings = settings
        self.start_timeout = start_timeout
        self.tokens = tokens or SandboxTokens()
        self._procs: dict[str, tuple[subprocess.Popen, str]] = {}
        self._harness_tokens: dict[str, str] = {}

    def harness_token(self, user_id: str) -> str | None:
        return self._harness_tokens.get(user_id)

    async def ensure_running(self, spec: SandboxSpec) -> str:
        current = self._procs.get(spec.user_id)
        if current and current[0].poll() is None:
            return current[1]
        port = free_port()
        token = self.tokens.issue(spec.user_id, spec.profile)
        harness_token = new_harness_token()
        self._harness_tokens[spec.user_id] = harness_token
        proc = await asyncio.to_thread(self._spawn, spec, port, token, harness_token)
        base_url = f"http://127.0.0.1:{port}"
        self._procs[spec.user_id] = (proc, base_url)
        try:
            await wait_healthy(base_url, self.start_timeout, alive=lambda: proc.poll() is None)
        except BaseException:
            await self.stop(spec.user_id)
            raise
        return base_url

    def _spawn(self, spec: SandboxSpec, port: int, gateway_token: str = "",
               harness_token: str = "") -> subprocess.Popen:
        env = dict(os.environ)
        env.pop("MENTOR_SANDBOX_ISOLATED", None)  # a host process is not isolated
        env.pop("S2_API_KEY", None)  # upstream keys stay in the gateway
        env.pop("ASTA_API_KEY", None)
        env.update(sandbox_env(self.settings, spec, str(spec.workspace_dir), gateway_token, harness_token))
        log_path = self.settings.data_dir / "logs" / f"sandbox-{spec.user_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as logf:
            return subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "mentor_harness.server:app", "--host", "127.0.0.1",
                 "--port", str(port)],
                env=env,
                cwd=str(spec.workspace_dir),
                stdout=logf,
                stderr=subprocess.STDOUT,
            )

    async def stop(self, user_id: str) -> None:
        self.tokens.revoke(user_id)
        self._harness_tokens.pop(user_id, None)
        entry = self._procs.pop(user_id, None)
        if not entry:
            return
        proc = entry[0]
        if proc.poll() is None:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, 10)
            except subprocess.TimeoutExpired:
                proc.kill()

    async def status(self, user_id: str) -> BackendStatus:
        entry = self._procs.get(user_id)
        return "running" if entry and entry[0].poll() is None else "stopped"

    async def shutdown(self) -> None:
        for uid in list(self._procs):
            await self.stop(uid)


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    """lchown root and everything below it (never follows symlinks out of the workspace)."""
    for dirpath, dirnames, filenames in os.walk(root):
        for name in (*dirnames, *filenames):
            os.chown(os.path.join(dirpath, name), uid, gid, follow_symlinks=False)
    os.chown(root, uid, gid, follow_symlinks=False)


class DockerBackend:
    def __init__(self, settings: Settings, start_timeout: float = 60.0, tokens: SandboxTokens | None = None) -> None:
        self.settings = settings
        self.start_timeout = start_timeout
        self.tokens = tokens or SandboxTokens()
        self._urls: dict[str, str] = {}
        self._harness_tokens: dict[str, str] = {}

    @staticmethod
    def container_name(user_id: str) -> str:
        return f"mentor-sbx-{user_id}"

    @staticmethod
    def network_name(user_id: str) -> str:
        return f"mentor-sbx-net-{user_id}"

    def harness_token(self, user_id: str) -> str | None:
        return self._harness_tokens.get(user_id)

    @property
    def per_sandbox_network(self) -> bool:
        return bool(self.attachments())

    def attachments(self) -> list[tuple[str, str | None]]:
        """SANDBOX_NETWORK_ATTACH = `container[:alias],...`; `self` = the gateway's own container (its hostname)."""
        out = []
        for item in (self.settings.sandbox_network_attach or "").split(","):
            item = item.strip()
            if not item:
                continue
            container, _, alias = item.partition(":")
            if container == "self":
                container = socket.gethostname()
            out.append((container, alias or None))
        return out

    def sandbox_user(self) -> str:
        """uid:gid for `--user`. Default: the gateway's own (so both write the working copy), never root."""
        user = self.settings.sandbox_docker_user
        if user:
            if user.split(":")[0] in ("0", "root"):
                raise RuntimeError("SANDBOX_DOCKER_USER must not be root (uid 0)")
            return user
        if hasattr(os, "getuid") and os.getuid() != 0:
            return f"{os.getuid()}:{os.getgid()}"
        return SANDBOX_DEFAULT_USER  # Windows host, or a root gateway (workspace is chowned, see ensure_running)

    async def _docker(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = await asyncio.to_thread(subprocess.run, ["docker", *args], capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise RuntimeError(f"docker {' '.join(args[:2])} failed: {proc.stderr.strip()}")
        return proc

    def _host_path(self, workspace_dir: Path) -> str:
        if self.settings.host_data_dir is None:
            return str(workspace_dir.resolve())
        rel = workspace_dir.resolve().relative_to(self.settings.data_dir.resolve())
        return str(self.settings.host_data_dir / rel)

    async def _prepare_network(self, user_id: str) -> str:
        """Create the learner's own internal network (idempotent) and attach the gateway and router to it."""
        net = self.network_name(user_id)
        created = await self._docker("network", "create", "--internal", "--label", "mentor.sandbox=1", net,
                                     check=False)
        if created.returncode != 0 and "already exists" not in created.stderr:
            raise RuntimeError(f"docker network create {net} failed: {created.stderr.strip()}")
        for container, alias in self.attachments():
            args = ["network", "connect", *(["--alias", alias] if alias else []), net, container]
            proc = await self._docker(*args, check=False)
            if proc.returncode != 0 and "already exists" not in proc.stderr:
                raise RuntimeError(f"docker network connect {net} {container} failed: {proc.stderr.strip()}")
        return net

    async def _remove_network(self, user_id: str) -> None:
        net = self.network_name(user_id)
        for container, _alias in self.attachments():
            await self._docker("network", "disconnect", "-f", net, container, check=False)
        await self._docker("network", "rm", net, check=False)

    async def ensure_running(self, spec: SandboxSpec) -> str:
        name = self.container_name(spec.user_id)
        user = self.sandbox_user()
        uid, _, gid = user.partition(":")
        if hasattr(os, "geteuid") and os.geteuid() == 0 and uid.isdigit() and (gid or uid).isdigit():
            # A root gateway cannot hand its uid to the sandbox: give the working copy to the sandbox uid instead
            # (after every pull, which may have created root-owned files). Prefer a non-root gateway.
            await asyncio.to_thread(_chown_tree, spec.workspace_dir, int(uid), int(gid or uid))
        if await self.status(spec.user_id) == "running" and spec.user_id in self._urls:
            return self._urls[spec.user_id]
        await self._docker("rm", "-f", name, check=False)
        args = ["run", "-d", "--name", name, "--label", "mentor.sandbox=1",
                "--memory", "1g", "--cpus", "1", "--pids-limit", "256",
                "--user", user,
                "--read-only", "--tmpfs", f"/tmp:rw,nosuid,nodev,noexec,size={self.settings.sandbox_tmpfs_size},mode=1777",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "-v", f"{self._host_path(spec.workspace_dir)}:/workspace"]
        harness_token = new_harness_token()
        env = sandbox_env(self.settings, spec, "/workspace", self.tokens.issue(spec.user_id, spec.profile),
                          harness_token)
        # tells the harness it may enable run_python (CONTRACTS section 3). Only true on an internal network:
        # a port-published container has internet access. "0" overrides the image's default of 1.
        isolated = self.per_sandbox_network or bool(self.settings.sandbox_docker_network)
        env["MENTOR_SANDBOX_ISOLATED"] = "1" if isolated else "0"
        for k, v in env.items():
            args += ["-e", f"{k}={v}"]
        if self.per_sandbox_network:
            args += ["--network", await self._prepare_network(spec.user_id)]
            base_url = f"http://{name}:8080"
        elif self.settings.sandbox_docker_network:
            args += ["--network", self.settings.sandbox_docker_network]
            base_url = f"http://{name}:8080"
            log.warning("sandbox %s shares network %s with other sandboxes (only the harness token separates "
                        "them); set SANDBOX_NETWORK_ATTACH for one network per sandbox", name,
                        self.settings.sandbox_docker_network)
        else:
            port = free_port()
            args += ["-p", f"127.0.0.1:{port}:8080"]
            base_url = f"http://127.0.0.1:{port}"
            log.warning("DockerBackend without SANDBOX_NETWORK_ATTACH / SANDBOX_DOCKER_NETWORK: sandbox %s is not "
                        "network-isolated", name)
        args.append(self.settings.sandbox_image)
        await self._docker(*args)
        self._urls[spec.user_id] = base_url
        self._harness_tokens[spec.user_id] = harness_token
        await wait_healthy(base_url, self.start_timeout)
        return base_url

    async def stop(self, user_id: str) -> None:
        self.tokens.revoke(user_id)
        self._urls.pop(user_id, None)
        self._harness_tokens.pop(user_id, None)
        await self._docker("rm", "-f", self.container_name(user_id), check=False)
        if self.per_sandbox_network:
            await self._remove_network(user_id)

    async def status(self, user_id: str) -> BackendStatus:
        proc = await self._docker("inspect", "-f", "{{.State.Running}}", self.container_name(user_id), check=False)
        return "running" if proc.returncode == 0 and proc.stdout.strip() == "true" else "stopped"

    async def shutdown(self) -> None:
        for uid in list(self._urls):
            await self.stop(uid)


def make_backend(settings: Settings, tokens: SandboxTokens | None = None) -> SandboxBackend:
    if settings.sandbox_backend == "docker":
        return DockerBackend(settings, tokens=tokens)
    return LocalProcessBackend(settings, tokens=tokens)
