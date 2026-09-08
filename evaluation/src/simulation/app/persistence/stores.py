"""Persistence rules independent of EI scoring and workbook semantics."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from simulation.app.contracts import RunRecord, ScorePackage, SelectionPlan


class ScoreResolutionError(ValueError):
    pass


SCORE_ID_PATTERN = re.compile(r"^\d{14}(?:-\d{2})?$")


def _validate_score_id(score_id: str) -> None:
    if not SCORE_ID_PATTERN.fullmatch(score_id):
        raise ScoreResolutionError(
            "score_id must be YYYYMMDDHHMMSS or YYYYMMDDHHMMSS-NN"
        )


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def allocate_score_id(
    runs: Iterable[RunRecord],
    *,
    now: datetime | None = None,
    batch_root: Path | None = None,
) -> str:
    records = tuple(runs)
    base = (now or datetime.now().astimezone()).strftime("%Y%m%d%H%M%S")
    candidate = base
    suffix = 1
    while (
        any((record.run_dir / "scores" / candidate).exists() for record in records)
        or (batch_root is not None and (batch_root / candidate).exists())
    ):
        suffix += 1
        candidate = f"{base}-{suffix:02d}"
    return candidate


def _letters(index: int) -> str:
    value = index
    output = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        output = chr(65 + remainder) + output
    return output


def allocate_report_directory(
    reports_root: Path, *, now: datetime | None = None
) -> tuple[str, Path]:
    root = reports_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    prefix = (now or datetime.now().astimezone()).strftime("%m%d")
    index = 1
    while True:
        report_id = f"{prefix}{_letters(index)}"
        target = root / report_id
        try:
            target.mkdir()
            return report_id, target
        except FileExistsError:
            index += 1


class ScoreStore:
    """Write/read canonical packages under the physical run directory."""

    def write(
        self,
        record: RunRecord,
        score_id: str,
        package: ScorePackage,
        *,
        created_at: str,
    ) -> Path:
        _validate_score_id(score_id)
        payload = dict(package.payload)
        expected_identity = {
            "score_id": score_id,
            "created_at": created_at,
            "run": record.as_dict(),
        }
        mismatched = {
            field: {"expected": expected, "actual": payload.get(field)}
            for field, expected in expected_identity.items()
            if payload.get(field) != expected
        }
        if mismatched:
            raise ValueError(
                "score package persistence identity mismatch: "
                + ", ".join(
                    f"{field} expected {values['expected']!r}, "
                    f"got {values['actual']!r}"
                    for field, values in mismatched.items()
                )
            )
        scores = record.run_dir / "scores"
        scores.mkdir(parents=True, exist_ok=True)
        target = scores / score_id
        if target.exists():
            raise FileExistsError(f"score directory already exists: {target}")
        temporary = scores / f".{score_id}.tmp-{uuid.uuid4().hex}"
        temporary.mkdir()
        try:
            atomic_write_json(temporary / "score.json", payload)
            temporary.rename(target)
        except Exception:
            # A private empty/partial temp directory is safe to clean up here.
            for child in temporary.iterdir() if temporary.exists() else ():
                if child.is_file():
                    child.unlink()
            if temporary.exists():
                temporary.rmdir()
            raise
        return target / "score.json"

    def resolve(self, record: RunRecord, score_id: str = "latest") -> Path:
        scores = record.run_dir / "scores"
        if score_id != "latest":
            _validate_score_id(score_id)
            candidate = scores / score_id / "score.json"
            if not candidate.is_file():
                raise ScoreResolutionError(
                    f"score {score_id} does not exist for {record.run_name}"
                )
            return candidate
        candidates = sorted(
            (
                path
                for path in scores.glob("*/score.json")
                if path.is_file() and SCORE_ID_PATTERN.fullmatch(path.parent.name)
            ),
            key=lambda path: path.parent.name,
        )
        if not candidates:
            raise ScoreResolutionError(f"no canonical scores for {record.run_name}")
        return candidates[-1]

    def read(self, record: RunRecord, score_id: str = "latest") -> dict[str, Any]:
        path = self.resolve(record, score_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ScoreResolutionError(f"invalid canonical score: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ScoreResolutionError(f"canonical score must be an object: {path}")
        return payload


def write_selection_snapshot(
    repository_root: Path,
    batch_id: str,
    plan: SelectionPlan,
    *,
    kind: str,
) -> Path:
    directory = repository_root / "eval_results" / "run_batches" / batch_id
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "selection.json"
    payload = plan.as_dict()
    payload["batch_id"] = batch_id
    payload["kind"] = kind
    atomic_write_json(path, payload)
    return path
