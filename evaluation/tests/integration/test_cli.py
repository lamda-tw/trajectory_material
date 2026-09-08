from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from simulation.app.contracts import RunRecord, SelectionGroup, SelectionPlan
from simulation.cli import main


def _record() -> RunRecord:
    return RunRecord(
        Path("run"), "run", "EI", "EI-Q-v1.2", "gpt56", "codex", "noskill",
        ("2026-08-14", "0814A", ""), {},
    )


def test_score_run_needs_only_run_dir_and_echoes_all_five_metrics() -> None:
    record = _record()
    result = {
        "run": "run",
        "question": record.question,
        "score_id": "20260814120000",
        "status": "SCORED",
        "scores": {
            "effectiveness.o2": 70,
            "key.raw": 84,
            "key.discrete": 60,
            "key.piecewise": 68,
            "all.raw": 80,
        },
        "score_path": "run/scores/20260814120000/score.json",
    }
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli.discover_questions", return_value=(record.question,)),
        patch("simulation.cli.record_from_run", return_value=record) as normalize,
        patch("simulation.cli.score_one", return_value=result) as score,
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        assert main(["score", "run", "run"]) == 0
    normalize.assert_called_once_with(Path("run"), question_ids=(record.question,))
    score.assert_called_once_with(record, repository_root=Path("repo"))
    assert set(json.loads(stdout.getvalue())["scores"]) == set(result["scores"])
    progress = stderr.getvalue()
    assert "[评分]" in progress
    assert "[完成] 单运行评分完成" in progress
    assert "O2成效=70.00" in progress
    assert "关键·分段=68.00" in progress
    assert "分数文件=run/scores/20260814120000/score.json" in progress


def test_batch_preview_uses_shared_selection_without_writing() -> None:
    record = _record()
    plan = SelectionPlan(
        "latest", (SelectionGroup(record.repeat_key, (record,)),), 1, 1
    )
    stdout = StringIO()
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli._selection", return_value=plan),
        patch("simulation.cli.score_batch") as score,
        redirect_stdout(stdout),
    ):
        assert main(["score", "batch", "--task", "EI", "--preview"]) == 0
    score.assert_not_called()
    assert json.loads(stdout.getvalue())["selected_run_count"] == 1


def test_batch_uses_six_workers_by_default_and_reports_it() -> None:
    record = _record()
    plan = SelectionPlan(
        "latest", (SelectionGroup(record.repeat_key, (record,)),), 1, 1
    )
    result = {
        "score_id": "20260814120000",
        "selected_run_count": 1,
        "jobs": 1,
        "completed_count": 1,
        "failure_count": 0,
        "error_result_count": 0,
        "runs": [],
        "failures": [],
    }
    stderr = StringIO()
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli._selection", return_value=plan),
        patch("simulation.cli.score_batch", return_value=result) as score,
        redirect_stdout(StringIO()),
        redirect_stderr(stderr),
    ):
        assert main(["score", "batch", "--task", "EI"]) == 0
    assert score.call_args.kwargs["jobs"] == 6
    assert "请求并行度=6" in stderr.getvalue()


def test_report_can_read_one_explicit_score_version_from_a_new_selection() -> None:
    record = _record()
    plan = SelectionPlan(
        "average", (SelectionGroup(record.repeat_key, (record,)),), 1, 1
    )
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli._selection", return_value=plan),
        patch(
            "simulation.cli.report_selection",
            return_value={"report_id": "0814A", "score_id": "20260814120000"},
        ) as report,
        redirect_stdout(StringIO()),
    ):
        assert main(["report", "--score-id", "20260814120000"]) == 0
    report.assert_called_once_with(
        plan,
        repository_root=Path("repo"),
        score_id="20260814120000",
        progress=ANY,
    )


def test_quiet_suppresses_human_progress_but_keeps_json() -> None:
    record = _record()
    result = {
        "run": "run",
        "question": record.question,
        "score_id": "20260814120000",
        "status": "SCORED",
        "scores": {
            "effectiveness.o2": 70,
            "key.raw": 84,
            "key.discrete": 60,
            "key.piecewise": 68,
            "all.raw": 80,
        },
        "score_path": "run/scores/20260814120000/score.json",
    }
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli.discover_questions", return_value=(record.question,)),
        patch("simulation.cli.record_from_run", return_value=record),
        patch("simulation.cli.score_one", return_value=result),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        assert main(["score", "run", "run", "--quiet"]) == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["score_id"] == "20260814120000"


def test_command_failure_has_a_human_readable_status() -> None:
    stderr = StringIO()
    with (
        patch("simulation.cli.repository_root", return_value=Path("repo")),
        patch("simulation.cli.discover_questions", return_value=()),
        patch(
            "simulation.cli.record_from_run",
            side_effect=ValueError("cannot determine question"),
        ),
        redirect_stderr(stderr),
    ):
        assert main(["score", "run", "bad-run"]) == 2
    output = stderr.getvalue()
    assert "[评分] 正在识别" in output
    assert "[失败] ValueError: cannot determine question" in output
    assert '"error": "ValueError: cannot determine question"' in output


def test_cli_rejects_jobs_above_the_supported_maximum() -> None:
    stderr = StringIO()
    with redirect_stderr(stderr), pytest.raises(SystemExit) as exc_info:
        main(["score", "batch", "--task", "EI", "--jobs", "25"])
    assert exc_info.value.code == 2
    assert "jobs must be between 1 and 24" in stderr.getvalue()
