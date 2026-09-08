"""Physical artifact readers; no discovery or business normalization."""

from __future__ import annotations

import csv
import json
from concurrent.futures import Future
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

import pandas as pd

from ._shared import (
    _attach_source_headers,
    _recover_gap_rows_missing_control_cells,
)


def _read_csv_preserving_headers(path: Path) -> pd.DataFrame:
    """Read every physical CSV column without merging duplicate names."""

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.reader(stream))
    headers = tuple(source_rows[0]) if source_rows else ()
    if not headers:
        raise ValueError("CSV has no header row")
    rows, recovery = _recover_gap_rows_missing_control_cells(
        headers,
        source_rows[1:],
    )
    widths = {len(row) for row in rows}
    if widths - {len(headers)}:
        actual = sorted(widths)
        raise ValueError(
            f"CSV row widths {actual} do not match header width {len(headers)}"
        )
    frame = pd.DataFrame(rows, columns=range(len(headers)), dtype=object)
    frame = _attach_source_headers(frame, headers)
    if recovery:
        frame.attrs["recoveries"] = (recovery,)
    return frame


def _promote_excel_header(frame: pd.DataFrame, header: int) -> pd.DataFrame:
    if header < 0:
        raise ValueError(f"Excel header row {header} is invalid")
    if header >= len(frame):
        return pd.DataFrame(dtype=object)
    headers = frame.iloc[header].tolist()
    body = frame.iloc[header + 1 :].reset_index(drop=True).copy()
    return _attach_source_headers(body, headers)


def read_table(path: Path, options: Mapping[str, Any] | None = None) -> Any:
    options = options or {}
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return _read_csv_preserving_headers(path)
    if suffix in {".xlsx", ".xls"}:
        sheet_name = options.get("sheet_name", 0)
        header = options.get("header", 0)
        value = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            dtype=object,
        )
        if header is None:
            return value
        if not isinstance(header, int):
            raise ValueError("Excel header must be an integer row or null")
        if isinstance(value, dict):
            return {
                name: _promote_excel_header(frame, header)
                for name, frame in value.items()
            }
        return _promote_excel_header(value, header)
    if suffix == ".json":
        return pd.read_json(path, dtype=False)
    raise ValueError(f"unsupported artifact format: {path.suffix}")


@lru_cache(maxsize=128)
def _cached_question_table(path: str, options_json: str) -> Any:
    return read_table(Path(path), json.loads(options_json))


_QUESTION_LOADS_LOCK = Lock()
_QUESTION_LOADS: dict[tuple[str, str], Future[Any]] = {}


def read_question_table(path: str, options_json: str) -> Any:
    """Load immutable question evidence once, including concurrent cold calls.

    ``functools.lru_cache`` permits duplicate execution while an identical miss
    is still running.  Large EI workbooks therefore used to be parsed once per
    scoring thread.  The small single-flight layer makes one caller the loader
    and lets concurrent callers await the same result.
    """

    key = (path, options_json)
    with _QUESTION_LOADS_LOCK:
        future = _QUESTION_LOADS.get(key)
        owner = future is None
        if future is None:
            future = Future()
            _QUESTION_LOADS[key] = future
    if not owner:
        return future.result()
    try:
        value = _cached_question_table(path, options_json)
    except BaseException as exc:
        future.set_exception(exc)
        raise
    else:
        future.set_result(value)
        return value
    finally:
        with _QUESTION_LOADS_LOCK:
            _QUESTION_LOADS.pop(key, None)


def clear_question_table_cache() -> None:
    """Clear completed question inputs; intended for tests and long-lived apps."""

    _cached_question_table.cache_clear()


def question_table_cache_info():
    return _cached_question_table.cache_info()


__all__ = [
    "clear_question_table_cache",
    "question_table_cache_info",
    "read_question_table",
    "read_table",
]
