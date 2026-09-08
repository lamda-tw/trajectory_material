from simulation.ei.rules.ei_standard.scheduling.o1 import score_o1

from .support import context


def test_o1_owns_its_missing_artifact_state() -> None:
    result = score_o1(context("O1"))
    assert result.check_id == "scheduling.O1"
    assert result.reason_code == "MISSING_ARTIFACT"
