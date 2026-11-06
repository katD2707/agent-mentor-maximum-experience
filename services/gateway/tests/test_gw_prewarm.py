"""Sandbox pre-warming: POST /api/sandbox/warm and the WebSocket connect hook (CONTRACTS section 5)."""

import asyncio

import pytest
from gateway_fakes import onboard, recv_until
from mentor_schemas import Profile

from mentor_gateway.sandbox import SandboxSpec


@pytest.fixture
def prewarm(gw):
    gw.orchestrator.prewarm = True
    return gw.orchestrator


def _spec(gw, uid: str) -> SandboxSpec:
    return SandboxSpec(user_id=uid, profile=Profile.NCS, workspace_dir=gw.sync.path(uid))


def _drain_warm(client, gw, uid: str) -> None:
    client.portal.call(gw.orchestrator._join_warm, uid)


def _gate(backend) -> tuple[asyncio.Event, asyncio.Event]:
    """Hold the fake backend's start until `gate` is set; `entered` is set once a start is waiting."""
    gate, entered = asyncio.Event(), asyncio.Event()
    real = backend.ensure_running

    async def slow(spec):
        entered.set()
        await gate.wait()
        return await real(spec)

    backend.ensure_running = slow
    return gate, entered


def test_warm_starts_sandbox_without_turn_then_throttles(client, gw, ncs_user, prewarm, backend, sandbox, clock):
    uid = ncs_user["user_id"]
    head = gw.mirror.head(uid)
    r = client.post("/api/sandbox/warm")
    assert r.status_code == 200
    assert r.json() == {"state": "waking", "warming": True, "result": "started"}
    _drain_warm(client, gw, uid)
    assert backend.running == {uid} and backend.starts == 1
    assert sandbox.turns == [] and sandbox.jobs == [] and sandbox.auth_headers == []  # no turn, not even a call
    assert gw.mirror.head(uid) == head  # no push to the mirror
    assert gw.orchestrator.active_client(uid) is not None

    assert client.post("/api/sandbox/warm").json() == {"state": "ready", "warming": False, "result": "throttled"}
    clock.advance(seconds=61)
    assert client.post("/api/sandbox/warm").json() == {"state": "ready", "warming": False,
                                                         "result": "already_running"}
    assert backend.starts == 1


def test_concurrent_warmups_start_once(client, gw, ncs_user, prewarm, backend, clock):
    uid = ncs_user["user_id"]
    spec = _spec(gw, uid)

    async def scenario():
        gate, _ = _gate(backend)
        first, second = await asyncio.gather(prewarm.warm(spec), prewarm.warm(spec))
        clock.advance(minutes=5)  # past the throttle: still one start in flight
        third = await prewarm.warm(spec)
        mid_state = await prewarm.state(uid)
        gate.set()
        await prewarm._join_warm(uid)
        return first, second, third, mid_state

    first, second, third, mid_state = client.portal.call(scenario)
    assert first == ("waking", "started")
    assert second[1] in ("throttled", "starting")  # depends on whether status() yielded; never a 2nd start
    assert third == ("waking", "starting")
    assert mid_state == "waking"
    assert backend.starts == 1


def test_turn_during_warmup_joins_it(client, gw, ncs_user, prewarm, backend, clock):
    """A turn that arrives while the warm-up is starting waits for it (one start), keeps the lock semantics
    (pull, busy, push) and sees no "ready" flicker between waking and busy. A warm-up during the turn is a no-op."""
    uid = ncs_user["user_id"]
    spec = _spec(gw, uid)
    states: list[str] = []

    async def record(_uid, state):
        states.append(state)

    async def scenario():
        prewarm.on_status = record
        gate, entered = _gate(backend)
        assert (await prewarm.warm(spec))[1] == "started"
        await asyncio.wait_for(entered.wait(), 10)  # the warm task is inside ensure_running

        async def turn():
            async with prewarm.session(spec) as c:
                clock.advance(minutes=2)
                during = await prewarm.warm(spec)
                healthy = await c.health()
            return during, healthy

        t = asyncio.create_task(turn())
        await asyncio.sleep(0.05)
        assert not t.done()  # waiting for the warm-up, not starting a second sandbox
        gate.set()
        return await t

    during, healthy = client.portal.call(scenario)
    assert during == ("busy", "busy")
    assert healthy
    assert backend.starts == 1
    assert states == ["waking", "waking", "busy", "ready"]


def test_inactive_and_anonymous_skipped(client, gw, prewarm, backend):
    assert client.post("/api/sandbox/warm").status_code == 401
    me = onboard(client, "hs@example.com", "thpt")  # parent not verified yet: needs_parent
    assert me["onboarding_state"] == "needs_parent"
    r = client.post("/api/sandbox/warm")
    assert r.json() == {"state": "sleeping", "warming": False, "result": "not_active"}
    assert backend.starts == 0


def test_disabled_by_setting(client, gw, ncs_user, backend):
    assert gw.orchestrator.prewarm is False  # conftest sets SANDBOX_PREWARM off
    assert client.post("/api/sandbox/warm").json()["result"] == "disabled"
    assert backend.starts == 0


def test_unused_warm_sandbox_sleeps_after_idle_timeout(client, gw, ncs_user, prewarm, backend, clock):
    uid = ncs_user["user_id"]
    client.post("/api/sandbox/warm")
    _drain_warm(client, gw, uid)
    assert backend.running == {uid}
    clock.advance(minutes=14)
    assert client.portal.call(gw.orchestrator.reap_idle, clock()) == []
    clock.advance(minutes=2)
    assert client.portal.call(gw.orchestrator.reap_idle, clock()) == [uid]
    assert not backend.running


def test_ws_connect_prewarms(client, gw, ncs_user, prewarm, backend, sandbox):
    with client.websocket_connect("/api/ws/chat") as ws:
        assert ws.receive_json() == {"type": "sandbox_status", "state": "waking"}
        while recv_until(ws, "sandbox_status")[-1]["state"] != "ready":
            pass
        assert backend.starts == 1 and sandbox.turns == []
        ws.send_json({"type": "user_message", "client_msg_id": "c1", "text": "xin chào", "attachments": []})
        msgs = recv_until(ws, "turn_done")
    states = [m["state"] for m in msgs if m["type"] == "sandbox_status"]
    assert "waking" not in states and states[-2:] == ["busy", "ready"]  # already warm: no cold start
    assert backend.starts == 1 and len(sandbox.turns) == 1
