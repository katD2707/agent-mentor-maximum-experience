"""Token helpers. Only hashes of bearer tokens are stored in the ops DB."""

import hashlib
import secrets
import string

_CODE_ALPHABET = string.ascii_lowercase + string.digits


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_id(prefix: str = "") -> str:
    return prefix + secrets.token_hex(8)


def random_code(length: int = 10) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
