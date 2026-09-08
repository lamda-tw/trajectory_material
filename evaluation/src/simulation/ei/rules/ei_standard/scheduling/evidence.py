"""Rule-scoped scheduling evidence prepared without cross-rule short circuits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from simulation.ei.core.models import RuleContext

from .._shared import normalized, table
from ..batching import BatchLookup, assert_question_region_consistency
from ..common import _delivery_batches, _expected_actions, _master_plan, _months_from_frame
from ..drop_selection import SeededDropSelection, compile_seeded_drop_selection
from .parsing import batch_for


_RULE_DEPENDENCIES: dict[str, frozenset[str]] = {
    "C1": frozenset({"scope_input"}),
    "C2": frozenset({"scope_input"}),
    "C3": frozenset({"calendar", "master_plan"}),
    "C4": frozenset({"calendar", "master_plan"}),
    "C5": frozenset({"scope_input", "batch_input"}),
    "C6a": frozenset({"batch_input"}),
    "C6b": frozenset({"batch_input"}),
}


@dataclass(frozen=True)
class SchedulingEvidence:
    plan: pd.DataFrame
    parameters: Mapping[str, Any]
    site_scope: str
    batch_map: Mapping[str, str]
    batch_rows: list[dict[str, object]]
    expected: pd.DataFrame
    source_action_count: int
    excluded_action_count: int
    expected_sites: set[str]
    actual_sites: set[str]
    master_by_region: dict[tuple[str, int], float]
    installs: pd.DataFrame
    drop_selection: SeededDropSelection | None = None


@dataclass(frozen=True)
class SchedulingAuthority:
    parameters: Mapping[str, Any]
    site_scope: str
    batch_map: Mapping[str, str]
    batch_rows: tuple[dict[str, object], ...]
    expected: pd.DataFrame
    source_action_count: int
    excluded_action_count: int
    master_by_region: dict[tuple[str, int], float]
    planning_year: int
    failures: Mapping[str, Exception]
    drop_selection: SeededDropSelection | None = None


def prepare_scheduling_authority(context: RuleContext) -> SchedulingAuthority:
    """Compile candidate-independent scheduling evidence once per question."""

    configured = {check.check_id.split(".", 1)[1] for check in context.component.checks}
    parameters = context.component.parameters
    site_scope = str(parameters.get("site_scope", "all_material_sites"))
    failures: dict[str, Exception] = {}

    scope_rules = {"C1", "C2", "C5"} & configured
    master_rules = {"C3", "C4"} & configured
    batch_rules = {"C5", "C6a", "C6b"} & configured
    if parameters.get("drop_selection_contract") is not None and scope_rules:
        batch_rules.update(scope_rules)
    if scope_rules and site_scope == "batch_intersection":
        batch_rules.update(scope_rules)

    batch_map: Mapping[str, str] = BatchLookup({})
    batch_rows: list[dict[str, object]] = []
    normalized_batch_input: pd.DataFrame | None = None
    if batch_rules:
        try:
            batch_input = table(context, "batch_input")
            if batch_input is None:
                raise FileNotFoundError(
                    "configured authoritative delivery batch input is missing"
                )
            batch_map, batch_rows = _delivery_batches(
                batch_input,
                batch_kind=str(parameters["batch_kind"]),
            )
            normalized_batch_input = normalized(context, "batch_input")
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["batch_input"] = exc

    expected = pd.DataFrame()
    source_action_count = 0
    excluded_action_count = 0
    if scope_rules:
        try:
            scope_input = table(context, "scope_input")
            if scope_input is None:
                raise FileNotFoundError("configured authoritative scope input is missing")
            normalized_scope_input = normalized(context, "scope_input")
            if normalized_batch_input is not None:
                assert_question_region_consistency(
                    normalized_scope_input,
                    normalized_batch_input,
                )
            expected = _expected_actions(scope_input)
            source_action_count = len(expected)
            if site_scope == "batch_intersection":
                if "batch_input" not in failures:
                    expected = expected[
                        expected["site_key"].map(
                            lambda value: batch_for(str(value), batch_map) is not None
                        )
                    ].copy()
                    if expected.empty:
                        raise ValueError(
                            "material and delivery batch inputs have no common site actions"
                        )
            elif site_scope != "all_material_sites":
                raise ValueError(f"unsupported scheduling site_scope: {site_scope}")
            excluded_action_count = source_action_count - len(expected)
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["scope_input"] = exc

    drop_selection: SeededDropSelection | None = None
    drop_contract = parameters.get("drop_selection_contract")
    if (
        drop_contract is not None
        and scope_rules
        and "scope_input" not in failures
        and "batch_input" not in failures
    ):
        try:
            drop_selection = compile_seeded_drop_selection(
                expected,
                batch_map,
                batch_kind=str(parameters["batch_kind"]),
                drop_rate=float(parameters["skip_rate"]),
                pool_scope=str(parameters["skip_pool_scope"]),
                contract=drop_contract,
            )
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["drop_selection"] = exc

    planning_year = 2027
    if master_rules:
        try:
            planning_year = int(parameters.get("planning_year", 2027))
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["calendar"] = exc

    master_by_region: dict[tuple[str, int], float] = {}
    if master_rules and "calendar" not in failures:
        try:
            master_format = str(parameters.get("master_format", "standard"))
            master_input = (
                normalized(context, "master_plan")
                if master_format == "site-action-weekly-install"
                else table(context, "master_plan")
            )
            if master_input is None:
                raise FileNotFoundError(
                    "configured authoritative master plan is missing"
                )
            master_by_region, _ = _master_plan(
                master_input,
                sheet_hint=str(parameters.get("master_sheet_hint", "")),
                planning_year=planning_year,
                master_format=master_format,
            )
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["master_plan"] = exc

    return SchedulingAuthority(
        parameters=parameters,
        site_scope=site_scope,
        batch_map=batch_map,
        batch_rows=tuple(batch_rows),
        expected=expected,
        source_action_count=source_action_count,
        excluded_action_count=excluded_action_count,
        master_by_region=master_by_region,
        planning_year=planning_year,
        failures=failures,
        drop_selection=drop_selection,
    )


def prepare_scheduling_evidence(
    context: RuleContext,
    plan: pd.DataFrame,
    *,
    authority: SchedulingAuthority | None = None,
) -> tuple[SchedulingEvidence, dict[str, Exception]]:
    """Prepare only selected evidence families and retain family-local errors."""

    configured = {check.check_id.split(".", 1)[1] for check in context.component.checks}
    master_rules = {"C3", "C4"} & configured
    if authority is None:
        authority = prepare_scheduling_authority(context)
    parameters = authority.parameters
    failures = dict(authority.failures)
    plan = plan.copy()
    plan["month"] = pd.NA
    if master_rules and "calendar" not in failures:
        try:
            plan["month"] = _months_from_frame(
                plan,
                authority.planning_year,
                week_to_month=str(parameters.get("week_to_month", "calendar")),
                project_start_month=int(parameters.get("project_start_month", 1)),
            )
        except Exception as exc:  # noqa: BLE001 - retained for dependent leaves
            failures["calendar"] = exc

    expected = authority.expected
    expected_sites = set(expected["site_key"]) if not expected.empty else set()
    actual_sites = set(plan["site_key"])
    return (
        SchedulingEvidence(
            plan=plan,
            parameters=parameters,
            site_scope=authority.site_scope,
            batch_map=authority.batch_map,
            batch_rows=list(authority.batch_rows),
            expected=expected,
            source_action_count=authority.source_action_count,
            excluded_action_count=authority.excluded_action_count,
            expected_sites=expected_sites,
            actual_sites=actual_sites,
            master_by_region=authority.master_by_region,
            installs=plan[
                (plan["action"] == "install")
                & (plan["status"] != "unscheduled")
            ],
            drop_selection=authority.drop_selection,
        ),
        failures,
    )


def scheduling_evidence_failure(
    rule_id: str,
    evidence: SchedulingEvidence,
    failures: Mapping[str, Exception],
) -> Exception | None:
    """Return one diagnostic exception only when this rule needs failed evidence."""

    dependencies = set(_RULE_DEPENDENCIES.get(rule_id, ()))
    if rule_id in {"C1", "C2"} and evidence.site_scope == "batch_intersection":
        dependencies.add("batch_input")
    if (
        rule_id in {"C1", "C2", "C5"}
        and evidence.parameters.get("drop_selection_contract") is not None
    ):
        dependencies.update(("batch_input", "drop_selection"))
    selected = [
        (dependency, failures[dependency])
        for dependency in sorted(dependencies)
        if dependency in failures
    ]
    if not selected:
        return None
    details = "; ".join(
        f"{dependency}: {type(exc).__name__}: {exc}"
        for dependency, exc in selected
    )
    return RuntimeError(f"scheduling evidence unavailable for {rule_id}: {details}")
