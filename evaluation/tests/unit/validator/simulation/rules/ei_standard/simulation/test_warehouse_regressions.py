from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.adapters import _normalize_warehouse
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.simulation import score_simulation


def _context(
    normalized: dict,
    *,
    issues: tuple[dict, ...] = (),
    rule_id: str = "S3",
) -> RuleContext:
    run_dir = Path("run")
    role = "reuse_warehouse" if rule_id == "S3" else "new_warehouse"
    parameters = {"s3_required_roles": ["reuse_warehouse"]}
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig(f"simulation.{rule_id}", ("prompt/x.txt:L1",)),),
        parameters,
    )
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        {role: ArtifactSpec(role, "candidate", f"{role}.csv", (f"{role}.csv",), "ei.warehouse", False)},
        {"simulation": component},
        run_dir / "validator.yaml",
    )
    resolution = ArtifactResolution(
        role,
        "SELECTED_CANONICAL",
        run_dir / f"{role}.csv",
        table=pd.DataFrame({"week": [1]}),
        normalized=normalized,
        validation_issues=issues,
    )
    return RuleContext(
        profile,
        component,
        ArtifactBundle(run_dir, (), {role: resolution}),
    )


def test_s3_counts_one_bad_submitted_unit_once() -> None:
    warehouse = {
        ("a", 1): {"opening": 0, "inbound": 2, "outbound": 0, "closing": 2},
        ("a", 2): {"opening": 2, "inbound": 0, "outbound": 1, "closing": 1},
    }
    issues = (
        {"code": "NON_INTEGER_QUANTITY", "affected_unit_ids": ["wide:a:3"]},
        {"code": "UNVERIFIABLE_OPENING", "affected_unit_ids": ["wide:a:3"]},
    )

    result = score_simulation(_context(warehouse, issues=issues))

    check = result[0]
    assert check.evidence["cells"] == 2
    assert check.evidence["invalid_source_cells"] == 1
    assert check.evidence["failed_unit_ids"] == ["reuse_warehouse:wide:a:3"]
    assert check.score == round(100 * 2 / 3, 6)


def test_s4_adapter_fractional_fields_fail_the_normalized_unit_once() -> None:
    frame = pd.DataFrame(
        {
            "item_code": ["A"],
            "project_week": [1],
            "opening": [0],
            "inbound": [0.5],
            "outbound": [1.5],
            "closing": [-1],
        }
    )
    warehouse, issues = _normalize_warehouse(frame)

    result = score_simulation(_context(warehouse, issues=issues, rule_id="S4"))

    check = result[0]
    assert check.evidence["cells"] == 1
    assert check.evidence["evaluated_units"] == 1
    assert check.evidence["valid"] == 0
    assert check.evidence["invalid_source_cells"] == 1
    assert check.evidence["extra_invalid_source_cells"] == 0
    assert check.score == 0.0


def test_s4_allows_negative_inventory_but_not_negative_flow() -> None:
    valid_negative_inventory = {
        ("a", 1): {"opening": 0, "inbound": 0, "outbound": 2, "closing": -2},
        ("a", 2): {"opening": -2, "inbound": 0, "outbound": 1, "closing": -3},
    }
    negative_flow = {
        ("a", 1): {"opening": 0, "inbound": -1, "outbound": 0, "closing": -1},
    }

    assert score_simulation(_context(valid_negative_inventory, rule_id="S4"))[0].score == 100.0
    assert score_simulation(_context(negative_flow, rule_id="S4"))[0].score == 0.0


def _missing_warehouse_context(
    rule_id: str,
    *,
    full_credit: bool,
) -> RuleContext:
    run_dir = Path("run")
    roles = ("reuse_warehouse", "initial_warehouse") if rule_id == "S3" else ("new_warehouse",)
    parameters = {
        "s3_required_roles": ["reuse_warehouse", "initial_warehouse"],
        **(
            {f"{rule_id.casefold()}_missing_evidence_policy": "full-credit"}
            if full_credit
            else {}
        ),
    }
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig(f"simulation.{rule_id}", ("prompt/x.txt:L1",)),),
        parameters,
    )
    specs = {
        role: ArtifactSpec(
            role,
            "candidate",
            f"{role}.csv",
            (f"{role}.csv",),
            "ei.warehouse",
            False,
        )
        for role in roles
    }
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        specs,
        {"simulation": component},
        run_dir / "validator.yaml",
    )
    resolutions = {
        role: ArtifactResolution(role, "MISSING", None, error="not found")
        for role in roles
    }
    return RuleContext(
        profile,
        component,
        ArtifactBundle(run_dir, (), resolutions),
    )


def test_easy_medium_missing_optional_warehouses_receive_full_s3_s4_credit() -> None:
    for rule_id, maximum in (("S3", 100.0), ("S4", 100.0)):
        check = score_simulation(
            _missing_warehouse_context(rule_id, full_credit=True)
        )[0]

        assert check.score == maximum
        assert check.status == "PASS"
        assert check.reason_code == "OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT"
        assert check.evidence["missing_roles"]


def test_hard_hell_missing_warehouses_still_fail_s3_s4() -> None:
    for rule_id in ("S3", "S4"):
        check = score_simulation(
            _missing_warehouse_context(rule_id, full_credit=False)
        )[0]

        assert check.score == 0.0
        assert check.reason_code == "MISSING_OR_INVALID_ARTIFACT"


def test_easy_medium_partial_warehouse_submission_does_not_receive_full_credit() -> None:
    context = _missing_warehouse_context("S3", full_credit=True)
    context.artifacts.artifacts["reuse_warehouse"] = ArtifactResolution(
        "reuse_warehouse",
        "SELECTED_CANONICAL",
        Path("run/reuse_warehouse.csv"),
        table=pd.DataFrame({"week": [1]}),
        normalized={
            ("a", 1): {
                "opening": 0,
                "inbound": 1,
                "outbound": 0,
                "closing": 1,
            }
        },
    )

    check = score_simulation(context)[0]

    assert check.score == 0.0
    assert check.reason_code == "MISSING_OR_INVALID_ARTIFACT"


def test_s3_checks_continuity_independently_for_each_scope() -> None:
    warehouse = {
        ("scope=north", "a", 1): {"opening": 0, "inbound": 1, "outbound": 0, "closing": 1},
        ("scope=north", "a", 2): {"opening": 1, "inbound": 0, "outbound": 1, "closing": 0},
        ("scope=south", "a", 1): {"opening": 0, "inbound": 5, "outbound": 0, "closing": 5},
        ("scope=south", "a", 2): {"opening": 5, "inbound": 0, "outbound": 1, "closing": 4},
    }

    result = score_simulation(_context(warehouse))

    assert result[0].score == 100.0
    assert result[0].evidence["cells"] == 4


def test_s2_uses_bom_identity_input2_scope_maturity_and_reuse_rate(
) -> None:
    run_dir = Path("run")
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S2", ("prompt/x.txt:L1",)),),
        {"repair_weeks": 6, "reuse_rate": 0.9},
    )
    artifacts = {
        "reuse_warehouse": ArtifactSpec(
            "reuse_warehouse",
            "candidate",
            "weekly_dismantle_warehouse.csv",
            ("weekly_dismantle_warehouse.csv",),
            "ei.warehouse",
            False,
        ),
        "site_material_timeline": ArtifactSpec(
            "site_material_timeline",
            "candidate",
            "site_material_timeline.csv",
            ("site_material_timeline.csv",),
            "ei.timeline",
            False,
        ),
        "initial_inventory_source": ArtifactSpec(
            "initial_inventory_source",
            "question",
            "Input2.xlsx",
            (),
            "generic",
            True,
        ),
    }
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        artifacts,
        {"simulation": component},
        run_dir / "validator.yaml",
    )
    timeline = pd.DataFrame(
        {
            "item_code": ["RRU5526(850M&900M)", "NOT-IN-INPUT2"],
            "required_qty": [-10, -20],
            "action": ["dismantle", "dismantle"],
            "week_num": [1, 1],
        }
    )
    inventory_source = pd.DataFrame(
        {
            "*BOM/编码": ["rru5526(850m&900m)"],
            "Initial Inventory/初始库存": [0],
        }
    )
    warehouse = {
        ("rru5526(850m&900m)", 7): {
            "opening": 0,
            "inbound": 9,
            "outbound": 0,
            "closing": 9,
        }
    }
    bundle = ArtifactBundle(
        run_dir,
        (),
        {
            "reuse_warehouse": ArtifactResolution(
                "reuse_warehouse",
                "SELECTED_CANONICAL",
                run_dir / "weekly_dismantle_warehouse.csv",
                table=pd.DataFrame({"week": [7]}),
                normalized=warehouse,
            ),
            "site_material_timeline": ArtifactResolution(
                "site_material_timeline",
                "SELECTED_CANONICAL",
                run_dir / "site_material_timeline.csv",
                table=timeline,
                normalized=timeline,
            ),
            "initial_inventory_source": ArtifactResolution(
                "initial_inventory_source",
                "SELECTED_CANONICAL",
                run_dir / "Input2.xlsx",
                table=inventory_source,
                normalized=inventory_source,
            ),
        },
    )

    result = score_simulation(
        RuleContext(profile, component, bundle)
    )

    check = result[0]
    assert check.score == 100.0
    assert check.evidence["matched_qty"] == 9.0
    assert check.evidence["combined_qty"] == 9.0
    assert check.evidence["excluded_unstorable_objects"] == 1
    assert check.evidence["excluded_unstorable_qty"] == 18.0
