# mentor

Personal AI mentor with long-term, file-based memory for high-school students (THPT) and graduate
students (NCS/SV). Interfaces between the parts: [CONTRACTS.md](CONTRACTS.md).

## Layout

| Path | What |
|---|---|
| `packages/mentor-schemas` | Shared pydantic contracts (workspace layout, events, sandbox API, outbox, protocols) |
| `sandbox-image/harness` | Agent loop, tools, hooks and HTTP server running inside each learner's sandbox |
| `sandbox-image/scripts` | Deterministic CLIs the agent runs: events, wellbeing, BKT, SymPy, PDF, report check |
| `mentor-content` | `AGENTS.md`, skills, workspace templates, curricula |
| `services/gateway` | Control plane: auth, ops DB, sandbox orchestrator, mirror, scheduler, outbox, REST + WS |
| `services/parent-channel` | Zalo Bot: parent linking, reports, crisis alerts |
| `services/email-ingest` | Inbound email → learner `inbox/` |
| `services/model-router` | LiteLLM config mapping model aliases to the FPT endpoint |
| `apps/web` | Next.js app: chat, memory, plans, reports, workspace, settings; `/popup` is the desktop panel |
| `apps/desktop` | Tauri 2 desktop pop-up: floating "M" bubble + compact chat panel (loads the web app's `/popup`) |
| `evals` | Scenario evals: synthetic personas run through the harness in-process (`uv run --package mentor-evals mentor-evals run`) |
| `infra` | Dev docker-compose and run guide; local demo (`demo.sh`); pilot deployment (`docker-compose.prod.yml`, `Caddyfile`, `deploy.sh`) |

## Chạy thử trên máy (Linux + Docker)

Bản dùng thử trên một máy Linux, chỉ cần FPT key. Không cần email, Zalo hay tên miền; chỉ mở cho chính máy đó.

```bash
git clone https://github.com/katD2707/agent-mentor-maximum-experience.git mentor && cd mentor
bash infra/demo.sh            # lần đầu: tạo infra/.env.demo rồi dừng lại
nano infra/.env.demo          # điền FPT_API_BASE và FPT_API_KEY
bash infra/demo.sh            # build + chạy (lần đầu 5-15 phút), xong mở http://localhost:3000
```

- **Đăng nhập**: gõ email bất kỳ, link và mã 6 số hiện ngay trên trang. Học sinh THPT: ở bước liên kết phụ huynh bấm
  nút xác minh thử.
- **Tài khoản mẫu có sẵn dữ liệu** (giả lập): `bash infra/demo.sh accounts` in link đăng nhập của học sinh lớp 11 và
  nghiên cứu sinh.
- Khác: `bash infra/demo.sh logs gateway` (xem log), `stop` (dừng, giữ dữ liệu), `reset` (xoá hết dữ liệu demo),
  `login <email>` (link đăng nhập mới). Cổng 3000/8000 bận thì đổi `WEB_PORT`/`API_PORT` trong `infra/.env.demo`.
- Cần Docker Engine + plugin compose, khoảng 4 GB RAM trống và 10 GB đĩa.
- Đây là bản thử (chế độ dev, sandbox không tách container từng người): không dùng cho học viên thật; bản cho học viên
  là mục "Triển khai lên server (pilot)" bên dưới.

## Dev setup

```bash
uv sync --all-packages --python 3.11
uv run pytest            # all Python tests
cd apps/web && pnpm install && NEXT_PUBLIC_API_MOCK=1 pnpm dev
```

Full stack with real models, Windows PowerShell: put `FPT_API_BASE`, `FPT_API_KEY` and `MODEL_ROUTER_MASTER_KEY`
(optional: `ASTA_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `ZALO_BOT_TOKEN/URL`) in `.env.dev.local` at the repo
root (gitignored), then run the line below. It opens the router, gateway and web in separate windows, with data in
`var-dev`; add `-Desktop` for the desktop bubble.

```powershell
powershell -ExecutionPolicy Bypass -File infra\dev-up.ps1
```

Full stack with the scripted model (no API key needed; two terminals; see `infra/README.md` for bash):

```powershell
# terminal 1, repo root
$env:MENTOR_ENV="dev"; $env:MENTOR_DATA_DIR="var"; $env:SANDBOX_BACKEND="local"; $env:MENTOR_MODEL_MODE="scripted"
uv run uvicorn mentor_gateway.app:app --port 8000
# terminal 2
cd apps/web; Remove-Item Env:NEXT_PUBLIC_API_MOCK -ErrorAction SilentlyContinue
$env:NEXT_PUBLIC_API_BASE="http://localhost:8000/api"; pnpm dev
```

`MENTOR_ENV` must be set for development: when it is missing the gateway assumes `prod` (no magic links in
responses, no dev parent verification, no local sandbox backend, `MENTOR_MASTER_KEY` required), so a forgotten
variable fails safe instead of silently running in dev mode.

Models are reached only through the router aliases in `mentor_schemas.ModelAlias`. Without router
credentials, run the harness with `MENTOR_MODEL_MODE=scripted`.

Literature tools (NCS) use arXiv, Semantic Scholar and the **Asta Scientific Corpus Tool** by Ai2 (Allen Institute
for AI), which is licensed for academic and non-commercial use only; this is a non-commercial research project.
Asta results shown to learners carry an attribution line, and only search terms and paper ids are sent to Ai2.

## Triển khai lên server (pilot)

Một VM Linux có Docker chạy toàn bộ phía server: **Caddy** (HTTPS tự động, cổng 80/443 duy nhất mở ra ngoài) chuyển
`/api/*` (cả WebSocket `/api/ws/chat`) và `/webhooks/*` (Zalo, email chuyển tiếp) tới **gateway**, phần còn lại tới **web** (Next.js);
**model-router** (LiteLLM) gọi model FPT; **SearXNG** cho công cụ tìm web; mỗi học viên một **container sandbox**
riêng do gateway khởi động. File: `infra/docker-compose.prod.yml`, `infra/Caddyfile`, `infra/.env.prod.example`,
`infra/deploy.sh`, `apps/web/Dockerfile`. Học viên dùng link web `https://<DOMAIN>` hoặc app máy tính cho Windows (`.exe`) / Linux
(`.deb`, `.AppImage`), cùng trỏ tới địa chỉ đó (infra/README.md, "Desktop app downloads (prod)").

### 1. Chuẩn bị trước

| Cần có | Lấy ở đâu |
|---|---|
| VM Linux (Ubuntu 22.04/24.04), IP công khai, đăng nhập SSH bằng key | nhà cung cấp cloud (FPT Cloud, Azure, AWS, ...) |
| Tên miền, hoặc dùng `sslip.io` | bản ghi A trỏ về IP của VM. Không có tên miền: IP `203.0.113.5` -> `DOMAIN=203-0-113-5.sslip.io` (tự phân giải về IP đó, không cần cấu hình DNS, vẫn có chứng chỉ Let's Encrypt thật) |
| `FPT_API_BASE`, `FPT_API_KEY` | FPT AI Factory (giống `.env.dev.local`, nhưng nên tạo key riêng cho pilot) |
| Gmail gửi thư đăng nhập: địa chỉ + **app password** | nên dùng một tài khoản Gmail riêng. Bật Xác minh 2 bước, rồi https://myaccount.google.com/apppasswords -> tạo app password (16 ký tự) |
| Zalo bot: token + link chia sẻ | https://bot.zaloplatforms.com -> tạo bot. **Bắt buộc nếu có học sinh THPT** (xem mục 9) |
| (tuỳ chọn) Email chuyển tiếp: một tên miền dùng DNS của Cloudflare | tài khoản Cloudflare (gói Free được). Xem mục 10 |
| (tuỳ chọn) `ASTA_API_KEY`, Google OAuth client | infra/README.md ("Gateway environment", "Google Calendar"). Redirect URI cần đăng ký: `https://<DOMAIN>/api/integrations/google-calendar/callback` |

`MENTOR_MASTER_KEY`, `MODEL_ROUTER_MASTER_KEY`, `SEARXNG_SECRET`, `ZALO_WEBHOOK_SECRET`, `EMAIL_WEBHOOK_SECRET` do
`deploy.sh` tự sinh lần đầu.

### 2. Chọn cỡ VM

Đo ngày 2026-11-02 trên Docker Desktop: sandbox rảnh dùng **~40 MB** RAM, khi chạy `run_python` có
matplotlib **~90 MB**; mỗi sandbox bị giới hạn cứng 1 GB RAM, 1 CPU, 256 PIDs, và `/tmp` (tmpfs 256 MB) cũng tính vào
RAM. Các dịch vụ nền đo được ~0,9 GB khi rảnh (LiteLLM ~600 MB, SearXNG ~110 MB, gateway ~75 MB, web ~40 MB,
Caddy ~15 MB); tính 1,5 GB cho có dư, cộng hệ điều hành ~0,5 GB. Mỗi lượt
chat chủ yếu chờ model, nên CPU ít khi là nút thắt. Ước lượng **~150 MB cho mỗi sandbox đang thức**; sandbox rảnh quá
`SANDBOX_IDLE_SECONDS` thì bị tắt (dữ liệu vẫn còn).

| Số học viên pilot | VM gợi ý | Trong `infra/.env.prod` |
|---|---|---|
| tới ~15 | 2 vCPU, 4 GB RAM, 40 GB SSD | `SANDBOX_IDLE_SECONDS=300`, `SANDBOX_PREWARM=0` |
| 15-40 | 4 vCPU, 8 GB RAM, 60 GB SSD | mặc định (`600`, `1`) |
| 40-100 | 8 vCPU, 16 GB RAM, 100 GB SSD | mặc định, **và** nới giới hạn mạng bên dưới |

**Giới hạn mạng Docker.** Mỗi sandbox đang thức có một mạng nội bộ riêng (cách ly học viên với nhau). Mặc định
Docker chỉ cấp được khoảng 30 mạng, tức khoảng 29 sandbox thức cùng lúc; sandbox thứ 30 sẽ không khởi động được.
Muốn nhiều hơn (và để log của các sandbox cũng được xoay vòng), tạo `/etc/docker/daemon.json` **trước lần deploy đầu**:

```json
{
  "default-address-pools": [{"base": "10.201.0.0/16", "size": 24}],
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
```

rồi `sudo systemctl restart docker`. Kết quả: 256 mạng. Chọn dải `base` không trùng mạng VPC của VM (xem `ip -4 addr`).
Nếu stack đã chạy rồi: `bash infra/deploy.sh down`, sửa file, restart docker, `bash infra/deploy.sh`.

### 3. Tạo VM, mở tường lửa, cài Docker

Trong security group / firewall của cloud chỉ mở **22, 80, 443** (TCP; thêm 443/UDP nếu muốn HTTP/3). Trên VM:

```bash
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine + plugin compose
sudo usermod -aG docker $USER                         # rồi thoát SSH và đăng nhập lại
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable
```

(Cổng do Docker publish đi vòng qua ufw; ở đây chỉ Caddy publish 80/443 nên không sao, nhưng security group của cloud
mới là lớp chặn chính.)

### 4. DNS

Tên miền riêng: tạo bản ghi **A** `mentor.example.vn -> <IP VM>`, đợi vài phút, kiểm tra từ PowerShell:
`Resolve-DnsName mentor.example.vn`. Dùng sslip.io thì bỏ qua bước này. DNS phải đúng **trước** khi chạy deploy,
vì Caddy xin chứng chỉ ngay lúc khởi động (Let's Encrypt giới hạn số lần thử sai; volume `caddy_data` giữ chứng chỉ,
đừng xoá nó).

### 5. Chép mã nguồn lên VM (từ Windows PowerShell)

Windows 10/11 có sẵn `tar`, `ssh`, `scp`. Từ thư mục chứa `mentor` (không mang theo dữ liệu dev, file bí mật và app desktop, server không cần):

```powershell
cd "<thư mục chứa mentor>"
tar -czf mentor.tgz --exclude=.venv --exclude=node_modules --exclude=.next --exclude=target `
  --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache `
  --exclude=mentor/var --exclude="mentor/var-*" --exclude=mentor/apps/desktop `
  --exclude=.env --exclude=".env.*.local" --exclude=.env.prod mentor
scp mentor.tgz ubuntu@203.0.113.5:~/
ssh ubuntu@203.0.113.5 "tar -xzf mentor.tgz && rm mentor.tgz"
```

(`ubuntu@203.0.113.5` = user và IP của VM.) Có WSL thì `rsync -az --exclude ...` cũng được. Nếu sau này mã nguồn nằm
trong một git repo riêng tư, `git clone` trên VM thì `deploy.sh update` sẽ tự `git pull`.

### 6. Cấu hình và chạy lần đầu (trên VM)

```bash
ssh ubuntu@203.0.113.5
cd ~/mentor
bash infra/deploy.sh          # lần đầu: tạo infra/.env.prod, sinh khoá, rồi báo các biến còn thiếu
nano infra/.env.prod          # điền DOMAIN, FPT_API_BASE/KEY, SMTP_USERNAME/PASSWORD, MAIL_FROM, ZALO_*
bash infra/deploy.sh          # kiểm tra biến -> build image -> chạy -> chờ healthy -> in URL
```

Lần build đầu mất khoảng 5-15 phút. `deploy.sh` từ chối chạy khi thiếu biến bắt buộc, tự đăng ký webhook Zalo
`https://<DOMAIN>/webhooks/zalo` nếu có `ZALO_BOT_TOKEN`, và cuối cùng in `Xong. Mở: https://<DOMAIN>`.

**Ngay sau đó**: chép `MENTOR_MASTER_KEY` (`grep MENTOR_MASTER_KEY infra/.env.prod`) vào trình quản lý mật khẩu, ngoài
VM. Mất khoá này thì mọi bản sao lưu và các trường đã mã hoá đều không đọc được.

### 7. Đăng nhập lần đầu

Không có vai trò admin riêng: người vận hành đăng nhập như một học viên. Mở `https://<DOMAIN>`, nhập email -> thư
"Đăng nhập AI mentor" tới từ Gmail (xem cả mục Spam) chứa liên kết và mã 6 số (mã dùng cho ứng dụng desktop). Thử với hồ
sơ **NCS** trước (THPT cần phụ huynh liên kết Zalo). Không nhận được thư: `bash infra/deploy.sh logs gateway`, tìm
`login email to ... failed` (ví dụ `SMTPAuthenticationError` = sai app password).

### 8. Vận hành hằng ngày

```bash
bash infra/deploy.sh status               # trạng thái + health từng dịch vụ
bash infra/deploy.sh logs gateway         # log (caddy, gateway, model-router, web, searxng); Ctrl+C để thoát
docker ps --filter label=mentor.sandbox=1 # sandbox đang thức
docker stats --no-stream                  # RAM/CPU từng container
bash infra/deploy.sh update               # sau khi chép mã mới lên (mục 5): build lại + chạy lại, dữ liệu giữ nguyên;
                                          # tự chép AGENTS.md/skills mới vào workspace học viên cũ (không đụng file của họ)
bash infra/deploy.sh content              # chỉ bước chép AGENTS.md/skills đó
bash infra/deploy.sh down                 # dừng tất cả (dữ liệu, chứng chỉ vẫn còn)
```

Dữ liệu nằm ở `/srv/mentor/data` (ops.db, mirror git và bản làm việc của từng học viên; **chưa mã hoá**, nên dùng ổ
đĩa có mã hoá của nhà cung cấp cloud). Log container được xoay vòng (10 MB x 5).

**Sao lưu.** Gateway tự tạo bản sao lưu **đã mã hoá** mỗi ngày lúc 02:00 giờ Việt Nam vào `/srv/mentor/backups`
(`users/<uid>/*.mbk` cho từng học viên, `ops/*.mbk` cho ops.db). Bản sao trên cùng VM không cứu được khi mất VM, nên
chép ra ngoài định kỳ:

```bash
bash infra/deploy.sh backup     # trên VM: sao lưu ngay + đóng gói ~/mentor-backups-<thời điểm>.tgz
```

```powershell
scp ubuntu@203.0.113.5:~/mentor-backups-*.tgz .     # trên Windows
```

Khôi phục: infra/README.md, "Encryption at rest and backups" (`backup-restore`, chạy trong container:
`docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec gateway python -m mentor_gateway.cli ...`).

### 9. Lưu ý trước khi cho người dùng thật vào

- **Học sinh THPT cần Zalo bot.** Ở prod không có nút "xác minh phụ huynh" của bản dev: tài khoản THPT bị khoá ở
  bước liên kết cho tới khi phụ huynh nhắn bot Zalo. Thiếu `ZALO_BOT_TOKEN` thì chỉ NCS dùng được.
- **Giới hạn gửi của Gmail**: khoảng 500 người nhận/ngày với Gmail thường (2000 với Google Workspace); vượt quá thì
  Gmail chặn gửi tới 24 giờ và không ai đăng nhập được. Mỗi yêu cầu đăng nhập là một thư (tối đa 5 lần/giờ/email). Pilot
  lớn hơn: đổi sang dịch vụ gửi thư chuyên dụng, cùng các biến `SMTP_*`.
- **Dữ liệu của trẻ vị thành niên đi tới nhà cung cấp model.** Tin nhắn, bài làm và hồ sơ của học viên được gửi tới
  model qua FPT; tên model có tiền tố `Alibaba:` (`services/model-router/config.yaml`), tức có thể đi qua hạ tầng bên
  thứ ba. Trước khi nhận học sinh THPT thật: kiểm tra điều khoản xử lý dữ liệu (lưu trữ, dùng để huấn luyện, chuyển dữ
  liệu ra nước ngoài), đối chiếu với quy định bảo vệ dữ liệu cá nhân của Việt Nam (Nghị định 13/2023/NĐ-CP và luật
  hiện hành), và có đồng ý của phụ huynh. Tavily (nếu bật) gửi truy vấn tìm kiếm sang Mỹ.
- **Điền `SIGNUP_ALLOWLIST`** (email hoặc `@tên-miền` được mời, cách nhau bằng dấu phẩy). Để trống thì ai biết URL
  cũng tự đăng ký được, và mỗi tài khoản tiêu quota model.
- **Gateway giữ Docker socket** để chạy sandbox: chiếm được gateway là chiếm được root của VM. Gateway chạy user 4242,
  root fs chỉ đọc, bỏ mọi capability, chỉ `/api` và `/webhooks` lộ ra internet; vẫn nên dùng VM riêng cho pilot.

### 10. Chuyển tiếp email của học viên (Cloudflare Email Routing)

Mỗi học viên có một địa chỉ riêng `<mã>@<INBOUND_EMAIL_DOMAIN>` (web app: **Cài đặt -> Email chuyển tiếp**). Thư gửi
tới đó được lưu vào `inbox/email/` trong workspace (kèm tệp đính kèm), rồi mentor đọc thư và ghi lại các hạn chót. VM
**không** mở cổng 25: Cloudflare nhận thư, một Email Worker ký thư bằng HMAC-SHA256 rồi gửi nguyên văn qua HTTPS:

```
người gửi -> MX Cloudflare -> Email Routing (catch-all) -> Email Worker -> https://<DOMAIN>/webhooks/email/inbound
          -> Caddy -> gateway -> inbox/email/<ngày>-<tiêu đề>.md + tệp đính kèm + một việc "intake" cho mentor
```

File liên quan: `infra/cloudflare/email-worker.js` (Worker, không cần thư viện), `infra/cloudflare/wrangler.toml`
(tuỳ chọn), các biến `INBOUND_EMAIL_DOMAIN`, `EMAIL_WEBHOOK_SECRET` trong `infra/.env.prod`.

**Chọn tên miền nhận thư (đọc trước).**

- Tên miền phải dùng **DNS của Cloudflare** (nameserver trỏ về Cloudflare; gói Free là đủ). `sslip.io` không dùng
  được. Tên miền của web app (`DOMAIN`) thì không bắt buộc nằm trên Cloudflare.
- Cloudflare chỉ cho quy tắc **catch-all** (mọi `*@tên-miền` -> Worker) trên **tên miền gốc (apex)**, không cho
  subdomain ("Catch-all entries support apex domains only"). Vì mã của học viên là ngẫu nhiên, cần catch-all, nên:
  - **Khuyến nghị:** một tên miền riêng chỉ để nhận thư, ví dụ `mentor-inbox.vn`, thêm vào Cloudflare, rồi
    `INBOUND_EMAIL_DOMAIN=mentor-inbox.vn`.
  - Dùng tên miền gốc đang có (ví dụ `example.vn`) chỉ khi nó **chưa nhận thư ở nơi khác**: bật Email Routing sẽ thêm
    bản ghi MX của Cloudflare cho tên miền gốc. Nếu `example.vn` đang dùng Google Workspace / Microsoft 365, đừng làm
    vậy (thư của mọi người sẽ đi sai chỗ).
  - Subdomain (`inbox.example.vn`) chỉ chạy được nếu tạo **một quy tắc riêng cho từng học viên** (tối đa 200 quy tắc mỗi
    tên miền), làm tay mỗi khi có học viên mới: chỉ hợp với pilot rất nhỏ.

**Bước 1. Gateway (trên VM).** Chép mã mới lên (mục 5), rồi:

```bash
nano infra/.env.prod          # INBOUND_EMAIL_DOMAIN=mentor-inbox.vn  (EMAIL_WEBHOOK_SECRET để trống: tự sinh)
bash infra/deploy.sh update   # sinh EMAIL_WEBHOOK_SECRET, build lại, khởi động lại gateway
bash infra/deploy.sh email    # in URL webhook + secret cho Worker, và kiểm tra webhook trả 401 khi không có chữ ký
```

Địa chỉ của học viên đã có tài khoản tự đổi theo tên miền mới (phần mã giữ nguyên). Chép secret in ra để dùng ở bước
3, đừng dán nó vào chat hay email; chạy `clear` sau khi chép.

**Bước 2. Bật Email Routing (dashboard Cloudflare, trình duyệt).**

1. https://dash.cloudflare.com -> chọn tài khoản -> **Compute -> Email Service -> Email Routing** (giao diện cũ: chọn
   tên miền -> **Email -> Email Routing**; tên menu có thể đổi theo thời gian).
2. **Onboard Domain** -> chọn tên miền nhận thư -> xem danh sách bản ghi Cloudflare sẽ thêm: **MX** (thư đến
   Cloudflare), **TXT** SPF và **TXT** DKIM -> đồng ý thêm -> **Done**. Nếu Cloudflare báo có bản ghi MX cũ xung đột,
   dừng lại và xem lại mục "Chọn tên miền" ở trên.
3. Kiểm tra từ PowerShell trên máy bạn (sau vài phút):

   ```powershell
   Resolve-DnsName mentor-inbox.vn -Type MX      # các máy chủ phải kết thúc bằng mx.cloudflare.net
   ```

**Bước 3. Tạo Email Worker.** Chọn một trong hai cách.

Cách A, chỉ dùng dashboard:

1. **Compute -> Workers & Pages -> Create -> Create Worker** (mẫu "Hello World"), đặt tên `mentor-email-inbound` ->
   **Deploy**.
2. **Edit code**: xoá hết mã mẫu, dán toàn bộ `infra/cloudflare/email-worker.js` -> **Deploy**. Để chép file trên Windows:

   ```powershell
   Get-Content "<thư mục mentor>\infra\cloudflare\email-worker.js" -Raw -Encoding UTF8 | Set-Clipboard
   ```

3. Worker -> **Settings -> Variables and Secrets -> Add**:
   - Type **Text**: `MENTOR_WEBHOOK_URL` = `https://<DOMAIN>/webhooks/email/inbound` (đúng dòng `bash infra/deploy.sh email` in ra);
   - Type **Secret**: `EMAIL_WEBHOOK_SECRET` = secret ở bước 1;
   - **Deploy** (hoặc Save).
4. Worker -> **Settings -> Observability**: bật **Workers Logs** để xem log ở bước 5.

Cách B, Wrangler (cần Node.js trên máy Windows):

```powershell
cd "<thư mục mentor>\infra\cloudflare"
notepad wrangler.toml                            # sửa MENTOR_WEBHOOK_URL thành https://<DOMAIN>/webhooks/email/inbound
npx wrangler login                               # mở trình duyệt để đăng nhập Cloudflare
npx wrangler deploy
npx wrangler secret put EMAIL_WEBHOOK_SECRET     # dán secret khi được hỏi (không lưu vào file nào)
```

(Với Wrangler 4.113.0 trở lên, bỏ dấu `#` ở dòng `addresses = ["*@..."]` trong `wrangler.toml` thì `wrangler deploy`
tự tạo luôn quy tắc catch-all ở bước 4.)

**Bước 4. Quy tắc catch-all -> Worker.** **Email Routing -> Routing rules -> Catch-all address** -> **Edit** ->
Action **Send to a Worker** -> Destination `mentor-email-inbound` -> **Save**, và bật để trạng thái là **Active**.
(Subdomain: thay vào đó **Create address** cho từng mã học viên, cùng action **Send to a Worker**.)

**Bước 5. Thử.**

1. Đăng nhập web app bằng một tài khoản NCS -> **Cài đặt -> Email chuyển tiếp** -> **Sao chép** địa chỉ.
2. Từ Gmail cá nhân, gửi tới địa chỉ đó một thư có tiêu đề như "Hạn nộp báo cáo 15/11" và một tệp PDF nhỏ.
3. Trong vòng một phút: web app -> **Workspace -> inbox/email/** có file `.md` (đầu file là cảnh báo "NỘI DUNG KHÔNG
   TIN CẬY") và tệp PDF; mentor nhận một việc đọc thư và ghi hạn chót.
4. Log gateway trên VM: `bash infra/deploy.sh logs gateway`, tìm `email webhook: rcpt abc…, 12345 bytes, stored`
   (chỉ có 3 ký tự đầu của mã và kích thước, không có địa chỉ hay nội dung).
5. Log Worker: dashboard -> Worker -> **Logs**: `{"event":"delivered","status":202,...}`. Email Routing -> trang tổng
   quan cũng có nhật ký từng thư.

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| Worker log `gateway_error`, `status: 404` | gateway chưa có `EMAIL_WEBHOOK_SECRET` (chưa `deploy.sh update`), hoặc URL sai |
| `status: 401` | secret trên Worker khác `infra/.env.prod`, hoặc đồng hồ VM lệch quá 5 phút (`timedatectl`) |
| `status: 429` | quá `EMAIL_WEBHOOK_PER_RCPT_PER_HOUR` (mặc định 30) thư/giờ cho một địa chỉ; máy chủ người gửi sẽ gửi lại sau |
| Log gateway `dropped (no learner with this address)` | sai mã, hoặc tên miền nhận thư khác `INBOUND_EMAIL_DOMAIN` |
| Người gửi nhận thư báo lỗi "Message too large" | thư (kể cả đính kèm) trên 25 MB |
| Worker log `EXCEEDED_CPU` | thư lớn trên gói Workers Free (xem chi phí bên dưới) |

Khi gateway lỗi tạm thời (429, 401/404 do cấu hình, 5xx, mất kết nối), Worker **ném lỗi** thay vì trả thư lại, để máy
chủ người gửi thử lại sau (thường trong nhiều giờ), cho bạn thời gian sửa. Tài liệu Cloudflare không ghi rõ lỗi này
được báo cho người gửi là tạm thời hay vĩnh viễn; nếu là vĩnh viễn, người gửi nhận thư báo lỗi, không có thư nào mất
lặng lẽ. Chỉ thư quá lớn (413) và địa chỉ sai dạng (400) bị trả lại ngay bằng `setReject`.

**Chi phí và giới hạn** (theo tài liệu Cloudflare, kiểm tra ngày 2026-11-03; xem lại trước khi dùng):

- Email Routing dùng được trên gói Free và trả phí; tối đa **25 MiB** mỗi thư (kể cả đính kèm), lớn hơn bị từ chối;
  200 quy tắc mỗi tên miền.
- Workers Free: 100.000 lượt gọi/ngày, 10 ms CPU mỗi lượt, 128 MB bộ nhớ. Worker phải tính HMAC trên toàn bộ thư, nên thư
  vài MB trở lên có thể vượt 10 ms (lỗi `EXCEEDED_CPU`, thư không được xử lý); Cloudflare khuyên dùng Workers Paid
  cho trường hợp này. Workers Paid: từ 5 USD/tháng mỗi tài khoản, gồm 10 triệu lượt gọi và 30 triệu ms CPU mỗi tháng.
- Gateway không tốn thêm gì: cùng cổng 443 qua Caddy.

**Spam, lạm dụng, quyền riêng tư.**

- **Địa chỉ chính là chìa khoá**: ai biết địa chỉ đều gửi được, và mỗi thư tạo một việc cho mentor (tiêu quota model).
  Dặn học viên chỉ dán địa chỉ vào bộ lọc chuyển tiếp của Gmail/Outlook, không đăng công khai. Hiện chưa có nút đổi mã
  địa chỉ; nếu một địa chỉ bị spam, tạo trong Email Routing một quy tắc **Drop** cho đúng địa chỉ đó (quy tắc cụ thể
  được dùng trước catch-all), hoặc giảm `EMAIL_WEBHOOK_PER_RCPT_PER_HOUR`.
- Mỗi địa chỉ tối đa 30 thư/giờ (mặc định); thư vượt mức nhận lỗi tạm thời.
- Thư tới địa chỉ không tồn tại được nhận rồi bỏ đi, không trả lại: người ngoài không dò được địa chỉ nào có thật, và
  không sinh thư báo lỗi gửi ngược cho địa chỉ giả mạo.
- Nội dung thư luôn được đánh dấu là dữ liệu không tin cậy (mentor không làm theo chỉ dẫn trong thư); tệp đính kèm chỉ
  được lưu, không được chạy. Worker không lọc theo SPF/DKIM/DMARC, vì thư chuyển tiếp tự động đôi khi không qua được
  các kiểm tra này.
- Thư đi qua Cloudflare (công ty Mỹ) trước khi tới VM. Với học sinh THPT, cân nhắc như mục 9 (dữ liệu cá nhân).
- Đổi secret: xoá dòng `EMAIL_WEBHOOK_SECRET=` trong `infra/.env.prod`, `bash infra/deploy.sh update` (sinh secret
  mới), rồi cập nhật secret trên Worker. Thư tới trong lúc hai bên chưa khớp nhận lỗi tạm thời và được gửi lại sau.
