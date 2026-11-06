"""Per-sandbox credentials for sandbox -> gateway calls (e.g. GET /internal/papers/*).

The backend issues a fresh random token every time it starts a sandbox and passes it as
MENTOR_GATEWAY_TOKEN; the harness sends it as `Authorization: Bearer <token>`. Tokens live only in the
gateway's memory (stored as SHA-256 hashes) and are revoked when the sandbox stops. A gateway restart
forgets them, which is fine: the backends also forget their sandboxes and start new ones with new tokens.
"""

import hashlib
import secrets
from dataclasses import dataclass

from mentor_schemas import Profile


@dataclass(frozen=True)
class SandboxIdentity:
    user_id: str
    profile: Profile


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SandboxTokens:
    def __init__(self) -> None:
        self._by_digest: dict[str, SandboxIdentity] = {}
        self._digest_by_user: dict[str, str] = {}

    def issue(self, user_id: str, profile: Profile) -> str:
        """New token for a sandbox being started; replaces the user's previous one."""
        self.revoke(user_id)
        token = secrets.token_urlsafe(32)
        digest = _digest(token)
        self._by_digest[digest] = SandboxIdentity(user_id, profile)
        self._digest_by_user[user_id] = digest
        return token

    def verify(self, token: str | None) -> SandboxIdentity | None:
        if not token:
            return None
        return self._by_digest.get(_digest(token))

    def revoke(self, user_id: str) -> None:
        digest = self._digest_by_user.pop(user_id, None)
        if digest is not None:
            self._by_digest.pop(digest, None)
