from __future__ import annotations

from pathlib import Path

from simulation.ei.core.models import (
    ArtifactBundle,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)


def context(rule_id: str, *, parameters: dict[str, object] | None = None) -> RuleContext:
    component = ComponentConfig(
        name="reuse-accounting",
        scorer="ei.reuse",
        checks=(CheckConfig(f"reuse-accounting.{rule_id}", ("prompt.txt",)),),
        parameters=dict(parameters or {}),
    )
    question = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=(".",),
        artifacts={},
        components={"reuse-accounting": component},
        path=Path("validator.yaml"),
    )
    return RuleContext(
        question=question,
        component=component,
        artifacts=ArtifactBundle(Path("run"), (), {}),
    )


def passing_rate_rows() -> list[dict[str, object]]:
    return [
        {"row": 2, "item_key": "a", "metric": "Inter-Site Reuse", "metric_key": "intersitereuse", "metric_type": "quantity", "total": 5, "total_valid": True},
        {"row": 3, "item_key": "a", "metric": "Dismantled", "metric_key": "dismantled", "metric_type": "quantity", "total": 10, "total_valid": True},
        {"row": 4, "item_key": "a", "metric": "New Proposal", "metric_key": "newproposal", "metric_type": "quantity", "total": 5, "total_valid": True},
        {"row": 5, "item_key": "a", "metric": "Reuse Rate", "metric_key": "reuserate", "metric_type": "rate", "total": "50%"},
        {"row": 6, "item_key": "a", "metric": "All Scope Reuse Rate", "metric_key": "allscopereuserate", "metric_type": "rate", "total": "50%"},
    ]
