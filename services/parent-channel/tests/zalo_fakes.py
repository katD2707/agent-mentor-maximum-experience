import json
from datetime import UTC, datetime, timedelta

import httpx
from mentor_schemas.protocols import ParentLink

TOKEN = "123456789:secret-bot-token"
BASE = "https://zalo.test"


class InMemoryStore:
    """In-memory ParentLinkStore keyed by student, as the gateway's DB table would be."""

    def __init__(self) -> None:
        self.links: dict[str, ParentLink] = {}
        self.audit: list[tuple[str, str, str]] = []

    def get_by_code(self, link_code: str) -> ParentLink | None:
        return next((link for link in self.links.values() if link.link_code == link_code), None)

    def get_by_chat(self, zalo_chat_id: str) -> ParentLink | None:
        return next((link for link in self.links.values() if link.zalo_chat_id == zalo_chat_id), None)

    def get_by_student(self, student_user_id: str) -> ParentLink | None:
        return self.links.get(student_user_id)

    def save(self, link: ParentLink) -> None:
        self.links[link.student_user_id] = link.model_copy()

    def record_audit(self, student_user_id: str, kind: str, detail: str) -> None:
        self.audit.append((student_user_id, kind, detail))


class FakeZalo:
    """httpx.MockTransport handler that records Bot API calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_with: dict | None = None
        self._n = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        prefix = f"/bot{TOKEN}/"
        assert request.url.path.startswith(prefix), request.url.path
        method = request.url.path[len(prefix) :]
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        if self.fail_with is not None:
            return httpx.Response(200, json=self.fail_with)
        self._n += 1
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": "1459", "account_name": "bot.x"}})
        if method == "sendMessage":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": f"m{self._n}", "date": 1}})
        if method == "setWebhook":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"url": body["url"], "verification": {"ok": True, "outcome": "webhook.ok"}},
                },
            )
        return httpx.Response(404, json={"ok": False, "error_code": 404, "description": "Not found"})

    def sent(self) -> list[tuple[str, str]]:
        return [(b["chat_id"], b["text"]) for m, b in self.calls if m == "sendMessage"]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def text_update(text: str, chat_id: str = "chat-1", message_id: str | None = None) -> dict:
    """Webhook body as documented at https://bot.zapps.me/docs/webhook/."""
    text_update.counter += 1  # type: ignore[attr-defined]
    return {
        "event_name": "message.text.received",
        "message": {
            "message_id": message_id or f"in-{text_update.counter}",  # type: ignore[attr-defined]
            "date": 1750316131602,
            "message_type": "CHAT_TEXT",
            "from": {"id": "u-1", "display_name": "Mẹ Lan", "is_bot": False},
            "chat": {"id": chat_id, "chat_type": "PRIVATE"},
            "text": text,
        },
    }


text_update.counter = 0  # type: ignore[attr-defined]
