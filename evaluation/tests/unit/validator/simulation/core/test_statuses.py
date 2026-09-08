from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
from pathlib import Path

import pytest

from simulation.ei.core.aggregation import (
    AggregationPolicy,
    AggregationRule,
    ScoreBand,
    aggregate_total,
)
from simulation.ei.core.engine import assemble_component_result
from simulation.ei.core.models import (
    ArtifactBundle,
    CheckConfig,
    CheckResult,
    ComponentConfig,
    ComponentResult,
    QuestionProfile,
    RuleContext,
    RunScore,
)
from simulation.ei.core.reporting import component_payload, total_payload
from simulation.ei.rules.ei_standard._shared import (
    contract_incomplete_leaf,
    failed_leaf,
    leaf,
    not_applicable_leaf,
)


def _context(tmp_path: Path) -> RuleContext:
    component = ComponentConfig(
        name="simulation",
        scorer="ei.simulation",
        checks=(CheckConfig("simulation.S3", ("prompt/x.txt:L1",)),),
    )
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts={},
        components={"simulation": component},
        path=tmp_path / "validator.yaml",
    )
    return RuleContext(
        question=profile,
        component=component,
        artifacts=ArtifactBundle(tmp_path, (), {}),
    )


def test_all_candidate_contract_failures_are_invalid_candidate(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = assemble_component_result(
        context,
        [
            failed_leaf(
                context,
                "S3",
                "Warehouse balance",
                "MISSING_ARTIFACT",
                "missing",
            )
        ],
    )

    assert result.status == "INVALID_CANDIDATE"


def test_invalid_reference_is_evaluated_not_candidate_invalid(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = assemble_component_result(
        context,
        [
            failed_leaf(
                context,
                "S3",
                "Warehouse balance",
                "INVALID_REFERENCE",
                "question input cannot be evaluated",
            )
        ],
    )

    assert result.status == "SCORED"


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_leaf_rate_is_rejected_before_clamping(
    tmp_path: Path,
    rate: float,
) -> None:
    context = _context(tmp_path)

    with pytest.raises(ValueError, match="leaf rate must be finite"):
        leaf(context, "S3", "Warehouse balance", rate, "invalid rate")


def test_batch_outcome_preserves_invalid_candidate(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = assemble_component_result(
        context,
        [failed_leaf(context, "S3", "S3", "INVALID_ARTIFACT", "invalid")],
    )
    assert result.status == "INVALID_CANDIDATE"


def test_question_contract_incomplete_blocks_numeric_total(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = assemble_component_result(
        context,
        [
            contract_incomplete_leaf(
                context,
                "S3",
                "S3",
                "Prompt contract is incomplete",
            )
        ],
    )

    assert result.status == "QUESTION_CONTRACT_INCOMPLETE"


def test_not_applicable_check_is_excluded_from_component_and_total_denominators(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    result = assemble_component_result(
        context,
        [
            not_applicable_leaf(
                context,
                "S3",
                "Warehouse balance",
                "no applicable object",
            )
        ],
    )

    assert result.status == "NOT_APPLICABLE"


def test_component_result_has_no_aggregate_score_fields() -> None:
    assert {value.name for value in fields(ComponentResult)} == {
        "question_id",
        "component",
        "checks",
        "status",
        "error",
    }


def test_unselected_unscorable_leaf_is_diagnostic_only_for_run_status(
    tmp_path: Path,
) -> None:
    component_config = ComponentConfig(
        name="simulation",
        scorer="ei.simulation",
        checks=(
            CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),
            CheckConfig("simulation.S2", ("prompt/x.txt:L2",)),
        ),
    )
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts={},
        components={"simulation": component_config},
        path=tmp_path / "validator.yaml",
    )
    context = RuleContext(
        question=profile,
        component=component_config,
        artifacts=ArtifactBundle(tmp_path, (), {}),
    )
    component = assemble_component_result(
        context,
        (
            CheckResult("simulation.S1", "S1", 100.0, "PASS", "", "ok"),
            CheckResult(
                "simulation.S2",
                "S2",
                0.0,
                "UNSCORABLE",
                "EVALUATOR_ERROR",
                "diagnostic-only failure",
            ),
        ),
    )
    policy = AggregationPolicy(
        ruleset_release="4.13.0",
        policy_id="selected-s1",
        rules=(
            AggregationRule(
                "simulation.S1",
                1,
                (ScoreBand(Decimal("100"), Decimal("90")),),
            ),
        ),
    )

    total, status, error = aggregate_total(profile, (component,), policy)
    run_score = RunScore(
        question_id="Q",
        release="4.0.0",
        artifacts=context.artifacts,
        components=(component,),
        total_score=total,
        status=status,
        error=error,
    )
    assert component.status == "EVALUATOR_ERROR"
    assert total == 90.0
    assert run_score.status == "SCORED"


def test_component_persistence_contains_leaves_and_status_without_aggregate_fields(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    component = assemble_component_result(
        context,
        [leaf(context, "S3", "S3", 1.0, "ok")],
    )
    run_score = RunScore(
        question_id="Q",
        release="4.0.0",
        artifacts=context.artifacts,
        components=(component,),
        total_score=90.0,
        status="SCORED",
    )

    persisted_component = component_payload(run_score, component)
    persisted_total = total_payload(run_score)
    assert set(persisted_component["result"]) == {"status", "error", "checks"}
    assert set(persisted_total["result"]["components"][0]) == {"id", "status"}
