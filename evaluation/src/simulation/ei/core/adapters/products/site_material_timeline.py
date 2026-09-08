"""Adapter contract for the standard ``site_material_timeline`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .._shared import normalize_timeline_mature_supply
from ._tabular import copy_source_table

NormalizedSiteMaterialTimeline = pd.DataFrame


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[NormalizedSiteMaterialTimeline, tuple[dict[str, Any], ...]]:
    return copy_source_table(frame, options)


__all__ = [
    "NormalizedSiteMaterialTimeline",
    "normalize",
    "normalize_timeline_mature_supply",
]
