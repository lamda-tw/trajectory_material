from simulation.ei.rules.ei_standard.reuse.r3 import score_r3

from .support import context


def test_r3_owns_candidate_artifact_failure() -> None:
    result = score_r3(context("R3"))
    assert result.check_id == "reuse-accounting.R3"
    assert result.reason_code == "CANDIDATE_ARTIFACT_MISSING"
