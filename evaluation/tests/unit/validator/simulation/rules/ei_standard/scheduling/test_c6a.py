from simulation.ei.rules.ei_standard.scheduling.c6a import score_c6a

from .support import context, evidence


def test_c6a_scores_batch_lag_directly() -> None:
    result = score_c6a(
        context(
            "C6a",
            parameters={
                "batch_kind": "cluster",
                "c6a_contract": {"relation": "exact", "lag_weeks": 2},
            },
        ),
        evidence(),
    )
    assert result.check_id == "scheduling.C6a"
    assert result.status == "PASS"
