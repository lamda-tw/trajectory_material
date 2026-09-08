"""Strict prepared-master comparison against a historical site-action authority."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

import pandas as pd

from simulation.ei.core.adapters import parse_iso_week

from ..common import _key, _norm, _number


_AUTHORITY_COLUMNS = (
    "site_name",
    "site_action",
    "mos_weekly_plan",
    "week_num",
    "region",
    "site_count",
)
_PREPARED_COLUMNS = ("region", "action", "month", "master_count")
_ACTIONS = frozenset({"install", "dismantle"})


def _invalid(message: str, **details: Any) -> dict[str, Any]:
    return {"message": message, **details}


def _authority_totals(
    frame: pd.DataFrame,
) -> tuple[dict[tuple[str, str, int], int], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if tuple(str(column) for column in frame.columns) != _AUTHORITY_COLUMNS:
        return {}, [
            _invalid(
                "historical authority columns do not match the prompt contract",
                expected=list(_AUTHORITY_COLUMNS),
                actual=[str(column) for column in frame.columns],
            )
        ]
    output: dict[tuple[str, str, int], int] = defaultdict(int)
    seen_actions: dict[tuple[str, str], int] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        site = _norm(row.get("site_name"))
        action = _norm(row.get("site_action")).casefold()
        region = _norm(row.get("region"))
        site_count = _number(row.get("site_count"))
        row_errors: list[str] = []
        if not site:
            row_errors.append("EMPTY_SITE")
        if action not in _ACTIONS:
            row_errors.append("INVALID_ACTION")
        if not region:
            row_errors.append("EMPTY_REGION")
        if site_count != 1:
            row_errors.append("SITE_COUNT_NOT_ONE")
        action_key = (site.casefold(), action)
        if action_key in seen_actions:
            row_errors.append("DUPLICATE_SITE_ACTION")
        try:
            iso_week = parse_iso_week(row.get("mos_weekly_plan"))
            monday = date.fromisocalendar(iso_week // 100, iso_week % 100, 1)
            period = monday.year * 100 + monday.month
        except ValueError:
            period = 0
            row_errors.append("INVALID_ISO_WEEK")
        if row_errors:
            errors.append(
                _invalid(
                    "invalid historical site-action authority row",
                    row=position,
                    reasons=row_errors,
                )
            )
            continue
        seen_actions[action_key] = position
        output[(_key(region), action, period)] += 1
    if not output:
        errors.append(_invalid("historical authority produced no monthly action totals"))
    return dict(output), errors


def _prepared_totals(
    frame: pd.DataFrame,
) -> tuple[dict[tuple[str, str, int], int], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if tuple(str(column) for column in frame.columns) != _PREPARED_COLUMNS:
        return {}, [
            _invalid(
                "prepared master columns do not match the prompt contract",
                expected=list(_PREPARED_COLUMNS),
                actual=[str(column) for column in frame.columns],
            )
        ]
    output: dict[tuple[str, str, int], int] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        region = _norm(row.get("region"))
        action = _norm(row.get("action")).casefold()
        month = _norm(row.get("month"))
        count = _number(row.get("master_count"))
        match = re.fullmatch(r"(20\d{2})M(\d{1,2})", month)
        row_errors: list[str] = []
        if not region:
            row_errors.append("EMPTY_REGION")
        if action not in _ACTIONS:
            row_errors.append("INVALID_ACTION")
        if match is None or not 1 <= int(match.group(2)) <= 12:
            row_errors.append("INVALID_NATURAL_MONTH")
            period = 0
        else:
            period = int(match.group(1)) * 100 + int(match.group(2))
        if (
            count is None
            or not float(count).is_integer()
            or int(count) < 0
        ):
            row_errors.append("INVALID_MASTER_COUNT")
        key = (_key(region), action, period)
        if key in output:
            row_errors.append("DUPLICATE_REGION_ACTION_MONTH")
        if row_errors:
            errors.append(
                _invalid(
                    "invalid prepared master row",
                    row=position,
                    reasons=row_errors,
                )
            )
            continue
        output[key] = int(count)
    if not output:
        errors.append(_invalid("prepared master produced no monthly action totals"))
    return output, errors


def compare_prepared_master(
    authority: pd.DataFrame,
    prepared: pd.DataFrame,
) -> dict[str, Any]:
    """Return a deterministic binary gate plus coordinate-level differences."""

    expected, authority_errors = _authority_totals(authority)
    actual, prepared_errors = _prepared_totals(prepared)
    expected_keys = set(expected)
    actual_keys = set(actual)
    keys = sorted(expected_keys | actual_keys)
    differences = [
        {
            "region": key[0],
            "action": key[1],
            "period": key[2],
            "expected": int(expected.get(key, 0)),
            "actual": int(actual.get(key, 0)),
        }
        for key in keys
        if (
            key not in expected_keys
            or key not in actual_keys
            or int(expected.get(key, 0)) != int(actual.get(key, 0))
        )
    ]
    expected_actions = sorted({key[1] for key in expected})
    actual_actions = sorted({key[1] for key in actual})
    expected_periods = sorted({key[2] for key in expected})
    actual_periods = sorted({key[2] for key in actual})
    missing_coordinates = sorted(expected_keys - actual_keys)
    extra_coordinates = sorted(actual_keys - expected_keys)
    passed = not authority_errors and not prepared_errors and not differences
    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "gate_rate": 1.0 if passed else 0.0,
        "comparison_key": ["region", "action", "YYYYMM"],
        "authority_schema": list(_AUTHORITY_COLUMNS),
        "prepared_schema": list(_PREPARED_COLUMNS),
        "authority_errors": authority_errors[:50],
        "prepared_errors": prepared_errors[:50],
        "expected_coordinate_count": len(expected),
        "actual_coordinate_count": len(actual),
        "expected_actions": expected_actions,
        "actual_actions": actual_actions,
        "action_universe_match": expected_actions == actual_actions,
        "expected_periods": expected_periods,
        "actual_periods": actual_periods,
        "period_universe_match": expected_periods == actual_periods,
        "missing_coordinate_count": len(missing_coordinates),
        "extra_coordinate_count": len(extra_coordinates),
        "missing_coordinates": [
            {"region": key[0], "action": key[1], "period": key[2]}
            for key in missing_coordinates[:100]
        ],
        "extra_coordinates": [
            {"region": key[0], "action": key[1], "period": key[2]}
            for key in extra_coordinates[:100]
        ],
        "difference_count": len(differences),
        "differences": differences[:100],
    }


__all__ = ["compare_prepared_master"]
