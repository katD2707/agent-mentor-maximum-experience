"""First-run tour state: GET/PUT /api/onboarding and Me.tour (CONTRACTS 12)."""

from gateway_fakes import login, onboard

from mentor_gateway.db import UserOnboarding


def test_tour_defaults_and_me(client):
    me = onboard(client, "thpt@example.com", "thpt")
    assert me["tour"] == {"tour_step": None, "tour_completed_at": None, "tour_skipped_at": None, "tips_seen": []}
    assert client.get("/api/onboarding").json() == me["tour"]


def test_tour_progress_complete_and_replay(client, clock):
    onboard(client, "a@example.com", "thpt")
    r = client.put("/api/onboarding", json={"step": "practice"})
    assert r.status_code == 200, r.text
    assert r.json()["tour_step"] == "practice"
    assert client.get("/api/me").json()["tour"]["tour_step"] == "practice"  # resumes on another device

    done = client.put("/api/onboarding", json={"complete": True}).json()
    assert done["tour_step"] is None and done["tour_completed_at"] is not None
    clock.advance(hours=1)
    # completing again keeps the first time
    assert client.put("/api/onboarding", json={"complete": True}).json()["tour_completed_at"] == done["tour_completed_at"]

    again = client.put("/api/onboarding", json={"restart": True}).json()
    assert again["tour_step"] == "welcome" and again["tour_completed_at"] is None and again["tour_skipped_at"] is None


def test_tour_skip(client):
    onboard(client, "b@example.com", "ncs")
    s = client.put("/api/onboarding", json={"skip": True}).json()
    assert s["tour_skipped_at"] is not None and s["tour_step"] is None and s["tour_completed_at"] is None


def test_tips_seen_once_and_validated(client):
    onboard(client, "c@example.com", "thpt")
    client.put("/api/onboarding", json={"tip": "progress"})
    client.put("/api/onboarding", json={"tip": "progress"})
    out = client.put("/api/onboarding", json={"tip": "plans"}).json()
    assert out["tips_seen"] == ["progress", "plans"]
    # replaying the tour does not bring tips back
    assert client.put("/api/onboarding", json={"restart": True}).json()["tips_seen"] == ["progress", "plans"]
    assert client.put("/api/onboarding", json={"tip": "Bad Tip!"}).status_code == 422
    assert client.put("/api/onboarding", json={"step": "nope"}).status_code == 422
    assert client.put("/api/onboarding", json={}).status_code == 422


def test_tour_needs_session_and_is_deleted_with_account(client, gw):
    assert client.get("/api/onboarding").status_code == 401
    login(client, "new@example.com")
    assert client.get("/api/onboarding").status_code == 409  # not onboarded yet
    me = onboard(client, "d@example.com", "thpt")
    client.put("/api/onboarding", json={"tip": "plans"})
    assert client.delete("/api/account").status_code == 200
    with gw.db.session() as s:
        assert s.get(UserOnboarding, me["user_id"]) is None
