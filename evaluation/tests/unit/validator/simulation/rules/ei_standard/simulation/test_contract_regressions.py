from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    CheckResult,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.simulation import score_simulation


@pytest.fixture
def contract_root() -> Path:
    """The scorer only records this path; these unit tests perform no file I/O."""

    return Path(".")


def _resolved(
    role: str,
    frame: pd.DataFrame,
    *,
    quantity_errors: tuple[dict[str, object], ...] = (),
) -> ArtifactResolution:
    return ArtifactResolution(
        role,
        "SELECTED_CANONICAL",
        Path(f"{role}.csv"),
        table=frame,
        normalized=frame,
        quantity_error_count=len(quantity_errors),
        quantity_errors=quantity_errors,
    )


def _context(
    tmp_path: Path,
    *,
    rule_ids: tuple[str, ...],
    parameters: dict[str, object],
    frames: dict[str, pd.DataFrame],
    quantity_error_roles: set[str] | None = None,
    quantity_error_columns: dict[str, str] | None = None,
) -> RuleContext:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        tuple(
            CheckConfig(f"simulation.{rule_id}", ("prompt/x.txt:L1",))
            for rule_id in rule_ids
        ),
        parameters,
    )
    specs = {
        role: ArtifactSpec(
            role,
            "question" if role == "substitution_source" else "candidate",
            f"{role}.csv",
            () if role == "substitution_source" else (f"{role}.csv",),
        )
        for role in frames
    }
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        specs,
        {"simulation": component},
        tmp_path / "validator.yaml",
    )
    quantity_error_roles = quantity_error_roles or set()
    quantity_error_columns = quantity_error_columns or {}
    artifacts = {
        role: _resolved(
            role,
            frame,
            quantity_errors=(
                (
                    {
                        "row": 3,
                        "column": quantity_error_columns.get(
                            role,
                            "required_qty",
                        ),
                        "value": 1.5,
                    },
                )
                if role in quantity_error_roles
                else ()
            ),
        )
        for role, frame in frames.items()
    }
    return RuleContext(
        profile,
        component,
        ArtifactBundle(tmp_path, (), artifacts),
    )


def _single_relation() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": ["G1"],
            "priority": [1],
            "target_item_code": ["A"],
            "target_qty": [1],
            "sub_item_code": ["B"],
            "sub_qty": [1],
            "new_issue_item_code": [""],
        }
    )


def _scope(actions: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SITE ID": [f"S{index}" for index in range(1, len(actions) + 1)],
            "REGION": ["R1"] * len(actions),
            "ITEM CODE": ["A"] * len(actions),
            "NEW": [1 if action == "install" else 0 for action in actions],
            "REDEPLOY": [0] * len(actions),
            "DISMANTLE": [1 if action == "dismantle" else 0 for action in actions],
        }
    )


def _plan(actions: tuple[str, ...], weeks: tuple[int, ...] | None = None) -> pd.DataFrame:
    weeks = weeks or tuple(2 for _ in actions)
    return pd.DataFrame(
        {
            "site_name": [f"S{index}" for index in range(1, len(actions) + 1)],
            "region": ["R1"] * len(actions),
            "site_action": list(actions),
            "week_num": list(weeks),
            "mos_weekly_plan": [f"WK{week}" for week in weeks],
            "status": ["scheduled"] * len(actions),
        }
    )


def _material_final(
    actions: tuple[str, ...],
    quantities: tuple[float, ...],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": [f"S{index}" for index in range(1, len(actions) + 1)],
            "region": ["R1"] * len(actions),
            "action": list(actions),
            "item_code": ["B"] * len(actions),
            "required_qty": list(quantities),
            "original_bom": ["A"] * len(actions),
            "original_bom_qty": [1] * len(actions),
        }
    )


def _material_parameters(*, quantity_mode: str = "signed-action") -> dict[str, object]:
    return {
        "s1_substitution_mode": "priority-row-views",
        "s1_traceability_mode": "explicit-origin",
        "s1_region_scope": "exact",
        "final_bom_quantity_mode": quantity_mode,
    }


def _priority_relation_views() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": ["G1_P1", "G1_P2", "G2_P1", "G2_P2"],
            "priority": [1, 2, 1, 2],
            "target_item_code": ["A", "", "X", ""],
            "target_qty": [1, "", 1, ""],
            "sub_item_code": ["", "B", "", "Y"],
            "sub_qty": [0, 1, 0, 1],
            "new_issue_item_code": ["", "", "", ""],
        }
    )


def _expanded_relation_views() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": [
                "G1_T1_P1",
                "G1_T1_P2",
                "G1_T2_P1",
                "G1_T2_P2",
            ],
            "priority": [1, 2, 1, 2],
            "target_item_code": ["A", "", "X", ""],
            "target_qty": [1, "", 1, ""],
            "sub_item_code": ["", "B", "", "Y"],
            "sub_qty": [0, 1, 0, 1],
            "new_issue_item_code": ["", "", "", ""],
        }
    )


def _scope_materials(materials: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SITE ID": [f"S{index}" for index in range(1, len(materials) + 1)],
            "REGION": ["R1"] * len(materials),
            "ITEM CODE": list(materials),
            "NEW": [1] * len(materials),
            "REDEPLOY": [0] * len(materials),
            "DISMANTLE": [0] * len(materials),
        }
    )


def _final_material_pairs(
    pairs: tuple[tuple[str, str], ...],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": [f"S{index}" for index in range(1, len(pairs) + 1)],
            "region": ["R1"] * len(pairs),
            "action": ["install"] * len(pairs),
            "item_code": [actual for _, actual in pairs],
            "required_qty": [1] * len(pairs),
            "original_bom": [original for original, _ in pairs],
            "original_bom_qty": [1] * len(pairs),
        }
    )


def _checks_by_id(context: RuleContext) -> dict[str, CheckResult]:
    return {
        check.check_id.rsplit(".", 1)[-1]: check
        for check in score_simulation(context)
    }


def test_s1_local_target_conflict_keeps_valid_view_and_uses_partial_c_for_p_apply(
    contract_root: Path,
) -> None:
    source = _priority_relation_views()
    candidate = source.copy()
    candidate.loc[candidate["solution_id"].eq("G2_P2"), [
        "target_item_code",
        "target_qty",
    ]] = ["Z", 1]
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A", "X")),
            "final_material": _final_material_pairs((("A", "B"), ("X", "Y"))),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "PARTIAL", check.evidence
    assert check.reason_code == "MODEL_OR_APPLICATION_MISMATCH"
    assert check.evidence["expected_relation_objects"] == 2
    assert check.evidence["candidate_relation_objects"] == 1
    assert check.evidence["intersection_relation_objects"] == 1
    assert check.evidence["union_relation_objects"] == 2
    assert check.evidence["invalid_relation_views"] == 1
    assert len(check.evidence["invalid_relation_view_examples"]) == 1
    assert check.evidence["model_fidelity"] == 0.5
    assert check.evidence["candidate_units"] == 2
    assert check.evidence["valid_candidate_units"] == 1
    assert check.evidence["application_precision"] == 0.5
    assert check.evidence["final_rate"] == 0.25
    assert check.score == 25.0


def test_s1_new_issue_conflict_only_removes_the_ambiguous_fallback(
    contract_root: Path,
) -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1_P1", "G1_P2", "G1_P3"],
            "priority": [1, 2, 3],
            "target_item_code": ["A", "", ""],
            "target_qty": [1, "", ""],
            "sub_item_code": ["", "B", "N"],
            "sub_qty": [0, 1, 1],
            "new_issue_item_code": ["N", "N", "N"],
        }
    )
    candidate = source.copy()
    candidate.loc[candidate["solution_id"].eq("G1_P2"), "new_issue_item_code"] = "X"
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A",)),
            "final_material": _final_material_pairs((("A", "B"),)),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "PARTIAL", check.evidence
    assert check.evidence["expected_relation_objects"] == 2
    assert check.evidence["candidate_relation_objects"] == 1
    assert check.evidence["intersection_relation_objects"] == 1
    assert check.evidence["union_relation_objects"] == 2
    assert check.evidence["invalid_relation_views"] == 1
    assert check.evidence["model_fidelity"] == 0.5
    assert check.evidence["application_precision"] == 1.0
    assert check.evidence["final_rate"] == 0.5
    assert check.score == 50.0


def test_s1_expanded_pm_mismatch_is_local_not_invalid_artifact(
    contract_root: Path,
) -> None:
    source = _expanded_relation_views()
    candidate = source.copy()
    candidate.loc[candidate["solution_id"].eq("G1_T2_P2"), "solution_id"] = (
        "G1_T2_P3"
    )
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters={
            **_material_parameters(),
            "s1_substitution_mode": "expanded-bidirectional",
        },
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A",)),
            "final_material": _final_material_pairs((("A", "B"),)),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "PASS", check.evidence
    assert check.reason_code == ""
    assert check.evidence["expected_relation_objects"] == 2
    assert check.evidence["candidate_relation_objects"] == 2
    assert check.evidence["intersection_relation_objects"] == 2
    assert check.evidence["union_relation_objects"] == 2
    assert check.evidence["invalid_relation_views"] == 1
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.evidence["final_rate"] == 1.0
    assert check.score == 100.0


def test_s1_legacy_priority_suffix_recovers_the_unique_target_anchor(
    contract_root: Path,
) -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["SOL", "SOL"],
            "priority": [1, 2],
            "target_item_code": ["A", "A"],
            "target_qty": [1, 1],
            "sub_item_code": ["A", "B"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["", ""],
        }
    )
    candidate = pd.DataFrame(
        {
            "solution_id": ["SOL_1", "SOL_2"],
            "priority": [1, 2],
            "target_item_code": ["A", ""],
            "target_qty": [1, ""],
            "sub_item_code": ["A", "B"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["", ""],
        }
    )
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters={
            **_material_parameters(),
            "s1_substitution_mode": "legacy-combination",
        },
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A",)),
            "final_material": _final_material_pairs((("A", "B"),)),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "PASS", check.evidence
    assert check.evidence["expected_relation_objects"] == 1
    assert check.evidence["candidate_relation_objects"] == 1
    assert check.evidence["invalid_relation_views"] == 0
    assert check.evidence["invalid_relation_view_examples"] == []
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_all_local_conflicts_yield_zero_model_not_invalid_artifact(
    contract_root: Path,
) -> None:
    source = _priority_relation_views().iloc[:2].reset_index(drop=True)
    candidate = source.copy()
    candidate.loc[candidate["solution_id"].eq("G1_P2"), [
        "target_item_code",
        "target_qty",
    ]] = ["Z", 1]
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A",)),
            "final_material": _final_material_pairs((("A", "A"),)),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "FAIL", check.evidence
    assert check.reason_code == "MODEL_OR_APPLICATION_MISMATCH"
    assert check.evidence["expected_relation_objects"] == 1
    assert check.evidence["candidate_relation_objects"] == 0
    assert check.evidence["intersection_relation_objects"] == 0
    assert check.evidence["union_relation_objects"] == 1
    assert check.evidence["invalid_relation_views"] == 1
    assert check.evidence["model_fidelity"] == 0.0
    assert check.score == 0.0


def test_s1_missing_relation_columns_remains_invalid_artifact(
    contract_root: Path,
) -> None:
    source = _priority_relation_views().iloc[:2].reset_index(drop=True)
    candidate = source.drop(columns=["sub_qty"])
    context = _context(
        contract_root,
        rule_ids=("S1",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": candidate,
            "substitution_source": source,
            "scope_input": _scope_materials(("A",)),
            "final_material": _final_material_pairs((("A", "A"),)),
        },
    )

    check = _checks_by_id(context)["S1"]

    assert check.status == "FAIL"
    assert check.reason_code == "INVALID_ARTIFACT"
    assert check.score == 0.0
    assert "invalid_relation_views" not in check.evidence


def test_fractional_final_quantity_only_invalidates_its_own_s1_s5_unit(
    contract_root: Path,
) -> None:
    actions = ("install", "install")
    relations = _single_relation()
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": _material_final(actions, (1, 1.5)),
            "site_plan": _plan(actions),
        },
        quantity_error_roles={"final_material"},
    )

    checks = _checks_by_id(context)
    s1 = checks["S1"]
    s5 = checks["S5"]

    assert s1.status == "PARTIAL", s1.evidence
    assert s1.evidence["model_fidelity"] == 1.0
    assert s1.evidence["candidate_units"] == 2
    assert s1.evidence["valid_candidate_units"] == 1
    assert s1.evidence["application_precision"] == 0.5
    assert s1.score == 50.0
    assert s5.status == "PARTIAL", s5.evidence
    assert s5.evidence["authoritative_quantity"] == 2
    assert s5.evidence["covered_quantity"] == 1
    assert s5.evidence["recall_rate"] == 0.5
    assert s5.score == 50.0


def test_s5_fails_when_candidate_plan_has_no_authoritative_action_overlap(
    contract_root: Path,
) -> None:
    relations = _single_relation()
    foreign_plan = _plan(("install",))
    foreign_plan["site_name"] = ["S9"]
    foreign_final = _material_final(("install",), (1,))
    foreign_final["site_name"] = ["S9"]
    context = _context(
        contract_root,
        rule_ids=("S5",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(("install",)),
            "final_material": foreign_final,
            "site_plan": foreign_plan,
        },
    )

    check = _checks_by_id(context)["S5"]

    assert check.status == "FAIL"
    assert check.score == 0.0
    assert check.reason_code == "NO_SCHEDULED_AUTHORITY_OVERLAP"
    assert check.evidence["scope_authority_actions"] == 1
    assert check.evidence["scope_authority_quantity"] == 1
    assert check.evidence["scheduled_authority_actions"] == 0
    assert check.evidence["authoritative_quantity"] == 0
    assert check.evidence["scheduled_actions_without_authority"] == 1
    assert check.evidence["scheduled_actions_without_authority_examples"] == [
        "r1|s9|install"
    ]


def test_s5_is_not_applicable_when_standardized_scope_has_no_authority(
    contract_root: Path,
) -> None:
    relations = _single_relation()
    filtered_scope = pd.DataFrame(
        {
            "site id": ["S1"],
            "region": ["R1"],
            "item_code": ["RRU5905(2100M)"],
            "band": ["2100"],
            "ntnr": ["4T4R"],
            "required_qty": [1],
        }
    )
    context = _context(
        contract_root,
        rule_ids=("S5",),
        parameters={
            **_material_parameters(),
            "s5_scope_material_mode": "base-pk-standardized",
        },
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": filtered_scope,
            "final_material": _material_final(("install",), (1,)),
            "site_plan": _plan(("install",)),
        },
    )

    check = _checks_by_id(context)["S5"]

    assert check.status == "NOT_APPLICABLE"
    assert check.score == 0.0
    assert check.reason_code == "NOT_APPLICABLE"
    assert check.evidence["scope_authority_actions"] == 0
    assert check.evidence["scope_authority_quantity"] == 0
    assert check.evidence["scheduled_authority_actions"] == 0
    assert check.evidence["authoritative_quantity"] == 0


def test_s5_keeps_scoring_the_nonempty_scheduled_authority_intersection(
    contract_root: Path,
) -> None:
    relations = _single_relation()
    partly_foreign_plan = _plan(("install", "install"))
    partly_foreign_plan["site_name"] = ["S1", "S9"]
    context = _context(
        contract_root,
        rule_ids=("S5",),
        parameters=_material_parameters(),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(("install", "install")),
            "final_material": _material_final(("install",), (1,)),
            "site_plan": partly_foreign_plan,
        },
    )

    check = _checks_by_id(context)["S5"]

    assert check.status == "PASS", check.evidence
    assert check.score == 100.0
    assert check.reason_code == ""
    assert check.evidence["scope_authority_actions"] == 2
    assert check.evidence["scope_authority_quantity"] == 2
    assert check.evidence["scheduled_authority_actions"] == 1
    assert check.evidence["authoritative_quantity"] == 1
    assert check.evidence["covered_quantity"] == 1
    assert check.evidence["recall_rate"] == 1.0
    assert check.evidence["scheduled_actions_without_authority"] == 1


def test_unused_original_bom_qty_issue_does_not_zero_s1_or_s5(
    contract_root: Path,
) -> None:
    actions = ("install",)
    relations = _single_relation()
    final = _material_final(actions, (1,))
    final["original_bom_qty"] = None
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": final,
            "site_plan": _plan(actions),
        },
        quantity_error_roles={"final_material"},
        quantity_error_columns={"final_material": "original_bom_qty"},
    )

    checks = _checks_by_id(context)

    assert checks["S1"].score == 100.0, checks["S1"].evidence
    assert checks["S5"].score == 100.0, checks["S5"].evidence


@pytest.mark.parametrize("quantity", (1, -1))
def test_absolute_final_quantity_mode_accepts_either_dismantle_sign(
    contract_root: Path,
    quantity: int,
) -> None:
    actions = ("dismantle",)
    relations = _single_relation()
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(quantity_mode="absolute"),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": _material_final(actions, (quantity,)),
            "site_plan": _plan(actions),
        },
    )

    checks = _checks_by_id(context)

    assert checks["S1"].score == 0.0, checks["S1"].evidence
    assert checks["S1"].evidence["application_precision"] == 0.0
    assert checks["S1"].evidence["final_bom_quantity_mode"] == "absolute"
    assert checks["S1"].evidence["action_scope"] == ["install"]
    assert checks["S1"].evidence["out_of_scope_final_rows"] == 1
    assert checks["S5"].score == 100.0, checks["S5"].evidence
    assert checks["S5"].evidence["covered_quantity"] == 1
    assert checks["S5"].evidence["final_bom_quantity_mode"] == "absolute"


@pytest.mark.parametrize("quantity", (1, -1))
def test_dismantle_absolute_mode_accepts_either_dismantle_sign(
    contract_root: Path,
    quantity: int,
) -> None:
    actions = ("dismantle",)
    relations = _single_relation()
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(quantity_mode="dismantle-absolute"),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": _material_final(actions, (quantity,)),
            "site_plan": _plan(actions),
        },
    )

    checks = _checks_by_id(context)

    assert checks["S1"].score == 0.0, checks["S1"].evidence
    assert (
        checks["S1"].evidence["final_bom_quantity_mode"]
        == "dismantle-absolute"
    )
    assert checks["S1"].evidence["out_of_scope_final_rows"] == 1
    assert checks["S5"].score == 100.0, checks["S5"].evidence
    assert checks["S5"].evidence["covered_quantity"] == 1
    assert (
        checks["S5"].evidence["final_bom_quantity_mode"]
        == "dismantle-absolute"
    )
    sign_counts = checks["S5"].evidence["final_bom_submitted_sign_counts"]
    assert sign_counts["dismantle"][
        "positive" if quantity > 0 else "negative"
    ] == 1
    assert checks["S5"].evidence["final_bom_normalization"] == {
        "direction": "action",
        "magnitude": "abs(required_qty)",
        "install": "+abs(required_qty)",
        "dismantle": "-abs(required_qty)",
        "accepted_submitted_signs": {
            "install": ["positive"],
            "dismantle": ["positive", "negative"],
        },
    }


def test_dismantle_absolute_mode_still_rejects_negative_install_quantity(
    contract_root: Path,
) -> None:
    actions = ("install",)
    relations = _single_relation()
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(quantity_mode="dismantle-absolute"),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": _material_final(actions, (-1,)),
            "site_plan": _plan(actions),
        },
    )

    checks = _checks_by_id(context)

    assert checks["S1"].score == 0.0, checks["S1"].evidence
    assert checks["S1"].evidence["invalid_final_rows"] == 1
    assert checks["S1"].evidence["final_bom_submitted_sign_counts"][
        "install"
    ]["negative"] == 1
    assert checks["S5"].score == 0.0, checks["S5"].evidence
    assert checks["S5"].evidence["invalid_final_rows"] == 1


@pytest.mark.parametrize(
    ("quantity", "expected_s5"),
    ((-1, 100.0), (1, 0.0)),
)
def test_signed_action_mode_still_requires_negative_dismantle_quantity(
    contract_root: Path,
    quantity: int,
    expected_s5: float,
) -> None:
    actions = ("dismantle",)
    relations = _single_relation()
    context = _context(
        contract_root,
        rule_ids=("S1", "S5"),
        parameters=_material_parameters(quantity_mode="signed-action"),
        frames={
            "material_substitution": relations,
            "substitution_source": relations,
            "scope_input": _scope(actions),
            "final_material": _material_final(actions, (quantity,)),
            "site_plan": _plan(actions),
        },
    )

    checks = _checks_by_id(context)

    assert checks["S1"].score == 0.0, checks["S1"].evidence
    assert checks["S5"].score == expected_s5, checks["S5"].evidence
    assert checks["S1"].evidence["final_bom_quantity_mode"] == "signed-action"
    assert checks["S1"].evidence["out_of_scope_final_rows"] == 1
    assert checks["S1"].evidence["invalid_final_rows"] == 0
    assert checks["S5"].evidence["final_bom_quantity_mode"] == "signed-action"
    if quantity > 0:
        assert checks["S5"].evidence["invalid_final_rows"] == 1


@pytest.mark.parametrize(
    ("require_blank", "expected_score", "expected_errors"),
    (
        (False, 100.0, set()),
        (
            True,
            0.0,
            {"INAPPLICABLE_MONTH_NOT_EMPTY", "INAPPLICABLE_WEEK_NOT_EMPTY"},
        ),
    ),
)
def test_s6_inactive_time_fields_are_checked_only_when_configured(
    contract_root: Path,
    require_blank: bool,
    expected_score: float,
    expected_errors: set[str],
) -> None:
    final = pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["R1"],
            "action": ["install"],
            "install_wk_label": ["WK6"],
            "install_month": ["2026M2"],
            "dismantle_wk_label": ["WK6"],
            "dismantle_month": ["2026M2"],
        }
    )
    context = _context(
        contract_root,
        rule_ids=("S6",),
        parameters={
            "s6_time_mode": "action-week-month",
            "s6_week_kind": "project",
            "planning_year": 2026,
            "week_to_month": "four-week-project",
            "project_start_month": 1,
            "s6_require_inactive_time_blank": require_blank,
        },
        frames={
            "final_material": final,
            "site_plan": _plan(("install",), (6,)),
        },
    )

    check = _checks_by_id(context)["S6"]

    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["require_inactive_time_blank"] is require_blank
    assert check.score == expected_score, check.evidence
    observed_errors = (
        set(check.evidence["failures"][0]["errors"])
        if check.evidence["failures"]
        else set()
    )
    assert observed_errors == expected_errors


def test_pk0002_project_start_month_one_maps_wk6_and_wk13(
    contract_root: Path,
) -> None:
    actions = ("install", "dismantle")
    final = pd.DataFrame(
        {
            "site_name": ["S1", "S2"],
            "region": ["R1", "R1"],
            "action": list(actions),
            "install_wk_label": ["WK6", ""],
            "install_month": ["2026M2", ""],
            "dismantle_wk_label": ["", "WK13"],
            "dismantle_month": ["", "2026M4"],
        }
    )
    context = _context(
        contract_root,
        rule_ids=("S6",),
        parameters={
            "s6_time_mode": "action-week-month",
            "s6_week_kind": "project",
            "planning_year": 2026,
            "week_to_month": "four-week-project",
            "project_start_month": 1,
            "s6_require_inactive_time_blank": True,
        },
        frames={
            "final_material": final,
            "site_plan": _plan(actions, (6, 13)),
        },
    )

    check = _checks_by_id(context)["S6"]

    assert check.evidence["comparable_actions"] == 2
    assert check.evidence["time_correct_actions"] == 2
    assert check.evidence["time_accuracy"] == 1.0
    assert check.score == 100.0, check.evidence


def test_s6_four_week_project_months_cross_the_natural_year(
    contract_root: Path,
) -> None:
    weeks = (48, 49, 52, 53, 67)
    months = ("2026M12", "2027M1", "2027M1", "2027M2", "2027M5")
    final = pd.DataFrame(
        {
            "site_name": [f"S{index}" for index in range(1, 6)],
            "region": ["R1"] * 5,
            "action": ["install"] * 5,
            "install_wk_label": [f"WK{week}" for week in weeks],
            "install_month": list(months),
            "dismantle_wk_label": [""] * 5,
            "dismantle_month": [""] * 5,
        }
    )
    parameters = {
        "s6_time_mode": "action-week-month",
        "s6_week_kind": "project",
        "planning_year": 2026,
        "week_to_month": "four-week-project",
        "project_start_month": 1,
        "s6_require_inactive_time_blank": True,
    }
    context = _context(
        contract_root,
        rule_ids=("S6",),
        parameters=parameters,
        frames={
            "final_material": final,
            "site_plan": _plan(("install",) * 5, weeks),
        },
    )

    check = _checks_by_id(context)["S6"]

    assert check.evidence["comparable_actions"] == 5
    assert check.evidence["time_correct_actions"] == 5
    assert check.evidence["time_accuracy"] == 1.0
    assert check.score == 100.0, check.evidence

    wrong_year = final.copy()
    wrong_year.loc[1, "install_month"] = "2026M1"
    mismatch = _context(
        contract_root,
        rule_ids=("S6",),
        parameters=parameters,
        frames={
            "final_material": wrong_year,
            "site_plan": _plan(("install",) * 5, weeks),
        },
    )
    mismatch_check = _checks_by_id(mismatch)["S6"]

    assert mismatch_check.evidence["comparable_actions"] == 5
    assert mismatch_check.evidence["time_correct_actions"] == 4
    assert mismatch_check.evidence["time_accuracy"] == 0.8
    assert mismatch_check.score == 80.0
    assert mismatch_check.evidence["failures"][0]["errors"] == [
        "FINAL_MONTH_MISMATCH"
    ]
