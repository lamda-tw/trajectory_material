"""Shared warehouse-rule execution for S3 and S4."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import (
    artifact,
    failed_leaf,
    leaf,
    normalized,
    validation_issues,
)
from .evidence import GapEvidence
from .gap import _gap_rule_issue_scope, _gap_s3
from .warehouse import _warehouse_balance
from .week_contract import WeekAxisResult, score_warehouse_week_axis


def _blackout_warehouse(
    cells: Mapping[tuple[Any, ...], Mapping[str, int | float]],
    expected_weeks: tuple[int, ...],
    blackout_weeks: int,
) -> tuple[float, dict[str, Any]]:
    blocked = set(expected_weeks[:blackout_weeks])
    units = [
        (key, float(cell.get("outbound", 0)))
        for key, cell in cells.items()
        if int(key[-1]) in blocked
    ]
    failures = [
        {"key": list(key), "week": int(key[-1]), "outbound": outbound}
        for key, outbound in units
        if outbound != 0
    ]
    valid = len(units) - len(failures)
    return (
        valid / len(units) if units else 1.0,
        {
            "blackout_weeks": blackout_weeks,
            "blocked_axis_weeks": list(expected_weeks[:blackout_weeks]),
            "evaluated_units": len(units),
            "valid_units": valid,
            "violation_count": len(failures),
            "violation_samples": failures[:50],
        },
    )


def _blackout_gap(
    blocks: Mapping[tuple[str, str], Mapping[str, Any]],
    expected_weeks: tuple[int, ...],
    blackout_weeks: int,
) -> tuple[float, dict[str, Any]]:
    blocked = expected_weeks[:blackout_weeks]
    units: list[tuple[tuple[str, str], int, float]] = []
    for key, block in blocks.items():
        consumed = block.get("metrics", {}).get("ReuseConsumed", {})
        units.extend(
            (key, week, float(consumed.get(week, 0))) for week in blocked
        )
    failures = [
        {
            "region": key[0],
            "item": key[1],
            "week": week,
            "reuse_consumed": value,
        }
        for key, week, value in units
        if value != 0
    ]
    valid = len(units) - len(failures)
    return (
        valid / len(units) if units else 1.0,
        {
            "blackout_weeks": blackout_weeks,
            "blocked_axis_weeks": list(blocked),
            "evaluated_units": len(units),
            "valid_units": valid,
            "violation_count": len(failures),
            "violation_samples": failures[:50],
        },
    )


def _combined_week_axis(
    results: Mapping[str, WeekAxisResult],
) -> tuple[float, dict[str, Any]]:
    if not results:
        return 1.0, {"configured_roles": [], "evaluated_units": 0}
    matched = 0
    evaluated = 0
    unresolved = False
    for result in results.values():
        matched += int(result.evidence.get("matched_unit_count", 0))
        evaluated += int(result.evidence.get("evaluated_unit_count", 0))
        unresolved = unresolved or result.status == "UNRESOLVED"
    rate = 0.0 if unresolved else matched / evaluated if evaluated else 0.0
    return rate, {
        "configured_roles": list(results),
        "matched_units": matched,
        "evaluated_units": evaluated,
        "unresolved": unresolved,
        "roles": {
            role: {"status": result.status, **result.evidence}
            for role, result in results.items()
        },
    }


def _zero_business_warehouse(
    cells: Mapping[tuple[Any, ...], Mapping[str, int | float]],
) -> tuple[int, int, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    for key, cell in cells.items():
        values = {
            field: float(cell.get(field, 0))
            for field in ("opening", "inbound", "outbound", "closing")
        }
        if any(value != 0 for value in values.values()):
            failures.append({"key": list(key), **values})
    return len(cells) - len(failures), len(cells), failures[:50]


def score_warehouse_rule(
    context: RuleContext,
    rule_id: str,
    gap: GapEvidence,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> CheckResult:
    parameters = context.component.parameters
    evidence_modes = gap.evidence_modes
    gap_role = gap.role
    gap_frame = gap.frame
    gap_adapter_issues = gap.adapter_issues
    gap_blocks = gap.blocks
    gap_weeks = gap.weeks
    gap_contract_issues = gap.contract_issues
    name = 'Reuse warehouse balance' if rule_id == 'S3' else 'New warehouse balance'
    if rule_id == 'S3' and evidence_modes[rule_id] == 'gap-wide':
        issue_scope = _gap_rule_issue_scope(gap_frame, gap_blocks, gap_weeks, gap_adapter_issues, gap_contract_issues, rule_id) if gap_frame is not None else None
        if gap_frame is None:
            return failed_leaf(context, rule_id, name, 'MISSING_ARTIFACT', f'{gap_role} is missing or unusable')
        elif issue_scope and issue_scope['blocking']:
            return failed_leaf(context, rule_id, name, 'INVALID_GAP_CONTRACT', 'gap.csv does not satisfy the Prompt structure and integer contract', {'scoped_issues': issue_scope['relevant'], 'blocking_issues': issue_scope['blocking']})
        else:
            assert issue_scope is not None
            rate, evidence = _gap_s3(gap_blocks, gap_weeks, invalid_week_fields=issue_scope['weekly_fields'], invalid_summary_fields=issue_scope['summary_fields'], extra_invalid_units=len(issue_scope['extra_units']))
            blackout_weeks = int(parameters.get('blackout_weeks', 0))
            expected_weeks = (
                gap.week_axis.expected_weeks
                if gap.week_axis is not None
                else gap_weeks
            )
            blackout_rate, blackout_evidence = _blackout_gap(
                gap_blocks,
                expected_weeks,
                blackout_weeks,
            )
            rate *= blackout_rate
            explanation = 'Reuse availability must remain nonnegative after each mature inbound and reuse consumption'
            reason_code = (
                'REUSE_BLACKOUT_VIOLATION'
                if blackout_rate < 1
                else 'REUSE_BALANCE_MISMATCH'
                if rate < 1
                else ''
            )
            evidence.update({'invalid_source_units': len(issue_scope['source_unit_ids']), 'failed_source_unit_ids': sorted(issue_scope['source_unit_ids']), 'scoped_validation_issues': issue_scope['relevant'][:50], 'blackout_contract': blackout_evidence})
            return leaf(context, rule_id, name, rate, explanation, evidence, reason_code=reason_code)
    roles = list(parameters['s3_required_roles']) if rule_id == 'S3' else ['new_warehouse']
    warehouses = [normalized(context, value) for value in roles]
    structural_issues = validation_issues(context, *roles)
    if any((value is None for value in warehouses)):
        resolutions = [artifact(context, role) for role in roles]
        all_missing = all(
            value is None or value.status == "MISSING"
            for value in resolutions
        )
        if (
            all_missing
            and parameters.get(f"{rule_id.casefold()}_missing_evidence_policy")
            == "full-credit"
        ):
            return leaf(
                context,
                rule_id,
                name,
                1.0,
                "The Prompt does not require this optional warehouse product; complete absence receives full comparison credit",
                {
                    "policy": "full-credit",
                    "missing_roles": roles,
                    "artifact_statuses": {
                        role: resolution.status if resolution is not None else "UNRESOLVED"
                        for role, resolution in zip(roles, resolutions)
                    },
                },
                reason_code="OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT",
            )
        return failed_leaf(context, rule_id, name, 'MISSING_OR_INVALID_ARTIFACT', f'one or more required warehouse roles are missing or structurally invalid: {roles}')
    else:
        issues_by_role = {str(value['role']): list(value.get('issues', ())) for value in (structural_issues or {}).get('artifacts', [])}
        diagnostics = []
        week_axis_results: dict[str, WeekAxisResult] = {}
        zero_business_results: dict[str, dict[str, Any]] = {}
        represented_failed_unit_ids: set[str] = set()
        failed_unit_ids: set[str] = set()
        for role, warehouse in zip(roles, warehouses):
            assert warehouse is not None
            forced_invalid_keys: set[tuple[Any, ...]] = set()
            for issue in issues_by_role.get(role, ()):
                qualified_unit_ids = {f'{role}:{unit_id}' for unit_id in issue.get('affected_unit_ids', ())}
                failed_unit_ids.update(qualified_unit_ids)
                raw_key = issue.get('key')
                issue_key = tuple(raw_key) if isinstance(raw_key, (list, tuple)) else None
                if issue_key is not None and issue_key in warehouse:
                    forced_invalid_keys.add(issue_key)
                    represented_failed_unit_ids.update(qualified_unit_ids)
            diagnostics.append(_warehouse_balance(warehouse, allow_negative_closing=rule_id == 'S4', forced_invalid_keys=forced_invalid_keys)[1])
            week_contracts = parameters.get('warehouse_week_contracts', {})
            contract = (
                week_contracts.get(role)
                if isinstance(week_contracts, Mapping)
                else None
            )
            if isinstance(contract, Mapping):
                week_axis_results[role] = score_warehouse_week_axis(
                    warehouse,
                    contract,
                    scheduled_plan=scheduled_plan,
                )
            if role in set(parameters.get('warehouse_zero_business_roles', ())):
                zero_valid, zero_total, zero_failures = _zero_business_warehouse(
                    warehouse
                )
                zero_business_results[role] = {
                    'valid_units': zero_valid,
                    'evaluated_units': zero_total,
                    'violation_count': zero_total - zero_valid,
                    'violation_samples': zero_failures,
                }
        cells = sum((int(value['cells']) for value in diagnostics))
        valid = sum((int(value['valid']) for value in diagnostics))
        extra_failed_unit_ids = failed_unit_ids - represented_failed_unit_ids
        denominator = cells + len(extra_failed_unit_ids)
        balance_rate = valid / denominator if denominator else 0.0
        week_axis_rate, week_axis_evidence = _combined_week_axis(
            week_axis_results
        )
        zero_valid = sum(
            int(value['valid_units']) for value in zero_business_results.values()
        )
        zero_evaluated = sum(
            int(value['evaluated_units']) for value in zero_business_results.values()
        )
        zero_business_rate = (
            zero_valid / zero_evaluated
            if zero_business_results and zero_evaluated
            else 0.0
            if zero_business_results
            else 1.0
        )
        zero_business_evidence = {
            'configured_roles': list(zero_business_results),
            'valid_units': zero_valid,
            'evaluated_units': zero_evaluated,
            'violation_count': zero_evaluated - zero_valid,
            'roles': zero_business_results,
        }
        blackout_rate = 1.0
        blackout_evidence: dict[str, Any] = {
            'blackout_weeks': int(parameters.get('blackout_weeks', 0)),
            'evaluated_units': 0,
            'violation_count': 0,
        }
        if rule_id == 'S3' and int(parameters.get('blackout_weeks', 0)) > 0:
            try:
                role_position = roles.index('reuse_warehouse')
            except ValueError:
                role_position = -1
            role_axis = week_axis_results.get('reuse_warehouse')
            if role_position >= 0:
                expected_weeks = (
                    role_axis.expected_weeks
                    if role_axis is not None
                    else tuple(
                        sorted(
                            {
                                int(key[-1])
                                for key in warehouses[role_position]
                            }
                        )
                    )
                )
                blackout_rate, blackout_evidence = _blackout_warehouse(
                    warehouses[role_position],
                    expected_weeks,
                    int(parameters['blackout_weeks']),
                )
            else:
                blackout_rate = 0.0
                blackout_evidence = {
                    **blackout_evidence,
                    'error': 'reuse_warehouse week axis is unresolved',
                }
        rate = (
            balance_rate
            * week_axis_rate
            * zero_business_rate
            * blackout_rate
        )
        evidence = {'files': len(warehouses), 'cells': cells, 'valid': valid, 'invalid': denominator - valid, 'evaluated_units': denominator, 'invalid_source_cells': len(failed_unit_ids), 'extra_invalid_source_cells': len(extra_failed_unit_ids), 'failed_unit_ids': sorted(failed_unit_ids), 'validation_issues': structural_issues or {}, 'failures': [{'role': role, **failure} for role, diagnostic in zip(roles, diagnostics) for failure in diagnostic['failures']], 'balance_rate': round(balance_rate, 12), 'warehouse_week_contracts': week_axis_evidence, 'warehouse_week_axis_rate': round(week_axis_rate, 12), 'zero_business_contract': zero_business_evidence, 'zero_business_rate': round(zero_business_rate, 12), 'blackout_contract': blackout_evidence, 'blackout_rate': round(blackout_rate, 12)}
        reason_code = (
            'WAREHOUSE_VALIDATION_ISSUES'
            if structural_issues
            else 'WAREHOUSE_BALANCE_MISMATCH'
            if balance_rate < 1
            else 'WAREHOUSE_WEEK_CONTRACT_UNRESOLVED'
            if week_axis_evidence.get('unresolved')
            else 'WAREHOUSE_WEEK_CONTRACT_MISMATCH'
            if week_axis_rate < 1
            else 'WAREHOUSE_ZERO_BUSINESS_VIOLATION'
            if zero_business_rate < 1
            else 'REUSE_BLACKOUT_VIOLATION'
            if blackout_rate < 1
            else ''
        )
        explanation = (
            'Check exact opening + inbound - outbound = closing, complete Prompt-authorized week coverage, and nonnegative inbound/outbound; new-warehouse inventory may be negative'
            if rule_id == 'S4'
            else 'Check exact opening + inbound - outbound = closing, complete Prompt-authorized week coverage, continuity, and the configured no-reuse-outbound window'
        )
        return leaf(context, rule_id, name, rate, explanation, evidence, reason_code=reason_code)
