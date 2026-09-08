from __future__ import annotations

from simulation.ei.core.models import ArtifactSpec
from simulation.ei.core.adapters import resolve_artifacts
from simulation.ei.core.adapters._shared import _resolved_artifact

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    make_profile,
    write_csv_case,
)


def _diagnostic(result):
    return next(
        item
        for item in result.resolution_diagnostics
        if item["code"] == "REGION_ALIAS_APPLIED"
    )


def test_region_alias_normalizes_row_values_before_product_adapter(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    relative = "project/model_output/site_plan.csv"
    write_csv_case(
        run / relative,
        {
            "headers": ["site_name", "site_action", "region"],
            "rows": [["SITE-A", "install", "BMA"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("project",),
        canonical_path=relative,
        filenames=("site_plan.csv",),
        schema_options={"region_aliases": {"BMA": "Region-1"}},
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_CANONICAL"
    assert result.table.loc[0, "region"] == "Region-1"
    assert result.normalized.loc[0, "region"] == "Region-1"
    diagnostic = _diagnostic(result)
    assert diagnostic["score_effect"] == "none"
    assert diagnostic["applied_count"] == 1
    assert diagnostic["examples"] == [
        {
            "location": "region",
            "raw_region": "BMA",
            "normalized_region": "Region-1",
            "row": 2,
        }
    ]


def test_region_alias_normalizes_dynamic_summary_column(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    relative = "project/model_output/reuse_by_region.csv"
    write_csv_case(
        run / relative,
        {
            "headers": ["item_code", "metric", "BMA", "Total"],
            "rows": [["Grand Summary", "Dismantled", "5", "5"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="reuse_by_region",
        schema="ei.reuse-summary",
        artifact_roots=("project",),
        canonical_path=relative,
        filenames=("reuse_by_region.csv",),
        schema_options={"region_aliases": {"BMA": "Region-1"}},
    )

    result = resolve_artifacts(profile, run, repository).get("reuse_by_region")

    assert result.status == "SELECTED_CANONICAL"
    assert result.table.attrs["source_headers"] == (
        "item_code",
        "metric",
        "Region-1",
        "Total",
    )
    assert result.normalized[0]["regions"] == {"Region-1": 5}
    assert _diagnostic(result)["examples"] == [
        {
            "location": "column_header",
            "raw_region": "BMA",
            "normalized_region": "Region-1",
        }
    ]


def test_region_alias_collision_is_not_silently_merged(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    relative = "project/model_output/reuse_by_region.csv"
    write_csv_case(
        run / relative,
        {
            "headers": [
                "item_code",
                "metric",
                "BMA",
                "Region-1",
                "Total",
            ],
            "rows": [["Grand Summary", "Dismantled", "2", "3", "5"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="reuse_by_region",
        schema="ei.reuse-summary",
        artifact_roots=("project",),
        canonical_path=relative,
        filenames=("reuse_by_region.csv",),
        schema_options={"region_aliases": {"BMA": "Region-1"}},
    )

    result = resolve_artifacts(profile, run, repository).get("reuse_by_region")

    assert result.status == "PARSE_ERROR"
    assert "region alias normalization creates duplicate columns" in result.error


def test_region_alias_normalizes_region_label_exposed_by_product_adapter(
    tmp_path,
) -> None:
    path = tmp_path / "master_plan.csv"
    write_csv_case(
        path,
        {
            "headers": ["month", "curve"],
            "rows": [["", "BMA"], ["2023M1", "10"]],
        },
    )
    spec = ArtifactSpec(
        role="master_plan",
        source="candidate",
        path="master_plan.csv",
        filenames=("master_plan.csv",),
        schema="generic",
        required=True,
        schema_options={"region_aliases": {"BMA": "Region-1"}},
    )

    result = _resolved_artifact(
        spec,
        path,
        status="SELECTED_CANONICAL",
        normalization_options={
            "region_aliases": {"BMA": "Region-1"},
            "_effective_delivery": {
                "o2_master_format": "standard",
                "o2_planning_year": 2023,
            },
        },
    )

    assert result.status == "SELECTED_CANONICAL"
    assert result.normalized["region"].tolist() == ["Region-1"]
    diagnostic = _diagnostic(result)
    assert diagnostic["applied_count"] == 1
    assert diagnostic["examples"] == [
        {
            "location": "region",
            "raw_region": "BMA",
            "normalized_region": "Region-1",
            "row": 2,
        }
    ]
