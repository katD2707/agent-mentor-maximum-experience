"""Web Push (VAPID) for nudges when the learner has no open WebSocket (CONTRACTS section 9).

- Off unless `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` are all set.
- A subscription (endpoint URL + keys) is personal data: sealed with the master key (`SecretBox`, aad
  "push-sub:<user_id>:<bidx>"); an HMAC blind index of the endpoint finds duplicates without decrypting.
- The gateway POSTs to the endpoint, so endpoints are limited to the browser push services (https, port 443,
  host under PUSH_HOST_SUFFIXES, no redirects); anything else would let a learner make the gateway call
  internal URLs.
- A push carries the notification's own title and body (a planner reminder shows its real text, no lock-screen
  privacy handling), its actions, the notification id, and for a reminder `reminder_id` + `deep_link`.
- 404/410 from the push service = the subscription is gone: it is deleted.
"""

import asyncio
import base64
import binascii
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import requests
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from mentor_gateway.crypto import SecretBox
from mentor_gateway.db import Database, PushSubscription
from mentor_gateway.notifications import PLANNER_SOURCE, Item, primary_item
from mentor_gateway.planner.tables import Reminder
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)

PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com", "android.googleapis.com",  # Chrome, Edge (Chromium), Android
    "push.services.mozilla.com",  # Firefox
    "notify.windows.com",  # legacy Edge / Windows
    "push.apple.com",  # Safari (web.push.apple.com)
)
MAX_SUBSCRIPTIONS_PER_USER = 10
MAX_ENDPOINT_CHARS = 2048
PUSH_TIMEOUT_SECONDS = 10
DEFAULT_PUSH_TTL = timedelta(hours=6)


class PushSubscriptionError(ValueError):
    pass


def _b64url(value: Any, length: int, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200:
        raise PushSubscriptionError(f"{what} missing")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise PushSubscriptionError(f"{what} is not base64url") from exc
    if len(raw) != length:
        raise PushSubscriptionError(f"{what} has the wrong length")
    return value


def validate_subscription(raw: Any) -> dict:
    """A browser PushSubscription.toJSON() -> {endpoint, keys: {p256dh, auth}}; raises PushSubscriptionError."""
    if not isinstance(raw, dict):
        raise PushSubscriptionError("subscription must be an object")
    endpoint = raw.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > MAX_ENDPOINT_CHARS:
        raise PushSubscriptionError("endpoint missing or too long")
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError as exc:
        raise PushSubscriptionError("endpoint is not a URL") from exc
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        raise PushSubscriptionError("endpoint must be https on port 443")
    if not any(host == s or host.endswith("." + s) for s in PUSH_HOST_SUFFIXES):
        raise PushSubscriptionError("endpoint is not a known push service")
    keys = raw.get("keys")
    if not isinstance(keys, dict):
        raise PushSubscriptionError("keys missing")
    p256dh = _b64url(keys.get("p256dh"), 65, "keys.p256dh")
    auth = _b64url(keys.get("auth"), 16, "keys.auth")
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


def push_payload(batch: list[Item], reminder: Reminder | None = None) -> dict:
    """What the service worker receives: the notification's own title and body (a reminder shows its real text). A
    planner reminder adds `reminder_id` and `deep_link`: the tap opens that screen and reports the outcome like a
    device reminder."""
    primary = primary_item(batch)
    if len(batch) > 1:
        title, body = "Mentor", f"Mentor có {len(batch)} lời nhắn cho bạn."
    else:
        title, body = primary.title or "Mentor", primary.body or primary.title or "Mentor có lời nhắn cho bạn."
    payload = {"type": "notification", "id": primary.id, "kind": primary.kind, "title": title, "body": body,
               "actions": list(primary.actions), "mascot": primary.mascot, "created_at": primary.created_at.isoformat(),
               "bundled_ids": [i.id for i in batch if i is not primary], "url": f"/chat?notification={primary.id}"}
    if reminder is not None:
        payload.update(reminder_id=reminder.id, deep_link=reminder.deep_link)
    return payload


class PushService:
    def __init__(self, db: Database, box: SecretBox, settings: Settings, clock: Clock) -> None:
        self.db = db
        self.box = box
        self.settings = settings
        self.clock = clock
        self._vapid: Any = None

    @property
    def enabled(self) -> bool:
        return self.settings.push_enabled

    @property
    def public_key(self) -> str | None:
        return self.settings.vapid_public_key if self.enabled else None

    def _bidx(self, endpoint: str) -> str:
        return self.box.blind_index(endpoint, purpose="push-endpoint")

    @staticmethod
    def _aad(user_id: str, bidx: str) -> str:
        return f"push-sub:{user_id}:{bidx}"

    # ---- subscriptions -----------------------------------------------------------------------

    def subscribe(self, user_id: str, raw: Any, device: str | None = None) -> int:
        sub = validate_subscription(raw)
        bidx = self._bidx(sub["endpoint"])
        sealed = self.box.seal_str(json.dumps(sub), aad=self._aad(user_id, bidx))
        device = (device or "").strip()[:64] or None
        try:
            with self.db.session() as s:
                row = s.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id,
                                                               PushSubscription.endpoint_bidx == bidx)).first()
                if row is None:
                    row = PushSubscription(user_id=user_id, endpoint_bidx=bidx, sealed=sealed, device=device,
                                           created_at=self.clock())
                    s.add(row)
                else:  # same endpoint again (e.g. keys rotated): replace
                    row.sealed, row.device = sealed, device or row.device
                s.flush()
                sub_id = row.id
                # keep the newest MAX_SUBSCRIPTIONS_PER_USER devices
                ids = s.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user_id)
                                .order_by(PushSubscription.id.desc())).all()
                if len(ids) > MAX_SUBSCRIPTIONS_PER_USER:
                    s.execute(delete(PushSubscription).where(
                        PushSubscription.id.in_(ids[MAX_SUBSCRIPTIONS_PER_USER:])))
                return sub_id
        except IntegrityError:  # the same endpoint subscribed concurrently
            return self.subscribe(user_id, raw, device)

    def unsubscribe(self, user_id: str, endpoint: str | None = None) -> int:
        """Remove one device (by endpoint) or, without an endpoint, every subscription of the learner."""
        with self.db.session() as s:
            q = delete(PushSubscription).where(PushSubscription.user_id == user_id)
            if endpoint:
                q = q.where(PushSubscription.endpoint_bidx == self._bidx(endpoint))
            return s.execute(q).rowcount or 0

    def has_subscriptions(self, user_id: str) -> bool:
        return self.count(user_id) > 0

    def count(self, user_id: str) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(PushSubscription)
                            .where(PushSubscription.user_id == user_id)) or 0

    def _subscriptions(self, user_id: str) -> list[tuple[int, dict]]:
        out = []
        with self.db.session() as s:
            rows = s.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
        for row in rows:
            try:
                out.append((row.id, json.loads(self.box.unseal_str(row.sealed,
                                                                   aad=self._aad(user_id, row.endpoint_bidx)))))
            except Exception:  # noqa: BLE001 - wrong key after a botched rotation, tampering: drop it, the device resubscribes
                log.warning("push subscription %s of %s cannot be opened; removed", row.id, user_id)
                self._remove(row.id)
        return out

    def _remove(self, sub_id: int) -> None:
        with self.db.session() as s:
            s.execute(delete(PushSubscription).where(PushSubscription.id == sub_id))

    # ---- sending -----------------------------------------------------------------------------

    def _vapid_key(self) -> Any:
        if self._vapid is None:
            from py_vapid import Vapid

            self._vapid = Vapid.from_string(private_key=self.settings.vapid_private_key)
        return self._vapid

    def _send_one(self, sub: dict, data: str, ttl: int) -> int:
        """POST one push; returns the push service's HTTP status (0 = network error)."""
        session = requests.Session()
        session.max_redirects = 0  # push services answer directly; never follow a redirect elsewhere
        try:
            resp = webpush(sub, data=data, vapid_private_key=self._vapid_key(),
                           vapid_claims={"sub": self.settings.vapid_subject}, ttl=ttl,
                           timeout=PUSH_TIMEOUT_SECONDS, requests_session=session)
            return int(getattr(resp, "status_code", 201))
        except WebPushException as exc:
            return int(getattr(exc.response, "status_code", 0) or 0)
        except Exception:  # DNS, TLS, timeout, redirect
            log.warning("web push failed", exc_info=True)
            return 0
        finally:
            session.close()

    async def send(self, user_id: str, payload: dict, ttl: int) -> int:
        """Send to every device of the learner; returns how many accepted. Gone subscriptions are deleted."""
        if not self.enabled:
            return 0
        data = json.dumps(payload, ensure_ascii=False)
        delivered = 0
        for sub_id, sub in self._subscriptions(user_id):
            status = await asyncio.to_thread(self._send_one, sub, data, ttl)
            if 200 <= status < 300:
                delivered += 1
                with self.db.session() as s:
                    row = s.get(PushSubscription, sub_id)
                    if row is not None:
                        row.last_sent_at = self.clock()
            elif status in (404, 410):
                log.info("push subscription %s of %s is gone (%s); removed", sub_id, user_id, status)
                self._remove(sub_id)
            else:
                log.warning("push to subscription %s of %s failed: HTTP %s", sub_id, user_id, status)
        return delivered

    async def send_batch(self, user_id: str, batch: list[Item], now: datetime) -> int:
        expiries = [i.expires_at for i in batch if i.expires_at is not None]
        ttl = (min(expiries) - now) if expiries else DEFAULT_PUSH_TTL
        source = primary_item(batch).source
        reminder = None
        if len(batch) == 1 and source.startswith(PLANNER_SOURCE):  # a bundle opens the hub, not one reminder's screen
            with self.db.session() as s:
                reminder = s.get(Reminder, source[len(PLANNER_SOURCE):])
                if reminder is not None and reminder.user_id == user_id:
                    s.expunge(reminder)
                else:
                    reminder = None
        return await self.send(user_id, push_payload(batch, reminder), max(60, int(ttl.total_seconds())))


def rotate_subscriptions(s: Any, old: SecretBox, new: SecretBox) -> int:
    """Master-key rotation (rotation.ROTATORS): re-seal under the new key; the blind index (and so the aad)
    derives from the master key, so it is recomputed too."""
    rows = s.scalars(select(PushSubscription)).all()
    for r in rows:
        sub = old.unseal_str(r.sealed, aad=PushService._aad(r.user_id, r.endpoint_bidx))
        bidx = new.blind_index(json.loads(sub)["endpoint"], purpose="push-endpoint")
        r.endpoint_bidx = bidx
        r.sealed = new.seal_str(sub, aad=PushService._aad(r.user_id, bidx))
    return len(rows)


def generate_vapid_keys() -> tuple[str, str]:
    """(public, private) in the formats VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY expect."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def enc(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return enc(pub), enc(priv)
