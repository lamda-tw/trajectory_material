"""Adapter contract for the standard ``recovered_supply`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ._tabular import copy_source_table

NormalizedRecoveredSupply = pd.DataFrame


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[NormalizedRecoveredSupply, tuple[dict[str, Any], ...]]:
    return copy_source_table(frame, options)


__all__ = ["NormalizedRecoveredSupply", "normalize"]
