from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("reuse_warehouse")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_reuse_warehouse_filename_shape_and_empty_file_is_handled(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "reuse_warehouse", case)

    assert_case_contract(result, case)
