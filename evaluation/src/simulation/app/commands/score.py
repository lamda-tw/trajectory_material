"""Score command orchestration; all EI decisions stay in the provider."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from simulation.app.contracts import RunRecord, SelectionPlan
from simulation.app.persistence import (
    ScoreStore,
    allocate_score_id,
    atomic_write_json,
    write_selection_snapshot,
)
from simulation.app.progress import ProgressCallback, emit
from simulation.ei.provider import PreparedQuestion, prepare_question, score_record


DEFAULT_SCORE_JOBS = 6
MAX_SCORE_JOBS = 24


def score_one(
    record: RunRecord,
    *,
    repository_root: Path,
    score_id: str | None = None,
    store: ScoreStore | None = None,
    prepared_question: PreparedQuestion | None = None,
) -> dict[str, Any]:
    score_store = store or ScoreStore()
    identifier = score_id or allocate_score_id((record,))
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    package = score_record(
        record,
        repository_root=repository_root,
        score_id=identifier,
        created_at=created_at,
        prepared_question=prepared_question,
    )
    score_path = score_store.write(
        record, identifier, package, created_at=created_at
    )
    return {
        "run": record.run_name,
        "question": package.question,
        "score_id": identifier,
        "status": package.status,
        "scores": dict(package.totals),
        "score_path": score_path.as_posix(),
    }


def score_batch(
    plan: SelectionPlan,
    *,
    repository_root: Path,
    progress: ProgressCallback | None = None,
    jobs: int = DEFAULT_SCORE_JOBS,
) -> dict[str, Any]:
    if not plan.runs:
        raise ValueError("selection matched no runs")
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 1 <= jobs <= MAX_SCORE_JOBS:
        raise ValueError(f"jobs must be an integer between 1 and {MAX_SCORE_JOBS}")
    indexed_groups: dict[str, list[tuple[int, RunRecord]]] = {}
    for index, record in enumerate(plan.runs, start=1):
        indexed_groups.setdefault(record.question, []).append((index, record))
    worker_count = min(jobs, len(indexed_groups))
    score_id = allocate_score_id(
        plan.runs,
        batch_root=repository_root / "eval_results" / "run_batches",
    )
    snapshot = write_selection_snapshot(
        repository_root, score_id, plan, kind="score"
    )
    emit(
        progress,
        "score_batch_allocated",
        score_id=score_id,
        total=len(plan.runs),
        jobs=worker_count,
        selection_path=snapshot.as_posix(),
    )
    store = ScoreStore()
    completed_by_index: dict[int, dict[str, Any]] = {}
    failures_by_index: dict[int, dict[str, str]] = {}
    state_lock = Lock()
    progress_lock = Lock()
    finished_count = 0

    def progress_event(event: str, **details: Any) -> None:
        with progress_lock:
            emit(progress, event, **details)

    def record_failure(index: int, record: RunRecord, exc: Exception) -> None:
        nonlocal finished_count
        error = f"{type(exc).__name__}: {exc}"
        with state_lock:
            failures_by_index[index] = {
                "run": record.run_name,
                "run_dir": record.run_dir.as_posix(),
                "error": error,
            }
            finished_count += 1
            completed_count = finished_count
        progress_event(
            "score_run_failed",
            index=index,
            completed_count=completed_count,
            total=len(plan.runs),
            run=record.run_name,
            error=error,
        )

    def run_group(question: str, records: list[tuple[int, RunRecord]]) -> None:
        try:
            prepared = prepare_question(
                question,
                repository_root=repository_root,
            )
        except Exception as exc:  # noqa: BLE001 - retain every affected run
            for index, record in records:
                progress_event(
                    "score_run_started",
                    index=index,
                    total=len(plan.runs),
                    run=record.run_name,
                    question=record.question,
                )
                record_failure(index, record, exc)
            return

        for index, record in records:
            progress_event(
                "score_run_started",
                index=index,
                total=len(plan.runs),
                run=record.run_name,
                question=record.question,
            )
            try:
                run_result = score_one(
                    record,
                    repository_root=repository_root,
                    score_id=score_id,
                    store=store,
                    prepared_question=prepared,
                )
            except Exception as exc:  # noqa: BLE001 - retain per-run evidence
                record_failure(index, record, exc)
                continue
            nonlocal finished_count
            with state_lock:
                completed_by_index[index] = run_result
                finished_count += 1
                completed_count = finished_count
            progress_event(
                "score_run_completed",
                index=index,
                completed_count=completed_count,
                total=len(plan.runs),
                run=record.run_name,
                status=run_result["status"],
                scores=run_result["scores"],
                score_path=run_result["score_path"],
            )

    futures: dict[Future[None], str] = {}
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="eval-score",
    ) as executor:
        for question, records in indexed_groups.items():
            futures[executor.submit(run_group, question, records)] = question
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # pragma: no cover - defensive group guard
                question = futures[future]
                for index, record in indexed_groups[question]:
                    with state_lock:
                        already_recorded = (
                            index in completed_by_index or index in failures_by_index
                        )
                    if not already_recorded:
                        record_failure(index, record, exc)

    completed = [completed_by_index[index] for index in sorted(completed_by_index)]
    failures = [failures_by_index[index] for index in sorted(failures_by_index)]
    results_path = snapshot.parent / "results.json"
    result = {
        "schema_version": "eval-score-batch-result.v1",
        "score_id": score_id,
        "selection": snapshot.as_posix(),
        "results": results_path.as_posix(),
        "selected_run_count": len(plan.runs),
        "question_count": len(indexed_groups),
        "requested_jobs": jobs,
        "jobs": worker_count,
        "job_unit": "question",
        "completed_count": len(completed),
        "failure_count": len(failures),
        "error_result_count": sum(
            value["status"] in {"EVALUATOR_ERROR", "QUESTION_CONTRACT_INCOMPLETE"}
            for value in completed
        ),
        "runs": completed,
        "failures": failures,
    }
    atomic_write_json(results_path, result)
    emit(
        progress,
        "score_batch_persisted",
        score_id=score_id,
        completed_count=len(completed),
        failure_count=len(failures),
        error_result_count=result["error_result_count"],
        results_path=results_path.as_posix(),
    )
    return result
