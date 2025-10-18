#!/usr/bin/env bash
# Run your Telegram bot after exporting the bot token.
# Usage:
#   ./run_bot.sh                  # reads token from .env
#   TELEGRAM_BOT_TOKEN=xxx ./run_bot.sh   # or pass via env
#   ./run_bot.sh --token xxx      # or pass as arg

set -Eeuo pipefail

# --- cd to script dir (so it works from anywhere) ---
cd "$(dirname "$0")"

# --- parse optional --token ARG ---
TOKEN_FROM_ARG=""
if [[ "${1:-}" == "--token" ]]; then
  TOKEN_FROM_ARG="${2:-}"
  shift 2 || true
fi

# --- load .env if present (exports all vars in it) ---
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

# --- final token resolution order: arg > env > error ---
TG_TOKEN="${TOKEN_FROM_ARG:-${TG_TOKEN:-}}"
if [[ -z "${TG_TOKEN}" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN not set.
Set it in .env, or run:
  TELEGRAM_BOT_TOKEN=YOUR_TOKEN ./run_bot.sh
or:
  ./run_bot.sh --token YOUR_TOKEN" >&2
  exit 1
fi
export TG_TOKEN

# --- Python venv setup (optional but nice) ---
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- deps (no-op if requirements.txt not present) ---
if [[ -f "requirements.txt" ]]; then
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
fi

# --- run the bot ---
echo "Starting bot.py ..."
exec python3 bot.py