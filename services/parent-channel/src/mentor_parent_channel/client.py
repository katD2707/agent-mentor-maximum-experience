"""Minimal synchronous client for the Zalo Bot API (https://bot.zapps.me/docs/).

Every method is `POST https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>` with a JSON body. Responses
are `{"ok": bool, "result": ..., "description": str, "error_code": int}`. The token is part of the URL, so
it is never put into exception messages or reprs.
"""

import logging
from typing import Any, Self

import httpx
from pydantic import BaseModel, ConfigDict

from mentor_parent_channel.text import MAX_MESSAGE_CHARS, split_text

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://bot-api.zaloplatforms.com"
SECRET_TOKEN_MIN = 8
SECRET_TOKEN_MAX = 256


class ZaloError(Exception):
    """Base class for everything the client raises."""


class ZaloNetworkError(ZaloError):
    """Transport failure, timeout, or a response that is not the documented JSON envelope."""


class ZaloApiError(ZaloError):
    """Zalo answered with `ok: false` (or an HTTP error carrying an error_code)."""

    def __init__(self, method: str, error_code: int, description: str) -> None:
        self.method = method
        self.error_code = error_code
        self.description = description
        super().__init__(f"Zalo {method} failed: {error_code} {description}".strip())


class ZaloBadRequestError(ZaloApiError):
    """400: wrong path or invalid parameters."""


class ZaloUnauthorizedError(ZaloApiError):
    """401: token expired or invalid."""


class ZaloNotFoundError(ZaloApiError):
    """404: e.g. unknown chat_id."""


class ZaloRequestTimeoutError(ZaloApiError):
    """408: Zalo took too long to process the request."""


class ZaloQuotaExceededError(ZaloApiError):
    """429: API quota exceeded."""


_ERRORS: dict[int, type[ZaloApiError]] = {
    400: ZaloBadRequestError,
    401: ZaloUnauthorizedError,
    404: ZaloNotFoundError,
    408: ZaloRequestTimeoutError,
    429: ZaloQuotaExceededError,
}


class BotInfo(BaseModel):
    """Result of getMe."""

    model_config = ConfigDict(extra="allow")

    id: str
    account_name: str | None = None
    account_type: str | None = None
    can_join_groups: bool | None = None


class ZaloBotClient:
    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not token:
            raise ValueError("Zalo bot token is required")
        self._token = token
        self._http = httpx.Client(base_url=base_url.rstrip("/"), transport=transport, timeout=timeout)

    def __repr__(self) -> str:
        return f"ZaloBotClient(base_url={str(self._http.base_url)!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        """Call any Bot API method and return its `result`, raising a typed ZaloError otherwise."""
        try:
            response = self._http.post(f"/bot{self._token}/{method}", json=payload or {})
        except httpx.HTTPError as exc:
            # `from None`: the chained exception would carry the URL, which contains the token.
            raise ZaloNetworkError(f"Zalo {method}: {type(exc).__name__}") from None
        try:
            data = response.json()
        except ValueError:
            raise ZaloNetworkError(f"Zalo {method}: HTTP {response.status_code} with a non-JSON body") from None
        if not isinstance(data, dict):
            raise ZaloNetworkError(f"Zalo {method}: unexpected response shape")
        if data.get("ok") is True:
            return data.get("result")
        code = data.get("error_code")
        if not isinstance(code, int):
            code = response.status_code
        description = str(data.get("description") or "")
        raise _ERRORS.get(code, ZaloApiError)(method, code, description)

    def get_me(self) -> BotInfo:
        return BotInfo.model_validate(self.call("getMe"))

    def send_message(self, chat_id: str, text: str) -> list[str]:
        """Send plain text, split into ≤2,000-char messages at paragraph/line boundaries.

        Returns the Zalo message ids in order. If a later chunk fails, earlier chunks stay delivered and
        the error is raised.
        """
        chunks = split_text(text, MAX_MESSAGE_CHARS)
        if not chunks:
            raise ValueError("message text is empty")
        ids: list[str] = []
        for chunk in chunks:
            result = self.call("sendMessage", {"chat_id": chat_id, "text": chunk}) or {}
            ids.append(str(result.get("message_id", "")))
        return ids

    def set_webhook(self, url: str, secret_token: str) -> dict[str, Any]:
        """Register the webhook. Zalo sends `secret_token` back in the `X-Bot-Api-Secret-Token` header.

        The URL must be public HTTPS (Zalo rejects localhost and private IPs). Zalo saves the URL even if its
        verification request fails; inspect `result["verification"]["ok"]`.
        """
        if not SECRET_TOKEN_MIN <= len(secret_token) <= SECRET_TOKEN_MAX:
            raise ValueError(f"secret_token must be {SECRET_TOKEN_MIN}-{SECRET_TOKEN_MAX} characters")
        return self.call("setWebhook", {"url": url, "secret_token": secret_token}) or {}

    def delete_webhook(self) -> Any:
        return self.call("deleteWebhook")

    def get_webhook_info(self) -> Any:
        return self.call("getWebhookInfo")
