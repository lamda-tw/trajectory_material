from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("new_warehouse")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_new_warehouse_filename_and_shape_is_resolved(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "new_warehouse", case)

    assert_case_contract(result, case)
