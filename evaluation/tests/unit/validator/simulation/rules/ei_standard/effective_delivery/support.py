from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

import pandas as pd

from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.core.adapters.products import normalize_product


PROMPT_REFS = ("prompt/test.txt:L1",)


def scope_frame(
    rows: Iterable[tuple[str, str, str, str, int]],
) -> pd.DataFrame:
    """Build authoritative site/action material rows.

    Each row is ``(region, site, action, item, quantity)``.  Dismantle
    quantities are supplied as positive physical quantities because the Prompt
    input contract uses a dedicated dismantle column.
    """

    values = []
    for region, site, action, item, quantity in rows:
        if action not in {"install", "dismantle"}:
            raise ValueError(f"unsupported fixture action: {action}")
        values.append(
            {
                "SITE ID": site,
                "REGION": region,
                "ITEM CODE": item,
                "NEW": quantity if action == "install" else 0,
                "REDEPLOY": 0,
                "DISMANTLE": quantity if action == "dismantle" else 0,
            }
        )
    return pd.DataFrame(
        values,
        columns=("SITE ID", "REGION", "ITEM CODE", "NEW", "REDEPLOY", "DISMANTLE"),
    )


def batch_frame(
    rows: Iterable[tuple[str, str, object]],
    *,
    batch_kind: str = "cluster",
) -> pd.DataFrame:
    """Build authoritative Cluster or base-PK MOCN batch rows."""

    if batch_kind not in {"cluster", "mocn"}:
        raise ValueError(f"unsupported fixture batch kind: {batch_kind}")
    batch_column = "cluster" if batch_kind == "cluster" else "mocn_batch"

    return pd.DataFrame(
        (
            {"region": region, "site_name": site, batch_column: batch}
            for region, site, batch in rows
        ),
        columns=("region", "site_name", batch_column),
    )


def master_frame(curves: Mapping[str, Mapping[int, float]]) -> pd.DataFrame:
    """Build Region/month authoritative curve rows."""

    return pd.DataFrame(
        (
            {"region": region, "month": month, "master_count": value}
            for region, curve in curves.items()
            for month, value in curve.items()
        ),
        columns=("region", "month", "master_count"),
    )


def plan_frame(
    rows: Iterable[tuple[str, str, str, int]],
    *,
    planning_year: int = 2027,
    batch_kind: str = "cluster",
    delivery_batch: object | None = None,
) -> pd.DataFrame:
    """Build strict candidate ``(region, site, action, project_week)`` rows.

    The base-PK candidate contract carries both the integer project week and
    its ISO-week Monday.  Tests that exercise malformed values should mutate a
    valid frame explicitly, so ordinary fixtures cannot accidentally omit a
    required delivery field.
    """

    if batch_kind not in {"cluster", "mocn"}:
        raise ValueError(f"unsupported fixture batch kind: {batch_kind}")
    batch_column = "cluster" if batch_kind == "cluster" else "mocn_batch"
    batch_value = (
        delivery_batch
        if delivery_batch is not None
        else "C1" if batch_kind == "cluster" else 1
    )

    return pd.DataFrame(
        (
            {
                "region": region,
                batch_column: batch_value,
                "site_name": site,
                "site_action": action,
                "project_week": week,
                "week_start": date.fromisocalendar(
                    planning_year,
                    week,
                    1,
                ).isoformat(),
                "status": "scheduled",
                "site_count": 1,
            }
            for region, site, action, week in rows
        ),
        columns=(
            "region",
            batch_column,
            "site_name",
            "site_action",
            "project_week",
            "week_start",
            "status",
            "site_count",
        ),
    )


def final_frame(
    rows: Iterable[tuple[str, str, str, str, int, str, int]],
) -> pd.DataFrame:
    """Build strict final-BOM rows, including the candidate action week."""

    return pd.DataFrame(
        (
            {
                "region": region,
                "site_name": site,
                "action": action,
                "item_code": item,
                "required_qty": quantity,
                "original_bom": original,
                "original_bom_qty": abs(quantity),
                "project_week": project_week,
            }
            for (
                region,
                site,
                action,
                item,
                quantity,
                original,
                project_week,
            ) in rows
        ),
        columns=(
            "region",
            "site_name",
            "action",
            "item_code",
            "required_qty",
            "original_bom",
            "original_bom_qty",
            "project_week",
        ),
    )


def _resolution(
    role: str,
    frame: pd.DataFrame,
    parameters: Mapping[str, object],
) -> ArtifactResolution:
    normalized, issues = normalize_product(
        role,
        "",
        frame,
        {"_effective_delivery": dict(parameters)},
    )
    return ArtifactResolution(
        role=role,
        status="SELECTED_CANONICAL",
        selected_path=Path(f"{role}.csv"),
        table=frame,
        normalized=normalized,
        validation_issues=issues,
    )


def o2_context(
    *,
    scope: pd.DataFrame,
    batches: pd.DataFrame,
    master: pd.DataFrame,
    plan: pd.DataFrame,
    final: pd.DataFrame,
    parameters: Mapping[str, object] | None = None,
    substitution_source: pd.DataFrame | None = None,
    prepared_master: pd.DataFrame | None = None,
) -> RuleContext:
    """Create a standalone O2 context with no legacy five-check components."""

    values: dict[str, object] = {
        "o2_group_by": "region",
        "o2_delivery_action": "install",
        "o2_planning_year": 2027,
        "o2_site_scope": "batch_intersection",
        "o2_batch_kind": "cluster",
        "o2_skip_rate": 0.0,
        "o2_skip_pool_scope": "region-batch",
        "o2_interval_contract": {
            "anchor": "batch-finish",
            "relation": "minimum",
            "lag_weeks": 2,
        },
        "o2_substitution_mode": "identity-only",
        "o2_traceability_mode": "explicit-origin",
        "o2_region_scope": "exact",
        "o2_scope_material_mode": "raw",
        "o2_final_bom_quantity_mode": "absolute",
        "o2_project_week_source": "reconcile",
        "o2_delivery_month_source": "week-start",
        "o2_site_plan_required_fields": [
            "site_id",
            "region",
            "action",
            "project_week",
            "week_start",
            "status",
            "site_count",
            "cluster_id",
        ],
        "o2_week_to_month": "calendar",
        "o2_project_start_month": 1,
        "o2_master_format": "standard",
    }
    values.update(parameters or {})
    if not parameters or "o2_site_plan_required_fields" not in parameters:
        required = [
            value
            for value in values["o2_site_plan_required_fields"]
            if value not in {"cluster_id", "mocn_batch_id"}
        ]
        required.append(
            "mocn_batch_id"
            if values["o2_batch_kind"] == "mocn"
            else "cluster_id"
        )
        values["o2_site_plan_required_fields"] = required
    component = ComponentConfig(
        name="effective-delivery",
        scorer="ei.effective-delivery",
        checks=(CheckConfig("effective-delivery.O2", PROMPT_REFS),),
        parameters=values,
    )
    frames = {
        "scope_input": scope,
        "batch_input": batches,
        "master_plan": master,
        "site_plan": plan,
        "final_material": final,
    }
    if substitution_source is not None:
        frames["substitution_source"] = substitution_source
    if prepared_master is not None:
        frames["prepared_master_plan"] = prepared_master
    question_roles = {
        "scope_input",
        "batch_input",
        "master_plan",
        "substitution_source",
    }
    specs = {
        role: ArtifactSpec(
            role=role,
            source="question" if role in question_roles else "candidate",
            path=f"{role}.csv",
            filenames=() if role in question_roles else (f"{role}.csv",),
        )
        for role in frames
    }
    profile = QuestionProfile(
        question_id="Q-O2",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts=specs,
        components={"effective-delivery": component},
        path=Path("validator.yaml"),
    )
    return RuleContext(
        question=profile,
        component=component,
        artifacts=ArtifactBundle(
            run_dir=Path("run"),
            artifact_roots=(),
            artifacts={
                role: _resolution(role, frame, values)
                for role, frame in frames.items()
            },
        ),
    )


def fixed_o2_context(
    *,
    scope: pd.DataFrame,
    plan: pd.DataFrame,
    final: pd.DataFrame,
    parameters: Mapping[str, object] | None = None,
    substitution_source: pd.DataFrame | None = None,
) -> RuleContext:
    """Create an easy-style fixed-authority O2 context."""

    values: dict[str, object] = {
        "o2_plan_mode": "fixed-authority",
        "o2_group_by": "region",
        "o2_delivery_action": "install",
        "o2_planning_year": 2027,
        "o2_site_scope": "fixed-site-plan",
        "o2_substitution_mode": "identity-only",
        "o2_traceability_mode": "explicit-origin",
        "o2_region_scope": "exact",
        "o2_scope_material_mode": "raw",
        "o2_final_bom_quantity_mode": "absolute",
        "o2_project_week_source": "reconcile",
        "o2_delivery_month_source": "week-label",
        "o2_site_plan_required_fields": [
            "site_id",
            "region",
            "action",
            "week_num",
            "week_label",
            "site_count",
        ],
        "o2_week_to_month": "calendar",
    }
    values.update(parameters or {})
    component = ComponentConfig(
        name="effective-delivery",
        scorer="ei.effective-delivery",
        checks=(CheckConfig("effective-delivery.O2", PROMPT_REFS),),
        parameters=values,
    )
    frames = {
        "scope_input": scope,
        "site_plan": plan,
        "final_material": final,
    }
    if substitution_source is not None:
        frames["substitution_source"] = substitution_source
    question_roles = {"scope_input", "site_plan", "substitution_source"}
    specs = {
        role: ArtifactSpec(
            role=role,
            source="question" if role in question_roles else "candidate",
            path=f"{role}.csv",
            filenames=() if role in question_roles else (f"{role}.csv",),
        )
        for role in frames
    }
    profile = QuestionProfile(
        question_id="Q-O2-FIXED",
        ruleset_release="4.13.0",
        artifact_roots=("output",),
        artifacts=specs,
        components={"effective-delivery": component},
        path=Path("validator.yaml"),
    )
    return RuleContext(
        question=profile,
        component=component,
        artifacts=ArtifactBundle(
            run_dir=Path("run"),
            artifact_roots=(),
            artifacts={
                role: _resolution(role, frame, values)
                for role, frame in frames.items()
            },
        ),
    )


def fixed_plan_frame(
    rows: Iterable[tuple[str, str, str, int]],
    *,
    planning_year: int = 2027,
) -> pd.DataFrame:
    """Build immutable question-plan rows without candidate-only columns."""

    return pd.DataFrame(
        (
            {
                "site_name": site,
                "site_action": action,
                "mos_weekly_plan": f"{planning_year}WK{week}",
                "week_num": week,
                "region": region,
                "site_count": 1,
            }
            for region, site, action, week in rows
        )
    )


def fixed_final_frame(
    rows: Iterable[tuple[str, str, str, str, int, str, int]],
    *,
    planning_year: int = 2027,
) -> pd.DataFrame:
    """Build the easy final-BOM action-week/month contract."""

    values = []
    for region, site, action, item, quantity, original, project_week in rows:
        month = date.fromisocalendar(planning_year, project_week, 1).month
        values.append(
            {
                "site_name": site,
                "install_month": month if action == "install" else "",
                "install_wk_label": (
                    f"{planning_year}WK{project_week}"
                    if action == "install"
                    else ""
                ),
                "dismantle_month": month if action == "dismantle" else "",
                "dismantle_wk_label": (
                    f"{planning_year}WK{project_week}"
                    if action == "dismantle"
                    else ""
                ),
                "item_code": item,
                "required_qty": quantity,
                "original_bom": original,
                "original_bom_qty": abs(quantity),
                "region": region,
                "action": action,
            }
        )
    return pd.DataFrame(values)
