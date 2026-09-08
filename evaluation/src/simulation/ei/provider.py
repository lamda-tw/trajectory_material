"""Single public facade through which the application invokes EI logic."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from simulation.app.contracts import RunRecord, ScorePackage
from simulation.ei.aggregation import AggregationPolicy, load_aggregation_policy
from simulation.ei.core.adapters import prepare_question_artifacts
from simulation.ei.core.config import contract_header, load_profile, load_ruleset
from simulation.ei.core.config import question_contract_snapshot
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.effective_delivery import (
    prepare_o2_authority,
    score_effective_delivery,
)
from simulation.ei.rules.ei_standard.scheduling import (
    prepare_scheduling_authority,
    score_pacing,
    score_scheduling,
)
from simulation.ei.rules.ei_standard.preparation import prepare_run_rule_data
from simulation.ei.rules.ei_standard.simulation import score_simulation
from simulation.ei.scoring.service import score_run


PROVIDER_ID = "simulation.ei"
_SCORE_ID_PATTERN = re.compile(r"^\d{14}(?:-\d{2})?$")


@dataclass(frozen=True)
class PreparedQuestion:
    """Immutable question inputs and compiled EI authority shared by its runs."""

    question: str
    profile: QuestionProfile
    ruleset: dict[str, Any]
    aggregation_policy: AggregationPolicy
    question_contract: Mapping[str, Any]
    question_artifacts: Mapping[str, ArtifactResolution]
    prepared_scorers: Mapping[str, Any]


def prepare_question(
    question: str,
    *,
    repository_root: Path,
) -> PreparedQuestion:
    """Load and compile candidate-independent evidence once for a question."""

    ruleset = load_ruleset()
    policy = load_aggregation_policy(
        ruleset,
        allowed_check_ids=ruleset["checks"],
    )
    profile = load_profile(question, repo=repository_root)
    question_contract = question_contract_snapshot(
        question,
        repo=repository_root,
        profile=profile,
    )
    if profile.release_status != "active":
        return PreparedQuestion(
            question=question,
            profile=profile,
            ruleset=ruleset,
            aggregation_policy=policy,
            question_contract=question_contract,
            question_artifacts={},
            prepared_scorers={},
        )
    question_artifacts = prepare_question_artifacts(profile, repository_root)
    bundle = ArtifactBundle(
        run_dir=repository_root.resolve(),
        artifact_roots=(),
        artifacts=dict(question_artifacts),
    )
    prepared_scorers: dict[str, Any] = {}
    for component in profile.components.values():
        context = RuleContext(profile, component, bundle)
        if component.scorer == "ei.scheduling":
            authority = prepare_scheduling_authority(context)
            prepared_scorers[component.scorer] = partial(
                score_scheduling,
                authority=authority,
            )
        elif component.scorer == "ei.effective-delivery":
            try:
                authority = prepare_o2_authority(context)
                prepared_scorers[component.scorer] = partial(
                    score_effective_delivery,
                    authority=authority,
                )
            except Exception:  # noqa: BLE001 - runtime retains leaf-local diagnostics
                # A future profile may use candidate-owned O2 authority.  Fall
                # back to the normal per-run compilation instead of changing
                # its scoring/error semantics during preparation.
                pass
    return PreparedQuestion(
        question=question,
        profile=profile,
        ruleset=ruleset,
        aggregation_policy=policy,
        question_contract=question_contract,
        question_artifacts=question_artifacts,
        prepared_scorers=prepared_scorers,
    )


def _required_identity(value: Any, *, label: str) -> str:
    """Return one non-empty identity value or reject an incomplete score contract."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_prepared_identity(prepared: PreparedQuestion) -> None:
    """Prevent caller-injected prepared state from mixing scoring releases."""

    ruleset_release = _required_identity(
        prepared.ruleset.get("release"),
        label="prepared ruleset release",
    )
    _required_identity(
        prepared.ruleset.get("semantic_baseline"),
        label="prepared ruleset semantic baseline",
    )
    if prepared.profile.question_id != prepared.question:
        raise ValueError(
            f"prepared profile {prepared.profile.question_id!r} does not match "
            f"{prepared.question!r}"
        )
    if prepared.profile.ruleset_release != ruleset_release:
        raise ValueError(
            "prepared profile ruleset release does not match prepared ruleset: "
            f"{prepared.profile.ruleset_release!r} != {ruleset_release!r}"
        )
    if prepared.aggregation_policy.ruleset_release != ruleset_release:
        raise ValueError(
            "prepared aggregation policy ruleset release does not match prepared "
            f"ruleset: {prepared.aggregation_policy.ruleset_release!r} != "
            f"{ruleset_release!r}"
        )
    contract_question = prepared.question_contract.get("question_id")
    if contract_question != prepared.question:
        raise ValueError(
            f"prepared question contract {contract_question!r} does not match "
            f"{prepared.question!r}"
        )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _artifact_resolutions_payload(
    bundle: ArtifactBundle,
    profile: QuestionProfile,
    repository_root: Path,
) -> list[dict[str, Any]]:
    """Serialize adapter selection evidence into the public run score."""

    repository = repository_root.resolve()
    run = bundle.run_dir.resolve()

    def evidence_path(path: Path | None, *, source: str) -> str | None:
        if path is None:
            return None
        base = run if source == "candidate" else repository
        try:
            return path.resolve().relative_to(base).as_posix()
        except ValueError:
            return path.as_posix()

    output: list[dict[str, Any]] = []
    for role in sorted(bundle.artifacts):
        value = bundle.artifacts[role]
        spec = profile.artifacts[role]
        output.append(
            {
                "role": role,
                "source": spec.source,
                "status": value.status,
                "selected_path": evidence_path(
                    value.selected_path,
                    source=spec.source,
                ),
                "error": value.error,
                "validation_issue_count": len(value.validation_issues),
                "validation_issues": _jsonable(value.validation_issues),
                "quantity_error_count": value.quantity_error_count,
                "quantity_errors": _jsonable(value.quantity_errors),
                "resolution_diagnostics": _jsonable(
                    value.resolution_diagnostics
                ),
                "candidates": [
                    {
                        "path": evidence_path(
                            candidate.path,
                            source=spec.source,
                        ),
                        "required_coverage": candidate.required_coverage,
                        "prompt_filename": candidate.prompt_filename,
                        "common_parent_suffix": candidate.common_parent_suffix,
                        "usable": candidate.usable,
                        "error": candidate.error,
                        "canonical": candidate.canonical,
                    }
                    for candidate in value.candidates
                ],
            }
        )
    return output


def _prepare_run_scorers(
    prepared: PreparedQuestion,
    artifacts: ArtifactBundle,
) -> Mapping[str, Any]:
    """Bind run-derived evidence to scorers without widening RuleContext."""

    run_data = prepare_run_rule_data(prepared.profile, artifacts)
    scorers = dict(prepared.prepared_scorers)
    for component in prepared.profile.components.values():
        scorer = component.scorer
        mode = (
            "reconcile"
            if scorer == "ei.pacing"
            else str(component.parameters.get("project_week_source", "reconcile"))
        )
        if scorer == "ei.scheduling" and mode in run_data.candidate_plans:
            base = scorers.get(scorer, score_scheduling)
            scorers[scorer] = partial(
                base,
                plan=run_data.candidate_plans[mode],
            )
        elif scorer == "ei.pacing" and mode in run_data.candidate_plans:
            scorers[scorer] = partial(
                score_pacing,
                plan=run_data.candidate_plans[mode],
            )
        elif scorer == "ei.simulation" and mode in run_data.scheduled_plans:
            scorers[scorer] = partial(
                score_simulation,
                scheduled_plan=run_data.scheduled_plans[mode],
            )
    return scorers


def score_record(
    record: RunRecord,
    *,
    repository_root: Path,
    score_id: str,
    created_at: str,
    prepared_question: PreparedQuestion | None = None,
) -> ScorePackage:
    """Score one physical run and return a complete canonical package."""

    if _SCORE_ID_PATTERN.fullmatch(score_id) is None:
        raise ValueError(
            "score_id must be YYYYMMDDHHMMSS or YYYYMMDDHHMMSS-NN"
        )
    _required_identity(created_at, label="created_at")

    prepared = prepared_question or prepare_question(
        record.question,
        repository_root=repository_root,
    )
    if prepared.question != record.question:
        raise ValueError(
            f"prepared question {prepared.question!r} does not match {record.question!r}"
        )
    _validate_prepared_identity(prepared)
    ruleset = prepared.ruleset
    policy = prepared.aggregation_policy
    score = score_run(
        record.question,
        record.run_dir,
        repo=repository_root,
        aggregation_policy=policy,
        question_profile=prepared.profile,
        prepared_question_artifacts=prepared.question_artifacts,
        prepared_scorers=prepared.prepared_scorers,
        scorer_preparer=partial(_prepare_run_scorers, prepared),
        release=str(ruleset["release"]),
    )
    if score.question_id != record.question:
        raise ValueError(
            f"scored question {score.question_id!r} does not match {record.question!r}"
        )
    if score.release != ruleset["release"]:
        raise ValueError(
            "scored ruleset release does not match prepared ruleset: "
            f"{score.release!r} != {ruleset['release']!r}"
        )
    if len(score.aggregates) != 5:
        raise ValueError(
            f"EI scoring did not produce the five aggregate metrics: {score.question_id}/{score.status}"
        )
    checks = []
    components = []
    for component in score.components:
        components.append(
            {"id": component.component, "status": component.status, "error": component.error}
        )
        for value in component.checks:
            checks.append(
                {
                    "id": value.check_id,
                    "name": value.name,
                    "score": value.score,
                    "status": value.status,
                    "reason_code": value.reason_code,
                    "explanation": value.explanation,
                    "prompt_refs": list(value.prompt_refs),
                    "evidence": _jsonable(value.evidence),
                }
            )
    aggregates = [value.as_dict() for value in score.aggregates]
    payload = {
        "contract": contract_header("run-score"),
        "provider_id": PROVIDER_ID,
        "question": score.question_id,
        "score_id": score_id,
        "created_at": created_at,
        "run": record.as_dict(),
        "ruleset": {
            "release": score.release,
            "semantic_baseline": ruleset.get("semantic_baseline"),
        },
        "question_contract": _jsonable(
            {
                key: prepared.question_contract[key]
                for key in (
                    "question_id",
                    "question_kind",
                    "question_root",
                    "files",
                    "question_inputs",
                )
            }
        ),
        "artifacts": _artifact_resolutions_payload(
            score.artifacts,
            prepared.profile,
            repository_root,
        ),
        "result": {
            "status": score.status,
            "error": score.error,
            "aggregates": aggregates,
            "components": components,
            "checks": checks,
        },
    }
    totals = tuple((value.metric_id, value.score) for value in score.aggregates)
    return ScorePackage(PROVIDER_ID, score.question_id, score.status, totals, payload)


def totals_dict(payload: dict[str, Any]) -> dict[str, float | None]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("score package has no result object")
    raw = result.get("aggregates")
    if not isinstance(raw, list):
        raise ValueError("score package has no aggregates")
    output: dict[str, float | None] = {}
    for value in raw:
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            raise ValueError("score package contains an invalid aggregate")
        score = value.get("score")
        if score is not None and not isinstance(score, (int, float)):
            raise ValueError(f"aggregate score is not numeric: {value.get('id')}")
        output[str(value["id"])] = None if score is None else float(score)
    expected = {
        "effectiveness.o2", "key.raw", "key.discrete", "key.piecewise", "all.raw"
    }
    if set(output) != expected:
        raise ValueError(
            f"score package aggregate set differs: missing={sorted(expected - set(output))}, "
            f"extra={sorted(set(output) - expected)}"
        )
    return output
