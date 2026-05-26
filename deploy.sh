#!/usr/bin/env bash
# =================================================================
#  deploy.sh — Crypto Trading Bot · Full deployment script
#  Server : 66.29.156.92
#  Ports  : Frontend → 3002 | Backend → 8000  (tránh anchoi.xxx)
#
#  Cách dùng (lần đầu):
#    git clone https://github.com/pattayakynu/crypto-trading-bot.git
#    cd crypto-trading-bot
#    bash deploy.sh
#
#  Cập nhật lần sau:
#    cd ~/crypto-trading-bot && bash deploy.sh
# =================================================================

set -euo pipefail

# ── Màu sắc ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# ── Cấu hình server ──────────────────────────────────────────────
SERVER_IP="66.29.156.92"
REPO_URL="https://github.com/pattayakynu/crypto-trading-bot.git"
APP_DIR="$HOME/crypto-trading-bot"
FRONTEND_PORT=3002
BACKEND_PORT=8000

# ── Helper functions ─────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ ✓ ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[ ! ]${NC}  $*"; }
die()     { echo -e "${RED}[ ✗ ]${NC}  $*"; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

# Nhập giá trị bình thường
ask() {
    local var=$1 label=$2 default=${3:-}
    local current; current=$(eval echo "\${$var:-$default}")
    printf "  ${YELLOW}→${NC} %-36s [%s]: " "$label" "$current"
    read -r val || true
    eval "$var='${val:-$current}'"
}

# Nhập giá trị ẩn (password / API key)
ask_secret() {
    local var=$1 label=$2
    local current; current=$(eval echo "\${$var:-}")
    if [[ -n "$current" ]]; then
        printf "  ${GREEN}✓${NC} %-36s ${YELLOW}[đã có — Enter để giữ]${NC}: " "$label"
    else
        printf "  ${YELLOW}→${NC} %-36s : " "$label"
    fi
    read -rs val || true; echo
    [[ -n "$val" ]] && eval "$var='$val'" || true
}

# Sinh secret ngẫu nhiên
gen_secret() { openssl rand -hex 32 2>/dev/null || head -c 48 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 48; }

# ── Banner ───────────────────────────────────────────────────────
clear
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║       🤖  Crypto Trading Bot  🤖                 ║"
echo "  ║            Deployment Script                     ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Server IP : ${CYAN}$SERVER_IP${NC}"
echo -e "  Frontend  : ${CYAN}http://$SERVER_IP:$FRONTEND_PORT${NC}"
echo -e "  Backend   : ${CYAN}http://$SERVER_IP:$BACKEND_PORT${NC}"
echo -e "  Repo      : ${CYAN}$REPO_URL${NC}"
echo


# ══════════════════════════════════════════════════════════════════
section "1. Kiểm tra prerequisites"
# ══════════════════════════════════════════════════════════════════

command -v git    >/dev/null 2>&1 || die "git chưa cài  →  sudo apt install git -y"
command -v docker >/dev/null 2>&1 || die "Docker chưa cài  →  https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1   || die "Docker Compose v2 chưa có"

ok "git · docker · docker compose đều sẵn sàng"


# ══════════════════════════════════════════════════════════════════
section "2. Clone / cập nhật code"
# ══════════════════════════════════════════════════════════════════

if [[ -d "$APP_DIR/.git" ]]; then
    info "Repo đã có — kéo code mới nhất..."
    git -C "$APP_DIR" pull
    ok "git pull hoàn tất"
else
    info "Clone lần đầu..."
    git clone "$REPO_URL" "$APP_DIR"
    ok "Clone hoàn tất"
fi

cd "$APP_DIR"


# ══════════════════════════════════════════════════════════════════
section "3. Tạo docker-compose.override.yml"
# ══════════════════════════════════════════════════════════════════

cat > docker-compose.override.yml <<OVERRIDE
# ----------------------------------------------------------------
# docker-compose.override.yml — chỉ tồn tại trên server này
# Tự động sinh bởi deploy.sh — KHÔNG commit file này lên git
# Docker Compose tự động merge với docker-compose.yml
# ----------------------------------------------------------------

services:
  web-frontend:
    ports:
      - "${FRONTEND_PORT}:3000"        # tránh port 3000 của anchoi.xxx
    build:
      args:
        NEXT_PUBLIC_API_URL: http://${SERVER_IP}:${BACKEND_PORT}
        NEXT_PUBLIC_API_KEY: \${WEB_API_KEY}

  web-backend:
    ports:
      - "${BACKEND_PORT}:8000"         # port 8000 free trên server này
OVERRIDE

ok "docker-compose.override.yml → frontend:$FRONTEND_PORT / backend:$BACKEND_PORT"


# ══════════════════════════════════════════════════════════════════
section "4. Cấu hình .env (nhập API keys)"
# ══════════════════════════════════════════════════════════════════

# Load giá trị cũ nếu .env đã tồn tại
if [[ -f .env ]]; then
    info ".env đã có — load giá trị cũ, chỉ nhập những key còn trống"
    set -o allexport
    source .env 2>/dev/null || true
    set +o allexport
else
    info ".env chưa có — sẽ tạo mới"
fi

# Tự tạo WEB_API_KEY nếu chưa có hoặc còn là placeholder
if [[ -z "${WEB_API_KEY:-}" || "$WEB_API_KEY" == "change-me-secret"* ]]; then
    WEB_API_KEY=$(gen_secret)
    info "Đã tự sinh WEB_API_KEY: ${WEB_API_KEY:0:8}…"
fi

echo
echo -e "  ${BOLD}── Binance ──────────────────────────────────────────${NC}"
ask_secret BINANCE_API_KEY    "BINANCE_API_KEY"
ask_secret BINANCE_SECRET_KEY "BINANCE_SECRET_KEY"
ask        BINANCE_TLD        "BINANCE_TLD (com = Binance global / us = Binance.US)" "com"
ask        BINANCE_TESTNET    "BINANCE_TESTNET (true=testnet / false=live)" "true"

echo
echo -e "  ${BOLD}── AI APIs ──────────────────────────────────────────${NC}"
ask_secret CLAUDE_API_KEY   "CLAUDE_API_KEY   (sk-ant-…)"
ask_secret DEEPSEEK_API_KEY "DEEPSEEK_API_KEY"

echo
echo -e "  ${BOLD}── Telegram ─────────────────────────────────────────${NC}"
ask_secret TELEGRAM_BOT_TOKEN        "TELEGRAM_BOT_TOKEN   (123:ABC…)"
ask        TELEGRAM_ALLOWED_USER_IDS "TELEGRAM_ALLOWED_USER_IDS" "${TELEGRAM_ALLOWED_USER_IDS:-}"

# Ghi .env
cat > .env <<ENV
# ----------------------------------------------------------------
# .env — Crypto Trading Bot
# Sinh bởi deploy.sh lúc $(date '+%Y-%m-%d %H:%M:%S')
# ⚠️  KHÔNG commit file này lên git (.gitignore đã bảo vệ)
# ----------------------------------------------------------------

# Binance
BINANCE_API_KEY=${BINANCE_API_KEY:-}
BINANCE_SECRET_KEY=${BINANCE_SECRET_KEY:-}
BINANCE_TLD=${BINANCE_TLD:-com}
BINANCE_TESTNET=${BINANCE_TESTNET:-true}

# AI
CLAUDE_API_KEY=${CLAUDE_API_KEY:-}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}

# Telegram
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
TELEGRAM_ALLOWED_USER_IDS=${TELEGRAM_ALLOWED_USER_IDS:-}

# Web Dashboard
WEB_API_KEY=${WEB_API_KEY}
NEXT_PUBLIC_API_URL=http://${SERVER_IP}:${BACKEND_PORT}
NEXT_PUBLIC_API_KEY=${WEB_API_KEY}

# Redis (nội bộ Docker — không đụng Redis của anchoi.xxx)
REDIS_URL=redis://redis:6379
REDIS_KEY_PREFIX=bot:

# Engine
SCAN_INTERVAL_SECONDS=300
REPORT_TIMES=07:00,12:00,17:00,22:00
ENV

chmod 600 .env
ok ".env đã lưu và chmod 600"


# ══════════════════════════════════════════════════════════════════
section "5. Cấu hình Nginx"
# ══════════════════════════════════════════════════════════════════

NGINX_CONF="/etc/nginx/sites-available/trading-bot"

if command -v nginx >/dev/null 2>&1; then
    sudo tee "$NGINX_CONF" > /dev/null <<NGINX
# ----------------------------------------------------------------
# Nginx config: Trading Bot (port $FRONTEND_PORT/$BACKEND_PORT)
# File: /etc/nginx/sites-available/trading-bot
# KHÔNG đụng file anchoi.xxx
# ----------------------------------------------------------------

server {
    listen 80;
    server_name $SERVER_IP;

    # Dashboard (Next.js frontend)
    location / {
        proxy_pass         http://127.0.0.1:$FRONTEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_cache_bypass \$http_upgrade;
    }

    # REST API
    location /api/ {
        proxy_pass         http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_cache_bypass \$http_upgrade;
    }

    # WebSocket (live events)
    location /api/ws/ {
        proxy_pass          http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version  1.1;
        proxy_set_header    Upgrade \$http_upgrade;
        proxy_set_header    Connection "upgrade";
        proxy_read_timeout  86400;
    }
}
NGINX

    # Bật site nếu chưa
    if [[ ! -L /etc/nginx/sites-enabled/trading-bot ]]; then
        sudo ln -s "$NGINX_CONF" /etc/nginx/sites-enabled/trading-bot
        ok "Nginx site enabled"
    fi

    if sudo nginx -t 2>/dev/null; then
        sudo nginx -s reload
        ok "Nginx reload thành công"
    else
        warn "Nginx config có lỗi — kiểm tra: sudo nginx -t"
    fi
else
    warn "Nginx không có trên server — bỏ qua bước này"
    warn "Truy cập trực tiếp: http://$SERVER_IP:$FRONTEND_PORT"
fi


# ══════════════════════════════════════════════════════════════════
section "6. Build & khởi động Docker Compose"
# ══════════════════════════════════════════════════════════════════

info "Build và start tất cả services (lần đầu ~5-10 phút)..."
docker compose up -d --build

ok "Docker Compose đã chạy"


# ══════════════════════════════════════════════════════════════════
section "7. Kiểm tra health"
# ══════════════════════════════════════════════════════════════════

echo
info "Chờ services khởi động..."
sleep 8

echo -e "\n  ${BOLD}Trạng thái containers:${NC}"
docker compose ps

echo
info "Kiểm tra backend /health..."
RETRIES=12
for i in $(seq 1 $RETRIES); do
    if curl -sf "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
        ok "Backend healthy  ✓"
        break
    fi
    if [[ $i -eq $RETRIES ]]; then
        warn "Backend chưa phản hồi sau 60s"
        warn "Xem log: docker compose logs --tail=30 web-backend"
    else
        printf "  Thử %d/%d...\r" "$i" "$RETRIES"
        sleep 5
    fi
done


# ══════════════════════════════════════════════════════════════════
echo
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║         ✅  DEPLOY HOÀN THÀNH                    ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo
echo -e "  🌐 Dashboard     ${CYAN}http://$SERVER_IP:$FRONTEND_PORT${NC}"
echo -e "  🔌 API docs      ${CYAN}http://$SERVER_IP:$BACKEND_PORT/docs${NC}"
echo -e "  ❤️  Health check  ${CYAN}http://$SERVER_IP:$BACKEND_PORT/health${NC}"
echo
echo -e "  ${BOLD}Lệnh hữu ích:${NC}"
echo -e "  ${YELLOW}docker compose logs -f engine${NC}       # theo dõi trading engine"
echo -e "  ${YELLOW}docker compose logs -f telegram${NC}     # theo dõi telegram bot"
echo -e "  ${YELLOW}docker compose ps${NC}                   # trạng thái tất cả service"
echo -e "  ${YELLOW}docker compose restart engine${NC}       # restart 1 service"
echo -e "  ${YELLOW}docker compose down${NC}                 # dừng tất cả"
echo
echo -e "  ${BOLD}Cập nhật code sau này:${NC}"
echo -e "  ${YELLOW}cd $APP_DIR && bash deploy.sh${NC}"
echo
