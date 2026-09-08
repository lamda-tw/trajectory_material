"""Canonical adapter for the authoritative monthly master-plan curve."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

import pandas as pd

from .._shared import (
    _attach_source_headers,
    _issue,
    _norm,
    _source_headers,
    parse_iso_week,
)
from ._canonical import (
    TabularSource,
    column,
    effective_delivery_options,
    number,
    select_frame,
)


NormalizedMasterPlan = pd.DataFrame
_COLUMNS = (
    "source_row",
    "region",
    "site_type",
    "period",
    "month",
    "planned_count",
)


def _calendar_coordinates(year: int, month: int) -> tuple[int, int] | None:
    if not 2000 <= year <= 2099 or not 1 <= month <= 12:
        return None
    return year * 100 + month, month


def _project_month_coordinates(
    project_month: int,
    *,
    planning_year: int | None,
    project_start_month: int,
) -> tuple[int, int] | None:
    if planning_year is None or project_month < 1 or not 1 <= project_start_month <= 12:
        return None
    zero_based = project_start_month - 1 + project_month - 1
    year = planning_year + zero_based // 12
    month = zero_based % 12 + 1
    return _calendar_coordinates(year, month)


def _month_coordinates(
    value: Any,
    *,
    planning_year: int | None,
    project_start_month: int,
) -> tuple[int, int] | None:
    """Return ``(YYYYMM, calendar_month)`` without discarding source years."""

    text = _norm(value)
    if not text:
        return None

    # Explicit year/month labels are calendar coordinates, not project-month
    # ordinals. This form is used by the PIP prompt when it describes YYYYM<n>.
    match = re.fullmatch(r"(20\d{2})\s*[-_/]?\s*M\s*(\d{1,2})", text, re.I)
    if match:
        return _calendar_coordinates(int(match.group(1)), int(match.group(2)))

    # A bare M<n> is a project-month ordinal and therefore starts at the
    # configured project month, rolling into the next year when necessary.
    match = re.fullmatch(r"M\s*(\d{1,3})", text, re.I)
    if match:
        return _project_month_coordinates(
            int(match.group(1)),
            planning_year=planning_year,
            project_start_month=project_start_month,
        )

    numeric = number(value)
    if numeric is not None and float(numeric).is_integer():
        integer = int(numeric)
        if 200001 <= integer <= 209912:
            return _calendar_coordinates(integer // 100, integer % 100)
        if 1 <= integer <= 12 and planning_year is not None:
            return _calendar_coordinates(planning_year, integer)

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return _calendar_coordinates(int(parsed.year), int(parsed.month))


def _configured_year(value: Any) -> int | None:
    parsed = number(value)
    if parsed is None or not float(parsed).is_integer():
        return None
    year = int(parsed)
    return year if 2000 <= year <= 2099 else None


def _configured_start_month(value: Any) -> int:
    parsed = number(value)
    if parsed is None or not float(parsed).is_integer():
        return 1
    month = int(parsed)
    return month if 1 <= month <= 12 else 1


def _region_marker(value: Any) -> str | None:
    match = re.fullmatch(r"(?:region|zone)[- ]?(\d+)", _norm(value), re.I)
    return None if match is None else f"Region-{int(match.group(1))}"


def _empty() -> NormalizedMasterPlan:
    return pd.DataFrame(columns=_COLUMNS)


def _project_columns(frame: pd.DataFrame) -> list[tuple[str, int]]:
    columns: list[tuple[str, int]] = []
    for physical, header in zip(frame.columns, _source_headers(frame)):
        match = re.fullmatch(r"M(\d{1,3})", _norm(header), re.I)
        if match and int(match.group(1)) >= 1:
            columns.append((str(physical), int(match.group(1))))
    columns.sort(key=lambda item: item[1])
    return columns


def _promote_pip_embedded_header(frame: pd.DataFrame) -> pd.DataFrame:
    """Promote the PIP pivot header when Excel metadata occupies earlier rows.

    The production ``City wise-PIP`` workbook uses its physical first row for
    pivot filters (for example ``Top 17``) and stores ``行标签,M1,...`` in the
    body.  The physical reader intentionally does not guess headers, so the
    product adapter owns this PIP-specific promotion.
    """

    if len(_project_columns(frame)) >= 2 or frame.empty:
        return frame
    scan_limit = min(len(frame), 32)
    for offset in range(scan_limit):
        values = frame.iloc[offset].tolist()
        first = _norm(values[0]).casefold() if values else ""
        if _region_marker(first) is not None:
            continue
        month_headers = {
            int(match.group(1))
            for value in values
            if (match := re.fullmatch(r"M(\d{1,3})", _norm(value), re.I))
        }
        if len(month_headers) < 2:
            continue
        body = frame.iloc[offset + 1 :].reset_index(drop=True).copy()
        _attach_source_headers(body, values)
        previous_offset = frame.attrs.get("pip_source_row_offset", 0)
        body.attrs["pip_source_row_offset"] = (
            int(previous_offset) if isinstance(previous_offset, int) else 0
        ) + offset + 1
        return body
    return frame


def _pip_frame(
    source: TabularSource,
    *,
    sheet_hint: str,
) -> tuple[pd.DataFrame, str, tuple[dict[str, Any], ...]]:
    """Select a PIP summary sheet by its data contract, not workbook order."""

    if isinstance(source, pd.DataFrame):
        candidates = (("", _promote_pip_embedded_header(source)),)
    elif isinstance(source, Mapping):
        candidates = tuple(
            (str(name), _promote_pip_embedded_header(frame))
            for name, frame in source.items()
            if isinstance(frame, pd.DataFrame)
        )
    else:
        raise TypeError(f"unsupported tabular source: {type(source).__name__}")

    valid: list[tuple[str, pd.DataFrame, int]] = []
    for sheet, candidate in candidates:
        if not _project_columns(candidate) or candidate.empty:
            continue
        scope_col = candidate.columns[0]
        marker_count = sum(
            _region_marker(value) is not None
            for value in candidate[scope_col].tolist()
        )
        if marker_count:
            valid.append((sheet, candidate, marker_count))
    if valid:
        hint = _norm(sheet_hint).casefold()
        sheet, selected, _ = min(
            valid,
            key=lambda value: (
                0 if hint and hint in value[0].casefold() else 1,
                0 if "city" in value[0].casefold() and "pip" in value[0].casefold() else 1,
                -value[2],
                value[0].casefold(),
            ),
        )
        return selected, sheet, ()

    prepared: TabularSource = (
        candidates[0][1]
        if isinstance(source, pd.DataFrame) and candidates
        else {name: candidate for name, candidate in candidates}
    )
    return select_frame(
        prepared,
        (("month", "月份", *(f"M{value}" for value in range(1, 13))),),
        sheet_hint=sheet_hint,
    )


def _pip_source_row(frame: pd.DataFrame, zero_based_position: int) -> int:
    offset = frame.attrs.get("pip_source_row_offset", 0)
    return zero_based_position + 2 + (
        int(offset) if isinstance(offset, int) else 0
    )


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedMasterPlan, tuple[dict[str, Any], ...]]:
    parameters = effective_delivery_options(options)
    master_format = str(parameters.get("o2_master_format", "standard")).casefold()
    sheet_hint = str(parameters.get("o2_master_sheet_hint", ""))
    planning_year = _configured_year(parameters.get("o2_planning_year"))
    project_start_month = _configured_start_month(
        parameters.get("o2_project_start_month", 1)
    )
    month_aliases = (
        "month",
        "mouth",
        "mouth/月",
        "month/月",
        "月份",
        "安装/拆除月份",
    )
    historical_site_aliases = (
        "site_name",
        "site name",
        "site_id",
        "site id",
    )
    historical_action_aliases = ("site_action", "site action", "action")
    historical_week_aliases = (
        "mos_weekly_plan",
        "week_label",
        "week label",
    )
    historical_region_aliases = ("region", "region/区域", "区域")
    selection_contract = (
        (
            historical_site_aliases,
            historical_action_aliases,
            historical_week_aliases,
            historical_region_aliases,
        )
        if master_format == "site-action-weekly-install"
        else (month_aliases + tuple(f"M{value}" for value in range(1, 13)),)
    )
    if master_format == "pip-city-wise":
        raw, sheet, selection_issues = _pip_frame(
            frame,
            sheet_hint=sheet_hint,
        )
    else:
        raw, sheet, selection_issues = select_frame(
            frame,
            selection_contract,
            sheet_hint=sheet_hint,
        )
    if raw.empty and len(raw.columns) == 0:
        return _empty(), selection_issues

    month_col = column(raw, month_aliases)
    region_col = column(raw, ("region", "区域"))
    site_type_col = column(raw, ("site_type", "site type", "type"))
    count_col = column(
        raw,
        ("master_count", "master count", "planned_count", "planned count", "count", "site_count"),
    )
    project_columns = _project_columns(raw)

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    def append_value(
        *,
        source_row: int,
        region: Any,
        site_type: Any,
        coordinates: tuple[int, int] | None,
        value: Any,
        one_if_nonzero: bool = False,
        blank_as_zero: bool = False,
    ) -> None:
        if coordinates is None:
            issues.append(
                _issue(
                    "INVALID_CANONICAL_VALUE",
                    "master-plan month cannot be mapped to a YYYYMM period",
                    row=source_row,
                    column="period",
                )
            )
            return
        parsed = number(value)
        if parsed is None:
            if blank_as_zero and not _norm(value):
                parsed = 0.0
            else:
                if _norm(value):
                    issues.append(
                        _issue(
                            "INVALID_CANONICAL_VALUE",
                            "master-plan count is not numeric",
                            row=source_row,
                            column="planned_count",
                            raw=value,
                        )
                    )
                return
        if one_if_nonzero:
            if parsed == 0:
                return
            parsed = 1.0
        period, month = coordinates
        rows.append(
            {
                "source_row": source_row,
                "region": _norm(region) or "ALL",
                "site_type": _norm(site_type),
                "period": int(period),
                "month": int(month),
                "planned_count": parsed,
            }
        )

    if master_format == "site-action-weekly-install":
        site_col = column(raw, historical_site_aliases)
        action_col = column(raw, historical_action_aliases)
        week_col = column(raw, historical_week_aliases)
        historical_region_col = column(raw, historical_region_aliases)
        missing_columns = [
            name
            for name, physical in (
                ("site_id", site_col),
                ("action", action_col),
                ("week_label", week_col),
                ("region", historical_region_col),
            )
            if physical is None
        ]
        for name in missing_columns:
            issues.append(
                _issue(
                    "MISSING_CANONICAL_COLUMN",
                    "historical site-action plan lacks a required authority column",
                    column=name,
                )
            )
        seen_actions: dict[tuple[str, str], int] = {}
        if not missing_columns:
            for position, (_, row) in enumerate(raw.iterrows(), start=2):
                site = _norm(row.get(site_col))
                action = _norm(row.get(action_col)).casefold()
                region = _norm(row.get(historical_region_col))
                if action not in {"install", "dismantle"}:
                    issues.append(
                        _issue(
                            "INVALID_CANONICAL_VALUE",
                            "historical site-action plan contains an unsupported action",
                            row=position,
                            column="action",
                            raw=row.get(action_col),
                        )
                    )
                    continue
                if not site or not region:
                    issues.append(
                        _issue(
                            "INVALID_CANONICAL_VALUE",
                            "historical site-action plan requires nonblank site and region",
                            row=position,
                            column="site_id|region",
                        )
                    )
                    continue
                action_key = (site.casefold(), action)
                if action_key in seen_actions:
                    issues.append(
                        _issue(
                            "INVALID_CANONICAL_VALUE",
                            "historical site-action authority contains a duplicate site/action",
                            row=position,
                            column="site_id|action",
                            raw=f"first row {seen_actions[action_key]}",
                        )
                    )
                    continue
                seen_actions[action_key] = position
                # Delivery capacity, pacing and O2 all consume the install
                # curve. Dismantle actions remain authoritative through the
                # material/action scope and interval checks, not this curve.
                if action != "install":
                    continue
                try:
                    iso_week = parse_iso_week(row.get(week_col))
                    monday = date.fromisocalendar(
                        iso_week // 100,
                        iso_week % 100,
                        1,
                    )
                    coordinates = _calendar_coordinates(monday.year, monday.month)
                except ValueError:
                    coordinates = None
                append_value(
                    source_row=position,
                    region=region,
                    site_type="install",
                    coordinates=coordinates,
                    value=1,
                )
    elif master_format == "pip-city-wise" and project_columns:
        # The PIP export's first column (usually ``行标签``) owns the
        # Region-N hierarchy; metric headers such as ``计数项:City`` must not
        # be mistaken for the region dimension.
        scope_col = str(raw.columns[0])
        markers = [
            (offset, marker)
            for offset, value in enumerate(raw[scope_col].tolist())
            if (marker := _region_marker(value)) is not None
        ]
        physical_by_month = {month: physical for physical, month in project_columns}
        for marker_position, (start, region) in enumerate(markers):
            end = (
                markers[marker_position + 1][0]
                if marker_position + 1 < len(markers)
                else len(raw)
            )
            selected_offset: int | None = None
            for offset in range(start, end):
                candidate = raw.iloc[offset]
                numeric_cells = sum(
                    number(candidate.get(physical)) is not None
                    for physical in physical_by_month.values()
                )
                if numeric_cells >= 2:
                    selected_offset = offset
                    break
            if selected_offset is None:
                issues.append(
                    _issue(
                        "CANONICAL_PRODUCT_EMPTY",
                        "PIP region segment has no numeric monthly summary row",
                        row=_pip_source_row(raw, start),
                        column="planned_count",
                        raw=region,
                    )
                )
                continue
            row = raw.iloc[selected_offset]
            # Preserve every month column declared by this workbook instead
            # of baking the current PIP horizon into the adapter.  Missing
            # cells inside the declared horizon remain explicit zeroes.
            for project_month in sorted(physical_by_month):
                physical = physical_by_month.get(project_month)
                append_value(
                    source_row=_pip_source_row(raw, selected_offset),
                    region=region,
                    site_type=row.get(site_type_col) if site_type_col else "",
                    coordinates=_project_month_coordinates(
                        project_month,
                        planning_year=planning_year,
                        project_start_month=project_start_month,
                    ),
                    value=row.get(physical) if physical is not None else None,
                    blank_as_zero=True,
                )
    elif month_col is not None and count_col is not None:
        for position, (_, row) in enumerate(raw.iterrows(), start=2):
            coordinates = _month_coordinates(
                row.get(month_col),
                planning_year=planning_year,
                project_start_month=project_start_month,
            )
            if coordinates is None:
                if _norm(row.get(month_col)):
                    issues.append(
                        _issue(
                            "INVALID_CANONICAL_VALUE",
                            "master-plan month cannot be mapped to a YYYYMM period",
                            row=position,
                            column="period",
                            raw=row.get(month_col),
                        )
                    )
                continue
            append_value(
                source_row=position,
                region=row.get(region_col) if region_col else "ALL",
                site_type=row.get(site_type_col) if site_type_col else "",
                coordinates=coordinates,
                value=row.get(count_col),
            )
    elif month_col is not None:
        excluded = {month_col, region_col, site_type_col}
        value_columns = [str(value) for value in raw.columns if str(value) not in excluded]
        region_labels: dict[str, str] = {}
        for _, row in raw.iterrows():
            coordinates = _month_coordinates(
                row.get(month_col),
                planning_year=planning_year,
                project_start_month=project_start_month,
            )
            if coordinates is not None:
                continue
            for value_col in value_columns:
                label = _norm(row.get(value_col))
                if value_col not in region_labels and label and number(label) is None:
                    region_labels[value_col] = label
        for position, (_, row) in enumerate(raw.iterrows(), start=2):
            coordinates = _month_coordinates(
                row.get(month_col),
                planning_year=planning_year,
                project_start_month=project_start_month,
            )
            if coordinates is None:
                continue
            for value_col in value_columns:
                append_value(
                    source_row=position,
                    region=region_labels.get(value_col, value_col),
                    site_type="",
                    coordinates=coordinates,
                    value=row.get(value_col),
                )
    elif project_columns:
        # The standard wide form is a row-level month assignment.  Preserve
        # each occupied cell as one planned site so aggregation is explicit.
        for position, (_, row) in enumerate(raw.iterrows(), start=2):
            for physical, project_month in project_columns:
                append_value(
                    source_row=position,
                    region="ALL",
                    site_type="",
                    coordinates=_project_month_coordinates(
                        project_month,
                        planning_year=planning_year,
                        project_start_month=project_start_month,
                    ),
                    value=row.get(physical),
                    one_if_nonzero=True,
                )

    normalized = pd.DataFrame(rows, columns=_COLUMNS)
    if sheet:
        normalized.attrs["source_sheet"] = sheet
    if normalized.empty:
        issues.append(
            _issue(
                "CANONICAL_PRODUCT_EMPTY",
                "master plan produced no canonical month quantities",
            )
        )
    return normalized, selection_issues + tuple(issues)


__all__ = ["NormalizedMasterPlan", "normalize"]
