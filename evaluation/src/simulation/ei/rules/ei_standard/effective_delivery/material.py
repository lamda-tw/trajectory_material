"""Strict final-BOM result evidence used only by O2."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import re
from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.adapters import parse_iso_week

from ..common import (
    _bom_key,
    _month_number,
    _norm,
    _number,
)
from .parsing import (
    _schedule_label_identity,
    action_key,
    action_key_parts,
    integer_project_week,
    site_identity,
)


@lru_cache(maxsize=None)
def _action_month_label(label: str) -> int | None:
    parsed = _month_number(label)
    if parsed is not None:
        return parsed
    match = re.fullmatch(
        r"(?:(?:20\d{2})\s*年?\s*)?(\d{1,2})\s*月",
        label,
    )
    if not match:
        return None
    month = int(match.group(1))
    return month if 1 <= month <= 12 else None


def _action_month_number(value: Any) -> int | None:
    """Parse the month semantics without imposing an unstated display format."""

    return _action_month_label(_norm(value))


def _authority_action(
    authority: Mapping[str, Mapping[str, int]],
    key: str,
    *,
    region_scope: str,
) -> Mapping[str, int] | None:
    direct = authority.get(key)
    if direct is not None:
        return direct
    if region_scope == "exact":
        return None
    if region_scope != "regionless":
        raise ValueError(f"unsupported O2 region scope: {region_scope}")
    _, site, action = action_key_parts(key)
    matches = [
        value
        for action_key, value in authority.items()
        if action_key_parts(action_key)[1:] == (site, action)
    ]
    return matches[0] if len(matches) == 1 else None


def _maximum_material_match(
    authority: Mapping[str, int],
    actual: Mapping[str, int],
    alternatives: Mapping[
        str,
        tuple[tuple[int, tuple[tuple[str, int], ...]], ...],
    ],
) -> dict[str, Any]:
    """Maximize covered original quantity, then consumed delivered quantity."""

    expected = {
        item: abs(int(quantity))
        for item, quantity in authority.items()
        if int(quantity) != 0
    }
    remaining = {
        item: abs(int(quantity))
        for item, quantity in actual.items()
        if int(quantity) != 0
    }
    targets: list[
        tuple[
            str,
            int,
            tuple[tuple[int, tuple[tuple[str, int], ...]], ...],
        ]
    ] = []
    for item, demand in expected.items():
        # Identity permission is part of the authoritative adapter contract;
        # a missing target is not silently treated as "keep the original".
        options = alternatives.get(item, ())
        targets.append((item, demand, tuple(options)))
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
        materials = {
            item
            for _, bundle in options
            for item, _ in bundle
        }
        target_materials.append(materials)
        for item in materials:
            owner = material_owner.setdefault(item, target_index)
            union(target_index, owner)

    component_indices: dict[int, list[int]] = defaultdict(list)
    for target_index in range(len(targets)):
        component_indices[find(target_index)].append(target_index)

    def solve_component(
        component_targets: list[
            tuple[
                str,
                int,
                tuple[tuple[int, tuple[tuple[str, int], ...]], ...],
            ]
        ],
        material_keys: list[str],
    ) -> tuple[int, int, dict[str, int]]:
        positions = {
            item: index
            for index, item in enumerate(material_keys)
        }
        initial = tuple(remaining.get(item, 0) for item in material_keys)

        def better(
            left: tuple[int, int, tuple[int, ...]],
            right: tuple[int, int, tuple[int, ...]],
        ) -> tuple[int, int, tuple[int, ...]]:
            left_key = (left[0], left[1], tuple(-value for value in left[2]))
            right_key = (right[0], right[1], tuple(-value for value in right[2]))
            return left if left_key >= right_key else right

        @lru_cache(maxsize=None)
        def solve(
            target_index: int,
            consumed_target: int,
            state: tuple[int, ...],
        ) -> tuple[int, int, tuple[int, ...]]:
            if target_index >= len(component_targets):
                return (0, 0, state)
            _, demand, options = component_targets[target_index]
            best = solve(target_index + 1, 0, state)
            for target_quantity, bundle in options:
                if (
                    target_quantity <= 0
                    or consumed_target + target_quantity > demand
                ):
                    continue
                updated = list(state)
                physical_quantity = 0
                for item, quantity in bundle:
                    position = positions[item]
                    if quantity <= 0 or updated[position] < quantity:
                        break
                    updated[position] -= quantity
                    physical_quantity += quantity
                else:
                    child = solve(
                        target_index,
                        consumed_target + target_quantity,
                        tuple(updated),
                    )
                    candidate = (
                        target_quantity + child[0],
                        physical_quantity + child[1],
                        child[2],
                    )
                    best = better(best, candidate)
            return best

        covered, consumed, final_state = solve(0, 0, initial)
        return (
            covered,
            consumed,
            {
                item: final_state[position]
                for item, position in positions.items()
                if final_state[position] > 0
            },
        )

    covered = 0
    consumed = 0
    unmatched: dict[str, int] = {
        item: quantity
        for item, quantity in remaining.items()
        if item not in material_owner and quantity > 0
    }
    component_target_counts: list[int] = []
    for indices in sorted(
        component_indices.values(),
        key=min,
    ):
        component_targets = [targets[index] for index in indices]
        component_materials = sorted(
            {
                item
                for index in indices
                for item in target_materials[index]
            }
        )
        component_covered, component_consumed, component_unmatched = (
            solve_component(component_targets, component_materials)
        )
        covered += component_covered
        consumed += component_consumed
        unmatched.update(component_unmatched)
        component_target_counts.append(len(indices))
    return {
        "authority_quantity": sum(expected.values()),
        "covered_authority_quantity": covered,
        "actual_quantity": sum(remaining.values()),
        "consumed_actual_quantity": consumed,
        "unmatched_actual": dict(sorted(unmatched.items())),
        "match_components": len(component_target_counts),
        "largest_match_component_targets": max(
            component_target_counts,
            default=0,
        ),
    }


def _final_bom_rows(
    final: pd.DataFrame,
    *,
    traceability_mode: str,
    quantity_mode: str = "signed-action",
    action_time_columns: bool = False,
    week_identity_mode: str = "schedule-week",
    planning_year: int | None = None,
    material_source_contract: Mapping[str, tuple[str, ...]] | None = None,
    material_source_missing_effect: str = "blocking",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    required = {
        "source_row",
        "site_id",
        "region",
        "action",
        "item_code",
        "quantity",
        "project_week",
    }
    if action_time_columns:
        required.update(("install_month", "dismantle_month"))
    if traceability_mode == "explicit-origin":
        required.add("original_item_code")
    missing = sorted(required - set(final.columns))
    if missing:
        raise ValueError(f"normalized final_material lacks O2 fields: {missing}")
    if traceability_mode not in {"explicit-origin", "aggregate-feasible"}:
        raise ValueError(f"unsupported traceability mode: {traceability_mode}")
    if quantity_mode not in {
        "signed-action",
        "dismantle-absolute",
        "absolute",
    }:
        raise ValueError(f"unsupported final-BOM quantity mode: {quantity_mode}")
    if week_identity_mode not in {
        "schedule-week",
        "calendar-week",
        "calendar-or-week-number",
        "hybrid-week",
    }:
        raise ValueError(f"unsupported final-BOM week identity: {week_identity_mode}")
    if (
        week_identity_mode == "schedule-week"
        and (
            not isinstance(planning_year, int)
            or isinstance(planning_year, bool)
        )
    ):
        raise ValueError("schedule-week final BOM requires integer planning_year")
    source_contract = {
        str(action): {
            _norm(value).casefold()
            for value in allowed
            if _norm(value)
        }
        for action, allowed in (material_source_contract or {}).items()
    }
    if any(
        action not in {"install", "dismantle"} or not allowed
        for action, allowed in source_contract.items()
    ):
        raise ValueError("invalid O2 material-source contract")
    if material_source_missing_effect not in {"blocking", "diagnostic"}:
        raise ValueError("invalid O2 material-source missing effect")

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row_index, row in final.iterrows():
        site = _norm(row.get("site_id"))
        action = _norm(row.get("action")).casefold()
        region = _norm(row.get("region")) or "ALL"
        material_source = _norm(row.get("material_source"))
        try:
            source_row = int(row.get("source_row"))
        except (TypeError, ValueError):
            source_row = int(row_index) + 2
        if not site or action not in {"install", "dismantle"}:
            issues.append(
                {
                    "row": source_row,
                    "error": "INVALID_SITE_ACTION",
                    "site": site,
                    "action": action,
                }
            )
            continue
        item = _bom_key(row.get("item_code"))
        quantity_value = _number(row.get("quantity"))
        row_errors: list[str] = []
        project_week: int | None = None
        calendar_week: int | None = None
        action_month: int | None = None
        quantity = 0
        submitted_quantity_sign = "invalid"
        if (
            quantity_value is None
            or not float(quantity_value).is_integer()
            or int(quantity_value) == 0
        ):
            if quantity_value is not None and float(quantity_value).is_integer():
                submitted_quantity_sign = "zero"
            row_errors.append("INVALID_QUANTITY")
        else:
            signed_quantity = int(quantity_value)
            submitted_quantity_sign = (
                "positive" if signed_quantity > 0 else "negative"
            )
            wrong_sign = (
                action == "install" and signed_quantity <= 0
            ) or (
                action == "dismantle" and signed_quantity >= 0
            )
            sign_is_invalid = (
                quantity_mode == "signed-action" and wrong_sign
            ) or (
                quantity_mode == "dismantle-absolute"
                and action == "install"
                and signed_quantity <= 0
            )
            if sign_is_invalid:
                row_errors.append("INVALID_QUANTITY_SIGN")
            else:
                quantity = abs(signed_quantity)
        if not item:
            row_errors.append("EMPTY_ITEM_CODE")
        material_source_scoped = action in source_contract
        missing_material_source = material_source_scoped and not material_source
        invalid_material_source = (
            material_source_scoped
            and bool(material_source)
            and material_source.casefold() not in source_contract[action]
        )
        if (
            missing_material_source
            and material_source_missing_effect == "blocking"
        ):
            row_errors.append("MISSING_MATERIAL_SOURCE")
        if invalid_material_source:
            row_errors.append("INVALID_MATERIAL_SOURCE")
        if week_identity_mode == "calendar-week":
            try:
                calendar_week = parse_iso_week(row.get(f"{action}_week"))
                project_week = calendar_week % 100
            except (TypeError, ValueError):
                row_errors.append("INVALID_CALENDAR_WEEK")
        else:
            try:
                parsed_week = integer_project_week(row.get("project_week"))
                maximum_week = (
                    53
                    if week_identity_mode == "calendar-or-week-number"
                    else 52
                )
                if not 1 <= parsed_week <= maximum_week:
                    raise ValueError(
                        f"project_week is outside 1..{maximum_week}"
                    )
                project_week = parsed_week
            except ValueError:
                row_errors.append("INVALID_PROJECT_WEEK")
            if week_identity_mode == "schedule-week":
                action_week = row.get(f"{action}_week")
                if _norm(action_week):
                    try:
                        label_week, calendar_week = _schedule_label_identity(
                            action_week,
                            planning_year=int(planning_year),
                        )
                    except ValueError:
                        row_errors.append("INVALID_CALENDAR_WEEK")
                    else:
                        if calendar_week // 100 != int(planning_year):
                            row_errors.append("WEEK_YEAR_MISMATCH")
                        if project_week is None or label_week != project_week:
                            row_errors.append("FINAL_BOM_WEEK_MISMATCH")
            if week_identity_mode in {
                "hybrid-week",
                "calendar-or-week-number",
            }:
                # Prompt-authorized short labels such as ``WK13`` use the
                # business schedule coordinate.  When a candidate explicitly
                # supplies a year, retain the full ISO identity too so a wrong
                # year cannot be hidden by the compatible short-label path.
                action_week = row.get(f"{action}_week")
                if _norm(action_week):
                    try:
                        calendar_week = parse_iso_week(action_week)
                    except (TypeError, ValueError):
                        calendar_week = None
        if action_time_columns:
            month_value = _action_month_number(
                row.get(f"{action}_month")
            )
            if month_value is None:
                row_errors.append("INVALID_ACTION_MONTH")
            else:
                action_month = int(month_value)
        rows.append(
            {
                "row": source_row,
                "action_key": action_key(region, site, action),
                "site_identity": site_identity(site),
                "item": item,
                "quantity": quantity,
                "submitted_quantity_sign": submitted_quantity_sign,
                "material_source": material_source,
                "normalized_material_source": material_source.casefold(),
                "missing_material_source": missing_material_source,
                "invalid_material_source": invalid_material_source,
                "original": (
                    _bom_key(row.get("original_item_code"))
                    if "original_item_code" in final.columns
                    else ""
                ),
                "errors": tuple(sorted(set(row_errors))),
                "project_week": project_week,
                "calendar_week": calendar_week,
                "action_month": action_month,
            }
        )
    return rows, issues


def _strict_final_bom_actions(
    authority: Mapping[str, Mapping[str, int]],
    final: pd.DataFrame,
    alternatives: Mapping[
        str,
        tuple[tuple[int, tuple[tuple[str, int], ...]], ...],
    ],
    *,
    traceability_mode: str,
    region_scope: str,
    final_bom_quantity_mode: str = "signed-action",
    action_time_columns: bool = False,
    week_identity_mode: str = "schedule-week",
    planning_year: int | None = None,
    material_source_contract: Mapping[str, tuple[str, ...]] | None = None,
    material_source_missing_effect: str = "blocking",
) -> dict[str, Any]:
    """Return exact action-level coverage with no hidden malformed or extra rows."""

    final_rows, unassigned_issues = _final_bom_rows(
        final,
        traceability_mode=traceability_mode,
        quantity_mode=final_bom_quantity_mode,
        action_time_columns=action_time_columns,
        week_identity_mode=week_identity_mode,
        planning_year=planning_year,
        material_source_contract=material_source_contract,
        material_source_missing_effect=material_source_missing_effect,
    )
    submitted_sign_counts = {
        action: {
            sign: sum(
                1
                for row in final_rows
                if row["action_key"].rsplit("|", 1)[-1] == action
                and row["submitted_quantity_sign"] == sign
            )
            for sign in ("positive", "negative", "zero", "invalid")
        }
        for action in ("install", "dismantle")
    }
    accepted_signs = {
        "signed-action": {
            "install": ["positive"],
            "dismantle": ["negative"],
        },
        "dismantle-absolute": {
            "install": ["positive"],
            "dismantle": ["positive", "negative"],
        },
        "absolute": {
            "install": ["positive", "negative"],
            "dismantle": ["positive", "negative"],
        },
    }[final_bom_quantity_mode]
    if region_scope not in {"exact", "regionless"}:
        raise ValueError(f"unsupported final-BOM region scope: {region_scope}")

    if region_scope == "regionless":
        suffix_index: dict[tuple[str, str], list[str]] = defaultdict(list)
        for authority_key in authority:
            _, site, action = action_key_parts(authority_key)
            suffix_index[(site, action)].append(authority_key)
        canonical_rows: list[dict[str, Any]] = []
        for row in final_rows:
            value = dict(row)
            _, site, action = action_key_parts(row["action_key"])
            matches = suffix_index.get((site, action), [])
            if len(matches) == 1:
                value["action_key"] = matches[0]
            canonical_rows.append(value)
        final_rows = canonical_rows

    final_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in final_rows:
        final_groups[row["action_key"]].append(row)

    results: dict[str, dict[str, Any]] = {}
    for action_key in sorted(set(authority) | set(final_groups)):
        authority_materials = _authority_action(
            authority,
            action_key,
            region_scope=region_scope,
        ) or {}
        expected = {
            item: abs(int(quantity))
            for item, quantity in authority_materials.items()
            if int(quantity) != 0
        }
        _, _, action = action_key_parts(action_key)
        action_alternatives = (
            alternatives
            if action == "install"
            else {
                item: ((1, ((item, 1),)),)
                for item in expected
            }
        )
        rows = final_groups.get(action_key, [])
        row_errors = sorted({error for row in rows for error in row["errors"]})
        actual_quantity = 0
        covered = 0
        consumed = 0
        unmatched: dict[str, int] = defaultdict(int)

        if traceability_mode == "explicit-origin":
            by_original: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                by_original[row["original"]].append(row)
            for original in sorted(set(expected) | set(by_original)):
                actual: dict[str, int] = defaultdict(int)
                for row in by_original.get(original, []):
                    if not row["errors"] and row["item"] and row["quantity"]:
                        actual[row["item"]] += int(row["quantity"])
                actual_quantity += sum(actual.values())
                if original:
                    match = _maximum_material_match(
                        {original: expected.get(original, 0)},
                        actual,
                        action_alternatives,
                    )
                    covered += int(match["covered_authority_quantity"])
                    consumed += int(match["consumed_actual_quantity"])
                    for item, quantity in match["unmatched_actual"].items():
                        unmatched[item] += int(quantity)
                else:
                    for item, quantity in actual.items():
                        unmatched[item] += int(quantity)
        else:
            actual: dict[str, int] = defaultdict(int)
            for row in rows:
                if not row["errors"] and row["item"] and row["quantity"]:
                    actual[row["item"]] += int(row["quantity"])
            match = _maximum_material_match(
                expected,
                actual,
                action_alternatives,
            )
            actual_quantity = int(match["actual_quantity"])
            covered = int(match["covered_authority_quantity"])
            consumed = int(match["consumed_actual_quantity"])
            unmatched.update(
                {
                    item: int(quantity)
                    for item, quantity in match["unmatched_actual"].items()
                }
            )

        authority_quantity = sum(expected.values())
        reasons: list[str] = []
        if authority_quantity <= 0:
            reasons.append("NO_AUTHORITY_MATERIAL")
        if not rows:
            reasons.append("MISSING_FINAL_ACTION")
        if covered != authority_quantity:
            reasons.append("MATERIAL_COVERAGE_GAP")
        if row_errors:
            reasons.append("INVALID_FINAL_ROW")
        if "MISSING_MATERIAL_SOURCE" in row_errors:
            reasons.append("MISSING_MATERIAL_SOURCE")
        if "INVALID_MATERIAL_SOURCE" in row_errors:
            reasons.append("INVALID_MATERIAL_SOURCE")
        if unmatched or consumed != actual_quantity:
            reasons.append("EXTRA_OR_UNMATCHED_MATERIAL")
        results[action_key] = {
            "strict_material_valid": not reasons,
            "reasons": reasons,
            "authority_quantity": authority_quantity,
            "covered_authority_quantity": covered,
            "actual_quantity": actual_quantity,
            "consumed_actual_quantity": consumed,
            "unmatched_actual": dict(sorted(unmatched.items())),
            "final_row_count": len(rows),
            "invalid_row_count": sum(bool(row["errors"]) for row in rows),
            "row_errors": row_errors,
            "material_source_values": sorted(
                {
                    str(row["material_source"])
                    for row in rows
                    if str(row["material_source"])
                }
            ),
            "invalid_material_source_rows": sorted(
                int(row["row"])
                for row in rows
                if row["invalid_material_source"]
            )[:50],
            "missing_material_source_rows": sorted(
                int(row["row"])
                for row in rows
                if row["missing_material_source"]
            )[:50],
            "rows": [int(row["row"]) for row in rows[:50]],
            "project_weeks": sorted(
                {
                    int(row["project_week"])
                    for row in rows
                    if row["project_week"] is not None
                }
            ),
            "calendar_weeks": sorted(
                {
                    int(row["calendar_week"])
                    for row in rows
                    if row["calendar_week"] is not None
                }
            ),
            "action_months": sorted(
                {
                    int(row["action_month"])
                    for row in rows
                    if row["action_month"] is not None
                }
            ),
            "site_identities": sorted(
                {str(row["site_identity"]) for row in rows}
            ),
        }

    return {
        "traceability_mode": traceability_mode,
        "region_scope": region_scope,
        "final_bom_quantity_mode": final_bom_quantity_mode,
        "final_bom_submitted_sign_counts": submitted_sign_counts,
        "final_bom_normalization": {
            "direction": "action",
            "magnitude": "abs(required_qty)",
            "install": "+abs(required_qty)",
            "dismantle": "-abs(required_qty)",
            "accepted_submitted_signs": accepted_signs,
        },
        "action_time_columns": action_time_columns,
        "week_identity_mode": week_identity_mode,
        "material_source_contract": {
            action: list(allowed)
            for action, allowed in sorted((material_source_contract or {}).items())
        },
        "material_source_missing_effect": material_source_missing_effect,
        "missing_material_source_row_count": sum(
            bool(row["missing_material_source"])
            for row in final_rows
        ),
        "missing_material_source_examples": [
            {
                "row": int(row["row"]),
                "action": action_key_parts(row["action_key"])[2],
            }
            for row in final_rows
            if row["missing_material_source"]
        ][:50],
        "invalid_material_source_row_count": sum(
            bool(row["invalid_material_source"])
            for row in final_rows
        ),
        "invalid_material_source_examples": [
            {
                "row": int(row["row"]),
                "action": action_key_parts(row["action_key"])[2],
                "material_source": str(row["material_source"]),
            }
            for row in final_rows
            if row["invalid_material_source"]
        ][:50],
        "parsed_final_rows": len(final_rows),
        "invalid_final_rows": sum(bool(row["errors"]) for row in final_rows),
        "unassigned_row_issues": unassigned_issues,
        "actions": results,
    }
