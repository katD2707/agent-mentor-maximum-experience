#!/usr/bin/env bash
# Local demo of Mentor on one Linux machine with Docker (README "Chạy thử trên máy").
#
#   bash infra/demo.sh            first run: create infra/.env.demo, then build and start; later runs: start/update
#   bash infra/demo.sh accounts   create two demo learners (THPT + NCS, synthetic data) and print their login links
#   bash infra/demo.sh login EMAIL   print a fresh login link + code for EMAIL
#   bash infra/demo.sh logs [svc]    follow logs (gateway, web, model-router, searxng)
#   bash infra/demo.sh stop          stop everything (data stays in the mentor_demo_data volume)
#   bash infra/demo.sh reset         stop and DELETE all demo data
#
# Needs: Docker Engine with the compose plugin. Only FPT_API_BASE and FPT_API_KEY are required (infra/.env.demo).
set -euo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$INFRA/.env.demo"
COMPOSE=(docker compose -f "$INFRA/docker-compose.demo.yml" --env-file "$ENV_FILE")

info() { printf '\n==> %s\n' "$*"; }
die() { printf 'LỖI: %s\n' "$*" >&2; exit 1; }
env_get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }
env_set() {  # KEY VALUE (generated values only: [A-Za-z0-9])
    if grep -qE "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"; fi
}
rand_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
web_port() { local p; p="$(env_get WEB_PORT)"; echo "${p:-3000}"; }
api_port() { local p; p="$(env_get API_PORT)"; echo "${p:-8000}"; }

check_docker() {
    command -v docker >/dev/null || die "chưa có Docker. Cài: https://docs.docker.com/engine/install/"
    docker info >/dev/null 2>&1 || die "không gọi được Docker (dịch vụ chưa chạy, hoặc user chưa thuộc nhóm docker: sudo usermod -aG docker \$USER rồi đăng nhập lại)."
    docker compose version >/dev/null 2>&1 || die "thiếu docker compose (gói docker-compose-plugin)."
}

ensure_env() {
    if [ ! -f "$ENV_FILE" ]; then
        cp "$INFRA/.env.demo.example" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        info "Đã tạo $ENV_FILE"
    fi
    [ -n "$(env_get MODEL_ROUTER_MASTER_KEY)" ] || env_set MODEL_ROUTER_MASTER_KEY "sk-$(rand_hex 24)"
    [ -n "$(env_get SEARXNG_SECRET)" ] || env_set SEARXNG_SECRET "$(rand_hex 32)"
    if [ -z "$(env_get FPT_API_BASE)" ] || [ -z "$(env_get FPT_API_KEY)" ]; then
        printf '\nĐiền FPT_API_BASE và FPT_API_KEY vào %s, rồi chạy lại: bash infra/demo.sh\n' "$ENV_FILE"
        exit 1
    fi
}

wait_up() {
    info "Chờ gateway và web sẵn sàng (lần đầu build có thể mất 5-15 phút)"
    local api web i
    api="http://127.0.0.1:$(api_port)/healthz"
    web="http://127.0.0.1:$(web_port)/login"
    for i in $(seq 1 90); do
        if curl -fs -o /dev/null "$api" 2>/dev/null && curl -fs -o /dev/null "$web" 2>/dev/null; then return 0; fi
        sleep 2
    done
    die "chưa lên sau 3 phút. Xem log: bash infra/demo.sh logs gateway"
}

login_link() {  # EMAIL -> prints link + code (dev mode returns them instead of sending an email)
    local out
    out="$(curl -fsS -X POST "http://127.0.0.1:$(api_port)/api/auth/request-link" \
        -H "Origin: http://localhost:$(web_port)" -H 'Content-Type: application/json' \
        --data "{\"email\":\"$1\"}")" || die "không tạo được link đăng nhập cho $1"
    printf '%s\n' "$out" | sed -n 's/.*"dev_link":"\([^"]*\)".*"dev_code":"\([^"]*\)".*/  link: \1\n  mã:   \2/p'
}

up() {
    check_docker; ensure_env
    info "Build và khởi động (gateway, web, model-router, searxng)"
    "${COMPOSE[@]}" up -d --build
    wait_up
    cat <<EOF

Xong. Mở http://localhost:$(web_port) trên máy này.
  - Đăng nhập bằng email bất kỳ: link và mã 6 số hiện ngay trên trang (không gửi email).
  - Học sinh THPT: ở bước liên kết phụ huynh, bấm nút xác minh thử (chế độ dev).
  - Tài khoản mẫu có sẵn dữ liệu: bash infra/demo.sh accounts
EOF
}

case "${1:-up}" in
    up|start|update) up ;;
    accounts)
        check_docker
        info "Tạo 2 tài khoản mẫu (dữ liệu giả lập, không chat với model)"
        "${COMPOSE[@]}" exec -T gateway python infra/seed-demo.py --base http://127.0.0.1:8000 \
            --web-origin "http://localhost:$(web_port)" --no-chat
        info "Đăng nhập"
        for e in demo.thpt@example.com demo.ncs@example.com; do echo "$e"; login_link "$e"; done ;;
    login) [ -n "${2:-}" ] || die "dùng: bash infra/demo.sh login EMAIL"; login_link "$2" ;;
    logs) shift; "${COMPOSE[@]}" logs -f --tail=200 "$@" ;;
    stop|down) "${COMPOSE[@]}" down ;;
    reset)
        read -r -p "Xoá TOÀN BỘ dữ liệu demo (tài khoản, trí nhớ, lịch sử)? Gõ XOA để xác nhận: " ans
        [ "$ans" = XOA ] || { echo "Đã huỷ."; exit 0; }
        "${COMPOSE[@]}" down -v ;;
    *) sed -n '2,10p' "$0"; exit 1 ;;
esac
