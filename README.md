# mentor

One learning app for students from grade 1 to university, and for teachers. Students see four things (Courses, Practice,
Ask, Progress); teachers drop in material and review the course an agent drafts. Everything else (lesson building, the weekly
plan, reminders) is done by agents on the server. Product spec: `../REQUIREMENTS-PLAN.md`. Interfaces: [CONTRACTS.md](CONTRACTS.md).

## Layout

| Path | What |
|---|---|
| `apps/app` | The app: Vite + React 19 + TypeScript, packaged with Tauri 2 for desktop; also the web/PWA build |
| `packages/mentor-schemas` | Shared pydantic contracts (course packs, practice, planner, events, notifications) |
| `packages/mentor-mascot` | The mascot "Mực" as a framework-free custom element |
| `services/gateway` | FastAPI backend: login, ops DB, catalog and course packs, practice, Ask, planner, reminders, teacher authoring |
| `services/course-builder` | Course-builder agent (`mcb`): intake, outline, lessons, quizzes, media. The gateway runs it as subprocesses |
| `services/model-router` | LiteLLM config that maps model aliases to the FPT endpoint |
| `mentor-content` | Content that ships with the server: `courses/` (published course packs), `bank/` (question bank), `curricula/`, `exam-profiles.json`, agent skills |
| `sandbox-image/harness`, `sandbox-image/scripts` | Agent-loop library for the server-side agents; `mentor_scripts` (BKT mastery) is used by the practice engine |
| `evals` | Scenario evals with synthetic personas |
| `infra` | Docker Compose (dev, demo, pilot), `deploy.sh`, `dev-up.ps1`; see [infra/README.md](infra/README.md) |

## Run (Windows PowerShell)

Setup once: `uv sync --all-packages --python 3.11`, and `pnpm install` in `apps/app`.

```powershell
# Gateway. MENTOR_ENV must be set: unset means prod (no dev accounts, MENTOR_MASTER_KEY required).
$env:MENTOR_ENV="dev"; $env:MENTOR_DATA_DIR="var-dev"
uv run uvicorn mentor_gateway.app:app --port 8000
# dev accounts: hocsinh / 123456 (student), giaovien / 123456 (teacher)

# App in the browser, no backend (in-browser mock)
cd apps/app; $env:VITE_API_MOCK="1"; pnpm dev            # http://localhost:5173

# App against the gateway (default API is http://localhost:8000/api)
cd apps/app; $env:VITE_API_BASE="http://localhost:8000/api"; pnpm dev

# Desktop window
cd apps/app; $env:VITE_API_MOCK="1"; pnpm tauri dev
```

Model router and everything together: put `FPT_API_BASE`, `FPT_API_KEY` and `MODEL_ROUTER_MASTER_KEY` in `.env.dev.local`
(gitignored), then `powershell -ExecutionPolicy Bypass -File infra\dev-up.ps1` (add `-Desktop` for the Tauri window).
Without a router the gateway still runs; course search falls back to keyword search and the agents cannot call a model.

### Course builder

A teacher uploads material in the app; the gateway runs the builder stages as subprocesses (`mcb job ...`, interpreter
`BUILDER_PYTHON`, default the gateway's own) and keeps their state under `<MENTOR_DATA_DIR>/builder`. The CLI also works by hand:

```powershell
uv run mcb intake <files> --out work/intake
uv run mcb outline work/intake
uv run mcb build work/intake --outline work/intake/outline.json --out work/course
```

Builder stages call the model router (`MODEL_ROUTER_URL`, `MODEL_ROUTER_KEY`).

### Tests

Run only what you touched:

```powershell
uv run pytest services/gateway -q                  # gateway, fakes only, no network
uv run pytest services/course-builder -q
pnpm -C apps/app test; pnpm -C apps/app build
```

## Content and releases

Published courses live in `mentor-content/courses/<course-id>/<version>/` (`pack.json` plus assets) with a `catalog.json`.
A new course or version reaches students through the gateway; **no new app is needed**. Releasing the app itself (desktop
installers and updater feed, web build) is a separate pipeline: see [RELEASING.md](RELEASING.md).

## Pilot deployment (one Linux VM)

Caddy (automatic HTTPS, the only open ports 80/443) sends `/api/*` to the **gateway** and everything else to **web** (the static
`apps/app` build); **model-router** (LiteLLM) calls the FPT models. Files: `infra/docker-compose.prod.yml`, `infra/Caddyfile`,
`infra/web.Dockerfile`, `infra/.env.prod.example`, `infra/deploy.sh`. Learners use `https://<DOMAIN>` or the desktop app.

1. VM with Docker (Ubuntu 22.04/24.04), ports 22/80/443 open, a DNS A record for `DOMAIN` (or `<ip-with-dashes>.sslip.io`),
   and an FPT key (`FPT_API_BASE`, `FPT_API_KEY`).
2. Copy the repo to the VM (or `git clone`), then `bash infra/deploy.sh`: the first run creates `infra/.env.prod` and generates
   `MENTOR_MASTER_KEY`, `MODEL_ROUTER_MASTER_KEY` and the Web Push keys. Fill `DOMAIN`, `FPT_API_BASE`, `FPT_API_KEY`, run it
   again (checks, build, start, wait for health). Copy `MENTOR_MASTER_KEY` to a password manager: without it, backups and
   sealed fields cannot be read.
3. Create accounts (there is no sign-up): `bash infra/deploy.sh user USERNAME student|teacher`.

Daily: `deploy.sh status`, `logs [svc]`, `update` (pull, rebuild, restart; data is kept), `backup`, `down`. Data lives in
`DATA_DIR` (default `/srv/mentor/data`), encrypted snapshots in `BACKUP_DIR`; put both on an encrypted disk. Details:
[infra/README.md](infra/README.md).

Before real learners: the gateway sends learner data to the model provider (FPT, models prefixed `Alibaba:` in
`services/model-router/config.yaml`), so check the provider's data terms and get consent where the learners are minors.

## Local demo (Linux + Docker)

`bash infra/demo.sh` (first run creates `infra/.env.demo`; fill `FPT_API_BASE`, `FPT_API_KEY`, run again), then open
`http://localhost:3000` and sign in with the dev accounts. Also `logs`, `stop`, `reset`. Dev mode, bound to this machine only.
