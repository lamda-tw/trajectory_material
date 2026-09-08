"""R6 per-item reuse-rate formulas."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import failed_leaf, leaf
from ..common import _norm
from .summary import DISMANTLED_METRICS, NEW_METRICS, SUMMARY_KEYS


PRIMARY_RATE_METRICS = {"reuserate", "reuserate拆除重部署率"}
ALL_SCOPE_RATE_METRICS = {"allscopereuserate", "allscopereuserate整体scope利旧率"}
INTER_SITE_REUSE_METRICS = {"intersitereuse", "reuse"}
MAX_ABS_TOLERANCE = 0.0001
_DEFAULT_RATE_FAMILIES = ("primary", "all-scope")
_RATE_FAMILY_CONTRACTS = {
    "primary": {
        "evidence_key": "primary_rate",
        "rate_metrics": PRIMARY_RATE_METRICS,
        "formula": "Inter-Site Reuse / Dismantled",
        "denominator_metrics": DISMANTLED_METRICS,
        "denominator_label": "Dismantled",
    },
    "all-scope": {
        "evidence_key": "all_scope_rate",
        "rate_metrics": ALL_SCOPE_RATE_METRICS,
        "formula": "Inter-Site Reuse / (Inter-Site Reuse + New Proposal)",
        "denominator_metrics": NEW_METRICS,
        "denominator_label": "New Proposal",
    },
}


def _rate_value(value: Any) -> dict[str, Any] | None:
    text = _norm(value)
    if not text:
        return None
    percent = text.endswith("%")
    numeric_text = text[:-1].strip() if percent else text
    try:
        parsed = Decimal(numeric_text)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    if percent:
        if not Decimal(0) <= parsed <= Decimal(100):
            return None
        ratio = parsed / Decimal(100)
        precision = max(0, -parsed.as_tuple().exponent)
        tolerance = Decimal("0.5") * (Decimal(10) ** -precision) / Decimal(100)
        representation = "percent"
    else:
        if not Decimal(0) <= parsed <= Decimal(1):
            return None
        ratio = parsed
        precision = max(0, -parsed.as_tuple().exponent)
        tolerance = (
            Decimal(0)
            if precision == 0
            else Decimal("0.5") * (Decimal(10) ** -precision)
        )
        representation = "decimal"
    return {
        "raw": text,
        "value": float(ratio),
        "precision": precision,
        "representation": representation,
        "tolerance": float(tolerance),
    }


def _rate_tolerance(parsed: dict[str, Any] | None, maximum: float) -> float:
    if parsed is None:
        return float(maximum)
    return min(float(parsed["tolerance"]), float(maximum))


def _rate_matches(
    parsed: dict[str, Any] | None,
    expected: float,
    *,
    maximum_tolerance: float,
) -> bool:
    return parsed is not None and abs(float(parsed["value"]) - expected) <= (
        _rate_tolerance(parsed, maximum_tolerance) + 1e-12
    )


def _unique_quantity_total(
    item_rows: list[dict[str, Any]],
    metrics: set[str],
) -> tuple[int | None, dict[str, Any]]:
    matched = [
        row
        for row in item_rows
        if row["metric_type"] == "quantity" and row["metric_key"] in metrics
    ]
    if not matched:
        return None, {"status": "MISSING_QUANTITY_ROW"}
    if len(matched) != 1:
        return None, {
            "status": "DUPLICATE_QUANTITY_ROW",
            "rows": [row["row"] for row in matched],
        }
    row = matched[0]
    if not row.get("total_valid", True) or row.get("total") is None:
        return None, {
            "status": "INVALID_QUANTITY_TOTAL",
            "row": row["row"],
            "raw_total": _norm(row.get("raw_total")),
        }
    total = int(row["total"])
    if total < 0:
        return None, {
            "status": "NEGATIVE_QUANTITY_TOTAL",
            "row": row["row"],
            "total": total,
        }
    return total, {
        "status": "VALID",
        "row": row["row"],
        "metric": row["metric"],
        "total": total,
    }


def _score_item_rates(
    rows: list[dict[str, Any]],
    *,
    coordinate_scope: str = "item-totals",
    rate_families: tuple[str, ...] = _DEFAULT_RATE_FAMILIES,
    zero_denominator_policy: str = "not-applicable",
) -> tuple[float, dict[str, Any], str]:
    if coordinate_scope == "grand-summary-total":
        item_keys = ["grandsummary"] if any(
            row.get("item_key") == "grandsummary" for row in rows
        ) else []
        missing_reason = "MISSING_GRAND_SUMMARY_RATE_EVIDENCE"
        ignored_rows = sum(1 for row in rows if row.get("item_key") != "grandsummary")
        granularity = "grand_summary_total"
    else:
        item_keys = sorted(
            {
                str(row["item_key"])
                for row in rows
                if row.get("item_key") and row["item_key"] not in SUMMARY_KEYS
            }
        )
        missing_reason = "MISSING_ITEM_RATE_EVIDENCE"
        ignored_rows = sum(1 for row in rows if row.get("item_key") in SUMMARY_KEYS)
        granularity = "item_total"
    if not item_keys:
        return (
            0.0,
            {
                "item_count": 0,
                "ignored_row_count": ignored_rows,
                "coordinate_scope": coordinate_scope,
                "reason": (
                    "reuse_by_region contains no Grand Summary evidence"
                    if coordinate_scope == "grand-summary-total"
                    else "reuse_by_region contains no non-summary item evidence"
                ),
            },
            missing_reason,
        )

    rows_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item_key = str(row.get("item_key", ""))
        if item_key in item_keys:
            rows_by_item[item_key].append(row)
    families: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    passes: list[dict[str, Any]] = []
    grand_summary_quantity_contract: dict[str, Any] | None = None
    if coordinate_scope == "grand-summary-total":
        grand_summary_rows = rows_by_item["grandsummary"]
        required_quantities = {
            "dismantled": DISMANTLED_METRICS,
            "inter_site_reuse": INTER_SITE_REUSE_METRICS,
            "new_proposal": NEW_METRICS,
        }
        quantity_results = {
            name: _unique_quantity_total(grand_summary_rows, metrics)[1]
            for name, metrics in required_quantities.items()
        }
        quantity_contract_passed = all(
            result.get("status") == "VALID"
            for result in quantity_results.values()
        )
        grand_summary_quantity_contract = {
            "required_metrics": list(required_quantities),
            "passed": quantity_contract_passed,
            "metrics": quantity_results,
        }
        if not quantity_contract_passed:
            failures.append(
                {
                    "item": "grandsummary",
                    "status": "INVALID_REQUIRED_SUMMARY_QUANTITIES",
                    "quantities": quantity_results,
                }
            )
    family_weight = 1.0 / len(rate_families)
    for family in rate_families:
        contract = _RATE_FAMILY_CONTRACTS[family]
        evidence_key = str(contract["evidence_key"])
        expected_coordinates = 0
        correct_coordinates = 0
        not_applicable_coordinates = 0
        for item_key in item_keys:
            item_rows = rows_by_item[item_key]
            reuse_total, reuse_evidence = _unique_quantity_total(
                item_rows,
                INTER_SITE_REUSE_METRICS,
            )
            other_total, other_evidence = _unique_quantity_total(
                item_rows,
                contract["denominator_metrics"],
            )
            quantity_evidence = {
                "inter_site_reuse": reuse_evidence,
                str(contract["denominator_label"]): other_evidence,
            }
            if reuse_total is None or other_total is None:
                expected_coordinates += 1
                failures.append(
                    {
                        "item": item_key,
                        "family": evidence_key,
                        "status": "INVALID_FORMULA_QUANTITY",
                        "quantities": quantity_evidence,
                    }
                )
                continue
            denominator = (
                other_total
                if family == "primary"
                else reuse_total + other_total
            )
            if denominator == 0:
                if zero_denominator_policy == "require-blank-rate":
                    expected_coordinates += 1
                    rate_rows = [
                        row
                        for row in item_rows
                        if row["metric_type"] == "rate"
                        and row["metric_key"] in contract["rate_metrics"]
                    ]
                    passed = len(rate_rows) == 1 and not _norm(rate_rows[0]["total"])
                    detail = {
                        "item": item_key,
                        "family": evidence_key,
                        "status": "PASS" if passed else "ZERO_DENOMINATOR_RATE_NOT_BLANK",
                        "rate_rows": [row["row"] for row in rate_rows],
                        "raw_rates": [_norm(row["total"]) for row in rate_rows],
                        "numerator": reuse_total,
                        "denominator": denominator,
                    }
                    if passed:
                        correct_coordinates += 1
                        passes.append(detail)
                    else:
                        failures.append(detail)
                    continue
                not_applicable_coordinates += 1
                passes.append(
                    {
                        "item": item_key,
                        "family": evidence_key,
                        "status": "NOT_APPLICABLE",
                        "numerator": reuse_total,
                        "denominator": denominator,
                    }
                )
                continue
            expected_coordinates += 1
            rate_rows = [
                row
                for row in item_rows
                if row["metric_type"] == "rate"
                and row["metric_key"] in contract["rate_metrics"]
            ]
            if not rate_rows:
                failures.append(
                    {
                        "item": item_key,
                        "family": evidence_key,
                        "status": "MISSING_RATE_ROW",
                        "numerator": reuse_total,
                        "denominator": denominator,
                    }
                )
                continue
            if len(rate_rows) != 1:
                failures.append(
                    {
                        "item": item_key,
                        "family": evidence_key,
                        "status": "DUPLICATE_RATE_ROW",
                        "rows": [row["row"] for row in rate_rows],
                        "numerator": reuse_total,
                        "denominator": denominator,
                    }
                )
                continue
            rate_row = rate_rows[0]
            expected_rate = reuse_total / denominator
            actual_rate = _rate_value(rate_row["total"])
            passed = _rate_matches(
                actual_rate,
                expected_rate,
                maximum_tolerance=MAX_ABS_TOLERANCE,
            )
            detail = {
                "item": item_key,
                "family": evidence_key,
                "status": "PASS" if passed else "FORMULA_MISMATCH",
                "rate_row": rate_row["row"],
                "raw_rate": _norm(rate_row["total"]),
                "actual_rate": actual_rate,
                "expected_rate": expected_rate,
                "numerator": reuse_total,
                "denominator": denominator,
                "difference": (
                    None
                    if actual_rate is None
                    else abs(float(actual_rate["value"]) - expected_rate)
                ),
                "tolerance": _rate_tolerance(actual_rate, MAX_ABS_TOLERANCE),
            }
            if passed:
                correct_coordinates += 1
                passes.append(detail)
            else:
                failures.append(detail)
        if expected_coordinates:
            family_rate = correct_coordinates / expected_coordinates
        elif not_applicable_coordinates == len(item_keys):
            family_rate = 1.0
        else:
            family_rate = 0.0
        families[evidence_key] = {
            "formula": contract["formula"],
            "weight_share": family_weight,
            "expected_coordinates": expected_coordinates,
            "correct_coordinates": correct_coordinates,
            "not_applicable_coordinates": not_applicable_coordinates,
            "rate": family_rate,
            "score_contribution": 100.0 * family_weight * family_rate,
        }
    overall_rate = sum(float(value["rate"]) for value in families.values()) / len(
        families
    )
    if (
        grand_summary_quantity_contract is not None
        and not grand_summary_quantity_contract["passed"]
    ):
        overall_rate = 0.0
    evidence = {
        "granularity": granularity,
        "coordinate_scope": coordinate_scope,
        "rate_families": list(rate_families),
        "zero_denominator_policy": zero_denominator_policy,
        "item_count": len(item_keys),
        "items": item_keys,
        "ignored_row_count": ignored_rows,
        # Retain the released item-contract field for machine consumers.
        "summary_rows_ignored": (
            ignored_rows if coordinate_scope == "item-totals" else 0
        ),
        "maximum_absolute_tolerance": MAX_ABS_TOLERANCE,
        "families": families,
        "grand_summary_quantity_contract": grand_summary_quantity_contract or {},
        "failures": failures,
        "passes": passes,
    }
    reason = "" if overall_rate >= 1.0 else (
        "GRAND_SUMMARY_RATE_MISMATCH"
        if coordinate_scope == "grand-summary-total"
        else "ITEM_RATE_MISMATCH"
    )
    return overall_rate, evidence, reason


def _r6_contract(context: RuleContext) -> tuple[str, tuple[str, ...], str]:
    raw = context.component.parameters.get("r6_contract", {})
    if not isinstance(raw, dict):
        raise ValueError("r6_contract must be a mapping")
    coordinate_scope = str(raw.get("coordinate_scope", "item-totals"))
    raw_families = raw.get("rate_families", list(_DEFAULT_RATE_FAMILIES))
    if not isinstance(raw_families, (list, tuple)):
        raise ValueError("r6_contract.rate_families must be a list")
    rate_families = tuple(str(value) for value in raw_families)
    zero_denominator_policy = str(
        raw.get("zero_denominator_policy", "not-applicable")
    )
    return coordinate_scope, rate_families, zero_denominator_policy


def score_r6(
    context: RuleContext,
    summary_rows: list[dict[str, Any]] | None,
) -> CheckResult:
    if summary_rows is None:
        return failed_leaf(
            context,
            "R6",
            "Reuse-rate calculation",
            "MISSING_OR_INVALID_ARTIFACT",
            "reuse_by_region is missing or structurally invalid",
        )
    coordinate_scope, rate_families, zero_denominator_policy = _r6_contract(context)
    rate, evidence, reason_code = _score_item_rates(
        summary_rows,
        coordinate_scope=coordinate_scope,
        rate_families=rate_families,
        zero_denominator_policy=zero_denominator_policy,
    )
    return leaf(
        context,
        "R6",
        (
            "Grand Summary reuse-rate calculation"
            if coordinate_scope == "grand-summary-total"
            else "Per-item reuse-rate calculation"
        ),
        rate,
        (
            "Recompute the configured Grand Summary Total rate families from "
            "the same summary quantity rows"
            if coordinate_scope == "grand-summary-total"
            else "For each item Total, recompute dismantled reuse rate and "
            "all-scope reuse rate from the same item's quantity rows"
        ),
        evidence,
        reason_code=reason_code,
    )
