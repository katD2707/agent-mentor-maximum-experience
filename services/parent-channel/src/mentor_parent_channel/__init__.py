"""Zalo Bot parent channel: link a parent to a THPT student, collect consent, send reports and
crisis alerts. A library: the gateway (services/gateway) owns the store and mounts the webhook router.
See CONTRACTS.md section 6.
"""

from mentor_parent_channel import messages
from mentor_parent_channel.client import (
    DEFAULT_BASE_URL,
    BotInfo,
    ZaloApiError,
    ZaloBadRequestError,
    ZaloBotClient,
    ZaloError,
    ZaloNetworkError,
    ZaloNotFoundError,
    ZaloQuotaExceededError,
    ZaloRequestTimeoutError,
    ZaloUnauthorizedError,
)
from mentor_parent_channel.service import (
    MessageSender,
    ParentLinkError,
    ParentLinkService,
    find_forbidden,
    find_leaks,
    is_consent_reply,
)
from mentor_parent_channel.text import MAX_MESSAGE_CHARS, markdown_to_plain, split_text
from mentor_parent_channel.webhook import SECRET_HEADER, WEBHOOK_PATH, create_webhook_router

__all__ = [
    "DEFAULT_BASE_URL",
    "MAX_MESSAGE_CHARS",
    "SECRET_HEADER",
    "WEBHOOK_PATH",
    "BotInfo",
    "MessageSender",
    "ParentLinkError",
    "ParentLinkService",
    "ZaloApiError",
    "ZaloBadRequestError",
    "ZaloBotClient",
    "ZaloError",
    "ZaloNetworkError",
    "ZaloNotFoundError",
    "ZaloQuotaExceededError",
    "ZaloRequestTimeoutError",
    "ZaloUnauthorizedError",
    "create_webhook_router",
    "find_forbidden",
    "find_leaks",
    "is_consent_reply",
    "markdown_to_plain",
    "messages",
    "split_text",
]
