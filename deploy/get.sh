#!/usr/bin/env bash
# Bir qatorli o'rnatish:
#   curl -fsSL https://raw.githubusercontent.com/uBakhtiyarov3/yaproqgosht/claude/zen-euler-bvolwi/deploy/get.sh | bash
set -euo pipefail
REPO="https://github.com/uBakhtiyarov3/yaproqgosht.git"
BRANCH="${YAPROQ_BRANCH:-claude/zen-euler-bvolwi}"
DIR="$HOME/yaproqgosht"

if ! command -v git >/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y git curl
fi
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch origin "$BRANCH" && git -C "$DIR" checkout "$BRANCH" && git -C "$DIR" pull --ff-only
else
  git clone -b "$BRANCH" "$REPO" "$DIR"
fi
# savollarga klaviaturadan javob berish uchun stdin ni terminalga ulaymiz
bash "$DIR/deploy/install.sh" </dev/tty
