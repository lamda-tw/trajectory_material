"""C2 site-action consistency."""

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from .evidence import SchedulingEvidence


def score_c2(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    drop_selection = evidence.drop_selection
    dropped = (
        set(drop_selection.dropped_install_site_keys)
        if drop_selection is not None
        else set()
    )
    expected_rows = evidence.expected.loc[
        ~evidence.expected["site_key"].isin(dropped)
    ]
    expected = set(expected_rows["action_key"])
    actual = set(evidence.plan["action_key"])
    union = expected | actual
    rate = len(expected & actual) / len(union) if union else 0.0
    return leaf(
        context,
        "C2",
        "Site action consistency",
        rate,
        "Matched site actions divided by the union of required and candidate actions",
        {
            "expected": len(expected),
            "actual": len(actual),
            "drop_selection": (
                drop_selection.evidence() if drop_selection is not None else None
            ),
            "pre_drop_expected": len(set(evidence.expected["action_key"])),
            "dropped_expected_actions": len(evidence.expected) - len(expected_rows),
        },
    )
