"""Discover, normalize, filter, and repeat-collapse evaluation runs."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from simulation.app.contracts import RunRecord, SelectionGroup, SelectionPlan


class SelectionError(ValueError):
    pass


FILTER_FIELDS = ("task", "question", "model", "harness", "skill", "run")


@dataclass(frozen=True)
class SelectorSpec:
    roots: tuple[Path, ...]
    include: dict[str, tuple[str, ...]] = field(default_factory=dict)
    exclude: dict[str, tuple[str, ...]] = field(default_factory=dict)
    repeat: str = "latest"


def _patterns(value: Any, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = value
    else:
        raise SelectionError(f"{label} must be a string or list of strings")
    if any(not item.strip() for item in values):
        raise SelectionError(f"{label} contains an empty pattern")
    return tuple(values)


def load_selector(path: Path, *, base: Path | None = None) -> SelectorSpec:
    source = path.resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SelectionError(f"selector root must be a mapping: {source}")
    unexpected = set(payload) - {"schema_version", "roots", "include", "exclude", "repeat"}
    if unexpected:
        raise SelectionError(f"unknown selector keys: {sorted(unexpected)}")
    if payload.get("schema_version") != "1.0":
        raise SelectionError("selector schema_version must be 1.0")
    raw_roots = payload.get("roots")
    if not isinstance(raw_roots, list) or not raw_roots or not all(
        isinstance(value, str) and value.strip() for value in raw_roots
    ):
        raise SelectionError("selector roots must be a non-empty list of paths")
    root_base = (base or source.parent).resolve()
    roots = tuple(
        (Path(value) if Path(value).is_absolute() else root_base / value).resolve()
        for value in raw_roots
    )
    mappings: list[dict[str, tuple[str, ...]]] = []
    for section in ("include", "exclude"):
        raw = payload.get(section, {})
        if not isinstance(raw, dict):
            raise SelectionError(f"selector {section} must be a mapping")
        unknown = set(raw) - set(FILTER_FIELDS)
        if unknown:
            raise SelectionError(f"unknown selector {section} fields: {sorted(unknown)}")
        mappings.append(
            {key: _patterns(value, label=f"{section}.{key}") for key, value in raw.items()}
        )
    repeat = payload.get("repeat", "latest")
    if repeat not in {"latest", "average"}:
        raise SelectionError("selector repeat must be latest or average")
    return SelectorSpec(roots, mappings[0], mappings[1], repeat)


def _read_metadata(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_metadata.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SelectionError(f"invalid run metadata: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SelectionError(f"run metadata must be an object: {path}")
    return value


def _question(metadata: dict[str, Any], name: str, question_ids: tuple[str, ...]) -> str:
    matches = [value for value in question_ids if name.startswith(f"{value}_") or name == value]
    if matches:
        return max(matches, key=len)
    direct = metadata.get("question_version") or metadata.get("question_id")
    if isinstance(direct, str) and direct:
        if re.search(r"-v\d+(?:\.\d+)+$", direct, re.IGNORECASE):
            return direct
        version = metadata.get("evalset_version")
        if isinstance(version, str) and version:
            return f"{direct}-{version}"
    eval_id = metadata.get("eval_id")
    version = metadata.get("evalset_version")
    if isinstance(eval_id, str) and eval_id:
        return f"{eval_id}-{version}" if isinstance(version, str) and version else eval_id
    raise SelectionError(f"cannot determine question/version for run: {name}")


def _directory_parts(name: str, question: str) -> tuple[str, str, str, str]:
    suffix = name[len(question) + 1 :] if name.startswith(f"{question}_") else name
    serial = suffix.rsplit("_", 1)[-1] if "_" in suffix else ""
    body = suffix[: -(len(serial) + 1)] if serial else suffix
    harness = ""
    for candidate in ("claude_code", "claude", "codex", "cowork", "dsh", "sdk"):
        if body.startswith(f"{candidate}_"):
            harness = "claude" if candidate == "claude_code" else candidate
            body = body[len(candidate) + 1 :]
            break
    skill = ""
    if body.endswith("_noskill"):
        skill = "noskill"
        body = body[:-8]
    else:
        match = re.search(r"_(\d{4}(?:[A-Z])?skill)$", body, re.IGNORECASE)
        if match:
            skill = match.group(1)
            body = body[: match.start()]
    return harness, body, skill, serial


def _normalise_run(run_dir: Path, question_ids: tuple[str, ...]) -> RunRecord:
    metadata = _read_metadata(run_dir)
    name = run_dir.name
    question = _question(metadata, name, question_ids)
    dir_harness, dir_model, dir_skill, serial = _directory_parts(name, question)
    task_value = metadata.get("task") or metadata.get("subtask")
    task = str(task_value).upper() if task_value else (
        "EI" if question.upper().startswith("EI") else "OPT" if question.upper().startswith("OPT") else "UNKNOWN"
    )
    harness = str(dir_harness or metadata.get("harness") or "unknown")
    if harness == "claude_code":
        harness = "claude"
    model = str(dir_model or metadata.get("model") or "unknown")
    skill = str(dir_skill or metadata.get("skill_version") or "noskill")
    execution_date = str(metadata.get("execution_date") or "")
    execution_run = str(metadata.get("execution_run") or serial or "")
    timestamp = str(
        metadata.get("execution_datetime")
        or metadata.get("standardized_at")
        or metadata.get("created_at")
        or ""
    )
    return RunRecord(
        run_dir.resolve(), name, task, question, model, harness, skill,
        (execution_date, execution_run, timestamp), metadata,
    )


def record_from_run(run_dir: Path, *, question_ids: Iterable[str]) -> RunRecord:
    """Normalize one explicitly supplied RUN_DIR."""

    resolved = run_dir.resolve()
    if not resolved.is_dir():
        raise SelectionError(f"RUN_DIR is not a directory: {resolved}")
    ids = tuple(sorted(set(question_ids), key=lambda value: (-len(value), value)))
    return _normalise_run(resolved, ids)


def _discover(roots: Iterable[Path], question_ids: tuple[str, ...]) -> tuple[list[RunRecord], list[dict[str, str]]]:
    directories: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise SelectionError(f"selection root is not a directory: {resolved}")
        for current, child_dirs, filenames in os.walk(resolved):
            directory = Path(current)
            prefixed = any(
                directory.name.startswith(f"{question}_") for question in question_ids
            )
            metadata: dict[str, Any] = {}
            if "run_metadata.json" in filenames:
                metadata = _read_metadata(directory)
            identified = any(
                metadata.get(key)
                for key in ("question_version", "question_id", "eval_id")
            )
            if prefixed or identified:
                directories.add(directory.resolve())
                # A physical run may contain project-local metadata; never
                # interpret its descendants as additional evaluation runs.
                child_dirs[:] = []
                continue
            child_dirs[:] = [
                name
                for name in child_dirs
                if name not in {"scores", "validator_scores", "trajectory", "__pycache__"}
            ]
    records: list[RunRecord] = []
    excluded: list[dict[str, str]] = []
    for directory in sorted(directories, key=lambda value: value.as_posix().casefold()):
        try:
            records.append(_normalise_run(directory, question_ids))
        except SelectionError as exc:
            excluded.append({"run_dir": directory.as_posix(), "reason": str(exc)})
    return records, excluded


def _value(record: RunRecord, field: str) -> str:
    return record.run_name if field == "run" else str(getattr(record, field))


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    folded = value.casefold()
    return any(fnmatch.fnmatchcase(folded, pattern.casefold()) for pattern in patterns)


def _included(record: RunRecord, filters: dict[str, tuple[str, ...]]) -> bool:
    return all(not patterns or _matches(_value(record, field), patterns) for field, patterns in filters.items())


def _excluded(record: RunRecord, filters: dict[str, tuple[str, ...]]) -> bool:
    return any(patterns and _matches(_value(record, field), patterns) for field, patterns in filters.items())


def select_runs(
    spec: SelectorSpec,
    *,
    question_ids: Iterable[str],
) -> SelectionPlan:
    ids = tuple(sorted(set(question_ids), key=lambda value: (-len(value), value)))
    records, rejected = _discover(spec.roots, ids)
    filtered = [
        value for value in records
        if _included(value, spec.include) and not _excluded(value, spec.exclude)
    ]
    grouped: dict[tuple[str, str, str, str, str], list[RunRecord]] = {}
    for record in filtered:
        grouped.setdefault(record.repeat_key, []).append(record)
    groups: list[SelectionGroup] = []
    for key in sorted(grouped):
        members = sorted(
            grouped[key], key=lambda value: (*value.execution_key, value.run_name.casefold())
        )
        if spec.repeat == "latest":
            members = members[-1:]
        groups.append(SelectionGroup(key, tuple(members)))
    return SelectionPlan(
        spec.repeat,
        tuple(groups),
        len(records),
        len(filtered),
        tuple(rejected),
    )
