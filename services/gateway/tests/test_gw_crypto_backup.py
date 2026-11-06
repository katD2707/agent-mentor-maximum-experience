"""Field encryption, per-user data keys, encrypted snapshots, retention, crypto-shredding, key rotation."""

import io
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from mentor_schemas import ParentLink
from sqlalchemy import select

from mentor_gateway.backup import (
    OPS_OWNER,
    BackupError,
    BackupService,
    IntegrityError,
    Snapshot,
    decrypt_stream,
    encrypt_stream,
    retention_keep,
)
from mentor_gateway.crypto import DecryptError, SecretBox
from mentor_gateway.db import AuditRow, Database, ParentContact, ParentLinkRow, User, UserDataKey
from mentor_gateway.gitrepo import UserLocks, out, run_git
from mentor_gateway.mirror import Mirror
from mentor_gateway.parent import SqlParentLinkStore
from mentor_gateway.rotation import rotate_master_key
from mentor_gateway.settings import Settings

NOW = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)


@pytest.fixture
def box() -> SecretBox:
    return SecretBox(secrets.token_bytes(32))


@pytest.fixture
def db(tmp_path) -> Database:
    d = Database(f"sqlite:///{(tmp_path / 'ops.db').as_posix()}")
    d.create_all()
    yield d
    d.dispose()


@pytest.fixture
def svc(tmp_path, db, box) -> BackupService:
    settings = Settings(env="test", data_dir=tmp_path, backup_keep_daily=3, backup_keep_weekly=2)
    return BackupService(settings, db, box, Mirror(tmp_path / "mirrors", UserLocks()), lambda: NOW)


def _add_user(db: Database, uid: str) -> None:
    with db.session() as s:
        s.add(User(id=uid, email=f"{uid}@x.vn", created_at=NOW, provisioned_at=NOW))


def _commit(svc: BackupService, uid: str, files: dict[str, bytes]) -> str:
    svc.mirror.create(uid)
    return svc.mirror.commit_files(uid, files, author="user", message="m")


# ---- SecretBox ---------------------------------------------------------------------------------------


def test_seal_unseal_binds_aad_and_key(box):
    token = box.seal_str("0901234567", aad="t:c:1")
    assert "0901234567" not in token
    assert box.unseal_str(token, aad="t:c:1") == "0901234567"
    with pytest.raises(DecryptError):
        box.unseal_str(token, aad="t:c:2")
    with pytest.raises(DecryptError):
        SecretBox(secrets.token_bytes(32)).unseal_str(token, aad="t:c:1")
    assert box.blind_index("x", purpose="a") == box.blind_index("x", purpose="a")
    assert box.blind_index("x", purpose="a") != box.blind_index("x", purpose="b")
    assert box.subkey("p") != box.subkey("q")


# ---- parent contacts and audit -----------------------------------------------------------------------


def test_parent_chat_id_encrypted_and_found_by_blind_index(db, box):
    store = SqlParentLinkStore(db, lambda: NOW, box)
    link = ParentLink(student_user_id="u1", link_code="123456", code_expires_at=NOW + timedelta(hours=1),
                      zalo_chat_id="zalo-chat-777", status="verified", verified_at=NOW)
    store.save(link)
    store.save(link.model_copy(update={"student_user_id": "u2", "zalo_chat_id": "other", "status": "pending"}))
    with db.session() as s:
        assert s.get(ParentLinkRow, "u1").zalo_chat_id is None
        contact = s.get(ParentContact, "u1")
        assert "zalo-chat-777" not in contact.zalo_chat_enc + contact.zalo_chat_bidx
    assert store.get_by_chat("zalo-chat-777").student_user_id == "u1"
    assert store.get_by_student("u1").zalo_chat_id == "zalo-chat-777"
    assert store.get_by_code("123456").student_user_id == "u2"  # the pending one
    assert store.get_by_chat("nope") is None
    store.save(link.model_copy(update={"zalo_chat_id": None}))  # unlinking removes the contact
    assert store.get_by_chat("zalo-chat-777") is None

    store.record_audit("u1", "consent", "zalo_chat_id=zalo-chat-777; display_name=Mẹ")
    with db.session() as s:
        raw = s.scalars(select(AuditRow.detail)).one()
    assert "zalo-chat-777" not in raw and "Mẹ" not in raw
    assert store.read_audit("u1")[0][:2] == ("consent", "zalo_chat_id=zalo-chat-777; display_name=Mẹ")
    store.delete_student("u1")
    with db.session() as s:
        assert s.get(ParentContact, "u1") is None


# ---- stream format ------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", [0, 5, 64, 200])
def test_chunked_stream_roundtrip(size):
    key, data = secrets.token_bytes(32), secrets.token_bytes(size)
    buf = io.BytesIO()
    encrypt_stream(key, {"kind": "user", "owner": "u"}, io.BytesIO(data), buf, chunk_size=64)
    plain = io.BytesIO()
    assert decrypt_stream(key, io.BytesIO(buf.getvalue()), plain)["owner"] == "u"
    assert plain.getvalue() == data


def test_stream_rejects_tamper_truncation_and_wrong_key():
    key = secrets.token_bytes(32)
    buf = io.BytesIO()
    encrypt_stream(key, {"owner": "u"}, io.BytesIO(b"a" * 200), buf, chunk_size=64)
    blob = buf.getvalue()
    flipped = bytearray(blob)
    flipped[-20] ^= 1
    header_swap = blob.replace(b'"owner":"u"', b'"owner":"v"')
    last_frame = 4 + 16 + 200 - 192  # u32 len + tag + last 8-byte chunk
    for bad in (bytes(flipped), blob[:-last_frame], header_swap, blob + b"x"):
        with pytest.raises(IntegrityError):
            decrypt_stream(key, io.BytesIO(bad), io.BytesIO())
    with pytest.raises(IntegrityError):
        decrypt_stream(secrets.token_bytes(32), io.BytesIO(blob), io.BytesIO())


# ---- learner snapshots --------------------------------------------------------------------------------


def test_backup_restore_roundtrip_skips_unchanged(svc, db, tmp_path):
    _add_user(db, "u1")
    head = _commit(svc, "u1", {"me/profile.md": b"# Lan\n", "goals/a.md": b"thi THPT"})
    snap = svc.backup_user("u1")
    assert snap is not None and b"Lan" not in snap.path.read_bytes()
    assert svc.backup_user("u1") is None  # unchanged mirror
    dest = svc.restore_user("u1", snap.id, tmp_path / "restored")
    assert (dest / "me" / "profile.md").read_bytes() == b"# Lan\n"
    assert out(run_git(["rev-parse", "HEAD"], cwd=dest)) == head
    with pytest.raises(Exception, match="not empty"):
        svc.restore_user("u1", snap.id, dest)

    summary = svc.run(NOW + timedelta(days=1))  # unchanged user skipped, ops.db snapshot made
    assert summary["users"] == [] and summary["skipped"] == 1 and summary["ops"] and not summary["errors"]


def test_restore_rejects_snapshot_of_another_user(svc, db, tmp_path):
    for uid in ("u1", "u2"):
        _add_user(db, uid)
        _commit(svc, uid, {"a.md": uid.encode()})
    s1 = svc.backup_user("u1")
    target = svc._dir("u2") / s1.path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(s1.path.read_bytes())  # u1's file planted under u2
    with pytest.raises(IntegrityError):
        svc.restore_user("u2", s1.id, tmp_path / "x")
    assert not (tmp_path / "x").exists()


def test_crypto_shred_makes_restore_fail_and_scrubs_ops(svc, db, tmp_path):
    for uid in ("u1", "u2"):
        _add_user(db, uid)
        _commit(svc, uid, {"a.md": uid.encode()})
    s1 = svc.backup_user("u1")
    svc.backup_user("u2")
    copy = tmp_path / "offsite.mbk"
    copy.write_bytes(s1.path.read_bytes())  # e.g. an object-storage copy we cannot delete
    ops = svc.backup_ops()

    svc.forget_user("u1")
    assert svc.keys.get("u1") is None and svc.snapshots("u1") == []
    svc._dir("u1").mkdir(parents=True)
    (svc._dir("u1") / s1.path.name).write_bytes(copy.read_bytes())  # bring the off-site copy back
    with pytest.raises(IntegrityError, match="crypto-shredded"):
        svc.restore_user("u1", s1.id, tmp_path / "r")
    # even with the file and a guessed/random key, the copy cannot be opened
    with pytest.raises(IntegrityError), open(copy, "rb") as f:
        decrypt_stream(secrets.token_bytes(32), f, io.BytesIO())
    # the wrapped key and the user's rows are gone from the ops snapshot too; u2 is intact
    restored = svc.restore_ops(ops.id, tmp_path / "ops-restored.db")
    conn = sqlite3.connect(restored)
    try:
        keys = {r[0] for r in conn.execute("SELECT user_id FROM user_keys")}
        users = {r[0] for r in conn.execute("SELECT id FROM users")}
    finally:
        conn.close()
    assert keys == {"u2"} and users == {"u2"}


def test_retention_keeps_daily_and_weekly(svc):
    d = svc._dir("u1")
    d.mkdir(parents=True)
    start = datetime(2026, 9, 1, 19, 0, tzinfo=UTC)
    for i in range(40):  # one snapshot a day for 40 days, two on the last day
        (d / f"{(start + timedelta(days=i)).strftime('%Y%m%dT%H%M%SZ')}.mbk").write_bytes(b"x")
    (d / f"{(start + timedelta(days=39, hours=1)).strftime('%Y%m%dT%H%M%SZ')}.mbk").write_bytes(b"x")
    gone = svc.prune("u1")
    left = sorted(s.id for s in svc.snapshots("u1"))
    # 3 daily (Oct 8, 9, 10 20:00) + 2 weekly (ISO week 41 = Oct 10 20:00, already kept; week 40 = Oct 4)
    assert len(left) == 4 and len(gone) == 37
    assert left[-1] == (start + timedelta(days=39, hours=1)).strftime("%Y%m%dT%H%M%SZ")
    snaps = [Snapshot("u", (start + timedelta(days=i)).strftime("%Y%m%dT%H%M%SZ"), d) for i in range(5)]
    assert retention_keep(snaps, 0, 0) == {snaps[-1]}  # the newest always survives


# ---- rotation -----------------------------------------------------------------------------------------


def test_rotate_master_key_rewraps(svc, db, box, tmp_path):
    store = SqlParentLinkStore(db, lambda: NOW, box)
    store.save(ParentLink(student_user_id="u1", link_code="1", code_expires_at=NOW, zalo_chat_id="c1",
                          status="verified"))
    store.record_audit("u1", "consent", "c1")
    _add_user(db, "u1")
    _commit(svc, "u1", {"a.md": b"x"})
    snap = svc.backup_user("u1")
    ops = svc.backup_ops()

    new = SecretBox(secrets.token_bytes(32))
    counts = rotate_master_key(db, box, new)
    assert counts["user_keys"] == 1 and counts["parent_contacts"] == 1 and counts["audit_log"] == 1
    svc.box = new
    svc.keys.box = new
    assert svc.reencrypt_ops(box) == 1
    new_store = SqlParentLinkStore(db, lambda: NOW, new)
    assert new_store.get_by_chat("c1").student_user_id == "u1"
    assert new_store.read_audit("u1")[0][1] == "c1"
    assert svc.restore_user("u1", snap.id, tmp_path / "r").is_dir()  # data key unchanged, only re-wrapped
    assert svc.restore_ops(ops.id, tmp_path / "o.db").is_file()
    with db.session() as s:
        sealed = s.get(UserDataKey, "u1").sealed_key
    with pytest.raises(DecryptError):
        SqlParentLinkStore(db, lambda: NOW, box).get_by_student("u1")
    assert sealed


# ---- account deletion through the API ------------------------------------------------------------------


def test_delete_account_shreds_backups(client, gw, ncs_user, tmp_path):
    uid = ncs_user["user_id"]
    snap = gw.backups.backup_user(uid)
    assert snap is not None and gw.backups.keys.get(uid) is not None
    assert client.delete("/api/account").json() == {"ok": True}
    assert gw.backups.keys.get(uid) is None
    assert not gw.backups._dir(uid).exists()
    with pytest.raises(BackupError):
        gw.backups.restore_user(uid, snap.id, tmp_path / "r")
    assert gw.scheduler.backups is None  # MENTOR_ENV=test: no daily job unless BACKUP_ENABLED
    assert gw.backups.snapshots(OPS_OWNER) == []


def test_cli_backup_run_list_restore(svc, db, tmp_path, capsys):
    from mentor_gateway import cli

    _add_user(db, "u1")
    _commit(svc, "u1", {"a.md": b"cli"})
    cli.main(["backup-run"], settings=svc.settings)
    assert '"errors": []' in capsys.readouterr().out
    cli.main(["backup-list", "--user", "u1"], settings=svc.settings)
    owner, sid, _size = capsys.readouterr().out.split()
    cli.main(["backup-restore", "--user", owner, "--snapshot", sid, "--to", str(tmp_path / "r")], settings=svc.settings)
    assert (tmp_path / "r" / "a.md").read_bytes() == b"cli"
    with pytest.raises(SystemExit, match="restore failed"):
        cli.main(["backup-restore", "--user", "u1", "--snapshot", "20200101T000000Z", "--to", str(tmp_path / "q")],
                 settings=svc.settings)


async def test_scheduler_hook_runs_once_a_day_after_the_hour(svc):
    await svc.maybe_run(NOW.replace(hour=18))
    assert svc._task is None
    await svc.maybe_run(NOW)  # 20:00 UTC
    await svc._task
    first = svc._task
    await svc.maybe_run(NOW + timedelta(hours=2))
    assert svc._task is first and len(svc.snapshots(OPS_OWNER)) == 1
