from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("material_substitution")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_substitution_structure_keeps_blank_text_and_decimal_quantities(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "material_substitution", case)

    assert_case_contract(result, case)
