from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("initial_warehouse")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_initial_warehouse_shape_is_resolved_and_diagnosed(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "initial_warehouse", case)

    assert_case_contract(result, case)
