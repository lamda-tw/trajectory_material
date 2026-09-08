from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("site_plan")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_site_plan_structure_is_resolved_without_rewriting_source(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "site_plan", case)

    assert_case_contract(result, case)
    assert result.selected_path.name == case["filename"]
