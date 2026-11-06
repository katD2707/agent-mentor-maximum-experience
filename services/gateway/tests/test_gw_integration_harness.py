"""Opt-in: the gateway with LocalProcessBackend against the real harness in scripted mode.

Run with: MENTOR_IT_HARNESS=1 uv run pytest services/gateway/tests/test_gw_integration_harness.py -q
Add MENTOR_IT_DOCKER=1 to also run it with DockerBackend (needs the mentor-sandbox:dev image).
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gateway_fakes import onboard, recv_until
from mentor_schemas import JobKind, JobRequest, Profile

from mentor_gateway.app import create_app
from mentor_gateway.sandbox import DockerBackend, LocalProcessBackend
from mentor_gateway.settings import Settings

pytestmark = pytest.mark.skipif(os.environ.get("MENTOR_IT_HARNESS") != "1", reason="set MENTOR_IT_HARNESS=1")

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("kind", ["local", "docker"])
def test_turn_and_job_through_real_harness(tmp_path, kind):
    if kind == "docker" and os.environ.get("MENTOR_IT_DOCKER") != "1":
        pytest.skip("set MENTOR_IT_DOCKER=1")
    settings = Settings(env="test", data_dir=tmp_path / "var", content_dir=REPO / "mentor-content",
                        public_base_url="http://testserver", background_tasks=False, model_mode="scripted",
                        model_router_url="http://127.0.0.1:9")
    backend = (LocalProcessBackend if kind == "local" else DockerBackend)(settings, start_timeout=90)
    app = create_app(settings, backend=backend)
    gw = app.state.gw
    with TestClient(app) as client:
        me = onboard(client, "it@example.com", "ncs")
        uid = me["user_id"]
        head_before = gw.mirror.head(uid)
        with client.websocket_connect("/api/ws/chat") as ws:
            assert ws.receive_json()["state"] in ("sleeping", "waking")  # waking: pre-warm started on connect
            ws.send_json({"type": "user_message", "client_msg_id": "c1", "text": "Xin chào mentor", "attachments": []})
            msgs = recv_until(ws, "turn_done", limit=500)
        errors = [m for m in msgs if m["type"] == "error"]
        assert not errors, errors
        text = "".join(m.get("text", "") for m in msgs if m["type"] == "text_delta")
        assert text.strip()
        assert gw.mirror.head(uid) != head_before  # harness committed, gateway pushed
        assert any(c.author == "mentor" for c in gw.mirror.history(uid))

        gw.jobs.enqueue(JobRequest(job_id="it-job", user_id=uid, profile=Profile.NCS, kind=JobKind.NIGHTLY_REFLECTION))
        client.portal.call(gw.scheduler.tick, gw.clock())
        client.portal.call(gw.runner.drain)
        row = gw.jobs.get("it-job")
        assert row.status in ("ok", "skipped"), row.error
