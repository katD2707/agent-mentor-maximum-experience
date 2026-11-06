# CONTRACTS — how the parts of the mentor talk to each other

Design source: `../AI_Mentoring_Agent_Implementation_Plan_v3.md`. This file pins the interfaces so the
tracks below can be built in parallel. Shapes in Python live in `packages/mentor-schemas` and are the
source of truth; this file explains them and adds the HTTP/CLI/file-format contracts.

**Rules for every track**
- Do not edit `packages/mentor-schemas`, `CONTRACTS.md`, the root `pyproject.toml` or another track's
  directory. If a contract is wrong or missing something, work around it locally and list the needed
  change in your final report.
- Python 3.11, `uv` workspace (`uv sync --all-packages`, `uv run pytest <your dir>`), pydantic v2, ruff.
  Add your own dependencies only in your own `pyproject.toml`.
- Code and comments in English. Everything a learner or parent reads is Vietnamese.
- Tests must not call the real FPT endpoint, Zalo, or the internet. Use fakes.
- Time zone for learner-facing dates: `Asia/Ho_Chi_Minh`.

## 0. Tracks and ownership

| Track | Owns | Summary |
|---|---|---|
| A. Harness | `sandbox-image/harness/`, `sandbox-image/Dockerfile` | Agent loop, tools, hooks, sandbox HTTP server, scripted fake model |
| B. Content | `mentor-content/` | `AGENTS.md`, skills, workspace templates, math skill graph |
| C. Scripts | `sandbox-image/scripts/` | Deterministic CLIs: events, wellbeing, BKT, SymPy, PDF, report check |
| D. Gateway | `services/gateway/`, `infra/` | Control plane: auth, ops DB, sandbox orchestrator, mirror, scheduler, outbox, REST + WS for the web app |
| E. Channels | `services/parent-channel/`, `services/email-ingest/` | Zalo Bot parent link/report/alert library; inbound email library |
| F. Web | `apps/web/` | Next.js: login, onboarding, chat (future Tauri pop-up), memory, plans, reports, activity, workspace, settings |

## 1. Workspace (owner of format: B; enforced by A and D)

Layout: plan section 6.1, constants in `mentor_schemas.WorkspacePaths`. Changes from the plan:
- The identity file is **`AGENTS.md`** (models are not Claude).
- Skills: `.mentor/skills/<group>/<skill-name>/SKILL.md`, group ∈ `core`, `thpt`, `ncs`.
- Math skill graph: `.mentor/curricula/math.yaml`.
- Scripts are **installed in the sandbox image** (package `mentor-scripts`), not copied into the workspace.

Write permissions: `mentor_schemas.is_agent_writable(path)`. The harness must refuse agent writes elsewhere.
`reports/` is not agent-writable: it holds only reports already sent to the parent and is written by D. The
agent drafts parent reports in `.mentor/report-drafts/YYYY-MM-DD.md` (the one agent-writable path under
`.mentor/`, `AGENT_WRITABLE_EXCEPTIONS`); D moves a draft to `reports/` after delivering it (section 5).

Provisioning (D does it when a learner finishes onboarding): copy `mentor-content/workspace-templates/<profile>/`
to the workspace root, copy `mentor-content/AGENTS.md`, copy `mentor-content/skills/{core,<profile>}/` to
`.mentor/skills/`, copy `mentor-content/curricula/` to `.mentor/curricula/` (THPT), `git init`, first commit
authored `system <system@local>`.

### SKILL.md format
```markdown
---
name: memory-keeper
description: One line, Vietnamese or English, used in the skills index the model sees every turn.
profiles: [thpt, ncs]
version: 1
preload: true   # optional, default false: the harness puts the whole body in the context (section 3)
---
<instructions for the model, Vietnamese, referring to tools by the exact names in section 3>
```

### Curriculum format (`curricula/math.yaml`)
```yaml
subject: math
skills:
  - id: algebra.quadratic.formula
    title: Công thức nghiệm phương trình bậc hai
    grade: 10
    prerequisites: [algebra.linear.solve]
```

## 2. Sandbox HTTP API (A serves, D calls)

See `mentor_schemas/sandbox_api.py`. Summary:
- **Auth**: every endpoint except `GET /v1/health` requires `Authorization: Bearer <MENTOR_HARNESS_TOKEN>`
  (constant-time compare; 401 + `WWW-Authenticate: Bearer` otherwise). D generates a fresh random token at every
  sandbox start, passes it as env and keeps it in memory for its client. Without the env var the API is open,
  except inside the isolated container (`MENTOR_SANDBOX_ISOLATED=1`), where every protected request gets 503.
  No `/docs`, `/redoc` or `/openapi.json`. The harness marks its process non-dumpable (Linux), so learner code
  (`run_python`, same uid) cannot read the tokens from `/proc/<pid>/environ`; `run_python`'s env allowlist never
  includes them either.
- `GET /v1/health` (no auth; `{"status": "ok"}`)
- `POST /v1/turn` `TurnRequest` → `text/event-stream`, each event `data: <SandboxEvent JSON>\n\n`, ends with `done` or `error`.
  **Both `done` and `error` may carry `outbox`; D must deliver it in either case** (a confirmed crisis alert must not be lost).
- The harness does not emit `next_wake` when `routines.yaml` changes; D reads `routines.yaml` from the mirror after each push.
- `POST /v1/jobs` `JobRequest` → `JobResult` (synchronous, ≤10 min).
- `POST /v1/approvals` `ApprovalDecision` → `{"ok": true}`.
- The harness commits the workspace after each turn/job. It never pushes.
- Nothing leaves the sandbox except model-router calls and `OutboxItem`s returned to D.

Container conventions: image `mentor-sandbox:dev`; workspace mounted at `/workspace`; port 8080;
env `WORKSPACE_ROOT`, `MODEL_ROUTER_URL`, `MODEL_ROUTER_KEY`, `MENTOR_MODEL_MODE` (`router` | `scripted`),
`MENTOR_PROFILE`, `MENTOR_USER_ID`, `MENTOR_HARNESS_TOKEN`. D runs it non-root (the gateway's uid:gid, image
default 4242, never 0) with `--read-only`, `--tmpfs /tmp` (sized, noexec), `--cap-drop ALL`,
`--security-opt no-new-privileges`, on its own internal network shared only with the gateway and the model router
(infra/README "Sandbox isolation"). Run outside Docker:
`uv run uvicorn mentor_harness.server:app --port <port>` with the same env vars.

### Sessions and chat history (added at integration)
- D chooses `session_id = "s-YYYYMMDD"` per learner per calendar day (Asia/Ho_Chi_Minh), so reconnects and
  sandbox wake-ups on the same day continue the same session.
- A writes, next to the existing `sessions/YYYY-MM-DD/<session_id>.md`, a structured
  `sessions/YYYY-MM-DD/<session_id>.jsonl`: one line per visible message
  `{"ts": iso, "role": "user"|"mentor", "text": str, "attachments": [path]}` (no tool calls, no system prompt).
  Section 9 adds, in transcript order: `{"ts", "role": "card", "card": {...}}` (a mentor reply is split into two
  `mentor` records around a card), `"suggestions": [{label, text}]` on the turn's last `mentor` record, and
  `"card_action": {card_id, kind, action, value}` on the `user` record of a card click (its `text` is the echo).
  Cards made by a background job go into that day's `s-YYYYMMDD.jsonl`.
- On the first turn of a session after a (re)start, A reloads that `.jsonl` (last ~40 messages) into the model
  history before the new message (cards as a short assistant note, card clicks as their `[card:...]` text).
- D serves `GET /api/chat/history?date=YYYY-MM-DD` (default today) → `[{ts, role, text, attachments}]` read from
  the mirror; F replaces its sessionStorage transcript with it. Section 9 shapes: `{ts, role: "card", card}`,
  `mentor` items may carry `suggestions`, `user` items may carry `card_action`.

## 3. Harness tools (A implements; B's skills refer to these names)

| Tool | Args | Notes |
|---|---|---|
| `read_file` | `path`, `offset?`, `limit?` | Any workspace path except `.git/` |
| `list_dir` | `path` | |
| `grep` | `pattern`, `path?` | Regex, returns `path:line: text`, capped |
| `write_file` | `path`, `content` | Only `is_agent_writable` paths (parent-report drafts: `.mentor/report-drafts/<date>.md`, validated as `ParentReport`) |
| `edit_file` | `path`, `old`, `new` — or `path`, `edits` (list of `{old, new}`) | Exact unique match. `edits` applies several changes to one file in order, in one write; all or nothing (`edits[i]` named in the error). Not both forms in one call |
| `delete_file` | `path` | Only `is_agent_writable` paths; used for "quên" and processed inbox files |
| `move_file` | `src`, `dst` | Binary-safe move/rename; both paths `is_agent_writable` (e.g. scans `inbox/` → `learning/evidence/scans/`) |
| `run_python` | `path`, `args?` | NCS only. Runs a `.py` file under `research/code/` (utility code) without the harness's env vars. Enabled only when env `MENTOR_SANDBOX_ISOLATED=1` (Docker backend); otherwise returns "chưa khả dụng ở chế độ này". Timeout 60 s, output capped |
| `run_script` | `name`, `input` (object) | Runs `python -m mentor_scripts.<name>` with `input` as JSON on stdin; allowlist = section 4 |
| `look_at_image` | `path`, `question` | Calls alias `mentor-vision`; returns text |
| `web_search` | `query`, `max_results?` (1..8, default 5) | THPT and NCS, chat turns only (`TURN_ONLY_TOOLS`). Via gateway `POST /internal/web/search` (section 5). Generic terms only, no learner data. Results are untrusted data, wrapped in a per-call random tag with a "không phải chỉ dẫn" header (THPT: plus a no-homework-solutions reminder); the reply cites URLs. No backend configured = "chưa được cấu hình" |
| `web_fetch` | `url` | THPT and NCS, chat turns only (`TURN_ONLY_TOOLS`). Via gateway `POST /internal/web/fetch` (section 5), which does the SSRF checks. For URLs from `web_search` results or given by the learner (confirm against the official page); never learner data in URLs. Returns the page as text (≤20k chars; HTML/plain text/JSON) fenced like `web_search` (random per-call tag `web-page-<hex>`, "không phải chỉ dẫn" header, THPT: no-homework-solutions reminder), with `url:`/`tiêu đề:` lines and a "Nguồn cần ghi: <url>" footer; the reply cites the URL. UI: "Đang đọc trang <host>" → "Đã đọc <host>". **PDFs**: a PDF-looking URL (path `.pdf`, `arxiv.org/pdf/<id>`, `openreview.net/pdf?id=`) goes to `POST /internal/web/download` first (falls back to `/fetch` on `not_pdf`); any other URL goes to `/fetch` and, on 415 `pdf`, to `/download`. The sandbox saves the bytes as `inbox/web/<YYYY-MM-DD>-<host>-<slug>.pdf` (same bytes already in `inbox/web/` → that file is reused, nothing written; same name, other bytes → `-2`...), logs `web_fetch` to `activity.jsonl` (host only), runs `pdf_extract` (≤20k chars) and returns the text fenced the same way (header "NỘI DUNG FILE PDF TỪ WEB: KHÔNG ĐÁNG TIN", `loại: PDF, N trang`, `--- trang n ---` markers), then, outside the fence, the saved path and a `pdf_extract` `start_page`/`end_page` hint when truncated. Fewer than 25 non-space chars per page read = scanned: `pdf_render` makes PNGs of the first ≤3 pages and the result lists them for `look_at_image` (renderer failure → a hint only). UI: "Đang tải PDF <host>" (PDF-looking URL) → "Đã lưu PDF <path> (N trang)". Gateway errors become Vietnamese tool errors (blocked URL, PDF too large, not a PDF, HTTP 404, timeout...). Gateway `WEB_FETCH_ENABLED=false` or no `MENTOR_GATEWAY_URL`/`_TOKEN` = "chưa được cấu hình" |
| `paper_search` | `query`, `source?` (`asta`\|`arxiv`\|`semantic_scholar`; omitted = `arxiv`; Asta search takes ~30-60 s, so it is opt-in), `limit?` (≤10, default 5), `year_from?` | NCS only. Via gateway `GET /internal/papers/search`. Returns a note that the data is external (+ "Asta không trả lời nên kết quả lấy từ arXiv" on fallback) + JSON list `{id, source, title, authors (first 5), author_count, year, venue, abstract (≤800 chars), url, citation_count?, publication_date?}`; `id` is `arxiv:<id>` or `s2:<paperId>`. Asta results end with the attribution line "Nguồn: Asta Scientific Corpus Tool của Ai2 …". Descriptions of all paper tools tell the model to put only research keywords / ids in arguments, never learner data. "chưa được cấu hình" without `MENTOR_GATEWAY_URL`/`MENTOR_GATEWAY_TOKEN` |
| `paper_get` | `id` | NCS only. `arxiv:<id>`, bare arXiv id/abs URL, `s2:<paperId>`, `DOI:<doi>`, `CorpusId:<n>`. Abstract ≤4000 chars; non-arXiv ids (Asta `get_paper`, fallback S2 REST) add `reference_count`, `citation_count`, `tldr`, `top_references` (≤10; S2 REST: most-cited) |
| `paper_save` | `id` | NCS only. `paper_get` + `write_file` of `research/papers/<họ tác giả đầu><năm>-<từ khóa>.md` in the paper-reading-coach note format (info + abstract, learner sections empty). Never overwrites: same paper → "đã có", other paper with the same slug → `-2` suffix |
| `paper_snippets` | `query`, `paper_ids?` (list, ≤10 ids in `paper_get` forms), `limit?` (≤10, default 5) | NCS only. Via gateway `GET /internal/papers/snippets` (Asta `snippet_search`). External-data note + JSON list `{paper_id (s2:<id> or CorpusId:<n>), paper_title, authors, author_count, year, url, section, kind, text (≤2500 chars), score}` + Asta attribution line |
| `paper_citations` | `id`, `limit?` (≤20, default 10), `year_from?` | NCS only. Via gateway `GET /internal/papers/citations` (Asta `get_citations`). External-data note + JSON list of citing papers (same shape as `paper_search`), most-cited first + Asta attribution line |
| `calendar_list_events` | `start?`, `end?` (ISO date or datetime; naive = Asia/Ho_Chi_Minh; a date `end` is inclusive) | NCS only. Learner's Google Calendar (primary) via gateway `GET /internal/calendar/events`; default now → +14 days, window ≤60 days, ≤50 events. Returns a note that the data is external + JSON `{start, end, time_zone, truncated, events: [{id, title, start, end, all_day, location, description (≤300 chars, HTML stripped), created_by_mentor}]}` (all-day `end` = last day, inclusive). Not connected → error telling the learner to connect in Cài đặt |
| `calendar_create_event` | `title`, `start`, `end?`, `description?`, `location?` | NCS only, turns only. Checks the connection, then shows an approval card itself (`action` `calendar.create_event`; no separate `request_approval`) and creates only on approve (deny/timeout → non-error result, nothing created). `start`/`end` ISO datetime (default 1 h) or `YYYY-MM-DD` (all-day, `end` inclusive). The event is tagged `extendedProperties.private.mentorCreated = "1"`. Logged to `activity.jsonl` |
| `calendar_update_event` | `id`, `title?`, `start?`, `end?`, `description?`, `location?` | NCS only, turns only. Only events with `created_by_mentor` (else error before any card). Approval `calendar.update_event`. Moving only `start` keeps the duration |
| `calendar_delete_event` | `id` | NCS only, turns only. Only `created_by_mentor` events. Approval `calendar.delete_event` |
| `notify_user` | `text`, `kind?`, `title?`, `actions?` (≤3 `{id, label}`), `mascot?`, `prefill?` | Adds `OutboxItem(notify_user)`, payload `NotifyPayload` (section 9); queues nothing after a crisis alert in the same turn/job |
| `schedule_wake` | `at`, `job_kind`, `prompt?` | Adds `OutboxItem(next_wake)`. Not `focus_end` (only `start_focus` schedules it) |
| `suggest_replies` | `items` (1..3 `{label (≤40), text? (≤300, default label)}`) | Turns only, section 9. The last call of a turn wins; sent as `suggestions` just before `done`, kept on the last `mentor` transcript record. No tool UI events |
| `show_card` | `kind`, `data` | Section 9. Kinds `flashcard`, `deadline`, `checkin`, `weekly`, `celebration`, `practice`, `mock` (not `focus`: use `start_focus`). Jobs: only `weekly`, `checkin`, `deadline` (notification-action jobs: all but `focus`; written into that day's chat transcript, relayed live when the chat is open). Data validated per kind, unknown fields refused, ≤3 cards per turn/job. `flashcard.skill` must be listed in a `learning/**/review-queue.md`. `weekly`: missing `focus_minutes`/`streak_days` are computed (activity `start_focus`/`focus_extend` of the last 7 days; consecutive days with a learner chat message). `celebration`, `weekly`, `practice` and `mock` refused in crisis context. `practice` `{subject, minutes, goal?, topics?, title, reason}` and `mock` `{subject, profile_id, title}`: section 10.5 |
| `start_focus` | `task` (≤120), `minutes` (5..90) | Turns, and jobs started by a notification action (section 9). Emits a `focus` card, adds `OutboxItem(next_wake)` `{at: ends_at, job_kind: "focus_end", card_id, task, minutes}`, logs activity `start_focus` ("Bắt đầu tập trung N phút: task", target = card id). One per turn |
| `celebrate` | `title` (≤80), `detail?` (≤200) | Turns, and jobs started by a notification action. One `celebration` per turn (also counting `show_card` celebration), shown at the end of the turn; refused (tool error) and any held celebration dropped when `flag_crisis` ran in the session or `wellbeing-and-crisis/SKILL.md` was read in it |
| `request_approval` | `action`, `summary`, `details` | Emits `approval_request`, waits for `/v1/approvals` (turns only). Not needed before `calendar_*` writes (they ask themselves); a `scope: session` approval of an action id also covers the calendar tool with that id |
| `send_parent_report` | `path` | THPT only. `path` = `.mentor/report-drafts/<date>.md` (`reports/<date>.md` or `<date>.md` are mapped to that draft). Runs `check_report`; on pass adds `OutboxItem(parent_report)` with the draft path. D re-checks, sends, then moves it to `reports/` |
| `flag_crisis` | `category`, `reason` | THPT only. Category ∈ `self_harm`, `abuse`, `harm_others`, `run_away`. Harness asks alias `mentor-safety-b` to confirm from the recent transcript; only if confirmed adds `OutboxItem(crisis_alert)`. Never written to `activity.jsonl` |

Model aliases: `mentor_schemas.ModelAlias`. A session sticks to `mentor-chat`; images go through `look_at_image`;
jobs `nightly_reflection` and `parent_report` use `mentor-reasoning`.

Context loaded at the start of every turn (plan 6.5), in this order so the prefix stays cacheable:
`AGENTS.md` → skills index (name + description of skills for the profile), then the full body of skills with
`preload: true` (today: memory-keeper) → `me/profile.md`, `me/preferences.md`,
`me/now.md`, `goals/goals.md`, `goals/plans/this-week.md`, last 3 journal files → file map (names only of
`me/`, `goals/`, `learning/`, `research/`, `reports/`, ≤15 per folder; `inbox/` as a count; `routines.yaml`)
→ today's date/time.
Tool calls of one model response: consecutive read-only calls (`read_file`, `list_dir`, `grep`, `look_at_image`,
`web_*`, `paper_*` except `paper_save`, `calendar_list_events`) run concurrently; all others one at a time, in order.
Tool results go back in the order of the calls.

## 4. Scripts (C implements, A runs, B's skills mention)

Uniform protocol: `python -m mentor_scripts.<name>`, cwd = workspace root (also env `WORKSPACE_ROOT`),
input JSON on stdin, output JSON on stdout, exit code 0 on success, 1 with `{"error": "..."}` otherwise.

| Name | Input | Output | Effect |
|---|---|---|---|
| `record_event` | `LearningEvent` fields minus `event_id`, `ts` | `{"event_id"}` | Validates and appends to `events.jsonl` |
| `record_wellbeing` | `{date, level, note_ref?}` | `{"ok": true}` | Upserts by date in `.mentor/wellbeing.jsonl` (THPT) |
| `wellbeing_window` | `{days: 30, threshold: 0.4}` | `{days_recorded, negative_ratio, trigger_nudge}` | Read-only |
| `bkt_update` | `{subject: "math"}` | `{skills_updated}` | Reads events + curriculum, writes `learning/<subject>/skills.md` and `review-queue.md` |
| `sympy_check` | `{kind: "solve"\|"equivalent"\|"simplify", problem, answer}`, or `{checks: [that, ...]}` (1..10) | `{correct, expected, detail, verified}`; batch: `{results: [that, ...], all_correct}` | Read-only. Batch = one tool round for a whole quiz or solution |
| `pdf_extract` | `{path, max_chars?: 200000, start_page?, end_page?}` (pages from 1, inclusive) | `{pages: [{n, text}], page_count, truncated}` | Read-only; pypdf, no OCR |
| `pdf_render` | `{path, pages?: [n] (default first 3, ≤5), width?: 1400 (400..2000)}` | `{images: [{n, path}], page_count}` | Writes `<pdf stem>-p<n>.png` next to the PDF (must be agent-writable); pypdfium2. For scanned PDFs → `look_at_image` |
| `check_report` | `{path}` | `{ok, violations: [str]}` | Read-only; uses `REPORT_FORBIDDEN_PATTERNS` plus checks frontmatter and disclaimer |

`skills.md` written by `bkt_update` is a markdown table: `| skill_id | Tên | Mastery | Bằng chứng | Lần cuối |`.

`sympy_check` answer format (what skills send): SymPy-style expressions; multiple solutions separated by `;`
(`x = 2; x = -4`); variables of a system separated by `,` (`x = 1, y = 2`); the literal `vô nghiệm` means no
solution. The script also accepts the looser handwritten forms it can parse (`x²`, `2x`, `hoặc`, `S = {…}`).

## 5. Gateway API for the web app (D serves, F consumes)

Base `http://localhost:8000/api`, cookie session `mentor_session`, JSON. `MENTOR_ENV` unset means `prod` (no
implicit dev mode). `MENTOR_ENV=dev` returns the
magic link and the login code in the response instead of emailing them.

| Method | Path | Body / query | Response |
|---|---|---|---|
| POST | `/auth/request-link` | `{email}` | `{sent: true, dev_link?: str, dev_code?: str}` (email has the link and a 6-digit code) |
| GET | `/auth/verify` | `?token=` | sets cookie, 302 to `/onboarding` or `/chat` |
| POST | `/auth/verify-code` | `{email, code}` | sets cookie, `{ok: true, next: "/onboarding"\|"/chat"}`; 400 wrong/expired/used, 422 malformed |
| POST | `/auth/logout` | | `{ok: true}` |
| GET | `/me` | | `Me` |
| POST | `/onboarding` | `{role: "thpt"\|"ncs", display_name, language: "vi"\|"en"}` | `Me` |
| POST | `/parent-link` | | `{link_code, expires_at, bot_name, bot_url: str | null, dev_verify: bool}` (bot_url null when `ZALO_BOT_URL` is unset; dev_verify true only in dev) |
| GET | `/parent-link` | | `{status: "none"\|"pending"\|"awaiting_consent"\|"verified", expires_at?}` |
| POST | `/uploads` | multipart `file` | `{path, mime_type}` (saved under `inbox/`) |
| POST | `/uploads/mobile-token` | | `{upload_url, expires_at}` |
| POST | `/m/{token}` | multipart `file` | `{path}` (no session; token-bound) |
| GET | `/workspace/tree` | `?prefix=` | `[{path, type: "file"\|"dir", size, modified_at}]` (no `.git`, no `.mentor` except `.mentor/activity.jsonl`) |
| GET | `/workspace/file` | `?path=` | `{path, content, sha}` |
| PUT | `/workspace/file` | `{path, content, base_sha}` | `{sha}`; 409 if `base_sha` is stale; 403 outside `me/`, `goals/`, `learning/`, `research/` |
| DELETE | `/workspace/file` | `?path=` | `{ok: true}` (same 403 rule) |
| GET | `/workspace/history` | `?path=` | `[{sha, author: "mentor"\|"user"\|"system", ts, message}]` |
| GET | `/workspace/export` | | zip of the workspace |
| DELETE | `/account` | | `{ok: true}` |
| GET | `/activity` | `?limit=50&before=` | `[ActivityEntry]` newest first |
| GET | `/reports` | | `[{path, period_start, period_end, sent_at}]` (THPT; only reports D has sent: unsent drafts in `.mentor/report-drafts/` are never listed, and like all of `.mentor/` are hidden from tree/file/raw/history and left out of the export) |
| GET | `/settings` | | `{proactivity, quiet_hours, language, routines: [Routine]}` |
| PUT | `/settings` | same | same (writes `routines.yaml` as a user commit). 422 (Vietnamese `detail`) when a new or changed learner routine uses a platform job kind (`parent_report`, `nightly_reflection`) or runs more than once per hour |
| PUT | `/settings/setup-guide` | `{dismissed: bool}` | `{setup_guide_dismissed_at: str\|null}`. First-login setup guide: `true` records when the learner closed it (first time kept), `false` clears it so the web app shows it again; 409 before onboarding. Stored in the ops DB (`user_ui_state`), not the workspace, so it holds across devices and the desktop pop-up |
| GET | `/integrations/google-calendar` | | `{available, connected, email: str\|null, scopes: [str]}` (NCS only, 403 THPT; `available` false when `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` are unset) |
| GET | `/integrations/google-calendar/connect` | | 302 to Google (browser navigation, not fetch); 403 THPT, 503 unavailable |
| GET | `/integrations/google-calendar/callback` | `?code=&state=` or `?error=&state=` (from Google) | 302 to `{WEB_ORIGIN}/settings?calendar=connected` or `?calendar=error&reason=denied\|state\|session\|scope\|exchange\|google` |
| DELETE | `/integrations/google-calendar` | | `{ok: true}` (revokes at Google, deletes the tokens) |
| POST | `/sandbox/warm` | | `{state: "sleeping"\|"waking"\|"ready"\|"busy", warming: bool, result: "started"\|"starting"\|"already_running"\|"busy"\|"throttled"\|"disabled"\|"not_active"\|"error"}`; 401 without a session. Pre-warm, see below |
| GET | `/notifications` | `?limit=30` (1..100) | `[Notification]` newest first: delivered ones (also snoozed or dismissed after a delivery); section 9 |
| POST | `/notifications/{id}/action` | `{action}` | section 9; 404 unknown or another learner's, 422 invalid or not offered |
| GET | `/engagement` | | section 9 |
| GET | `/push/vapid-public-key` | | `{enabled, public_key: str\|null, subscribed_devices}` |
| POST | `/push/subscribe` | `{subscription: PushSubscription.toJSON(), device?: str ≤64}` | `{ok, id}`; 503 when push is off, 422 malformed or not a known push service |
| DELETE | `/push/subscribe` | `{endpoint?}` or `{subscription?}` or `?endpoint=` | `{ok, removed}` (no endpoint = every device of the learner) |
| WS | `/ws/chat` | | see below |

Login code (for the desktop pop-up, whose webview cannot receive the magic-link cookie from the system
browser): each `request-link` creates one pending login with both a link and a 6-digit code (random, stored
salted-hashed, compared in constant time), valid `magic_link_minutes` (15). Using either one consumes the login;
only the newest code per email is valid (a new request replaces older codes; older links still work until they
expire); the 5th wrong code invalidates that login (code and link). Unknown email answers like a wrong code.

Additional endpoints (added by D): `GET /workspace/raw?path=` (binary download), `GET /m/{token}` (phone upload
form), `POST /internal/email/inbound?rcpt=` (internal; `X-Internal-Token: <GATEWAY_INTERNAL_TOKEN>`, constant-time;
without that env var the endpoint is closed (403) in prod and whenever `SANDBOX_BACKEND=docker`, because sandboxes
can reach the gateway), `POST /webhooks/email/inbound` (below), `GET /healthz`, and in dev only
`POST /dev/parent-link/verify`.

Inbound email webhook (production; Cloudflare Email Routing catch-all -> Email Worker `infra/cloudflare/email-worker.js`
-> Caddy, which routes `/webhooks/*` to the gateway): `POST /webhooks/email/inbound`, body = raw RFC 822 message,
headers `X-Mentor-Rcpt: <envelope recipient>` (printable ASCII, ≤320 chars, one `@`; a header rather than `?rcpt=`
so it stays out of access logs, and Caddy deletes it and the signature from its log), `X-Mentor-Timestamp: <unix
seconds>`, `X-Mentor-Signature: v1=<lowercase hex HMAC-SHA256(EMAIL_WEBHOOK_SECRET, "v1\n" + timestamp + "\n" + rcpt
+ "\n" + body)>`. Order of checks: `EMAIL_WEBHOOK_SECRET` unset → 404; `Content-Length` or streamed body over
`INBOUND_EMAIL_MAX_BYTES` (25 MiB) → 413; missing/malformed timestamp or signature, timestamp more than 300 s from
the gateway clock, or a signature that does not match (constant-time) → 401; malformed rcpt → 400; the same signature
again within the window → 202 without storing twice; more than `EMAIL_WEBHOOK_PER_RCPT_PER_HOUR` messages for one
recipient (local part without `+tag`, checked before lookup) → 429 + `Retry-After`; then section 7's handler with
`recipients=[rcpt]` (`inbox/email/`, intake job) → 202 `{ok: true}`, identical for unknown recipients so addresses
cannot be probed; 500 if storing fails. The Worker accepts on 2xx, bounces with `setReject` on 413/400, and throws
(temporary failure, the sending server retries) on anything else. Logged: the first 3 characters of the code and the
size only.

Sandbox → gateway web search (same token, both profiles): `POST /internal/web/search` body `{query (1..400 chars),
max_results (1..8, default 5)}` → `{backend: "tavily"|"searxng", results: [{title, url, snippet, published?}]}`;
errors `{detail, reason}`: 401 token, 422 input, 429 + `Retry-After` over `WEB_SEARCH_REQUESTS_PER_MINUTE`, 503
`not_configured`/`rate_limited`, 504 `timeout`, 502 upstream. The query is never logged; audit row kind `web_search`
holds only backend and result count.

Sandbox → gateway page reading (same token, both profiles, no search backend needed): `POST /internal/web/fetch`
body `{url (1..2000 chars)}` → `{url, final_url, title, text, truncated, content_type}` (`text` ≤20 000 chars of
readable text; HTML: script/style/nav/footer dropped, link text kept). SSRF rules: http/https on ports 80/443 only,
no credentials in the URL; `localhost`, single-label and internal-suffix hosts (`.local`, `.internal`, ...) and the
gateway's own hosts refused; the gateway resolves DNS and every address must be public (no private, loopback,
link-local incl. 169.254.169.254, CGNAT, multicast, reserved; v4 and v6 incl. IPv4-mapped/6to4/Teredo/NAT64), then
connects to that vetted IP (Host header + TLS SNI/cert check on the hostname); redirects followed by hand, ≤5, each
re-checked; no cookies; 15 s total, ≤2 MB read; types `text/html`, `application/xhtml+xml`, `text/plain`,
`application/json`. Errors `{detail, reason, upstream_status}`: 401 token, 422 input, 429 + `Retry-After` over
`WEB_FETCH_REQUESTS_PER_MINUTE`, 400 `blocked_url`/`bad_url`, 415 `pdf` (the URL is a PDF, or PDF bytes behind
any other type: use `/download`) / `unsupported_type`, 502 `http_error` (+ `upstream_status`)/`too_many_redirects`/
`dns`/`tls`/`upstream`, 504 `timeout`, 503 `disabled` (`WEB_FETCH_ENABLED=false`). Audit row kind `web_fetch` holds
only host(s) and status, never the URL path or query.
PDF download: `POST /internal/web/download` body `{url}` → 200 with the raw bytes (`Content-Type: application/pdf`,
headers `X-Final-Url` (percent-encoded final URL after redirects) and `X-Content-Sha256`), not base64 in JSON. Same
token, rate limit (shared with `/fetch`), SSRF rules, redirects and audit (`pdf_bytes=<n>`); 60 s total; at most
`WEB_FETCH_PDF_MAX_MB` (default 30, raw and decoded; over the cap → 413 `too_large`, never truncated); the body
must carry `%PDF-` in its first 1024 bytes whatever the content type says, and an HTML response is refused, both
415 `not_pdf`. The gateway never parses the PDF (it holds the keys and the Docker socket); the sandbox saves and
parses it (section 3 `web_fetch`). Other errors as for `/fetch`.

Sandbox → gateway (no `/api` prefix, not for the web app): `GET /internal/papers/search?q=&source=asta|arxiv|semantic_scholar&limit=1..10&year_from=`
→ `{source, query, results: [Paper], fallback_from?: "asta", attribution?}`, `GET /internal/papers/get?id=` →
`{source, paper: Paper, attribution?}`, `GET /internal/papers/snippets?q=&paper_ids=<id>(repeated or comma-separated, ≤10)&limit=1..10`
→ `{source: "asta", query, snippets: [Snippet], attribution}` and `GET /internal/papers/citations?id=&limit=1..20&year_from=`
→ `{source: "asta", id, citations: [Paper], attribution}` (shapes: section 3 `paper_*`). `attribution` (present
whenever `source` is `asta`) = "Asta Scientific Corpus Tool, Ai2 (Allen Institute for AI); data: Semantic Scholar". Auth `Authorization: Bearer <MENTOR_GATEWAY_TOKEN>`: a random per-sandbox token the
backend issues at every sandbox start, kept in gateway memory (hashed), revoked when the sandbox stops; 401 unknown
token, 403 non-NCS sandbox, 429 + `Retry-After` over `PAPER_REQUESTS_PER_MINUTE` per learner, 400 bad id/query,
404 not found, 502/503/504 upstream error/rate limit/timeout as `{detail}`. Upstream hosts are fixed to
`export.arxiv.org`, `api.semanticscholar.org` and `asta-tools.allen.ai` (https, no redirects, 15 s timeout / Asta
`ASTA_TIMEOUT_SECONDS` overall, 2 MB cap), one request at a time per host spaced 3 s (arXiv) / 1 s (S2); Asta call
starts spaced 0.3 s with a key / 1 s without; results cached in memory for 10 min. Asta is Ai2's MCP server
(Streamable HTTP, `x-api-key`); its license is academic / non-commercial and Ai2 may use inputs, so only search
terms and paper ids are sent. Asta search failure → arXiv (`fallback_from`); `get` Asta failure (not 400/404) →
S2 REST; after an Asta 5xx that tool is skipped for 2 min (search goes straight to arXiv, snippets/citations 503).
Measured without a key (2026-10-30): `get_paper`/`get_citations` ~6 s, search ~34 s, `snippet_search` never answers.

Google Calendar (NCS): OAuth 2.0 web-server flow, scopes `openid email https://www.googleapis.com/auth/calendar.events`,
`access_type=offline`, `prompt=consent`, PKCE S256, redirect URI `{PUBLIC_BASE_URL}/api/integrations/google-calendar/callback`.
`state` is random, stored hashed with the session it was issued to, single use, valid 10 min; the callback requires the same
session cookie. The granted scopes must include `calendar.events` (else the grant is revoked, `reason=scope`). Refresh and
access tokens are stored sealed with the master key (`SecretBox`, aad `gcal-refresh:<user_id>` / `gcal-access:<user_id>`),
refreshed server side; `invalid_grant` on refresh deletes the link (learner must reconnect). Account deletion revokes too.
Sandbox side, same bearer token as papers, NCS only, 429 over `CALENDAR_REQUESTS_PER_MINUTE` per learner:
`GET /internal/calendar/status` → `{available, connected, email}`; `GET /internal/calendar/events?start=&end=` → list shape
of `calendar_list_events`; `GET /internal/calendar/events/{id}` → `{event}`; `POST /internal/calendar/events`
`{title, start, end?, description?, location?}` → `{event}`; `PATCH /internal/calendar/events/{id}` (same fields, all optional)
→ `{event}`; `DELETE /internal/calendar/events/{id}` → `{ok, event}`. Errors `{detail, reason}`: 409 `not_connected`,
503 `unavailable` (no OAuth client) or `rate_limited`, 403 `not_mentor_event` (PATCH/DELETE of an event without the
`mentorCreated` marker), 404 `not_found`, 400 bad input (window >60 days, end before start, title >200 chars...), 502/504
Google errors. Google hosts are fixed (`oauth2.googleapis.com`, `www.googleapis.com`; https, no redirects, 15 s, 2 MB).
Tokens never leave the gateway.

`POST /parent-link` returns 409 when already verified; `GET /workspace/file`
returns 415 for binary files. `PUT /settings` leaves routines with `user_editable: false` unchanged. The
scheduler applies the same routine policy to `routines.yaml` written by the agent: a routine running more than
hourly, or a platform job kind outside its fixed routine (id = job kind, `user_editable: false`), is skipped.

Parent reports (outbox `parent_report` with a `.mentor/report-drafts/<name>.md` path): D does not trust the
sandbox's `check_report`. It reads the draft from the mirror and re-runs `mentor_parent_channel.find_leaks`
(`REPORT_FORBIDDEN_PATTERNS` + email + phone + private workspace paths `me/`, `sessions/`, `inbox/`, `.mentor/`);
on failure it sends nothing, returns `blocked` and writes an audit row `parent_report_blocked` with only the names of
the failed checks. After the parent channel delivered it, D records `sent_reports` and commits (author `system`) the
move of the draft to `reports/<name>.md`; only then does the learner see it.

`Me = {user_id, email, role: "thpt"|"ncs"|null, display_name, language, onboarding_state: "needs_role"|"needs_parent"|"active", inbound_email_address: str|null, setup_guide_dismissed_at: str|null}`
(`setup_guide_dismissed_at` null = the web app opens the setup guide once on the next visit after onboarding is `active`).
`onboarding_state = needs_parent` blocks chat for THPT until the parent link is `verified`.

Sandbox pre-warm (`SANDBOX_PREWARM`, default on): opening `/ws/chat` and `POST /sandbox/warm` (the web app calls it
when the chat page or the pop-up regains focus, at most once a minute) start an active learner's sandbox in the
background so the first message skips the cold start (5-8 s locally). The call returns at once; progress is sent as
`sandbox_status` (`waking`, then `ready`; `sleeping` if the start failed) to the learner's sockets, and the first
`sandbox_status` after connecting is already `waking` (it may repeat once). A warm-up only starts the sandbox and waits
until it is healthy: no git pull/push, no turn, never while a turn or job holds the sandbox (`busy`), one start in
flight per learner (`starting`), at most one per learner per 60 s (`throttled`). A turn or job that arrives during a
warm-up waits for it instead of starting a second sandbox, then pulls web edits as usual. A warm-up of a running
sandbox (`already_running`) resets its idle timer; an unused warm sandbox sleeps after `SANDBOX_IDLE_SECONDS`
like any other. Learners who are not `active` are skipped (`not_active`).

WebSocket `/api/ws/chat` messages:
- client → server: `{type: "user_message", client_msg_id, text, attachments: [{path, mime_type}]}`,
  `{type: "approval_decision", approval_id, decision, scope}`,
  `{type: "card_action", card_id, action, value?, client_msg_id?}` (section 9)
- server → client: `{type: "sandbox_status", state: "sleeping"|"waking"|"ready"|"busy"}`, `{type: "text_delta", text}`,
  `{type: "tool_started"|"tool_finished", tool, summary}`, `{type: "approval_request", approval}`,
  `{type: "turn_done", client_msg_id}`, `{type: "notification", id, kind, title, body, actions, mascot, prefill, text, created_at, bundled_ids?}` (section 9; old clients read `text`), `{type: "error", error}`,
  `{type: "upload_received", path}` (a phone upload landed in `inbox/`), and from section 9:
  `{type: "card", card}`, `{type: "suggestions", client_msg_id, items}`,
  `{type: "card_echo", client_msg_id, card_id, action, value, text}`; a refused `card_action` gets
  `{type: "error", error, card_id}`. `user_message` and `card_action` take an optional `conversation_id` (section 10.5);
  an unknown one gets `{type: "error", error, conversation_id}` and no turn

## 6. Parent channel library (E builds, D wires)

Package `mentor_parent_channel`:
- `ZaloBotClient(token, base_url="https://bot-api.zaloplatforms.com")`: `get_me()`, `send_message(chat_id, text)`
  (splits at 2000 chars), `set_webhook(url, secret_token)`. Payload shapes: plan + `https://bot.zapps.me/docs/`.
- `ParentLinkService(store: ParentLinkStore, client, bot_name, now=...)`:
  `start_link(student_user_id) -> ParentLink` (6-digit code, 24 h expiry, replaces a pending one),
  `handle_update(update: dict) -> None` (code → `awaiting_consent` + consent message disclosing an automated AI
  bot and what parents receive; reply `ĐỒNG Ý`/`dong y`/`đồng ý` → `verified` + `record_audit("consent")`; anything else → short help),
  `send_report(student_user_id, report_text) -> bool` (only if verified; re-checks forbidden patterns; the report
  already contains `AI_DISCLAIMER` because `check_report` requires it — append it only if missing, never twice),
  `send_crisis_alert(student_user_id, category) -> bool` (fixed template from plan 7.6, no details; `record_audit("crisis_alert")`).
- `create_webhook_router(service, secret_token) -> fastapi.APIRouter` with `POST /webhooks/zalo`.
- Zalo Bot webhooks must be used in production; `getUpdates` does not keep messages (tested 2026-10-28).

## 7. Email ingest library (E builds, D wires)

Package `mentor_email_ingest`:
- `parse_message(raw: bytes) -> ParsedEmail` (`from_addr, to_addrs, subject, date, text, attachments: [(filename, mime, bytes)]`), HTML → text.
- `InboundHandler(users: UserDirectory, writer: WorkspaceWriter, jobs: JobQueue, max_bytes=10_000_000)` (the gateway
  passes `INBOUND_EMAIL_MAX_BYTES`):
  `handle(raw: bytes) -> str | None` — resolve user from any recipient `<code>@<INBOUND_EMAIL_DOMAIN>`, write
  `inbox/email/<YYYY-MM-DD>-<slug>.md` beginning with a banner that the content is untrusted data, save attachments
  next to it, enqueue `JobRequest(kind=intake)`. Unknown recipient or oversize → dropped, returns `None`.
- Dev server: `uv run python -m mentor_email_ingest.dev_smtp --port 2525` (aiosmtpd) calling a handler.

## 8. Ports and env (dev)

| Service | Port | Key env |
|---|---|---|
| Gateway | 8000 | `MENTOR_ENV=dev` (unset = `prod`: refuses the local backend, needs `MENTOR_MASTER_KEY`, no dev links), `SANDBOX_NETWORK_ATTACH` (docker backend: `container[:alias],...` attached to each sandbox's own internal network, `self` = the gateway's container; compose: `self:gateway,mentor-dev-model-router-1:model-router`), `SANDBOX_DOCKER_USER` (default the gateway's uid:gid; root refused), `SANDBOX_TMPFS_SIZE=256m`, `GATEWAY_INTERNAL_TOKEN` (required for `/internal/email/inbound` in prod and with the docker backend), `MENTOR_DATA_DIR=var/`, `SANDBOX_BACKEND=local\|docker`, `SANDBOX_IDLE_SECONDS=900`, `SANDBOX_PREWARM` (default on; `0`/`false` turns off starting the sandbox when the learner opens the chat, section 5), `ZALO_BOT_TOKEN`, `ZALO_WEBHOOK_SECRET`, `INBOUND_EMAIL_DOMAIN=inbox.mentor.local` (prod: the Cloudflare Email Routing domain; used in `Me.inbound_email_address` and to resolve recipients), `EMAIL_WEBHOOK_SECRET` (unset = `/webhooks/email/inbound` answers 404; prod: `deploy.sh` generates it), `INBOUND_EMAIL_MAX_BYTES=26214400` (every inbound path), `EMAIL_WEBHOOK_PER_RCPT_PER_HOUR=30`, `SANDBOX_GATEWAY_URL` (gateway as seen from a sandbox; default `PUBLIC_BASE_URL`; compose: `http://gateway:8000`), `S2_API_KEY` (optional), `PAPER_REQUESTS_PER_MINUTE=20`, `ASTA_API_KEY` (optional; higher Asta rate limit, needed for snippets), `ASTA_MCP_URL=https://asta-tools.allen.ai/mcp/v1` (`off` disables), `ASTA_TIMEOUT_SECONDS=40`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (optional; Google Calendar for NCS, setup in infra/README), `CALENDAR_REQUESTS_PER_MINUTE=30`, `SIGNUP_ALLOWLIST` (comma-separated emails / `@domain`; empty = open signup; others get 403 on request-link), `TAVILY_API_KEY` or `SEARXNG_URL` (web search backend; Tavily wins if both; neither = off), `WEB_SEARCH_REQUESTS_PER_MINUTE=10`, `WEB_FETCH_ENABLED=true` (`web_fetch` page reader; `false` = off), `WEB_FETCH_REQUESTS_PER_MINUTE=10`, `WEB_FETCH_PDF_MAX_MB=30` (`POST /internal/web/download` cap, 1..200; HTML pages stay at 2 MB), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (Web Push, section 9; all three set = on; prod: `deploy.sh` generates the pair once; dev: `python -m mentor_gateway.cli vapid-generate`), `MENTOR_MASTER_KEY` (urlsafe base64, 32 bytes; required outside dev/test, from a secret manager; dev/test generate `$MENTOR_DATA_DIR/master.key`), `MENTOR_BACKUP_DIR` (default `$MENTOR_DATA_DIR/backups`), `BACKUP_ENABLED` (default on except `MENTOR_ENV=test`), `BACKUP_HOUR_UTC=19`, `BACKUP_KEEP_DAILY=14`, `BACKUP_KEEP_WEEKLY=8`; rotation only: `MENTOR_NEW_MASTER_KEY` (infra/README "Encryption at rest and backups") |
| Harness | 8080 (container) / dynamic (local) | section 2, plus `MENTOR_HARNESS_TOKEN` (random per start, gateway -> harness bearer token), `MENTOR_GATEWAY_URL`, `MENTOR_GATEWAY_TOKEN` (sandbox -> gateway; paper_*, calendar_*, web_search and web_fetch tools), all set by the gateway backend |
| Model router (LiteLLM) | 4000 | `FPT_API_BASE`, `FPT_API_KEY`, `MODEL_ROUTER_MASTER_KEY`; config `services/model-router/config.yaml` |
| Web | 3000 | `NEXT_PUBLIC_API_BASE=http://localhost:8000/api`, `NEXT_PUBLIC_API_MOCK=1` for UI work without the gateway |
| Desktop pop-up (Tauri, `apps/desktop`) | none | `WEB_ORIGIN=http://localhost:3000` (build or run time): the panel loads `$WEB_ORIGIN/popup`; same origin as the web app, so no extra `CORS_ORIGINS` |
| Dev SMTP | 2525 | |

## 9. Interaction layer (draft 2026-11-03; owners: H = harness/chat cards, N = gateway nudges/push, W = web, K = desktop, M = mascot)

Goal: the mentor starts conversations and the UI answers with motion, not only text. Every proactive surface
obeys the learner's proactivity level (off/medium/high) and quiet hours exactly like notifications do today, and
`prefers-reduced-motion` turns animation into fades. **Never** in crisis context: no celebration, confetti, streak or
playful mascot state in a turn where `flag_crisis` ran or the safety skill is active (mascot uses `calm`). No guilt
mechanics: streaks never "break" loudly, no countdown pressure, no leaderboards.

**Mascot (M).** One framework-free custom element `<mentor-mascot state size>` in `packages/mentor-mascot/`
(ESM `mascot.js` + inline SVG, no runtime deps), used by web (W) and desktop (K). States: `idle`, `listening`,
`thinking`, `talking`, `happy`, `celebrate`, `sleepy`, `calm` (gentle, for serious topics), `wave` (greeting).
Event `mascot-done` fires when a one-shot state (`celebrate`, `wave`) ends, then it returns to `idle`.
Built (M, 2026-11-03): attributes also `label` (aria name; `""` = decorative), `tail` (`right|left|none`, desktop maps
its docked side), `theme` (`light|dark`, else OS), `motion` (`reduce|full`, else OS). `el.play(state)` returns a
promise (one-shots resolve with `{state, interrupted}`); `mascot-done.detail = {state, interrupted}`. Colors via
`--mascot-body`, `--mascot-ink`, `--mascot-cheek`, `--mascot-spark` (web sets body/ink to `--accent`/`--accent-text`).
Exports `MentorMascot`, `defineMentorMascot()`; SSR-safe import. Types in `mascot.d.ts`; details in its README.

**Chat events (H → gateway → W), added to the WebSocket list in section 5:**
- `{type: "suggestions", client_msg_id, items: [{label, text}]}`: ≤3 quick replies, sent before `turn_done`.
  Clicking sends `text` as a normal `user_message`.
- `{type: "card", card}` with `card = {id, kind, created_at, ...}`; stored in the chat transcript so history replays it.
  Kinds: `flashcard {skill, front, choices?: [string], reveal?: string}`, `deadline {title, due_at (ISO, VN time),
  source?}`, `focus {task, minutes, ends_at}`, `celebration {title, detail?}`, `weekly {focus_minutes,
  milestones_done, mistakes_fixed, streak_days, highlight?}`, `checkin {prompt, options: [string]}`, `practice {subject, minutes, goal, topics?, title, reason}`, `mock {subject,
  profile_id, title}` (section 10.5; no `card_action`).
- client → server `{type: "card_action", card_id, action, value?}` (e.g. flashcard answer, focus done/extend,
  check-in option). The gateway turns it into a user turn the agent sees as `[card:<kind> <action> <value>]` plus
  a short human-readable echo for history.
- Harness tools (turn-only unless noted): `suggest_replies {items}`; `show_card {kind, data}`; `start_focus {task,
  minutes 5..90}` (emits a `focus` card and schedules a `focus_end` wake via the job queue); `celebrate {title,
  detail?}` (max 1 per turn, refused in crisis context). Background jobs may emit cards into the next chat open.

Built (H, 2026-11-03); details above stay valid, these refine them:
- Card ids are `card-YYYYMMDD-<12 hex>` (the day of the transcript file the card was first written to).
  `created_at` is ISO with `+07:00`. **A `card` event or history item whose `id` is already shown is an update:
  replace that card in place** (focus extended or ended). History returns each card once, at its first position,
  with its newest content.
- Field limits: flashcard `skill` ≤80, `front` ≤300, `choices` 2..4 × ≤120 (skills ask for 3–4), `reveal` ≤300
  (show it only after the learner answered); deadline `title` ≤120, `due_at` ISO `+07:00`, `source` ≤120; checkin
  `prompt` ≤300 and ≤6 lines (line breaks kept: render `\n`), `options` 2..4 × ≤60; celebration `title` ≤80, `detail` ≤200; weekly ints always present,
  `highlight` ≤200; focus `minutes` = total planned minutes, plus optional `ended_at` (ISO) once ended early or done.
- Suggestions are not separate history items: they ride on the turn's last `mentor` item as `suggestions`. Show the
  chips only under the newest transcript item (live: from the `suggestions` event, before `turn_done`).
- `card_action` (any card kind with actions; others are refused):

  | kind | action | value | echo stored in history |
  |---|---|---|---|
  | `flashcard` | `answer` | choice letter `A`..`D` (or the exact choice text; free text when the card has no choices) | `Đã chọn: B. <choice>` / `Trả lời: <text>` |
  | `flashcard` | `skip` | — | `Bỏ qua thẻ này` |
  | `checkin` | `answer` | an option (or free text ≤300) | `Đã chọn: <option>` / `Trả lời: <text>` |
  | `deadline` | `done` / `start_focus` | `start_focus`: minutes 5..90, default 25 | `Đã xong: <title>` / `Bắt đầu tập trung N phút cho: <title>` |
  | `focus` | `done` / `extend` | `extend`: minutes 5..60, default 10 | `Đã xong phiên tập trung` / `Thêm N phút tập trung` |

  The gateway looks the card up in the learner's transcript (unknown id, bad action or value → `{type: "error",
  error, card_id}`, no turn), refuses while a turn is running like `user_message`, sends `card_echo`
  (`value` normalized, e.g. `B`), then runs a normal turn: `TurnRequest.text = "[card:<kind> <action> <value>]"`,
  `TurnRequest.card_action = {card_id, kind, action, value, echo}`, ending with `turn_done` (the request's
  `client_msg_id`, or a new one). The harness adds the card's content for the model; a flashcard answer is graded
  and recorded (`record_event`, `source_ref` = the transcript file, then `bkt_update`) like a typed answer.
- Focus: `done` and `extend` are applied by the harness itself (an updated `focus` card: `ended_at`, or new
  `ends_at`/`minutes`; activity `focus_done` "Xong phiên tập trung sau N phút: task" / `focus_extend` "Thêm N phút
  tập trung: task", target = card id); the gateway first cancels the card's pending `focus_end` job (status
  `cancelled`) and the harness schedules a new one on `extend`. JobKind `focus_end` (payload `{card_id, task,
  minutes}`) skips when the card ended or was extended, otherwise ends with exactly one `notify_user` outbox item
  `{text, kind: "focus_end", title: "Hết giờ tập trung" (or the model's), actions: [done "Xong rồi", start_focus
  "Thêm một phiên", snooze_1h "Nhắc sau 1 giờ"], focus: {card_id, task, minutes}}` (the harness adds one if the
  model did not), so N can apply `start_focus`/`done` without asking the sandbox.
- Crisis context = `flag_crisis` ran (confirmed or not) or `wellbeing-and-crisis/SKILL.md` was read, in this turn or
  earlier in the same session (sticky until the harness restarts), **or** N's 24 h crisis hold is active: the
  gateway sets `TurnRequest.crisis_hold` / `JobRequest.crisis_hold` from `NotificationHub.hold_active(user)`. Then
  `celebrate` and `show_card` `celebration` / `weekly` return a tool error (so they never reach the transcript),
  and a celebration already requested in the turn/job is dropped (celebrations are sent at the end for this reason).
- Job cards: `JobResult.cards` lists them; the harness has already written them to that day's transcript, and the
  gateway also sends `{type: "card", card}` to open chats after the job, skipping `celebration`/`weekly` while a
  hold is active (re-checked after the job's own outbox, which may have started one).
- Learner-started jobs: a job N enqueues from a notification action (`POST /api/notifications/{id}/action`
  `start_focus` or `answer:<x>`) is a `routine` job with `payload = {source: "notification_action", action,
  notification_id, notification_kind}`. Only for such jobs the harness also offers `start_focus` and `celebrate`
  and allows every `show_card` kind except `focus`; every other job keeps the job rules (`show_card` `weekly`,
  `checkin`, `deadline` only; `start_focus`/`celebrate` neither offered nor accepted). The marker is set only by the
  gateway (routines get `payload: {}`; `schedule_wake` passes only harness-built keys).

**Nudges (N).** Notification records gain `kind` (`checkin|deadline|review|focus_end|celebration|report|nudge`),
`title`, `body`, `actions: [{id, label}]` (≤3; ids `open`, `snooze_1h`, `done`, `start_focus`, `answer:<x>`),
`mascot` (state hint) and `prefill?` (chat text for `open`). `{type: "notification", ...}` on the WebSocket carries
the same fields (old `text` stays for compatibility). `POST /api/notifications/{id}/action {action}` applies
it (snooze reschedules, done marks read, start_focus starts a focus session, open returns `{prefill}`).
New routines (default per profile, editable in routines.yaml/settings): morning check-in 07:30 weekdays
(top 3 for today), evening wrap-up 21:00 (1–2 questions), review-due nudge when the review queue has due items.
`GET /api/engagement` → `{streak_days, today: {focus_minutes, done}, week: {focus_minutes, milestones_done,
mistakes_fixed, active_days}}` computed from activity/events (no new tracking of wellbeing for NCS).
Web Push: `GET /api/push/vapid-public-key`, `POST /api/push/subscribe {subscription}`, `DELETE /api/push/subscribe`;
sent only when the learner has no open WebSocket; env `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`.

Built (N, 2026-11-03); the paragraph above stays valid, these refine it:
- Proactivity values are `off|normal|high` (`normal` is what this section calls medium; `RoutinesFile`).
- `Notification = {id: int, kind, title (≤80, may be ""), body (≤500; = text when the sender gave none), actions:
  [{id, label ≤40}] (≤3), mascot, prefill: str|null, text, created_at, status, delivered_at, read_at, answer:
  str|null}` (`GET /notifications`). The WebSocket event is `{type: "notification", id, kind, title, body, actions,
  mascot, prefill, text, created_at}` plus `bundled_ids: [int]` when several were bundled (`normal` level): then the
  fields are those of the most important one (deadline > checkin > review > focus_end > report > celebration >
  nudge) and `text` joins all texts. Rows from before this change read as kind `nudge`, body = text, no actions.
- Outbox payload (`OutboxItem(notify_user)`, `mentor_schemas.NotifyPayload`): `{text (required, ≤500), kind?
  (default nudge), title?, body?, actions?, mascot?, prefill?, expires_at?, focus?: {card_id, task, minutes}}`. Action
  ids match `open|snooze_1h|done|start_focus|answer:[A-Za-z0-9_.-]{1,32}`. Invalid rich fields degrade to a plain
  text nudge. Default mascot per kind: checkin `wave`, review/focus_end `happy`, celebration `celebrate`, others
  `idle`. Default expiry (not delivered later, status `expired`): checkin 6 h, review 12 h, focus_end 2 h,
  celebration 24 h, others none.
- Policy (same rules as before, per kind): `off` drops everything except `focus_end` (a timer the learner started);
  `normal` allows one delivery per local day, bundling the rest, but `deadline` (AGENTS.md: always report deadlines
  within 48 h), `focus_end` and a snoozed notification coming back go out on their own and do not count; `high`
  sends each one. Quiet hours hold everything. Delivery: open WebSockets, else Web Push (below), else it waits for
  the next connection.
- Safety: an outbox with a `crisis_alert` (any profile) drops the `notify_user` items next to it (`suppressed`) and
  holds `checkin`, `review`, `celebration`, `report`, `nudge` for 24 h (pending ones too); `deadline` and `focus_end`
  still go out. A notification whose text, title, body, prefill or labels mention crisis topics (self-harm,
  abuse, running away, hotlines 111/113/115, ...) is suppressed. The harness `notify_user` tool queues nothing after
  a crisis alert in the same turn/job. Parents never see nudges.
- `POST /notifications/{id}/action {action}` (owner only, else 404; audit row `notification_action` with id, kind
  and verb only). `open`, `done`, `snooze_1h` always allowed; `start_focus` and `answer:<x>` only when the
  notification offers them (else 422). Idempotent per (id, action, delivery number): a repeat returns the first
  result without doing it again. Responses `{ok, action, id, ...}`:
  `open` → `prefill` (str|null), marks read; `done` → marks read (a snoozed one is cancelled, status `dismissed`);
  `snooze_1h` → `snoozed_until` (ISO): delivered again on the first scheduler tick after it, outside quiet hours,
  not counted against the daily cap; `start_focus` → `job_id`: a job (kind `routine`, started at once) asking the
  agent to call `start_focus` (with the `focus` task/minutes of a `focus_end` nudge, else from the nudge text,
  25 min); `answer:<x>` → `job_id`: stores `answer`, job prompt "Dùng skill daily-checkin, phần C. Người học vừa
  trả lời lời nhắn (<kind>) “<title>”: <body> — chọn “<label>” (answer:<x>)". The answer job may update the plan
  and emit cards (`JobResult.cards`); it does not notify. **H: `start_focus` and `show_card` must work in jobs.**
- Routines (in the workspace templates; a routine missing from `routines.yaml` is off, so only new workspaces
  get them): `morning_checkin` `30 7 * * 1-5` and `evening_wrapup` `0 21 * * *` (job_kind `routine`, skill
  daily-checkin parts A/B: a `checkin` card + one `checkin` notification with `answer:` actions), THPT also
  `review_due` `30 20 * * *`: handled by the gateway alone (no sandbox; prompt ignored) when
  `learning/<subject>/review-queue.md` has rows due today or earlier: one `review` notification "Đến giờ ôn nhanh"
  (actions open/snooze_1h/done), at most once per local day and not when a `review` notification already exists
  that day (THPT `evening_review` at 19:30 sends one with kind `review`). These three ids are proactive: the job is
  skipped (status `skipped`, error `proactivity off` / `quiet hours` / `nudge hold`) when proactivity is `off`, the
  run time is in quiet hours, or a crisis hold is active. All other routines run as before.
- `GET /engagement` = `{streak_days, today: {focus_minutes, done}, week: {focus_minutes, milestones_done,
  mistakes_fixed, active_days}}`, days in Asia/Ho_Chi_Minh, `week` = last 7 days including today, cached 60 s per
  learner (an action clears it). Active day = a chat turn (`chat_sessions`), a web edit (mirror commit by `user`) or
  a notification action. `streak_days` = consecutive active days up to today, or up to yesterday while today has
  none yet. Focus minutes from `focus_end` jobs grouped by `card_id`: from `scheduled_for - minutes` to the last
  `scheduled_for`, cut at now and at a cancelled job's `finished_at`, counted on the day it started. `today.done` =
  checkboxes newly `[x]` since local midnight in `goals/goals.md` + `goals/plans/*.md`; `milestones_done` = newly
  `[x]` in `goals/goals.md` this week; `mistakes_fixed` = new lines under "## Đã khắc phục" in
  `learning/*/mistakes.md` this week (0 for NCS). No wellbeing data is read.
- Web Push: off unless all three VAPID vars are set (`GET /push/vapid-public-key` → `enabled: false, public_key:
  null`). Subscriptions are sealed with the master key (blind index on the endpoint, re-wrapped by
  `rotate-master-key`), ≤10 devices per learner (oldest dropped), deleted with the account and on 404/410 from the
  push service. Endpoints must be https:443 under `fcm.googleapis.com`, `android.googleapis.com`,
  `push.services.mozilla.com`, `notify.windows.com` or `push.apple.com` (the gateway POSTs there; no redirects).
  Sent only when the learner has no open WebSocket, under the same policy. TTL = until the notification expires
  (default 6 h). Payload (JSON): `{type: "notification", id, kind, title, body, actions, mascot, created_at,
  bundled_ids, url: "/chat?notification=<id>"}` where **title/body are generic per kind** ("Mentor" / e.g. "Mentor
  có một câu hỏi nhanh cho bạn.") because lock screens are public; only gateway templates (the review-due nudge)
  keep their own text. Push actions: `answer:` actions are left out (they need the app) and the others get fixed
  labels (`open` "Mở", `snooze_1h` "Nhắc lại sau 1 giờ", `done` "Xong", `start_focus` "Bắt đầu tập trung"). The
  service worker (W) shows it, and on a click posts `/notifications/{id}/action` or opens `url`; the app then reads
  the full notification from `GET /notifications`.

**Desktop bridge (W ↔ K).** The hidden panel page forwards nudges to the shell with the Tauri command
`desktop_nudge {id, kind, title, body, actions, mascot}`; the shell shows a speech balloon next to the bubble (and a
native Windows toast when the bubble is hidden or the session is locked) and reports clicks back with the event
`mentor://nudge-action {id, action}`, which the panel turns into `POST /api/notifications/{id}/action`. The bubble
shows the mascot (`state` pushed with the existing `mentorSetState`, new field `mascot`).

*K notes (implemented in `apps/desktop`, 2026-11-03):*
- `invoke("desktop_nudge", {id, kind, title, body, actions, mascot})`: `id` string (≤128 chars) or integer, handed
  back unchanged in the event; `title`/`body` are clipped (120/400 chars), one of them must be non-empty; `kind`
  outside the list becomes `nudge`; `actions` ≤3, ids must match `word` or `word:value` (lowercase `[a-z0-9_]`,
  value ≤64 chars), labels ≤40 chars, invalid ones are dropped; `mascot` outside the state list becomes `happy`.
  Rejects (Promise error) only on a bad id or empty text. Resolves to where it went: `"balloon"` (on screen now),
  `"queued"` (after the current one), `"duplicate"` (same id already shown/queued, or same kind+title+body),
  `"toast"`, `"panel"` (the chat panel is open: the shell shows nothing, the page shows it inline), `"off"` (user
  turned nudges off in the tray, or signed out). Send each notification once; replays are ignored anyway.
- Event `mentor://nudge-action` payload `{id, action}`, emitted to the panel webview only; listen with
  `window.__TAURI__.event.listen("mentor://nudge-action", e => ...)` (the panel capability now grants
  `core:event:allow-listen`/`allow-unlisten`). `action` is one of the nudge's action ids, or `open` for a click on
  the balloon text or on a toast itself (even if the nudge had no `open` button). For `open` the shell has already
  shown the panel; the page should call the action API and put `prefill` in the composer. × / Esc / the 12 s
  timeout send nothing (the notification stays unread in the chat).
- `invoke("desktop_mascot", {state})`: what the chat is doing, for the bubble: `thinking` on `user_message` sent
  until `turn_done`, `sleepy` in quiet hours or with the sandbox asleep, `calm` in crisis/safety turns (blocks
  playful states, including nudge `happy`), `idle` otherwise; `wave`/`celebrate` play once. Reset to `idle` on
  sign-out. The bubble waves by itself at startup.
- Shell → bubble: `mentorSetState({unread, open, side, signedIn, mascot})`, `mentorMascotOnce(state)`.
- Routing in the shell: tray "Nhắc nhở: bong bóng" (default) shows the balloon, or a silent toast when the bubble
  is hidden, the session is locked, a full-screen app/presentation runs, or a screen reader is on; "thông báo
  Windows" always toasts; "tắt" shows nothing. Saved as `nudge_mode` in `bubble.json`.
- Toast privacy (N's rule): Windows toasts are silent and say only "Mentor" + a generic line per kind (same style
  as the Web Push payload); `answer:` buttons are left out and the others get fixed labels (`open` "Mở",
  `snooze_1h` "Nhắc lại sau 1 giờ", `done` "Xong", `start_focus` "Bắt đầu tập trung"). Only the balloon shows
  the real title, body and labels. A bundle (`bundled_ids`) is one `desktop_nudge` with the main id; one balloon.
- Mascot hints: a nudge's `mascot` shows on the bubble while its balloon is up; `wave` (checkin) and `celebrate`
  play once, then the bubble rests; `calm` from `desktop_mascot` overrides every hint.
- In the panel, `tauri-plugin-notification` injects a `window.Notification` shim with no permission behind it:
  in desktop mode the page should not use `Notification`/Web Push; `desktop_nudge` is the desktop channel.

*W notes (implemented in `apps/web`, 2026-11-03):*
- Cards: a `card` event or history item with a known `id` replaces that card in place; history is
  `{ts, role: "card", card}`, user items with `card_action` replay the click onto their card (answered flashcards
  show their answer; `reveal` only after an answer). Clicks send `card_action` with a `client_msg_id`, update the
  card at once, track the turn until `turn_done` echoes that id, and draw the learner's bubble from `card_echo`;
  `error` with `card_id` rolls the card back. Card buttons are disabled while a turn runs. Flashcard answers send
  the letter; the card grades locally only when `reveal` starts with the correct choice text or letter (else it
  stays neutral). Text right after a card is trimmed of leading whitespace. Quick replies show only while their
  turn's last item is the newest item (live event, or `suggestions` on the newest history item).
- Safety: the UI treats a turn as crisis context when the reply mentions support lines/self-harm or an approval's
  action/summary mentions crisis/safety (sticky until the next reply text); then the mascot is `calm`, no confetti,
  no streak line, no quick replies. A celebration plays (confetti + mascot `celebrate`) once, only when it arrives
  live; never from history or the tab's offline copy. Confetti is off under reduced motion.
- Nudges: in-app Sonner toast (mascot, title, body, ≤3 actions → `POST /notifications/{id}/action`; `open` puts
  `prefill` in the composer), never in quiet hours (they wait in the centre), never a sound. The centre loads
  `GET /notifications?limit=30` and handles `/chat?notification=<id>` and the service worker's
  `postMessage({type: "mentor:notification", id})`. `bundled_ids` shows "và N lời nhắc khác".
- Web Push: `public/sw.js` registered only from the Settings switch (`/sw.js?api=<absolute API base>`), hidden in
  desktop mode and when `enabled` is false; subscribe sends `{subscription, device}` (label like "Chrome ·
  Windows"), turning off deletes this endpoint only. Notifications are `silent`; action clicks POST from the
  worker (`start_focus` also focuses/opens the app), body clicks focus an open tab or open `url`.
- Desktop (`/popup`, inside Tauri): one `desktop_nudge` per notification (main id for a bundle); only a `"panel"`
  result (or a failed invoke) shows the toast in the page. `mentor://nudge-action` runs the same action code.
  `desktop_mascot` is sent on change: `calm` (crisis) > `celebrate` > `thinking` (turn in flight) > `sleepy` (quiet
  hours or sandbox asleep) > `idle`. No `Notification`/Web Push in desktop mode.
- Mascot: `packages/mentor-mascot/mascot.{js,d.ts}` is vendored into `apps/web/src/vendor/` by
  `apps/web/scripts/sync-mascot.mjs` (`predev`/`prebuild`; the prod Docker context is `apps/web` only), loaded
  client-side with a dynamic import; the brand mark stands in until it is defined. A test flags drift.

## 10. Practice, mock exams and progress (draft 2026-11-06; owners: C = content, P = practice backend, S = conversations + harness cards, W1 = web practice UI, W2 = web progress/shell)

Ported from the agent-mentor project (Kotlin; read-only reference: `core/.../assessment/*`,
`core/.../learner/Recommender.kt`, `docs/01-product/exam-modes-and-scoring.md`, `docs/03-ai-and-content/question-schema.md`,
`docs/03-ai-and-content/adaptive-test-generator.md`, `app-desktop/.../ui/screens/*`). Learner side only.
**No LLM in item selection, scoring or mastery.** The mentor only reads the results and talks about them.

### 10.1 Content (C)
- Bank: `mentor-content/bank/<subject>/<topic>.json` = agent-mentor bank format unchanged
  (`{schema_version: 1, questions: [...]}`, fields `id, revision, subject_id, type, topic_ids, language, stem, options,
  statements, short_answer, answer_key, hint, explanation, tip, option_feedback, difficulty{level 1-4, estimate 0..1},
  estimated_seconds, assets, source, quality_status, reviews`), **plus** `skill_ids: [str]` = ids from
  `mentor-content/curricula/<subject>.yaml` (≥ 1 per question). Subjects: `math`, `physics`, `english`.
  Text uses `$...$` / `$$...$$` LaTeX. Types: `SINGLE_CHOICE`, `TRUE_FALSE_GROUP`, `SHORT_ANSWER`.
- Only the 194 seed questions (`source.license == "PROJECT_AUTHORED"`) are imported. The bank-v2 items crawled from
  2048.vn are NOT imported (licensing unclear). Served only when `quality_status == "APPROVED"`.
- `mentor-content/exam-profiles.json` = agent-mentor `content/exam-profiles.json` (all `official_format: false`, each
  with its `disclaimer`, shown to the learner).
- Curricula: `math.yaml` extended with grade 11-12 skills covering the bank's topics; new `physics.yaml`,
  `english.yaml` (same format, CONTRACTS section 1). Each curriculum skill keeps `id, title, grade, prerequisites`;
  C may add `topic: <agent-mentor topic id>` so P can group skills into the topics shown in the UI.
- Importer: `infra/import-agent-mentor-bank.py --src <agent-mentor root>` (idempotent; refuses non-allowlisted licences).
- The bank is platform content: the gateway reads it from `MENTOR_CONTENT_DIR`; it is never copied into workspaces.

### 10.2 Engine and storage (P, in the gateway)
- Package `mentor_gateway/practice/`: bank loader, assembler (practice, mock, diagnostic), scoring
  (`mcq-v1`; `scoring-v2` for true/false groups 0/0.1/0.25/0.5/1 per 0-4 correct statements; short answers
  normalised: comma or dot decimal, minus, units stripped, compared at the key's precision or tolerance), recommender.
- Practice: minutes ∈ {10, 20, 30, 45}, goal ∈ `balanced | weak | challenge`, optional topic list. Target P(correct)
  ≈ 0.70 for core items and ≈ 0.50 for ~20 % stretch items from the learner's current mastery (section 10.4); ≤ 40 %
  per topic; recently seen items penalised; deterministic per `seed` so the started set equals the preview. Too few
  items: error `insufficient_content`, never pad.
- Mock: follows an exam profile (topic matrix + level mix, or the 3-part `OFFICIAL_FORMAT_MOCK` for math), timed,
  answers editable and hidden until finish, flags, auto-finish at time-out (server enforces the deadline).
- Diagnostic: ≤ 12 MCQ items, ≤ 15 min, 2 per topic over up to 6 topics, no feedback while answering; may be skipped.
- ops.db tables (new): `practice_sessions`, `practice_answers` (answer, draft, flagged, hints_seen, revealed,
  time_spent_sec, correct, points), `mastery_snapshots (user_id, subject, skill_id, mastery, at)`, `item_reports`.
- Evidence: on finish, one `LearningEvent` per answered item and skill id is appended to the workspace's
  `events.jsonl` in one mirror commit (author `system`), validated with `mentor_schemas.LearningEvent`
  (`type: "practice_item"`, `mode: "independent"` when no hint was seen and nothing was revealed before answering,
  else `"guided"`; mock items `independent`; `source_ref: "practice:<session_id>"`, `grader: "bank"`). Then mastery is
  recomputed with the same code as `mentor_scripts.bkt_update` (single source of truth; P decides how the gateway
  calls it) so `learning/<subject>/skills.md` and `review-queue.md` update at once, a `mastery_snapshots` row is stored
  per touched skill, and one line is appended to `learning/<subject>/practice-log.md`:
  `- 2026-11-06 20:15 · luyện tập 20 phút · 8/10 đúng · 1 gợi ý · chủ đề: Hàm số, Mũ-log · session p-…`
  (mock: `thi thử · 7,25/10`). The mentor reads that file; it never sees answers of an unfinished mock.
- Recommender (deterministic, port of agent-mentor `Recommender.kt`): codes `TAKE_A_BREAK` (≥ 120 min of practice +
  mock today), `TAKE_DIAGNOSTIC`, `PRACTICE_WEAK`, `PROBE_UNKNOWN`, `CHALLENGE_STRONG`, `TAKE_MOCK`, `REDIAGNOSE`,
  each with Vietnamese `title`, `reason` ("Vì sao: …") and an `action`.

### 10.3 API (P serves under `/api/practice`, W1/W2 consume; all need a session; THPT profile only)
| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/subjects` | | `[{id, label, topics: [{id, title, item_count}], diagnostic: "none"\|"done"\|"skipped", mock_profiles: [{id, label, type, item_count, time_limit_sec, disclaimer}]}]` |
| POST | `/preview` | `{subject, minutes, goal, topics?}` | `{seed, item_count, minutes, level_mix: [n1..n4], per_topic: [{topic, title, count}]}` |
| POST | `/sessions` | `{kind: "practice"\|"mock"\|"diagnostic", subject, minutes?, goal?, topics?, seed?, profile_id?}` | `Session` (below); starting a new one in the same subject finishes the old practice one (scored) |
| POST | `/diagnostic/skip` | `{subject}` | `{ok}` |
| GET | `/sessions/active` | `?subject=` | `Session \| null` |
| GET | `/sessions/{id}` | | `Session` (resume: position, drafts, flags, remaining time) |
| POST | `/sessions/{id}/answer` | `{position, answer, time_spent_sec}` | practice: `{correct, points, correct_answer, option_feedback?, statement_results?}`; mock/diagnostic: `{saved: true}` |
| POST | `/sessions/{id}/hint` | `{position}` | `{hint}` (practice only, before the answer is checked) |
| POST | `/sessions/{id}/reveal` | `{position}` | `{explanation, tip?}`; 409 before the item is answered; 403 in mock/diagnostic |
| POST | `/sessions/{id}/flag` | `{position, flagged}` | `{ok}` (mock) |
| POST | `/sessions/{id}/tick` | `{position, elapsed_sec}` | `{remaining_sec?}` autosave every 5 s and on leave |
| POST | `/sessions/{id}/finish` | | `Report` |
| GET | `/sessions` | `?subject=&limit=30` | `[{id, kind, subject, started_at, finished_at, score_10?, correct, total, minutes}]` |
| GET | `/sessions/{id}/review` | | items with the learner's answers, correct answers, explanations (finished sessions only) |
| GET | `/progress` | `?subject=` | `{skills: [{skill_id, title, topic, mastery, evidence, confidence: "high"\|"medium"\|"low", label, trend: [{at, mastery}]}]}` |
| GET | `/recommendations` | `?subject=` | `[{code, subject, title, reason, action: {kind: "practice"\|"mock"\|"diagnostic"\|"break"\|"progress", params}}]` (≤ 3) |
| POST | `/items/{item_id}/report` | `{session_id, reason: "wrong_key"\|"wrong_solution"\|"unclear"\|"typo"\|"other", note?}` | `{id, status}`; only after the answer was shown; ≤ 10/day |
| GET | `/items/reports` | | the learner's reports with status |

`Session = {id, kind, subject, profile_id?, started_at, deadline?, position, items: [ClientItem], answers: {position:
{answer?, draft?, flagged, checked, correct?}}, parts?: [{label, positions, points_each}], disclaimer?}`.
`ClientItem = {position, id, type, stem, options?, statements?: [{id, text}], short_answer?: {max_chars}, assets,
topic, topic_title, level, estimated_seconds}`; never the key, hint, explanation or feedback.
Labels: `Report.per_topic[].label` and progress labels use `Chưa có dữ liệu | Cần thêm dữ liệu | Cần củng cố |
Đang tiến bộ | Vững` (never "yếu"). `Report = {session, correct, total, answered, score_10?, minutes, hints,
per_topic: [{topic, title, right, total, mastery_before, mastery_after, label}], per_part?, recommendations,
disclaimer?}`. Mastery is never shown as an exam-score prediction.

### 10.4 Mastery source
Per skill: `learning/<subject>/skills.md` (BKT, section 4). Item difficulty for targeting = `difficulty.estimate`.
Topic mastery shown in the UI = mean of its skills weighted by evidence; no evidence = `Chưa có dữ liệu`.

### 10.5 Chat integration (S: harness + gateway; C: content)
- `show_card` gains kinds `practice {subject, minutes, goal, topics?, title, reason}` and `mock {subject, profile_id,
  title}`; validated against `/practice/subjects`; the web card has one button that opens the practice setup (or
  the mock confirm dialog) prefilled; nothing starts without the learner's click.
- Conversations: besides the daily main chat (`s-YYYYMMDD`), the learner can open named conversations
  (`session_id = "c-<id>"`, optional `subject`), each with its own transcript files and history reload. API:
  `GET/POST /api/conversations`, `PATCH/DELETE /api/conversations/{id}`, `GET /api/conversations/search?q=`
  (diacritic-insensitive over transcript text, newest first). The WebSocket `user_message` gains optional
  `conversation_id`. Nightly reflection and jobs read all of the day's transcripts.
- Slash commands are parsed by the web client (W2): `/luyen [môn] [phút]`, `/thithu [môn]`, `/tienbo [môn]` open the
  practice UI; `/nhac …`, `/nho …` are sent to the mentor as normal messages.
- C updates AGENTS.md/skills: the mentor reads `practice-log.md` and `skills.md`, proposes practice/mock via those
  cards, and `parent-report` covers every subject with a curriculum.

*W2 coordination (in progress, 2026-11-06; W1 please confirm or correct in your Built note):*
- Routes W2 links to (W1 owns them): practice setup `/practice?subject=<id>&minutes=<n>&goal=<g>&topics=<a,b>`,
  mock confirm `/practice/mock?subject=<id>&profile_id=<p>`, diagnostic `/practice/diagnostic?subject=<id>`,
  session review `/practice/review/<session_id>`. W2 builds them in one place: `src/lib/practice/routes.ts`.
- W2 owns `/progress` (Tiến bộ; `/learning` keeps the review queue/mistakes/files and links to it), the
  recommendation card `src/components/progress/NextSteps.tsx` (W1 may reuse it on the report screen), the
  conversation list/search, slash commands, text size and the F1/`?` shortcut overlay.
- Types W2 adds in `src/lib/practice/progressTypes.ts`: `ProgressSkill`, `Progress`, `Recommendation`,
  `SessionSummary` (shapes of section 10.3). API methods W2 adds to `ApiClient`: `getProgress(subject)`,
  `getRecommendations(subject?)`, `listPracticeSessions({subject?, limit?})`; mocks for them live in
  `src/lib/api/mock/mockProgress.ts`. W1 keeps the rest of `/practice` (subjects, preview, sessions, review...).
- Shared UI prefs `src/lib/uiPrefs.ts` (localStorage, per user): `textScale` (0.85..1.4) and `sounds`
  (default off). W1: read `useUiPref("sounds")` for any practice sound instead of adding a second switch.

### 10.6 Built (S, 2026-11-06): conversations and practice/mock cards
- **Cards** (`mentor_schemas.interaction`, `mentor_harness/cards.py`): `practice {subject: math|physics|english, minutes:
  10|20|30|45, goal: balanced|weak|challenge (default balanced), topics?: [1..6 topic ids, shape ^[a-z0-9][a-z0-9_-]*$],
  title ≤80, reason ≤200}`; `mock {subject, profile_id (^<subject>\.<name>$, e.g. math.mcq-mock.2026), title ≤80}`.
  The harness validates shape and the fixed subject list only; it does not call `/practice/subjects`, so **W1/P must
  tolerate unknown topic/profile ids** (hide the button or show "không còn bài này" and fall back to the setup page).
  No `card_action`: the card's button navigates (`/practice?subject=&minutes=&goal=&topics=a,b` and
  `/practice/mock?subject=&profile_id=`) and nothing starts without the learner's click. Allowed in turns and in
  notification-action jobs (other jobs: no). Refused in crisis context (`CRISIS_REFUSED_KINDS` = celebration, weekly,
  practice, mock; the gateway also skips relaying such job cards during a hold). History reload note
  `[đã hiện thẻ practice (...)]`.
- **Table** `conversations(user_id, id (12 hex), title ≤80, auto_title, subject?, created_at, updated_at, archived_at?)`
  (`mentor_gateway/db.py`; rows deleted with the account). Only the label lives in the DB; messages are
  `sessions/<day>/c-<id>.jsonl|.md` in the workspace (same format as the daily chat). Not sealed (title is short,
  learner-chosen; same class as `chat_sessions`).
- **API** (`api/conversations.py`; all need a provisioned session; CORS now allows PATCH). Conversation =
  `{id, session_id: "c-<id>", title, subject: str|null, created_at, updated_at, archived: bool}`.
  - `GET /api/conversations?archived=false|true|all` (default false) → `[Conversation]`, `updated_at` newest first.
  - `POST /api/conversations {title?, subject?}` → `Conversation`. No title = "Cuộc trò chuyện mới", renamed after the
    first words (≤50 chars) of its first typed message unless the learner named it; `subject` is a slug (`math`,
    `physics`, `english`, ...) or null. 422 on title >80 or a bad slug.
  - `PATCH /api/conversations/{id} {title?, subject? (null clears), archived?}` → `Conversation`; 404 unknown/other
    learner; 422 empty body or empty title.
  - `DELETE /api/conversations/{id}` → `{ok: true}`: removes the row and its transcripts (`c-<id>.jsonl` and `.md`, all
    days) from the mirror in one commit (author `user`); the sandbox picks that up on its next pull. Memory notes
    elsewhere (journal etc.) stay.
  - `GET /api/conversations/search?q=&limit=` (limit 1..50, default 30; q 1..200 chars) → `[{conversation_id: str|null (null
    = daily chat), session_id, date: "YYYY-MM-DD", ts, role: "user"|"mentor", snippet (≤~180 chars around the match,
    "…" at cut ends, original text and accents), title: str|null}]`, newest day first and newest message first within a
    day; one hit per message; cards and tool text are not searched. Case, diacritics and đ/d are ignored.
  - `GET /api/chat/history?conversation_id=<id>&limit=300` → the conversation's items across all days, oldest first
    (the newest `limit`); 404 for an unknown id. `date` is ignored when `conversation_id` is given.
- **WebSocket**: `user_message {conversation_id?}` and `card_action {conversation_id?}` → `session_id = "c-<id>"`
  (cards of a conversation are looked up in its transcript; without it the daily `s-YYYYMMDD`). A turn bumps
  `updated_at` and un-archives. Notifications, nudges and jobs still write into the daily chat.
- **Harness**: sessions, crisis stickiness, approvals and the `suggest_replies`/card state are all keyed by
  `session_id`, so they work per conversation unchanged. `Workspace.load_chat` already reads `*/c-<id>.jsonl` across
  day folders (last 40 messages), so a conversation keeps its context across days and sandbox restarts (tested).
- **Engagement**: a turn in a conversation counts as an active day (`chat_sessions.last_active_at`).
- Tests: `services/gateway/tests/test_gw_conversations.py`, `sandbox-image/harness/tests/test_harness_practice_cards.py`.

### 10.7 Built (C, 2026-11-06): bank, curricula, mentor content
- **Importer** `infra/import-agent-mentor-bank.py --src <agent-mentor root> [--dry-run]` (run with `uv run python`). Reads only
  `content/bank/{math,physics,english}/*.json`; refuses (reports) anything not `PROJECT_AUTHORED` + `APPROVED`
  (today: `phys.gas.004`, `NEEDS_HUMAN_REVIEW`); writes `mentor-content/bank/<subject>/<topic>.json` (file name = agent-mentor's:
  `function`, `exp-log`, `integral`, `oxyz`, `probability`, `statistics`, `thermal`, `gas`, `electromagnetism`, `nuclear`,
  `mechanics`, `waves-optics`, `grammar`, `vocabulary`, `word-formation`, `communication`, `reading`, `sentence-arrangement`),
  and copies `exam-profiles.json` verbatim. Idempotent (second run writes 0 files).
- **Imported: 193** questions (math 70: 60 SC, 4 TF, 6 SA; physics 63: 59 SC, 2 TF, 2 SA; english 60 SC). `skill_ids` come from
  `mentor-content/bank/skill-map.yaml` (`topics:` default per topic id, `questions:` per question id). `topic_ids[0]` is the
  topic; the file's topic = `id` minus the 3-digit suffix.
- **Curricula**: `math.yaml` 30 -> 66 skills (grade 11-12 added, ids `calculus.*`, `functions.*` (new: `monotonic.derivative`,
  `extrema`, `minmax`, `asymptotes`, `graph_reading`, `parameter`, `optimization`), `explog.*`, `integral.*`, `oxyz.*`,
  `statistics.grouped.*`, `probability.*`); `physics.yaml` 35 skills (`physics.<area>.<name>`); `english.yaml` 25 skills
  (`english.<area>.<name>`, bilingual titles). Skill ids are unique across subjects. Optional `topic: <bank topic id>` on a
  skill (e.g. `math.function`, `phys.gas`, `eng.reading`); skills without bank content (grade 10 math, electric field, circuit,
  phonetics...) have none, except a few tagged skills with no question yet (listed in `test_bank.py`). All prerequisites resolve, graphs acyclic.
- **Exam profiles**: all servable except `physics.format-2025-mock.2026` (needs 4 TRUE_FALSE_GROUP + 6 SHORT_ANSWER, bank has 2 + 2):
  P must not offer it (`KNOWN_GAPS` in `test_bank.py`). The math 3-part mock is servable only at exactly 4 TF / 6 SA, and all TF
  items are level 3, so its Part II level mix (0/.25/.5/.25) cannot be met: relax the mix, never pad. English/math MCQ mocks fine.
- Topic ids in profiles (`math.function`, `phys.gas`, `eng.grammar`...) equal the bank topic ids.
- **Mentor content**: AGENTS.md section 10 (practice/mock, labels, no unfinished-mock answers; 8,996/9,000 chars);
  `spaced-review` (part C), `exam-prep`, `parent-report` (v3: every curriculum subject, label words = UI labels, practice count
  only), `math-tutoring` (practice events are automatic: do not `record_event` them), `nightly-reflection` (reads `c-*.md`).
  `profile_id` added to the identifier allowlist of `test_content.py`; its curriculum-shape test now allows grade 8-12, 60-90 skills.
- Tests: `mentor-content/tests/test_bank.py` (schema sanity, skill ids, licences, profiles/gaps).

### 10.8 Built (W2, 2026-11-06): progress, recommendations, conversations UI, slash commands, text size, shortcuts
- **Routes**: `/progress` (new, THPT only, nav "Tiến bộ"; `?subject=math|physics|english`). `/learning` keeps skills table, review
  queue, mistakes and files and gets a button to `/progress`. Links into W1's screens are built only in
  `src/lib/practice/routes.ts`: `/practice?subject=&minutes=&goal=&topics=a,b`, `/practice/mock?subject=&profile_id=`,
  `/practice/diagnostic?subject=`, `/practice/review/<session_id>`; change them there if W1 differs.
- **Progress** (`src/app/(app)/progress/page.tsx`, `components/progress/*`, `lib/practice/progress.ts`): per subject, topics
  (evidence-weighted mean, label `Chưa có dữ liệu` when no evidence) → skills with a mastery bar plus an uncertainty band from
  `confidence` (high ±6 pp, medium ±14, low ±26), label badge, evidence count, sparkline of `trend`, the 30 last sessions with
  score and "Xem lại", and the disclaimer "Mức thành thạo là ước lượng, không phải dự đoán điểm thi". Labels outside the five
  contract words are mapped from mastery/evidence (never "yếu"). Uses `GET /practice/progress`, `/sessions?subject=&limit=30`.
- **Recommendations**: `components/progress/NextSteps.tsx` (`NextSteps` fetches `GET /practice/recommendations`;
  `RecommendationList` is the pure view W1 may reuse). Up to 3 steps with "Vì sao: …", first one is the only primary button,
  `TAKE_A_BREAK` is a separate gentle card with no button. Shown on `/progress` and inside the Hôm nay widget (THPT, hidden in
  crisis context; renders nothing on error/403/404).
- **Conversations**: header of the chat (full and `/popup`) has a conversation button (dialog: list, new, rename, subject tag
  math/physics/english, delete with confirm), a search button, Ctrl+N (new) and Ctrl+K (search, debounced, ≥2 chars,
  highlighted snippets, diacritic-insensitive on the client too). Active conversation is per tab/webview in sessionStorage
  (`lib/conversationNav.ts`); `ChatView` remounts on switch, history from `GET /chat/history?conversation_id=`, `user_message`
  and `card_action` carry `conversation_id`. A 404 on history falls back to the daily chat. The daily chat is always the first
  entry; "Hôm trước" is hidden inside a named conversation. `ApiClient` gained `listConversations`, `createConversation`,
  `updateConversation`, `deleteConversation`, `searchConversations`, `getConversationHistory`, `getProgress`,
  `getRecommendations`, `listPracticeSessions`. Mocks: `mock/mockConversations.ts`, `mock/mockProgress.ts`.
- **Slash commands** (`lib/slashCommands.ts`): `/luyen [môn] [phút]` (minutes snap to 10/20/30/45), `/thithu [môn]`, `/tienbo [môn]`
  route (full chat: in-app; pop-up: new window with the full app); `/nhac …`, `/nho …` are sent as normal messages; unknown
  subject shows a hint instead of sending. Subjects accent-insensitive (toán/toan/math, lý/ly/vat ly/physics, anh/tieng anh/english).
  Typing `/` shows an autocomplete list (↑↓, Tab to complete, Esc hides, Enter completes while the command is partial).
- **Settings**: card "Hiển thị và âm thanh": text size 85-140 % (step 5) applied app-wide and in the pop-up through the root
  font-size (all CSS is rem; a head script applies it before paint) and a sounds switch (default off). Stored in localStorage on
  the device (`lib/uiPrefs.ts`: `useUiPref("textScale" | "sounds")`, `readSounds()`); no server setting fits, so it is per device,
  not per account. W1's `sfx.ts` already reads this switch.
- **Shortcuts**: F1 or `?` (outside text fields) opens the overlay with the page's shortcuts plus global ones
  (`lib/shortcuts.ts`); W1 can add its own with `usePageShortcuts(id, title, list)`. Also "Tìm kiếm" and "Phím tắt" in the sidebar.
  `GlobalUi` is mounted in `AppShell` and in `/popup`. Ctrl+N may be reserved by a regular browser tab (the button always works;
  it works in the desktop webview).
- **Tests** (vitest): `lib/slashCommands.test.ts`, `lib/text.test.ts` (highlighting), `lib/practice/progress.test.ts` (labels,
  band, topics, recommendations, routes), `components/progress/NextSteps.test.tsx`, `lib/uiPrefs.test.ts`. `pnpm tsc --noEmit` and
  `pnpm lint` clean (one warning in W1's `mockPractice.ts`).
- **Gaps**: not verified against the real gateway (P's `/api/practice` was not up while I worked); search "Enter to open at the
  message" only opens the conversation (no scroll to the hit); no sidebar list of conversations in `AppShell` itself (they live
  in the chat header dialog); no archived-conversation UI (API supports it).

### 10.9 Built (P, 2026-11-06): practice engine and `/api/practice`
Code: `services/gateway/src/mentor_gateway/practice/` (`bank`, `topics`, `scoring`, `assembler`, `mastery`, `evidence`,
`recommender`, `tables`, `service`), router `api/practice.py`. Tests: `services/gateway/tests/test_gw_practice_engine.py`,
`test_gw_practice_api.py` (fixture bank `practice_fixtures.py`). Shapes of 10.3 hold; refinements and deviations:
- **Errors** are `{detail, code, ...}`: `insufficient_content` (422, + `available`, `required`), `bad_minutes`, `bad_goal`,
  `unknown_subject` (404), `unknown_topic`, `unknown_profile` (404), `active_session` (409, + `session_id`, `kind`: a running mock or
  diagnostic of that subject blocks starting another; a practice session is finished and replaced), `expired` (409: the deadline passed,
  the session was auto-finished; go to `/finish` for the report), `finished` (409), `not_answered` (409 reveal), `hints_locked` /
  `reveal_locked` / `flag_locked` (403), `answer_not_shown` (409 item report), `report_limit` (429), `evidence_failed` (503, session
  stays active, retry). NCS: 403 `practice is for THPT learners` (plain `detail`).
- **Positions are 0-based indexes** into `Session.items`. Answers: single choice = option id; true/false = 4 chars `T`/`F`/`-` for
  a-d (`"TTFF"`; `ĐĐSS` and `1100` also parse); short answer = the number as typed (`-0,5`, `-0.5`, unit allowed).
  `time_spent_sec` (answer) and `elapsed_sec` (tick) = seconds spent on that item so far.
- **Session** also has `status` (`active | finished | expired | abandoned`), `finished_at`, `remaining_sec` (mock/diagnostic while
  active), `minutes`, `goal`. `answers[pos]` = `{flagged, checked, hints_seen, ...}`; practice adds, once checked, `answer`, `correct`,
  `revealed` and `result` (same shape as the `/answer` response, so feedback survives a reload), and `hint` once a hint was used;
  mock/diagnostic add `draft` while active and `answer`/`correct` after finish. Practice resumes at the first unanswered `position`.
  `parts` = `[{label, positions, points_each}]` (3-part mock). `ClientItem.assets` is the bank's `assets` untouched (`{id, type:
  "diagram", alt_text, diagram: {kind: "function_plot", ...}}` or `{type: "table", table: {headers, rows}}`; text uses `$..$` LaTeX);
  `short_answer = {max_chars, unit, decimals}`. 3-part mock: the whole item list is in part order, easy to hard inside a part.
- **`/answer` (practice)** = `{correct (null = blank), points, max_points, correct_answer, option_feedback?, statement_results?:
  [{id, given, truth, correct, explanation?}]}`; `correct_answer` is the key in the answer encoding (`"TTFF"`, `"B"`, `"-0,5 m"`). A
  blank answer is a skip (no evidence). Replaying a checked position returns the stored result. `/hint` allows one hint per item
  (`hints_seen` 1). `/reveal` = `{explanation, tip?}`. `/tick` returns `{remaining_sec}` (mock/diagnostic) or `{}`; after the deadline
  or on a finished session `{remaining_sec: 0, expired: true}`.
- **Report** = `{session: {id, kind, subject, started_at, finished_at, score_10, correct, total, minutes, status}, correct, total,
  answered, score_10?, minutes, hints, per_topic: [{topic, title, right, total, mastery_before, mastery_after (null = no evidence),
  label}], per_part?: [{part, label, total, answered, correct, points, max_points}], recommendations, disclaimer?}`. Practice and
  diagnostic: `total` = answered; mock: `total` = all items, blanks count 0, `score_10` = points / max points x 10 (2 decimals).
- **`/review`** = a list of ClientItems plus `answer, correct, points, max_points, hints_seen, flagged, time_spent_sec,
  correct_answer, explanation, tip, hint, option_feedback (all options), statement_results, skills`; true/false `statements` there
  also carry `truth` and `explanation`.
- **`/progress`** = `{skills: [{skill_id, subject, title, topic, mastery (null = no independent evidence), evidence, guided,
  confidence, label, trend}], topics: [{topic, subject, title, mastery, evidence, confidence, label}]}`; `subject` omitted = all
  subjects. Topic mastery = skills weighted by independent evidence. Labels: no evidence `Chưa có dữ liệu`; evidence < 2 `Cần thêm
  dữ liệu`; mastery < 0.5 `Cần củng cố`; mastery >= 0.8 with >= 4 attempts `Vững`; otherwise `Đang tiến bộ`.
- **`/recommendations`** without `subject` = round-robin over subjects (one `TAKE_A_BREAK` at most), <= 3. `action.params` match the
  start request (`practice`: `{subject, minutes, goal, topics}`; `mock`: `{subject, profile_id}`; `diagnostic`: `{subject}`).
- **`/subjects`** lists only mock profiles the bank can satisfy now (`physics.format-2025-mock.2026` is hidden until 4 TF + 6 SA
  exist). In a 3-part mock the level mix is best effort (`LEVEL_FALLBACK`), never refused or padded.
- **Mastery sharing**: `mentor-scripts` is now a gateway dependency (`services/gateway/pyproject.toml`; it is a uv workspace member so
  `infra/gateway.Dockerfile`'s `uv sync --all-packages` already installs it). `practice/mastery.py` stages the learner's
  `events.jsonl` (+ curriculum) in a temp dir and calls `mentor_scripts.bkt_update` (`bkt_update`, `load_events`, `compute_states`), so
  `skills.md`/`review-queue.md` are byte-identical to the sandbox script's output (a test runs the script and compares). Curriculum:
  `MENTOR_CONTENT_DIR/curricula/<subject>.yaml`, else the workspace copy.
- **Schema change** (`mentor_schemas.LearningEvent`, old events stay valid): `type` also `"practice_item"`, `grader` also `"bank"`.
  Event id `practice-<session>-<position>-<skill>` (deterministic, so a retry never duplicates). One mirror commit (author `system`)
  per finish carries events, `skills.md`, `review-queue.md` and `practice-log.md`; it runs under the learner's `UserLocks` lock (which
  the sandbox push also takes) with compare-and-swap on `events.jsonl` and redo on a conflict.
- **Deadline**: wall clock (`started_at + time limit`; diagnostic 15 min), 2 s grace. Enforced on every request, by
  `PracticeService.sweep` (called from `Scheduler.tick`), and when listing active sessions.
- **Tables** (new, `practice/tables.py`): `practice_sessions` (stores a copy of its questions so resume/review ignore bank changes),
  `practice_answers`, `mastery_snapshots`, `item_reports`; account deletion removes them. Assembler `assembler-v3`: practice and mock
  are ports of `ExamAssembler.kt` (weights, allocation, 70 %/50 % targets, repeat penalties, slot repair); the diagnostic is a fixed
  plan (2 items on each of <= 6 topics by curriculum weight), not adaptive. Topic titles come from `practice/topics.py` (agent-mentor
  taxonomy for the 18 bank topics; optional `bank/topics.json` overrides).
- **Not done**: the `GET /sessions` list returns finished sessions only; item reports have no review UI (status stays `open`);
  per-item "skip" in practice is "answer with an empty string".

### 10.10 Built (W1, 2026-11-06): web practice, mock, diagnostic, LaTeX, diagrams
Code in `apps/web`: pages `src/app/(app)/practice/**` (+ `practice.css`), components `src/components/practice/*`, pure rules
`src/lib/practice/{logic,setup,diagram,expr,assets,sfx,reportCache,types}.ts`, API `src/lib/api/practiceHttp.ts` (HTTP) and
`src/lib/api/mock/{mockPractice,practiceBank}.ts` (fake gateway with its own tiny bank). `ApiClient.practice: PracticeApi`
covers subjects, preview, start, skipDiagnostic, active, get, answer, hint, reveal, flag, tick, finish, review, reportItem,
itemReports (W2's `getProgress`/`getRecommendations`/`listPracticeSessions` stay theirs; `PracticeApi` also has `list`,
`progress`, `recommendations` that nothing in W1 uses).
- **Routes** (THPT only, `RoleGate`): `/practice` (subject picker, or setup with `?subject=&minutes=&goal=&topics=a,b`),
  `/practice/mock?subject=&profile_id=` (confirmation dialog), `/practice/diagnostic?subject=`, `/practice/session/<id>` (player
  for practice, mock and diagnostic), `/practice/summary/<id>`, `/practice/review/<id>`. These match W2's `lib/practice/routes.ts`
  and S's cards, so that file did not change. Topic ids in links match a subject topic by full id or by its last dotted part;
  unknown ones are dropped with a notice. An unknown mock `profile_id` falls back to the first profile with a notice.
- **Nav / entry points**: "Luyện tập" in `AppShell` (THPT only); the pop-up header has a "Luyện tập" link (`target=_blank`, which
  `DesktopBridge` sends to the system browser = the full page); chat cards `practice`/`mock` (`PracticeLinkCard`, types added to
  `ChatCard`) render one button that opens setup/confirm prefilled (a plain link in the app, `target=_blank` in `/popup`).
- **LaTeX**: `Markdown` now uses `remark-math` + `rehype-katex` (`trust: false`, `throwOnError: false`, `errorColor: inherit`, so a
  broken formula shows its source); KaTeX CSS is bundled (`katex/dist/katex.min.css` in the root layout, fonts via the bundler, no
  CDN). `$..$` inline; `$$..$$` on its own lines = display (a one-line `$$x$$` renders inline-sized). New props: `inline`
  (span, paragraphs unwrapped; options/statements) and `renderAsset`. Applies to chat, workspace markdown, items, hints, solutions.
- **Assets**: `function_plot`, `force_diagram`, `geometry` are drawn by `lib/practice/diagram.ts` (port of `DiagramRenderer.kt` +
  `Expression.kt`, no eval) as inline SVG using theme CSS variables, with the asset's `alt_text` as `aria-label`; `table` assets
  (LaTeX in cells); `image` assets point to **`GET <API_BASE>/practice/assets/<sha256>`** (session cookie, PNG/JPEG). **P has not
  built that route yet** (CONTRACTS 10.9 does not mention images): until it exists, image figures show their alt text. Tokens
  `![](asset:<id>)` place an asset; unplaced assets render below the stem; solution-only assets come from `/reveal` (`assets`) or
  `/review` (`solution_assets`).
- **Player**: one item per screen; keys 1-4/A-D, Enter (check / next), H hint, E solution, S skip (sends a blank answer), L report,
  F flag, G grid, arrows (mock/review), Esc pause dialog; shortcuts are registered with `usePageShortcuts`. Timer from the
  server's `remaining_sec` (ticks every 5 s send **seconds spent on the current item**, as P specified), ≤ 5 min warning badge,
  auto-submit at 0 (also on `409 expired` or `tick.expired`), autosave on leave/tab hide, resume from `Session.position`,
  `answers[pos].result`/`hint` restore practice feedback. `409 active_session` shows "Làm tiếp". Effects: shake on a wrong option,
  bounce on a right one, "Chuỗi đúng ×n" pill from 2, optional sounds (`readSounds()` from `uiPrefs`, WebAudio tones), all CSS
  motion inside `prefers-reduced-motion: no-preference`; confetti only on the summary at ≥ 60 % (`fireConfetti` is already off
  under reduced motion). Disclaimers: items carry "Thử nghiệm · AI đã kiểm định"; the mock confirmation and summary show the
  profile disclaimer ("KHÔNG phải cấu trúc đề chính thức", "điểm KHÔNG dự báo điểm thi thật" as the gateway words it).
- **Summary** reads the `Report` cached by the player (sessionStorage) else calls `/finish` again (expects it to be idempotent);
  next steps = W2's `RecommendationList` (≤ 3). **Review** reads `/review` (array or `{items}`).
- **Mock mode** (`NEXT_PUBLIC_API_MOCK=1`): same shapes and error codes as 10.9 (wall-clock deadline, `active_session`, `expired`,
  `not_answered`, `*_locked`, blank = skip, `statement_results` objects). Subjects: Toán (20 items incl. 2 TF, 4 SA, diagrams),
  Vật lí, Tiếng Anh; math has an 8-item MCQ mock and a 12-item 3-part mock.
- **Dependencies added** (exact pins): `katex@0.16.22`, `remark-math@6.0.0`, `rehype-katex@7.0.1`.
- **Tests**: `src/lib/practice/{logic,diagram}.test.ts`, `src/components/practice/practice.test.tsx`,
  `src/lib/api/mock/mockPractice.test.ts` (70 tests with `Markdown.test.tsx`).
- **Gaps**: image asset route (above); not run against the real gateway session (no login available to W1); the pause dialog
  does not stop a mock clock (the gateway deadline is wall-clock); no per-item report list UI (P: status stays `open`); the
  `practice`-card button hides nothing when a topic no longer exists (the setup page handles it).

### 10.11 Grade filter (P, 2026-11-06)

Practice, mock and diagnostic follow the learner's grade (lớp 10-12). **Grade source**: no stored field; the gateway parses
`me/profile.md` (`Lớp: 11` / `Khối: 11` / `Grade: 11` line wins, else "học lớp 11A2", "học sinh lớp 11"; HTML comments and
bare mentions such as "ôn kiến thức lớp 10" are ignored). Unknown or outside 10-12 → `learner_grade: null`, nothing is
filtered. **Topic grade** = minimum `grade` of the curriculum skills whose `topic:` is that topic (`null` when none states
one → treated as in grade). A topic is *above grade* when its grade > learner grade.
- `GET /subjects`: each subject gains `learner_grade: int|null`; each topic gains `grade: int|null`, `above_grade: bool`; each
  `mock_profiles[]` entry gains `above_grade: bool` and `note: string|null` (e.g. "Đề này gồm chủ đề lớp 12 em chưa học"; a
  profile is above grade when its topic matrix, parts included, contains an above-grade topic).
- `POST /preview` and `POST /sessions` accept `include_above_grade: bool` (default `false`). Practice without `topics` uses
  only in-grade topics; with `topics` containing above-grade ones and no opt-in → 422 `above_grade_topic` (`topics: [...]`).
  Mock of an `above_grade` profile without opt-in → 422 `above_grade` (`detail` = the note, `topics: [...]`); with no
  `profile_id` the first in-grade profile is picked (404 `unknown_profile` if none). Diagnostic always uses in-grade topics
  only (the flag is ignored). No in-grade content → 422 `insufficient_content` with a Vietnamese `detail` naming the grade.
- `GET /recommendations` never suggests above-grade topics or an above-grade mock.
- Web: grey out above-grade topic chips with a "lớp N" badge; opt-in toggle "Thử cả chủ đề lớp trên" that sends
  `include_above_grade: true` (and unlocks those chips); mock cards with `above_grade` show `note` and require the toggle
  (or a confirm) before starting; show the `insufficient_content` `detail` as-is.

## 12. First-run tour and one-time tips (2026-11-06; owner W)

Replaces the auto-opening "Hướng dẫn thiết lập" modal. Progress lives on the gateway so the tour never repeats across
devices or in the desktop pop-up. Table `user_onboarding` (user_id pk, `tour_step`, `tour_completed_at`,
`tour_skipped_at`, `tips_seen` JSON); a new table because `create_all` does not add columns to existing SQLite tables.
Deleted with the account.

- `GET /api/onboarding` → `TourState` `{tour_step: "welcome"|"ask"|"practice"|"time"|null, tour_completed_at, tour_skipped_at, tips_seen: string[]}`.
  Session + provisioned learner (409 before onboarding). The same object is in `GET /me` as `tour`.
- `PUT /api/onboarding`, one change per call, returns the new `TourState`; empty body = 422:
  `{step}` resume point; `{complete: true}` / `{skip: true}` end the tour (first time kept, `tour_step` → null);
  `{restart: true}` replay (clears completed/skipped, step = welcome, `tips_seen` kept); `{tip: "<id>"}` marks a tip seen
  (`^[a-z0-9_-]{1,40}$`, unique, at most 50). Tip ids: `progress`, `plans`, `practice`.
- Web starts the tour by itself when `onboarding_state == active`, no step/completed/skipped, and the learner never closed
  the old setup guide (`setup_guide_dismissed_at == null`). THPT: welcome, ask, practice, time. NCS: welcome, ask, time.
  The pop-up runs ask + time only and shares the saved step.
- Study time (step "time") uses `GET/PUT /settings` only. THPT hour H: `evening_review` at H-0:30, `review_due` at H:00
  (missing routines are added; weekdays of an existing cron are kept); NCS: `evening_wrapup` at H:00; "Không cần nhắc"
  disables them. Quiet hours and proactivity are never changed; the finish card says when they would swallow the reminder.
