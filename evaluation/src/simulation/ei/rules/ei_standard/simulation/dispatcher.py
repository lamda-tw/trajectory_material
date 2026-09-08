"""Explicit S1-S6 dispatcher; rule order follows validator.yaml."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext
from .._shared import evaluator_error_leaf
from .evidence import prepare_gap_evidence
from .s1 import score_s1
from .s2 import score_s2
from .s3 import score_s3
from .s4 import score_s4
from .s5 import score_s5
from .s6 import score_s6
from .week_contract import apply_gap_week_axis


def score_simulation(
    context: RuleContext,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> tuple[CheckResult, ...]:
    configured = tuple(
        check.check_id.split(".", 1)[1] for check in context.component.checks
    )
    gap = None
    gap_error = None
    if set(configured) & {"S2", "S3", "S4"}:
        try:
            gap = prepare_gap_evidence(context, scheduled_plan=scheduled_plan)
        except Exception as exc:  # noqa: BLE001
            gap_error = exc
    checks = []
    for rule_id in configured:
        try:
            if rule_id == "S1":
                checks.append(score_s1(context))
            elif rule_id == "S2":
                if gap_error is not None:
                    raise gap_error
                checks.append(score_s2(context, gap))
            elif rule_id == "S3":
                if gap_error is not None:
                    raise gap_error
                checks.append(
                    score_s3(context, gap, scheduled_plan=scheduled_plan)
                )
            elif rule_id == "S4":
                if gap_error is not None:
                    raise gap_error
                checks.append(
                    score_s4(context, gap, scheduled_plan=scheduled_plan)
                )
            elif rule_id == "S5":
                checks.append(score_s5(context, scheduled_plan=scheduled_plan))
            elif rule_id == "S6":
                checks.append(score_s6(context, scheduled_plan=scheduled_plan))
        except Exception as exc:  # noqa: BLE001
            checks.append(evaluator_error_leaf(context, rule_id, exc))
        checks[-1] = apply_gap_week_axis(
            context,
            checks[-1],
            rule_id=rule_id,
            axis=gap.week_axis if gap is not None else None,
            site_rollout_axis=(
                gap.site_rollout_axis if gap is not None else None
            ),
            gap_zero_business=(
                gap.gap_zero_business if gap is not None else None
            ),
        )
    return tuple(checks)
