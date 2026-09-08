from __future__ import annotations

import pytest

from simulation.ei.core.adapters import resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    issue_codes,
    make_profile,
    write_csv_case,
)


def _resolve(tmp_path, *, schema, filename, headers, required_columns):
    repository, _, run = build_layout(tmp_path)
    relative = f"56TESTPK/MaterialCycleEI/model_output/{filename}"
    write_csv_case(
        run / relative,
        {"headers": headers, "rows": [["1" for _ in headers]]},
    )
    profile = make_profile(
        tmp_path,
        role="artifact",
        schema=schema,
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=relative,
        filenames=(filename,),
        schema_options={"required_columns": required_columns},
    )
    return resolve_artifacts(profile, run, repository).get("artifact")


def test_profile_can_authorize_a_site_plan_contract_without_action(tmp_path) -> None:
    columns = [
        "site_name", "site_type", "mos_weekly_plan", "week_num",
        "delivery_region", "warehouse", "dependency", "status_category",
        "po_status", "project_category",
    ]

    result = _resolve(
        tmp_path,
        schema="ei.site-plan",
        filename="site_plan.csv",
        headers=columns,
        required_columns=columns,
    )

    assert result.usable
    assert result.candidates[0].required_coverage == 1.0
    assert "MISSING_REQUIRED_COLUMN" not in issue_codes(result)


def test_profile_specific_missing_column_remains_visible_to_rule_judgement(
    tmp_path,
) -> None:
    required = [
        "solution_id", "priority", "target_item_code", "target_qty",
        "sub_item_code", "sub_qty", "new_issue_item_code",
    ]

    result = _resolve(
        tmp_path,
        schema="ei.material-substitution",
        filename="material_substitution.csv",
        headers=required[:-1],
        required_columns=required,
    )

    assert result.usable
    assert result.candidates[0].required_coverage == pytest.approx(6 / 7, abs=1e-6)
    assert "MISSING_REQUIRED_COLUMN" in issue_codes(result)
