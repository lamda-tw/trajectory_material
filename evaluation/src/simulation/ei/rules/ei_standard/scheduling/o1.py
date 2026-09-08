"""O1 normalized monthly delivery pacing."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import failed_leaf, leaf, normalized, table
from ..common import _master_plan, _periods_from_frame
from .parsing import _candidate_plan


def score_o1(
    context: RuleContext,
    *,
    plan: pd.DataFrame | None = None,
) -> CheckResult:
    normalized_plan = normalized(context, "site_plan")
    if isinstance(normalized_plan, pd.DataFrame):
        try:
            plan = _candidate_plan(normalized_plan)
        except Exception:
            # The rule-local parsed plan remains a safe fallback for legacy
            # adapter results that predate the canonical site-plan columns.
            pass
    if plan is None:
        raw_plan = table(context, "site_plan")
        if raw_plan is None:
            return failed_leaf(
                context,
                "O1",
                "Monthly delivery pacing",
                "MISSING_ARTIFACT",
                "site_plan is missing or unusable",
            )
        try:
            plan = _candidate_plan(raw_plan)
        except Exception as exc:  # noqa: BLE001
            return failed_leaf(
                context,
                "O1",
                "Monthly delivery pacing",
                "INVALID_ARTIFACT",
                "site_plan cannot be parsed",
                {"error": str(exc)},
            )
    parameters = context.component.parameters
    master_format = str(parameters.get("master_format", "standard"))
    normalized_master = normalized(context, "master_plan")
    master_input = (
        normalized_master
        if isinstance(normalized_master, pd.DataFrame)
        else table(context, "master_plan")
    )
    if master_input is None:
        raise FileNotFoundError("configured authoritative master plan is missing")
    planning_year = int(parameters.get("planning_year", 2027))
    if isinstance(normalized_master, pd.DataFrame) and {
        "period",
        "planned_count",
    } <= set(normalized_master.columns):
        canonical = normalized_master[["period", "planned_count"]].copy()
        canonical["period"] = pd.to_numeric(canonical["period"], errors="coerce")
        canonical["planned_count"] = pd.to_numeric(
            canonical["planned_count"], errors="coerce"
        )
        canonical = canonical.dropna(subset=["period", "planned_count"])
        if canonical.empty:
            raise ValueError("normalized master_plan produced no period quantities")
        if not canonical["period"].map(
            lambda value: float(value).is_integer()
        ).all():
            raise ValueError("normalized master_plan period must be integer YYYYMM")
        master = {
            int(period): float(count)
            for period, count in canonical.groupby("period", sort=True)[
                "planned_count"
            ].sum().items()
        }
    else:
        _, legacy_master = _master_plan(
            master_input,
            sheet_hint=str(parameters.get("master_sheet_hint", "")),
            planning_year=planning_year,
            master_format=master_format,
        )
        master = {
            (planning_year + (int(month) - 1) // 12) * 100
            + (int(month) - 1) % 12
            + 1: value
            for month, value in legacy_master.items()
        }
    installs = plan[plan["action"] == "install"].drop_duplicates("site_key")
    period_counts = _periods_from_frame(
        installs,
        planning_year,
        week_to_month=str(parameters.get("week_to_month", "calendar")),
        project_start_month=int(parameters.get("project_start_month", 1)),
    ).dropna().value_counts()
    actual = {
        int(period): int(count)
        for period, count in period_counts.items()
    }
    periods = sorted(set(master) | set(actual))
    expected_total = sum(master.values())
    actual_total = sum(actual.values())
    if expected_total <= 0 or actual_total <= 0:
        rate = 0.0
    else:
        distance = 0.5 * sum(
            abs(
                master.get(period, 0.0) / expected_total
                - actual.get(period, 0.0) / actual_total
            )
            for period in periods
        )
        rate = 1.0 - distance
    return leaf(
        context,
        "O1",
        "Monthly delivery pacing",
        rate,
        "Compare normalized candidate and authoritative monthly delivery curves",
        {
            "master_total": expected_total,
            "actual_total": actual_total,
            "periods": periods,
            "master_curve": {str(key): master[key] for key in sorted(master)},
            "actual_curve": {str(key): actual[key] for key in sorted(actual)},
        },
    )
