from __future__ import annotations

import pytest

from simulation.ei.core.adapters import resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    load_corpus,
    make_profile,
    write_csv_case,
)


TOPOLOGIES = load_corpus()["discovery_topologies"]
SITE_PLAN = {
    "headers": ["site_name", "site_action"],
    "rows": [["SITE-A", "install"]],
}


@pytest.mark.parametrize("topology", TOPOLOGIES, ids=lambda value: value["id"])
def test_discovery_matches_the_directory_boundaries_observed_in_eval_results(
    topology, tmp_path
) -> None:
    repository, _, run = build_layout(tmp_path)
    write_csv_case(run / topology["path"], SITE_PLAN)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/data-pipeline/model_output/site_plan.csv",
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    if topology["expected"] == "discoverable":
        assert result.usable, topology["source"]
        assert result.selected_path == (run / topology["path"]).resolve()
    else:
        assert result.status == "MISSING", topology["source"]


def test_score_and_cache_trees_cannot_compete_with_a_business_output(tmp_path) -> None:
    repository, _, run = build_layout(tmp_path)
    selected = run / "56TESTPK/MaterialCycleEI/model_output/site_plan.csv"
    write_csv_case(selected, SITE_PLAN)
    write_csv_case(
        run / "56TESTPK/MaterialCycleEI/scores/0803A/site_plan.csv", SITE_PLAN
    )
    write_csv_case(
        run / "56TESTPK/MaterialCycleEI/validator_scores_v3/site_plan.csv", SITE_PLAN
    )
    write_csv_case(run / "intermediate_files/artifacts/cache/site_plan.csv", SITE_PLAN)
    profile = make_profile(
        tmp_path,
        role="site_plan",
        schema="ei.site-plan",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="56TESTPK/MaterialCycleEI/model_output/site_plan.csv",
        filenames=("site_plan.csv",),
    )

    result = resolve_artifacts(profile, run, repository).get("site_plan")

    assert result.selected_path == selected.resolve()
    assert [candidate.path for candidate in result.candidates] == [selected.resolve()]
