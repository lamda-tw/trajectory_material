from __future__ import annotations

from .support import (
    assert_full_score_contract,
    checks_by_rule,
    material_context,
)


def test_s6_runs_independently_with_week_and_month_accuracy_evidence() -> None:
    checks = checks_by_rule(material_context(("S6",)))

    assert set(checks) == {"S6"}
    check = checks["S6"]
    assert_full_score_contract(check, "S6")
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 1
    assert check.evidence["time_accuracy"] == 1.0
