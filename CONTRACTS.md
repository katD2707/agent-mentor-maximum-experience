# CONTRACTS — how the parts of the mentor talk to each other

Product spec: `../REQUIREMENTS-PLAN.md`. This file pins the interfaces so the
tracks below can be built in parallel. Shapes in Python live in `packages/mentor-schemas` and are the
source of truth; this file explains them and adds the HTTP/CLI/file-format contracts.

**Rules for every track**
- Do not edit `packages/mentor-schemas`, `CONTRACTS.md`, the root `pyproject.toml` or another track's
  directory. If a contract is wrong or missing something, work around it locally and list the needed
  change in your final report.
- Python 3.11, `uv` workspace (`uv sync --all-packages`, `uv run pytest <your dir>`), pydantic v2, ruff.
  Add your own dependencies only in your own `pyproject.toml`.
- Code and comments in English. Everything a learner reads is Vietnamese.
- Tests must not call the real FPT endpoint or the internet. Use fakes.
- Time zone for learner-facing dates: `Asia/Ho_Chi_Minh`.

> The product was redesigned (REQUIREMENTS-PLAN.md). Gone: parent channel (Zalo), email ingest, crisis/wellbeing, free chat,
> the NCS research tools, magic-link login, SearXNG/web tools, the per-learner Docker sandbox and the old Next.js and desktop
> apps. Roles are `student` and `teacher`.

## Run, content and releases

- How to run the gateway, the app (web, mock, desktop) and the course builder: [README.md](README.md); deployment and env: `infra/README.md`.
- Published courses live in `mentor-content/courses/<course-id>/<version>/` (`pack.json` + assets) with `catalog.json`; the gateway
  serves them (section 11). Publishing a course never needs a new app.
- App releases (desktop installers, updater feed, web build) are a separate pipeline: [RELEASING.md](RELEASING.md). The only
  link between them is `pack.json` `min_app_version`.

## 0. Tracks and ownership

| Track | Owns | Summary |
|---|---|---|
| A. Harness | `sandbox-image/harness/` | Agent loop as an importable library (tools, hooks, scripted fake model); no server |
| B. Content | `mentor-content/` | `AGENTS.md`, skills, workspace templates, math skill graph, question bank, curricula |
| C. Scripts | `sandbox-image/scripts/` | Deterministic CLIs: events, BKT, SymPy, PDF |
| D. Gateway | `services/gateway/`, `infra/` | Auth (bearer token), ops DB, mirror, scheduler/jobs, notifications, push, practice engine, REST |
| F. App | `apps/app/` | Vite + React app, packaged with Tauri 2 for desktop |

## 1. Workspace (owner of format: B; enforced by A and D)

Layout: plan section 6.1, constants in `mentor_schemas.WorkspacePaths`. Changes from the plan:
- The identity file is **`AGENTS.md`** (models are not Claude).
- Skills: `.mentor/skills/<group>/<skill-name>/SKILL.md`, group ∈ `core`, `student`.
- Math skill graph: `.mentor/curricula/math.yaml`.
- Scripts are the package `mentor-scripts` (installed where the agent runs), not copied into the workspace.

Write permissions: `mentor_schemas.is_agent_writable(path)`. The harness must refuse agent writes elsewhere.

Provisioning (D does it on a student's first login): copy `mentor-content/workspace-templates/<profile>/`
to the workspace root, copy `mentor-content/AGENTS.md`, copy `mentor-content/skills/{core,<profile>}/` to
`.mentor/skills/`, copy `mentor-content/curricula/` to `.mentor/curricula/`, `git init`, first commit
authored `system <system@local>`.

### SKILL.md format
```markdown
---
name: memory-keeper
description: One line, Vietnamese or English, used in the skills index the model sees every turn.
profiles: [student]
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

## 2. Job execution (no sandbox)

There is no per-learner container and no sandbox HTTP API any more. Jobs (routines from `routines.yaml`, `next_wake`,
notification actions) are rows in the ops DB (`jobs`); the scheduler tick hands each due one to a `JobExecutor`
(`mentor_gateway.jobs`): `async (JobRequest, workspace_dir) -> JobResult`. No executor configured = the job finishes as
`skipped` ("no job executor configured"). The server-side agent workers (course builder, planner) will implement it on top of
`mentor_harness` (`Harness(settings, model, script_runner=...)` with `run_turn`, `stream_turn`, `run_job`).
Gateway-only routines (`review_due`) need no executor. `JobRequest`/`JobResult`/`OutboxItem` shapes: `mentor_schemas`.
`OutboxItem` kinds: `notify_user` (payload `NotifyPayload`, section 9) and `next_wake`.

## 3. Harness tools (A implements; B's skills refer to these names)

This is the tool set of the `mentor_harness` library, for the server-side agents (planner, course builder). The gateway exposes no
chat, so students never call these directly; the notification and card tools stay in the library only.

| Tool | Args | Notes |
|---|---|---|
| `read_file` | `path`, `offset?`, `limit?` | Any workspace path except `.git/` |
| `list_dir` | `path` | |
| `grep` | `pattern`, `path?` | Regex, returns `path:line: text`, capped |
| `write_file` | `path`, `content` | Only `is_agent_writable` paths  |
| `edit_file` | `path`, `old`, `new` — or `path`, `edits` (list of `{old, new}`) | Exact unique match. `edits` applies several changes to one file in order, in one write; all or nothing (`edits[i]` named in the error). Not both forms in one call |
| `delete_file` | `path` | Only `is_agent_writable` paths; used for "quên" and processed inbox files |
| `move_file` | `src`, `dst` | Binary-safe move/rename; both paths `is_agent_writable` (e.g. scans `inbox/` → `learning/evidence/scans/`) |
| `run_script` | `name`, `input` (object) | Runs `python -m mentor_scripts.<name>` with `input` as JSON on stdin; allowlist = section 4 |
| `look_at_image` | `path`, `question` | Calls alias `mentor-vision`; returns text |
| `notify_user` | `text`, `kind?`, `title?`, `actions?` (≤3 `{id, label}`), `mascot?`, `prefill?` | Adds `OutboxItem(notify_user)`, payload `NotifyPayload` (section 9); queues nothing after a crisis alert in the same turn/job |
| `schedule_wake` | `at`, `job_kind`, `prompt?` | Adds `OutboxItem(next_wake)`. Not `focus_end` (only `start_focus` schedules it) |
| `suggest_replies` | `items` (1..3 `{label (≤40), text? (≤300, default label)}`) | Turns only, section 9. The last call of a turn wins; sent as `suggestions` just before `done`, kept on the last `mentor` transcript record. No tool UI events |
| `show_card` | `kind`, `data` | Section 9. Kinds `flashcard`, `deadline`, `checkin`, `weekly`, `celebration`, `practice`, `mock` (not `focus`: use `start_focus`). Jobs: only `weekly`, `checkin`, `deadline` (notification-action jobs: all but `focus`; written into that day's chat transcript, relayed live when the chat is open). Data validated per kind, unknown fields refused, ≤3 cards per turn/job. `flashcard.skill` must be listed in a `learning/**/review-queue.md`. `weekly`: missing `focus_minutes`/`streak_days` are computed (activity `start_focus`/`focus_extend` of the last 7 days; consecutive days with a learner chat message). `celebration`, `weekly`, `practice` and `mock` refused in crisis context. `practice` `{subject, minutes, goal?, topics?, title, reason}` and `mock` `{subject, profile_id, title}`: section 10.5 |
| `start_focus` | `task` (≤120), `minutes` (5..90) | Turns, and jobs started by a notification action (section 9). Emits a `focus` card, adds `OutboxItem(next_wake)` `{at: ends_at, job_kind: "focus_end", card_id, task, minutes}`, logs activity `start_focus` ("Bắt đầu tập trung N phút: task", target = card id). One per turn |
| `celebrate` | `title` (≤80), `detail?` (≤200) | Turns, and jobs started by a notification action. One `celebration` per turn (also counting `show_card` celebration), shown at the end of the turn; refused (tool error) and any held celebration dropped when `flag_crisis` ran in the session or `wellbeing-and-crisis/SKILL.md` was read in it |
| `request_approval` | `action`, `summary`, `details` | Emits `approval_request`, waits for `/v1/approvals` (turns only). Not needed before `calendar_*` writes (they ask themselves); a `scope: session` approval of an action id also covers the calendar tool with that id |

Model aliases: `mentor_schemas.ModelAlias`. A session sticks to `mentor-chat`; images go through `look_at_image`;
the job `nightly_reflection` uses `mentor-reasoning`. Chat-style tools (`suggest_replies`, `show_card`, `start_focus`, `celebrate`,
`request_approval`) stay in the library but nothing in the gateway exposes a chat any more.

Context loaded at the start of every turn (plan 6.5), in this order so the prefix stays cacheable:
`AGENTS.md` → skills index (name + description of skills for the profile), then the full body of skills with
`preload: true` (today: memory-keeper) → `me/profile.md`, `me/preferences.md`,
`me/now.md`, `goals/goals.md`, `goals/plans/this-week.md`, last 3 journal files → file map (names only of
`me/`, `goals/`, `learning/`, `research/`, `reports/`, ≤15 per folder; `inbox/` as a count; `routines.yaml`)
→ today's date/time.
Tool calls of one model response: consecutive read-only calls (`read_file`, `list_dir`, `grep`, `look_at_image`,
other pure reads) run concurrently; all others one at a time, in order.
Tool results go back in the order of the calls.

## 4. Scripts (C implements, A runs, B's skills mention)

Uniform protocol: `python -m mentor_scripts.<name>`, cwd = workspace root (also env `WORKSPACE_ROOT`),
input JSON on stdin, output JSON on stdout, exit code 0 on success, 1 with `{"error": "..."}` otherwise.

| Name | Input | Output | Effect |
|---|---|---|---|
| `record_event` | `LearningEvent` fields minus `event_id`, `ts` | `{"event_id"}` | Validates and appends to `events.jsonl` |
| `bkt_update` | `{subject: "math"}` | `{skills_updated}` | Reads events + curriculum, writes `learning/<subject>/skills.md` and `review-queue.md` |
| `sympy_check` | `{kind: "solve"\|"equivalent"\|"simplify", problem, answer}`, or `{checks: [that, ...]}` (1..10) | `{correct, expected, detail, verified}`; batch: `{results: [that, ...], all_correct}` | Read-only. Batch = one tool round for a whole quiz or solution |
| `pdf_extract` | `{path, max_chars?: 200000, start_page?, end_page?}` (pages from 1, inclusive) | `{pages: [{n, text}], page_count, truncated}` | Read-only; pypdf, no OCR |
| `pdf_render` | `{path, pages?: [n] (default first 3, ≤5), width?: 1400 (400..2000)}` | `{images: [{n, path}], page_count}` | Writes `<pdf stem>-p<n>.png` next to the PDF (must be agent-writable); pypdfium2. For scanned PDFs → `look_at_image` |

`skills.md` written by `bkt_update` is a markdown table: `| skill_id | Tên | Mastery | Bằng chứng | Lần cuối |`.

`sympy_check` answer format (what skills send): SymPy-style expressions; multiple solutions separated by `;`
(`x = 2; x = -4`); variables of a system separated by `,` (`x = 1, y = 2`); the literal `vô nghiệm` means no
solution. The script also accepts the looser handwritten forms it can parse (`x²`, `2x`, `hoặc`, `S = {…}`).

## 5. Gateway API (D serves, the app consumes)

Base `http://localhost:8000/api`, JSON. Auth: `Authorization: Bearer <token>` (token from login; long-lived, 365 days; only its
hash is stored; logout deletes it). CORS allows `http://localhost:5173`, `tauri://localhost`, `http://tauri.localhost`,
`https://tauri.localhost` (+ `WEB_ORIGIN`, `CORS_ORIGINS`); no cookies. `MENTOR_ENV` unset means `prod`; `MENTOR_ENV=dev` seeds
`hocsinh`/`123456` (student, "Lan") and `giaovien`/`123456` (teacher, "Thầy Minh"). There is no sign-up and no password reset:
accounts are seeded or made with `python -m mentor_gateway.cli create-user` (`deploy.sh user`).

**Errors** with a machine code are `{"error": "<code>"}`: `invalid_credentials` (401), `role_mismatch` (403), `unauthorized`
(401, missing/expired token). Other errors are FastAPI's `{"detail": ...}`; practice errors `{detail, code, ...}` (section 10.3).

**User** = `{id, role: "student"|"teacher", username, display_name, age_band: "g1_5"|"g6_9"|"g10_12"|"uni"|null,
birth_year: int|null, language: "vi"|"en"|null, theme: "light"|"dark"|"system", quiet_until: ISO-8601 UTC|null}`. `username` is unique (stored lower-case,
login is case-insensitive); the password is hashed with stdlib scrypt.

**Birth year and age band.** `birth_year` is asked once at first run (UI: a select, 2020 down to 1980) and stored on the user;
`null` means first run is still due. `age_band` is never stored as truth: it is derived from `birth_year` and today's date on
every request (`mentor_gateway/age.py`, the clock is the gateway clock) and everything that used the stored band (catalog and
search filter and bonus, planner, practice, Ask) reads the derived value. The Vietnamese school year starts on 1 September and
grade 1 is the year a child turns 6: `grade = schoolYearStart - birth_year - 5` where `schoolYearStart` is the current year
from September on and the previous year before it. Grade <= 5 (including before grade 1) is `g1_5`, <= 9 `g6_9`, <= 12
`g10_12`, above that `uni`. Example: born 2010 is `g10_12` in November 2026 and `uni` in November 2030. The app computes the same
band locally on every launch and re-checks on focus and every few minutes, so the density changes by itself across 1 September.
Age and grade are never shown to the learner; settings show a read-only "Năm sinh". Migration: `users.birth_year` is added to
an older database and rows that only had a stored band get a birth year in the middle of it (the old `age_band` column is kept
but no longer read). The dev student `hocsinh` is born 2010. An operator corrects a wrong year with
`python -m mentor_gateway.cli set-birth-year --username X --year Y`; students cannot.

| Method | Path | Body / query | Response |
|---|---|---|---|
| POST | `/auth/login` | `{username, password, role}` | 200 `{token, user}`; wrong password or unknown user 401 `invalid_credentials`; right credentials, other role 403 `role_mismatch`; a student's workspace is created on the first login |
| POST | `/auth/logout` | | 204 |
| GET | `/me` | | `User` |
| PATCH | `/me` | `{birth_year?, language?, theme?, display_name?}` (only present fields change; `language` may be `null`; `age_band` is derived and ignored) | `User`; 422 for unknown values (`birth_year` outside 1950-2025, or `null`) or an empty name. `birth_year` is accepted only while it is `null`: afterwards 409 `birth_year_locked`. `role`/`username` cannot change |
| PUT | `/me/quiet` | `{until: ISO-8601 string \| null}` | `{until}` (UTC, `Z`). A future `until` holds back every notification and proactive routine until then; `null` clears it. Jobs still run |
| * | `/practice/...` | section 10.3 | students only (every age band); a teacher gets 403 `role_mismatch` |
| POST | `/uploads` | multipart `file` | `{path, mime_type}` (saved under `inbox/`; students) |
| POST | `/uploads/mobile-token` | | `{upload_url, expires_at}` (students) |
| GET/POST | `/m/{token}` | multipart `file` | phone upload page / `{path}` (no auth; token-bound) |
| GET | `/workspace/tree` | `?prefix=` | `[{path, type: "file"\|"dir", size, modified_at}]` (no `.git`, no `.mentor` except `.mentor/activity.jsonl`; students) |
| GET | `/workspace/file`, `/workspace/raw` | `?path=` | `{path, content, sha}` / raw bytes |
| PUT/DELETE | `/workspace/file` | `{path, content, base_sha}` / `?path=` | `{sha}` / `{ok: true}`; 409 stale `base_sha`; 403 outside `me/`, `goals/`, `learning/` |
| GET | `/workspace/history`, `/workspace/export`, `/activity` | | commits / zip / `[ActivityEntry]` |
| GET | `/notifications` | `?limit=30` (1..100) | `[Notification]` newest first (section 9) |
| POST | `/notifications/{id}/action` | `{action}` | section 9; 404 unknown or another user's, 422 invalid |
| GET | `/engagement` | | section 9 |
| GET | `/push/vapid-public-key` | | `{enabled, public_key: str\|null, subscribed_devices}` |
| POST/DELETE | `/push/subscribe` | `{subscription, device?}` / `{endpoint?}` | `{ok, id}` / `{ok, removed}` |

`GET /healthz` → `{status: "ok"}` (not under `/api`).

**Age band → practice grade** (section 10.11): `g1_5` → grades up to 5, `g6_9` → up to 9, `uni` → no filter, `g10_12` or unset →
the exact grade 10-12 read from `me/profile.md` as before.

**Dev DB reset.** The users table changed (no email, new columns); `create_all` cannot alter tables. A SQLite ops DB with the old
schema is dropped and recreated on start-up (logged); a Postgres one raises. Manual wipe: delete `<MENTOR_DATA_DIR>/ops.db`
(and `mirrors/`, `workspaces/` to drop old learner data), e.g. `Remove-Item -Recurse -Force var-dev`.

## 8. Ports and env (dev)

| Service | Port | Key env |
|---|---|---|
| Gateway | 8000 | `MENTOR_ENV=dev` (unset = `prod`: no dev accounts, needs `MENTOR_MASTER_KEY`), `MENTOR_DATA_DIR`, `MENTOR_CONTENT_DIR`, `WEB_ORIGIN` (default `http://localhost:5173`), `CORS_ORIGINS`, `SEED_DEV_ACCOUNTS`, `VAPID_*`, `BACKUP_*`, `GATEWAY_BACKGROUND_TASKS`, `SCHEDULER_INTERVAL_SECONDS` |
| Model router (LiteLLM) | 4000 | `FPT_API_BASE`, `FPT_API_KEY`, `MODEL_ROUTER_MASTER_KEY`; config `services/model-router/config.yaml` |
| App (`apps/app`, Vite) | 5173 | `pnpm dev`; talks to `http://localhost:8000/api` |

## 9. Notifications, nudges, mascot (trimmed 2026-11-06)

**Mascot (M).** One framework-free custom element `<mentor-mascot state size>` in `packages/mentor-mascot/`
(ESM `mascot.js` + inline SVG, no runtime deps), used by `apps/app`. States: `idle`, `listening`,
`thinking`, `talking`, `happy`, `celebrate`, `sleepy`, `calm` (gentle, for serious topics), `wave` (greeting).
Event `mascot-done` fires when a one-shot state (`celebrate`, `wave`) ends, then it returns to `idle`.
Built (M, 2026-11-03): attributes also `label` (aria name; `""` = decorative), `tail` (`right|left|none`, desktop maps
its docked side), `theme` (`light|dark`, else OS), `motion` (`reduce|full`, else OS). `el.play(state)` returns a
promise (one-shots resolve with `{state, interrupted}`); `mascot-done.detail = {state, interrupted}`. Colors via
`--mascot-body`, `--mascot-ink`, `--mascot-cheek`, `--mascot-spark` (web sets body/ink to `--accent`/`--accent-text`).
Exports `MentorMascot`, `defineMentorMascot()`; SSR-safe import. Types in `mascot.d.ts`; details in its README.

**Notifications** (`GET /api/notifications`, `notifications` + `notification_meta` tables). A `Notification` = `{id, kind, title, body,
actions: [{id, label}] (≤3), mascot, prefill, text, created_at, status, delivered_at, read_at, answer}`; kinds `checkin`, `deadline`,
`review`, `focus_end`, `celebration`, `nudge`. They are created from `OutboxItem(notify_user)` (payload `NotifyPayload`) or by
gateway routines. Delivery policy (`notifications.py`): proactivity in `routines.yaml` (`off` drops all but `focus_end`; `normal` = one
bundled delivery per local day, `deadline`/`focus_end`/snoozed items exempt; `high` = at once), `quiet_hours` and the user's
`quiet_until` (section 5) hold everything back, expired items are dropped, delivery goes to live connections registered on the
hub, else Web Push (the notification's own title and text, no lock-screen privacy handling), else the item waits in the pending list. Nothing is delivered over a socket yet
(the chat WebSocket is gone); the app polls `GET /api/notifications`.

**Actions** (`POST /api/notifications/{id}/action`): `open` (returns `prefill`), `done`, `snooze_1h` always allowed; `start_focus` and
`answer:<x>` only when the notification offers them. Idempotent per (id, action, delivery number); a content-free audit row is
written. `start_focus`/`answer:` enqueue a short job for the `JobExecutor`.

**Routines** (`routines.yaml`; defaults in the workspace template): `nightly_reflection` (platform, not editable), `evening_review`,
and the proactive `morning_checkin`, `evening_wrapup`, `review_due` (the last is gateway-only: one `review` notification per local
day when `learning/*/review-queue.md` has due rows). Proactive routines are skipped when proactivity is `off`, in quiet hours or
while `quiet_until` has not passed. `routine_policy.py`: platform job kinds only from their own fixed routine, at most one run
per hour.

**Engagement** (`GET /api/engagement`): `{streak_days, today: {focus_minutes, done}, week: {focus_minutes, milestones_done,
mistakes_fixed, active_days}}` from workspace commits by the user, notification taps and `focus_end` jobs; cached a minute.

**Web Push** (`push.py`): VAPID keys via `python -m mentor_gateway.cli vapid-generate`; subscriptions are sealed with the master
key; a 404/410 from the push service deletes the subscription.

## 10. Practice, mock exams and progress (draft 2026-11-06; owners: C = content, P = practice backend)

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

### 10.3 API (P serves under `/api/practice`, the app consumes; all need a bearer token; students only, every age band, teachers get 403 `role_mismatch`)
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
  `spaced-review` (part C), `exam-prep` (v3: every curriculum subject, label words = UI labels, practice count
  only), `math-tutoring` (practice events are automatic: do not `record_event` them), `nightly-reflection` (reads `c-*.md`).
  `profile_id` added to the identifier allowlist of `test_content.py`; its curriculum-shape test now allows grade 8-12, 60-90 skills.
- Tests: `mentor-content/tests/test_bank.py` (schema sanity, skill ids, licences, profiles/gaps).

### 10.9 Built (P, 2026-11-06): practice engine and `/api/practice`
Code: `services/gateway/src/mentor_gateway/practice/` (`bank`, `topics`, `scoring`, `assembler`, `mastery`, `evidence`,
`recommender`, `tables`, `service`), router `api/practice.py`. Tests: `services/gateway/tests/test_gw_practice_engine.py`,
`test_gw_practice_api.py` (fixture bank `practice_fixtures.py`). Shapes of 10.3 hold; refinements and deviations:
- **Errors** are `{detail, code, ...}`: `insufficient_content` (422, + `available`, `required`), `bad_minutes`, `bad_goal`,
  `unknown_subject` (404), `unknown_topic`, `unknown_profile` (404), `active_session` (409, + `session_id`, `kind`: a running mock or
  diagnostic of that subject blocks starting another; a practice session is finished and replaced), `expired` (409: the deadline passed,
  the session was auto-finished; go to `/finish` for the report), `finished` (409), `not_answered` (409 reveal), `hints_locked` /
  `reveal_locked` / `flag_locked` (403), `answer_not_shown` (409 item report), `report_limit` (429), `evidence_failed` (503, session
  stays active, retry). Teachers: 403 `{"error": "role_mismatch"}`.
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

### 10.11 Grade filter (P, 2026-11-06)

Practice, mock and diagnostic follow the learner's grade. **Grade source** (P1-A): the user's `age_band`: `g1_5` = ceiling grade 5,
`g6_9` = 9, `uni` = `null` (no filter), `g10_12` or unset = parsed from `me/profile.md` as below. The gateway parses
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
- App: grey out above-grade topic chips with a "lớp N" badge; opt-in toggle "Thử cả chủ đề lớp trên" that sends
  `include_above_grade: true` (and unlocks those chips); mock cards with `above_grade` show `note` and require the toggle
  (or a confirm) before starting; show the `insufficient_content` `detail` as-is.

### 10.12 Practice from courses (P5-A, 2026-11-07)

Luyện tập draws from the quiz items of the student's enrolled courses (at the **pinned** version) as well as the bank, for every age
band. Code: `practice/sources.py` (QuizItem -> engine item), `practice/mixed.py` (selection, home, result lines). No LLM.
- **Start variants**: `POST /sessions {source}` instead of `{kind, subject}` (old bodies still work). `source`: `quick` (the default
  session), `course:<course_id>` (lessons studied so far), `mock:<profile_id>` (bank mock, same as `kind: "mock"`). `quick` and `course:`
  give a normal `kind: "practice"` session (hint, one-answer-at-a-time feedback, resume) with `subject` `"quick"` / `"c:<course_id>"`
  and `params.mixed = true`. Errors: `insufficient_content` (422, fewer than 3 items), `course_not_found` (404, not enrolled),
  `bad_source`, `unknown_profile`, `bad_request`. Starting one replaces the unfinished practice session of the same subject.
- **Size by age band** (never padded): g1_5 5 items / 6 min (PICTURE_CHOICE, TAP_COUNT, SINGLE_CHOICE first), g6_9 8 / 10, g10_12 and
  uni 10 / 12. Items come from studied lessons (up to the furthest lesson with a block done, the last lesson, or a quiz item answered),
  scored by: FSRS due (`planner.fsrs_items.due_items`), last answer wrong, weak skill (BKT < 0.5), lesson being studied, never seen;
  minus repeat penalty and distance from the difficulty that suits the learner's mastery; <= 40 % per lesson; bank items (in-grade,
  weak or due only) <= 30 % when courses supply the session. `Selected.reasons`: `DUE_REVIEW PREVIOUSLY_WRONG WEAK_SKILL CURRENT_LESSON
  NEW_ITEM`. Deterministic per `seed`. Mocks stay bank/exam-profile based.
- **`GET /api/practice/home?seed=`** -> `{quick: {count, minutes, from: [{course_id, label, n} | {subject, label, n}], seed, reason?:
  "insufficient_content"}, mocks: [{profile_id, title, subject, minutes, items, last_score}], by_course: [{course_id, title, cover_sha256,
  lessons_range: "Bài 1–3", lessons_from, lessons_to, items}]}`. `quick.seed` (default: today's date) passed back to `/sessions` gives the
  same set; `quick.count` 0 + `reason` = nothing to practise yet. `mocks` = in-grade, servable bank profiles (empty for g1_5/g6_9:
  the bank is grade 10-12). `by_course` = enrolled courses with at least one studied lesson (`items` = quiz items in them); `lessons_*`
  count lessons 1-based in course order. Cover: `/api/courses/<id>/cover?v=<cover_sha256>`.
- **ClientItem** gains, for course items: `source {course_id, version, course_title, lesson_id, lesson_title, item_id}`, `topic_title` =
  lesson title, `stem_audio?`, `stem_image?` and media as `{path, mime, sha256, url}` (`url` = `/api/courses/<id>/versions/<v>/assets/<path>`,
  add `?t=<media token>`). `type` is also `PICTURE_CHOICE` (`options: [{id, text, image, audio?}]`; answer = option id) and `TAP_COUNT`
  (`tap: {image, total}`; answer = the count as digits, `"7"`); `TRUE_FALSE_GROUP` may have 3-4 statements (answer = one `T`/`F`/`-` per
  statement, `"TFT"`); `SHORT_ANSWER` has `short_answer {max_chars: 24, unit: null, decimals: null}`. Item id = `"<course_id>:<item_id>"`.
  `/answer` (`correct_answer`: option id, count, or the first accepted spelling), `/reveal`, `/review` are unchanged in shape.
- **Scoring** (`scoring.py`, same rules as `apps/app/src/lib/quiz.ts`): short answers match an accepted spelling as text or number
  (`0,5` = `0.5`, `4e5`, `4×10^5`), `tolerance` relative; groups of 4 keep the official shares, 3 statements score right/3.
- **Feedback loop**: on finish, one `LearningEvent` per answered item and skill is committed under the item's subject (the bank/curriculum
  subject when its skills belong to one, else a slug of the course subject: `vat-li`, `toan`; no author skill ids -> one skill
  `<course_id>.<lesson_id>`), BKT as for the bank. Planner: the answers appear as `quiz_answer {item: <quiz item id>, course_id}` (from
  `PracticeAnswer`, `planner/events.derived`; bank items stay `p:<id>`), so FSRS due dates and the lesson link work; nothing else of
  the planner changed.
- **Report** (practice only) gains `takeaway: {line_vi, line_en} | null` (one line, from the most-missed lesson/topic) and `redo:
  {line_vi, line_en} | null` ("Mentor sẽ cho em làm lại 2 câu sai vào thứ Năm, giờ em hay học."; only when something was wrong and the
  stored plan has a `review` item; the plan is never generated at answer time). `recommendations` is `[]` for quick/course sessions.
- **Not done**: `/progress` still lists bank subjects only (course skills are in `learning/<subject>/skills.md`); `/preview` has no
  `source` form (use `/home`); no drag-drop items; bank "previously wrong" items come back only through FSRS due.

## 11. Courses and content (P2-A, 2026-11-07; gateway serves under `/api`, the app consumes)

Schema: `mentor_schemas.course` (CoursePack, CourseMeta, Catalog). Store layout and rules are in its docstring. Root:
`<MENTOR_CONTENT_DIR>/courses` (default `<repo>/mentor-content/courses`). Dev samples `dev-sample-dien-truong` (g10_12, every block
type) and `dev-sample-dem-tao` (g1_5, TAP_COUNT, PICTURE_CHOICE, read-aloud) now live in `services/gateway/tests/fixtures/courses` (test fixtures only; P4 moved them out of `mentor-content/courses`, which holds the three published sample courses).
Errors: `{"error": code}` (`course_not_found`, `version_not_found`, `asset_not_found`, `not_enrolled` 404; `unknown_block`,
`unknown_lesson`, `unknown_quiz_item` 422). Drafts are never revealed to students (404, not 403). Teachers read everything; they
get 403 `role_mismatch` on enrollments (student only). Teacher authoring endpoints: section 14.

| Method | Path | Notes |
|---|---|---|
| GET | `/catalog` | `?age_band=&all=1`. `Catalog` for the student's age band (all bands for `all=1` and for teachers). `ETag` + `If-None-Match` -> 304 |
| GET | `/courses/{id}` | `CourseMeta` (students: published versions only) + `tree: [{id, title, lessons: [{id, title, est_minutes, summary, key_ideas}]}]` from the latest published version |
| GET | `/courses/{id}/cover` | image; ETag; `?v=<cover_sha256>` makes it `immutable` (1 year), otherwise 1 hour |
| GET | `/courses/{id}/versions/{v}/pack` | `pack.json`, ETag = `pack_sha256`, `immutable` for published versions; Bearer only |
| GET | `/courses/{id}/versions/{v}/assets/{path}` | the file, correct mime, `Range`/206, `immutable`; Bearer or `?t=` |
| POST | `/media-token` | `{token, expires_at}`; see below |
| POST | `/enrollments` | `{course_id}` -> 201 (new) / 200 (existing) enrollment; pins the latest published version; idempotent |
| GET | `/enrollments` | `[Enrollment]`, most recently updated first |
| PUT | `/enrollments/{course_id}/progress` | `{lesson_id?, block_id?, completed_block_ids?: [..], quiz?: {item_id, correct, seconds}}` -> Enrollment. Completed ids are **merged** (progress only grows, safe for offline replay); ids must exist in the pinned version |
| DELETE | `/enrollments/{course_id}` | 204 (404 `not_enrolled`) |
| GET | `/search` | `?q=&age_band=&all=1` -> `{query, mode: "hybrid"\|"lexical", results: [CatalogEntry + score + students], suggested_all_ages}` (used by Ask) |
| GET | `/catalog/query`, `/search/suggest` | the catalog screen: filters, facet counts, sort, paging, autocomplete (see "Catalog query" below) |

**Enrollment** = `{course_id, version (pinned), latest_version, update_available, enrolled_at, updated_at, last_lesson_id,
last_block_id, completed_block_ids, blocks_total, blocks_done, progress_pct (0-100, done/total blocks of the pinned version),
quiz: {item_id: {correct, seconds, attempts}}, course: {id, title, subject, age_band, language, teacher_name, description_short,
cover_sha256, lessons_count, est_minutes}}`. Publishing v2 never moves an enrolled student; only new enrollments get v2.

**Media auth.** `<video src>`, `<img src>`, `<audio src>` and `<track src>` cannot send `Authorization`. The app calls
`POST /api/media-token` (Bearer) and appends `?t=<token>` to cover and asset URLs. The token is an HMAC-signed
`user|expiry` (master-key subkey, `MEDIA_TOKEN_MINUTES`, default 240), accepted only on the cover and asset routes (never on pack,
catalog or enrollments) and still subject to the student's published-only rule. Refresh it when it expires (401 on media). Assets
are also `Content-Security-Policy: sandbox` so an SVG opened directly cannot run script. For offline caching, download assets with
the Bearer header via `fetch` (no token needed) and key the cache by `AssetRef.sha256`.

**Search.** Retrieval text = title + subject + description_short + outcomes + chapter and lesson titles + key ideas. Lexical score is
diacritic-insensitive (idf-weighted, title > subject > lessons > description/ideas, prefix match, phrase bonus). With a router
(`MODEL_ROUTER_URL`, `MODEL_ROUTER_KEY` or `MODEL_ROUTER_MASTER_KEY`) the alias `mentor-embed` is called at `/v1/embeddings`; vectors
are cached in `<MENTOR_DATA_DIR>/embeddings/<pack_sha256>-<text hash>.json`; score = 0.55 cosine (rescaled) + 0.45 lexical. On a
router failure the gateway falls back to lexical for 60 s (`mode: "lexical"`). `suggested_all_ages` is true when nothing matched in
the band but something matched in another.

**Coming-soon placeholders (2026-11-07).** `CourseMeta.status` is `"live"` (default) or `"coming_soon"`. A placeholder is an overview
only: title, subject, age band, language, teacher name, description, outcomes, `media`, and `outline: [{id, title, lessons: [{id, title,
est_minutes}]}]` in `course.json`, plus `cover.webp`. It has no versions and no `pack.json`. They live next to real courses as
`<courses>/ph-<slug>/` and are made, regenerated and removed in one command: `python mentor-content/tools/make_placeholders.py [remove]`
(overviews in `placeholder_courses.txt`, covers drawn by `placeholder_covers.py`, `--svg-dir` also writes the SVGs).
- `CatalogEntry.status` (`"live"` default). Live entries keep `version >= 1`, `pack_sha256`, `published_at`; a coming_soon entry has
  `version 0`, `pack_sha256 ""`, `pack_bytes 0`, `published_at null`, and its `lessons_count`/`est_minutes` come from the outline.
  `regenerate_catalog` lists live courses first, then placeholders. `GET /catalog` filters them by age band like any other entry.
- `GET /courses/{id}` works: `status: "coming_soon"`, `versions: []`, `tree` from the outline (`summary: null`, `key_ideas: []`). The cover
  route serves their cover.
- Refused with **409 `{"error": "coming_soon"}`**: `GET .../versions/{v}/pack`, `GET .../versions/{v}/assets/...`, `POST /enrollments`.
  `POST /practice/sessions` with `source: "course:<ph-id>"` answers 409 `{"code": "coming_soon"}`. They can never be enrolled, so they are
  never goals, progress rows or practice sources.
- `GET /search` includes them (`status` in each result). On equal score real courses come first. Embeddings are cached per course as usual
  and a cold cache is filled in batches of 32 texts (`EMBED_BATCH`), so ~110 courses cost 4 calls once, then none.
- Apps: show "Sắp có / Coming soon" instead of the Start button; do not offer them for Add or as goals. Ask course cards also carry them
  (`enrolled: false`), so a client must check the catalog `status` before offering "Thêm".

**Catalog query and autocomplete (hs-03, 2026-11-07).** The course screen (Shopee-style catalog) asks the gateway for one page at a time.
Any bearer user; `/search` is unchanged for Ask (same hybrid relevance, plus `students` in each result).

| Method | Path | Notes |
|---|---|---|
| GET | `/catalog/query` | `?q=&band=&subject=&language=&level=&duration=&media=&status=&teacher=&sort=rel\|new\|pop\|dur&dir=asc\|desc&page=1&page_size=10` -> page below. Every filter may repeat (`band=g10_12&band=uni`): OR inside one filter, AND across filters. `band` is **not** defaulted (the app sends the student's band). `page_size` 1-50 (app: 10); a `page` past the end returns the last page; bad `sort`/`dir`/`page` -> 422 |
| GET | `/search/suggest` | `?q=` -> `{courses: [{id, title}] (max 4), subjects: [str] (max 3), teachers: [str] (max 3), did_you_mean: str\|null}`; each name has to contain every word of `q` (accent-insensitive); `did_you_mean` only when nothing matched |

Filter values: `band` g1_5 g6_9 g10_12 uni; `subject` and `teacher` the exact text; `language` vi en; `level` basic intermediate advanced; `duration`
`short` (< 60 min) `medium` (60-180) `long` (> 180), from `est_minutes`; `media` video reading quiz interactive audio (the course `media` field);
`status` `live` `coming_soon`.

Response: `{query, mode: "hybrid"|"lexical", total, page, pages (>= 1), page_size, items: [CatalogEntry + {students, score}], facets:
{band|subject|language|level|duration|media|status|teacher: [{v, n}]}, did_you_mean: str|null}`.
- `students` = **active learners** of the course: enrolled students whose enrollment changed (enrolled, progressed, answered) in the last 30 days (`ACTIVE_LEARNER_DAYS` in `content/service.py`; 0 for placeholders). Students who stopped learning drop out of it after 30 days. `sort=pop` orders by it. `students` is not in `GET /catalog`
  (that one is an ETag-cached file). `CatalogEntry.level` (`"basic"|"intermediate"|"advanced"|null`, from `CourseMeta.level`) is in both.
- Facet counts are live: `facets[k]` counts the courses that match `q` and every filter **except** filter `k`, so ticking a value never hides
  its siblings. `band language level duration status media` always list every value (n may be 0); `subject` and `teacher` list values with
  n > 0 (plus ticked ones) by count, then name.
- Text match: a course matches when the hybrid/lexical search of section 11 finds it (title, subject, description, outcomes, lessons, ideas;
  embeddings when the router is up, `fast` mode: no embedding call when the lexical match is clear) **or** when every word of `q`
  is contained, accent-insensitively, in `title + subject + teacher_name + ("english" | "tieng viet")` (so half-typed words and teacher names work with
  no router). Order for `sort=rel`: search score plus a name bonus (title starts with the first word +0.5, title contains all words +0.3, subject/teacher
  only +0.15), then live before coming_soon, then catalog order. `sort=new`: live courses by `published_at` desc, then placeholders in catalog order.
  `sort=pop`: active `students` desc. `sort=dur`: `est_minutes` by `dir`. Ties always keep catalog order. With no `q`, `rel` is live first, then catalog order.
- `did_you_mean`: each word of `q` that is not the start of any word in titles, subjects or teacher names is replaced by the closest word (edit
  distance 1, or 2 for words over 4 letters; swapping two neighbouring letters counts as 1); null when nothing changes. A half-typed word is not a typo.
- Implementation: `content/catalog_query.py` (pure functions), `ContentService.query_catalog` and `.suggest`. The mock API
  (`apps/app/src/api/catalogEngine.ts`) implements the same rules over all 107 placeholders and the 3 live courses, without embeddings.

**Course level (difficulty).** `CourseMeta.level` and `CatalogEntry.level`: `"basic" | "intermediate" | "advanced" | null`. The teacher confirms it when
publishing (`VersionInfo.level_confirmed`, section 14); `publish` copies it to `CourseMeta.level`, `regenerate_catalog` to the catalog entry. The 3
published courses carry it in `course.json` only (Toán 1 basic, Vật lí 11 intermediate, Bayes advanced; their packs are untouched). Placeholders get it from
a `v:` line in `placeholder_courses.txt` (same values as the mockup's `courses.js`, 1 basic, 2 intermediate, 3 advanced). The app shows it as 1-3 bars plus the word
(cards, preview rows, course intro); nothing is shown when it is null.

**Catalog screen (app).** `/khoa-hoc/tim-kiem`. All state is in the URL: `q`, one param per filter (`subject=Toán&level=basic&level=advanced`), `sort`, `dir`
(only `sort=dur`), `page`, `view=list`. `band` absent = the student's own band (a removable chip, not counted in the filter badge), `band=all` = every
band. Cards link to `/khoa-hoc/<id>` with `state.from` = the catalog URL, so the back arrow on the course page restores query, filters, sort and page. A page
change scrolls the first card of the new page under the sticky search bar (focus on it, `prefers-reduced-motion` respected); a filter or sort change resets to
page 1. The pager is always shown. g1_5 learners get the simple version (big search with a mic, subject picture chips, 2-column tiles, no sidebar or sort bar).
Recent searches are kept in localStorage per user (`mentor.recentSearches.<user id>`, 6 max). `/khoa-hoc` ("Khóa học khác") shows 4 courses and "Xem tất cả".

**Store API for the course builder** (`mentor_gateway.content.ContentStore(root)`): `create_draft(meta, note=None) -> version`,
`write_pack(course_id, version, pack, assets: {path: bytes | Path})` (refuses published), `set_status(course_id, version,
"draft"|"review")`, `publish(course_id, version, note=None) -> VersionInfo` (verifies every asset's size and sha256 and the cover,
fills sha256/bytes/published_at, `lessons_count`, `est_minutes`, `media`, regenerates `catalog.json` atomically),
`load_meta`, `load_pack`, `list_courses`, `load_catalog`, helper `asset_ref_for(path, bytes | Path)`. Errors: `ContentError(code)`,
`NotFound`, `Immutable`. Table `enrollments` lives in ops.db (`content/tables.py`).

## 12. Planner, goals, reminders (P5-C backend, 2026-11-07; gateway serves under `/api`; students only, teachers get 403 `role_mismatch`)

Design: REQUIREMENTS-PLAN 3.6 and 3.7. Package `mentor_gateway/planner/`: behaviour events (`events.py`) -> study profile by code
(`profile.py`, `fsrs_items.py`, `goals.py`) -> LLM planner agent (`llm.py`, REASONING alias via `MODEL_ROUTER_URL`/`KEY`, skills in
`planner/skills/`, CC BY-SA 4.0, see `planner/skills/ATTRIBUTION.md`) -> hard validator (`validator.py`) -> rule-based fallback
(`fallback.py`, port of agent-mentor `Recommender.kt`). No router configured, model error, bad JSON or an unfixable plan = fallback
(`plan.source = "fallback"`, reason in `study_plans.note`). Tables (new): `behaviour_events`, `study_goals`, `study_plans`,
`study_reminders`. Dependency: `fsrs` (py-fsrs, MIT). All dates/times are local `Asia/Ho_Chi_Minh`; reminder `at` carries `+07:00`.

| Method | Path | Notes |
|---|---|---|
| POST | `/events` | `{events: [{id, kind, ts, data}]}` (<= 500) -> `{accepted, duplicates, rejected}`. Idempotent on `id`. Unknown `data` keys are dropped |
| GET | `/today` | hub lines + the "today" block, see below |
| GET | `/plan/week` | the plan with a one-sentence reason per item, from Monday of this week to today + 6 days, with a `done` flag per item |
| GET | `/reminders` | `?since=<iso>` (default: last 24 h). What the device schedules locally |
| POST | `/reminders/{id}/outcome` | `{outcome: "opened"\|"ignored"\|"snoozed"}` -> `{ok: true}`; 404 `reminder_not_found` |
| GET | `/goals` | `[Goal]` (inferred + student's) |
| POST | `/goals` | `{title, deadline?: "YYYY-MM-DD", course_ids?: [..]}` -> 201 `Goal` |
| PATCH | `/goals/{id}` | `{title?, deadline?, course_ids?}` (inferred goals: only `deadline`); 404 `goal_not_found` |
| DELETE | `/goals/{id}` | 204. Deleting an inferred goal hides it for good |

**Events** (`data` fields): `app_open {}`; `session_start {session}`; `session_end {session, seconds}`; `focus_tick {session, seconds}`
(active seconds since the previous tick, app visible and an input within 60 s; send about every 30-60 s while active);
`lesson_progress {course_id, lesson_id, pct}`; `video_watch {course_id, lesson_id, block_id, pct}`;
`quiz_answer {item, course_id, correct, seconds}` (`item` = the quiz item id; repeated items drive FSRS);
`reminder_outcome {reminder_id, outcome, at}` (the outcome endpoint writes this one itself);
`ask_question {intent: learn|solve|other, input: text|photo|voice}` (the app sends it once per new question in Hỏi đáp when the `intent`
event arrives; follow-up actions and the question text are never sent); `ask_course_open {course_id}` (a course card of an answer was
opened). Nothing of Hỏi đáp is derived from other tables, so these do not double count; the profile gets `ask_14d` from them. `ts` is the client time (ISO 8601,
more than 24 h in the future is rejected). Without any events the profile is derived from enrollment progress and practice answers.

**GET /today** -> `{date, now, hub: {courses, practice, ask, progress}, today, week: {done, planned}, due_review_count, quiet_until,
plan_source}`. Each `hub.*` is `{line_vi, line_en}` (the live line of that square). `today` is the next planned session (today, or a
later day when today is over) or null: `{title_vi, title_en ("Tối nay: 20 phút Điện trường"), date, start, is_today, minutes, kind,
course_id, lesson_id, reason_vi, reason_en, deep_link}`.

**GET /plan/week** -> `{generated_at, source: "llm"|"fallback", trigger, today, days: [dates], items, goals, note_vi, note_en, moves}`.
`days` runs from Monday of the current week to today + 6 (7 to 13 dates). Sessions of this week that already began stay in `items`
(kept in `study_plans.snapshot.past_items` when a replan drops them). `items[]`: `{date, start, minutes, kind: lesson|review|practice|break,
course_id, lesson_id, reason_vi, reason_en, weekday (0=Mon), weekday_vi, label ("Điện trường 20′"), title_vi, title_en, course_title,
deep_link, done}`; `done` = a study session began in the planned slot (30 min grace either side), always false for `break` and for
sessions still to come. `goals[]`: `{goal_id, status, line_vi, line_en}`.
`moves[]`: the last explained moves `{date, reason_vi, reason_en, trigger, at}`. `note_*`: the one sentence under the week.

**GET /reminders** -> `{now, quiet_until, break_after_minutes, reminders: [{id, at, kind: study|break|nudge, text_vi, text_en, deep_link,
status, outcome}]}`. The device schedules every `status: "scheduled"` reminder with `at` in the future, cancels the ones now
`cancelled` (a new plan replaced them) or `skipped_quiet`, and drops anything before `quiet_until`. `break_after_minutes` is the age-band
threshold for the local "take a break" reminder (device-side: after that many minutes of continuous focus). Report every reminder:
tapped -> `opened`; passed with no open within 30 minutes -> `ignored`; snoozed -> `snoozed`. Web users with a push subscription also get
the reminder from the gateway (hub, so quiet mode applies; no catch-up). That Web Push payload is the usual notification payload
(section 9: the reminder's real text as `body`, title "Mentor") plus `reminder_id` and `deep_link`, so the service worker opens the right screen on tap and the app reports the outcome
`opened` like for a device reminder (a bundled push of several notifications carries neither). `deep_link` is an app path: `/khoa-hoc/<course>?lesson=<lesson>`,
`/khoa-hoc/<course>`, `/luyen-tap`.

**Goal** = `{id, title, kind: "student"|"inferred", deadline, progress_pct, status: on_track|slightly_behind|behind|new, line_vi, line_en,
course_ids, courses: [{id, title, subject}], required_min_per_day, created_at}`. Inferred goals (`inf-<course_id>`, "Học xong <course>")
follow enrollments by themselves; a student goal links to courses by explicit `course_ids` or by words shared with a course title or
subject. Status compares the required pace (remaining lesson minutes / days to the deadline) with the real pace of the last 14 days
(>= 0.9 on track, >= 0.6 slightly behind); without a deadline it uses days since the linked course was last touched (7 / 14).

**When the plan is rebuilt** (scheduler tick, `planner.tick`): first plan; nightly (first tick after 03:00 local); Monday as a weekly review
pass; after a new or removed enrollment; a goal change; a missed planned session (30 min after its end, once); a practice accuracy change of
>= 0.2 over the last 20 answers. Event-driven replans are rate limited (20 min).

**Hard limits** (validator, every plan whatever made it): <= 2 reminders a day; none in the past, before `quiet_until`, in a slot where the
student already studied today, in a slot ignored 3 times, before 06:30 or from the age-band bedtime (g1_5 20:30, g6_9 21:30, g10_12 22:30, uni
23:30); one `nudge` at most, only after 2 idle days; session length g1_5 5-15, g6_9 and g10_12 15-30, uni 20-45 minutes; no session before 06:30
or from bedtime; no overlaps; <= 6 study days; weekly minutes <= max(1.5 x real weekly minutes, 3 default sessions).
Cold start (< 3 sessions): g1_5 18:00 x 10, g6_9 and g10_12 19:30 x 20, uni 20:00 x 30.

Research additions for the `uni` band (item and reminder kind `research`, `Goal.source` and `milestones`, `hub.research`, four server-recorded events, two replan triggers): section 15.8 and 15.9.

## 13. Q&A and guide (P5-B backend, 2026-11-07; gateway serves under `/api`)

Design: REQUIREMENTS-PLAN 3.5 (Hỏi đáp) and 3.9 (Mực). Package `mentor_gateway/ask/` (`service.py` flow, `llm.py` router client, `photo.py`
photo check, `prompts.py`, `guide.py`, `guide_map.json`). Models through router aliases only: `mentor-chat` (intent, short answers, guide),
`mentor-vision` (OCR, Gemini 3.5 Flash), `mentor-audio` (speech to text, Gemini 3.5 Flash), `mentor-reasoning` (solutions, similar items).
Streamed and retried 3 times (`RouterChatLLM`). No `MODEL_ROUTER_URL`: learn still works (lexical search + template sentence), solve/photo/audio
end with `error: model_unavailable`, `/guide` answers from the map by keyword. Table `ask_threads` (ops.db): per thread the last 8 turns, the
current problem, its solution (with the withheld last step) and the pending problem choices; rows older than 7 days are pruned. No other chat memory.

| Method | Path | Notes |
|---|---|---|
| POST | `/ask` | student only (teacher 403 `role_mismatch`, anonymous 401). Response `text/event-stream`. Body JSON or multipart (below). 404 `thread_not_found`, 404 `upload_not_found`, 413 `file_too_large`, 422 `empty_question` / `bad_upload_id` |
| POST | `/guide` | any signed-in user. `{question (<=300), lang?, screen?, visible_keys?: [..]}` -> `{answer}` (1-3 sentences, only about using the app) |

**Request fields** (JSON, or multipart/form-data with the same names): `text?`, `thread_id?` (from a previous `thread` event), `lang` (`vi`|`en`,
default the user's), `image_upload_id?` (the `path` returned by `POST /api/uploads`) **or** multipart `image` (jpeg/png/webp/heic, <= 15 MB), multipart
`audio` (<= 10 MB; wav and mp3 go straight to the model, webm/ogg/mp4/m4a are converted with ffmpeg when it is installed), `action?`
(`choose` + `problem_id` | `last_step` | `simpler` | `similar`). The same actions are recognised from text: "Xem bước cuối", "Giải thích dễ hơn",
"Làm 3 bài tương tự" (and English), and "Giải bài 4" after a choice.

**SSE**: `event: <name>` + `data: <json>`. Always starts with `thread` and ends with `done` (also after an `error`).

| event | data | when |
|---|---|---|
| `thread` | `{thread_id}` | first |
| `status` | `{stage: "listening"\|"reading"\|"solving"}` | progress lines ("Đang đọc đề...") |
| `transcript` | `{text}` | audio given |
| `intent` | `{intent: "learn"\|"solve"\|"other"}` | after routing (follow-up actions report `solve`) |
| `answer` | `{text}` | learn (one template sentence naming only courses that matched, sent **after** `courses`; a concept question ("X là gì") gets one model sentence first), other (one redirect sentence), free follow-up question |
| `courses` | `{items: [Card], suggested_all_ages, start_with: {course_id, lesson_id, title}\|null}` | learn. `Card` = `{course_id, title, cover_sha256, description_short, language, lessons_count, est_minutes, tree (as GET /courses/{id}), age_band, score, enrolled, first_lesson}`; <= 3 cards, best first, live courses first, then the student's band as a bonus (not a filter), then score; only courses that match are returned (hybrid score >= 0.2 and >= 0.55 of the best, `suggested_all_ages` when the top card is another band). `Card.status` is `live` or `coming_soon`: a placeholder has `first_lesson: null`, never leads `start_with`, and the app shows "Sắp có" instead of Thêm/Bắt đầu |
| `quality` | `{ok, reasons: [blurry\|too_dark\|low_contrast\|missing_area\|low_resolution\|skewed\|blank_page], metrics}` | photo |
| `message` | `{kind: "retake"\|"no_speech"\|"bad_image"\|"no_problem"\|"no_last_step"\|"empty", text, ...}` | `retake` also has `where`, `reasons`, `tips: [3 lines: light, steady, straight above the page]`, `offer_readable` |
| `choices` | `{problems: [{id, label, text}], reason: "multiple"\|"partial"}` | photo with >1 problem, or some parts unreadable (`partial`: after a `retake` message; the UI offers "Chỉ giải bài N"). Reply with `action: "choose", problem_id` |
| `problem` | `{id, label, text}` | the problem being solved |
| `solution` | `{problem_id, problem_md, steps: [{title, md}], last_step_withheld, tip}` | the **last step is not included** (a one-step solution is shown whole, `last_step_withheld: false`). `md` is KaTeX Markdown |
| `last_step` | `{problem_id, step: {title, md}}` | on `last_step`; no model call |
| `similar` | `{items: [{problem_md, answer_md}] (3)}` | on `similar` |
| `error` | `{code: "model_unavailable"\|"internal", message}` | |
| `done` | `{thread_id}` | last |

**Flows.** Intent is decided without a model when the text is clear (`route_text`: learn words such as "muốn học", "khóa", "ôn thi"; an equation or a solve verb with a number; greetings); anything else is searched first and, if a short message matches a course with score >= 0.5, is learn too; only the rest calls `mentor-chat` (`_classify`, with the search running beside it, and keyword rules when the router is down). learn: search (CONTRACTS 11 service, hybrid RAG; a clear lexical hit skips the embedding call, so cards arrive in ~0.1 s, else ~1.5-2.5 s with one embedding) -> `courses` first -> one short answer sentence. `settings.model_router_url` is normalised from `localhost` to `127.0.0.1` (on Windows `localhost` costs 2-3 s per connection). Photo OCR and solving pass `reasoning_effort: low`; a photo that is hopelessly blurry or dark (Laplacian variance < 8, p95 < 55) gets the `retake` message without a vision call.
solve with a photo: size/EXIF normalised, deterministic check (blur, dark, cut-off, resolution, skew; copied from course-builder `quality.py`, skipped if
numpy/opencv/pillow are missing), then ONE vision call returning `{problems, unreadable}` (full page OCR, strict JSON through the copied
`jsonparse`); unreadable parts get a `retake` message that names the part and gives the three tips; one readable problem is solved at once, more
than one (or partial) -> `choices`. A typed problem skips vision. Solution = one REASONING call (3-6 steps, last step withheld, one tip). other:
one friendly redirect sentence, no chit-chat. Text fields (`answer`, `tip`, messages) go through `planner.text.clean` (no emoji, dashes, `!`); step
`md` is never altered. Photos and audio are never stored (only the OCR'd problem text lives in the thread).
Dev live runs: direct mode (`FPT_API_BASE` + `FPT_API_KEY`, fixed `DIRECT_MODELS` in `ask/llm.py`), see `tests/test_gw_ask_live.py` (`MENTOR_LIVE_ASK=1`).
Questions about one paper (uni band) use `POST /api/research/papers/{id}/ask`, not `/ask` (section 15.5).
`guide_map.json` is generated from `GUIDES` in `apps/app/src/lib/guides.ts` by `pnpm run guides:export` (apps/app, also the `prebuild` step); `test_guide_map_json_matches_guides_ts` fails when it is stale.

## 14. Teacher authoring (P3-E, 2026-11-07; gateway serves under `/api/teacher`; role teacher only, students get 403 `role_mismatch`)

Each teacher sees only their own courses (someone else's: 403 `not_owner`; unknown: 404). Errors `{"error": code}`: `busy` 409 (the
course already has a job running, or a build is), `outline_not_ready` 409, `use_new_version` 409 (build on a published course),
`draft_exists` 409, `version_published` 409 (comments on a published version), `anchor_mismatch` 422, `unknown_block` 422/404,
`bad_outline_edit` 422, `no_files` 422. Media URLs accept `?t=<media token>` (section 11) like the student routes; `/events` too.

**Builder out of process.** Stages run as subprocesses `python -m mentor_course_builder.cli job <kind> --dir <MENTOR_DATA_DIR>/builder/<course_id>
--args a.json --result r.json` (`BUILDER_PYTHON` picks the interpreter, cwd = repo root so `.env.dev.local` is found). State is JSON under
that dir (`state.json` = chat + jobs + comments, `intake/pages.json|checks.json`, `outline.json`, `build/progress.json`,
`versions/<v>/media.json` + `media/` editable sources, `uploads/`, `jobs/*.log`). One job at a time per course, `BUILDER_WORKERS` (default 1)
stages overall; a gateway restart sets `running` jobs back to `queued` and the stage runs again (stages are idempotent), so the teacher can
close the app at any time. Kinds: `intake` (intake + merge + outline), `outline_chat`, `build`, `revise_text`, `revise_media`, `revise_all`.
Env: `BUILDER_WORKERS`, `BUILDER_PYTHON`, `BUILDER_JOB_TIMEOUT_S` (3600), `BUILDER_MEDIA_KINDS` (`tts,video,diagram,illustration,picture,cover`;
drop kinds to skip them), `BUILDER_DEEPTUTOR=1`, `BUILDER_CHAT_WAIT_S` (20). TTS order edge -> gemini is the media stage default.

**Verify-and-refine gate (build, then publish).** The `build` stage ends with `mentor_course_builder.refine`: every outline lesson present, a quiz in every lesson, pack validates, asset files exist with matching size and sha256, no empty or placeholder block, every formula parses in KaTeX (node + the `katex` package; regex fallback), quiz keys consistent and independently re-solved (items the pipeline already verified are not solved twice), no lesson repeating its neighbour, no duplicate question, humanize-linter tells. Each problem has an automatic repair (rewrite the lesson, regenerate quiz or item, re-ask the model with the KaTeX error, re-render media, second humanize pass), up to 3 rounds. What is left is `hard` (lesson/quiz missing, pack, asset, KaTeX, quiz key, wrong answer, empty block: **blocks publishing**) or `soft` (media left out, writing tells, repetition). The `build` result gains `issues: [{code, severity, lesson_id, block_id, detail, fixed, vi, en}]`, `blocked: bool`, `fixed: int`, `profile: {content_s, media_done_s, verify_s, total_s}`; `message_vi/en` lists the issues in plain words (shown as the chat `build` message). The report is stored as `versions/<v>/verify.json` (`{rounds, katex, blocked, hard, soft, fixed, checked_at}`). Build args add `refine_rounds` (3), `tts_workers` (6), `plan_media` (true: media per lesson chosen by content and age band, `mediaplan.py`). `ImageBlock.attribution` (optional `{provider, title, author, license, license_url, source_url}`) carries the credit of a picture taken from the web.

| Method | Path | Notes |
|---|---|---|
| GET | `/courses/{id}/versions/{v}/verify` | `{blocked, issues[]}`: the hard problems that would stop `publish` right now (live static checks plus the build's still-valid wrong-answer verdicts) |

| Method | Path | Notes |
|---|---|---|
| POST | `/uploads` | multipart `files[]` (+ `note`) -> `{course_id, job_id}`; new draft course + intake job (reads, checks pages, proposes the outline). The course id is a readable slug of the first file's name (else the note): ASCII, no diacritics, <= 32 chars, `-2`, `-3` on collision, `khoa-hoc` if nothing is left; existing ids never change |
| POST | `/courses/{id}/materials` | multipart `files[]`, repeated `replace` = `"<source_file>#<page>"` -> `{job_id}`. With `replace` the i-th photo takes that page's place (same ref, so lessons citing it keep working); without it the pages are added. The outline is rebuilt only if the teacher never edited it, otherwise new pages are folded in by `revise_outline` |
| GET | `/courses?since=<iso>` | `[{id, title, status, status_line_vi, status_line_en, cover_sha256?, updated_at, latest_version, versions: [{version, status: draft\|review\|published, students}], build?: {done, total}}]`; `status` = `reading\|needs_retake\|outline_ready\|building\|review\|published\|revising` (active job first: building / revising / reading; else unpublished version: `revising` if a published one exists, else `review`; else published; else retake pages; else outline). `since` filters by `updated_at` (polling fallback for SSE) |
| GET | `/courses/{id}` | `{course, status, status_line_*, outline (CourseOutline: chapters -> lessons {id, title, est_minutes, summary, key_ideas, source_pages, grounded}), retake: [{ref, source_file, page, reasons, message_vi, message_en, thumb_url}], build: {lessons: [{id, title, state: waiting\|writing\|media\|video\|done\|failed, note?}]}, verify: {rounds, blocked, hard[], soft[], fixed[]} or null (report of the latest unpublished version), chat: [{id, role: teacher\|agent, kind: text\|outline\|retake\|build\|notice, text, text_en, created_at}], updated_at, released_app_version}` (`released_app_version` = env `RELEASED_APP_VERSION`, default 0.1.0; review warns when the pack's `min_app_version` is above it). Pages that are not readable do not stop the course: the rest is used. `thumb_url` (`GET /courses/{id}/thumb?ref=`, Bearer or `?t=`) is an `<img>` source |
| POST | `/courses/{id}/chat` | `{text}` -> list of the new messages (the teacher's, an acknowledgement, and the agent's answer if it finished within `BUILDER_CHAT_WAIT_S`; else it arrives later through `GET`/SSE). Before a build: `revise_outline` ("gộp bài 2 và 3"). After a build: a course-wide instruction applied to every text block of the draft ("ngắn hơn"; a new draft version is started if only published versions exist). The agent never asks back |
| PUT | `/courses/{id}/outline` | `{ops: [...]}` structured edits (`rename` (a lesson, a chapter, or the course itself with `id` = the course id), `update`, `reorder`, `delete`, `add_lesson`, `add_chapter`, `move_lesson`, `merge`; see `apply_outline_edits`) -> the outline. Ids of surviving lessons never change. Pure data, applied in the gateway process; 409 `busy` while a job runs |
| POST | `/courses/{id}/build` | -> `{job_id}`: content + media (video, diagrams, illustrations, read-aloud) for the current outline, per-lesson states in `GET`, the cover (`kind cover`; a plain gradient if generation fails), ending in a draft version with status `review`. Re-running replaces the unpublished draft |
| GET | `/courses/{id}/versions/{v}/pack` , `/assets/{path}` | the owner's drafts and published versions (no-store for drafts); same bodies as section 11 |
| POST | `/courses/{id}/versions/{v}/comments` | `{block_id, anchor, body}` -> `{id, status: "open", ...}`. `anchor` = `{kind:"text", start?, end?, quote}` (text, callout or quiz block; the builder rewrites only that block, ids kept, humanized, quiz answers re-solved, read-aloud audio re-made) / `{kind:"time", t}` (video block: `MediaRequest.revise {comment, source_dir, at_s}`) / `{kind:"point", x, y}` (0-1; image block: `revise {comment, source_dir, x, y}`). Wrong anchor for the block: 422 `anchor_mismatch`. Status `open -> applying -> applied`, or `failed` with `note` |
| GET | `/courses/{id}/versions/{v}/comments` | `[{id, block_id, anchor, body, status, note, version, stale, created_at, updated_at}]`. Rebuilding the open draft rewrites it in place, so its earlier comments become `stale: true`: hidden by default, `?stale=true` lists only those (nothing is deleted; other versions keep theirs) |
| PUT | `/courses/{id}/versions/{v}/level` | `{level: "basic"\|"intermediate"\|"advanced"}` (else 422) -> `{version, new_version, level, level_suggested, level_confirmed}`. The teacher confirms the course level of a draft (stored as `VersionInfo.level_confirmed`). On a published version a *different* level takes the new-version path: it is stored in the open draft (created from the published one when there is none, `new_version: true`) and students see it when that version is published; the same level is a no-op. Another teacher's course 403/404, unknown version 404 |
| POST | `/courses/{id}/versions/{v}/publish` | refuses with 409 `{error: "level_unconfirmed"}` until the version has a confirmed level (the agent only suggests one); then runs the verify gate: hard problems -> 409 `{error: "verify_failed", issues: [...]}` and nothing is published; else `ContentStore.publish` -> `{version: VersionInfo, course}` |
| POST | `/courses/{id}/versions` | 201 `{version, status: "draft", course}`: draft v+1 copied (pack, assets, editable media sources) from the latest published; comments and chat then apply to it; enrolled students keep their pinned version (`update_available` shows for them) |
| GET | `/events` | SSE (Bearer or `?t=`): `event: course` `data: {type, course_id, status, status_line_vi, status_line_en, title, updated_at, build?}` on every change, `id:` per event (`Last-Event-ID` replays a short in-memory buffer), `: keepalive` every 15 s |

**Course level (2026-11-07).** `Level = "basic"|"intermediate"|"advanced"`. The outline model returns `level` in the same call (no extra
model call); `outline.suggest_level` clamps it to the age band (g1_5 never advanced, g6_9 at most intermediate, uni never basic) or, without
a valid answer, derives it from the band and the material. It travels as `CourseOutline.level_suggested` -> `VersionInfo.level_suggested`
(store `set_level`; never overwrites a confirmed one). `VersionInfo.level_confirmed` is the teacher's choice; a new draft of a published
course starts with the published level. `ContentStore.publish` copies it to `CourseMeta.level`, and `catalog.json` entries carry `level`
(null until a course has one). Teacher reads: `GET /courses` rows and `GET /courses/{id}` `course` add `level` (what students see, latest
published), `level_suggested` and `level_confirmed` (of the working version: the open draft, else the latest published); every `versions[]`
item adds `level_suggested`, `level_confirmed`.

When a job finishes the teacher also gets a notification (`notifications.py`, kind `nudge`, source `builder`): material read (retake count), build
done, comment applied, failures. Store courses seeded without builder state are listed for their owner (`teacher_id` = user id or username) and can
get a new version and text comments; media comments need the builder's `versions/<v>/media.json` and fail with a note otherwise.

## 15. Nghiên cứu / Research (P5N, contract 2026-11-07; gateway serves under `/api/research`; students of the `uni` band only)

Design: REQUIREMENTS-PLAN 3.11, mockups `hs-11-nghien-cuu`, `hs-12-doc-paper`, `shared.js` (`mockSources`), hub `hs-02`. Shapes:
`packages/mentor-schemas/src/mentor_schemas/research.py` (import `mentor_schemas.research`; not re-exported from `__init__`, like `course.py`) and
`apps/app/src/api/research-types.ts`; names are identical in both and here. Library: `mentor_gateway/research/papers.py` (`search_arxiv`,
`discover_frontier`, `literature_pass`; `Paper` -> `PaperCard`, `SearchRun` reused as is, `MatrixRow` replaced by `ReviewRow`) plus the S2 and Asta clients restored
from git HEAD (`papers.py`, `asta.py`).

**Auth, all endpoints.** Bearer token. Anonymous 401 `unauthorized`; teacher 403 `role_mismatch`; a student whose derived `age_band` (section 5) is not `uni`
403 `not_university` (checked on every request, so a band change takes effect at once). Errors are `{"error": "<code>"}` (the `ResearchErrorCode` type); 422 bodies
from request validation are FastAPI's `{detail}`. Dates `YYYY-MM-DD`, times `HH:MM` Vietnam time, instants ISO 8601 with `+07:00`. Text Mentor writes for the learner
(`reason`, feedback rows, answers) is one string in the user's language when written and goes through `planner.text.clean`; lines built by code carry `_vi` and `_en`.
Model calls (profile derivation, discovery reasons, review matrix, feedback, answers, experiment and meeting structuring, deadline parsing) go through the router
(`mentor-chat`, `mentor-reasoning`, `mentor-vision` for photos); search result cards use **no** model. Only keywords and paper ids leave to S2, Asta and arXiv.
Per-user rate limits: search 30/min, key validation 5/min, review 10/hour, discovery 1 per 6 hours; over the limit 429 `rate_limited` (`retry_after` seconds).

### 15.1 Endpoints

| Method | Path | Request -> response; errors; systems touched |
|---|---|---|
| GET | `/research` | -> `ResearchOverview`: profile, `status_line`, `hero`, `upcoming`, `reading_list`, featured `suggestions`, thesis `milestones`, `goal_id`, last 5 `experiments`, `discovery`. One call paints hs-11. Reads planner goals and plan items |
| GET | `/research/profile` | -> `ResearchProfile` (`title: ""` when nothing is set; `asta_connected`, `s2_connected`; keys are never returned) |
| PUT | `/research/profile` | `ResearchProfileInput` (present fields change; `keywords` replaces the list, 1-8 items) -> `ResearchProfile`. `title` alone: Mentor derives `question` and 3-5 English `keywords` (one `mentor-chat` call; no model: keywords from the title words) and queues a discovery job. 422 `empty_title`, `bad_keywords` |
| GET | `/research/source-keys` | -> `SourceKeysStatus` (settings row "Nguồn tìm paper") |
| PUT | `/research/source-keys/{asta\|s2}` | `{key}` -> 200 `SourceKeysStatus`. One cheap call to that source validates first (S2: a one-result search; Asta: `search_papers_by_relevance`, limit 1); wrong or expired 422 `invalid_key` (UI: "Key không đúng hoặc đã hết hạn"), source down 503 `source_unreachable` (nothing saved). Replaces an existing key. Stored encrypted (`crypto.py`/`datakeys.py`), never logged or returned. 404 `unknown_source`; 429 |
| DELETE | `/research/source-keys/{asta\|s2}` | -> 200 `SourceKeysStatus`; erases the key (idempotent). 404 `unknown_source` |
| GET | `/research/search` | `?q=` (<= 300) `&year_min=<year>` (inclusive; the UI sends none, this year - 4, or this year) `&pdf=true` `&page=1` `&depth=quick\|thorough\|deep` (quick = arXiv, thorough = + S2, deep = + Asta; none = every source with a key; a source with a key left out by `depth` is `skipped`) -> `SearchResponse`. 422 `empty_query`; 429 |
| GET | `/research/papers/{id}/related` | -> `RelatedPapers`. 404 `paper_not_found`; 429 |
| POST | `/research/review` | `ReviewRequest` -> 202 `JobStarted`. Poll `GET /research/jobs/{job_id}`. 409 `job_running` (+ `job_id`) when one is running; 429 |
| GET | `/research/jobs/{job_id}` | -> `ResearchJob` (own jobs only; kept 1 hour). 404 `job_not_found` |
| POST | `/research/discovery` | -> 202 `JobStarted` (manual run; the Monday run is automatic). 409 `job_running`; 422 `empty_title` (no topic yet); 429 |
| GET | `/research/suggestions` | -> `SuggestionList` (pending, <= 10, featured first) |
| POST | `/research/suggestions/{id}/accept` | -> 201 `ReadingEntry` (`origin: "suggestion"`). 404 `suggestion_not_found`; 409 `reading_list_full` |
| POST | `/research/suggestions/{id}/dismiss` | -> 204; never suggested again. 404 `suggestion_not_found` |
| GET | `/research/reading-list` | -> `ReadingList` |
| POST | `/research/reading-list` | `AddPaperRequest` (`card` from search or related, or `link` URL/DOI, or `upload_path` of a PDF from `POST /uploads`) -> 201 `ReadingEntry`; 200 with the existing entry when already in the list. 409 `reading_list_full`; 422 `bad_paper_ref`; 422 `paper_unresolved` (nothing resolves the link or DOI); 404 `upload_not_found`. When the profile has no `title`, the first paper added derives the profile like `PUT /research/profile` |
| DELETE | `/research/reading-list/{id}` | -> 204. Takes the paper off the list; the paper, summary and notes are kept (re-adding restores them). 404 `paper_not_found` |
| PUT | `/research/papers/{id}/status` | `StatusInput` -> `ReadingEntry`. `read` frees a slot ("Đã đọc"); any status can be set back. 404 `paper_not_found`; 409 `reading_list_full` when moving `read` -> active with 5 active |
| GET | `/research/papers/{id}` | -> `PaperDetail`; the first open of a day sets `new` -> `reading`. 404 `paper_not_found` |
| PUT | `/research/papers/{id}/summary` | `SummaryInput` (>= 20 chars) -> `PaperNote`; a changed summary drops the old feedback. 404 `paper_not_found` |
| POST | `/research/papers/{id}/feedback` | no body -> `PaperFeedback` (stored in the note; returned as stored when the summary is unchanged). 409 `summary_required` (Mentor never reviews before the learner writes); 503 `model_unavailable`; 404 |
| POST | `/research/papers/{id}/ask` | `AskInput` (JSON; multipart `audio` as in section 13 also works, `mentor-audio`) -> `text/event-stream`, see 15.5. 404 `paper_not_found` |
| GET | `/research/papers/{id}/qa` | -> `[PaperQA]` oldest first (the thread). 404 |
| GET | `/research/experiments` | `?limit=20 (<= 50)&before=<next_before>` -> `ExperimentList` |
| POST | `/research/experiments` | `ExperimentInput` -> 201 `Experiment` (structured in one call, 3-8 s). 404 `upload_not_found`; never 503: without a model the entry is stored with `structured: false` |
| GET | `/research/experiments/{id}` | -> `Experiment`. 404 `experiment_not_found` |
| PATCH | `/research/experiments/{id}` | `ExperimentPatch` -> `Experiment` (setting `commit` or `seed` clears it from `missing`). 404 |
| GET | `/research/meetings` | `?status=scheduled\|done\|all` (default `scheduled`, soonest first; the others newest first) -> `[Meeting]` |
| GET | `/research/meetings/next` | -> `Meeting` or `null` (200) |
| POST | `/research/meetings` | `MeetingInput` -> 201 `Meeting`. 422 `meeting_unparsed` (text with no date) |
| PATCH | `/research/meetings/{id}` | `MeetingPatch` -> `Meeting` (a moved time moves the agenda draft). 404 `meeting_not_found` |
| DELETE | `/research/meetings/{id}` | -> 204. 404 |
| PUT | `/research/meetings/{id}/agenda` | `AgendaInput` -> `Meeting` (the learner's two boxes). 404 |
| POST | `/research/meetings/{id}/agenda/draft` | no body -> `Meeting` with a (re)drafted `agenda.promised`; keeps the learner's boxes. 503 `model_unavailable` |
| PUT | `/research/meetings/{id}/notes` | `NotesInput` -> `Meeting`: sets `status: "done"`, splits the notes into `action_items`; items with a `due_date` become planner items (15.8). 404 |
| PATCH | `/research/meetings/{id}/actions/{aid}` | `ActionItemPatch` -> `Meeting`. 404 `action_not_found` |
| GET | `/research/deadlines` | `?include_done=false` -> `[Milestone]` by date |
| POST | `/research/deadlines` | `MilestoneInput` -> 201 `Milestone`. 422 `deadline_unparsed` |
| PATCH | `/research/deadlines/{id}` | `MilestonePatch` -> `Milestone`. 404 `deadline_not_found` |
| DELETE | `/research/deadlines/{id}` | -> 204. 404 `deadline_not_found` |

### 15.2 Search (hs-11)

`results` order: Asta results, then S2 results not seen yet, then arXiv results not seen yet; inside each source its own relevance order. Dedupe by `arxiv:<id>`
(version stripped), else `doi:<doi>` (lower case), else `s2:<paperId>`; the **earlier source's card wins**, and `source` is the source of the card shown. A source with no key
is `not_connected` and not called; a bad or expired key, a rate limit or an outage is `failed` and skipped for that search (never an error response; arXiv failing too gives empty `results`).
`sources` always lists all three, so the line "Kết quả từ arXiv" or "Asta, Semantic Scholar, arXiv" is built from the `ok` ones. Filters apply server side: `year_min`, `pdf=true`
(arXiv always has a PDF; S2 uses `openAccessPdf`; `has_pdf: false` shows "Chỉ có abstract"). `page_size` is 10; `has_more` is true when any source had more.
Fields by source: arXiv gives `excerpt` (first sentences of the abstract, <= 240 chars), `authors` (<= 5), `year`, `url`, `arxiv_id`, `has_pdf: true`, **no** `citation_count`, **no** `tldr`.
S2 adds `citation_count`, `tldr` (English, when the paper has one), `venue`, `doi`, `s2_id`. Asta adds `snippet` (from `snippet_search` for the same query, when it found one for that paper) and
`citation_count`. `in_reading_list` and `paper_id` are filled for stored papers. Mentor summarises and translates nothing here. Example (arXiv-only card):

```json
{"key": "arxiv:2603.01234", "source": "arxiv", "title": "Learning Formation Energies from Fewer Than Five Thousand Crystal Structures",
 "authors": ["Haddad", "Nguyen"], "year": 2026, "venue": null, "arxiv_id": "2603.01234", "doi": null, "s2_id": null,
 "url": "https://arxiv.org/abs/2603.01234", "excerpt": "Formation energy models usually need tens of thousands of labelled structures.",
 "tldr": null, "snippet": null, "citation_count": null, "has_pdf": true, "in_reading_list": false, "paper_id": null}
```

### 15.3 Related papers (hs-12)

`GET /research/papers/{id}/related` for a stored paper. With S2 connected: `citing` from S2 `citations`, `cited` from S2 `references`; with Asta connected: Asta `get_citations` adds to `citing`.
Merged and deduped like search, <= 20 items each, `count` = the source's total ("Trích dẫn bài này (14)", "Bài này trích dẫn (38)"), `sources` = the ones used. With no key at all:
`{"available": false, "reason": "no_source_key", "sources": [], "partial": false, "citing": {"count": 0, "items": []}, "cited": {"count": 0, "items": []}}` (UI: a small line plus "+ Semantic Scholar").
A connected source failing gives 200 with `partial: true`. Cached 24 h per (user, paper).

### 15.4 Quick review and weekly discovery (async jobs)

One shared job shape, polled: `POST` returns 202 `JobStarted`, the app polls `GET /research/jobs/{job_id}` every 1.5 s (SSE is used only for paper answers, 15.5).
`ResearchJob.status` runs `queued` -> `running` -> `done` or `failed`. An in-memory or ops row with a 1-hour TTL (a review table is not stored for the learner; a discovery result is its suggestions). `progress`, `result` and `error` are always present and null when they do not apply: `result` is non-null only when `done`, `error` only when `failed`.

**Review** (`kind: "review"`): `literature_pass(query, followups)` (arXiv, <= 3 follow-up queries given by the app or chosen by Mentor, <= 8 papers), then one `mentor-chat` call turns each
abstract into `ReviewRow {key, problem, method, data, result}`; a cell the abstract does not state is `null` (UI: "Abstract không nêu"), never inferred. `progress`: `{stage: "searching"|"reading", total, done}`
(UI: "Mentor đang đọc abstract của 8 bài..."). `result: ReviewResult` = `papers` (<= 8 `PaperCard`, `source: "arxiv"`), `matrix` (one row per paper, same `key`), `followups` (<= 3 queries, the "Tìm tiếp" chips),
`searches`, `coverage`, and the fixed caveat `caveat_vi`/`caveat_en`, always present. `error`: `model_unavailable` (no matrix; the app shows the papers only), `search_failed`, `internal`.
The rows are the papers `literature_pass` found for `query`; they usually but not always equal the cards on screen, so the app matches rows to cards by `key`.

**Discovery** (`kind: "discovery"`): `discover_frontier(topic, keywords)` (<= 3 arXiv queries, last 3 years, read-only) -> drop papers already in the list, dismissed or suggested before ->
keep <= 10 new -> one `mentor-chat` call writes a one-line `reason` per paper from the profile and the papers the learner read (fallback template "Khớp từ khóa <keyword>"); the first 5 are `featured`.
Only arXiv results, nothing invented. `result: DiscoveryResult`. Runs automatically on Monday 06:00 local (scheduler job kind `literature_watch`, only for `uni` users with a `title`),
right after the first `PUT /research/profile` with a title, and on `POST /research/discovery`. A suggestion joins the learner's papers only on `accept`, which needs a free slot
(409 `reading_list_full`; the UI says to mark one read or remove one). With no model and no usable English keywords (the title words of a non-English title do not count; keywords the learner typed always do) the run is skipped: `discovery.last_status` = `waiting_model`, and it runs again when a model is back (scheduler tick) or the learner edits the keywords. `week_of` = Monday of the run; a new run replaces the older pending suggestions.

### 15.5 Reading list, paper reader and Q&A

**Reading list.** Active = `status` `new` or `reading`, at most 5 (`READING_LIST_LIMIT`); `read` entries stay listed for 14 days. `new` = never opened; the app shows "Mới" when `new_this_week`, else "Chưa đọc".
Every entry has a `reason` (from the suggestion, or Mentor's one line when the learner adds by link or card; `AddPaperRequest.reason` overrides). Home shows `reading_list.items`, then `suggestions` (featured, pending) after them until 5 rows.

**Reader order is fixed:** the learner writes `my_summary` (>= 20 chars), then `POST .../feedback`. Feedback = `rows` (`right`, `inaccurate`, `missing`; any number of each, usually one) and `for_thesis` ("Với luận văn của bạn: ...", null when
there is no profile). Mentor says what the abstract and text support and what the learner has not covered; it does not rewrite the summary. Example row: `{"kind": "inaccurate", "text": "Bạn viết hơn 18%. Bài đạt 18% trên toàn bộ dữ liệu, còn với 3.000 cấu trúc chỉ là 7%. Bạn muốn nói trường hợp nào?"}`.
`PaperDetail.thesis_tag` ("Mục 3 của bạn") is set when the profile notes tie the paper to a section. `fulltext` is `ready` once the PDF text is indexed (an uploaded PDF, or the arXiv PDF fetched in the background into the learner's own KB), `indexing`, else `none`.

**Ask about a paper** (not `/ask`: it has its own thread in `paper_qa` and sends no `ask_question` event). Retrieval: `fulltext: ready` -> the paper's KB passages; else, only with an Asta key, Asta `snippet_search` for this paper;
else there is no text to read. SSE `event: <name>` + `data: <json>`, always ends with `done`:

| event | data |
|---|---|
| `status` | `{stage: "searching"\|"reading"}` |
| `qa` | `PaperQA` (one per question). The answer is short and every claim is backed by `citations: [{section, snippet, url}]`. Nothing found: `found: false` and `not_found_reason: "no_passage"` (an honest "Mình không tìm thấy đoạn nào nói về điều này...") or `"no_fulltext"` (no PDF text and no Asta key). `course_hint` when the paper leans on a course the learner has (section 11 search) |
| `error` | `{code: "model_unavailable"\|"internal", message}` |
| `done` | `{qa_id: string \| null}` |

### 15.6 Experiment log

`POST /research/experiments` takes the learner's free text and an optional `photo_path` (a table photo is read with `mentor-vision` into `result`). Mentor makes one `Experiment`:
`id` `EXP-<local date>-<a..z>` (`aa` after 26 in a day), `title`, `status` (`running`, `done`, `failed`, `cancelled`; failed runs are logged like any other), `aim`, `setup`, `result` (the learner's numbers restated), `user_note` (the learner's own comment), `next`.
**Mentor does not interpret results**: no "good", "worse", causes or advice in any field. `commit` and `seed` are taken from the text when present; the ones not found are listed in `missing` (UI: "Chưa ghi commit. Thêm vào để sau này chạy lại được."),
a nudge shown on the entry only, never a push. `raw_text` is always kept. Without a model: `structured: false`, `title` = first 60 chars, `status: "done"`, other fields empty. Records the event `experiment_logged`.

### 15.7 Meetings

`Meeting.at` is the time; the learner says it once (`text` or `at`). Two days before `at` (first scheduler tick after `at - 48 h`) Mentor drafts `agenda.promised` from the last meeting's open `action_items`, experiments logged since,
milestones and papers read (`AgendaItem {text, done}`); the learner fills `new_results` and `open_questions` (`PUT .../agenda`). `agenda` is `null` until drafted. The draft also triggers a `research` reminder (15.8). After the meeting `PUT .../notes`
with a few lines: Mentor splits `action_items`; an item with a `due_date` (given in the notes, or "trước thứ Sáu") becomes a planner item (`kind: "research"`, `in_plan: true`) placed before the date within the section 12 limits; items without a date stay as items and feed the next agenda.

### 15.8 Deadlines, milestones, planner, reminders, goals

No new tables: dates reuse section 12.
- **Milestone** (`Milestone`) = an external deadline or a thesis milestone, kept in `study_goals.milestones` (JSON) of the learner's one research goal (`id: "res-thesis"`, `kind: "student"`). `thesis: true` ones are listed in "Mốc luận văn" and counted in the goal.
- **Goal.** `Goal` (section 12) gets `source: "learning" | "research"` (default `learning`) and `milestones: Milestone[]` (`[]` unless research). The research goal appears in `GET /goals` and in Tiến độ like any goal: `title` = profile title, `deadline` = last thesis milestone, `progress_pct` = done thesis milestones / all, `status` by the section 12 rules from the milestone dates, `course_ids: []`. Created with the first `thesis` milestone, removed with the last. `ResearchOverview.goal_id` links to it ("Xem trong Tiến độ"); the research screen does not redraw it.
- **Parsing** (`text`): Mentor (skill `deadline-watch` rules) reads title, date and time; a time given in AoE (UTC-12) or another zone is converted to Vietnam time and kept in `original_text` ("23:59 AoE 15/11" -> `due_date 2026-11-16`, `due_time 18:59`); no time or an unclear date gives `confirmed: false` ("Chưa xác nhận", no time-based reminder). Example in 15.9.
- **Planner.** The planner profile gets a `research` block: open deadlines, the next meeting, open action items, and a default reading block of 3 sessions x 30 min a week (inside uni 20-45 min) at the usual study hours. `PlanItem.kind` gains `research` (`course_id`, `lesson_id` null; `deep_link` `/nghien-cuu/...`; `reason_vi/_en` as usual); deadline prep, reading blocks and action items use it. New replan triggers: `research_deadline_changed`, `research_meeting_notes`. Two deadlines within 3 days: the plan gives one earlier-heads-up reason.
- **Reminders.** `Reminder.kind` gains `research` (a confirmed deadline at 7 days and 48 hours before, agenda ready, meeting day). They count in the <= 2 a day limit and respect quiet mode, `quiet_until` and bedtime; a deadline within 48 h always gets one if the limit allows. `deep_link` is an app path (`/nghien-cuu`, `/nghien-cuu/paper/<id>`).
- **Hub.** `GET /today` `hub` gets `research: LiveLine`, **present only for `uni` users** (omitted, not null, for others). `ResearchOverview.status_line` is the same value. Built by code: part 1 the nearest open confirmed deadline within 30 days: kind `submission` "Hạn nộp bài còn N ngày" / "Paper due in N days", else "Hạn gần nhất còn N ngày" / "Next deadline in N days" (N = 0 "hôm nay", 1 "ngày mai"); part 2 K = featured pending suggestions + `new` entries added in the last 7 days: "K paper mới" / "K new papers"; parts joined with ", "; neither: "Chưa có gì mới" / "Nothing new"; no topic yet: "Đặt đề tài của bạn" / "Set your topic".
- **"Đọc tiếp" hero** (`ResearchOverview.hero`): the `reading` entry opened last, else the oldest `new` entry whose reason mentions a deadline, else the newest `new` entry; null with no active entries. `reason` = the entry's `reason`; when a confirmed deadline is within 14 days, one `mentor-chat` sentence ties them ("Bài full paper của bạn còn 9 ngày nữa đến hạn, và mục 3 của bài so sánh với paper này."), cached per day, with the entry `reason` on model failure.

### 15.9 Behaviour events (section 12 `behaviour_events`)

The research endpoints record these themselves with `planner.events.record` (client id `res-<kind>-<id>-<local date>`, so repeats on the same day are one event); the app does not send them, and `POST /events` still rejects them.
Add to `FIELDS` in `planner/events.py`:

| kind | data | recorded when |
|---|---|---|
| `paper_opened` | `{paper_id}` | `GET /research/papers/{id}` |
| `paper_read` | `{paper_id}` | status set to `read` |
| `summary_written` | `{paper_id, chars}` | `PUT .../summary` |
| `experiment_logged` | `{experiment_id, status}` | `POST /research/experiments` |

They count as study activity in the profile (a research session = from `paper_opened` to the last `focus_tick` of that day) and stop the "idle 2 days" nudge. `ReadingEntry.minutes_spent` sums the `focus_tick` seconds of those sessions.
Deadline example: `POST /research/deadlines {"text": "nộp full paper 15/11, 23:59 AoE"}` -> `{"id": "ms-1", "title": "Nộp full paper hội nghị", "due_date": "2026-11-16", "due_time": "18:59", "original_text": "23:59 AoE 15/11", "confirmed": true, "kind": "submission", "thesis": true, "done": false, "days_left": 9, "planned_sessions": 2, "created_at": "2026-11-07T09:00:00+07:00"}`.

### 15.10 Data model

Implementation notes (2026-11-07, clarifications only): `ReadingEntry.id` is the paper id and is the `{id}` of every `/research/papers/{id}` and `/research/reading-list/{id}` path. `Goal.milestones` lists the thesis milestones only (all milestones, including external deadlines, are in `GET /research/deadlines`); the goal row is created with the first milestone but shown in `/goals` only while a thesis milestone exists, and its row id is `res-thesis:<user_id>` (the API id stays `res-thesis`). `kind` defaults to `submission` when the text says submit/nộp, and `thesis` defaults to `kind == "submission"`. A discovery run keeps at most 10 papers before the learner's own filters (the vendored library caps it), so a run can add fewer than 10 new suggestions. Research reminders carry `?ref=<tag>` in `deep_link` so a replan does not repeat one that already fired.

SQLite ops DB (next to `ask_threads`; Postgres later without an API change), every row scoped by `user_id`. New tables:

| Table | Columns (main) |
|---|---|
| `research_profile` | `user_id` PK, `title`, `question`, `keywords` JSON, `advisor_name`, `asta_key_enc`, `s2_key_enc` (encrypted, write-only), `discovery_last_run_at`, `discovery_last_status`, `updated_at` |
| `paper` | `id`, `user_id`, `key` (unique per user), `arxiv_id`, `doi`, `s2_id`, `title`, `authors` JSON, `year`, `venue`, `url`, `pdf_url`, `abstract`, `tldr`, `citation_count`, `has_pdf`, `upload_path`, `fulltext_state`, `source`, `created_at` |
| `reading_entry` | `paper_id` PK, `user_id`, `status`, `reason`, `origin`, `added_at`, `opened_at`, `read_at`, `minutes_spent`, `removed_at` |
| `paper_note` | `paper_id` PK, `user_summary`, `summary_updated_at`, `feedback` JSON, `thesis_tag` |
| `paper_qa` | `id`, `paper_id`, `user_id`, `question`, `answer`, `found`, `not_found_reason`, `citations` JSON, `course_hint` JSON, `created_at` |
| `experiment` | `id` (`EXP-...`) PK, `user_id`, `date`, `title`, `status`, `aim`, `setup`, `result`, `user_note`, `next`, `commit`, `seed`, `photo_path`, `raw_text`, `structured`, `created_at`, `updated_at` |
| `meeting` | `id`, `user_id`, `at`, `title`, `status`, `agenda` JSON, `notes_md`, `action_items` JSON, `created_at` |
| `suggestion` | `id`, `user_id`, `paper_id`, `week_of`, `reason`, `query`, `featured`, `status`, `created_at`, `decided_at` |

Reused: `users` (band, language), `study_goals` (+ `source` and `milestones` JSON columns), study plans and items (+ kind `research`), `study_reminders` (+ kind `research`), `behaviour_events` (+ 4 kinds), `jobs` and `scheduler`
(job kind `literature_watch`, agenda drafts), `uploads` and `inbox` (PDFs and photos), `crypto.py` and `datakeys.py` (keys), the Hỏi đáp router client (`ask/llm.py`), course search (section 11) for `course_hint`. Not stored: review
results, related lists (24 h cache), search results. Not in this contract: the markdown export folder of REQUIREMENTS-PLAN 3.11 and the layout of the settings dialog (it uses the `source-keys` endpoints).
