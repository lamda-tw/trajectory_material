"""Report command orchestration with report IDs independent from score IDs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from simulation.app.contracts import SelectionPlan
from simulation.app.persistence import allocate_report_directory, atomic_write_json
from simulation.app.progress import ProgressCallback, emit
from simulation.ei.reports import build_report, validate_report_runtime


def report_selection(
    plan: SelectionPlan,
    *,
    repository_root: Path,
    score_id: str = "latest",
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not plan.runs:
        raise ValueError("selection matched no runs")
    validate_report_runtime()
    report_id, report_dir = allocate_report_directory(
        repository_root / "eval_reports"
    )
    emit(
        progress,
        "report_allocated",
        report_id=report_id,
        report_dir=report_dir.as_posix(),
        score_id=score_id,
    )
    try:
        artifacts = build_report(
            plan,
            report_id=report_id,
            report_dir=report_dir,
            score_id=score_id,
            progress=progress,
        )
    except Exception as exc:
        failure_path = report_dir / "report_failure.json"
        atomic_write_json(
            failure_path,
            {
                "schema_version": "ei-report-failure.v1",
                "report_id": report_id,
                "score_id": score_id,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        emit(
            progress,
            "report_failed",
            report_id=report_id,
            error=f"{type(exc).__name__}: {exc}",
            failure_path=failure_path.as_posix(),
        )
        raise
    return {
        "report_id": report_id,
        "score_id": score_id,
        "report_dir": report_dir.as_posix(),
        **{key: value.as_posix() for key, value in artifacts.items()},
    }
