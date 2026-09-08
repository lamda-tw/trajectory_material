from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.scheduling import score_scheduling


def _resolution(role: str, frame: pd.DataFrame) -> ArtifactResolution:
    return ArtifactResolution(
        role=role,
        status="SELECTED_CANONICAL",
        selected_path=Path(f"{role}.csv"),
        table=frame,
        normalized=frame,
    )


def _plan() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "site_action": ["install"],
            "week_num": [1],
            "region": ["R1"],
        }
    )


def _scope() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "action": ["install"],
            "required_qty": [1],
            "region": ["R1"],
        }
    )


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": [1],
            "region": ["R1"],
            "master_count": [1],
        }
    )


def _context(
    tmp_path: Path,
    checks: tuple[str, ...],
    frames: dict[str, pd.DataFrame],
) -> RuleContext:
    component = ComponentConfig(
        name="scheduling",
        scorer="ei.scheduling",
        checks=tuple(
            CheckConfig(f"scheduling.{check}", ("prompt/x.txt:L1",))
            for check in checks
        ),
        parameters={
            "site_scope": "all_material_sites",
            "planning_year": 2027,
            "week_to_month": "calendar",
            "project_start_month": 1,
            "batch_kind": "cluster",
            "capacity_factor": 1.0,
            "c6a_contract": {"relation": "minimum", "lag_weeks": 1},
        },
    )
    roles = ("site_plan", "scope_input", "batch_input", "master_plan")
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts={
            role: ArtifactSpec(
                role,
                "candidate" if role == "site_plan" else "question",
                f"{role}.csv",
                (f"{role}.csv",),
            )
            for role in roles
        },
        components={"scheduling": component},
        path=tmp_path / "validator.yaml",
    )
    return RuleContext(
        question=profile,
        component=component,
        artifacts=ArtifactBundle(
            tmp_path,
            (),
            {role: _resolution(role, frame) for role, frame in frames.items()},
        ),
    )


def _by_id(results):
    return {result.check_id: result for result in results}


def test_c2_does_not_read_invalid_master_or_batch_evidence(tmp_path: Path) -> None:
    results = score_scheduling(
        _context(
            tmp_path,
            ("C2",),
            {
                "site_plan": _plan(),
                "scope_input": _scope(),
                "master_plan": pd.DataFrame({"bad": [1]}),
                "batch_input": pd.DataFrame({"bad": [1]}),
            },
        )
    )

    assert len(results) == 1
    assert results[0].check_id == "scheduling.C2"
    assert results[0].status == "PASS"
    assert results[0].score == 100.0


def test_master_failure_only_marks_master_dependent_leaves(tmp_path: Path) -> None:
    results = _by_id(
        score_scheduling(
            _context(
                tmp_path,
                ("C2", "C3"),
                {
                    "site_plan": _plan(),
                    "scope_input": _scope(),
                    "master_plan": pd.DataFrame({"bad": [1]}),
                },
            )
        )
    )

    assert results["scheduling.C2"].status == "PASS"
    assert results["scheduling.C2"].score == 100.0
    assert results["scheduling.C3"].status == "UNSCORABLE"
    assert "master_plan" in results["scheduling.C3"].evidence["error"]


def test_batch_failure_only_marks_batch_dependent_leaves(tmp_path: Path) -> None:
    results = _by_id(
        score_scheduling(
            _context(
                tmp_path,
                ("C2", "C6a"),
                {
                    "site_plan": _plan(),
                    "scope_input": _scope(),
                    "batch_input": pd.DataFrame({"bad": [1]}),
                },
            )
        )
    )

    assert results["scheduling.C2"].status == "PASS"
    assert results["scheduling.C2"].score == 100.0
    assert results["scheduling.C6a"].status == "UNSCORABLE"
    assert "batch_input" in results["scheduling.C6a"].evidence["error"]


def test_scope_failure_only_marks_scope_dependent_leaves(tmp_path: Path) -> None:
    results = _by_id(
        score_scheduling(
            _context(
                tmp_path,
                ("C2", "C3"),
                {
                    "site_plan": _plan(),
                    "scope_input": pd.DataFrame({"bad": [1]}),
                    "master_plan": _master(),
                },
            )
        )
    )

    assert results["scheduling.C2"].status == "UNSCORABLE"
    assert "scope_input" in results["scheduling.C2"].evidence["error"]
    assert results["scheduling.C3"].status == "PASS"
    assert results["scheduling.C3"].score == 100.0
