"""Adapter contract for the standard ``reuse_warehouse`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ._warehouse import WarehouseLedger, normalize as normalize_warehouse

NormalizedReuseWarehouse = WarehouseLedger


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[NormalizedReuseWarehouse, tuple[dict[str, Any], ...]]:
    return normalize_warehouse(frame, options)


__all__ = ["NormalizedReuseWarehouse", "normalize"]
