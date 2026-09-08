"""S3 reuse-warehouse balance scoring."""

from __future__ import annotations

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .evidence import GapEvidence
from .warehouse_rule import score_warehouse_rule


def score_s3(
    context: RuleContext,
    gap: GapEvidence,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> CheckResult:
    return score_warehouse_rule(
        context,
        "S3",
        gap,
        scheduled_plan=scheduled_plan,
    )
