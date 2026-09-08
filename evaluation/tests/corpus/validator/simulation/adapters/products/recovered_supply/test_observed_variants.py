from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("recovered_supply")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_recovered_supply_structure_preserves_week_dialects(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "recovered_supply", case)

    assert_case_contract(result, case)
