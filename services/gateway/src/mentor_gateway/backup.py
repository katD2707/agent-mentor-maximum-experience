"""Encrypted snapshots of learner mirrors and the ops DB (see infra/README.md "Backups and encryption at rest").

Layout under MENTOR_BACKUP_DIR (default $MENTOR_DATA_DIR/backups):

    users/<user_id>/<snapshot>.mbk   `git bundle --all` of the mirror, encrypted with the user's data key
    ops/<snapshot>.mbk               sqlite online backup of ops.db, encrypted with HKDF(master, "mentor:ops-backup")

<snapshot> = UTC time `YYYYMMDDTHHMMSSZ` (plus `-N` if two land in the same second).

File format "MBK1" (chunked AES-256-GCM, streamable, truncation- and reorder-proof):

    b"MBK1" | u32be H | header (H bytes, UTF-8 JSON, plaintext but authenticated) | frame* (last one final)
    header = {"v": 1, "kind": "user"|"ops", "owner", "snapshot", "created_at", "head"?, "chunk", "salt": b64(32)}
    frame  = u32be L (plaintext length <= chunk) | AES-GCM(file_key, nonce, chunk) (L + 16 bytes)
    file_key = HKDF-SHA256(data_key, salt=header.salt, info="mentor-backup-v1")
    nonce    = 4 zero bytes | u64be frame index        (unique: the key is fresh per file)
    aad      = sha256(magic | H | header) | u64be index | final flag (1 byte)

The last frame has final=1 (an empty input still writes one empty final frame); nothing may follow it.
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import struct
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from mentor_gateway.crypto import SecretBox, derive_key
from mentor_gateway.datakeys import UserKeyStore
from mentor_gateway.db import BackupState, Database, User
from mentor_gateway.gitrepo import git_env, out, run_git
from mentor_gateway.mirror import BRANCH, Mirror
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)

MAGIC = b"MBK1"
CHUNK = 1 << 20
OPS_OWNER = "_ops"
OPS_KEY_PURPOSE = "ops-backup"
SUFFIX = ".mbk"
_MAX_HEADER = 64 * 1024
_ID_RE = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,63}$")
# ops-DB tables never scrubbed of a deleted user: audit_log is the legal record (plan 8.3)
_SCRUB_KEEP = {"audit_log"}


class BackupError(Exception):
    pass


class IntegrityError(BackupError):
    """Wrong key (e.g. crypto-shredded), tampered, truncated or not a backup file."""


# ---- file format -----------------------------------------------------------------------------------


def _frame_aad(digest: bytes, index: int, final: bool) -> bytes:
    return digest + struct.pack(">QB", index, 1 if final else 0)


def _nonce(index: int) -> bytes:
    return b"\0\0\0\0" + struct.pack(">Q", index)


def encrypt_stream(key: bytes, header: dict, src: BinaryIO, dst: BinaryIO, chunk_size: int = CHUNK) -> int:
    """Encrypt `src` into `dst` with a per-file key derived from `key`. Returns plaintext bytes written."""
    salt = secrets.token_bytes(32)
    header = {**header, "v": 1, "chunk": chunk_size, "salt": base64.b64encode(salt).decode()}
    hbytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    prefix = MAGIC + struct.pack(">I", len(hbytes)) + hbytes
    digest = hashlib.sha256(prefix).digest()
    aead = AESGCM(derive_key(key, "mentor-backup-v1", salt=salt))
    dst.write(prefix)
    total, index = 0, 0
    current = src.read(chunk_size)
    while True:
        nxt = src.read(chunk_size) if len(current) == chunk_size else b""
        final = not nxt
        dst.write(struct.pack(">I", len(current)))
        dst.write(aead.encrypt(_nonce(index), current, _frame_aad(digest, index, final)))
        total += len(current)
        if final:
            return total
        current, index = nxt, index + 1


def read_header(src: BinaryIO) -> tuple[dict, bytes]:
    """Parse the plaintext header (not yet authenticated). Returns (header, prefix bytes)."""
    magic = src.read(4)
    if magic != MAGIC:
        raise IntegrityError("not a mentor backup (bad magic)")
    raw_len = src.read(4)
    if len(raw_len) != 4:
        raise IntegrityError("truncated header")
    (hlen,) = struct.unpack(">I", raw_len)
    if hlen > _MAX_HEADER:
        raise IntegrityError("header too large")
    hbytes = src.read(hlen)
    if len(hbytes) != hlen:
        raise IntegrityError("truncated header")
    try:
        header = json.loads(hbytes)
    except ValueError as exc:
        raise IntegrityError("corrupt header") from exc
    if not isinstance(header, dict) or header.get("v") != 1:
        raise IntegrityError("unsupported backup version")
    return header, magic + raw_len + hbytes


def decrypt_stream(key: bytes, src: BinaryIO, dst: BinaryIO) -> dict:
    """Decrypt and verify every frame; raises IntegrityError on any failure. Returns the header."""
    header, prefix = read_header(src)
    digest = hashlib.sha256(prefix).digest()
    try:
        salt = base64.b64decode(header["salt"])
        chunk = int(header["chunk"])
    except (KeyError, ValueError, TypeError) as exc:
        raise IntegrityError("corrupt header") from exc
    aead = AESGCM(derive_key(key, "mentor-backup-v1", salt=salt))
    index = 0
    while True:
        raw_len = src.read(4)
        if len(raw_len) != 4:
            raise IntegrityError("truncated backup (no final frame)")
        (length,) = struct.unpack(">I", raw_len)
        if length > chunk:
            raise IntegrityError("corrupt frame length")
        ct = src.read(length + 16)
        if len(ct) != length + 16:
            raise IntegrityError("truncated frame")
        plain = None
        for final in (False, True):
            try:
                plain = aead.decrypt(_nonce(index), ct, _frame_aad(digest, index, final))
            except InvalidTag:
                continue
            break
        if plain is None:
            raise IntegrityError("authentication failed (wrong key, tampered or reordered)")
        dst.write(plain)
        if final:
            if src.read(1):
                raise IntegrityError("data after final frame")
            return header
        index += 1


# ---- object storage hook ------------------------------------------------------------------------------


class BackupUploader(Protocol):
    """Copy snapshots off the box (S3-compatible object storage, ...). `key` is the path relative to the backup
    dir, e.g. "users/<uid>/<snapshot>.mbk". Uploading the same key again replaces the object."""

    def upload(self, local_path: Path, key: str) -> None: ...
    def delete(self, key: str) -> None: ...


class LocalOnly:
    """Default: snapshots stay in MENTOR_BACKUP_DIR (which should itself be on separate, encrypted storage)."""

    def upload(self, local_path: Path, key: str) -> None:
        pass

    def delete(self, key: str) -> None:
        pass


# ---- service ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    owner: str  # user id or "_ops"
    id: str
    path: Path

    @property
    def created_at(self) -> datetime:
        return datetime.strptime(self.id.split("-")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)

    @property
    def key(self) -> str:
        sub = "ops" if self.owner == OPS_OWNER else f"users/{self.owner}"
        return f"{sub}/{self.id}{SUFFIX}"


def retention_keep(snapshots: list[Snapshot], daily: int, weekly: int) -> set[Snapshot]:
    """Newest snapshot of each of the `daily` most recent days and `weekly` most recent ISO weeks (UTC) that have
    one, plus the newest overall."""
    ordered = sorted(snapshots, key=lambda s: s.id, reverse=True)
    keep: set[Snapshot] = set(ordered[:1])
    days: set = set()
    weeks: set = set()
    for snap in ordered:
        day = snap.created_at.date()
        week = day.isocalendar()[:2]
        if day not in days and len(days) < daily:
            days.add(day)
            keep.add(snap)
        if week not in weeks and len(weeks) < weekly:
            weeks.add(week)
            keep.add(snap)
    return keep


def check_owner(owner: str) -> str:
    if not _OWNER_RE.match(owner):
        raise BackupError(f"invalid user id: {owner!r}")
    return owner


class BackupService:
    def __init__(self, settings: Settings, db: Database, box: SecretBox, mirror: Mirror, clock: Clock,
                 uploader: BackupUploader | None = None) -> None:
        self.settings = settings
        self.db = db
        self.box = box
        self.mirror = mirror
        self.clock = clock
        self.uploader: BackupUploader = uploader or LocalOnly()
        self.keys = UserKeyStore(db, box, clock)
        self.root = settings.backups_dir
        self._task: asyncio.Task | None = None
        self._last_run_day = None

    # ---- paths and listing ----

    def _dir(self, owner: str) -> Path:
        return self.root / "ops" if owner == OPS_OWNER else self.root / "users" / check_owner(owner)

    def snapshots(self, owner: str | None = None) -> list[Snapshot]:
        owners = [owner] if owner else [OPS_OWNER] + sorted(
            p.name for p in (self.root / "users").glob("*") if p.is_dir()
        )
        snaps = []
        for o in owners:
            d = self._dir(o)
            if d.is_dir():
                snaps += [Snapshot(o, p.name[: -len(SUFFIX)], p) for p in d.glob(f"*{SUFFIX}")
                          if _ID_RE.match(p.name[: -len(SUFFIX)])]
        return sorted(snaps, key=lambda s: (s.owner, s.id))

    def get(self, owner: str, snapshot_id: str) -> Snapshot:
        if not _ID_RE.match(snapshot_id):
            raise BackupError(f"invalid snapshot id: {snapshot_id!r}")
        path = self._dir(owner) / f"{snapshot_id}{SUFFIX}"
        if not path.is_file():
            raise BackupError(f"no snapshot {snapshot_id} for {owner}")
        return Snapshot(owner, snapshot_id, path)

    def _new_snapshot(self, owner: str, now: datetime) -> Snapshot:
        d = self._dir(owner)
        d.mkdir(parents=True, exist_ok=True)
        base = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        sid, n = base, 0
        while (d / f"{sid}{SUFFIX}").exists():
            n += 1
            sid = f"{base}-{n}"
        return Snapshot(owner, sid, d / f"{sid}{SUFFIX}")

    def _ops_key(self) -> bytes:
        return self.box.subkey(OPS_KEY_PURPOSE)

    def _finish(self, snap: Snapshot, part: Path) -> None:
        os.replace(part, snap.path)
        self.uploader.upload(snap.path, snap.key)

    # ---- users ----

    def backup_user(self, user_id: str, *, force: bool = False, now: datetime | None = None) -> Snapshot | None:
        """Snapshot the mirror if it changed since the last snapshot. Returns None when skipped."""
        check_owner(user_id)
        head = self.mirror.head(user_id)
        if head is None:
            return None
        with self.db.session() as s:
            state = s.get(BackupState, user_id)
            last = (state.last_head, state.last_snapshot) if state else None
        if not force and last and last[0] == head and (self._dir(user_id) / f"{last[1]}{SUFFIX}").is_file():
            return None
        key = self.keys.get_or_create(user_id)
        now = now or self.clock()
        snap = self._new_snapshot(user_id, now)
        part = snap.path.with_name(snap.path.name + ".part")
        header = {"kind": "user", "owner": user_id, "snapshot": snap.id, "created_at": now.isoformat(), "head": head}
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(["git", "--git-dir", str(self.mirror.path(user_id)), "bundle", "create", "-q",
                                     "-", "--all"], stdout=subprocess.PIPE, stderr=err, env=git_env())
            try:
                assert proc.stdout is not None
                with open(part, "wb") as dst:
                    encrypt_stream(key, header, proc.stdout, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
            finally:
                if proc.stdout is not None:
                    proc.stdout.close()
                code = proc.wait()
            if code != 0:
                part.unlink(missing_ok=True)
                err.seek(0)
                raise BackupError(f"git bundle failed for {user_id}: {err.read().decode('utf-8', 'replace')}")
        self._finish(snap, part)
        with self.db.session() as s:
            state = s.get(BackupState, user_id)
            if state is None:
                s.add(BackupState(user_id=user_id, last_head=head, last_snapshot=snap.id))
            else:
                state.last_head, state.last_snapshot = head, snap.id
        return snap

    def restore_user(self, user_id: str, snapshot_id: str, dest: Path) -> Path:
        """Decrypt + verify the snapshot and clone it into `dest` (must not exist or be empty)."""
        snap = self.get(user_id, snapshot_id)
        dest = Path(dest)
        if dest.exists() and any(dest.iterdir()):
            raise BackupError(f"{dest} is not empty")
        key = self.keys.get(user_id)
        if key is None:
            raise IntegrityError(f"no data key for {user_id} (account deleted: backups are crypto-shredded)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".restore-", suffix=".bundle", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as plain, open(snap.path, "rb") as src:
                header = decrypt_stream(key, src, plain)
            if header.get("owner") != user_id or header.get("kind") != "user" or header.get("snapshot") != snap.id:
                raise IntegrityError("snapshot header does not match the requested user/snapshot")
            run_git(["clone", "-q", "-b", BRANCH, tmp, str(dest)])
            verify = run_git(["bundle", "verify", "-q", tmp], cwd=dest, check=False)  # needs a repo
            if verify.returncode != 0:
                raise IntegrityError(f"git bundle verify failed: {verify.stderr.decode('utf-8', 'replace')}")
            run_git(["remote", "remove", "origin"], cwd=dest)
            got = out(run_git(["rev-parse", "HEAD"], cwd=dest))
            if header.get("head") and got != header["head"]:
                raise IntegrityError(f"restored HEAD {got} != snapshot head {header['head']}")
            run_git(["fsck", "--no-progress", "--no-dangling"], cwd=dest)
        except BaseException:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            raise
        finally:
            Path(tmp).unlink(missing_ok=True)
        return dest

    # ---- ops DB ----

    def _sqlite_path(self) -> Path | None:
        if self.db.engine.dialect.name != "sqlite":
            return None
        name = self.db.engine.url.database
        return Path(name) if name and name != ":memory:" else None

    def backup_ops(self, *, now: datetime | None = None) -> Snapshot | None:
        """sqlite online backup of ops.db, encrypted with the master-derived ops key. None for non-sqlite DBs
        (use the database's own backups, e.g. managed Postgres PITR)."""
        path = self._sqlite_path()
        if path is None:
            return None
        src = sqlite3.connect(str(path))
        mem = sqlite3.connect(":memory:")
        try:
            src.backup(mem)
            data = _no_wal(mem.serialize())
        finally:
            src.close()
            mem.close()
        now = now or self.clock()
        snap = self._new_snapshot(OPS_OWNER, now)
        part = snap.path.with_name(snap.path.name + ".part")
        with open(part, "wb") as dst:
            encrypt_stream(self._ops_key(), {"kind": "ops", "owner": OPS_OWNER, "snapshot": snap.id,
                                             "created_at": now.isoformat()}, io.BytesIO(data), dst)
            dst.flush()
            os.fsync(dst.fileno())
        self._finish(snap, part)
        return snap

    def _read_ops(self, snap: Snapshot, key: bytes) -> tuple[dict, bytes]:
        buf = io.BytesIO()
        with open(snap.path, "rb") as src:
            header = decrypt_stream(key, src, buf)
        if header.get("kind") != "ops" or header.get("snapshot") != snap.id:
            raise IntegrityError("snapshot header does not match")
        return header, buf.getvalue()

    def restore_ops(self, snapshot_id: str, dest: Path) -> Path:
        """Write the decrypted ops.db snapshot to `dest` (a file that must not exist) after an integrity check."""
        dest = Path(dest)
        if dest.exists():
            raise BackupError(f"{dest} exists")
        _, data = self._read_ops(self.get(OPS_OWNER, snapshot_id), self._ops_key())
        conn = sqlite3.connect(":memory:")
        try:
            conn.deserialize(_no_wal(data))
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IntegrityError("sqlite integrity_check failed")
        finally:
            conn.close()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def _rewrite_ops(self, snap: Snapshot, transform: Callable[[sqlite3.Connection], None], old_key: bytes,
                     new_key: bytes) -> None:
        header, data = self._read_ops(snap, old_key)
        conn = sqlite3.connect(":memory:")
        try:
            conn.deserialize(_no_wal(data))
            conn.execute("PRAGMA secure_delete=ON")
            transform(conn)
            conn.commit()
            conn.execute("VACUUM")
            data = conn.serialize()
        finally:
            conn.close()
        part = snap.path.with_name(snap.path.name + ".part")
        keep = {k: header[k] for k in ("kind", "owner", "snapshot", "created_at")}
        with open(part, "wb") as dst:
            encrypt_stream(new_key, keep, io.BytesIO(data), dst)
        self._finish(snap, part)

    def reencrypt_ops(self, old_box: SecretBox) -> int:
        """After a master-key rotation: re-encrypt local ops snapshots under the new master key."""
        old, new = old_box.subkey(OPS_KEY_PURPOSE), self._ops_key()
        snaps = self.snapshots(OPS_OWNER)
        for snap in snaps:
            self._rewrite_ops(snap, lambda conn: None, old, new)
        return len(snaps)

    # ---- runs, retention, deletion ----

    def prune(self, owner: str) -> list[Snapshot]:
        snaps = self.snapshots(owner)
        keep = retention_keep(snaps, self.settings.backup_keep_daily, self.settings.backup_keep_weekly)
        gone = [s for s in snaps if s not in keep]
        for s in gone:
            s.path.unlink(missing_ok=True)
            self.uploader.delete(s.key)
        return gone

    def run(self, now: datetime | None = None) -> dict:
        """Snapshot every changed mirror and ops.db, then apply retention. Errors per user are logged, not raised."""
        now = now or self.clock()
        for stale in self.root.glob("**/*.part"):
            stale.unlink(missing_ok=True)
        with self.db.session() as s:
            user_ids = list(s.scalars(select(User.id).where(User.provisioned_at.is_not(None))))
        made, skipped, errors = [], 0, []
        for uid in user_ids:
            try:
                snap = self.backup_user(uid, now=now)
            except Exception as exc:
                log.exception("backup of %s failed", uid)
                errors.append(f"{uid}: {exc}")
                continue
            if snap is None:
                skipped += 1
            else:
                made.append(f"{uid}/{snap.id}")
        ops = None
        try:
            ops = self.backup_ops(now=now)
        except Exception as exc:
            log.exception("ops.db backup failed")
            errors.append(f"ops: {exc}")
        pruned = 0
        for owner in {s.owner for s in self.snapshots()}:
            pruned += len(self.prune(owner))
        summary = {"users": made, "skipped": skipped, "ops": ops.id if ops else None, "pruned": pruned,
                   "errors": errors}
        log.info("backup run: %s", summary)
        return summary

    async def maybe_run(self, now: datetime) -> None:
        """Scheduler hook: start one run per UTC day at/after BACKUP_HOUR_UTC, in a thread."""
        if self._task is not None and not self._task.done():
            return
        if now.hour < self.settings.backup_hour_utc:
            return
        if self._last_run_day is None:
            latest = max((s.id for s in self.snapshots()), default=None)
            self._last_run_day = Snapshot("", latest, Path()).created_at.date() if latest else None
        if self._last_run_day == now.date():
            return
        self._last_run_day = now.date()

        async def _run() -> None:
            try:
                await asyncio.to_thread(self.run, now)
            except Exception:
                log.exception("backup run failed")

        self._task = asyncio.create_task(_run())

    def forget_user(self, user_id: str) -> None:
        """Account deletion: shred the data key (all copies of the user's snapshots become unreadable), delete the
        local snapshot files and backup state, and scrub the user's rows (including the wrapped key) from local
        ops.db snapshots."""
        check_owner(user_id)
        self.keys.delete(user_id)
        with self.db.session() as s:
            state = s.get(BackupState, user_id)
            if state is not None:
                s.delete(state)
        for snap in self.snapshots(user_id):
            snap.path.unlink(missing_ok=True)
            self.uploader.delete(snap.key)
        d = self._dir(user_id)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
        key = self._ops_key()
        for snap in self.snapshots(OPS_OWNER):
            try:
                self._rewrite_ops(snap, lambda conn: scrub_user(conn, user_id), key, key)
            except Exception:
                log.exception("scrubbing %s from ops snapshot %s", user_id, snap.id)


def scrub_user(conn: sqlite3.Connection, user_id: str) -> None:
    """Delete a user's rows from an ops.db copy: every table with a user_id/student_user_id column (except the
    audit log), the users row, and login rows for the user's email."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    emails = []
    if "users" in tables:
        emails = [r[0] for r in conn.execute("SELECT email FROM users WHERE id = ?", (user_id,))]
    for table in tables:
        if table in _SCRUB_KEEP or table.startswith("sqlite_"):
            continue
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        for col in ("user_id", "student_user_id"):
            if col in cols:
                conn.execute(f'DELETE FROM "{table}" WHERE "{col}" = ?', (user_id,))
        if table == "users":
            conn.execute('DELETE FROM "users" WHERE id = ?', (user_id,))
        if "email" in cols and table != "users":
            for email in emails:
                conn.execute(f'DELETE FROM "{table}" WHERE email = ?', (email,))


def _no_wal(data: bytes) -> bytes:
    """Mark a serialized sqlite image as rollback-journal: a WAL-mode header (bytes 18-19 = 2) cannot be opened
    from memory, and the restored file should not expect a -wal file next to it."""
    if len(data) >= 20 and data[18:20] != b"\x01\x01":
        data = data[:18] + b"\x01\x01" + data[20:]
    return data
