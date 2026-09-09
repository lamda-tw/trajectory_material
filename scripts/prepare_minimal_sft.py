#!/usr/bin/env python3
"""Build a deterministic, tiny train/validation subset from one grouped fold."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                row = json.loads(line)
                row["_source_line_number"] = line_number
                rows.append(row)
    return rows


def trajectory_id(row: dict[str, Any]) -> str:
    return str(row.get("metadata", {}).get("trajectory_id") or row["id"].split("::", 1)[0])


def serialized_size(row: dict[str, Any]) -> int:
    view = {key: value for key, value in row.items() if not key.startswith("_")}
    return len(json.dumps(view, ensure_ascii=False, separators=(",", ":")))


def select_round_robin_shortest(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count < 1 or count > len(rows):
        raise ValueError(f"requested {count} rows from a population of {len(rows)}")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[trajectory_id(row)].append(row)
    for group in groups.values():
        group.sort(key=lambda row: (serialized_size(row), str(row["id"])))

    selected: list[dict[str, Any]] = []
    depth = 0
    names = sorted(groups)
    while len(selected) < count:
        made_progress = False
        for name in names:
            if depth < len(groups[name]):
                selected.append(groups[name][depth])
                made_progress = True
                if len(selected) == count:
                    break
        if not made_progress:
            raise RuntimeError("selection exhausted unexpectedly")
        depth += 1
    return selected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            view = {key: value for key, value in row.items() if not key.startswith("_")}
            handle.write(json.dumps(view, ensure_ascii=False, separators=(",", ":")) + "\n")


def describe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "trajectory_id": trajectory_id(row),
            "task_family": row.get("metadata", {}).get("task_family"),
            "source_line_number": row["_source_line_number"],
            "serialized_chars": serialized_size(row),
        }
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fold-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-size", type=int, default=8)
    parser.add_argument("--validation-size", type=int, default=4)
    args = parser.parse_args()

    fold_dir = args.fold_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    train_source = fold_dir / "train.jsonl"
    validation_source = fold_dir / "validation.jsonl"
    split_source = fold_dir / "split.json"
    for path in (train_source, validation_source, split_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    train_rows = select_round_robin_shortest(load_jsonl(train_source), args.train_size)
    validation_rows = select_round_robin_shortest(
        load_jsonl(validation_source), args.validation_size
    )
    train_families = sorted({str(row["metadata"]["task_family"]) for row in train_rows})
    validation_families = sorted(
        {str(row["metadata"]["task_family"]) for row in validation_rows}
    )
    if set(train_families) & set(validation_families):
        raise ValueError("train/validation task-family leakage detected")

    train_out = output_dir / "train.jsonl"
    validation_out = output_dir / "validation.jsonl"
    write_jsonl(train_out, train_rows)
    write_jsonl(validation_out, validation_rows)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_policy": (
            "round-robin across trajectories; within each trajectory choose shortest "
            "serialized samples first; deterministic tie-break by sample id"
        ),
        "fold_dir": str(fold_dir),
        "source": {
            "train": {"path": str(train_source), "sha256": sha256(train_source)},
            "validation": {
                "path": str(validation_source),
                "sha256": sha256(validation_source),
            },
            "split": {"path": str(split_source), "sha256": sha256(split_source)},
        },
        "train": {
            "count": len(train_rows),
            "task_families": train_families,
            "trajectories": sorted({trajectory_id(row) for row in train_rows}),
            "samples": describe(train_rows),
            "output_sha256": sha256(train_out),
        },
        "validation": {
            "count": len(validation_rows),
            "task_families": validation_families,
            "trajectories": sorted({trajectory_id(row) for row in validation_rows}),
            "samples": describe(validation_rows),
            "output_sha256": sha256(validation_out),
        },
    }
    manifest_path = output_dir / "selection_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
