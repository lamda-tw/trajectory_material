"""Adapter contract for the standard ``reuse_by_region`` product."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

import pandas as pd

from .._shared import (
    _normalize_reuse_summary,
    _normalize_reuse_summary_with_issues,
)


ReuseSummaryRows: TypeAlias = list[dict[str, Any]]


def normalize(
    frame: pd.DataFrame,
    options: Mapping[str, Any],
) -> tuple[ReuseSummaryRows, tuple[dict[str, Any], ...]]:
    del options
    return _normalize_reuse_summary_with_issues(frame)


__all__ = ["ReuseSummaryRows", "_normalize_reuse_summary", "normalize"]
