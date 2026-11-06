# infra — running the mentor in dev

Pilot deployment on a Linux VM (Caddy + `docker-compose.prod.yml` + `deploy.sh`): see the root README,
"Triển khai lên server (pilot)".

Pieces: **gateway** (`services/gateway`, port 8000), **model router** (LiteLLM, port 4000,
`services/model-router/config.yaml`), **sandbox** per learner (harness; local process or `mentor-sandbox:dev`
container), **web** (`apps/web`, port 3000), **mail**: inbound SMTP on 2525 (in the gateway) and Mailpit on
1025/8025 for outbound magic links.

**`MENTOR_ENV` is required for development.** When it is unset the gateway assumes `prod`: no magic links or
login codes in responses, no `/api/dev/parent-link/verify`, `SANDBOX_BACKEND=local` refused at start-up and
`MENTOR_MASTER_KEY` required. Every command below sets `MENTOR_ENV=dev` explicitly (tests use `test`).

## A. Everything on the host (fastest loop, no Docker)

```bash
uv sync --all-packages
# no model needed: the harness answers with its scripted fake model
MENTOR_ENV=dev MENTOR_DATA_DIR=var SANDBOX_BACKEND=local MENTOR_MODEL_MODE=scripted \
  uv run uvicorn mentor_gateway.app:app --port 8000
# web app (separate shell)
cd apps/web && NEXT_PUBLIC_API_BASE=http://localhost:8000/api npm run dev
```

On Windows, killing the gateway process leaves its harness subprocesses (`mentor_harness.server` on random
localhost ports) running; kill them by hand.

With a real model, start the router first and drop `MENTOR_MODEL_MODE=scripted`:

```bash
FPT_API_BASE=... FPT_API_KEY=... MODEL_ROUTER_MASTER_KEY=sk-dev-master \
  uv tool run --from 'litellm[proxy]' litellm --config services/model-router/config.yaml --port 4000
MENTOR_ENV=dev MENTOR_DATA_DIR=var MODEL_ROUTER_URL=http://localhost:4000 MODEL_ROUTER_KEY=sk-dev-master \
  uv run uvicorn mentor_gateway.app:app --port 8000
```

On Windows set `PYTHONUTF8=1` before starting LiteLLM (PowerShell: `$env:PYTHONUTF8="1"`); otherwise its startup
banner crashes on the console code page and the router never comes up. The first `uv tool run` also downloads
LiteLLM, which can take several minutes.

Chat history: `GET /api/chat/history?date=YYYY-MM-DD` reads `sessions/<date>/s-YYYYMMDD.jsonl` from the mirror
(one session per learner per local day). A phone upload pushes `{type: "upload_received", path, mime_type}`
to open chat sockets.

Logging in: `POST /api/auth/request-link {"email": ...}` returns `dev_link` in dev mode; open it in the browser.
THPT accounts stay in `needs_parent` until the parent links on Zalo. Without a Zalo bot, unlock with
`POST /api/dev/parent-link/verify` (dev only).

Inbound email: set `INBOUND_SMTP_PORT=2525`, then send to the address shown in `/api/me`:

```bash
python -c "import smtplib; smtplib.SMTP('127.0.0.1', 2525).sendmail('a@b.vn', ['<code>@inbox.mentor.local'], b'Subject: hi\n\nxin chao')"
```

or POST a raw message: `curl -X POST 'localhost:8000/internal/email/inbound?rcpt=<code>@inbox.mentor.local' --data-binary @mail.eml`
(needs `X-Internal-Token: $GATEWAY_INTERNAL_TOKEN` when that is set; without it the endpoint answers 403 in prod
and whenever `SANDBOX_BACKEND=docker`, because sandbox containers can reach the gateway).
Production uses neither: Cloudflare Email Routing hands mail to an Email Worker (`infra/cloudflare/email-worker.js`)
that POSTs it, HMAC-signed with `EMAIL_WEBHOOK_SECRET`, to `/webhooks/email/inbound` (README.md section 10).

## B. Docker Compose

```bash
docker build -f sandbox-image/Dockerfile -t mentor-sandbox:dev .        # only for SANDBOX_BACKEND=docker
docker compose -f infra/docker-compose.dev.yml up --build
```

- Default `SANDBOX_BACKEND=local`: the harness runs as a subprocess inside the gateway container.
- `SANDBOX_BACKEND=docker`: one `mentor-sandbox:dev` container per learner, hardened and on its own internal network
  (next section), workspace bind-mounted at `/workspace`, env `MENTOR_SANDBOX_ISOLATED=1`. The gateway talks to the
  Docker daemon through the mounted socket, so it needs the **absolute host path** of its data dir:
  `SANDBOX_BACKEND=docker MENTOR_HOST_DATA_DIR=$(pwd)/var docker compose -f infra/docker-compose.dev.yml up --build`.
- The gateway container runs as the non-root user 4242 (`user:` in compose, overridable with `MENTOR_UID`/`MENTOR_GID`)
  and gets the docker socket through the socket's group: `group_add: ${DOCKER_GID:-0}` (Docker Desktop: `0`; Linux:
  `DOCKER_GID=$(stat -c %g /var/run/docker.sock)`). On Linux the host data dir must be writable by that uid
  (`sudo chown -R 4242:4242 var`, or run with your own `MENTOR_UID=$(id -u) MENTOR_GID=$(id -g)`). On Docker
  Desktop (WSL2) files created from Windows show up as `0:0 rwxrwxrwx` (writable), but files created inside a
  container keep that container's uid (checked 2026-10-30: a `0:0 rw-r--r--` file written by a root container is not
  writable by 4242). A data dir written by the earlier root gateway therefore needs a one-time
  `docker run --rm -v <abs data dir>:/d python:3.11-slim chown -R 4242:4242 /d`.
- Mailpit UI: http://localhost:8025 (magic links when `MENTOR_ENV` is not `dev`).

## Sandbox isolation (docker backend)

Each learner's sandbox must not be able to reach any other sandbox: the harness API (`/v1/turn` with
`/tool read_file ...`, `/v1/jobs`, approvals) reads and writes that learner's workspace. Two independent layers:

1. **Harness token.** At every sandbox start the gateway generates a random `MENTOR_HARNESS_TOKEN`, passes it as
   env and keeps it in memory; the harness answers every endpoint except `GET /v1/health` only with
   `Authorization: Bearer <token>` (constant-time compare; 401 otherwise; 503 if an isolated container has no token).
   Learner code (`run_python`) never sees it: the env allowlist leaves it out and the harness process is
   non-dumpable, so `/proc/<harness pid>/environ` is root-only even for the same uid.
2. **One internal network per sandbox** (`SANDBOX_NETWORK_ATTACH`). On start the gateway runs
   `docker network create --internal mentor-sbx-net-<user>`, attaches the containers listed in
   `SANDBOX_NETWORK_ATTACH` (`container[:alias]`, `self` = the gateway's own container; compose:
   `self:gateway,mentor-dev-model-router-1:model-router`) and starts the sandbox only on that network. The sandbox can
   reach the gateway (`http://gateway:8000`, for `/internal/papers|calendar/*`) and the router
   (`http://model-router:4000`), nothing else: no other sandbox, no internet. Stopping the sandbox disconnects them and
   removes the network.

Why not one shared network with inter-container communication disabled
(`-o com.docker.network.bridge.enable_icc=false`)? ICC applies to *every* pair of containers on that bridge, and the
gateway and the router are containers too: it blocks gateway -> sandbox and sandbox -> router as well (measured on
Docker Desktop 29 / WSL2: a request between two containers on an `--internal`, `enable_icc=false` network times out;
Linux behaves the same, it is the same iptables rule). Re-allowing just those pairs needs host iptables rules or the
legacy `--link`, which user-defined networks do not support. Per-sandbox networks need nothing beyond the Docker API
and work the same on Docker Desktop and Linux.

Limits and notes:
- Each network takes a subnet from the daemon's default address pools; the stock pools give about 30 networks,
  i.e. about 30 sandboxes awake at once (idle ones are stopped after `SANDBOX_IDLE_SECONDS`). For more, give the
  daemon smaller subnets, e.g. in `daemon.json` (Docker Desktop: Settings > Docker Engine):
  `"default-address-pools": [{"base": "10.200.0.0/16", "size": 28}]` (4096 networks of 14 hosts; each sandbox
  network needs 3).
- `self` resolves to the gateway's hostname, which Docker sets to its container id; do not set `hostname:` on the
  gateway service (or list its container name instead of `self`).
- Legacy `SANDBOX_DOCKER_NETWORK` (one shared internal network) still works but leaves sandboxes able to reach each
  other's port 8080 (only the token protects them); the gateway logs a warning. Neither variable: the sandbox port is
  published on 127.0.0.1 (internet access, `run_python` disabled), for a gateway running on the host.

Container hardening (every sandbox): `--user <gateway uid:gid>` (the compose gateway is 4242:4242; a root gateway or
a Windows host uses the image's 4242:4242 and, if the gateway is root, chowns the working copy to it before each
session; `SANDBOX_DOCKER_USER` overrides, root refused), `--read-only` root file system, `--tmpfs
/tmp:rw,nosuid,nodev,noexec,size=$SANDBOX_TMPFS_SIZE,mode=1777` (HOME=/tmp; the image copies its pre-built
matplotlib font cache to `MPLCONFIGDIR=/tmp/.cache/matplotlib` at start), `--cap-drop ALL`,
`--security-opt no-new-privileges`, `--memory 1g --cpus 1 --pids-limit 256`. The workspace bind mount is the only
writable persistent path.

## Parent reports

The mentor drafts a report in `.mentor/report-drafts/<date>.md` (hidden from the learner: the web API never shows
`.mentor/` except the activity log, and the export zip leaves drafts out). `send_parent_report` runs `check_report`
in the sandbox and queues it; the gateway re-runs the leak checks itself (scores, quotes, emails, phone numbers,
private paths), sends it through the parent channel and only then moves it to `reports/<date>.md` with a `system`
commit. `/api/reports` lists only sent reports. A blocked report leaves an audit row `parent_report_blocked` (check
names only). Drafts are committed like any workspace file (the gateway reads them from the mirror), so they are in the
mirror's git history and in encrypted backups, but not in anything the learner can open.

## Zalo bot

Webhooks only (polling loses messages). Set `ZALO_BOT_TOKEN` and `ZALO_WEBHOOK_SECRET` (8–256 chars), expose
`/webhooks/zalo` over HTTPS, then once per deploy:

```bash
uv run python -m mentor_gateway.cli zalo-set-webhook --url https://<public-host>/webhooks/zalo
uv run python -m mentor_gateway.cli zalo-webhook-info
```

Without a token the gateway uses a logging client (messages go to the log, nothing is sent).

## Google Calendar (NCS)

NCS learners can connect their Google Calendar in Settings; the mentor then reads upcoming events and, after the
learner approves each card in chat, adds/changes/deletes events it created. Tokens stay in the gateway (sealed with
`MENTOR_MASTER_KEY`); sandboxes call `/internal/calendar/*`. Without the two env vars below the Settings card says
the integration is unavailable and the calendar tools say so.

One-time setup of an OAuth client (about 10 minutes):

1. https://console.cloud.google.com → project picker → **New project** (e.g. `mentor-dev`) → select it.
2. **APIs & Services → Library** → search "Google Calendar API" → **Enable**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform → Branding / Audience / Data access):
   - User type **External**, app name (e.g. "Mentor dev"), your email as support and developer contact.
   - **Audience**: leave the publishing status **Testing**, and under **Test users** add the Google account(s) you will
     connect (only these can log in while in Testing; refresh tokens of apps in Testing expire after 7 days, so
     reconnect weekly or publish the app later).
   - **Data access → Add or remove scopes**: `openid`, `.../auth/userinfo.email` and
     `https://www.googleapis.com/auth/calendar.events`.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → application type **Web application**:
   - Authorized redirect URIs: `http://localhost:8000/api/integrations/google-calendar/callback`
     (it is `$PUBLIC_BASE_URL/api/integrations/google-calendar/callback`; add one per deployment, https outside dev).
   - No JavaScript origins needed. **Create**, then copy the client ID and secret.
5. Start the gateway with them:

```bash
GOOGLE_OAUTH_CLIENT_ID=1234-abc.apps.googleusercontent.com GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-... \
  MENTOR_ENV=dev MENTOR_DATA_DIR=var uv run uvicorn mentor_gateway.app:app --port 8000
```

6. Web app → log in as an **NCS** learner → Settings → Google Calendar → **Kết nối Google Calendar** → pick the test
   account, tick the calendar permission → you land on `/settings?calendar=connected` showing the account.
   In chat: "lịch tuần này của mình có gì?" (`calendar_list_events`), "thêm hạn nộp paper 16/11 18:59 vào lịch"
   (`calendar_create_event` → approval card → event appears in Google Calendar with the mentor marker).
   "Ngắt kết nối" revokes the grant at Google (also visible at https://myaccount.google.com/permissions).

The browser must reach the gateway at the same host as `PUBLIC_BASE_URL` (the callback needs the `mentor_session`
cookie, set for `localhost`). Calendar tools need a sandbox with `MENTOR_GATEWAY_URL` (set automatically by both
backends).

## Web search and page reading (`web_search`, `web_fetch` tools)

The FPT-hosted model has no built-in search, so the harness tool `web_search` (THPT and NCS, chat turns only)
calls the gateway's `POST /internal/web/search` with the sandbox token, and the gateway asks a search backend.
Sandboxes still have no internet. The gateway picks the backend from its env (restart the gateway after a change):

- **Tavily** (hosted, `TAVILY_API_KEY`): sign up at https://app.tavily.com, copy the API key (`tvly-...`). The free
  plan has a monthly credit allowance (a basic search costs 1 credit; check the current limits on the site).
  Queries go to Tavily in the US, so the tool tells the model to send only generic terms, never learner data.
- **SearXNG** (self-hosted, `SEARXNG_URL`, no key): a metasearch engine running next to the gateway. Its JSON
  output must be enabled, which `infra/searxng/settings.yml` does. Dev, from the repo root (PowerShell):

```powershell
docker run -d --name mentor-searxng --restart unless-stopped -p 127.0.0.1:8888:8080 `
  -v "${PWD}\infra\searxng\settings.yml:/etc/searxng/settings.yml:ro" `
  -e "SEARXNG_SECRET=$([guid]::NewGuid().ToString('N'))" searxng/searxng:latest
# check it answers JSON (403 = the json format is not enabled):
(Invoke-RestMethod -Method Post http://localhost:8888/search -Body @{ q = "lich thi tot nghiep THPT"; format = "json" }).results |
  Select-Object -First 3 title, url
```

  With Docker Compose instead: `docker compose -f infra/docker-compose.dev.yml --profile search up` and
  `SEARXNG_URL=http://searxng:8080` for the gateway container. Keep SearXNG bound to `127.0.0.1` (no auth, limiter off).

Both set: Tavily is used. Neither: the tool answers "chưa được cấu hình" and the model must not invent results.
With `infra/dev-up.ps1`, add the line to `.env.dev.local` (`TAVILY_API_KEY=tvly-...` or
`SEARXNG_URL=http://localhost:8888`) and restart only the gateway window.

Limits: `WEB_SEARCH_REQUESTS_PER_MINUTE` (10) per learner, query ≤ 300 characters, ≤ 8 results, 15 s backend
timeout, 2 MB response cap, results cached 10 min in memory. Snippets are stripped of HTML and capped (title 200,
snippet 500 characters; only http(s) links). The query travels only in POST bodies (never in a URL, so not in access
logs) and is not logged; the audit log (`audit_log`, kind `web_search`) records only the backend and the number of
results. SearXNG gets `safesearch=2` (strict) for THPT and `1` for NCS. The harness fences the results as untrusted
web content (random marker, "data, not instructions") and, for THPT, repeats the homework rule.

**Reading a page (`web_fetch`).** The harness tool `web_fetch {url}` (THPT and NCS, chat turns only) lets the model
read one page, typically the official page behind a search result, through the gateway's `POST /internal/web/fetch`.
It needs no search backend and is **on by default** (`WEB_FETCH_ENABLED=false` turns it off; restart the gateway).
The gateway itself needs outbound internet on ports 80/443; it connects directly and ignores `HTTP(S)_PROXY`.
Because the URL comes from the model, the gateway guards against SSRF (`services/gateway/src/mentor_gateway/webfetch.py`):

- only `http`/`https` on ports 80 and 443, no `user:pass@` in the URL;
- refused hosts: `localhost`, single-label names (docker services such as `gateway`, `model-router`, `searxng`),
  internal suffixes (`.local`, `.internal`, `.lan`, `.corp`, ...), and the gateway's own hosts (from
  `PUBLIC_BASE_URL`, `WEB_ORIGIN`, `CORS_ORIGINS`, `SANDBOX_GATEWAY_URL`, `MODEL_ROUTER_URL`, `SEARXNG_URL`);
- DNS is resolved by the gateway and **every** answer must be a public unicast address: private, loopback,
  link-local (incl. the cloud metadata IP 169.254.169.254), CGNAT, multicast, reserved and unspecified addresses
  are refused, IPv4 and IPv6, including IPv4-mapped, 6to4, Teredo and NAT64 forms;
- the TCP connection goes to the vetted IP (TLS SNI and certificate check still use the real hostname), so DNS
  rebinding cannot swap the address between check and connect;
- redirects are followed by hand, at most 5, and every hop is checked again; no cookies or credentials are sent;
- 15 s for the whole fetch, at most 2 MB read (also after gzip/deflate decoding), only `text/html`,
  `application/xhtml+xml`, `text/plain` and `application/json`. A PDF answers 415 `pdf` (see below).

HTML becomes readable text (stdlib `html.parser`: script, style, nav, footer and similar dropped, link text kept,
whitespace collapsed), capped at 20 000 characters (`truncated: true`). Limit: `WEB_FETCH_REQUESTS_PER_MINUTE` (10)
per learner. The URL path and query may hold personal data, so only the host and the status are logged (audit
kind `web_fetch`). The harness fences the page like search results, adds the THPT homework rule, and tells the
model to cite the page URL.

**PDF links (arXiv, conference papers).** The gateway does **not** parse PDFs: it holds the keys and the Docker
socket, and PDF parsers have a long CVE history. `POST /internal/web/download` only downloads the bytes, with the
same SSRF rules, redirect checks and rate limit as `/fetch`, 60 s, at most `WEB_FETCH_PDF_MAX_MB` (default 30;
bigger files are refused, not truncated), and only if the `%PDF-` magic is in the first 1 KB of the body,
whatever the content type says. It returns them as `application/pdf` (no base64 in JSON). The learner's sandbox,
isolated and without internet, saves the file as `inbox/web/<YYYY-MM-DD>-<host>-<slug>.pdf` (identical bytes
already there are reused), extracts the first 20 000 characters with `pdf_extract` (pypdf) and returns them fenced
like a page, with the page count and the saved path so the model can read further pages. A PDF with no text
layer (a scan) gets PNG images of its first 3 pages (`pdf_render`, pypdfium2) for `look_at_image`; there is no
OCR. Changing the cap needs a gateway restart; the renderer needs a sandbox image rebuild
(`docker build -f sandbox-image/Dockerfile -t mentor-sandbox:dev .`).

## Web Push (nudges while the app is closed)

Nudges (CONTRACTS section 9) go over the open chat WebSocket; when the learner has none open and a browser
subscribed, the gateway sends a Web Push instead (same proactivity, quiet hours and daily cap). Push is off until
`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` are all set.

- Production: `deploy.sh` generates the key pair once with openssl and sets `VAPID_SUBJECT=https://$DOMAIN`.
- Dev: generate once and add the three lines to `.env.dev.local` (loaded by `dev-up.ps1`), then restart the gateway:
  ```powershell
  $env:PYTHONUTF8 = "1"; uv run python -m mentor_gateway.cli vapid-generate --subject mailto:you@example.com
  # or append them (skipped if the file already has VAPID keys):
  uv run python -m mentor_gateway.cli vapid-generate --env-file .env.dev.local --subject mailto:you@example.com
  ```
- **Never regenerate** a key pair that is in use: browsers subscribed with the old public key silently stop
  receiving pushes (they resubscribe the next time the web app asks).
- Subscriptions (endpoint URL + keys, personal data) are sealed with `MENTOR_MASTER_KEY` and re-wrapped by
  `rotate-master-key`. Endpoints must be https on a known push service (FCM, Mozilla, Windows, Apple); the gateway
  never posts anywhere else. A 404/410 from the push service deletes the subscription.
- A push never shows the mentor's own text on the lock screen: it carries a generic Vietnamese line per kind and
  the notification id; the app shows the details.

## Gateway environment

| Var | Default | |
|---|---|---|
| `MENTOR_ENV` | `prod` | `dev` returns magic links in the response and allows the local backend; **unset = prod** |
| `MENTOR_DATA_DIR` | `var` | `ops.db`, `mirrors/<user>.git`, `workspaces/<user>/`, `logs/`. On Windows keep this path short: git object paths inside it can exceed MAX_PATH. |
| `MENTOR_DATABASE_URL` | sqlite in data dir | any SQLAlchemy URL (Postgres works) |
| `MENTOR_CONTENT_DIR` | `<repo>/mentor-content` | templates, skills, curricula for provisioning |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | gateway URL in magic links |
| `WEB_ORIGIN` | `http://localhost:3000` | web app: CORS + WebSocket origin (with credentials), redirect after login, phone upload page `/m/{token}` |
| `CORS_ORIGINS` | | extra comma-separated origins (e.g. the Tauri pop-up) |
| `SANDBOX_BACKEND` | `local` | `local` or `docker` |
| `SANDBOX_IDLE_SECONDS` | `900` | idle sandboxes are stopped |
| `SANDBOX_PREWARM` | `1` | start a learner's sandbox in the background when they open the chat or pop-up (WebSocket connect, `POST /api/sandbox/warm` on focus; max once a minute per learner), hiding the cold start. `0` turns it off, e.g. when sandboxes are scarce (each warm-up keeps one awake for up to `SANDBOX_IDLE_SECONDS`) |
| `SANDBOX_NETWORK_ATTACH` | | docker backend: `container[:alias],...` attached to each sandbox's own internal network (`self` = this gateway). Set = per-sandbox networks (see "Sandbox isolation") |
| `SANDBOX_DOCKER_NETWORK` | | docker backend, legacy: one internal network shared by all sandboxes (token-only separation) |
| `SANDBOX_DOCKER_USER` | gateway's uid:gid (4242:4242 if root/Windows) | `--user` of sandbox containers; root is refused |
| `SANDBOX_TMPFS_SIZE` | `256m` | size of the sandbox's `/tmp` tmpfs (its root fs is read-only) |
| `SANDBOX_IMAGE`, `MENTOR_HOST_DATA_DIR` | `mentor-sandbox:dev` | docker backend |
| `MODEL_ROUTER_URL`, `MODEL_ROUTER_KEY`, `MENTOR_MODEL_MODE` | | passed to the sandbox |
| `INBOUND_EMAIL_DOMAIN`, `INBOUND_SMTP_PORT` | `inbox.mentor.local` | inbound email |
| `GATEWAY_INTERNAL_TOKEN` | | `X-Internal-Token` for `POST /internal/email/inbound`; without it that endpoint is closed in prod and with `SANDBOX_BACKEND=docker` |
| `EMAIL_WEBHOOK_SECRET` | | HMAC key shared with the Cloudflare Email Worker (`infra/cloudflare/email-worker.js`) for `POST /webhooks/email/inbound` (CONTRACTS section 5); unset = that endpoint answers 404. Production setup: README.md section 10 |
| `INBOUND_EMAIL_MAX_BYTES` | `26214400` (25 MiB) | largest raw inbound message, every path (webhook 413, SMTP and `/internal` drop it) |
| `EMAIL_WEBHOOK_PER_RCPT_PER_HOUR` | `30` | per learner address, `POST /webhooks/email/inbound` (429 + `Retry-After`) |
| `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | `1025` | outbound login mail (magic link + 6-digit code); unset host = nothing sent |
| `SIGNUP_ALLOWLIST` | empty (open) | comma-separated emails and/or `@domain` entries allowed to log in; others get 403 "chưa được mời" |
| `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_USERNAME`, `SMTP_PASSWORD` | off | authenticated relay, e.g. Gmail: `smtp.gmail.com`, `587`, `SMTP_STARTTLS=true`, the address + an app password (or `465` + `SMTP_SSL=true`). A username without STARTTLS/SSL is refused (no credentials in plaintext); a send failure answers 502 |
| `ZALO_BOT_TOKEN`, `ZALO_WEBHOOK_SECRET`, `ZALO_BOT_NAME`, `ZALO_BOT_URL` | | parent channel. `ZALO_BOT_URL` is the bot's share link (QR on the onboarding page); unset hides the QR |
| `GATEWAY_BACKGROUND_TASKS`, `SCHEDULER_INTERVAL_SECONDS` | `true`, `30` | scheduler loop |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | | Google Calendar for NCS (see above); unset = unavailable |
| `CALENDAR_REQUESTS_PER_MINUTE` | `30` | per learner, `/internal/calendar/*` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | | Web Push for nudges (see "Web Push"); any unset = push off. Keys: base64url, public = uncompressed P-256 point (87 chars), private = raw 32-byte scalar (43 chars); subject `mailto:` or `https:` |
| `S2_API_KEY` | | optional Semantic Scholar REST key (fallback for `paper_get`; search without it often gets HTTP 429) |
| `PAPER_REQUESTS_PER_MINUTE` | `20` | per learner, `/internal/papers/*` |
| `ASTA_API_KEY` | | Ai2 Asta Scientific Corpus Tool key (sent as `x-api-key`). Without it Asta still answers `get_paper`/citations (~6 s) and search (~35 s), but snippet search never returns; with it Asta becomes the default `paper_search` source. Request one at https://share.hsforms.com/1L4hUh20oT3mu8iXJQMV77w3ioxm (Ai2 approves by hand; Gmail addresses may be rejected, use an institutional email). License: academic / non-commercial only, attribution required (the tools add it), Ai2 may use the queries, so only keywords and paper ids are sent |
| `ASTA_MCP_URL` | `https://asta-tools.allen.ai/mcp/v1` | Asta MCP endpoint; `off` disables Asta (search defaults to arXiv, snippets/citations return 503) |
| `ASTA_TIMEOUT_SECONDS` | `40` | per Asta call; on timeout search falls back to arXiv and that Asta tool is skipped for 2 min |
| `TAVILY_API_KEY` | | `web_search` backend, hosted (https://app.tavily.com, key `tvly-...`). Preferred when both backends are set. Queries go to Tavily (US) |
| `SEARXNG_URL` | | `web_search` backend, self-hosted SearXNG with the JSON format on, e.g. `http://localhost:8888` (compose: `http://searxng:8080`). Neither var set = the tool answers "chưa được cấu hình" |
| `WEB_SEARCH_REQUESTS_PER_MINUTE` | `10` | per learner, `POST /internal/web/search` |
| `WEB_FETCH_ENABLED` | `true` | `web_fetch` tool (`POST /internal/web/fetch`, SSRF-checked page reader); independent of the search backend. `false` = the tool answers "chưa được cấu hình" |
| `WEB_FETCH_REQUESTS_PER_MINUTE` | `10` | per learner, `POST /internal/web/fetch` and `/download` together |
| `WEB_FETCH_PDF_MAX_MB` | `30` | largest PDF `web_fetch` downloads (`POST /internal/web/download`), 1..200 MB; bigger files are refused, not truncated. HTML pages stay at 2 MB |
| `MENTOR_MASTER_KEY` | dev/test: generated at `$MENTOR_DATA_DIR/master.key` | urlsafe base64 of 32 bytes. **Required outside dev/test**; from a secret manager. See below |
| `MENTOR_BACKUP_DIR` | `$MENTOR_DATA_DIR/backups` | encrypted snapshots; put it on different storage than the data dir |
| `BACKUP_ENABLED` | on, except `MENTOR_ENV=test` | daily snapshot job in the scheduler loop |
| `BACKUP_HOUR_UTC` | `19` (02:00 Vietnam) | the job runs once per UTC day at/after this hour |
| `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY` | `14`, `8` | retention per learner and for ops.db |

## Encryption at rest and backups

**What the app encrypts.** The ops DB keeps sensitive fields sealed with AES-256-GCM (`mentor_gateway/crypto.py`),
each bound by its AAD to its row/owner so a blob copied elsewhere does not open:

| Data | Where | AAD | Lookup |
|---|---|---|---|
| Parent's Zalo chat id | `parent_contacts.zalo_chat_enc` (`parent_links.zalo_chat_id` is no longer written) | `parent_contacts:zalo_chat_id:<student>` | `zalo_chat_bidx` = HMAC-SHA256 blind index (key HKDF'd from the master key), used by the webhook's `get_by_chat` |
| Audit details (consent: chat id + parent's Zalo name; crisis alerts) | `audit_log.detail`, prefixed `enc1:` | `audit_log:detail:<student>:<kind>` | none (read with `SqlParentLinkStore.read_audit`) |
| Google Calendar tokens, OAuth PKCE verifier | `google_calendar_links`, `oauth_states` | `gcal-refresh:<uid>`, `gcal-access:<uid>`, `oauth-verifier:<state>` | |
| Per-user data keys | `user_keys.sealed_key` | `user-key:<uid>` | |

There is no parent phone number anywhere (the Zalo bot only gives a chat id). No migrations exist: **dev databases
are disposable**; delete `var/ops.db*` after pulling this change (an old DB still opens, but a linked parent's chat
id in the old plaintext column is only read, never searched, until the link is saved again).

**What the app does not encrypt.** Learner working copies (`workspaces/<uid>/`) and mirrors (`mirrors/<uid>.git`)
are plaintext: the sandbox and git need the files. ops.db itself is a plain SQLite file apart from the sealed
columns. **Production must therefore run the data dir (and the backup dir) on an encrypted volume** (Azure Disk
Encryption / encryption at host with a customer-managed key, LUKS/dm-crypt on bare VMs), with the host, not the
app, holding that key.

**Key hierarchy.**

```
MENTOR_MASTER_KEY (secret manager: Azure Key Vault / AWS Secrets Manager / Vault; never in git or the image)
 ├─ seals sensitive columns (table above)
 ├─ HKDF "mentor:blind-index"  -> HMAC key for blind indexes
 ├─ HKDF "mentor:ops-backup"   -> ops.db snapshots
 └─ seals each learner's random 32-byte data key (user_keys)
      └─ HKDF(data key, per-file salt) -> that learner's snapshots
```

**Crypto-shredding.** `DELETE /api/account` deletes the learner's data key (SQLite `secure_delete` + WAL
checkpoint), deletes their local snapshot files (and calls the uploader's `delete`), and rewrites every local ops.db
snapshot without that learner's rows (wrapped key included; `audit_log` is kept as the legal record). Copies of
learner snapshots anywhere else (object storage, tapes) are then undecryptable. Copies of *ops* snapshots outside
the backup dir still contain the wrapped key until they age out, so give the object-storage bucket a lifecycle
rule no longer than the retention window (8 weeks) and no object versioning beyond it.

**Snapshots.** Once a day (`BACKUP_HOUR_UTC`) the scheduler, or `backup-run` by hand, writes
`users/<uid>/<YYYYMMDDTHHMMSSZ>.mbk` for every mirror whose `main` moved since its last snapshot (`git bundle
--all`, streamed through encryption with no plaintext on disk) and `ops/<id>.mbk` (sqlite online backup, SQLite
only; on Postgres use the database's own backups). Retention keeps, per learner and for ops, the newest snapshot of
each of the last `BACKUP_KEEP_DAILY` days and `BACKUP_KEEP_WEEKLY` ISO weeks that have one (UTC), and always the
newest. Unchanged learners keep their last snapshot indefinitely.

File format `MBK1` (chunked AES-256-GCM): `"MBK1" | u32be header length | JSON header (plaintext, authenticated:
kind, owner, snapshot, created_at, head, chunk size, 32-byte salt) | frames`, each frame `u32be plaintext length |
ciphertext+tag` of up to 1 MiB. File key = HKDF-SHA256(data key or ops key, salt, "mentor-backup-v1"); nonce =
4 zero bytes + u64be frame index; AAD = SHA-256(magic+length+header) + u64be index + final-flag byte. The last frame
carries final=1 and nothing may follow, so truncation, reordering, header edits and appended data all fail.

Off-box copies: `BackupService(..., uploader=...)` takes any object with `upload(local_path, key)` and
`delete(key)` (`key` = path relative to the backup dir); only the local no-op `LocalOnly` exists today. An
S3-compatible implementation is a few lines with boto3.

```bash
uv run python -m mentor_gateway.cli backup-run [--user <uid> [--force]]
uv run python -m mentor_gateway.cli backup-list [--user <uid>|_ops]
uv run python -m mentor_gateway.cli backup-restore --user <uid> --snapshot <id> --to /tmp/restore-<uid>
uv run python -m mentor_gateway.cli backup-restore --ops --snapshot <id> --to /tmp/ops-restored.db
```

Restore checks every frame's tag, that the header names that learner and snapshot, `git bundle verify`, that the
clone's HEAD is the recorded head, and `git fsck`; the result is a normal clone of `main` (no remote). To put a
learner back: stop their sandbox, replace `mirrors/<uid>.git` with `git clone --bare` of the restored clone, delete
`workspaces/<uid>/` (it is re-cloned on the next turn). An ops restore yields a plain SQLite file to swap in for
`ops.db` with the gateway stopped (delete the old `-wal`/`-shm` files).

**Rotating the master key.** Learner data keys never change, so no snapshot needs re-encrypting; rotation re-wraps
what the master key protects. With the gateway stopped:

```bash
MENTOR_MASTER_KEY=<old> MENTOR_NEW_MASTER_KEY=<new> uv run python -m mentor_gateway.cli rotate-master-key
# or --generate (prints the new key once). In dev without MENTOR_MASTER_KEY it rewrites var/master.key.
```

This re-wraps `user_keys`, `parent_contacts` (and recomputes blind indexes), `audit_log`, Google Calendar tokens
in one transaction (all or nothing; pending OAuth states are dropped), then re-encrypts the local ops snapshots.
Then store the new key in the secret manager and start the gateway. Keep the old key version (disabled) until the
retention window has passed: off-box ops snapshots taken before the rotation still need it. A new sealed column
must be added to `ROTATORS` in `mentor_gateway/rotation.py`. Rotate on a schedule (e.g. yearly) and immediately if
the key may have leaked; a leaked key plus a copy of ops.db exposes every sealed field and every learner backup.

## Desktop app downloads (prod)

The web app's setup guide ("Cài app máy tính") links to the desktop packages. Both links are build args
of the web image (`docker-compose.prod.yml`, `NEXT_PUBLIC_*`, inlined at build time, so a change needs
`docker compose build web`), set in `infra/.env.prod`; empty hides them:

- `DESKTOP_DOWNLOAD_URL`: the Windows installer, `dist/Mentor-Setup-<version>.exe` from
  `apps/desktop/build-release.ps1`. Shown to everyone except Linux desktops that have a Linux link.
- `DESKTOP_DOWNLOAD_URL_LINUX`: the Linux package, `dist/Mentor_<version>_amd64.deb` (or the
  `Mentor-<version>-x86_64.AppImage`) from `apps/desktop/build-linux.sh`, which runs on this VM
  (Docker builder `infra/desktop-linux.Dockerfile`). Shown to Linux desktop browsers (not Android,
  ChromeOS); without it they get the Windows link as before. Link the .deb (it works for Ubuntu
  22.04/24.04 users with `sudo apt install ./...`) and send the AppImage on request.

Host the files anywhere over https (the `.sha256` files next to them let users check a download); the
packages carry the web origin they were built for, so rebuild them when `DOMAIN` changes. The
`apps/desktop/README.md` has the build details.

## Tests

```bash
uv run pytest services/gateway -q                       # fakes only, no network
MENTOR_IT_HARNESS=1 uv run pytest services/gateway/tests/test_gw_integration_harness.py -q   # real harness, scripted
MENTOR_IT_HARNESS=1 MENTOR_IT_DOCKER=1 uv run pytest services/gateway/tests/test_gw_integration_harness.py -q
```
