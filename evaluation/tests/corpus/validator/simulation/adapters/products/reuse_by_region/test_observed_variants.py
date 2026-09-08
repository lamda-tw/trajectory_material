from __future__ import annotations

import pytest

from evaluation.tests.helpers.simulation_adapter_factory import assert_case_contract, product_case_params, resolve_case


CASES = product_case_params("reuse_by_region")


@pytest.mark.parametrize("case", CASES)
def test_each_observed_reuse_summary_region_layout_retains_metric_values(
    case, tmp_path
) -> None:
    result = resolve_case(tmp_path, "reuse_by_region", case)

    assert_case_contract(result, case)
    if case["id"] in {
        "four_regions", "one_region", "bma", "region_bma", "three_regions", "vietnam_regions"
    }:
        assert result.normalized
        assert set(result.normalized[0]["regions"]) == set(case["headers"][2:-1])
    else:
        assert result.normalized == []
