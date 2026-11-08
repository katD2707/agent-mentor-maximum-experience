"""Master-key rotation: re-wrap everything sealed with MENTOR_MASTER_KEY under a new key, in one DB transaction.

Re-wrapped: user data keys (backups themselves need no re-encryption: their data keys do not change) and Web Push
subscriptions (+ blind indexes, which derive from the master key). Local ops.db snapshots are re-encrypted by the
CLI afterwards.
Run with the gateway stopped.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from mentor_gateway.crypto import SecretBox
from mentor_gateway.datakeys import b64d, b64e, user_key_aad
from mentor_gateway.db import Database, UserDataKey

Rotator = Callable[[Session, SecretBox, SecretBox], int]


def _user_keys(s: Session, old: SecretBox, new: SecretBox) -> int:
    rows = s.scalars(select(UserDataKey)).all()
    for r in rows:
        aad = user_key_aad(r.user_id)
        r.sealed_key = b64e(new.seal(old.unseal(b64d(r.sealed_key), aad=aad), aad=aad))
    return len(rows)


def _push(s: Session, old: SecretBox, new: SecretBox) -> int:
    from mentor_gateway.push import rotate_subscriptions

    return rotate_subscriptions(s, old, new)


# A new sealed column must be added here, or rotation leaves it unreadable.
ROTATORS: dict[str, Rotator] = {
    "user_keys": _user_keys,
    "push_subscriptions": _push,
}


def rotate_master_key(db: Database, old: SecretBox, new: SecretBox) -> dict[str, int]:
    """All-or-nothing: any row that does not open with the old key aborts the whole rotation."""
    with db.session() as s:
        return {name: fn(s, old, new) for name, fn in ROTATORS.items()}
