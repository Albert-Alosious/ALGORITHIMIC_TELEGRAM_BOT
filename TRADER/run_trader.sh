#!/usr/bin/env bash
# Run the trader application inside its virtual environment.
# Usage:
#   ./run_trader.sh                  # runs uvicorn main:app
#   PORT=9000 ./run_trader.sh        # run on different port
#   RELOAD=1 ./run_trader.sh         # enable auto-reload (dev only)

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ -f "requirements.txt" ]]; then
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
fi

PORT="8000"
RELOAD="${RELOAD:-0}"
UVICORN_CMD=(uvicorn main:app --host 0.0.0.0 --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
  UVICORN_CMD+=(--reload)
fi

exec "${UVICORN_CMD[@]}"
