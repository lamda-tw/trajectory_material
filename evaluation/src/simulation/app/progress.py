"""Structured progress events shared by CLI orchestration and providers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


ProgressCallback = Callable[[str, Mapping[str, Any]], None]


def emit(
    progress: ProgressCallback | None,
    event: str,
    **details: Any,
) -> None:
    """Emit one optional progress event without coupling services to a console."""

    if progress is not None:
        progress(event, details)
