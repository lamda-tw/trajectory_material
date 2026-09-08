from __future__ import annotations

from .support import assert_full_score_contract, checks_by_rule, flow_context


def test_s4_runs_independently_with_new_warehouse_balance_evidence() -> None:
    checks = checks_by_rule(flow_context(("S4",)))

    assert set(checks) == {"S4"}
    check = checks["S4"]
    assert_full_score_contract(check, "S4")
    assert check.evidence["files"] == 1
    assert check.evidence["cells"] == 1
    assert check.evidence["valid"] == 1
    assert check.evidence["invalid"] == 0
