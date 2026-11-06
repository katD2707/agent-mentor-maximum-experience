"""Master-key rotation: re-wrap everything sealed with MENTOR_MASTER_KEY under a new key, in one DB transaction.

Re-wrapped: user data keys (backups themselves need no re-encryption: their data keys do not change), parent
contacts and Web Push subscriptions (+ blind indexes, which derive from the master key), audit details, Google
Calendar tokens. Pending OAuth states (10-minute lifetime) are dropped. Local ops.db snapshots are re-encrypted by the CLI afterwards.
Run with the gateway stopped.
"""

from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mentor_gateway.crypto import SecretBox
from mentor_gateway.datakeys import b64d, b64e, user_key_aad
from mentor_gateway.db import AuditRow, Database, ParentContact, UserDataKey
from mentor_gateway.parent import AUDIT_PREFIX, ZALO_CHAT_BIDX, audit_aad, zalo_chat_aad

Rotator = Callable[[Session, SecretBox, SecretBox], int]


def _user_keys(s: Session, old: SecretBox, new: SecretBox) -> int:
    rows = s.scalars(select(UserDataKey)).all()
    for r in rows:
        aad = user_key_aad(r.user_id)
        r.sealed_key = b64e(new.seal(old.unseal(b64d(r.sealed_key), aad=aad), aad=aad))
    return len(rows)


def _parent_contacts(s: Session, old: SecretBox, new: SecretBox) -> int:
    rows = s.scalars(select(ParentContact)).all()
    for r in rows:
        aad = zalo_chat_aad(r.student_user_id)
        chat = old.unseal_str(r.zalo_chat_enc, aad=aad)
        r.zalo_chat_enc = new.seal_str(chat, aad=aad)
        r.zalo_chat_bidx = new.blind_index(chat, purpose=ZALO_CHAT_BIDX)
    return len(rows)


def _audit(s: Session, old: SecretBox, new: SecretBox) -> int:
    rows = s.scalars(select(AuditRow).where(AuditRow.detail.startswith(AUDIT_PREFIX))).all()
    for r in rows:
        aad = audit_aad(r.student_user_id, r.kind)
        text = old.unseal_str(r.detail[len(AUDIT_PREFIX):], aad=aad)
        r.detail = AUDIT_PREFIX + new.seal_str(text, aad=aad)
    return len(rows)


def _gcal(s: Session, old: SecretBox, new: SecretBox) -> int:
    try:
        from mentor_gateway.gcal import GoogleCalendarLink, OAuthState
    except ImportError:
        return 0
    s.execute(delete(OAuthState))
    rows = s.scalars(select(GoogleCalendarLink)).all()
    for r in rows:
        r.refresh_token = new.seal_str(old.unseal_str(r.refresh_token, aad=f"gcal-refresh:{r.user_id}"),
                                       aad=f"gcal-refresh:{r.user_id}")
        if r.access_token:
            r.access_token = new.seal_str(old.unseal_str(r.access_token, aad=f"gcal-access:{r.user_id}"),
                                          aad=f"gcal-access:{r.user_id}")
    return len(rows)


def _push(s: Session, old: SecretBox, new: SecretBox) -> int:
    from mentor_gateway.push import rotate_subscriptions

    return rotate_subscriptions(s, old, new)


# A new sealed column must be added here, or rotation leaves it unreadable.
ROTATORS: dict[str, Rotator] = {
    "user_keys": _user_keys,
    "parent_contacts": _parent_contacts,
    "audit_log": _audit,
    "google_calendar_links": _gcal,
    "push_subscriptions": _push,
}


def rotate_master_key(db: Database, old: SecretBox, new: SecretBox) -> dict[str, int]:
    """All-or-nothing: any row that does not open with the old key aborts the whole rotation."""
    with db.session() as s:
        return {name: fn(s, old, new) for name, fn in ROTATORS.items()}
