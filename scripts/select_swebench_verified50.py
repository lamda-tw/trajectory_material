#!/usr/bin/env python3
"""Create the frozen, repository-stratified SWE-bench Verified holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


EXPECTED_FIELDS = {"instance_id", "repo", "base_commit", "problem_statement"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def rank(seed: str, instance_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{instance_id}".encode()).hexdigest()


def allocate_quotas(counts: Counter[str], total_selected: int) -> dict[str, int]:
    repositories = sorted(counts)
    if total_selected < len(repositories):
        raise ValueError("Selection size is smaller than the repository count")
    quotas = {repository: 1 for repository in repositories}
    remaining = total_selected - len(repositories)
    shares = {repository: Fraction(counts[repository] * remaining, sum(counts.values())) for repository in repositories}
    for repository, share in shares.items():
        quotas[repository] += share.numerator // share.denominator
    unallocated = total_selected - sum(quotas.values())
    remainders = sorted(
        repositories,
        key=lambda repository: (-(shares[repository] - int(shares[repository])), repository),
    )
    for repository in remainders[:unallocated]:
        quotas[repository] += 1
    if sum(quotas.values()) != total_selected:
        raise AssertionError("Quota allocation did not produce the requested selection size")
    return quotas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--seed", default="20260914")
    parser.add_argument("--size", type=int, default=50)
    args = parser.parse_args()

    input_path = args.input.resolve(strict=True)
    experiment = args.experiment.resolve()
    data_dir = experiment / "data"
    output_paths = [
        data_dir / "selected_tasks.jsonl",
        data_dir / "selected_instance_ids.txt",
        data_dir / "selection_manifest.json",
    ]
    if any(path.exists() for path in output_paths):
        raise FileExistsError("Frozen selection output already exists; refusing to overwrite it")

    rows = []
    for line_number, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if set(row) != EXPECTED_FIELDS:
            raise ValueError(f"Unexpected fields on line {line_number}: {sorted(row)}")
        rows.append(row)
    if len(rows) != 500:
        raise ValueError(f"Expected 500 rows, found {len(rows)}")
    instance_ids = [row["instance_id"] for row in rows]
    if len(set(instance_ids)) != len(instance_ids):
        raise ValueError("instance_id values are not unique")

    counts = Counter(row["repo"] for row in rows)
    quotas = allocate_quotas(counts, args.size)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["repo"]].append(row)

    selected = []
    for repository in sorted(grouped):
        candidates = sorted(grouped[repository], key=lambda row: (rank(args.seed, row["instance_id"]), row["instance_id"]))
        selected.extend(candidates[: quotas[repository]])
    selected.sort(key=lambda row: (rank(args.seed, row["instance_id"]), row["instance_id"]))
    if len(selected) != args.size or len({row["instance_id"] for row in selected}) != args.size:
        raise AssertionError("Selection is not the requested number of unique instances")

    selected_distribution = Counter(row["repo"] for row in selected)
    if dict(selected_distribution) != quotas:
        raise AssertionError("Selected repository distribution differs from allocated quotas")

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "source_path": str(input_path),
        "source_sha256": sha256_file(input_path),
        "source_row_count": len(rows),
        "source_fields": sorted(EXPECTED_FIELDS),
        "selection_size": args.size,
        "seed": args.seed,
        "algorithm": {
            "stratification": "one per repository, then proportional largest remainder",
            "quota_tie_break": "repository name ascending",
            "within_repository_order": 'sha256(seed + "\\0" + instance_id), then instance_id ascending',
            "final_output_order": 'sha256(seed + "\\0" + instance_id), then instance_id ascending',
        },
        "source_repository_counts": dict(sorted(counts.items())),
        "selected_repository_quotas": dict(sorted(quotas.items())),
        "instance_ids_in_output_order": [row["instance_id"] for row in selected],
    }
    atomic_write(data_dir / "selected_tasks.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected))
    atomic_write(data_dir / "selected_instance_ids.txt", "".join(row["instance_id"] + "\n" for row in selected))
    atomic_write(data_dir / "selection_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"selected": len(selected), "quotas": dict(sorted(quotas.items()))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
