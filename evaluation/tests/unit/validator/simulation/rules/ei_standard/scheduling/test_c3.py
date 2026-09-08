from simulation.ei.rules.ei_standard.scheduling.c3 import score_c3

from .support import context, evidence


def test_c3_scores_capacity_excess_directly() -> None:
    result = score_c3(context("C3"), evidence())
    assert result.check_id == "scheduling.C3"
    assert result.score == 50.0
