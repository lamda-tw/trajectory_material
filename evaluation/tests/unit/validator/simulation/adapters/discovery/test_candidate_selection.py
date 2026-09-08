from __future__ import annotations

from simulation.ei.core.adapters import resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    make_profile,
    write_csv_case,
)


def _site_plan(path, *, complete: bool = True) -> None:
    headers = ["site_name", "site_action"] if complete else ["site_name"]
    write_csv_case(path, {"headers": headers, "rows": [["SITE-A"] + (["install"] if complete else [])]})


def test_schema_coverage_beats_prompt_filename_when_real_run_contains_both(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    _site_plan(run / "56TESTPK/MaterialCycleEI/model_output/site_plan.csv", complete=False)
    complete = run / "56TESTPK/MaterialCycleEI/data-pipeline/intermediate/plan.csv"
    _site_plan(complete)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv",
        filenames=("site_plan.csv", "plan.csv"),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.selected_path == complete.resolve()
    assert result.candidates[0].required_coverage == 1.0
    assert result.candidates[1].required_coverage == 0.5
    assert result.resolution_diagnostics == (
        {
            "code": "ARTIFACT_PATH_MISMATCH",
            "score_effect": "none",
            "canonical_path": (
                "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
            ),
            "selected_path": (
                "56TESTPK/MaterialCycleEI/data-pipeline/intermediate/plan.csv"
            ),
        },
    )


def test_canonical_parent_breaks_tie_across_three_observed_site_plan_locations(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    paths = [
        run / "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv",
        run / "56TESTPK/MaterialCycleEI/data-pipeline/intermediate/site_plan.csv",
        run / "56TESTPK/MaterialCycleEI/data-pipeline/script/site_plan/output/site_plan.csv",
    ]
    for path in paths:
        _site_plan(path)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/data-pipeline/intermediate/site_plan.csv",
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert len(result.candidates) == 3
    assert result.selected_path == paths[1].resolve()
    assert result.status == "SELECTED_CANONICAL"


def test_complete_canonical_beats_filename_alias_when_both_are_usable(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    folder = run / "56TESTPK/MaterialCycleEI/data-pipeline/model_output"
    long_name = folder / "new_warehouse_weekly_outflow.csv"
    wide_name = folder / "weekly_new_warehouse.csv"
    long_case = {
        "headers": ["scope", "item_code", "project_week", "opening", "inbound", "outbound", "closing"],
        "rows": [["North", "A", "WK5", "0", "2", "1", "1"]],
    }
    for path in (long_name, wide_name):
        write_csv_case(path, long_case)
    profile = make_profile(
        tmp_path,
        role="new_warehouse",
        schema="ei.warehouse",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/data-pipeline/model_output/weekly_new_warehouse.csv",
        filenames=("new_warehouse_weekly_outflow.csv", "weekly_new_warehouse.csv"),
        schema_options={"week_kind": "auto"},
    )

    result = resolve_artifacts(profile, run, repository).get("new_warehouse")

    assert len(result.candidates) == 2
    assert result.selected_path == wide_name.resolve()
    assert result.status == "SELECTED_CANONICAL"
    assert result.resolution_diagnostics == ()


def test_equal_fallback_copies_use_stable_path_order(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    paths = [
        run / "56TESTPK/MaterialCycleEI/copy-a/model_output/site_plan.csv",
        run / "56TESTPK/MaterialCycleEI/copy-b/model_output/site_plan.csv",
    ]
    for path in paths:
        _site_plan(path)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_FALLBACK"
    assert result.selected_path == paths[0].resolve()
    assert [item["code"] for item in result.resolution_diagnostics] == [
        "ARTIFACT_PATH_MISMATCH",
    ]


def test_fallbacks_apply_filename_rank_before_directory_rank(
    tmp_path,
) -> None:
    repository, _, run = build_layout(tmp_path)
    prompt_name = run / "56TESTPK/MaterialCycleEI/far/site_plan.csv"
    closer_alias = (
        run
        / "56TESTPK/MaterialCycleEI/data-pipeline/model_output/plan.csv"
    )
    for path in (prompt_name, closer_alias):
        _site_plan(path)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv", "plan.csv"),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_FALLBACK"
    assert result.selected_path == prompt_name.resolve()
    assert result.resolution_diagnostics[0]["code"] == (
        "ARTIFACT_PATH_MISMATCH"
    )


def test_equal_fallback_candidates_use_stable_path_order(
    tmp_path,
) -> None:
    repository, _, run = build_layout(tmp_path)
    first = run / "56TESTPK/MaterialCycleEI/copy-a/model_output/site_plan.csv"
    second = run / "56TESTPK/MaterialCycleEI/copy-b/model_output/site_plan.csv"
    _site_plan(first)
    write_csv_case(
        second,
        {
            "headers": ["site_name", "site_action"],
            "rows": [["SITE-B", "install"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_FALLBACK"
    assert result.selected_path == first.resolve()
    assert result.usable is True
    assert result.resolution_diagnostics[0]["code"] == "ARTIFACT_PATH_MISMATCH"


def test_complete_fallbacks_use_filename_then_path_rank(
    tmp_path,
) -> None:
    repository, _, run = build_layout(tmp_path)
    primary_name = run / "56TESTPK/MaterialCycleEI/copy/site_plan.csv"
    closer_alias = (
        run
        / "56TESTPK/MaterialCycleEI/data-pipeline/model_output/plan.csv"
    )
    _site_plan(primary_name)
    write_csv_case(
        closer_alias,
        {
            "headers": ["site_name", "site_action"],
            "rows": [["SITE-B", "install"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv", "plan.csv"),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_FALLBACK"
    assert result.selected_path == primary_name.resolve()
    diagnostic = result.resolution_diagnostics[0]
    assert diagnostic["code"] == "ARTIFACT_PATH_MISMATCH"
    assert diagnostic["selected_path"] == (
        "56TESTPK/MaterialCycleEI/copy/site_plan.csv"
    )


def test_normalization_rejected_canonical_falls_back_to_healthy_product(
    tmp_path,
) -> None:
    repository, _, run = build_layout(tmp_path)
    canonical = (
        run
        / "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
    )
    fallback = run / "56TESTPK/MaterialCycleEI/copy/site_plan.csv"
    write_csv_case(
        canonical,
        {
            "headers": [
                "site_name",
                "site_action",
                "BMA",
                "Region-1",
            ],
            "rows": [["SITE-A", "install", "1", "2"]],
        },
    )
    write_csv_case(
        fallback,
        {
            "headers": ["site_name", "site_action", "region"],
            "rows": [["SITE-A", "install", "BMA"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv",),
        schema_options={"region_aliases": {"BMA": "Region-1"}},
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_FALLBACK"
    assert result.selected_path == fallback.resolve()
    canonical_candidate = next(
        value for value in result.candidates if value.canonical
    )
    assert canonical_candidate.usable is False
    assert "duplicate columns" in canonical_candidate.error
    diagnostics = {
        value["code"]: value for value in result.resolution_diagnostics
    }
    assert diagnostics["REJECTED_CANDIDATE"]["path"] == (
        "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
    )
    assert diagnostics["REJECTED_CANDIDATE"]["canonical"] is True
    assert diagnostics["ARTIFACT_PATH_MISMATCH"]["selected_path"] == (
        "56TESTPK/MaterialCycleEI/copy/site_plan.csv"
    )
    assert result.normalized.loc[0, "region"] == "Region-1"


def test_complete_canonical_wins_over_different_complete_fallback_content(
    tmp_path,
) -> None:
    repository, _, run = build_layout(tmp_path)
    canonical = (
        run
        / "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
    )
    fallback = run / "56TESTPK/MaterialCycleEI/copy/site_plan.csv"
    _site_plan(canonical)
    write_csv_case(
        fallback,
        {
            "headers": ["site_name", "site_action"],
            "rows": [["SITE-B", "install"]],
        },
    )
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=(
            "56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv"
        ),
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.status == "SELECTED_CANONICAL"
    assert result.selected_path == canonical.resolve()
    # Missing optional/default product columns are validation evidence, not a
    # normalization failure that would make the canonical file ineligible.
    assert result.validation_issues
    assert result.resolution_diagnostics == ()
