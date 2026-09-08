from __future__ import annotations

import pytest

from simulation.ei.core.adapters import resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    make_profile,
    write_xlsx_case,
)


def _profile(tmp_path):
    return make_profile(
        tmp_path,
        role="timeline",
        schema="ei.timeline",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/model_output/site_material_timeline.csv",
        filenames=("site_material_timeline.csv",),
    )


@pytest.mark.xfail(
    strict=True,
    reason="66 observed non-site-plan XLSX artifacts are invisible unless every XLSX alias is enumerated in the profile",
)
def test_same_stem_xlsx_serialization_is_resolved_as_the_standard_product(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    path = run / "56TESTPK/MaterialCycleEI/model_output/site_material_timeline.xlsx"
    write_xlsx_case(
        path,
        {
            "headers": ["site_name", "item_code", "required_qty", "action", "week_num"],
            "rows": [["SITE-A", "A", "1", "install", "27"]],
        },
    )

    result = resolve_artifacts(_profile(tmp_path), run, repository).get("timeline")

    assert result.selected_path == path.resolve()


@pytest.mark.xfail(
    strict=True,
    reason="7 observed JSON artifacts are invisible unless every JSON alias is enumerated in the profile",
)
def test_same_stem_json_serialization_is_resolved_as_the_standard_product(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    path = run / "56TESTPK/MaterialCycleEI/model_output/site_material_timeline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[{"site_name":"SITE-A","item_code":"A","required_qty":1,"action":"install","week_num":27}]',
        encoding="utf-8",
    )

    result = resolve_artifacts(_profile(tmp_path), run, repository).get("timeline")

    assert result.selected_path == path.resolve()
