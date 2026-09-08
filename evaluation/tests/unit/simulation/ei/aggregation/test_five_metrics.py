from pathlib import Path

import pytest

from simulation.ei.aggregation import (
    aggregate_metrics,
    load_aggregation_policy,
    piecewise_score,
)
from simulation.ei.core.config import load_ruleset
from simulation.ei.core.models import (
    CheckConfig,
    CheckResult,
    ComponentConfig,
    ComponentResult,
    QuestionProfile,
)


def _profile() -> QuestionProfile:
    return QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=(),
        artifacts={},
        components={
            "scheduling": ComponentConfig(
                "scheduling",
                "ei.scheduling",
                (CheckConfig("scheduling.C1", ()), CheckConfig("scheduling.C2", ())),
            ),
            "effective-delivery": ComponentConfig(
                "effective-delivery",
                "ei.effective-delivery",
                (CheckConfig("effective-delivery.O2", ()),),
            ),
        },
        path=Path("validator.yaml"),
    )


def _components() -> tuple[ComponentResult, ...]:
    return (
        ComponentResult(
            "Q",
            "scheduling",
            (
                CheckResult("scheduling.C1", "C1", 60, "PASS", "", "ok"),
                CheckResult("scheduling.C2", "C2", 80, "PASS", "", "ok"),
            ),
            "SCORED",
        ),
        ComponentResult(
            "Q",
            "effective-delivery",
            (CheckResult("effective-delivery.O2", "O2", 70, "PASS", "", "ok"),),
            "SCORED",
        ),
    )


def test_piecewise_is_continuous_monotone_and_keeps_full_score() -> None:
    assert float(piecewise_score(0)) == 0
    assert float(piecewise_score(59.999)) == pytest.approx(19.9996666667)
    assert float(piecewise_score(60)) == 20
    assert float(piecewise_score(80)) == 60
    assert float(piecewise_score(100)) == 100


def test_five_metrics_keep_o2_out_of_key_and_all_denominators() -> None:
    policy = load_aggregation_policy(allowed_check_ids=load_ruleset()["checks"])
    metrics = {
        value.metric_id: value
        for value in aggregate_metrics(_profile(), _components(), policy)
    }

    assert list(metrics) == [
        "effectiveness.o2",
        "key.raw",
        "key.discrete",
        "key.piecewise",
        "all.raw",
    ]
    assert metrics["effectiveness.o2"].score == 70
    assert metrics["key.raw"].score == 96
    assert metrics["key.discrete"].score == 84
    assert metrics["key.piecewise"].score == 92
    assert metrics["all.raw"].score == 70
    assert {value.check_id for value in metrics["all.raw"].contributions} == {
        "scheduling.C1",
        "scheduling.C2",
    }
    assert sum(value.filled for value in metrics["key.raw"].contributions) == 4


def test_missing_mandatory_o2_is_an_error_not_a_fill() -> None:
    profile = _profile()
    components = _components()[:1]
    policy = load_aggregation_policy(allowed_check_ids=load_ruleset()["checks"])
    o2 = aggregate_metrics(profile, components, policy)[0]
    assert o2.score is None
    assert o2.status == "EVALUATOR_ERROR"
    assert "no rule result" in o2.error


def test_o2_only_profile_keeps_five_metrics_without_fabricating_all_raw() -> None:
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=(),
        artifacts={},
        components={
            "effective-delivery": ComponentConfig(
                "effective-delivery",
                "ei.effective-delivery",
                (CheckConfig("effective-delivery.O2", ()),),
            ),
        },
        path=Path("validator.yaml"),
    )
    components = (
        ComponentResult(
            "Q",
            "effective-delivery",
            (CheckResult("effective-delivery.O2", "O2", 73, "PASS", "", "ok"),),
            "SCORED",
        ),
    )
    policy = load_aggregation_policy(allowed_check_ids=load_ruleset()["checks"])

    metrics = {
        value.metric_id: value
        for value in aggregate_metrics(profile, components, policy)
    }

    assert len(metrics) == 5
    assert metrics["effectiveness.o2"].score == 73
    assert metrics["all.raw"].score is None
    assert metrics["all.raw"].status == "NOT_APPLICABLE"
    assert metrics["all.raw"].contributions == ()
    assert metrics["all.raw"].error == ""


def test_default_policy_partitions_ruleset_into_o2_and_17_non_o2_rules() -> None:
    active = set(load_ruleset()["checks"])
    policy = load_aggregation_policy(allowed_check_ids=active)
    assert policy.effectiveness_check_id == "effective-delivery.O2"
    assert len(policy.rules) == 5
    assert len(policy.all_rules) == 17
    assert {policy.effectiveness_check_id, *(value.check_id for value in policy.all_rules)} == active
