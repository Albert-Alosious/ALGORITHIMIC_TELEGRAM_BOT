"""
Utilities for loading Excel workbooks and searching their contents.

This module keeps the responsibilities small so it can be imported by
Telegram handlers or standalone scripts.  It relies on `pandas` when
available because it provides a consistent interface across Excel
formats.  If pandas is missing, it falls back to `openpyxl` for basic
`.xlsx` support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from functools import lru_cache
import csv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_NSE_CSV = BASE_DIR / "res" / "EQUITY_L.csv"

try:
    import pandas as _pd  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - runtime fallback
    _pd = None  # pyright: ignore[reportPrivateUsage]

try:
    import openpyxl as _openpyxl  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - runtime fallback
    _openpyxl = None


class ExcelLoadError(RuntimeError):
    """Raised when the workbook cannot be loaded."""


def _load_with_pandas(path: Path, sheet: str | int | None):
    if _pd is None:
        raise ExcelLoadError("pandas is required to read this Excel file.")
    try:
        return _pd.read_excel(path, sheet_name=sheet)
    except Exception as exc:  # pragma: no cover - delegate to caller
        raise ExcelLoadError(f"Failed to load {path} with pandas: {exc}") from exc


def _load_with_openpyxl(path: Path, sheet: str | int | None):
    if _openpyxl is None:
        raise ExcelLoadError("openpyxl is required to read this Excel file.")
    try:
        workbook = _openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # pragma: no cover
        raise ExcelLoadError(f"Failed to open workbook {path}: {exc}") from exc

    if sheet is None:
        ws = workbook.active
    elif isinstance(sheet, int):
        try:
            ws = workbook.worksheets[sheet]
        except IndexError as exc:  # pragma: no cover
            raise ExcelLoadError(f"Sheet index {sheet} is out of range.") from exc
    else:
        if sheet not in workbook.sheetnames:
            raise ExcelLoadError(f"Sheet named {sheet!r} was not found.")
        ws = workbook[sheet]

    rows = list(ws.iter_rows(values_only=True))
    headers = rows[0] if rows else ()
    data = rows[1:] if len(rows) > 1 else ()
    return {"headers": headers, "rows": data}


def load_table(path: str | Path, sheet: str | int | None = None):
    """
    Load an Excel sheet into a pandas DataFrame when available, otherwise
    return a simple dictionary containing ``headers`` and ``rows`` lists.
    """
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    if _pd is not None:
        return _load_with_pandas(file_path, sheet)
    return _load_with_openpyxl(file_path, sheet)


@lru_cache(maxsize=None)
def _load_nse_dataset(path: str = str(DEFAULT_NSE_CSV)):
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"NSE equity file not found: {file_path}")
    if _pd is not None:
        df = _pd.read_csv(file_path)
        df.columns = [str(col).strip() for col in df.columns]
        return df
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, object]] = []
        for row in reader:
            normalized = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            rows.append(normalized)
        return rows


@dataclass(frozen=True)
class NSEEntry:
    symbol: str
    name: str
    name_lower: str


@lru_cache(maxsize=None)
def _load_nse_entries(path: str = str(DEFAULT_NSE_CSV)) -> tuple[NSEEntry, ...]:
    dataset = _load_nse_dataset(path)
    entries: list[NSEEntry] = []
    column_name = "NAME OF COMPANY"
    symbol_col = "SYMBOL"
    if _pd is not None and hasattr(dataset, "iterrows"):
        df = dataset  # type: ignore[assignment]
        df_pairs = df[[symbol_col, column_name]].dropna()
        for symbol, name in df_pairs.itertuples(index=False):
            symbol_str = str(symbol).strip()
            name_str = str(name).strip()
            if not symbol_str or not name_str:
                continue
            entries.append(NSEEntry(symbol_str, name_str, name_str.casefold()))
    else:
        for row in dataset:  # type: ignore[assignment]
            symbol = str(row.get(symbol_col, "")).strip()
            name = str(row.get(column_name, "")).strip()
            if not symbol or not name:
                continue
            entries.append(NSEEntry(symbol, name, name.casefold()))
    return tuple(entries)


def search_nse_companies(query: str, limit: int = 10) -> list[dict[str, object]]:
    """
    Search NSE equities by company name (column B) using a case-insensitive
    substring match. Returns dictionaries with ``symbol`` and ``name`` keys.
    """
    entries = _load_nse_entries()
    cleaned = query.strip().casefold()
    if not cleaned:
        return []
    matches: list[dict[str, object]] = []
    for entry in entries:
        if cleaned in entry.name_lower:
            matches.append({"symbol": entry.symbol, "name": entry.name})
            if len(matches) >= limit:
                break
    return matches


def get_nse_company(symbol: str) -> dict[str, object] | None:
    """Return a single NSE company record by symbol."""
    entries = _load_nse_entries()
    target = symbol.strip().casefold()
    for entry in entries:
        if entry.symbol.casefold() == target:
            return {"symbol": entry.symbol, "name": entry.name}
    return None


def find_rows(
    table: Mapping[str, Sequence] | "pd.DataFrame",
    contains: Mapping[str, str] | None = None,
) -> Iterable[Mapping[str, object]]:
    """
    Yield rows whose text matches the ``contains`` mapping.

    ``contains`` is a mapping of column name to a case-insensitive substring.
    When ``table`` is a pandas DataFrame, rows are converted to dicts.  When
    using the fallback dictionary structure, the function constructs dicts
    on the fly.
    """
    filters = {k: v.lower() for k, v in (contains or {}).items()}

    if _pd is not None and hasattr(table, "iterrows"):
        df = table  # type: ignore[assignment]
        for _, row in df.iterrows():
            as_dict = row.to_dict()
            if _matches_filters(as_dict, filters):
                yield as_dict
        return

    headers = table.get("headers", ())
    for row in table.get("rows", ()):
        as_dict = {str(col): row[idx] for idx, col in enumerate(headers)}
        if _matches_filters(as_dict, filters):
            yield as_dict


def _matches_filters(row: Mapping[str, object], filters: Mapping[str, str]) -> bool:
    for column, needle in filters.items():
        haystack = str(row.get(column, "")).lower()
        if needle not in haystack:
            return False
    return True
