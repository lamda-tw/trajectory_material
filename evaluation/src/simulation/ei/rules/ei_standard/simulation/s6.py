"""S6 final-BOM action-time scoring."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import (
    failed_leaf,
    leaf,
    table,
)
from .time import _time_accuracy


def score_s6(
    context: RuleContext,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> CheckResult:
    parameters = context.component.parameters
    final = table(context, 'final_material')
    plan_frame = table(context, 'site_plan')
    if final is None:
        return failed_leaf(context, 'S6', 'Final-BOM action-time accuracy', 'MISSING_FINAL_MATERIAL', 'site_final_bom is missing or unusable')
    elif plan_frame is None:
        return failed_leaf(context, 'S6', 'Final-BOM action-time accuracy', 'MISSING_SITE_PLAN', 'site_plan is missing or unusable')
    else:
        try:
            rate, evidence = _time_accuracy(plan_frame, final, time_mode=str(parameters.get('s6_time_mode', 'action-week-month')), week_kind=str(parameters.get('s6_week_kind', 'project')), project_week_source=str(parameters.get('project_week_source', 'reconcile')), planning_year=int(parameters.get('planning_year', 2027)), week_to_month=str(parameters.get('week_to_month', 'calendar')), project_start_month=int(parameters.get('project_start_month', 1)), require_inactive_time_blank=bool(parameters.get('s6_require_inactive_time_blank', True)), scheduled_plan=scheduled_plan)
            evidence['time_correct_actions'] = int(evidence['passed_actions'])
            evidence['time_accuracy'] = rate
            return leaf(context, 'S6', 'Final-BOM action-time accuracy', rate, 'Each comparable site action is checked once against site_plan', evidence, reason_code='' if rate >= 0.999999 else 'NO_COMPARABLE_TIME_UNITS' if int(evidence['comparable_actions']) == 0 else 'FINAL_ACTION_TIME_MISMATCH')
        except Exception as exc:
            return failed_leaf(context, 'S6', 'Final-BOM action-time accuracy', 'INVALID_ARTIFACT', 'Final-BOM time evidence cannot be parsed', {'error': str(exc)})
