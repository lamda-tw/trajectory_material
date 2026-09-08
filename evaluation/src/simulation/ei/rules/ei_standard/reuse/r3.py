"""R3 final installed-material code validity."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import failed_leaf, leaf, not_applicable_leaf, quantity_error, table
from ..common import (
    _bom_key,
    _find_column,
    _key,
    _norm,
    _number,
    _scope_material_facts,
    _substitution_roles,
)
from ..scheduling import _candidate_plan


def _evaluate_r3(context: RuleContext) -> tuple[float, dict[str, Any], str]:
    final = table(context, "final_material")
    source = table(context, "substitution_source")
    plan = table(context, "site_plan")
    scope = table(context, "scope_input")
    if final is None:
        return 0.0, {"error": "site_final_bom is missing or structurally unusable"}, "CANDIDATE_ARTIFACT_MISSING"
    if source is None:
        raise FileNotFoundError("configured substitution source is missing or invalid")
    if plan is None:
        spec = context.question.artifacts.get("site_plan")
        if spec is not None and spec.source == "question":
            raise FileNotFoundError("configured question site plan is missing or invalid")
        return 0.0, {"error": "site_plan is missing or structurally unusable"}, "CANDIDATE_ARTIFACT_MISSING"
    mode = str(context.component.parameters["r3_validation_mode"])
    substitution_mode = str(
        context.component.parameters.get("r3_substitution_mode", "legacy-combination")
    )
    roles = _substitution_roles(source, mode=substitution_mode)
    target_codes = set(roles)
    allowed_codes = set().union(*roles.values()) if roles else set()
    site_col = _find_column(final, "site_name", "site id", "site id radio", "站点")
    region_col = _find_column(final, "region", "区域")
    action_col = _find_column(final, "action", "site_action")
    item_col = _find_column(final, "item_code")
    quantity_col = _find_column(final, "required_qty", "quantity")
    original_col = _find_column(final, "original_bom")
    if None in {site_col, action_col, item_col, quantity_col}:
        return 0.0, {"error": "site_final_bom lacks required R3 fields"}, "CANDIDATE_ARTIFACT_INVALID"
    install_rows = []
    for row_index, row in final.iterrows():
        quantity = _number(row.get(quantity_col))
        if (
            _norm(row.get(action_col)).casefold() != "install"
            or quantity is None
            or quantity <= 0
        ):
            continue
        install_rows.append(
            {
                "row": int(row_index) + 2,
                "raw_site": _norm(row.get(site_col)),
                "site": _key(row.get(site_col)),
                "region": _key(row.get(region_col)) if region_col else "all",
                "raw_item": _norm(row.get(item_col)),
                "item": _bom_key(row.get(item_col)),
                "original": _bom_key(row.get(original_col)) if original_col else "",
            }
        )
    if scope is None:
        raise FileNotFoundError("R3 requires configured scope_input authority")
    authority = _scope_material_facts(scope)
    candidate_plan = _candidate_plan(plan)
    planned_actions = {
        str(value)
        for value in candidate_plan.loc[
            candidate_plan["action"] == "install",
            "action_key",
        ]
    }
    applicable_action_materials = {
        action_key: {
            original: int(quantity)
            for original, quantity in materials.items()
            if original in target_codes and int(quantity) > 0
        }
        for action_key, materials in authority.items()
        if action_key.endswith("|install") and action_key in planned_actions
    }
    applicable_action_materials = {
        action_key: materials
        for action_key, materials in applicable_action_materials.items()
        if materials
    }
    for row in install_rows:
        row["action_key"] = f"{row['region']}|{row['site']}|install"
    failures: list[dict[str, Any]] = []
    legal = 0
    if mode == "CONTEXTUAL":
        if original_col is None:
            return 0.0, {"error": "CONTEXTUAL mode requires original_bom"}, "CANDIDATE_ARTIFACT_INVALID"
        applicable_units = {
            (action_key, original)
            for action_key, materials in applicable_action_materials.items()
            for original in materials
        }
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in install_rows:
            unit = (row["action_key"], row["original"])
            if unit in applicable_units:
                grouped[unit].append(row)
        for action_key, original in sorted(applicable_units):
            rows = grouped.get((action_key, original), [])
            business_keys = [
                (action_key, value["original"], value["item"]) for value in rows
            ]
            duplicate = len(business_keys) != len(set(business_keys))
            invalid_items = sorted(
                {
                    value["item"]
                    for value in rows
                    if not value["item"]
                    or value["item"] == original
                    or value["item"] not in roles[original]
                }
            )
            passed = bool(rows) and not duplicate and not invalid_items
            legal += int(passed)
            if not passed:
                failures.append(
                    {
                        "action_key": action_key,
                        "original_bom": original,
                        "missing_final_rows": not rows,
                        "duplicate_business_key": duplicate,
                        "invalid_items": invalid_items,
                        "source_rows": [int(value["row"]) for value in rows],
                        "raw_rows": [
                            {
                                "row": int(value["row"]),
                                "site": value["raw_site"],
                                "item": value["raw_item"],
                            }
                            for value in rows
                        ],
                    }
                )
        applicable = len(applicable_units)
        evidence = {
            "validation_mode": "CONTEXTUAL",
            "denominator_source": "scope_input + scheduled install actions",
            "applicable_units": applicable,
            "applicable_unit_keys": [
                {"action_key": action_key, "original_bom": original}
                for action_key, original in sorted(applicable_units)
            ],
            "legal_units": legal,
            "failures": failures,
        }
    elif mode == "LEGACY_RESIDUAL_ONLY":
        overlap = target_codes & allowed_codes
        if overlap:
            raise ValueError(
                "legacy residual-only contract is invalid because target and actual roles overlap"
            )
        by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in install_rows:
            if row["action_key"] in applicable_action_materials:
                by_action[row["action_key"]].append(row)
        for action_key in sorted(applicable_action_materials):
            rows = by_action.get(action_key, [])
            residuals = sorted(
                {value["item"] for value in rows if value["item"] in target_codes}
            )
            passed = bool(rows) and not residuals
            legal += int(passed)
            if not passed:
                failures.append(
                    {
                        "action_key": action_key,
                        "missing_positive_final_rows": not rows,
                        "residual_targets": residuals,
                        "source_rows": [int(value["row"]) for value in rows],
                        "raw_rows": [
                            {
                                "row": int(value["row"]),
                                "site": value["raw_site"],
                                "item": value["raw_item"],
                            }
                            for value in rows
                        ],
                    }
                )
        applicable = len(applicable_action_materials)
        evidence = {
            "validation_mode": "LEGACY_RESIDUAL_ONLY",
            "denominator_source": "scope_input virtual targets + scheduled install actions",
            "validated_semantics": "virtual_target_residual",
            "not_validated": ["target_specific_actual_membership"],
            "applicable_units": applicable,
            "applicable_action_keys": sorted(applicable_action_materials),
            "legal_units": legal,
            "failures": failures,
        }
    else:
        raise ValueError(f"unsupported R3 validation mode: {mode}")
    if not applicable:
        evidence["not_applicable_reason"] = (
            "no scheduled install action has Prompt-authorized virtual target demand"
        )
        return 0.0, evidence, "NOT_APPLICABLE"
    reason = "" if legal == applicable else "INVALID_FINAL_MATERIAL_CODE"
    return legal / applicable, evidence, reason


def score_r3(context: RuleContext) -> CheckResult:
    integer_error = quantity_error(context, "final_material")
    if integer_error:
        return failed_leaf(
            context,
            "R3",
            "Material code validity",
            "NON_INTEGER_QUANTITY",
            "Final material quantities must be integers",
            integer_error,
        )
    try:
        rate, evidence, reason_code = _evaluate_r3(context)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("R3 authority evidence cannot be evaluated") from exc
    if reason_code == "NOT_APPLICABLE":
        return not_applicable_leaf(
            context,
            "R3",
            "Material code validity",
            "No scheduled install action has Prompt-authorized virtual target demand",
            evidence,
        )
    return leaf(
        context,
        "R3",
        "Material code validity",
        rate,
        "Final installed material codes must be legal in their Prompt-authorized substitution context",
        evidence,
        reason_code=reason_code,
    )
