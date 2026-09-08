from __future__ import annotations

import json
from pathlib import Path

import pytest

from simulation.ei.core.question_sources import (
    QuestionSourceError,
    discover_question_sources,
    resolve_question_source,
)


def _write_question(
    directory: Path,
    question_id: str,
    *,
    kind: str,
    validator: bool = True,
) -> Path:
    directory.mkdir(parents=True)
    eval_id, version = question_id.rsplit("-", 1)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "eval_id": eval_id,
                "evalset_version": version,
                "question_kind": kind,
            }
        ),
        encoding="utf-8",
    )
    if validator:
        (directory / "validator.yaml").write_text("schema_version: '2.0'\n", encoding="utf-8")
    return directory


def _variant_directory(repo: Path, question_id: str, group: str = "BASE-variants") -> Path:
    return repo / "datasets" / group / question_id


def test_resolver_selects_the_self_contained_root_by_exact_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    evaluation_id = "EI-BASE-v1.2"
    variant_id = "EI-BASE-VAR01-v1.2"
    evaluation = _write_question(
        repo / "evalsets" / "simulation" / evaluation_id,
        evaluation_id,
        kind="evaluation",
    )
    variant = _write_question(
        _variant_directory(repo, variant_id),
        variant_id,
        kind="variant",
    )

    evaluation_source = resolve_question_source(repo, evaluation_id)
    variant_source = resolve_question_source(repo, variant_id)

    assert evaluation_source.directory == evaluation.resolve()
    assert evaluation_source.kind == "evaluation"
    assert evaluation_source.validator_path == evaluation / "validator.yaml"
    assert variant_source.directory == variant.resolve()
    assert variant_source.kind == "variant"
    assert variant_source.validator_path == variant / "validator.yaml"


def test_duplicate_identity_across_target_roots_is_an_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    question_id = "EI-DUP-v1.2"
    _write_question(
        repo / "evalsets" / "simulation" / question_id,
        question_id,
        kind="evaluation",
    )
    _write_question(
        _variant_directory(repo, question_id),
        question_id,
        kind="variant",
    )

    with pytest.raises(QuestionSourceError, match="duplicate question identity"):
        resolve_question_source(repo, question_id)


def test_variant_without_its_own_validator_never_falls_back_to_base(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    base_id = "EI-BASE-v1.2"
    variant_id = "EI-BASE-VAR01-v1.2"
    _write_question(
        repo / "evalsets" / "simulation" / base_id,
        base_id,
        kind="evaluation",
    )
    _write_question(
        _variant_directory(repo, variant_id),
        variant_id,
        kind="variant",
        validator=False,
    )

    with pytest.raises(QuestionSourceError, match="validator.yaml is missing"):
        resolve_question_source(repo, variant_id)


def test_legacy_fallback_is_one_explicit_question_profile_pair(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    package_root = repo / "evaluation" / "src" / "simulation" / "ei"
    question_id = "EI-LEGACY-VAR01-v1.2"
    question = _write_question(
        repo / "evalset" / "simulation" / question_id,
        question_id,
        kind="variant",
        validator=False,
    )
    legacy_validator = package_root / "questions" / question_id / "validator.yaml"
    legacy_validator.parent.mkdir(parents=True)
    legacy_validator.write_text("schema_version: '2.0'\n", encoding="utf-8")

    source = resolve_question_source(
        repo,
        question_id,
        legacy_profile_root=package_root,
    )

    assert source.directory == question.resolve()
    assert source.validator_path == legacy_validator.resolve()
    assert source.uses_legacy_shared_data


def test_discovery_ignores_non_ei_packages_without_validator(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    question_id = "EI-Q-v1.2"
    _write_question(
        repo / "evalsets" / "simulation" / question_id,
        question_id,
        kind="evaluation",
    )
    _write_question(
        repo / "evalsets" / "simulation" / "OPT-Q-v1.2",
        "OPT-Q-v1.2",
        kind="evaluation",
        validator=False,
    )

    sources = discover_question_sources(repo)

    assert tuple(value.question_id for value in sources) == (question_id,)


def test_discovery_finds_variants_below_source_question_groups(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    first_id = "EI-BASE-VAR01-v1.2"
    second_id = "EI-BASE-VAR02-v1.2"
    _write_question(
        _variant_directory(repo, first_id),
        first_id,
        kind="variant",
    )
    _write_question(
        _variant_directory(repo, second_id),
        second_id,
        kind="variant",
    )

    sources = discover_question_sources(repo)

    assert tuple(value.question_id for value in sources) == (first_id, second_id)


def test_duplicate_variant_identity_across_groups_is_an_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    question_id = "EI-BASE-VAR01-v1.2"
    _write_question(
        _variant_directory(repo, question_id, "BASE-variants"),
        question_id,
        kind="variant",
    )
    _write_question(
        _variant_directory(repo, question_id, "OTHER-variants"),
        question_id,
        kind="variant",
    )

    with pytest.raises(QuestionSourceError, match="duplicate question identity"):
        resolve_question_source(repo, question_id)


def test_flat_dataset_question_is_not_a_supported_target_layout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    question_id = "EI-BASE-VAR01-v1.2"
    _write_question(
        repo / "datasets" / question_id,
        question_id,
        kind="variant",
    )

    with pytest.raises(QuestionSourceError, match="question source directory is missing"):
        resolve_question_source(repo, question_id)


def test_manifest_identity_must_match_the_requested_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    directory_id = "EI-Q-v1.3"
    directory = _variant_directory(repo, directory_id)
    _write_question(directory, "EI-Q-v1.2", kind="variant")

    with pytest.raises(QuestionSourceError, match="manifest identity mismatch"):
        resolve_question_source(repo, directory_id)
