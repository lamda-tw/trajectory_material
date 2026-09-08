from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("site_material_timeline")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_timeline_structure_preserves_week_action_and_quantity_evidence(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "site_material_timeline", case)

    assert_case_contract(result, case)
