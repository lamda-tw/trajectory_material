from __future__ import annotations

from .support import (
    assert_full_score_contract,
    checks_by_rule,
    material_context,
)


def test_s5_runs_independently_with_authoritative_quantity_recall() -> None:
    checks = checks_by_rule(material_context(("S5",)))

    assert set(checks) == {"S5"}
    check = checks["S5"]
    assert_full_score_contract(check, "S5")
    assert check.evidence["unit"] == "original_bom_quantity_in_scheduled_site_action"
    assert check.evidence["authoritative_quantity"] == 1
    assert check.evidence["covered_quantity"] == 1
    assert check.evidence["recall_rate"] == 1.0
