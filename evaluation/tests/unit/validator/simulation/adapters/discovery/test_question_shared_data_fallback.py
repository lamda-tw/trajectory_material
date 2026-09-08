from __future__ import annotations

from dataclasses import replace

import pytest

from simulation.ei.core.adapters import resolve_artifacts
from simulation.ei.core.config import question_contract_snapshot

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    make_profile,
    write_csv_case,
)


def test_question_data_is_local_and_legacy_shared_fallback_must_be_explicit(
    tmp_path,
) -> None:
    repository, question, run = build_layout(tmp_path)
    local = question / "data/input.csv"
    shared = question.parent / "data/Q/input.csv"
    write_csv_case(local, {"headers": ["item_code"], "rows": [["LOCAL"]]})
    write_csv_case(shared, {"headers": ["item_code"], "rows": [["SHARED"]]})
    profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=(),
        canonical_path="data/input.csv",
        filenames=(),
        source="question",
    )
    local_result = resolve_artifacts(profile, run, repository).get("input")
    assert local_result.status == "SELECTED_CANONICAL"
    assert local_result.selected_path == local.resolve()

    local.unlink()
    missing_result = resolve_artifacts(profile, run, repository).get("input")
    assert missing_result.status == "MISSING"
    assert missing_result.selected_path is None

    legacy_profile = replace(profile, legacy_shared_data=True)
    shared_result = resolve_artifacts(legacy_profile, run, repository).get("input")
    assert shared_result.status == "SELECTED_CANONICAL"
    assert shared_result.selected_path == shared.resolve()

    outside = question.parent / "outside.csv"
    write_csv_case(outside, {"headers": ["item_code"], "rows": [["OUTSIDE"]]})
    escaping_profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=(),
        canonical_path="../outside.csv",
        filenames=(),
        source="question",
    )

    with pytest.raises(ValueError, match=r"must not contain '\.\.'|escapes question directory"):
        resolve_artifacts(escaping_profile, run, repository)


def test_question_snapshot_hashes_the_same_local_input_selected_at_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    repository, question, run = build_layout(tmp_path)
    local = question / "data/input.csv"
    write_csv_case(local, {"headers": ["item_code"], "rows": [["LOCAL"]]})
    profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=(),
        canonical_path="data/input.csv",
        filenames=(),
        source="question",
    )
    profile_path = repository / "evaluation/profile.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text("test", encoding="utf-8")
    profile = replace(profile, path=profile_path, question_dir=question)
    runtime = resolve_artifacts(profile, run, repository).get("input")

    from simulation.ei.core import config as config_module

    monkeypatch.setattr(config_module, "repository_root", lambda: repository)
    monkeypatch.setattr(config_module, "load_profile", lambda *_args, **_kwargs: profile)
    snapshot = question_contract_snapshot("Q", repository, repo=repository)

    assert runtime.selected_path == local.resolve()
    frozen = {value["role"]: value for value in snapshot["question_inputs"]}
    assert frozen["input"]["path"] == local.resolve().relative_to(
        repository.resolve()
    ).as_posix()
