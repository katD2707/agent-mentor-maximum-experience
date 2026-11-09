# Mentor app

One frontend (Vite + React 19 + TypeScript) for the desktop (Tauri 2), the web/PWA and, later, mobile. Design source:
`mockups/` at the repo root (`shared.css`, `DESIGN.md`). Spec: `survey/REQUIREMENTS-PLAN.md`.

## Screens

Student: login, first run (language and age band), hub with four squares, Courses (today block, my courses, search, course intro
tree, lesson player), Practice (10-question runs, mock exams, practice from a course), Ask (text, photo, voice, course cards),
Progress (goals, planned week, per-course strengths), settings popover (grade, language, theme, reminders, quiet time, sign out).
Teacher: send material, structure chat, review and publish. There is no tab bar: each feature screen has a small back button at the
top left. The mascot "Mực" is on every screen and also opens the guide chat.

Routes are Vietnamese slugs: `/khoa-hoc`, `/luyen-tap`, `/hoi-dap`, `/tien-do`; teachers use `/khoa/:id`.

## Run (Windows PowerShell)

```powershell
pnpm install

# browser, in-browser mock API (hocsinh/123456 student "Lan", giaovien/123456 teacher "Thầy Minh")
$env:VITE_API_MOCK="1"; pnpm dev          # http://localhost:5173

# browser against the gateway (default http://localhost:8000/api)
$env:VITE_API_BASE="http://localhost:8000/api"; pnpm dev

# desktop window
$env:VITE_API_MOCK="1"; pnpm tauri dev

pnpm build        # typecheck + production build into dist/ (first exports the guide map to the gateway)
pnpm test         # vitest
cd src-tauri; cargo check
pnpm release --bump patch --channel stable --base-url https://updates.example.org/app    # see ../../RELEASING.md
```

The mock keeps its users in `localStorage` (`mentor.mock.users`); clear site data to see first run again.

## Layout

- `src/api`: contract types (`course.ts`, `planner.ts`, ... mirror `packages/mentor-schemas`), HTTP client, and the mock API
  (`mock-*.ts`). `media.ts` is the one place that builds asset and cover URLs (`?t=<media token>`).
- `src/state/auth.tsx`: session, `PATCH /me`, quiet time; applies theme, `data-age` and language to `<html>`.
- `src/styles`: `tokens.css` (light/dark/system and age density via `data-age="g1_5|g6_9|g10_12|uni"`), `base.css`, `screens.css`.
- `src/i18n`: vi (default) and en. Every string exists in both.
- `src/screens`: `courses`, `practice`, `ask`, `teacher`, plus Hub, Login, FirstRun, Progress. `src/components`: Settings, Guide (Mực), icons.
- `src/lib`: offline and sync (`offline.ts`, `sync.ts`: enrolled courses are cached, sha256 checked), behaviour logging
  (`behaviour.ts`, `events.ts`, `focus.ts`, `reminders.ts`), deep links, updater, quiet-time rules.
- `public/sw.js`: service worker (offline shell, Web Push); stamped per build by `vite.config.ts`.
- `src-tauri`: product `Mentor`, identifier `vn.mentor.app`; notification, single-instance, opener, autostart and updater plugins,
  tray, hide-on-close.

## Notes

- Mực's guide text lives in `src/lib/guides.ts` (`data-guide` keys on screen regions). After editing it run `pnpm run guides:export`;
  `build` does it too, and a gateway test fails when `ask/guide_map.json` is stale.
- Ask mock (`api/mock-ask.ts`): learning questions give course cards, a maths task gives a solution, a photo gives two problems,
  audio gives a transcript; `localStorage["mentor.mock.badphoto"]="1"` makes photos return the retake flow.
- Mock courses (`api/mock-courses.ts`): Điện trường (g10_12), Đếm táo (g1_5), Suy luận Bayes (uni). Their videos are missing on
  purpose, so the placeholder shows.

## Updates

- Desktop: the app checks its channel's `latest.json` 15 s after start and every 6 h, downloads in the background (thin progress bar with a
  percentage in the notice at the bottom; the Rust side emits `update-progress {downloaded, total}`), and restarts only when calm
  (`canRestart`: not in a lesson or practice run, window hidden or idle for a minute).
- Settings popover (gear), desktop only: **Kiểm tra cập nhật** ("Đang kiểm tra…", then "Bạn đang dùng bản mới nhất (x.y.z)" or the found
  version, whose download starts at once) and **Dùng thử bản mới sớm (beta)**. The switch is stored in `localStorage["mentor.updateChannel"]`
  and sent with `update_check`; Rust reads `<base>/beta/latest.json` instead of `<base>/stable/latest.json` (same base as the built-in endpoint).
  A beta install that returns to stable gets no downgrade; it waits for a stable version above its own.
- Web: no check button and no beta (the row is hidden). The service worker installs a new build in the background and takes over on the next launch.
- Local feed test: build with `--dev-feed` (see `../../RELEASING.md`), serve `release-out` on `http://127.0.0.1:8099`, flip the beta switch, press the button.
