"""Bounded candidate discovery and question-source location."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path


_EXCLUDED_PARTS = {
    "reference_answer",
    "trajectory",
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}


def _is_candidate_file(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    parts = tuple(value.casefold() for value in relative.parts)
    return not any(
        value in _EXCLUDED_PARTS
        or value.startswith("scores")
        or value.startswith("validator_scores")
        for value in parts
    )


def discover_candidate_files(
    roots: tuple[Path, ...],
    filenames: set[str],
) -> dict[str, set[Path]]:
    """Traverse each bounded artifact root once and index configured names."""

    wanted = {value.casefold() for value in filenames}
    output: dict[str, set[Path]] = defaultdict(set)
    for root in roots:
        if not root.is_dir():
            continue
        for directory, names, files in os.walk(root):
            names[:] = [
                value
                for value in names
                if value.casefold() not in _EXCLUDED_PARTS
                and not value.casefold().startswith("scores")
                and not value.casefold().startswith("validator_scores")
            ]
            base = Path(directory)
            for name in files:
                key = name.casefold()
                if key in wanted:
                    value = (base / name).resolve()
                    if _is_candidate_file(root, value):
                        output[key].add(value)
    return output


def question_directory(repository_root: Path, question_id: str) -> Path:
    datasets_root = repository_root / "datasets"
    variant_candidates = (
        tuple(
            group / question_id
            for group in sorted(
                (
                    value
                    for value in datasets_root.iterdir()
                    if value.is_dir() and value.name.endswith("-variants")
                ),
                key=lambda value: value.name.casefold(),
            )
        )
        if datasets_root.is_dir()
        else ()
    )
    candidates = tuple(
        value.resolve()
        for value in (
            repository_root / "evalsets" / "simulation" / question_id,
            *variant_candidates,
            repository_root / "evalset" / "simulation" / question_id,
        )
        if value.is_dir()
    )
    if len(candidates) > 1:
        raise FileExistsError(
            f"duplicate question identity {question_id!r} exists in multiple roots: "
            + ", ".join(str(value) for value in candidates)
        )
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"question source directory is missing: {question_id}")


__all__ = ["discover_candidate_files", "question_directory"]
