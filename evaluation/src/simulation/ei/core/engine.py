"""In-process Simulation scoring engine for validator v4.12."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Callable

from simulation.ei.rules.ei_standard.reuse import score_reuse
from simulation.ei.rules.ei_standard.effective_delivery import (
    score_effective_delivery,
)
from simulation.ei.rules.ei_standard.scheduling import score_pacing, score_scheduling
from simulation.ei.rules.ei_standard.simulation import score_simulation
from simulation.ei.aggregation import AggregateMetric, aggregate_metrics

from .adapters import resolve_artifacts
from .aggregation import (
    AggregationPolicy,
    load_aggregation_policy,
)
from .config import load_profile, load_ruleset, repository_root, simulation_root
from .models import (
    ArtifactBundle,
    ArtifactResolution,
    CheckResult,
    ComponentResult,
    QuestionProfile,
    RuleContext,
    RunScore,
)


Scorer = Callable[[RuleContext], tuple[CheckResult, ...]]
ScorerPreparer = Callable[[ArtifactBundle], Mapping[str, Scorer]]
SCORERS: dict[str, Scorer] = {
    "ei.scheduling": score_scheduling,
    "ei.pacing": score_pacing,
    "ei.simulation": score_simulation,
    "ei.reuse": score_reuse,
    "ei.effective-delivery": score_effective_delivery,
}


def assemble_component_result(
    context: RuleContext,
    checks: Iterable[CheckResult],
    *,
    error: str = "",
) -> ComponentResult:
    """Validate configured leaf coverage and derive diagnostic component status."""

    values = tuple(checks)
    if not all(isinstance(value, CheckResult) for value in values):
        raise TypeError("component scorer must return CheckResult leaves")
    configured = {value.check_id for value in context.component.checks}
    reported = {value.check_id for value in values}
    if configured != reported:
        missing = sorted(configured - reported)
        extra = sorted(reported - configured)
        raise ValueError(f"component result mismatch; missing={missing}, extra={extra}")
    if len(reported) != len(values):
        raise ValueError("component result contains duplicate check IDs")

    applicable = [value for value in values if value.status != "NOT_APPLICABLE"]
    contract_incomplete = any(
        value.status == "QUESTION_CONTRACT_INCOMPLETE" for value in values
    )
    evaluator_error = any(
        value.status in {"UNSCORABLE", "EVALUATOR_ERROR"} for value in values
    )
    invalid_candidate = (
        not contract_incomplete
        and not evaluator_error
        and bool(applicable)
        and all(
            value.score <= 0.000001
            and bool(value.reason_code)
            and value.reason_code not in {"EVALUATOR_ERROR", "INVALID_REFERENCE"}
            for value in applicable
        )
    )
    status = (
        "QUESTION_CONTRACT_INCOMPLETE"
        if contract_incomplete
        else "EVALUATOR_ERROR"
        if evaluator_error
        else "NOT_APPLICABLE"
        if not applicable
        else "INVALID_CANDIDATE"
        if invalid_candidate
        else "SCORED"
    )
    return ComponentResult(
        question_id=context.question.question_id,
        component=context.component.name,
        checks=values,
        status=status,
        error=error,
    )


def _error_result(
    profile: QuestionProfile,
    component,
    artifacts: ArtifactBundle,
    exc: Exception,
) -> ComponentResult:
    checks = tuple(
        CheckResult(
            check_id=value.check_id,
            name=value.check_id.split(".", 1)[1],
            score=0.0,
            status="UNSCORABLE",
            reason_code="EVALUATOR_ERROR",
            explanation="The evaluator could not execute this component",
            evidence={"error": f"{type(exc).__name__}: {exc}"},
            prompt_refs=value.prompt_refs,
        )
        for value in component.checks
    )
    return assemble_component_result(
        RuleContext(profile, component, artifacts),
        checks,
        error=f"{type(exc).__name__}: {exc}"[-4000:],
    )


def score_components(
    profile: QuestionProfile,
    artifacts: ArtifactBundle,
    *,
    components: Iterable[str] | None = None,
    checks: Iterable[str] | None = None,
    root: Path | None = None,
    prepared_scorers: Mapping[str, Scorer] | None = None,
) -> tuple[ComponentResult, ...]:
    """Score selected components or checks against one resolved artifact bundle."""

    sim_root = (root or simulation_root()).resolve()
    if profile.release_status != "active":
        raise ValueError(
            f"question profile is not active: {profile.release_status}; "
            + "; ".join(profile.blocking_reasons)
        )
    selected = set(components) if components is not None else set(profile.components)
    unknown = selected - set(profile.components)
    if unknown:
        raise ValueError(f"components are not enabled for {profile.question_id}: {sorted(unknown)}")
    enabled_checks = {
        check.check_id
        for component in profile.components.values()
        for check in component.checks
    }
    selected_checks = set(checks) if checks is not None else enabled_checks
    unknown_checks = selected_checks - enabled_checks
    if unknown_checks:
        raise ValueError(
            f"checks are not enabled for {profile.question_id}: {sorted(unknown_checks)}"
        )
    results = []
    scorers = {**SCORERS, **(prepared_scorers or {})}
    for name, component in profile.components.items():
        if name not in selected:
            continue
        component_checks = tuple(
            check for check in component.checks if check.check_id in selected_checks
        )
        if not component_checks:
            continue
        component = replace(component, checks=component_checks)
        context = RuleContext(
            question=profile,
            component=component,
            artifacts=artifacts,
        )
        try:
            leaves = tuple(scorers[component.scorer](context))
            result = assemble_component_result(context, leaves)
        except Exception as exc:  # noqa: BLE001
            result = _error_result(profile, component, artifacts, exc)
        results.append(result)
    return tuple(results)


def score_run(
    question_id: str,
    run_dir: Path,
    *,
    components: Iterable[str] | None = None,
    root: Path | None = None,
    repo: Path | None = None,
    aggregation_policy: AggregationPolicy | None = None,
    question_profile: QuestionProfile | None = None,
    prepared_question_artifacts: Mapping[str, ArtifactResolution] | None = None,
    prepared_scorers: Mapping[str, Scorer] | None = None,
    scorer_preparer: ScorerPreparer | None = None,
    release: str | None = None,
) -> RunScore:
    """Resolve one run once, score in process, and return without writing files."""

    sim_root = (root or simulation_root()).resolve()
    repository = (repo or repository_root()).resolve()
    ruleset = load_ruleset(sim_root)
    active_release = ruleset.get("release")
    if not isinstance(active_release, str) or not active_release:
        raise ValueError("active ruleset release must be a non-empty string")
    profile = question_profile or load_profile(question_id, sim_root, repo=repository)
    if profile.question_id != question_id:
        raise ValueError(
            f"prepared profile {profile.question_id!r} does not match {question_id!r}"
        )
    if profile.ruleset_release != active_release:
        raise ValueError(
            "question profile ruleset release does not match active ruleset: "
            f"{profile.ruleset_release!r} != {active_release!r}"
        )
    if release is not None and release != active_release:
        raise ValueError(
            "requested ruleset release does not match active ruleset: "
            f"{release!r} != {active_release!r}"
        )
    selected_release = active_release
    if aggregation_policy is not None:
        if aggregation_policy.ruleset_release != active_release:
            raise ValueError(
                "aggregation policy ruleset release does not match active ruleset: "
                f"{aggregation_policy.ruleset_release!r} != {active_release!r}"
            )
    if profile.release_status != "active":
        error = "; ".join(profile.blocking_reasons)
        aggregates = (
            tuple(
                AggregateMetric(
                    metric_id,
                    group,
                    None,
                    "QUESTION_CONTRACT_INCOMPLETE",
                    (),
                    error,
                )
                for metric_id, group in (
                    ("effectiveness.o2", "effectiveness"),
                    ("key.raw", "key"),
                    ("key.discrete", "key"),
                    ("key.piecewise", "key"),
                    ("all.raw", "all"),
                )
            )
            if components is None
            else ()
        )
        return RunScore(
            question_id=question_id,
            release=selected_release,
            artifacts=ArtifactBundle(run_dir.resolve(), (), {}),
            components=(),
            total_score=None,
            status="QUESTION_CONTRACT_INCOMPLETE",
            error=error,
            aggregates=aggregates,
        )
    artifacts = resolve_artifacts(
        profile,
        run_dir,
        repository,
        prepared_question_artifacts=(
            dict(prepared_question_artifacts)
            if prepared_question_artifacts is not None
            else None
        ),
    )
    run_scorers = dict(prepared_scorers or {})
    if scorer_preparer is not None:
        run_scorers.update(scorer_preparer(artifacts))
    results = score_components(
        profile,
        artifacts,
        components=components,
        root=sim_root,
        prepared_scorers=run_scorers,
    )
    if components is None:
        policy = aggregation_policy or load_aggregation_policy(
            ruleset,
            allowed_check_ids=ruleset["checks"],
        )
        aggregates = aggregate_metrics(profile, results, policy)
        discrete = next(value for value in aggregates if value.metric_id == "key.discrete")
        total = discrete.score
        errors = [value.error for value in aggregates if value.error]
        if any(value.status == "EVALUATOR_ERROR" for value in aggregates):
            status = "EVALUATOR_ERROR"
        elif any(value.status == "QUESTION_CONTRACT_INCOMPLETE" for value in aggregates):
            status = "QUESTION_CONTRACT_INCOMPLETE"
        elif any(value.status == "INVALID_CANDIDATE" for value in aggregates):
            status = "INVALID_CANDIDATE"
        else:
            status = "SCORED"
        error = "; ".join(dict.fromkeys(errors))
    else:
        total = None
        aggregates = ()
        failures = [value for value in results if value.status == "EVALUATOR_ERROR"]
        incomplete = [
            value for value in results if value.status == "QUESTION_CONTRACT_INCOMPLETE"
        ]
        status = (
            "EVALUATOR_ERROR"
            if failures
            else "QUESTION_CONTRACT_INCOMPLETE"
            if incomplete
            else "INVALID_CANDIDATE"
            if any(value.status == "INVALID_CANDIDATE" for value in results)
            else "SCORED"
        )
        error = "; ".join(value.error for value in failures + incomplete if value.error)
    return RunScore(
        question_id=question_id,
        release=selected_release,
        artifacts=artifacts,
        components=results,
        total_score=total,
        status=status,
        error=error,
        aggregates=aggregates,
    )
