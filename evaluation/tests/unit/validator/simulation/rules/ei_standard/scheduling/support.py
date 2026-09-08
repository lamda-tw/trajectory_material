from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.models import (
    ArtifactBundle,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.scheduling.evidence import SchedulingEvidence
from simulation.ei.rules.ei_standard.drop_selection import (
    compile_seeded_drop_selection,
)


def context(rule_id: str, *, parameters: dict[str, object] | None = None) -> RuleContext:
    component = ComponentConfig(
        name="scheduling",
        scorer="ei.scheduling",
        checks=(CheckConfig(f"scheduling.{rule_id}", ("prompt.txt",)),),
        parameters=dict(parameters or {}),
    )
    question = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=(".",),
        artifacts={},
        components={"scheduling": component},
        path=Path("validator.yaml"),
    )
    return RuleContext(
        question=question,
        component=component,
        artifacts=ArtifactBundle(Path("run"), (), {}),
    )


def evidence(**overrides: object) -> SchedulingEvidence:
    plan = pd.DataFrame(
        {
            "site_key": ["r|s1", "r|s2", "r|s1"],
            "action_key": ["r|s1|install", "r|s2|install", "r|s1|dismantle"],
            "site": ["S1", "S2", "S1"],
            "region": ["R", "R", "R"],
            "action": ["install", "install", "dismantle"],
            "project_week": [1, 2, 3],
            "week_issue": ["", "", ""],
            "source_row": [2, 3, 4],
            "month": [1, 2, 1],
        }
    )
    expected = pd.DataFrame(
        {
            "site_key": ["r|s1", "r|s2"],
            "action_key": ["r|s1|install", "r|s2|install"],
            "action": ["install", "install"],
        }
    )
    values: dict[str, object] = {
        "plan": plan,
        "parameters": {
            "batch_kind": "cluster",
            "skip_rate": 0.0,
            "skip_pool_scope": "region-batch",
            "capacity_factor": 1.0,
            "c6a_contract": {"relation": "exact", "lag_weeks": 2},
            "c6b_contract": {
                "event": "first_install_week",
                "order_mode": "numeric_ascending",
                "scope": "region",
            },
        },
        "site_scope": "all_material_sites",
        "batch_map": {"r|s1": "1", "r|s2": "2"},
        "batch_rows": [
            {"region": "R", "batch": "1"},
            {"region": "R", "batch": "2"},
        ],
        "expected": expected,
        "source_action_count": 2,
        "excluded_action_count": 0,
        "expected_sites": {"r|s1", "r|s2"},
        "actual_sites": {"r|s1", "r|s2"},
        "master_by_region": {("r", 1): 1.0},
        "installs": plan[plan["action"] == "install"],
    }
    values.update(overrides)
    return SchedulingEvidence(**values)


def seeded_drop_evidence() -> SchedulingEvidence:
    """Return a correct post-Drop plan whose authority also has dismantle rows."""

    sites = [f"r|s{index}" for index in range(1, 21)]
    expected = pd.DataFrame(
        [
            {
                "site_key": site,
                "action_key": f"{site}|{action}",
                "action": action,
            }
            for site in sites
            for action in ("install", "dismantle")
        ]
    )
    parameters = {
        "batch_kind": "mocn",
        "skip_rate": 0.05,
        "skip_pool_scope": "batch",
        "drop_selection_contract": {"mode": "seeded-random", "seed": 42},
    }
    batch_map = {site: "1" for site in sites}
    selection = compile_seeded_drop_selection(
        expected,
        batch_map,
        batch_kind="mocn",
        drop_rate=0.05,
        pool_scope="batch",
        contract=parameters["drop_selection_contract"],
    )
    dropped = set(selection.dropped_install_site_keys)
    retained_rows = expected.loc[~expected["site_key"].isin(dropped)].copy()
    plan = retained_rows.assign(
        site=retained_rows["site_key"].str.rsplit("|", n=1).str[-1],
        region="R",
        project_week=1,
        week_issue="",
        source_row=range(2, len(retained_rows) + 2),
        month=1,
    )
    return evidence(
        plan=plan,
        parameters=parameters,
        batch_map=batch_map,
        expected=expected,
        expected_sites=set(sites),
        actual_sites=set(plan["site_key"]),
        installs=plan.loc[plan["action"] == "install"],
        source_action_count=len(expected),
        drop_selection=selection,
    )
