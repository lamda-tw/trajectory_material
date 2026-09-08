"""Adapter contract for the standard ``final_material`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .._shared import _issue, _norm, parse_iso_week, parse_project_week
from ._canonical import TabularSource, project_columns, select_frame

NormalizedFinalMaterial = pd.DataFrame


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedFinalMaterial, tuple[dict[str, Any], ...]]:
    del options
    fields = {
        "site_id": (
            "site_name",
            "site name",
            "site id",
            "site id radio",
            "site id radio/站点",
        ),
        "region": ("region", "region/区域", "区域"),
        "action": ("site_action", "site action", "action"),
        "item_code": ("item_code", "item code", "bom", "bom code"),
        "quantity": ("required_qty", "required qty", "quantity"),
        "material_source": (
            "material_source",
            "material source",
            "material source/物料来源",
            "物料来源",
        ),
        "original_item_code": (
            "original_bom",
            "original bom",
            "original_item_code",
            "original item code",
        ),
        "original_quantity": (
            "original_bom_qty",
            "original bom qty",
            "original_quantity",
            "original quantity",
        ),
        "project_week": ("project_week", "project week", "week_num", "week num"),
        "install_week": ("install_wk_label", "install week", "install_week"),
        "install_month": ("install_month", "install month"),
        "dismantle_week": (
            "dismantle_wk_label",
            "dismantle week",
            "dismantle_week",
        ),
        "dismantle_month": ("dismantle_month", "dismantle month"),
    }
    raw, sheet, selection_issues = select_frame(
        frame,
        (fields["site_id"], fields["action"], fields["item_code"], fields["quantity"]),
    )
    normalized, issues = project_columns(
        raw,
        fields,
        required=("site_id", "region", "action", "item_code", "quantity"),
        source_sheet=sheet,
    )
    # Easy contracts expose one week column per action instead of a generic
    # project_week.  Canonicalize that row-level choice here while retaining the
    # two physical source fields for auditability.
    normalized["project_week"] = normalized["project_week"].astype(object)
    missing_week = normalized["project_week"].map(_norm).eq("")
    actions = normalized["action"].map(lambda value: _norm(value).casefold())
    install_rows = missing_week & actions.eq("install")
    dismantle_rows = missing_week & actions.eq("dismantle")
    def action_week(value: Any) -> Any:
        try:
            return parse_project_week(value)
        except ValueError:
            try:
                return parse_iso_week(value) % 100
            except ValueError:
                return value

    normalized.loc[install_rows, "project_week"] = normalized.loc[
        install_rows, "install_week"
    ].map(action_week)
    normalized.loc[dismantle_rows, "project_week"] = normalized.loc[
        dismantle_rows, "dismantle_week"
    ].map(action_week)
    if not normalized.empty and not normalized["project_week"].map(_norm).any():
        issues += (
            _issue(
                "MISSING_CANONICAL_COLUMN",
                "final material lacks a canonical project-week value",
                column="project_week",
            ),
        )
    return normalized, selection_issues + issues


__all__ = ["NormalizedFinalMaterial", "normalize"]
