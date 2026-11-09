# mentor

One learning app for students from grade 1 to university, and for teachers. Students see four things (Courses, Practice,
Ask, Progress); teachers drop in material and review the course an agent drafts. Everything else (lesson building, the weekly
plan, reminders) is done by agents on the server. Product spec: `../REQUIREMENTS-PLAN.md`. Interfaces: [CONTRACTS.md](CONTRACTS.md).

## Cài đặt và dùng thử

Bản dùng thử có hai phần chạy trên **cùng một máy**:

1. **App Mentor**: cài bằng cách bấm đúp, như mọi phần mềm khác.
2. **Máy chủ**: một cửa sổ chạy nền để app gọi AI. Bản thử nói chuyện với máy chủ ngay trên máy đó (`127.0.0.1`), nên cần bật máy chủ trước khi mở app.

Khi Mentor có máy chủ thật trên mạng, người dùng chỉ cần bước 1.

### Bước 1. Cài app

Các file cài đặt (`Mentor_0.1.0_...`) nằm ngay trong thư mục `mentor` trên máy đã build. Chúng không lên GitHub vì mỗi file nặng 6–85 MB, nên được gửi kèm riêng.

| Máy | File | Cách cài |
|---|---|---|
| Windows 10, 11 | `Mentor_0.1.0_x64-setup.exe` | Bấm đúp rồi làm theo trình cài. Nếu hiện "Windows protected your PC", bấm **More info**, rồi **Run anyway**: bản thử chưa có chữ ký số. |
| Ubuntu, Linux Mint, Debian | `Mentor_0.1.0_amd64.deb` | Bấm đúp, cửa sổ Software hiện ra, bấm **Install**. |
| Linux khác | `Mentor_0.1.0_amd64.AppImage` | Chuột phải, chọn **Properties**, rồi **Permissions**; bật **Allow executing file as program**, sau đó bấm đúp. |
| macOS | chưa có sẵn | Dùng bản web ở bước 2, hoặc nhờ người phụ trách build trên GitHub (**Actions**, chọn **Desktop installers**, rồi **Run workflow**). Lần đầu mở app: vào **System Settings**, chọn **Privacy & Security**, bấm **Open Anyway**. |

Sau khi cài, app tự mở cùng máy và nằm ở khay hệ thống (góc dưới bên phải) để nhắc giờ học. Muốn thoát hẳn: chuột phải vào biểu tượng Mực ở khay, chọn **Thoát Mentor**.

### Bước 2. Bật máy chủ

**Windows.** Làm một lần:

1. Cài **uv** (công cụ chạy Python). Mở **PowerShell**, dán dòng dưới rồi nhấn Enter. Xong thì đóng PowerShell.
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. Tải mã nguồn: trên trang GitHub của repo, bấm **Code**, rồi **Download ZIP**, sau đó giải nén.
3. Trong thư mục vừa giải nén, chép file `.env.dev.example` thành `.env.dev.local`. Mở bằng Notepad và điền key (xem bước 3).

Mỗi lần dùng: mở thư mục đó trong File Explorer, bấm vào thanh địa chỉ, gõ `powershell` rồi nhấn Enter. Trong cửa sổ hiện ra, chạy:

```powershell
powershell -ExecutionPolicy Bypass -File infra\dev-up.ps1 -ServerOnly
```

Hai cửa sổ mới sẽ mở (model router và gateway). Lần đầu mất vài phút để tải thư viện. Khi cửa sổ **gateway** có dòng `Uvicorn running` là xong. Cứ để hai cửa sổ đó mở trong lúc dùng app; đóng chúng là tắt máy chủ.

**macOS, Linux** (cần Docker): điền key vào `infra/.env.demo` (lần chạy đầu, script tự tạo file này từ `infra/.env.demo.example`), rồi chạy `bash infra/demo.sh`. Lệnh này bật cả máy chủ lẫn bản web ở http://localhost:3000, nên trên Mac có thể dùng thử ngay bằng trình duyệt.

### Bước 3. Các key cần có

Key là mật khẩu để máy chủ gọi các model AI. **Repo là công khai nên không chứa key nào.** Người phụ trách dự án sẽ gửi riêng giá trị key; chỉ dán chúng vào `.env.dev.local` (hoặc `infra/.env.demo`). Cả hai file đã được loại khỏi git, đừng dán key vào chỗ nào khác.

| Key | Bắt buộc | Dùng để | Lấy ở đâu |
|---|---|---|---|
| `FPT_API_BASE` | Có | Địa chỉ dịch vụ model | Người phụ trách gửi kèm, hoặc trang API của FPT AI Factory |
| `FPT_API_KEY` | Có | Mọi phần dùng AI: hỏi đáp, giải bài từ ảnh, nói thay gõ, lập lịch, soạn khóa, nghiên cứu | FPT AI Factory, mục API keys |
| `MODEL_ROUTER_MASTER_KEY` | Không cần điền | Khóa nội bộ giữa máy chủ và bộ chuyển model | Để trống; lần chạy đầu script tự tạo và lưu lại |
| `GEMINI_API_KEY` | Không | Ảnh minh họa và giọng đọc dự phòng khi soạn khóa | https://aistudio.google.com, bấm **Get API key** |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Không | Sinh ảnh minh họa cho bài học | Chạy `powershell -ExecutionPolicy Bypass -File infra\cloudflare-key.ps1`, script hướng dẫn từng bước và tự lưu |
| Semantic Scholar, Asta | Không | Tìm paper kỹ hơn (giao diện đại học) | Không đặt ở máy chủ: mỗi người tự dán key của mình trong app, ở **Cài đặt**, mục **Nguồn tìm paper** |

Thiếu `FPT_API_KEY` thì máy chủ không bật. Thiếu các key tùy chọn thì app vẫn chạy đủ: bài học dùng hình vẽ thay ảnh, giọng đọc dùng giọng miễn phí, tìm paper chỉ dùng arXiv.

### Bước 4. Đăng nhập thử

| Vai trò | Tài khoản | Mật khẩu |
|---|---|---|
| Học sinh | `hocsinh` | `123456` |
| Giáo viên | `giaovien` | `123456` |

Chạm vào hình học sinh hoặc giáo viên trước, rồi mới điền tài khoản. Lần đầu, học sinh chọn ngôn ngữ và năm sinh; năm sinh quyết định giao diện. Ví dụ trong năm học 2026–2027: sinh năm 2018 là tiểu học, 2013 là THCS, 2010 là THPT, từ 2008 trở về trước là đại học (có thêm phần **Nghiên cứu**). Lần đầu mở mỗi trang, Mực sẽ chỉ nhanh các phần chính.

### Khi có lỗi

- **"Không kết nối được máy chủ"**: máy chủ chưa bật, hoặc cửa sổ gateway chưa hiện `Uvicorn running`. Làm lại bước 2.
- **Script báo thiếu `.env.dev.local` hoặc `FPT_API_KEY`**: xem mục 3 của bước 2, và bước 3.
- **Các phần AI báo lỗi, phần còn lại vẫn chạy**: key FPT sai, hoặc đã hết hạn mức. Hỏi người phụ trách.

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

## Local demo (Linux or macOS + Docker)

`bash infra/demo.sh` (first run creates `infra/.env.demo`; fill `FPT_API_BASE`, `FPT_API_KEY`, run again), then open
`http://localhost:3000` and sign in with the dev accounts. Also `logs`, `stop`, `reset`. Dev mode, bound to this machine only.
