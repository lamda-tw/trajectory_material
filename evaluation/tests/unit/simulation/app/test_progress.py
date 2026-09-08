from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from threading import Barrier, Lock
from time import sleep
from unittest.mock import patch

import pytest

from simulation.app.commands.score import score_batch
from simulation.app.contracts import RunRecord, SelectionGroup, SelectionPlan
from simulation.cli import ConsoleProgress


class TtyBuffer(StringIO):
    def isatty(self) -> bool:
        return True


def test_score_batch_emits_all_progress_stages_and_artifact_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "EI-Q-v1.2_codex_gpt56_noskill_0814A"
    run_dir.mkdir()
    record = RunRecord(
        run_dir,
        run_dir.name,
        "EI",
        "EI-Q-v1.2",
        "gpt56",
        "codex",
        "noskill",
        ("2026-08-14", "0814A", ""),
        {},
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )
    events: list[tuple[str, object]] = []
    run_result = {
        "run": record.run_name,
        "question": record.question,
        "score_id": "ignored-by-test",
        "status": "SCORED",
        "scores": {
            "effectiveness.o2": 70,
            "key.raw": 84,
            "key.discrete": 60,
            "key.piecewise": 68,
            "all.raw": 80,
        },
        "score_path": (run_dir / "scores" / "score.json").as_posix(),
    }

    with (
        patch("simulation.app.commands.score.prepare_question", return_value=object()),
        patch("simulation.app.commands.score.score_one", return_value=run_result),
    ):
        result = score_batch(
            plan,
            repository_root=tmp_path,
            progress=lambda event, details: events.append((event, details)),
        )

    assert [event for event, _details in events] == [
        "score_batch_allocated",
        "score_run_started",
        "score_run_completed",
        "score_batch_persisted",
    ]
    assert Path(result["results"]).is_file()
    assert result["completed_count"] == 1
    assert result["requested_jobs"] == 6
    assert result["jobs"] == 1
    assert result["question_count"] == 1
    assert result["job_unit"] == "question"


def test_score_batch_does_not_count_not_applicable_aggregate_as_an_error(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "EI-Q-v1.2_codex_gpt56_noskill_0814A"
    run_dir.mkdir()
    record = RunRecord(
        run_dir,
        run_dir.name,
        "EI",
        "EI-Q-v1.2",
        "gpt56",
        "codex",
        "noskill",
        ("2026-08-14", "0814A", ""),
        {},
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )
    run_result = {
        "run": record.run_name,
        "question": record.question,
        "score_id": "ignored-by-test",
        "status": "SCORED",
        "scores": {
            "effectiveness.o2": 73,
            "key.raw": 100,
            "key.discrete": 90,
            "key.piecewise": 100,
            "all.raw": None,
        },
        "score_path": (run_dir / "scores" / "score.json").as_posix(),
    }

    with (
        patch("simulation.app.commands.score.prepare_question", return_value=object()),
        patch("simulation.app.commands.score.score_one", return_value=run_result),
    ):
        result = score_batch(plan, repository_root=tmp_path)

    assert result["completed_count"] == 1
    assert result["failure_count"] == 0
    assert result["error_result_count"] == 0


def test_score_batch_runs_concurrently_and_keeps_selection_order(tmp_path: Path) -> None:
    records = []
    for index in range(4):
        run_dir = tmp_path / f"EI-Q{index}-v1.2_codex_gpt56_noskill_0814A"
        run_dir.mkdir()
        records.append(
            RunRecord(
                run_dir,
                run_dir.name,
                "EI",
                f"EI-Q{index}-v1.2",
                "gpt56",
                "codex",
                "noskill",
                ("2026-08-14", "0814A", ""),
                {},
            )
        )
    plan = SelectionPlan(
        "latest",
        tuple(SelectionGroup(record.repeat_key, (record,)) for record in records),
        4,
        4,
    )
    first_wave = {record.run_name for record in records[:3]}
    barrier = Barrier(3, timeout=2)

    def fake_score_one(record: RunRecord, **kwargs: object) -> dict[str, object]:
        if record.run_name in first_wave:
            barrier.wait()
        return {
            "run": record.run_name,
            "question": record.question,
            "score_id": kwargs["score_id"],
            "status": "SCORED",
            "scores": {
                "effectiveness.o2": 70,
                "key.raw": 84,
                "key.discrete": 60,
                "key.piecewise": 68,
                "all.raw": 80,
            },
            "score_path": (record.run_dir / "scores" / "score.json").as_posix(),
        }

    with (
        patch("simulation.app.commands.score.prepare_question", return_value=object()),
        patch("simulation.app.commands.score.score_one", side_effect=fake_score_one),
    ):
        result = score_batch(plan, repository_root=tmp_path, jobs=3)

    assert result["jobs"] == 3
    assert result["question_count"] == 4
    assert result["failure_count"] == 0
    assert [value["run"] for value in result["runs"]] == [
        record.run_name for record in records
    ]


def test_score_batch_prepares_once_and_serializes_runs_of_one_question(
    tmp_path: Path,
) -> None:
    records = []
    for index in range(4):
        run_dir = tmp_path / f"EI-Q-v1.2_codex_model{index}_noskill_0814A"
        run_dir.mkdir()
        records.append(
            RunRecord(
                run_dir,
                run_dir.name,
                "EI",
                "EI-Q-v1.2",
                f"model{index}",
                "codex",
                "noskill",
                ("2026-08-14", "0814A", ""),
                {},
            )
        )
    plan = SelectionPlan(
        "latest",
        tuple(SelectionGroup(record.repeat_key, (record,)) for record in records),
        4,
        4,
    )
    active = 0
    maximum_active = 0
    active_lock = Lock()

    def fake_score_one(record: RunRecord, **kwargs: object) -> dict[str, object]:
        nonlocal active, maximum_active
        with active_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        sleep(0.01)
        with active_lock:
            active -= 1
        return {
            "run": record.run_name,
            "question": record.question,
            "score_id": kwargs["score_id"],
            "status": "SCORED",
            "scores": {
                "effectiveness.o2": 70,
                "key.raw": 84,
                "key.discrete": 60,
                "key.piecewise": 68,
                "all.raw": 80,
            },
            "score_path": (record.run_dir / "scores" / "score.json").as_posix(),
        }

    with (
        patch("simulation.app.commands.score.prepare_question", return_value=object()) as prepare,
        patch("simulation.app.commands.score.score_one", side_effect=fake_score_one),
    ):
        result = score_batch(plan, repository_root=tmp_path, jobs=3)

    assert prepare.call_count == 1
    assert result["jobs"] == 1
    assert result["question_count"] == 1
    assert maximum_active == 1
    assert [value["run"] for value in result["runs"]] == [
        record.run_name for record in records
    ]


@pytest.mark.parametrize("jobs", [0, 25])
def test_score_batch_rejects_jobs_outside_supported_range(
    tmp_path: Path,
    jobs: int,
) -> None:
    run_dir = tmp_path / "EI-Q-v1.2_codex_gpt56_noskill_0814A"
    run_dir.mkdir()
    record = RunRecord(
        run_dir,
        run_dir.name,
        "EI",
        "EI-Q-v1.2",
        "gpt56",
        "codex",
        "noskill",
        ("2026-08-14", "0814A", ""),
        {},
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )
    with pytest.raises(ValueError, match="between 1 and 24"):
        score_batch(plan, repository_root=tmp_path, jobs=jobs)


def test_console_uses_one_dynamic_bar_with_latest_result_in_a_tty() -> None:
    stream = TtyBuffer()
    scores = {
        "effectiveness.o2": 70,
        "key.raw": 84,
        "key.discrete": 60,
        "key.piecewise": 68,
        "all.raw": 80,
    }
    with redirect_stderr(stream):
        progress = ConsoleProgress()
        progress(
            "score_batch_allocated",
            {
                "score_id": "20260814120000",
                "jobs": 2,
                "total": 2,
                "selection_path": "selection.json",
            },
        )
        progress(
            "score_run_completed",
            {
                "index": 2,
                "completed_count": 1,
                "total": 2,
                "run": "EI-Q2-v1.2_codex_gpt56_noskill_0814A",
                "status": "SCORED",
                "scores": scores,
                "score_path": "score.json",
            },
        )
        progress(
            "score_batch_persisted",
            {
                "score_id": "20260814120000",
                "completed_count": 2,
                "failure_count": 0,
                "error_result_count": 0,
                "results_path": "results.json",
            },
        )

    output = stream.getvalue()
    assert "\r评分 [" in output
    assert "1/2  50.0%" in output
    assert "最新完成：EI-Q2-v1.2_codex_gpt56_noskill_0814A" in output
    assert "O2=70.00 | 分段=68.00 | 全项=80.00" in output
    assert "批次结果=results.json" in output
