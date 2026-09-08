from __future__ import annotations

from .support import (
    assert_full_score_contract,
    checks_by_rule,
    material_context,
)


def test_s1_runs_independently_with_model_and_application_evidence() -> None:
    checks = checks_by_rule(material_context(("S1",)))

    assert set(checks) == {"S1"}
    check = checks["S1"]
    assert_full_score_contract(check, "S1")
    assert check.evidence["formula"] == "F_model * P_apply"
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.evidence["final_rate"] == 1.0
