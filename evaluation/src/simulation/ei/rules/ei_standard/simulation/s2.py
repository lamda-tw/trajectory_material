"""S2 mature reuse inbound scoring."""

from __future__ import annotations

from collections import defaultdict
from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import (
    failed_leaf,
    leaf,
    normalized,
    quantity_error,
    table,
    validation_issues,
)
from simulation.ei.core.adapters import warehouse_week_kind
from ..common import (
    _find_column,
    _bom_key,
    _norm,
    _number,
    _quantity_overlap,
)
from .evidence import GapEvidence
from .gap import (
    _aggregate_gap_s2,
    _combine_s2_stages,
    _gap_expected_mature_by_item_week,
    _gap_rule_issue_scope,
    _gap_s2,
    _timeline_expected,
    _warehouse_allowed_materials,
)
from .warehouse import _warehouse_field_by_item_week


def score_s2(context: RuleContext, gap: GapEvidence) -> CheckResult:
    parameters = context.component.parameters
    rule_id = 'S2'
    evidence_modes = gap.evidence_modes
    gap_role = gap.role
    gap_frame = gap.frame
    gap_adapter_issues = gap.adapter_issues
    gap_blocks = gap.blocks
    gap_aggregate_blocks = gap.aggregate_blocks
    gap_weeks = gap.weeks
    gap_evidence_level = gap.evidence_level
    gap_contract_issues = gap.contract_issues
    gap_alignment = gap.alignment
    if evidence_modes['S2'] == 'gap-wide':
        issue_scope = _gap_rule_issue_scope(gap_frame, gap_blocks, gap_weeks, gap_adapter_issues, gap_contract_issues, 'S2', metric_aliases={str(metric): 'ReuseInbound' for metric in gap_alignment.get('source_metrics', ()) if str(metric) != 'initial_inventory'}) if gap_frame is not None else None
        if gap_frame is None:
            return failed_leaf(context, 'S2', 'Mature reuse inbound', 'MISSING_ARTIFACT', f'{gap_role} is missing or unusable')
        elif issue_scope and issue_scope['blocking']:
            return failed_leaf(context, 'S2', 'Mature reuse inbound', 'INVALID_GAP_CONTRACT', 'gap.csv does not satisfy the Prompt structure and integer contract', {'scoped_issues': issue_scope['relevant'], 'blocking_issues': issue_scope['blocking']})
        else:
            assert issue_scope is not None
            warehouse_role_configured = 'reuse_warehouse' in context.question.artifacts
            warehouse = normalized(context, 'reuse_warehouse')
            dedicated_warehouse_present = warehouse is not None
            warehouse_issues = validation_issues(context, 'reuse_warehouse')
            failed_warehouse_units = {str(unit_id) for artifact in (warehouse_issues or {}).get('artifacts', []) for issue in artifact.get('issues', []) if issue.get('code') == 'NON_INTEGER_QUANTITY' for unit_id in issue.get('affected_unit_ids', [])}
            reuse_rate = float(parameters.get('reuse_rate', 1.0))
            if gap_evidence_level == 'aggregate':
                rate, evidence = _aggregate_gap_s2(gap_aggregate_blocks, warehouse, reuse_rate=reuse_rate, invalid_quantity_units=len(failed_warehouse_units) + len(issue_scope['source_unit_ids']))
            else:
                maturity_stage = _gap_s2(gap_blocks, gap_weeks, repair_weeks=int(parameters['repair_weeks']), reuse_rate=reuse_rate, invalid_week_fields=issue_scope['weekly_fields'], extra_invalid_units=len(issue_scope['extra_units']))
                if dedicated_warehouse_present:
                    expected_mature = _gap_expected_mature_by_item_week(gap_blocks, gap_weeks, repair_weeks=int(parameters['repair_weeks']), reuse_rate=reuse_rate)
                    actual_inbound = _warehouse_field_by_item_week(warehouse, 'inbound') if warehouse is not None else {}
                    warehouse_stage = _quantity_overlap(expected_mature, actual_inbound)
                    rate, evidence = _combine_s2_stages(maturity_stage, warehouse_stage, invalid_quantity_units=len(failed_warehouse_units))
                else:
                    rate, evidence = maturity_stage
            evidence.update({'invalid_source_units': len(issue_scope['source_unit_ids']), 'failed_source_unit_ids': sorted(issue_scope['source_unit_ids']), 'scoped_validation_issues': issue_scope['relevant'][:50], 'inbound_alignment': gap_alignment, 'dedicated_warehouse_role_configured': warehouse_role_configured, 'dedicated_warehouse_present': dedicated_warehouse_present, 'warehouse_evidence_source': 'gap-aligned-inbound+dedicated-warehouse' if dedicated_warehouse_present else 'gap-aligned-inbound', 'warehouse_validation_issues': warehouse_issues or {}, 'failed_warehouse_unit_ids': sorted(failed_warehouse_units)[:50]})
            return leaf(context, 'S2', 'Mature reuse inbound', rate, 'Dismantled quantity must appear as reuse-warehouse Inbound only after the Prompt maturity period', evidence, reason_code='GAP_MATURE_SUPPLY_MISMATCH' if rate < 1 else '')
    warehouse = normalized(context, 'reuse_warehouse')
    timeline = table(context, 'site_material_timeline')
    recovered = table(context, 'recovered_supply')
    inventory_scope_configured = 'initial_inventory_source' in context.question.artifacts
    inventory_source = table(context, 'initial_inventory_source')
    integer_error = quantity_error(context, 'reuse_warehouse', 'site_material_timeline', 'recovered_supply')
    if warehouse is None or (timeline is None and recovered is None):
        return failed_leaf(context, 'S2', 'Mature reuse inbound', 'MISSING_ARTIFACT', 'Mature supply evidence or reuse warehouse is missing')
    elif inventory_scope_configured and inventory_source is None:
        return failed_leaf(context, 'S2', 'Mature reuse inbound', 'MISSING_ARTIFACT', 'The Prompt Input2 warehouse-material scope is missing or unusable')
    else:
        try:
            expected: dict[tuple[str, int], float] = defaultdict(float)
            if recovered is not None:
                item_col = _find_column(recovered, 'item_code')
                week_col = _find_column(recovered, 'available_week')
                qty_col = _find_column(recovered, 'available_qty')
                if None in {item_col, week_col, qty_col}:
                    raise ValueError('recovered_supply lacks item/week/quantity columns')
                for _, row in recovered.iterrows():
                    item = _norm(row.get(item_col))
                    week = _number(row.get(week_col))
                    qty = _number(row.get(qty_col))
                    if item and week is not None and (qty is not None):
                        expected[_bom_key(item), int(week)] += qty
            else:
                reuse_rate = float(parameters['reuse_rate'])
                timeline_week_kind = warehouse_week_kind(warehouse)
                source_expected = _timeline_expected(timeline, int(parameters['repair_weeks']), reuse_rate, timeline_week_kind)
                allowed_materials = _warehouse_allowed_materials(inventory_source) if inventory_source is not None else None
                expected.update({key: quantity for key, quantity in source_expected.items() if allowed_materials is None or key[0] in allowed_materials})
            actual = _warehouse_field_by_item_week(warehouse, 'inbound')
            if timeline is not None and recovered is None and (allowed_materials is not None):
                actual = {key: quantity for key, quantity in actual.items() if key[0] in allowed_materials}
            rate, evidence = _quantity_overlap(expected, actual)
            source_issues = validation_issues(context, 'reuse_warehouse', 'site_material_timeline', 'recovered_supply')
            failed_unit_ids = {str(unit_id) for artifact in (source_issues or {}).get('artifacts', []) for issue in artifact.get('issues', []) if issue.get('code') == 'NON_INTEGER_QUANTITY' for unit_id in issue.get('affected_unit_ids', [])}
            if failed_unit_ids:
                combined = float(evidence.get('combined_qty', 0.0)) + len(failed_unit_ids)
                rate = float(evidence.get('matched_qty', 0.0)) / combined if combined else 0.0
            evidence.update({'invalid_quantity_unit_count': len(failed_unit_ids), 'invalid_quantity_unit_samples': sorted(failed_unit_ids)[:50], 'integer_contract': integer_error or {}})
            if timeline is not None and recovered is None:
                excluded = {key: quantity for key, quantity in source_expected.items() if key not in expected}
                evidence.update({'repair_weeks': int(parameters['repair_weeks']), 'reuse_rate': reuse_rate, 'warehouse_allowed_materials': len(allowed_materials) if allowed_materials is not None else None, 'source_expected_objects': len(source_expected), 'source_expected_qty': round(sum(source_expected.values()), 6), 'excluded_unstorable_objects': len(excluded), 'excluded_unstorable_qty': round(sum(excluded.values()), 6)})
            return leaf(context, 'S2', 'Mature reuse inbound', rate, 'Only supply that has reached its prompt maturity week may enter the reuse warehouse', evidence)
        except Exception as exc:
            return failed_leaf(context, 'S2', 'Mature reuse inbound', 'INVALID_ARTIFACT', 'Mature supply evidence cannot be parsed', {'error': str(exc)})
