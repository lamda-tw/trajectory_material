"""S4 new-warehouse balance scoring."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .evidence import GapEvidence
from .warehouse_rule import score_warehouse_rule


def score_s4(
    context: RuleContext,
    gap: GapEvidence,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> CheckResult:
    return score_warehouse_rule(
        context,
        "S4",
        gap,
        scheduled_plan=scheduled_plan,
    )
