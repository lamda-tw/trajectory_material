"""Release preflight and direct evidence dependencies for EI leaves."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from simulation.ei.core.config import load_profile


ARTIFACT_ROLES: dict[str, tuple[str, ...]] = {
    "effective-delivery.O2": (
        "site_plan", "scope_input", "master_plan", "batch_input", "final_material",
    ),
    "scheduling.C4": ("site_plan", "scope_input", "master_plan"),
    "scheduling.C6a": ("site_plan", "batch_input"),
    "scheduling.C6b": ("site_plan", "batch_input"),
    "simulation.S1": (
        "substitution_source", "material_substitution", "scope_input", "final_material",
    ),
    "simulation.S2": (),
    "simulation.S3": (),
    "simulation.S4": ("new_warehouse",),
    "simulation.S5": (
        "substitution_source", "material_substitution", "scope_input", "final_material", "site_plan",
    ),
    "simulation.S6": ("final_material", "site_plan"),
    "reuse-accounting.R6": ("reuse_by_region",),
}


def artifact_roles_for_checks(
    profile: Any,
    check_ids: tuple[str, ...],
) -> tuple[str, ...]:
    roles = {role for check_id in check_ids for role in ARTIFACT_ROLES[check_id]}
    scheduling = profile.components.get("scheduling")
    if scheduling is not None and "scheduling.C4" in check_ids:
        if scheduling.parameters.get("site_scope") == "batch_intersection":
            roles.add("batch_input")
    effective_delivery = profile.components.get("effective-delivery")
    if effective_delivery is not None and "effective-delivery.O2" in check_ids:
        if effective_delivery.parameters.get("o2_plan_mode") == "fixed-authority":
            roles.difference_update(("master_plan", "batch_input"))
        if effective_delivery.parameters.get("o2_substitution_mode") != "identity-only":
            roles.add("substitution_source")
        prepared_master_role = effective_delivery.parameters.get(
            "o2_prepared_master_plan_role"
        )
        if isinstance(prepared_master_role, str) and prepared_master_role:
            roles.add(prepared_master_role)
    simulation = profile.components.get("simulation")
    if simulation is not None:
        parameters = simulation.parameters
        simulation_ids = set(check_ids) & {
            "simulation.S1", "simulation.S2", "simulation.S3",
            "simulation.S4", "simulation.S5", "simulation.S6",
        }
        default_mode = str(parameters.get("simulation_evidence_mode", "warehouse"))
        modes = {
            rule_id: str(parameters.get(f"{rule_id.casefold()}_evidence_mode", default_mode))
            for rule_id in ("S2", "S3")
        }
        if any(
            f"simulation.{rule_id}" in simulation_ids and modes[rule_id] == "gap-wide"
            for rule_id in modes
        ):
            roles.add(str(parameters.get("gap_role", "gap")))
        if "simulation.S2" in simulation_ids and modes["S2"] == "gap-wide":
            roles.update(("reuse_warehouse", "site_material_timeline", "recovered_supply"))
        if "simulation.S2" in simulation_ids and modes["S2"] == "warehouse":
            roles.update(
                ("reuse_warehouse", "site_material_timeline", "recovered_supply", "initial_inventory_source")
            )
        if "simulation.S3" in simulation_ids and modes["S3"] == "warehouse":
            roles.update(parameters.get("s3_required_roles", ()))
        if "simulation.S4" in simulation_ids:
            roles.add("new_warehouse")
        warehouse_week_contracts = parameters.get("warehouse_week_contracts")
        if isinstance(warehouse_week_contracts, dict):
            roles.update(
                str(role) for role in warehouse_week_contracts
            )
            if any(
                isinstance(contract, dict)
                and contract.get("source") == "site-plan"
                for contract in warehouse_week_contracts.values()
            ):
                roles.add("site_plan")
        gap_week_contract = parameters.get("gap_week_contract")
        if (
            isinstance(gap_week_contract, dict)
            and simulation_ids & {
                "simulation.S2",
                "simulation.S3",
                "simulation.S4",
            }
        ):
            roles.add(str(parameters.get("gap_role", "gap")))
            if gap_week_contract.get("source") == "site-plan":
                roles.add("site_plan")
        if (
            isinstance(parameters.get("gap_zero_business_metrics"), list)
            and simulation_ids & {"simulation.S2", "simulation.S3"}
        ):
            roles.add(str(parameters.get("gap_role", "gap")))
        site_rollout_week_contract = parameters.get(
            "site_rollout_week_contract"
        )
        if (
            isinstance(site_rollout_week_contract, dict)
            and simulation_ids & {
                "simulation.S2",
                "simulation.S3",
                "simulation.S4",
            }
        ):
            roles.update(("site_rollout", "site_plan"))
    return tuple(sorted(role for role in roles if role in profile.artifacts))


_artifact_roles_for_checks = artifact_roles_for_checks


def validate_release_contracts(repo: Path, questions: tuple[str, ...]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    component_count = 0
    artifact_binding_count = 0
    for question in questions:
        try:
            profile = load_profile(question, repo=repo)
        except Exception as exc:  # noqa: BLE001
            errors.append({"question": question, "message": f"{type(exc).__name__}: {exc}"})
            continue
        component_count += len(profile.components)
        artifact_binding_count += len(profile.artifacts)
        candidate = (repo / "eval_results" / "__candidate__").resolve()
        for root in profile.artifact_roots:
            if not (candidate / root).resolve().is_relative_to(candidate):
                errors.append(
                    {"question": question, "message": f"artifact root escapes run: {root}"}
                )
    return {
        "passed": not errors,
        "errors": errors,
        "component_count": component_count,
        "artifact_binding_count": artifact_binding_count,
    }
