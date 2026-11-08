# infra

Docker and scripts for running the gateway, the model router and the web build. Learner-facing steps are in the root
[README](../README.md); this file has the details.

| File | What |
|---|---|
| `dev-up.ps1` | Windows: router (:4000), gateway (:8000), app (:5173) in separate windows; `-Desktop` adds the Tauri window |
| `docker-compose.dev.yml` | Gateway + model router in Docker; the app runs on the host (`pnpm dev` in `apps/app`) |
| `docker-compose.demo.yml`, `demo.sh` | Local demo on one Linux machine, dev mode, bound to 127.0.0.1 |
| `docker-compose.prod.yml`, `Caddyfile`, `deploy.sh`, `.env.prod.example` | Pilot on one Linux VM |
| `gateway.Dockerfile`, `web.Dockerfile`, `web.Caddyfile` | Images: gateway; static build of `apps/app` served by Caddy |
| `import-agent-mentor-bank.py` | Imports the agent-mentor seed question bank into `mentor-content/bank` (CONTRACTS 10.1) |

`MENTOR_ENV` is required for development. Unset means `prod`: no dev accounts and `MENTOR_MASTER_KEY` is required. Dev and
demo seed `hocsinh` / `giaovien` (password `123456`).

## Dev

```powershell
# Gateway on the host, no Docker
$env:MENTOR_ENV="dev"; $env:MENTOR_DATA_DIR="var-dev"; uv run uvicorn mentor_gateway.app:app --port 8000

# Gateway + router in Docker (secrets from the shell or a repo-root .env: FPT_API_BASE, FPT_API_KEY, MODEL_ROUTER_MASTER_KEY)
docker compose -f infra/docker-compose.dev.yml up --build
```

Reset dev data: `Remove-Item -Recurse -Force var-dev` (an old SQLite ops DB with a different schema is also recreated on start).
On Linux the gateway container runs as uid 4242, so the host data dir must be writable by it (`sudo chown -R 4242:4242 var`) or
set `MENTOR_UID` / `MENTOR_GID`.

## Pilot (docker-compose.prod.yml)

Caddy (80/443, Let's Encrypt) routes `/api/*` to the gateway and the rest to `web`. Only Caddy publishes ports. The gateway runs
as uid 4242 with a read-only root filesystem and no capabilities. `deploy.sh` commands: (none) deploy, `update`, `backup`,
`logs [svc]`, `status`, `content`, `user USERNAME ROLE`, `down`. The web image bakes in `VITE_API_BASE`
(`https://$DOMAIN/api`), so a new domain needs `deploy.sh` to rebuild it. Log in with an account made by `deploy.sh user`;
there is no sign-up.

## Gateway environment

Read in `services/gateway/src/mentor_gateway/settings.py`.

| Var | Default | |
|---|---|---|
| `MENTOR_ENV` | `prod` | `dev` seeds the dev accounts; `test` is for the test suite |
| `MENTOR_DATA_DIR` | `var` | `ops.db`, `mirrors/`, `workspaces/`, `builder/`, `backups/`. On Windows keep the path short |
| `MENTOR_DATABASE_URL` | SQLite in the data dir | any SQLAlchemy URL |
| `MENTOR_CONTENT_DIR` | `<repo>/mentor-content` | content root; courses are read from and published to `courses/` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | where the gateway is reachable |
| `WEB_ORIGIN`, `CORS_ORIGINS` | `http://localhost:5173`, empty | allowed web origins (Tauri origins are always allowed) |
| `SEED_DEV_ACCOUNTS` | on in dev | the two dev accounts |
| `MODEL_ROUTER_URL`, `MODEL_ROUTER_KEY` | unset | LiteLLM router; unset = keyword course search only |
| `MEDIA_TOKEN_MINUTES` | `240` | lifetime of the `?t=` token for video, image and audio URLs |
| `BUILDER_WORKERS`, `BUILDER_PYTHON`, `BUILDER_JOB_TIMEOUT_S`, `BUILDER_MEDIA_KINDS`, `BUILDER_DEEPTUTOR`, `BUILDER_CHAT_WAIT_S` | `1`, gateway's Python, `3600`, all kinds, off, `20` | course builder subprocesses |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | unset | Web Push; any unset = push off |
| `GATEWAY_BACKGROUND_TASKS`, `SCHEDULER_INTERVAL_SECONDS` | `true`, `30` | scheduler loop |
| `MENTOR_MASTER_KEY` | dev/test: generated in `<data dir>/master.key` | urlsafe base64 of 32 bytes; required in prod, from a secret manager |
| `MENTOR_BACKUP_DIR` | `<data dir>/backups` | encrypted snapshots; use different storage |
| `BACKUP_ENABLED`, `BACKUP_HOUR_UTC`, `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY` | on (not in test), `19`, `14`, `8` | daily snapshot job (19 UTC = 02:00 Vietnam) |

## Web Push

Reminders reach a closed app as Web Push once the three `VAPID_*` vars are set. `deploy.sh` generates the pair once. In dev:
`uv run python -m mentor_gateway.cli vapid-generate --env-file .env.dev.local --subject mailto:you@example.com`, then restart the
gateway. Never regenerate a pair in use: browsers subscribed with the old key silently stop receiving pushes. Subscriptions are
sealed with the master key; a 404/410 from the push service deletes them; the lock screen shows a generic line only.

## Encryption and backups

The master key (`MENTOR_MASTER_KEY`) seals each user's random data key (`user_keys`) and Web Push subscriptions, and derives the
key for `ops.db` snapshots. Not encrypted: `workspaces/`, `mirrors/` and `ops.db` itself, so run the data and backup dirs on an
encrypted volume.

Once a day (and on `backup-run`) the scheduler writes `users/<uid>/<snapshot>.mbk` (a `git bundle` of the learner's mirror, only if
it changed) and `ops/<snapshot>.mbk` (SQLite only; on Postgres use the database's own backups), as chunked AES-256-GCM
(format in `backup.py`). Retention keeps the newest snapshot of each of the last 14 days and 8 weeks. `BackupService.forget_user` deletes a user's data key, which makes
every copy of that user's snapshots unreadable (no HTTP endpoint calls it yet).

```powershell
uv run python -m mentor_gateway.cli backup-run [--user <uid> [--force]]
uv run python -m mentor_gateway.cli backup-list [--user <uid>|_ops]
uv run python -m mentor_gateway.cli backup-restore --user <uid> --snapshot <id> --to <dir>
uv run python -m mentor_gateway.cli backup-restore --ops --snapshot <id> --to <file.db>
uv run python -m mentor_gateway.cli rotate-master-key [--generate]     # gateway stopped; MENTOR_NEW_MASTER_KEY=<new>
```

Restore checks every frame, the bundle and `git fsck`. To put a learner back: stop the gateway, replace `mirrors/<uid>.git` with a
bare clone of the restored clone, delete `workspaces/<uid>/`. An ops restore gives a SQLite file to swap in for `ops.db`
(delete the old `-wal` and `-shm`). In the pilot the commands run inside the container:
`docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec gateway python -m mentor_gateway.cli ...`.

## Tests

```powershell
uv run pytest services/gateway -q        # fakes only, no network
```
