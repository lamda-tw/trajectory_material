"""Explicit shared evidence prepared once for S2 and S3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.adapters.products.gap import align_gap_reuse_inbound
from simulation.ei.core.models import RuleContext

from .._shared import normalized, table, validation_issues
from .gap import _gap_flat_adapter_issues, _simulation_evidence_mode
from .week_contract import (
    WeekAxisResult,
    score_gap_zero_business,
    score_site_rollout_week_axis,
    score_week_axis,
)


@dataclass(frozen=True)
class GapEvidence:
    evidence_modes: dict[str, str]
    role: str
    frame: pd.DataFrame | None
    adapter_issues: dict[str, Any] | None
    blocks: dict[tuple[str, str], dict[str, Any]]
    aggregate_blocks: dict[tuple[str, str], dict[str, Any]]
    weeks: tuple[int, ...]
    evidence_level: str
    contract_issues: list[dict[str, Any]]
    alignment: dict[str, Any]
    week_axis: WeekAxisResult | None
    site_rollout_axis: WeekAxisResult | None
    gap_zero_business: WeekAxisResult | None


def prepare_gap_evidence(
    context: RuleContext,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> GapEvidence:
    parameters = context.component.parameters
    evidence_modes = {
        rule_id: _simulation_evidence_mode(parameters, rule_id)
        for rule_id in ("S2", "S3")
    }
    week_contract = parameters.get("gap_week_contract")
    site_rollout_contract = parameters.get("site_rollout_week_contract")
    zero_business_metrics = parameters.get("gap_zero_business_metrics")
    uses_gap = (
        any(value == "gap-wide" for value in evidence_modes.values())
        or isinstance(week_contract, Mapping)
        or isinstance(zero_business_metrics, list)
    )
    role = str(parameters.get("gap_role", "gap"))
    frame = table(context, role) if uses_gap else None
    all_issues = validation_issues(context, role) if uses_gap else None
    adapter_issues: dict[str, Any] | None = None
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    aggregate_blocks: dict[tuple[str, str], dict[str, Any]] = {}
    weeks: tuple[int, ...] = ()
    evidence_level = "none"
    contract_issues: list[dict[str, Any]] = []
    alignment: dict[str, Any] = {}
    week_axis: WeekAxisResult | None = None
    site_rollout_axis: WeekAxisResult | None = None
    gap_zero_business: WeekAxisResult | None = None
    payload = normalized(context, role) if uses_gap else None
    if frame is not None and isinstance(payload, Mapping):
        aligned = align_gap_reuse_inbound(
            payload,
            repair_weeks=int(parameters.get("repair_weeks", 0)),
            reuse_rate=float(parameters.get("reuse_rate", 1.0)),
        )
        blocks = dict(aligned.get("blocks", {}))
        aggregate_blocks = dict(aligned.get("aggregate_blocks", {}))
        weeks = tuple(int(value) for value in aligned.get("weeks", ()))
        evidence_level = str(aligned.get("evidence_level", "weekly"))
        alignment = dict(aligned.get("inbound_alignment", {}))
        normalizer_codes = {
            "MISSING_GAP_KEY_COLUMNS",
            "MISSING_GAP_WEEK_COLUMNS",
            "NON_CONTIGUOUS_GAP_WEEKS",
            "GAP_WEEK_WINDOW_MISMATCH",
            "INVALID_GAP_DATE_ROW",
            "INVALID_GAP_QUANTITY",
            "NON_INTEGER_QUANTITY",
            "UNKNOWN_GAP_METRIC",
            "EMPTY_GAP_BUSINESS_KEY",
            "DUPLICATE_GAP_METRIC",
            "MISSING_GAP_METRICS",
            "CONFLICTING_GAP_SUMMARY",
            "CONFLICTING_GAP_METRIC_COLUMNS",
            "EMPTY_GAP_BUSINESS_ROWS",
        }
        flattened = _gap_flat_adapter_issues(all_issues)
        contract_issues = [
            issue
            for issue in flattened
            if str(issue.get("code", "")) in normalizer_codes
        ]
        schema_issues = [
            issue
            for issue in flattened
            if str(issue.get("code", "")) not in normalizer_codes
        ]
        if schema_issues:
            adapter_issues = {
                "artifacts": [
                    {
                        "role": role,
                        "count": len(schema_issues),
                        "issues": schema_issues,
                    }
                ]
            }
    if isinstance(week_contract, Mapping):
        week_axis = score_week_axis(
            weeks,
            week_contract,
            scheduled_plan=scheduled_plan,
        )
    if isinstance(site_rollout_contract, Mapping):
        site_rollout_axis = score_site_rollout_week_axis(
            table(context, "site_rollout"),
            site_rollout_contract,
            scheduled_plan=scheduled_plan,
        )
    if isinstance(zero_business_metrics, list):
        gap_zero_business = score_gap_zero_business(
            frame,
            blocks,
            aggregate_blocks,
            weeks,
            zero_business_metrics,
        )
    return GapEvidence(
        evidence_modes=evidence_modes,
        role=role,
        frame=frame,
        adapter_issues=adapter_issues,
        blocks=blocks,
        aggregate_blocks=aggregate_blocks,
        weeks=weeks,
        evidence_level=evidence_level,
        contract_issues=contract_issues,
        alignment=alignment,
        week_axis=week_axis,
        site_rollout_axis=site_rollout_axis,
        gap_zero_business=gap_zero_business,
    )
