from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.adapters.products import normalize_product
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.scheduling import (
    score_pacing,
    score_scheduling,
)


def _historical_master() -> pd.DataFrame:
    return pd.DataFrame(
        (
            {
                "site_name": "S1",
                "site_action": "install",
                "mos_weekly_plan": "2027WK5",
                "week_num": 5,
                "region": "R1",
                "site_count": 1,
            },
            {
                "site_name": "D1",
                "site_action": "dismantle",
                "mos_weekly_plan": "2027WK10",
                "week_num": 10,
                "region": "R1",
                "site_count": 1,
            },
        )
    )


def _context(rule_id: str) -> RuleContext:
    parameters = {
        "master_format": "site-action-weekly-install",
        "planning_year": 2027,
        "week_to_month": "calendar",
        "project_start_month": 1,
        "site_scope": "all_material_sites",
        "batch_kind": "cluster",
        "capacity_factor": 1.0,
    }
    component_name = "scheduling" if rule_id == "C3" else "pacing"
    component = ComponentConfig(
        name=component_name,
        scorer="ei.scheduling" if rule_id == "C3" else "ei.pacing",
        checks=(CheckConfig(f"{component_name}.{rule_id}", ("prompt/x.txt:L1",)),),
        parameters=parameters,
    )
    historical = _historical_master()
    normalized, issues = normalize_product(
        "master_plan",
        "",
        historical,
        {
            "_effective_delivery": {
                "o2_master_format": "site-action-weekly-install",
                "o2_planning_year": 2027,
            }
        },
    )
    assert issues == ()
    plan = pd.DataFrame(
        {
            "site_name": ["S1"],
            "site_action": ["install"],
            "week_num": [5],
            "region": ["R1"],
        }
    )
    artifacts = {
        "site_plan": ArtifactResolution(
            role="site_plan",
            status="SELECTED_CANONICAL",
            selected_path=Path("site_plan.csv"),
            table=plan,
            normalized=plan,
        ),
        "master_plan": ArtifactResolution(
            role="master_plan",
            status="SELECTED_CANONICAL",
            selected_path=Path("fixed_site_plan.csv"),
            table=historical,
            normalized=normalized,
        ),
    }
    profile = QuestionProfile(
        question_id="Q-HISTORICAL-MASTER",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts={
            "site_plan": ArtifactSpec(
                role="site_plan",
                source="candidate",
                path="site_plan.csv",
                filenames=("site_plan.csv",),
            ),
            "master_plan": ArtifactSpec(
                role="master_plan",
                source="question",
                path="fixed_site_plan.csv",
            ),
        },
        components={component.name: component},
        path=Path("validator.yaml"),
    )
    return RuleContext(
        question=profile,
        component=component,
        artifacts=ArtifactBundle(Path("run"), (), artifacts),
    )


def test_historical_fixed_plan_drives_c3_install_capacity() -> None:
    context = _context("C3")
    normalized = context.artifacts.artifacts["master_plan"].normalized

    assert normalized[["region", "period", "month", "planned_count"]].to_dict(
        "records"
    ) == [
        {
            "region": "R1",
            "period": 202702,
            "month": 2,
            "planned_count": 1.0,
        }
    ]
    result = score_scheduling(context)[0]
    assert result.check_id == "scheduling.C3"
    assert result.score == 100.0


def test_historical_fixed_plan_drives_o1_install_pacing() -> None:
    result = score_pacing(_context("O1"))[0]

    assert result.check_id == "pacing.O1"
    assert result.score == 100.0
    assert result.evidence == {
        "master_total": 1.0,
        "actual_total": 1,
        "periods": [202702],
        "master_curve": {"202702": 1.0},
        "actual_curve": {"202702": 1},
    }


def test_o1_keeps_the_same_month_in_different_years_distinct() -> None:
    context = _context("O1")
    master = pd.DataFrame(
        (
            {"region": "R1", "period": 202701, "month": 1, "planned_count": 1},
            {"region": "R1", "period": 202801, "month": 1, "planned_count": 1},
        )
    )
    plan = pd.DataFrame(
        (
            {
                "site_name": "S1",
                "site_action": "install",
                "week_label": "2027WK1",
                "week_num": 1,
                "region": "R1",
            },
            {
                "site_name": "S2",
                "site_action": "install",
                "week_label": "2028WK1",
                "week_num": 1,
                "region": "R1",
            },
        )
    )
    context.artifacts.artifacts["master_plan"] = ArtifactResolution(
        role="master_plan",
        status="SELECTED_CANONICAL",
        selected_path=Path("master_plan.csv"),
        table=master,
        normalized=master,
    )
    context.artifacts.artifacts["site_plan"] = ArtifactResolution(
        role="site_plan",
        status="SELECTED_CANONICAL",
        selected_path=Path("site_plan.csv"),
        table=plan,
        normalized=plan,
    )

    result = score_pacing(context)[0]

    assert result.score == 100.0
    assert result.evidence["periods"] == [202701, 202801]
    assert result.evidence["master_curve"] == {"202701": 1, "202801": 1}
    assert result.evidence["actual_curve"] == {"202701": 1, "202801": 1}
