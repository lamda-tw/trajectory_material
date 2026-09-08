"""R5 summary-to-warehouse consistency."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from simulation.ei.core.adapters import warehouse_key_parts
from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import artifact, failed_leaf, leaf, normalized, quantity_error, validation_issues
from ..common import _key, _quantity_overlap
from .summary import NEW_METRICS, REUSE_METRICS, summary_quantities


def _quantity_rows_consistent(
    rows: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    errors = []
    for row in rows:
        if row["metric_type"] != "quantity":
            continue
        region_sum = sum(int(value) for value in row["regions"].values())
        if region_sum != int(row["total"]):
            errors.append(
                {
                    "row": row["row"],
                    "metric": row["metric"],
                    "region_sum": region_sum,
                    "total": int(row["total"]),
                }
            )
    return not errors, errors


def _aggregate_actual(
    expected: Mapping[str, int],
    actual: Mapping[str, int],
) -> dict[str, int]:
    if set(expected) == {"__summary__"}:
        return {"__summary__": sum(actual.values())}
    return dict(actual)


def _zero_metric_evidence(
    rows: list[dict[str, Any]],
    configured_metrics: list[str],
) -> tuple[bool, dict[str, Any]]:
    required = {_key(value) for value in configured_metrics}
    found: set[str] = set()
    failures: list[dict[str, Any]] = []
    checked_rows = 0
    for row in rows:
        metric = str(row.get("metric_key", ""))
        if row.get("metric_type") != "quantity" or metric not in required:
            continue
        found.add(metric)
        checked_rows += 1
        invalid_regions = list(row.get("invalid_regions", ()))
        regions = row.get("regions", {})
        nonzero_regions = {
            str(region): value
            for region, value in regions.items()
            if value is None or int(value) != 0
        }
        total = row.get("total")
        if (
            invalid_regions
            or not row.get("total_valid", True)
            or total is None
            or int(total) != 0
            or nonzero_regions
        ):
            failures.append(
                {
                    "row": row.get("row"),
                    "item": row.get("item_key"),
                    "metric": metric,
                    "total": total,
                    "invalid_regions": invalid_regions,
                    "nonzero_regions": nonzero_regions,
                }
            )
    missing = sorted(required - found)
    return not failures and not missing, {
        "required_metrics": sorted(required),
        "found_metrics": sorted(found),
        "missing_metrics": missing,
        "checked_rows": checked_rows,
        "failure_count": len(failures),
        "failures": failures[:50],
    }


def score_r5(
    context: RuleContext,
    summary_rows: list[dict[str, Any]] | None,
) -> CheckResult:
    zero_metrics = context.component.parameters.get("r5_zero_metrics")
    zero_metric_evidence: dict[str, Any] | None = None
    if zero_metrics is not None:
        if summary_rows is None:
            return failed_leaf(
                context,
                "R5",
                "Summary/warehouse consistency",
                "MISSING_OR_INVALID_ARTIFACT",
                "reuse_by_region is required by the configured zero-metric contract",
            )
        passed, zero_metric_evidence = _zero_metric_evidence(
            summary_rows,
            list(zero_metrics),
        )
        if not passed:
            return failed_leaf(
                context,
                "R5",
                "Summary/warehouse consistency",
                "FORBIDDEN_REUSE_BUSINESS_QUANTITY",
                "Prompt-forbidden reuse metrics must be present and zero in every submitted quantity row",
                zero_metric_evidence,
            )
    required_roles = ("reuse_warehouse", "new_warehouse")
    resolutions = [artifact(context, role) for role in required_roles]
    all_missing = all(
        resolution is None or resolution.status == "MISSING"
        for resolution in resolutions
    )
    if (
        all_missing
        and context.component.parameters.get("r5_missing_evidence_policy")
        == "full-credit"
    ):
        return leaf(
            context,
            "R5",
            "Summary/warehouse consistency",
            1.0,
            "The Prompt does not require the warehouse ledgers needed for this cross-artifact comparison; complete absence receives full comparison credit",
            {
                "policy": "full-credit",
                "missing_roles": list(required_roles),
                "zero_metrics": zero_metric_evidence or {},
                "artifact_statuses": {
                    role: resolution.status if resolution is not None else "UNRESOLVED"
                    for role, resolution in zip(required_roles, resolutions)
                },
            },
            reason_code="OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT",
        )
    integer_error = quantity_error(context, "reuse_by_region")
    if integer_error:
        return failed_leaf(
            context,
            "R5",
            "Summary/warehouse consistency",
            "NON_INTEGER_QUANTITY",
            "Reuse summary quantities must be integers",
            integer_error,
        )
    if summary_rows is None:
        return failed_leaf(
            context,
            "R5",
            "Summary/warehouse consistency",
            "MISSING_OR_INVALID_ARTIFACT",
            "reuse_by_region is missing or structurally invalid",
        )
    reuse = summary_quantities(summary_rows, REUSE_METRICS)
    new = summary_quantities(summary_rows, NEW_METRICS)
    reuse_warehouse = normalized(context, "reuse_warehouse")
    initial_warehouse = normalized(context, "initial_warehouse")
    new_warehouse = normalized(context, "new_warehouse")
    warehouse_issues = validation_issues(
        context,
        "reuse_warehouse",
        "initial_warehouse",
        "new_warehouse",
    )
    if reuse_warehouse is None or new_warehouse is None:
        return failed_leaf(
            context,
            "R5",
            "Summary/warehouse consistency",
            "MISSING_WEEKLY_EVIDENCE",
            "R5 requires reuse and new warehouse ledgers",
        )
    consistent, consistency_errors = _quantity_rows_consistent(summary_rows)
    if not consistent:
        return failed_leaf(
            context,
            "R5",
            "Summary/warehouse consistency",
            "INCONSISTENT_QUANTITY_TOTAL",
            "Quantity-row Total must equal the sum of prompt region columns before warehouse comparison",
            {"errors": consistency_errors},
        )
    reuse_out: dict[str, int] = defaultdict(int)
    for warehouse in (reuse_warehouse, initial_warehouse or {}):
        for key, cell in warehouse.items():
            _, item, _ = warehouse_key_parts(key)
            reuse_out[item] += max(0, int(cell["outbound"]))
    new_out: dict[str, int] = defaultdict(int)
    for key, cell in new_warehouse.items():
        _, item, _ = warehouse_key_parts(key)
        new_out[item] += max(0, int(cell["outbound"]))
    _, reuse_diag = _quantity_overlap(reuse, _aggregate_actual(reuse, reuse_out))
    _, new_diag = _quantity_overlap(new, _aggregate_actual(new, new_out))
    denominator = reuse_diag["combined_qty"] + new_diag["combined_qty"]
    matched = reuse_diag["matched_qty"] + new_diag["matched_qty"]
    return leaf(
        context,
        "R5",
        "Summary/warehouse consistency",
        matched / denominator if denominator else 1.0,
        "Reuse and new summary quantities must match the corresponding warehouse outbound quantities",
        {
            "reuse": reuse_diag,
            "new": new_diag,
            "zero_metrics": zero_metric_evidence or {},
            "validation_issues": warehouse_issues or {},
        },
        reason_code="WAREHOUSE_VALIDATION_ISSUES" if warehouse_issues else "",
    )
