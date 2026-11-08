"""Authenticated encryption for secrets the gateway keeps at rest (OAuth tokens, parent contacts, backups).

AES-256-GCM. A sealed blob is b"v1" + 12-byte nonce + ciphertext||tag. `aad` binds a blob to its purpose and owner
(e.g. "push-sub:<user_id>"), so a blob copied into another row or user fails to open.

The master key comes from MENTOR_MASTER_KEY (urlsafe base64 of 32 bytes). In dev/test, if it is unset, a key is
generated once at $MENTOR_DATA_DIR/master.key. Outside dev/test a missing key is an error.
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

_VERSION = b"v1"
_NONCE = 12


class DecryptError(ValueError):
    pass


class SecretBox:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("master key must be 32 bytes")
        self._key = key
        self._aead = AESGCM(key)
        self._bidx_key = self.subkey("blind-index")

    def seal(self, plaintext: bytes, *, aad: str) -> bytes:
        nonce = secrets.token_bytes(_NONCE)
        return _VERSION + nonce + self._aead.encrypt(nonce, plaintext, aad.encode())

    def unseal(self, blob: bytes, *, aad: str) -> bytes:
        if not blob.startswith(_VERSION) or len(blob) < len(_VERSION) + _NONCE + 16:
            raise DecryptError("not a sealed blob")
        nonce = blob[len(_VERSION):len(_VERSION) + _NONCE]
        try:
            return self._aead.decrypt(nonce, blob[len(_VERSION) + _NONCE:], aad.encode())
        except InvalidTag as exc:
            raise DecryptError("wrong key, wrong aad or tampered blob") from exc

    def seal_str(self, text: str, *, aad: str) -> str:
        return base64.urlsafe_b64encode(self.seal(text.encode(), aad=aad)).decode()

    def unseal_str(self, token: str, *, aad: str) -> str:
        return self.unseal(base64.urlsafe_b64decode(token.encode()), aad=aad).decode()

    def subkey(self, purpose: str) -> bytes:
        """A 32-byte key derived from the master key (HKDF-SHA256, info = "mentor:<purpose>")."""
        return derive_key(self._key, f"mentor:{purpose}")

    def blind_index(self, value: str, *, purpose: str) -> str:
        """Deterministic HMAC-SHA256 of `value` (hex) for equality lookups on an encrypted column.

        `purpose` (e.g. "push-endpoint") separates indexes so equal values in different columns do not match.
        Changes when the master key rotates (re-index on rotation).
        """
        msg = purpose.encode() + b"\x00" + value.encode()
        return hmac.new(self._bidx_key, msg, hashlib.sha256).hexdigest()


def derive_key(key: bytes, info: str, salt: bytes | None = None) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info.encode()).derive(key)


def load_master_key(env: str, data_dir: Path) -> bytes:
    raw = os.environ.get("MENTOR_MASTER_KEY", "").strip()
    if raw:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(key) != 32:
            raise ValueError("MENTOR_MASTER_KEY must decode to 32 bytes")
        return key
    if env not in ("dev", "test"):
        raise RuntimeError("MENTOR_MASTER_KEY is required outside dev/test")
    path = data_dir / "master.key"
    if path.is_file():
        return base64.urlsafe_b64decode(path.read_text().strip())
    data_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_text(base64.urlsafe_b64encode(key).decode())
    log.warning("generated a dev master key at %s; set MENTOR_MASTER_KEY in production", path)
    return key
