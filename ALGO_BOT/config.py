from __future__ import annotations

import os
from pathlib import Path

# Telegram bot token. Exported via environment or .env (see run_bot.sh).
TOKEN: str | None = os.getenv("TG_TOKEN")

# Restrict access to certain Telegram user IDs. Keep empty set to allow all.
ALLOWED_USER_IDS: set[int] = set()

# Target application you control via the bot.
WORKDIR = Path("/Users/yourname/projects/my_app").expanduser()
APP_CMD = ["python3", "main.py"]
LOGFILE = WORKDIR / "app.log"
PIDFILE = WORKDIR / "app.pid"

# Order persistence configuration.
BASE_DIR = Path(__file__).resolve().parent
ORDER_FILE = BASE_DIR / "res" / "ORDER_LIST.csv"
ORDER_HEADERS = [
    "Serial",
    "Symbol",
    "Company",
    "Quantity",
    "MinProfitINR",
    "MaxProfitINR",
    "Date",
    "Time",
]

# WebSocket configuration for communicating with the trader engine.
WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws")
