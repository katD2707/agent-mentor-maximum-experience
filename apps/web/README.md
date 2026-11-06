# apps/web — learner web app (Track F)

Next.js 16 (App Router, TypeScript) app for learners: login, onboarding (with parent link for THPT),
chat, practice, progress, goals, memory, reports/research and settings. The learner UI is deliberately minimal and never shows agent internals (file paths, skill ids, job logs). All UI text is
Vietnamese. It talks to the gateway API in `CONTRACTS.md` section 5, or to an in-browser mock.

## Requirements

Node 20.9+ (tested with Node 24) and pnpm 9.

```bash
cd apps/web
pnpm install
```

## Run with the mock (no gateway needed)

```bash
NEXT_PUBLIC_API_MOCK=1 pnpm dev        # http://localhost:3000
```

PowerShell: `$env:NEXT_PUBLIC_API_MOCK="1"; pnpm dev`.

- On `/login`, pick sample data: THPT learner (Lan Anh), NCS (Minh Đức) or a new account that goes through
  onboarding. Enter any email; the page shows the dev magic link. Click it to sign in.
- The mock implements every endpoint in section 5 and the chat WebSocket. State lives in `localStorage`
  (`mentor-mock-state-v1`), so it survives reloads. Switch or reset sample data in **Cài đặt → Chế độ mock**.
- The fake mentor wakes the sandbox (`sleeping → waking → ready`), reports `busy`, streams `text_delta`,
  emits a `tool_started`/`tool_finished` pair, and sends `turn_done`. Things to try in chat:
  - mention “lịch”, “sự kiện” or “nhắc em” (or send every 4th message) → an `approval_request` card; the turn
    waits for your decision;
  - start with “nhớ …” → the mentor edits `me/now.md` (open that file in the editor first to see the 409
    conflict flow);
  - “thông báo” → a `notification`; one also arrives ~25 s after connecting unless proactivity is off;
  - `/loi` → an `error` event.
- Every turn is appended to `sessions/<date>/s-<YYYYMMDD>.jsonl`, which the mock serves as
  `GET /chat/history`; THPT has seeded transcripts for 27–28/10, NCS for 28/10.
- A phone upload (`/m/{token}`, same browser) emits `upload_received` on open chat sockets.
- THPT onboarding: the parent link goes `pending → awaiting_consent → verified` on its own in ~12 s (toggle in
  mock settings), or press “Giả lập bước tiếp theo”.
- In mock mode `window.__mentorMock` is the fake backend, for poking from devtools.

## Run against the gateway

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000/api pnpm dev
```

`NEXT_PUBLIC_API_BASE` defaults to `http://localhost:8000/api`. The WebSocket URL is derived from it
(`ws://localhost:8000/api/ws/chat`). Requests use `credentials: "include"` for the `mentor_session` cookie.
`NEXT_PUBLIC_*` variables are baked in at build time, so set them before `pnpm build`.

What the gateway needs for this to work in dev (web on :3000, gateway on :8000):

- CORS for `http://localhost:3000` with `Access-Control-Allow-Credentials: true` (GET, POST, PUT, DELETE;
  `Content-Type` header). The cookie is `SameSite=Lax`, which is fine because both are `localhost`.
- `GET /auth/verify` must redirect to absolute web URLs (`http://localhost:3000/onboarding` or `/chat`).
  The web app also has `/login/verify?token=…`, which forwards to the gateway, so emailed links may point
  at either.
- `upload_url` from `POST /uploads/mobile-token` should point to the web page `/m/{token}`; that page
  posts the file to `POST /m/{token}` on the gateway.

## Routes

| Route | What |
|---|---|
| `/login`, `/login/verify` | Email magic link; shows `dev_link` when the gateway returns one |
| `/onboarding` | Role (THPT/NCS), display name, language; THPT: 6-digit parent code, bot link/QR, live status polling. Chat stays locked until `verified` |
| `/chat` | Today's history, “Hôm trước” dialog, streaming chat, upload (drag/paste/screenshot/phone QR). Notifications sit behind the bell in the header; approval requests appear inline only while pending; tool activity is one collapsed line; one “Bước tiếp theo” (THPT) in the empty state |
| `/popup` | Same chat, compact layout for the desktop pop-up (`apps/desktop`); `?desktop=1` previews desktop mode in a browser |
| `/memory` | What the mentor remembers (Hồ sơ, Hiện tại, Sở thích, Người quen, Điều gì hiệu quả), each item with Sửa and Quên, “Suy luận” badge; refs and paths are stripped from display |
| `/plans` | Mục tiêu: goal checklist (tick, confetti) and this week's learner tasks |
| `/learning`, `/activity`, `/workspace` | Redirects only (`/progress` or `/research`, `/settings`) |
| `/research` | NCS: research question, thesis milestones, reading queue, readable paper notes |
| `/progress` | THPT: per subject/topic/skill with uncertainty band, trend, “Sắp ôn”, “Lỗi hay gặp”, last 30 sessions, “Bước tiếp theo” |
| `/reports` | THPT: reports sent to parents (front matter hidden) |
| `/settings` | Auto-saved: proactivity, quiet hours, language, up to 3 reminder switches (editable routines only), browser notifications, display; inbound email only on a real domain; “Dữ liệu và tài khoản” (export .zip, delete account, shortcuts, setup guide) |
| `/m/[token]` | Phone upload page opened from the QR code (no session) |

## Checks

```bash
pnpm lint                 # eslint (next core-web-vitals + typescript)
pnpm exec tsc --noEmit    # or: pnpm typecheck
pnpm test                 # vitest: mock API + fake chat socket, chat reducer, markdown parsers, <Markdown> safety
pnpm build
```

## Layout

```
src/
  app/                 routes (App Router); (app)/ holds the signed-in pages behind AuthGate + AppShell
  components/          shell, session, chat/, files/ (FilePanel, FileWorkbench, ChecklistCard), Markdown, QR
  lib/types.ts         TypeScript mirror of CONTRACTS §5 and mentor_schemas (ActivityEntry, Routine, ApprovalRequest…)
  lib/api/client.ts    ApiClient interface, HttpApiClient (fetch + reconnecting WebSocket), ApiError
  lib/api/mock/        MockApiClient, MockChatSocket, seed workspaces (THPT, NCS)
  lib/chat/reducer.ts  chat state machine for the WebSocket messages
  lib/markdown.ts      parsers for skills.md, checklists, frontmatter, memory items
```

Markdown from the workspace is rendered with `react-markdown` + `remark-gfm`; raw HTML is skipped,
`javascript:` links are stripped and remote images are shown as links, never loaded. No runtime CDNs; fonts are
the system stack. QR codes are generated in the browser (`qrcode`).

## Notes

- Chat history comes from `GET /chat/history?date=` (CONTRACTS “Sessions and chat history”). A copy of
  today's transcript is kept in `sessionStorage` and shown only if that request fails.
- Phone uploads are attached when the optional `upload_received` WS event arrives; while the QR dialog is
  open the app also polls `GET /workspace/tree?prefix=inbox` as a fallback.
- A 422 from `PUT /settings` is shown as a Vietnamese message (naming the routine when the detail does).
- Practice setup follows the grade filter (CONTRACTS 10.11): above-grade topics are greyed with a “lớp N” badge until “Thử cả chủ đề lớp trên” is on, which sends `include_above_grade`.
