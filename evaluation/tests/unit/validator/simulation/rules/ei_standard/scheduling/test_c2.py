from simulation.ei.rules.ei_standard.scheduling.c2 import score_c2

from .support import context, evidence, seeded_drop_evidence


def test_c2_scores_action_union_directly() -> None:
    value = evidence()
    value.plan.drop(value.plan.index[[1, 2]], inplace=True)
    result = score_c2(context("C2"), value)
    assert result.check_id == "scheduling.C2"
    assert result.score == 50.0


def test_c2_removes_all_actions_for_a_dropped_install_site() -> None:
    value = seeded_drop_evidence()

    result = score_c2(context("C2", parameters=value.parameters), value)

    assert result.score == 100.0
    assert result.evidence["pre_drop_expected"] == 40
    assert result.evidence["dropped_expected_actions"] == 2
