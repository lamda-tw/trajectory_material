from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.app.commands.score import score_one
from simulation.app.contracts import RunRecord, ScorePackage
from simulation.app.persistence import ScoreResolutionError, ScoreStore, allocate_score_id


def _record(tmp_path: Path) -> RunRecord:
    run = tmp_path / "run"
    run.mkdir()
    return RunRecord(
        run, "run", "EI", "EI-Q-v1.2", "gpt56", "codex", "noskill",
        ("2026-08-14", "0814A", ""), {},
    )


def test_score_id_is_precise_time_and_path_traversal_is_rejected(tmp_path: Path) -> None:
    record = _record(tmp_path)
    score_id = allocate_score_id((record,))
    assert len(score_id) == 14
    assert score_id.isdigit()
    with pytest.raises(ScoreResolutionError, match="YYYYMMDDHHMMSS"):
        ScoreStore().resolve(record, "../../outside")


def _package(record: RunRecord, score_id: str, created_at: str) -> ScorePackage:
    return ScorePackage(
        "simulation.ei",
        record.question,
        "SCORED",
        (),
        {
            "score_id": score_id,
            "created_at": created_at,
            "run": record.as_dict(),
            "sentinel": "preserved",
        },
    )


def test_score_store_preserves_a_complete_payload_without_backfilling(
    tmp_path: Path,
) -> None:
    record = _record(tmp_path)
    score_id = "20260820120000"
    created_at = "2026-08-20T12:00:00+08:00"
    package = _package(record, score_id, created_at)

    ScoreStore().write(
        record,
        score_id,
        package,
        created_at=created_at,
    )

    assert ScoreStore().read(record, score_id) == package.payload


@pytest.mark.parametrize("missing", ("score_id", "created_at", "run"))
def test_score_store_rejects_partial_score_identity(
    tmp_path: Path,
    missing: str,
) -> None:
    record = _record(tmp_path)
    score_id = "20260820120000"
    created_at = "2026-08-20T12:00:00+08:00"
    package = _package(record, score_id, created_at)
    del package.payload[missing]

    with pytest.raises(ValueError, match="persistence identity mismatch"):
        ScoreStore().write(
            record,
            score_id,
            package,
            created_at=created_at,
        )


def test_score_one_gives_provider_the_final_persistence_identity(
    tmp_path: Path,
) -> None:
    record = _record(tmp_path)
    score_id = "20260820120000"

    def fake_score_record(
        current: RunRecord,
        **kwargs: object,
    ) -> ScorePackage:
        assert kwargs["score_id"] == score_id
        created_at = kwargs["created_at"]
        assert isinstance(created_at, str) and created_at
        return _package(current, score_id, created_at)

    with patch(
        "simulation.app.commands.score.score_record",
        side_effect=fake_score_record,
    ):
        result = score_one(
            record,
            repository_root=tmp_path,
            score_id=score_id,
        )

    payload = ScoreStore().read(record, score_id)
    assert payload["score_id"] == result["score_id"] == score_id
    assert payload["run"] == record.as_dict()
