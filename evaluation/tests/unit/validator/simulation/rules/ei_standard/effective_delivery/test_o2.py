from __future__ import annotations

import pytest
import pandas as pd

from simulation.ei.core.models import CheckResult
from simulation.ei.rules.ei_standard.effective_delivery import (
    score_effective_delivery,
)

from .support import (
    batch_frame,
    final_frame,
    fixed_final_frame,
    fixed_o2_context,
    fixed_plan_frame,
    master_frame,
    o2_context,
    plan_frame,
    scope_frame,
)


def test_fixed_authority_uses_question_plan_as_b_and_only_bom_filters_a() -> None:
    context = fixed_o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "I1", 1),
                ("R1", "S1", "dismantle", "D1", 1),
                ("R1", "S2", "install", "I2", 1),
            )
        ),
        plan=fixed_plan_frame(
            (
                ("R1", "S1", "install", 5),
                ("R1", "S1", "dismantle", 7),
                ("R1", "S2", "install", 10),
            )
        ),
        final=fixed_final_frame(
            (
                ("R1", "S1", "install", "I1", 1, "I1", 5),
                ("R1", "S1", "dismantle", "D1", 1, "D1", 7),
            )
        ),
    )

    check = _score(context)

    assert check.score == 50.0
    assert check.evidence["plan_mode"] == "fixed-authority"
    assert check.evidence["N_target_sites"] == 2
    assert check.evidence["candidate_selected_authority_sites"] == 2
    assert check.evidence["valid_delivery_sites"] == 1
    grid = {
        (row["group"], row["month"]): (
            row["valid_deliveries_A"],
            row["target_B"],
        )
        for row in check.evidence["scaled_target_grid"]
    }
    assert grid == {("r1", 2): (1, 1), ("r1", 3): (0, 1)}


def test_fixed_authority_does_not_add_a_site_f_for_orphan_final_bom() -> None:
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 5),)),
        final=fixed_final_frame(
            (
                ("R1", "S1", "install", "I1", 1, "I1", 5),
                ("R1", "FAKE", "install", "X", 1, "X", 5),
            )
        ),
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.evidence["total_absolute_deviation"] == 0
    assert "out_of_scope_site_count" not in check.evidence
    assert check.evidence["non_scoring_orphan_final_material_site_count"] == 1
    assert check.evidence[
        "non_scoring_orphan_final_material_score_effect"
    ] == "none"


def test_fixed_authority_does_not_use_candidate_display_month_to_reassign_a() -> None:
    final = fixed_final_frame(
        (("R1", "S1", "install", "I1", 1, "I1", 5),)
    )
    final.loc[:, "install_month"] = 3
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 5),)),
        final=final,
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["valid_delivery_sites"] == 1


def test_fixed_authority_accepts_short_final_week_against_absolute_plan_week() -> None:
    final = fixed_final_frame(
        (("R1", "S1", "install", "I1", 1, "I1", 13),)
    )
    final.loc[:, "install_wk_label"] = "WK13"
    # ISO week 13 of 2027 starts in March.  Keep this test focused on the week
    # representation; month semantics are checked independently below.
    final.loc[:, "install_month"] = 3
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 13),)),
        final=final,
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["valid_delivery_sites"] == 1


def test_fixed_authority_rejects_explicit_wrong_year_in_final_week() -> None:
    final = fixed_final_frame(
        (("R1", "S1", "install", "I1", 1, "I1", 13),)
    )
    final.loc[:, "install_wk_label"] = "2028WK13"
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 13),)),
        final=final,
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.evidence["valid_delivery_sites"] == 0
    assert "FINAL_BOM_WEEK_MISMATCH" in _invalid_sites(check)["S1"][
        "reasons"
    ]


@pytest.mark.parametrize(
    "month_label",
    ["2027M03", "2027-03", "3月", "not-a-month"],
)
def test_fixed_authority_ignores_candidate_display_month_format(
    month_label: str,
) -> None:
    final = fixed_final_frame(
        (("R1", "S1", "install", "I1", 1, "I1", 13),)
    )
    final["install_month"] = month_label
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 13),)),
        final=final,
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["scaled_target_grid"] == [
        {
            "group": "r1",
            "month": 3,
            "year_month": "2027-03",
            "valid_deliveries_A": 1,
            "target_B": 1,
            "absolute_deviation": 0,
        }
    ]


def test_fixed_authority_reports_plan_external_dismantle_only_as_orphan() -> None:
    context = fixed_o2_context(
        scope=scope_frame((("R1", "S1", "install", "I1", 1),)),
        plan=fixed_plan_frame((("R1", "S1", "install", 5),)),
        final=fixed_final_frame(
            (
                ("R1", "S1", "install", "I1", 1, "I1", 5),
                ("R1", "FAKE", "dismantle", "X", 1, "X", 7),
            )
        ),
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["non_scoring_orphan_final_material_site_count"] == 1


def test_fixed_authority_does_not_add_f_for_install_on_pure_dismantle_site() -> None:
    context = fixed_o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "I1", 1),
                ("R1", "D1", "dismantle", "D", 1),
            )
        ),
        plan=fixed_plan_frame(
            (
                ("R1", "S1", "install", 5),
                ("R1", "D1", "dismantle", 7),
            )
        ),
        final=fixed_final_frame(
            (
                ("R1", "S1", "install", "I1", 1, "I1", 5),
                ("R1", "D1", "dismantle", "D", 1, "D", 7),
                ("R1", "D1", "install", "X", 1, "X", 5),
            )
        ),
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.evidence["total_absolute_deviation"] == 0


def _score(context) -> CheckResult:
    checks = score_effective_delivery(context)
    assert len(checks) == 1
    check = checks[0]
    assert check.check_id == "effective-delivery.O2"
    return check


def _historical_site_action_master() -> pd.DataFrame:
    return pd.DataFrame(
        (
            {
                "site_name": "S1",
                "site_action": "install",
                "mos_weekly_plan": "2027WK5",
                "week_num": 5,
                "region": "R1",
                "site_count": 1,
            },
            {
                "site_name": "D1",
                "site_action": "dismantle",
                "mos_weekly_plan": "2027WK10",
                "week_num": 10,
                "region": "R1",
                "site_count": 1,
            },
        )
    )


def _prepared_master(*, dismantle_count: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        (
            {
                "region": "R1",
                "action": "install",
                "month": "2027M2",
                "master_count": 1,
            },
            {
                "region": "R1",
                "action": "dismantle",
                "month": "2027M3",
                "master_count": dismantle_count,
            },
        )
    )


def _prepared_master_o2_context(*, dismantle_count: int = 1):
    return o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=_historical_site_action_master(),
        plan=plan_frame((("R1", "S1", "install", 5),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 5),)),
        prepared_master=_prepared_master(dismantle_count=dismantle_count),
        parameters={
            "o2_master_format": "site-action-weekly-install",
            "o2_prepared_master_plan_role": "prepared_master_plan",
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
        },
    )


def test_o2_prepared_master_gate_accepts_exact_full_action_month_summary() -> None:
    check = _score(_prepared_master_o2_context())

    assert check.score == 100.0
    assert check.evidence["prepared_master_hard_gate_triggered"] is False
    comparison = check.evidence["prepared_master_comparison"]
    assert comparison["passed"] is True
    assert comparison["expected_actions"] == ["dismantle", "install"]
    assert comparison["expected_periods"] == [202702, 202703]


def test_o2_prepared_master_gate_rejects_wrong_dismantle_total() -> None:
    check = _score(_prepared_master_o2_context(dismantle_count=0))

    assert check.score == 0.0
    assert check.reason_code == "PREPARED_MASTER_PLAN_MISMATCH"
    assert check.evidence["prepared_master_hard_gate_triggered"] is True
    assert check.evidence["zero_cause"] == "prepared_master_plan_mismatch"
    comparison = check.evidence["prepared_master_comparison"]
    assert comparison["passed"] is False
    assert comparison["differences"] == [
        {
            "region": "r1",
            "action": "dismantle",
            "period": 202703,
            "expected": 1,
            "actual": 0,
        }
    ]


def test_o2_does_not_blame_an_unexpected_scorer_error_on_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _install_fixture(
        (("R1", "S1", "C1", 1),),
        {"R1": {1: 1}},
    )

    def broken_candidate_parser(*_args, **_kwargs):
        raise KeyError("internal regression")

    monkeypatch.setattr(
        "simulation.ei.rules.ei_standard.effective_delivery.o2."
        "candidate_plan",
        broken_candidate_parser,
    )

    check = _score(context)

    assert check.status == "UNSCORABLE"
    assert check.reason_code == "EVALUATOR_ERROR"
    assert "KeyError" in check.evidence["error"]


def test_o2_does_not_score_a_partially_normalized_authority_as_candidate_zero(
) -> None:
    context = _install_fixture(
        (("R1", "S1", "C1", 1),),
        {"R1": {1: 1}},
    )
    master = context.artifacts.get("master_plan")
    assert master is not None
    master.validation_issues = (
        {
            "code": "INVALID_CANONICAL_VALUE",
            "column": "planned_count",
            "row": 2,
        },
    )

    check = _score(context)

    assert check.status == "UNSCORABLE"
    assert check.reason_code == "EVALUATOR_ERROR"
    assert "authoritative master_plan" in check.evidence["error"]


def _install_fixture(
    sites: tuple[tuple[str, str, str, int], ...],
    curves: dict[str, dict[int, float]],
):
    """Return a standalone install-only context.

    ``sites`` contains ``(region, site, cluster, candidate_week)`` values.
    """

    return o2_context(
        scope=scope_frame(
            (region, site, "install", "A", 1)
            for region, site, _, _ in sites
        ),
        batches=batch_frame(
            (region, site, cluster)
            for region, site, cluster, _ in sites
        ),
        master=master_frame(curves),
        plan=plan_frame(
            (region, site, "install", week)
            for region, site, _, week in sites
        ).assign(cluster=[cluster for _, _, cluster, _ in sites]),
        final=final_frame(
            (region, site, "install", "A", 1, "A", week)
            for region, site, _, week in sites
        ),
    )


def _target_grid(check: CheckResult) -> dict[tuple[str, int], int]:
    return {
        (str(row["group"]), int(row["month"])): int(row["target_B"])
        for row in check.evidence["scaled_target_grid"]
    }


def _single_install_context(
    *,
    plan: pd.DataFrame | None = None,
    final: pd.DataFrame | None = None,
    parameters: dict[str, object] | None = None,
):
    """Build one valid delivery, with selected candidate frames replaceable."""

    return o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=(
            plan
            if plan is not None
            else plan_frame((("R1", "S1", "install", 1),))
        ),
        final=(
            final
            if final is not None
            else final_frame((("R1", "S1", "install", "A", 1, "A", 1),))
        ),
        parameters=parameters,
    )


def _invalid_sites(check: CheckResult) -> dict[str, dict[str, object]]:
    return {
        str(row["site"]): row
        for row in check.evidence["invalid_site_examples"]
    }


def _mocn_two_site_context(
    plan: pd.DataFrame,
):
    """Build two base-PK sites sharing authoritative MOCN batch 1."""

    return o2_context(
        scope=scope_frame(
            tuple(
                ("R1", site, action, "A", 1)
                for site in ("S1", "S2")
                for action in ("install", "dismantle")
            )
        ),
        batches=batch_frame(
            (("R1", "S1", 1), ("R1", "S2", 1)),
            batch_kind="mocn",
        ),
        master=master_frame({"R1": {1: 2}}),
        plan=plan,
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "A", 1, "A", 3),
                ("R1", "S2", "install", "A", 1, "A", 10),
                ("R1", "S2", "dismantle", "A", 1, "A", 12),
            )
        ),
        parameters={"o2_batch_kind": "mocn"},
    )


def test_o2_scales_each_region_with_largest_remainder_and_ignores_plan_total() -> None:
    sites = (
        ("R1", "R1-S1", "C1", 1),
        ("R1", "R1-S2", "C1", 1),
        ("R1", "R1-S3", "C1", 1),
        ("R1", "R1-S4", "C1", 5),
        ("R2", "R2-S1", "C2", 1),
        ("R2", "R2-S2", "C2", 5),
    )
    shape = {"R1": {1: 2, 2: 1}, "R2": {1: 1, 2: 1, 3: 1}}
    scaled_shape = {
        region: {month: value * 1000 for month, value in curve.items()}
        for region, curve in shape.items()
    }

    original = _score(_install_fixture(sites, shape))
    rescaled = _score(_install_fixture(sites, scaled_shape))

    expected = {
        ("r1", 1): 3,
        ("r1", 2): 1,
        ("r2", 1): 1,
        ("r2", 2): 1,
        ("r2", 3): 0,
    }
    assert original.score == 100.0
    assert rescaled.score == 100.0
    assert original.evidence["N_target_sites"] == 6
    assert original.evidence["group_targets"] == {"r1": 4, "r2": 2}
    assert _target_grid(original) == expected
    assert _target_grid(rescaled) == expected
    assert original.evidence["largest_remainder_tie_break"] == "month_ascending"


def test_o2_formula_has_zero_and_hundred_boundaries() -> None:
    sites = (("R1", "S1", "C1", 1), ("R1", "S2", "C1", 1))
    perfect_context = _install_fixture(sites, {"R1": {1: 999}})
    perfect = _score(perfect_context)

    empty_context = o2_context(
        scope=perfect_context.artifacts.get("scope_input").table,
        batches=perfect_context.artifacts.get("batch_input").table,
        master=perfect_context.artifacts.get("master_plan").table,
        plan=plan_frame(()),
        final=final_frame(()),
    )
    empty = _score(empty_context)

    assert perfect.score == 100.0
    assert perfect.status == "PASS"
    assert perfect.evidence["formula"] == (
        "max(0, 1 - (count_gap_units + redistribution_units + "
        "drop_identity_deviation) / N)"
    )
    assert perfect.evidence["curve_absolute_deviation"] == 0
    assert perfect.evidence["A_total"] == perfect.evidence["B_total"] == 2
    assert perfect.evidence["shortfall_units"] == 0
    assert perfect.evidence["overage_units"] == 0
    assert perfect.evidence["overlap_units"] == 2
    assert perfect.evidence["redistribution_units"] == 0
    assert perfect.evidence["curve_loss_units"] == 0
    assert perfect.evidence["total_loss_units"] == 0
    assert perfect.evidence["zero_cause"] == "not_zero"
    assert perfect.evidence["rate"] == 1.0
    assert perfect.evidence["substitution_catalog"] == {
        "mode": "identity-only",
        "source_kind": "identity-only",
        "undefined_target_policy": "identity-only",
        "authority_target_count": 1,
        "defined_target_count": 0,
        "allow_original_target_count": 1,
        "target_examples": [
            {
                "target_item_code": "a",
                "defined_in_source": False,
                "allow_original": True,
                "option_count": 1,
                "roles": ["no-replacement-identity"],
                "source_rows": [],
            }
        ],
    }
    assert empty.score == 0.0
    assert empty.status == "FAIL"
    assert empty.evidence["N_target_sites"] == 2
    assert empty.evidence["valid_delivery_sites"] == 0
    assert empty.evidence["curve_absolute_deviation"] == 2
    assert empty.evidence["total_absolute_deviation"] == 2
    assert empty.evidence["shortfall_units"] == 2
    assert empty.evidence["overage_units"] == 0
    assert empty.evidence["count_gap_units"] == 2
    assert empty.evidence["redistribution_units"] == 0
    assert empty.evidence["curve_loss_units"] == 2
    assert empty.evidence["total_loss_units"] == 2
    assert empty.evidence["at_zero_boundary"] is True
    assert empty.evidence["clamp_truncated"] is False
    assert empty.evidence["zero_cause"] == "no_valid_deliveries"
    assert empty.evidence["rate"] == 0.0


def test_o2_counts_one_cross_month_move_as_one_redistribution_unit() -> None:
    check = _score(
        _install_fixture(
            (
                ("R1", "S1", "C1", 1),
                ("R1", "S2", "C1", 5),
            ),
            {"R1": {1: 2}},
        )
    )

    grid = {
        (row["group"], row["month"]): (
            row["target_B"],
            row["valid_deliveries_A"],
            row["absolute_deviation"],
        )
        for row in check.evidence["scaled_target_grid"]
    }
    assert check.evidence["candidate_month_policy"] == "candidate_install_result"
    assert {
        row["site"]: row["month"]
        for row in check.evidence["valid_site_examples"]
    } == {"S1": 1, "S2": 2}
    assert grid == {("r1", 1): (2, 1, 1), ("r1", 2): (0, 1, 1)}
    assert check.evidence["total_absolute_deviation"] == 2
    assert check.evidence["shortfall_units"] == 1
    assert check.evidence["overage_units"] == 1
    assert check.evidence["count_gap_units"] == 0
    assert check.evidence["redistribution_units"] == 1
    assert check.evidence["curve_decomposition_identity_holds"] is True
    assert check.evidence["curve_absolute_deviation"] == (
        check.evidence["count_gap_units"]
        + 2 * check.evidence["redistribution_units"]
    )
    assert check.evidence["curve_loss_units"] == 1
    assert check.evidence["total_loss_units"] == 1
    assert check.evidence["invalid_selected_sites"] == 0
    assert check.evidence["site_validity_reason_counts"] == {}
    assert all(
        row["reasons"] == []
        for row in check.evidence["valid_site_examples"]
    )
    assert check.evidence["clamp_truncated"] is False
    assert check.evidence["zero_cause"] == "not_zero"
    assert check.score == 50.0


def test_o2_candidate_plan_external_sites_are_diagnostic_only() -> None:
    base = _install_fixture(
        (("R1", "S1", "C1", 1), ("R1", "S2", "C1", 1)),
        {"R1": {1: 1}},
    )
    plan = base.artifacts.get("site_plan").table.copy()
    fictitious = plan_frame(
        (("R9", "FICTITIOUS", "install", 1), ("R9", "FICTITIOUS", "install", 1))
    )
    context = o2_context(
        scope=base.artifacts.get("scope_input").table,
        batches=base.artifacts.get("batch_input").table,
        master=base.artifacts.get("master_plan").table,
        plan=pd.concat([plan, fictitious], ignore_index=True),
        final=base.artifacts.get("final_material").table,
    )

    check = _score(context)

    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.evidence["total_absolute_deviation"] == 0
    assert "out_of_scope_site_count" not in check.evidence
    assert check.evidence["non_scoring_plan_external_site_count"] == 1
    assert check.evidence["non_scoring_plan_external_sites"][0]["site"] == "FICTITIOUS"
    assert len(check.evidence["non_scoring_plan_external_sites"][0]["source_rows"]) == 2
    assert check.score == 100.0


def test_o2_plan_external_diagnostics_use_the_complete_authoritative_site_scope() -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "DELIVERY", "install", "A", 1),
                ("R1", "PURE-DISMANTLE", "dismantle", "A", 1),
                ("R1", "OUTSIDE-BATCH", "install", "A", 1),
            )
        ),
        batches=batch_frame((("R1", "DELIVERY", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "DELIVERY", "install", 1),
                ("R1", "PURE-DISMANTLE", "install", 1),
                ("R1", "OUTSIDE-BATCH", "install", 1),
            )
        ),
        final=final_frame(
            (("R1", "DELIVERY", "install", "A", 1, "A", 1),)
        ),
    )

    check = _score(context)

    assert check.evidence["non_scoring_plan_external_site_count"] == 0
    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.score == 100.0


def test_o2_material_scope_filter_defines_n_a_actions_and_out_normal_scope(
    monkeypatch,
) -> None:
    def filtered_material_authority(_source, *, material_mode):
        assert material_mode == "base-pk-standardized"
        return {"r1|ACTIVE|install": {"a": 1}}

    monkeypatch.setattr(
        "simulation.ei.rules.ei_standard.effective_delivery.o2."
        "_normalized_scope_material_facts",
        filtered_material_authority,
    )
    scope = scope_frame(
        (
            ("R1", "ACTIVE", "install", "A", 1),
            # The selected material mode removes both raw FILTERED actions.
            ("R1", "FILTERED", "install", "UNSUPPORTED", 1),
            ("R1", "FILTERED", "dismantle", "UNSUPPORTED", 1),
        )
    )
    scope["band"] = "1800"
    scope["ntnr"] = "4T4R"
    scope["required_qty"] = 1
    batches = batch_frame(
        (("R1", "ACTIVE", "C1"), ("R1", "FILTERED", "C1"))
    )
    master = master_frame({"R1": {1: 999}})
    final = final_frame(
        (("R1", "ACTIVE", "install", "A", 1, "A", 1),)
    )
    parameters = {"o2_scope_material_mode": "base-pk-standardized"}

    baseline = _score(
        o2_context(
            scope=scope,
            batches=batches,
            master=master,
            plan=plan_frame((("R1", "ACTIVE", "install", 1),)),
            final=final,
            parameters=parameters,
        )
    )

    assert baseline.evidence["N_target_sites"] == 1
    assert baseline.evidence["expected_source_actions"] == 1
    assert baseline.evidence["scoped_authority_actions"] == 1
    assert baseline.evidence["candidate_selected_authority_sites"] == 1
    assert baseline.evidence["valid_delivery_sites"] == 1
    assert baseline.evidence["invalid_selected_sites"] == 0
    assert baseline.evidence["non_scoring_plan_external_site_count"] == 0
    assert [row["site"] for row in baseline.evidence["valid_site_examples"]] == [
        "ACTIVE"
    ]
    assert baseline.evidence["valid_site_examples"][0][
        "candidate_action_counts"
    ] == {"install": 1}
    assert baseline.score == 100.0

    submitted_filtered = _score(
        o2_context(
            scope=scope,
            batches=batches,
            master=master,
            plan=plan_frame(
                (
                    ("R1", "ACTIVE", "install", 1),
                    ("R1", "FILTERED", "install", 1),
                )
            ),
            final=final,
            parameters=parameters,
        )
    )

    assert submitted_filtered.evidence["N_target_sites"] == 1
    assert submitted_filtered.evidence["candidate_selected_authority_sites"] == 1
    assert submitted_filtered.evidence["valid_delivery_sites"] == 1
    assert submitted_filtered.evidence["non_scoring_plan_external_site_count"] == 1
    assert [
        row["site"]
        for row in submitted_filtered.evidence["non_scoring_plan_external_sites"]
    ] == ["FILTERED"]
    assert submitted_filtered.evidence["curve_absolute_deviation"] == 0
    assert submitted_filtered.evidence["total_absolute_deviation"] == 0
    assert submitted_filtered.score == 100.0


def test_o2_accepts_original_bom_even_when_source_only_lists_a_replacement() -> None:
    substitution_source = pd.DataFrame(
        (
            {
                "solution_id": "S_P1",
                "priority": 1,
                "target_item_code": "A",
                "target_qty": 1,
                "sub_item_code": "",
                "sub_qty": 0,
                "new_issue_item_code": "",
            },
            {
                "solution_id": "S_P2",
                "priority": 2,
                "target_item_code": "",
                "target_qty": 0,
                "sub_item_code": "B",
                "sub_qty": 1,
                "new_issue_item_code": "",
            },
        )
    )
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
        substitution_source=substitution_source,
        parameters={"o2_substitution_mode": "legacy-combination"},
    )
    # The adapter has already frozen the authoritative catalog. Mutating the
    # physical source table must not change O2's legal identity set.
    context.artifacts.get("substitution_source").table.loc[
        lambda frame: frame["sub_item_code"].eq("B"),
        "sub_item_code",
    ] = "A"

    check = _score(context)

    catalog = check.evidence["substitution_catalog"]
    assert catalog["defined_target_count"] == 1
    assert catalog["allow_original_target_count"] == 1
    assert catalog["target_examples"][0]["allow_original"] is True
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 0
    assert check.score == 100.0


def test_o2_accepts_original_bom_only_when_authority_catalog_allows_identity() -> None:
    substitution_source = pd.DataFrame(
        (
            {
                "solution_id": "S_P1",
                "priority": 1,
                "target_item_code": "A",
                "target_qty": 1,
                "sub_item_code": "A",
                "sub_qty": 1,
                "new_issue_item_code": "",
            },
            {
                "solution_id": "S_P2",
                "priority": 2,
                "target_item_code": "",
                "target_qty": 0,
                "sub_item_code": "B",
                "sub_qty": 1,
                "new_issue_item_code": "",
            },
        )
    )
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
        substitution_source=substitution_source,
        parameters={"o2_substitution_mode": "priority-row-views"},
    )

    check = _score(context)

    catalog = check.evidence["substitution_catalog"]
    assert catalog["defined_target_count"] == 1
    assert catalog["allow_original_target_count"] == 1
    assert catalog["target_examples"][0]["roles"] == ["identity", "substitute"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 0
    assert check.score == 100.0


@pytest.mark.parametrize(
    ("dismantle_item", "expected_score"),
    (("A", 100.0), ("B", 0.0)),
)
def test_o2_applies_substitution_catalog_only_to_install_actions(
    dismantle_item: str,
    expected_score: float,
) -> None:
    substitution_source = pd.DataFrame(
        (
            {
                "solution_id": "S_P1",
                "priority": 1,
                "target_item_code": "A",
                "target_qty": 1,
                "sub_item_code": "",
                "sub_qty": 0,
                "new_issue_item_code": "",
            },
            {
                "solution_id": "S_P2",
                "priority": 2,
                "target_item_code": "",
                "target_qty": 0,
                "sub_item_code": "B",
                "sub_qty": 1,
                "new_issue_item_code": "",
            },
        )
    )
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S1", "dismantle", "A", 1),
            )
        ),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 3),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "B", 1, "A", 1),
                (
                    "R1",
                    "S1",
                    "dismantle",
                    dismantle_item,
                    1,
                    "A",
                    3,
                ),
            )
        ),
        substitution_source=substitution_source,
        parameters={"o2_substitution_mode": "legacy-combination"},
    )

    check = _score(context)

    assert check.score == expected_score
    assert check.evidence["install_material_policy"] == (
        "authority-substitution-catalog"
    )
    assert check.evidence["dismantle_material_policy"] == (
        "exact-authority-original"
    )
    assert check.evidence["valid_delivery_sites"] == (
        1 if expected_score == 100.0 else 0
    )
    if expected_score == 0.0:
        assert "DISMANTLE_BOM_INVALID" in _invalid_sites(check)["S1"][
            "reasons"
        ]


@pytest.mark.parametrize(
    (
        "quantity_mode",
        "install_quantity",
        "dismantle_quantity",
        "expected_score",
        "expected_reason",
    ),
    (
        ("dismantle-absolute", 1, 1, 100.0, None),
        ("dismantle-absolute", 1, -1, 100.0, None),
        ("dismantle-absolute", -1, 1, 0.0, "INSTALL_BOM_INVALID"),
        ("signed-action", 1, 1, 0.0, "DISMANTLE_BOM_INVALID"),
    ),
)
def test_o2_final_bom_quantity_mode_keeps_install_direction_strict(
    quantity_mode: str,
    install_quantity: int,
    dismantle_quantity: int,
    expected_score: float,
    expected_reason: str | None,
) -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S1", "dismantle", "A", 1),
            )
        ),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 3),
            )
        ),
        final=final_frame(
            (
                (
                    "R1",
                    "S1",
                    "install",
                    "A",
                    install_quantity,
                    "A",
                    1,
                ),
                (
                    "R1",
                    "S1",
                    "dismantle",
                    "A",
                    dismantle_quantity,
                    "A",
                    3,
                ),
            )
        ),
        parameters={"o2_final_bom_quantity_mode": quantity_mode},
    )

    check = _score(context)

    assert check.score == expected_score, check.evidence
    assert check.evidence["final_bom_quantity_mode"] == quantity_mode
    sign_counts = check.evidence["final_bom_submitted_sign_counts"]
    assert sign_counts["install"][
        "positive" if install_quantity > 0 else "negative"
    ] == 1
    assert sign_counts["dismantle"][
        "positive" if dismantle_quantity > 0 else "negative"
    ] == 1
    expected_accepted_signs = {
        "install": (
            ["positive", "negative"]
            if quantity_mode == "absolute"
            else ["positive"]
        ),
        "dismantle": (
            ["negative"]
            if quantity_mode == "signed-action"
            else ["positive", "negative"]
        ),
    }
    assert check.evidence["final_bom_normalization"] == {
        "direction": "action",
        "magnitude": "abs(required_qty)",
        "install": "+abs(required_qty)",
        "dismantle": "-abs(required_qty)",
        "accepted_submitted_signs": expected_accepted_signs,
    }
    assert check.evidence["valid_delivery_sites"] == int(expected_reason is None)
    assert check.evidence["strict_bom_invalid_rows"] == int(
        expected_reason is not None
    )
    if expected_reason is not None:
        assert expected_reason in _invalid_sites(check)["S1"]["reasons"]


@pytest.mark.parametrize(
    ("defect_kind", "extra_rows", "expected_reason"),
    (
        ("fictitious-code", 1, "INSTALL_BOM_INVALID"),
        ("fictitious-code", 3, "INSTALL_BOM_INVALID"),
        ("over-quantity", 1, "INSTALL_BOM_INVALID"),
        ("over-quantity", 3, "INSTALL_BOM_INVALID"),
        ("extra-action", 1, "EXTRA_BOM_ACTION"),
        ("extra-action", 3, "EXTRA_BOM_ACTION"),
    ),
)
def test_o2_material_defect_invalidates_its_target_site_exactly_once(
    defect_kind: str,
    extra_rows: int,
    expected_reason: str,
) -> None:
    final_rows = [
        ("R1", "S1", "install", "A", 1, "A", 1),
        ("R1", "S2", "install", "A", 1, "A", 1),
    ]
    for index in range(extra_rows):
        if defect_kind == "fictitious-code":
            final_rows.append(
                ("R1", "S2", "install", f"OUT-{index}", 1, "A", 1)
            )
        elif defect_kind == "over-quantity":
            final_rows.append(("R1", "S2", "install", "A", 1, "A", 1))
        else:
            final_rows.append(("R1", "S2", "dismantle", "A", 1, "A", 1))
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S2", "install", "A", 1),
            )
        ),
        batches=batch_frame(
            (("R1", "S1", "C1"), ("R1", "S2", "C1"))
        ),
        master=master_frame({"R1": {1: 2}}),
        plan=plan_frame(
            (("R1", "S1", "install", 1), ("R1", "S2", "install", 1))
        ),
        final=final_frame(final_rows),
    )

    check = _score(context)

    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["curve_absolute_deviation"] == 1
    assert check.evidence["total_absolute_deviation"] == 1
    assert expected_reason in _invalid_sites(check)["S2"]["reasons"]
    assert check.evidence["fictitious_material_invalid_site_count"] == (
        1 if defect_kind == "fictitious-code" else 0
    )
    if defect_kind == "over-quantity":
        assert check.evidence["legal_but_unmatched_material_site_count"] == 1
    if defect_kind == "extra-action":
        assert check.evidence["extra_bom_action_site_count"] == 1
    assert check.score == 50.0


def test_o2_orphan_final_bom_is_diagnostic_and_does_not_create_site_f() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R9", "FAKE", "install", "X", 1, "X", 1),
            )
        ),
    )

    check = _score(context)

    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.evidence["total_absolute_deviation"] == 0
    assert check.evidence["non_scoring_orphan_final_material_site_count"] == 1
    assert check.evidence["non_scoring_orphan_final_material_sites"][0]["site"] == "FAKE"
    assert check.score == 100.0


def test_o2_plan_external_sites_do_not_clamp_an_otherwise_perfect_score() -> None:
    base = _install_fixture((("R1", "S1", "C1", 1),), {"R1": {1: 1}})
    plan = base.artifacts.get("site_plan").table.copy()
    out_rows = plan_frame(
        (
            ("R9", "OUT-1", "install", 1),
            ("R9", "OUT-2", "install", 1),
            ("R9", "OUT-3", "install", 1),
        )
    )
    context = o2_context(
        scope=base.artifacts.get("scope_input").table,
        batches=base.artifacts.get("batch_input").table,
        master=base.artifacts.get("master_plan").table,
        plan=pd.concat([plan, out_rows], ignore_index=True),
        final=base.artifacts.get("final_material").table,
    )

    check = _score(context)

    assert check.evidence["N_target_sites"] == 1
    assert check.evidence["curve_absolute_deviation"] == 0
    assert check.evidence["non_scoring_plan_external_site_count"] == 3
    assert check.evidence["non_scoring_plan_external_score_effect"] == "none"
    assert check.evidence["total_absolute_deviation"] == 0
    assert check.evidence["rate"] == 1.0
    assert check.score == 100.0


@pytest.mark.parametrize(
    ("defect", "expected_reason"),
    (
        ("missing_action", "MISSING_DISMANTLE_ACTION"),
        ("illegal_bom", "INSTALL_BOM_INVALID"),
        ("bad_interval", "INTERVAL_VIOLATION"),
    ),
)
def test_o2_invalidates_only_the_defective_site_without_legacy_five_checks(
    defect: str,
    expected_reason: str,
) -> None:
    authority_rows = tuple(
        ("R1", site, action, "A", 1)
        for site in ("S1", "S2")
        for action in ("install", "dismantle")
    )
    plan_rows = [
        ("R1", "S1", "install", 1),
        ("R1", "S1", "dismantle", 3),
        ("R1", "S2", "install", 1),
        ("R1", "S2", "dismantle", 3),
    ]
    final_rows = [
        (
            "R1",
            site,
            action,
            "A",
            1,
            "A",
            1 if action == "install" else 3,
        )
        for site in ("S1", "S2")
        for action in ("install", "dismantle")
    ]
    if defect == "missing_action":
        plan_rows = [
            row
            for row in plan_rows
            if not (row[1] == "S2" and row[2] == "dismantle")
        ]
    elif defect == "illegal_bom":
        final_rows = [
            (*row[:3], "X", *row[4:])
            if row[1] == "S2" and row[2] == "install"
            else row
            for row in final_rows
        ]
    elif defect == "bad_interval":
        plan_rows = [
            (*row[:3], 2)
            if row[1] == "S2" and row[2] == "dismantle"
            else row
            for row in plan_rows
        ]
        final_rows = [
            (*row[:6], 2)
            if row[1] == "S2" and row[2] == "dismantle"
            else row
            for row in final_rows
        ]

    context = o2_context(
        scope=scope_frame(authority_rows),
        batches=batch_frame(("R1", site, "C1") for site in ("S1", "S2")),
        master=master_frame({"R1": {1: 10}}),
        plan=plan_frame(plan_rows),
        final=final_frame(final_rows),
    )

    # A standalone O2 context cannot consume the old C2/C6a/O1/S1/S5 leaves.
    assert set(context.question.components) == {"effective-delivery"}
    assert [check.check_id for check in context.component.checks] == [
        "effective-delivery.O2"
    ]

    check = _score(context)
    valid = {row["site"]: row for row in check.evidence["valid_site_examples"]}
    invalid = {row["site"]: row for row in check.evidence["invalid_site_examples"]}

    assert set(valid) == {"S1"}
    assert set(invalid) == {"S2"}
    assert expected_reason in invalid["S2"]["reasons"]
    assert check.evidence["candidate_selected_authority_sites"] == 2
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1
    assert check.evidence["curve_absolute_deviation"] == 1
    assert check.score == 50.0


def test_o2_batch_finish_anchor_is_global_across_regions() -> None:
    authority = tuple(
        (region, site, action, "A", 1)
        for region, site in (("R1", "S1"), ("R2", "S2"))
        for action in ("install", "dismantle")
    )
    context = o2_context(
        scope=scope_frame(authority),
        batches=batch_frame(
            (("R1", "S1", "C1"), ("R2", "S2", "C1"))
        ),
        master=master_frame({"R1": {1: 1}, "R2": {3: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 12),
                ("R2", "S2", "install", 10),
                ("R2", "S2", "dismantle", 12),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "A", 1, "A", 12),
                ("R2", "S2", "install", "A", 1, "A", 10),
                ("R2", "S2", "dismantle", "A", 1, "A", 12),
            )
        ),
        parameters={
            "o2_interval_contract": {
                "anchor": "batch-finish",
                "relation": "exact",
                "lag_weeks": 2,
            }
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["batch_finish_scope"] == "global_batch"
    assert {row["site"] for row in check.evidence["valid_site_examples"]} == {
        "S1",
        "S2",
    }


def test_o2_site_install_anchor_does_not_wait_for_another_site_in_batch() -> None:
    authority = tuple(
        ("R1", site, action, "A", 1)
        for site in ("S1", "S2")
        for action in ("install", "dismantle")
    )
    plan_rows = (
        ("R1", "S1", "install", 1),
        ("R1", "S1", "dismantle", 1),
        ("R1", "S2", "install", 10),
        ("R1", "S2", "dismantle", 10),
    )
    final_rows = tuple(
        (region, site, action, "A", 1, "A", week)
        for region, site, action, week in plan_rows
    )
    common = {
        "scope": scope_frame(authority),
        "batches": batch_frame(("R1", site, "C1") for site in ("S1", "S2")),
        "master": master_frame({"R1": {1: 1, 3: 1}}),
        "plan": plan_frame(plan_rows),
        "final": final_frame(final_rows),
    }

    site_check = _score(
        o2_context(
            **common,
            parameters={
                "o2_interval_contract": {
                    "anchor": "site-install",
                    "relation": "minimum",
                    "lag_weeks": 0,
                }
            },
        )
    )
    batch_check = _score(
        o2_context(
            **common,
            parameters={
                "o2_interval_contract": {
                    "anchor": "batch-finish",
                    "relation": "minimum",
                    "lag_weeks": 0,
                }
            },
        )
    )

    assert site_check.score == 100.0
    assert site_check.evidence["interval_anchor_scope"] == "site"
    assert site_check.evidence["interval_contract"] == {
        "anchor": "site-install",
        "relation": "minimum",
        "lag_weeks": 0,
    }
    assert {row["site"] for row in site_check.evidence["valid_site_examples"]} == {
        "S1",
        "S2",
    }
    assert batch_check.score == 50.0
    invalid = {
        row["site"]: row for row in batch_check.evidence["invalid_site_examples"]
    }
    assert "INTERVAL_VIOLATION" in invalid["S1"]["reasons"]


def test_o2_site_install_minimum_zero_rejects_early_dismantle() -> None:
    check = _score(
        o2_context(
            scope=scope_frame(
                (
                    ("R1", "S1", "install", "A", 1),
                    ("R1", "S1", "dismantle", "A", 1),
                )
            ),
            batches=batch_frame((("R1", "S1", "C1"),)),
            master=master_frame({"R1": {1: 1}}),
            plan=plan_frame(
                (
                    ("R1", "S1", "install", 2),
                    ("R1", "S1", "dismantle", 1),
                )
            ),
            final=final_frame(
                (
                    ("R1", "S1", "install", "A", 1, "A", 2),
                    ("R1", "S1", "dismantle", "A", 1, "A", 1),
                )
            ),
            parameters={
                "o2_interval_contract": {
                    "anchor": "site-install",
                    "relation": "minimum",
                    "lag_weeks": 0,
                }
            },
        )
    )

    assert check.score == 0.0
    invalid = check.evidence["invalid_site_examples"][0]
    assert invalid["interval_anchor"] == "site-install"
    assert invalid["interval_anchor_week"] == 2
    assert invalid["dismantle_week"] == 1
    assert invalid["actual_lag_weeks"] == -1
    assert "INTERVAL_VIOLATION" in invalid["reasons"]


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_reason"),
    (
        ("status", "cancelled", "INVALID_SITE_STATUS"),
        ("site_count", 2, "SITE_COUNT_NOT_ONE"),
    ),
)
def test_o2_invalid_plan_row_does_not_enter_the_batch_finish_anchor(
    field: str,
    bad_value: object,
    expected_reason: str,
) -> None:
    plan = plan_frame(
        (
            ("R1", "S1", "install", 1),
            ("R1", "S1", "dismantle", 3),
            ("R1", "S2", "install", 10),
            ("R1", "S2", "dismantle", 12),
        )
    )
    plan.loc[
        (plan["site_name"] == "S2") & (plan["site_action"] == "install"),
        field,
    ] = bad_value
    context = o2_context(
        scope=scope_frame(
            tuple(
                ("R1", site, action, "A", 1)
                for site in ("S1", "S2")
                for action in ("install", "dismantle")
            )
        ),
        batches=batch_frame(("R1", site, "C1") for site in ("S1", "S2")),
        master=master_frame({"R1": {1: 2}}),
        plan=plan,
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "A", 1, "A", 3),
                ("R1", "S2", "install", "A", 1, "A", 10),
                ("R1", "S2", "dismantle", "A", 1, "A", 12),
            )
        ),
    )

    check = _score(context)
    valid = {row["site"]: row for row in check.evidence["valid_site_examples"]}
    invalid = {
        row["site"]: row for row in check.evidence["invalid_site_examples"]
    }

    # If S2's invalid week-10 install entered the finish anchor, S1's week-3
    # dismantle would also fail its two-week interval. Only S2 may be invalid.
    assert set(valid) == {"S1"}
    assert set(invalid) == {"S2"}
    assert expected_reason in invalid["S2"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1


def test_o2_unscheduled_blank_time_counts_once_without_time_or_bom_cascade() -> None:
    plan = plan_frame(
        (
            ("R1", "S1", "install", 1),
            ("R1", "S2", "install", 2),
        )
    )
    unscheduled = plan["site_name"] == "S2"
    plan.loc[unscheduled, "status"] = "unscheduled"
    plan["project_week"] = plan["project_week"].astype(object)
    plan.loc[unscheduled, ["project_week", "week_start"]] = ""
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S2", "install", "A", 1),
            )
        ),
        batches=batch_frame(
            (("R1", "S1", "C1"), ("R1", "S2", "C1"))
        ),
        master=master_frame({"R1": {1: 2}}),
        plan=plan,
        final=final_frame(
            (("R1", "S1", "install", "A", 1, "A", 1),)
        ),
    )

    check = _score(context)

    invalid = check.evidence["invalid_site_examples"]
    assert len(invalid) == 1
    assert invalid[0]["site"] == "S2"
    assert invalid[0]["reasons"] == ["INSTALL_UNSCHEDULED"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1


def test_o2_reports_question_region_conflict_as_evaluator_error() -> None:
    context = o2_context(
        scope=scope_frame((("R3", "S1", "install", "A", 1),)),
        batches=batch_frame((("R4", "S1", "C1"),)),
        master=master_frame({"R3": {1: 1}}),
        plan=plan_frame((("R3", "S1", "install", 1),)),
        final=final_frame((("R3", "S1", "install", "A", 1, "A", 1),)),
    )

    check = _score(context)

    assert check.status == "UNSCORABLE"
    assert check.reason_code == "EVALUATOR_ERROR"
    assert "QUESTION_DATA_CONFLICT" in check.evidence["error"]


def test_o2_rejects_final_bom_week_that_differs_from_the_unique_plan_action() -> None:
    context = o2_context(
        scope=scope_frame(
            tuple(
                ("R1", site, action, "A", 1)
                for site in ("S1", "S2")
                for action in ("install", "dismantle")
            )
        ),
        batches=batch_frame(("R1", site, "C1") for site in ("S1", "S2")),
        master=master_frame({"R1": {1: 2}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 3),
                ("R1", "S2", "install", 1),
                ("R1", "S2", "dismantle", 3),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "A", 1, "A", 3),
                # S2's install BOM claims week 2 while its unique plan row is week 1.
                ("R1", "S2", "install", "A", 1, "A", 2),
                ("R1", "S2", "dismantle", "A", 1, "A", 3),
            )
        ),
    )

    check = _score(context)
    valid = {row["site"]: row for row in check.evidence["valid_site_examples"]}
    invalid = {
        row["site"]: row for row in check.evidence["invalid_site_examples"]
    }

    assert set(valid) == {"S1"}
    assert set(invalid) == {"S2"}
    assert "FINAL_BOM_WEEK_MISMATCH" in invalid["S2"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1


def test_o2_missing_final_action_does_not_invent_a_week_mismatch() -> None:
    check = _score(
        _single_install_context(
            final=final_frame(()),
        )
    )

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert "INSTALL_BOM_INVALID" in invalid["S1"]["reasons"]
    assert "FINAL_BOM_WEEK_MISMATCH" not in invalid["S1"]["reasons"]


def test_o2_wrong_region_with_legal_material_is_not_fictitious_or_a_week_error() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R9", "S1", "install", 1),)),
        final=final_frame((("R9", "S1", "install", "A", 1, "A", 1),)),
    )

    check = _score(context)

    invalid = _invalid_sites(check)
    assert "SITE_REGION_MISMATCH" in invalid["S1"]["reasons"]
    assert "INSTALL_BOM_INVALID" in invalid["S1"]["reasons"]
    assert "FINAL_BOM_WEEK_MISMATCH" not in invalid["S1"]["reasons"]
    assert check.evidence["fictitious_material_invalid_site_count"] == 0
    assert check.evidence["legal_but_unmatched_material_site_count"] == 1


@pytest.mark.parametrize(
    "missing_column",
    ("status", "site_count", "week_start"),
)
def test_o2_rejects_site_plan_missing_a_required_delivery_column(
    missing_column: str,
) -> None:
    plan = plan_frame((("R1", "S1", "install", 1),)).drop(
        columns=[missing_column]
    )

    check = _score(_single_install_context(plan=plan))

    assert check.score == 0.0
    assert check.status == "FAIL"
    assert check.reason_code == "INVALID_ARTIFACT"
    assert "site_plan cannot be parsed" in check.explanation
    assert missing_column in check.evidence["error"]


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_reason"),
    (
        ("week_start", "2027/01/04", "INVALID_WEEK_START"),
    ),
)
def test_o2_rejects_invalid_or_inconsistent_plan_week_fields(
    field: str,
    bad_value: object,
    expected_reason: str,
) -> None:
    plan = plan_frame((("R1", "S1", "install", 1),))
    plan.loc[0, field] = bad_value

    check = _score(_single_install_context(plan=plan))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert expected_reason in invalid["S1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["invalid_selected_sites"] == 1
    assert check.score == 0.0


def test_o2_week_start_uses_a_result_internal_project_anchor_not_iso_year_start() -> None:
    plan = plan_frame(
        (("R1", "S1", "install", 1), ("R1", "S2", "install", 2))
    )
    plan.loc[plan["site_name"] == "S1", "week_start"] = "2027-02-03"
    plan.loc[plan["site_name"] == "S2", "week_start"] = "2027-02-10"
    context = o2_context(
        scope=scope_frame(
            (("R1", "S1", "install", "A", 1), ("R1", "S2", "install", "A", 1))
        ),
        batches=batch_frame((("R1", "S1", "C1"), ("R1", "S2", "C1"))),
        master=master_frame({"R1": {2: 2}}),
        plan=plan,
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S2", "install", "A", 1, "A", 2),
            )
        ),
        parameters={"o2_delivery_month_source": "week-start"},
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["delivery_month_source"] == "week-start"
    assert check.evidence["scaled_target_grid"] == [
        {
            "group": "r1",
            "month": 2,
            "year_month": "2027-02",
            "target_B": 2,
            "valid_deliveries_A": 2,
            "absolute_deviation": 0,
        }
    ]


def test_o2_week_start_rejects_rows_without_one_relative_project_anchor() -> None:
    plan = plan_frame(
        (("R1", "S1", "install", 1), ("R1", "S2", "install", 2))
    )
    plan.loc[plan["site_name"] == "S1", "week_start"] = "2027-02-03"
    plan.loc[plan["site_name"] == "S2", "week_start"] = "2027-02-17"
    context = o2_context(
        scope=scope_frame(
            (("R1", "S1", "install", "A", 1), ("R1", "S2", "install", "A", 1))
        ),
        batches=batch_frame((("R1", "S1", "C1"), ("R1", "S2", "C1"))),
        master=master_frame({"R1": {2: 2}}),
        plan=plan,
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S2", "install", "A", 1, "A", 2),
            )
        ),
        parameters={"o2_delivery_month_source": "week-start"},
    )

    check = _score(context)

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1", "S2"}
    assert all("WEEK_START_MISMATCH" in row["reasons"] for row in invalid.values())


def test_o2_reconcile_accepts_prompt_week_num_when_project_week_is_absent() -> None:
    plan = plan_frame((("R1", "S1", "install", 1),)).rename(
        columns={"project_week": "week_num"}
    )
    plan["week_num"] = plan["week_num"].astype(object)
    plan.loc[:, "week_num"] = "WK1"
    plan["mos_weekly_plan"] = "2027WK1"

    check = _score(
        _single_install_context(
            plan=plan,
            parameters={
                "o2_site_plan_required_fields": [
                    "site_id",
                    "region",
                    "action",
                    "week_num",
                    "week_start",
                    "status",
                    "site_count",
                    "cluster_id",
                ]
            },
        )
    )

    assert check.score == 100.0
    assert check.evidence["valid_delivery_sites"] == 1


def test_o2_week_label_month_is_independent_of_continuous_schedule_week() -> None:
    plan = plan_frame((("R1", "S1", "install", 1),))
    plan["week_num"] = 1
    plan["mos_weekly_plan"] = "2027WK5"
    final = pd.DataFrame(
        {
            "site_name": ["S1"],
            "install_month": [2],
            "install_wk_label": ["2027WK5"],
            "dismantle_month": [""],
            "dismantle_wk_label": [""],
            "item_code": ["A"],
            "required_qty": [1],
            "original_bom": ["A"],
            "original_bom_qty": [1],
            "region": ["R1"],
            "action": ["install"],
        }
    )
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {2: 1}}),
        plan=plan,
        final=final,
        parameters={
            "o2_project_week_source": "week_num",
            "o2_delivery_month_source": "week-label",
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["schedule_week_source"] == "week_num"
    assert check.evidence["delivery_month_source"] == "week-label"


@pytest.mark.parametrize(
    ("final_week_label", "expected_score"),
    (
        ("2024-W27", 100.0),
        ("WK27", 100.0),
        ("2023-W27", 0.0),
    ),
)
def test_o2_week_label_contract_uses_full_year_when_present_and_plan_year_for_short_label(
    final_week_label: str,
    expected_score: float,
) -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["S1"],
            "site_action": ["install"],
            "mos_weekly_plan": ["2024-W27"],
            "week_num": [1],
            "region": ["R1"],
            "site_count": [1],
        }
    )
    final = pd.DataFrame(
        {
            "site_name": ["S1"],
            "install_month": ["2024M7"],
            "install_wk_label": [final_week_label],
            "dismantle_month": [""],
            "dismantle_wk_label": [""],
            "item_code": ["A"],
            "required_qty": [1],
            "original_bom": ["A"],
            "original_bom_qty": [1],
            "region": ["R1"],
            "action": ["install"],
        }
    )
    check = _score(
        o2_context(
            scope=scope_frame((("R1", "S1", "install", "A", 1),)),
            batches=batch_frame((("R1", "S1", "C1"),)),
            master=pd.DataFrame(
                {"region": ["R1"], "month": ["2024-07-01"], "master_count": [1]}
            ),
            plan=plan,
            final=final,
            parameters={
                "o2_project_week_source": "week_num",
                "o2_delivery_month_source": "week-label",
                "o2_site_plan_required_fields": [
                    "site_id",
                    "action",
                    "week_label",
                    "week_num",
                    "region",
                    "site_count",
                ],
            },
        )
    )

    assert check.score == expected_score
    assert check.evidence["valid_delivery_sites"] == (
        1 if expected_score == 100.0 else 0
    )
    if expected_score == 100.0:
        assert "FINAL_BOM_WEEK_MISMATCH" not in check.evidence[
            "site_validity_reason_counts"
        ]
    else:
        assert "FINAL_BOM_WEEK_MISMATCH" in check.evidence[
            "site_validity_reason_counts"
        ]


def test_o2_keeps_same_calendar_month_in_different_years_as_distinct_periods() -> None:
    plan = pd.DataFrame(
        {
            "site_name": ["S1", "S2"],
            "site_action": ["install", "install"],
            "mos_weekly_plan": ["2023-W27", "2024-W27"],
            "week_num": [1, 27],
            "region": ["R1", "R1"],
            "site_count": [1, 1],
        }
    )
    final = pd.DataFrame(
        {
            "site_name": ["S1", "S2"],
            "install_month": ["2023M7", "2024M7"],
            "install_wk_label": ["2023-W27", "2024-W27"],
            "dismantle_month": ["", ""],
            "dismantle_wk_label": ["", ""],
            "item_code": ["A", "A"],
            "required_qty": [1, 1],
            "original_bom": ["A", "A"],
            "original_bom_qty": [1, 1],
            "region": ["R1", "R1"],
            "action": ["install", "install"],
        }
    )
    check = _score(
        o2_context(
            scope=scope_frame(
                (
                    ("R1", "S1", "install", "A", 1),
                    ("R1", "S2", "install", "A", 1),
                )
            ),
            batches=batch_frame(
                (("R1", "S1", "C1"), ("R1", "S2", "C1"))
            ),
            master=pd.DataFrame(
                {
                    "region": ["R1", "R1"],
                    "month": ["2023-07-01", "2024-07-01"],
                    "master_count": [1, 1],
                }
            ),
            plan=plan,
            final=final,
            parameters={
                "o2_project_week_source": "week_num",
                "o2_delivery_month_source": "week-label",
                "o2_site_plan_required_fields": [
                    "site_id",
                    "action",
                    "week_label",
                    "week_num",
                    "region",
                    "site_count",
                ],
            },
        )
    )

    assert check.score == 100.0
    assert [row["year_month"] for row in check.evidence["scaled_target_grid"]] == [
        "2023-07",
        "2024-07",
    ]


def test_o2_canonical_batch_identity_is_used_before_skip_rounding() -> None:
    sites = tuple(("R1", f"S{index}", "install", "A", 1) for index in range(1, 7))
    batches = tuple(
        ("R1", f"S{index}", "C-1" if index <= 3 else "C 1")
        for index in range(1, 7)
    )
    plan = plan_frame(tuple((region, site, action, 1) for region, site, action, _, _ in sites))
    plan["cluster"] = [batch for _, _, batch in batches]
    check = _score(
        o2_context(
            scope=scope_frame(sites),
            batches=batch_frame(batches),
            master=master_frame({"R1": {1: 1}}),
            plan=plan,
            final=final_frame(
                tuple(
                    (region, site, action, "A", 1, "A", 1)
                    for region, site, action, _, _ in sites
                )
            ),
            parameters={"o2_skip_rate": 0.1},
        )
    )

    assert check.evidence["authority_install_pool_sites"] == 6
    assert check.evidence["N_target_sites"] == 5
    assert len(check.evidence["pool_targets"]) == 1
    assert check.score == 80.0


def test_o2_skip_rounding_can_be_frozen_at_region_scope() -> None:
    authority_rows = tuple(
        ("R1", f"S{index}", "install", "A", 1) for index in range(1, 11)
    )
    batch_rows = tuple(
        ("R1", f"S{index}", "C1" if index <= 5 else "C2")
        for index in range(1, 11)
    )
    selected = authority_rows[:9]
    plan = plan_frame(
        tuple((region, site, action, 1) for region, site, action, _, _ in selected)
    )
    plan["cluster"] = ["C1" if index <= 5 else "C2" for index in range(1, 10)]
    final = final_frame(
        tuple(
            (region, site, action, "A", 1, "A", 1)
            for region, site, action, _, _ in selected
        )
    )
    common = {
        "scope": scope_frame(authority_rows),
        "batches": batch_frame(batch_rows),
        "master": master_frame({"R1": {1: 1}}),
        "plan": plan,
        "final": final,
    }

    batch_check = _score(
        o2_context(
            **common,
            parameters={"o2_skip_rate": 0.1},
        )
    )
    region_check = _score(
        o2_context(
            **common,
            parameters={
                "o2_skip_rate": 0.1,
                "o2_skip_pool_scope": "region",
            },
        )
    )

    assert batch_check.evidence["skip_pool_scope"] == "region-batch"
    assert batch_check.evidence["N_target_sites"] == 10
    assert batch_check.score == 90.0
    assert region_check.evidence["skip_pool_scope"] == "region"
    assert region_check.evidence["N_target_sites"] == 9
    assert region_check.evidence["pool_targets"] == [
        {
            "group": "r1",
            "batch": None,
            "skip_pool_scope": "region",
            "install_pool_sites": 10,
            "skip_rate": 0.1,
            "target_sites": 9,
        }
    ]
    assert region_check.score == 100.0


def test_o2_hamilton_tie_uses_decimal_aggregation_then_period_order() -> None:
    master = pd.DataFrame(
        {
            "region": ["R1", "R1", "R1"],
            "month": [1, 2, 2],
            "master_count": [0.3, 0.1, 0.2],
        }
    )
    check = _score(
        o2_context(
            scope=scope_frame((("R1", "S1", "install", "A", 1),)),
            batches=batch_frame((("R1", "S1", "C1"),)),
            master=master,
            plan=plan_frame((("R1", "S1", "install", 1),)),
            final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
        )
    )

    assert check.score == 100.0
    assert _target_grid(check) == {("r1", 1): 1, ("r1", 2): 0}


def test_o2_rejects_final_bom_missing_project_week() -> None:
    final = final_frame(
        (("R1", "S1", "install", "A", 1, "A", 1),)
    ).drop(columns=["project_week"])

    check = _score(_single_install_context(final=final))

    assert check.score == 0.0
    assert check.status == "FAIL"
    assert check.reason_code == "INVALID_ARTIFACT"
    assert "site_final_bom cannot be parsed" in check.explanation
    assert "project_week" in check.evidence["error"]


@pytest.mark.parametrize(
    "bad_project_week",
    ("W2", "2026WK2", 1.5, None),
)
def test_o2_project_week_requires_an_integer_even_with_a_valid_display_week(
    bad_project_week: object,
) -> None:
    plan = plan_frame((("R1", "S1", "install", 2),))
    plan["mos_weekly_plan"] = "2026WK2"
    plan["project_week"] = plan["project_week"].astype(object)
    plan.loc[0, "project_week"] = bad_project_week
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 2),))

    check = _score(_single_install_context(plan=plan, final=final))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert "INSTALL_UNPARSEABLE_WEEK" in invalid["S1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["invalid_selected_sites"] == 1
    assert check.score == 0.0


def test_o2_project_week_53_is_out_of_contract_range() -> None:
    plan = plan_frame((("R1", "S1", "install", 2),))
    plan.loc[0, "project_week"] = 53
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 2),))

    check = _score(_single_install_context(plan=plan, final=final))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert "PROJECT_WEEK_OUT_OF_RANGE" in invalid["S1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.score == 0.0


def test_o2_rejects_compact_week_start_date() -> None:
    plan = plan_frame((("R1", "S1", "install", 1),))
    plan.loc[0, "week_start"] = "20270104"

    check = _score(_single_install_context(plan=plan))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert "INVALID_WEEK_START" in invalid["S1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.score == 0.0


def test_o2_rejects_conflicting_display_week_for_a_valid_integer_project_week(
) -> None:
    plan = plan_frame((("R1", "S1", "install", 1),))
    plan["mos_weekly_plan"] = "2026WK2"

    check = _score(_single_install_context(plan=plan))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert "INSTALL_WEEK_CONFLICT" in invalid["S1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.score == 0.0


@pytest.mark.parametrize(
    "bad_project_week",
    ("W2", "2026WK2", 1.5, 53),
)
def test_o2_final_bom_project_week_requires_an_integer_from_1_to_52(
    bad_project_week: object,
) -> None:
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 2),))
    final["project_week"] = final["project_week"].astype(object)
    final.loc[0, "project_week"] = bad_project_week
    plan = plan_frame((("R1", "S1", "install", 2),))

    check = _score(_single_install_context(plan=plan, final=final))

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S1"}
    assert {
        "INSTALL_BOM_INVALID",
        "FINAL_BOM_WEEK_MISMATCH",
    } & set(invalid["S1"]["reasons"])
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["invalid_selected_sites"] == 1
    assert check.score == 0.0


def test_o2_enriches_optional_candidate_mocn_from_authoritative_batch_input(
) -> None:
    plan = plan_frame(
        (("R1", "S1", "install", 1),),
        batch_kind="mocn",
    ).drop(columns=["mocn_batch"])
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame(
            (("R1", "S1", 7),),
            batch_kind="mocn",
        ),
        master=master_frame({"R1": {1: 1}}),
        plan=plan,
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
        parameters={
            "o2_batch_kind": "mocn",
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
            "o2_site_plan_required_fields": [
                "site_id",
                "region",
                "action",
                "project_week",
                "week_start",
                "status",
                "site_count",
            ],
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.status == "PASS"
    assert check.evidence["valid_delivery_sites"] == 1


@pytest.mark.parametrize("missing_column", ("region", "mocn_batch"))
def test_o2_rejects_base_site_plan_missing_region_or_mocn_batch(
    missing_column: str,
) -> None:
    plan = plan_frame(
        (("R1", "S1", "install", 1),),
        batch_kind="mocn",
    ).drop(columns=[missing_column])
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame(
            (("R1", "S1", 1),),
            batch_kind="mocn",
        ),
        master=master_frame({"R1": {1: 1}}),
        plan=plan,
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
        parameters={"o2_batch_kind": "mocn"},
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.status == "FAIL"
    assert check.reason_code == "INVALID_ARTIFACT"
    assert "site_plan cannot be parsed" in check.explanation
    expected_field = (
        "delivery_batch" if missing_column == "mocn_batch" else missing_column
    )
    assert expected_field in check.evidence["error"]


@pytest.mark.parametrize(
    ("bad_region", "expected_reason"),
    (
        ("", "SITE_REGION_MISSING"),
        ("R9", "SITE_REGION_MISMATCH"),
    ),
)
def test_o2_bad_candidate_region_invalidates_only_that_site_and_not_the_anchor(
    bad_region: str,
    expected_reason: str,
) -> None:
    plan = plan_frame(
        (
            ("R1", "S1", "install", 1),
            ("R1", "S1", "dismantle", 3),
            ("R1", "S2", "install", 10),
            ("R1", "S2", "dismantle", 12),
        ),
        batch_kind="mocn",
    )
    plan.loc[
        (plan["site_name"] == "S2") & (plan["site_action"] == "install"),
        "region",
    ] = bad_region

    check = _score(_mocn_two_site_context(plan))

    valid = {
        row["site"]: row for row in check.evidence["valid_site_examples"]
    }
    invalid = _invalid_sites(check)
    # If S2 week 10 entered the anchor, S1 dismantle at week 3 would fail.
    assert set(valid) == {"S1"}
    assert set(invalid) == {"S2"}
    assert expected_reason in invalid["S2"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1


@pytest.mark.parametrize(
    ("bad_batch", "expected_reason"),
    (
        ("", "DELIVERY_BATCH_MISSING"),
        (0, "DELIVERY_BATCH_INVALID"),
        (1.5, "DELIVERY_BATCH_INVALID"),
        ("WRONG", "DELIVERY_BATCH_INVALID"),
        (2, "DELIVERY_BATCH_MISMATCH"),
    ),
)
def test_o2_bad_mocn_batch_invalidates_only_that_site_and_not_the_anchor(
    bad_batch: object,
    expected_reason: str,
) -> None:
    plan = plan_frame(
        (
            ("R1", "S1", "install", 1),
            ("R1", "S1", "dismantle", 3),
            ("R1", "S2", "install", 10),
            ("R1", "S2", "dismantle", 12),
        ),
        batch_kind="mocn",
    )
    plan["mocn_batch"] = plan["mocn_batch"].astype(object)
    plan.loc[
        (plan["site_name"] == "S2") & (plan["site_action"] == "install"),
        "mocn_batch",
    ] = bad_batch

    check = _score(_mocn_two_site_context(plan))

    valid = {
        row["site"]: row for row in check.evidence["valid_site_examples"]
    }
    invalid = _invalid_sites(check)
    assert set(valid) == {"S1"}
    assert set(invalid) == {"S2"}
    assert expected_reason in invalid["S2"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 1
    assert check.evidence["invalid_selected_sites"] == 1


def test_o2_rejects_final_material_missing_region() -> None:
    final = final_frame(
        (("R1", "S1", "install", "A", 1, "A", 1),)
    ).drop(columns=["region"])

    check = _score(_single_install_context(final=final))

    assert check.score == 0.0
    assert check.status == "FAIL"
    assert check.reason_code == "INVALID_ARTIFACT"
    assert "site_final_bom cannot be parsed" in check.explanation
    assert "region" in check.evidence["error"]


def test_o2_does_not_match_candidate_site_id_after_punctuation_removal() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S-1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S-1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
    )

    check = _score(context)

    assert check.evidence["N_target_sites"] == 1
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["non_scoring_plan_external_site_count"] == 1
    assert [
        row["site"]
        for row in check.evidence["non_scoring_plan_external_sites"]
    ] == [
        "S1"
    ]
    assert check.evidence["non_scoring_orphan_final_material_site_count"] == 1
    assert check.score == 0.0


def test_o2_does_not_match_final_bom_site_id_after_punctuation_removal() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S-1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S-1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S-1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
    )

    check = _score(context)

    invalid = _invalid_sites(check)
    assert set(invalid) == {"S-1"}
    assert "INSTALL_BOM_INVALID" in invalid["S-1"]["reasons"]
    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["invalid_selected_sites"] == 1
    assert check.evidence["non_scoring_orphan_final_material_site_count"] == 1
    assert check.score == 0.0


def test_o2_diagnoses_distinct_punctuated_plan_external_site_ids() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "AUTH", "install", "A", 1),)),
        batches=batch_frame((("R1", "AUTH", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S-1", "install", 1),
                ("R1", "S1", "install", 1),
            )
        ),
        final=final_frame(()),
    )

    check = _score(context)

    assert check.evidence["valid_delivery_sites"] == 0
    assert check.evidence["non_scoring_plan_external_site_count"] == 2
    assert {
        row["site"]
        for row in check.evidence["non_scoring_plan_external_sites"]
    } == {
        "S-1",
        "S1",
    }
    assert check.score == 0.0


def test_o2_keeps_distinct_punctuated_authoritative_site_ids() -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S-1", "install", "A", 1),
                ("R1", "S1", "install", "A", 1),
            )
        ),
        batches=batch_frame(
            (("R1", "S-1", "C1"), ("R1", "S1", "C1"))
        ),
        master=master_frame({"R1": {1: 999}}),
        plan=plan_frame(
            (
                ("R1", "S-1", "install", 1),
                ("R1", "S1", "install", 1),
            )
        ),
        final=final_frame(
            (
                ("R1", "S-1", "install", "A", 1, "A", 1),
                ("R1", "S1", "install", "A", 1, "A", 1),
            )
        ),
    )

    check = _score(context)

    assert check.evidence["N_target_sites"] == 2
    assert check.evidence["valid_delivery_sites"] == 2
    assert check.evidence["invalid_selected_sites"] == 0
    assert {row["site"] for row in check.evidence["valid_site_examples"]} == {
        "S-1",
        "S1",
    }
    assert check.score == 100.0


def test_o2_delivery_batches_accepts_real_chinese_mocn_column_with_strict_site_ids(
) -> None:
    authoritative_batches = pd.DataFrame(
        (
            {"region": "R1", "DU ID": "S-1", "MOCN开通批次": 1},
            {"region": "R1", "DU ID": "S1", "MOCN开通批次": 2},
        )
    )
    plan = pd.concat(
        (
            plan_frame(
                (("R1", "S-1", "install", 1),),
                batch_kind="mocn",
                delivery_batch=1,
            ),
            plan_frame(
                (("R1", "S1", "install", 1),),
                batch_kind="mocn",
                delivery_batch=2,
            ),
        ),
        ignore_index=True,
    )
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S-1", "install", "A", 1),
                ("R1", "S1", "install", "A", 1),
            )
        ),
        batches=authoritative_batches,
        master=master_frame({"R1": {1: 1}}),
        plan=plan,
        final=final_frame(
            (
                ("R1", "S-1", "install", "A", 1, "A", 1),
                ("R1", "S1", "install", "A", 1, "A", 1),
            )
        ),
        parameters={"o2_batch_kind": "mocn"},
    )

    check = _score(context)

    assert check.evidence["N_target_sites"] == 2
    assert check.evidence["valid_delivery_sites"] == 2
    assert {row["site"] for row in check.evidence["valid_site_examples"]} == {
        "S-1",
        "S1",
    }
    assert check.score == 100.0


def test_o2_install_only_authority_supports_a_not_applicable_interval() -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S1", "dismantle", "D", 1),
            )
        ),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 2),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "D", -1, "D", 2),
            )
        ),
        parameters={
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
            "o2_final_bom_quantity_mode": "signed-action",
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["authority_actions"] == ["install"]
    assert check.evidence["expected_source_actions"] == 2
    assert check.evidence["scoped_authority_actions"] == 1
    assert check.evidence["interval_contract"] == {"anchor": "not-applicable"}
    assert check.evidence["interval_anchor_scope"] == "not-applicable"
    assert check.evidence["out_of_scope_plan_action_row_count"] == 1
    assert check.evidence["out_of_scope_final_material_row_count"] == 1


def test_o2_install_only_contract_hard_gates_candidate_dismantle_rows() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 2),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S1", "dismantle", "A", 1, "A", 2),
            )
        ),
        parameters={
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
            "o2_install_only_contract": {"forbidden_actions": ["dismantle"]},
        },
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.reason_code == "INSTALL_ONLY_ACTION_VIOLATION"
    assert check.evidence["install_only_hard_gate_triggered"] is True
    assert check.evidence["forbidden_action_plan_row_count"] == 1
    assert check.evidence["forbidden_action_final_material_row_count"] == 1


def test_o2_fixed_seed_drop_removes_selected_site_and_all_of_its_actions() -> None:
    authority_sites = [f"S{index}" for index in range(1, 21)]
    # Batch-input order is S1..S20; Random(42).sample(..., 1) selects S4.
    retained = [site for site in authority_sites if site != "S4"]
    scope_rows = [
        ("R1", site, "install", "A", 1) for site in authority_sites
    ] + [("R1", "S4", "dismantle", "D", 1)]
    parameters = {
        "o2_batch_kind": "mocn",
        "o2_skip_rate": 0.05,
        "o2_skip_pool_scope": "batch",
        "o2_drop_selection_contract": {"mode": "seeded-random", "seed": 42},
        "o2_interval_contract": {"anchor": "not-applicable"},
        "o2_authority_actions": ["install"],
    }

    def build_context(selected: list[str], *, add_dropped_dismantle: bool = False):
        plan_rows = [("R1", site, "install", 1) for site in selected]
        final_rows = [
            ("R1", site, "install", "A", 1, "A", 1) for site in selected
        ]
        if add_dropped_dismantle:
            plan_rows.append(("R1", "S4", "dismantle", 2))
            final_rows.append(("R1", "S4", "dismantle", "D", 1, "D", 2))
        return o2_context(
            scope=scope_frame(scope_rows),
            batches=batch_frame(
                (("R1", site, index) for index, site in enumerate(authority_sites, 1)),
                batch_kind="mocn",
            ).assign(mocn_batch=1),
            master=master_frame({"R1": {1: 19}}),
            plan=plan_frame(
                plan_rows,
                batch_kind="mocn",
                delivery_batch=1,
            ),
            final=final_frame(final_rows),
            parameters=parameters,
        )

    exact = _score(build_context(retained))
    wrong = _score(
        build_context(
            [site for site in retained if site != "S5"] + ["S4"],
            add_dropped_dismantle=True,
        )
    )

    assert exact.score == 100.0, exact.evidence
    assert exact.evidence["drop_selection"]["dropped_site_keys"] == ["r1|S4"]
    assert exact.evidence["N_target_sites"] == 19
    assert wrong.reason_code == "DROP_IDENTITY_MISMATCH"
    assert wrong.evidence["forbidden_dropped_site_keys"] == ["r1|S4"]
    # Both install and dismantle rows are forbidden, but the identity penalty
    # remains site-based and is therefore counted once.
    assert wrong.evidence["dropped_plan_row_count"] == 2
    assert wrong.evidence["dropped_final_material_row_count"] == 2
    assert wrong.evidence["drop_identity_deviation"] == 1


def test_o2_install_only_authority_still_rejects_a_negative_install() -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S1", "dismantle", "D", 1),
            )
        ),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame(
            (
                ("R1", "S1", "install", 1),
                ("R1", "S1", "dismantle", 2),
            )
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", -1, "A", 1),
                ("R1", "S1", "dismantle", "D", -1, "D", 2),
            )
        ),
        parameters={
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
            "o2_final_bom_quantity_mode": "signed-action",
        },
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.evidence["site_validity_reason_counts"] == {
        "INSTALL_BOM_INVALID": 1
    }
    assert check.evidence["out_of_scope_plan_action_row_count"] == 1
    assert check.evidence["out_of_scope_final_material_row_count"] == 1


def test_o2_not_applicable_interval_rejects_dismantle_authority() -> None:
    context = _install_fixture(
        (("R1", "S1", "C1", 1),),
        {"R1": {1: 1}},
    )
    context.component.parameters["o2_authority_actions"] = [
        "install",
        "dismantle",
    ]
    context.component.parameters["o2_interval_contract"] = {
        "anchor": "not-applicable"
    }

    check = _score(context)

    assert check.status == "UNSCORABLE"
    assert check.reason_code == "EVALUATOR_ERROR"
    assert "requires install-only authority" in check.evidence["error"]


def test_o2_completion_by_deadline_does_not_penalize_in_window_redistribution(
) -> None:
    scope = scope_frame(
        (
            ("R1", "S1", "install", "A", 1),
            ("R1", "S2", "install", "A", 1),
        )
    )
    batches = batch_frame(
        (("R1", "S1", "C1"), ("R1", "S2", "C1"))
    )
    plan = plan_frame(
        (("R1", "S1", "install", 1), ("R1", "S2", "install", 1))
    )
    final = final_frame(
        (
            ("R1", "S1", "install", "A", 1, "A", 1),
            ("R1", "S2", "install", "A", 1, "A", 1),
        )
    )
    # Month 1 can admit both sites.  Completion mode may therefore move the
    # second site inside the covered window without violating the hard cap.
    master = master_frame({"R1": {1: 2, 2: 1}})

    distribution = _score(
        o2_context(
            scope=scope,
            batches=batches,
            master=master,
            plan=plan,
            final=final,
        )
    )
    completion = _score(
        o2_context(
            scope=scope,
            batches=batches,
            master=master,
            plan=plan,
            final=final,
            parameters={
                "o2_target_curve_mode": "completion-by-deadline",
                "o2_monthly_capacity_mode": "hard-limit",
            },
        )
    )

    assert distribution.score == 50.0
    assert completion.score == 100.0
    assert completion.evidence["target_curve_mode"] == "completion-by-deadline"
    assert completion.evidence["target_curve_covered_periods"] == {
        "r1": ["2027-01", "2027-02"]
    }
    assert completion.evidence["completion_buckets"] == {"r1": "2027-02"}
    assert completion.evidence["monthly_capacity_gate"]["grid"][0][
        "capacity_limit"
    ] == 2
    assert completion.evidence["scaled_target_grid"] == [
        {
            "group": "r1",
            "month": 2,
            "year_month": "2027-02",
            "target_B": 2,
            "valid_deliveries_A": 2,
            "absolute_deviation": 0,
        }
    ]


def test_o2_monthly_capacity_overflow_is_invalid_and_counted_once() -> None:
    context = o2_context(
        scope=scope_frame(
            (
                ("R1", "S1", "install", "A", 1),
                ("R1", "S2", "install", "A", 1),
            )
        ),
        batches=batch_frame(
            (("R1", "S1", "C1"), ("R1", "S2", "C1"))
        ),
        master=master_frame({"R1": {1: 1, 2: 1}}),
        plan=plan_frame(
            (("R1", "S1", "install", 1), ("R1", "S2", "install", 1))
        ),
        final=final_frame(
            (
                ("R1", "S1", "install", "A", 1, "A", 1),
                ("R1", "S2", "install", "A", 1, "A", 1),
            )
        ),
        parameters={
            "o2_target_curve_mode": "completion-by-deadline",
            "o2_monthly_capacity_mode": "hard-limit",
        },
    )

    check = _score(context)

    assert check.score == 50.0
    assert check.evidence["count_gap_units"] == 1
    assert check.evidence["redistribution_units"] == 0
    assert check.evidence["total_loss_units"] == 1
    assert check.evidence["site_validity_reason_counts"] == {
        "MONTHLY_CAPACITY_EXCEEDED": 1
    }
    assert check.evidence["monthly_capacity_gate"]["exceeded_site_keys"] == [
        "r1|S2"
    ]


def test_o2_completion_by_deadline_rejects_an_uncovered_install_period() -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1, 2: 1}}),
        plan=plan_frame((("R1", "S1", "install", 9),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 9),)),
        parameters={"o2_target_curve_mode": "completion-by-deadline"},
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.evidence["site_validity_reason_counts"] == {
        "INSTALL_OUTSIDE_DEADLINE": 1
    }
    assert check.evidence["invalid_site_examples"][0]["submitted_period"] == 202703


@pytest.mark.parametrize(
    ("submitted_source", "allowed", "expected_score"),
    (
        (" new ", ["NEW", "REUSE"], 100.0),
        ("reuse", ["NEW"], 0.0),
        ("", ["NEW"], 0.0),
    ),
)
def test_o2_material_source_contract_is_action_local_and_normalized(
    submitted_source: str,
    allowed: list[str],
    expected_score: float,
) -> None:
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 1),))
    final["material_source"] = submitted_source
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final,
        parameters={"o2_material_source_contract": {"install": allowed}},
    )

    check = _score(context)

    assert check.score == expected_score
    assert check.evidence["material_source_contract"] == {"install": allowed}
    if expected_score == 100.0:
        assert check.evidence["invalid_material_source_row_count"] == 0
    else:
        expected_reason = (
            "INVALID_MATERIAL_SOURCE"
            if submitted_source.strip()
            else "MISSING_MATERIAL_SOURCE"
        )
        assert check.evidence["invalid_material_source_row_count"] == int(
            bool(submitted_source.strip())
        )
        assert check.evidence["missing_material_source_row_count"] == int(
            not submitted_source.strip()
        )
        assert check.evidence["material_action_failure_reason_counts"][
            expected_reason
        ] == 1
        assert "INSTALL_BOM_INVALID" in check.evidence[
            "invalid_site_examples"
        ][0]["reasons"]


def test_o2_material_source_missing_diagnostic_does_not_invalidate_site(
) -> None:
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 1),))
    final["material_source"] = ""
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final,
        parameters={
            "o2_material_source_contract": {"install": ["NEW", "REUSE"]},
            "o2_material_source_missing_effect": "diagnostic",
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["material_source_missing_effect"] == "diagnostic"
    assert check.evidence["missing_material_source_row_count"] == 1
    assert check.evidence["missing_material_source_examples"] == [
        {"row": 2, "action": "install"}
    ]
    assert check.evidence["invalid_material_source_row_count"] == 0
    assert check.evidence["invalid_material_source_examples"] == []
    assert check.evidence["material_action_failure_reason_counts"] == {}
    assert check.evidence["strict_bom_invalid_rows"] == 0
    assert check.evidence["valid_delivery_sites"] == 1


def test_o2_missing_diagnostic_does_not_relax_nonempty_invalid_source() -> None:
    final = final_frame((("R1", "S1", "install", "A", 1, "A", 1),))
    final["material_source"] = "OTHER"
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final,
        parameters={
            "o2_material_source_contract": {"install": ["NEW", "REUSE"]},
            "o2_material_source_missing_effect": "diagnostic",
        },
    )

    check = _score(context)

    assert check.score == 0.0
    assert check.evidence["missing_material_source_row_count"] == 0
    assert check.evidence["invalid_material_source_row_count"] == 1
    assert check.evidence["material_action_failure_reason_counts"] == {
        "INVALID_FINAL_ROW": 1,
        "INVALID_MATERIAL_SOURCE": 1,
        "MATERIAL_COVERAGE_GAP": 1,
    }


def test_o2_publishes_compact_final_material_adapter_diagnostics_without_penalty(
) -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
    )
    final_material = context.artifacts.get("final_material")
    assert final_material is not None
    final_material.validation_issues = (
        {
            "code": "EXACT_COLUMNS_MISMATCH",
            "message": "source columns do not match the Prompt order exactly",
            "expected": ["site_name", "cluster_id", "material_source"],
            "actual": ["site_name"],
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["final_material_adapter_validation"] == {
        "role": "final_material",
        "issue_count": 1,
        "score_effect": "none",
        "issues": [
            {
                "code": "EXACT_COLUMNS_MISMATCH",
                "message": "source columns do not match the Prompt order exactly",
                "missing_columns": ["cluster_id", "material_source"],
                "unexpected_columns": [],
            }
        ],
    }


def test_o2_publishes_compact_site_plan_adapter_diagnostics_without_penalty(
) -> None:
    context = o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan_frame((("R1", "S1", "install", 1),)),
        final=final_frame((("R1", "S1", "install", "A", 1, "A", 1),)),
    )
    site_plan = context.artifacts.get("site_plan")
    assert site_plan is not None
    site_plan.validation_issues = (
        {
            "code": "EXACT_COLUMNS_MISMATCH",
            "message": "source columns do not match the Prompt order exactly",
            "expected": [
                "site_name",
                "site_action",
                "mos_weekly_plan",
                "week_num",
                "region",
            ],
            "actual": [
                "site_name",
                "site_action",
                "mos_weekly_plan",
                "week_num",
                "region",
                "site_count",
            ],
        },
    )

    check = _score(context)

    assert check.score == 100.0
    assert check.evidence["site_plan_adapter_validation"] == {
        "role": "site_plan",
        "issue_count": 1,
        "score_effect": "none",
        "issues": [
            {
                "code": "EXACT_COLUMNS_MISMATCH",
                "message": "source columns do not match the Prompt order exactly",
                "missing_columns": [],
                "unexpected_columns": ["site_count"],
            }
        ],
    }


def _schedule_week_identity_context(
    *,
    plan_label: str,
    final_label: str,
    plan_week: int = 1,
    final_week: int = 1,
):
    plan = plan_frame((("R1", "S1", "install", plan_week),))
    plan["week_num"] = plan_week
    plan["mos_weekly_plan"] = plan_label
    final = final_frame(
        (("R1", "S1", "install", "A", 1, "A", final_week),)
    )
    final["install_wk_label"] = final_label
    return o2_context(
        scope=scope_frame((("R1", "S1", "install", "A", 1),)),
        batches=batch_frame((("R1", "S1", "C1"),)),
        master=master_frame({"R1": {1: 1}}),
        plan=plan,
        final=final,
        parameters={
            "o2_delivery_month_source": "schedule-week",
            "o2_week_to_month": "four-week-project",
            "o2_project_start_month": 1,
            "o2_authority_actions": ["install"],
            "o2_interval_contract": {"anchor": "not-applicable"},
            "o2_site_plan_required_fields": [
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
            ],
        },
    )


@pytest.mark.parametrize(
    ("plan_label", "final_label"),
    (
        ("WK1", "WK1"),
        ("2027WK1", "2027WK1"),
        ("2027WK1", "WK1"),
        ("WK1", "2027WK1"),
    ),
)
def test_o2_schedule_week_accepts_short_or_correct_explicit_year(
    plan_label: str,
    final_label: str,
) -> None:
    check = _score(
        _schedule_week_identity_context(
            plan_label=plan_label,
            final_label=final_label,
        )
    )

    assert check.score == 100.0
    assert check.evidence["valid_delivery_sites"] == 1


def test_o2_schedule_week_rejects_wrong_explicit_year_in_site_plan() -> None:
    check = _score(
        _schedule_week_identity_context(
            plan_label="2026WK1",
            final_label="2027WK1",
        )
    )

    assert check.score == 0.0
    assert "INSTALL_WEEK_YEAR_MISMATCH" in check.evidence[
        "invalid_site_examples"
    ][0]["reasons"]


def test_o2_schedule_week_rejects_wrong_explicit_year_in_final_material() -> None:
    check = _score(
        _schedule_week_identity_context(
            plan_label="2027WK1",
            final_label="2026WK1",
        )
    )

    assert check.score == 0.0
    assert "INSTALL_BOM_INVALID" in check.evidence[
        "invalid_site_examples"
    ][0]["reasons"]
    assert check.evidence["material_action_failure_reason_counts"][
        "INVALID_FINAL_ROW"
    ] == 1


def test_o2_schedule_week_rejects_label_week_num_conflict_in_site_plan() -> None:
    check = _score(
        _schedule_week_identity_context(
            plan_label="2027WK2",
            final_label="2027WK1",
        )
    )

    assert check.score == 0.0
    assert "INSTALL_WEEK_CONFLICT" in check.evidence[
        "invalid_site_examples"
    ][0]["reasons"]


def test_o2_schedule_week_rejects_current_action_week_conflict_in_final_material(
) -> None:
    check = _score(
        _schedule_week_identity_context(
            plan_label="2027WK1",
            final_label="2027WK2",
            final_week=1,
        )
    )

    assert check.score == 0.0
    assert "INSTALL_BOM_INVALID" in check.evidence[
        "invalid_site_examples"
    ][0]["reasons"]
    assert check.evidence["material_action_failure_reason_counts"][
        "INVALID_FINAL_ROW"
    ] == 1
