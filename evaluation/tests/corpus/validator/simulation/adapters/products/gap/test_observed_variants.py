from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("gap")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_gap_horizon_is_visible_to_exact_schema_validation(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "gap", case)

    assert_case_contract(result, case)
