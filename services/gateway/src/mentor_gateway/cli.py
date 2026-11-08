"""Operator commands. Run with `uv run python -m mentor_gateway.cli <command>`.

  create-user --username U --role student|teacher [--display-name N] [--birth-year Y] [--language L]
                                                               create an account (password from MENTOR_NEW_PASSWORD
                                                               or a prompt); there is no sign-up
  set-birth-year --username U --year Y                         correct a learner's birth year (students cannot;
                                                               the age band follows from it)
  backup-run [--user <uid>] [--force]                          snapshot changed mirrors + ops.db, apply retention
  backup-list [--user <uid>|_ops]                              list snapshots
  backup-restore --user <uid> --snapshot <id> --to <dir>       verify + decrypt + clone a learner snapshot
  backup-restore --ops --snapshot <id> --to <file>             verify + decrypt an ops.db snapshot
  rotate-master-key [--generate]                               re-wrap everything under MENTOR_NEW_MASTER_KEY
                                                               (gateway stopped; see infra/README.md)
  vapid-generate [--env-file F] [--subject S]                  Web Push keys, once: print them, or append
                                                               VAPID_* to F unless F already has them
  refresh-content [--user <uid>] [--dry-run]                   copy the current mentor-content (AGENTS.md, skills,
                                                               curricula) into existing workspaces; run after
                                                               every content update (deploy.sh does)
"""

import argparse
import base64
import json
import os
import secrets
import sys
from pathlib import Path

from mentor_gateway.settings import Settings


def _backups(settings: Settings):
    from mentor_gateway.backup import BackupService
    from mentor_gateway.crypto import SecretBox, load_master_key
    from mentor_gateway.db import Database
    from mentor_gateway.gitrepo import UserLocks
    from mentor_gateway.mirror import Mirror
    from mentor_gateway.settings import utc_now

    box = SecretBox(load_master_key(settings.env, settings.data_dir))
    db = Database(settings.ops_db_url)
    db.create_all()
    return BackupService(settings, db, box, Mirror(settings.mirrors_dir, UserLocks()), utc_now)


def _rotate(settings: Settings, generate: bool) -> None:
    from mentor_gateway.crypto import SecretBox, load_master_key
    from mentor_gateway.rotation import rotate_master_key

    raw = os.environ.get("MENTOR_NEW_MASTER_KEY", "").strip()
    if raw and generate:
        sys.exit("pass either MENTOR_NEW_MASTER_KEY or --generate")
    if generate:
        raw = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    if not raw:
        sys.exit("set MENTOR_NEW_MASTER_KEY (urlsafe base64 of 32 bytes) or pass --generate")
    new_key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(new_key) != 32:
        sys.exit("MENTOR_NEW_MASTER_KEY must decode to 32 bytes")
    old_box = SecretBox(load_master_key(settings.env, settings.data_dir))
    svc = _backups(settings)
    new_box = SecretBox(new_key)
    counts = rotate_master_key(svc.db, old_box, new_box)
    svc.box = new_box
    counts["ops_snapshots"] = svc.reencrypt_ops(old_box)
    dev_file = settings.data_dir / "master.key"
    if not os.environ.get("MENTOR_MASTER_KEY") and dev_file.is_file():
        dev_file.write_text(base64.urlsafe_b64encode(new_key).decode())
        counts["dev_key_file"] = 1
    print(json.dumps(counts))
    if generate and not counts.get("dev_key_file"):
        print(f"new MENTOR_MASTER_KEY (store it in the secret manager now; it is not saved anywhere): {raw}")
    print("Done. Set MENTOR_MASTER_KEY to the new key before starting the gateway.", file=sys.stderr)


def main(argv: list[str] | None = None, settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mentor_gateway.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user")
    cu.add_argument("--username", required=True)
    cu.add_argument("--role", required=True, choices=["student", "teacher"])
    cu.add_argument("--display-name")
    cu.add_argument("--birth-year", type=int)
    cu.add_argument("--language", choices=["vi", "en"])
    sb = sub.add_parser("set-birth-year")
    sb.add_argument("--username", required=True)
    sb.add_argument("--year", required=True, type=int)
    run = sub.add_parser("backup-run")
    run.add_argument("--user", help="only this learner; with --force even if unchanged")
    run.add_argument("--force", action="store_true")
    ls = sub.add_parser("backup-list")
    ls.add_argument("--user", help="a learner id, or _ops")
    restore = sub.add_parser("backup-restore")
    who = restore.add_mutually_exclusive_group(required=True)
    who.add_argument("--user")
    who.add_argument("--ops", action="store_true")
    restore.add_argument("--snapshot", required=True)
    restore.add_argument("--to", required=True, type=Path)
    rot = sub.add_parser("rotate-master-key")
    rot.add_argument("--generate", action="store_true", help="generate the new key and print it once")
    vap = sub.add_parser("vapid-generate")
    vap.add_argument("--env-file", type=Path, help="append VAPID_* here if they are not set yet")
    vap.add_argument("--subject", default="mailto:admin@localhost", help="VAPID_SUBJECT (mailto: or https:)")
    ref = sub.add_parser("refresh-content")
    ref.add_argument("--user", help="only this learner")
    ref.add_argument("--dry-run", action="store_true", help="list what would change, commit nothing")
    args = parser.parse_args(argv)
    settings = settings or Settings.from_env()

    if args.cmd == "create-user":
        _create_user(settings, args)
    elif args.cmd == "set-birth-year":
        _set_birth_year(settings, args.username, args.year)
    elif args.cmd == "backup-run":
        svc = _backups(settings)
        if args.user:
            snap = svc.backup_user(args.user, force=args.force)
            svc.prune(args.user)
            print(json.dumps({"user": args.user, "snapshot": snap.id if snap else None}))
        else:
            summary = svc.run()
            print(json.dumps(summary))
            if summary["errors"]:
                sys.exit(1)
    elif args.cmd == "backup-list":
        for snap in _backups(settings).snapshots(args.user):
            print(f"{snap.owner}\t{snap.id}\t{snap.path.stat().st_size}")
    elif args.cmd == "backup-restore":
        from mentor_gateway.backup import BackupError

        svc = _backups(settings)
        try:
            dest = svc.restore_ops(args.snapshot, args.to) if args.ops else svc.restore_user(
                args.user, args.snapshot, args.to)
        except BackupError as exc:
            sys.exit(f"restore failed: {exc}")
        print(f"restored to {dest}")
    elif args.cmd == "rotate-master-key":
        _rotate(settings, args.generate)
    elif args.cmd == "vapid-generate":
        _vapid(args.env_file, args.subject)
    elif args.cmd == "refresh-content":
        _refresh_content(settings, args.user, args.dry_run)


def _create_user(settings: Settings, args: argparse.Namespace) -> None:
    import getpass

    from mentor_gateway.db import Database
    from mentor_gateway.gitrepo import UserLocks
    from mentor_gateway.mirror import Mirror
    from mentor_gateway.settings import utc_now
    from mentor_gateway.users import UserService

    password = os.environ.get("MENTOR_NEW_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 6:
        sys.exit("password must be at least 6 characters")
    db = Database(settings.ops_db_url)
    db.create_all()
    users = UserService(db, Mirror(settings.mirrors_dir, UserLocks()), settings, utc_now)
    if users.by_username(args.username):
        sys.exit(f"user {args.username} already exists")
    user = users.create(username=args.username, password=password, role=args.role,
                        display_name=args.display_name or args.username, birth_year=args.birth_year,
                        language=args.language)
    print(user.id)


def _set_birth_year(settings: Settings, username: str, year: int) -> None:
    from mentor_gateway.age import BIRTH_YEAR_MAX, BIRTH_YEAR_MIN, band_for_birth_year
    from mentor_gateway.db import Database
    from mentor_gateway.gitrepo import UserLocks
    from mentor_gateway.mirror import Mirror
    from mentor_gateway.settings import utc_now
    from mentor_gateway.users import UserService

    if not BIRTH_YEAR_MIN <= year <= BIRTH_YEAR_MAX:
        sys.exit(f"year must be between {BIRTH_YEAR_MIN} and {BIRTH_YEAR_MAX}")
    db = Database(settings.ops_db_url)
    db.create_all()
    users = UserService(db, Mirror(settings.mirrors_dir, UserLocks()), settings, utc_now)
    user = users.by_username(username)
    if user is None:
        sys.exit(f"no user {username}")
    if user.role != "student":
        sys.exit(f"{username} is not a student")
    users.update(user.id, birth_year=year)
    print(f"{username}: birth year {year} (age band {band_for_birth_year(year)})")


def _refresh_content(settings: Settings, only: str | None, dry_run: bool) -> None:
    """One line per learner: changed paths, or "unchanged". Exit 1 if any learner failed."""
    from mentor_schemas import Profile
    from sqlalchemy import select

    from mentor_gateway.db import Database, User
    from mentor_gateway.gitrepo import UserLocks
    from mentor_gateway.mirror import Mirror
    from mentor_gateway.provisioning import refresh_content

    class _DryRun(Mirror):
        def commit_files(self, *a, **k) -> str:  # dry run: report the diff, write nothing
            return ""

    db = Database(settings.ops_db_url)
    with db.session() as s:
        query = select(User).where(User.provisioned_at.is_not(None), User.role == "student")
        users = [(u.id, u.role) for u in s.scalars(query if only is None else query.where(User.id == only))]
    if only and not users:
        sys.exit(f"no provisioned learner {only}")
    mirror = (_DryRun if dry_run else Mirror)(settings.mirrors_dir, UserLocks())
    failed = 0
    for uid, role in users:
        try:
            changed = refresh_content(settings.content_dir, mirror, uid, Profile.STUDENT)
        except Exception as exc:  # noqa: BLE001 - report and go on with the other learners
            failed += 1
            print(f"{uid}\tERROR {type(exc).__name__}: {exc}")
            continue
        if not changed:
            print(f"{uid}\tunchanged")
            continue
        print(f"{uid}\t{len(changed)} changed{' (dry run)' if dry_run else ''}")
        for path in changed:
            print(f"  {path}")
    if failed:
        sys.exit(1)


def _vapid(env_file: Path | None, subject: str) -> None:
    """Generate the Web Push key pair once. Never replaces existing keys: browsers subscribed with the old public
    key would stop receiving pushes."""
    from mentor_gateway.push import generate_vapid_keys

    text = env_file.read_text(encoding="utf-8") if env_file is not None and env_file.is_file() else ""
    if any(line.startswith("VAPID_PRIVATE_KEY=") and line.strip() != "VAPID_PRIVATE_KEY="
           for line in text.splitlines()):
        print(f"{env_file} already has VAPID keys; nothing changed")
        return
    public, private = generate_vapid_keys()
    lines = [f"VAPID_PUBLIC_KEY={public}", f"VAPID_PRIVATE_KEY={private}", f"VAPID_SUBJECT={subject}"]
    if env_file is None:
        print("\n".join(lines))
        return
    with env_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(("\n" if text and not text.endswith("\n") else "") + "\n".join(lines) + "\n")
    print(f"appended VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT to {env_file}")


if __name__ == "__main__":
    main()
