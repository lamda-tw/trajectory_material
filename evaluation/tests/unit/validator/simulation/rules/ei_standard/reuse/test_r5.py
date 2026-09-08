from pathlib import Path

from simulation.ei.core.models import ArtifactResolution
from simulation.ei.rules.ei_standard.reuse.r5 import score_r5

from .support import context, passing_rate_rows


def _warehouse(quantity: int) -> dict[tuple[str, int], dict[str, int]]:
    return {
        ("a", 1): {
            "opening": 0,
            "inbound": quantity,
            "outbound": quantity,
            "closing": 0,
        }
    }


def _select(ctx, role: str, normalized: object, **kwargs: object) -> None:
    ctx.artifacts.artifacts[role] = ArtifactResolution(
        role,
        "SELECTED_CANONICAL",
        Path(f"run/{role}.csv"),
        normalized=normalized,
        **kwargs,
    )


def _quantity_rows() -> list[dict[str, object]]:
    rows = passing_rate_rows()
    for row in rows:
        if row["metric_type"] == "quantity":
            row["regions"] = {"region-1": row["total"]}
    return rows


def test_hard_hell_r5_owns_missing_warehouse_evidence_failure() -> None:
    result = score_r5(context("R5"), passing_rate_rows())
    assert result.check_id == "reuse-accounting.R5"
    assert result.reason_code == "MISSING_WEEKLY_EVIDENCE"


def test_easy_medium_r5_receives_full_credit_when_all_warehouses_are_absent() -> None:
    result = score_r5(
        context("R5", parameters={"r5_missing_evidence_policy": "full-credit"}),
        passing_rate_rows(),
    )

    assert result.score == 100.0
    assert result.status == "PASS"
    assert result.reason_code == "OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT"
    assert result.evidence["missing_roles"] == ["reuse_warehouse", "new_warehouse"]


def test_r5_optional_absence_is_decided_before_unrelated_summary_quantity_errors() -> None:
    ctx = context("R5", parameters={"r5_missing_evidence_policy": "full-credit"})
    _select(
        ctx,
        "reuse_by_region",
        passing_rate_rows(),
        quantity_error_count=1,
        quantity_errors=({"code": "NON_INTEGER_QUANTITY"},),
    )

    result = score_r5(ctx, passing_rate_rows())

    assert result.score == 100.0
    assert result.reason_code == "OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT"


def test_r5_partial_warehouse_submission_does_not_receive_full_credit() -> None:
    ctx = context("R5", parameters={"r5_missing_evidence_policy": "full-credit"})
    _select(ctx, "reuse_warehouse", _warehouse(5))

    result = score_r5(ctx, _quantity_rows())

    assert result.score == 0
    assert result.reason_code == "MISSING_WEEKLY_EVIDENCE"


def test_r5_submitted_warehouses_use_the_standard_consistency_formula() -> None:
    ctx = context("R5", parameters={"r5_missing_evidence_policy": "full-credit"})
    _select(ctx, "reuse_warehouse", _warehouse(5))
    _select(ctx, "new_warehouse", _warehouse(5))

    result = score_r5(ctx, _quantity_rows())

    assert result.score == 100.0
    assert result.reason_code == ""


def _install_only_rows(*, dismantled: int = 0) -> list[dict[str, object]]:
    return [
        {
            "row": 2,
            "item_key": "grandsummary",
            "metric": "Dismantled",
            "metric_key": "dismantled",
            "metric_type": "quantity",
            "regions": {"Region-1": dismantled, "Region-2": 0},
            "invalid_regions": [],
            "total": dismantled,
            "total_valid": True,
        },
        {
            "row": 3,
            "item_key": "grandsummary",
            "metric": "Inter-Site Reuse",
            "metric_key": "intersitereuse",
            "metric_type": "quantity",
            "regions": {"Region-1": 0, "Region-2": 0},
            "invalid_regions": [],
            "total": 0,
            "total_valid": True,
        },
    ]


def test_r5_install_only_zero_metrics_are_checked_before_optional_warehouse_policy() -> None:
    ctx = context(
        "R5",
        parameters={
            "r5_missing_evidence_policy": "full-credit",
            "r5_zero_metrics": ["dismantled", "intersitereuse"],
        },
    )

    passing = score_r5(ctx, _install_only_rows())
    failing = score_r5(ctx, _install_only_rows(dismantled=1))

    assert passing.score == 100.0
    assert passing.evidence["zero_metrics"]["checked_rows"] == 2
    assert failing.score == 0.0
    assert failing.reason_code == "FORBIDDEN_REUSE_BUSINESS_QUANTITY"
    assert failing.evidence["failures"][0]["metric"] == "dismantled"


def test_r5_install_only_zero_metrics_must_each_be_present() -> None:
    ctx = context(
        "R5",
        parameters={"r5_zero_metrics": ["dismantled", "intersitereuse"]},
    )

    result = score_r5(ctx, _install_only_rows()[:1])

    assert result.score == 0.0
    assert result.reason_code == "FORBIDDEN_REUSE_BUSINESS_QUANTITY"
    assert result.evidence["missing_metrics"] == ["intersitereuse"]
