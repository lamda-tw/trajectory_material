"""Prompt-authorized auxiliary contracts shared by GAP and warehouse rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

import pandas as pd

from simulation.ei.core.adapters import (
    parse_iso_week,
    shift_week_coordinate,
    warehouse_key_parts,
    warehouse_series_key,
    week_coordinate_kind,
)
from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from ..common import _norm


@dataclass(frozen=True)
class WeekAxisResult:
    """One resolved expected axis and its global submitted-week comparison."""

    rate: float
    status: str
    reason_code: str
    expected_weeks: tuple[int, ...]
    evidence: dict[str, Any]


_GAP_ZERO_WEEKLY_METRICS = frozenset(
    {"Dismantled", "Arrive", "DismantledSupply", "ReuseConsumed"}
)
_GAP_ZERO_SUMMARY_METRICS = frozenset(
    {"total_dismantled", "initial_inventory", "totalArrive", "totalReuse"}
)
_GAP_ZERO_SUMMARY_HEADERS = {
    "total_dismantled": "total_dismantled",
    "initial_inventory": "initial_inventory",
    "totalArrive": "totalArrive",
    "totalReuse": "totalReuse",
}


def _coordinate_sequence(start: int, end: int, kind: str) -> tuple[int, ...]:
    """Enumerate an inclusive project/ISO week interval with a bounded loop."""

    weeks = [int(start)]
    while weeks[-1] != int(end):
        if len(weeks) >= 10000:
            raise ValueError("week contract exceeds 10000 coordinates")
        next_week = shift_week_coordinate(weeks[-1], 1, kind)
        if kind == "project" and next_week > int(end):
            raise ValueError("week contract end precedes start")
        if kind == "iso" and next_week > int(end):
            raise ValueError("ISO week contract end is not reachable from start")
        weeks.append(next_week)
    return tuple(weeks)


def _site_plan_coordinates(
    scheduled_plan: pd.DataFrame | None,
    *,
    week_kind: str,
) -> tuple[tuple[int, ...], tuple[dict[str, Any], ...]]:
    if not isinstance(scheduled_plan, pd.DataFrame) or scheduled_plan.empty:
        return (), ({"code": "MISSING_SITE_PLAN_AXIS", "message": "site_plan has no scheduled rows"},)

    values: list[int] = []
    issues: list[dict[str, Any]] = []
    for offset, row in enumerate(scheduled_plan.to_dict("records"), start=2):
        if week_kind == "project":
            raw = row.get("project_week")
            issue = _norm(row.get("week_issue"))
            if issue or raw is None or pd.isna(raw):
                issues.append(
                    {
                        "code": "INVALID_SITE_PLAN_AXIS_WEEK",
                        "row": offset,
                        "raw": _norm(raw),
                        "detail": issue or "missing project_week",
                    }
                )
                continue
            try:
                numeric = float(raw)
                if not numeric.is_integer() or numeric < 1:
                    raise ValueError
                values.append(int(numeric))
            except (TypeError, ValueError):
                issues.append(
                    {
                        "code": "INVALID_SITE_PLAN_AXIS_WEEK",
                        "row": offset,
                        "raw": _norm(raw),
                        "detail": "project_week must be a positive integer",
                    }
                )
        else:
            raw = row.get("week_label")
            try:
                values.append(parse_iso_week(raw))
            except ValueError as exc:
                issues.append(
                    {
                        "code": "INVALID_SITE_PLAN_AXIS_WEEK",
                        "row": offset,
                        "raw": _norm(raw),
                        "detail": str(exc),
                    }
                )
    return tuple(sorted(set(values))), tuple(issues)


def expected_week_axis(
    contract: Mapping[str, Any],
    *,
    scheduled_plan: pd.DataFrame | None,
) -> tuple[tuple[int, ...], dict[str, Any], str]:
    """Resolve a fixed axis or the continuous span of the formal SitePlan."""

    source = str(contract.get("source", ""))
    week_kind = str(contract.get("week_kind", ""))
    evidence: dict[str, Any] = {
        "source": source,
        "coverage": str(contract.get("coverage", "")),
        "week_kind": week_kind,
    }
    try:
        if source == "fixed":
            expected = _coordinate_sequence(
                int(contract["start_week"]),
                int(contract["end_week"]),
                week_kind,
            )
            evidence.update(
                {
                    "configured_start_week": int(contract["start_week"]),
                    "configured_end_week": int(contract["end_week"]),
                }
            )
        elif source == "site-plan":
            coordinates, issues = _site_plan_coordinates(
                scheduled_plan,
                week_kind=week_kind,
            )
            evidence["site_plan_axis_issues"] = list(issues[:50])
            evidence["site_plan_axis_issue_count"] = len(issues)
            if not coordinates:
                evidence["expected_weeks"] = []
                return (), evidence, "SITE_PLAN_WEEK_AXIS_UNRESOLVED"
            expected = _coordinate_sequence(
                coordinates[0],
                coordinates[-1],
                week_kind,
            )
            evidence.update(
                {
                    "site_plan_observed_weeks": list(coordinates),
                    "site_plan_start_week": coordinates[0],
                    "site_plan_end_week": coordinates[-1],
                }
            )
        else:  # Configuration validation should make this unreachable.
            raise ValueError(f"unsupported week contract source: {source!r}")
    except (KeyError, TypeError, ValueError) as exc:
        evidence.update({"expected_weeks": [], "error": str(exc)})
        return (), evidence, "WEEK_AXIS_CONTRACT_UNRESOLVED"

    evidence["expected_weeks"] = list(expected)
    return expected, evidence, ""


def score_week_axis(
    actual_weeks: Iterable[int],
    contract: Mapping[str, Any],
    *,
    scheduled_plan: pd.DataFrame | None,
) -> WeekAxisResult:
    """Score one global week-column axis without inventing omitted zero weeks."""

    expected, evidence, error = expected_week_axis(
        contract,
        scheduled_plan=scheduled_plan,
    )
    actual = tuple(sorted(set(int(value) for value in actual_weeks)))
    evidence["actual_weeks"] = list(actual)
    if error:
        evidence.update(
            {
                "matched_week_count": 0,
                "missing_weeks": list(expected),
                "extra_weeks": list(actual),
                "evaluated_week_count": max(1, len(expected)),
            }
        )
        return WeekAxisResult(0.0, "UNRESOLVED", error, expected, evidence)

    expected_set = set(expected)
    actual_set = set(actual)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    coverage = str(contract["coverage"])
    denominator = len(expected_set) + (len(extra) if coverage == "exact" else 0)
    matched = len(expected_set & actual_set)
    coordinate_mismatch = bool(actual) and week_coordinate_kind(actual) != str(
        contract["week_kind"]
    )
    rate = 0.0 if coordinate_mismatch else matched / denominator if denominator else 0.0
    evidence.update(
        {
            "matched_week_count": matched,
            "missing_weeks": missing,
            "extra_weeks": extra,
            "evaluated_week_count": denominator,
            "coordinate_kind_mismatch": coordinate_mismatch,
        }
    )
    mismatch = bool(missing or coordinate_mismatch or (coverage == "exact" and extra))
    return WeekAxisResult(
        rate,
        "MISMATCH" if mismatch else "PASS",
        "WEEK_AXIS_CONTRACT_MISMATCH" if mismatch else "",
        expected,
        evidence,
    )


def score_warehouse_week_axis(
    cells: Mapping[tuple[Any, ...], Mapping[str, int | float]],
    contract: Mapping[str, Any],
    *,
    scheduled_plan: pd.DataFrame | None,
) -> WeekAxisResult:
    """Score every submitted warehouse series against its complete expected axis."""

    global_axis = score_week_axis(
        (warehouse_key_parts(key)[2] for key in cells),
        contract,
        scheduled_plan=scheduled_plan,
    )
    if global_axis.status == "UNRESOLVED":
        return global_axis

    expected = set(global_axis.expected_weeks)
    by_series: dict[tuple[str, ...], set[int]] = {}
    for key in cells:
        by_series.setdefault(warehouse_series_key(key), set()).add(
            warehouse_key_parts(key)[2]
        )
    if not by_series:
        evidence = dict(global_axis.evidence)
        evidence.update(
            {
                "series_count": 0,
                "matched_unit_count": 0,
                "missing_unit_count": len(expected),
                "extra_unit_count": 0,
                "evaluated_unit_count": max(1, len(expected)),
                "missing_unit_samples": [],
                "extra_unit_samples": [],
            }
        )
        return WeekAxisResult(
            0.0,
            "MISMATCH",
            "WEEK_AXIS_CONTRACT_MISMATCH",
            global_axis.expected_weeks,
            evidence,
        )

    coverage = str(contract["coverage"])
    matched = 0
    denominator = 0
    missing_units: list[dict[str, Any]] = []
    extra_units: list[dict[str, Any]] = []
    for series, actual in sorted(by_series.items()):
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        matched += len(expected & actual)
        denominator += len(expected) + (len(extra) if coverage == "exact" else 0)
        missing_units.extend(
            {"series": list(series), "week": week} for week in missing[:50]
        )
        if coverage == "exact":
            extra_units.extend(
                {"series": list(series), "week": week} for week in extra[:50]
            )
    coordinate_mismatch = bool(cells) and global_axis.evidence.get(
        "coordinate_kind_mismatch", False
    )
    rate = 0.0 if coordinate_mismatch else matched / denominator if denominator else 0.0
    evidence = dict(global_axis.evidence)
    evidence.update(
        {
            "series_count": len(by_series),
            "matched_unit_count": matched,
            "missing_unit_count": sum(
                len(expected - actual) for actual in by_series.values()
            ),
            "extra_unit_count": (
                sum(len(actual - expected) for actual in by_series.values())
                if coverage == "exact"
                else 0
            ),
            "evaluated_unit_count": denominator,
            "missing_unit_samples": missing_units[:50],
            "extra_unit_samples": extra_units[:50],
        }
    )
    mismatch = bool(
        evidence["missing_unit_count"]
        or evidence["extra_unit_count"]
        or coordinate_mismatch
    )
    return WeekAxisResult(
        rate,
        "MISMATCH" if mismatch else "PASS",
        "WEEK_AXIS_CONTRACT_MISMATCH" if mismatch else "",
        global_axis.expected_weeks,
        evidence,
    )


def _iso_week_date_header(coordinate: int) -> str:
    year, week = divmod(int(coordinate), 100)
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return f"{monday.month}/{monday.day}~{sunday.month}/{sunday.day}"


def score_site_rollout_week_axis(
    frame: pd.DataFrame | None,
    contract: Mapping[str, Any],
    *,
    scheduled_plan: pd.DataFrame | None,
) -> WeekAxisResult:
    """Compare rollout date-range columns with the formal SitePlan ISO span."""

    expected, evidence, error = expected_week_axis(
        contract,
        scheduled_plan=scheduled_plan,
    )
    expected_headers = tuple(_iso_week_date_header(week) for week in expected)
    evidence["expected_date_headers"] = list(expected_headers)
    if not isinstance(frame, pd.DataFrame):
        evidence.update(
            {
                "actual_date_headers": [],
                "missing_date_headers": list(expected_headers),
                "extra_date_headers": [],
                "ordered_position_matches": 0,
                "evaluated_date_header_count": max(1, len(expected_headers)),
                "error": "site_rollout is missing or unusable",
            }
        )
        return WeekAxisResult(
            0.0,
            "UNRESOLVED",
            "SITE_ROLLOUT_WEEK_AXIS_UNRESOLVED",
            expected,
            evidence,
        )
    controls = {"region", "type", "sitetype"}
    actual_headers = tuple(
        str(column).strip()
        for column in frame.columns
        if "".join(character for character in str(column).casefold() if character.isalnum())
        not in controls
    )
    evidence["actual_date_headers"] = list(actual_headers)
    if error:
        evidence.update(
            {
                "missing_date_headers": list(expected_headers),
                "extra_date_headers": list(actual_headers),
                "ordered_position_matches": 0,
                "evaluated_date_header_count": max(1, len(expected_headers)),
            }
        )
        return WeekAxisResult(
            0.0,
            "UNRESOLVED",
            error,
            expected,
            evidence,
        )

    expected_set = set(expected_headers)
    actual_set = set(actual_headers)
    missing = [value for value in expected_headers if value not in actual_set]
    extra = [value for value in actual_headers if value not in expected_set]
    coverage = str(contract["coverage"])
    if coverage == "exact":
        denominator = max(len(expected_headers), len(actual_headers), 1)
        ordered_matches = sum(
            1
            for position in range(min(len(expected_headers), len(actual_headers)))
            if expected_headers[position] == actual_headers[position]
        )
        rate = ordered_matches / denominator
        order_mismatch = actual_headers != expected_headers
    else:
        denominator = max(1, len(expected_headers))
        ordered_matches = len(expected_set & actual_set)
        positions = [
            actual_headers.index(value)
            for value in expected_headers
            if value in actual_set
        ]
        order_mismatch = positions != sorted(positions)
        rate = 0.0 if order_mismatch else ordered_matches / denominator
    evidence.update(
        {
            "missing_date_headers": missing,
            "extra_date_headers": extra,
            "ordered_position_matches": ordered_matches,
            "evaluated_date_header_count": denominator,
            "order_mismatch": order_mismatch,
        }
    )
    mismatch = bool(
        missing or order_mismatch or (coverage == "exact" and extra)
    )
    return WeekAxisResult(
        rate,
        "MISMATCH" if mismatch else "PASS",
        "SITE_ROLLOUT_WEEK_AXIS_MISMATCH" if mismatch else "",
        expected,
        evidence,
    )


def score_gap_zero_business(
    frame: pd.DataFrame | None,
    blocks: Mapping[tuple[str, str], Mapping[str, Any]],
    aggregate_blocks: Mapping[tuple[str, str], Mapping[str, Any]],
    weeks: tuple[int, ...],
    metrics: Iterable[str],
) -> WeekAxisResult:
    """Require explicitly declared GAP recovery/reuse fields to exist and be zero."""

    requested = tuple(str(value) for value in metrics)
    weekly_metrics = tuple(
        value for value in requested if value in _GAP_ZERO_WEEKLY_METRICS
    )
    summary_metrics = tuple(
        value for value in requested if value in _GAP_ZERO_SUMMARY_METRICS
    )
    evidence: dict[str, Any] = {
        "declared_metrics": list(requested),
        "weekly_metrics": list(weekly_metrics),
        "summary_metrics": list(summary_metrics),
        "weeks": list(weeks),
    }
    source_blocks = blocks or aggregate_blocks
    if not isinstance(frame, pd.DataFrame) or not source_blocks:
        evidence.update(
            {
                "block_count": len(source_blocks),
                "evaluated_unit_count": 0,
                "matched_zero_unit_count": 0,
                "missing_unit_count": len(requested),
                "nonzero_unit_count": 0,
                "missing_unit_samples": [],
                "nonzero_unit_samples": [],
                "error": "gap zero-business evidence is missing or unusable",
            }
        )
        return WeekAxisResult(
            0.0,
            "UNRESOLVED",
            "GAP_ZERO_BUSINESS_CONTRACT_UNRESOLVED",
            weeks,
            evidence,
        )

    actual_header_keys = {
        "".join(
            character
            for character in str(column).casefold()
            if character.isalnum()
        )
        for column in frame.columns
    }
    matched = 0
    denominator = 0
    missing_units: list[dict[str, Any]] = []
    nonzero_units: list[dict[str, Any]] = []
    for key, block in sorted(source_blocks.items()):
        series = dict(block.get("metrics", {})) if blocks else {}
        summary = dict(block.get("summary", {}))
        for metric in weekly_metrics:
            values = series.get(metric)
            for week in weeks or (None,):
                denominator += 1
                if not isinstance(values, Mapping) or week is None or week not in values:
                    missing_units.append(
                        {"block": list(key), "metric": metric, "week": week}
                    )
                    continue
                value = float(values[week])
                if abs(value) <= 0.000001:
                    matched += 1
                else:
                    nonzero_units.append(
                        {
                            "block": list(key),
                            "metric": metric,
                            "week": week,
                            "actual": value,
                        }
                    )
        for metric in summary_metrics:
            denominator += 1
            required_header = "".join(
                character
                for character in _GAP_ZERO_SUMMARY_HEADERS[metric].casefold()
                if character.isalnum()
            )
            if required_header not in actual_header_keys or metric not in summary:
                missing_units.append(
                    {"block": list(key), "metric": metric, "scope": "summary"}
                )
                continue
            value = float(summary[metric])
            if abs(value) <= 0.000001:
                matched += 1
            else:
                nonzero_units.append(
                    {
                        "block": list(key),
                        "metric": metric,
                        "scope": "summary",
                        "actual": value,
                    }
                )
    rate = matched / denominator if denominator else 0.0
    evidence.update(
        {
            "block_count": len(source_blocks),
            "evaluated_unit_count": denominator,
            "matched_zero_unit_count": matched,
            "missing_unit_count": len(missing_units),
            "nonzero_unit_count": len(nonzero_units),
            "missing_unit_samples": missing_units[:50],
            "nonzero_unit_samples": nonzero_units[:50],
        }
    )
    if nonzero_units:
        status = "MISMATCH"
        reason_code = "GAP_ZERO_BUSINESS_VIOLATION"
    elif missing_units:
        status = "UNRESOLVED"
        reason_code = "GAP_ZERO_BUSINESS_CONTRACT_UNRESOLVED"
    else:
        status = "PASS"
        reason_code = ""
    return WeekAxisResult(rate, status, reason_code, weeks, evidence)


def gap_week_contract_owner(context: RuleContext) -> str | None:
    """Assign a global GAP-axis defect to one enabled rule, never three."""

    if not {
        "gap_week_contract",
        "site_rollout_week_contract",
        "gap_zero_business_metrics",
    } & set(context.component.parameters):
        return None
    configured = {
        check.check_id.rsplit(".", 1)[-1] for check in context.component.checks
    }
    return next((rule_id for rule_id in ("S2", "S3", "S4") if rule_id in configured), None)


def apply_gap_week_axis(
    context: RuleContext,
    result: CheckResult,
    *,
    rule_id: str,
    axis: WeekAxisResult | None,
    site_rollout_axis: WeekAxisResult | None = None,
    gap_zero_business: WeekAxisResult | None = None,
) -> CheckResult:
    """Conjoin auxiliary week axes with their single owning S2/S3/S4 leaf."""

    axes = {
        name: value
        for name, value in (
            ("gap_week_contract", axis),
            ("site_rollout_week_contract", site_rollout_axis),
            ("gap_zero_business_metrics", gap_zero_business),
        )
        if value is not None
    }
    if not axes or gap_week_contract_owner(context) != rule_id:
        return result
    evidence = dict(result.evidence)
    for name, value in axes.items():
        evidence[name] = dict(value.evidence)
    if result.status in {"UNSCORABLE", "NOT_APPLICABLE", "QUESTION_CONTRACT_INCOMPLETE"}:
        return replace(result, evidence=evidence)
    combined_axis_rate = 1.0
    for value in axes.values():
        combined_axis_rate *= value.rate
    if combined_axis_rate >= 0.999999:
        return replace(result, evidence=evidence)
    evidence["base_reason_code"] = result.reason_code
    evidence["base_score"] = result.score
    if result.score <= 0.000001:
        return replace(result, evidence=evidence)
    unresolved = [
        name for name, value in axes.items() if value.status == "UNRESOLVED"
    ]
    if unresolved == ["gap_week_contract"]:
        reason_code = "GAP_WEEK_CONTRACT_UNRESOLVED"
    elif unresolved == ["site_rollout_week_contract"]:
        reason_code = "SITE_ROLLOUT_WEEK_CONTRACT_UNRESOLVED"
    elif unresolved == ["gap_zero_business_metrics"]:
        reason_code = "GAP_ZERO_BUSINESS_CONTRACT_UNRESOLVED"
    elif unresolved:
        reason_code = "AUXILIARY_WEEK_CONTRACT_UNRESOLVED"
    elif gap_zero_business is not None and gap_zero_business.rate < 0.999999:
        reason_code = "GAP_ZERO_BUSINESS_VIOLATION"
    elif site_rollout_axis is not None and site_rollout_axis.rate < 0.999999:
        reason_code = "SITE_ROLLOUT_WEEK_CONTRACT_MISMATCH"
    else:
        reason_code = "GAP_WEEK_CONTRACT_MISMATCH"
    return leaf(
        context,
        rule_id,
        result.name,
        (result.score / 100.0) * combined_axis_rate,
        result.explanation + "; auxiliary week columns must satisfy their Prompt week-axis contracts",
        evidence,
        reason_code=reason_code,
    )


__all__ = [
    "WeekAxisResult",
    "apply_gap_week_axis",
    "expected_week_axis",
    "gap_week_contract_owner",
    "score_gap_zero_business",
    "score_site_rollout_week_axis",
    "score_warehouse_week_axis",
    "score_week_axis",
]
