# Làng gà: contract additions (2026-11-22)

The student UI is now the "Làng gà" village (mockups: `mockups/lg-*.html`, teacher: `mockups/gv-*.html`). This file is the
shared contract between the gateway work and the app work. Everything in `CONTRACTS.md` still holds unless replaced here.
All routes are under `/api`, Bearer auth as today. Errors keep the `{"error": code}` shape.

## 1. Chickens (subjects)

A chicken is a subject for one school stage. The id list and names are fixed in code (gateway `mentor_gateway/langga/subjects.py`,
mirrored in the app `src/lang/subjects.ts`). Taken from the mockups (`lg-01` market, `lg-02`, `lg-03 SUBJ2GA`):

| Stage (age band) | Chicken ids |
|---|---|
| g1_5, g6_9 | toan, van, anh, khoahoc, su, dia, cd, tin, cn, nt, kn |
| g10_12 | toan, van, anh, li, hoa, sinh, su, dia, cd, tin, cn, nt, kn |
| uni | khmt, ktmt, httt, khdl, toanhoc, vatli, hoahoc, kinhte, ketoan, nna, daicuong |

- Names: "Gà " + label (Toán, Văn, Anh, Khoa học, Sử, Địa, Công dân, Tin, Công nghệ, Nghệ thuật, Kỹ năng, Lí, Hóa, Sinh,
  Khoa học máy tính, Kỹ thuật máy tính, Hệ thống thông tin, Khoa học dữ liệu, Toán học, Vật lí, Hóa học, Kinh tế, Kế toán,
  Ngôn ngữ Anh, Đại cương); English "<Label> chicken".
- Art id (file under the app's `ga/` assets): same as id except nt→nghethuat, kn→kynang, toanhoc→toan, nna→anh.
- Course → chicken: `chicken_of(course)` maps the catalog's free-text `subject` + `age_band` with the `SUBJ2GA` table of
  `mockups/lg-03-chuong-ga.html` (school vs uni), plus: g10_12 Vật lí/Hóa học/Sinh học → li/hoa/sinh; below g10_12 they go to
  khoahoc; unknown → kn (school) / daicuong (uni). A course may carry an explicit `chicken` field (teacher label, gv-03)
  which wins. `CatalogEntry` gains `chicken: str` (computed when missing) and the catalog query gains a `chicken` facet.

### Levels and XP
- 100 XP per level, level starts at 1. Growth stage for art: 4 stages: 1 = Gà con (lv 1), 2 = Gà choai (lv 2–4), 3 = Trưởng thành (lv 5–9), 4 = Cao thủ (lv 10+).
- XP is a ledger `xp_events(user_id, chicken, source, ref, amount, created_at)` with UNIQUE(user_id, source, ref), so
  every award is idempotent. Sources and amounts (the rules shown in `lg-09`):

| source | amount | ref |
|---|---|---|
| lesson_done | +20 when every block of a lesson is complete (blocks and single quiz answers pay nothing) | `<course>:<lesson>` |
| lesson_perfect | +5 on top when every quiz item of that lesson was right on the first try | `<course>:<lesson>` |
| practice_right | +2 per right answer in a practice session | `<session>:<item>` |
| fix_right | +3 per wrong answer fixed | `<session>:<item>` |
| mock_submit | +40 when a course mock exam is submitted | `<session>` |
| paper_submit | +40 when an arena paper is submitted | `<session>` |
| boss_beaten | +50 when the arena score >= 5/10 (first time per paper) | `<paper>` |
| focus | +1 per focus minute in the study room | `<focus_id>` |
| focus_full | +5 more when the planned session is completed in full | `<focus_id>` |
| notes_review | +2 per notes review card answered right | `<session>:<item>` |

These are the amounts of the approved UI (`mockups/lg-09-tien-do.html`, "cách gà lớn"). Study-room XP has a quiet cap of 120 a day
(`focus` + `focus_full`).

## 2. Endpoints (new)

### Village and market
- `GET /village` → `{ chickens: Chicken[], speaker: {chicken, line_vi, line_en, action:{kind, deep_link, minutes}} | null,
  news: NewsItem[], streak:{days,today_done}, week:{done,planned} }`. `speaker` is the chicken that speaks first (today's
  planned session from the planner, else the chicken with the most recent activity). `news`: level-ups, reminders, new courses.
- `Chicken = { id, name_vi, name_en, art, level, xp, xp_in_level, stage, courses: number, active_course: {id,title,percent}|null,
  done_today: bool, taken_at }`.
- `GET /market` → `{ stage: band, chickens: [{id, name_vi, name_en, art, courses, owned}] }` (only the band's list).
- `POST /chickens {chicken}` → `Chicken` (take, free; 409 `already_owned`; 400 `not_in_stage`).
- `DELETE /chickens/{id}` → 204 (let go; XP kept in the ledger, restored if taken again).
- `GET /chickens/{id}` → `{ chicken: Chicken, courses: [enrolled course rows with percent, last lesson], suggested: CatalogEntry[] (≤12),
  week_xp: [7 numbers], tests: [{course_id, profile_or_mock, title, minutes, items, last_score}] }`.
- First run: `PATCH /me` accepts `avatar: "nam"|"nu"`; after FirstRun the app POSTs up to 3 chickens.
- Students with no chickens yet: `GET /village` returns `chickens: []` and the app sends them to choose (lg-02).
- Migration: on first `/village` call for an existing student, chickens are created for every enrolled course's chicken.

### Course tests (lg-07)
- `POST /practice/sessions {source: "course-mock:<course_id>"}` → a timed mock built from that course's own quiz items
  (all lessons, mixed difficulty; 22 items or all if fewer, ≥ 6 items else 422 `insufficient_content`; minutes = 2 per item,
  capped 45). Same runner as bank mocks (deadline, flag, auto-finish). Existing `course:<id>` practice levels stay.

### Arena (lg-05)
- Papers are content files `mentor-content/papers/<id>.json` (schema `mentor_schemas.paper.Paper`):
  `{id, kind: "thpt"|"minh-hoa"|"dgnl"|"cuoi-ky", band: "g10_12"|"uni", chicken, title_vi, title_en, year, minutes,
    parts:[{id, title_vi, title_en, type, items:[QuizItem-like with answer_key, explanation]}], source:{name,url}, placeholder: bool}`.
  The crawl project will later write files in this format (importer: `mcb papers import <dir>` — stub ok).
- Ship 4–6 placeholder papers (`placeholder: true`, items drawn from the bank, correct THPT 2025 structures), clearly labelled
  "Đề mẫu" in the UI until real ones are imported.
- `GET /arena/papers?chicken=&year=` → `[{id, kind, title_vi, title_en, year, minutes, items, chicken, boss:{name_vi, name_en, art},
  best_score, beaten, placeholder}]` (filtered to the user's band).
- `POST /practice/sessions {source: "paper:<id>"}` → mock-kind session (deadline = minutes, auto-finish at 0, no feedback).
- The finish `Report` for a paper adds `boss: {name, hp: items, damage: right, beaten: score_10 >= 5}` and `xp: [{source, amount}]`.
- Bosses: one per chicken art family; names from the mockups (toan "Quái Sai Số", van "Bóng Lạc Đề", anh "Quái Lỗi Ngữ Pháp",
  others reuse the closest).

### Study room (lg-06)
- `POST /focus {minutes, chicken}` → `{id, ends_at}`; `POST /focus/{id}/finish {minutes_done}` → `{xp, chicken: Chicken}`;
  `GET /focus/active`. Also emits the existing `session_start/end` behaviour events server side.

### Chat with a chicken (lg-01 tray)
- `POST /chat/{chicken}` SSE, body `{text?, thread_id?, lang}` or multipart with `image`/`audio` → events
  `thread, status, transcript, delta (streamed text), message, actions([{label_vi,label_en,deep_link}]), error, done`.
  Persona: that subject's chicken, talks only about its subject and the student's learning; remembers the last 30 turns per
  chicken (`chat_turns` table). Solve requests (photo of an exercise) reuse the Ask solve pipeline and stream its events.
- `GET /chat/{chicken}/history?limit=30`.

### Notes (Chụp vở)
- `GET /ask/notes` → list of the learner's notes sets `{notes_id, title, pages, items, created_at, next_review_at}`.

### XP read
- Every response that changes XP includes `xp: [{chicken, source, amount, level_up: bool}]` where natural
  (enrollment progress PUT, practice answer/finish/fix, focus finish). `GET /xp/week` → per chicken, 7-day sums (lg-09).

## 3. Teacher (gv-01..gv-04)
Same endpoints as today. Additions: the course labels step (gv-03) edits `{chicken, band, level, difficulty, goals, language, topics}` via
`PUT /teacher/courses/{id}/versions/{v}/labels` (chicken validated against the band's list).

## 4. App structure
- Routes (hash): `/` village (lg-01), `/chon-ga` (lg-02 first run), `/chuong/:chicken` (lg-03), `/khoa-hoc/:id/hoc` (lg-04),
  `/dau-truong` and `/dau-truong/:paper` (lg-05), `/phong-tu-hoc` (lg-06), `/kiem-tra/:courseId` (lg-07),
  `/luyen-tap/:sessionId` (+`/ket-qua`, `/xem-lai`), `/tien-do` (lg-09), `/thu-vien` and `/thu-vien/paper/:id` (lg-10, uni).
  Old deep links (`/khoa-hoc/:id`, `/luyen-tap?notes=`, `/hoi-dap`, `/nghien-cuu...`) redirect to their new homes.
- The chicken guide (`mockups/ga-guide.js/css`) replaces the Mực mascot.

## 5. As built (gateway, 2026-11-22): details and deviations

- **XP amounts** are those of section 1 (the approved lg-09 list). Constants live in `langga/xp.py` (`AMOUNTS`, `FOCUS_*`). Lesson
  XP is paid only for lessons touched by the progress call (earlier progress is not paid back); `lesson_perfect` needs at least one quiz
  item and every item answered right with `attempts == 1`. "Review card due today" has no separate source: due-review items answered
  in practice pay `practice_right` (+2) and notes cards `notes_review` (+2).
  Awards of one response are summed per `(chicken, source)`: `xp: [{chicken, source, amount, level_up}]`; `xp: []` means nothing new.
  Where `xp` appears: `PUT /enrollments/{id}/progress` (view + `xp`), `POST /practice/sessions/{id}/answer` (only for a
  *practice* session, right or wrong), `.../fix`, the finish `Report` (`mock_submit`, `paper_submit`, `boss_beaten`), `POST /focus/{id}/finish`.
  A bank mock (`mock:<profile>`) also pays `mock_submit`. Notes sessions (`notes:<id>`) pay `notes_review` instead of `practice_right`.
  XP goes to the chicken of the item's course, bank subject (math->toan, physics->li, english->anh; uni: toanhoc, vatli, nna) or paper.
- `GET /village` also returns `avatar` and `stage` (the band); `speaker` carries `chicken`, `line_vi/en`, `action`, `name_vi`; each
  `news` item is `{kind: level_up|reminder|new_course, chicken, text_vi, text_en, deep_link}`. `streak`/`week` come from the planner.
- `GET /chickens/{id}` works for any chicken of the student's stage (owned or not); `tests[]` also lists bank mocks of the chicken
  (`course_id: null`, `profile_or_mock: "mock:<profile>"`). `GET /xp/week` -> `{days[7], chickens:[{chicken, owned, level, xp,
  xp_in_level, stage, week[7], week_total, by_source}], total}`.
- Course mock: `course-mock:<id>`; needs an enrollment (404 `course_not_found`); items are *all* quiz items of the pinned version
  (22 chosen with a 40/30/20/10 level mix when there are more); minutes = 2 per item, max 45. Sessions carry `source`.
- Arena: `GET /arena/papers` rows also have `band`, `note_vi/en`, `source`. Paper sessions use the mock runner; `subject` is
  `pp:<id>`; the session view has `source` and `paper: {id, kind, chicken, title_*, placeholder, boss}`. Report `boss` =
  `{name, name_vi, name_en, art, hp, damage, beaten}` (`name` is the Vietnamese name; art ids `boss-toan|boss-van|boss-anh`; English
  names: The Slip-Up Monster, The Off-Topic Phantom, The Grammar-Slip Monster). Errors: 404 `unknown_paper`, 403 `band_mismatch`.
  Papers are text only (no asset files). Placeholders: thpt-toan-2025-mau (12+4+6, 90 min), thpt-ly-2025-mau (18+2+2, 50 min; the
  bank has only 2 true/false and 2 short-answer physics items), thpt-anh-2025-mau (40, 50 min), dgnl-toan-mau (30, 60 min),
  cuoi-ky-xstk-mau (uni, 8 items from the live Xác suất thống kê course). Importer: `python -m mentor_gateway.langga.papers import
  <dir>` (the real thing, not a stub; `mcb papers import` was not added to the course-builder CLI).
- Study room: `POST /focus` -> `{id, ends_at, chicken, minutes}` (5-120 min); a new one replaces an unfinished one. `finish` pays
  `min(minutes_done, planned, elapsed + 1 min)` XP (`focus`, +1 a minute) and `focus_full` +5 when that equals the planned minutes;
  the quiet cap is 120 focus XP a day; response `{xp, gained, minutes_done, daily_cap, chicken}`. `GET /focus/active` ->
  `{id, chicken, minutes, started_at, ends_at, remaining_sec, status}` or `null`.
- Chat: SSE `actions` data is `{actions: [{key, label_vi, label_en, deep_link}]}`; `delta` is `{text}`; the reply is also sent whole as
  `message {kind: "chat", text}`. Keys: practice, lesson, test, arena, study_room, chuong, progress (lesson/test only with an enrolled
  course in that chicken). Body also takes `action`/`problem_id` for Ask follow-ups. `GET /chat/{chicken}/history` -> list of
  `{role, text, actions, created_at}` oldest first. Alias `mentor-chat` only; with no router: `error model_unavailable` then `done`.
- Notes: `GET /ask/notes` rows also have `subject`.
- Teacher labels: `PUT .../labels {chicken?, band?, level?, difficulty?, goals?, language?, topics?}`: `band` = bậc học, `chicken` = gà chính (422
  `chicken_not_in_band`), `difficulty` = basic|intermediate|advanced (the existing course level), `level` = school grade 1-12 (a
  difficulty word is accepted there too). A draft keeps the labels until publish; the latest published version takes them at once
  (`course.json` + `catalog.json`, no new version, unlike `PUT .../level`). Response `{version, chicken, band, level, difficulty,
  labels, published}`. New optional fields: `goals: string[]` (Mục tiêu, <= 6 lines of <= 160 chars; becomes the course `outcomes`),
  `language: "vi"|"en"` (the course language tag), `topics: string[]` (Chủ đề, <= 8 tags of <= 40 chars; new `topics` on
  `course.json` and each catalog entry). Blank lines are dropped, whitespace collapsed; over the limits = 422. Stored in
  `labels` ({goals, language, topics} next to chicken/band/grade); the latest published version applies them at once to
  `course.json` + `catalog.json`, a draft at publish. `GET /teacher/courses/{id}` `course.labels` =
  `{goals, language, topics, suggested: {goals, language, topics}}`: current values of the working version (open draft, else latest
  published), falling back to Mentor's suggestion (outline outcomes, course language, `[subject]`).
- Tables: `user_chickens`, `langga_state`, `xp_events`, `focus_sessions`, `chat_turns`; column `users.avatar`; `course.json` gains
  `chicken`, `grade`; a version gains `labels`.
