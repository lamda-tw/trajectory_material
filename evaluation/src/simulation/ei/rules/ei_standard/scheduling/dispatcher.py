"""Explicit leaf dispatchers with rule-local evidence failure isolation."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import evaluator_error_leaf, failed_leaf, table
from .c1 import score_c1
from .c2 import score_c2
from .c3 import score_c3
from .c4 import score_c4
from .c5 import score_c5
from .c6a import score_c6a
from .c6b import score_c6b
from .evidence import (
    SchedulingAuthority,
    prepare_scheduling_evidence,
    scheduling_evidence_failure,
)
from .o1 import score_o1
from .parsing import _candidate_plan


def _configured_local_ids(context: RuleContext) -> tuple[str, ...]:
    return tuple(
        check.check_id.split(".", 1)[1]
        for check in context.component.checks
    )


def score_scheduling(
    context: RuleContext,
    *,
    authority: SchedulingAuthority | None = None,
    plan: pd.DataFrame | None = None,
) -> tuple[CheckResult, ...]:
    configured = _configured_local_ids(context)
    if plan is None:
        raw_plan = table(context, "site_plan")
        if raw_plan is None:
            return tuple(
                failed_leaf(
                    context,
                    rule_id,
                    rule_id,
                    "MISSING_ARTIFACT",
                    "Prompt-required site_plan artifact is missing or structurally unusable",
                )
                for rule_id in configured
            )
        try:
            plan = _candidate_plan(
                raw_plan,
                project_week_source=str(
                    context.component.parameters.get("project_week_source", "reconcile")
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return tuple(
                failed_leaf(
                    context,
                    rule_id,
                    rule_id,
                    "INVALID_ARTIFACT",
                    "site_plan cannot be parsed under the prompt contract",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
                for rule_id in configured
            )
    evidence, evidence_failures = prepare_scheduling_evidence(
        context,
        plan,
        authority=authority,
    )
    scorers = {
        "C1": score_c1,
        "C2": score_c2,
        "C3": score_c3,
        "C4": score_c4,
        "C5": score_c5,
        "C6a": score_c6a,
        "C6b": score_c6b,
    }
    checks: list[CheckResult] = []
    for rule_id in configured:
        dependency_error = scheduling_evidence_failure(
            rule_id,
            evidence,
            evidence_failures,
        )
        if dependency_error is not None:
            checks.append(evaluator_error_leaf(context, rule_id, dependency_error))
            continue
        try:
            checks.append(scorers[rule_id](context, evidence))
        except Exception as exc:  # noqa: BLE001
            checks.append(evaluator_error_leaf(context, rule_id, exc))
    return tuple(checks)


def score_pacing(
    context: RuleContext,
    *,
    plan: pd.DataFrame | None = None,
) -> tuple[CheckResult, ...]:
    try:
        result = score_o1(context, plan=plan)
    except Exception as exc:  # noqa: BLE001
        result = evaluator_error_leaf(context, "O1", exc)
    return (result,)
