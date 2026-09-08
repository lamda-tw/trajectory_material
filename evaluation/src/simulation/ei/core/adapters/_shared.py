"""Shared parsing and normalization algorithms for product adapters."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from ..models import (
    ArtifactBundle,
    ArtifactCandidate,
    ArtifactResolution,
    ArtifactSpec,
    QuestionProfile,
)
from ..question_sources import locate_question_artifact


_NON_ITEM_COLUMNS = {
    "month",
    "week",
    "type",
    "total",
    "scope",
    "scopeid",
    "region",
    "regionid",
    "itemcode",
    "projectweek",
    "opening",
    "inbound",
    "outbound",
    "closing",
}
_WAREHOUSE_DIMENSIONS = {
    "scope": ("scope", "scopeid"),
    "region": ("region", "regionid"),
}
_GAP_METRICS = {
    "dismantled": "Dismantled",
    "arrive": "Arrive",
    "dismantledsupply": "DismantledSupply",
    "reuseconsumed": "ReuseConsumed",
    "demand": "Demand",
    "gap": "GAP",
    "newproposal": "GAP",
}
_GAP_SUMMARIES = {
    "total_dismantled": "total_dismantled",
    "initial_inventory": "initial_inventory",
    "total_arrive": "totalArrive",
    "total_reuse": "totalReuse",
    "total_demand": "totalDemand",
    "total_gap": "totalGap",
}
_QUANTITY_METRICS = {
    "dismantled",
    "intersitereuse",
    "reuse",
    "initialstockreuse",
    "newproposal",
    "new",
}
_DEFAULT_REQUIRED_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "ei.site-plan": (
        ("site_name", "site id", "site id radio", "站点"),
        ("site_action", "action"),
    ),
    "ei.site-rollout": (
        ("region",),
        ("type",),
        ("site_type",),
    ),
    "ei.material-substitution": (
        ("solution_id",),
        ("priority",),
        ("target_item_code",),
        ("target_qty",),
        ("sub_item_code",),
        ("sub_qty",),
    ),
    "ei.timeline": (
        ("item_code",),
        ("required_qty", "quantity"),
        ("action",),
        ("week_num", "project_week"),
    ),
    "ei.recovered-supply": (
        ("item_code",),
        ("available_week",),
        ("available_qty",),
    ),
    "ei.reuse-summary": (
        ("item_code",),
        ("metric",),
        ("total",),
    ),
    "ei.final-material": (
        ("site_name", "site id", "site id radio", "站点"),
        ("item_code",),
        ("required_qty", "quantity"),
        ("action", "site_action"),
    ),
    "ei.gap-wide": (
        ("region",),
        ("item_code",),
        ("initial_inventory",),
        ("week",),
        ("WK5",),
        ("WK33",),
    ),
}
_UNSET = object()


def _norm(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", " ", str(value).strip())


def _header_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _norm(value).casefold())


def _material_key(value: Any) -> str:
    """Material identity normalization authorized by the prompts."""

    return _norm(value).casefold()


def warehouse_key_parts(key: tuple[Any, ...]) -> tuple[tuple[str, ...], str, int]:
    """Return preserved dimensions, material and week from a normalized ledger key.

    Warehouse keys remain backward compatible: files without business dimensions
    use ``(material, week)``; files with Prompt columns such as Scope or Region use
    ``("scope=...", "region=...", material, week)``.
    """

    if len(key) < 2:
        raise ValueError(f"invalid warehouse key: {key!r}")
    return tuple(str(value) for value in key[:-2]), str(key[-2]), int(key[-1])


def warehouse_series_key(key: tuple[Any, ...]) -> tuple[str, ...]:
    dimensions, item, _ = warehouse_key_parts(key)
    return (*dimensions, item)


# Kept for existing rule helpers.  Artifact identity code must use _material_key.
def _key(value: Any) -> str:
    return _header_key(value)


def _source_headers(frame: pd.DataFrame) -> tuple[str, ...]:
    raw = frame.attrs.get("source_headers")
    if isinstance(raw, (list, tuple)) and len(raw) == len(frame.columns):
        return tuple(str(value) for value in raw)
    return tuple(str(value) for value in frame.columns)


def _attach_source_headers(frame: pd.DataFrame, headers: Iterable[Any]) -> pd.DataFrame:
    raw_headers = tuple(_norm(value) for value in headers)
    if len(frame.columns) != len(raw_headers):
        raise ValueError("table width does not match source header width")
    seen: dict[str, int] = defaultdict(int)
    labels: list[str] = []
    for position, header in enumerate(raw_headers):
        key = _header_key(header)
        seen[key] += 1
        labels.append(
            header
            if seen[key] == 1
            else f"__duplicate_source_column_{position + 1}__"
        )
    frame.columns = labels
    frame.attrs["source_headers"] = raw_headers
    return frame


def _recover_gap_rows_missing_control_cells(
    headers: tuple[str, ...],
    rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, Any] | None]:
    """Recover the observed GAP layout that omitted three unused controls.

    One candidate family retained the canonical forty-column header but wrote
    every physical row as the first eight controls followed by all twenty-nine
    weekly values.  The omitted ``totalDemand``, ``totalGap`` and ``week``
    cells are unambiguous because every row has the same width and the weekly
    suffix is complete.  No other row-width mismatch is repaired here.
    """

    header_keys = tuple(_header_key(value) for value in headers)
    omitted = ("totaldemand", "totalgap", "week")
    if (
        len(headers) >= 11
        and header_keys[8:11] == omitted
        and rows
        and all(len(row) == len(headers) - len(omitted) for row in rows)
    ):
        recovered = [row[:8] + ["", "", ""] + row[8:] for row in rows]
        return recovered, {
            "code": "RECOVERED_GAP_OMITTED_CONTROL_CELLS",
            "inserted_positions": [9, 10, 11],
            "inserted_headers": list(headers[8:11]),
            "source_row_width": len(headers) - len(omitted),
            "recovered_row_count": len(rows),
        }
    return rows, None


def _column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    wanted = {_header_key(value) for value in aliases}
    for position, value in enumerate(_source_headers(frame)):
        if _header_key(value) in wanted:
            return str(frame.columns[position])
    return None


def _column_positions(frame: pd.DataFrame, aliases: Iterable[str]) -> tuple[int, ...]:
    wanted = {_header_key(value) for value in aliases}
    return tuple(
        position
        for position, value in enumerate(_source_headers(frame))
        if _header_key(value) in wanted
    )


def _groups_from_options(options: Mapping[str, Any]) -> tuple[tuple[str, ...], ...] | None:
    raw = options.get("required_columns")
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError("schema_options.required_columns must be a list")
    groups: list[tuple[str, ...]] = []
    for value in raw:
        if isinstance(value, str) and value:
            groups.append((value,))
        elif isinstance(value, (list, tuple)) and value and all(
            isinstance(item, str) and item for item in value
        ):
            groups.append(tuple(value))
        else:
            raise ValueError("each required column must be a name or a non-empty alias list")
    return tuple(groups)


def _group_coverage(frame: pd.DataFrame, groups: tuple[tuple[str, ...], ...]) -> float:
    if not groups:
        return 1.0
    matched = sum(1 for aliases in groups if _column(frame, aliases) is not None)
    return matched / len(groups)


def _required_coverage(
    frame: Any,
    schema: str,
    options: Mapping[str, Any] | None = None,
) -> float:
    if not isinstance(frame, pd.DataFrame):
        return 1.0 if schema == "generic" else 0.0
    options = options or {}
    exact = options.get("exact_columns")
    if exact is not None:
        if not isinstance(exact, (list, tuple)) or not all(
            isinstance(value, str) and value for value in exact
        ):
            raise ValueError("schema_options.exact_columns must be a list of names")
        actual_keys = [_header_key(value) for value in _source_headers(frame)]
        expected_keys = [_header_key(value) for value in exact]
        matched = sum(
            1
            for index, value in enumerate(expected_keys)
            if index < len(actual_keys) and actual_keys[index] == value
        )
        return (
            1.0
            if actual_keys == expected_keys
            else matched / max(len(expected_keys), len(actual_keys), 1)
        )
    configured = _groups_from_options(options)
    if configured is not None:
        return _group_coverage(frame, configured)
    if schema == "ei.warehouse":
        long_form = _group_coverage(
            frame,
            (
                ("item_code",),
                ("project_week",),
                ("opening",),
                ("inbound",),
                ("outbound",),
                ("closing",),
            ),
        )
        wide_form = _group_coverage(frame, (("week",), ("type",)))
        return max(long_form, wide_form)
    return _group_coverage(frame, _DEFAULT_REQUIRED_GROUPS.get(schema, ()))


def _schema_issues(
    frame: Any,
    schema: str,
    options: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Describe schema defects without discarding readable source content."""

    if not isinstance(frame, pd.DataFrame):
        return ()
    options = options or {}
    headers = _source_headers(frame)
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for position, header in enumerate(headers):
        key = _header_key(header)
        if key:
            grouped[key].append((position + 1, header))
    issues: list[dict[str, Any]] = []
    if schema not in {"ei.warehouse", "ei.reuse-summary"}:
        for values in grouped.values():
            if len(values) > 1:
                issues.append(
                    {
                        "code": "DUPLICATE_SOURCE_COLUMN",
                        "message": "source contains duplicate logical column names",
                        "column": values[0][1],
                        "positions": [position for position, _ in values],
                    }
                )
    exact = options.get("exact_columns")
    if isinstance(exact, (list, tuple)):
        if [_header_key(value) for value in headers] != [
            _header_key(value) for value in exact
        ]:
            issues.append(
                {
                    "code": "EXACT_COLUMNS_MISMATCH",
                    "message": "source columns do not match the Prompt order exactly",
                    "expected": [str(value) for value in exact],
                    "actual": list(headers),
                }
            )
        return tuple(issues)
    groups = _groups_from_options(options)
    if groups is None:
        if schema == "ei.warehouse":
            long_groups = (
                ("item_code",),
                ("project_week",),
                ("opening",),
                ("inbound",),
                ("outbound",),
                ("closing",),
            )
            wide_groups = (("week",), ("type",))
            groups = (
                long_groups
                if _group_coverage(frame, long_groups)
                >= _group_coverage(frame, wide_groups)
                else wide_groups
            )
        else:
            groups = _DEFAULT_REQUIRED_GROUPS.get(schema, ())
    for aliases in groups:
        if not _column_positions(frame, aliases):
            issues.append(
                {
                    "code": "MISSING_REQUIRED_COLUMN",
                    "message": "source lacks a required Prompt field",
                    "aliases": list(aliases),
                }
            )
    return tuple(issues)


def _integer_quantity(value: Any) -> bool:
    if _norm(value) == "":
        return False
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return False
    return parsed.is_finite() and parsed == parsed.to_integral_value()


def material_quantity(value: Any) -> int:
    """Parse one physical quantity without tolerance, rounding, or repair."""

    if not _integer_quantity(value):
        raise ValueError(f"material quantity is not an integer: {_norm(value)!r}")
    return int(Decimal(str(value).strip()))


def preserved_quantity(value: Any) -> int | float:
    """Parse a finite quantity without discarding a readable fractional value.

    Integer-ness is a scoring contract, not an artifact-retention contract.  The
    adapter therefore preserves fractional evidence for unit-level validation;
    callers can still report ``NON_INTEGER_QUANTITY`` without losing the cell.
    """

    text = _norm(value)
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"material quantity is not numeric: {text!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"material quantity is not finite: {text!r}")
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def parse_project_week(value: Any) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric) and numeric.is_integer():
            week = int(numeric)
            if week >= 1:
                return week
            raise ValueError(f"project week is out of range: {week}")
    text = _norm(value)
    match = re.fullmatch(r"(?:(?:20\d{2})\s*)?(?:WK|W)?\s*(\d{1,2})", text, re.I)
    if not match:
        raise ValueError(f"invalid project week: {text!r}")
    week = int(match.group(1))
    if week < 1:
        raise ValueError(f"project week is out of range: {week}")
    return week


def parse_iso_week(value: Any) -> int:
    """Return a sortable YYYYWW integer after strict ISO-week validation."""

    text = _norm(value)
    match = re.fullmatch(r"(20\d{2})\s*-?\s*W(?:K)?\s*(\d{1,2})", text, re.I)
    if not match:
        raise ValueError(f"invalid ISO week: {text!r}")
    year, week = int(match.group(1)), int(match.group(2))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"invalid ISO week: {text!r}") from exc
    return year * 100 + week


def _week(value: Any, kind: str = "project") -> int:
    if kind == "project":
        return parse_project_week(value)
    if kind == "iso":
        return parse_iso_week(value)
    if kind == "auto":
        text = _norm(value)
        if re.fullmatch(r"20\d{2}\s*-\s*W(?:K)?\s*\d{1,2}", text, re.I):
            return parse_iso_week(text)
        return parse_project_week(text)
    raise ValueError(f"unsupported week_kind: {kind!r}")


def week_coordinate_kind(values: Iterable[int]) -> str:
    """Infer the canonical coordinate family from normalized week values."""

    submitted = tuple(int(value) for value in values)
    return "iso" if any(value >= 100000 for value in submitted) else "project"


def shift_week_coordinate(week: int, offset: int, kind: str) -> int:
    """Shift either a continuous project week or a validated ISO week."""

    if kind == "project":
        shifted = int(week) + int(offset)
        if shifted < 1:
            raise ValueError(f"project week shift leaves the valid range: {shifted}")
        return shifted
    if kind == "iso":
        year, iso_week = divmod(int(week), 100)
        try:
            monday = date.fromisocalendar(year, iso_week, 1)
        except ValueError as exc:
            raise ValueError(f"invalid normalized ISO week: {week!r}") from exc
        shifted = monday + timedelta(weeks=int(offset))
        iso_year, shifted_week, _ = shifted.isocalendar()
        return int(iso_year) * 100 + int(shifted_week)
    raise ValueError(f"unsupported week_kind: {kind!r}")


def gap_week_column(value: Any) -> tuple[int, str] | None:
    """Parse the two observed GAP header dialects into canonical coordinates."""

    text = _norm(value)
    if re.fullmatch(r"W(?:K)?\d+", text, re.I):
        return parse_project_week(text), "project"
    if re.fullmatch(r"20\d{2}\s*-?\s*W(?:K)?\s*\d{1,2}", text, re.I):
        return parse_iso_week(text), "iso"
    return None


def _issue(
    code: str,
    message: str,
    *,
    row: int | None = None,
    column: str | None = None,
    raw: Any = None,
    key: Any = None,
    unit_id: str | None = None,
    affected_unit_ids: Iterable[str] | None = None,
    source_rows: Iterable[int] | None = None,
    physical_columns: Iterable[int] | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {"code": code, "message": message}
    if row is not None:
        output["row"] = row
    if column is not None:
        output["column"] = column
    if raw is not None:
        output["raw"] = _norm(raw)
    if key is not None:
        output["key"] = key
    if unit_id is not None:
        output["unit_id"] = unit_id
    if affected_unit_ids is not None:
        output["affected_unit_ids"] = list(dict.fromkeys(affected_unit_ids))
    if source_rows is not None:
        output["source_rows"] = list(dict.fromkeys(source_rows))
    if physical_columns is not None:
        columns = list(dict.fromkeys(physical_columns))
        output["physical_columns"] = columns
        output["positions"] = columns
    return output


def _warehouse_long(
    frame: pd.DataFrame,
    *,
    week_kind: str,
) -> tuple[dict[tuple[Any, ...], dict[str, int | float]], tuple[dict[str, Any], ...]]:
    headers = _source_headers(frame)
    positions: dict[str, list[int]] = defaultdict(list)
    for position, value in enumerate(headers):
        positions[_header_key(value)].append(position)
    required_positions = {
        name: positions[name][0]
        for name in ("itemcode", "projectweek", "opening", "inbound", "outbound", "closing")
    }
    dimension_positions = []
    for name, aliases in _WAREHOUSE_DIMENSIONS.items():
        matches = [position for alias in aliases for position in positions.get(alias, ())]
        if len(matches) == 1:
            dimension_positions.append((name, matches[0]))
    staged: dict[tuple[Any, ...], list[tuple[int, pd.Series]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    for row_index, row in frame.iterrows():
        source_row = int(row_index) + 2
        item = _material_key(row.iloc[required_positions["itemcode"]])
        if not item:
            unit_id = f"long:row:{source_row}"
            issues.append(_issue("EMPTY_ITEM", "warehouse row has empty item_code", row=source_row, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
            continue
        try:
            raw_week = row.iloc[required_positions["projectweek"]]
            week = _week(raw_week, week_kind)
        except ValueError as exc:
            unit_id = f"long:{item}:row:{source_row}"
            issues.append(_issue("INVALID_WEEK", str(exc), row=source_row, column=headers[required_positions["projectweek"]], raw=raw_week, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
            continue
        dimensions = tuple(
            f"{name}={_material_key(row.iloc[position])}"
            for name, position in dimension_positions
        )
        staged[(*dimensions, item, week)].append((source_row, row))

    parsed: dict[tuple[Any, ...], dict[str, Any]] = {}
    for key, rows in staged.items():
        dimensions, item, week = warehouse_key_parts(key)
        identity = ":".join((*dimensions, item, str(week)))
        if len(rows) != 1:
            unit_ids = [f"long:{identity}:row:{source_row}" for source_row, _ in rows]
            issues.append(_issue("DUPLICATE_KEY", "warehouse contains duplicate dimension/item/week rows", row=rows[0][0], key=key, affected_unit_ids=unit_ids, source_rows=[source_row for source_row, _ in rows]))
            parsed[key] = {"valid": False, "closing": None, "source_rows": [value[0] for value in rows]}
            continue
        source_row, row = rows[0]
        cell: dict[str, int | float] = {}
        valid = True
        for name in ("opening", "inbound", "outbound", "closing"):
            raw = row.iloc[required_positions[name]]
            try:
                cell[name] = preserved_quantity(raw)
            except ValueError as exc:
                valid = False
                unit_id = f"long:{identity}:row:{source_row}"
                issues.append(_issue("INVALID_QUANTITY", str(exc), row=source_row, column=headers[required_positions[name]], raw=raw, key=key, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
                continue
            if not _integer_quantity(raw):
                unit_id = f"long:{identity}:row:{source_row}"
                issues.append(_issue("NON_INTEGER_QUANTITY", f"material quantity is not an integer: {_norm(raw)!r}", row=source_row, column=headers[required_positions[name]], raw=raw, key=key, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
        parsed[key] = {
            "valid": valid,
            "cell": cell,
            # A row with another bad field still supplies its explicitly
            # submitted closing to the immediately following row.
            "closing": cell.get("closing"),
            "source_rows": [source_row],
        }

    result: dict[tuple[Any, ...], dict[str, int | float]] = {}
    by_series: dict[tuple[str, ...], list[tuple[Any, ...]]] = defaultdict(list)
    for key in staged:
        by_series[warehouse_series_key(key)].append(key)
    for series, keys in by_series.items():
        has_previous = False
        previous_closing: int | float | None = None
        for key in sorted(keys, key=lambda value: warehouse_key_parts(value)[2]):
            entry = parsed[key]
            if entry["valid"]:
                cell = dict(entry["cell"])
                if has_previous:
                    if previous_closing is None:
                        dimensions, item, week = warehouse_key_parts(key)
                        identity = ":".join((*dimensions, item, str(week)))
                        unit_id = f"long:{identity}:row:{entry['source_rows'][0]}"
                        issues.append(
                            _issue(
                                "UNVERIFIABLE_OPENING",
                                "opening cannot be checked against the immediately preceding submitted row",
                                key=key,
                                unit_id=unit_id,
                                affected_unit_ids=[unit_id],
                                source_rows=entry["source_rows"],
                            )
                        )
                    else:
                        cell["continuity_expected"] = previous_closing
                        result[key] = cell
                else:
                    result[key] = cell
            has_previous = True
            previous_closing = entry["closing"]
    return result, tuple(issues)


def _warehouse_wide(
    frame: pd.DataFrame,
    *,
    week_kind: str,
    enforce_type_order: bool,
) -> tuple[dict[tuple[Any, ...], dict[str, int | float]], tuple[dict[str, Any], ...]]:
    week_positions = _column_positions(frame, ("week",))
    type_positions = _column_positions(frame, ("type",))
    issues: list[dict[str, Any]] = []
    if len(week_positions) != 1 or len(type_positions) != 1:
        issues.append(
            _issue(
                "AMBIGUOUS_CONTROL_COLUMN",
                "weekly warehouse requires exactly one week column and one type column",
            )
        )
        return {}, tuple(issues)
    week_position, type_position = week_positions[0], type_positions[0]
    headers = _source_headers(frame)
    dimension_positions: list[tuple[str, int]] = []
    for name, aliases in _WAREHOUSE_DIMENSIONS.items():
        matches = _column_positions(frame, aliases)
        if len(matches) > 1:
            issues.append(
                _issue(
                    "AMBIGUOUS_DIMENSION_COLUMN",
                    f"weekly warehouse contains duplicate {name} dimensions",
                    physical_columns=[value + 1 for value in matches],
                )
            )
            return {}, tuple(issues)
        if matches:
            dimension_positions.append((name, matches[0]))
    grouped_items: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for position, header in enumerate(headers):
        if _header_key(header) not in _NON_ITEM_COLUMNS:
            grouped_items[_material_key(header)].append((position, header))
    item_columns = [
        values[0]
        for values in grouped_items.values()
        if len(values) == 1 and values[0][0] not in {week_position, type_position}
    ]
    if not item_columns:
        issues.append(
            _issue(
                "NO_UNAMBIGUOUS_MATERIAL_COLUMN",
                "weekly warehouse contains no unambiguous material column",
            )
        )
        return {}, tuple(issues)
    all_material_columns = [
        value
        for values in grouped_items.values()
        for value in values
        if value[0] not in {week_position, type_position}
    ]
    staged: dict[tuple[Any, ...], dict[str, list[tuple[int, Any]]]] = defaultdict(lambda: defaultdict(list))
    week_type_rows: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for row_index, row in frame.iterrows():
        source_row = int(row_index) + 2
        dimensions = tuple(
            f"{name}={_material_key(row.iloc[position])}"
            for name, position in dimension_positions
        )
        try:
            week = _week(row.iloc[week_position], week_kind)
        except ValueError as exc:
            raw_week = _norm(row.iloc[week_position]) or "blank"
            unit_ids = [
                f"wide:column:{position + 1}:{_material_key(header)}:raw-week:{raw_week}"
                for position, header in all_material_columns
            ]
            issues.append(_issue("INVALID_WEEK", str(exc), row=source_row, column=headers[week_position], raw=row.iloc[week_position], affected_unit_ids=unit_ids, source_rows=[source_row], physical_columns=[position + 1 for position, _ in all_material_columns]))
            continue
        kind = _norm(row.iloc[type_position]).casefold()
        kind = "closing" if kind == "inventory" else kind
        if kind not in {"inbound", "outbound", "closing"}:
            unit_ids = [
                f"wide:column:{position + 1}:{_material_key(header)}:{week}"
                for position, header in all_material_columns
            ]
            issues.append(_issue("INVALID_TYPE", f"invalid warehouse type {kind!r}", row=source_row, column=headers[type_position], raw=row.iloc[type_position], affected_unit_ids=unit_ids, source_rows=[source_row], physical_columns=[position + 1 for position, _ in all_material_columns]))
            continue
        series_week = (*dimensions, week)
        week_type_rows[series_week].append(kind)
        for position, header in item_columns:
            staged[(*dimensions, _material_key(header), week)][kind].append((source_row, row.iloc[position]))
    invalid_order_weeks: set[tuple[Any, ...]] = set()
    if enforce_type_order:
        expected = ["inbound", "outbound", "closing"]
        for series_week, kinds in week_type_rows.items():
            if kinds != expected:
                invalid_order_weeks.add(series_week)
                unit_ids = [
                    "wide:" + ":".join(str(value) for value in key)
                    for key in staged
                    if (*key[:-2], key[-1]) == series_week
                ]
                issues.append(_issue("TYPE_ORDER", "warehouse type rows are not Inbound/Outbound/Inventory in order", key=series_week, affected_unit_ids=unit_ids))
    submitted_weeks = sorted(week_type_rows, key=lambda value: (value[:-1], value[-1]))
    for item, values in grouped_items.items():
        if len(values) > 1:
            unit_ids = [
                "wide:column:"
                + str(position + 1)
                + ":"
                + item
                + ":"
                + ":".join(str(value) for value in series_week)
                for position, _ in values
                for series_week in submitted_weeks
            ] or [f"wide:column:{position + 1}:{item}:no-week" for position, _ in values]
            issues.append(
                {
                    **_issue(
                        "DUPLICATE_MATERIAL_COLUMN",
                        "one logical material is represented by multiple physical columns",
                        column=values[0][1],
                        key=item,
                        affected_unit_ids=unit_ids,
                        physical_columns=[position + 1 for position, _ in values],
                    ),
                    "affected_cells": len(submitted_weeks),
                }
            )
    parsed: dict[tuple[Any, ...], dict[str, int | float]] = {}
    required = {"inbound", "outbound", "closing"}
    for key, by_type in staged.items():
        missing = required - set(by_type)
        unit_id = "wide:" + ":".join(str(value) for value in key)
        if missing:
            issues.append(_issue("MISSING_TYPE", "warehouse cell is missing types: " + ", ".join(sorted(missing)), key=key, unit_id=unit_id, affected_unit_ids=[unit_id]))
        duplicate = {kind: values for kind, values in by_type.items() if len(values) != 1}
        for kind, values in duplicate.items():
            issues.append(_issue("DUPLICATE_TYPE", f"warehouse contains duplicate {kind} rows", row=values[0][0], key=key, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row for source_row, _ in values]))
        if missing or duplicate or (*key[:-2], key[-1]) in invalid_order_weeks:
            continue
        cell: dict[str, int | float] = {}
        valid = True
        for kind in required:
            source_row, raw = by_type[kind][0]
            try:
                cell[kind] = preserved_quantity(raw)
            except ValueError as exc:
                valid = False
                issues.append(_issue("INVALID_QUANTITY", str(exc), row=source_row, column=kind, raw=raw, key=key, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
                continue
            if not _integer_quantity(raw):
                issues.append(_issue("NON_INTEGER_QUANTITY", f"material quantity is not an integer: {_norm(raw)!r}", row=source_row, column=kind, raw=raw, key=key, unit_id=unit_id, affected_unit_ids=[unit_id], source_rows=[source_row]))
        if valid:
            parsed[key] = cell
    result: dict[tuple[Any, ...], dict[str, int | float]] = {}
    by_series: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for key in staged:
        by_series[warehouse_series_key(key)].append(warehouse_key_parts(key)[2])
    for series, weeks in by_series.items():
        previous_inventory: int | None = 0
        for week in sorted(set(weeks)):
            key = (*series, week)
            cell = parsed.get(key)
            if cell is None:
                previous_inventory = None
                continue
            if previous_inventory is None:
                unit_id = "wide:" + ":".join(str(value) for value in key)
                issues.append(_issue("UNVERIFIABLE_OPENING", "opening cannot be derived from the immediately preceding submitted week", key=key, unit_id=unit_id, affected_unit_ids=[unit_id]))
                previous_inventory = cell["closing"]
                continue
            result[key] = {
                "opening": previous_inventory,
                "inbound": cell["inbound"],
                "outbound": cell["outbound"],
                "closing": cell["closing"],
            }
            previous_inventory = cell["closing"]
    return result, tuple(issues)


def _normalize_warehouse(
    frame: pd.DataFrame,
    options: Mapping[str, Any] | None = None,
) -> tuple[dict[tuple[str, int], dict[str, int | float]], tuple[dict[str, Any], ...]]:
    options = options or {}
    headers = _source_headers(frame)
    positions: dict[str, list[int]] = defaultdict(list)
    for position, value in enumerate(headers):
        positions[_header_key(value)].append(position)
    week_kind = str(options.get("week_kind", "auto"))
    long_keys = {"itemcode", "projectweek", "opening", "inbound", "outbound", "closing"}
    if long_keys.issubset(positions):
        ambiguous = sorted(key for key in long_keys if len(positions[key]) != 1)
        ambiguous.extend(
            name
            for name, aliases in _WAREHOUSE_DIMENSIONS.items()
            if sum(len(positions.get(alias, ())) for alias in aliases) > 1
        )
        if ambiguous:
            return {}, (
                {
                    "code": "AMBIGUOUS_LONG_COLUMN",
                    "message": "long warehouse contains duplicate required fields",
                    "columns": ambiguous,
                },
            )
        return _warehouse_long(frame, week_kind=week_kind)
    return _warehouse_wide(
        frame,
        week_kind=week_kind,
        enforce_type_order=bool(options.get("enforce_type_order", False)),
    )


def _gap_block_id(region: str, item: str) -> str:
    return f"gap:{_material_key(region)}:{_material_key(item)}"


def _gap_number(
    value: Any,
    *,
    row: int,
    column: str,
    block_id: str,
    metric: str,
    issues: list[dict[str, Any]],
) -> int | None:
    """Parse one GAP quantity without silently rounding or repairing it."""

    if not _norm(value):
        return 0
    try:
        return material_quantity(value)
    except ValueError as exc:
        unit_id = f"{block_id}:{metric}:{column}"
        issues.append(
            _issue(
                "NON_INTEGER_QUANTITY",
                str(exc),
                row=row,
                column=column,
                raw=value,
                unit_id=unit_id,
                affected_unit_ids=[unit_id],
                source_rows=[row],
            )
            | {
                "affected_block_ids": [block_id],
                "affected_metrics": [metric],
                **(
                    {"week": int(match.group(1))}
                    if (match := re.fullmatch(r"WK([0-9]+)", column, re.IGNORECASE))
                    else {}
                ),
            }
        )
        return None


def _gap_sign_error_count(block: Mapping[str, Any], weeks: tuple[int, ...], sign: int) -> int:
    """Count balance mismatches for one submitted GAP sign convention."""

    previous = int(block["summary"]["initial_inventory"])
    failures = 0
    for week in weeks:
        metrics = block["metrics"]
        submitted = sign * int(metrics["GAP"][week])
        expected = (
            previous
            + int(metrics["Arrive"][week])
            + int(metrics["DismantledSupply"][week])
            - int(metrics["Demand"][week])
        )
        failures += int(submitted != expected)
        previous = submitted
    failures += int(previous != sign * int(block["summary"]["total_gap"]))
    return failures


def _aggregate_gap_payload(
    frame: pd.DataFrame,
    *,
    region_col: str,
    item_col: str,
    week_col: str,
    week_columns: tuple[tuple[int, str], ...],
    week_kind: str | None,
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], ...]]:
    """Preserve one-row-per-material GAP evidence without inventing semantics.

    The observed compact layout exposes summary quantities and, in some runs,
    an unlabeled weekly series.  It does not identify that series as dismantled
    or mature supply, so the adapter retains it as submitted evidence and marks
    the artifact aggregate-only.  Business rules can award only the evidence
    that is actually present.
    """

    business: list[tuple[int, pd.Series]] = []
    keys: list[tuple[str, str]] = []
    for row_index, row in frame.iterrows():
        region = _norm(row.get(region_col))
        item = _norm(row.get(item_col))
        if not region and not item:
            continue
        if not region or not item:
            return None, ()
        business.append((int(row_index), row))
        keys.append((_material_key(region), _material_key(item)))
    if not business or len(set(keys)) != len(keys):
        return None, ()

    control_values = [
        _norm(row.get(week_col))
        for _, row in business
        if _norm(row.get(week_col))
    ]
    if any(_GAP_METRICS.get(_header_key(value)) for value in control_values):
        return None, ()

    summary_columns = {
        canonical: _column(frame, (source,))
        for canonical, source in _GAP_SUMMARIES.items()
    }
    if not any(summary_columns.values()):
        return None, ()

    issues: list[dict[str, Any]] = []
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    for (row_index, row), key in zip(business, keys):
        source_row = row_index + 2
        block_id = _gap_block_id(*key)
        summary: dict[str, int | float] = {}
        for name, column in summary_columns.items():
            raw = row.get(column) if column is not None else ""
            if not _norm(raw):
                summary[name] = 0
                continue
            try:
                summary[name] = preserved_quantity(raw)
            except ValueError as exc:
                issues.append(
                    _issue(
                        "INVALID_GAP_QUANTITY",
                        str(exc),
                        row=source_row,
                        column=column,
                        raw=raw,
                        key=key,
                        unit_id=f"{block_id}:{name}",
                        affected_unit_ids=[f"{block_id}:{name}"],
                        source_rows=[source_row],
                    )
                    | {
                        "affected_block_ids": [block_id],
                        "affected_metrics": [name],
                    }
                )
                continue
            if not _integer_quantity(raw):
                issues.append(
                    _issue(
                        "NON_INTEGER_QUANTITY",
                        f"material quantity is not an integer: {_norm(raw)!r}",
                        row=source_row,
                        column=column,
                        raw=raw,
                        key=key,
                        unit_id=f"{block_id}:{name}",
                        affected_unit_ids=[f"{block_id}:{name}"],
                        source_rows=[source_row],
                    )
                    | {
                        "affected_block_ids": [block_id],
                        "affected_metrics": [name],
                    }
                )
        weekly: dict[int, int | float] = {}
        for coordinate, column in week_columns:
            raw = row.get(column)
            if not _norm(raw):
                weekly[coordinate] = 0
                continue
            try:
                weekly[coordinate] = preserved_quantity(raw)
            except ValueError as exc:
                unit_id = f"{block_id}:unlabelled:{coordinate}"
                issues.append(
                    _issue(
                        "INVALID_GAP_QUANTITY",
                        str(exc),
                        row=source_row,
                        column=column,
                        raw=raw,
                        key=key,
                        unit_id=unit_id,
                        affected_unit_ids=[unit_id],
                        source_rows=[source_row],
                    )
                    | {
                        "affected_block_ids": [block_id],
                        "affected_metrics": ["UNLABELLED_WEEKLY_SERIES"],
                        "week": coordinate,
                    }
                )
                continue
            if not _integer_quantity(raw):
                unit_id = f"{block_id}:unlabelled:{coordinate}"
                issues.append(
                    _issue(
                        "NON_INTEGER_QUANTITY",
                        f"material quantity is not an integer: {_norm(raw)!r}",
                        row=source_row,
                        column=column,
                        raw=raw,
                        key=key,
                        unit_id=unit_id,
                        affected_unit_ids=[unit_id],
                        source_rows=[source_row],
                    )
                    | {
                        "affected_block_ids": [block_id],
                        "affected_metrics": ["UNLABELLED_WEEKLY_SERIES"],
                        "week": coordinate,
                    }
                )
        blocks[key] = {
            "region": _norm(row.get(region_col)),
            "item": _norm(row.get(item_col)),
            "block_id": block_id,
            "summary": summary,
            "submitted_weekly_series": weekly,
            "weekly_semantics": "unlabelled",
            "source_row": source_row,
            "control_value": _norm(row.get(week_col)),
        }

    return {
        "blocks": {},
        "aggregate_blocks": blocks,
        "weeks": tuple(value for value, _ in week_columns),
        "week_kind": week_kind,
        "sign_conventions": {},
        "metric_column": None,
        "evidence_level": "aggregate",
        "recoveries": (
            {
                "code": "PRESERVED_AGGREGATE_GAP",
                "block_count": len(blocks),
                "weekly_semantics": "unlabelled",
            },
        ),
    }, tuple(issues)


def normalize_gap_wide(
    frame: pd.DataFrame,
    options: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Compile GAP rows and normalize GAP to a signed inventory balance.

    Some historical candidates use negative inventory balance while others use
    positive shortage for the same ``GAP`` field.  The adapter chooses one
    convention per business block from the submitted recurrence, then exposes
    only the canonical signed-balance form to business rules.  The raw table is
    retained on the artifact resolution for audit.  ``week`` remains the
    primary metric carrier; ``category`` is accepted only when ``week`` has no
    business metrics and ``category`` unambiguously covers the complete Prompt
    metric set.  Project-week and ISO-week headers are normalized without
    conflation. Historical files that dropped all metric labels, or exactly one
    label in an otherwise canonical block, are recovered only from the frozen
    six-row order. Compact one-row-per-material submissions retain summaries and
    unlabeled weekly values as aggregate evidence; they are never promoted to
    item-week maturity evidence. Conflicting or ambiguous carriers remain invalid.
    """

    options = options or {}
    region_col = _column(frame, ("region",))
    item_col = _column(frame, ("item_code",))
    week_col = _column(frame, ("week",))
    category_col = _column(frame, ("category",))
    if None in {region_col, item_col, week_col}:
        issue = _issue(
            "MISSING_GAP_KEY_COLUMNS",
            "gap.csv requires region, item_code and week control columns",
        ) | {"affected_metrics": list(_GAP_METRICS.values())}
        return {"blocks": {}, "weeks": (), "sign_conventions": {}}, (issue,)

    parsed_week_columns = [
        (parsed[0], str(column), parsed[1])
        for column in frame.columns
        if (parsed := gap_week_column(column)) is not None
    ]
    week_kinds = {kind for _, _, kind in parsed_week_columns}
    issues: list[dict[str, Any]] = []
    if len(week_kinds) > 1:
        issues.append(
            _issue(
                "MIXED_GAP_WEEK_KINDS",
                "gap.csv mixes project-week and ISO-week columns",
            )
            | {"affected_metrics": list(_GAP_METRICS.values())}
        )
    week_kind = (
        next(iter(week_kinds))
        if len(week_kinds) == 1
        else "mixed"
        if week_kinds
        else None
    )
    week_columns = sorted(
        ((coordinate, column) for coordinate, column, _ in parsed_week_columns),
        key=lambda value: value[0],
    )
    weeks = tuple(value for value, _ in week_columns)
    contiguous_weeks = (
        tuple(
            shift_week_coordinate(weeks[0], offset, str(week_kind))
            for offset in range(len(weeks))
        )
        if weeks and week_kind in {"project", "iso"}
        else ()
    )
    if weeks and weeks != contiguous_weeks:
        issues.append(
            _issue(
                "NON_CONTIGUOUS_GAP_WEEKS",
                "gap.csv week columns are not contiguous",
            )
            | {
                "weeks": list(weeks),
                "affected_metrics": list(_GAP_METRICS.values()),
            }
        )

    exact_columns = tuple(str(value) for value in options.get("exact_columns", ()))
    expected_weeks = tuple(
        parsed[0]
        for value in exact_columns
        if (parsed := gap_week_column(value)) is not None
    )
    if expected_weeks and weeks != expected_weeks:
        issues.append(
            _issue(
                "GAP_WEEK_WINDOW_MISMATCH",
                "gap.csv week window differs from the frozen Prompt contract",
            )
            | {
                "expected_weeks": list(expected_weeks),
                "actual_weeks": list(weeks),
                "affected_metrics": list(_GAP_METRICS.values()),
            }
        )

    def row_metric(row: pd.Series, column: str | None) -> str | None:
        if column is None:
            return None
        raw = _norm(row.get(column))
        key = re.sub(r"[^0-9a-z]+", "", raw.casefold())
        return _GAP_METRICS.get(key)

    required_metrics = set(_GAP_METRICS.values())
    week_metrics = {
        metric
        for _, row in frame.iterrows()
        if (metric := row_metric(row, week_col)) is not None
    }
    category_metrics = {
        metric
        for _, row in frame.iterrows()
        if (metric := row_metric(row, category_col)) is not None
    }
    metric_col = week_col
    metric_column = "week"
    if not week_metrics and required_metrics <= category_metrics:
        metric_col = category_col
        metric_column = "category"
    elif week_metrics and category_metrics:
        conflicts = []
        for row_index, row in frame.iterrows():
            week_metric = row_metric(row, week_col)
            category_metric = row_metric(row, category_col)
            if category_metric is not None and category_metric != week_metric:
                conflicts.append(
                    {
                        "row": int(row_index) + 2,
                        "week_metric": week_metric,
                        "category_metric": category_metric,
                    }
                )
        if conflicts:
            issues.append(
                _issue(
                    "CONFLICTING_GAP_METRIC_COLUMNS",
                    "gap.csv week and category columns provide conflicting business metrics",
                )
                | {
                    "conflicts": conflicts[:50],
                    "affected_metrics": sorted(required_metrics),
                }
            )

    aggregate, aggregate_issues = _aggregate_gap_payload(
        frame,
        region_col=region_col,
        item_col=item_col,
        week_col=week_col,
        week_columns=tuple(week_columns),
        week_kind=week_kind,
    )
    if aggregate is not None and not week_metrics and not category_metrics:
        aggregate["recoveries"] = tuple(frame.attrs.get("recoveries", ())) + tuple(
            aggregate.get("recoveries", ())
        )
        return aggregate, tuple(issues) + aggregate_issues

    if not weeks:
        issue = _issue(
            "MISSING_GAP_WEEK_COLUMNS",
            "gap.csv contains no project-week or ISO-week columns",
        ) | {"affected_metrics": list(_GAP_METRICS.values())}
        return {
            "blocks": {},
            "aggregate_blocks": {},
            "weeks": (),
            "week_kind": None,
            "sign_conventions": {},
            "evidence_level": "none",
        }, tuple(issues) + (issue,)

    control_columns = tuple(
        value
        for value in (
            region_col,
            item_col,
            _column(frame, ("device",)),
            category_col,
            week_col,
        )
        if value is not None
    )
    date_row_indexes = {
        row_index
        for row_index, row in frame.iterrows()
        if not _norm(row.get(item_col))
        and any(_header_key(row.get(column)) == "date" for column in control_columns)
    }
    row_metrics: dict[int, str] = {
        int(row_index): metric
        for row_index, row in frame.iterrows()
        if (metric := row_metric(row, metric_col)) is not None
    }
    recoveries: list[dict[str, Any]] = [
        dict(value) for value in frame.attrs.get("recoveries", ())
    ]
    if not row_metrics:
        business_indexes = [
            int(row_index)
            for row_index in frame.index
            if int(row_index) not in date_row_indexes
        ]
        metric_order = tuple(dict.fromkeys(_GAP_METRICS.values()))
        recoverable = bool(business_indexes) and len(business_indexes) % len(metric_order) == 0
        recovered: dict[int, str] = {}
        if recoverable:
            for offset in range(0, len(business_indexes), len(metric_order)):
                indexes = business_indexes[offset : offset + len(metric_order)]
                keys = {
                    (
                        _material_key(_norm(frame.loc[row_index].get(region_col))),
                        _material_key(_norm(frame.loc[row_index].get(item_col))),
                    )
                    for row_index in indexes
                }
                if len(keys) != 1 or not all(next(iter(keys))):
                    recoverable = False
                    break
                recovered.update(zip(indexes, metric_order))
        if recoverable:
            row_metrics = recovered
            metric_col = None
            metric_column = "fixed-six-row-order"
            recoveries.append(
                {
                    "code": "RECOVERED_GAP_FIXED_ROW_ORDER",
                    "metric_order": list(metric_order),
                    "block_count": len(business_indexes) // len(metric_order),
                    "source_rows": [value + 2 for value in business_indexes],
                }
            )
    elif metric_col is not None:
        metric_order = tuple(dict.fromkeys(_GAP_METRICS.values()))
        grouped_indexes: dict[tuple[str, str], list[int]] = defaultdict(list)
        for row_index, row in frame.iterrows():
            if int(row_index) in date_row_indexes:
                continue
            key = (
                _material_key(_norm(row.get(region_col))),
                _material_key(_norm(row.get(item_col))),
            )
            if all(key):
                grouped_indexes[key].append(int(row_index))
        recovered_rows: list[int] = []
        for indexes in grouped_indexes.values():
            if len(indexes) != len(metric_order):
                continue
            observed = [row_metrics.get(row_index) for row_index in indexes]
            missing_positions = [
                position for position, metric in enumerate(observed) if metric is None
            ]
            if len(missing_positions) != 1:
                continue
            missing_position = missing_positions[0]
            raw = _norm(frame.loc[indexes[missing_position]].get(metric_col))
            if raw:
                continue
            if any(
                metric is not None and metric != metric_order[position]
                for position, metric in enumerate(observed)
            ):
                continue
            row_metrics[indexes[missing_position]] = metric_order[missing_position]
            recovered_rows.append(indexes[missing_position])
        if recovered_rows:
            recoveries.append(
                {
                    "code": "RECOVERED_GAP_SINGLE_BLANK_METRIC",
                    "metric_order": list(metric_order),
                    "block_count": len(recovered_rows),
                    "source_rows": [value + 2 for value in recovered_rows],
                }
            )

    summary_columns = {
        key: _column(frame, (source,)) for key, source in _GAP_SUMMARIES.items()
    }
    staged: dict[tuple[str, str], dict[str, Any]] = {}
    invalid_blocks: set[tuple[str, str]] = set()
    date_rows: list[int] = []
    for row_index, row in frame.iterrows():
        source_row = int(row_index) + 2
        if int(row_index) in date_row_indexes:
            date_rows.append(source_row)
            continue
        metric_raw = (
            _norm(row.get(metric_col))
            if metric_col is not None
            else row_metrics.get(int(row_index), "")
        )
        metric_key = re.sub(r"[^0-9a-z]+", "", metric_raw.casefold())
        region = _norm(row.get(region_col))
        item = _norm(row.get(item_col))
        block_id = _gap_block_id(region or f"row-{source_row}", item or "missing-item")
        canonical_metric = row_metrics.get(int(row_index)) or _GAP_METRICS.get(metric_key)
        if canonical_metric is None:
            issues.append(
                _issue(
                    "UNKNOWN_GAP_METRIC",
                    "gap.csv contains an unsupported business metric",
                    row=source_row,
                    raw=metric_raw,
                )
                | {
                    "metric": metric_raw,
                    "affected_block_ids": [block_id],
                    "affected_metrics": [metric_raw or "UNKNOWN"],
                }
            )
            continue
        if not region or not item:
            invalid_blocks.add((_material_key(region), _material_key(item)))
            issues.append(
                _issue(
                    "EMPTY_GAP_BUSINESS_KEY",
                    "gap.csv business row has an empty region or item_code",
                    row=source_row,
                )
                | {
                    "metric": canonical_metric,
                    "affected_block_ids": [block_id],
                    "affected_metrics": [canonical_metric],
                }
            )
            continue
        key = (_material_key(region), _material_key(item))
        block_id = _gap_block_id(region, item)
        block = staged.setdefault(
            key,
            {
                "region": region,
                "item": item,
                "block_id": block_id,
                "metrics": {},
                "summary_values": defaultdict(set),
                "rows": {},
            },
        )
        if canonical_metric in block["metrics"]:
            invalid_blocks.add(key)
            issues.append(
                _issue(
                    "DUPLICATE_GAP_METRIC",
                    "gap.csv contains a duplicate region/item/metric row",
                    row=source_row,
                    key=key,
                    source_rows=[block["rows"][canonical_metric], source_row],
                )
                | {
                    "metric": canonical_metric,
                    "affected_block_ids": [block_id],
                    "affected_metrics": [canonical_metric],
                }
            )
            continue
        values: dict[int, int] = {}
        valid = True
        for week, column in week_columns:
            value = _gap_number(
                row.get(column),
                row=source_row,
                column=column,
                block_id=block_id,
                metric=canonical_metric,
                issues=issues,
            )
            if value is None:
                valid = False
                values[week] = 0
            else:
                values[week] = value
        if not valid:
            invalid_blocks.add(key)
        block["metrics"][canonical_metric] = values
        block["rows"][canonical_metric] = source_row
        for summary_name, column in summary_columns.items():
            if column is None or not _norm(row.get(column)):
                continue
            value = _gap_number(
                row.get(column),
                row=source_row,
                column=column,
                block_id=block_id,
                metric=summary_name,
                issues=issues,
            )
            if value is None:
                invalid_blocks.add(key)
                block["summary_values"][summary_name].add(0)
            else:
                block["summary_values"][summary_name].add(value)

    if date_rows != [2]:
        issues.append(
            _issue(
                "INVALID_GAP_DATE_ROW",
                "gap.csv requires exactly one Date helper row at source row 2",
            )
            | {
                "expected_rows": [2],
                "actual_rows": date_rows,
                "affected_metrics": list(_GAP_METRICS.values()),
            }
        )

    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    sign_conventions: dict[str, str] = {}
    for key, block in staged.items():
        block_id = str(block["block_id"])
        missing = sorted(required_metrics - set(block["metrics"]))
        if missing:
            issues.append(
                _issue(
                    "MISSING_GAP_METRICS",
                    "gap.csv business block is missing required metric rows",
                    key=key,
                )
                | {
                    "region": block["region"],
                    "item": block["item"],
                    "missing": missing,
                    "affected_block_ids": [block_id],
                    "affected_metrics": missing,
                }
            )
        summary: dict[str, int] = {}
        for summary_name in _GAP_SUMMARIES:
            values = block["summary_values"].get(summary_name, set())
            if len(values) > 1:
                issues.append(
                    _issue(
                        "CONFLICTING_GAP_SUMMARY",
                        "gap.csv repeats one summary field with conflicting values",
                        key=key,
                    )
                    | {
                        "region": block["region"],
                        "item": block["item"],
                        "field": summary_name,
                        "values": sorted(values),
                        "affected_block_ids": [block_id],
                        "affected_metrics": [summary_name],
                    }
                )
            summary[summary_name] = next(iter(values), 0)
        block["summary"] = summary
        block.pop("summary_values", None)
        if key in invalid_blocks or missing:
            blocks[key] = block
            continue
        signed_errors = _gap_sign_error_count(block, weeks, 1)
        shortage_errors = _gap_sign_error_count(block, weeks, -1)
        sign = -1 if shortage_errors < signed_errors else 1
        convention = "shortage-positive" if sign == -1 else "signed-balance"
        sign_conventions[block_id] = convention
        block["gap_sign_convention"] = convention
        if sign == -1:
            block["metrics"]["GAP"] = {
                week: -int(value) for week, value in block["metrics"]["GAP"].items()
            }
            block["summary"]["total_gap"] = -int(block["summary"]["total_gap"])
        blocks[key] = block

    if not staged:
        issues.append(
            _issue("EMPTY_GAP_BUSINESS_ROWS", "gap.csv contains no business metric rows")
            | {"affected_metrics": list(_GAP_METRICS.values())}
        )
    return {
        "blocks": blocks,
        "aggregate_blocks": {},
        "weeks": weeks,
        "week_kind": week_kind,
        "sign_conventions": sign_conventions,
        "metric_column": metric_column,
        "evidence_level": "weekly",
        "recoveries": tuple(recoveries),
    }, tuple(issues)


def align_gap_reuse_inbound(
    payload: Mapping[str, Any],
    *,
    repair_weeks: int,
    reuse_rate: float,
) -> dict[str, Any]:
    """Align historical GAP warehouse representations to one inbound flow.

    GAP candidates have used ``Arrive`` and ``DismantledSupply`` for the same
    mature-reuse warehouse event, and a smaller family submitted warehouse
    closing inventory instead of an inbound flow.  This adapter considers only
    those three known representations, selects one representation for the whole
    artifact, and exposes it as ``ReuseInbound``.  Selection is artifact-wide so
    a file cannot switch semantics per item merely to improve individual cells.
    Raw metrics remain untouched for S3 and audit evidence.
    """

    weeks = tuple(int(value) for value in payload.get("weeks", ()))
    week_kind = str(
        (payload.get("week_kind") or week_coordinate_kind(weeks))
        if weeks
        else (payload.get("week_kind") or "project")
    )
    source_blocks = payload.get("blocks", {})
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    for key, source in source_blocks.items():
        block = dict(source)
        block["metrics"] = {
            str(metric): dict(values)
            for metric, values in source.get("metrics", {}).items()
        }
        block["summary"] = dict(source.get("summary", {}))
        block["rows"] = dict(source.get("rows", {}))
        blocks[key] = block

    if week_kind not in {"project", "iso"}:
        aligned = dict(payload)
        aligned["blocks"] = blocks
        aligned["inbound_alignment"] = {
            "status": "INVALID_WEEK_KIND",
            "selected": None,
            "source_metrics": [],
            "repair_weeks": int(repair_weeks),
            "reuse_rate": float(reuse_rate),
            "candidate_comparisons": {},
            "recoveries": [dict(value) for value in payload.get("recoveries", ())],
        }
        return aligned

    expected: dict[tuple[str, str, int], float] = defaultdict(float)
    candidate_values: dict[str, dict[tuple[str, str, int], float]] = {
        "dismantled-supply-flow": defaultdict(float),
        "arrive-flow": defaultdict(float),
        "dismantled-supply-inventory": defaultdict(float),
    }
    available = {
        "dismantled-supply-flow": any(
            "DismantledSupply" in block["metrics"] for block in blocks.values()
        ),
        "arrive-flow": any("Arrive" in block["metrics"] for block in blocks.values()),
        "dismantled-supply-inventory": any(
            "DismantledSupply" in block["metrics"]
            and "ReuseConsumed" in block["metrics"]
            for block in blocks.values()
        ),
    }
    for (region, item), block in blocks.items():
        metrics = block["metrics"]
        dismantled = metrics.get("Dismantled", {})
        arrive = metrics.get("Arrive", {})
        supply = metrics.get("DismantledSupply", {})
        outbound = metrics.get("ReuseConsumed", {})
        opening = float(block["summary"].get("initial_inventory", 0))
        for week in weeks:
            try:
                mature_source_week = shift_week_coordinate(
                    week,
                    -int(repair_weeks),
                    week_kind,
                )
            except ValueError:
                mature_source_week = -1
            expected[(region, item, week)] += max(
                0.0,
                float(dismantled.get(mature_source_week, 0)),
            ) * float(reuse_rate)
            candidate_values["dismantled-supply-flow"][(region, item, week)] += float(
                supply.get(week, 0)
            )
            candidate_values["arrive-flow"][(region, item, week)] += float(
                arrive.get(week, 0)
            )
            closing = float(supply.get(week, 0))
            derived_inbound = closing - opening + float(outbound.get(week, 0))
            if derived_inbound < 0:
                available["dismantled-supply-inventory"] = False
            candidate_values["dismantled-supply-inventory"][(region, item, week)] += derived_inbound
            opening = closing

    def similarity(actual: Mapping[tuple[str, str, int], float]) -> dict[str, float]:
        units = set(expected) | set(actual)
        matched = sum(
            min(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0)))
            for key in units
        )
        combined = sum(
            max(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0)))
            for key in units
        )
        return {
            "matched_qty": round(matched, 6),
            "combined_qty": round(combined, 6),
            "similarity": round(matched / combined if combined else 1.0, 12),
        }

    priority = (
        "dismantled-supply-flow",
        "arrive-flow",
        "dismantled-supply-inventory",
    )
    comparisons = {
        name: similarity(candidate_values[name])
        for name in priority
        if available[name]
    }
    selected = max(
        comparisons,
        key=lambda name: (comparisons[name]["similarity"], -priority.index(name)),
        default=None,
    )
    selected_values = candidate_values[selected] if selected else {}
    source_metrics = {
        "dismantled-supply-flow": ("DismantledSupply",),
        "arrive-flow": ("Arrive",),
        "dismantled-supply-inventory": (
            "DismantledSupply",
            "ReuseConsumed",
            "initial_inventory",
        ),
    }
    for (region, item), block in blocks.items():
        block["metrics"]["ReuseInbound"] = {
            week: selected_values.get((region, item, week), 0.0) for week in weeks
        }
        block["reuse_inbound_source"] = selected

    aligned = dict(payload)
    aligned["blocks"] = blocks
    aligned["inbound_alignment"] = {
        "status": "ALIGNED" if selected else "MISSING",
        "selected": selected,
        "source_metrics": list(source_metrics.get(selected, ())),
        "repair_weeks": int(repair_weeks),
        "reuse_rate": float(reuse_rate),
        "candidate_comparisons": comparisons,
        "recoveries": [dict(value) for value in payload.get("recoveries", ())],
    }
    return aligned


def warehouse_week_kind(
    cells: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> str:
    """Return the coordinate family used by one normalized warehouse ledger."""

    return week_coordinate_kind(
        warehouse_key_parts(key)[2] for key in cells
    )


def normalize_timeline_mature_supply(
    frame: pd.DataFrame,
    *,
    repair_weeks: int,
    reuse_rate: float,
    week_kind: str,
) -> tuple[dict[tuple[str, int], float], tuple[dict[str, Any], ...]]:
    """Compile dismantle rows to mature supply in the warehouse's week space.

    Timeline candidates commonly carry both a continuous ``week_num`` and an
    ISO ``mos_weekly_plan``.  Selecting the column is an adapter concern: the
    scorer receives only item/week mature-supply facts in the same coordinate
    family as the selected warehouse artifact.
    """

    item_col = _column(frame, ("item_code",))
    quantity_col = _column(frame, ("required_qty", "quantity", "qty"))
    action_col = _column(frame, ("action",))
    if week_kind == "iso":
        week_col = _column(
            frame,
            ("mos_weekly_plan", "iso_week", "calendar_week", "week_label"),
        )
    elif week_kind == "project":
        week_col = _column(frame, ("week_num", "project_week"))
    else:
        raise ValueError(f"unsupported week_kind: {week_kind!r}")
    if None in {item_col, quantity_col, action_col, week_col}:
        return {}, (
            _issue(
                "MISSING_TIMELINE_MATURE_SUPPLY_COLUMNS",
                f"timeline lacks item/quantity/action/{week_kind}-week columns",
            ),
        )

    output: dict[tuple[str, int], float] = defaultdict(float)
    issues: list[dict[str, Any]] = []
    for row_index, row in frame.iterrows():
        if _norm(row.get(action_col)).casefold() != "dismantle":
            continue
        source_row = int(row_index) + 2
        item = _material_key(row.get(item_col))
        if not item:
            issues.append(
                _issue(
                    "EMPTY_TIMELINE_ITEM",
                    "dismantle timeline row has no item_code",
                    row=source_row,
                    source_rows=[source_row],
                )
            )
            continue
        raw_quantity = row.get(quantity_col)
        try:
            quantity = preserved_quantity(raw_quantity)
        except ValueError as exc:
            unit_id = f"timeline:{item}:row:{source_row}"
            issues.append(
                _issue(
                    "INVALID_QUANTITY",
                    str(exc),
                    row=source_row,
                    column=quantity_col,
                    raw=raw_quantity,
                    unit_id=unit_id,
                    affected_unit_ids=[unit_id],
                    source_rows=[source_row],
                )
            )
            continue
        if not _integer_quantity(raw_quantity):
            unit_id = f"timeline:{item}:row:{source_row}"
            issues.append(
                _issue(
                    "NON_INTEGER_QUANTITY",
                    f"material quantity is not an integer: {_norm(raw_quantity)!r}",
                    row=source_row,
                    column=quantity_col,
                    raw=raw_quantity,
                    unit_id=unit_id,
                    affected_unit_ids=[unit_id],
                    source_rows=[source_row],
                )
            )
        raw_week = row.get(week_col)
        try:
            dismantle_week = _week(raw_week, week_kind)
            mature_week = shift_week_coordinate(
                dismantle_week,
                int(repair_weeks),
                week_kind,
            )
        except ValueError as exc:
            unit_id = f"timeline:{item}:row:{source_row}"
            issues.append(
                _issue(
                    "INVALID_WEEK",
                    str(exc),
                    row=source_row,
                    column=week_col,
                    raw=raw_week,
                    unit_id=unit_id,
                    affected_unit_ids=[unit_id],
                    source_rows=[source_row],
                )
            )
            continue
        output[(item, mature_week)] += abs(float(quantity)) * float(reuse_rate)
    return dict(output), tuple(issues)


def _normalize_reuse_summary_with_issues(
    frame: pd.DataFrame,
) -> tuple[list[dict[str, Any]], tuple[dict[str, Any], ...]]:
    item_positions = _column_positions(frame, ("item_code",))
    metric_positions = _column_positions(frame, ("metric",))
    total_positions = _column_positions(frame, ("total",))
    issues: list[dict[str, Any]] = []
    if not all(len(value) == 1 for value in (item_positions, metric_positions, total_positions)):
        issues.append(
            _issue(
                "AMBIGUOUS_SUMMARY_CONTROL_COLUMN",
                "reuse summary requires exactly one item_code, metric and Total column",
            )
        )
        return [], tuple(issues)
    item_position, metric_position, total_position = (
        item_positions[0],
        metric_positions[0],
        total_positions[0],
    )
    headers = _source_headers(frame)
    grouped_regions: dict[str, list[int]] = defaultdict(list)
    controls = {item_position, metric_position, total_position}
    for position, header in enumerate(headers):
        if position not in controls:
            grouped_regions[_header_key(header)].append(position)
    region_positions: list[int] = []
    for key, positions in grouped_regions.items():
        if len(positions) == 1:
            region_positions.append(positions[0])
        else:
            issues.append(
                {
                    "code": "DUPLICATE_REGION_COLUMN",
                    "message": "reuse summary has an ambiguous duplicate region column",
                    "key": key,
                    "positions": [value + 1 for value in positions],
                }
            )
    rows: list[dict[str, Any]] = []
    for row_index, row in frame.iterrows():
        metric_key = _header_key(row.iloc[metric_position])
        raw_item = row.iloc[item_position]
        summary_key = _header_key(raw_item)
        item_key = (
            summary_key
            if summary_key in {"total", "grandsummary"}
            else _material_key(raw_item)
        )
        if metric_key in _QUANTITY_METRICS:
            values: dict[str, int | None] = {}
            raw_values: dict[str, Any] = {}
            invalid_regions: list[str] = []
            for position in region_positions:
                header = headers[position]
                raw_value = row.iloc[position]
                raw_values[header] = raw_value
                try:
                    values[header] = material_quantity(raw_value)
                except ValueError:
                    values[header] = None
                    invalid_regions.append(header)
            raw_total = row.iloc[total_position]
            try:
                total: int | float | None = material_quantity(raw_total)
                total_valid = True
            except ValueError:
                total = None
                total_valid = False
            metric_type = "quantity"
        else:
            values = {
                headers[position]: row.iloc[position]
                for position in region_positions
            }
            total = row.iloc[total_position]
            raw_values = dict(values)
            raw_total = total
            total_valid = True
            invalid_regions = []
            metric_type = "rate"
        rows.append(
            {
                "row": int(row_index) + 2,
                "item": _norm(raw_item),
                "item_key": item_key,
                "metric": _norm(row.iloc[metric_position]),
                "metric_key": metric_key,
                "metric_type": metric_type,
                "regions": values,
                "raw_regions": raw_values,
                "total": total,
                "raw_total": raw_total,
                "total_valid": total_valid,
                "invalid_regions": invalid_regions,
            }
        )
    return rows, tuple(issues)


def _normalize_reuse_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Compatibility helper for in-memory rule fixtures."""

    rows, _ = _normalize_reuse_summary_with_issues(frame)
    return rows


def _quantity_columns(
    frame: pd.DataFrame,
    schema: str,
    options: Mapping[str, Any],
) -> list[str]:
    configured = options.get("quantity_columns")
    if configured is not None:
        if not isinstance(configured, (list, tuple)):
            raise ValueError("schema_options.quantity_columns must be a list")
        output = []
        for value in configured:
            if not isinstance(value, str):
                raise ValueError("quantity column names must be strings")
            column = _column(frame, (value,))
            if column is not None:
                output.append(column)
        return output
    if schema == "ei.material-substitution":
        return [value for value in (_column(frame, ("target_qty",)), _column(frame, ("sub_qty",))) if value]
    if schema == "ei.final-material":
        return [
            value
            for value in (
                _column(frame, ("required_qty", "quantity")),
                _column(frame, ("original_bom_qty",)),
            )
            if value
        ]
    if schema == "ei.timeline":
        value = _column(frame, ("required_qty", "quantity"))
        return [value] if value else []
    if schema == "ei.recovered-supply":
        value = _column(frame, ("available_qty",))
        return [value] if value else []
    return []


def _quantity_errors(
    frame: Any,
    schema: str,
    options: Mapping[str, Any] | None = None,
) -> tuple[int, tuple[dict[str, Any], ...]]:
    if not isinstance(frame, pd.DataFrame) or schema in {"ei.warehouse", "ei.gap-wide"}:
        return 0, ()
    options = options or {}
    errors: list[dict[str, Any]] = []
    count = 0
    if schema == "ei.reuse-summary":
        metric_col = _column(frame, ("metric",))
        item_col = _column(frame, ("item_code",))
        value_columns = [str(value) for value in frame.columns if str(value) not in {metric_col, item_col}]
        if metric_col is None:
            return 0, ()
        quantity_rows = frame[metric_col].map(_header_key).isin(_QUANTITY_METRICS)
        for column in value_columns:
            series = frame.loc[quantity_rows, column]
            valid = series.map(_integer_quantity)
            invalid = series[~valid]
            count += int(len(invalid))
            for row_index, raw in invalid.iloc[: max(0, 20 - len(errors))].items():
                errors.append(
                    {
                        "row": int(row_index) + 2,
                        "column": column,
                        "raw": _norm(raw),
                    }
                )
        return count, tuple(errors)
    if schema == "ei.gap-wide":
        metric_col = _column(frame, ("week",))
        if metric_col is None:
            return 0, ()
        quantity_columns = [
            str(value)
            for value in frame.columns
            if _header_key(value)
            in {
                "totaldismantled",
                "initialinventory",
                "totalarrive",
                "totalreuse",
                "totaldemand",
                "totalgap",
            }
            or re.fullmatch(r"wk[0-9]+", _header_key(value))
        ]
        business_rows = frame[metric_col].map(_header_key).ne("date")
        for column in quantity_columns:
            series = frame.loc[business_rows, column]
            nonblank = series.map(_norm).ne("")
            invalid = series[nonblank & ~series.map(_integer_quantity)]
            count += int(len(invalid))
            for row_index, raw in invalid.iloc[: max(0, 20 - len(errors))].items():
                errors.append(
                    {
                        "row": int(row_index) + 2,
                        "column": column,
                        "raw": _norm(raw),
                    }
                )
        return count, tuple(errors)
    for column in _quantity_columns(frame, schema, options):
        series = frame[column]
        valid = series.map(_integer_quantity)
        invalid = series[~valid]
        count += int(len(invalid))
        for row_index, raw in invalid.iloc[: max(0, 20 - len(errors))].items():
            errors.append(
                {
                    "row": int(row_index) + 2,
                    "column": column,
                    "raw": _norm(raw),
                }
            )
    return count, tuple(errors)


def _normalize_table(
    frame: Any,
    role: str,
    schema: str,
    options: Mapping[str, Any] | None = None,
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    # Imported lazily so the shared parsing algorithms remain dependency-free
    # while product modules can reuse them without an import cycle.
    from .products import normalize_product

    return normalize_product(role, schema, frame, options or {})


_REGION_VALUE_HEADER_KEYS = {
    "region",
    "regionid",
    "region区域",
    "区域",
    "区域名称",
}


def _apply_region_aliases(
    table: Any,
    options: Mapping[str, Any],
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Apply question-local region identities before schema/rule processing.

    The physical value is retained in non-scoring resolution diagnostics.  The
    table exposed to every downstream adapter and legacy rule contains only the
    configured canonical display value.
    """

    raw_aliases = options.get("region_aliases")
    if raw_aliases is None:
        return table, ()
    if not isinstance(raw_aliases, Mapping) or not raw_aliases:
        raise ValueError("region_aliases must be a non-empty mapping")
    aliases: dict[str, tuple[str, str]] = {}
    for raw_source, raw_target in raw_aliases.items():
        source = _norm(raw_source)
        target = _norm(raw_target)
        source_key = _header_key(source)
        if not source_key or not target or not _header_key(target):
            raise ValueError("region_aliases requires non-empty string identities")
        if source_key in aliases:
            raise ValueError("region_aliases sources collide after normalization")
        aliases[source_key] = (source, target)

    applied_count = 0
    examples: list[dict[str, Any]] = []

    def record(
        *,
        raw: str,
        normalized: str,
        location: str,
        sheet: str | None,
        row: int | None = None,
    ) -> None:
        nonlocal applied_count
        applied_count += 1
        if len(examples) >= 20:
            return
        example: dict[str, Any] = {
            "location": location,
            "raw_region": raw,
            "normalized_region": normalized,
        }
        if sheet is not None:
            example["sheet"] = sheet
        if row is not None:
            example["row"] = row
        examples.append(example)

    def normalize_frame(frame: pd.DataFrame, *, sheet: str | None) -> pd.DataFrame:
        source_headers = list(_source_headers(frame))
        normalized_headers = list(source_headers)
        changed_header_positions: set[int] = set()
        for position, raw_header in enumerate(source_headers):
            alias = aliases.get(_header_key(raw_header))
            if alias is None:
                continue
            _, target = alias
            if _norm(raw_header) == target:
                continue
            normalized_headers[position] = target
            changed_header_positions.add(position)

        if changed_header_positions:
            positions_by_key: dict[str, list[int]] = defaultdict(list)
            for position, header in enumerate(normalized_headers):
                positions_by_key[_header_key(header)].append(position)
            for positions in positions_by_key.values():
                if len(positions) > 1 and any(
                    position in changed_header_positions for position in positions
                ):
                    raw_values = [source_headers[position] for position in positions]
                    raise ValueError(
                        "region alias normalization creates duplicate columns: "
                        f"{raw_values!r}"
                    )

        output = frame.copy()
        if changed_header_positions:
            output = _attach_source_headers(output, normalized_headers)
            for position in sorted(changed_header_positions):
                record(
                    raw=_norm(source_headers[position]),
                    normalized=_norm(normalized_headers[position]),
                    location="column_header",
                    sheet=sheet,
                )

        effective_headers = _source_headers(output)
        for position, header in enumerate(effective_headers):
            if _header_key(header) not in _REGION_VALUE_HEADER_KEYS:
                continue
            for row_position in range(len(output)):
                raw_value = output.iat[row_position, position]
                alias = aliases.get(_header_key(raw_value))
                if alias is None:
                    continue
                _, target = alias
                if _norm(raw_value) == target:
                    continue
                output.iat[row_position, position] = target
                record(
                    raw=_norm(raw_value),
                    normalized=target,
                    location=_norm(header),
                    sheet=sheet,
                    row=row_position + 2,
                )
        return output

    if isinstance(table, pd.DataFrame):
        normalized_table: Any = normalize_frame(table, sheet=None)
    elif isinstance(table, Mapping):
        normalized_table = {
            name: normalize_frame(frame, sheet=str(name))
            if isinstance(frame, pd.DataFrame)
            else frame
            for name, frame in table.items()
        }
    else:
        normalized_table = table

    diagnostics = (
        {
            "code": "REGION_ALIAS_APPLIED",
            "score_effect": "none",
            "applied_count": applied_count,
            "mapping": {
                source: target for source, target in raw_aliases.items()
            },
            "examples": examples,
        },
    ) if applied_count else ()
    return normalized_table, diagnostics


def _merge_region_alias_diagnostics(
    *groups: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Expose raw-table and canonical-product aliasing as one audit record."""

    matching = [
        dict(value)
        for group in groups
        for value in group
        if value.get("code") == "REGION_ALIAS_APPLIED"
    ]
    passthrough = [
        value
        for group in groups
        for value in group
        if value.get("code") != "REGION_ALIAS_APPLIED"
    ]
    if not matching:
        return tuple(passthrough)
    combined = dict(matching[0])
    combined["applied_count"] = sum(
        int(value.get("applied_count", 0)) for value in matching
    )
    combined["examples"] = [
        example
        for value in matching
        for example in value.get("examples", ())
    ][:20]
    return (combined, *passthrough)


def _common_parent_suffix(left: Path, right: Path) -> int:
    left_parts = tuple(value.casefold() for value in left.parts)
    right_parts = tuple(value.casefold() for value in right.parts)
    count = 0
    for a, b in zip(reversed(left_parts), reversed(right_parts)):
        if a != b:
            break
        count += 1
    return count


def _resolved_artifact(
    spec: ArtifactSpec,
    path: Path,
    *,
    status: str,
    candidates: tuple[ArtifactCandidate, ...] = (),
    read_options: Mapping[str, Any] | None = None,
    normalization_options: Mapping[str, Any] | None = None,
    preloaded_table: Any = _UNSET,
    resolution_diagnostics: tuple[dict[str, Any], ...] = (),
) -> ArtifactResolution:
    from .io import read_table

    try:
        table = (
            read_table(path, read_options or spec.schema_options)
            if preloaded_table is _UNSET
            else preloaded_table
        )
        table, region_diagnostics = _apply_region_aliases(
            table,
            spec.schema_options,
        )
        schema_issues = _schema_issues(table, spec.schema, spec.schema_options)
        quantity_count, quantity_errors = _quantity_errors(table, spec.schema, spec.schema_options)
        normalized, issues = _normalize_table(
            table,
            spec.role,
            spec.schema,
            spec.schema_options
            if normalization_options is None
            else normalization_options,
        )
        # Some legacy workbook shapes carry the region identity in a data
        # label that only becomes a canonical ``region`` column after product
        # normalization.  Apply the same question-local identity map at both
        # adapter boundaries so every downstream rule sees one representation.
        normalized, normalized_region_diagnostics = _apply_region_aliases(
            normalized,
            spec.schema_options,
        )
        region_diagnostics = _merge_region_alias_diagnostics(
            region_diagnostics,
            normalized_region_diagnostics,
        )
    except Exception as exc:  # noqa: BLE001
        return ArtifactResolution(
            role=spec.role,
            status="PARSE_ERROR",
            selected_path=path,
            candidates=candidates,
            error=f"{type(exc).__name__}: {exc}",
            resolution_diagnostics=resolution_diagnostics,
        )
    quantity_issues = tuple(
        _issue(
            "NON_INTEGER_QUANTITY",
            "physical material quantity is not an exact integer",
            row=value.get("row"),
            column=value.get("column"),
            raw=value.get("raw"),
        )
        for value in quantity_errors
    )
    combined = tuple(schema_issues) + tuple(issues) + quantity_issues
    warehouse_quantity_errors = tuple(
        {key: value for key, value in issue.items() if key in {"row", "column", "raw"}}
        for issue in issues
        if issue.get("code") == "NON_INTEGER_QUANTITY"
    )
    if spec.schema == "ei.warehouse":
        quantity_errors = warehouse_quantity_errors[:20]
        quantity_count = sum(1 for value in issues if value.get("code") == "NON_INTEGER_QUANTITY")
    return ArtifactResolution(
        role=spec.role,
        status=status,
        selected_path=path,
        candidates=candidates,
        table=table,
        normalized=normalized,
        validation_issues=combined,
        quantity_error_count=quantity_count,
        quantity_errors=quantity_errors,
        resolution_diagnostics=(
            tuple(resolution_diagnostics) + tuple(region_diagnostics)
        ),
    )


def _candidate_resolution(
    spec: ArtifactSpec,
    run_dir: Path,
    roots: tuple[Path, ...],
    discovered: Mapping[str, set[Path]] | None = None,
    normalization_options: Mapping[str, Any] | None = None,
) -> ArtifactResolution:
    from .discovery import discover_candidate_files
    from .io import read_table

    canonical = (run_dir / spec.path).resolve()

    def run_relative(value: Path) -> str:
        try:
            return value.resolve().relative_to(run_dir.resolve()).as_posix()
        except ValueError:
            return value.as_posix()

    index = (
        discovered
        if discovered is not None
        else discover_candidate_files(roots, set(spec.filenames))
    )
    found = {
        value
        for filename in spec.filenames
        for value in index.get(filename.casefold(), set())
    }
    candidates: list[ArtifactCandidate] = []
    preflight_results: dict[Path, ArtifactResolution] = {}
    prompt_name = spec.filenames[0].casefold()
    for value in sorted(found, key=lambda item: item.as_posix().casefold()):
        error = ""
        try:
            table = read_table(value, spec.schema_options)
            coverage = _required_coverage(table, spec.schema, spec.schema_options)
            usable = not (
                isinstance(table, pd.DataFrame)
                and (table.empty or len(table.columns) == 0)
            )
            if not usable:
                error = "HEADER_ONLY"
            else:
                # Candidate eligibility must cross the same product-adapter
                # boundary as the final selection.  Validation issues remain
                # evidence on a readable product; only an exception that makes
                # normalization impossible rejects the physical candidate.
                preflight = _resolved_artifact(
                    spec,
                    value,
                    status=(
                        "SELECTED_CANONICAL"
                        if value == canonical
                        else "SELECTED_FALLBACK"
                    ),
                    normalization_options=normalization_options,
                    preloaded_table=table,
                )
                preflight_results[value] = preflight
                usable = preflight.usable
                if not usable:
                    error = preflight.error or preflight.status
        except Exception as exc:  # noqa: BLE001
            coverage = 0.0
            usable = False
            error = f"{type(exc).__name__}: {exc}"
        candidates.append(
            ArtifactCandidate(
                path=value,
                required_coverage=round(coverage, 6),
                prompt_filename=value.name.casefold() == prompt_name,
                common_parent_suffix=_common_parent_suffix(value.parent, canonical.parent),
                usable=usable,
                error=error,
                canonical=value == canonical,
            )
        )

    def selection_rank(item: ArtifactCandidate) -> tuple[float | int, ...]:
        # A complete, readable Prompt path is authoritative.  An incomplete
        # canonical file may still fall back to a structurally complete copy.
        canonical_ready = (
            item.canonical and item.usable and item.required_coverage >= 1.0
        )
        return (
            -int(canonical_ready),
            -item.required_coverage,
            -int(item.prompt_filename),
            -item.common_parent_suffix,
        )

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                *selection_rank(item),
                item.path.as_posix().casefold(),
            ),
        )
    )
    usable_candidates = tuple(value for value in ordered if value.usable)
    if not usable_candidates:
        if len(ordered) == 1 and ordered[0].path in preflight_results:
            return replace(
                preflight_results[ordered[0].path],
                candidates=ordered,
            )
        status = "MISSING" if not ordered else "SCHEMA_MISMATCH"
        if ordered and all(value.error == "HEADER_ONLY" for value in ordered):
            status = "HEADER_ONLY"
        elif ordered and all(value.error and value.error != "HEADER_ONLY" for value in ordered):
            status = "PARSE_ERROR"
        return ArtifactResolution(
            role=spec.role,
            status=status,
            selected_path=None,
            candidates=ordered,
            error=(
                f"no {spec.role} candidate under configured artifact roots"
                if not ordered
                else f"no structurally usable {spec.role} candidate"
            ),
        )
    complete_canonical = next(
        (
            value
            for value in usable_candidates
            if value.canonical and value.required_coverage >= 1.0
        ),
        None,
    )
    complete_fallbacks = tuple(
        value
        for value in usable_candidates
        if not value.canonical and value.required_coverage >= 1.0
    )

    if complete_canonical is not None:
        # A fully parseable Prompt path is authoritative.  Different lower-rank
        # copies are retained as evidence but cannot make it ambiguous.
        selected = complete_canonical
    elif complete_fallbacks:
        # A missing or unusable Prompt path falls back by structural evidence
        # and a stable path order.  Candidate contents are not identity data.
        selected = min(
            complete_fallbacks,
            key=lambda value: (
                -int(value.prompt_filename),
                -value.common_parent_suffix,
                value.path.as_posix().casefold(),
            ),
        )
    else:
        # Preserve partial-evidence behavior when no complete product exists.
        selected = usable_candidates[0]
    resolution_diagnostics: list[dict[str, Any]] = [
        {
            "code": "REJECTED_CANDIDATE",
            "score_effect": "none",
            "path": run_relative(value.path),
            "canonical": value.canonical,
            "reason": value.error,
        }
        for value in ordered
        if not value.usable and value.error
    ]
    if selected.path != canonical:
        resolution_diagnostics.append(
            {
                "code": "ARTIFACT_PATH_MISMATCH",
                "score_effect": "none",
                "canonical_path": run_relative(canonical),
                "selected_path": run_relative(selected.path),
            }
        )
    selected_resolution = preflight_results[selected.path]
    return replace(
        selected_resolution,
        status=(
            "SELECTED_CANONICAL"
            if selected.path == canonical
            else "SELECTED_FALLBACK"
        ),
        candidates=ordered,
        resolution_diagnostics=(
            tuple(resolution_diagnostics)
            + tuple(selected_resolution.resolution_diagnostics)
        ),
    )


def _question_resolution(
    spec: ArtifactSpec,
    question_dir: Path,
    repository_root: Path,
    question_id: str,
    normalization_options: Mapping[str, Any] | None = None,
    *,
    allow_legacy_shared_data: bool = False,
) -> ArtifactResolution:
    from .io import read_question_table

    location = locate_question_artifact(
        repository_root,
        question_dir,
        question_id,
        spec.path,
        allow_legacy_shared_data=allow_legacy_shared_data,
    )
    path = location.selected_path
    if path is None:
        attempted = ", ".join(str(value) for value in location.candidates)
        return ArtifactResolution(
            role=spec.role,
            status="MISSING",
            selected_path=None,
            error=f"configured question artifact is missing; tried: {attempted}",
        )
    read_options = dict(spec.schema_options)
    if path.suffix.casefold() in {".xlsx", ".xls"} and "sheet_name" not in read_options:
        # Question workbooks are authoritative inputs.  Load every sheet once so
        # pure rules can select the prompt-relevant table without reopening files.
        read_options["sheet_name"] = None
    try:
        table = read_question_table(
            str(path),
            json.dumps(read_options, ensure_ascii=False, sort_keys=True),
        )
    except Exception as exc:  # noqa: BLE001
        return ArtifactResolution(
            role=spec.role,
            status="PARSE_ERROR",
            selected_path=path,
            error=f"{type(exc).__name__}: {exc}",
        )
    return _resolved_artifact(
        spec,
        path,
        status="SELECTED_CANONICAL",
        read_options=read_options,
        normalization_options=normalization_options,
        preloaded_table=table,
    )


def resolve_artifacts(
    profile: QuestionProfile,
    run_dir: Path,
    repository_root: Path,
    *,
    roles: Iterable[str] | None = None,
    prepared_question_artifacts: Mapping[str, ArtifactResolution] | None = None,
) -> ArtifactBundle:
    """Resolve selected roles once; scorers must not discover files again."""

    from .discovery import discover_candidate_files, question_directory

    run = run_dir.resolve()
    roots = tuple((run / value).resolve() for value in profile.artifact_roots)
    question_dir = (
        profile.question_dir.resolve()
        if profile.question_dir is not None
        else question_directory(repository_root.resolve(), profile.question_id)
    )
    selected = set(roles) if roles is not None else set(profile.artifacts)
    unknown = selected - set(profile.artifacts)
    if unknown:
        raise ValueError(
            f"artifact roles are not configured for {profile.question_id}: {sorted(unknown)}"
        )
    candidate_names = {
        filename
        for spec in profile.artifacts.values()
        if spec.role in selected and spec.source == "candidate"
        for filename in spec.filenames
    }
    discovered = discover_candidate_files(roots, candidate_names)
    normalization_options: dict[str, Any] = {}
    effective_delivery = profile.components.get("effective-delivery")
    if effective_delivery is not None:
        normalization_options["_effective_delivery"] = dict(
            effective_delivery.parameters
        )
    resolutions: dict[str, ArtifactResolution] = {}
    for role, spec in profile.artifacts.items():
        if role not in selected:
            continue
        if spec.source == "candidate":
            resolutions[role] = _candidate_resolution(
                spec,
                run,
                roots,
                discovered,
                {**spec.schema_options, **normalization_options},
            )
        else:
            prepared = (
                prepared_question_artifacts.get(role)
                if prepared_question_artifacts is not None
                else None
            )
            resolutions[role] = prepared or _question_resolution(
                spec,
                question_dir,
                repository_root.resolve(),
                profile.question_id,
                {**spec.schema_options, **normalization_options},
                allow_legacy_shared_data=profile.legacy_shared_data,
            )
    return ArtifactBundle(run_dir=run, artifact_roots=roots, artifacts=resolutions)


def prepare_question_artifacts(
    profile: QuestionProfile,
    repository_root: Path,
    *,
    roles: Iterable[str] | None = None,
) -> dict[str, ArtifactResolution]:
    """Resolve and normalize immutable question evidence once for a run group."""

    from .discovery import question_directory

    repository = repository_root.resolve()
    question_dir = (
        profile.question_dir.resolve()
        if profile.question_dir is not None
        else question_directory(repository, profile.question_id)
    )
    available = {
        role for role, spec in profile.artifacts.items() if spec.source == "question"
    }
    selected = set(roles) if roles is not None else available
    unknown = selected - available
    if unknown:
        raise ValueError(
            f"question artifacts are not configured for {profile.question_id}: {sorted(unknown)}"
        )
    normalization_options: dict[str, Any] = {}
    effective_delivery = profile.components.get("effective-delivery")
    if effective_delivery is not None:
        normalization_options["_effective_delivery"] = dict(
            effective_delivery.parameters
        )
    return {
        role: _question_resolution(
            profile.artifacts[role],
            question_dir,
            repository,
            profile.question_id,
            {
                **profile.artifacts[role].schema_options,
                **normalization_options,
            },
            allow_legacy_shared_data=profile.legacy_shared_data,
        )
        for role in profile.artifacts
        if role in selected
    }
