"""Final-BOM matching calculations shared by S1 and S5."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any, Mapping

import pandas as pd

from ..common import (
    _find_column,
    _bom_key,
    _key,
    _norm,
    _number,
)


_SUPPORTED_ACTIONS = frozenset({'install', 'dismantle'})


def _authority_action(authority: Mapping[str, Mapping[str, int]], key: str, *, region_scope: str) -> Mapping[str, int] | None:
    direct = authority.get(key)
    if direct is not None:
        return direct
    if region_scope == 'exact':
        return None
    if region_scope != 'regionless':
        raise ValueError(f'unsupported S1 region scope: {region_scope}')
    parts = key.split('|')
    suffix = '|'.join(parts[-2:])
    matches = [value for action_key, value in authority.items() if action_key.endswith(suffix)]
    return matches[0] if len(matches) == 1 else None


def _maximum_material_match(authority: Mapping[str, int], actual: Mapping[str, int], alternatives: Mapping[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]) -> dict[str, Any]:
    """Maximize covered original-BOM quantity, then consumed actual quantity."""
    expected = {item: abs(int(quantity)) for item, quantity in authority.items() if int(quantity) != 0}
    remaining = {item: abs(int(quantity)) for item, quantity in actual.items() if int(quantity) != 0}
    targets: list[tuple[str, int, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]] = []
    for item, demand in expected.items():
        options = set(alternatives.get(item, ()))
        options.add((1, ((item, 1),)))
        targets.append((item, demand, tuple(sorted(options))))
    targets.sort(key=lambda value: (len(value[2]), -value[1], value[0]))
    parent = list(range(len(targets)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root
    material_owner: dict[str, int] = {}
    target_materials: list[set[str]] = []
    for target_index, (_, _, options) in enumerate(targets):
        materials = {item for _, bundle in options for item, _ in bundle}
        target_materials.append(materials)
        for item in materials:
            owner = material_owner.setdefault(item, target_index)
            union(target_index, owner)
    component_indices: dict[int, list[int]] = defaultdict(list)
    for target_index in range(len(targets)):
        component_indices[find(target_index)].append(target_index)

    def solve_component(component_targets: list[tuple[str, int, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]], material_keys: list[str]) -> tuple[int, int, dict[str, int]]:
        positions = {item: index for index, item in enumerate(material_keys)}
        initial = tuple((remaining.get(item, 0) for item in material_keys))

        def better(left: tuple[int, int, tuple[int, ...]], right: tuple[int, int, tuple[int, ...]]) -> tuple[int, int, tuple[int, ...]]:
            left_key = (left[0], left[1], tuple((-value for value in left[2])))
            right_key = (right[0], right[1], tuple((-value for value in right[2])))
            return left if left_key >= right_key else right

        @lru_cache(maxsize=None)
        def solve(target_index: int, consumed_target: int, state: tuple[int, ...]) -> tuple[int, int, tuple[int, ...]]:
            if target_index >= len(component_targets):
                return (0, 0, state)
            _, demand, options = component_targets[target_index]
            best = solve(target_index + 1, 0, state)
            for target_quantity, bundle in options:
                if target_quantity <= 0 or consumed_target + target_quantity > demand:
                    continue
                updated = list(state)
                physical_quantity = 0
                allowed = True
                for item, quantity in bundle:
                    position = positions[item]
                    if quantity <= 0 or updated[position] < quantity:
                        allowed = False
                        break
                    updated[position] -= quantity
                    physical_quantity += quantity
                if not allowed:
                    continue
                child = solve(target_index, consumed_target + target_quantity, tuple(updated))
                candidate = (target_quantity + child[0], physical_quantity + child[1], child[2])
                best = better(best, candidate)
            return best
        covered, consumed, final_state = solve(0, 0, initial)
        return (covered, consumed, {item: final_state[position] for item, position in positions.items() if final_state[position] > 0})
    covered = 0
    consumed = 0
    unmatched: dict[str, int] = {item: quantity for item, quantity in remaining.items() if item not in material_owner and quantity > 0}
    component_target_counts: list[int] = []
    for indices in sorted(component_indices.values(), key=lambda values: min(values)):
        component_targets = [targets[index] for index in indices]
        component_materials = sorted({item for index in indices for item in target_materials[index]})
        component_covered, component_consumed, component_unmatched = solve_component(component_targets, component_materials)
        covered += component_covered
        consumed += component_consumed
        unmatched.update(component_unmatched)
        component_target_counts.append(len(indices))
    return {'authority_quantity': sum(expected.values()), 'covered_authority_quantity': covered, 'actual_quantity': sum(remaining.values()), 'consumed_actual_quantity': consumed, 'unmatched_actual': dict(sorted(unmatched.items())), 'match_components': len(component_target_counts), 'largest_match_component_targets': max(component_target_counts, default=0)}


def _final_bom_rows(final: pd.DataFrame, *, traceability_mode: str, quantity_mode: str='signed-action') -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns = {'site': _find_column(final, 'site_name', 'site id', 'site id radio', '绔欑偣'), 'region': _find_column(final, 'region', '鍖哄煙'), 'action': _find_column(final, 'action', 'site_action'), 'item': _find_column(final, 'item_code'), 'quantity': _find_column(final, 'required_qty', 'quantity'), 'original': _find_column(final, 'original_bom')}
    missing = sorted((name for name in ('site', 'action', 'item', 'quantity') if columns[name] is None))
    if missing:
        raise ValueError(f'site_final_bom lacks material fields: {missing}')
    if traceability_mode == 'explicit-origin' and columns['original'] is None:
        raise ValueError('explicit-origin matching requires original_bom')
    if traceability_mode not in {'explicit-origin', 'aggregate-feasible'}:
        raise ValueError(f'unsupported traceability mode: {traceability_mode}')
    if quantity_mode not in {
        'signed-action',
        'dismantle-absolute',
        'absolute',
    }:
        raise ValueError(f'unsupported final-BOM quantity mode: {quantity_mode}')
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row_index, row in final.iterrows():
        site = _norm(row.get(columns['site']))
        action = _norm(row.get(columns['action'])).casefold()
        region = _norm(row.get(columns['region'])) if columns['region'] else 'ALL'
        source_row = int(row_index) + 2
        if not site or action not in {'install', 'dismantle'}:
            issues.append({'row': source_row, 'error': 'INVALID_SITE_ACTION', 'site': site, 'action': action})
            continue
        item = _bom_key(row.get(columns['item']))
        quantity_value = _number(row.get(columns['quantity']))
        row_errors: list[str] = []
        quantity = 0
        submitted_quantity_sign = 'invalid'
        if quantity_value is None or not float(quantity_value).is_integer() or int(quantity_value) == 0:
            if quantity_value is not None and float(quantity_value).is_integer():
                submitted_quantity_sign = 'zero'
            row_errors.append('INVALID_QUANTITY')
        else:
            signed_quantity = int(quantity_value)
            submitted_quantity_sign = 'positive' if signed_quantity > 0 else 'negative'
            wrong_sign = (
                action == 'install' and signed_quantity <= 0
            ) or (
                action == 'dismantle' and signed_quantity >= 0
            )
            sign_is_invalid = (
                quantity_mode == 'signed-action' and wrong_sign
            ) or (
                quantity_mode == 'dismantle-absolute'
                and action == 'install'
                and signed_quantity <= 0
            )
            if sign_is_invalid:
                row_errors.append('INVALID_QUANTITY_SIGN')
            else:
                quantity = abs(signed_quantity)
        if not item:
            row_errors.append('EMPTY_ITEM_CODE')
        rows.append({'row': source_row, 'action_key': f'{_key(region)}|{_key(site)}|{action}', 'item': item, 'quantity': quantity, 'submitted_quantity_sign': submitted_quantity_sign, 'original': _bom_key(row.get(columns['original'])) if columns['original'] else '', 'errors': tuple(sorted(set(row_errors)))})
    return (rows, issues)


def _match_final_bom(authority: Mapping[str, Mapping[str, int]], final: pd.DataFrame, alternatives: Mapping[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]], *, traceability_mode: str, region_scope: str, final_bom_quantity_mode: str='signed-action', action_scope: frozenset[str] | None=None) -> dict[str, Any]:
    """Match final BOM once; S1 reads precision units and S5 reads recall quantities."""
    final_rows, unassigned_issues = _final_bom_rows(final, traceability_mode=traceability_mode, quantity_mode=final_bom_quantity_mode)
    parsed_final_rows = len(final_rows)
    submitted_sign_counts = {
        action: {
            sign: sum(
                1
                for row in final_rows
                if row['action_key'].rsplit('|', 1)[-1] == action
                and row['submitted_quantity_sign'] == sign
            )
            for sign in ('positive', 'negative', 'zero', 'invalid')
        }
        for action in ('install', 'dismantle')
    }
    accepted_signs = {
        'signed-action': {
            'install': ['positive'],
            'dismantle': ['negative'],
        },
        'dismantle-absolute': {
            'install': ['positive'],
            'dismantle': ['positive', 'negative'],
        },
        'absolute': {
            'install': ['positive', 'negative'],
            'dismantle': ['positive', 'negative'],
        },
    }[final_bom_quantity_mode]
    if action_scope is not None:
        invalid_actions = set(action_scope) - _SUPPORTED_ACTIONS
        if not action_scope or invalid_actions:
            raise ValueError(f'unsupported final-BOM action scope: {sorted(action_scope)}')
        final_rows = [row for row in final_rows if row['action_key'].rsplit('|', 1)[-1] in action_scope]
    final_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in final_rows:
        final_groups[row['action_key']].append(row)
    action_keys = set(authority) | set(final_groups)
    if action_scope is not None:
        action_keys = {action_key for action_key in action_keys if action_key.rsplit('|', 1)[-1] in action_scope}
    relation_actual_codes = set(alternatives)
    for options in alternatives.values():
        relation_actual_codes.update((item for _, bundle in options for item, _ in bundle))
    match_cache: dict[tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]], dict[str, Any]] = {}
    match_queries = 0

    def material_match(expected: Mapping[str, int], actual: Mapping[str, int]) -> dict[str, Any]:
        nonlocal match_queries
        match_queries += 1
        signature = (tuple(sorted(((item, abs(int(quantity))) for item, quantity in expected.items() if int(quantity) != 0))), tuple(sorted(((item, abs(int(quantity))) for item, quantity in actual.items() if int(quantity) != 0))))
        if signature not in match_cache:
            match_cache[signature] = _maximum_material_match(dict(signature[0]), dict(signature[1]), alternatives)
        return match_cache[signature]
    action_results: dict[str, dict[str, Any]] = {}
    candidate_units = 0
    valid_candidate_units = 0
    failures: list[dict[str, Any]] = []
    for action_key in sorted(action_keys):
        authority_materials = _authority_action(authority, action_key, region_scope=region_scope) or {}
        authority_materials = {item: abs(int(quantity)) for item, quantity in authority_materials.items() if int(quantity) != 0}
        rows = final_groups.get(action_key, [])
        action_covered = 0
        action_units = 0
        action_valid_units = 0
        if traceability_mode == 'explicit-origin':
            by_original: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                by_original[row['original']].append(row)
            originals = set(authority_materials) | set(by_original)
            for original in sorted(originals):
                original_rows = by_original.get(original, [])
                actual: dict[str, int] = defaultdict(int)
                for row in original_rows:
                    if not row['errors'] and row['item'] and row['quantity']:
                        actual[row['item']] += int(row['quantity'])
                match = material_match({original: authority_materials.get(original, 0)}, actual) if original else {'covered_authority_quantity': 0, 'unmatched_actual': dict(actual)}
                action_covered += int(match['covered_authority_quantity'])
                changed = any((row['item'] != original for row in original_rows))
                relevant = bool(original_rows) and (original in alternatives or changed or (not original))
                if not relevant:
                    continue
                action_units += 1
                row_errors = sorted({error for row in original_rows for error in row['errors']})
                unmatched = dict(match['unmatched_actual'])
                valid = not row_errors and (not unmatched)
                action_valid_units += int(valid)
                if not valid and len(failures) < 50:
                    failures.append({'unit': f"{action_key}|{original or '<missing-original>'}", 'errors': row_errors + (['UNMATCHED_ACTUAL_MATERIAL'] if unmatched else []), 'unmatched_actual': unmatched, 'rows': [row['row'] for row in original_rows]})
        else:
            actual: dict[str, int] = defaultdict(int)
            for row in rows:
                if not row['errors'] and row['item'] and row['quantity']:
                    actual[row['item']] += int(row['quantity'])
            match = material_match(authority_materials, actual)
            action_covered = int(match['covered_authority_quantity'])
            has_target_demand = any((item in alternatives for item in authority_materials))
            relevant = bool(rows) and (has_target_demand or any((row['item'] in relation_actual_codes for row in rows)))
            if relevant:
                action_units = 1
                row_errors = sorted({error for row in rows for error in row['errors']})
                unmatched = dict(match['unmatched_actual'])
                valid = not row_errors and (not unmatched)
                action_valid_units = int(valid)
                if not valid and len(failures) < 50:
                    failures.append({'unit': action_key, 'errors': row_errors + (['UNMATCHED_ACTUAL_MATERIAL'] if unmatched else []), 'unmatched_actual': unmatched, 'rows': [row['row'] for row in rows]})
        candidate_units += action_units
        valid_candidate_units += action_valid_units
        action_results[action_key] = {'authority_quantity': sum(authority_materials.values()), 'covered_authority_quantity': action_covered, 'final_row_count': len(rows), 'candidate_units': action_units, 'valid_candidate_units': action_valid_units}
    return {'final_bom_quantity_mode': final_bom_quantity_mode, 'final_bom_submitted_sign_counts': submitted_sign_counts, 'final_bom_normalization': {'direction': 'action', 'magnitude': 'abs(required_qty)', 'install': '+abs(required_qty)', 'dismantle': '-abs(required_qty)', 'accepted_submitted_signs': accepted_signs}, 'action_scope': sorted(action_scope or _SUPPORTED_ACTIONS), 'parsed_final_rows': parsed_final_rows, 'out_of_scope_final_rows': parsed_final_rows - len(final_rows), 'final_rows': len(final_rows), 'invalid_final_rows': sum((bool(row['errors']) for row in final_rows)), 'final_actions': len(final_groups), 'candidate_units': candidate_units, 'valid_candidate_units': valid_candidate_units, 'invalid_candidate_units': candidate_units - valid_candidate_units, 'unit_failures': failures, 'unassigned_row_issues': unassigned_issues[:50], 'material_match_queries': match_queries, 'material_match_unique_queries': len(match_cache), 'actions': action_results}
