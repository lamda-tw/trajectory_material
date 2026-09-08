"""Canonical adapter for authoritative site-to-delivery-batch mappings."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .._shared import _norm
from ._canonical import (
    TabularSource,
    effective_delivery_options,
    project_columns,
    select_frame,
)


NormalizedBatchInput = pd.DataFrame


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedBatchInput, tuple[dict[str, Any], ...]]:
    parameters = effective_delivery_options(options)
    batch_kind = str(parameters.get("o2_batch_kind", "")).strip().casefold()
    fields = {
        "site_id": (
            "site_name",
            "site name",
            "site id",
            "site id radio",
            "site id radio/站点",
            "du id",
            "*du id",
        ),
        "region": ("region", "region/区域", "区域"),
        "cluster_id": (
            "cluster",
            "cluster_id",
            "cluster id",
            "cluster/簇",
            *(("batch_id",) if batch_kind == "cluster" else ()),
        ),
        "mocn_batch_id": (
            "mocn_batch",
            "mocn batch",
            "mocn batch id",
            "mocn开通批次",
            "mocn批次号",
            *(("batch_id",) if batch_kind == "mocn" else ()),
        ),
    }
    if batch_kind == "cluster":
        batch_field = "cluster_id"
    elif batch_kind == "mocn":
        batch_field = "mocn_batch_id"
    else:
        # No O2 consumer means there is no authorized interpretation of a
        # generic batch_id.  Explicit columns can still be projected.
        batch_field = "cluster_id"
    raw, sheet, selection_issues = select_frame(
        frame,
        (fields["site_id"], fields[batch_field]),
    )
    normalized, issues = project_columns(
        raw,
        fields,
        required=("site_id", batch_field),
        source_sheet=sheet,
    )
    normalized["region"] = normalized["region"].map(
        lambda value: _norm(value) or "ALL"
    )
    return normalized, selection_issues + issues


__all__ = ["NormalizedBatchInput", "normalize"]
