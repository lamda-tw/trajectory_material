"""Pure GAP and mature-supply evidence calculations for S2 and S3."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.adapters import (
    shift_week_coordinate,
    warehouse_key_parts,
    week_coordinate_kind,
)
from simulation.ei.core.adapters.products.gap import (
    normalize_gap_wide,
)
from simulation.ei.core.adapters.products.site_material_timeline import (
    normalize_timeline_mature_supply,
)

from ..common import (
    _find_column,
    _bom_key,
    _norm,
    _sheet_with,
)


_GAP_METRICS = {'dismantled': 'Dismantled', 'arrive': 'Arrive', 'dismantledsupply': 'DismantledSupply', 'reuseconsumed': 'ReuseConsumed', 'demand': 'Demand', 'gap': 'GAP', 'newproposal': 'GAP'}


_GAP_SUMMARIES = {'total_dismantled': 'total_dismantled', 'initial_inventory': 'initial_inventory', 'total_arrive': 'totalArrive', 'total_reuse': 'totalReuse', 'total_demand': 'totalDemand', 'total_gap': 'totalGap'}


_GAP_RULE_METRICS = {'S2': frozenset({'Dismantled', 'ReuseInbound'}), 'S3': frozenset({'DismantledSupply', 'ReuseConsumed'})}


_GAP_RULE_SUMMARIES = {'S2': frozenset(), 'S3': frozenset({'initial_inventory', 'total_reuse'})}


def _timeline_expected(frame: pd.DataFrame, repair_weeks: int, reuse_rate: float, week_kind: str='project') -> dict[tuple[str, int], float]:
    result, issues = normalize_timeline_mature_supply(frame, repair_weeks=repair_weeks, reuse_rate=reuse_rate, week_kind=week_kind)
    blocking = [value for value in issues if value.get('code') == 'MISSING_TIMELINE_MATURE_SUPPLY_COLUMNS']
    if blocking:
        raise ValueError(str(blocking[0].get('message', blocking[0])))
    return {(_bom_key(item), week): quantity for (item, week), quantity in result.items()}


def _warehouse_allowed_materials(source: pd.DataFrame | Mapping[str, pd.DataFrame]) -> set[str]:
    """Compile the Prompt Input2 whitelist with the same BOM identity as warehouses."""
    frame = _sheet_with(source, (('*bom/编码', 'bom', 'item_code'),), sheet_hint='Sheet1')
    item_col = _find_column(frame, '*bom/编码', 'bom', 'item_code')
    if item_col is None:
        raise ValueError('initial inventory source lacks a BOM item column')
    materials = {item for value in frame[item_col] if (item := _bom_key(value))}
    if not materials:
        raise ValueError('initial inventory source contains no warehouse-eligible materials')
    return materials


def _gap_wide_contract(frame: pd.DataFrame) -> tuple[dict[tuple[str, str], dict[str, Any]], tuple[int, ...], list[dict[str, Any]]]:
    """Compatibility facade over the authoritative GAP adapter."""
    payload, issues = normalize_gap_wide(frame)
    return (payload['blocks'], tuple(payload['weeks']), list(issues))


def _simulation_evidence_mode(parameters: Mapping[str, Any], rule_id: str) -> str:
    """Resolve a rule-local evidence mode with the legacy component mode as fallback."""
    return str(parameters.get(f'{rule_id.casefold()}_evidence_mode', parameters.get('simulation_evidence_mode', 'warehouse')))


def _gap_header_key(value: Any) -> str:
    return re.sub('[^0-9a-z]+', '', _norm(value).casefold())


def _gap_flat_adapter_issues(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [dict(issue) for artifact_issues in (payload or {}).get('artifacts', []) for issue in artifact_issues.get('issues', [])]


def _gap_row_identity(frame: pd.DataFrame, issue: Mapping[str, Any]) -> tuple[tuple[str, str] | None, str | None]:
    region = _norm(issue.get('region'))
    item = _norm(issue.get('item'))
    metric = issue.get('metric')
    row_number = issue.get('row')
    if (not region or not item or metric is None) and isinstance(row_number, int):
        offset = row_number - 2
        if 0 <= offset < len(frame):
            row = frame.iloc[offset]
            region_col = _find_column(frame, 'region')
            item_col = _find_column(frame, 'item_code')
            metric_col = _find_column(frame, 'week')
            region = region or (_norm(row.get(region_col)) if region_col else '')
            item = item or (_norm(row.get(item_col)) if item_col else '')
            metric_raw = _norm(row.get(metric_col)) if metric_col else ''
            metric_key = re.sub('[^0-9a-z]+', '', metric_raw.casefold())
            metric = metric or _GAP_METRICS.get(metric_key)
    key = (_bom_key(region), _bom_key(item)) if region and item else None
    return (key, str(metric) if metric else None)


def _gap_rule_issue_scope(frame: pd.DataFrame, blocks: Mapping[tuple[str, str], Mapping[str, Any]], weeks: tuple[int, ...], adapter_payload: Mapping[str, Any] | None, contract_issues: list[dict[str, Any]], rule_id: str, metric_aliases: Mapping[str, str] | None=None) -> dict[str, Any]:
    """Keep gap defects inside the checks and units that consume their fields."""
    metrics = _GAP_RULE_METRICS[rule_id]
    summaries = _GAP_RULE_SUMMARIES[rule_id]
    weekly_fields: set[tuple[tuple[str, str], str, int]] = set()
    summary_fields: set[tuple[tuple[str, str], str]] = set()
    extra_units: set[str] = set()
    relevant: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    metric_aliases = metric_aliases or {}

    def record(issue: Mapping[str, Any]) -> None:
        relevant.append(dict(issue))

    def add_metric_issue(issue: Mapping[str, Any], key: tuple[str, str] | None, metric: str | None, issue_weeks: tuple[int, ...] | None=None) -> None:
        metric = metric_aliases.get(str(metric), str(metric)) if metric else metric
        if metric not in metrics:
            return
        record(issue)
        target_weeks = issue_weeks or weeks
        if key is None:
            extra_units.add(f"row:{issue.get('row', 'unknown')}:{metric}:{issue.get('column', '')}")
            return
        for week in target_weeks:
            weekly_fields.add((key, metric, int(week)))

    def add_summary_issue(issue: Mapping[str, Any], key: tuple[str, str] | None, field: str | None) -> None:
        if field not in summaries:
            return
        record(issue)
        if key is None:
            extra_units.add(f"row:{issue.get('row', 'unknown')}:summary:{field or 'unknown'}")
            return
        summary_fields.add((key, str(field)))
    actual_headers = {_gap_header_key(value) for value in frame.columns}
    summary_by_header = {_gap_header_key(source): name for name, source in _GAP_SUMMARIES.items()}
    key_headers = {'region', 'itemcode', 'week'}
    for issue in _gap_flat_adapter_issues(adapter_payload):
        code = str(issue.get('code', ''))
        if code in {'MISSING_GAP_KEY_COLUMNS', 'MISSING_GAP_WEEK_COLUMNS', 'NON_CONTIGUOUS_GAP_WEEKS', 'INVALID_GAP_DATE_ROW', 'INVALID_GAP_QUANTITY', 'NON_INTEGER_QUANTITY', 'UNKNOWN_GAP_METRIC', 'EMPTY_GAP_BUSINESS_KEY', 'DUPLICATE_GAP_METRIC', 'MISSING_GAP_METRICS', 'CONFLICTING_GAP_SUMMARY', 'EMPTY_GAP_BUSINESS_ROWS'}:
            continue
        column_key = _gap_header_key(issue.get('column'))
        key, metric = _gap_row_identity(frame, issue)
        week_match = re.fullmatch('wk([0-9]+)', column_key)
        summary = summary_by_header.get(column_key)
        if code == 'NON_INTEGER_QUANTITY':
            if week_match:
                add_metric_issue(issue, key, metric, (int(week_match.group(1)),))
            elif summary:
                add_summary_issue(issue, key, summary)
            continue
        if code == 'GAP_WEEK_WINDOW_MISMATCH':
            record(issue)
            expected = {int(value) for value in issue.get('expected_weeks', [])}
            actual = {int(value) for value in issue.get('actual_weeks', [])}
            for week in sorted(expected - actual):
                for block_key in blocks:
                    if rule_id == 'S2':
                        for dependency in metrics:
                            weekly_fields.add((block_key, dependency, week))
                    else:
                        extra_units.add(f'{block_key[0]}|{block_key[1]}|WK{week}')
        elif code == 'EXACT_COLUMNS_MISMATCH':
            expected = {_gap_header_key(value) for value in issue.get('expected', [])}
            missing = expected - actual_headers
            missing_keys = missing & key_headers
            if missing_keys:
                record(issue)
                blocking.append(dict(issue))
                continue
            for header in missing:
                if (match := re.fullmatch('wk([0-9]+)', header)):
                    week = int(match.group(1))
                    for block_key in blocks:
                        if rule_id == 'S2':
                            for dependency in metrics:
                                weekly_fields.add((block_key, dependency, week))
                        else:
                            extra_units.add(f'{block_key[0]}|{block_key[1]}|WK{week}')
                elif (field := summary_by_header.get(header)) in summaries:
                    for block_key in blocks:
                        summary_fields.add((block_key, str(field)))
            if missing:
                record(issue)
        elif code == 'DUPLICATE_SOURCE_COLUMN':
            if column_key in key_headers:
                record(issue)
                blocking.append(dict(issue))
            elif week_match:
                record(issue)
                week = int(week_match.group(1))
                for block_key in blocks:
                    for dependency in metrics:
                        weekly_fields.add((block_key, dependency, week))
            elif summary in summaries:
                record(issue)
                for block_key in blocks:
                    summary_fields.add((block_key, str(summary)))
        elif code == 'MISSING_REQUIRED_COLUMN':
            aliases = {_gap_header_key(value) for value in issue.get('aliases', [])}
            if aliases & key_headers:
                record(issue)
                blocking.append(dict(issue))
            elif any((re.fullmatch('wk[0-9]+', value) for value in aliases)):
                record(issue)
                for value in aliases:
                    if (match := re.fullmatch('wk([0-9]+)', value)):
                        week = int(match.group(1))
                        for block_key in blocks:
                            if rule_id == 'S2':
                                for dependency in metrics:
                                    weekly_fields.add((block_key, dependency, week))
                            else:
                                extra_units.add(f'{block_key[0]}|{block_key[1]}|WK{week}')
            elif any((summary_by_header.get(value) in summaries for value in aliases)):
                record(issue)
                for block_key in blocks:
                    for value in aliases:
                        if (field := summary_by_header.get(value)) in summaries:
                            summary_fields.add((block_key, str(field)))
        else:
            record(issue)
            blocking.append(dict(issue))
    for issue in contract_issues:
        code = str(issue.get('code', ''))
        key, metric = _gap_row_identity(frame, issue)
        if code in {'MISSING_GAP_KEY_COLUMNS', 'MISSING_GAP_WEEK_COLUMNS', 'EMPTY_GAP_BUSINESS_ROWS'}:
            record(issue)
            blocking.append(dict(issue))
        elif code == 'NON_CONTIGUOUS_GAP_WEEKS':
            present = {int(value) for value in issue.get('weeks', [])}
            missing = range(min(present), max(present) + 1) if present else ()
            for week in missing:
                if week not in present:
                    for block_key in blocks:
                        if rule_id == 'S2':
                            for dependency in metrics:
                                weekly_fields.add((block_key, dependency, week))
                        else:
                            extra_units.add(f'{block_key[0]}|{block_key[1]}|WK{week}')
            record(issue)
        elif code == 'GAP_WEEK_WINDOW_MISMATCH':
            expected = {int(value) for value in issue.get('expected_weeks', [])}
            actual = {int(value) for value in issue.get('actual_weeks', [])}
            for week in sorted(expected - actual):
                for block_key in blocks:
                    if rule_id == 'S2':
                        for dependency in metrics:
                            weekly_fields.add((block_key, dependency, week))
                    else:
                        extra_units.add(f'{block_key[0]}|{block_key[1]}|WK{week}')
            record(issue)
        elif code == 'INVALID_GAP_DATE_ROW':
            continue
        elif code in {'INVALID_GAP_QUANTITY', 'NON_INTEGER_QUANTITY'}:
            affected_metrics = [str(value) for value in issue.get('affected_metrics', [])]
            affected_metric = metric if metric in _GAP_METRICS.values() else affected_metrics[0] if affected_metrics else str(issue.get('metric') or '')
            if affected_metric in _GAP_METRICS.values():
                issue_week = issue.get('week')
                add_metric_issue(issue, key, affected_metric, (int(issue_week),) if issue_week is not None else None)
            else:
                add_summary_issue(issue, key, str(issue.get('field') or affected_metric))
        elif code in {'DUPLICATE_GAP_METRIC', 'MISSING_GAP_METRICS'}:
            affected = [str(issue.get('metric'))] if code == 'DUPLICATE_GAP_METRIC' else [str(value) for value in issue.get('missing', [])]
            for affected_metric in affected:
                add_metric_issue(issue, key, affected_metric)
        elif code == 'EMPTY_GAP_BUSINESS_KEY':
            add_metric_issue(issue, None, metric)
        elif code == 'CONFLICTING_GAP_SUMMARY':
            add_summary_issue(issue, key, str(issue.get('field') or ''))
        elif code == 'UNKNOWN_GAP_METRIC':
            continue
        else:
            record(issue)
            blocking.append(dict(issue))
    source_unit_ids = {f'{key[0]}|{key[1]}|WK{week}' for key, _, week in weekly_fields}
    source_unit_ids.update((f'{key[0]}|{key[1]}|summary:{field}' for key, field in summary_fields))
    source_unit_ids.update(extra_units)
    return {'blocking': blocking, 'relevant': relevant, 'weekly_fields': weekly_fields, 'summary_fields': summary_fields, 'extra_units': extra_units, 'source_unit_ids': source_unit_ids}


def _gap_s2(blocks: Mapping[tuple[str, str], Mapping[str, Any]], weeks: tuple[int, ...], *, repair_weeks: int, reuse_rate: float, invalid_week_fields: set[tuple[tuple[str, str], str, int]] | None=None, extra_invalid_units: int=0) -> tuple[float, dict[str, Any]]:
    expected: dict[tuple[str, str, int], float] = defaultdict(float)
    actual: dict[tuple[str, str, int], float] = defaultdict(float)
    invalid_week_fields = invalid_week_fields or set()
    score_weeks = tuple(sorted(set(weeks) | {int(value[2]) for value in invalid_week_fields}))
    week_kind = week_coordinate_kind(score_weeks)
    week_set = set(score_weeks)
    invalid_score_units: set[tuple[str, str, int]] = set()
    for key, metric, week in invalid_week_fields:
        if metric == 'Dismantled':
            mature_week = shift_week_coordinate(int(week), repair_weeks, week_kind)
            if mature_week in week_set:
                invalid_score_units.add((key[0], key[1], mature_week))
        elif metric == 'ReuseInbound':
            invalid_score_units.add((key[0], key[1], int(week)))
    sign_failures: list[dict[str, Any]] = []
    for (region, item), block in blocks.items():
        dismantled = block['metrics'].get('Dismantled', {})
        supply = block['metrics'].get('ReuseInbound', {})
        for week in score_weeks:
            dismantled_quantity = int(dismantled.get(week, 0))
            supply_quantity = int(supply.get(week, 0))
            if dismantled_quantity < 0 or supply_quantity < 0:
                sign_failures.append({'region': region, 'item': item, 'week': week, 'dismantled': dismantled_quantity, 'reuse_inbound': supply_quantity})
            mature_week = shift_week_coordinate(week, repair_weeks, week_kind)
            if mature_week in week_set:
                expected[region, item, mature_week] += max(0, dismantled_quantity) * reuse_rate
                if dismantled_quantity < 0:
                    invalid_score_units.add((region, item, mature_week))
            actual[region, item, week] += max(0, supply_quantity)
            if supply_quantity < 0:
                invalid_score_units.add((region, item, week))
    quantity_units = set(expected) | set(actual) | invalid_score_units
    matched = sum((0.0 if key in invalid_score_units else min(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0))) for key in quantity_units))
    combined = sum((max(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0)), 1.0 if key in invalid_score_units else 0.0) for key in quantity_units)) + max(0, int(extra_invalid_units))
    rate = matched / combined if combined else 1.0
    mismatches = [{'region': key[0], 'item': key[1], 'week': key[2], 'expected': expected.get(key, 0.0), 'actual': actual.get(key, 0.0), 'invalid_source': key in invalid_score_units} for key in sorted(quantity_units) if key in invalid_score_units or expected.get(key, 0.0) != actual.get(key, 0.0)]
    return (rate, {'objects': len(quantity_units) + max(0, int(extra_invalid_units)), 'matched_qty': round(matched, 6), 'combined_qty': round(combined, 6), 'repair_weeks': repair_weeks, 'reuse_rate': reuse_rate, 'invalid_score_unit_count': len(invalid_score_units), 'invalid_score_unit_samples': [{'region': key[0], 'item': key[1], 'week': key[2]} for key in sorted(invalid_score_units)[:50]], 'extra_invalid_units': max(0, int(extra_invalid_units)), 'sign_failure_count': len(sign_failures), 'sign_failure_samples': sign_failures[:50], 'mismatch_count': len(mismatches), 'mismatch_samples': mismatches[:50]})


def _gap_expected_mature_by_item_week(blocks: Mapping[tuple[str, str], Mapping[str, Any]], weeks: tuple[int, ...], *, repair_weeks: int, reuse_rate: float) -> dict[tuple[str, int], float]:
    week_kind = week_coordinate_kind(weeks)
    submitted_weeks = set(weeks)
    expected: dict[tuple[str, int], float] = defaultdict(float)
    for (_, item), block in blocks.items():
        dismantled = block.get('metrics', {}).get('Dismantled', {})
        for week in weeks:
            mature_week = shift_week_coordinate(week, repair_weeks, week_kind)
            if mature_week not in submitted_weeks:
                continue
            expected[item, mature_week] += max(0.0, float(dismantled.get(week, 0))) * float(reuse_rate)
    return dict(expected)


def _combine_s2_stages(first: tuple[float, Mapping[str, Any]], second: tuple[float, Mapping[str, Any]], *, invalid_quantity_units: int=0) -> tuple[float, dict[str, Any]]:
    first_rate, first_evidence = first
    second_rate, second_evidence = second
    matched = float(first_evidence.get('matched_qty', 0.0)) + float(second_evidence.get('matched_qty', 0.0))
    combined = float(first_evidence.get('combined_qty', 0.0)) + float(second_evidence.get('combined_qty', 0.0)) + max(0, int(invalid_quantity_units))
    return (matched / combined if combined else min(first_rate, second_rate), {'evidence_level': 'weekly', 'maturity_interval': dict(first_evidence), 'warehouse_inbound': dict(second_evidence), 'matched_qty': round(matched, 6), 'combined_qty': round(combined, 6), 'invalid_quantity_unit_count': max(0, int(invalid_quantity_units))})


def _aggregate_gap_s2(aggregate_blocks: Mapping[tuple[str, str], Mapping[str, Any]], warehouse: Mapping[tuple[Any, ...], Mapping[str, Any]] | None, *, reuse_rate: float, invalid_quantity_units: int=0) -> tuple[float, dict[str, Any]]:
    expected: dict[str, float] = defaultdict(float)
    submitted: dict[str, float] = defaultdict(float)
    for (_, item), block in aggregate_blocks.items():
        summary = block.get('summary', {})
        expected[item] += max(0.0, float(summary.get('total_dismantled', 0))) * float(reuse_rate)
        submitted[item] += max(0.0, float(summary.get('total_arrive', 0)))
    actual: dict[str, float] = defaultdict(float)
    if warehouse is not None:
        for key, cell in warehouse.items():
            _, item, _ = warehouse_key_parts(key)
            actual[item] += max(0.0, float(cell.get('inbound', 0)))
    items = set(expected) | set(submitted) | set(actual)
    matched = sum((min(expected.get(item, 0.0), submitted.get(item, 0.0), actual.get(item, 0.0)) for item in items))
    combined = sum((max(expected.get(item, 0.0), submitted.get(item, 0.0), actual.get(item, 0.0)) for item in items)) + max(0, int(invalid_quantity_units))
    quantity_rate = matched / combined if combined else 0.0
    rate = 0.5 * quantity_rate
    return (rate, {'evidence_level': 'aggregate', 'maximum_evidence_credit': 0.5, 'missing_dimension': 'item_week_maturity_interval', 'items': len(items), 'matched_qty': round(matched, 6), 'combined_qty': round(combined, 6), 'quantity_rate': round(quantity_rate, 12), 'invalid_quantity_unit_count': max(0, int(invalid_quantity_units))})


def _gap_s3(blocks: Mapping[tuple[str, str], Mapping[str, Any]], weeks: tuple[int, ...], *, invalid_week_fields: set[tuple[tuple[str, str], str, int]] | None=None, invalid_summary_fields: set[tuple[tuple[str, str], str]] | None=None, extra_invalid_units: int=0) -> tuple[float, dict[str, Any]]:
    invalid_week_fields = invalid_week_fields or set()
    invalid_summary_fields = invalid_summary_fields or set()
    total = 0
    valid = 0
    failures: list[dict[str, Any]] = []
    for key, block in blocks.items():
        region, item = key
        opening = int(block['summary'].get('initial_inventory', 0))
        state_source_valid = (key, 'initial_inventory') not in invalid_summary_fields
        reuse_total_source_valid = True
        reuse_total = 0
        for week in weeks:
            inbound = int(block['metrics'].get('DismantledSupply', {}).get(week, 0))
            outbound = int(block['metrics'].get('ReuseConsumed', {}).get(week, 0))
            source_fields = sorted((field for field in ('DismantledSupply', 'ReuseConsumed') if (key, field, week) in invalid_week_fields))
            source_valid = state_source_valid and (not source_fields)
            closing = opening + inbound - outbound
            cell_valid = source_valid and opening >= 0 and (inbound >= 0) and (outbound >= 0) and (closing >= 0)
            total += 1
            valid += int(cell_valid)
            if not cell_valid and len(failures) < 50:
                failures.append({'region': region, 'item': item, 'week': week, 'opening': opening, 'inbound': inbound, 'outbound': outbound, 'inferred_closing': closing, 'invalid_source_fields': source_fields, 'upstream_source_valid': state_source_valid})
            state_source_valid = source_valid
            reuse_total_source_valid = reuse_total_source_valid and 'ReuseConsumed' not in source_fields
            opening = closing
            reuse_total += outbound
        total += 1
        summary_source_valid = (key, 'total_reuse') not in invalid_summary_fields and reuse_total_source_valid
        summary_valid = summary_source_valid and reuse_total == int(block['summary'].get('total_reuse', 0))
        valid += int(summary_valid)
        if not summary_valid and len(failures) < 50:
            failures.append({'region': region, 'item': item, 'field': 'totalReuse', 'expected': reuse_total, 'actual': int(block['summary'].get('total_reuse', 0)), 'source_valid': summary_source_valid})
    total += max(0, int(extra_invalid_units))
    return (valid / total if total else 0.0, {'unit': 'region_item_week_plus_summary', 'units': total, 'valid': valid, 'invalid': total - valid, 'failure_samples': failures})
