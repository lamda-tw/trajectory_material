from __future__ import annotations

from .support import (
    assert_full_score_contract,
    checks_by_rule,
    flow_context,
)


def test_s3_runs_independently_with_reuse_warehouse_balance_evidence() -> None:
    checks = checks_by_rule(flow_context(("S3",)))

    assert set(checks) == {"S3"}
    check = checks["S3"]
    assert_full_score_contract(check, "S3")
    assert check.evidence["files"] == 1
    assert check.evidence["cells"] == 1
    assert check.evidence["valid"] == 1
    assert check.evidence["invalid"] == 0
