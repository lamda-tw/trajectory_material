"""Shared normalized reuse-summary quantities."""

from collections import defaultdict
from typing import Any


REUSE_METRICS = {"intersitereuse", "reuse", "initialstockreuse"}
NEW_METRICS = {"newproposal", "new"}
DISMANTLED_METRICS = {"dismantled"}
SUMMARY_KEYS = {"total", "grandsummary"}


def summary_quantities(
    rows: list[dict[str, Any]],
    metrics: set[str],
) -> dict[str, int]:
    output: dict[str, int] = defaultdict(int)
    summary = 0
    for row in rows:
        if row["metric_key"] not in metrics:
            continue
        if row["item_key"] in SUMMARY_KEYS:
            summary += int(row["total"])
            continue
        output[row["item_key"]] += int(row["total"])
    return dict(output) if output else {"__summary__": summary}
