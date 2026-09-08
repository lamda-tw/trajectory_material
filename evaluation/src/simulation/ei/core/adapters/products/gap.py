"""Adapter contract for the standard ``gap`` product."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

import pandas as pd

from .._shared import align_gap_reuse_inbound, normalize_gap_wide


GapPayload: TypeAlias = dict[str, Any]


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[GapPayload, tuple[dict[str, Any], ...]]:
    return normalize_gap_wide(frame, options)


__all__ = [
    "GapPayload",
    "align_gap_reuse_inbound",
    "normalize",
    "normalize_gap_wide",
]
