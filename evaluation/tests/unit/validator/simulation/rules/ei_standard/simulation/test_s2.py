from __future__ import annotations

from .support import (
    assert_full_score_contract,
    checks_by_rule,
    flow_context,
)


def test_s2_runs_independently_with_gap_and_warehouse_maturity_evidence() -> None:
    checks = checks_by_rule(flow_context(("S2",)))

    assert set(checks) == {"S2"}
    check = checks["S2"]
    assert_full_score_contract(check, "S2")
    assert check.evidence["evidence_level"] == "weekly"
    assert check.evidence["maturity_interval"]["matched_qty"] == 3.0
    assert check.evidence["warehouse_inbound"]["matched_qty"] == 3.0
