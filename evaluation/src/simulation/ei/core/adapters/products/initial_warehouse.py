"""Adapter contract for the standard ``initial_warehouse`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ._warehouse import WarehouseLedger, normalize as normalize_warehouse

NormalizedInitialWarehouse = WarehouseLedger


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[NormalizedInitialWarehouse, tuple[dict[str, Any], ...]]:
    return normalize_warehouse(frame, options)


__all__ = ["NormalizedInitialWarehouse", "normalize"]
