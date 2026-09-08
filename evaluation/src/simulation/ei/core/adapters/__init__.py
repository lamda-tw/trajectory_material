"""Stable public facade for Simulation artifact adapters.

Product-specific normalization lives under :mod:`.products`; existing imports
remain valid while callers migrate to the explicit product modules.
"""

from ._shared import (
    _normalize_reuse_summary,
    _normalize_warehouse,
    _recover_gap_rows_missing_control_cells,
    align_gap_reuse_inbound,
    gap_week_column,
    material_quantity,
    normalize_gap_wide,
    normalize_timeline_mature_supply,
    parse_iso_week,
    parse_project_week,
    preserved_quantity,
    shift_week_coordinate,
    warehouse_key_parts,
    warehouse_series_key,
    warehouse_week_kind,
    week_coordinate_kind,
)
from .io import read_table as _read_table
from .resolver import prepare_question_artifacts, resolve_artifacts

__all__ = [
    "align_gap_reuse_inbound",
    "gap_week_column",
    "material_quantity",
    "normalize_gap_wide",
    "normalize_timeline_mature_supply",
    "parse_iso_week",
    "parse_project_week",
    "preserved_quantity",
    "prepare_question_artifacts",
    "resolve_artifacts",
    "shift_week_coordinate",
    "warehouse_key_parts",
    "warehouse_series_key",
    "warehouse_week_kind",
    "week_coordinate_kind",
]
