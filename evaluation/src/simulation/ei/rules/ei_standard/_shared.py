"""Small evidence and 0..100 leaf helpers shared by EI v4.12 scorers."""

from __future__ import annotations

import math
from typing import Any, Mapping

from simulation.ei.core.models import (
    ArtifactResolution,
    CheckResult,
    RuleContext,
)


def artifact(context: RuleContext, role: str) -> ArtifactResolution | None:
    return context.artifacts.get(role)


def usable_artifact(context: RuleContext, role: str) -> ArtifactResolution | None:
    value = artifact(context, role)
    if value is None or not value.usable or value.error:
        return None
    return value


def table(context: RuleContext, role: str):
    value = usable_artifact(context, role)
    return value.table if value else None


def normalized(context: RuleContext, role: str):
    value = usable_artifact(context, role)
    return value.normalized if value else None


def quantity_error(context: RuleContext, *roles: str) -> dict[str, Any] | None:
    failures = []
    for role in roles:
        value = artifact(context, role)
        if value is not None and value.quantity_error_count:
            failures.append(
                {
                    "role": role,
                    "count": value.quantity_error_count,
                    "samples": list(value.quantity_errors),
                }
            )
    return {"artifacts": failures} if failures else None


def validation_issues(context: RuleContext, *roles: str) -> dict[str, Any] | None:
    failures = []
    for role in roles:
        value = artifact(context, role)
        if value is not None and value.validation_issues:
            unit_ids = sorted(
                {
                    str(unit_id)
                    for issue_index, issue in enumerate(value.validation_issues)
                    for unit_id in (
                        issue.get("affected_unit_ids")
                        or ([issue["unit_id"]] if issue.get("unit_id") else [])
                        or [f"issue:{issue_index}:{issue.get('code', 'UNKNOWN')}"]
                    )
                }
            )
            failures.append(
                {
                    "role": role,
                    "count": len(value.validation_issues),
                    "affected_unit_count": len(unit_ids),
                    "affected_unit_ids": unit_ids,
                    "issues": list(value.validation_issues),
                    "samples": list(value.validation_issues[:20]),
                }
            )
    return {"artifacts": failures} if failures else None


def _status(rate: float) -> str:
    if rate >= 0.999999:
        return "PASS"
    if rate <= 0.000001:
        return "FAIL"
    return "PARTIAL"


def leaf(
    context: RuleContext,
    local_id: str,
    name: str,
    rate: float,
    explanation: str,
    evidence: Mapping[str, Any] | None = None,
    *,
    reason_code: str = "",
) -> CheckResult:
    raw_rate = float(rate)
    if not math.isfinite(raw_rate):
        raise ValueError(f"leaf rate must be finite: {context.component.name}.{local_id}")
    normalized_rate = max(0.0, min(1.0, raw_rate))
    check_id = f"{context.component.name}.{local_id}"
    prompt_refs = next(
        (value.prompt_refs for value in context.component.checks if value.check_id == check_id),
        (),
    )
    return CheckResult(
        check_id=check_id,
        name=name,
        score=round(100.0 * normalized_rate, 6),
        status=_status(normalized_rate),
        reason_code=reason_code,
        explanation=explanation,
        evidence=dict(evidence or {}),
        prompt_refs=prompt_refs,
    )


def contract_incomplete_leaf(
    context: RuleContext,
    local_id: str,
    name: str,
    explanation: str,
    evidence: Mapping[str, Any] | None = None,
) -> CheckResult:
    result = failed_leaf(
        context,
        local_id,
        name,
        "QUESTION_CONTRACT_INCOMPLETE",
        explanation,
        evidence,
    )
    return CheckResult(
        check_id=result.check_id,
        name=result.name,
        score=result.score,
        status="QUESTION_CONTRACT_INCOMPLETE",
        reason_code=result.reason_code,
        explanation=result.explanation,
        evidence=result.evidence,
        prompt_refs=result.prompt_refs,
    )


def failed_leaf(
    context: RuleContext,
    local_id: str,
    name: str,
    reason_code: str,
    explanation: str,
    evidence: Mapping[str, Any] | None = None,
) -> CheckResult:
    return leaf(
        context,
        local_id,
        name,
        0.0,
        explanation,
        evidence,
        reason_code=reason_code,
    )


def not_applicable_leaf(
    context: RuleContext,
    local_id: str,
    name: str,
    explanation: str,
    evidence: Mapping[str, Any] | None = None,
) -> CheckResult:
    check_id = f"{context.component.name}.{local_id}"
    prompt_refs = next(
        (value.prompt_refs for value in context.component.checks if value.check_id == check_id),
        (),
    )
    return CheckResult(
        check_id=check_id,
        name=name,
        score=0.0,
        status="NOT_APPLICABLE",
        reason_code="NOT_APPLICABLE",
        explanation=explanation,
        evidence=dict(evidence or {}),
        prompt_refs=prompt_refs,
    )


def evaluator_error_leaf(
    context: RuleContext,
    local_id: str,
    exc: Exception,
) -> CheckResult:
    """Isolate an evaluator exception to the leaf that raised it."""

    check_id = f"{context.component.name}.{local_id}"
    prompt_refs = next(
        (value.prompt_refs for value in context.component.checks if value.check_id == check_id),
        (),
    )
    return CheckResult(
        check_id=check_id,
        name=local_id,
        score=0.0,
        status="UNSCORABLE",
        reason_code="EVALUATOR_ERROR",
        explanation="The evaluator could not execute this rule",
        evidence={"error": f"{type(exc).__name__}: {exc}"},
        prompt_refs=prompt_refs,
    )
