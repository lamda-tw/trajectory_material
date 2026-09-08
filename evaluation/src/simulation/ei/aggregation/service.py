"""Apply EI aggregate policy to already-scored leaf results."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Callable

from simulation.ei.core.models import CheckResult, ComponentResult, QuestionProfile

from .config import AggregationPolicy, AggregationRule
from .methods import discrete_score, piecewise_score
from .models import AggregateMetric, RuleContribution


def _result_index(
    components: tuple[ComponentResult, ...],
) -> tuple[dict[str, CheckResult], tuple[str, ...]]:
    results: dict[str, CheckResult] = {}
    duplicate: set[str] = set()
    for component in components:
        for check in component.checks:
            if check.check_id in results:
                duplicate.add(check.check_id)
            results[check.check_id] = check
    return results, tuple(sorted(duplicate))


def _supported(profile: QuestionProfile) -> set[str]:
    return {
        check.check_id
        for component in profile.components.values()
        for check in component.checks
    }


def _leaf_error(check_id: str, result: CheckResult | None) -> tuple[str, str] | None:
    if result is None:
        return "EVALUATOR_ERROR", f"validator.yaml declares {check_id}, but no rule result was produced"
    if result.status == "QUESTION_CONTRACT_INCOMPLETE":
        return (
            "QUESTION_CONTRACT_INCOMPLETE",
            f"selected rule has an incomplete question contract: {check_id}",
        )
    if result.status in {"UNSCORABLE", "EVALUATOR_ERROR"}:
        return (
            "EVALUATOR_ERROR",
            f"selected supported rule is not scorable: {check_id}/{result.status}",
        )
    if not math.isfinite(result.score) or not 0 <= result.score <= 100:
        return "EVALUATOR_ERROR", f"selected rule score is outside 0..100: {check_id}"
    return None


def _invalid_candidate(results: list[CheckResult]) -> bool:
    return any(
        value.score <= 0.000001
        and bool(value.reason_code)
        and value.reason_code not in {"EVALUATOR_ERROR", "INVALID_REFERENCE"}
        for value in results
    )


def _weighted_metric(
    metric_id: str,
    group: str,
    rules: tuple[AggregationRule, ...],
    supported: set[str],
    results: dict[str, CheckResult],
    transform: Callable[[AggregationRule, float], Decimal],
    *,
    unsupported: str,
    empty_status: str = "EVALUATOR_ERROR",
) -> AggregateMetric:
    contributions: list[RuleContribution] = []
    applicable_results: list[CheckResult] = []
    numerator = Decimal("0")
    denominator = 0
    for rule in rules:
        if rule.check_id not in supported:
            if unsupported == "excluded":
                continue
            raw_score = 100.0
            filled = True
        else:
            result = results.get(rule.check_id)
            failure = _leaf_error(rule.check_id, result)
            if failure:
                return AggregateMetric(metric_id, group, None, failure[0], (), failure[1])
            assert result is not None
            raw_score = result.score
            filled = False
            applicable_results.append(result)
        converted = transform(rule, raw_score)
        contributions.append(
            RuleContribution(
                rule.check_id,
                round(raw_score, 6),
                round(float(converted), 6),
                rule.weight,
                rule.check_id in supported,
                filled,
            )
        )
        numerator += converted * rule.weight
        denominator += rule.weight
    if denominator <= 0:
        if empty_status == "NOT_APPLICABLE":
            return AggregateMetric(
                metric_id,
                group,
                None,
                "NOT_APPLICABLE",
                (),
                "",
            )
        return AggregateMetric(
            metric_id, group, None, "EVALUATOR_ERROR", (), "aggregate has no applicable rules"
        )
    status = "INVALID_CANDIDATE" if _invalid_candidate(applicable_results) else "SCORED"
    return AggregateMetric(
        metric_id,
        group,
        round(float(numerator / denominator), 6),
        status,
        tuple(contributions),
    )


def aggregate_metrics(
    profile: QuestionProfile,
    components: tuple[ComponentResult, ...],
    policy: AggregationPolicy,
) -> tuple[AggregateMetric, ...]:
    """Produce O2, three key-check metrics, and all-items raw in fixed order."""

    results, duplicate = _result_index(components)
    if duplicate:
        error = f"duplicate selected rule results: {list(duplicate)}"
        return tuple(
            AggregateMetric(metric_id, group, None, "EVALUATOR_ERROR", (), error)
            for metric_id, group in (
                ("effectiveness.o2", "effectiveness"),
                ("key.raw", "key"),
                ("key.discrete", "key"),
                ("key.piecewise", "key"),
                ("all.raw", "all"),
            )
        )
    supported = _supported(profile)
    o2_id = policy.effectiveness_check_id
    if o2_id not in supported:
        o2 = AggregateMetric(
            "effectiveness.o2",
            "effectiveness",
            None,
            "EVALUATOR_ERROR",
            (),
            f"O2 is mandatory but not enabled by validator.yaml: {o2_id}",
        )
    else:
        o2_result = results.get(o2_id)
        failure = _leaf_error(o2_id, o2_result)
        if failure:
            o2 = AggregateMetric(
                "effectiveness.o2", "effectiveness", None, failure[0], (), failure[1]
            )
        else:
            assert o2_result is not None
            contribution = RuleContribution(
                o2_id, o2_result.score, o2_result.score, 1, True, False
            )
            o2 = AggregateMetric(
                "effectiveness.o2",
                "effectiveness",
                round(o2_result.score, 6),
                "INVALID_CANDIDATE" if _invalid_candidate([o2_result]) else "SCORED",
                (contribution,),
            )

    raw = lambda _rule, score: Decimal(str(score))
    return (
        o2,
        _weighted_metric(
            "key.raw", "key", policy.rules, supported, results, raw,
            unsupported="full_credit",
        ),
        _weighted_metric(
            "key.discrete", "key", policy.rules, supported, results, discrete_score,
            unsupported="full_credit",
        ),
        _weighted_metric(
            "key.piecewise", "key", policy.rules, supported, results,
            lambda _rule, score: piecewise_score(score),
            unsupported="full_credit",
        ),
        _weighted_metric(
            "all.raw", "all", policy.all_rules, supported, results, raw,
            unsupported="excluded",
            empty_status="NOT_APPLICABLE",
        ),
    )


def aggregate_total(
    profile: QuestionProfile,
    components: tuple[ComponentResult, ...],
    policy: AggregationPolicy,
) -> tuple[float | None, str, str]:
    """Compatibility total: return the key.discrete metric, never O2/all.raw."""

    metrics = aggregate_metrics(profile, components, policy)
    selected = next(
        (value for value in metrics if value.metric_id == "key.discrete"),
        metrics[0],
    )
    return selected.score, selected.status, selected.error
