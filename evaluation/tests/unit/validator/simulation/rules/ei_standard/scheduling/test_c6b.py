from simulation.ei.rules.ei_standard.scheduling.c6b import score_c6b

from .support import context, evidence


def test_c6b_scores_authoritative_batch_order_directly() -> None:
    result = score_c6b(
        context(
            "C6b",
            parameters={
                "batch_kind": "cluster",
                "c6b_contract": {
                    "event": "first_install_week",
                    "order_mode": "numeric_ascending",
                    "scope": "region",
                },
            },
        ),
        evidence(),
    )
    assert result.check_id == "scheduling.C6b"
    assert result.status == "PASS"
