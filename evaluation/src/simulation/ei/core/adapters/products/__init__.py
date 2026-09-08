"""Explicit product-to-adapter boundary for Simulation artifacts."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from . import (
    batch_input,
    final_material,
    gap,
    initial_warehouse,
    material_substitution,
    master_plan,
    scope_input,
    new_warehouse,
    recovered_supply,
    reuse_by_region,
    reuse_warehouse,
    site_material_timeline,
    site_plan,
)
from ._tabular import copy_source_table


def normalize_product(
    role: str,
    schema: str,
    frame: Any,
    options: Mapping[str, Any],
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Normalize one configured artifact through its standard product module."""

    # These product contracts intentionally accept a workbook mapping as well
    # as one DataFrame.  Dispatch by role before the legacy tabular guard so
    # worksheet selection remains an adapter responsibility.
    if role == "site_plan":
        return site_plan.normalize(frame, options)
    if role == "scope_input":
        return scope_input.normalize(frame, options)
    if role == "master_plan":
        return master_plan.normalize(frame, options)
    if role == "batch_input":
        return batch_input.normalize(frame, options)
    if role == "final_material":
        return final_material.normalize(frame, options)
    if role == "substitution_source":
        return material_substitution.normalize(frame, options)

    if not isinstance(frame, pd.DataFrame):
        return frame, ()

    if role == "site_material_timeline":
        return site_material_timeline.normalize(frame, options)
    if role == "material_substitution":
        # Candidate relationship output remains a raw tabular product for the
        # legacy S1 scorer.  O2 consumes only the authoritative question role
        # ``substitution_source`` compiled above.
        return copy_source_table(frame, options)
    if role == "recovered_supply":
        return recovered_supply.normalize(frame, options)
    if role == "gap":
        return gap.normalize(frame, options)
    if role == "reuse_by_region":
        return reuse_by_region.normalize(frame, options)
    if role == "initial_warehouse":
        return initial_warehouse.normalize(frame, options)
    if role == "new_warehouse":
        return new_warehouse.normalize(frame, options)
    if role == "reuse_warehouse":
        return reuse_warehouse.normalize(frame, options)

    # Compatibility for question-specific role names. Schema remains the
    # authority only when no standard product role was configured.
    if schema == "ei.warehouse":
        return initial_warehouse.normalize(frame, options)
    if schema == "ei.gap-wide":
        return gap.normalize(frame, options)
    if schema == "ei.reuse-summary":
        return reuse_by_region.normalize(frame, options)
    return copy_source_table(frame, options)


__all__ = ["normalize_product"]
