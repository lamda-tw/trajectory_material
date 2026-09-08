from simulation.ei.rules.ei_standard.scheduling.c1 import score_c1

from .support import context, evidence, seeded_drop_evidence


def test_c1_scores_required_site_recall_directly() -> None:
    result = score_c1(
        context("C1"),
        evidence(actual_sites={"r|s1"}),
    )
    assert result.check_id == "scheduling.C1"
    assert result.score == 50.0


def test_c1_uses_post_drop_site_authority() -> None:
    value = seeded_drop_evidence()

    result = score_c1(context("C1", parameters=value.parameters), value)

    assert result.score == 100.0
    assert result.evidence["pre_drop_expected"] == 20
    assert result.evidence["dropped_expected_sites"] == 1
