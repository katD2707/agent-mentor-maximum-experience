"""Wake/sleep sandboxes and keep the working copy in sync around every turn and job (plan 5.3, 5.4).

Pre-warming (`warm`): when a learner opens the chat (WebSocket connect, or POST /api/sandbox/warm on focus) the
sandbox is started in the background so the first message does not pay the cold start. A warm-up only starts the
sandbox and waits until it is healthy: no git pull/push, no turn, and it never holds the per-user session lock.
`session()` joins an in-flight warm-up before calling `ensure_running` itself, so a backend is never asked to
start the same sandbox twice concurrently. A warm-up refreshes the idle timer like a turn does, so an unused warm
sandbox still goes to sleep after `idle_seconds`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Literal

from mentor_gateway.mirror import WorkspaceSync
from mentor_gateway.sandbox.backends import SandboxBackend, SandboxSpec
from mentor_gateway.sandbox.client import SandboxClient
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

SandboxState = Literal["sleeping", "waking", "ready", "busy"]
# started: a background start was launched; starting: one is already in flight; already_running: the idle timer
# was refreshed; busy: a turn or job holds the sandbox; throttled: a warm-up ran less than `warm_interval` ago;
# disabled: SANDBOX_PREWARM is off
WarmResult = Literal["started", "starting", "already_running", "busy", "throttled", "disabled"]
StatusCallback = Callable[[str, SandboxState], Awaitable[None]]


async def _noop(_user_id: str, _state: SandboxState) -> None:
    return None


class Orchestrator:
    def __init__(
        self,
        backend: SandboxBackend,
        sync: WorkspaceSync,
        clock: Clock,
        idle_seconds: int = 900,
        on_status: StatusCallback = _noop,
        prewarm: bool = True,
        warm_interval_seconds: float = 60.0,
    ) -> None:
        self.backend = backend
        self.sync = sync
        self.clock = clock
        self.idle = timedelta(seconds=idle_seconds)
        self.on_status = on_status
        self._locks: dict[str, asyncio.Lock] = {}
        self._clients: dict[str, SandboxClient] = {}
        self._last_used: dict[str, datetime] = {}
        self.prewarm = prewarm
        self.warm_interval = timedelta(seconds=warm_interval_seconds)
        self._warming: dict[str, asyncio.Task] = {}
        self._last_warm: dict[str, datetime] = {}

    def _lock(self, user_id: str) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    async def state(self, user_id: str) -> SandboxState:
        if self._lock(user_id).locked():
            return "busy"
        if self._warm_in_flight(user_id):
            return "waking"
        return "ready" if await self.backend.status(user_id) == "running" else "sleeping"

    def active_client(self, user_id: str) -> SandboxClient | None:
        """Client of a running sandbox (used to forward approval decisions during a turn)."""
        return self._clients.get(user_id)

    @asynccontextmanager
    async def session(self, spec: SandboxSpec) -> AsyncIterator[SandboxClient]:
        """Exclusive use of the learner's sandbox: wake, pull web edits, yield, then push to the mirror.

        Outbox items must be dispatched after this context exits so the mirror already has the
        files they reference (e.g. a parent report).
        """
        uid = spec.user_id
        async with self._lock(uid):
            if await self.backend.status(uid) != "running":
                await self.on_status(uid, "waking")
            await asyncio.to_thread(self.sync.ensure_clone, uid)
            await asyncio.to_thread(self.sync.pull, uid)
            await self._join_warm(uid)  # never two concurrent ensure_running calls for one learner
            base_url = await self.backend.ensure_running(spec)
            client = SandboxClient(base_url, token=self.backend.harness_token(uid))
            self._clients[uid] = client
            await self.on_status(uid, "busy")
            try:
                yield client
            finally:
                try:
                    await asyncio.to_thread(self.sync.push, uid)
                except Exception:
                    log.exception("push to mirror failed for %s", uid)
                self._last_used[uid] = self.clock()
        await self.on_status(uid, "ready")

    # ---- pre-warming ---------------------------------------------------------------------------

    def _warm_in_flight(self, user_id: str) -> bool:
        task = self._warming.get(user_id)
        return task is not None and not task.done()

    async def _join_warm(self, user_id: str) -> None:
        task = self._warming.get(user_id)
        if task is not None and not task.done():
            await asyncio.wait([task])  # its failure is logged by the task; the caller starts the sandbox itself

    async def warm(self, spec: SandboxSpec) -> tuple[SandboxState, WarmResult]:
        """Start the learner's sandbox in the background if it is asleep. Never blocks on the start itself.

        Idempotent (one start in flight per learner, nothing while a turn/job holds the sandbox) and throttled to
        one warm-up per `warm_interval` per learner. The caller checks that the learner is active.
        """
        uid = spec.user_id
        if not self.prewarm:
            return await self.state(uid), "disabled"
        if self._warm_in_flight(uid):
            return "waking", "starting"
        if self._lock(uid).locked():
            return "busy", "busy"
        now = self.clock()
        last = self._last_warm.get(uid)
        if last is not None and now - last < self.warm_interval:
            return await self.state(uid), "throttled"
        self._last_warm[uid] = now  # before any await: a concurrent call is throttled
        if await self.backend.status(uid) == "running":
            if not self._lock(uid).locked():
                self._last_used[uid] = now  # the learner is here: keep it awake for another idle period
            return await self.state(uid), "already_running"
        if self._lock(uid).locked():  # a turn or job took the sandbox during the status call
            return "busy", "busy"
        task = asyncio.create_task(self._warm(spec), name=f"warm-{uid}")
        self._warming[uid] = task
        task.add_done_callback(lambda t: self._warming.pop(uid, None) if self._warming.get(uid) is t else None)
        return "waking", "started"

    async def _warm(self, spec: SandboxSpec) -> None:
        uid = spec.user_id
        try:
            await asyncio.to_thread(self.sync.ensure_clone, uid)  # the sandbox's cwd; no pull, no push
            if self._lock(uid).locked():
                return  # a turn or job took the sandbox meanwhile; it starts the sandbox itself after pulling
            await self.on_status(uid, "waking")
            # No double start: session() waits for this task (_join_warm) before its own ensure_running, and
            # warm() never launches a task while session() holds the lock.
            base_url = await self.backend.ensure_running(spec)
            self._clients[uid] = SandboxClient(base_url, token=self.backend.harness_token(uid))
            self._last_used[uid] = self.clock()  # an unused warm sandbox sleeps after the normal idle timeout
            if not self._lock(uid).locked():  # a waiting turn reports busy next; no ready flicker in between
                await self.on_status(uid, "ready")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("pre-warming the sandbox of %s failed", uid, exc_info=True)
            if not self._lock(uid).locked():
                await self.on_status(uid, "sleeping")

    async def stop(self, user_id: str) -> None:
        self._clients.pop(user_id, None)
        self._last_used.pop(user_id, None)
        await self.backend.stop(user_id)
        await self.on_status(user_id, "sleeping")

    async def reap_idle(self, now: datetime | None = None) -> list[str]:
        """Stop sandboxes idle for longer than the idle timeout. Returns the stopped user ids."""
        now = now or self.clock()
        stopped = []
        for uid, last in list(self._last_used.items()):
            if self._lock(uid).locked() or self._warm_in_flight(uid) or now - last < self.idle:
                continue
            await self.stop(uid)
            stopped.append(uid)
        return stopped

    async def shutdown(self) -> None:
        warming = [t for t in self._warming.values() if not t.done()]
        for t in warming:
            t.cancel()
        await asyncio.gather(*warming, return_exceptions=True)
        self._warming.clear()
        for uid in list(self._clients):
            try:
                await self.backend.stop(uid)
            except Exception:
                log.exception("stopping sandbox %s", uid)
        self._clients.clear()
