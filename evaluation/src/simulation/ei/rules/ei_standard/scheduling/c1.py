"""C1 required-site completion."""

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from .evidence import SchedulingEvidence


def score_c1(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    drop_selection = evidence.drop_selection
    dropped = (
        set(drop_selection.dropped_install_site_keys)
        if drop_selection is not None
        else set()
    )
    expected = evidence.expected_sites - dropped
    actual = evidence.actual_sites
    rate = len(expected & actual) / len(expected) if expected else 0.0
    return leaf(
        context,
        "C1",
        "Required site completion",
        rate,
        "Matched required sites divided by required sites",
        {
            "expected": len(expected),
            "matched": len(expected & actual),
            "site_scope": evidence.site_scope,
            "source_actions": evidence.source_action_count,
            "excluded_outside_batch_scope": evidence.excluded_action_count,
            "drop_selection": (
                drop_selection.evidence() if drop_selection is not None else None
            ),
            "pre_drop_expected": len(evidence.expected_sites),
            "dropped_expected_sites": len(dropped & evidence.expected_sites),
        },
    )
