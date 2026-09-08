"""Adapter contract for the standard ``site_plan`` product."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

import pandas as pd

from ._canonical import (
    TabularSource,
    column,
    effective_delivery_options,
    number,
    project_columns,
    select_frame,
)

NormalizedSitePlan = pd.DataFrame


def _canonical_week_num(value: Any) -> Any:
    """Normalize the prompt-observed numeric or strict ``WK<n>`` week value."""

    numeric = number(value)
    if numeric is not None and float(numeric).is_integer():
        return int(numeric)
    match = re.fullmatch(r"WK\s*(\d{1,3})", str(value).strip(), re.I)
    return int(match.group(1)) if match else value


def _is_blank(value: Any) -> bool:
    return bool(pd.isna(value)) or not str(value).strip()


def _iso_week_start(value: Any) -> str:
    """Return the Monday encoded by an explicit year-qualified ISO week."""

    match = re.fullmatch(
        r"(20\d{2})\s*-?\s*W(?:K)?\s*(\d{1,2})",
        str(value).strip(),
        re.I,
    )
    if match is None:
        return ""
    try:
        monday = date.fromisocalendar(
            int(match.group(1)),
            int(match.group(2)),
            1,
        )
    except ValueError:
        return ""
    return monday.isoformat()


def _standardize_required_time_fields(
    raw: pd.DataFrame,
    fields: Mapping[str, tuple[str, ...]],
    required: list[str],
) -> pd.DataFrame:
    """Fill missing canonical time fields from equivalent submitted columns.

    The candidate's nonblank canonical values remain authoritative.  The two
    accepted substitutions only rename ``week_num`` to ``project_week`` and
    convert an explicit ``YYYYWK<n>`` label to its ISO-week Monday; neither
    operation guesses a year or repairs an invalid submitted value.
    """

    output = raw.copy()
    if "project_week" in required:
        project_week_column = column(output, fields["project_week"])
        week_num_column = column(output, fields["week_num"])
        if week_num_column is not None:
            project_week = (
                output[project_week_column].astype(object).copy()
                if project_week_column is not None
                else pd.Series("", index=output.index, dtype=object)
            )
            missing = project_week.map(_is_blank)
            project_week.loc[missing] = output.loc[
                missing, week_num_column
            ].map(_canonical_week_num)
            output["project_week"] = project_week

    if "week_start" in required:
        week_start_column = column(output, fields["week_start"])
        week_label_column = column(output, fields["week_label"])
        if week_label_column is not None:
            week_start = (
                output[week_start_column].astype(object).copy()
                if week_start_column is not None
                else pd.Series("", index=output.index, dtype=object)
            )
            missing = week_start.map(_is_blank)
            week_start.loc[missing] = output.loc[
                missing, week_label_column
            ].map(_iso_week_start)
            output["week_start"] = week_start
    return output


def _configured_planning_year(value: Any) -> int | None:
    numeric = number(value)
    if numeric is None or not float(numeric).is_integer():
        return None
    year = int(numeric)
    return year if 2000 <= year <= 2099 else None


def _qualify_short_week_label(
    value: Any,
    *,
    week_num: Any,
    planning_year: int,
) -> Any:
    """Qualify an unambiguous single-year ``WK<n>`` calendar label.

    The short form is repaired only when it agrees with the separately
    normalized numeric week and denotes a real ISO week in ``planning_year``.
    All other values are preserved so the O2 parser can report their original
    conflict or invalidity instead of the adapter silently changing meaning.
    """

    match = re.fullmatch(r"WK(\d{1,2})", str(value).strip(), re.I)
    canonical = number(week_num)
    if (
        match is None
        or canonical is None
        or not float(canonical).is_integer()
    ):
        return value
    week = int(match.group(1))
    if week != int(canonical):
        return value
    try:
        date.fromisocalendar(planning_year, week, 1)
    except ValueError:
        return value
    return f"{planning_year}WK{week}"


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedSitePlan, tuple[dict[str, Any], ...]]:
    parameters = effective_delivery_options(options)
    batch_kind = str(parameters.get("o2_batch_kind", "")).strip().casefold()
    fields = {
        "site_id": (
            "site_name",
            "site name",
            "site id",
            "site id radio",
            "site id radio/站点",
            "du id",
            "*du id",
        ),
        "region": ("region", "region/区域", "区域"),
        "action": ("site_action", "site action", "action"),
        "project_week": ("project_week", "project week"),
        "week_num": ("week_num", "week num"),
        "week_label": ("mos_weekly_plan", "week_label", "week label"),
        "week_start": ("week_start", "week start"),
        "status": ("status",),
        "site_count": ("site_count", "site count"),
        "cluster_id": (
            "cluster",
            "cluster_id",
            "cluster id",
            *(("batch_id",) if batch_kind == "cluster" else ()),
        ),
        "mocn_batch_id": (
            "mocn_batch",
            "mocn batch",
            "mocn batch id",
            "mocn开通批次",
            "mocn批次号",
            *(("batch_id",) if batch_kind == "mocn" else ()),
        ),
    }
    raw, sheet, selection_issues = select_frame(
        frame,
        (fields["site_id"], fields["action"], fields["region"]),
    )
    # The physical site-plan contract differs by question family.  In
    # particular, most EI prompts publish the compact six-column schedule and
    # keep batch membership in the authoritative prepared input; only the base
    # PK prompt publishes status, week_start and batch on site_plan itself.
    # Requiring the superset here would turn a Prompt-conformant compact plan
    # into INVALID_ARTIFACT before O2 can evaluate its business result.
    configured_required = parameters.get("o2_site_plan_required_fields")
    required = (
        list(configured_required)
        if isinstance(configured_required, (list, tuple))
        else ["site_id", "region", "action", "site_count"]
    )
    if configured_required is None and str(
        parameters.get("o2_plan_mode", "candidate-scheduled")
    ).casefold() == "candidate-scheduled":
        required.extend(("week_start", "status"))
        if batch_kind == "cluster":
            required.append("cluster_id")
        elif batch_kind == "mocn":
            required.append("mocn_batch_id")
    raw = _standardize_required_time_fields(raw, fields, required)
    normalized, issues = project_columns(
        raw,
        fields,
        required=required,
        source_sheet=sheet,
    )
    normalized["week_num"] = normalized["week_num"].map(
        _canonical_week_num
    )
    planning_year = _configured_planning_year(parameters.get("o2_planning_year"))
    if (
        planning_year is not None
        and str(parameters.get("o2_delivery_month_source", "")).casefold()
        == "week-label"
        and str(parameters.get("o2_project_week_source", "")).casefold()
        == "reconcile"
    ):
        normalized["week_label"] = [
            _qualify_short_week_label(
                label,
                week_num=week_num,
                planning_year=planning_year,
            )
            for label, week_num in zip(
                normalized["week_label"], normalized["week_num"]
            )
        ]
    required_numeric_week_fields = tuple(
        name for name in ("project_week", "week_num") if name in required
    )
    if (
        not normalized.empty
        and required_numeric_week_fields
        and not any(
            normalized[name].map(lambda value: str(value).strip()).any()
            for name in required_numeric_week_fields
        )
    ):
        issues += (
            {
                "code": "MISSING_CANONICAL_COLUMN",
                "message": "site plan lacks a configured canonical project-week value",
                "column": "|".join(required_numeric_week_fields),
            },
        )
    return normalized, selection_issues + issues


__all__ = ["NormalizedSitePlan", "normalize"]
