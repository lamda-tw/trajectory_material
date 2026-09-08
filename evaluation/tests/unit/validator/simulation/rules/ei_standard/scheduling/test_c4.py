from simulation.ei.rules.ei_standard.scheduling.c4 import score_c4

from .support import context, evidence


def test_c4_scores_authoritative_month_membership_directly() -> None:
    result = score_c4(context("C4"), evidence())
    assert result.check_id == "scheduling.C4"
    assert result.score == 50.0
