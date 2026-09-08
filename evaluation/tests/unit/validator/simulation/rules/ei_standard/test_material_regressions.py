from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.reuse import score_reuse
from simulation.ei.rules.ei_standard.common import (
    _month_number,
    _scope_material_facts,
    _substitution_alternatives,
    _substitution_relation_objects,
)
from simulation.ei.rules.ei_standard.simulation import (
    _maximum_material_match,
    score_simulation,
)


def _resolved(
    role: str,
    frame: pd.DataFrame,
    normalized: object | None = None,
) -> ArtifactResolution:
    return ArtifactResolution(
        role,
        "SELECTED_CANONICAL",
        Path(f"{role}.csv"),
        table=frame,
        normalized=frame if normalized is None else normalized,
    )


def _context(
    tmp_path: Path,
    component: ComponentConfig,
    frames: dict[str, pd.DataFrame],
    _legacy_score_contract: dict[str, float],
    normalized: dict[str, object] | None = None,
) -> RuleContext:
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
        {component.name: component},
        tmp_path / "validator.yaml",
    )
    bundle = ArtifactBundle(
        tmp_path,
        (),
        {
            role: _resolved(role, frame, (normalized or {}).get(role))
            for role, frame in frames.items()
        },
    )
    return RuleContext(profile, component, bundle)


def _relations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": ["G1", "G2"],
            "priority": [1, 1],
            "target_item_code": ["A", "B"],
            "target_qty": [1, 1],
            "sub_item_code": ["B", "C"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["", ""],
        }
    )


def _single_relation() -> pd.DataFrame:
    return _relations().iloc[[0]].reset_index(drop=True)


def _candidate_with_extra_relation() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": ["G1", "G2"],
            "priority": [1, 1],
            "target_item_code": ["A", "A"],
            "target_qty": [1, 1],
            "sub_item_code": ["B", "D"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["", ""],
        }
    )


def _expanded_target_view(*substitutes: str) -> pd.DataFrame:
    priorities = list(range(1, len(substitutes) + 2))
    return pd.DataFrame(
        {
            "solution_id": [
                f"G1_T1_P{priority}"
                for priority in priorities
            ],
            "priority": priorities,
            "target_item_code": ["A", *([""] * len(substitutes))],
            "target_qty": [1, *([0] * len(substitutes))],
            "sub_item_code": ["", *substitutes],
            "sub_qty": [0, *([1] * len(substitutes))],
            "new_issue_item_code": [""] * len(priorities),
        }
    )


def _plan() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "site_action": ["install"],
            "week_num": [2],
            "mos_weekly_plan": ["2027WK2"],
            "region": ["R1"],
        }
    )


def _final() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "install_month": [1],
            "install_wk_label": ["2027WK2"],
            "dismantle_month": [""],
            "dismantle_wk_label": [""],
            "item_code": ["B"],
            "required_qty": [1],
            "original_bom": ["A"],
            "original_bom_qty": [1],
            "region": ["R1"],
            "action": ["install"],
        }
    )


def _scope() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SITE ID": ["S1"],
            "REGION": ["R1"],
            "ITEM CODE": ["A"],
            "NEW": [1],
            "REDEPLOY": [0],
            "DISMANTLE": [0],
        }
    )


def test_month_number_accepts_prompt_labels_dates_and_numeric_months() -> None:
    assert _month_number("2026M6") == 6
    assert _month_number("M6") == 6
    assert _month_number("2026-06-15") == 6
    assert _month_number(6) == 6
    assert _month_number("6") == 6
    assert _month_number("2026M0") is None
    assert _month_number("2026M13") is None
    assert _month_number("M13") is None
    assert _month_number(0) is None
    assert _month_number(13) is None


def test_scope_material_facts_prefers_explicit_action_columns_to_existing() -> None:
    scope = pd.DataFrame(
        {
            "Region/区域": ["BMA", "BMA"],
            "Site ID Radio/站点": ["BKA0001", "BKA0001"],
            "*BOM/编码": ["RRU_NEW2100", "RRU39712100"],
            "Existing/当前数量": [0, 3],
            "Installation Outbound/增加数量": [3, 0],
            "Dismantling Inbound/减少数量": [0, 3],
        }
    )

    assert _scope_material_facts(scope) == {
        "bma|bka0001|install": {"rru_new2100": 3},
        "bma|bka0001|dismantle": {"rru39712100": -3},
    }


def test_scope_material_facts_retains_single_signed_quantity_schema() -> None:
    scope = pd.DataFrame(
        {
            "REGION": ["R1", "R1"],
            "SITE ID": ["S1", "S1"],
            "ITEM CODE": ["A", "B"],
            "*数量": [2, -1],
        }
    )

    assert _scope_material_facts(scope) == {
        "r1|s1|install": {"a": 2},
        "r1|s1|dismantle": {"b": -1},
    }


def test_material_match_splits_independent_substitution_families() -> None:
    authority = {f"T{index}": 30 for index in range(20)}
    actual = {f"M{index}": 30 for index in range(20)}
    alternatives = {
        f"T{index}": ((1, ((f"M{index}", 1),)),)
        for index in range(20)
    }

    result = _maximum_material_match(authority, actual, alternatives)

    assert result["authority_quantity"] == 600
    assert result["covered_authority_quantity"] == 600
    assert result["consumed_actual_quantity"] == 600
    assert result["unmatched_actual"] == {}
    assert result["match_components"] == 20
    assert result["largest_match_component_targets"] == 1


def test_material_match_keeps_shared_material_targets_in_one_component() -> None:
    result = _maximum_material_match(
        {"A": 2, "X": 2},
        {"B": 2, "C": 1},
        {
            "A": ((1, (("B", 1),)), (1, (("C", 1),))),
            "X": ((1, (("B", 1),)),),
        },
    )

    assert result["authority_quantity"] == 4
    assert result["covered_authority_quantity"] == 3
    assert result["consumed_actual_quantity"] == 3
    assert result["unmatched_actual"] == {}
    assert result["match_components"] == 1
    assert result["largest_match_component_targets"] == 2


def test_material_match_preserves_unknown_actual_and_cross_component_tie_break() -> None:
    result = _maximum_material_match(
        {"A": 1, "X": 1},
        {"a": 1, "b": 1, "y": 1, "z": 1, "UNKNOWN": 7},
        {
            "A": ((1, (("a", 1),)), (1, (("z", 1),))),
            "X": ((1, (("b", 1),)), (1, (("y", 1),))),
        },
    )

    assert result["covered_authority_quantity"] == 2
    assert result["consumed_actual_quantity"] == 2
    assert result["unmatched_actual"] == {"UNKNOWN": 7, "z": 1, "y": 1}
    assert result["match_components"] == 2
    assert result["largest_match_component_targets"] == 1


def test_r3_is_target_contextual_not_a_global_target_blacklist(tmp_path: Path) -> None:
    component = ComponentConfig(
        "reuse-accounting",
        "ei.reuse",
        (CheckConfig("reuse-accounting.R3", ("prompt/x.txt:L1",)),),
        {"r3_validation_mode": "CONTEXTUAL", "r3_substitution_mode": "input-views"},
    )
    context = _context(
        tmp_path,
        component,
        {
            "final_material": _final(),
            "site_plan": _plan(),
            "substitution_source": _relations(),
            "scope_input": _scope(),
        },
        {"R3": 10.0},
    )

    result = score_reuse(context)

    assert result[0].score == 100.0
    assert result[0].evidence["legal_units"] == 1


def test_r3_authoritative_scope_prevents_candidate_denominator_shrink(tmp_path: Path) -> None:
    component = ComponentConfig(
        "reuse-accounting",
        "ei.reuse",
        (CheckConfig("reuse-accounting.R3", ("prompt/x.txt:L1",)),),
        {"r3_validation_mode": "CONTEXTUAL", "r3_substitution_mode": "input-views"},
    )
    plan = pd.concat(
        [_plan(), _plan().assign(site_name="S2")],
        ignore_index=True,
    )
    scope = pd.concat(
        [_scope(), _scope().assign(**{"SITE ID": "S2"})],
        ignore_index=True,
    )
    context = _context(
        tmp_path,
        component,
        {
            "final_material": _final(),
            "site_plan": plan,
            "substitution_source": _relations(),
            "scope_input": scope,
        },
        {"R3": 10.0},
    )

    result = score_reuse(context)

    assert result[0].score == 50.0
    assert result[0].evidence["applicable_units"] == 2
    assert result[0].evidence["failures"][0]["missing_final_rows"] is True


def test_structured_substitution_groups_same_priority_rows_into_one_bundle() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1", "G1"],
            "priority": [2, 2],
            "target_item_code": ["A", ""],
            "target_qty": [1, ""],
            "sub_item_code": ["B", "C"],
            "sub_qty": [1, 2],
            "new_issue_item_code": ["", ""],
        }
    )

    alternatives = _substitution_alternatives(source, mode="input-views")

    assert alternatives["a"] == ((1, (("b", 1), ("c", 2))),)


def test_structured_substitution_carries_target_across_priority_encoded_rows() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["Group 001_T1_P1", "Group 001_T1_P2", "Group 001_T1_P3"],
            "priority": [1, 2, 3],
            "target_item_code": ["A", "", ""],
            "target_qty": [1, 0, 0],
            "sub_item_code": ["", "B", "C"],
            "sub_qty": [0, 1, 1],
            "new_issue_item_code": ["N", "N", "N"],
        }
    )

    alternatives = _substitution_alternatives(source, mode="priority-row-views")

    assert alternatives["a"] == (
        (1, (("b", 1),)),
        (1, (("c", 1),)),
        (1, (("n", 1),)),
    )


def test_structured_substitution_preserves_explicit_target_identity() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1_T1_P1", "G1_T1_P2", "G1_T1_P3"],
            "priority": [1, 2, 3],
            "target_item_code": ["A", "", ""],
            "target_qty": [1, 0, 0],
            "sub_item_code": ["", "A", "B"],
            "sub_qty": [0, 1, 1],
            "new_issue_item_code": ["", "", ""],
        }
    )

    alternatives = _substitution_alternatives(source, mode="priority-row-views")

    assert alternatives["a"] == (
        (1, (("a", 1),)),
        (1, (("b", 1),)),
    )


def test_structured_substitution_treats_pandas_na_as_blank_continuation() -> None:
    source = pd.DataFrame(
        {
            "solution_id": pd.Series(["Group 001_T1_P1", "Group 001_T1_P2"], dtype="string"),
            "priority": [1, 2],
            "target_item_code": pd.Series(["A", pd.NA], dtype="string"),
            "target_qty": pd.Series([1, pd.NA], dtype="Int64"),
            "sub_item_code": pd.Series([pd.NA, "B"], dtype="string"),
            "sub_qty": pd.Series([0, 1], dtype="Int64"),
            "new_issue_item_code": pd.Series(["N", "N"], dtype="string"),
        }
    )

    alternatives = _substitution_alternatives(source, mode="priority-row-views")

    assert alternatives["a"] == (
        (1, (("b", 1),)),
        (1, (("n", 1),)),
    )


def test_structured_substitution_unions_quantity_specific_views() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1_P1", "G1_P2", "G2_P1", "G2_P2"],
            "priority": [1, 2, 1, 2],
            "target_item_code": ["A", "", "A", ""],
            "target_qty": [1, 0, 2, 0],
            "sub_item_code": ["", "B", "", "B"],
            "sub_qty": [0, 1, 0, 2],
            "new_issue_item_code": ["N", "N", "N", "N"],
        }
    )

    alternatives = _substitution_alternatives(source, mode="priority-row-views")

    assert alternatives["a"] == (
        (1, (("b", 1),)),
        (1, (("n", 1),)),
        (2, (("b", 2),)),
        (2, (("n", 2),)),
    )


def test_structured_substitution_unions_prompt_solution_rows() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1_T1_P1", "G1_T1_P2", "G1_T1_P3"],
            "priority": [1, 2, 3],
            "target_item_code": ["A", "", ""],
            "target_qty": [1, 0, 0],
            "sub_item_code": ["", "B", "C"],
            "sub_qty": [0, 1, 1],
            "new_issue_item_code": ["N", "N", "N"],
        }
    )

    alternatives = _substitution_alternatives(
        source,
        mode="expanded-bidirectional",
    )

    assert alternatives["a"] == (
        (1, (("b", 1),)),
        (1, (("c", 1),)),
        (1, (("n", 1),)),
    )


def test_structured_substitution_does_not_invent_a_second_fallback_quantity() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["G1_T1_P1", "G1_T1_P2"],
            "priority": [1, 2],
            "target_item_code": ["A", ""],
            "target_qty": [2, 0],
            "sub_item_code": ["", "N"],
            "sub_qty": [0, 1],
            "new_issue_item_code": ["N", "N"],
        }
    )

    alternatives = _substitution_alternatives(
        source,
        mode="expanded-bidirectional",
    )

    assert alternatives["a"] == ((2, (("n", 1),)),)


def _structured_relation_view() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": [
                "G1_T1_P1",
                "G1_T1_P2",
                "G1_T1_P2",
                "G1_T1_P3",
            ],
            "priority": [1, 2, 2, 3],
            "target_item_code": ["A", "", "", ""],
            "target_qty": [1, "", "", ""],
            "sub_item_code": ["", "B", "C", "N"],
            "sub_qty": [0, 2, 1, 1],
            "new_issue_item_code": ["N", "N", "N", "N"],
        }
    )


def test_relation_objects_preserve_and_bundle_priority_direction_and_fallback() -> None:
    source = _structured_relation_view()

    relations = _substitution_relation_objects(
        source,
        mode="priority-row-views",
    )

    assert relations == {
        ("g1_t1", "t1", "a", 1, 2, (("b", 2), ("c", 1)), "substitute"),
        ("g1_t1", "t1", "a", 1, 3, (("n", 1),), "fallback"),
    }

    reversed_direction = source.copy()
    reversed_direction.loc[0, "target_item_code"] = "X"
    assert _substitution_relation_objects(
        reversed_direction,
        mode="priority-row-views",
    ) != relations

    changed_priority = source.copy()
    changed_priority.loc[changed_priority["priority"].eq(2), "priority"] = 4
    assert _substitution_relation_objects(
        changed_priority,
        mode="priority-row-views",
    ) != relations

    changed_fallback_role = source.copy()
    changed_fallback_role["new_issue_item_code"] = ""
    changed_relations = _substitution_relation_objects(
        changed_fallback_role,
        mode="priority-row-views",
    )
    assert changed_relations != relations
    assert (
        "g1_t1",
        "t1",
        "a",
        1,
        3,
        (("n", 1),),
        "substitute",
    ) in changed_relations


def test_relation_objects_keep_same_target_in_distinct_tk_views() -> None:
    source = pd.DataFrame(
        {
            "solution_id": [
                "G1_T1_P1",
                "G1_T1_P2",
                "G1_T1_P3",
                "G1_T2_P1",
                "G1_T2_P2",
                "G1_T2_P3",
            ],
            "priority": [1, 2, 3, 1, 2, 3],
            "target_item_code": ["A", "", "", "A", "", ""],
            "target_qty": [1, "", "", 1, "", ""],
            "sub_item_code": ["", "B", "N", "", "C", "A"],
            "sub_qty": [0, 1, 1, 0, 1, 1],
            "new_issue_item_code": ["N", "N", "N", "A", "A", "A"],
        }
    )

    relations = _substitution_relation_objects(
        source,
        mode="expanded-bidirectional",
    )

    assert relations == {
        ("g1", "t1", "a", 1, 2, (("b", 1),), "substitute"),
        ("g1", "t1", "a", 1, 3, (("n", 1),), "fallback"),
        ("g1", "t2", "a", 1, 2, (("c", 1),), "substitute"),
        ("g1", "t2", "a", 1, 3, (("a", 1),), "fallback"),
    }
    assert not any(
        bundle == (("b", 1), ("c", 1))
        for _, _, _, _, _, bundle, _ in relations
    )


def test_legacy_target_fallback_resets_repeated_target_on_each_p1() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["arbitrary-a", "row-b", "another-c", "row-d"],
            "priority": [1, 2, 1, 2],
            "target_item_code": ["A", "A", "A", "A"],
            "target_qty": [1, 1, 1, 1],
            "sub_item_code": ["A", "B", "A", "C"],
            "sub_qty": [1, 1, 1, 1],
            "new_issue_item_code": ["A", "A", "A", "A"],
        }
    )

    relations = _substitution_relation_objects(
        source,
        mode="legacy-target-fallback",
    )

    assert relations == {
        ("a", "t1", "a", 1, 1, (("a", 1),), "fallback"),
        ("a", "t1", "a", 1, 2, (("b", 1),), "substitute"),
        ("a", "t1", "a", 1, 2, (("c", 1),), "substitute"),
    }
    assert not any(
        bundle == (("b", 1), ("c", 1))
        for _, _, _, _, _, bundle, _ in relations
    )


def test_legacy_target_fallback_compiles_explicit_relations_without_p1() -> None:
    source = pd.DataFrame(
        {
            "solution_id": ["SOL0001", "SOL0001"],
            "priority": [2, 3],
            "target_item_code": ["NEW_A", "NEW_A"],
            "target_qty": [1, 1],
            "sub_item_code": ["A_REUSE", "A_NEW"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["A_NEW", "A_NEW"],
        }
    )

    relations = _substitution_relation_objects(
        source,
        mode="legacy-target-fallback",
    )
    alternatives = _substitution_alternatives(
        source,
        mode="legacy-target-fallback",
    )

    assert relations == {
        ("new_a", "t1", "new_a", 1, 2, (("a_reuse", 1),), "substitute"),
        ("new_a", "t1", "new_a", 1, 3, (("a_new", 1),), "substitute"),
    }
    assert alternatives["new_a"] == (
        (1, (("a_new", 1),)),
        (1, (("a_reuse", 1),)),
    )


def test_legacy_missing_p1_still_rejects_target_and_fallback_ambiguity() -> None:
    target_conflict = pd.DataFrame(
        {
            "solution_id": ["SOL0001", "SOL0001"],
            "priority": [2, 3],
            "target_item_code": ["NEW_A", "NEW_B"],
            "target_qty": [1, 1],
            "sub_item_code": ["A_REUSE", "B_REUSE"],
            "sub_qty": [1, 1],
            "new_issue_item_code": ["A_NEW", "A_NEW"],
        }
    )
    fallback_conflict = target_conflict.copy()
    fallback_conflict["target_item_code"] = "NEW_A"
    fallback_conflict["new_issue_item_code"] = ["A_NEW", "A_OTHER_NEW"]

    for source, expected_error in (
        (target_conflict, "target conflicts within one legacy solution"),
        (fallback_conflict, "new_issue_item_code conflicts for one legacy target"),
    ):
        try:
            _substitution_relation_objects(
                source,
                mode="legacy-target-fallback",
            )
        except ValueError as exc:
            assert str(exc) == expected_error
        else:
            raise AssertionError(f"expected ValueError: {expected_error}")


def _expanded_input5(
    items: tuple[str, ...] = ("A", "B", "C", "N"),
) -> pd.DataFrame:
    rows: list[list[object]] = [["header", *([""] * 13)], ["header", *([""] * 13)]]
    for priority, item in enumerate(items, start=1):
        row: list[object] = [""] * 14
        row[0] = "Group 001"
        row[1] = priority
        row[2] = item
        row[5] = 1
        rows.append(row)
    return pd.DataFrame(rows)


def test_expanded_bidirectional_relations_keep_prompt_direction_boundaries() -> None:
    relations = _substitution_relation_objects(
        _expanded_input5(),
        mode="expanded-bidirectional",
    )
    directed_pairs = {
        (target, bundle[0][0])
        for _, _, target, _, _, bundle, _ in relations
        if len(bundle) == 1
    }
    targets = {target for _, _, target, _, _, _, _ in relations}

    assert {("a", "b"), ("a", "c"), ("a", "n")} <= directed_pairs
    assert {("b", "c"), ("c", "b")} <= directed_pairs
    assert ("b", "a") not in directed_pairs
    assert ("c", "a") not in directed_pairs
    assert "n" not in targets
    assert {
        role
        for _, _, target, _, _, bundle, role in relations
        if target in {"a", "b", "c"} and bundle == (("n", 1),)
    } == {"fallback"}


def test_expanded_source_only_treats_new_prefixed_final_row_as_fallback() -> None:
    relations = _substitution_relation_objects(
        _expanded_input5(("A", "B", "C", "D")),
        mode="expanded-bidirectional",
        fallback_requires_new_prefix=True,
    )

    targets = {target for _, _, target, _, _, _, _ in relations}
    assert targets == {"a", "b", "c", "d"}
    assert len(relations) == 9
    assert {role for *_, role in relations} == {"substitute"}
    assert (
        "group 001",
        "t4",
        "d",
        1,
        2,
        (("b", 1),),
        "substitute",
    ) in relations


def test_expanded_source_keeps_new_prefixed_final_row_as_fallback() -> None:
    relations = _substitution_relation_objects(
        _expanded_input5(("A", "B", "NEW_D")),
        mode="expanded-bidirectional",
        fallback_requires_new_prefix=True,
    )

    targets = {target for _, _, target, _, _, _, _ in relations}
    assert targets == {"a", "b"}
    assert "new_d" not in targets
    assert {
        role
        for _, _, _, _, _, bundle, role in relations
        if bundle == (("new_d", 1),)
    } == {"fallback"}


def test_expanded_source_prefix_policy_preserves_explicit_identity() -> None:
    relations = _substitution_relation_objects(
        _expanded_input5(("A", "A", "B")),
        mode="expanded-bidirectional",
        fallback_requires_new_prefix=True,
    )

    assert (
        "group 001",
        "t1",
        "a",
        1,
        2,
        (("a", 1),),
        "substitute",
    ) in relations


def test_expanded_source_alternatives_apply_prefix_policy_only_when_requested() -> None:
    source = _expanded_input5(("A", "B", "C"))

    s1_alternatives = _substitution_alternatives(
        source,
        mode="expanded-bidirectional",
        fallback_requires_new_prefix=True,
    )
    default_alternatives = _substitution_alternatives(
        source,
        mode="expanded-bidirectional",
    )

    assert s1_alternatives == {
        "a": ((1, (("b", 1),)), (1, (("c", 1),))),
        "b": ((1, (("c", 1),)),),
        "c": ((1, (("b", 1),)),),
    }
    assert default_alternatives == {
        "a": ((1, (("b", 1),)), (1, (("c", 1),))),
        "b": ((1, (("c", 1),)),),
    }


def test_s1_uses_new_prefix_policy_for_raw_input5_authority(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "expanded-bidirectional",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    candidate = pd.DataFrame(
        {
            "solution_id": [
                "Group 001_T1_P1",
                "Group 001_T1_P2",
                "Group 001_T1_P3",
                "Group 001_T2_P1",
                "Group 001_T2_P2",
                "Group 001_T3_P1",
                "Group 001_T3_P2",
            ],
            "priority": [1, 2, 3, 1, 2, 1, 2],
            "target_item_code": ["A", "", "", "B", "", "C", ""],
            "target_qty": [1, 0, 0, 1, 0, 1, 0],
            "sub_item_code": ["", "B", "C", "", "C", "", "B"],
            "sub_qty": [0, 1, 1, 0, 1, 0, 1],
            "new_issue_item_code": ["", "", "", "", "", "", ""],
        }
    )
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": candidate,
            "substitution_source": _expanded_input5(("A", "B", "C")),
            "scope_input": _scope(),
            "final_material": _final().assign(item_code="B"),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["source_fallback_policy"] == "new-prefix-only"
    assert check.evidence["expected_relation_objects"] == 4
    assert check.evidence["candidate_relation_objects"] == 4
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_scores_exact_model_and_legal_application(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_check_material_source": False,
        },
    )
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _single_relation(),
            "substitution_source": _single_relation(),
            "scope_input": _scope(),
            "final_material": _final(),
        },
        {"S1": 20.0},
    )

    result = score_simulation(context)

    assert result[0].score == 100.0, result[0].evidence
    assert result[0].evidence["model_fidelity"] == 1.0
    assert result[0].evidence["application_precision"] == 1.0
    assert result[0].evidence["final_rate"] == 1.0


def test_s1_scores_install_rows_only(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_check_material_source": False,
        },
    )
    dismantle = _final().assign(
        action="dismantle",
        item_code="X",
        required_qty=-1,
    )
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _single_relation(),
            "substitution_source": _single_relation(),
            "scope_input": _scope().assign(DISMANTLE=1),
            "final_material": pd.concat([_final(), dismantle], ignore_index=True),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.score == 100.0, check.evidence
    assert check.evidence["action_scope"] == ["install"]
    assert check.evidence["parsed_final_rows"] == 2
    assert check.evidence["out_of_scope_final_rows"] == 1
    assert check.evidence["final_rows"] == 1
    assert check.evidence["candidate_units"] == 1
    assert check.evidence["valid_candidate_units"] == 1


def test_s1_does_not_award_application_credit_for_dismantle_only_output(
    tmp_path: Path,
) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_check_material_source": False,
        },
    )
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _single_relation(),
            "substitution_source": _single_relation(),
            "scope_input": _scope().assign(NEW=0, DISMANTLE=1),
            "final_material": _final().assign(
                action="dismantle",
                required_qty=-1,
            ),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.score == 0.0, check.evidence
    assert check.evidence["action_scope"] == ["install"]
    assert check.evidence["parsed_final_rows"] == 1
    assert check.evidence["out_of_scope_final_rows"] == 1
    assert check.evidence["final_rows"] == 0
    assert check.evidence["candidate_units"] == 0
    assert check.evidence["application_precision"] == 0.0


def test_s1_preserves_explicit_identity_in_model_and_application(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "expanded-bidirectional",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    relation = _expanded_target_view("A", "B")
    final = _final().assign(item_code="A")
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": relation.copy(),
            "substitution_source": relation,
            "scope_input": _scope(),
            "final_material": final,
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["identity_relation_policy"] == "preserve-explicit-identity-alternatives"
    assert check.evidence["filtered_expected_identity_relations"] == 0
    assert check.evidence["filtered_candidate_identity_relations"] == 0
    assert check.evidence["filtered_candidate_identity_alternatives"] == 0
    assert check.evidence["expected_relation_objects"] == 2
    assert check.evidence["candidate_relation_objects"] == 2
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_preserves_explicit_identity_from_source_authority(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_candidate_substitution_required": False,
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    relation = _expanded_target_view("A", "B")
    context = _context(
        tmp_path,
        component,
        {
            "substitution_source": relation,
            "scope_input": _scope(),
            "final_material": _final().assign(item_code="A"),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["candidate_substitution_required"] is False
    assert check.evidence["identity_relation_policy"] == "preserve-explicit-identity-alternatives"
    assert check.evidence["candidate_units"] == 1
    assert check.evidence["valid_candidate_units"] == 1
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_accepts_direct_original_material_for_a_defined_target(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "expanded-bidirectional",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    relation = _expanded_target_view("B")
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": relation.copy(),
            "substitution_source": relation,
            "scope_input": _scope(),
            "final_material": _final().assign(item_code="A"),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["expected_relation_objects"] == 1
    assert check.evidence["candidate_relation_objects"] == 1
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["candidate_units"] == 1
    assert check.evidence["valid_candidate_units"] == 1
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_penalizes_a_candidate_for_omitting_explicit_identity(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "expanded-bidirectional",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    candidate = _expanded_target_view("A", "B")
    candidate.loc[1, "sub_item_code"] = ""
    candidate.loc[1, "sub_qty"] = 0
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": candidate,
            "substitution_source": _expanded_target_view("A", "B"),
            "scope_input": _scope(),
            "final_material": _final(),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["filtered_expected_identity_relations"] == 0
    assert check.evidence["filtered_candidate_identity_relations"] == 0
    assert check.evidence["model_fidelity"] == 0.5
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 50.0


def test_s1_uses_unit_identity_even_when_source_identity_ratio_is_coarser(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "expanded-bidirectional",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    relation = _expanded_target_view("A")
    relation.loc[0, "target_qty"] = 2
    relation.loc[1, "sub_qty"] = 2
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": relation.copy(),
            "substitution_source": relation,
            "scope_input": _scope(),
            "final_material": _final().assign(item_code="A"),
        },
        {"S1": 20.0},
    )

    check = score_simulation(context)[0]

    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["valid_candidate_units"] == 1
    assert check.evidence["application_precision"] == 1.0
    assert check.score == 100.0


def test_s1_uses_candidate_model_as_the_direct_authority_for_final_bom(
    tmp_path: Path,
) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_check_material_source": False,
        },
    )
    final = _final()
    final.loc[0, "item_code"] = "D"
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _candidate_with_extra_relation(),
            "substitution_source": _single_relation(),
            "scope_input": _scope(),
            "final_material": final,
        },
        {"S1": 20.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["model_fidelity"] == 0.5
    assert check.evidence["application_precision"] == 1.0
    assert check.evidence["final_rate"] == 0.5
    assert check.score == 50.0


def test_s1_multiplies_model_fidelity_by_application_precision(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_check_material_source": False,
        },
    )
    second_final = _final().assign(site_name="S2", item_code="X")
    final = pd.concat([_final().assign(item_code="D"), second_final], ignore_index=True)
    scope = pd.concat(
        [_scope(), _scope().assign(**{"SITE ID": "S2"})],
        ignore_index=True,
    )
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _candidate_with_extra_relation(),
            "substitution_source": _single_relation(),
            "scope_input": scope,
            "final_material": final,
            "site_plan": _plan(),
        },
        {"S1": 20.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["model_fidelity"] == 0.5
    assert check.evidence["application_precision"] == 0.5
    assert check.evidence["final_rate"] == 0.25
    assert check.score == 25.0


def test_s5_preserves_explicit_identity_across_relation_modes(
    tmp_path: Path,
) -> None:
    relation = _expanded_target_view("A", "B")
    scores: dict[str, tuple[float, float]] = {}

    for mode, candidate_required in (
        ("priority-row-views", False),
        ("expanded-bidirectional", True),
    ):
        component = ComponentConfig(
            "simulation",
            "ei.simulation",
            (CheckConfig("simulation.S5", ("prompt/x.txt:L1",)),),
            {
                "s1_candidate_substitution_required": candidate_required,
                "s1_substitution_mode": mode,
                "s1_traceability_mode": "explicit-origin",
                "s1_region_scope": "exact",
            },
        )
        frames = {
            "material_substitution": relation.copy(),
            "substitution_source": relation.copy(),
            "scope_input": _scope(),
            "site_plan": _plan(),
        }

        identity_context = _context(
            tmp_path,
            component,
            {**frames, "final_material": _final().assign(item_code="A")},
            {"S5": 5.0},
        )
        substitute_context = _context(
            tmp_path,
            component,
            {**frames, "final_material": _final().assign(item_code="B")},
            {"S5": 5.0},
        )

        identity_check = score_simulation(identity_context)[0]
        substitute_check = score_simulation(substitute_context)[0]
        scores[mode] = (identity_check.score, substitute_check.score)

        assert identity_check.evidence["identity_relation_policy"] == (
            "preserve-explicit-identity-alternatives"
        )
        assert identity_check.evidence["covered_quantity"] == 1
        assert substitute_check.evidence["covered_quantity"] == 1

    assert scores == {
        "priority-row-views": (100.0, 100.0),
        "expanded-bidirectional": (100.0, 100.0),
    }


def test_s5_preserves_legacy_identity_contract(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S5", ("prompt/x.txt:L1",)),),
        {
            "s1_candidate_substitution_required": True,
            "s1_substitution_mode": "legacy-target-fallback",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    relation = _expanded_target_view("A")
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": relation.copy(),
            "substitution_source": relation,
            "scope_input": _scope(),
            "final_material": _final().assign(item_code="A"),
            "site_plan": _plan(),
        },
        {"S5": 5.0},
    )

    check = score_simulation(context)[0]

    assert check.score == 100.0, check.evidence
    assert check.evidence["identity_relation_policy"] == "preserve-explicit-identity-alternatives"
    assert check.evidence["filtered_candidate_identity_alternatives"] == 0


def test_s5_scores_partial_authoritative_quantity_recall(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S5", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    scope = _scope().assign(NEW=2)
    final = _final()
    final.loc[0, "original_bom_qty"] = 2
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _single_relation(),
            "substitution_source": _single_relation(),
            "scope_input": scope,
            "final_material": final,
            "site_plan": _plan(),
        },
        {"S5": 5.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["authoritative_quantity"] == 2
    assert check.evidence["covered_quantity"] == 1
    assert check.evidence["recall_rate"] == 0.5
    assert check.score == 50.0


def test_s5_still_scores_install_and_dismantle_actions(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S5", ("prompt/x.txt:L1",)),),
        {
            "s1_substitution_mode": "priority-row-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    dismantle_final = _final().assign(
        action="dismantle",
        required_qty=-1,
    )
    dismantle_plan = _plan().assign(site_action="dismantle")
    context = _context(
        tmp_path,
        component,
        {
            "material_substitution": _single_relation(),
            "substitution_source": _single_relation(),
            "scope_input": _scope().assign(DISMANTLE=1),
            "final_material": pd.concat(
                [_final(), dismantle_final],
                ignore_index=True,
            ),
            "site_plan": pd.concat([_plan(), dismantle_plan], ignore_index=True),
        },
        {"S5": 5.0},
    )

    check = score_simulation(context)[0]

    assert check.score == 100.0, check.evidence
    assert check.evidence["action_scope"] == ["dismantle", "install"]
    assert check.evidence["out_of_scope_final_rows"] == 0
    assert check.evidence["authoritative_quantity"] == 2
    assert check.evidence["covered_quantity"] == 2


def test_s5_base_pk_standardizes_scope_before_identity_recall(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S5", ("prompt/x.txt:L1",)),),
        {"s5_scope_material_mode": "base-pk-standardized"},
    )
    scope = pd.DataFrame(
        {
            "*DU ID": ["S1"] * 7,
            "Region": ["R1"] * 7,
            "*物料编码": [
                "RRU5516",
                "RRU5516",
                "RRU5905 900M",
                "UBBPd6",
                "RRU5905 2100M",
                "RRU5905 900M&1800M",
                "RRU5905 900M",
            ],
            "频段": ["850M", "900M", "900M", "", "2100M", "900M&1800M", "900M"],
            "nTnR": ["4T4R", "4T4R", "4T4R", "", "4T4R", "4T4R", "4T4R"],
            "*数量": [2, 3, 4, 5, 10, 11, 0],
        }
    )
    final = pd.DataFrame(
        {
            "site_name": ["S1"] * 4,
            "region": ["R1"] * 4,
            "action": ["install"] * 4,
            "item_code": [
                "rru5516_850_4t4r",
                "rru5516_900_4t4r",
                "rru900_900_4t4r",
                "ubbp",
            ],
            "required_qty": [2, 3, 4, 5],
        }
    )
    context = _context(
        tmp_path,
        component,
        {
            "scope_input": scope,
            "final_material": final,
            "site_plan": _plan(),
        },
        {"S5": 5.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["authoritative_quantity"] == 14
    assert check.evidence["covered_quantity"] == 14
    assert check.evidence["recall_rate"] == 1.0
    assert check.score == 100.0


def test_r3_legacy_denominator_uses_only_authorized_virtual_install_actions(
    tmp_path: Path,
) -> None:
    component = ComponentConfig(
        "reuse-accounting",
        "ei.reuse",
        (CheckConfig("reuse-accounting.R3", ("prompt/x.txt:L1",)),),
        {
            "r3_validation_mode": "LEGACY_RESIDUAL_ONLY",
            "r3_substitution_mode": "input-views",
        },
    )
    plan = pd.concat(
        [_plan(), _plan().assign(site_name="S2")],
        ignore_index=True,
    )
    scope = pd.concat(
        [
            _scope(),
            _scope().assign(**{"SITE ID": "S2", "ITEM CODE": "X"}),
        ],
        ignore_index=True,
    )
    source = _relations().iloc[[0]].reset_index(drop=True)
    context = _context(
        tmp_path,
        component,
        {
            "final_material": _final(),
            "site_plan": plan,
            "substitution_source": source,
            "scope_input": scope,
        },
        {"R3": 10.0},
    )

    result = score_reuse(context)

    assert result[0].score == 100.0, result[0].evidence
    assert result[0].evidence["applicable_units"] == 1


def test_r3_with_no_authorized_virtual_demand_is_not_applicable(tmp_path: Path) -> None:
    component = ComponentConfig(
        "reuse-accounting",
        "ei.reuse",
        (CheckConfig("reuse-accounting.R3", ("prompt/x.txt:L1",)),),
        {
            "r3_validation_mode": "LEGACY_RESIDUAL_ONLY",
            "r3_substitution_mode": "input-views",
        },
    )
    context = _context(
        tmp_path,
        component,
        {
            "final_material": _final(),
            "site_plan": _plan(),
            "substitution_source": _relations().iloc[[0]].reset_index(drop=True),
            "scope_input": _scope().assign(**{"ITEM CODE": "X"}),
        },
        {"R3": 10.0},
    )

    result = score_reuse(context)

    assert result[0].status == "NOT_APPLICABLE"
    assert result[0].score == 0.0


def test_s1_input_provided_model_has_unit_fidelity(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S1", ("prompt/x.txt:L1",)),),
        {
            "s1_candidate_substitution_required": False,
            "s1_substitution_mode": "input-views",
            "s1_traceability_mode": "explicit-origin",
            "s1_region_scope": "exact",
        },
    )
    context = _context(
        tmp_path,
        component,
        {
            "substitution_source": _single_relation(),
            "scope_input": _scope(),
            "final_material": _final(),
        },
        {"S1": 20.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["model_fidelity"] == 1.0
    assert check.evidence["application_precision"] == 1.0
    assert check.evidence["final_rate"] == 1.0
    assert check.score == 100.0


def test_s6_rejects_active_month_that_disagrees_with_plan(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {
            "planning_year": 2027,
            "week_to_month": "calendar",
            "project_start_month": 1,
        },
    )
    final = _final().copy()
    final.loc[0, "install_month"] = 2
    context = _context(
        tmp_path,
        component,
        {
            "final_material": final,
            "site_plan": _plan(),
        },
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 0
    assert check.evidence["time_accuracy"] == 0.0
    assert check.score == 0.0


def test_s6_rejects_active_week_that_disagrees_with_plan(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {
            "planning_year": 2027,
            "week_to_month": "calendar",
            "project_start_month": 1,
        },
    )
    final = _final().copy()
    final.loc[0, "install_wk_label"] = "2027WK3"
    context = _context(
        tmp_path,
        component,
        {
            "final_material": final,
            "site_plan": _plan(),
        },
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 0
    assert check.evidence["time_accuracy"] == 0.0
    assert check.score == 0.0


def test_s6_scores_correct_week_and_month(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {
            "planning_year": 2027,
            "week_to_month": "calendar",
            "project_start_month": 1,
        },
    )
    context = _context(
        tmp_path,
        component,
        {
            "final_material": _final(),
            "site_plan": _plan(),
        },
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 1
    assert check.evidence["time_accuracy"] == 1.0
    assert check.score == 100.0


def test_s6_compares_th_iso_week_labels_not_continuous_project_weeks(
    tmp_path: Path,
) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {
            "planning_year": 2027,
            "s6_time_mode": "action-week-month",
            "s6_week_kind": "iso",
            "project_week_source": "week_num",
        },
    )
    plan = pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["BMA"],
            "site_action": ["install"],
            "mos_weekly_plan": ["2024-W08"],
            "week_num": [34],
        }
    )
    final = pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["BMA"],
            "action": ["install"],
            "install_month": ["2024M2"],
            "install_wk_label": ["2024-W08"],
            "dismantle_month": [""],
            "dismantle_wk_label": [""],
            "item_code": ["A"],
            "required_qty": [1],
        }
    )
    context = _context(
        tmp_path,
        component,
        {"final_material": final, "site_plan": plan},
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["week_kind"] == "iso"
    assert check.evidence["project_week_source"] == "week_num"
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 1
    assert check.score == 100.0

    final.loc[0, "install_wk_label"] = "2025-W08"
    mismatch = _context(
        tmp_path,
        component,
        {"final_material": final, "site_plan": plan},
        {"S6": 3.0},
    )
    mismatch_check = score_simulation(mismatch)[0]
    assert mismatch_check.evidence["time_correct_actions"] == 0
    assert mismatch_check.score == 0.0


def test_s6_scores_pk0002_year_month_label_contract(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {
            "planning_year": 2026,
            "week_to_month": "four-week-project",
            "project_start_month": 2,
            "s6_time_mode": "action-week-month",
        },
    )
    plan = _plan().assign(week_num=17, mos_weekly_plan="2026WK17")
    final = _final().assign(
        install_month="2026M6",
        install_wk_label="2026WK17",
    )
    context = _context(
        tmp_path,
        component,
        {"final_material": final, "site_plan": plan},
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 1
    assert check.evidence["time_accuracy"] == 1.0
    assert check.score == 100.0


def test_s6_scores_base_project_week_contract(tmp_path: Path) -> None:
    component = ComponentConfig(
        "simulation",
        "ei.simulation",
        (CheckConfig("simulation.S6", ("prompt/x.txt:L1",)),),
        {"planning_year": 2026, "s6_time_mode": "project-week"},
    )
    plan = pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["R1"],
            "site_action": ["install"],
            "project_week": [2],
            "status": ["scheduled"],
        }
    )
    final = pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["R1"],
            "site_action": ["install"],
            "item_code": ["A"],
            "required_qty": [1],
            "project_week": [2],
        }
    )
    context = _context(
        tmp_path,
        component,
        {"final_material": final, "site_plan": plan},
        {"S6": 3.0},
    )

    result = score_simulation(context)

    check = result[0]
    assert check.evidence["comparable_actions"] == 1
    assert check.evidence["time_correct_actions"] == 1
    assert check.evidence["time_accuracy"] == 1.0
    assert check.score == 100.0
