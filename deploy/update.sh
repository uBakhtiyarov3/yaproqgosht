#!/usr/bin/env bash
# Kodni yangilash: GitHub dan oxirgi o'zgarishlarni olib, botni qayta quradi (ma'lumotlar saqlanadi).
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
sudo docker compose up -d --build
sudo docker image prune -f >/dev/null
sudo docker compose ps
