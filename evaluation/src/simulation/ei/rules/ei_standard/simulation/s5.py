"""S5 original-BOM demand recall scoring."""

from __future__ import annotations

from typing import Any

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import (
    failed_leaf,
    leaf,
    not_applicable_leaf,
    table,
)
from ..common import (
    _compile_candidate_substitution,
    _scope_material_facts,
    _substitution_alternatives,
)
from .material import _match_final_bom
from .time import _scheduled_plan


def score_s5(
    context: RuleContext,
    *,
    scheduled_plan: pd.DataFrame | None = None,
) -> CheckResult:
    parameters = context.component.parameters
    scope = table(context, 'scope_input')
    final = table(context, 'final_material')
    plan_frame = table(context, 'site_plan')
    if final is None:
        return failed_leaf(context, 'S5', 'Original-BOM demand recall', 'MISSING_FINAL_MATERIAL', 'site_final_bom is missing or unusable')
    elif plan_frame is None:
        return failed_leaf(context, 'S5', 'Original-BOM demand recall', 'MISSING_SITE_PLAN', 'site_plan is missing or unusable')
    elif scope is None:
        raise FileNotFoundError('configured scope input is missing')
    else:
        relation_error = ''
        relation_issues: list[dict[str, Any]] = []
        alternatives = {}
        mode = parameters.get('s1_substitution_mode')
        relation_table = None
        if mode:
            candidate_required = bool(parameters.get('s1_candidate_substitution_required', True))
            relation_table = table(context, 'material_substitution') if candidate_required else table(context, 'substitution_source')
            if relation_table is None:
                relation_error = 'material_substitution is missing or unusable'
            else:
                try:
                    relation_mode = str(mode)
                    relation_key = (id(relation_table), relation_mode)
                    if candidate_required:
                        candidate_compilation = _compile_candidate_substitution(relation_table, mode=relation_mode)
                        alternatives = dict(candidate_compilation['alternatives'])
                        relation_issues = list(candidate_compilation['issues'])
                    else:
                        alternatives = _substitution_alternatives(relation_table, mode=relation_mode)
                except Exception as exc:
                    relation_error = str(exc)
        try:
            traceability_mode = str(parameters.get('s1_traceability_mode', 'aggregate-feasible'))
            region_scope = str(parameters.get('s1_region_scope', 'exact'))
            scope_material_mode = str(parameters.get('s5_scope_material_mode', parameters.get('s1_scope_material_mode', 'raw')))
            final_bom_quantity_mode = str(parameters.get('final_bom_quantity_mode', 'signed-action'))
            match_key = (id(scope), id(final), id(relation_table), str(mode or ''), traceability_mode, region_scope, scope_material_mode, final_bom_quantity_mode)
            try:
                authority = _scope_material_facts(scope, material_mode=scope_material_mode)
            except Exception as exc:
                raise RuntimeError('S5 authority evidence cannot be compiled') from exc
            matched = _match_final_bom(authority, final, alternatives, traceability_mode=traceability_mode, region_scope=region_scope, final_bom_quantity_mode=final_bom_quantity_mode)
            scheduled = (
                scheduled_plan
                if scheduled_plan is not None
                else _scheduled_plan(plan_frame, project_week_source=str(parameters.get('project_week_source', 'reconcile')))
            )
            scheduled_actions = set(scheduled['action_key'])
            action_results = matched['actions']
            scope_authority_actions = {action_key for action_key, result in action_results.items() if int(result.get('authority_quantity', 0)) > 0}
            scope_authority_quantity = sum((int(result.get('authority_quantity', 0)) for result in action_results.values()))
            scheduled_authority_actions = scheduled_actions & scope_authority_actions
            scheduled_actions_without_authority = scheduled_actions - scope_authority_actions
            denominator = sum((int(action_results.get(action_key, {}).get('authority_quantity', 0)) for action_key in scheduled_actions))
            numerator = sum((int(action_results.get(action_key, {}).get('covered_authority_quantity', 0)) for action_key in scheduled_actions))
            evidence = {'unit': 'original_bom_quantity_in_scheduled_site_action', 'scheduled_actions': len(scheduled_actions), 'authority_quantity': denominator, 'covered_authority_quantity': numerator, 'authoritative_quantity': denominator, 'covered_quantity': numerator, 'recall_rate': numerator / denominator if denominator else 0.0, 'scope_authority_actions': len(scope_authority_actions), 'scope_authority_quantity': scope_authority_quantity, 'scheduled_authority_actions': len(scheduled_authority_actions), 'scheduled_actions_without_authority': len(scheduled_actions_without_authority), 'scheduled_actions_without_authority_examples': sorted(scheduled_actions_without_authority)[:20], 'missing_final_actions': sum((1 for action_key in scheduled_actions if int(action_results.get(action_key, {}).get('final_row_count', 0)) == 0)), 'relation_parse_error': relation_error, 'invalid_relation_views': len(relation_issues), 'invalid_relation_view_examples': relation_issues[:20], 'identity_relation_policy': 'preserve-explicit-identity-alternatives', 'filtered_candidate_identity_alternatives': 0, 'traceability_mode': str(parameters.get('s1_traceability_mode', 'aggregate-feasible')), 'scope_material_mode': scope_material_mode, 'final_bom_quantity_mode': final_bom_quantity_mode, 'final_bom_submitted_sign_counts': matched.get('final_bom_submitted_sign_counts', {}), 'final_bom_normalization': matched.get('final_bom_normalization', {}), 'action_scope': matched.get('action_scope', []), 'out_of_scope_final_rows': int(matched.get('out_of_scope_final_rows', 0)), 'invalid_final_rows': int(matched.get('invalid_final_rows', 0))}
            if scope_authority_quantity <= 0:
                return not_applicable_leaf(context, 'S5', 'Original-BOM demand recall', 'The authoritative scope contains no material demand', evidence)
            elif denominator <= 0:
                return leaf(context, 'S5', 'Original-BOM demand recall', 0.0, 'Candidate scheduled actions do not overlap authoritative material demand', evidence, reason_code='NO_SCHEDULED_AUTHORITY_OVERLAP')
            else:
                return leaf(context, 'S5', 'Original-BOM demand recall', numerator / denominator, 'Covered original-BOM equivalent quantity divided by scheduled authoritative demand', evidence, reason_code='' if numerator == denominator else 'ORIGINAL_BOM_RECALL_GAP')
        except Exception as exc:
            return failed_leaf(context, 'S5', 'Original-BOM demand recall', 'INVALID_ARTIFACT', 'Final-BOM recall evidence cannot be parsed', {'error': str(exc), 'relation_parse_error': relation_error})
