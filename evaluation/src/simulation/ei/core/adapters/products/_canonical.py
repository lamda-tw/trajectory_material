"""Shared primitives for canonical tabular product adapters.

The physical reader deliberately preserves source headers and workbook sheets.
These helpers form the next boundary: a product module selects one relevant
table and projects prompt-specific aliases into a stable column contract.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, TypeAlias

import pandas as pd

from .._shared import _column, _header_key, _issue, _norm, _source_headers


TabularSource: TypeAlias = pd.DataFrame | Mapping[str, pd.DataFrame]


def effective_delivery_options(options: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return profile parameters injected solely for product normalization."""

    value = options.get("_effective_delivery")
    return value if isinstance(value, Mapping) else {}


def column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    """Resolve an explicitly declared source alias.

    Exact normalized aliases remain the primary contract.  A unique containment
    match is accepted for legacy bilingual headers (for example
    ``Region/区域``); ambiguous containment matches are rejected.
    """

    aliases = tuple(str(value) for value in aliases)
    direct = _column(frame, aliases)
    if direct is not None:
        return direct
    wanted = tuple(value for value in (_header_key(alias) for alias in aliases) if value)
    matches: list[str] = []
    for position, header in enumerate(_source_headers(frame)):
        actual = _header_key(header)
        if any(alias in actual or actual in alias for alias in wanted):
            matches.append(str(frame.columns[position]))
    return matches[0] if len(matches) == 1 else None


def exact_column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    """Resolve only an exact normalized alias.

    Quantity columns use this stricter boundary because generic tokens such as
    ``quantity``/``数量`` are valid signed-column names but are also suffixes of
    action-specific headers.  Containment would duplicate one physical value
    across incompatible canonical quantity semantics.
    """

    return _column(frame, tuple(str(value) for value in aliases))


def _frames(source: TabularSource, *, sheet_hint: str = "") -> tuple[tuple[str, pd.DataFrame], ...]:
    if isinstance(source, pd.DataFrame):
        return (("", source),)
    if not isinstance(source, Mapping):
        raise TypeError(f"unsupported tabular source: {type(source).__name__}")
    values = tuple(
        (str(name), frame)
        for name, frame in source.items()
        if isinstance(frame, pd.DataFrame)
    )
    hint = _norm(sheet_hint).casefold()
    return tuple(
        sorted(
            values,
            key=lambda value: (
                0 if hint and hint in value[0].casefold() else 1,
                value[0].casefold(),
            ),
        )
    )


def select_frame(
    source: TabularSource,
    required_aliases: Iterable[Iterable[str]],
    *,
    sheet_hint: str = "",
) -> tuple[pd.DataFrame, str, tuple[dict[str, Any], ...]]:
    """Select the deterministic workbook table with greatest contract coverage."""

    groups = tuple(tuple(group) for group in required_aliases)
    candidates = _frames(source, sheet_hint=sheet_hint)
    if not candidates:
        return (
            pd.DataFrame(dtype=object),
            "",
            (
                _issue(
                    "CANONICAL_TABLE_MISSING",
                    "resolved artifact contains no tabular worksheet",
                ),
            ),
        )
    ranked = sorted(
        enumerate(candidates),
        key=lambda value: (
            -sum(column(value[1][1], group) is not None for group in groups),
            value[0],
        ),
    )
    _, (sheet, frame) = ranked[0]
    coverage = sum(column(frame, group) is not None for group in groups)
    issues: tuple[dict[str, Any], ...] = ()
    if groups and coverage < len(groups):
        issues = (
            _issue(
                "CANONICAL_TABLE_PARTIAL_MATCH",
                "selected worksheet does not cover every canonical discriminator",
                raw=sheet,
            ),
        )
    return frame, sheet, issues


def project_columns(
    frame: pd.DataFrame,
    fields: Mapping[str, Iterable[str]],
    *,
    required: Iterable[str] = (),
    source_sheet: str = "",
) -> tuple[pd.DataFrame, tuple[dict[str, Any], ...]]:
    """Project one source table into an exact canonical DataFrame contract."""

    output = pd.DataFrame(index=frame.index)
    output["source_row"] = [position + 2 for position in range(len(frame))]
    resolved: dict[str, str | None] = {}
    for name, aliases in fields.items():
        resolved[name] = column(frame, aliases)
        output[name] = frame[resolved[name]] if resolved[name] is not None else ""
    output = output.reset_index(drop=True)
    if source_sheet:
        output.attrs["source_sheet"] = source_sheet
    issues = tuple(
        _issue(
            "MISSING_CANONICAL_COLUMN",
            "source lacks a column required by the canonical product contract",
            column=name,
            raw="|".join(str(value) for value in fields[name]),
        )
        for name in required
        if resolved.get(name) is None
    )
    return output, issues


def number(value: Any) -> float | None:
    text = _norm(value)
    if not text:
        return None
    try:
        parsed = float(text.replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    if not pd.notna(parsed):
        return None
    return parsed / 100.0 if "%" in text else parsed


def month_number(value: Any) -> int | None:
    numeric = number(value)
    if numeric is not None and float(numeric).is_integer() and 1 <= numeric <= 12:
        return int(numeric)
    match = re.fullmatch(r"M(\d{1,2})", _norm(value), re.I)
    if match and 1 <= int(match.group(1)) <= 12:
        return int(match.group(1))
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed.month)


__all__ = [
    "TabularSource",
    "column",
    "exact_column",
    "effective_delivery_options",
    "month_number",
    "number",
    "project_columns",
    "select_frame",
]
