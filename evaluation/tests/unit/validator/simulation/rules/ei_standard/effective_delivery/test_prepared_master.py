from __future__ import annotations

import pandas as pd

from simulation.ei.rules.ei_standard.effective_delivery.prepared_master import (
    compare_prepared_master,
)


def _authority() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1", "S2", "S3"],
            "site_action": ["install", "install", "dismantle"],
            "mos_weekly_plan": ["2027WK5", "2027WK6", "2027WK10"],
            "week_num": [5, 6, 10],
            "region": ["Region-1", "Region-1", "Region-2"],
            "site_count": [1, 1, 1],
        }
    )


def _prepared() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["Region-1", "Region-2"],
            "action": ["install", "dismantle"],
            "month": ["2027M2", "2027M3"],
            "master_count": [2, 1],
        }
    )


def test_prepared_master_matches_all_region_action_natural_month_totals() -> None:
    result = compare_prepared_master(_authority(), _prepared())

    assert result["passed"] is True
    assert result["gate_rate"] == 1.0
    assert result["expected_actions"] == ["dismantle", "install"]
    assert result["expected_periods"] == [202702, 202703]
    assert result["difference_count"] == 0


def test_prepared_master_fails_on_missing_dismantle_or_wrong_month_quantity() -> None:
    prepared = _prepared().iloc[:1].copy()
    prepared.loc[0, "master_count"] = 3

    result = compare_prepared_master(_authority(), prepared)

    assert result["passed"] is False
    assert result["gate_rate"] == 0.0
    assert result["actual_actions"] == ["install"]
    assert result["difference_count"] == 2


def test_prepared_master_requires_exact_schema_and_unique_coordinates() -> None:
    wrong_schema = _prepared().rename(columns={"master_count": "count"})
    duplicate = pd.concat([_prepared(), _prepared().iloc[[0]]], ignore_index=True)

    schema_result = compare_prepared_master(_authority(), wrong_schema)
    duplicate_result = compare_prepared_master(_authority(), duplicate)

    assert schema_result["passed"] is False
    assert schema_result["prepared_errors"][0]["expected"] == [
        "region",
        "action",
        "month",
        "master_count",
    ]
    assert duplicate_result["passed"] is False
    assert "DUPLICATE_REGION_ACTION_MONTH" in duplicate_result[
        "prepared_errors"
    ][0]["reasons"]


def test_prepared_master_rejects_an_extra_zero_month_coordinate() -> None:
    extra = pd.concat(
        [
            _prepared(),
            pd.DataFrame(
                {
                    "region": ["Region-1"],
                    "action": ["install"],
                    "month": ["2027M4"],
                    "master_count": [0],
                }
            ),
        ],
        ignore_index=True,
    )

    result = compare_prepared_master(_authority(), extra)

    assert result["passed"] is False
    assert result["period_universe_match"] is False
    assert result["extra_coordinate_count"] == 1
    assert result["extra_coordinates"] == [
        {"region": "region1", "action": "install", "period": 202704}
    ]
