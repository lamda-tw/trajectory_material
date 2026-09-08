"""Resolve one self-contained question source without cross-root mixing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class QuestionSourceError(ValueError):
    """Raised when a question identity is missing, incomplete, or ambiguous."""


@dataclass(frozen=True)
class QuestionSource:
    """The one physical question package selected for a question identity."""

    question_id: str
    kind: str
    directory: Path
    manifest_path: Path
    validator_path: Path
    layout: str = "self-contained"

    @property
    def uses_legacy_shared_data(self) -> bool:
        return self.layout == "legacy-shared-data"


@dataclass(frozen=True)
class QuestionArtifactLocation:
    """Selected question input and the bounded paths considered for it."""

    selected_path: Path | None
    candidates: tuple[Path, ...]


def _question_leaf(question_id: str) -> str:
    if (
        not isinstance(question_id, str)
        or not question_id.strip()
        or question_id in {".", ".."}
        or Path(question_id).name != question_id
        or "/" in question_id
        or "\\" in question_id
    ):
        raise QuestionSourceError(f"invalid question id: {question_id!r}")
    return question_id


def _manifest_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QuestionSourceError(f"invalid question manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise QuestionSourceError(f"question manifest must be an object: {path}")
    return payload


def _validate_manifest_identity(
    path: Path,
    *,
    question_id: str,
    expected_kind: str,
) -> None:
    payload = _manifest_payload(path)
    eval_id = payload.get("eval_id")
    version = payload.get("evalset_version")
    if not isinstance(eval_id, str) or not eval_id.strip():
        raise QuestionSourceError(f"question manifest has no eval_id: {path}")
    if not isinstance(version, str) or not version.strip():
        raise QuestionSourceError(f"question manifest has no evalset_version: {path}")
    manifest_identity = (
        eval_id if eval_id.endswith(f"-{version}") else f"{eval_id}-{version}"
    )
    if manifest_identity != question_id:
        raise QuestionSourceError(
            "question manifest identity mismatch: "
            f"requested {question_id!r}, manifest declares {manifest_identity!r}: {path}"
        )
    declared_kind = payload.get("question_kind")
    if declared_kind is not None and declared_kind != expected_kind:
        raise QuestionSourceError(
            f"question_kind {declared_kind!r} does not match {expected_kind!r}: {path}"
        )


def _existing_question_directories(
    repository_root: Path,
    question_id: str,
) -> tuple[tuple[str, Path, str], ...]:
    datasets_root = repository_root / "datasets"
    variant_candidates = (
        tuple(
            (
                "variant",
                group / question_id,
                "target",
            )
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
    candidates = (
        (
            "evaluation",
            repository_root / "evalsets" / "simulation" / question_id,
            "target",
        ),
        *variant_candidates,
        (
            "variant",
            repository_root / "evalset" / "simulation" / question_id,
            "legacy",
        ),
    )
    return tuple(value for value in candidates if value[1].is_dir())


def resolve_question_source(
    repository_root: Path,
    question_id: str,
    *,
    legacy_profile_root: Path | None = None,
    allow_legacy: bool = True,
) -> QuestionSource:
    """Resolve an exact question package as one atomic source.

    Target packages own ``manifest.json``, ``validator.yaml``, and ``data/`` in
    the same directory. During migration only, a question directory may pair
    with the old centrally stored validator. The selected directory is still
    atomic: prompt and data never fall through to another question root.
    """

    leaf = _question_leaf(question_id)
    repo = repository_root.resolve()
    present = _existing_question_directories(repo, leaf)
    if len(present) > 1:
        locations = ", ".join(str(value[1]) for value in present)
        raise QuestionSourceError(
            f"duplicate question identity {leaf!r} exists in multiple roots: {locations}"
        )
    if not present:
        raise QuestionSourceError(f"question source directory is missing: {leaf}")

    kind, directory, root_kind = present[0]
    directory = directory.resolve()
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise QuestionSourceError(
            f"question package is incomplete; manifest.json is missing: {directory}"
        )
    _validate_manifest_identity(
        manifest_path,
        question_id=leaf,
        expected_kind=kind,
    )

    local_validator = directory / "validator.yaml"
    if local_validator.is_file():
        return QuestionSource(
            leaf,
            kind,
            directory,
            manifest_path,
            local_validator,
        )

    if not allow_legacy or legacy_profile_root is None:
        raise QuestionSourceError(
            f"question package is incomplete; validator.yaml is missing: {directory}"
        )
    legacy_validator = (
        legacy_profile_root.resolve() / "questions" / leaf / "validator.yaml"
    )
    if not legacy_validator.is_file():
        raise QuestionSourceError(
            f"question package is incomplete; validator.yaml is missing: {directory}"
        )
    return QuestionSource(
        leaf,
        kind,
        directory,
        manifest_path,
        legacy_validator,
        layout=(
            "legacy-shared-data"
            if root_kind == "legacy" or not (directory / "data").is_dir()
            else "legacy-central-profile"
        ),
    )


def discover_question_sources(
    repository_root: Path,
    *,
    legacy_profile_root: Path | None = None,
    allow_legacy: bool = True,
) -> tuple[QuestionSource, ...]:
    """Discover manifest-backed EI questions and validate every exact identity."""

    repo = repository_root.resolve()
    ids: set[str] = set()
    legacy_ids = (
        {
            value.parent.name
            for value in legacy_profile_root.resolve().glob("questions/*/validator.yaml")
        }
        if legacy_profile_root is not None
        else set()
    )
    for parent in (
        repo / "evalsets" / "simulation",
        repo / "evalset" / "simulation",
    ):
        if not parent.is_dir():
            continue
        ids.update(
            child.name
            for child in parent.iterdir()
            if child.is_dir()
            and (child / "manifest.json").is_file()
            and (
                (child / "validator.yaml").is_file()
                or allow_legacy
                and child.name in legacy_ids
            )
        )
    datasets_root = repo / "datasets"
    if datasets_root.is_dir():
        for group in sorted(
            (
                value
                for value in datasets_root.iterdir()
                if value.is_dir() and value.name.endswith("-variants")
            ),
            key=lambda value: value.name.casefold(),
        ):
            ids.update(
                child.name
                for child in group.iterdir()
                if child.is_dir()
                and (child / "manifest.json").is_file()
                and (
                    (child / "validator.yaml").is_file()
                    or allow_legacy
                    and child.name in legacy_ids
                )
            )
    return tuple(
        resolve_question_source(
            repo,
            question_id,
            legacy_profile_root=legacy_profile_root,
            allow_legacy=allow_legacy,
        )
        for question_id in sorted(ids)
    )


def _bounded_path(root: Path, relative_parts: tuple[str, ...], *, label: str) -> Path:
    bounded_root = root.resolve()
    path = bounded_root.joinpath(*relative_parts).resolve()
    try:
        path.relative_to(bounded_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its allowed root") from exc
    return path


def locate_question_artifact(
    repository_root: Path,
    question_dir: Path,
    question_id: str,
    configured_path: str,
    *,
    allow_legacy_shared_data: bool = False,
) -> QuestionArtifactLocation:
    """Locate one configured artifact inside the already-selected question root."""

    repo = repository_root.resolve()
    question_root = question_dir.resolve()
    try:
        question_root.relative_to(repo)
    except ValueError as exc:
        raise ValueError("question directory escapes repository root") from exc

    relative = PurePosixPath(str(configured_path).replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("question artifact path must be relative and must not contain '..'")

    local = _bounded_path(
        question_root,
        tuple(relative.parts),
        label="question artifact",
    )
    candidates = [local]
    if local.is_file():
        return QuestionArtifactLocation(selected_path=local, candidates=tuple(candidates))

    if allow_legacy_shared_data and relative.parts[0] == "data":
        shared_root = (question_root.parent / "data" / question_id).resolve()
        try:
            shared_root.relative_to(repo)
        except ValueError as exc:
            raise ValueError("shared question-data root escapes repository root") from exc
        shared = _bounded_path(
            shared_root,
            tuple(relative.parts[1:]),
            label="shared question artifact",
        )
        candidates.append(shared)
        if shared.is_file():
            return QuestionArtifactLocation(
                selected_path=shared,
                candidates=tuple(candidates),
            )

    return QuestionArtifactLocation(selected_path=None, candidates=tuple(candidates))


__all__ = [
    "QuestionArtifactLocation",
    "QuestionSource",
    "QuestionSourceError",
    "discover_question_sources",
    "locate_question_artifact",
    "resolve_question_source",
]
