"""Per-user data keys (crypto-shredding).

Key hierarchy:
    MENTOR_MASTER_KEY (secret manager)
      ├─ seals each user's random 32-byte data key   -> ops DB `user_keys` (aad "user-key:<user_id>")
      │    └─ HKDF per file -> that user's backup snapshots (backup.py)
      ├─ seals sensitive columns directly            -> audit_log.detail, push subscriptions
      ├─ HKDF "mentor:blind-index" -> HMAC blind indexes for equality lookups on sealed columns
      └─ HKDF "mentor:ops-backup"  -> ops.db snapshots

Deleting a user's `user_keys` row makes every backup of that user unreadable, wherever the files were copied.
"""

import base64
import secrets

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from mentor_gateway.crypto import SecretBox
from mentor_gateway.db import Database, UserDataKey
from mentor_gateway.settings import Clock


def user_key_aad(user_id: str) -> str:
    return f"user-key:{user_id}"


class UserKeyStore:
    def __init__(self, db: Database, box: SecretBox, clock: Clock) -> None:
        self.db = db
        self.box = box
        self.clock = clock

    def get(self, user_id: str) -> bytes | None:
        with self.db.session() as s:
            row = s.get(UserDataKey, user_id)
            return None if row is None else self.box.unseal(b64d(row.sealed_key), aad=user_key_aad(user_id))

    def get_or_create(self, user_id: str) -> bytes:
        key = self.get(user_id)
        if key is not None:
            return key
        key = secrets.token_bytes(32)
        try:
            with self.db.session() as s:
                s.add(UserDataKey(user_id=user_id, sealed_key=b64e(self.box.seal(key, aad=user_key_aad(user_id))),
                                  created_at=self.clock()))
        except IntegrityError:  # created concurrently
            existing = self.get(user_id)
            assert existing is not None
            return existing
        return key

    def delete(self, user_id: str) -> bool:
        with self.db.session() as s:
            n = s.execute(delete(UserDataKey).where(UserDataKey.user_id == user_id)).rowcount
        if self.db.engine.dialect.name == "sqlite":
            # secure_delete zeroes the page; checkpoint so the old page does not linger in the WAL file either
            with self.db.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        return bool(n)


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode()


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode())
