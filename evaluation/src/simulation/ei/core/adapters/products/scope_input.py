"""Canonical adapter for the authoritative site/BOM scope input."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .._shared import _norm
from ._canonical import (
    TabularSource,
    effective_delivery_options,
    exact_column,
    project_columns,
    select_frame,
)


NormalizedScopeInput = pd.DataFrame


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedScopeInput, tuple[dict[str, Any], ...]]:
    parameters = effective_delivery_options(options)
    fields = {
        "site_id": (
            "site_name",
            "site name",
            "site id",
            "site id radio",
            "site id radio/站点",
            "du id",
            "*du id",
            "*du id 站点 id",
        ),
        "region": ("region", "region/区域", "区域"),
        "year": ("year", "年份"),
        "item_code": (
            "item_code",
            "item code",
            "*物料编码",
            "*bom/编码",
            "bom code",
        ),
        "band": ("band", "频段"),
        "ntnr": ("ntnr", "nTnR"),
        "action": ("site_action", "site action", "action"),
        "signed_quantity": (
            "required_qty",
            "required qty",
            "quantity",
            "*数量",
            "数量",
        ),
        "install_quantity": (
            "new",
            "installation outbound",
            "installation outbound/增加数量",
            "install quantity",
        ),
        "redeploy_quantity": ("redeploy", "redeploy quantity"),
        "dismantle_quantity": (
            "dismantle",
            "dismantling inbound",
            "dismantling inbound/减少数量",
            "dismantle quantity",
        ),
    }
    quantity_aliases = tuple(
        dict.fromkeys(
            fields["signed_quantity"]
            + fields["install_quantity"]
            + fields["redeploy_quantity"]
            + fields["dismantle_quantity"]
        )
    )
    raw, sheet, selection_issues = select_frame(
        frame,
        (fields["site_id"], fields["item_code"], quantity_aliases),
    )
    required = ["site_id", "region", "item_code"]
    if str(parameters.get("o2_scope_material_mode", "raw")).casefold() == "base-pk-standardized":
        required.extend(("band", "ntnr", "signed_quantity"))
    normalized, issues = project_columns(
        raw,
        fields,
        required=required,
        source_sheet=sheet,
    )
    quantity_columns = (
        "signed_quantity",
        "install_quantity",
        "redeploy_quantity",
        "dismantle_quantity",
    )
    # Quantity semantics are mutually exclusive source columns.  Re-project
    # them using exact aliases so a generic signed ``数量`` column cannot also
    # satisfy verbose install/dismantle aliases (and vice versa).
    for name in quantity_columns:
        physical = exact_column(raw, fields[name])
        normalized[name] = raw[physical].reset_index(drop=True) if physical else ""
    if not normalized.empty and not any(
        normalized[name].map(lambda value: str(value).strip()).any()
        for name in quantity_columns
    ):
        issues += (
            {
                "code": "MISSING_CANONICAL_COLUMN",
                "message": "scope input lacks every canonical quantity column",
                "column": "|".join(quantity_columns),
            },
        )
    included_years = options.get("included_years")
    if included_years is not None:
        if (
            not isinstance(included_years, (list, tuple))
            or not included_years
            or any(not isinstance(value, str) for value in included_years)
        ):
            raise ValueError("schema_options.included_years must be a non-empty list of strings")
        allowed = {str(value).strip().casefold() for value in included_years}
        normalized = normalized[
            normalized["year"].map(lambda value: _norm(value).casefold()).isin(allowed)
        ].reset_index(drop=True)
    return normalized, selection_issues + issues


__all__ = ["NormalizedScopeInput", "normalize"]
