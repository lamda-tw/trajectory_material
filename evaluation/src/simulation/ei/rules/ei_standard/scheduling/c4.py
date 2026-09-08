"""C4 valid delivery month."""

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from ..common import _key
from .evidence import SchedulingEvidence


def score_c4(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    valid = 0
    for _, row in evidence.installs.iterrows():
        month = row["month"]
        cap = (
            0.0
            if month is None or pd.isna(month)
            else evidence.master_by_region.get(
                (_key(row["region"]), int(month)),
                evidence.master_by_region.get(("all", int(month)), 0.0),
            )
        )
        valid += int(cap > 0)
    return leaf(
        context,
        "C4",
        "Valid delivery month",
        valid / len(evidence.installs) if len(evidence.installs) else 0.0,
        "Installations must fall in months present in the authoritative plan",
        {"install_sites": len(evidence.installs), "valid": valid},
    )
