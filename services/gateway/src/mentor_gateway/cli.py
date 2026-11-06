"""Operator commands. Run with `uv run python -m mentor_gateway.cli <command>`.

  zalo-set-webhook --url https://<public host>/webhooks/zalo   register the webhook (uses ZALO_BOT_TOKEN,
                                                               ZALO_WEBHOOK_SECRET); run once per deploy
  zalo-webhook-info                                            show what Zalo has registered
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


def _client(settings: Settings):
    from mentor_parent_channel import ZaloBotClient

    if not settings.zalo_bot_token:
        sys.exit("ZALO_BOT_TOKEN is not set")
    return ZaloBotClient(settings.zalo_bot_token)


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
    hook = sub.add_parser("zalo-set-webhook")
    hook.add_argument("--url", required=True, help="public HTTPS URL ending in /webhooks/zalo")
    sub.add_parser("zalo-webhook-info")
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

    if args.cmd == "zalo-set-webhook":
        if not args.url.startswith("https://"):
            sys.exit("Zalo requires an https:// webhook URL")
        with _client(settings) as client:
            print(json.dumps(client.set_webhook(args.url, settings.zalo_webhook_secret), default=str))
    elif args.cmd == "zalo-webhook-info":
        with _client(settings) as client:
            print(json.dumps(client.get_webhook_info(), default=str))
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
        query = select(User).where(User.provisioned_at.is_not(None))
        users = [(u.id, u.role) for u in s.scalars(query if only is None else query.where(User.id == only))]
    if only and not users:
        sys.exit(f"no provisioned learner {only}")
    mirror = (_DryRun if dry_run else Mirror)(settings.mirrors_dir, UserLocks())
    failed = 0
    for uid, role in users:
        try:
            changed = refresh_content(settings.content_dir, mirror, uid, Profile(role))
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
