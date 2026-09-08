from simulation.ei.rules.ei_standard.reuse.r6 import score_r6

from .support import context, passing_rate_rows


def test_r6_scores_both_item_rate_families_directly() -> None:
    result = score_r6(context("R6"), passing_rate_rows())
    assert result.check_id == "reuse-accounting.R6"
    assert result.score == 100.0
    assert result.status == "PASS"


def _grand_summary_rows(*, dismantled: int, reused: int, rate: object):
    return [
        {
            "row": 2,
            "item_key": "grandsummary",
            "metric": "Dismantled",
            "metric_key": "dismantled",
            "metric_type": "quantity",
            "total": dismantled,
            "total_valid": True,
        },
        {
            "row": 3,
            "item_key": "grandsummary",
            "metric": "Inter-Site Reuse",
            "metric_key": "intersitereuse",
            "metric_type": "quantity",
            "total": reused,
            "total_valid": True,
        },
        {
            "row": 4,
            "item_key": "grandsummary",
            "metric": "New Proposal",
            "metric_key": "newproposal",
            "metric_type": "quantity",
            "total": 10,
            "total_valid": True,
        },
        {
            "row": 5,
            "item_key": "grandsummary",
            "metric": "reuse rate (拆除重部署率)",
            "metric_key": "reuserate拆除重部署率",
            "metric_type": "rate",
            "total": rate,
        },
    ]


def _grand_summary_context():
    return context(
        "R6",
        parameters={
            "r6_contract": {
                "coordinate_scope": "grand-summary-total",
                "rate_families": ["primary"],
                "zero_denominator_policy": "require-blank-rate",
            }
        },
    )


def test_r6_can_score_only_the_prompt_required_grand_summary_primary_rate() -> None:
    rows = passing_rate_rows() + _grand_summary_rows(
        dismantled=40,
        reused=6,
        rate="15.00%",
    )

    result = score_r6(_grand_summary_context(), rows)

    assert result.score == 100.0
    assert result.status == "PASS"
    assert result.evidence["coordinate_scope"] == "grand-summary-total"
    assert result.evidence["rate_families"] == ["primary"]
    assert set(result.evidence["families"]) == {"primary_rate"}


def test_r6_grand_summary_requires_a_blank_rate_when_denominator_is_zero() -> None:
    passing = score_r6(
        _grand_summary_context(),
        _grand_summary_rows(dismantled=0, reused=0, rate=""),
    )
    failing = score_r6(
        _grand_summary_context(),
        _grand_summary_rows(dismantled=0, reused=0, rate="0.00%"),
    )

    assert passing.score == 100.0
    assert passing.status == "PASS"
    assert failing.score == 0.0
    assert failing.reason_code == "GRAND_SUMMARY_RATE_MISMATCH"
    assert failing.evidence["failures"][0]["status"] == (
        "ZERO_DENOMINATOR_RATE_NOT_BLANK"
    )


def test_r6_grand_summary_requires_all_three_core_quantity_rows() -> None:
    rows = [
        row
        for row in _grand_summary_rows(dismantled=10, reused=5, rate="50%")
        if row["metric_key"] != "newproposal"
    ]

    result = score_r6(_grand_summary_context(), rows)

    assert result.score == 0.0
    contract = result.evidence["grand_summary_quantity_contract"]
    assert contract["passed"] is False
    assert contract["metrics"]["new_proposal"]["status"] == "MISSING_QUANTITY_ROW"
