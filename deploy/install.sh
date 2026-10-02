#!/usr/bin/env bash
# Yaproq go'sht botini Ubuntu serverga bir buyruq bilan o'rnatish.
# Ishlatish:  bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

say() { printf "\n\033[1;33m==> %s\033[0m\n" "$1"; }

# 1) Kam xotirali serverlar (1 GB) uchun swap
if [ "$(free -m | awk '/^Mem:/{print $2}')" -lt 2000 ] && ! swapon --show | grep -q .; then
  say "2 GB swap yaratilmoqda"
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# 2) Docker
if ! command -v docker >/dev/null; then
  say "Docker o'rnatilmoqda"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi

# 3) Firewall: 80 va 443 portlarni ochish (Oracle Ubuntu obrazlarida iptables yopiq bo'ladi)
say "80/443 portlar ochilmoqda"
if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
fi
if sudo iptables -L INPUT -n 2>/dev/null | grep -q "REJECT"; then
  for p in 80 443; do
    sudo iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport $p -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save; fi
fi

# 4) .env
PUBLIC_IP="$(curl -fsS https://api.ipify.org || true)"
if [ ! -f .env ]; then
  say ".env sozlamalari"
  read -rp "BOT_TOKEN (@BotFather): " BOT_TOKEN
  read -rp "ADMIN_IDS (bosh menejer Telegram ID, vergul bilan): " ADMIN_IDS
  echo "Domen: DuckDNS subdomeningiz (masalan yaproqgosht.duckdns.org)."
  echo "Bo'sh qoldirsangiz vaqtinchalik ${PUBLIC_IP//./-}.sslip.io ishlatiladi."
  read -rp "DOMAIN: " DOMAIN
  DOMAIN="${DOMAIN:-${PUBLIC_IP//./-}.sslip.io}"
  read -rp "DUCKDNS_TOKEN (DuckDNS ishlatmasangiz bo'sh qoldiring): " DUCKDNS_TOKEN
  cat > .env <<ENV
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
DOMAIN=$DOMAIN
WEBAPP_URL=https://$DOMAIN
PORT=8080
DB_PATH=data/bot.db
DEBUG=0
DUCKDNS_TOKEN=$DUCKDNS_TOKEN
ENV
  chmod 600 .env
fi
set -a; . ./.env; set +a

# 5) DuckDNS: IP o'zgarsa domen avtomatik yangilanadi (har 5 daqiqada)
if [ -n "${DUCKDNS_TOKEN:-}" ] && [[ "$DOMAIN" == *.duckdns.org ]]; then
  say "DuckDNS yangilagich o'rnatilmoqda"
  SUB="${DOMAIN%.duckdns.org}"
  URL="https://www.duckdns.org/update?domains=${SUB}&token=${DUCKDNS_TOKEN}&ip="
  curl -fsS "$URL" && echo
  ( crontab -l 2>/dev/null | grep -v duckdns.org/update; echo "*/5 * * * * curl -fsS '$URL' >/dev/null 2>&1" ) | crontab -
fi

# 6) Ishga tushirish
say "Bot va HTTPS ishga tushirilmoqda"
mkdir -p data
sudo docker compose up -d --build
sleep 5
sudo docker compose ps

cat <<DONE

✅ Tayyor!
   Mini App:   https://$DOMAIN   (SSL sertifikat 1-2 daqiqada olinadi)
   Tekshirish: https://$DOMAIN/health
   Loglar:     sudo docker compose logs -f bot
   Yangilash:  bash deploy/update.sh

Botga /start bosing.
DONE
