"""Deterministic parsing helpers shared by scheduling checks."""

from __future__ import annotations

import re
from collections.abc import Mapping

import pandas as pd

from simulation.ei.core.adapters import parse_project_week

from ..batching import resolve_batch
from ..common import _find_column, _key, _norm, _number


def _parse_project_weeks(values: pd.Series) -> list[int | None]:
    """Parse each distinct typed week label once and retain invalid values."""

    cache: dict[tuple[type[object], str], int | None] = {}
    parsed: list[int | None] = []
    for value in values.tolist():
        signature = (type(value), _norm(value))
        if signature not in cache:
            try:
                cache[signature] = parse_project_week(value)
            except ValueError:
                cache[signature] = None
        parsed.append(cache[signature])
    return parsed


def _candidate_plan(
    raw: pd.DataFrame,
    *,
    project_week_source: str = "reconcile",
) -> pd.DataFrame:
    if project_week_source not in {"reconcile", "week_num"}:
        raise ValueError(
            f"unsupported scheduling project_week_source: {project_week_source}"
        )
    site_col = _find_column(raw, "site_name", "site id", "site id radio", "站点")
    action_col = _find_column(raw, "site_action", "action")
    region_col = _find_column(raw, "region", "region/区域", "区域")
    status_col = _find_column(raw, "status")
    if site_col is None or action_col is None:
        raise ValueError("site_plan lacks site/action columns")
    output = pd.DataFrame()
    output["site"] = raw[site_col].map(_norm)
    output["action"] = raw[action_col].map(lambda value: _norm(value).casefold())
    output["region"] = raw[region_col].map(_norm) if region_col else "ALL"
    output["status"] = (
        raw[status_col].map(lambda value: _norm(value).casefold())
        if status_col
        else "scheduled"
    )
    output.loc[output["status"] == "", "status"] = "scheduled"
    output["source_row"] = [position + 2 for position in range(len(raw))]
    for target, aliases in {
        "week": ("week_num", "project_week"),
        "week_label": ("week_label", "mos_weekly_plan", "week_start"),
        "batch": ("mocn_batch", "cluster"),
    }.items():
        column = _find_column(raw, *aliases)
        output[target] = raw[column] if column else ""
    output["site_key"] = output["region"].map(_key) + "|" + output["site"].map(_key)
    output["action_key"] = output["site_key"] + "|" + output["action"]
    week_values: list[int | None] = []
    week_issues: list[str] = []
    week_sources: list[str] = []
    week_fields = (
        ("week", "week_label")
        if project_week_source == "reconcile"
        else ("week",)
    )
    parsed_columns = {
        field: _parse_project_weeks(output[field])
        for field in week_fields
    }
    for position in range(len(output)):
        status = str(output.iloc[position]["status"])
        raw_time_values = [_norm(output.iloc[position][field]) for field in week_fields]
        if status == "unscheduled":
            if any(raw_time_values):
                week_values.append(None)
                week_issues.append("UNSCHEDULED_TIME_NOT_BLANK")
                week_sources.append("")
            else:
                week_values.append(None)
                week_issues.append("")
                week_sources.append("unscheduled")
            continue
        if status != "scheduled":
            week_values.append(None)
            week_issues.append("INVALID_STATUS")
            week_sources.append("")
            continue
        parsed = {
            field: int(parsed_columns[field][position])
            for field in week_fields
            if parsed_columns[field][position] is not None
        }
        if len(set(parsed.values())) > 1:
            week_values.append(None)
            week_issues.append("WEEK_CONFLICT")
            week_sources.append("")
        elif parsed:
            week_values.append(next(iter(parsed.values())))
            week_issues.append("")
            week_sources.append("+".join(parsed))
        else:
            week_values.append(None)
            week_issues.append("UNPARSEABLE_WEEK")
            week_sources.append("")
    output["project_week"] = week_values
    output["week_issue"] = week_issues
    output["week_source"] = week_sources
    return output


def _unique_action_week(
    rows: pd.DataFrame,
    action: str,
) -> tuple[int | None, str | None]:
    """Return one site's action week for rules whose unit is a unique site-action."""

    matching = rows[rows["action"] == action]
    if matching.empty:
        return None, "MISSING_ACTION"
    if len(matching) > 1:
        return None, "DUPLICATE_ACTION"
    row = matching.iloc[0]
    issue = str(row["week_issue"] or "")
    if issue:
        return None, issue
    if pd.isna(row["project_week"]):
        return None, "UNPARSEABLE_WEEK"
    return int(row["project_week"]), None


def batch_for(site_key: str, mapping: Mapping[str, str]) -> str | None:
    return resolve_batch(site_key, mapping)


def batch_order_value(batch: str) -> float | None:
    numeric = _number(batch)
    if numeric is not None:
        return numeric
    match = re.search(r"(\d+(?:\.\d+)?)", batch)
    return float(match.group(1)) if match else None
