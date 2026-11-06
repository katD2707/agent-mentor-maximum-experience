"""Google Calendar for NCS learners (CONTRACTS.md sections 3, 5 and 8).

Connect: OAuth 2.0 web-server flow with PKCE (S256) and a `state` that is random, single use, bound to the
learner's web session and valid for 10 minutes. Tokens (refresh and access) are stored sealed with the gateway's
SecretBox; access tokens are refreshed here, server side. Nothing token-like ever goes to a sandbox: the harness
calls /internal/calendar/* and the gateway calls Google for it.

Events the mentor creates carry `extendedProperties.private.mentorCreated = "1"`; only those can be updated or
deleted through the sandbox endpoints.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
import secrets
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import ForeignKey, String, Text, delete
from sqlalchemy.orm import Mapped, mapped_column

from mentor_gateway.crypto import DecryptError, SecretBox
from mentor_gateway.db import Base, Database, UTCDateTime
from mentor_gateway.papers import RateLimiter
from mentor_gateway.security import hash_token
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
ALLOWED_HOSTS = frozenset({"oauth2.googleapis.com", "www.googleapis.com"})
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
SCOPES = ("openid", "email", CALENDAR_SCOPE)
STATE_MINUTES = 10
MARKER_KEY = "mentorCreated"
LOCAL_TZ_NAME = "Asia/Ho_Chi_Minh"
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)
DEFAULT_WINDOW_DAYS = 14
MAX_WINDOW_DAYS = 60
MAX_EVENTS = 50
LIST_DESCRIPTION_CHARS = 300
GET_DESCRIPTION_CHARS = 2000
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 4000
MAX_LOCATION_CHARS = 300
MAX_EVENT_DAYS = 31
MAX_RESPONSE_BYTES = 2_000_000
ACCESS_MARGIN = timedelta(seconds=60)
_EVENT_ID = re.compile(r"^[A-Za-z0-9_\-@.]{1,1024}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG = re.compile(r"<[^>]{0,500}>")


# ---- storage ------------------------------------------------------------------------------------


class GoogleCalendarLink(Base):
    """One connected Google account per learner. Token columns hold SecretBox blobs, never plaintext."""

    __tablename__ = "google_calendar_links"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text)  # sealed, aad gcal-refresh:<user_id>
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # sealed, aad gcal-access:<user_id>
    access_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime)


class OAuthState(Base):
    """Pending authorization: hashed `state`, the session it belongs to and the sealed PKCE verifier."""

    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    code_verifier: Mapped[str] = mapped_column(Text)  # sealed, aad oauth-verifier:<state_hash>
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


# ---- errors and helpers -------------------------------------------------------------------------


class CalendarError(Exception):
    """`status` is the HTTP status the endpoint returns; `reason` a short machine code for redirects."""

    def __init__(self, status: int, message: str, reason: str = "error") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


class NotConnected(CalendarError):
    def __init__(self) -> None:
        super().__init__(409, "google calendar not connected", "not_connected")


def _clean(text: Any, limit: int | None = None, *, html: bool = False) -> str:
    raw = str(text or "")
    if html:
        raw = _TAG.sub(" ", raw.replace("<br>", "\n").replace("<br/>", "\n"))
    raw = _CONTROL.sub("", unicodedata.normalize("NFC", raw))
    raw = "\n".join(" ".join(line.split()) for line in raw.splitlines()).strip()
    if limit is not None and len(raw) > limit:
        raw = raw[: limit - 1].rstrip() + "…"
    return raw


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _id_token_claims(id_token: str | None) -> dict[str, Any]:
    """Claims of an ID token received directly from Google's token endpoint over TLS (no signature check needed)."""
    if not id_token or id_token.count(".") != 2:
        return {}
    payload = id_token.split(".")[1]
    try:
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return {}


def parse_when(raw: str, field: str) -> date | datetime:
    """`YYYY-MM-DD` -> date (all-day); ISO datetime -> aware datetime (naive = Asia/Ho_Chi_Minh)."""
    value = (raw or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CalendarError(400, f"{field}: invalid date {value!r}") from exc
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CalendarError(400, f"{field}: use ISO 8601, e.g. 2026-11-04T19:00:00+07:00 or 2026-11-04") from exc
    return dt.replace(tzinfo=LOCAL_TZ) if dt.tzinfo is None else dt


def _event_times(start: date | datetime, end: date | datetime | None,
                 default_duration: timedelta) -> tuple[dict[str, str], dict[str, str]]:
    """Google start/end objects. All-day `end` is the last day (inclusive) and becomes Google's exclusive end."""
    if isinstance(start, datetime):
        if end is not None and not isinstance(end, datetime):
            raise CalendarError(400, "end must be a datetime when start is a datetime")
        end_dt = end if isinstance(end, datetime) else start + default_duration
        if end_dt <= start:
            raise CalendarError(400, "end must be after start")
        if end_dt - start > timedelta(days=MAX_EVENT_DAYS):
            raise CalendarError(400, f"events longer than {MAX_EVENT_DAYS} days are not allowed")
        return ({"dateTime": start.isoformat(), "timeZone": LOCAL_TZ_NAME},
                {"dateTime": end_dt.isoformat(), "timeZone": LOCAL_TZ_NAME})
    if isinstance(end, datetime):
        raise CalendarError(400, "end must be a date (YYYY-MM-DD) when start is a date")
    last = end or start
    if last < start:
        raise CalendarError(400, "end must not be before start")
    if (last - start).days >= MAX_EVENT_DAYS:
        raise CalendarError(400, f"events longer than {MAX_EVENT_DAYS} days are not allowed")
    return {"date": start.isoformat()}, {"date": (last + timedelta(days=1)).isoformat()}


def _is_day(value: date | datetime | None) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _parse_google_time(obj: dict[str, Any]) -> date | datetime | None:
    if obj.get("dateTime"):
        return datetime.fromisoformat(obj["dateTime"])
    if obj.get("date"):
        return date.fromisoformat(obj["date"])
    return None


def is_mentor_event(item: dict[str, Any]) -> bool:
    private = (item.get("extendedProperties") or {}).get("private") or {}
    return private.get(MARKER_KEY) == "1"


def to_event(item: dict[str, Any], description_chars: int = LIST_DESCRIPTION_CHARS) -> dict[str, Any]:
    start, end = item.get("start") or {}, item.get("end") or {}
    all_day = bool(start.get("date")) and not start.get("dateTime")
    end_value = end.get("dateTime") or end.get("date")
    if all_day and end.get("date"):  # back to an inclusive last day
        end_value = (date.fromisoformat(end["date"]) - timedelta(days=1)).isoformat()
    return {
        "id": item.get("id"),
        "title": _clean(item.get("summary"), MAX_TITLE_CHARS) or "(không có tiêu đề)",
        "start": start.get("dateTime") or start.get("date"),
        "end": end_value,
        "all_day": all_day,
        "location": _clean(item.get("location"), MAX_LOCATION_CHARS) or None,
        "description": _clean(item.get("description"), description_chars, html=True) or None,
        "created_by_mentor": is_mentor_event(item),
    }


def check_event_id(event_id: str) -> str:
    if not _EVENT_ID.match(event_id or ""):
        raise CalendarError(400, "invalid event id")
    return event_id


# ---- service ------------------------------------------------------------------------------------


class GoogleCalendar:
    def __init__(
        self,
        db: Database,
        box: SecretBox,
        settings: Settings,
        clock: Clock,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.db = db
        self.box = box
        self.settings = settings
        self.clock = clock
        self.transport = transport
        self.timeout_s = timeout_s
        self._locks: dict[str, asyncio.Lock] = {}
        self.limiter = RateLimiter(settings.calendar_requests_per_minute)  # per learner, /internal/calendar/*

    @property
    def available(self) -> bool:
        return bool(self.settings.google_oauth_client_id and self.settings.google_oauth_client_secret)

    @property
    def redirect_uri(self) -> str:
        return self.settings.google_redirect_uri

    # -- connect --

    def authorization_url(self, user_id: str, session_token: str) -> str:
        if not self.available:
            raise CalendarError(503, "google calendar is not configured", "unavailable")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        state_hash = hash_token(state)
        now = self.clock()
        with self.db.session() as s:
            s.execute(delete(OAuthState).where(OAuthState.expires_at <= now))
            s.execute(delete(OAuthState).where(OAuthState.user_id == user_id))  # one pending connect per learner
            s.add(OAuthState(state_hash=state_hash, user_id=user_id, session_hash=hash_token(session_token),
                             provider="google_calendar",
                             code_verifier=self.box.seal_str(verifier, aad=f"oauth-verifier:{state_hash}"),
                             expires_at=now + timedelta(minutes=STATE_MINUTES)))
        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "access_type": "offline",  # we need a refresh token
            "prompt": "consent",  # ... every time, also on reconnect
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def consume_state(self, state: str, user_id: str, session_token: str) -> str:
        """Consume the state (single use) and return the PKCE verifier."""
        state_hash = hash_token(state)
        with self.db.session() as s:
            row = s.get(OAuthState, state_hash)
            if row is not None:
                s.delete(row)
        if row is None or row.expires_at <= self.clock():
            raise CalendarError(400, "unknown or expired state", "state")
        if row.user_id != user_id or not secrets.compare_digest(row.session_hash, hash_token(session_token)):
            raise CalendarError(400, "state belongs to another session", "state")
        return self.box.unseal_str(row.code_verifier, aad=f"oauth-verifier:{state_hash}")

    async def finish(self, user_id: str, session_token: str, state: str, code: str) -> dict[str, Any]:
        verifier = self.consume_state(state, user_id, session_token)
        status, data = await self._request("POST", TOKEN_URL, data={
            "code": code,
            "client_id": self.settings.google_oauth_client_id,
            "client_secret": self.settings.google_oauth_client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        })
        if status != 200 or not data.get("access_token"):
            log.warning("google token exchange failed: %s %s", status, data.get("error"))
            raise CalendarError(502, "token exchange failed", "exchange")
        scopes = str(data.get("scope") or "").split()
        refresh = data.get("refresh_token")
        if CALENDAR_SCOPE not in scopes or not refresh:
            await self._revoke(refresh or data["access_token"])
            raise CalendarError(400, "calendar permission not granted", "scope")
        claims = _id_token_claims(data.get("id_token"))
        email = claims.get("email") if claims.get("aud") == self.settings.google_oauth_client_id else None
        now = self.clock()
        with self.db.session() as s:
            link = s.get(GoogleCalendarLink, user_id) or GoogleCalendarLink(user_id=user_id)
            link.email = str(email)[:320] if email else None
            link.scopes = " ".join(scopes)
            link.refresh_token = self.box.seal_str(refresh, aad=f"gcal-refresh:{user_id}")
            link.access_token = self.box.seal_str(data["access_token"], aad=f"gcal-access:{user_id}")
            link.access_expires_at = now + timedelta(seconds=int(data.get("expires_in") or 3600))
            link.connected_at = now
            s.merge(link)
        return self.status(user_id)

    def status(self, user_id: str) -> dict[str, Any]:
        with self.db.session() as s:
            link = s.get(GoogleCalendarLink, user_id)
        if link is None:
            return {"available": self.available, "connected": False, "email": None, "scopes": []}
        return {"available": self.available, "connected": True, "email": link.email, "scopes": link.scopes.split()}

    async def disconnect(self, user_id: str) -> bool:
        """Revoke at Google (best effort) and forget the tokens. False if nothing was connected."""
        with self.db.session() as s:
            link = s.get(GoogleCalendarLink, user_id)
            s.execute(delete(GoogleCalendarLink).where(GoogleCalendarLink.user_id == user_id))
            s.execute(delete(OAuthState).where(OAuthState.user_id == user_id))
        if link is None:
            return False
        try:
            await self._revoke(self.box.unseal_str(link.refresh_token, aad=f"gcal-refresh:{user_id}"))
        except DecryptError:
            log.warning("could not unseal the refresh token of %s; deleted without revoking", user_id)
        return True

    async def _revoke(self, token: str) -> None:
        try:
            status, _ = await self._request("POST", REVOKE_URL, data={"token": token})
            if status not in (200, 400):  # 400: already invalid
                log.warning("google revoke returned %s", status)
        except CalendarError as exc:
            log.warning("google revoke failed: %s", exc)

    # -- access tokens --

    async def _access_token(self, user_id: str, *, force_refresh: bool = False) -> str:
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            with self.db.session() as s:
                link = s.get(GoogleCalendarLink, user_id)
            if link is None:
                raise NotConnected()
            try:
                if (not force_refresh and link.access_token and link.access_expires_at
                        and link.access_expires_at - ACCESS_MARGIN > self.clock()):
                    return self.box.unseal_str(link.access_token, aad=f"gcal-access:{user_id}")
                refresh = self.box.unseal_str(link.refresh_token, aad=f"gcal-refresh:{user_id}")
            except DecryptError as exc:
                log.error("calendar tokens of %s cannot be decrypted (master key changed?)", user_id)
                raise NotConnected() from exc
            status, data = await self._request("POST", TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
            })
            if status in (400, 401) and data.get("error") in ("invalid_grant", "unauthorized_client"):
                with self.db.session() as s:  # revoked or expired at Google: the learner must reconnect
                    s.execute(delete(GoogleCalendarLink).where(GoogleCalendarLink.user_id == user_id))
                raise NotConnected()
            if status != 200 or not data.get("access_token"):
                raise CalendarError(502, f"google token refresh failed (HTTP {status})")
            with self.db.session() as s:
                row = s.get(GoogleCalendarLink, user_id)
                if row is not None:
                    row.access_token = self.box.seal_str(data["access_token"], aad=f"gcal-access:{user_id}")
                    row.access_expires_at = self.clock() + timedelta(seconds=int(data.get("expires_in") or 3600))
                    if data.get("refresh_token"):
                        row.refresh_token = self.box.seal_str(data["refresh_token"], aad=f"gcal-refresh:{user_id}")
            return data["access_token"]

    async def _api(self, user_id: str, method: str, url: str, *, params: dict[str, Any] | None = None,
                   body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        token = await self._access_token(user_id)
        status, data = await self._request(method, url, params=params, json_body=body, bearer=token)
        if status == 401:  # expired early or revoked: refresh once
            token = await self._access_token(user_id, force_refresh=True)
            status, data = await self._request(method, url, params=params, json_body=body, bearer=token)
        if status == 401:
            raise NotConnected()
        if status in (404, 410):
            raise CalendarError(404, "event not found", "not_found")
        if status == 429 or (status == 403 and "limit" in json.dumps(data).lower()):
            raise CalendarError(503, "google calendar is rate limiting; try again later", "rate_limited")
        if status == 403:
            raise CalendarError(502, "google calendar denied the request", "forbidden")
        if status == 400:
            msg = str(((data.get("error") or {}) if isinstance(data.get("error"), dict) else {}).get("message") or "")
            raise CalendarError(400, f"google calendar rejected the request: {msg[:200]}")
        if status >= 300:
            raise CalendarError(502, f"google calendar returned HTTP {status}")
        return status, data

    # -- events --

    def window(self, start: str | None, end: str | None) -> tuple[datetime, datetime]:
        def bound(raw: str, field: str) -> datetime:
            value = parse_when(raw, field)
            if isinstance(value, datetime):
                return value
            day = value + timedelta(days=1) if field == "end" else value  # a date end includes that whole day
            return datetime.combine(day, time.min, LOCAL_TZ)

        t0 = bound(start, "start") if start else self.clock().astimezone(LOCAL_TZ)
        t1 = bound(end, "end") if end else t0 + timedelta(days=DEFAULT_WINDOW_DAYS)
        if t1 <= t0:
            raise CalendarError(400, "end must be after start")
        if t1 - t0 > timedelta(days=MAX_WINDOW_DAYS):
            raise CalendarError(400, f"window longer than {MAX_WINDOW_DAYS} days")
        return t0, t1

    async def list_events(self, user_id: str, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        t0, t1 = self.window(start, end)
        _, data = await self._api(user_id, "GET", EVENTS_URL, params={
            "timeMin": t0.isoformat(), "timeMax": t1.isoformat(), "singleEvents": "true", "orderBy": "startTime",
            "maxResults": str(MAX_EVENTS), "timeZone": LOCAL_TZ_NAME,
        })
        items = [i for i in data.get("items") or [] if isinstance(i, dict) and i.get("status") != "cancelled"]
        return {
            "start": t0.isoformat(), "end": t1.isoformat(), "time_zone": LOCAL_TZ_NAME,
            "events": [to_event(i) for i in items[:MAX_EVENTS]],
            "truncated": bool(data.get("nextPageToken")) or len(items) > MAX_EVENTS,
        }

    async def _get_raw(self, user_id: str, event_id: str) -> dict[str, Any]:
        _, data = await self._api(user_id, "GET", f"{EVENTS_URL}/{quote(check_event_id(event_id), safe='')}",
                                  params={"timeZone": LOCAL_TZ_NAME})
        if data.get("status") == "cancelled":
            raise CalendarError(404, "event not found", "not_found")
        return data

    async def _get_own(self, user_id: str, event_id: str) -> dict[str, Any]:
        item = await self._get_raw(user_id, event_id)
        if not is_mentor_event(item):
            raise CalendarError(403, "only events created by the mentor can be changed", "not_mentor_event")
        return item

    async def get_event(self, user_id: str, event_id: str) -> dict[str, Any]:
        return to_event(await self._get_raw(user_id, event_id), GET_DESCRIPTION_CHARS)

    async def create_event(self, user_id: str, *, title: str, start: str, end: str | None = None,
                           description: str | None = None, location: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"summary": _text(title, MAX_TITLE_CHARS, "title", required=True)}
        body["start"], body["end"] = _event_times(parse_when(start, "start"),
                                                  parse_when(end, "end") if end else None, timedelta(hours=1))
        if description:
            body["description"] = _text(description, MAX_DESCRIPTION_CHARS, "description")
        if location:
            body["location"] = _text(location, MAX_LOCATION_CHARS, "location")
        body["extendedProperties"] = {"private": {MARKER_KEY: "1"}}
        _, data = await self._api(user_id, "POST", EVENTS_URL, body=body)
        return to_event(data, GET_DESCRIPTION_CHARS)

    async def update_event(self, user_id: str, event_id: str, *, title: str | None = None, start: str | None = None,
                           end: str | None = None, description: str | None = None,
                           location: str | None = None) -> dict[str, Any]:
        current = await self._get_own(user_id, event_id)
        patch: dict[str, Any] = {}
        if title is not None:
            patch["summary"] = _text(title, MAX_TITLE_CHARS, "title", required=True)
        if description is not None:
            patch["description"] = _text(description, MAX_DESCRIPTION_CHARS, "description")
        if location is not None:
            patch["location"] = _text(location, MAX_LOCATION_CHARS, "location")
        if start is not None or end is not None:
            old_start = _parse_google_time(current.get("start") or {})
            old_end = _parse_google_time(current.get("end") or {})
            new_start = parse_when(start, "start") if start else old_start
            if new_start is None:
                raise CalendarError(400, "event has no start; give start")
            new_end: date | datetime | None = None  # default: 1 hour / a single day
            if end:
                new_end = parse_when(end, "end")
            elif old_start is not None and old_end is not None and _is_day(new_start) == _is_day(old_start):
                # only start moved: keep the duration (all-day: Google's end is exclusive, ours inclusive)
                new_end = new_start + (old_end - old_start) - (timedelta(days=1) if _is_day(new_start) else timedelta())
            patch["start"], patch["end"] = _event_times(new_start, new_end, timedelta(hours=1))
        if not patch:
            raise CalendarError(400, "nothing to change")
        _, data = await self._api(user_id, "PATCH", f"{EVENTS_URL}/{quote(event_id, safe='')}", body=patch)
        return to_event(data, GET_DESCRIPTION_CHARS)

    async def delete_event(self, user_id: str, event_id: str) -> dict[str, Any]:
        item = await self._get_own(user_id, event_id)
        try:
            await self._api(user_id, "DELETE", f"{EVENTS_URL}/{quote(event_id, safe='')}")
        except CalendarError as exc:
            if exc.status != 404:
                raise
        return to_event(item)

    # -- HTTP --

    async def _request(self, method: str, url: str, *, data: dict[str, str] | None = None,
                       params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None,
                       bearer: str | None = None) -> tuple[int, dict[str, Any]]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
            raise CalendarError(500, f"host not allowed: {parts.hostname}")
        headers = {"Accept": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            async with (
                httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s, follow_redirects=False) as client,
                client.stream(method, url, data=data, params=params, json=json_body, headers=headers) as resp,
            ):
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise CalendarError(502, "google response too large")
                    chunks.append(chunk)
                status = resp.status_code
        except httpx.TimeoutException as exc:
            raise CalendarError(504, "google timed out", "timeout") from exc
        except httpx.HTTPError as exc:
            raise CalendarError(502, f"google unreachable: {exc.__class__.__name__}", "unreachable") from exc
        raw = b"".join(chunks)
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {}
        return status, parsed if isinstance(parsed, dict) else {}


def _text(value: str, limit: int, field: str, *, required: bool = False) -> str:
    text = _CONTROL.sub("", unicodedata.normalize("NFC", str(value))).strip()
    if required and not text:
        raise CalendarError(400, f"{field} must not be empty")
    if len(text) > limit:
        raise CalendarError(400, f"{field} longer than {limit} characters")
    return text
