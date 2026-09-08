"""Adapter contract for the standard ``new_warehouse`` product."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ._warehouse import WarehouseLedger, normalize as normalize_warehouse

NormalizedNewWarehouse = WarehouseLedger


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[NormalizedNewWarehouse, tuple[dict[str, Any], ...]]:
    return normalize_warehouse(frame, options)


__all__ = ["NormalizedNewWarehouse", "normalize"]
