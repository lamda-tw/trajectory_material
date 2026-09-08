"""Freeze cross-run aggregation and render the sole EI XLSX report."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from simulation.app.contracts import SelectionPlan
from simulation.app.persistence import ScoreStore, atomic_write_json
from simulation.app.progress import ProgressCallback, emit
from simulation.ei.core.config import contract_header
from simulation.ei.provider import PROVIDER_ID, totals_dict


METRIC_ORDER = (
    "effectiveness.o2",
    "key.raw",
    "key.discrete",
    "key.piecewise",
    "all.raw",
)
NULLABLE_METRIC_STATUSES = frozenset(
    {"NOT_APPLICABLE", "QUESTION_CONTRACT_INCOMPLETE"}
)
WORKBOOK_SHEET_SPECS = (
    ("O2目标分天梯图", "ladder", "question_rows", "effectiveness.o2"),
    ("五项分段分天梯图", "ladder", "question_rows", "key.piecewise"),
    ("五项分段分详表", "detail", "key_rows", "piecewise"),
    ("五项离散分天梯图", "ladder", "question_rows", "key.discrete"),
    ("五项离散分详表", "detail", "key_rows", "discrete"),
    ("五项原始分天梯图", "ladder", "question_rows", "key.raw"),
    ("五项原始分详表", "detail", "key_rows", "raw"),
    ("全项原始分天梯图", "ladder", "question_rows", "all.raw"),
    ("全项原始分详表", "detail", "all_rows", "raw"),
)
SHEET_NAMES = tuple(spec[0] for spec in WORKBOOK_SHEET_SPECS)
RULESET_IDENTITY_FIELDS = (
    "release",
    "semantic_baseline",
)
QUESTION_CONTRACT_IDENTITY_FIELDS = (
    "question_id",
    "question_kind",
    "question_root",
    "files",
    "question_inputs",
)
RELEASE_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SCORE_ID_PATTERN = re.compile(r"^[0-9]{14}(?:-[0-9]{2})?$")
CHECK_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*\.[A-Za-z0-9_.-]+$")
RUN_SCORE_FIELDS = frozenset(
    {
        "contract",
        "provider_id",
        "question",
        "ruleset",
        "question_contract",
        "artifacts",
        "result",
        "score_id",
        "created_at",
        "run",
    }
)


def _identity(group_key: tuple[str, str, str, str, str]) -> str:
    _task, _question, model, harness, skill = group_key
    suffix = "" if not skill or skill == "noskill" else f" / {skill}"
    return f"{harness} / {model}{suffix}"


def _identity_text(identity: dict[str, Any]) -> str:
    return json.dumps(identity, ensure_ascii=False, sort_keys=True)


def _validated_score_contracts(
    payload: dict[str, Any],
    *,
    run_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the release and question-source contracts used by a score."""

    expected_header = contract_header("run-score")
    if payload.get("contract") != expected_header:
        raise ValueError(
            "canonical EI score contract mismatch for "
            f"{run_name}: expected {_identity_text(expected_header)}"
        )
    actual_fields = set(payload)
    if actual_fields != RUN_SCORE_FIELDS:
        missing = sorted(RUN_SCORE_FIELDS - actual_fields)
        extra = sorted(actual_fields - RUN_SCORE_FIELDS)
        raise ValueError(
            "canonical EI score fields differ from the unified run-score contract: "
            f"{run_name}; missing={missing}; extra={extra}"
        )
    if not isinstance(payload.get("question"), str) or not payload["question"]:
        raise ValueError(f"canonical EI score has no question: {run_name}")
    if not isinstance(payload.get("artifacts"), list):
        raise ValueError(f"canonical EI score artifacts must be a list: {run_name}")
    if not isinstance(payload.get("run"), dict):
        raise ValueError(f"canonical EI score run must be an object: {run_name}")
    if not isinstance(payload.get("created_at"), str) or not payload["created_at"]:
        raise ValueError(f"canonical EI score has no created_at: {run_name}")
    score_id = payload.get("score_id")
    if not isinstance(score_id, str) or SCORE_ID_PATTERN.fullmatch(score_id) is None:
        raise ValueError(f"canonical EI score has an invalid score_id: {run_name}")

    raw_ruleset = payload.get("ruleset")
    if not isinstance(raw_ruleset, dict) or set(raw_ruleset) != set(
        RULESET_IDENTITY_FIELDS
    ):
        raise ValueError(
            "canonical EI score has an invalid ruleset identity: "
            f"{run_name}; required={list(RULESET_IDENTITY_FIELDS)}"
        )
    ruleset = {field: raw_ruleset.get(field) for field in RULESET_IDENTITY_FIELDS}
    if (
        not isinstance(ruleset["release"], str)
        or RELEASE_PATTERN.fullmatch(ruleset["release"]) is None
    ):
        raise ValueError(
            f"canonical EI score has an invalid ruleset release: {run_name}"
        )
    if (
        not isinstance(ruleset["semantic_baseline"], str)
        or not ruleset["semantic_baseline"]
    ):
        raise ValueError(
            f"canonical EI score has an invalid semantic baseline: {run_name}"
        )

    raw_question = payload.get("question_contract")
    allowed_question_fields = set(QUESTION_CONTRACT_IDENTITY_FIELDS)
    if not isinstance(raw_question, dict):
        raise ValueError(
            f"canonical EI score has no question contract identity: {run_name}"
        )
    missing_question_fields = set(QUESTION_CONTRACT_IDENTITY_FIELDS) - set(
        raw_question
    )
    extra_question_fields = set(raw_question) - allowed_question_fields
    if missing_question_fields or extra_question_fields:
        raise ValueError(
            "canonical EI score has an invalid question contract identity: "
            f"{run_name}; missing={sorted(missing_question_fields)}; "
            f"extra={sorted(extra_question_fields)}"
        )
    question_contract = {
        field: raw_question.get(field) for field in QUESTION_CONTRACT_IDENTITY_FIELDS
    }
    if (
        not isinstance(question_contract["question_id"], str)
        or not question_contract["question_id"]
        or question_contract["question_id"] != payload["question"]
    ):
        raise ValueError(
            "canonical EI score question contract does not identify its question: "
            f"{run_name}"
        )
    for field in ("question_kind", "question_root"):
        value = question_contract[field]
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"canonical EI score has an invalid {field}: {run_name}"
            )
    files = question_contract["files"]
    if not isinstance(files, dict):
        raise ValueError(f"canonical EI score files must be an object: {run_name}")
    for label, value in files.items():
        if (
            not isinstance(label, str)
            or not label
            or not isinstance(value, dict)
            or set(value) != {"path"}
            or not isinstance(value["path"], str)
            or not value["path"]
        ):
            raise ValueError(
                f"canonical EI score has an invalid question file: {run_name}/{label}"
            )
    question_inputs = question_contract["question_inputs"]
    if not isinstance(question_inputs, list):
        raise ValueError(
            f"canonical EI score question_inputs must be a list: {run_name}"
        )
    for index, value in enumerate(question_inputs):
        if (
            not isinstance(value, dict)
            or set(value) != {"role", "path"}
            or not isinstance(value["role"], str)
            or not value["role"]
            or not isinstance(value["path"], str)
            or not value["path"]
        ):
            raise ValueError(
                "canonical EI score has an invalid question input source: "
                f"{run_name}/{index}"
            )
    return ruleset, question_contract


def _validate_rule_contribution(
    contribution: Any,
    *,
    run_name: str,
    metric_id: str,
    index: int,
) -> None:
    fields = {
        "check_id",
        "raw_score",
        "transformed_score",
        "weight",
        "supported",
        "filled",
    }
    if not isinstance(contribution, dict) or set(contribution) != fields:
        raise ValueError(
            "canonical EI score has an invalid rule contribution: "
            f"{run_name}/{metric_id}/{index}"
        )
    check_id = contribution["check_id"]
    if not isinstance(check_id, str) or CHECK_ID_PATTERN.fullmatch(check_id) is None:
        raise ValueError(
            "canonical EI score has an invalid contribution check ID: "
            f"{run_name}/{metric_id}/{index}"
        )
    for field in ("raw_score", "transformed_score"):
        value = contribution[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 100
        ):
            raise ValueError(
                "canonical EI score has an invalid contribution score: "
                f"{run_name}/{metric_id}/{index}/{field}"
            )
    weight = contribution["weight"]
    if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 100:
        raise ValueError(
            "canonical EI score has an invalid contribution weight: "
            f"{run_name}/{metric_id}/{index}"
        )
    if not isinstance(contribution["supported"], bool) or not isinstance(
        contribution["filled"], bool
    ):
        raise ValueError(
            "canonical EI score has invalid contribution flags: "
            f"{run_name}/{metric_id}/{index}"
        )


def _aggregate_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("aggregates"), list):
        raise ValueError("canonical EI score has no aggregate list")
    return {
        str(value["id"]): value
        for value in result["aggregates"]
        if isinstance(value, dict) and isinstance(value.get("id"), str)
    }


def _contributions(payload: dict[str, Any], metric_id: str) -> dict[str, dict[str, Any]]:
    metric = _aggregate_index(payload).get(metric_id)
    if not metric or not isinstance(metric.get("contributions"), list):
        raise ValueError(f"canonical EI score has no contributions for {metric_id}")
    return {
        str(value["check_id"]): value
        for value in metric["contributions"]
        if isinstance(value, dict) and isinstance(value.get("check_id"), str)
    }


def _validated_run_metrics(
    payload: dict[str, Any],
    *,
    run_name: str,
) -> tuple[dict[str, float | None], str, str, dict[str, str]]:
    """Read one canonical score without turning unexplained nulls into blanks."""

    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"canonical EI score has no result object: {run_name}")
    result_fields = {"status", "error", "aggregates", "components", "checks"}
    if set(result) != result_fields:
        raise ValueError(
            "canonical EI score result fields differ from the unified contract: "
            f"{run_name}; missing={sorted(result_fields - set(result))}; "
            f"extra={sorted(set(result) - result_fields)}"
        )
    if not isinstance(result.get("components"), list) or not isinstance(
        result.get("checks"), list
    ):
        raise ValueError(
            f"canonical EI score components/checks must be lists: {run_name}"
        )
    result_status = result.get("status")
    if not isinstance(result_status, str) or not result_status:
        raise ValueError(f"canonical EI score has no result status: {run_name}")
    result_error = result.get("error", "")
    if not isinstance(result_error, str):
        raise ValueError(f"canonical EI score has a non-string result error: {run_name}")

    raw_aggregates = result.get("aggregates")
    if not isinstance(raw_aggregates, list) or len(raw_aggregates) != len(
        METRIC_ORDER
    ):
        raise ValueError(
            f"canonical EI score aggregate list differs: {run_name}"
        )
    aggregate_fields = {
        "id",
        "group",
        "score",
        "max_score",
        "status",
        "error",
        "contributions",
    }
    expected_groups = {
        "effectiveness.o2": "effectiveness",
        "key.raw": "key",
        "key.discrete": "key",
        "key.piecewise": "key",
        "all.raw": "all",
    }
    valid_statuses = {
        "SCORED",
        "INVALID_CANDIDATE",
        "EVALUATOR_ERROR",
        "QUESTION_CONTRACT_INCOMPLETE",
        "NOT_APPLICABLE",
    }
    for index, aggregate in enumerate(raw_aggregates):
        if not isinstance(aggregate, dict) or set(aggregate) != aggregate_fields:
            raise ValueError(
                f"canonical EI score has an invalid aggregate: {run_name}/{index}"
            )
        metric_id = aggregate["id"]
        if (
            not isinstance(metric_id, str)
            or metric_id not in expected_groups
            or aggregate["group"] != expected_groups[metric_id]
        ):
            raise ValueError(
                f"canonical EI score has an invalid aggregate identity: {run_name}/{index}"
            )
        score = aggregate["score"]
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0 <= float(score) <= 100
        ):
            raise ValueError(
                f"canonical EI score has an invalid aggregate score: {run_name}/{metric_id}"
            )
        if aggregate["max_score"] != 100 or isinstance(
            aggregate["max_score"], bool
        ):
            raise ValueError(
                f"canonical EI score has an invalid aggregate maximum: {run_name}/{metric_id}"
            )
        if (
            not isinstance(aggregate["status"], str)
            or aggregate["status"] not in valid_statuses
            or not isinstance(aggregate["error"], str)
        ):
            raise ValueError(
                f"canonical EI score has invalid aggregate status/error: {run_name}/{metric_id}"
            )

    totals = totals_dict(payload)
    aggregates = _aggregate_index(payload)
    if len(aggregates) != len(METRIC_ORDER):
        raise ValueError(
            f"canonical EI score aggregate set differs: {run_name}"
        )
    metric_statuses: dict[str, str] = {}
    for metric_id in METRIC_ORDER:
        aggregate = aggregates.get(metric_id)
        status = aggregate.get("status") if aggregate else None
        if not isinstance(status, str) or not status:
            raise ValueError(
                f"canonical EI score has no aggregate status: {run_name}/{metric_id}"
            )
        if totals[metric_id] is None and status not in NULLABLE_METRIC_STATUSES:
            raise ValueError(
                "score contains an unexplained null aggregate: "
                f"{run_name}/{metric_id}/{status}"
            )
        contributions = aggregate.get("contributions")
        if not isinstance(contributions, list):
            raise ValueError(
                f"canonical EI score has invalid contributions: {run_name}/{metric_id}"
            )
        for index, contribution in enumerate(contributions):
            _validate_rule_contribution(
                contribution,
                run_name=run_name,
                metric_id=metric_id,
                index=index,
            )
        metric_statuses[metric_id] = status
    return totals, result_status, result_error, metric_statuses


def _group_metric(
    values: list[float | None],
    *,
    metric_id: str,
    question: str,
) -> float | None:
    """Average a repeat group while rejecting numeric/null contract mixing."""

    null_count = sum(value is None for value in values)
    if 0 < null_count < len(values):
        raise ValueError(
            "repeat group mixes numeric and null aggregate values: "
            f"{question}/{metric_id}"
        )
    if null_count:
        return None
    return round(mean(float(value) for value in values if value is not None), 6)


def _model_metric(values: list[float | None]) -> float | None:
    """Give numeric questions one vote each; preserve an all-null model cell."""

    numeric = [float(value) for value in values if value is not None]
    return round(mean(numeric), 6) if numeric else None


def _score2(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 2)


def _average2(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(mean(numeric), 2) if numeric else None


def _descending_average_key(label: str, value: float | None) -> tuple[bool, float, str]:
    return value is None, -(value or 0.0), label


def _ladder_sheet(
    name: str,
    rows: list[dict[str, Any]],
    metric_id: str,
) -> dict[str, Any]:
    identities = list(dict.fromkeys(str(row["identity"]) for row in rows))
    questions = list(dict.fromkeys(str(row["question"]) for row in rows))
    values: dict[tuple[str, str], float | None] = {}
    for row in rows:
        identity = str(row["identity"])
        question = str(row["question"])
        key = (identity, question)
        if key in values:
            raise ValueError(f"duplicate report cell for {identity} / {question}")
        metrics = row.get("metrics")
        score = metrics.get(metric_id) if isinstance(metrics, dict) else None
        values[key] = _score2(score)

    question_averages = {
        question: _average2([values.get((identity, question)) for identity in identities])
        for question in questions
    }
    questions.sort(
        key=lambda question: _descending_average_key(
            question, question_averages[question]
        )
    )
    model_averages = {
        identity: _average2([values.get((identity, question)) for question in questions])
        for identity in identities
    }
    identities.sort(
        key=lambda identity: _descending_average_key(identity, model_averages[identity])
    )
    matrix = [
        [values.get((identity, question)) for question in questions]
        for identity in identities
    ]
    return {
        "name": name,
        "kind": "ladder",
        "metric_id": metric_id,
        "models": identities,
        "questions": questions,
        "values": matrix,
        "row_averages": [model_averages[identity] for identity in identities],
        "column_averages": [question_averages[question] for question in questions],
        "overall_average": _average2(
            [score for matrix_row in matrix for score in matrix_row]
        ),
    }


def _detail_sheet(
    name: str,
    rows: list[dict[str, Any]],
    score_field: str,
) -> dict[str, Any]:
    identities = list(dict.fromkeys(str(row["identity"]) for row in rows))
    check_order = list(dict.fromkeys(str(row["check_id"]) for row in rows))
    question_order: dict[str, list[str]] = {check_id: [] for check_id in check_order}
    values: dict[tuple[str, str, str], float | None] = {}
    for row in rows:
        check_id = str(row["check_id"])
        question = str(row["question"])
        identity = str(row["identity"])
        if question not in question_order[check_id]:
            question_order[check_id].append(question)
        key = (check_id, question, identity)
        if key in values:
            raise ValueError(
                f"duplicate detail cell for {check_id} / {question} / {identity}"
            )
        values[key] = _score2(row.get(score_field))

    model_averages = {
        identity: _average2(
            [
                score
                for (check_id, question, current_identity), score in values.items()
                if current_identity == identity
            ]
        )
        for identity in identities
    }
    identities.sort(
        key=lambda identity: _descending_average_key(identity, model_averages[identity])
    )

    detail_rows: list[dict[str, Any]] = []
    for check_id in check_order:
        ranked_questions = []
        for question in question_order[check_id]:
            scores = [values.get((check_id, question, identity)) for identity in identities]
            ranked_questions.append((question, scores, _average2(scores)))
        ranked_questions.sort(
            key=lambda item: _descending_average_key(item[0], item[2])
        )
        for index, (question, scores, average) in enumerate(ranked_questions):
            detail_rows.append(
                {
                    "check_id": check_id,
                    "question": question,
                    "values": scores,
                    "average": average,
                    "group_start": index == 0,
                }
            )

    return {
        "name": name,
        "kind": "detail",
        "score_field": score_field,
        "models": identities,
        "rows": detail_rows,
        "model_averages": [model_averages[identity] for identity in identities],
        "overall_average": _average2(list(values.values())),
    }


def _workbook_sheets(frozen: dict[str, Any]) -> list[dict[str, Any]]:
    sheets: list[dict[str, Any]] = []
    for name, kind, source, score_field in WORKBOOK_SHEET_SPECS:
        source_rows = frozen[source]
        if kind == "ladder":
            sheets.append(_ladder_sheet(name, source_rows, score_field))
        else:
            sheets.append(_detail_sheet(name, source_rows, score_field))
    return sheets


def freeze_aggregation(
    plan: SelectionPlan,
    score_store: ScoreStore,
    *,
    score_id: str,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Average repeats inside a question, then give every question one vote."""

    per_run: list[dict[str, Any]] = []
    question_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    model_questions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    frozen_ruleset: dict[str, Any] | None = None
    frozen_question_contracts: dict[str, dict[str, Any]] = {}

    emit(
        progress,
        "aggregation_started",
        group_count=len(plan.groups),
        run_count=len(plan.runs),
        score_id=score_id,
        repeat=plan.repeat,
    )
    for group_index, group in enumerate(plan.groups, start=1):
        emit(
            progress,
            "aggregation_group_started",
            index=group_index,
            total=len(plan.groups),
            question=group.repeat_key[1],
            model=group.repeat_key[2],
            harness=group.repeat_key[3],
            skill=group.repeat_key[4],
            repeat_count=len(group.members),
        )
        packages: list[dict[str, Any]] = []
        for record in group.members:
            payload = score_store.read(record, score_id)
            ruleset_identity, question_contract_identity = _validated_score_contracts(
                payload,
                run_name=record.run_name,
            )
            if payload.get("provider_id") != PROVIDER_ID:
                raise ValueError(f"score provider mismatch for {record.run_name}")
            if payload.get("question") != record.question:
                raise ValueError(f"score question mismatch for {record.run_name}")
            if frozen_ruleset is None:
                frozen_ruleset = ruleset_identity
            elif ruleset_identity != frozen_ruleset:
                raise ValueError(
                    "report mixes ruleset identities: "
                    f"{record.run_name}; expected={_identity_text(frozen_ruleset)}; "
                    f"actual={_identity_text(ruleset_identity)}"
                )
            question_id = question_contract_identity["question_id"]
            existing_question_contract = frozen_question_contracts.get(question_id)
            if existing_question_contract is None:
                frozen_question_contracts[question_id] = question_contract_identity
            elif question_contract_identity != existing_question_contract:
                raise ValueError(
                    "question contract identity mismatch for "
                    f"{question_id}: {record.run_name}; "
                    f"expected={_identity_text(existing_question_contract)}; "
                    f"actual={_identity_text(question_contract_identity)}"
                )
            totals, result_status, result_error, metric_statuses = (
                _validated_run_metrics(payload, run_name=record.run_name)
            )
            per_run.append(
                {
                    "run": record.run_name,
                    "run_dir": record.run_dir.as_posix(),
                    "question": record.question,
                    "identity": _identity(group.repeat_key),
                    "score_id": str(payload.get("score_id", "")),
                    "metrics": totals,
                    "result_status": result_status,
                    "result_error": result_error,
                    "metric_statuses": metric_statuses,
                }
            )
            packages.append(
                {
                    "payload": payload,
                    "metrics": totals,
                    "result_status": result_status,
                    "result_error": result_error,
                    "metric_statuses": metric_statuses,
                }
            )

        identity = _identity(group.repeat_key)
        metrics = {
            metric_id: _group_metric(
                [value["metrics"][metric_id] for value in packages],
                metric_id=metric_id,
                question=group.repeat_key[1],
            )
            for metric_id in METRIC_ORDER
        }
        question_row = {
            "task": group.repeat_key[0],
            "question": group.repeat_key[1],
            "model": group.repeat_key[2],
            "harness": group.repeat_key[3],
            "skill": group.repeat_key[4],
            "identity": identity,
            "repeat_count": len(packages),
            "metrics": metrics,
            "result_statuses": list(
                dict.fromkeys(str(value["result_status"]) for value in packages)
            ),
            "result_errors": list(
                dict.fromkeys(
                    str(value["result_error"])
                    for value in packages
                    if value["result_error"]
                )
            ),
            "metric_statuses": {
                metric_id: list(
                    dict.fromkeys(
                        str(value["metric_statuses"][metric_id])
                        for value in packages
                    )
                )
                for metric_id in METRIC_ORDER
            },
        }
        question_rows.append(question_row)
        model_questions[identity].append(question_row)

        first_payload = packages[0]["payload"]
        key_ids = (
            tuple(_contributions(first_payload, "key.raw"))
            if metrics["key.raw"] is not None
            else ()
        )
        for check_id in key_ids:
            raw_values = [
                _contributions(value["payload"], "key.raw")[check_id]
                for value in packages
            ]
            discrete_values = [
                _contributions(value["payload"], "key.discrete")[check_id]
                for value in packages
            ]
            piecewise_values = [
                _contributions(value["payload"], "key.piecewise")[check_id]
                for value in packages
            ]
            key_rows.append(
                {
                    "question": group.repeat_key[1],
                    "identity": identity,
                    "check_id": check_id,
                    "raw": round(mean(float(value["transformed_score"]) for value in raw_values), 6),
                    "discrete": round(mean(float(value["transformed_score"]) for value in discrete_values), 6),
                    "piecewise": round(mean(float(value["transformed_score"]) for value in piecewise_values), 6),
                    "weight": int(raw_values[0]["weight"]),
                    "supported": all(bool(value["supported"]) for value in raw_values),
                    "filled": any(bool(value["filled"]) for value in raw_values),
                }
            )
        all_ids = (
            tuple(_contributions(first_payload, "all.raw"))
            if metrics["all.raw"] is not None
            else ()
        )
        for check_id in all_ids:
            values = [
                _contributions(value["payload"], "all.raw")[check_id]
                for value in packages
            ]
            all_rows.append(
                {
                    "question": group.repeat_key[1],
                    "identity": identity,
                    "check_id": check_id,
                    "raw": round(mean(float(value["transformed_score"]) for value in values), 6),
                    "weight": int(values[0]["weight"]),
                }
            )
        emit(
            progress,
            "aggregation_group_completed",
            index=group_index,
            total=len(plan.groups),
            question=group.repeat_key[1],
            model=group.repeat_key[2],
            harness=group.repeat_key[3],
            skill=group.repeat_key[4],
            repeat_count=len(group.members),
            metrics=metrics,
        )

    model_rows = []
    for identity, rows in model_questions.items():
        model_rows.append(
            {
                "identity": identity,
                "question_count": len(rows),
                "metrics": {
                    metric_id: _model_metric(
                        [row["metrics"][metric_id] for row in rows]
                    )
                    for metric_id in METRIC_ORDER
                },
            }
        )
    model_rows.sort(
        key=lambda value: (
            value["metrics"]["key.piecewise"] is None,
            -(value["metrics"]["key.piecewise"] or 0.0),
            value["identity"],
        )
    )
    question_rows.sort(key=lambda value: (value["question"], value["identity"]))
    emit(
        progress,
        "aggregation_completed",
        model_count=len(model_rows),
        question_row_count=len(question_rows),
        run_count=len(per_run),
    )
    if frozen_ruleset is None or not frozen_question_contracts:
        raise ValueError("report selection contains no canonical EI scores")
    frozen = {
        "contract": contract_header("report-aggregation"),
        "provider_id": PROVIDER_ID,
        "ruleset": frozen_ruleset,
        "question_contracts": [
            frozen_question_contracts[question_id]
            for question_id in sorted(frozen_question_contracts)
        ],
        "score_id": score_id,
        "repeat": plan.repeat,
        "metric_order": list(METRIC_ORDER),
        "model_rows": model_rows,
        "question_rows": question_rows,
        "key_rows": key_rows,
        "all_rows": all_rows,
        "per_run": per_run,
    }
    frozen["workbook_sheets"] = _workbook_sheets(frozen)
    return frozen


def _artifact_tool_entry(node_modules: Path) -> Path:
    return node_modules / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"


def _bundled_node_modules_candidates() -> tuple[Path, ...]:
    """Return deterministic Codex runtime locations, without recursive searching."""

    return (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "node_modules",
    )


def _report_environment() -> dict[str, str]:
    environment = os.environ.copy()
    configured_modules = environment.get("EVAL_NODE_MODULES")
    if configured_modules:
        modules = Path(configured_modules).expanduser().resolve()
        if not _artifact_tool_entry(modules).is_file():
            raise RuntimeError(
                "EVAL_NODE_MODULES must point to the node_modules directory "
                f"that contains @oai/artifact-tool: {modules}"
            )
        environment["EVAL_NODE_MODULES"] = str(modules)
        return environment

    for modules in _bundled_node_modules_candidates():
        if _artifact_tool_entry(modules).is_file():
            environment["EVAL_NODE_MODULES"] = str(modules.resolve())
            break
    return environment


def _node_command(environment: dict[str, str] | None = None) -> str:
    runtime_environment = environment or os.environ
    configured = runtime_environment.get("EVAL_NODE")
    if configured:
        configured_path = Path(configured).expanduser().resolve()
        if configured_path.is_file():
            return str(configured_path)
        raise RuntimeError(f"EVAL_NODE does not exist: {configured}")

    configured_modules = runtime_environment.get("EVAL_NODE_MODULES")
    if configured_modules:
        node_root = Path(configured_modules).parent
        for candidate in (node_root / "bin" / "node.exe", node_root / "bin" / "node"):
            if candidate.is_file():
                return str(candidate.resolve())

    discovered = shutil.which("node", path=runtime_environment.get("PATH"))
    if not discovered:
        raise RuntimeError("Node.js is required to generate EI推演打分.xlsx")
    return discovered


def validate_report_runtime() -> None:
    """Fail before aggregation when the XLSX runtime cannot be resolved."""

    environment = _report_environment()
    node = _node_command(environment)
    configured_modules = environment.get("EVAL_NODE_MODULES")
    if configured_modules:
        return

    script = Path(__file__).with_name("build_ei_score_report.mjs")
    completed = subprocess.run(
        [
            node,
            "--input-type=module",
            "--eval",
            "import('@oai/artifact-tool')",
        ],
        cwd=script.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "EI XLSX runtime is incomplete: @oai/artifact-tool is unavailable. "
            "The default Codex runtime was also checked. Set EVAL_NODE and "
            "EVAL_NODE_MODULES explicitly if the runtime is installed elsewhere."
        )


def _process_detail(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout)[-4000:]


def _run_workbook_builder(
    payload: Path,
    *,
    operation: str,
    environment: dict[str, str],
    output: Path | None = None,
    preview: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).with_name("build_ei_score_report.mjs")
    command = [
        _node_command(environment),
        str(script),
        "--operation",
        operation,
        "--input",
        str(payload),
    ]
    if output is not None:
        command.extend(("--output", str(output)))
    if preview is not None:
        command.extend(("--preview-dir", str(preview)))
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
        env=environment,
    )


def _excel_preview_command() -> str | None:
    if os.name != "nt":
        return None
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = (
        system_root
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    return str(powershell.resolve()) if powershell.is_file() else None


def _render_previews_with_excel(
    payload: Path,
    output: Path,
    preview: Path,
    *,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str] | None:
    powershell = _excel_preview_command()
    if powershell is None:
        return None
    script = Path(__file__).with_name("render_ei_report_preview.ps1")
    return subprocess.run(
        [
            powershell,
            "-STA",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Workbook",
            str(output),
            "-Aggregation",
            str(payload),
            "-PreviewDirectory",
            str(preview),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
        env=environment,
    )


def _validate_workbook_archive(output: Path) -> None:
    try:
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None or "xl/workbook.xml" not in archive.namelist():
                raise RuntimeError("generated EI workbook is corrupt")
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"generated EI workbook is invalid: {exc}") from exc


def _render_workbook(payload: Path, output: Path) -> tuple[str, ...]:
    environment = _report_environment()
    preview = output.parent / ".ei-report-preview"
    if preview.exists():
        raise RuntimeError(f"report preview staging directory already exists: {preview}")
    preview.mkdir(parents=False)
    try:
        exported = _run_workbook_builder(
            payload,
            operation="export",
            output=output,
            environment=environment,
        )
        if exported.returncode != 0 or not output.is_file():
            raise RuntimeError(
                f"workbook export failed (exit={exported.returncode}); "
                f"{_process_detail(exported)}"
            )

        artifact_preview = _run_workbook_builder(
            payload,
            operation="preview",
            preview=preview,
            environment=environment,
        )
        preview_names = {path.stem for path in preview.glob("*.png")}
        if artifact_preview.returncode != 0 or preview_names != set(SHEET_NAMES):
            artifact_detail = _process_detail(artifact_preview)
            for path in preview.glob("*.png"):
                path.unlink()
            excel_preview = _render_previews_with_excel(
                payload,
                output,
                preview,
                environment=environment,
            )
            preview_names = {path.stem for path in preview.glob("*.png")}
            if excel_preview is None or excel_preview.returncode != 0 or preview_names != set(SHEET_NAMES):
                excel_detail = (
                    "Excel preview fallback is unavailable"
                    if excel_preview is None
                    else _process_detail(excel_preview)
                )
                rendered = tuple(name for name in SHEET_NAMES if name in preview_names)
                raise RuntimeError(
                    "workbook preview failed; "
                    f"artifact_tool_exit={artifact_preview.returncode}; "
                    f"excel_exit={getattr(excel_preview, 'returncode', 'unavailable')}; "
                    f"previews={rendered}; artifact_tool={artifact_detail}; "
                    f"excel={excel_detail}"
                )
        _validate_workbook_archive(output)
        rendered = tuple(name for name in SHEET_NAMES if name in preview_names)
    finally:
        if os.environ.get("EVAL_KEEP_REPORT_PREVIEWS") != "1":
            shutil.rmtree(preview, ignore_errors=True)
    diagnostic = Path(f"{output}.inspect.ndjson")
    diagnostic.unlink(missing_ok=True)
    return rendered


def build_report(
    plan: SelectionPlan,
    *,
    report_id: str,
    report_dir: Path,
    score_id: str = "latest",
    score_store: ScoreStore | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Path]:
    store = score_store or ScoreStore()
    frozen = freeze_aggregation(
        plan,
        store,
        score_id=score_id,
        progress=progress,
    )
    frozen["report_id"] = report_id
    frozen["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    aggregation_path = report_dir / "aggregation.json"
    selection_path = report_dir / "selection.json"
    atomic_write_json(aggregation_path, frozen)
    atomic_write_json(selection_path, plan.as_dict())
    workbook = report_dir / f"EI推演打分-{report_id}.xlsx"
    emit(
        progress,
        "workbook_started",
        workbook=workbook.as_posix(),
        sheet_count=len(SHEET_NAMES),
    )
    rendered = _render_workbook(aggregation_path, workbook)
    emit(
        progress,
        "workbook_completed",
        workbook=workbook.as_posix(),
        sheets=rendered,
    )
    manifest = report_dir / "report_manifest.json"
    atomic_write_json(
        manifest,
        {
            "contract": contract_header("report-manifest"),
            "report_id": report_id,
            "score_id": score_id,
            "repeat": plan.repeat,
            "workbook": workbook.name,
            "sheet_names": list(SHEET_NAMES),
            "rendered_sheets": list(rendered),
            "artifacts": {
                "workbook": workbook.name,
                "aggregation": aggregation_path.name,
                "selection": selection_path.name,
            },
        },
    )
    emit(
        progress,
        "report_artifacts_completed",
        workbook=workbook.as_posix(),
        aggregation=aggregation_path.as_posix(),
        manifest=manifest.as_posix(),
    )
    return {"workbook": workbook, "aggregation": aggregation_path, "manifest": manifest}
