"""Site-plan and final-BOM time calculations for S5 and S6."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

import pandas as pd

from simulation.ei.core.adapters import (
    parse_iso_week,
    parse_project_week,
)

from ..common import (
    _find_column,
    _key,
    _norm,
    _number,
    _month_from_row,
    _month_number,
)
from ..scheduling import _candidate_plan


def _scheduled_plan_from_candidate(
    plan_frame: pd.DataFrame,
    plan: pd.DataFrame,
) -> pd.DataFrame:
    """Filter a pre-parsed plan using candidate-owned scheduling status."""

    status_col = _find_column(plan_frame, 'status')
    if status_col is not None:
        statuses = plan_frame[status_col].map(lambda value: _norm(value).casefold())
        plan = plan.loc[statuses.eq('scheduled').to_numpy()].copy()
    return plan.loc[plan['site'].map(_norm).ne('') & plan['action'].isin(('install', 'dismantle'))].copy()


def _scheduled_plan(plan_frame: pd.DataFrame, *, project_week_source: str) -> pd.DataFrame:
    plan = _candidate_plan(plan_frame, project_week_source=project_week_source)
    return _scheduled_plan_from_candidate(plan_frame, plan)


def _s6_project_month_coordinate(week: int, *, planning_year: int, project_start_month: int) -> tuple[int, int] | None:
    """Map an unbounded project week to its four-week natural month."""
    if week < 1 or not 1 <= project_start_month <= 12:
        return None
    month_offset = project_start_month - 1 + (week - 1) // 4
    return (planning_year + month_offset // 12, month_offset % 12 + 1)


def _s6_plan_month_coordinate(row: pd.Series, *, project_week: int, planning_year: int, week_to_month: str, project_start_month: int) -> tuple[int, int] | None:
    """Return an S6 comparison coordinate without changing C/O month buckets."""
    if week_to_month == 'four-week-project':
        return _s6_project_month_coordinate(project_week, planning_year=planning_year, project_start_month=project_start_month)
    month = _month_from_row(row, planning_year, week_to_month=week_to_month, project_start_month=project_start_month)
    return (0, month) if month is not None else None


def _s6_final_month_coordinate(value: Any, *, planning_year: int, week_to_month: str) -> tuple[int, int] | None:
    """Normalize a final-BOM month into the coordinate used by S6."""
    if week_to_month != 'four-week-project':
        month = _month_number(value)
        return (0, month) if month is not None else None
    label = _norm(value)
    explicit = re.fullmatch('(20\\d{2})\\s*[-/]?\\s*M(\\d{1,2})', label, re.I)
    if explicit:
        year, month = (int(explicit.group(1)), int(explicit.group(2)))
        return (year, month) if 1 <= month <= 12 else None
    ordinal_match = re.fullmatch('M(\\d+)', label, re.I)
    ordinal_value = float(ordinal_match.group(1)) if ordinal_match else _number(value)
    if ordinal_value is not None:
        if float(ordinal_value).is_integer() and ordinal_value >= 1:
            ordinal = int(ordinal_value)
            return (planning_year + (ordinal - 1) // 12, (ordinal - 1) % 12 + 1)
        return None
    parsed = pd.to_datetime(value, errors='coerce')
    if not pd.isna(parsed):
        return (int(parsed.year), int(parsed.month))
    return None


def _time_accuracy(plan_frame: pd.DataFrame, final: pd.DataFrame, *, time_mode: str, week_kind: str, project_week_source: str, planning_year: int, week_to_month: str, project_start_month: int, require_inactive_time_blank: bool=True, scheduled_plan: pd.DataFrame | None=None) -> tuple[float, dict[str, Any]]:
    if time_mode not in {'project-week', 'action-week-month'}:
        raise ValueError(f'unsupported S6 time mode: {time_mode}')
    if week_kind not in {'project', 'iso'}:
        raise ValueError(f'unsupported S6 week kind: {week_kind}')
    if time_mode == 'project-week' and week_kind != 'project':
        raise ValueError('project-week S6 requires project week labels')
    plan = (
        scheduled_plan
        if scheduled_plan is not None
        else _scheduled_plan(plan_frame, project_week_source=project_week_source)
    )
    plan_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in plan.to_dict('records'):
        plan_groups[str(row['action_key'])].append(row)
    plan_references: dict[str, tuple[int, tuple[int, int] | None]] = {}
    reference_conflicts: list[dict[str, Any]] = []
    plan_month_cache: dict[tuple[str, str], tuple[int, int] | None] = {}
    for action_key, rows in plan_groups.items():
        action = action_key.rsplit('|', 1)[-1]
        matching = [row for row in rows if row.get('action') == action]
        if not matching:
            reference_conflicts.append({'action_key': action_key, 'error': 'MISSING_ACTION'})
            continue
        if len(matching) > 1:
            reference_conflicts.append({'action_key': action_key, 'error': 'DUPLICATE_ACTION'})
            continue
        row = matching[0]
        if week_kind == 'iso':
            try:
                week_value = parse_iso_week(row.get('week_label'))
            except ValueError:
                reference_conflicts.append({'action_key': action_key, 'error': 'UNPARSEABLE_ISO_WEEK'})
                continue
        else:
            week_error = str(row.get('week_issue') or '')
            week_value = row.get('project_week')
            if week_error:
                reference_conflicts.append({'action_key': action_key, 'error': week_error})
                continue
            if week_value is None or pd.isna(week_value):
                reference_conflicts.append({'action_key': action_key, 'error': 'UNPARSEABLE_WEEK'})
                continue
        plan_month: tuple[int, int] | None = None
        if time_mode == 'action-week-month':
            month_signature = (_norm(row.get('week_label')), _norm(row.get('week')))
            if month_signature not in plan_month_cache:
                plan_month_cache[month_signature] = _s6_plan_month_coordinate(row, project_week=int(week_value), planning_year=planning_year, week_to_month=week_to_month, project_start_month=project_start_month)
            plan_month = plan_month_cache[month_signature]
            if plan_month is None:
                reference_conflicts.append({'action_key': action_key, 'error': 'INVALID_PLAN_MONTH'})
                continue
        plan_references[action_key] = (int(week_value), plan_month)
    site_col = _find_column(final, 'site_name', 'site id', 'site id radio')
    region_col = _find_column(final, 'region')
    action_col = _find_column(final, 'action', 'site_action')
    if site_col is None or action_col is None:
        raise ValueError('site_final_bom lacks site/action fields for S6')
    project_week_col = _find_column(final, 'project_week')
    install_week_col = _find_column(final, 'install_wk_label')
    install_month_col = _find_column(final, 'install_month')
    dismantle_week_col = _find_column(final, 'dismantle_wk_label')
    dismantle_month_col = _find_column(final, 'dismantle_month')
    if time_mode == 'project-week' and project_week_col is None:
        raise ValueError('project-week S6 requires project_week')
    if time_mode == 'action-week-month' and None in {install_week_col, install_month_col, dismantle_week_col, dismantle_month_col}:
        raise ValueError('action-week-month S6 requires install/dismantle week and month')
    positions = {str(column): int(final.columns.get_loc(column)) for column in {site_col, region_col, action_col, project_week_col, install_week_col, install_month_col, dismantle_week_col, dismantle_month_col} if column is not None}
    final_week_cache: dict[str, int | None] = {}
    final_month_cache: dict[str, tuple[int, int] | None] = {}

    def final_week(value: Any) -> int | None:
        key = _norm(value).casefold()
        if key not in final_week_cache:
            try:
                final_week_cache[key] = parse_iso_week(value) if week_kind == 'iso' else parse_project_week(value)
            except ValueError:
                final_week_cache[key] = None
        return final_week_cache[key]

    def final_month(value: Any) -> tuple[int, int] | None:
        key = _norm(value).casefold()
        if key not in final_month_cache:
            final_month_cache[key] = _s6_final_month_coordinate(value, planning_year=planning_year, week_to_month=week_to_month)
        return final_month_cache[key]
    final_groups: dict[str, dict[str, Any]] = {}
    for offset, values in enumerate(final.itertuples(index=False, name=None), start=2):
        site = _norm(values[positions[str(site_col)]])
        action = _norm(values[positions[str(action_col)]]).casefold()
        region = _norm(values[positions[str(region_col)]]) if region_col is not None else 'ALL'
        if not site or action not in {'install', 'dismantle'}:
            continue
        action_key = f'{_key(region)}|{_key(site)}|{action}'
        group = final_groups.setdefault(action_key, {'weeks': set(), 'months': set(), 'errors': set(), 'rows': []})
        group['rows'].append(offset)
        if time_mode == 'project-week':
            raw_week = values[positions[str(project_week_col)]]
            parsed_week = final_week(raw_week)
            if parsed_week is None:
                group['errors'].add('INVALID_FINAL_WEEK')
            else:
                group['weeks'].add(parsed_week)
            continue
        active_week_col = install_week_col if action == 'install' else dismantle_week_col
        active_month_col = install_month_col if action == 'install' else dismantle_month_col
        inactive_week_col = dismantle_week_col if action == 'install' else install_week_col
        inactive_month_col = dismantle_month_col if action == 'install' else install_month_col
        parsed_week = final_week(values[positions[str(active_week_col)]])
        if parsed_week is None:
            group['errors'].add('INVALID_FINAL_WEEK')
        else:
            group['weeks'].add(parsed_week)
        parsed_month = final_month(values[positions[str(active_month_col)]])
        if parsed_month is None:
            group['errors'].add('INVALID_FINAL_MONTH')
        else:
            group['months'].add(parsed_month)
        if require_inactive_time_blank:
            if _norm(values[positions[str(inactive_week_col)]]):
                group['errors'].add('INAPPLICABLE_WEEK_NOT_EMPTY')
            if _norm(values[positions[str(inactive_month_col)]]):
                group['errors'].add('INAPPLICABLE_MONTH_NOT_EMPTY')
    passed = 0
    evaluated = 0
    failures: list[dict[str, Any]] = []
    comparable_keys = set(plan_references) & set(final_groups)
    for action_key in sorted(comparable_keys):
        plan_week, plan_month = plan_references[action_key]
        group = final_groups[action_key]
        errors = set(group['errors'])
        final_weeks = set(group['weeks'])
        if len(final_weeks) != 1:
            errors.add('FINAL_WEEK_CONFLICT')
        elif next(iter(final_weeks)) != plan_week:
            errors.add('FINAL_WEEK_MISMATCH')
        if time_mode == 'action-week-month':
            final_months = set(group['months'])
            if len(final_months) != 1:
                errors.add('FINAL_MONTH_CONFLICT')
            elif next(iter(final_months)) != plan_month:
                errors.add('FINAL_MONTH_MISMATCH')
        evaluated += 1
        passed += int(not errors)
        if errors and len(failures) < 50:
            failures.append({'action_key': action_key, 'errors': sorted(errors), 'final_rows': list(group['rows'])})
    plan_keys = set(plan_groups)
    final_keys = set(final_groups)
    return (passed / evaluated if evaluated else 0.0, {'unit': 'site_action', 'week_kind': week_kind, 'project_week_source': project_week_source, 'require_inactive_time_blank': require_inactive_time_blank, 'scheduled_plan_actions': len(plan_groups), 'final_actions': len(final_groups), 'comparable_actions': evaluated, 'passed_actions': passed, 'failed_actions': evaluated - passed, 'missing_final_actions': len(plan_keys - final_keys), 'extra_final_actions': len(final_keys - plan_keys), 'reference_conflicts': reference_conflicts[:50], 'failures': failures})
