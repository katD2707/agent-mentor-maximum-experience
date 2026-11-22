# Mentor app

One frontend (Vite + React 19 + TypeScript) for the desktop (Tauri 2), the web/PWA and, later, mobile. Design source:
`mockups/` at the repo root (`shared.css`, `DESIGN.md`). Spec: `survey/REQUIREMENTS-PLAN.md`.

## Screens

The student UI is **Làng gà** (design: `mockups/lg-*.html`, teacher `gv-*.html`; contract `CONTRACTS-LANGGA.md`). The home is the village:
each subject (or ngành at university) is one chicken that grows with XP (stages: level 1, 2-4, 5-9, 10+ "Cao thủ" with a gold crown). The chicken
that speaks first suggests what to do, and a chat tray takes questions, photos of homework and notes. From the village: the chicken's coop
(`/chuong/:chicken`: its courses, find and add courses), lessons (`/khoa-hoc/:id/hoc`), the arena with real papers and course tests
(`/dau-truong`, `/kiem-tra/:courseId`; the tray only points there), practice runs (`/luyen-tap/:id`), the study room (`/phong-tu-hoc`), progress
(`/tien-do`), the Library for university students (`/thu-vien`), the market to take more chickens, the news board and settings. Login and
first run (language, birth year, up to three chickens) use the same wood-board look.
Teacher: send material, structure chat, labels (chicken, level, grade, difficulty, goals, language, topics), review (the student's lesson
blocks, read only) and publish; routes `/khoa/:id`, `/khoa/:id/nhan`, `/khoa/:id/duyet`.
A small guide chicken stands on every screen, teachers included (first-visit tour, tap for help, drag it onto a part to have it explained).

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
- `src/styles`: shared sheets of the lesson blocks and the research body (`courses.css`, `practice.css`, `research.css`), `tokens.css` (light/dark/system and age density via `data-age="g1_5|g6_9|g10_12|uni"`), `base.css`, `screens.css`.
- `src/i18n`: vi (default) and en. Every string exists in both.
- `src/lang`: the whole UI. `screens/` (village, arena, chuong, lesson, practice, study, progress, library), `teacher/`, `guide/` (the chicken guide),
  `engine/` (the painted village), `api/` (typed clients + the mock for `VITE_API_MOCK=1`), `kit/` (lesson blocks, quiz and answer inputs, shared with the
  teacher review), `styles/`, `i18n*` (the `lg` namespace), `xp.ts` (XP event bus), `subjects.ts` (chickens, levels, stages) and `gaFiles.json`
  (which pictures exist; written by `node scripts/sync-ga-assets.mjs`, which also copies the art from `mockups/assets/ga`). `src/components`: icons, update notice.
- `src/lib`: offline and sync (`offline.ts`, `sync.ts`: enrolled courses are cached, sha256 checked), behaviour logging
  (`behaviour.ts`, `events.ts`, `focus.ts`, `reminders.ts`), deep links, updater, quiet-time rules.
- `public/sw.js`: service worker (offline shell, Web Push); stamped per build by `vite.config.ts`.
- `src-tauri`: product `Mentor`, identifier `vn.mentor.app`; notification, single-instance, opener, autostart and updater plugins,
  tray, hide-on-close.

## Notes

- `src/lib/guides.ts` is only the server's guide map (`pnpm run guides:export` copies it to the gateway, a gateway test checks it); the screens use the chicken guide.
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
