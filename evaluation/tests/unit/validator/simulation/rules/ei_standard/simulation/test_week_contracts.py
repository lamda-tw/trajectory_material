from __future__ import annotations

import pandas as pd
import pytest

from simulation.ei.core.config import (
    ConfigurationError,
    _validate_week_axis_contract,
)
from simulation.ei.rules.ei_standard.simulation import score_simulation

from .support import _context, _resolution, flow_context


def _warehouse_context(
    warehouses: dict[str, dict],
    *,
    contracts: dict,
    blackout_weeks: int = 0,
    zero_roles: list[str] | None = None,
):
    parameters = {
        "s3_evidence_mode": "warehouse",
        "s3_required_roles": list(warehouses),
        "warehouse_week_contracts": contracts,
        "blackout_weeks": blackout_weeks,
    }
    if zero_roles is not None:
        parameters["warehouse_zero_business_roles"] = zero_roles
    resolutions = {
        role: _resolution(
            role,
            table=pd.DataFrame({"week": sorted({key[-1] for key in cells})}),
            normalized=cells,
        )
        for role, cells in warehouses.items()
    }
    return _context(
        rule_ids=("S3",),
        parameters=parameters,
        sources=frozenset(),
        resolutions=resolutions,
    )


def _cell(opening: int, inbound: int, outbound: int, closing: int) -> dict:
    return {
        "opening": opening,
        "inbound": inbound,
        "outbound": outbound,
        "closing": closing,
    }


def test_s3_missing_zero_business_week_is_a_scoring_failure() -> None:
    context = _warehouse_context(
        {
            "reuse_warehouse": {
                ("item-a", 1): _cell(0, 0, 0, 0),
                ("item-a", 3): _cell(0, 0, 0, 0),
            }
        },
        contracts={
            "reuse_warehouse": {
                "source": "fixed",
                "coverage": "exact",
                "week_kind": "project",
                "start_week": 1,
                "end_week": 3,
            }
        },
    )

    check = score_simulation(context)[0]

    assert check.score == pytest.approx(100 * 2 / 3)
    assert check.reason_code == "WAREHOUSE_WEEK_CONTRACT_MISMATCH"
    role = check.evidence["warehouse_week_contracts"]["roles"]["reuse_warehouse"]
    assert role["missing_unit_count"] == 1
    assert role["missing_unit_samples"] == [
        {"series": ["item-a"], "week": 2}
    ]


def test_s3_fixed_exact_axis_rejects_out_of_window_week() -> None:
    context = _warehouse_context(
        {
            "reuse_warehouse": {
                ("item-a", 1): _cell(0, 0, 0, 0),
                ("item-a", 2): _cell(0, 0, 0, 0),
                ("item-a", 3): _cell(0, 0, 0, 0),
            }
        },
        contracts={
            "reuse_warehouse": {
                "source": "fixed",
                "coverage": "exact",
                "week_kind": "project",
                "start_week": 1,
                "end_week": 2,
            }
        },
    )

    check = score_simulation(context)[0]

    assert check.score == pytest.approx(100 * 2 / 3)
    role = check.evidence["warehouse_week_contracts"]["roles"]["reuse_warehouse"]
    assert role["extra_unit_count"] == 1


def test_s3_blackout_checks_outbound_in_first_expected_axis_weeks() -> None:
    context = _warehouse_context(
        {
            "reuse_warehouse": {
                ("item-a", 5): _cell(1, 0, 1, 0),
                ("item-a", 6): _cell(0, 0, 0, 0),
            }
        },
        contracts={
            "reuse_warehouse": {
                "source": "fixed",
                "coverage": "exact",
                "week_kind": "project",
                "start_week": 5,
                "end_week": 6,
            }
        },
        blackout_weeks=1,
    )

    check = score_simulation(context)[0]

    assert check.score == 0
    assert check.reason_code == "REUSE_BLACKOUT_VIOLATION"
    assert check.evidence["blackout_contract"]["blocked_axis_weeks"] == [5]
    assert check.evidence["blackout_contract"]["violation_count"] == 1


def test_s3_zero_business_roles_require_every_ledger_cell_to_be_zero() -> None:
    contract = {
        "source": "fixed",
        "coverage": "exact",
        "week_kind": "project",
        "start_week": 1,
        "end_week": 2,
    }
    context = _warehouse_context(
        {
            "reuse_warehouse": {
                ("item-a", 1): _cell(0, 0, 0, 0),
                ("item-a", 2): _cell(0, 0, 0, 0),
            },
            "initial_warehouse": {
                ("item-a", 1): _cell(0, 1, 0, 1),
                ("item-a", 2): _cell(1, 0, 0, 1),
            },
        },
        contracts={
            "reuse_warehouse": dict(contract),
            "initial_warehouse": dict(contract),
        },
        zero_roles=["reuse_warehouse", "initial_warehouse"],
    )

    check = score_simulation(context)[0]

    assert check.score == 50
    assert check.reason_code == "WAREHOUSE_ZERO_BUSINESS_VIOLATION"
    assert check.evidence["zero_business_contract"]["violation_count"] == 2


def test_s3_zero_business_full_axis_of_zero_cells_passes() -> None:
    zero_cells = {
        ("item-a", 1): _cell(0, 0, 0, 0),
        ("item-a", 2): _cell(0, 0, 0, 0),
    }
    context = _warehouse_context(
        {"reuse_warehouse": zero_cells},
        contracts={
            "reuse_warehouse": {
                "source": "fixed",
                "coverage": "exact",
                "week_kind": "project",
                "start_week": 1,
                "end_week": 2,
            }
        },
        zero_roles=["reuse_warehouse"],
    )

    check = score_simulation(context)[0]

    assert check.score == 100
    assert check.evidence["zero_business_contract"]["evaluated_units"] == 2


def test_gap_fixed_axis_is_conjoined_once_with_s2() -> None:
    context = flow_context(("S2", "S3", "S4"))
    context.component.parameters["gap_week_contract"] = {
        "source": "fixed",
        "coverage": "exact",
        "week_kind": "project",
        "start_week": 5,
        "end_week": 13,
    }

    checks = {check.check_id.rsplit(".", 1)[-1]: check for check in score_simulation(context)}

    assert checks["S2"].score == pytest.approx(100 * 8 / 9)
    assert checks["S2"].reason_code == "GAP_WEEK_CONTRACT_MISMATCH"
    assert "gap_week_contract" in checks["S2"].evidence
    assert "gap_week_contract" not in checks["S3"].evidence
    assert "gap_week_contract" not in checks["S4"].evidence


def test_gap_site_plan_contains_axis_allows_terminal_simulation_weeks() -> None:
    context = flow_context(("S2",))
    context.component.parameters["gap_week_contract"] = {
        "source": "site-plan",
        "coverage": "contains",
        "week_kind": "project",
    }
    scheduled_plan = pd.DataFrame(
        {
            "project_week": [5, 11],
            "week_issue": ["", ""],
            "week_label": ["2027WK5", "2027WK11"],
        }
    )

    check = score_simulation(context, scheduled_plan=scheduled_plan)[0]

    assert check.score == 100
    axis = check.evidence["gap_week_contract"]
    assert axis["expected_weeks"] == list(range(5, 12))
    assert axis["extra_weeks"] == [12]


def test_gap_site_plan_axis_missing_middle_week_is_not_diagnostic_only() -> None:
    context = flow_context(("S2",))
    context.component.parameters["gap_week_contract"] = {
        "source": "site-plan",
        "coverage": "contains",
        "week_kind": "project",
    }
    scheduled_plan = pd.DataFrame(
        {
            "project_week": [5, 13],
            "week_issue": ["", ""],
            "week_label": ["2027WK5", "2027WK13"],
        }
    )

    check = score_simulation(context, scheduled_plan=scheduled_plan)[0]

    assert check.score == pytest.approx(100 * 8 / 9)
    assert check.reason_code == "GAP_WEEK_CONTRACT_MISMATCH"
    assert check.evidence["gap_week_contract"]["missing_weeks"] == [13]


def test_week_contract_configuration_is_strict() -> None:
    assert _validate_week_axis_contract(
        {
            "source": "fixed",
            "coverage": "exact",
            "week_kind": "project",
            "start_week": 1,
            "end_week": 56,
        },
        label="contract",
    )["end_week"] == 56

    with pytest.raises(ConfigurationError, match="declare exactly"):
        _validate_week_axis_contract(
            {
                "source": "site-plan",
                "coverage": "contains",
                "week_kind": "project",
                "end_week": 56,
            },
            label="contract",
        )

    with pytest.raises(ConfigurationError, match="range is invalid"):
        _validate_week_axis_contract(
            {
                "source": "fixed",
                "coverage": "exact",
                "week_kind": "project",
                "start_week": 10,
                "end_week": 9,
            },
            label="contract",
        )


def test_missing_site_plan_axis_is_a_candidate_scoring_failure() -> None:
    context = flow_context(("S2",))
    context.component.parameters["gap_week_contract"] = {
        "source": "site-plan",
        "coverage": "contains",
        "week_kind": "project",
    }

    check = score_simulation(context, scheduled_plan=None)[0]

    assert check.score == 0
    assert check.reason_code == "GAP_WEEK_CONTRACT_UNRESOLVED"
    assert check.evidence["gap_week_contract"]["site_plan_axis_issue_count"] == 1


def _site_rollout_axis_context(columns: list[str] | None):
    context = flow_context(("S2",))
    context.component.parameters["site_rollout_week_contract"] = {
        "source": "site-plan",
        "coverage": "exact",
        "week_kind": "iso",
    }
    if columns is not None:
        frame = pd.DataFrame(columns=["region", "Type", "site_type", *columns])
        context.artifacts.artifacts["site_rollout"] = _resolution(
            "site_rollout",
            table=frame,
        )
    scheduled_plan = pd.DataFrame(
        {
            "project_week": [5, 7],
            "week_issue": ["", ""],
            "week_label": ["2027WK5", "2027WK7"],
        }
    )
    return context, scheduled_plan


def test_site_rollout_requires_exact_ordered_iso_date_headers() -> None:
    context, scheduled_plan = _site_rollout_axis_context(
        ["2/1~2/7", "2/8~2/14", "2/15~2/21"]
    )

    check = score_simulation(context, scheduled_plan=scheduled_plan)[0]

    assert check.score == 100
    assert check.evidence["site_rollout_week_contract"][
        "expected_weeks"
    ] == [202705, 202706, 202707]


def test_site_rollout_reordered_date_headers_are_a_scoring_failure() -> None:
    context, scheduled_plan = _site_rollout_axis_context(
        ["2/8~2/14", "2/1~2/7", "2/15~2/21"]
    )

    check = score_simulation(context, scheduled_plan=scheduled_plan)[0]

    assert check.score == pytest.approx(100 / 3)
    assert check.reason_code == "SITE_ROLLOUT_WEEK_CONTRACT_MISMATCH"
    assert check.evidence["site_rollout_week_contract"]["order_mismatch"] is True


def test_missing_site_rollout_is_a_candidate_scoring_failure() -> None:
    context, scheduled_plan = _site_rollout_axis_context(None)

    check = score_simulation(context, scheduled_plan=scheduled_plan)[0]

    assert check.score == 0
    assert check.reason_code == "SITE_ROLLOUT_WEEK_CONTRACT_UNRESOLVED"
    assert check.evidence["site_rollout_week_contract"]["error"] == (
        "site_rollout is missing or unusable"
    )


_ZERO_GAP_METRICS = [
    "Dismantled",
    "Arrive",
    "DismantledSupply",
    "ReuseConsumed",
    "total_dismantled",
    "initial_inventory",
    "totalArrive",
    "totalReuse",
]


def _zero_gap_business_context():
    context = flow_context(("S2", "S3"))
    context.component.parameters["gap_zero_business_metrics"] = list(
        _ZERO_GAP_METRICS
    )
    gap = context.artifacts.get("gap")
    assert gap is not None and isinstance(gap.normalized, dict)
    for block in gap.normalized["blocks"].values():
        for metric in ("Dismantled", "Arrive", "DismantledSupply", "ReuseConsumed"):
            block["metrics"][metric] = {
                week: 0 for week in gap.normalized["weeks"]
            }
        for metric in (
            "total_dismantled",
            "initial_inventory",
            "totalArrive",
            "totalReuse",
        ):
            block["summary"][metric] = 0
    for metric in (
        "total_dismantled",
        "initial_inventory",
        "totalArrive",
        "totalReuse",
    ):
        gap.table.loc[:, metric] = 0
    reuse = context.artifacts.get("reuse_warehouse")
    assert reuse is not None and isinstance(reuse.normalized, dict)
    for cell in reuse.normalized.values():
        cell.update(_cell(0, 0, 0, 0))
    return context


def test_gap_zero_business_contract_accepts_explicit_full_zero_evidence() -> None:
    context = _zero_gap_business_context()

    checks = {
        check.check_id.rsplit(".", 1)[-1]: check
        for check in score_simulation(context)
    }

    assert checks["S2"].score == 100
    evidence = checks["S2"].evidence["gap_zero_business_metrics"]
    assert evidence["evaluated_unit_count"] == 36
    assert evidence["nonzero_unit_count"] == 0
    assert "gap_zero_business_metrics" not in checks["S3"].evidence


def test_gap_zero_business_contract_penalizes_weekly_and_summary_business() -> None:
    context = _zero_gap_business_context()
    gap = context.artifacts.get("gap")
    assert gap is not None and isinstance(gap.normalized, dict)
    block = next(iter(gap.normalized["blocks"].values()))
    block["metrics"]["ReuseConsumed"][5] = 2
    block["summary"]["totalReuse"] = 2
    gap.table.loc[:, "totalReuse"] = 2

    check = score_simulation(context)[0]

    assert check.score == pytest.approx(100 * 34 / 36)
    assert check.reason_code == "GAP_ZERO_BUSINESS_VIOLATION"
    evidence = check.evidence["gap_zero_business_metrics"]
    assert evidence["nonzero_unit_count"] == 2
    assert {unit["metric"] for unit in evidence["nonzero_unit_samples"]} == {
        "ReuseConsumed",
        "totalReuse",
    }


def test_gap_zero_business_contract_does_not_treat_missing_summary_as_zero() -> None:
    context = _zero_gap_business_context()
    gap = context.artifacts.get("gap")
    assert gap is not None
    gap.table = gap.table.drop(columns=["totalReuse"])

    check = score_simulation(context)[0]

    assert check.score == pytest.approx(100 * 35 / 36)
    assert check.reason_code == "GAP_ZERO_BUSINESS_CONTRACT_UNRESOLVED"
    evidence = check.evidence["gap_zero_business_metrics"]
    assert evidence["missing_unit_count"] == 1
