"""Warehouse balance calculations shared by S2, S3, and S4."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from simulation.ei.core.adapters import (
    warehouse_key_parts,
    warehouse_series_key,
)


def _warehouse_balance(cells: Mapping[tuple[Any, ...], Mapping[str, int | float]], *, allow_negative_closing: bool, forced_invalid_keys: set[tuple[Any, ...]] | None=None) -> tuple[float, dict[str, Any]]:
    total = 0
    valid = 0
    previous: dict[tuple[str, ...], tuple[int, int]] = {}
    failures: list[dict[str, Any]] = []
    ordered = sorted(cells.items(), key=lambda value: (*warehouse_key_parts(value[0])[:2], warehouse_key_parts(value[0])[2]))
    forced_invalid = forced_invalid_keys or set()
    for key, cell in ordered:
        dimensions, item, week = warehouse_key_parts(key)
        series = warehouse_series_key(key)
        total += 1
        opening = float(cell['opening'])
        inbound = float(cell['inbound'])
        outbound = float(cell['outbound'])
        closing = float(cell['closing'])
        expected_opening = cell.get('continuity_expected')
        if expected_opening is None and series in previous:
            expected_opening = previous[series][1]
        continuity = expected_opening is None or opening == float(expected_opening)
        identity = closing == opening + inbound - outbound
        sign = inbound >= 0 and outbound >= 0 and (allow_negative_closing or (opening >= 0 and closing >= 0))
        source_valid = key not in forced_invalid
        valid += int(continuity and identity and sign and source_valid)
        if not (continuity and identity and sign and source_valid):
            codes = []
            if not source_valid:
                codes.append('SOURCE_VALIDATION_ISSUE')
            if not continuity:
                codes.append('OPENING_DISCONTINUITY')
            if not identity:
                codes.append('BALANCE_IDENTITY_MISMATCH')
            if not sign:
                codes.append('INVALID_QUANTITY_SIGN')
            failures.append({'key': list(key), 'dimensions': list(dimensions), 'item': item, 'week': week, 'errors': codes, 'opening': opening, 'expected_opening': expected_opening, 'inbound': inbound, 'outbound': outbound, 'closing': closing, 'expected_closing': opening + inbound - outbound})
        previous[series] = (week, closing)
    return (valid / total if total else 0.0, {'cells': total, 'valid': valid, 'invalid': total - valid, 'failures': failures})


def _warehouse_field_by_item_week(cells: Mapping[tuple[Any, ...], Mapping[str, int | float]], field: str) -> dict[tuple[str, int], float]:
    output: dict[tuple[str, int], float] = defaultdict(float)
    for key, cell in cells.items():
        _, item, week = warehouse_key_parts(key)
        output[item, week] += float(cell.get(field, 0))
    return dict(output)
