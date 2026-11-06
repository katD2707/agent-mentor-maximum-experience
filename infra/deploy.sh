#!/usr/bin/env bash
# Pilot deployment on one Linux VM with Docker (README "Triển khai lên server (pilot)").
#
#   bash infra/deploy.sh            first deploy / re-deploy: check env, build images, start, wait for health
#   bash infra/deploy.sh update     git pull (if this is a git checkout; otherwise rsync the code first), rebuild, up
#   bash infra/deploy.sh backup     take an encrypted snapshot now, list snapshots, show how to copy them off the VM
#   bash infra/deploy.sh logs [svc] follow logs (svc: caddy, gateway, model-router, web, searxng)
#   bash infra/deploy.sh status     container and health status
#   bash infra/deploy.sh zalo       (re-)register the Zalo webhook https://$DOMAIN/webhooks/zalo
#   bash infra/deploy.sh content    copy the current AGENTS.md/skills into existing learners' workspaces (deploy/update do it)
#   bash infra/deploy.sh email      values for the Cloudflare Email Worker (URL, secret) + check the webhook answers
#   bash infra/deploy.sh down       stop everything (data and certificates stay)
#
# Settings: infra/.env.prod (created from infra/.env.prod.example on the first run; ENV_FILE=... overrides).
set -euo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$INFRA")"
ENV_FILE="${ENV_FILE:-$INFRA/.env.prod}"
EXAMPLE="$INFRA/.env.prod.example"
COMPOSE=(docker compose -f "$INFRA/docker-compose.prod.yml" --env-file "$ENV_FILE")
SERVICES=(caddy gateway model-router web searxng)
REQUIRED=(DOMAIN FPT_API_BASE FPT_API_KEY SMTP_HOST SMTP_USERNAME SMTP_PASSWORD MAIL_FROM
          MENTOR_MASTER_KEY MODEL_ROUTER_MASTER_KEY SEARXNG_SECRET ZALO_WEBHOOK_SECRET DOCKER_GID)

info() { printf '\n==> %s\n' "$*"; }
warn() { printf 'CẢNH BÁO: %s\n' "$*" >&2; }
die() { printf 'LỖI: %s\n' "$*" >&2; exit 1; }

as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# ---- env file -----------------------------------------------------------------------------------------------------

env_get() {  # value of KEY in the env file, surrounding quotes removed ("" when unset)
    local v
    v="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    printf '%s' "$v"
}

env_set() {  # KEY VALUE (values written here are generated: [A-Za-z0-9_=-] only)
    if grep -qE "^$1=" "$ENV_FILE"; then
        sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
    fi
}

rand_b64_32() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'; }
rand_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
b64url() { base64 | tr '+/' '-_' | tr -d '=\n'; }

gen_vapid() {  # Web Push key pair (P-256): raw private scalar + uncompressed public point, base64url, once
    command -v openssl >/dev/null 2>&1 || { warn "không có openssl: bỏ qua tạo khoá Web Push (VAPID_*), thông báo đẩy tắt."; return 0; }
    local pem priv pub
    pem="$(openssl ecparam -name prime256v1 -genkey -noout 2>/dev/null)"
    priv="$(printf '%s\n' "$pem" | openssl ec -outform DER 2>/dev/null | tail -c +8 | head -c 32 | b64url)"
    pub="$(printf '%s\n' "$pem" | openssl ec -pubout -outform DER 2>/dev/null | tail -c 65 | b64url)"
    if [ "${#priv}" -ne 43 ] || [ "${#pub}" -ne 87 ]; then warn "tạo khoá VAPID thất bại; thông báo đẩy tắt."; return 0; fi
    env_set VAPID_PUBLIC_KEY "$pub"
    env_set VAPID_PRIVATE_KEY "$priv"
}

check_docker() {
    command -v docker >/dev/null 2>&1 || die "chưa cài Docker (https://docs.docker.com/engine/install/)."
    docker info >/dev/null 2>&1 || die "không gọi được Docker daemon. Chạy bằng sudo, hoặc: sudo usermod -aG docker \$USER rồi đăng nhập lại."
    docker compose version >/dev/null 2>&1 || die "thiếu plugin docker compose (gói docker-compose-plugin)."
}

ensure_env() {
    if [ ! -f "$ENV_FILE" ]; then
        cp "$EXAMPLE" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        info "Đã tạo $ENV_FILE từ mẫu."
    fi
    # random secrets, generated once (never overwritten: a new MENTOR_MASTER_KEY would make all data unreadable)
    [ -n "$(env_get MENTOR_MASTER_KEY)" ] || { env_set MENTOR_MASTER_KEY "$(rand_b64_32)"; warn "đã tạo MENTOR_MASTER_KEY mới trong $ENV_FILE: chép nó ra ngoài VM (trình quản lý mật khẩu). Mất khoá = mất toàn bộ bản sao lưu."; }
    [ -n "$(env_get MODEL_ROUTER_MASTER_KEY)" ] || env_set MODEL_ROUTER_MASTER_KEY "sk-$(rand_hex 24)"
    [ -n "$(env_get SEARXNG_SECRET)" ] || env_set SEARXNG_SECRET "$(rand_hex 32)"
    [ -n "$(env_get ZALO_WEBHOOK_SECRET)" ] || env_set ZALO_WEBHOOK_SECRET "$(rand_hex 24)"
    [ -n "$(env_get EMAIL_WEBHOOK_SECRET)" ] || env_set EMAIL_WEBHOOK_SECRET "$(rand_hex 32)"
    # Web Push: generated once, never replaced (browsers subscribed with the old public key would stop getting pushes)
    [ -n "$(env_get VAPID_PRIVATE_KEY)" ] || gen_vapid
    [ -n "$(env_get VAPID_SUBJECT)" ] || [ -z "$(env_get DOMAIN)" ] || env_set VAPID_SUBJECT "https://$(env_get DOMAIN)"
    if [ -S /var/run/docker.sock ] && [ "$(uname -s)" = Linux ]; then
        env_set DOCKER_GID "$(stat -c %g /var/run/docker.sock)"
    fi

    local missing=() k
    for k in "${REQUIRED[@]}"; do [ -n "$(env_get "$k")" ] || missing+=("$k"); done
    if [ "${#missing[@]}" -gt 0 ]; then
        die "còn thiếu trong $ENV_FILE: ${missing[*]}
       Mở file (nano $ENV_FILE), điền các dòng trên (xem chú thích trong file), rồi chạy lại."
    fi

    local domain key_len
    domain="$(env_get DOMAIN)"
    case "$domain" in
        http://*|https://*|*/*) die "DOMAIN chỉ là tên miền, không có https:// hay dấu / (ví dụ 203-0-113-5.sslip.io).";;
    esac
    key_len="$(env_get MENTOR_MASTER_KEY | tr '_-' '/+' | base64 -d 2>/dev/null | wc -c)"
    [ "$key_len" -eq 32 ] || die "MENTOR_MASTER_KEY phải là base64 (urlsafe) của đúng 32 byte."
    if [ -z "$(env_get ZALO_BOT_TOKEN)" ]; then
        warn "ZALO_BOT_TOKEN trống: tài khoản THPT sẽ kẹt ở bước liên kết phụ huynh (prod không có nút xác minh dev)."
    fi
    if [ -z "$(env_get INBOUND_EMAIL_DOMAIN)" ]; then
        warn "INBOUND_EMAIL_DOMAIN trống: địa chỉ email chuyển tiếp của học viên sẽ là @inbox.mentor.local và không nhận được thư (README: \"Chuyển tiếp email của học viên\")."
    fi
    if [ "$(env_get SMTP_HOST)" = smtp.gmail.com ] && ! env_get MAIL_FROM | grep -qiF "$(env_get SMTP_USERNAME)"; then
        warn "MAIL_FROM không chứa SMTP_USERNAME: Gmail sẽ thay người gửi bằng địa chỉ tài khoản."
    fi
    chmod 600 "$ENV_FILE" 2>/dev/null || true
}

public_url() {
    local u
    u="$(env_get PUBLIC_URL)"
    [ -n "$u" ] || u="https://$(env_get DOMAIN)"
    printf '%s' "${u%/}"
}

prepare_dirs() {
    [ "$(uname -s)" = Linux ] || return 0
    local data backup d
    data="$(env_get DATA_DIR)"; backup="$(env_get BACKUP_DIR)"
    for d in "${data:-/srv/mentor/data}" "${backup:-/srv/mentor/backups}"; do
        case "$d" in /*) ;; *) die "DATA_DIR/BACKUP_DIR phải là đường dẫn tuyệt đối: $d";; esac
        as_root mkdir -p "$d"
        as_root chown 4242:4242 "$d"   # the gateway (and sandboxes) run as uid 4242
        as_root chmod 700 "$d"
    done
}

# ---- build / start ------------------------------------------------------------------------------------------------

build() {
    local sandbox_image
    sandbox_image="$(env_get SANDBOX_IMAGE)"
    info "Build sandbox image ${sandbox_image:=mentor-sandbox:prod}"
    docker build -f "$ROOT/sandbox-image/Dockerfile" -t "$sandbox_image" "$ROOT"
    info "Pull caddy, model-router, searxng"
    "${COMPOSE[@]}" pull caddy model-router searxng
    info "Build gateway + web (web bakes in $(public_url)/api)"
    "${COMPOSE[@]}" build gateway web
}

up() {
    info "Start"
    "${COMPOSE[@]}" up -d --remove-orphans
}

wait_healthy() {
    info "Chờ các dịch vụ healthy (tối đa 5 phút)"
    local deadline=$(( $(date +%s) + 300 )) svc id st pending
    while :; do
        pending=()
        for svc in "${SERVICES[@]}"; do
            id="$("${COMPOSE[@]}" ps -q "$svc" 2>/dev/null || true)"
            st="$( [ -n "$id" ] && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || echo missing)"
            [ "$st" = healthy ] || pending+=("$svc:$st")
        done
        [ "${#pending[@]}" -eq 0 ] && break
        if [ "$(date +%s)" -ge "$deadline" ]; then
            "${COMPOSE[@]}" ps
            die "chưa healthy: ${pending[*]}. Xem log: bash infra/deploy.sh logs <dịch vụ>"
        fi
        sleep 5
    done
    local url curl_opts=(-fsS -o /dev/null --max-time 10)
    url="$(public_url)"
    case "$(env_get DOMAIN)" in localhost|*.localhost) curl_opts+=(-k);; esac   # Caddy internal CA
    info "Kiểm tra $url qua HTTPS (lần đầu Caddy xin chứng chỉ Let's Encrypt, có thể mất 1 phút)"
    deadline=$(( $(date +%s) + 120 ))
    until curl "${curl_opts[@]}" "$url/login"; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
            "${COMPOSE[@]}" logs --tail=30 caddy
            die "không mở được $url. Kiểm tra: DNS của DOMAIN trỏ đúng IP VM, tường lửa/security group mở 80 và 443."
        fi
        sleep 5
    done
    local code   # an empty body must get the gateway's 422: proves /api is routed to the gateway
    code="$(curl -s "${curl_opts[@]:1}" -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' \
        "$url/api/auth/verify-code" || true)"
    [ "$code" = 422 ] || warn "$url/api/auth/verify-code trả về HTTP $code (mong đợi 422): /api có tới được gateway không?"
    email_check "${curl_opts[@]:1}"
}

email_check() {  # an unsigned POST must get the gateway's 401: the email webhook is routed and has its secret
    [ -n "$(env_get EMAIL_WEBHOOK_SECRET)" ] || return 0
    local code
    code="$(curl -s "$@" -w '%{http_code}' -X POST --data-binary 'x' "$(public_url)/webhooks/email/inbound" || true)"
    [ "$code" = 401 ] || warn "$(public_url)/webhooks/email/inbound trả về HTTP $code (mong đợi 401): webhook email chưa sẵn sàng (404 = gateway chưa có EMAIL_WEBHOOK_SECRET)."
}

zalo_webhook() {
    if [ -z "$(env_get ZALO_BOT_TOKEN)" ]; then
        warn "bỏ qua đăng ký webhook Zalo (ZALO_BOT_TOKEN trống)."
        return 0
    fi
    info "Đăng ký webhook Zalo $(public_url)/webhooks/zalo"
    "${COMPOSE[@]}" exec -T gateway python -m mentor_gateway.cli zalo-set-webhook --url "$(public_url)/webhooks/zalo" \
        || warn "đăng ký webhook Zalo thất bại; thử lại: bash infra/deploy.sh zalo"
}

refresh_content() {  # existing learners get the AGENTS.md/skills/curricula baked into the new gateway image
    info "Cập nhật nội dung nền tảng (AGENTS.md, skills) cho học viên hiện có"
    "${COMPOSE[@]}" exec -T gateway python -m mentor_gateway.cli refresh-content \
        || warn "cập nhật nội dung lỗi ở một số học viên (xem dòng ERROR ở trên); chạy lại: bash infra/deploy.sh content"
}

email_info() {
    local curl_opts=(-sS -o /dev/null --max-time 10)
    case "$(env_get DOMAIN)" in localhost|*.localhost) curl_opts+=(-k);; esac
    info "Giá trị cho Cloudflare Email Worker (README: \"Chuyển tiếp email của học viên\")"
    echo "    INBOUND_EMAIL_DOMAIN (bật Email Routing cho tên miền này): $(env_get INBOUND_EMAIL_DOMAIN)"
    echo "    MENTOR_WEBHOOK_URL   (biến Text của Worker):              $(public_url)/webhooks/email/inbound"
    echo "    EMAIL_WEBHOOK_SECRET (biến Secret của Worker):            $(env_get EMAIL_WEBHOOK_SECRET)"
    echo "    (đừng dán secret vào chat/email; xoá màn hình sau khi chép: clear)"
    [ -n "$(env_get INBOUND_EMAIL_DOMAIN)" ] || warn "INBOUND_EMAIL_DOMAIN trống: điền vào $ENV_FILE rồi chạy bash infra/deploy.sh update."
    email_check "${curl_opts[@]}" && info "Kiểm tra webhook xong (không có cảnh báo ở trên = OK)."
}

done_banner() {
    info "Xong. Mở: $(public_url)"
    echo "    Log:        bash infra/deploy.sh logs gateway"
    echo "    Sao lưu:    bash infra/deploy.sh backup"
}

backup() {
    local dir
    dir="$(env_get BACKUP_DIR)"; dir="${dir:-/srv/mentor/backups}"
    info "Tạo bản sao lưu mã hoá ngay (bình thường tự chạy mỗi ngày lúc BACKUP_HOUR_UTC)"
    "${COMPOSE[@]}" exec -T gateway python -m mentor_gateway.cli backup-run
    "${COMPOSE[@]}" exec -T gateway python -m mentor_gateway.cli backup-list
    # the backup dir belongs to uid 4242 (mode 700): pack it into a file the login user can scp
    local archive
    archive="$HOME/mentor-backups-$(date -u +%Y%m%dT%H%M%SZ).tgz"
    as_root tar -C "$(dirname "$dir")" -czf "$archive" "$(basename "$dir")"
    as_root chown "$(id -u):$(id -g)" "$archive"
    cat <<EOF

Bản sao lưu (đã mã hoá, định dạng MBK1) nằm trên VM tại: $dir
  users/<uid>/<thời điểm>.mbk  (từng học viên)    ops/<id>.mbk  (cơ sở dữ liệu ops.db)
Đã đóng gói vào: $archive
Chép về máy Windows (PowerShell trên máy bạn), rồi xoá bản trên VM:
  scp <user>@<ip-VM>:$archive .
  ssh <user>@<ip-VM> rm $archive
Giải mã/khôi phục cần MENTOR_MASTER_KEY: giữ khoá ở nơi KHÁC với bản sao lưu.
EOF
}

update_code() {
    if [ -d "$ROOT/.git" ]; then
        info "git pull"
        git -C "$ROOT" pull --ff-only
    else
        info "Không phải git checkout: dùng mã nguồn hiện có (đã rsync/scp bản mới lên chưa?)"
    fi
}

cmd="${1:-deploy}"
[ $# -gt 0 ] && shift
case "$cmd" in
    deploy|up)
        check_docker; ensure_env; prepare_dirs; build; up; wait_healthy; refresh_content; zalo_webhook; done_banner;;
    update)
        check_docker; update_code; ensure_env; prepare_dirs; build; up; wait_healthy; refresh_content; zalo_webhook; done_banner;;
    check)
        check_docker; ensure_env; "${COMPOSE[@]}" config --quiet; info "OK: $ENV_FILE đủ biến, compose hợp lệ.";;
    backup) check_docker; backup;;
    logs) "${COMPOSE[@]}" logs -f --tail=200 "$@";;
    status) "${COMPOSE[@]}" ps;;
    zalo) zalo_webhook;;
    content) refresh_content;;
    email) email_info;;
    down)
        "${COMPOSE[@]}" down   # the gateway stops its sandboxes on shutdown
        docker network prune -f --filter label=mentor.sandbox=1 >/dev/null || true;;
    *) sed -n '2,13p' "$0"; exit 1;;
esac
