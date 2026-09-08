"""S1 replacement-chain and final-BOM application scoring."""

from __future__ import annotations

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import (
    failed_leaf,
    leaf,
    table,
    validation_issues,
)
from ..common import (
    _compile_candidate_substitution,
    _scope_material_facts,
    _substitution_alternatives,
    _substitution_relation_objects,
)
from .material import _match_final_bom


_S1_ACTION_SCOPE = frozenset({'install'})


def score_s1(context: RuleContext) -> CheckResult:
    parameters = context.component.parameters
    source_table = table(context, 'substitution_source')
    candidate_required = bool(parameters.get('s1_candidate_substitution_required', True))
    candidate = table(context, 'material_substitution') if candidate_required else source_table
    scope = table(context, 'scope_input')
    final = table(context, 'final_material')
    if candidate is None:
        return failed_leaf(context, 'S1', 'BOM replacement-chain accuracy', 'MISSING_ARTIFACT', 'The required material_substitution evidence is missing or unusable')
    elif final is None:
        return failed_leaf(context, 'S1', 'BOM replacement-chain accuracy', 'MISSING_FINAL_MATERIAL', 'site_final_bom is missing or unusable')
    elif source_table is None:
        raise FileNotFoundError('configured substitution source is missing')
    elif scope is None:
        raise FileNotFoundError('configured scope input is missing')
    else:
        mode = str(parameters['s1_substitution_mode'])
        try:
            source_schema_issues = validation_issues(context, 'substitution_source')
            if source_schema_issues:
                raise ValueError('configured substitution source violates its Prompt schema')
            expected_relations = _substitution_relation_objects(
                source_table,
                mode=mode,
                fallback_requires_new_prefix=True,
            ) if candidate_required else set()
            scope_material_mode = str(parameters.get('s1_scope_material_mode', 'raw'))
            authority = _scope_material_facts(scope, material_mode=scope_material_mode)
        except Exception as exc:
            raise RuntimeError('S1 authority evidence cannot be compiled') from exc
        try:
            if candidate_required:
                candidate_compilation = _compile_candidate_substitution(candidate, mode=mode)
                candidate_relations = set(candidate_compilation['relations'])
                candidate_alternatives = dict(candidate_compilation['alternatives'])
                candidate_relation_issues = list(candidate_compilation['issues'])
            else:
                candidate_relations = set()
                candidate_alternatives = _substitution_alternatives(
                    candidate,
                    mode=mode,
                    fallback_requires_new_prefix=True,
                )
                candidate_relation_issues = []
            if candidate_required:
                relation_intersection = expected_relations & candidate_relations
                relation_union = expected_relations | candidate_relations
                model_fidelity = len(relation_intersection) / len(relation_union) if relation_union else 1.0
            else:
                relation_intersection = set()
                relation_union = set()
                model_fidelity = 1.0
            traceability_mode = str(parameters['s1_traceability_mode'])
            region_scope = str(parameters.get('s1_region_scope', 'exact'))
            final_bom_quantity_mode = str(parameters.get('final_bom_quantity_mode', 'signed-action'))
            matched = _match_final_bom(authority, final, candidate_alternatives, traceability_mode=traceability_mode, region_scope=region_scope, final_bom_quantity_mode=final_bom_quantity_mode, action_scope=_S1_ACTION_SCOPE)
            candidate_units = int(matched['candidate_units'])
            application_precision = int(matched['valid_candidate_units']) / candidate_units if candidate_units else 1.0 if int(matched['final_rows']) > 0 else 0.0
            rate = model_fidelity * application_precision
            evidence = {key: value for key, value in matched.items() if key != 'actions'}
            evidence.update({'formula': 'F_model * P_apply', 'model_fidelity': model_fidelity, 'application_precision': application_precision, 'final_rate': rate, 'candidate_substitution_required': candidate_required, 'source_fallback_policy': 'new-prefix-only', 'identity_relation_policy': 'preserve-explicit-identity-alternatives', 'filtered_expected_identity_relations': 0, 'filtered_candidate_identity_relations': 0, 'filtered_candidate_identity_alternatives': 0, 'expected_relation_objects': len(expected_relations), 'candidate_relation_objects': len(candidate_relations), 'intersection_relation_objects': len(relation_intersection), 'union_relation_objects': len(relation_union), 'invalid_relation_views': len(candidate_relation_issues), 'invalid_relation_view_examples': candidate_relation_issues[:20], 'missing_relation_objects': [list(value) for value in sorted(expected_relations - candidate_relations)[:20]], 'extra_relation_objects': [list(value) for value in sorted(candidate_relations - expected_relations)[:20]], 'candidate_schema_issues': validation_issues(context, 'material_substitution') or {} if candidate_required else {}})
            return leaf(context, 'S1', 'BOM replacement-chain accuracy', rate, 'Relationship-model Jaccard is multiplied by final-BOM application precision', evidence, reason_code='' if rate >= 0.999999 else 'MODEL_OR_APPLICATION_MISMATCH')
        except Exception as exc:
            return failed_leaf(context, 'S1', 'BOM replacement-chain accuracy', 'INVALID_ARTIFACT', 'Replacement-chain evidence cannot be parsed', {'error': str(exc)})
