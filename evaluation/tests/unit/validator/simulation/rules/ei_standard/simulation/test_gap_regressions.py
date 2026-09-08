from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from simulation.ei.core.adapters import (
    _recover_gap_rows_missing_control_cells,
    align_gap_reuse_inbound,
    normalize_gap_wide,
    normalize_timeline_mature_supply,
)
from simulation.ei.scoring.contracts import _artifact_roles_for_checks
from simulation.ei.core.config import load_profile
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.simulation import (
    _gap_s2,
    _gap_s3,
    _gap_wide_contract,
    score_simulation,
)


TARGET_QUESTIONS = (
    "EI-56TESTPK0006-easy-v1.2",
    "EI-56TESTPK0006-medium-v1.2",
    "EI-56TESTPK0007-easy-v1.2",
    "EI-56TESTPK0007-medium-v1.2",
    "EI-56TESTPK0008-easy-v1.2",
    "EI-56TESTPK0008-medium-v1.2",
)
HARD_TARGET_QUESTIONS = (
    "EI-56TESTPK0006-hard-v1.2",
    "EI-56TESTPK0007-hard-v1.2",
    "EI-56TESTPK0008-hard-v1.2",
)


def test_pk0005_enables_s2_from_gap_without_changing_s3_evidence() -> None:
    profile = load_profile("EI-56TESTPK0005-v1.2")
    simulation = profile.components["simulation"]
    check_ids = {value.check_id for value in simulation.checks}

    assert "simulation.S2" in check_ids
    assert profile.artifacts["gap"].schema == "ei.gap-wide"
    assert simulation.parameters["s2_evidence_mode"] == "gap-wide"
    assert simulation.parameters["repair_weeks"] == 7
    assert simulation.parameters["reuse_rate"] == 0.95
    assert _artifact_roles_for_checks(profile, ("simulation.S2",)) == (
        "gap",
        "reuse_warehouse",
    )
    assert "reuse_warehouse" in _artifact_roles_for_checks(
        profile,
        ("simulation.S3",),
    )


def _gap_frame() -> pd.DataFrame:
    weeks = [f"WK{value}" for value in range(5, 13)]
    base = {
        "region": "Region-1",
        "item_code": "ITEM-A",
        "device": "ITEM-A",
        "category": "RRU",
        "total_dismantled": 3,
        "initial_inventory": 1,
        "totalArrive": 3,
        "totalReuse": 2,
        "totalDemand": 5,
        "totalGap": 2,
    }
    values = {
        "Dismantled": {"WK5": 3},
        "Arrive": {"WK7": 3},
        "DismantledSupply": {"WK7": 3},
        "ReuseConsumed": {"WK7": 2},
        "Demand": {"WK5": 1, "WK7": 4},
        "GAP": {
            "WK5": 0,
            "WK6": 0,
            "WK7": 2,
            "WK8": 2,
            "WK9": 2,
            "WK10": 2,
            "WK11": 2,
            "WK12": 2,
        },
    }
    rows = [
        {
            **{key: "" for key in base},
            "week": "Date",
            **{week: f"date-{week}" for week in weeks},
        }
    ]
    for metric, weekly in values.items():
        rows.append(
            {
                **base,
                "week": metric,
                **{week: weekly.get(week, 0) for week in weeks},
            }
        )
    return pd.DataFrame(rows, columns=[*base, "week", *weeks])


def _contract(frame: pd.DataFrame):
    payload, issues = normalize_gap_wide(frame)
    assert issues == ()
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)
    return aligned["blocks"], tuple(aligned["weeks"])


def _gap_context(
    rule_id: str,
    frame: pd.DataFrame,
    *,
    warehouse: dict | None = None,
) -> RuleContext:
    maximum = {"S2": 25.0, "S3": 25.0}[rule_id]
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig(f"simulation.{rule_id}", ("prompt/x.txt:L1",)),),
        {
            "simulation_evidence_mode": "gap-wide",
            "gap_role": "gap",
            "repair_weeks": 2,
            "reuse_rate": 1.0,
        },
    )
    artifact = ArtifactSpec(
        "gap",
        "candidate",
        "gap.csv",
        ("gap.csv",),
        "ei.gap-wide",
        True,
    )
    artifacts = {"gap": artifact}
    if warehouse is not None:
        artifacts["reuse_warehouse"] = ArtifactSpec(
            "reuse_warehouse",
            "candidate",
            "weekly_dismantle_warehouse.csv",
            ("weekly_dismantle_warehouse.csv",),
            "ei.warehouse",
            False,
        )
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        artifacts,
        {"simulation": component},
        Path("validator.yaml"),
    )
    normalized_gap, gap_issues = normalize_gap_wide(frame)
    resolution = ArtifactResolution(
        "gap",
        "SELECTED_CANONICAL",
        Path("gap.csv"),
        table=frame,
        normalized=normalized_gap,
        validation_issues=gap_issues,
    )
    resolutions = {"gap": resolution}
    if warehouse is not None:
        resolutions["reuse_warehouse"] = ArtifactResolution(
            "reuse_warehouse",
            "SELECTED_CANONICAL",
            Path("weekly_dismantle_warehouse.csv"),
            table=pd.DataFrame(),
            normalized=warehouse,
        )
    return RuleContext(
        profile,
        component,
        ArtifactBundle(Path("."), (), resolutions),
    )


def test_all_easy_medium_profiles_enable_prompt_authorized_simulation() -> None:
    for question in TARGET_QUESTIONS:
        profile = load_profile(question)
        simulation = profile.components["simulation"]
        check_ids = {value.check_id for value in simulation.checks}
        assert {
            "simulation.S1",
            "simulation.S2",
            "simulation.S3",
            "simulation.S4",
            "simulation.S5",
            "simulation.S6",
        } <= check_ids
        assert simulation.parameters["s2_evidence_mode"] == "gap-wide"
        assert simulation.parameters["s3_evidence_mode"] == "warehouse"
        assert simulation.parameters["s3_required_roles"] == [
            "reuse_warehouse",
            "initial_warehouse",
        ]
        assert simulation.parameters["s3_missing_evidence_policy"] == "full-credit"
        assert simulation.parameters["s4_missing_evidence_policy"] == "full-credit"
        assert (
            profile.components["reuse-accounting"].parameters[
                "r5_missing_evidence_policy"
            ]
            == "full-credit"
        )
        assert simulation.parameters["s1_candidate_substitution_required"] is False
        assert all(not hasattr(value, "weight") for value in profile.components.values())


def test_easy_and_medium_profiles_do_not_own_total_weights() -> None:
    easy = load_profile("EI-56TESTPK0006-easy-v1.2")
    medium = load_profile("EI-56TESTPK0006-medium-v1.2")
    assert set(easy.components) == {
        "effective-delivery",
        "simulation",
        "reuse-accounting",
    }
    assert set(medium.components) == {
        "effective-delivery",
        "scheduling",
        "scheduling-pacing",
        "simulation",
        "reuse-accounting",
    }
    assert all(not hasattr(value, "weight") for value in easy.components.values())
    assert all(not hasattr(value, "weight") for value in medium.components.values())


def test_easy_medium_s2_uses_gap_while_s3_uses_the_two_reuse_warehouses() -> None:
    for question in TARGET_QUESTIONS:
        profile = load_profile(question)

        s2_roles = _artifact_roles_for_checks(profile, ("simulation.S2",))
        assert "gap" in s2_roles

        s3_roles = _artifact_roles_for_checks(profile, ("simulation.S3",))
        assert "gap" not in s3_roles
        assert set(s3_roles) == {"reuse_warehouse", "initial_warehouse"}
        assert "new_warehouse" not in s3_roles

        s4_roles = _artifact_roles_for_checks(profile, ("simulation.S4",))
        assert set(s4_roles) == {"new_warehouse"}


def test_hard_profiles_resolve_gap_and_actual_reuse_warehouse_for_s2() -> None:
    for question in HARD_TARGET_QUESTIONS:
        profile = load_profile(question)
        simulation = profile.components["simulation"]
        assert "s3_missing_evidence_policy" not in simulation.parameters
        assert "s4_missing_evidence_policy" not in simulation.parameters
        assert (
            "r5_missing_evidence_policy"
            not in profile.components["reuse-accounting"].parameters
        )

        assert profile.artifacts["gap"].required is True
        assert simulation.parameters["s2_evidence_mode"] == "gap-wide"
        assert simulation.parameters["gap_role"] == "gap"

        s2_roles = _artifact_roles_for_checks(profile, ("simulation.S2",))
        assert {"gap", "reuse_warehouse", "site_material_timeline"} <= set(s2_roles)

        balance_roles = _artifact_roles_for_checks(profile, ("simulation.S3",))
        assert "gap" not in balance_roles
        assert {"reuse_warehouse", "initial_warehouse"} <= set(balance_roles)
        assert "new_warehouse" not in balance_roles


def test_valid_gap_contract_passes_s2_s3() -> None:
    blocks, weeks = _contract(_gap_frame())
    assert _gap_s2(blocks, weeks, repair_weeks=2, reuse_rate=1.0)[0] == 1.0
    assert _gap_s3(blocks, weeks)[0] == 1.0


def test_s2_combines_gap_maturity_and_actual_warehouse_inbound() -> None:
    warehouse = {
        ("item-a", 7): {
            "opening": 0,
            "inbound": 3,
            "outbound": 0,
            "closing": 3,
        }
    }

    check = score_simulation(
        _gap_context("S2", _gap_frame(), warehouse=warehouse)
    )[0]

    assert check.score == 100.0
    assert check.evidence["evidence_level"] == "weekly"
    assert check.evidence["maturity_interval"]["matched_qty"] == 3.0
    assert check.evidence["warehouse_inbound"]["matched_qty"] == 3.0


def test_s2_uses_gap_warehouse_flow_when_optional_dedicated_file_is_absent() -> None:
    context = _gap_context("S2", _gap_frame())
    context.question.artifacts["reuse_warehouse"] = ArtifactSpec(
        "reuse_warehouse",
        "candidate",
        "weekly_dismantle_warehouse.csv",
        ("weekly_dismantle_warehouse.csv",),
        "ei.warehouse",
        False,
    )

    check = score_simulation(context)[0]

    assert check.score == 100.0
    assert check.evidence["matched_qty"] == 3.0
    assert check.evidence["combined_qty"] == 3.0
    assert check.evidence["dedicated_warehouse_role_configured"] is True
    assert check.evidence["dedicated_warehouse_present"] is False
    assert check.evidence["warehouse_evidence_source"] == "gap-aligned-inbound"


def test_s2_compact_gap_keeps_total_evidence_but_cannot_pass_weekly_interval() -> None:
    frame = pd.DataFrame(
        [
            {
                "region": "Region-1",
                "item_code": "ITEM-A",
                "total_dismantled": 10,
                "initial_inventory": 0,
                "totalArrive": 10,
                "totalReuse": 0,
                "totalDemand": 0,
                "totalGap": 0,
                "week": "",
                "WK1": 0,
                "WK2": 0,
            }
        ]
    )
    warehouse = {
        ("item-a", 2): {
            "opening": 0,
            "inbound": 10,
            "outbound": 0,
            "closing": 10,
        }
    }

    check = score_simulation(_gap_context("S2", frame, warehouse=warehouse))[0]

    assert check.score == 50.0
    assert check.evidence["evidence_level"] == "aggregate"
    assert check.evidence["missing_dimension"] == "item_week_maturity_interval"


def test_gap_adapter_accepts_unambiguous_category_metric_carrier() -> None:
    frame = _gap_frame()
    business = frame["week"].ne("Date")
    frame.loc[business, "category"] = frame.loc[business, "week"]
    frame.loc[business, "week"] = "WK05-WK12"

    payload, issues = normalize_gap_wide(frame)

    assert issues == ()
    assert payload["metric_column"] == "category"
    assert _gap_s3(payload["blocks"], tuple(payload["weeks"]))[0] == 1.0


def test_gap_adapter_aligns_five_row_arrive_as_reuse_inbound() -> None:
    frame = _gap_frame()
    frame = frame.loc[~frame["week"].eq("DismantledSupply")].copy()
    frame.loc[frame["week"].eq("GAP"), "week"] = "NewProposal"

    payload, issues = normalize_gap_wide(frame)
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)
    rate, evidence = _gap_s2(
        aligned["blocks"],
        tuple(aligned["weeks"]),
        repair_weeks=2,
        reuse_rate=1.0,
    )

    assert "MISSING_GAP_METRICS" in {value["code"] for value in issues}
    assert "UNKNOWN_GAP_METRIC" not in {value["code"] for value in issues}
    assert aligned["inbound_alignment"]["selected"] == "arrive-flow"
    assert rate == 1.0
    assert evidence["matched_qty"] == 3.0


def test_gap_adapter_recovers_unlabeled_fixed_six_row_blocks() -> None:
    frame = _gap_frame()
    business = frame["week"].ne("Date")
    frame.loc[business, "week"] = ""
    frame.loc[~business, "region"] = "Date"
    frame.loc[~business, "week"] = ""

    payload, issues = normalize_gap_wide(frame)
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)

    assert issues == ()
    assert payload["metric_column"] == "fixed-six-row-order"
    assert payload["recoveries"][0]["code"] == "RECOVERED_GAP_FIXED_ROW_ORDER"
    assert aligned["inbound_alignment"]["selected"] == "dismantled-supply-flow"
    assert (
        aligned["inbound_alignment"]["recoveries"][0]["code"]
        == "RECOVERED_GAP_FIXED_ROW_ORDER"
    )
    assert _gap_s2(
        aligned["blocks"],
        tuple(aligned["weeks"]),
        repair_weeks=2,
        reuse_rate=1.0,
    )[0] == 1.0


def test_gap_adapter_recovers_one_blank_metric_inside_labeled_six_row_blocks() -> None:
    frame = _gap_frame()
    frame.loc[frame["week"].eq("Dismantled"), "week"] = ""

    payload, issues = normalize_gap_wide(frame)

    assert issues == ()
    recovery = next(
        value
        for value in payload["recoveries"]
        if value["code"] == "RECOVERED_GAP_SINGLE_BLANK_METRIC"
    )
    assert recovery["block_count"] == 1
    block = next(iter(payload["blocks"].values()))
    assert block["metrics"]["Dismantled"][5] == 3


def test_gap_adapter_preserves_compact_summary_without_inventing_weekly_semantics() -> None:
    frame = pd.DataFrame(
        [
            {
                "region": "Region-1",
                "item_code": "ITEM-A",
                "total_dismantled": 10,
                "initial_inventory": 0,
                "totalArrive": 9,
                "totalReuse": 2,
                "totalDemand": 4,
                "totalGap": 2,
                "week": "",
                "WK1": 0,
                "WK2": 2,
            }
        ]
    )

    payload, issues = normalize_gap_wide(frame)

    assert issues == ()
    assert payload["evidence_level"] == "aggregate"
    assert payload["blocks"] == {}
    block = next(iter(payload["aggregate_blocks"].values()))
    assert block["summary"]["total_arrive"] == 9
    assert block["submitted_weekly_series"] == {1: 0, 2: 2}
    assert block["weekly_semantics"] == "unlabelled"


def test_gap_adapter_preserves_compact_summary_without_week_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "region": "BMA",
                "item_code": "ITEM-A",
                "total_dismantled": 2,
                "initial_inventory": 0,
                "totalArrive": 1.8,
                "totalReuse": 0,
                "totalDemand": 0,
                "totalGap": 0,
                "week": "",
            }
        ]
    )

    payload, issues = normalize_gap_wide(frame)

    assert payload["evidence_level"] == "aggregate"
    block = next(iter(payload["aggregate_blocks"].values()))
    assert block["summary"]["total_arrive"] == 1.8
    assert "NON_INTEGER_QUANTITY" in {value["code"] for value in issues}


def test_gap_adapter_accepts_iso_week_headers_across_year_boundary() -> None:
    frame = _gap_frame().rename(
        columns={
            "WK5": "2023-W51",
            "WK6": "2023-W52",
            "WK7": "2024-W01",
            "WK8": "2024-W02",
            "WK9": "2024-W03",
            "WK10": "2024-W04",
            "WK11": "2024-W05",
            "WK12": "2024-W06",
        }
    )

    payload, issues = normalize_gap_wide(frame)
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)

    assert issues == ()
    assert payload["week_kind"] == "iso"
    assert tuple(payload["weeks"]) == (
        202351,
        202352,
        202401,
        202402,
        202403,
        202404,
        202405,
        202406,
    )
    assert aligned["inbound_alignment"]["selected"] == "dismantled-supply-flow"


def test_timeline_adapter_uses_iso_week_when_warehouse_is_iso() -> None:
    frame = pd.DataFrame(
        [
            {
                "item_code": "ITEM-A",
                "required_qty": 10,
                "action": "dismantle",
                "week_num": 26,
                "mos_weekly_plan": "2023-W52",
            }
        ]
    )

    mature, issues = normalize_timeline_mature_supply(
        frame,
        repair_weeks=2,
        reuse_rate=0.9,
        week_kind="iso",
    )

    assert issues == ()
    assert mature == {("item-a", 202402): 9.0}


def test_timeline_adapter_keeps_valid_rows_when_another_dismantle_week_is_blank() -> None:
    frame = pd.DataFrame(
        [
            {
                "item_code": "ITEM-A",
                "required_qty": 10,
                "action": "dismantle",
                "week_num": 1,
            },
            {
                "item_code": "ITEM-B",
                "required_qty": 5,
                "action": "dismantle",
                "week_num": "",
            },
        ]
    )

    mature, issues = normalize_timeline_mature_supply(
        frame,
        repair_weeks=2,
        reuse_rate=1.0,
        week_kind="project",
    )

    assert mature == {("item-a", 3): 10.0}
    assert {value["code"] for value in issues} == {"INVALID_WEEK"}


def test_gap_csv_adapter_recovers_omitted_control_cells_without_losing_weeks() -> None:
    headers = tuple(_gap_frame().columns)
    weekly = [str(value) for value in range(5, 13)]
    source_row = ["Region-1", "ITEM-A", "ITEM-A", "RRU", "3", "1", "3", "2", *weekly]

    rows, recovery = _recover_gap_rows_missing_control_cells(headers, [source_row])

    assert recovery is not None
    assert recovery["code"] == "RECOVERED_GAP_OMITTED_CONTROL_CELLS"
    assert len(rows[0]) == len(headers)
    assert rows[0][8:11] == ["", "", ""]
    assert rows[0][11:] == weekly


def test_gap_week_window_mismatch_is_scored_as_local_s2_failure() -> None:
    expected_columns = list(_gap_frame().columns)
    frame = _gap_frame().drop(columns="WK12")
    context = _gap_context("S2", frame)
    payload, issues = normalize_gap_wide(
        frame,
        {"exact_columns": expected_columns},
    )
    context.artifacts.artifacts["gap"].normalized = payload
    context.artifacts.artifacts["gap"].validation_issues = issues

    check = score_simulation(context)[0]

    assert "GAP_WEEK_WINDOW_MISMATCH" in {value["code"] for value in issues}
    assert check.reason_code != "INVALID_GAP_CONTRACT"
    assert 0 < check.score < 100.0


def test_gap_adapter_selects_supply_flow_when_arrive_is_new_issue() -> None:
    frame = _gap_frame()
    arrive = frame["week"].eq("Arrive")
    frame.loc[arrive, [f"WK{week}" for week in range(5, 13)]] = 0
    frame.loc[arrive, "WK5"] = 5

    payload, issues = normalize_gap_wide(frame)
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)

    assert issues == ()
    assert aligned["inbound_alignment"]["selected"] == "dismantled-supply-flow"
    assert _gap_s2(
        aligned["blocks"],
        tuple(aligned["weeks"]),
        repair_weeks=2,
        reuse_rate=1.0,
    )[0] == 1.0


def test_gap_adapter_derives_inbound_from_submitted_inventory() -> None:
    frame = _gap_frame()
    frame = frame.loc[~frame["week"].eq("Arrive")].copy()
    supply = frame["week"].eq("DismantledSupply")
    reuse = frame["week"].eq("ReuseConsumed")
    week_columns = [f"WK{week}" for week in range(5, 13)]
    frame.loc[supply, week_columns] = [0, 0, 2, 2, 2, 2, 2, 2]
    frame.loc[reuse, week_columns] = [0, 0, 1, 0, 0, 0, 0, 0]
    frame.loc[frame["week"].ne("Date"), "initial_inventory"] = 0

    payload, _ = normalize_gap_wide(frame)
    aligned = align_gap_reuse_inbound(payload, repair_weeks=2, reuse_rate=1.0)
    block = next(iter(aligned["blocks"].values()))

    assert (
        aligned["inbound_alignment"]["selected"]
        == "dismantled-supply-inventory"
    )
    assert block["metrics"]["ReuseInbound"][7] == 3
    assert _gap_s2(
        aligned["blocks"],
        tuple(aligned["weeks"]),
        repair_weeks=2,
        reuse_rate=1.0,
    )[0] == 1.0


def test_gap_adapter_rejects_conflicting_metric_carriers() -> None:
    frame = _gap_frame()
    frame.loc[frame["week"].eq("Demand"), "category"] = "GAP"

    payload, issues = normalize_gap_wide(frame)

    assert payload["metric_column"] == "week"
    assert "CONFLICTING_GAP_METRIC_COLUMNS" in {
        value["code"] for value in issues
    }
    check = score_simulation(_gap_context("S3", frame))[0]
    assert check.score == 0.0
    assert check.reason_code == "INVALID_GAP_CONTRACT"


def test_gap_adapter_normalizes_positive_shortage_to_signed_balance() -> None:
    frame = _gap_frame()
    business = frame["week"].ne("Date")
    for metric in ("Dismantled", "Arrive", "DismantledSupply", "ReuseConsumed"):
        frame.loc[frame["week"].eq(metric), [f"WK{week}" for week in range(5, 13)]] = 0
    demand = frame["week"].eq("Demand")
    frame.loc[demand, [f"WK{week}" for week in range(5, 13)]] = 0
    frame.loc[demand, "WK5"] = 1
    frame.loc[business, "initial_inventory"] = 0
    frame.loc[business, "totalArrive"] = 0
    frame.loc[business, "totalDemand"] = 1
    frame.loc[business, "totalGap"] = 1
    frame.loc[frame["week"].eq("GAP"), [f"WK{week}" for week in range(5, 13)]] = 1

    payload, issues = normalize_gap_wide(frame)

    assert issues == ()
    block = next(iter(payload["blocks"].values()))
    assert block["gap_sign_convention"] == "shortage-positive"
    assert set(block["metrics"]["GAP"].values()) == {-1}
    assert block["summary"]["total_gap"] == -1


def test_s2_detects_supply_before_the_prompt_maturity_week() -> None:
    frame = _gap_frame()
    inbound = frame["week"].isin(("Arrive", "DismantledSupply"))
    frame.loc[inbound, "WK6"] = 3
    frame.loc[inbound, "WK7"] = 0
    blocks, weeks = _contract(frame)
    rate, evidence = _gap_s2(blocks, weeks, repair_weeks=2, reuse_rate=1.0)
    assert rate < 1.0
    assert evidence["mismatch_count"] == 2


def test_s3_detects_reuse_that_makes_inventory_negative() -> None:
    frame = _gap_frame()
    reuse = frame["week"].eq("ReuseConsumed")
    frame.loc[reuse, "WK7"] = 5
    frame.loc[frame["week"].ne("Date"), "totalReuse"] = 5
    blocks, weeks = _contract(frame)
    rate, evidence = _gap_s3(blocks, weeks)
    assert rate < 1.0
    assert evidence["invalid"] > 0


def test_gap_contract_rejects_duplicate_business_metric() -> None:
    frame = _gap_frame()
    duplicate = copy.deepcopy(frame.loc[frame["week"].eq("Demand")].iloc[0])
    frame.loc[len(frame)] = duplicate
    _, _, issues = _gap_wide_contract(frame)
    assert "DUPLICATE_GAP_METRIC" in {value["code"] for value in issues}


def test_s2_and_s3_ignore_unscored_gap_balance_fields() -> None:
    frame = _gap_frame()
    gap = frame["week"].eq("GAP")
    frame.loc[gap, "WK7"] = 2.5
    frame.loc[gap, "totalGap"] = 2.5

    s2 = score_simulation(_gap_context("S2", frame))[0]
    s3 = score_simulation(_gap_context("S3", frame))[0]

    assert s2.score == 100.0
    assert s3.score == 100.0
    assert s3.reason_code == ""
    assert s3.evidence["invalid_source_units"] == 0


def test_s2_ignores_unknown_extra_gap_metric() -> None:
    frame = _gap_frame()
    extra = copy.deepcopy(frame.loc[frame["week"].eq("Demand")].iloc[0])
    extra["week"] = "AuditOnly"
    frame.loc[len(frame)] = extra

    s2 = score_simulation(_gap_context("S2", frame))[0]

    assert s2.score == 100.0
    assert s2.reason_code == ""
    assert s2.evidence["invalid_source_units"] == 0


def test_s2_noninteger_dependency_only_fails_the_affected_business_unit() -> None:
    frame = _gap_frame()
    second_region = frame.loc[frame["week"].ne("Date")].copy()
    second_region["region"] = "Region-2"
    frame = pd.concat([frame, second_region], ignore_index=True)
    affected = frame["region"].eq("Region-1") & frame["week"].isin(
        ("Arrive", "DismantledSupply")
    )
    frame.loc[affected, "WK7"] = 2.5

    s2 = score_simulation(_gap_context("S2", frame))[0]

    assert 0.0 < s2.score < 100.0
    assert s2.reason_code == "GAP_MATURE_SUPPLY_MISMATCH"
    assert s2.evidence["invalid_source_units"] == 1
    assert s2.evidence["invalid_score_unit_count"] == 1
    assert s2.evidence["matched_qty"] == 3.0
    assert s2.evidence["combined_qty"] == 6.0


def test_conflicting_total_gap_does_not_gate_s3() -> None:
    frame = _gap_frame()
    frame.loc[frame["week"].eq("Demand"), "totalGap"] = 99

    s3 = score_simulation(_gap_context("S3", frame))[0]

    assert s3.score == 100.0
    assert s3.reason_code == ""
    assert s3.evidence["invalid_source_units"] == 0


def test_s3_noninteger_dependency_deducts_affected_units_without_zeroing_check() -> None:
    frame = _gap_frame()
    reuse = frame["week"].eq("ReuseConsumed")
    frame.loc[reuse, "WK12"] = 0.5

    s3 = score_simulation(_gap_context("S3", frame))[0]

    assert 0.0 < s3.score < 100.0
    assert s3.reason_code == "REUSE_BALANCE_MISMATCH"
    assert s3.evidence["invalid_source_units"] == 1
    assert s3.evidence["units"] == 9
