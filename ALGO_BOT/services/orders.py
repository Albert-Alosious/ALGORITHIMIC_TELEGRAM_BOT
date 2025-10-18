from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime
from typing import Dict, List

from config import ORDER_FILE, ORDER_HEADERS

_LOCK = threading.RLock()
_CACHE: List[Dict[str, str]] | None = None
_SERIAL_TO_INDEX: Dict[str, int] = {}
_COMPANY_TO_SERIAL: Dict[str, str] = {}


def _ensure_file_exists() -> None:
    ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ORDER_FILE.exists() or ORDER_FILE.stat().st_size == 0:
        with ORDER_FILE.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(ORDER_HEADERS)


def _load_cache() -> None:
    global _CACHE, _SERIAL_TO_INDEX, _COMPANY_TO_SERIAL
    if _CACHE is not None:
        return
    _ensure_file_exists()
    cache: List[Dict[str, str]] = []
    serial_index: Dict[str, int] = {}
    company_serial: Dict[str, str] = {}
    try:
        with ORDER_FILE.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row:
                    continue
                cleaned = {
                    key.strip(): (value.strip() if isinstance(value, str) else value)
                    for key, value in row.items()
                }
                serial = cleaned.get("Serial", "")
                if not serial:
                    serial = str(len(cache) + 1)
                    cleaned["Serial"] = serial
                serial_index[serial] = len(cache)
                company_key = cleaned.get("Company", "").strip().lower()
                if company_key:
                    company_serial[company_key] = serial
                cache.append(cleaned)
    except Exception as exc:
        logging.error("Failed to read order file: %s", exc)
        cache = []
        serial_index = {}
        company_serial = {}
    _CACHE = cache
    _SERIAL_TO_INDEX = serial_index
    _COMPANY_TO_SERIAL = company_serial


def _write_cache() -> None:
    if _CACHE is None:
        return
    with ORDER_FILE.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ORDER_HEADERS)
        writer.writeheader()
        for row in _CACHE:
            writer.writerow({header: row.get(header, "") for header in ORDER_HEADERS})


def list_order_records() -> List[Dict[str, str]]:
    with _LOCK:
        _load_cache()
        if not _CACHE:
            return []
        return sorted(
            (row.copy() for row in _CACHE),
            key=lambda r: int(r.get("Serial", "0") or 0),
        )


def _next_serial() -> int:
    if not _CACHE:
        return 1
    highest = 0
    for row in _CACHE:
        try:
            value = int(row.get("Serial", "") or 0)
        except ValueError:
            continue
        highest = max(highest, value)
    return highest + 1


def save_order_record(
    *,
    symbol: str,
    company: str,
    quantity: int,
    min_profit: float,
    max_profit: float,
    serial: int | None = None,
) -> int:
    with _LOCK:
        _load_cache()
        assert _CACHE is not None
        serial_value: int | None = serial
        index: int | None = None
        if serial_value is not None:
            serial_str = str(serial_value)
            serial_value = int(serial_str)
            index = _SERIAL_TO_INDEX.get(serial_str)
        company_key = company.strip().lower()
        if index is None and company_key:
            existing_serial = _COMPANY_TO_SERIAL.get(company_key)
            if existing_serial:
                index = _SERIAL_TO_INDEX.get(existing_serial)
                try:
                    serial_value = int(existing_serial)
                except (ValueError, TypeError):
                    serial_value = None
        if serial_value is None:
            serial_value = _next_serial()
        serial_str = str(serial_value)
        now = datetime.now()
        record = {
            "Serial": serial_str,
            "Symbol": str(symbol),
            "Company": str(company),
            "Quantity": str(int(quantity)),
            "MinProfitINR": f"{float(min_profit):.2f}",
            "MaxProfitINR": f"{float(max_profit):.2f}",
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
        }
        if index is None:
            index = len(_CACHE)
            _CACHE.append(record)
        else:
            _CACHE[index] = record
        _SERIAL_TO_INDEX[serial_str] = index
        if company_key:
            _COMPANY_TO_SERIAL[company_key] = serial_str
        _write_cache()
        return serial_value
