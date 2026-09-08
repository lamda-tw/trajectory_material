"""Shared normalized ledger contract for the three warehouse products."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

import pandas as pd

from .._shared import _normalize_warehouse


WarehouseKey: TypeAlias = tuple[Any, ...]
WarehouseCell: TypeAlias = dict[str, int | float]
WarehouseLedger: TypeAlias = dict[WarehouseKey, WarehouseCell]


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[WarehouseLedger, tuple[dict[str, Any], ...]]:
    return _normalize_warehouse(frame, options)


__all__ = ["WarehouseCell", "WarehouseKey", "WarehouseLedger", "normalize"]
