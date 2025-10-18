"""
Stub application endpoints that mirror the Telegram bot actions.

Each function simply prints what it received so the rest of the project
can integrate later without breaking behaviour. Once real logic is
available, swap the print statements for actual side effects (database
writes, API calls, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

# === App control =============================================================


def open_app(workdir: Path) -> None:
    """Display where the managed application lives."""
    print(f"[INPUT_CALLS] Open app requested for workdir: {workdir}")


def start_app(workdir: Path, cmd: Iterable[str]) -> None:
    """Stub: launch the managed application."""
    print(f"[INPUT_CALLS] Start app requested. workdir={workdir} cmd={list(cmd)}")


def stop_app() -> None:
    """Stub: gracefully stop the managed application."""
    print("[INPUT_CALLS] Stop app requested.")


def close_app(force: bool = True) -> None:
    """Stub: force stop the application."""
    print(f"[INPUT_CALLS] Close app requested. force={force}")


def fetch_logs(lines: int = 100) -> None:
    """Stub: return recent log excerpt."""
    print(f"[INPUT_CALLS] Fetch logs requested. tail_lines={lines}")


def show_status(running: bool, pid: int | None = None) -> None:
    """Stub: report current process status."""
    print(f"[INPUT_CALLS] Status requested. running={running} pid={pid}")


def clear_panel() -> None:
    """Stub: clear chat messages."""
    print("[INPUT_CALLS] Clear panel requested.")


def show_models() -> None:
    """Stub: display help/models information."""
    print("[INPUT_CALLS] Models/help requested.")


# === Order workflow =========================================================


@dataclass
class OrderPayload:
    symbol: str
    company: str
    quantity: int
    min_profit_inr: float
    max_profit_inr: float
    exchange: str = "NSE"
    serial: int | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


def list_orders() -> None:
    """Stub: list saved orders."""
    print("[INPUT_CALLS] List orders requested.")


def create_or_update_order(payload: OrderPayload) -> None:
    """Stub: persist an order payload."""
    print(f"[INPUT_CALLS] Create/Update order: {payload}")


def prompt_quantity(order: OrderPayload) -> None:
    """Stub: prompt for quantity."""
    print(f"[INPUT_CALLS] Prompt quantity for {order.symbol}")


def prompt_profit_targets(order: OrderPayload) -> None:
    """Stub: prompt for profit targets."""
    print(f"[INPUT_CALLS] Prompt profit targets for {order.symbol}")


def order_summary(order: OrderPayload) -> None:
    """Stub: show final summary."""
    print(f"[INPUT_CALLS] Order summary: {order}")
