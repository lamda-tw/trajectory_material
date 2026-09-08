from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from simulation.ei.core.adapters import parse_project_week
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.scheduling import (
    _candidate_plan,
    score_scheduling,
)
from simulation.ei.rules.ei_standard.common import (
    _month_from_row,
    _months_from_frame,
)


def _resolution(role: str, frame: pd.DataFrame) -> ArtifactResolution:
    return ArtifactResolution(
        role=role,
        status="SELECTED_CANONICAL",
        selected_path=Path(f"{role}.csv"),
        table=frame,
        normalized=frame,
    )


def _context(
    tmp_path: Path,
    check_id: str,
    plan: pd.DataFrame,
    scope: pd.DataFrame,
    batches: pd.DataFrame,
    parameters: dict[str, object],
) -> RuleContext:
    component = ComponentConfig(
        name="scheduling",
        scorer="ei.scheduling",
        checks=(CheckConfig(f"scheduling.{check_id}", ("prompt/x.txt:L1",)),),
        parameters=parameters,
    )
    specs = {
        role: ArtifactSpec(role, source, f"{role}.csv", (f"{role}.csv",))
        for role, source in (
            ("site_plan", "candidate"),
            ("scope_input", "question"),
            ("batch_input", "question"),
        )
    }
    profile = QuestionProfile(
        "Q",
        "4.13.0",
        ("output",),
        specs,
        {"scheduling": component},
        tmp_path / "validator.yaml",
    )
    bundle = ArtifactBundle(
        tmp_path,
        (),
        {
            "site_plan": _resolution("site_plan", plan),
            "scope_input": _resolution("scope_input", scope),
            "batch_input": _resolution("batch_input", batches),
        },
    )
    return RuleContext(
        profile,
        component,
        bundle,
    )


def test_week_normalization_accepts_prompt_forms_and_rejects_conflicts() -> None:
    normalized = _candidate_plan(
        pd.DataFrame(
            {
                "site_name": ["A", "B", "C"],
                "site_action": ["install"] * 3,
                "week_num": [5.0, "WK6", "WK7"],
                "mos_weekly_plan": ["2027WK5", "2027WK6", "2027WK8"],
            }
        )
    )

    assert normalized["project_week"].tolist()[:2] == [5.0, 6.0]
    assert normalized.loc[2, "week_issue"] == "WEEK_CONFLICT"


def test_week_normalization_uses_week_num_for_separate_year_week_coordinate() -> None:
    normalized = _candidate_plan(
        pd.DataFrame(
            {
                "site_name": ["A", "B"],
                "site_action": ["install", "install"],
                "week_num": [2, 3],
                "mos_weekly_plan": ["2023W28", "2023W29"],
            }
        ),
        project_week_source="week_num",
    )

    assert normalized["project_week"].tolist() == [2, 3]
    assert normalized["week_issue"].tolist() == ["", ""]
    assert normalized["week_source"].tolist() == ["week", "week"]


def test_unscheduled_with_blank_time_is_a_valid_diagnostic_action() -> None:
    normalized = _candidate_plan(
        pd.DataFrame(
            {
                "site_name": ["A", "B", "C"],
                "site_action": ["install"] * 3,
                "status": ["unscheduled", "unscheduled", "cancelled"],
                "week_num": ["", 5, ""],
                "mos_weekly_plan": ["", "", ""],
            }
        )
    )

    assert pd.isna(normalized.loc[0, "project_week"])
    assert normalized.loc[0, "week_issue"] == ""
    assert normalized.loc[0, "week_source"] == "unscheduled"
    assert normalized.loc[1, "week_issue"] == "UNSCHEDULED_TIME_NOT_BLANK"
    assert normalized.loc[2, "week_issue"] == "INVALID_STATUS"


def test_week_normalization_parses_each_distinct_typed_value_once() -> None:
    raw = pd.DataFrame(
        {
            "site_name": [f"S{index}" for index in range(100)],
            "site_action": ["install"] * 100,
            "week_num": [5] * 50 + [6] * 50,
            "mos_weekly_plan": ["2027WK5"] * 50 + ["2027WK6"] * 50,
        }
    )

    with patch(
        "simulation.ei.rules.ei_standard.scheduling.parsing.parse_project_week",
        wraps=parse_project_week,
    ) as parser:
        normalized = _candidate_plan(raw)

    assert normalized["project_week"].tolist() == [5] * 50 + [6] * 50
    assert parser.call_count == 4


def test_month_vectorization_matches_row_contract_and_parses_unique_signatures() -> None:
    frame = pd.DataFrame(
        {
            "week": [5, 5, 9, 9],
            "week_label": ["2027WK5", "2027WK5", "2027WK9", "2027WK9"],
        }
    )
    expected = [
        _month_from_row(row, 2027)
        for _, row in frame.iterrows()
    ]

    with patch(
        "simulation.ei.rules.ei_standard.common.pd.to_datetime",
        wraps=pd.to_datetime,
    ) as parser:
        actual = _months_from_frame(frame, 2027).tolist()

    assert actual == expected
    assert parser.call_count == 2


def test_site_scope_uses_material_and_delivery_batch_intersection(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["IN"],
            "site_action": ["install"],
            "week_num": [1],
            "region": ["R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["IN", "OUT"],
            "action": ["install", "install"],
            "region": ["R1", "R1"],
            "required_qty": [1, 1],
        }
    )
    batches = pd.DataFrame(
        {"site_name": ["IN"], "region": ["R1"], "cluster": [1]}
    )
    context = _context(
        tmp_path,
        "C1",
        plan,
        scope,
        batches,
        {"site_scope": "batch_intersection", "batch_kind": "cluster"},
    )

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["expected"] == 1
    assert result[0].evidence["excluded_outside_batch_scope"] == 1


def test_region_conflict_between_question_inputs_is_not_a_candidate_penalty(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["S1"],
            "site_action": ["install"],
            "week_num": [1],
            "region": ["R3"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["S1"],
            "action": ["install"],
            "region": ["R3"],
            "required_qty": [1],
        }
    )
    batches = pd.DataFrame(
        {"site_name": ["S1"], "region": ["R4"], "cluster": [1]}
    )
    context = _context(
        tmp_path,
        "C1",
        plan,
        scope,
        batches,
        {"site_scope": "batch_intersection", "batch_kind": "cluster"},
    )

    result = score_scheduling(context)[0]

    assert result.status == "UNSCORABLE"
    assert result.reason_code == "EVALUATOR_ERROR"
    assert "QUESTION_DATA_CONFLICT" in result.evidence["error"]


def test_c6a_cluster_uses_latest_install_to_earliest_dismantle(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "I2", "D1"],
            "site_action": ["install", "install", "dismantle"],
            "week_num": ["WK2", "WK3", "WK5"],
            "mos_weekly_plan": ["2027WK2", "2027WK3", "2027WK5"],
            "region": ["R1"] * 3,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "I2", "D1"],
            "action": ["install", "install", "dismantle"],
            "region": ["R1"] * 3,
            "required_qty": [1, 1, -1],
        }
    )
    clusters = pd.DataFrame(
        {"site_name": ["I1", "I2", "D1"], "region": ["R1"] * 3, "cluster": [1, 1, 1]}
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6a_contract": {"relation": "exact", "lag_weeks": 2},
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["comparable_batches"] == 1
    assert result[0].evidence["batch_kind"] == "cluster"


def test_c6a_site_scope_anchors_each_dismantle_to_same_site_install(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["S1", "S1", "S2", "S2"],
            "site_action": ["install", "dismantle", "install", "dismantle"],
            "week_num": [1, 1, 10, 10],
            "region": ["R1"] * 4,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["S1", "S1", "S2", "S2"],
            "action": ["install", "dismantle", "install", "dismantle"],
            "region": ["R1"] * 4,
            "required_qty": [1, -1, 1, -1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["S1", "S2"],
            "region": ["R1", "R1"],
            "cluster": [1, 1],
        }
    )
    site_parameters = {
        "batch_kind": "cluster",
        "c6a_contract": {
            "scope": "site",
            "direction": "install_then_dismantle",
            "relation": "minimum",
            "lag_weeks": 0,
        },
    }
    batch_parameters = {
        "batch_kind": "cluster",
        "c6a_contract": {
            "scope": "batch",
            "direction": "install_then_dismantle",
            "relation": "minimum",
            "lag_weeks": 0,
        },
    }

    site_result = score_scheduling(
        _context(tmp_path, "C6a", plan, scope, clusters, site_parameters)
    )[0]
    batch_result = score_scheduling(
        _context(tmp_path, "C6a", plan, scope, clusters, batch_parameters)
    )[0]

    assert site_result.score == 100.0
    assert site_result.evidence["scope"] == "site"
    assert site_result.evidence["comparable_sites"] == 2
    assert batch_result.score == 0.0
    assert batch_result.evidence["scope"] == "batch"
    assert batch_result.evidence["failures"][0]["actual_offset"] == -9


def test_c6a_mocn_uses_the_prompt_mocn_batch_as_scoring_unit(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "I2", "D1"],
            "site_action": ["install", "install", "dismantle"],
            "week_num": [2, 4, 6],
            "region": ["R1"] * 3,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "I2", "D1"],
            "action": ["install", "install", "dismantle"],
            "region": ["R1"] * 3,
            "required_qty": [1, 1, -1],
        }
    )
    batches = pd.DataFrame(
        {
            "site_name": ["I1", "I2", "D1"],
            "region": ["R1"] * 3,
            "mocn_batch": [7, 7, 7],
        }
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        batches,
        {
            "batch_kind": "mocn",
            "c6a_contract": {"relation": "exact", "lag_weeks": 2},
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["batch_kind"] == "mocn"


def test_c6a_relation_is_prompt_configured(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "site_action": ["install", "dismantle"],
            "week_num": [2, 5],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "action": ["install", "dismantle"],
            "region": ["R1", "R1"],
            "required_qty": [1, -1],
        }
    )
    clusters = pd.DataFrame(
        {"site_name": ["I1", "D1"], "region": ["R1", "R1"], "cluster": [1, 1]}
    )
    minimum = score_scheduling(
        _context(
            tmp_path,
            "C6a",
            plan,
            scope,
            clusters,
            {
                "batch_kind": "cluster",
                "c6a_contract": {"relation": "minimum", "lag_weeks": 2},
            },
        )
    )
    exact = score_scheduling(
        _context(
            tmp_path,
            "C6a",
            plan,
            scope,
            clusters,
            {
                "batch_kind": "cluster",
                "c6a_contract": {"relation": "exact", "lag_weeks": 2},
            },
        )
    )

    assert minimum[0].score == 100.0
    assert minimum[0].evidence["relation"] == "minimum"
    assert exact[0].score == 0.0
    assert exact[0].evidence["failures"][0]["actual_offset"] == 3


def test_c6a_ignores_duplicate_action_rows_owned_by_c2(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "I1", "D1"],
            "site_action": ["install", "install", "dismantle"],
            "week_num": ["WK2", "WK2", "WK4"],
            "mos_weekly_plan": ["2027WK2", "2027WK2", "2027WK4"],
            "region": ["R1"] * 3,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "action": ["install", "dismantle"],
            "region": ["R1", "R1"],
            "required_qty": [1, -1],
        }
    )
    clusters = pd.DataFrame(
        {"site_name": ["I1", "D1"], "region": ["R1", "R1"], "cluster": [1, 1]}
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6a_contract": {"relation": "exact", "lag_weeks": 2},
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["comparable_batches"] == 1
    assert result[0].evidence["invalid"] == 0
    assert result[0].evidence["failures"] == []


def test_c6a_ignores_missing_expected_actions_owned_by_c1_c2(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "site_action": ["install", "dismantle"],
            "week_num": [2, 4],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "D1", "I2", "D2"],
            "action": ["install", "dismantle", "install", "dismantle"],
            "region": ["R1"] * 4,
            "required_qty": [1, -1, 1, -1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["I1", "D1", "I2", "D2"],
            "region": ["R1"] * 4,
            "cluster": [1, 1, 1, 1],
        }
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6a_contract": {"relation": "minimum", "lag_weeks": 2},
        },
    )
    context.artifacts.artifacts.pop("scope_input")

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["candidate_batches"] == 1
    assert result[0].evidence["comparable_batches"] == 1


def test_c6a_without_candidate_action_pair_is_not_applicable(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1"],
            "site_action": ["install"],
            "week_num": [2],
            "region": ["R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "action": ["install", "dismantle"],
            "region": ["R1", "R1"],
            "required_qty": [1, -1],
        }
    )
    clusters = pd.DataFrame(
        {"site_name": ["I1", "D1"], "region": ["R1", "R1"], "cluster": [1, 1]}
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6a_contract": {"relation": "minimum", "lag_weeks": 2},
        },
    )

    result = score_scheduling(context)

    assert result[0].status == "NOT_APPLICABLE"
    assert result[0].score == 0.0
    assert result[0].evidence["candidate_batches"] == 1
    assert result[0].evidence["comparable_batches"] == 0
    assert result[0].evidence["not_comparable_batches"] == 1


def test_c6a_rejects_invalid_time_in_a_comparable_batch(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "site_action": ["install", "dismantle"],
            "week_num": [2, "bad-week"],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["I1", "D1"],
            "action": ["install", "dismantle"],
            "region": ["R1", "R1"],
            "required_qty": [1, -1],
        }
    )
    clusters = pd.DataFrame(
        {"site_name": ["I1", "D1"], "region": ["R1", "R1"], "cluster": [1, 1]}
    )
    context = _context(
        tmp_path,
        "C6a",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6a_contract": {"relation": "minimum", "lag_weeks": 2},
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 0.0
    assert result[0].evidence["invalid_week_batches"] == 1
    assert result[0].evidence["failures"][0]["reason"] == "INVALID_WEEK"


def test_c6b_uses_cluster_id_and_first_install_week(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1"],
            "site_action": ["install"] * 3,
            "week_num": [2, 10, 3],
            "mos_weekly_plan": ["2027WK2", "2027WK10", "2027WK3"],
            "region": ["R1"] * 3,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1"],
            "action": ["install"] * 3,
            "region": ["R1"] * 3,
            "required_qty": [1, 1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1"],
            "region": ["R1"] * 3,
            "cluster": [1, 1, 2],
            "cluster priority": [99, 99, 1],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            }
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 100.0
    assert result[0].evidence["passed_pairs"] == 1
    assert result[0].evidence["pairs"][0]["predecessor_week"] == 2


def test_c6b_ignores_incomplete_sites_within_candidate_batches(tmp_path: Path) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "site_action": ["install", "install"],
            "week_num": [2, 3],
            "mos_weekly_plan": ["2027WK2", "2027WK3"],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1", "B2"],
            "action": ["install"] * 4,
            "region": ["R1"] * 4,
            "required_qty": [1] * 4,
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1", "B2"],
            "region": ["R1"] * 4,
            "cluster": [1, 1, 2, 2],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )
    context.artifacts.artifacts.pop("scope_input")

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 100.0
    assert evidence["candidate_batch_count"] == 2
    assert evidence["authoritative_pair_count"] == 1
    assert evidence["candidate_pair_count"] == 1
    assert evidence["pair_count"] == 1
    assert evidence["order_accuracy"] == 1.0
    assert evidence["pair_coverage"] == 1.0
    assert evidence["passed_pairs"] == 1
    assert "comparable_pairs" not in evidence
    assert "predecessor_errors" not in evidence["pairs"][0]


def test_c6b_compares_adjacent_candidate_batches_in_authoritative_order(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "C1"],
            "site_action": ["install", "install"],
            "week_num": [5, 7],
            "mos_weekly_plan": ["2027WK5", "2027WK7"],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1", "C1"],
            "action": ["install"] * 3,
            "region": ["R1"] * 3,
            "required_qty": [1] * 3,
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1", "C1"],
            "region": ["R1"] * 3,
            "cluster": [1, 2, 3],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    pair = result[0].evidence["pairs"][0]

    assert result[0].score == 50.0
    assert result[0].evidence["authoritative_batch_count"] == 3
    assert result[0].evidence["candidate_batch_count"] == 2
    assert result[0].evidence["authoritative_pair_count"] == 2
    assert result[0].evidence["candidate_pair_count"] == 1
    assert result[0].evidence["order_accuracy"] == 1.0
    assert result[0].evidence["pair_coverage"] == 0.5
    assert pair["predecessor"] == "1"
    assert pair["successor"] == "3"
    assert pair["status"] == "PASS"


def test_c6b_allows_same_week_and_rejects_true_order_violation(
    tmp_path: Path,
) -> None:
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "action": ["install", "install"],
            "region": ["R1", "R1"],
            "required_qty": [1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "region": ["R1", "R1"],
            "cluster": [1, 2],
        }
    )
    parameters = {
        "batch_kind": "cluster",
        "c6b_contract": {
            "order_mode": "numeric_ascending",
            "scope": "global",
            "event": "first_install_week",
        },
    }
    same_week_plan = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "site_action": ["install", "install"],
            "week_num": [3, 3],
            "mos_weekly_plan": ["2027WK3", "2027WK3"],
            "region": ["R1", "R1"],
        }
    )
    reverse_plan = same_week_plan.copy()
    reverse_plan["week_num"] = [4, 3]
    reverse_plan["mos_weekly_plan"] = ["2027WK4", "2027WK3"]

    same_week = score_scheduling(
        _context(tmp_path, "C6b", same_week_plan, scope, clusters, parameters)
    )
    reverse = score_scheduling(
        _context(tmp_path, "C6b", reverse_plan, scope, clusters, parameters)
    )

    assert same_week[0].score == 100.0
    assert same_week[0].evidence["pairs"][0]["status"] == "PASS"
    assert reverse[0].score == 0.0
    assert reverse[0].evidence["order_violation_pairs"] == 1
    assert reverse[0].evidence["pairs"][0]["status"] == "ORDER_VIOLATION"


def test_c6b_requires_two_candidate_batches_for_order_evidence(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1"],
            "site_action": ["install"],
            "week_num": [2],
            "mos_weekly_plan": ["2027WK2"],
            "region": ["R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "action": ["install", "install"],
            "region": ["R1", "R1"],
            "required_qty": [1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "region": ["R1", "R1"],
            "cluster": [1, 2],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)

    assert result[0].score == 0.0
    assert result[0].reason_code == "INSUFFICIENT_ORDER_EVIDENCE"
    assert result[0].evidence["candidate_batch_count"] == 1
    assert result[0].evidence["authoritative_pair_count"] == 1
    assert result[0].evidence["candidate_pair_count"] == 0
    assert result[0].evidence["pair_count"] == 0
    assert result[0].evidence["order_accuracy"] == 0.0
    assert result[0].evidence["pair_coverage"] == 0.0


def test_c6b_uses_authoritative_pair_denominator_without_requiring_complete_batches(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "C1", "D1"],
            "site_action": ["install"] * 3,
            "week_num": [2, 4, 5],
            "mos_weekly_plan": ["2027WK2", "2027WK4", "2027WK5"],
            "region": ["R1"] * 3,
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1", "C1", "D1"],
            "action": ["install"] * 5,
            "region": ["R1"] * 5,
            "required_qty": [1] * 5,
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "A2", "B1", "C1", "D1"],
            "region": ["R1"] * 5,
            "cluster": [1, 1, 2, 3, 4],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 66.666667
    assert evidence["authoritative_batch_count"] == 4
    assert evidence["candidate_batch_count"] == 3
    assert evidence["authoritative_pair_count"] == 3
    assert evidence["candidate_pair_count"] == 2
    assert evidence["passed_pairs"] == 2
    assert evidence["order_accuracy"] == 1.0
    assert evidence["pair_coverage"] == 2 / 3


def test_c6b_sums_authoritative_and_candidate_pairs_within_each_region(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "C1", "D1", "E1"],
            "site_action": ["install"] * 4,
            "week_num": [2, 4, 3, 5],
            "region": ["R1", "R1", "R2", "R2"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1", "C1", "D1", "E1"],
            "action": ["install"] * 5,
            "region": ["R1", "R1", "R1", "R2", "R2"],
            "required_qty": [1] * 5,
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1", "C1", "D1", "E1"],
            "region": ["R1", "R1", "R1", "R2", "R2"],
            "cluster": [1, 2, 3, 1, 2],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "region",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 66.666667
    assert evidence["authoritative_batch_count"] == 5
    assert evidence["candidate_batch_count"] == 4
    assert evidence["authoritative_pair_count"] == 3
    assert evidence["candidate_pair_count"] == 2
    assert evidence["passed_pairs"] == 2
    assert {pair["scope"] for pair in evidence["pairs"]} == {"r1", "r2"}


def test_c6b_reports_week_conflict_when_no_install_week_is_usable(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "site_action": ["install", "install"],
            "week_num": [2, 3],
            "mos_weekly_plan": ["2027WK5", "2027WK6"],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "action": ["install", "install"],
            "region": ["R1", "R1"],
            "required_qty": [1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "region": ["R1", "R1"],
            "cluster": [1, 2],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 0.0
    assert result[0].reason_code == "WEEK_CONFLICT"
    assert evidence["candidate_install_row_count"] == 2
    assert evidence["valid_install_week_row_count"] == 0
    assert evidence["week_issue_counts"] == {"WEEK_CONFLICT": 2}


def test_c6b_uses_prompt_project_week_when_label_is_calendar_week(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "site_action": ["install", "install"],
            "week_num": [2, 3],
            "mos_weekly_plan": ["2023W28", "2023W29"],
            "region": ["BMA", "BMA"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "action": ["install", "install"],
            "region": ["BMA", "BMA"],
            "required_qty": [1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "region": ["BMA", "BMA"],
            "cluster": ["BMA0001", "BMA0002"],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "project_week_source": "week_num",
            "c6b_contract": {
                "order_mode": "source_sequence",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 100.0
    assert evidence["valid_install_week_row_count"] == 2
    assert evidence["week_issue_counts"] == {}
    assert evidence["pairs"][0]["predecessor_week"] == 2
    assert evidence["pairs"][0]["successor_week"] == 3


def test_c6b_reports_unmapped_batch_when_candidate_sites_are_not_authoritative(
    tmp_path: Path,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["X1", "Y1"],
            "site_action": ["install", "install"],
            "week_num": [2, 3],
            "region": ["R1", "R1"],
        }
    )
    scope = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "action": ["install", "install"],
            "region": ["R1", "R1"],
            "required_qty": [1, 1],
        }
    )
    clusters = pd.DataFrame(
        {
            "site_name": ["A1", "B1"],
            "region": ["R1", "R1"],
            "cluster": [1, 2],
        }
    )
    context = _context(
        tmp_path,
        "C6b",
        plan,
        scope,
        clusters,
        {
            "batch_kind": "cluster",
            "c6b_contract": {
                "order_mode": "numeric_ascending",
                "scope": "global",
                "event": "first_install_week",
            },
        },
    )

    result = score_scheduling(context)
    evidence = result[0].evidence

    assert result[0].score == 0.0
    assert result[0].reason_code == "UNMAPPED_BATCH"
    assert evidence["valid_install_week_row_count"] == 2
    assert evidence["unmapped_install_row_count"] == 2
