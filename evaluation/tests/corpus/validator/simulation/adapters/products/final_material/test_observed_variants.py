from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("final_material")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_final_material_structure_preserves_fractional_raw_evidence(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "final_material", case)

    assert_case_contract(result, case)
