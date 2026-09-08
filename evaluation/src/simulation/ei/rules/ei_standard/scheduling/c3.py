"""C3 monthly delivery capacity."""

import math
from collections import defaultdict

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from ..common import _key
from .evidence import SchedulingEvidence


def score_c3(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    actual: dict[tuple[str, int], int] = defaultdict(int)
    for _, row in evidence.installs.dropna(subset=["month"]).iterrows():
        actual[(_key(row["region"]), int(row["month"]))] += 1
    factor = float(evidence.parameters.get("capacity_factor", 1.0))
    excess = 0.0
    for key, value in actual.items():
        cap = evidence.master_by_region.get(
            key,
            evidence.master_by_region.get(("all", key[1]), 0.0),
        )
        excess += max(0.0, value - math.floor(cap * factor + 1e-9))
    rate = 1.0 - excess / len(evidence.installs) if len(evidence.installs) else 0.0
    return leaf(
        context,
        "C3",
        "Monthly delivery capacity",
        rate,
        "Candidate installations must not exceed the prompt-authorized monthly capacity",
        {
            "install_sites": len(evidence.installs),
            "excess_sites": excess,
            "capacity_factor": factor,
        },
    )
