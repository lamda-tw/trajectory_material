"""Explicit R3/R5/R6 dispatcher; rule ordering follows validator.yaml."""

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import evaluator_error_leaf, normalized
from .r3 import score_r3
from .r5 import score_r5
from .r6 import score_r6


def score_reuse(context: RuleContext) -> tuple[CheckResult, ...]:
    summary_rows = normalized(context, "reuse_by_region")
    scorers = {
        "R3": lambda: score_r3(context),
        "R5": lambda: score_r5(context, summary_rows),
        "R6": lambda: score_r6(context, summary_rows),
    }
    checks = []
    for rule_id in (
        check.check_id.split(".", 1)[1] for check in context.component.checks
    ):
        try:
            checks.append(scorers[rule_id]())
        except Exception as exc:  # noqa: BLE001
            checks.append(evaluator_error_leaf(context, rule_id, exc))
    return tuple(checks)
