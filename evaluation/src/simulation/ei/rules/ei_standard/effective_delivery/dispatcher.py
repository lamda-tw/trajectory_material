"""Explicit O2 dispatcher with leaf-local evaluator isolation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import evaluator_error_leaf
from .o2 import score_o2


def score_effective_delivery(
    context: RuleContext,
    *,
    authority: Mapping[str, Any] | None = None,
) -> tuple[CheckResult, ...]:
    checks: list[CheckResult] = []
    for configured in context.component.checks:
        rule_id = configured.check_id.split(".", 1)[1]
        try:
            if rule_id != "O2":
                raise ValueError(f"unsupported effective-delivery rule: {rule_id}")
            checks.append(score_o2(context, authority=authority))
        except Exception as exc:  # noqa: BLE001 - isolate one configured leaf
            checks.append(evaluator_error_leaf(context, rule_id, exc))
    return tuple(checks)
