from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from simulation.ei.core.aggregation import (
    AggregationConfigurationError,
    AggregationPolicy,
    AggregationRule,
    ScoreBand,
    aggregate_total,
    load_aggregation_policy,
)
from simulation.ei.core.models import (
    CheckConfig,
    CheckResult,
    ComponentConfig,
    ComponentResult,
    QuestionProfile,
)


def _ruleset_payload() -> dict[str, Any]:
    path = (
        Path(__file__).parents[5]
        / "src"
        / "simulation"
        / "ei"
        / "ruleset.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _aggregation_rule(
    check_id: str,
    *,
    weight: int = 1,
    ladder: tuple[tuple[float, float], ...] = ((100.0, 0.0),),
) -> AggregationRule:
    return AggregationRule(
        check_id=check_id,
        weight=weight,
        ladder=tuple(
            ScoreBand(Decimal(str(max_deduction)), Decimal(str(score)))
            for max_deduction, score in ladder
        ),
    )


def _policy(*rules: AggregationRule) -> AggregationPolicy:
    return AggregationPolicy(
        ruleset_release="4.13.0",
        policy_id="test",
        rules=tuple(rules),
    )


def _rule(check_id: str, score: float) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        name=check_id,
        score=score,
        status="PASS" if score == 100 else "PARTIAL" if score else "FAIL",
        reason_code="" if score else "INVALID_ARTIFACT",
        explanation="test",
    )


def _profile(*check_ids: str) -> QuestionProfile:
    by_component: dict[str, list[str]] = {}
    for check_id in check_ids:
        component, _ = check_id.split(".", 1)
        by_component.setdefault(component, []).append(check_id)
    components = {
        name: ComponentConfig(
            name=name,
            scorer="ei.pacing",
            checks=tuple(CheckConfig(value, ("prompt/x.txt:L1",)) for value in values),
        )
        for name, values in by_component.items()
    }
    return QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts={},
        components=components,
        path=Path("validator.yaml"),
    )


def _components(*checks: CheckResult) -> tuple[ComponentResult, ...]:
    by_component: dict[str, list[CheckResult]] = {}
    for check in checks:
        component, _ = check.check_id.split(".", 1)
        by_component.setdefault(component, []).append(check)
    return tuple(
        ComponentResult(
            question_id="Q",
            component=component,
            checks=tuple(values),
            status="SCORED",
        )
        for component, values in by_component.items()
    )


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [
        (100.0, 90.0),
        (95.0, 90.0),
        (94.999999, 80.0),
        (90.0, 80.0),
        (89.999999, 60.0),
        (80.0, 60.0),
        (79.999999, 40.0),
        (60.0, 40.0),
        (59.999999, 0.0),
    ],
)
def test_default_ladder_boundaries(raw_score: float, expected: float) -> None:
    policy = _policy(
        _aggregation_rule(
            "simulation.S1",
            ladder=(
                (5, 90),
                (10, 80),
                (20, 60),
                (40, 40),
                (100, 0),
            ),
        )
    )

    total, status, error = aggregate_total(
        _profile("simulation.S1"),
        _components(_rule("simulation.S1", raw_score)),
        policy,
    )

    assert total == expected
    assert status in {"SCORED", "INVALID_CANDIDATE"}
    assert error == ""


def test_repository_policy_is_frozen_by_ruleset_release() -> None:
    ruleset = _ruleset_payload()
    policy = load_aggregation_policy(
        ruleset,
        allowed_check_ids=ruleset["checks"],
    )
    expected = (
        (5.0, 90.0),
        (10.0, 80.0),
        (20.0, 60.0),
        (40.0, 40.0),
        (100.0, 0.0),
    )

    assert policy.ruleset_release == ruleset["release"] == "4.13.0"
    assert "revision" not in ruleset["aggregation"]
    assert not hasattr(policy, "revision")
    assert all(
        tuple((float(band.max_deduction), float(band.score)) for band in rule.ladder)
        == expected
        for rule in policy.rules
    )


def test_rules_have_independent_ladders_and_integer_weights() -> None:
    policy = _policy(
        _aggregation_rule("scheduling.C2", ladder=((100, 20),)),
        _aggregation_rule("simulation.S1", weight=3, ladder=((100, 80),)),
    )

    total, status, _ = aggregate_total(
        _profile("scheduling.C2", "simulation.S1"),
        _components(
            _rule("scheduling.C2", 50),
            _rule("simulation.S1", 50),
        ),
        policy,
    )

    assert total == 65.0
    assert status == "SCORED"


def test_selected_rule_absent_from_validator_yaml_receives_raw_100() -> None:
    policy = _policy(
        _aggregation_rule(
            "scheduling.C2",
            ladder=((5, 90), (100, 0)),
        )
    )

    total, status, error = aggregate_total(_profile("simulation.S1"), (), policy)

    assert total == 90.0
    assert status == "SCORED"
    assert error == ""


def test_supported_rule_missing_result_blocks_total() -> None:
    policy = _policy(_aggregation_rule("simulation.S1"))

    total, status, error = aggregate_total(
        _profile("simulation.S1"),
        (),
        policy,
    )

    assert total is None
    assert status == "EVALUATOR_ERROR"
    assert "no rule result" in error


def test_supported_not_applicable_leaf_uses_its_zero_score() -> None:
    policy = _policy(
        _aggregation_rule(
            "scheduling.C6a",
            ladder=((5, 90), (100, 0)),
        )
    )
    unavailable_candidate = CheckResult(
        check_id="scheduling.C6a",
        name="Install/dismantle lag",
        score=0.0,
        status="NOT_APPLICABLE",
        reason_code="NOT_APPLICABLE",
        explanation="No candidate batch contains both phases",
    )

    total, status, error = aggregate_total(
        _profile("scheduling.C6a"),
        _components(unavailable_candidate),
        policy,
    )

    assert total == 0.0
    assert status == "INVALID_CANDIDATE"
    assert error == ""


@pytest.mark.parametrize("weight", [True, 0, 101, 1.5])
def test_weight_must_be_an_integer_in_one_to_one_hundred(
    weight: object,
) -> None:
    ruleset = _ruleset_payload()
    ruleset["aggregation"]["key"]["rules"]["simulation.S1"]["weight"] = weight

    with pytest.raises(AggregationConfigurationError, match="weight"):
        load_aggregation_policy(ruleset, allowed_check_ids=ruleset["checks"])
