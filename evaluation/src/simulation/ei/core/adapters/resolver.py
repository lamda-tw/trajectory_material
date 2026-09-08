"""Public artifact-resolution orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..models import ArtifactBundle, ArtifactResolution, QuestionProfile
from ._shared import (
    prepare_question_artifacts as _prepare_question_artifacts,
    resolve_artifacts as _resolve_artifacts,
)


def resolve_artifacts(
    profile: QuestionProfile,
    run_dir: Path,
    repository_root: Path,
    *,
    roles: Iterable[str] | None = None,
    prepared_question_artifacts: dict[str, ArtifactResolution] | None = None,
) -> ArtifactBundle:
    """Discover, select, read and normalize requested artifacts exactly once."""

    return _resolve_artifacts(
        profile,
        run_dir,
        repository_root,
        roles=roles,
        prepared_question_artifacts=prepared_question_artifacts,
    )


def prepare_question_artifacts(
    profile: QuestionProfile,
    repository_root: Path,
    *,
    roles: Iterable[str] | None = None,
) -> dict[str, ArtifactResolution]:
    return _prepare_question_artifacts(
        profile,
        repository_root,
        roles=roles,
    )


__all__ = ["prepare_question_artifacts", "resolve_artifacts"]
