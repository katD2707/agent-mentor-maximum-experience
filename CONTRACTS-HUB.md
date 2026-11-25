# Mentor hub: central accounts, teacher approval, shared course catalog

The UI follows the approved mockups:
- `mockups/lg-00-dang-nhap.html`: login, sign-up, forgot password, and the teacher gate.
- `mockups/gv-00-ho-so.html`: the teacher declaration form.
- `mockups/gv-01-gui-bai.html`: the teacher course list.
- `mockups/gv-03-duyet-noi-dung.html`: "Gửi duyệt".
- `mockups/quan-tri.html`: admin.

```
app (Tauri/web) ──> local gateway (FastAPI, one per PC) ──> hub (Cloudflare Worker + KV, https://hub.mentor-hoc.workers.dev)
                                                              └──> Google Apps Script web app (runs as the owner):
                                                                   Gmail sending + Drive packs + catalog.json
students download courses exactly as today: public catalog.json + packs on the owner's Drive (unchanged)
```

- The hub is on only when the gateway setting `MENTOR_HUB_URL` is set. The standalone package defaults it to `https://hub.mentor-hoc.workers.dev`.
- Without the hub (the dev flavour, tests), everything works as before: local accounts, the seeded `hocsinh`/`giaovien`, and teacher "publish" goes straight to the local store.

## 1. Hub HTTP API (`infra/hub/`)

All bodies are JSON unless marked multipart. Errors look like `{"error": "<code>"}`. User calls carry `Authorization: Bearer <hub token>`.

**`account`** object:
```json
{"id": "a_…", "username": "lan.nguyen", "display_name": "Lan", "role": "student|teacher",
 "email": "x@gmail.com|null", "grade": "1".."12"|"dh"|null, "parent_email": "…|null",
 "teacher_status": null | "chua_nop" | "cho_duyet" | "tu_choi" | "da_duyet" | "xac_minh",
 "reject_reason": "…|null"}
```
Teacher status moves `chua_nop` → (form sent) `cho_duyet` → owner rejects `tu_choi` (resubmit → `cho_duyet`), or the owner approves `da_duyet` (a 6-digit code is emailed) → the teacher enters the code → `xac_minh`. Only `xac_minh` teachers may use course pages.

### Accounts and login

| Method, path | Body | Result |
|---|---|---|
| POST `/api/register` | `{role, username, password, display_name, email?, grade?, parent_email?}` | 201 `{token, account}`. Errors: 409 `username_taken` or `email_taken`, 422 `bad_request`. See rules below. |
| POST `/api/login` | `{login, password}` (`login` = username or email) | `{token, account}`, or 401 `invalid_credentials` |
| GET `/api/me` | | `{account}` |
| POST `/api/logout` | | 204 |
| POST `/api/forgot` | `{login}` | Email on record (own, else parent): sends a 6-digit code and returns `{via: "email", to: "n•••@gmail.com"}`. No email: `{via: "none"}`. Unknown login: also `{via: "none"}`. |
| POST `/api/forgot/request` | `{login, phone?}` | 204. Adds a reset request to the admin list. |
| POST `/api/reset` | `{login, code, password}` | 204, or 400 `wrong_code` |

`/api/register` rules:
- `username` matches `^[a-z0-9][a-z0-9._-]{1,31}$`.
- `password` is at least 6 characters.
- Teachers must give `email`.
- A teacher sign-up gets status `chua_nop` and is emailed a link to the declaration form.

Codes (reset, teacher verification) are 6 digits, valid 24 h, with at most 5 wrong tries.

### Teacher

| Method, path | Body | Result |
|---|---|---|
| POST `/api/teacher/resend-form` | | 204. Emails the declaration form link again. |
| POST `/api/teacher/verify` | `{code}` | `{account}` (status `xac_minh`), or 400 `wrong_code` |
| POST `/api/teacher/resend-code` | | 204. Only when the status is `da_duyet`. |
| GET `/ho-so?t=<form token>` | | The HTML declaration form (port of gv-00). Shows the last reject reason on resubmit. |
| POST `/api/ho-so` (multipart) | `t, full_name, workplace, subjects (repeated), level, cert_kind, cert_number, pledge=1, photos (1–3 images, ≤ 5 MB each)` | An HTML "Đã nhận hồ sơ" page. Status becomes `cho_duyet`. |

### Courses

Only teachers with status `xac_minh` may call these. Any other teacher gets 403 `teacher_unverified`.

**POST `/api/courses/submit`** (multipart). Result: `{course}`.

| Field | What it is |
|---|---|
| `course_id`, `version`, `title` | The course being sent. |
| `entry` | JSON: the catalog entry, exactly as in `catalog.json` `courses[]`. |
| `meta` | JSON: `course.json`. |
| `pack` | The zip file. |
| `zip_sha256` | Hash of `pack`. |
| `cover` | The cover file. |
| `cover_name` | For example `cover.png`. |

Errors:
- 409 `not_owner`: the course id belongs to another teacher.
- 409 `pending`: this course is already waiting.

**GET `/api/courses/mine`** returns `{courses: [course]}`.

**POST `/api/courses/{id}/withdraw`**: only while `cho_duyet`. The queued version is dropped. The course becomes `rut_lai`, or goes back to `da_dang` if an older version is live.

**POST `/api/courses/{id}/remove`**: unpublishes now (Apps Script `unpublish`). The course becomes `da_go`.

**`course`** object:
```json
{"course_id": "c-…", "title": "…", "version": 2, "kind": "new|update",
 "state": "cho_duyet" | "tu_choi" | "da_dang" | "da_go" | "rut_lai",
 "live_version": 1|null, "reason": "…|null", "updated_at": "ISO"}
```

### Admin

Admin calls send the header `X-Admin-Key: <ADMIN_KEY worker secret>`.
- `GET /quan-tri` is a self-contained HTML page, a port of `mockups/quan-tri.html`. It asks once for the key and keeps it in `localStorage`.
- `GET /api/admin/teachers?status=cho_duyet`, and `GET /api/admin/teachers/{id}`, which returns the declaration and photo URLs.
- `GET /api/admin/photo/{key}`
- `POST /api/admin/teachers/{id}/approve` emails the code. `POST …/reject {reason}`.
- `GET /api/admin/courses?state=cho_duyet|da_dang`
- `POST /api/admin/courses/{id}/approve` publishes through Apps Script. `POST …/reject {reason}`. `POST …/remove {reason}`.
- `GET /api/admin/resets` lists the reset requests. `POST /api/admin/accounts/{username}/reset-password` returns `{temp_password}`. `GET /api/admin/accounts?q=` searches accounts.
- `GET /api/admin/outbox` lists the mails that could not be sent, so the owner can relay codes by hand.

Every reject or remove email tells the teacher the reason.

### Storage (KV namespace bound as `HUB`)

| Key | Holds |
|---|---|
| `acct:<id>` | The account. |
| `user:<username>` and `email:<lower email>` | `<id>` |
| `sess:<sha256(token)>` | `<id>`, with a 90-day TTL |
| `code:<purpose>:<id>` | A code, with a TTL |
| `form:<token>` | `<id>` |
| `decl:<id>` | The declaration. |
| `photo:<key>` | Photo bytes. |
| `course:<id>` | The course state and owner. |
| `pending:<id>` | The pack, cover and entry waiting for approval. |
| `reset:<ts>:<username>` | A reset request. |
| `outbox:<ts>` | A mail that could not be sent. |

Passwords are hashed with PBKDF2-SHA256 (WebCrypto) using a per-account salt. The iteration count is stored with the hash.

Worker secrets are `ADMIN_KEY`, `SCRIPT_URL` and `SCRIPT_SECRET`. Without `SCRIPT_URL`:
- mails go only to the outbox;
- course approval returns 503 `script_missing`.

## 2. Apps Script (`infra/hub/apps-script.gs`, deployed by the owner as a web app: execute as me, access anyone)

`doPost` takes the JSON `{secret, action, ...}`. A wrong secret returns `{ok: false, error: "forbidden"}`.

| `action` | Fields | What it does | Returns |
|---|---|---|---|
| `mail` | `to, subject, html` | `GmailApp.sendEmail`, sender name "Mentor" | `{ok: true}` |
| `publish` | `course_id, version, entry, meta, pack_b64, zip_sha256, zip_bytes, cover_b64, cover_name` | Writes into folder `<ROOT>/<course_id>`: `pack-v<version>.zip`, `course.json` and the cover. Shares them as anyone-with-link reader. Then reads `catalog.json` (`CATALOG_ID`), replaces or adds `courses[]` entry `entry`, sets `remote[course_id] = {pack_id, zip_sha256, zip_bytes, cover_id, cover_name, meta}`, and writes the catalog back in place, so its file id stays the same. | `{ok: true, pack_id, cover_id}` |
| `unpublish` | `course_id` | Removes the course from `courses[]` and `remote`. Its files stay. | `{ok: true}` |

`CATALOG_ID` is the existing public catalog `1AreHj5AxvmCmvHeyDHjJpIUXNWxCWHg1`. `ROOT` is that file's parent folder.

## 3. Gateway changes (`services/gateway`)

Setting `MENTOR_HUB_URL`: empty means off. The standalone default is the hub URL.

When the hub is on, the gateway proxies accounts to the hub and keeps a local mirror `User` row, keyed by the hub account id or username. It stores:
- the password hash, so login works offline with the last known password;
- the hub token;
- `teacher_status`;
- `email`.

Local sessions stay as they are: the app only ever talks to the gateway.

App ↔ gateway API:
- `GET /api/auth/config` → `{signup: bool, hub: bool}`.
- `POST /api/auth/register` `{role, username, password, display_name, email?, grade?, parent_email?}` → `{token, user}`.
  - `grade` sets the `birth_year` that `age.grade_for` maps back to that grade; `dh` (đại học) gives age band `uni`.
  - Hub errors pass through as `{error}` with the same status. Network failure gives 503 `hub_offline`.
- `POST /api/auth/login` `{username, password, role?}`.
  - `username` may be an email.
  - `role` is now optional; when it is sent and differs, the result is still `role_mismatch`.
  - With the hub on, try the hub first. On a network failure, fall back to the local mirror hash.
  - On `invalid_credentials` from the hub, when a local legacy account (made before the hub existed) matches the password, register it on the hub silently with the same username and role, then log in. This migrates 0.2.x PCs.
- `UserView` gains `email: str|null` and `teacher_status`. `teacher_status` is null when the hub is off; the app treats null as verified.
- `POST /api/auth/forgot {login}`, `POST /api/auth/forgot/request {login, phone?}` and `POST /api/auth/reset {login, code, password}` proxy to the hub. A reset also updates the local mirror hash.
- `GET /api/teacher/account` returns `{teacher_status, reject_reason, email}` and refreshes from the hub `/api/me`. `POST /api/teacher/account/verify {code}`, `POST /api/teacher/account/resend-form` and `POST /api/teacher/account/resend-code` proxy to the hub.
- Every existing `/api/teacher/*` course route (`teacher_only`) returns 403 `{"error": "teacher_unverified"}` unless `teacher_status` is null or `xac_minh`.
- `POST /api/teacher/courses/{id}/versions/{v}/submit` is the "Gửi duyệt" action.
  - It runs the same checks as `publish` (`level_unconfirmed`, `verify_failed`).
  - It builds the zip with `content.drive.pack_zip`, the entry and the meta (as `DrivePublisher` does), and calls the hub's `/api/courses/submit`.
  - It returns `{hub: course}`.
- With the hub off, the app keeps calling `publish` as today.
- `GET /api/teacher/courses` adds `hub: course|null` to each course, taken from the hub `/api/courses/mine`. The result is cached for 30 s, and the field is null when offline.
- `POST /api/teacher/courses/{id}/withdraw` and `POST /api/teacher/courses/{id}/remove` proxy to the hub.
- `DrivePublisher.push_catalog` (the owner's `push-all`) must keep catalog entries and `remote` entries for course ids that are not in the local store (teacher courses published through the hub). It reads the current public catalog and merges.

## 4. App changes (`apps/app/src/lang`)

**Login, a port of lg-00:**
- One "Tên đăng nhập hoặc email" field and a password field.
- "Tạo tài khoản" leads to the role cards, then the student form or the teacher form.
- Forgot password has two paths: by code, or by a request to the teachers.
- The new fields are shown only when `config.hub` is true. With the hub off, keep today's simple local sign-up.

**Teacher gate.** After login, a teacher whose `teacher_status` is not null and not `xac_minh` sees only the gate screens from lg-00:
- `chua_nop`: "Gửi lại email".
- `cho_duyet`: "Có thể đóng app".
- `tu_choi`: the reason, plus "Nộp lại hồ sơ", which asks the hub to resend the form link.
- `da_duyet`: 6 code boxes and "Gửi lại mã".

Every gate screen has "Đăng xuất". A correct code opens the teacher home.

**Teacher home, gv-01.** Each course shows a status chip from `hub.state`, with actions:
- Bản nháp: Tiếp tục.
- Chờ duyệt: Rút lại.
- Bị từ chối: shows the reason, plus Sửa.
- Đã đăng: Sửa, and Gỡ (with a confirm).

**End of the course flow, gv-03.** With the hub on, the final button is "Gửi duyệt" (submit). With the hub off, it stays "Xuất bản" (publish).
