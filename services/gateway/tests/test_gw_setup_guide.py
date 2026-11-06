"""First-login setup guide flag: PUT /settings/setup-guide and Me.setup_guide_dismissed_at."""

from datetime import datetime

from gateway_fakes import login, onboard

from mentor_gateway.db import UserUiState


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)  # Python 3.11+ accepts a trailing "Z"


def test_setup_guide_dismissal_is_stored_server_side(client, gw, clock):
    me = onboard(client, "ncs@example.com", "ncs")
    assert me["setup_guide_dismissed_at"] is None

    r = client.put("/api/settings/setup-guide", json={"dismissed": True})
    assert r.status_code == 200, r.text
    first = r.json()["setup_guide_dismissed_at"]
    assert _at(first) == clock()
    assert _at(client.get("/api/me").json()["setup_guide_dismissed_at"]) == clock()

    # closing it again (reopened from Settings) keeps the first dismissal time
    clock.advance(hours=1)
    assert client.put("/api/settings/setup-guide", json={"dismissed": True}).json()["setup_guide_dismissed_at"] == first

    # reset: shown again on the next visit
    assert client.put("/api/settings/setup-guide", json={"dismissed": False}).json() == {"setup_guide_dismissed_at": None}
    assert client.get("/api/me").json()["setup_guide_dismissed_at"] is None

    assert client.put("/api/settings/setup-guide", json={}).status_code == 422

    # account deletion removes the row
    client.put("/api/settings/setup-guide", json={"dismissed": True})
    uid = me["user_id"]
    assert client.delete("/api/account").status_code == 200
    with gw.db.session() as s:
        assert s.get(UserUiState, uid) is None


def test_setup_guide_needs_session_and_onboarding(client):
    assert client.put("/api/settings/setup-guide", json={"dismissed": True}).status_code == 401
    login(client, "new@example.com")
    assert client.get("/api/me").json()["setup_guide_dismissed_at"] is None
    assert client.put("/api/settings/setup-guide", json={"dismissed": True}).status_code == 409
