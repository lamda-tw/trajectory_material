"""Candidate-plan parsing owned by the independent O2 rule."""

from __future__ import annotations

import re
from collections.abc import Mapping
from collections import Counter
from datetime import date
from typing import Any, Iterable

import pandas as pd

from simulation.ei.core.adapters import parse_iso_week, parse_project_week

from ..batching import BatchLookup, compile_batch_lookup, resolve_batch
from ..common import _key, _month_from_row, _norm, _number


_DELIVERY_MONTH_SOURCES = {"week-start", "week-label", "schedule-week"}


def site_identity(value: Any) -> str:
    """Return the O2 identity of a site without deleting identifier syntax."""

    # site_name is a business identifier, not free text.  Whitespace is
    # normalized for spreadsheet hygiene, but punctuation, letter case and
    # leading zeroes are identity-bearing and must remain distinguishable.
    return _norm(value)


def site_key(region: Any, site: Any) -> str:
    """Build O2's Region-qualified strict site key."""

    return f"{_key(region)}|{site_identity(site)}"


def action_key(region: Any, site: Any, action: Any) -> str:
    """Build O2's strict site-action key."""

    return f"{site_key(region, site)}|{_norm(action).casefold()}"


def site_key_parts(value: str) -> tuple[str, str]:
    """Split an O2 site key while preserving punctuation inside site IDs."""

    region, separator, site = str(value).partition("|")
    if not separator:
        raise ValueError(f"invalid O2 site key: {value!r}")
    return region, site


def action_key_parts(value: str) -> tuple[str, str, str]:
    """Split an O2 action key while preserving punctuation inside site IDs."""

    site_value, separator, action = str(value).rpartition("|")
    if not separator:
        raise ValueError(f"invalid O2 action key: {value!r}")
    region, site = site_key_parts(site_value)
    return region, site, action


def delivery_batches(
    source: pd.DataFrame,
    *,
    batch_kind: str,
) -> BatchLookup:
    """Compile Prompt-authorized batches with O2's strict site identity."""

    if batch_kind == "cluster":
        batch_column = "cluster_id"
    elif batch_kind == "mocn":
        batch_column = "mocn_batch_id"
    else:
        raise ValueError(f"unsupported O2 batch kind: {batch_kind}")
    required = {"source_row", "site_id", "region", batch_column}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(
            f"normalized batch_input lacks O2 fields: {missing}"
        )

    mapping: dict[str, str] = {}
    for _, row in source.iterrows():
        site = site_identity(row.get("site_id"))
        batch = _norm(row.get(batch_column))
        region = _norm(row.get("region")) or "ALL"
        if not site or not batch:
            continue
        key = site_key(region, site)
        previous = mapping.get(key)
        if previous is not None and previous != batch:
            raise ValueError(
                f"authoritative site has conflicting {batch_kind} values: {site!r}"
            )
        mapping[key] = batch
    return compile_batch_lookup(mapping)


def integer_project_week(value: Any) -> int:
    """Parse the O2 contract's numeric integer project-week field."""

    numeric = _number(value)
    if numeric is None or not float(numeric).is_integer():
        raise ValueError(f"project_week must be an integer: {value!r}")
    return int(numeric)


def _schedule_label_identity(
    value: Any,
    *,
    planning_year: int,
) -> tuple[int, int]:
    """Return the project-week number and year-qualified ISO identity.

    A short label inherits the question's single planning year.  An explicit
    label retains its submitted year so callers can reject a wrong-year value
    instead of silently reducing it to the week number.
    """

    text = _norm(value)
    if re.fullmatch(r"20\d{2}\s*-?\s*W(?:K)?\s*\d{1,2}", text, re.I):
        calendar_week = parse_iso_week(text)
        return calendar_week % 100, calendar_week
    week = parse_project_week(text)
    try:
        date.fromisocalendar(planning_year, week, 1)
    except ValueError as exc:
        raise ValueError(f"invalid planning-year week label: {text!r}") from exc
    return week, planning_year * 100 + week


def _schedule_week(
    row: pd.Series,
    *,
    project_week_source: str,
    delivery_month_source: str,
    planning_year: int,
) -> tuple[int | None, str, str, int | None]:
    """Resolve the business schedule coordinate independently of calendar time.

    ``reconcile`` is used by contracts whose numeric week and display label
    represent the same week number.  The canonical adapter always exposes both
    numeric columns, but individual Prompts require either ``project_week`` or
    ``week_num``; therefore the nonblank column is selected instead of assuming
    that ``project_week`` exists.  ``week_num`` mode normally does not compare
    the display label because TESTTH defines it as a continuous project week
    while the label is an absolute calendar week.  ``schedule-week`` is the
    explicit exception: its label is the same business coordinate and must
    preserve and validate the frozen planning-year identity.
    """

    if project_week_source not in {"reconcile", "week_num"}:
        raise ValueError(f"unsupported O2 project_week_source: {project_week_source}")

    columns = (
        ("project_week", "week_num")
        if project_week_source == "reconcile"
        else ("week_num",)
    )
    parsed: dict[str, int] = {}
    invalid_numeric = False
    for column in columns:
        value = row.get(column)
        if not _norm(value):
            continue
        try:
            parsed[column] = integer_project_week(value)
        except ValueError:
            invalid_numeric = True

    values = set(parsed.values())
    if invalid_numeric or not values:
        return None, "UNPARSEABLE_WEEK", "+".join(parsed), None
    if len(values) != 1:
        return None, "WEEK_CONFLICT", "+".join(parsed), None

    schedule_week = next(iter(values))
    sources = list(parsed)
    label = _norm(row.get("week_label"))
    calendar_week: int | None = None
    should_reconcile_label = (
        project_week_source == "reconcile"
        or delivery_month_source == "schedule-week"
    )
    if should_reconcile_label and label:
        try:
            if delivery_month_source == "schedule-week":
                label_week, calendar_week = _schedule_label_identity(
                    label,
                    planning_year=planning_year,
                )
            else:
                label_week = parse_project_week(label)
                try:
                    calendar_week = parse_iso_week(label)
                except (TypeError, ValueError):
                    calendar_week = None
        except ValueError:
            return (
                schedule_week,
                "WEEK_CONFLICT",
                "+".join((*sources, "week_label")),
                None,
            )
        sources.append("week_label")
        if label_week != schedule_week:
            return schedule_week, "WEEK_CONFLICT", "+".join(sources), calendar_week
        if (
            delivery_month_source == "schedule-week"
            and calendar_week // 100 != planning_year
        ):
            return (
                schedule_week,
                "WEEK_YEAR_MISMATCH",
                "+".join(sources),
                calendar_week,
            )
    elif label:
        try:
            calendar_week = parse_iso_week(label)
        except (TypeError, ValueError):
            calendar_week = None
    return schedule_week, "", "+".join(sources), calendar_week


def _parsed_week_start(value: Any) -> date | None:
    text = _norm(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _delivery_month(
    row: pd.Series,
    *,
    schedule_week: int | None,
    delivery_month_source: str,
    planning_year: int,
    week_to_month: str,
    project_start_month: int,
) -> int | None:
    """Resolve calendar attribution without changing the schedule coordinate."""

    if schedule_week is None:
        return None
    if delivery_month_source == "week-start":
        parsed = _parsed_week_start(row.get("week_start"))
        return parsed.month if parsed is not None else None
    if delivery_month_source == "week-label":
        try:
            iso_week = parse_iso_week(row.get("week_label"))
            monday = date.fromisocalendar(iso_week // 100, iso_week % 100, 1)
        except (TypeError, ValueError):
            return None
        return monday.month
    if delivery_month_source == "schedule-week":
        month_row = pd.Series({"week": schedule_week, "week_label": ""})
        return _month_from_row(
            month_row,
            planning_year,
            week_to_month=week_to_month,
            project_start_month=project_start_month,
        )
    raise ValueError(f"unsupported O2 delivery_month_source: {delivery_month_source}")


def _delivery_period(
    row: pd.Series,
    *,
    schedule_week: int | None,
    delivery_month_source: str,
    planning_year: int,
    week_to_month: str,
    project_start_month: int,
) -> int | None:
    """Return a stable ``YYYYMM`` scoring key for one delivery action.

    Month numbers alone are ambiguous for schedules spanning a year boundary
    (the TH contract, for example, contains both July 2023 and July 2024).
    The display month remains available separately, while all A/B joins use
    this year-qualified key.
    """

    if schedule_week is None:
        return None
    if delivery_month_source == "week-start":
        parsed = _parsed_week_start(row.get("week_start"))
        return parsed.year * 100 + parsed.month if parsed is not None else None
    if delivery_month_source == "week-label":
        try:
            iso_week = parse_iso_week(row.get("week_label"))
            monday = date.fromisocalendar(iso_week // 100, iso_week % 100, 1)
        except (TypeError, ValueError):
            return None
        return monday.year * 100 + monday.month
    if delivery_month_source == "schedule-week":
        month_index = _month_from_row(
            pd.Series({"week": schedule_week, "week_label": ""}),
            planning_year,
            week_to_month=week_to_month,
            project_start_month=project_start_month,
        )
        if month_index is None:
            return None
        zero_based = int(month_index) - 1
        return (planning_year + zero_based // 12) * 100 + zero_based % 12 + 1
    raise ValueError(f"unsupported O2 delivery_month_source: {delivery_month_source}")


def _apply_relative_week_start_contract(output: pd.DataFrame) -> None:
    """Validate week-start dates against one result-internal project anchor.

    The Prompt does not define project week 1 as ISO week 1.  Each parseable
    row instead implies an anchor date ``week_start - 7 * (schedule_week - 1)``.
    Rows outside the unique modal anchor are invalid.  A tie has no defensible
    authority, so every conflicting row is marked rather than picking one by
    file order.
    """

    anchors: list[date | None] = []
    for _, row in output.iterrows():
        parsed = _parsed_week_start(row.get("week_start"))
        week = row.get("schedule_week")
        if parsed is None or pd.isna(week):
            anchors.append(None)
        else:
            anchors.append(date.fromordinal(parsed.toordinal() - 7 * (int(week) - 1)))
    counts = Counter(value for value in anchors if value is not None)
    if len(counts) <= 1:
        return
    ranked = counts.most_common()
    winner = ranked[0][0] if len(ranked) == 1 or ranked[0][1] > ranked[1][1] else None
    for index, anchor in zip(output.index, anchors):
        if anchor is None or (winner is not None and anchor == winner):
            continue
        issues = list(output.at[index, "row_contract_issues"])
        issues.append("WEEK_START_MISMATCH")
        output.at[index, "row_contract_issues"] = tuple(issues)


def candidate_plan(
    raw: pd.DataFrame,
    *,
    batch_kind: str,
    project_week_source: str = "reconcile",
    delivery_month_source: str = "week-start",
    planning_year: int,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
    required_fields: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Compile O2 plan rows, including delivery-row validity fields."""

    if project_week_source not in {"reconcile", "week_num"}:
        raise ValueError(f"unsupported O2 project_week_source: {project_week_source}")
    if delivery_month_source not in _DELIVERY_MONTH_SOURCES:
        raise ValueError(
            f"unsupported O2 delivery_month_source: {delivery_month_source}"
        )
    batch_column = (
        "mocn_batch_id"
        if batch_kind == "mocn"
        else "cluster_id"
        if batch_kind == "cluster"
        else ""
    )
    if not batch_column:
        raise ValueError(f"unsupported O2 batch kind: {batch_kind}")
    configured_required = (
        {str(value) for value in required_fields}
        if required_fields is not None
        else {
            "site_id",
            "region",
            "action",
            "project_week",
            "week_start",
            "status",
            "site_count",
            batch_column,
        }
    )
    required = {
        "source_row",
        "site_id",
        "action",
        "region",
        batch_column,
        "project_week",
        "week_num",
        "week_label",
        "week_start",
        "status",
        "site_count",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"normalized site_plan lacks O2 delivery fields: {missing}")

    output = pd.DataFrame()
    output["site"] = raw["site_id"].map(_norm)
    output["action"] = raw["action"].map(lambda value: _norm(value).casefold())
    output["region"] = raw["region"].map(_norm)
    output["source_row"] = raw["source_row"].map(int)
    output["batch"] = raw[batch_column].map(_norm)
    output["project_week"] = raw["project_week"]
    output["week_num"] = raw["week_num"]
    output["week_start"] = raw["week_start"]
    output["week_label"] = raw["week_label"]
    output["status"] = raw["status"].map(lambda value: _norm(value).casefold())
    output["site_count"] = raw["site_count"].map(_number)
    if batch_kind == "mocn":
        output["batch_compare"] = output["batch"].map(
            lambda value: (
                str(int(number))
                if (number := _number(value)) is not None
                and float(number).is_integer()
                and int(number) > 0
                else ""
            )
        )
    else:
        output["batch_compare"] = output["batch"].map(_key)
    output["site_identity"] = output["site"].map(site_identity)
    output["site_key"] = [
        site_key(region, site)
        for region, site in zip(output["region"], output["site_identity"])
    ]
    output["action_key"] = [
        action_key(region, site, action)
        for region, site, action in zip(
            output["region"],
            output["site_identity"],
            output["action"],
        )
    ]

    week_values: list[int | None] = []
    delivery_months: list[int | None] = []
    delivery_periods: list[int | None] = []
    calendar_weeks: list[int | None] = []
    week_issues: list[str] = []
    week_sources: list[str] = []
    row_contract_issues: list[tuple[str, ...]] = []
    for _, row in output.iterrows():
        status = str(row["status"])
        unscheduled = status == "unscheduled"
        submitted_time = any(
            _norm(row[field])
            for field in ("project_week", "week_num", "week_label", "week_start")
        )
        if unscheduled:
            schedule_week = None
            week_issue = "UNSCHEDULED_TIME_NOT_BLANK" if submitted_time else ""
            week_source = "unscheduled"
            calendar_week = None
        else:
            schedule_week, week_issue, week_source, calendar_week = _schedule_week(
                row,
                project_week_source=project_week_source,
                delivery_month_source=delivery_month_source,
                planning_year=planning_year,
            )
        week_values.append(schedule_week)
        week_issues.append(week_issue)
        week_sources.append(week_source)
        delivery_months.append(
            None if unscheduled else _delivery_month(
                row,
                schedule_week=schedule_week,
                delivery_month_source=delivery_month_source,
                planning_year=planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        )
        delivery_periods.append(
            None if unscheduled else _delivery_period(
                row,
                schedule_week=schedule_week,
                delivery_month_source=delivery_month_source,
                planning_year=planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        )
        calendar_weeks.append(calendar_week)

        issues: list[str] = []
        if schedule_week is not None and (
            int(schedule_week) < 1
            or (
                delivery_month_source == "week-start"
                and int(schedule_week) > 52
            )
        ):
            issues.append("PROJECT_WEEK_OUT_OF_RANGE")
        if (
            not unscheduled
            and
            "week_start" in configured_required
            and _parsed_week_start(row["week_start"]) is None
        ):
            issues.append("INVALID_WEEK_START")
        if not unscheduled and delivery_month_source == "week-label":
            try:
                parse_iso_week(row["week_label"])
            except (TypeError, ValueError):
                issues.append("INVALID_WEEK_LABEL")
        if "status" in configured_required and status not in {"scheduled", "unscheduled"}:
            issues.append("INVALID_SITE_STATUS")
        count = row["site_count"]
        if "site_count" in configured_required and (
            count is None or not float(count).is_integer() or int(count) != 1
        ):
            issues.append("SITE_COUNT_NOT_ONE")
        if not _norm(row["region"]):
            issues.append("SITE_REGION_MISSING")
        batch = _norm(row["batch"])
        if batch_column not in configured_required:
            pass
        elif not batch:
            issues.append("DELIVERY_BATCH_MISSING")
        elif batch_kind == "mocn":
            numeric_batch = _number(batch)
            if (
                numeric_batch is None
                or not float(numeric_batch).is_integer()
                or int(numeric_batch) <= 0
            ):
                issues.append("DELIVERY_BATCH_INVALID")
        row_contract_issues.append(tuple(issues))

    output["schedule_week"] = week_values
    # Retain the historical internal name for final-BOM joins while all time
    # arithmetic below consumes the explicitly named schedule coordinate.
    output["project_week"] = week_values
    output["delivery_month"] = delivery_months
    output["delivery_period"] = delivery_periods
    output["calendar_week"] = calendar_weeks
    output["week_issue"] = week_issues
    output["week_source"] = week_sources
    output["row_contract_issues"] = row_contract_issues
    if delivery_month_source == "week-start" and "week_start" in configured_required:
        _apply_relative_week_start_contract(output)
    return output


def fixed_authority_plan(
    raw: pd.DataFrame,
    *,
    project_week_source: str = "reconcile",
    delivery_month_source: str = "week-label",
    planning_year: int,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
    required_fields: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Compile the immutable easy-question plan without candidate-only fields.

    Easy questions provide ``site_plan.csv`` as a question input.  It is the
    schedule authority itself, so batch, status and ``week_start`` fields used
    to validate a candidate-scheduled plan are intentionally not part of this
    contract.
    """

    if project_week_source not in {"reconcile", "week_num"}:
        raise ValueError(f"unsupported O2 project_week_source: {project_week_source}")
    if delivery_month_source not in _DELIVERY_MONTH_SOURCES:
        raise ValueError(
            f"unsupported O2 delivery_month_source: {delivery_month_source}"
        )
    configured_required = (
        {str(value) for value in required_fields}
        if required_fields is not None
        else {"site_id", "region", "action", "week_num", "week_label", "site_count"}
    )
    required = {
        "source_row",
        "site_id",
        "action",
        "region",
        "site_count",
        "project_week",
        "week_num",
        "week_label",
        "week_start",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(
            f"normalized fixed site_plan lacks O2 authority fields: {missing}"
        )

    output = pd.DataFrame()
    output["site"] = raw["site_id"].map(_norm)
    output["action"] = raw["action"].map(lambda value: _norm(value).casefold())
    output["region"] = raw["region"].map(_norm)
    output["source_row"] = raw["source_row"].map(int)
    output["project_week"] = raw["project_week"]
    output["week_num"] = raw["week_num"]
    output["week_label"] = raw["week_label"]
    output["site_count"] = raw["site_count"].map(_number)
    output["batch"] = ""
    output["batch_compare"] = ""
    output["status"] = "authoritative"
    output["week_start"] = raw["week_start"]
    output["site_identity"] = output["site"].map(site_identity)
    output["site_key"] = [
        site_key(region, site)
        for region, site in zip(output["region"], output["site_identity"])
    ]
    output["action_key"] = [
        action_key(region, site, action)
        for region, site, action in zip(
            output["region"],
            output["site_identity"],
            output["action"],
        )
    ]

    week_values: list[int | None] = []
    delivery_months: list[int | None] = []
    delivery_periods: list[int | None] = []
    calendar_weeks: list[int | None] = []
    week_issues: list[str] = []
    week_sources: list[str] = []
    row_contract_issues: list[tuple[str, ...]] = []
    for _, row in output.iterrows():
        schedule_week, week_issue, week_source, calendar_week = _schedule_week(
            row,
            project_week_source=project_week_source,
            delivery_month_source=delivery_month_source,
            planning_year=planning_year,
        )
        if schedule_week is not None and (
            schedule_week < 1
            or (delivery_month_source == "week-start" and schedule_week > 52)
        ):
            week_issue = "PROJECT_WEEK_OUT_OF_RANGE"
        week_values.append(schedule_week)
        week_issues.append(week_issue)
        week_sources.append(week_source)
        delivery_months.append(
            _delivery_month(
                row,
                schedule_week=schedule_week,
                delivery_month_source=delivery_month_source,
                planning_year=planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        )
        delivery_periods.append(
            _delivery_period(
                row,
                schedule_week=schedule_week,
                delivery_month_source=delivery_month_source,
                planning_year=planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        )
        calendar_weeks.append(calendar_week)

        issues: list[str] = []
        if not row["site_identity"]:
            issues.append("SITE_ID_MISSING")
        if row["action"] not in {"install", "dismantle"}:
            issues.append("INVALID_SITE_ACTION")
        if not _norm(row["region"]):
            issues.append("SITE_REGION_MISSING")
        count = row["site_count"]
        if "site_count" in configured_required and (
            count is None or not float(count).is_integer() or int(count) != 1
        ):
            issues.append("SITE_COUNT_NOT_ONE")
        if (
            "week_start" in configured_required
            and _parsed_week_start(row["week_start"]) is None
        ):
            issues.append("INVALID_WEEK_START")
        if delivery_month_source == "week-label":
            try:
                parse_iso_week(row["week_label"])
            except (TypeError, ValueError):
                issues.append("INVALID_WEEK_LABEL")
        row_contract_issues.append(tuple(issues))

    output["schedule_week"] = week_values
    output["project_week"] = week_values
    output["delivery_month"] = delivery_months
    output["delivery_period"] = delivery_periods
    output["calendar_week"] = calendar_weeks
    output["week_issue"] = week_issues
    output["week_source"] = week_sources
    output["row_contract_issues"] = row_contract_issues
    if delivery_month_source == "week-start" and "week_start" in configured_required:
        _apply_relative_week_start_contract(output)
    duplicate_rows = output.loc[
        output["action_key"].duplicated(keep=False),
        "source_row",
    ].astype(int).tolist()
    invalid_rows = output.loc[
        output["row_contract_issues"].map(bool) | output["week_issue"].map(bool),
        "source_row",
    ].astype(int).tolist()
    if duplicate_rows:
        raise ValueError(
            f"fixed site_plan contains duplicate site actions at rows {duplicate_rows[:20]}"
        )
    if invalid_rows:
        raise ValueError(
            f"fixed site_plan contains invalid authority rows {invalid_rows[:20]}"
        )
    return output


def batch_for(site_key: str, mapping: Mapping[str, str]) -> str | None:
    """Resolve an authoritative site to one batch without candidate inference."""

    return resolve_batch(site_key, mapping)


__all__ = [
    "action_key",
    "action_key_parts",
    "batch_for",
    "candidate_plan",
    "delivery_batches",
    "fixed_authority_plan",
    "integer_project_week",
    "site_identity",
    "site_key",
    "site_key_parts",
]
