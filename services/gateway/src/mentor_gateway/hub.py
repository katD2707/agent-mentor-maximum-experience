"""Client of the central Mentor hub (CONTRACTS-HUB.md section 1).

The hub is on only when `Settings.hub_url` is set. A network failure raises `HubOffline` (HTTP 503 `hub_offline`);
an error answer from the hub raises `HubError` carrying the hub's status and `{"error": code}` unchanged.
"""

from __future__ import annotations

import threading
import time

import httpx

HUB_TIMEOUT = httpx.Timeout(10.0)
SUBMIT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)  # a course pack can be tens of MB
MINE_TTL_S = 30.0


class HubError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code


class HubOffline(HubError):
    def __init__(self) -> None:
        super().__init__(503, "hub_offline")


class HubClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base = base_url.strip().rstrip("/")
        self.http = httpx.Client(timeout=HUB_TIMEOUT, transport=transport)
        self._mine: dict[str, tuple[float, dict[str, dict]]] = {}  # hub token -> (fetched at, course id -> course)
        self._lock = threading.Lock()

    def call(self, method: str, path: str, *, token: str | None = None, json: object | None = None,
             data: dict | None = None, files: dict | None = None, timeout: httpx.Timeout | None = None) -> dict | None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = self.http.request(method, self.base + path, headers=headers, json=json, data=data, files=files,
                                  timeout=timeout or HUB_TIMEOUT)
        except httpx.HTTPError as e:  # connect, timeout, protocol: the hub cannot be reached
            raise HubOffline() from e
        if r.status_code >= 400:
            try:
                code = str(r.json().get("error") or "hub_error")
            except (ValueError, AttributeError):
                code = "hub_error"
            if r.status_code >= 500 and code == "hub_error":
                raise HubOffline()
            raise HubError(r.status_code, code)
        if r.status_code == 204 or not r.content:
            return None
        try:
            body = r.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else {"data": body}

    # ------------------------------------------------------------ my courses (cached 30 s)
    def mine(self, token: str, *, fresh: bool = False) -> dict[str, dict]:
        """Hub state of the teacher's courses, by course id. Raises HubError / HubOffline."""
        now = time.monotonic()
        with self._lock:
            hit = self._mine.get(token)
        if hit and not fresh and now - hit[0] < MINE_TTL_S:
            return hit[1]
        body = self.call("GET", "/api/courses/mine", token=token) or {}
        out = {c["course_id"]: c for c in body.get("courses", []) if isinstance(c, dict) and c.get("course_id")}
        with self._lock:
            self._mine[token] = (now, out)
        return out

    def forget_mine(self, token: str | None = None) -> None:
        with self._lock:
            if token is None:
                self._mine.clear()
            else:
                self._mine.pop(token, None)
