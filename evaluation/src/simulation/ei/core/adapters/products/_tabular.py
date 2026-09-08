"""Shared behavior for products whose business contract remains tabular."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def copy_source_table(
    frame: Any,
    options: Mapping[str, Any],
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Preserve the validated source table until a typed product model exists."""

    del options
    if not isinstance(frame, pd.DataFrame):
        return frame, ()
    return frame.copy(), ()
