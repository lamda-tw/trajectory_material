"""O2 effective delivered-site rate under explicit plan-authority modes."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.adapters.products.material_substitution import (
    NormalizedMaterialSubstitution,
    identity_catalog,
)
from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import artifact, failed_leaf, leaf, normalized
from ..common import (
    _base_pk_material_code,
    _bom_key,
    _key,
    _norm,
    _number,
)
from ..drop_selection import SeededDropSelection, compile_seeded_drop_selection
from ..batching import assert_question_region_consistency
from .material import _strict_final_bom_actions
from .prepared_master import compare_prepared_master
from .parsing import (
    action_key_parts,
    batch_for,
    candidate_plan,
    delivery_batches,
    fixed_authority_plan,
    site_identity,
)


_NAME = "Effective delivered-site rate"
_DELIVERY_ACTION = "install"


def _authority_actions(parameters: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the explicitly scored action universe, with legacy inference."""

    value = parameters.get("o2_authority_actions")
    if value is None:
        # All pre-v4.7 profiles score every install/dismantle action exposed by
        # the authoritative material scope.
        return ("install", "dismantle")
    if value not in (["install"], ["install", "dismantle"]):
        raise ValueError(
            "O2 authority actions must be ['install'] or "
            "['install', 'dismantle']"
        )
    return tuple(str(action) for action in value)


def _drop_selection_contract(
    parameters: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    value = parameters.get("o2_drop_selection_contract")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("O2 drop-selection contract must be a mapping")
    return value


def _install_only_contract(
    parameters: Mapping[str, Any],
    *,
    authority_actions: tuple[str, ...],
) -> dict[str, tuple[str, ...]] | None:
    value = parameters.get("o2_install_only_contract")
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise ValueError("O2 install-only contract must be a non-empty mapping")
    if set(value) != {"forbidden_actions"}:
        raise ValueError(
            "O2 install-only contract must contain exactly forbidden_actions"
        )
    if authority_actions != ("install",):
        raise ValueError(
            "O2 install-only contract requires authority_actions=['install']"
        )

    raw = value.get("forbidden_actions")
    if not isinstance(raw, (list, tuple)) or not raw or not all(
        isinstance(item, str) and _norm(item) for item in raw
    ):
        raise ValueError(
            "O2 install-only forbidden_actions must be a non-empty string list"
        )
    normalized_values = tuple(_norm(item).casefold() for item in raw)
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError("O2 install-only forbidden_actions must be unique")
    output = {"forbidden_actions": normalized_values}
    forbidden = set(output["forbidden_actions"])
    if not forbidden <= {"dismantle"}:
        raise ValueError(
            "O2 install-only forbidden_actions may only contain dismantle"
        )
    return output


def _material_source_contract(
    parameters: Mapping[str, Any],
    *,
    authority_actions: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Compile optional action-local final-BOM source labels."""

    value = parameters.get("o2_material_source_contract")
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not value:
        raise ValueError("O2 material-source contract must be a non-empty mapping")
    output: dict[str, tuple[str, ...]] = {}
    for raw_action, raw_allowed in value.items():
        action = str(raw_action)
        if action not in {"install", "dismantle"}:
            raise ValueError(f"O2 material-source action is unsupported: {action!r}")
        if action not in authority_actions:
            raise ValueError(
                f"O2 material-source action is outside authority_actions: {action!r}"
            )
        if not isinstance(raw_allowed, (list, tuple)) or not raw_allowed:
            raise ValueError(
                f"O2 material-source values for {action!r} must be a non-empty list"
            )
        allowed = tuple(
            _norm(item)
            for item in raw_allowed
            if isinstance(item, str) and _norm(item)
        )
        normalized = tuple(item.casefold() for item in allowed)
        if len(allowed) != len(raw_allowed) or len(set(normalized)) != len(normalized):
            raise ValueError(
                f"O2 material-source values for {action!r} must be "
                "non-empty normalized-unique strings"
            )
        output[action] = allowed
    return dict(sorted(output.items()))


def _material_source_missing_effect(
    parameters: Mapping[str, Any],
    *,
    material_source_contract: Mapping[str, tuple[str, ...]],
) -> str:
    """Return whether source-label defects invalidate O2 or stay diagnostic."""

    value = parameters.get("o2_material_source_missing_effect", "blocking")
    if value not in {"blocking", "diagnostic"}:
        raise ValueError(
            "O2 material-source missing effect must be blocking or diagnostic"
        )
    if (
        "o2_material_source_missing_effect" in parameters
        and not material_source_contract
    ):
        raise ValueError(
            "O2 material-source missing effect requires "
            "o2_material_source_contract"
        )
    return str(value)


def _filter_material_authority(
    material_authority: Mapping[str, Mapping[str, int]],
    authority_actions: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    allowed = set(authority_actions)
    filtered = {
        str(key): dict(materials)
        for key, materials in material_authority.items()
        if action_key_parts(str(key))[2] in allowed
    }
    if not filtered:
        raise ValueError("O2 authority action filter produced no material facts")
    return filtered


def _normalized_frame(context: RuleContext, role: str) -> pd.DataFrame:
    """Return one adapter-owned canonical table, never a physical source table."""

    value = normalized(context, role)
    if value is None:
        raise FileNotFoundError(f"configured {role} artifact is missing")
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"normalized {role} must be a DataFrame")
    return value


def _assert_authority_adapter(context: RuleContext, role: str) -> None:
    """Reject a partial question-authority normalization.

    Candidate defects may legitimately score zero.  A partially normalized
    question input must never silently shrink N or distort B and then be
    blamed on the candidate, so authority adapter issues are fatal upstream.
    """

    resolved = artifact(context, role)
    blocking_codes = {
        "CANONICAL_TABLE_MISSING",
        "CANONICAL_PRODUCT_EMPTY",
        "MISSING_CANONICAL_COLUMN",
        "INVALID_CANONICAL_VALUE",
    }
    issues = [
        dict(issue)
        for issue in (resolved.validation_issues if resolved is not None else ())
        if str(issue.get("code")) in blocking_codes
    ]
    if issues:
        raise ValueError(
            f"authoritative {role} has normalized adapter issues: {issues[:20]}"
        )


def _normalized_authority_frame(context: RuleContext, role: str) -> pd.DataFrame:
    """Return one complete adapter-owned question-authority table."""

    _assert_authority_adapter(context, role)
    value = _normalized_frame(context, role)
    return value


def _blocking_adapter_issues(
    context: RuleContext,
    role: str,
) -> list[dict[str, Any]]:
    """Return adapter contract failures that make a candidate table unusable."""

    resolved = artifact(context, role)
    if resolved is None:
        return []
    blocking_codes = {
        "CANONICAL_TABLE_MISSING",
        "CANONICAL_PRODUCT_EMPTY",
        "MISSING_CANONICAL_COLUMN",
    }
    return [
        dict(issue)
        for issue in resolved.validation_issues
        if str(issue.get("code")) in blocking_codes
    ]


def _public_adapter_validation(
    context: RuleContext,
    role: str,
) -> dict[str, Any]:
    """Expose compact, non-scoring adapter diagnostics in rule evidence."""

    resolved = artifact(context, role)
    raw_issues = tuple(resolved.validation_issues) if resolved is not None else ()
    compact: list[dict[str, Any]] = []
    for issue in raw_issues[:20]:
        value = {
            key: issue[key]
            for key in ("code", "message", "column", "row", "raw")
            if key in issue
        }
        if str(issue.get("code")) == "EXACT_COLUMNS_MISMATCH":
            expected = [str(item) for item in issue.get("expected", ())]
            actual = [str(item) for item in issue.get("actual", ())]
            expected_keys = {_key(item) for item in expected}
            actual_keys = {_key(item) for item in actual}
            value["missing_columns"] = [
                item for item in expected if _key(item) not in actual_keys
            ]
            value["unexpected_columns"] = [
                item for item in actual if _key(item) not in expected_keys
            ]
        compact.append(value)
    return {
        "role": role,
        "issue_count": len(raw_issues),
        "score_effect": "none",
        "issues": compact,
    }


def _integer_quantity(value: Any, *, label: str) -> int | None:
    number = _number(value)
    if number is None:
        return None
    if not float(number).is_integer():
        raise ValueError(f"{label} must contain integer quantities")
    return int(number)


def _normalized_scope_material_facts(
    source: pd.DataFrame,
    *,
    material_mode: str,
) -> dict[str, dict[str, int]]:
    """Compile business facts from the adapter's canonical scope entity."""

    required = {
        "site_id",
        "region",
        "item_code",
        "band",
        "ntnr",
        "action",
        "signed_quantity",
        "install_quantity",
        "redeploy_quantity",
        "dismantle_quantity",
    }
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"normalized scope_input lacks O2 fields: {missing}")
    if material_mode not in {"raw", "base-pk-standardized"}:
        raise ValueError(f"unsupported scope material mode: {material_mode}")

    facts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in source.itertuples(index=False):
        site = site_identity(getattr(row, "site_id"))
        region = _norm(getattr(row, "region")) or "ALL"
        if not site:
            continue
        item = (
            _base_pk_material_code(
                getattr(row, "item_code"),
                getattr(row, "band"),
                getattr(row, "ntnr"),
            )
            if material_mode == "base-pk-standardized"
            else _bom_key(getattr(row, "item_code"))
        )
        if not item:
            continue

        signed = _integer_quantity(
            getattr(row, "signed_quantity"),
            label="scope_input.signed_quantity",
        )
        install = _integer_quantity(
            getattr(row, "install_quantity"),
            label="scope_input.install_quantity",
        )
        redeploy = _integer_quantity(
            getattr(row, "redeploy_quantity"),
            label="scope_input.redeploy_quantity",
        )
        dismantle = _integer_quantity(
            getattr(row, "dismantle_quantity"),
            label="scope_input.dismantle_quantity",
        )
        action = _norm(getattr(row, "action")).casefold()
        action_quantities: dict[str, int] = {}
        if material_mode == "base-pk-standardized":
            if signed:
                action_quantities[
                    "install" if signed > 0 else "dismantle"
                ] = signed
        else:
            install_total = int(install or 0) + int(redeploy or 0)
            if install_total:
                action_quantities["install"] = install_total
            if dismantle:
                action_quantities["dismantle"] = -abs(int(dismantle))
            if not action_quantities and signed:
                resolved_action = (
                    action
                    if action in {"install", "dismantle"}
                    else "install" if signed > 0 else "dismantle"
                )
                action_quantities[resolved_action] = (
                    abs(signed) if resolved_action == "install" else -abs(signed)
                )
        for resolved_action, quantity in action_quantities.items():
            if quantity == 0:
                continue
            key = f"{_key(region)}|{site}|{resolved_action}"
            facts[key][item] += int(quantity)
    output = {
        key: {
            item: quantity
            for item, quantity in sorted(materials.items())
            if quantity != 0
        }
        for key, materials in sorted(facts.items())
    }
    output = {key: values for key, values in output.items() if values}
    if not output:
        raise ValueError("normalized scope_input produced no material facts")
    return output


def _expected_from_material_facts(
    material_authority: Mapping[str, Mapping[str, int]],
) -> pd.DataFrame:
    rows = []
    for key in sorted(material_authority):
        region, site, action = action_key_parts(key)
        rows.append(
            {
                "site": site,
                "region": region,
                "action": action,
                "site_key": f"{region}|{site}",
                "action_key": key,
            }
        )
    return pd.DataFrame(rows)


def _half_up_target(pool_size: int, skip_rate: float) -> int:
    value = Decimal(pool_size) * (Decimal("1") - Decimal(str(skip_rate)))
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _required_text_parameter(
    parameters: Mapping[str, Any],
    key: str,
    *,
    default: str | None = None,
) -> str:
    value = parameters.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"O2 requires nonempty {key}")
    return value.strip()


def _largest_remainder(
    total: int,
    curve: Mapping[int, Decimal | int | float | str],
) -> tuple[dict[int, int], dict[int, str]]:
    """Scale a shape to an integer total with deterministic Hamilton rounding."""

    values = {int(month): Decimal(str(value)) for month, value in curve.items()}
    if any(value < 0 for value in values.values()):
        raise ValueError("authoritative master plan contains a negative quantity")
    curve_total = sum(values.values(), Decimal("0"))
    if curve_total <= 0:
        raise ValueError("authoritative master plan curve has no positive quantity")
    quotas = {
        month: Decimal(total) * value / curve_total
        for month, value in values.items()
    }
    target = {
        month: int(quota.to_integral_value(rounding=ROUND_FLOOR))
        for month, quota in quotas.items()
    }
    seats = total - sum(target.values())
    ranked = sorted(
        quotas,
        key=lambda month: (-(quotas[month] - Decimal(target[month])), month),
    )
    for month in ranked[:seats]:
        target[month] += 1
    return target, {month: str(quotas[month]) for month in sorted(quotas)}


def _authoritative_curve(
    master: Mapping[tuple[str, int], Decimal],
    group: str,
) -> dict[int, Decimal]:
    exact = {
        int(period): value
        for (master_group, period), value in master.items()
        if master_group == group
    }
    if exact:
        return exact
    fallback = {
        int(period): value
        for (master_group, period), value in master.items()
        if master_group == "all"
    }
    if not fallback:
        raise ValueError(
            f"authoritative master plan has neither {group!r} nor ALL curve"
        )
    return fallback


def _normalized_master_plan(source: pd.DataFrame) -> dict[tuple[str, int], Decimal]:
    """Read the canonical long-form master curve emitted by its adapter."""

    required = {"region", "month", "period", "planned_count"}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"normalized master_plan lacks O2 fields: {missing}")
    values: dict[tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in source.itertuples(index=False):
        month_value = _number(getattr(row, "month"))
        period_value = _number(getattr(row, "period"))
        count_text = _norm(getattr(row, "planned_count")).replace(",", "")
        if month_value is None or period_value is None or not count_text:
            continue
        if not float(month_value).is_integer() or not 1 <= int(month_value) <= 12:
            raise ValueError("normalized master_plan month must be an integer in 1..12")
        if not float(period_value).is_integer() or not 200001 <= int(period_value) <= 209912:
            raise ValueError("normalized master_plan period must be YYYYMM")
        if int(period_value) % 100 != int(month_value):
            raise ValueError("normalized master_plan month and period disagree")
        try:
            count_value = Decimal(count_text)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("normalized master_plan contains invalid planned_count") from exc
        if not count_value.is_finite() or count_value < 0:
            raise ValueError("normalized master_plan contains invalid planned_count")
        group = _key(_norm(getattr(row, "region")) or "ALL")
        values[(group, int(period_value))] += count_value
    if not values:
        raise ValueError("normalized master_plan produced no month quantities")
    return dict(values)


def _capacity_factor(parameters: Mapping[str, Any]) -> Decimal:
    value = parameters.get("o2_capacity_factor", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("O2 capacity factor must be a finite nonnegative number")
    factor = Decimal(str(value))
    if not factor.is_finite() or factor < 0:
        raise ValueError("O2 capacity factor must be a finite nonnegative number")
    return factor


def _monthly_capacity_mode(parameters: Mapping[str, Any]) -> str:
    mode = str(parameters.get("o2_monthly_capacity_mode", "not-applicable"))
    if mode not in {"hard-limit", "not-applicable"}:
        raise ValueError(
            "O2 monthly capacity mode must be hard-limit or not-applicable"
        )
    return mode


def _monthly_capacity(
    master: Mapping[tuple[str, int], Decimal],
    *,
    group: str,
    period: int,
    factor: Decimal,
) -> tuple[Decimal, int, str]:
    """Return the raw and factored cap with C3's exact-cell/ALL fallback."""

    exact_key = (group, int(period))
    fallback_key = ("all", int(period))
    if exact_key in master:
        raw = master[exact_key]
        source = "exact-region-period"
    elif fallback_key in master:
        raw = master[fallback_key]
        source = "all-period-fallback"
    else:
        raw = Decimal("0")
        source = "missing-period-zero"
    limit = int((raw * factor).to_integral_value(rounding=ROUND_FLOOR))
    return raw, limit, source


def _apply_monthly_capacity(
    authority: Mapping[str, Any],
    site_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Admit intrinsically valid sites under deterministic monthly caps.

    Capacity is a gate into A, not an additional score term. Removing an
    over-cap site from A lets the existing curve decomposition charge exactly
    one loss unit, avoiding a second pacing penalty for the same site.
    """

    if (
        authority["plan_mode"] != "candidate-scheduled"
        or authority["monthly_capacity_mode"] != "hard-limit"
    ):
        return {
            "applied": False,
            "mode": authority.get("monthly_capacity_mode", "not-applicable"),
            "capacity_factor": None,
            "tie_break": "not_applicable",
            "grid": [],
            "exceeded_site_keys": [],
        }

    factor = Decimal(str(authority["capacity_factor"]))
    master = authority["master_plan"]
    candidates: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for result in site_results:
        if result["valid"] and result.get("submitted_period") is not None:
            candidates[(str(result["group"]), int(result["submitted_period"]))].append(
                result
            )

    keys = set(candidates)
    for group, periods in authority["target_curve_covered_periods"].items():
        keys.update((str(group), int(period)) for period in periods)

    grid: list[dict[str, Any]] = []
    exceeded_keys: list[str] = []
    for group, period in sorted(keys):
        raw, limit, source = _monthly_capacity(
            master,
            group=group,
            period=period,
            factor=factor,
        )
        ordered = sorted(candidates.get((group, period), ()), key=lambda row: row["site_key"])
        for rank, result in enumerate(ordered, start=1):
            result["monthly_capacity_raw"] = str(raw)
            result["monthly_capacity_limit"] = limit
            result["monthly_capacity_rank"] = rank
            result["monthly_capacity_source"] = source
            if rank <= limit:
                continue
            result["valid"] = False
            result["reasons"] = sorted(
                set((*result["reasons"], "MONTHLY_CAPACITY_EXCEEDED"))
            )
            exceeded_keys.append(str(result["site_key"]))
        admitted = ordered[:limit]
        exceeded = ordered[limit:]
        grid.append(
            {
                "group": group,
                "month": period % 100,
                "year_month": f"{period // 100:04d}-{period % 100:02d}",
                "raw_master_capacity": str(raw),
                "capacity_factor": str(factor),
                "capacity_limit": limit,
                "capacity_source": source,
                "intrinsic_valid_candidates": len(ordered),
                "admitted_candidates": len(admitted),
                "over_capacity_candidates": len(exceeded),
                "admitted_site_keys": [str(row["site_key"]) for row in admitted[:50]],
                "exceeded_site_keys": [str(row["site_key"]) for row in exceeded[:50]],
            }
        )
    return {
        "applied": True,
        "mode": "hard-limit",
        "capacity_factor": float(factor),
        "tie_break": "site_key_ascending",
        "grid": grid,
        "exceeded_site_keys": sorted(exceeded_keys),
    }


def _site_indexes(
    expected: pd.DataFrame,
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[str, ...]]]:
    sites: dict[str, dict[str, Any]] = {}
    names: dict[str, set[str]] = defaultdict(set)
    for _, row in expected.iterrows():
        site_key = str(row["site_key"])
        value = sites.setdefault(
            site_key,
            {
                "site_key": site_key,
                "site": str(row["site"]),
                "site_identity": site_identity(row["site"]),
                "region": str(row["region"]),
                "region_key": _key(row["region"]),
                "actions": set(),
            },
        )
        value["actions"].add(str(row["action"]))
        names[site_identity(row["site"])].add(site_key)
    return sites, {
        name: tuple(sorted(keys))
        for name, keys in names.items()
    }


def _resolve_site(
    site: Any,
    candidate_site_key: Any,
    authority_sites: Mapping[str, Mapping[str, Any]],
    authority_names: Mapping[str, tuple[str, ...]],
) -> str | None:
    identity = site_identity(site)
    direct = str(candidate_site_key)
    if (
        direct in authority_sites
        and identity == str(authority_sites[direct]["site_identity"])
    ):
        return direct
    matches = authority_names.get(identity, ())
    return matches[0] if len(matches) == 1 else None


def _material_contract(
    context: RuleContext,
    *,
    scope_material_mode: str,
    substitution_mode: str,
) -> tuple[dict[str, dict[str, int]], dict[str, Any], dict[str, Any]]:
    scope_input = _normalized_authority_frame(context, "scope_input")
    material_authority = _normalized_scope_material_facts(
        scope_input,
        material_mode=scope_material_mode,
    )
    if substitution_mode == "identity-only":
        catalog = identity_catalog()
    else:
        _assert_authority_adapter(context, "substitution_source")
        substitution_source = normalized(context, "substitution_source")
        if substitution_source is None:
            raise FileNotFoundError(
                "configured authoritative substitution source is missing"
            )
        if not isinstance(substitution_source, NormalizedMaterialSubstitution):
            raise TypeError(
                "normalized substitution_source must be an authoritative catalog"
            )
        catalog = substitution_source
        if catalog.mode != substitution_mode:
            raise ValueError(
                "normalized substitution catalog mode does not match O2 configuration"
            )
    authority_items = sorted(
        {
            item
            for materials in material_authority.values()
            for item in materials
        }
    )
    alternatives = catalog.matcher_mapping(authority_items)
    target_summaries = []
    for item in authority_items:
        target = catalog.target(item)
        target_summaries.append(
            {
                "target_item_code": item,
                "defined_in_source": bool(target.defined),
                "allow_original": bool(target.allow_original),
                "option_count": len(target.options),
                "roles": sorted({option.role for option in target.options}),
                "source_rows": list(target.source_rows[:20]),
            }
        )
    summary = {
        "mode": catalog.mode,
        "source_kind": catalog.source_kind,
        "undefined_target_policy": catalog.undefined_target_policy,
        "authority_target_count": len(authority_items),
        "defined_target_count": sum(
            bool(catalog.target(item).defined) for item in authority_items
        ),
        "allow_original_target_count": sum(
            bool(catalog.target(item).allow_original) for item in authority_items
        ),
        "target_examples": target_summaries[:50],
    }
    return material_authority, alternatives, summary


def _compile_fixed_authority(
    context: RuleContext,
    *,
    parameters: Mapping[str, Any],
    project_week_source: str,
    traceability_mode: str,
    region_scope: str,
    scope_material_mode: str,
    final_bom_quantity_mode: str,
    substitution_mode: str,
    week_to_month: str,
    delivery_month_source: str,
    site_plan_required_fields: frozenset[str],
    authority_actions: tuple[str, ...],
    target_curve_mode: str,
    material_source_contract: Mapping[str, tuple[str, ...]],
    material_source_missing_effect: str,
    install_only_contract: Mapping[str, tuple[str, ...]] | None,
) -> dict[str, Any]:
    planning_year_value = parameters.get("o2_planning_year")
    if (
        not isinstance(planning_year_value, int)
        or isinstance(planning_year_value, bool)
    ):
        raise ValueError("O2 requires integer o2_planning_year")
    planning_year = int(planning_year_value)
    raw_plan = _normalized_authority_frame(context, "site_plan")
    raw_plan_actions = raw_plan["action"].map(
        lambda value: _norm(value).casefold()
    )
    raw_plan = raw_plan.loc[raw_plan_actions.isin(authority_actions)].copy()
    plan = fixed_authority_plan(
        raw_plan,
        project_week_source=project_week_source,
        delivery_month_source=delivery_month_source,
        planning_year=planning_year,
        week_to_month=week_to_month,
        project_start_month=int(parameters.get("o2_project_start_month", 1)),
        required_fields=site_plan_required_fields,
    )
    raw_material_authority, alternatives, substitution_catalog_summary = _material_contract(
        context,
        scope_material_mode=scope_material_mode,
        substitution_mode=substitution_mode,
    )
    material_authority = _filter_material_authority(
        raw_material_authority,
        authority_actions,
    )
    scored_plan = plan[plan["action"].isin(authority_actions)].copy()
    missing_material_actions = sorted(
        set(scored_plan["action_key"].map(str)) - set(material_authority)
    )
    if missing_material_actions:
        raise ValueError(
            "fixed site_plan actions cannot be mapped to Input4 material facts: "
            f"{missing_material_actions[:20]}"
        )

    expected = scored_plan[
        scored_plan["action_key"].map(str).isin(material_authority)
    ][["site", "region", "action", "site_key", "action_key"]].copy()
    sites, names = _site_indexes(expected)
    delivery_sites = {
        site_key: value
        for site_key, value in sites.items()
        if _DELIVERY_ACTION in value["actions"]
    }
    if not delivery_sites:
        raise ValueError("fixed site_plan contains no install delivery sites")

    rows_by_site: dict[str, list[pd.Series]] = defaultdict(list)
    for _, row in scored_plan.iterrows():
        rows_by_site[str(row["site_key"])].append(row)
    target: dict[str, Counter[int]] = defaultdict(Counter)
    for site_key, site in delivery_sites.items():
        action_months: dict[str, int] = {}
        action_periods: dict[str, int] = {}
        for row in rows_by_site[site_key]:
            month = row["delivery_month"]
            period = row["delivery_period"]
            if month is None or pd.isna(month) or period is None or pd.isna(period):
                raise ValueError(
                    "fixed site_plan action month is unresolved for "
                    f"{site['site']!r}/{row['action']}"
                )
            action_months[str(row["action"])] = int(month)
            action_periods[str(row["action"])] = int(period)
        site["batch"] = ""
        site["batch_compare"] = ""
        site["batch_anchor_key"] = ""
        site["pool_key"] = (str(site["region_key"]), "")
        site["fixed_action_months"] = action_months
        site["fixed_action_periods"] = action_periods
        site["fixed_month"] = action_months[_DELIVERY_ACTION]
        site["fixed_period"] = action_periods[_DELIVERY_ACTION]
        target[str(site["region_key"])][site["fixed_period"]] += 1

    denominator = len(delivery_sites)
    return {
        "plan_mode": "fixed-authority",
        "authority_actions": authority_actions,
        "target_curve_mode": target_curve_mode,
        "target_curve_covered_periods": {
            group: sorted(int(period) for period in months)
            for group, months in target.items()
        },
        "completion_buckets": {},
        "material_source_contract": dict(material_source_contract),
        "material_source_missing_effect": material_source_missing_effect,
        "install_only_contract": (
            dict(install_only_contract) if install_only_contract else None
        ),
        "drop_selection": None,
        "dropped_sites": {},
        "dropped_names": {},
        "parameters": parameters,
        "project_week_source": project_week_source,
        "traceability_mode": traceability_mode,
        "region_scope": region_scope,
        "final_bom_quantity_mode": final_bom_quantity_mode,
        "planning_year": planning_year,
        "delivery_month_source": delivery_month_source,
        "site_plan_required_fields": site_plan_required_fields,
        "expected_source_actions": len(raw_material_authority),
        "expected_actions": len(expected),
        "sites": sites,
        "names": names,
        "complete_sites": sites,
        "complete_names": names,
        "delivery_sites": delivery_sites,
        "batch_map": {},
        "pool_counts": Counter(),
        "pool_targets": {},
        "group_targets": {
            group: sum(months.values()) for group, months in target.items()
        },
        "denominator": denominator,
        "scaled_targets": {
            group: dict(sorted(months.items())) for group, months in target.items()
        },
        "scaled_quotas": {},
        "material_authority": material_authority,
        "alternatives": alternatives,
        "substitution_catalog_summary": substitution_catalog_summary,
        "scope_material_mode": scope_material_mode,
        "substitution_mode": substitution_mode,
        "pure_dismantle": [
            {
                "site_key": site_key,
                "site": str(site["site"]),
                "region": str(site["region"]),
            }
            for site_key, site in sorted(sites.items())
            if _DELIVERY_ACTION not in site["actions"]
        ],
        "fixed_plan": scored_plan,
        "fixed_rows_by_site": rows_by_site,
    }


def _compile_authority(context: RuleContext) -> dict[str, Any]:
    parameters = context.component.parameters
    plan_mode = _required_text_parameter(
        parameters,
        "o2_plan_mode",
        default="candidate-scheduled",
    )
    group_by = _required_text_parameter(parameters, "o2_group_by")
    delivery_action = _required_text_parameter(parameters, "o2_delivery_action")
    site_scope = _required_text_parameter(
        parameters,
        "o2_site_scope",
        default="fixed-site-plan" if plan_mode == "fixed-authority" else None,
    )
    batch_kind = _required_text_parameter(
        parameters,
        "o2_batch_kind",
        default="none" if plan_mode == "fixed-authority" else None,
    )
    master_format = _required_text_parameter(
        parameters,
        "o2_master_format",
        default="standard",
    )
    week_to_month = _required_text_parameter(
        parameters,
        "o2_week_to_month",
        default="calendar",
    )
    delivery_month_source = _required_text_parameter(
        parameters,
        "o2_delivery_month_source",
        default="week-label" if plan_mode == "fixed-authority" else "week-start",
    )
    project_week_source = _required_text_parameter(
        parameters,
        "o2_project_week_source",
        default="reconcile",
    )
    substitution_mode = _required_text_parameter(
        parameters,
        "o2_substitution_mode",
    )
    traceability_mode = _required_text_parameter(
        parameters,
        "o2_traceability_mode",
    )
    region_scope = _required_text_parameter(parameters, "o2_region_scope")
    scope_material_mode = _required_text_parameter(
        parameters,
        "o2_scope_material_mode",
    )
    final_bom_quantity_mode = _required_text_parameter(
        parameters,
        "o2_final_bom_quantity_mode",
    )
    authority_actions = _authority_actions(parameters)
    install_only_contract = _install_only_contract(
        parameters,
        authority_actions=authority_actions,
    )
    material_source_contract = _material_source_contract(
        parameters,
        authority_actions=authority_actions,
    )
    material_source_missing_effect = _material_source_missing_effect(
        parameters,
        material_source_contract=material_source_contract,
    )
    target_curve_mode = _required_text_parameter(
        parameters,
        "o2_target_curve_mode",
        default=(
            "fixed-plan"
            if plan_mode == "fixed-authority"
            else "master-distribution"
        ),
    )
    required_fields_value = parameters.get("o2_site_plan_required_fields")
    if not isinstance(required_fields_value, (list, tuple)) or not all(
        isinstance(value, str) and value.strip() for value in required_fields_value
    ):
        raise ValueError("O2 requires o2_site_plan_required_fields as a string list")
    site_plan_required_fields = frozenset(
        str(value).strip() for value in required_fields_value
    )
    if group_by != "region":
        raise ValueError("O2 supports only o2_group_by=region")
    if delivery_action != _DELIVERY_ACTION:
        raise ValueError("O2 supports only o2_delivery_action=install")
    if plan_mode not in {"candidate-scheduled", "fixed-authority"}:
        raise ValueError("O2 plan mode must be candidate-scheduled or fixed-authority")
    if plan_mode == "fixed-authority" and target_curve_mode != "fixed-plan":
        raise ValueError("fixed-authority O2 requires target-curve mode fixed-plan")
    if plan_mode == "candidate-scheduled" and target_curve_mode not in {
        "master-distribution",
        "completion-by-deadline",
    }:
        raise ValueError(
            "candidate-scheduled O2 target-curve mode must be "
            "master-distribution or completion-by-deadline"
        )
    if plan_mode == "candidate-scheduled" and site_scope != "batch_intersection":
        raise ValueError("candidate-scheduled O2 requires batch_intersection")
    if plan_mode == "fixed-authority" and site_scope != "fixed-site-plan":
        raise ValueError("fixed-authority O2 requires fixed-site-plan scope")
    if plan_mode == "candidate-scheduled" and batch_kind not in {"cluster", "mocn"}:
        raise ValueError("O2 batch kind must be cluster or mocn")
    if master_format not in {
        "standard",
        "pip-city-wise",
        "site-action-weekly-install",
    }:
        raise ValueError(
            "O2 master format must be standard, pip-city-wise or "
            "site-action-weekly-install"
        )
    if week_to_month not in {"calendar", "four-week-project"}:
        raise ValueError("O2 week-to-month mode must be calendar or four-week-project")
    if delivery_month_source not in {"week-start", "week-label", "schedule-week"}:
        raise ValueError("O2 delivery-month source is unsupported")
    if project_week_source not in {"reconcile", "week_num"}:
        raise ValueError("O2 project-week source must be reconcile or week_num")
    if substitution_mode not in {
        "identity-only",
        "legacy-combination",
        "legacy-target-fallback",
        "expanded-bidirectional",
        "priority-row-views",
    }:
        raise ValueError("O2 substitution mode is unsupported")
    if traceability_mode not in {"aggregate-feasible", "explicit-origin"}:
        raise ValueError("O2 traceability mode is unsupported")
    if region_scope not in {"exact", "regionless"}:
        raise ValueError("O2 final-BOM region scope is unsupported")
    if scope_material_mode not in {"raw", "base-pk-standardized"}:
        raise ValueError("O2 scope material mode is unsupported")
    if final_bom_quantity_mode not in {
        "signed-action",
        "dismantle-absolute",
        "absolute",
    }:
        raise ValueError("O2 final-BOM quantity mode is unsupported")
    if week_to_month == "four-week-project":
        project_start_month = parameters.get("o2_project_start_month")
        if (
            not isinstance(project_start_month, int)
            or isinstance(project_start_month, bool)
            or project_start_month < 1
        ):
            raise ValueError(
                "O2 four-week-project mode requires positive o2_project_start_month"
            )
    if plan_mode == "fixed-authority":
        return _compile_fixed_authority(
            context,
            parameters=parameters,
            project_week_source=project_week_source,
            traceability_mode=traceability_mode,
            region_scope=region_scope,
            scope_material_mode=scope_material_mode,
            final_bom_quantity_mode=final_bom_quantity_mode,
            substitution_mode=substitution_mode,
            week_to_month=week_to_month,
            delivery_month_source=delivery_month_source,
            site_plan_required_fields=site_plan_required_fields,
            authority_actions=authority_actions,
            target_curve_mode=target_curve_mode,
            material_source_contract=material_source_contract,
            material_source_missing_effect=material_source_missing_effect,
            install_only_contract=install_only_contract,
        )

    interval_contract = parameters.get("o2_interval_contract")
    if not isinstance(interval_contract, Mapping):
        raise ValueError("O2 requires o2_interval_contract")
    interval_anchor = str(interval_contract.get("anchor"))
    if interval_anchor not in {
        "batch-finish",
        "site-install",
        "not-applicable",
    }:
        raise ValueError(
            "O2 interval anchor must be batch-finish, site-install, "
            "or not-applicable"
        )
    if interval_anchor == "not-applicable":
        if authority_actions != ("install",):
            raise ValueError(
                "O2 interval anchor not-applicable requires install-only authority"
            )
        if set(interval_contract) != {"anchor"}:
            raise ValueError(
                "O2 not-applicable interval contract may only declare anchor"
            )
        interval_relation: str | None = None
        lag_weeks: int | None = None
    else:
        interval_relation = str(interval_contract.get("relation"))
        if interval_relation not in {"minimum", "exact"}:
            raise ValueError("O2 interval relation must be minimum or exact")
        lag_value = interval_contract.get("lag_weeks")
        if (
            not isinstance(lag_value, int)
            or isinstance(lag_value, bool)
            or lag_value < 0
        ):
            raise ValueError("O2 interval lag_weeks must be a nonnegative integer")
        lag_weeks = int(lag_value)

    scope_input = _normalized_authority_frame(context, "scope_input")
    batch_input = _normalized_authority_frame(context, "batch_input")
    master_input = _normalized_authority_frame(context, "master_plan")

    raw_material_authority, alternatives, substitution_catalog_summary = _material_contract(
        context,
        scope_material_mode=scope_material_mode,
        substitution_mode=substitution_mode,
    )
    material_authority = _filter_material_authority(
        raw_material_authority,
        authority_actions,
    )
    # The normalized material facts are the single station/action authority;
    # O2 does not independently rediscover an action universe from raw columns.
    expected_source = _expected_from_material_facts(material_authority)
    if expected_source.empty:
        raise ValueError("O2 material scope produced no authoritative site actions")
    assert_question_region_consistency(scope_input, batch_input)
    batch_map = delivery_batches(
        batch_input,
        batch_kind=batch_kind,
    )
    expected = expected_source[
        expected_source["site_key"].map(
            lambda value: batch_for(str(value), batch_map) is not None
        )
    ].copy()
    if expected.empty:
        raise ValueError("scope and delivery batch inputs have no common site actions")
    sites, names = _site_indexes(expected)
    complete_sites, complete_names = _site_indexes(expected_source)
    delivery_sites = {
        site_key: value
        for site_key, value in sites.items()
        if _DELIVERY_ACTION in value["actions"]
    }
    if not delivery_sites:
        raise ValueError("authoritative scope contains no install delivery sites")

    skip_rate_value = parameters.get("o2_skip_rate")
    if (
        isinstance(skip_rate_value, bool)
        or not isinstance(skip_rate_value, (int, float))
    ):
        raise ValueError("O2 requires numeric o2_skip_rate")
    skip_rate = float(skip_rate_value)
    if not math.isfinite(skip_rate) or not 0 <= skip_rate < 1:
        raise ValueError("O2 skip_rate must be in [0, 1)")
    skip_pool_scope = str(parameters.get("o2_skip_pool_scope"))
    if skip_pool_scope not in {"batch", "region-batch", "region"}:
        raise ValueError("O2 skip pool scope must be batch, region-batch or region")

    drop_selection: SeededDropSelection | None = None
    dropped_sites: dict[str, dict[str, Any]] = {}
    dropped_names: dict[str, tuple[str, ...]] = {}
    drop_contract = _drop_selection_contract(parameters)
    if drop_contract is not None:
        drop_selection = compile_seeded_drop_selection(
            expected,
            batch_map,
            batch_kind=batch_kind,
            drop_rate=skip_rate,
            pool_scope=skip_pool_scope,
            contract=drop_contract,
        )
        dropped_site_keys = set(drop_selection.dropped_install_site_keys)
        if dropped_site_keys:
            # The fixed engine removes every action for a selected install
            # site.  Filter the candidate-independent authority before B/N and
            # strict material matching are compiled; candidate rows for these
            # identities are retained separately as forbidden evidence below.
            dropped_expected = expected.loc[
                expected["site_key"].map(str).isin(dropped_site_keys)
            ].copy()
            dropped_sites, dropped_names = _site_indexes(dropped_expected)
            expected = expected.loc[
                ~expected["site_key"].map(str).isin(dropped_site_keys)
            ].copy()
            expected_source = expected_source.loc[
                ~expected_source["site_key"].map(str).isin(dropped_site_keys)
            ].copy()
            material_authority = {
                key: values
                for key, values in material_authority.items()
                if key.rsplit("|", 1)[0] not in dropped_site_keys
            }
            sites, names = _site_indexes(expected)
            complete_sites, complete_names = _site_indexes(expected_source)
            delivery_sites = {
                site_key: value
                for site_key, value in sites.items()
                if _DELIVERY_ACTION in value["actions"]
            }
            if not delivery_sites:
                raise ValueError(
                    "O2 deterministic Drop removed every install delivery site"
                )
    pool_counts: Counter[tuple[str, str]] = Counter()
    # Every scoped site, including pure-dismantle sites, needs authoritative
    # batch identity so compact candidate plans can be enriched without reading
    # a non-contract candidate batch column.  Only install sites contribute to N.
    for site_key, site in sites.items():
        batch = batch_for(site_key, batch_map)
        if batch is None:  # filtered above; retain a defensive invariant.
            continue
        site["batch"] = str(batch)
        if batch_kind == "mocn":
            numeric_batch = Decimal(str(batch))
            if numeric_batch != numeric_batch.to_integral_value() or int(numeric_batch) <= 0:
                raise ValueError("O2 authoritative MOCN batch must be a positive integer")
            site["batch_compare"] = str(int(numeric_batch))
        else:
            site["batch_compare"] = _key(batch)
        # A delivery batch is a global business object.  Region remains part of
        # the monthly B curve, but must not split the batch-finish C6a anchor.
        site["batch_anchor_key"] = str(site["batch_compare"])
        site["pool_key"] = (
            "" if skip_pool_scope == "batch" else str(site["region_key"]),
            str(site["batch_compare"])
            if skip_pool_scope in {"batch", "region-batch"}
            else "",
        )
        if site_key in delivery_sites and drop_selection is None:
            pool_counts[site["pool_key"]] += 1
    if drop_selection is None:
        pool_targets = {
            key: _half_up_target(count, skip_rate)
            for key, count in pool_counts.items()
        }
    else:
        pool_counts = Counter(
            {
                (str(pool["region"]), str(pool["batch"] or "")): int(
                    pool["install_pool_sites"]
                )
                for pool in drop_selection.pools
            }
        )
        pool_targets = {
            (str(pool["region"]), str(pool["batch"] or "")): int(
                pool["target_sites"]
            )
            for pool in drop_selection.pools
        }
    group_targets: Counter[str] = Counter()
    if drop_selection is None:
        for (group, _), target in pool_targets.items():
            group_targets[group] += target
    else:
        for site_key in drop_selection.retained_install_site_keys:
            if site_key in delivery_sites:
                group_targets[str(delivery_sites[site_key]["region_key"])] += 1
    denominator = sum(group_targets.values())
    if denominator <= 0:
        raise ValueError("O2 authoritative target site count is zero after skip_rate")

    planning_year_value = parameters.get("o2_planning_year")
    if (
        not isinstance(planning_year_value, int)
        or isinstance(planning_year_value, bool)
    ):
        raise ValueError("O2 requires integer o2_planning_year")
    planning_year = int(planning_year_value)
    master = _normalized_master_plan(master_input)
    scaled_targets: dict[str, dict[int, int]] = {}
    scaled_quotas: dict[str, dict[int, str]] = {}
    target_curve_covered_periods: dict[str, list[int]] = {}
    completion_buckets: dict[str, int] = {}
    for group, count in sorted(group_targets.items()):
        curve = _authoritative_curve(master, group)
        periods = sorted(int(period) for period in curve)
        if not periods:
            raise ValueError(
                f"authoritative master plan has no covered period for {group!r}"
            )
        target_curve_covered_periods[group] = periods
        if target_curve_mode == "completion-by-deadline":
            completion_bucket = max(periods)
            completion_buckets[group] = completion_bucket
            target = {completion_bucket: int(count)}
            quota = {completion_bucket: str(int(count))}
        else:
            target, quota = _largest_remainder(int(count), curve)
        scaled_targets[group] = target
        scaled_quotas[group] = quota

    pure_dismantle = [
        {
            "site_key": site_key,
            "site": str(site["site"]),
            "region": str(site["region"]),
        }
        for site_key, site in sorted(sites.items())
        if _DELIVERY_ACTION not in site["actions"]
    ]
    return {
        "plan_mode": "candidate-scheduled",
        "authority_actions": authority_actions,
        "target_curve_mode": target_curve_mode,
        "target_curve_covered_periods": target_curve_covered_periods,
        "completion_buckets": completion_buckets,
        "material_source_contract": dict(material_source_contract),
        "material_source_missing_effect": material_source_missing_effect,
        "install_only_contract": (
            dict(install_only_contract) if install_only_contract else None
        ),
        "drop_selection": drop_selection,
        "dropped_sites": dropped_sites,
        "dropped_names": dropped_names,
        "parameters": parameters,
        "project_week_source": project_week_source,
        "traceability_mode": traceability_mode,
        "region_scope": region_scope,
        "final_bom_quantity_mode": final_bom_quantity_mode,
        "planning_year": planning_year,
        "delivery_month_source": delivery_month_source,
        "site_plan_required_fields": site_plan_required_fields,
        "expected_source_actions": len(raw_material_authority),
        "expected_actions": len(expected),
        "sites": sites,
        "names": names,
        "complete_sites": complete_sites,
        "complete_names": complete_names,
        "delivery_sites": delivery_sites,
        "batch_map": batch_map,
        "interval_contract": {
            "anchor": interval_anchor,
            **(
                {}
                if interval_anchor == "not-applicable"
                else {
                    "relation": str(interval_relation),
                    "lag_weeks": int(lag_weeks),
                }
            ),
        },
        "skip_pool_scope": skip_pool_scope,
        "pool_counts": pool_counts,
        "pool_targets": pool_targets,
        "group_targets": dict(group_targets),
        "denominator": denominator,
        "master_plan": master,
        "monthly_capacity_mode": _monthly_capacity_mode(parameters),
        "capacity_factor": _capacity_factor(parameters),
        "scaled_targets": scaled_targets,
        "scaled_quotas": scaled_quotas,
        "material_authority": material_authority,
        "alternatives": alternatives,
        "substitution_catalog_summary": substitution_catalog_summary,
        "scope_material_mode": scope_material_mode,
        "substitution_mode": substitution_mode,
        "pure_dismantle": pure_dismantle,
    }


def prepare_o2_authority(context: RuleContext) -> dict[str, Any]:
    """Compile the candidate-independent O2 authority for one question."""

    return _compile_authority(context)


def _candidate_evidence(
    context: RuleContext,
    authority: Mapping[str, Any],
) -> CheckResult | dict[str, Any]:
    parameters = authority["parameters"]
    final = normalized(context, "final_material")
    if not isinstance(final, pd.DataFrame):
        return failed_leaf(
            context,
            "O2",
            _NAME,
            "MISSING_ARTIFACT",
            "site_final_bom is missing or unusable",
            {"role": "final_material"},
        )
    authority_actions = set(authority["authority_actions"])
    legal_actions = {"install", "dismantle"}
    install_only_contract = authority.get("install_only_contract")
    forbidden_actions = set(
        install_only_contract.get("forbidden_actions", ())
        if isinstance(install_only_contract, Mapping)
        else ()
    )

    def dropped_site_key(site: Any, region: Any) -> str | None:
        if not authority["dropped_sites"]:
            return None
        candidate_key = f"{_key(region)}|{site_identity(site)}"
        return _resolve_site(
            site,
            candidate_key,
            authority["dropped_sites"],
            authority["dropped_names"],
        )

    final_actions = final["action"].map(lambda value: _norm(value).casefold())
    dropped_final_keys = final.apply(
        lambda row: dropped_site_key(row.get("site_id"), row.get("region")),
        axis=1,
    )
    dropped_final_mask = dropped_final_keys.notna()
    dropped_final_rows = [
        {
            "source_row": int(row.get("source_row", int(index) + 2)),
            "site_key": str(dropped_final_keys.loc[index]),
            "site": _norm(row.get("site_id")),
            "region": _norm(row.get("region")),
            "action": _norm(row.get("action")).casefold(),
        }
        for index, row in final.loc[dropped_final_mask].iterrows()
    ]
    out_of_scope_final_mask = final_actions.isin(legal_actions - authority_actions)
    out_of_scope_final_rows = [
        {
            "source_row": int(row.get("source_row", int(index) + 2)),
            "site": _norm(row.get("site_id")),
            "region": _norm(row.get("region")),
            "action": _norm(row.get("action")).casefold(),
        }
        for index, row in final.loc[out_of_scope_final_mask].iterrows()
    ]
    forbidden_final_rows = [
        row for row in out_of_scope_final_rows if row["action"] in forbidden_actions
    ]
    # A legal action excluded by the question's O2 action universe is neither
    # a malformed row nor an extra BOM action.  Unknown actions remain in the
    # strict parser and retain their candidate-invalidating behavior.
    final = final.loc[~out_of_scope_final_mask & ~dropped_final_mask].copy()
    final_adapter_issues = _blocking_adapter_issues(context, "final_material")
    if final_adapter_issues:
        issue_columns = [
            str(issue.get("column", issue.get("code", "UNKNOWN")))
            for issue in final_adapter_issues
        ]
        return failed_leaf(
            context,
            "O2",
            _NAME,
            "INVALID_ARTIFACT",
            "site_final_bom cannot be parsed under the normalized adapter contract",
            {
                "role": "final_material",
                "error": "normalized adapter issues: " + ", ".join(issue_columns),
                "adapter_issues": final_adapter_issues[:20],
            },
        )
    if authority["plan_mode"] == "fixed-authority":
        plan = authority["fixed_plan"]
        out_of_scope_plan_rows: list[dict[str, Any]] = []
        forbidden_plan_rows: list[dict[str, Any]] = []
        dropped_plan_rows: list[dict[str, Any]] = []
    else:
        raw_plan = normalized(context, "site_plan")
        if not isinstance(raw_plan, pd.DataFrame):
            return failed_leaf(
                context,
                "O2",
                _NAME,
                "MISSING_ARTIFACT",
                "site_plan is missing or unusable",
                {"role": "site_plan"},
            )
        plan_adapter_issues = _blocking_adapter_issues(context, "site_plan")
        if plan_adapter_issues:
            issue_columns = [
                (
                    "delivery_batch"
                    if str(issue.get("column"))
                    in {"cluster_id", "mocn_batch_id"}
                    else str(issue.get("column", issue.get("code", "UNKNOWN")))
                )
                for issue in plan_adapter_issues
            ]
            return failed_leaf(
                context,
                "O2",
                _NAME,
                "INVALID_ARTIFACT",
                "site_plan cannot be parsed under the normalized adapter contract",
                {
                    "role": "site_plan",
                    "error": "normalized adapter issues: " + ", ".join(issue_columns),
                    "adapter_issues": plan_adapter_issues[:20],
                },
            )
        try:
            raw_plan_actions = raw_plan["action"].map(
                lambda value: _norm(value).casefold()
            )
            out_of_scope_plan_mask = raw_plan_actions.isin(
                legal_actions - authority_actions
            )
            out_of_scope_plan_rows = [
                {
                    "source_row": int(row["source_row"]),
                    "site": _norm(row["site_id"]),
                    "region": _norm(row["region"]),
                    "action": _norm(row["action"]).casefold(),
                }
                for _, row in raw_plan.loc[out_of_scope_plan_mask].iterrows()
            ]
            forbidden_plan_rows = [
                row
                for row in out_of_scope_plan_rows
                if row["action"] in forbidden_actions
            ]
            dropped_plan_keys = raw_plan.apply(
                lambda row: dropped_site_key(
                    row.get("site_id"), row.get("region")
                ),
                axis=1,
            )
            dropped_plan_mask = dropped_plan_keys.notna()
            dropped_plan_rows = [
                {
                    "source_row": int(row["source_row"]),
                    "site_key": str(dropped_plan_keys.loc[index]),
                    "site": _norm(row["site_id"]),
                    "region": _norm(row["region"]),
                    "action": _norm(row["action"]).casefold(),
                }
                for index, row in raw_plan.loc[dropped_plan_mask].iterrows()
            ]
            plan = candidate_plan(
                raw_plan.loc[
                    ~out_of_scope_plan_mask & ~dropped_plan_mask
                ].copy(),
                batch_kind=str(parameters["o2_batch_kind"]),
                project_week_source=str(authority["project_week_source"]),
                delivery_month_source=str(authority["delivery_month_source"]),
                planning_year=int(authority["planning_year"]),
                week_to_month=str(parameters.get("o2_week_to_month", "calendar")),
                project_start_month=int(parameters.get("o2_project_start_month", 1)),
                required_fields=authority["site_plan_required_fields"],
            )
        except ValueError as exc:
            return failed_leaf(
                context,
                "O2",
                _NAME,
                "INVALID_ARTIFACT",
                "site_plan cannot be parsed under the O2 contract",
                {"error": f"{type(exc).__name__}: {exc}"},
            )
    try:
        # Most EI final-BOM contracts carry action-local ``WK<n>`` labels and
        # are joined to the already resolved site-plan action.  Compare their
        # business schedule week and, when present, the explicit calendar year.
        # TESTTH is the exception: its ``week_num`` is a continuous project
        # coordinate, so a short final label is joined to the plan's calendar
        # week number while an explicit year must match the full identity.
        if (
            authority["delivery_month_source"] == "week-label"
            and authority["project_week_source"] == "week_num"
        ):
            final_week_identity_mode = "calendar-or-week-number"
        elif authority["delivery_month_source"] == "week-label":
            final_week_identity_mode = "hybrid-week"
        else:
            final_week_identity_mode = "schedule-week"
        material = _strict_final_bom_actions(
            authority["material_authority"],
            final,
            authority["alternatives"],
            traceability_mode=str(authority["traceability_mode"]),
            region_scope=str(authority["region_scope"]),
            final_bom_quantity_mode=str(authority["final_bom_quantity_mode"]),
            # O2 uses the authoritative/final action week to join material to
            # the schedule.  It does not re-score the redundant display month
            # columns: month-field accuracy belongs to S6 and was never part
            # of the effective-site definition (actions, BOM and interval).
            action_time_columns=False,
            week_identity_mode=final_week_identity_mode,
            planning_year=int(authority["planning_year"]),
            material_source_contract=authority["material_source_contract"],
            material_source_missing_effect=str(
                authority["material_source_missing_effect"]
            ),
        )
    except ValueError as exc:
        return failed_leaf(
            context,
            "O2",
            _NAME,
            "INVALID_ARTIFACT",
            "site_final_bom cannot be parsed under the O2 contract",
            {"error": f"{type(exc).__name__}: {exc}"},
        )

    resolved_rows: dict[str, list[pd.Series]] = defaultdict(list)
    unresolved_rows: list[pd.Series] = []
    batch_field = (
        "mocn_batch_id"
        if str(parameters.get("o2_batch_kind")) == "mocn"
        else "cluster_id"
    )
    candidate_batch_required = (
        authority["plan_mode"] == "fixed-authority"
        or batch_field in authority["site_plan_required_fields"]
    )
    for _, row in plan.iterrows():
        resolved = _resolve_site(
            row["site"],
            row["site_key"],
            authority["sites"],
            authority["names"],
        )
        if resolved is None:
            unresolved_rows.append(row)
        else:
            if not candidate_batch_required:
                row = row.copy()
                row["batch"] = authority["sites"][resolved]["batch"]
                row["batch_compare"] = authority["sites"][resolved]["batch_compare"]
            resolved_rows[resolved].append(row)

    # Rows outside the authoritative station universe remain visible as
    # diagnostics, but they are not a second station-count penalty.  O2 only
    # penalizes material errors that can be attributed to a target station by
    # making that station fail ``strict_material_valid``.  This prevents one
    # fabricated material row from both invalidating A and adding an unrelated
    # OUT unit to the curve deviation.
    plan_external_sites: dict[str, dict[str, Any]] = {}
    if authority["plan_mode"] != "fixed-authority":
        for row in plan[plan["action"] == _DELIVERY_ACTION].itertuples(index=False):
            resolved = _resolve_site(
                row.site,
                row.site_key,
                authority["complete_sites"],
                authority["complete_names"],
            )
            if resolved is None and site_identity(row.site):
                identity = site_identity(row.site)
                plan_external_sites.setdefault(
                    identity,
                    {
                        "site": str(row.site),
                        "candidate_region": str(row.region),
                        "source_rows": [],
                    },
                )["source_rows"].append(int(row.source_row))

    orphan_final_material_sites: dict[str, dict[str, Any]] = {}
    for candidate_action_key, result in material["actions"].items():
        if int(result.get("final_row_count", 0)) <= 0:
            continue
        try:
            candidate_region, site_name, candidate_action = action_key_parts(
                str(candidate_action_key)
            )
        except ValueError:
            continue
        candidate_site_key = f"{_key(candidate_region)}|{site_identity(site_name)}"
        resolved = _resolve_site(
            site_name,
            candidate_site_key,
            authority["sites"],
            authority["names"],
        )
        if resolved is not None or not site_identity(site_name):
            continue
        identity = site_identity(site_name)
        value = orphan_final_material_sites.setdefault(
            identity,
            {
                "site": str(site_name),
                "candidate_region": str(candidate_region),
                "actions": set(),
                "source_rows": [],
            },
        )
        value["actions"].add(str(candidate_action))
        value["source_rows"].extend(int(row) for row in result.get("rows", ()))

    # Interval anchors are result properties.  Both variants use the same
    # uniquely and parseably scheduled authoritative installation evidence;
    # later BOM/action failures do not contaminate another site's anchor.
    batch_install_weeks: dict[str, list[int]] = defaultdict(list)
    site_install_weeks: dict[str, int] = {}
    for site_key, site in authority["delivery_sites"].items():
        install_rows = [
            row for row in resolved_rows.get(site_key, [])
            if str(row["action"]) == _DELIVERY_ACTION
        ]
        if len(install_rows) != 1:
            continue
        row = install_rows[0]
        if (
            not row["row_contract_issues"]
            and not row["week_issue"]
            and not pd.isna(row["schedule_week"])
            and _key(row["region"]) == str(site["region_key"])
            and str(row["batch_compare"]) == str(site["batch_compare"])
        ):
            install_week = int(row["schedule_week"])
            site_install_weeks[site_key] = install_week
            batch_install_weeks[site["batch_anchor_key"]].append(install_week)
    batch_finish = {
        batch: max(weeks)
        for batch, weeks in batch_install_weeks.items()
        if weeks
    }

    # Map malformed final-BOM action rows back to a unique authoritative site;
    # they must not disappear merely because no valid action key could be built.
    unassigned_material_by_site: Counter[str] = Counter()
    orphan_unassigned_material_rows: list[dict[str, Any]] = []
    for issue in material["unassigned_row_issues"]:
        resolved = _resolve_site(
            issue.get("site", ""),
            "",
            authority["sites"],
            authority["names"],
        )
        if resolved is not None:
            unassigned_material_by_site[resolved] += 1
        else:
            orphan_unassigned_material_rows.append(dict(issue))
            identity = site_identity(issue.get("site", ""))
            if identity:
                value = orphan_final_material_sites.setdefault(
                    identity,
                    {
                        "site": str(issue.get("site", "")),
                        "candidate_region": "",
                        "actions": set(),
                        "source_rows": [],
                    },
                )
                action = _norm(issue.get("action", "")).casefold()
                if action:
                    value["actions"].add(action)
                if issue.get("row") is not None:
                    value["source_rows"].append(int(issue["row"]))

    # Candidate final-BOM actions outside a site's authoritative action set are
    # strict extras for that site.  Regionless canonicalization already maps a
    # unique candidate action to its authoritative key.
    extra_material_actions: dict[str, list[str]] = defaultdict(list)
    for candidate_action_key, result in material["actions"].items():
        if int(result.get("final_row_count", 0)) <= 0:
            continue
        try:
            candidate_region, site_name, candidate_action = action_key_parts(
                str(candidate_action_key)
            )
        except ValueError:
            continue
        candidate_site_key = f"{_key(candidate_region)}|{site_identity(site_name)}"
        resolved = _resolve_site(
            site_name,
            candidate_site_key,
            authority["sites"],
            authority["names"],
        )
        if resolved is None:
            continue
        expected_action_key = f"{resolved}|{candidate_action}"
        wrong_exact_region = (
            material["region_scope"] == "exact"
            and str(candidate_action_key) != expected_action_key
        )
        if (
            candidate_action not in authority["sites"][resolved]["actions"]
            or expected_action_key not in authority["material_authority"]
            or wrong_exact_region
        ):
            extra_material_actions[resolved].append(str(candidate_action_key))

    return {
        "plan": plan,
        "material": material,
        "resolved_rows": resolved_rows,
        "unresolved_rows": unresolved_rows,
        "plan_external_sites": plan_external_sites,
        "orphan_final_material_sites": orphan_final_material_sites,
        "batch_finish": batch_finish,
        "site_install_weeks": site_install_weeks,
        "unassigned_material_by_site": unassigned_material_by_site,
        "orphan_unassigned_material_rows": orphan_unassigned_material_rows,
        "extra_material_actions": extra_material_actions,
        "out_of_scope_plan_rows": out_of_scope_plan_rows,
        "out_of_scope_final_material_rows": out_of_scope_final_rows,
        "forbidden_action_plan_rows": forbidden_plan_rows,
        "forbidden_action_final_material_rows": forbidden_final_rows,
        "dropped_plan_rows": dropped_plan_rows,
        "dropped_final_material_rows": dropped_final_rows,
        "site_plan_adapter_validation": _public_adapter_validation(
            context,
            "site_plan",
        ),
        "final_material_adapter_validation": _public_adapter_validation(
            context,
            "final_material",
        ),
    }


def _site_result(
    site_key: str,
    site: Mapping[str, Any],
    authority: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    parameters = authority["parameters"]
    rows = candidate["resolved_rows"].get(site_key, [])
    expected_actions = set(site["actions"])
    actual_actions = Counter(str(row["action"]) for row in rows)
    reasons: list[str] = []
    action_rows: dict[str, pd.Series] = {}
    unscheduled_actions: set[str] = set()

    for action in sorted(expected_actions):
        matching = [row for row in rows if str(row["action"]) == action]
        if not matching:
            reasons.append(f"MISSING_{action.upper()}_ACTION")
        elif len(matching) > 1:
            reasons.append(f"DUPLICATE_{action.upper()}_ACTION")
        else:
            action_rows[action] = matching[0]
            reasons.extend(str(value) for value in matching[0]["row_contract_issues"])
            if str(matching[0]["status"]) == "unscheduled":
                unscheduled_actions.add(action)
                reasons.append(f"{action.upper()}_UNSCHEDULED")
            else:
                issue = str(matching[0]["week_issue"] or "")
                if issue:
                    reasons.append(f"{action.upper()}_{issue}")
                elif pd.isna(matching[0]["schedule_week"]):
                    reasons.append(f"{action.upper()}_UNPARSEABLE_WEEK")
            candidate_region = _key(matching[0]["region"])
            if candidate_region and candidate_region != str(site["region_key"]):
                reasons.append("SITE_REGION_MISMATCH")
            candidate_batch = str(matching[0]["batch_compare"])
            if candidate_batch and candidate_batch != str(site["batch_compare"]):
                reasons.append("DELIVERY_BATCH_MISMATCH")
    extras = {
        action: count
        for action, count in actual_actions.items()
        if action not in expected_actions
    }
    if extras:
        reasons.append("EXTRA_SITE_ACTION")

    for action in sorted(expected_actions):
        if action in unscheduled_actions:
            continue
        action_key = f"{site_key}|{action}"
        material_result = candidate["material"]["actions"].get(action_key)
        if not material_result or not material_result.get("strict_material_valid"):
            reasons.append(f"{action.upper()}_BOM_INVALID")
        plan_row = action_rows.get(action)
        if (
            material_result
            and int(material_result.get("final_row_count", 0)) > 0
            and plan_row is not None
            and not plan_row["week_issue"]
        ):
            week_identity_mode = candidate["material"]["week_identity_mode"]
            if week_identity_mode == "calendar-week":
                expected_week = plan_row.get("calendar_week")
                actual_weeks = set(material_result.get("calendar_weeks", ()))
                week_mismatch = (
                    expected_week is None
                    or pd.isna(expected_week)
                    or actual_weeks != {int(expected_week)}
                )
            elif week_identity_mode == "calendar-or-week-number":
                expected_calendar_week = plan_row.get("calendar_week")
                actual_week_numbers = set(
                    material_result.get("project_weeks", ())
                )
                explicit_calendar_weeks = set(
                    material_result.get("calendar_weeks", ())
                )
                week_mismatch = (
                    expected_calendar_week is None
                    or pd.isna(expected_calendar_week)
                    or actual_week_numbers
                    != {int(expected_calendar_week) % 100}
                    or (
                        bool(explicit_calendar_weeks)
                        and explicit_calendar_weeks
                        != {int(expected_calendar_week)}
                    )
                )
            else:
                expected_week = plan_row.get("schedule_week")
                actual_weeks = set(material_result.get("project_weeks", ()))
                week_mismatch = (
                    expected_week is None
                    or pd.isna(expected_week)
                    or actual_weeks != {int(expected_week)}
                )
                if week_identity_mode == "hybrid-week":
                    explicit_calendar_weeks = set(
                        material_result.get("calendar_weeks", ())
                    )
                    expected_calendar_week = plan_row.get("calendar_week")
                    if explicit_calendar_weeks and (
                        expected_calendar_week is None
                        or pd.isna(expected_calendar_week)
                        or explicit_calendar_weeks
                        != {int(expected_calendar_week)}
                    ):
                        week_mismatch = True
            if week_mismatch:
                reasons.append("FINAL_BOM_WEEK_MISMATCH")
    if candidate["unassigned_material_by_site"].get(site_key, 0):
        reasons.append("INVALID_UNASSIGNED_BOM_ROW")
    if candidate["extra_material_actions"].get(site_key):
        reasons.append("EXTRA_BOM_ACTION")

    actual_lag: int | None = None
    interval_anchor_week: int | None = None
    dismantle_week: int | None = None
    if (
        authority["plan_mode"] == "candidate-scheduled"
        and "dismantle" in expected_actions
        and "dismantle" in action_rows
        and not unscheduled_actions
    ):
        dismantle = action_rows["dismantle"]
        contract = authority["interval_contract"]
        anchor = str(contract["anchor"])
        if anchor == "site-install":
            interval_anchor_week = candidate["site_install_weeks"].get(site_key)
            missing_anchor_reason = "MISSING_SITE_INSTALL_ANCHOR"
        else:
            interval_anchor_week = candidate["batch_finish"].get(
                site["batch_anchor_key"]
            )
            missing_anchor_reason = "MISSING_BATCH_FINISH_ANCHOR"
        if (
            interval_anchor_week is not None
            and not dismantle["week_issue"]
            and not pd.isna(dismantle["schedule_week"])
        ):
            dismantle_week = int(dismantle["schedule_week"])
            actual_lag = dismantle_week - int(interval_anchor_week)
            expected_lag = int(contract["lag_weeks"])
            relation = str(contract["relation"])
            lag_valid = (
                actual_lag >= expected_lag
                if relation == "minimum"
                else actual_lag == expected_lag
            )
            if not lag_valid:
                reasons.append("INTERVAL_VIOLATION")
        else:
            reasons.append(missing_anchor_reason)

    month: int | None = None
    period: int | None = None
    submitted_month: int | None = None
    submitted_period: int | None = None
    install = action_rows.get(_DELIVERY_ACTION)
    if (
        install is not None
        and _DELIVERY_ACTION not in unscheduled_actions
        and not install["week_issue"]
        and not pd.isna(install["schedule_week"])
    ):
        month_value = install["delivery_month"]
        period_value = install["delivery_period"]
        if (
            month_value is None
            or pd.isna(month_value)
            or period_value is None
            or pd.isna(period_value)
        ):
            reasons.append("INSTALL_MONTH_UNRESOLVABLE")
        else:
            submitted_month = int(month_value)
            submitted_period = int(period_value)
            month = submitted_month
            period = submitted_period
            if authority["target_curve_mode"] == "completion-by-deadline":
                group = str(site["region_key"])
                covered_periods = set(
                    authority["target_curve_covered_periods"].get(group, ())
                )
                if submitted_period not in covered_periods:
                    reasons.append("INSTALL_OUTSIDE_DEADLINE")
                else:
                    period = int(authority["completion_buckets"][group])
                    month = period % 100

    reasons = sorted(set(reasons))
    return {
        "site_key": site_key,
        "site": str(site["site"]),
        "region": str(site["region"]),
        "group": str(site["region_key"]),
        "batch": str(site["batch"]),
        "valid": not reasons,
        "month": month,
        "period": period,
        "submitted_month": submitted_month,
        "submitted_period": submitted_period,
        "reasons": reasons,
        "candidate_action_counts": dict(sorted(actual_actions.items())),
        "extra_actions": dict(sorted(extras.items())),
        "interval_anchor": (
            str(authority["interval_contract"]["anchor"])
            if authority["plan_mode"] == "candidate-scheduled"
            else "not-applicable"
        ),
        "interval_anchor_week": interval_anchor_week,
        "dismantle_week": dismantle_week,
        "actual_lag_weeks": actual_lag,
        "source_rows": sorted(int(row["source_row"]) for row in rows),
    }


def score_o2(
    context: RuleContext,
    *,
    authority: Mapping[str, Any] | None = None,
) -> CheckResult:
    """Score O2 from adapter-normalized authority and candidate entities."""

    authority = authority or _compile_authority(context)
    candidate = _candidate_evidence(context, authority)
    if isinstance(candidate, CheckResult):
        return candidate

    prepared_master_role = authority["parameters"].get(
        "o2_prepared_master_plan_role"
    )
    prepared_master_gate: dict[str, Any] | None = None
    if isinstance(prepared_master_role, str) and prepared_master_role:
        authority_resolution = artifact(context, "master_plan")
        prepared_resolution = artifact(context, prepared_master_role)
        if (
            authority_resolution is None
            or not authority_resolution.usable
            or not isinstance(authority_resolution.table, pd.DataFrame)
        ):
            raise ValueError(
                "prepared-master comparison requires a usable tabular question "
                "master_plan authority"
            )
        if (
            prepared_resolution is None
            or not prepared_resolution.usable
            or not isinstance(prepared_resolution.table, pd.DataFrame)
        ):
            prepared_master_gate = {
                "status": "FAIL",
                "passed": False,
                "gate_rate": 0.0,
                "candidate_role": prepared_master_role,
                "candidate_status": (
                    prepared_resolution.status
                    if prepared_resolution is not None
                    else "UNRESOLVED"
                ),
                "difference_count": None,
                "differences": [],
            }
        else:
            prepared_master_gate = {
                **compare_prepared_master(
                    authority_resolution.table,
                    prepared_resolution.table,
                ),
                "candidate_role": prepared_master_role,
                "candidate_status": prepared_resolution.status,
            }

    site_results = [
        _site_result(site_key, site, authority, candidate)
        for site_key, site in sorted(authority["delivery_sites"].items())
        # Candidate-scheduled questions select alternatives from a pool.  In
        # fixed-authority mode every fixed delivery is in B and must therefore
        # be considered even when its candidate final BOM is absent.
        if authority["plan_mode"] == "fixed-authority"
        or candidate["resolved_rows"].get(site_key)
    ]
    monthly_capacity = _apply_monthly_capacity(authority, site_results)
    valid_sites = [result for result in site_results if result["valid"]]
    actual: dict[str, Counter[int]] = defaultdict(Counter)
    for result in valid_sites:
        actual[str(result["group"])][int(result["period"])] += 1

    target = authority["scaled_targets"]
    grid: list[dict[str, Any]] = []
    curve_deviation = 0
    shortfall = 0
    overage = 0
    overlap = 0
    for group in sorted(set(target) | set(actual)):
        periods = sorted(set(target.get(group, {})) | set(actual.get(group, {})))
        for period in periods:
            expected = int(target.get(group, {}).get(period, 0))
            delivered = int(actual.get(group, {}).get(period, 0))
            deviation = abs(delivered - expected)
            curve_deviation += deviation
            shortfall += max(expected - delivered, 0)
            overage += max(delivered - expected, 0)
            overlap += min(expected, delivered)
            grid.append(
                {
                    "group": group,
                    "month": int(period) % 100,
                    "year_month": f"{int(period) // 100:04d}-{int(period) % 100:02d}",
                    "target_B": expected,
                    "valid_deliveries_A": delivered,
                    "absolute_deviation": deviation,
                }
            )

    dropped_candidate_site_keys = {
        str(row["site_key"])
        for row in (
            candidate["dropped_plan_rows"]
            + candidate["dropped_final_material_rows"]
        )
    }
    denominator = int(authority["denominator"])
    actual_total = len(valid_sites)
    count_gap = abs(denominator - actual_total)
    redistribution_numerator = curve_deviation - count_gap
    if redistribution_numerator < 0 or redistribution_numerator % 2:
        raise ValueError(
            "O2 curve decomposition invariant failed: "
            "D_L1 must equal count_gap + 2 * redistribution_units"
        )
    redistribution_units = redistribution_numerator // 2
    curve_loss_units = count_gap + redistribution_units
    drop_identity_deviation = len(dropped_candidate_site_keys)
    total_loss_units = curve_loss_units + drop_identity_deviation
    raw_total_absolute_deviation = curve_deviation + drop_identity_deviation
    unclamped_rate = 1.0 - total_loss_units / denominator
    rate = max(0.0, min(1.0, unclamped_rate))
    install_only_violation = bool(
        candidate["forbidden_action_plan_rows"]
        or candidate["forbidden_action_final_material_rows"]
    )
    if install_only_violation:
        rate = 0.0
    prepared_master_violation = bool(
        prepared_master_gate is not None
        and not prepared_master_gate.get("passed", False)
    )
    if prepared_master_violation:
        rate = 0.0
    invalid_sites = [result for result in site_results if not result["valid"]]
    reason_counts = Counter(
        reason
        for result in invalid_sites
        for reason in result["reasons"]
    )
    reason_combinations = Counter(
        "+".join(result["reasons"])
        for result in invalid_sites
    )
    material_invalid_sites = [
        result
        for result in invalid_sites
        if any(
            reason.endswith("_BOM_INVALID")
            or reason in {"EXTRA_BOM_ACTION", "INVALID_UNASSIGNED_BOM_ROW"}
            for reason in result["reasons"]
        )
    ]
    material_action_reason_counts = Counter(
        reason
        for result in candidate["material"]["actions"].values()
        if not result.get("strict_material_valid")
        for reason in result.get("reasons", ())
    )
    # OUT is reserved for genuinely fictitious material codes. Legal codes
    # that are over quantity, assigned to the wrong Region/action, malformed,
    # or otherwise unmatched remain strict material failures, but are reported
    # separately and must not be mislabeled as fabricated material.
    legal_material_codes = set(authority["alternatives"])
    for options in authority["alternatives"].values():
        for _, bundle in options:
            legal_material_codes.update(str(item) for item, _ in bundle)
    fictitious_material_site_keys: set[str] = set()
    legal_but_unmatched_site_keys: set[str] = set()
    invalid_bom_row_site_keys: set[str] = set()
    for candidate_action_key, result in candidate["material"]["actions"].items():
        try:
            candidate_region, site_name, _ = action_key_parts(
                str(candidate_action_key)
            )
        except ValueError:
            continue
        candidate_site_key = (
            f"{_key(candidate_region)}|{site_identity(site_name)}"
        )
        resolved = _resolve_site(
            site_name,
            candidate_site_key,
            authority["sites"],
            authority["names"],
        )
        if resolved is None:
            continue
        unmatched_codes = {
            str(item) for item in result.get("unmatched_actual", {})
        }
        if unmatched_codes - legal_material_codes:
            fictitious_material_site_keys.add(resolved)
        if unmatched_codes & legal_material_codes:
            legal_but_unmatched_site_keys.add(resolved)
        if int(result.get("invalid_row_count", 0)) > 0:
            invalid_bom_row_site_keys.add(resolved)
    invalid_by_site_key = {
        str(result["site_key"]): result for result in invalid_sites
    }
    fictitious_material_sites = [
        invalid_by_site_key[site_key]
        for site_key in sorted(fictitious_material_site_keys)
        if site_key in invalid_by_site_key
    ]
    legal_but_unmatched_material_sites = [
        invalid_by_site_key[site_key]
        for site_key in sorted(legal_but_unmatched_site_keys)
        if site_key in invalid_by_site_key
    ]
    invalid_bom_row_sites = [
        invalid_by_site_key[site_key]
        for site_key in sorted(invalid_bom_row_site_keys)
        if site_key in invalid_by_site_key
    ]
    extra_bom_action_sites = [
        result
        for result in invalid_sites
        if "EXTRA_BOM_ACTION" in result["reasons"]
    ]
    pool_rows = [
        {
            "group": group,
            "batch": batch or None,
            "skip_pool_scope": authority.get(
                "skip_pool_scope",
                "fixed-authority",
            ),
            "install_pool_sites": int(count),
            "skip_rate": float(
                authority["parameters"].get("o2_skip_rate", 0.0)
            ),
            "target_sites": int(authority["pool_targets"][(group, batch)]),
        }
        for (group, batch), count in sorted(authority["pool_counts"].items())
    ]
    fixed_mode = authority["plan_mode"] == "fixed-authority"
    interval_contract = authority.get("interval_contract")
    interval_anchor = (
        str(interval_contract["anchor"])
        if isinstance(interval_contract, Mapping)
        else "not-applicable"
    )
    authority_pool_total = (
        denominator
        if fixed_mode
        else sum(int(value) for value in authority["pool_counts"].values())
    )
    evidence = {
        "formula": (
            "max(0, 1 - (count_gap_units + redistribution_units + "
            "drop_identity_deviation) / N)"
        ),
        "drop_identity_formula": (
            "max(0, 1 - (curve_loss_units + "
            "forbidden_dropped_site_count) / N)"
            if authority.get("drop_selection") is not None
            else "not_applicable"
        ),
        "install_only_hard_gate_formula": (
            "rate=0 when any forbidden candidate action row exists"
            if authority.get("install_only_contract")
            else "not_applicable"
        ),
        "prepared_master_hard_gate_formula": (
            "rate=0 unless candidate region/action/natural-month master totals "
            "exactly equal the historical site-action authority"
            if prepared_master_gate is not None
            else "not_applicable"
        ),
        "unit": "authoritative_install_site",
        "plan_mode": authority["plan_mode"],
        "authority_actions": list(authority["authority_actions"]),
        "target_curve_mode": authority["target_curve_mode"],
        "target_curve_covered_periods": {
            group: [
                f"{int(period) // 100:04d}-{int(period) % 100:02d}"
                for period in periods
            ]
            for group, periods in sorted(
                authority["target_curve_covered_periods"].items()
            )
        },
        "completion_buckets": {
            group: f"{int(period) // 100:04d}-{int(period) % 100:02d}"
            for group, period in sorted(authority["completion_buckets"].items())
        },
        "candidate_month_policy": (
            "immutable_question_site_plan"
            if fixed_mode
            else "candidate_install_within_authoritative_period_coverage"
            if authority["target_curve_mode"] == "completion-by-deadline"
            else "candidate_install_result"
        ),
        "monthly_capacity_gate": monthly_capacity,
        "delivery_month_source": authority["delivery_month_source"],
        "schedule_week_source": authority["project_week_source"],
        "final_bom_week_identity_mode": candidate["material"][
            "week_identity_mode"
        ],
        "interval_contract": (
            dict(interval_contract)
            if isinstance(interval_contract, Mapping)
            else None
        ),
        "interval_anchor_scope": (
            "site"
            if interval_anchor == "site-install"
            else "global_batch"
            if interval_anchor == "batch-finish"
            else "not-applicable"
        ),
        "batch_finish_scope": (
            "global_batch" if interval_anchor == "batch-finish" else "not-applicable"
        ),
        "skip_pool_scope": authority.get(
            "skip_pool_scope",
            "fixed-authority",
        ),
        "group_by": "authoritative_region",
        "delivery_action": _DELIVERY_ACTION,
        "N_target_sites": denominator,
        "B_total": denominator,
        "A_total": actual_total,
        "valid_delivery_sites": len(valid_sites),
        "candidate_selected_authority_sites": len(site_results),
        "authority_install_pool_sites": authority_pool_total,
        "intended_skipped_sites": authority_pool_total - denominator,
        "candidate_unselected_authority_sites": max(
            authority_pool_total - len(site_results),
            0,
        ),
        "candidate_selected_fraction": round(
            len(site_results) / authority_pool_total,
            12,
        ),
        "invalid_selected_sites": len(invalid_sites),
        "curve_absolute_deviation": curve_deviation,
        "drop_identity_deviation": drop_identity_deviation,
        "forbidden_dropped_site_count": len(dropped_candidate_site_keys),
        "forbidden_dropped_site_keys": sorted(dropped_candidate_site_keys),
        "drop_selection": (
            authority["drop_selection"].evidence()
            if isinstance(authority.get("drop_selection"), SeededDropSelection)
            else None
        ),
        "total_absolute_deviation": raw_total_absolute_deviation,
        "shortfall_units": shortfall,
        "overage_units": overage,
        "overlap_units": overlap,
        "count_gap_units": count_gap,
        "redistribution_units": redistribution_units,
        "curve_decomposition_identity": (
            "curve_absolute_deviation = count_gap_units + "
            "2 * redistribution_units"
        ),
        "curve_decomposition_identity_holds": True,
        "curve_loss_units": curve_loss_units,
        "total_loss_units": total_loss_units,
        "unclamped_rate": round(unclamped_rate, 12),
        "at_zero_boundary": total_loss_units == denominator,
        "clamp_truncated": total_loss_units > denominator,
        "zero_cause": (
            "not_zero"
            if rate > 0
            else "install_only_action_violation"
            if install_only_violation
            else "prepared_master_plan_mismatch"
            if prepared_master_violation
            else "no_valid_deliveries"
            if actual_total == 0
            else "loss_boundary"
            if total_loss_units == denominator
            else "loss_clamped"
        ),
        "rate": round(rate, 12),
        "pool_targets": pool_rows,
        "group_targets": dict(sorted(authority["group_targets"].items())),
        "scaled_target_grid": grid,
        "scaled_fractional_quotas": authority["scaled_quotas"],
        "largest_remainder_tie_break": (
            "month_ascending"
            if authority["target_curve_mode"] == "master-distribution"
            else "not_applicable"
        ),
        "site_validity_reason_counts": dict(sorted(reason_counts.items())),
        "site_validity_reason_counts_are_multilabel": True,
        "site_validity_reason_combination_counts": dict(
            sorted(reason_combinations.items())
        ),
        "material_invalid_site_count": len(material_invalid_sites),
        "material_action_failure_reason_counts": dict(
            sorted(material_action_reason_counts.items())
        ),
        "fictitious_material_invalid_site_count": len(
            fictitious_material_sites
        ),
        "fictitious_material_invalid_site_examples": (
            fictitious_material_sites[:50]
        ),
        "legal_but_unmatched_material_site_count": len(
            legal_but_unmatched_material_sites
        ),
        "legal_but_unmatched_material_site_examples": (
            legal_but_unmatched_material_sites[:50]
        ),
        "extra_bom_action_site_count": len(extra_bom_action_sites),
        "extra_bom_action_site_examples": extra_bom_action_sites[:50],
        "invalid_bom_row_site_count": len(invalid_bom_row_sites),
        "invalid_bom_row_site_examples": invalid_bom_row_sites[:50],
        "invalid_site_examples": invalid_sites[:50],
        "valid_site_examples": valid_sites[:50],
        "non_scoring_plan_external_site_count": len(
            candidate["plan_external_sites"]
        ),
        "non_scoring_plan_external_score_effect": "none",
        "non_scoring_plan_external_sites": sorted(
            candidate["plan_external_sites"].values(),
            key=lambda value: site_identity(value["site"]),
        )[:50],
        "non_scoring_orphan_final_material_site_count": len(
            candidate["orphan_final_material_sites"]
        ),
        "non_scoring_orphan_final_material_score_effect": "none",
        "non_scoring_orphan_final_material_sites": [
            {
                **value,
                "actions": sorted(value["actions"]),
                "source_rows": sorted(set(value["source_rows"])),
            }
            for value in sorted(
                candidate["orphan_final_material_sites"].values(),
                key=lambda item: site_identity(item["site"]),
            )[:50]
        ],
        "non_scoring_orphan_final_material_row_count": len(
            candidate["orphan_unassigned_material_rows"]
        ),
        "non_scoring_orphan_final_material_rows": candidate[
            "orphan_unassigned_material_rows"
        ][:50],
        "out_of_scope_plan_action_row_count": len(
            candidate["out_of_scope_plan_rows"]
        ),
        "out_of_scope_plan_action_rows": candidate[
            "out_of_scope_plan_rows"
        ][:50],
        "out_of_scope_final_material_row_count": len(
            candidate["out_of_scope_final_material_rows"]
        ),
        "out_of_scope_final_material_rows": candidate[
            "out_of_scope_final_material_rows"
        ][:50],
        "install_only_contract": (
            {
                key: list(values)
                for key, values in sorted(
                    (authority.get("install_only_contract") or {}).items()
                )
            }
            if authority.get("install_only_contract")
            else None
        ),
        "install_only_hard_gate_triggered": install_only_violation,
        "prepared_master_hard_gate_triggered": prepared_master_violation,
        "prepared_master_comparison": prepared_master_gate,
        "forbidden_action_plan_row_count": len(
            candidate["forbidden_action_plan_rows"]
        ),
        "forbidden_action_plan_rows": candidate[
            "forbidden_action_plan_rows"
        ][:50],
        "forbidden_action_final_material_row_count": len(
            candidate["forbidden_action_final_material_rows"]
        ),
        "forbidden_action_final_material_rows": candidate[
            "forbidden_action_final_material_rows"
        ][:50],
        "dropped_plan_row_count": len(candidate["dropped_plan_rows"]),
        "dropped_plan_rows": candidate["dropped_plan_rows"][:50],
        "dropped_final_material_row_count": len(
            candidate["dropped_final_material_rows"]
        ),
        "dropped_final_material_rows": candidate[
            "dropped_final_material_rows"
        ][:50],
        "unscored_pure_dismantle_site_count": len(authority["pure_dismantle"]),
        "unscored_pure_dismantle_sites": authority["pure_dismantle"][:50],
        "unresolved_noninstall_plan_rows": sum(
            str(row["action"]) != _DELIVERY_ACTION
            for row in candidate["unresolved_rows"]
        ),
        "expected_source_actions": int(authority["expected_source_actions"]),
        "scoped_authority_actions": int(authority["expected_actions"]),
        "scope_material_mode": authority["scope_material_mode"],
        "substitution_mode": authority["substitution_mode"],
        "substitution_catalog": authority["substitution_catalog_summary"],
        "install_material_policy": "authority-substitution-catalog",
        "dismantle_material_policy": "exact-authority-original",
        "traceability_mode": candidate["material"]["traceability_mode"],
        "region_scope": candidate["material"]["region_scope"],
        "final_bom_quantity_mode": candidate["material"]["final_bom_quantity_mode"],
        "final_bom_submitted_sign_counts": candidate["material"][
            "final_bom_submitted_sign_counts"
        ],
        "final_bom_normalization": candidate["material"][
            "final_bom_normalization"
        ],
        "material_source_contract": candidate["material"][
            "material_source_contract"
        ],
        "material_source_missing_effect": candidate["material"][
            "material_source_missing_effect"
        ],
        "missing_material_source_row_count": int(
            candidate["material"]["missing_material_source_row_count"]
        ),
        "missing_material_source_examples": candidate["material"][
            "missing_material_source_examples"
        ],
        "invalid_material_source_row_count": int(
            candidate["material"]["invalid_material_source_row_count"]
        ),
        "invalid_material_source_examples": candidate["material"][
            "invalid_material_source_examples"
        ],
        "site_plan_adapter_validation": candidate[
            "site_plan_adapter_validation"
        ],
        "final_material_adapter_validation": candidate[
            "final_material_adapter_validation"
        ],
        "strict_bom_invalid_rows": int(candidate["material"]["invalid_final_rows"])
        + len(candidate["material"]["unassigned_row_issues"]),
    }
    return leaf(
        context,
        "O2",
        _NAME,
        rate,
        (
            "Compare result-valid sites with the immutable question site plan; "
            "final material and its action time determine whether a fixed site enters A"
            if fixed_mode
            else "Compare valid delivered sites with the g-scaled authoritative "
            "master curve; action, time, interval, and strict material validity filter A"
        ),
        evidence,
        reason_code=(
            ""
            if math.isclose(rate, 1.0)
            else "INSTALL_ONLY_ACTION_VIOLATION"
            if install_only_violation
            else "PREPARED_MASTER_PLAN_MISMATCH"
            if prepared_master_violation
            else "DROP_IDENTITY_MISMATCH"
            if drop_identity_deviation
            else "EFFECTIVE_DELIVERY_DEVIATION"
        ),
    )
