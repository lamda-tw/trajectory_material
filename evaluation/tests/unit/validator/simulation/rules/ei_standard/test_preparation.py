from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ComponentConfig,
    QuestionProfile,
)
from simulation.ei.rules.ei_standard.preparation import prepare_run_rule_data
from simulation.ei.rules.ei_standard.scheduling.parsing import _candidate_plan


def _profile(*modes: str) -> QuestionProfile:
    scorers = ("ei.scheduling", "ei.pacing", "ei.simulation")
    components = {
        f"component-{index}": ComponentConfig(
            name=f"component-{index}",
            scorer=scorer,
            checks=(),
            parameters={"project_week_source": mode},
        )
        for index, (scorer, mode) in enumerate(zip(scorers, modes))
    }
    return QuestionProfile("Q", "4.13.0", (), {}, components, Path("validator.yaml"))


def _artifacts() -> ArtifactBundle:
    frame = pd.DataFrame(
        {
            "site_name": ["A", "B"],
            "site_action": ["install", "dismantle"],
            "week_num": [1, 2],
            "mos_weekly_plan": ["2027WK1", "2027WK2"],
            "status": ["Scheduled", "Draft"],
        }
    )
    resolution = ArtifactResolution(
        role="site_plan",
        status="SELECTED_CANONICAL",
        selected_path=Path("site_plan.csv"),
        table=frame,
        normalized=frame,
    )
    return ArtifactBundle(Path("run"), (), {"site_plan": resolution})


def test_run_preparation_compiles_shared_reconcile_plan_once() -> None:
    with patch(
        "simulation.ei.rules.ei_standard.preparation._candidate_plan",
        wraps=_candidate_plan,
    ) as parser:
        prepared = prepare_run_rule_data(
            _profile("reconcile", "week_num", "reconcile"),
            _artifacts(),
        )

    # O1 intentionally keeps its historical reconcile behavior, so all three
    # rule families share the same compiled plan in this profile.
    assert parser.call_count == 1
    assert tuple(prepared.candidate_plans) == ("reconcile",)
    assert prepared.scheduled_plans["reconcile"]["site"].tolist() == ["A"]


def test_run_preparation_compiles_each_distinct_contract_once() -> None:
    with patch(
        "simulation.ei.rules.ei_standard.preparation._candidate_plan",
        wraps=_candidate_plan,
    ) as parser:
        prepared = prepare_run_rule_data(
            _profile("week_num", "reconcile", "reconcile"),
            _artifacts(),
        )

    assert parser.call_count == 2
    assert set(prepared.candidate_plans) == {"reconcile", "week_num"}
