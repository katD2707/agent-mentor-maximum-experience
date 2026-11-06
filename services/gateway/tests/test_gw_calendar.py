"""Google Calendar: OAuth connect flow, token storage/refresh and /internal/calendar/*, against a fake Google."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from gateway_fakes import login, onboard
from mentor_schemas import Profile

from mentor_gateway.app import create_app
from mentor_gateway.gcal import CALENDAR_SCOPE, GoogleCalendarLink, OAuthState, to_event

CLIENT_ID = "cid.apps.googleusercontent.com"


def _jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


class FakeGoogle:
    """oauth2.googleapis.com + the Calendar v3 events API, in memory."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.revoked: list[str] = []
        self.scope = f"openid {CALENDAR_SCOPE} https://www.googleapis.com/auth/userinfo.email"
        self.refresh_error: str | None = None
        self.n = 0
        self.valid_access: set[str] = set()
        self.events: dict[str, dict] = {
            "foreign1": {"id": "foreign1", "status": "confirmed", "summary": "Họp lab",
                         "description": "<b>Agenda</b>: " + "x" * 600, "location": "P.301",
                         "start": {"dateTime": "2026-10-29T09:00:00+07:00"},
                         "end": {"dateTime": "2026-10-29T10:00:00+07:00"}},
            "gone": {"id": "gone", "status": "cancelled"},
        }

    def _token(self) -> str:
        self.n += 1
        tok = f"access-{self.n}"
        self.valid_access.add(tok)
        return tok

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = request.url
        if url.host == "oauth2.googleapis.com" and url.path == "/token":
            form = parse_qs(request.content.decode())
            grant = form["grant_type"][0]
            if grant == "authorization_code":
                self.last_exchange = form
                if form["code"][0] != "good-code":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={
                    "access_token": self._token(), "expires_in": 3599, "refresh_token": "refresh-1",
                    "scope": self.scope, "token_type": "Bearer",
                    "id_token": _jwt({"aud": CLIENT_ID, "email": "ncs.learner@gmail.com"}),
                })
            if self.refresh_error:
                return httpx.Response(400, json={"error": self.refresh_error})
            assert form["refresh_token"] == ["refresh-1"]
            return httpx.Response(200, json={"access_token": self._token(), "expires_in": 3599})
        if url.host == "oauth2.googleapis.com" and url.path == "/revoke":
            self.revoked.append(parse_qs(request.content.decode())["token"][0])
            return httpx.Response(200)
        assert url.host == "www.googleapis.com" and url.path.startswith("/calendar/v3/calendars/primary/events")
        if request.headers.get("authorization", "")[7:] not in self.valid_access:
            return httpx.Response(401, json={"error": {"code": 401}})
        rest = url.path.removeprefix("/calendar/v3/calendars/primary/events").strip("/")
        if not rest and request.method == "GET":
            self.last_list = dict(url.params)
            return httpx.Response(200, json={"items": list(self.events.values())})
        if not rest and request.method == "POST":
            body = json.loads(request.content)
            eid = f"mentor{len(self.events)}"
            self.events[eid] = {"id": eid, "status": "confirmed", **body}
            return httpx.Response(200, json=self.events[eid])
        ev = self.events.get(rest)
        if ev is None or ev.get("status") == "cancelled":
            return httpx.Response(404, json={"error": {"code": 404}})
        if request.method == "GET":
            return httpx.Response(200, json=ev)
        if request.method == "PATCH":
            ev.update(json.loads(request.content))
            return httpx.Response(200, json=ev)
        if request.method == "DELETE":
            del self.events[rest]
            return httpx.Response(204)
        raise AssertionError(request)


class IdleBackend:
    async def ensure_running(self, spec):  # pragma: no cover - not used here
        raise AssertionError

    async def stop(self, user_id):
        return None

    async def status(self, user_id):
        return "stopped"


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def cal_client(settings, clock, google):
    settings = settings.model_copy(update={"google_oauth_client_id": CLIENT_ID, "google_oauth_client_secret": "sec",
                                           "calendar_requests_per_minute": 100})
    app = create_app(settings, clock=clock, backend=IdleBackend())
    app.state.gw.gcal.transport = httpx.MockTransport(google)
    with TestClient(app) as c:
        yield c


def _connect(client: TestClient, code: str = "good-code") -> httpx.Response:
    r = client.get("/api/integrations/google-calendar/connect", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return client.get("/api/integrations/google-calendar/callback", params={"code": code, "state": state},
                      follow_redirects=False)


def _sandbox(client: TestClient, user_id: str, profile: Profile = Profile.NCS) -> dict:
    return {"Authorization": f"Bearer {client.app.state.gw.tokens.issue(user_id, profile)}"}


# ---- connect flow ------------------------------------------------------------------------------


def test_connect_flow_pkce_and_sealed_tokens(cal_client: TestClient, google: FakeGoogle) -> None:
    me = onboard(cal_client, "ncs@example.com", "ncs")
    st = cal_client.get("/api/integrations/google-calendar").json()
    assert st == {"available": True, "connected": False, "email": None, "scopes": []}

    r = cal_client.get("/api/integrations/google-calendar/connect", follow_redirects=False)
    loc = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(loc.query).items()}
    assert (loc.scheme, loc.netloc, loc.path) == ("https", "accounts.google.com", "/o/oauth2/v2/auth")
    assert q["client_id"] == CLIENT_ID and q["response_type"] == "code" and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "http://testserver/api/integrations/google-calendar/callback"
    assert set(q["scope"].split()) == {"openid", "email", CALENDAR_SCOPE}
    assert q["access_type"] == "offline" and q["prompt"] == "consent"

    r = cal_client.get("/api/integrations/google-calendar/callback", params={"code": "good-code", "state": q["state"]},
                       follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://web.test/settings?calendar=connected"
    verifier = google.last_exchange["code_verifier"][0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == q["code_challenge"] and google.last_exchange["client_secret"] == ["sec"]

    st = cal_client.get("/api/integrations/google-calendar").json()
    assert st["connected"] and st["email"] == "ncs.learner@gmail.com" and CALENDAR_SCOPE in st["scopes"]
    gw = cal_client.app.state.gw
    with gw.db.session() as s:
        link = s.get(GoogleCalendarLink, me["user_id"])
        assert "refresh-1" not in link.refresh_token and "access-" not in (link.access_token or "")
        assert gw.box.unseal_str(link.refresh_token, aad=f"gcal-refresh:{me['user_id']}") == "refresh-1"
        assert s.query(OAuthState).count() == 0  # single use

    # replaying the same state fails
    r = cal_client.get("/api/integrations/google-calendar/callback", params={"code": "good-code", "state": q["state"]},
                       follow_redirects=False)
    assert r.headers["location"].endswith("calendar=error&reason=state")


def test_state_bound_to_session_and_expires(cal_client: TestClient, clock) -> None:
    onboard(cal_client, "ncs@example.com", "ncs")
    r = cal_client.get("/api/integrations/google-calendar/connect", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    login(cal_client, "ncs@example.com")  # same learner, new session cookie
    r = cal_client.get("/api/integrations/google-calendar/callback", params={"code": "good-code", "state": state},
                       follow_redirects=False)
    assert r.headers["location"].endswith("reason=state")

    r = cal_client.get("/api/integrations/google-calendar/connect", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    clock.advance(minutes=11)
    r = cal_client.get("/api/integrations/google-calendar/callback", params={"code": "good-code", "state": state},
                       follow_redirects=False)
    assert r.headers["location"].endswith("reason=state")
    assert not cal_client.get("/api/integrations/google-calendar").json()["connected"]


def test_denied_scope_missing_and_bad_code(cal_client: TestClient, google: FakeGoogle) -> None:
    onboard(cal_client, "ncs@example.com", "ncs")
    r = cal_client.get("/api/integrations/google-calendar/connect", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = cal_client.get("/api/integrations/google-calendar/callback", params={"error": "access_denied", "state": state},
                       follow_redirects=False)
    assert r.headers["location"] == "http://web.test/settings?calendar=error&reason=denied"
    assert _connect(cal_client, code="bad").headers["location"].endswith("reason=exchange")
    google.scope = "openid email"  # learner unticked the calendar box on the consent screen
    assert _connect(cal_client).headers["location"].endswith("reason=scope")
    assert google.revoked == ["refresh-1"]
    assert not cal_client.get("/api/integrations/google-calendar").json()["connected"]
    cal_client.cookies.clear()  # no web session at all
    r = cal_client.get("/api/integrations/google-calendar/callback", params={"code": "x", "state": "x"},
                       follow_redirects=False)
    assert r.headers["location"].endswith("reason=session")


def test_disconnect_revokes(cal_client: TestClient, google: FakeGoogle) -> None:
    onboard(cal_client, "ncs@example.com", "ncs")
    _connect(cal_client)
    assert cal_client.delete("/api/integrations/google-calendar").json() == {"ok": True}
    assert google.revoked == ["refresh-1"]
    assert not cal_client.get("/api/integrations/google-calendar").json()["connected"]


def test_thpt_forbidden_and_unconfigured(cal_client: TestClient, settings, clock) -> None:
    onboard(cal_client, "hs@example.com", "thpt")
    assert cal_client.get("/api/integrations/google-calendar").status_code == 403
    assert cal_client.get("/api/integrations/google-calendar/connect", follow_redirects=False).status_code == 403
    app = create_app(settings.model_copy(update={"data_dir": settings.data_dir / "b"}), clock=clock,
                     backend=IdleBackend())
    with TestClient(app) as c:
        onboard(c, "ncs@example.com", "ncs")
        assert c.get("/api/integrations/google-calendar").json()["available"] is False
        assert c.get("/api/integrations/google-calendar/connect", follow_redirects=False).status_code == 503


# ---- sandbox endpoints -----------------------------------------------------------------------------


def test_internal_auth_and_not_connected(cal_client: TestClient) -> None:
    me = onboard(cal_client, "ncs@example.com", "ncs")
    assert cal_client.get("/internal/calendar/events").status_code == 401
    assert cal_client.get("/internal/calendar/events", headers=_sandbox(cal_client, "u2", Profile.THPT)).status_code == 403
    h = _sandbox(cal_client, me["user_id"])
    assert cal_client.get("/internal/calendar/status", headers=h).json() == {
        "available": True, "connected": False, "email": None}
    r = cal_client.get("/internal/calendar/events", headers=h)
    assert r.status_code == 409 and r.json()["reason"] == "not_connected"


def test_list_events_and_refresh(cal_client: TestClient, google: FakeGoogle, clock) -> None:
    me = onboard(cal_client, "ncs@example.com", "ncs")
    _connect(cal_client)
    h = _sandbox(cal_client, me["user_id"])
    r = cal_client.get("/internal/calendar/events", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert google.last_list["maxResults"] == "50" and google.last_list["singleEvents"] == "true"
    assert body["start"].startswith("2026-10-28T10:00:00+07:00") and body["end"].startswith("2026-11-11T10:00")
    [ev] = body["events"]  # the cancelled one is dropped
    assert ev["title"] == "Họp lab" and ev["created_by_mentor"] is False and ev["location"] == "P.301"
    assert ev["description"].startswith("Agenda") and "<b>" not in ev["description"] and len(ev["description"]) <= 300
    assert set(ev) == {"id", "title", "start", "end", "all_day", "location", "description", "created_by_mentor"}
    assert "access" not in r.text and "refresh" not in r.text

    clock.advance(hours=2)  # access token expired: refreshed server side
    assert cal_client.get("/internal/calendar/events", headers=h).status_code == 200
    assert google.n == 2

    params = {"start": "2026-11-01", "end": "2027-02-01"}
    assert cal_client.get("/internal/calendar/events", params=params, headers=h).status_code == 400

    clock.advance(hours=2)
    google.refresh_error = "invalid_grant"  # learner removed access in their Google account
    r = cal_client.get("/internal/calendar/events", headers=h)
    assert r.status_code == 409 and not cal_client.get("/api/integrations/google-calendar").json()["connected"]


def test_create_update_delete_only_mentor_events(cal_client: TestClient, google: FakeGoogle) -> None:
    me = onboard(cal_client, "ncs@example.com", "ncs")
    _connect(cal_client)
    h = _sandbox(cal_client, me["user_id"])
    r = cal_client.post("/internal/calendar/events", headers=h, json={
        "title": "Nộp full paper ACL", "start": "2026-11-16T18:59:00", "description": "Hạn nộp (giờ VN)"})
    assert r.status_code == 200, r.text
    ev = r.json()["event"]
    stored = google.events[ev["id"]]
    assert stored["extendedProperties"] == {"private": {"mentorCreated": "1"}}
    assert stored["start"] == {"dateTime": "2026-11-16T18:59:00+07:00", "timeZone": "Asia/Ho_Chi_Minh"}
    assert stored["end"]["dateTime"] == "2026-11-16T19:59:00+07:00" and ev["created_by_mentor"]

    r = cal_client.patch(f"/internal/calendar/events/{ev['id']}", headers=h, json={"start": "2026-11-17T09:00:00+07:00"})
    assert r.status_code == 200 and google.events[ev["id"]]["end"]["dateTime"] == "2026-11-17T10:00:00+07:00"

    r = cal_client.post("/internal/calendar/events", headers=h, json={"title": "Hội nghị", "start": "2026-12-01",
                                                                      "end": "2026-12-03"})
    allday = google.events[r.json()["event"]["id"]]
    assert allday["start"] == {"date": "2026-12-01"} and allday["end"] == {"date": "2026-12-04"}
    assert r.json()["event"]["end"] == "2026-12-03" and r.json()["event"]["all_day"]

    for bad in ({"title": "", "start": "2026-11-16"}, {"title": "x", "start": "tomorrow"},
                {"title": "x", "start": "2026-11-16T10:00", "end": "2026-11-16T09:00"}):
        assert cal_client.post("/internal/calendar/events", headers=h, json=bad).status_code == 400, bad

    r = cal_client.patch("/internal/calendar/events/foreign1", headers=h, json={"title": "hijack"})
    assert r.status_code == 403 and google.events["foreign1"]["summary"] == "Họp lab"
    assert cal_client.delete("/internal/calendar/events/foreign1", headers=h).status_code == 403
    assert cal_client.get("/internal/calendar/events/foreign1", headers=h).json()["event"]["title"] == "Họp lab"
    assert cal_client.delete(f"/internal/calendar/events/{ev['id']}", headers=h).json()["ok"] is True
    assert ev["id"] not in google.events
    assert cal_client.delete(f"/internal/calendar/events/{ev['id']}", headers=h).status_code == 404


def test_to_event_all_day_inclusive_end() -> None:
    ev = to_event({"id": "a", "summary": "x", "start": {"date": "2026-11-01"}, "end": {"date": "2026-11-02"}})
    assert ev["all_day"] and ev["start"] == ev["end"] == "2026-11-01" and ev["created_by_mentor"] is False


def test_account_deletion_revokes(cal_client: TestClient, google: FakeGoogle) -> None:
    me = onboard(cal_client, "ncs@example.com", "ncs")
    _connect(cal_client)
    assert cal_client.delete("/api/account").status_code == 200
    assert google.revoked == ["refresh-1"]
    with cal_client.app.state.gw.db.session() as s:
        assert s.get(GoogleCalendarLink, me["user_id"]) is None
