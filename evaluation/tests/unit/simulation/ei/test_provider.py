from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.app.contracts import RunRecord
from simulation.ei.aggregation import AggregateMetric, AggregationPolicy
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactCandidate,
    ArtifactResolution,
    ArtifactSpec,
    QuestionProfile,
    RunScore,
)
from simulation.ei.provider import (
    PreparedQuestion,
    _artifact_resolutions_payload,
    prepare_question,
    score_record,
)


def test_public_score_contract_declares_release_sources_and_resolver_evidence() -> None:
    contract_path = (
        Path(__file__).parents[4]
        / "src"
        / "simulation"
        / "ei"
        / "contracts"
        / "ei-contract.schema.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    definitions = contract["$defs"]
    header = definitions["contractHeader"]
    run_score = definitions["runScoreDocument"]

    assert header["properties"]["id"]["const"] == "simulation.ei"
    assert header["properties"]["schema_revision"]["const"] == 2
    assert (
        definitions["runScoreContractHeader"]["allOf"][1]["properties"]
        ["document_type"]["const"]
        == "run-score"
    )
    assert {"contract", "ruleset", "question_contract", "artifacts"} <= set(
        run_score["required"]
    )
    assert "score_contract_version" not in run_score["properties"]
    assert "aggregation_policy" not in run_score["properties"]

    ruleset = definitions["rulesetRunIdentity"]
    assert {"release", "semantic_baseline"} == set(
        ruleset["required"]
    )
    question_contract = definitions["questionContractIdentity"]
    assert {
        "question_id",
        "question_kind",
        "question_root",
        "files",
        "question_inputs",
    } == set(question_contract["required"])

    artifact = definitions["artifactResolution"]
    assert {
        "role",
        "source",
        "status",
        "selected_path",
        "resolution_diagnostics",
        "candidates",
    } <= set(artifact["required"])


def test_public_artifact_payload_keeps_resolver_evidence_and_relative_paths(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    run = repository / "eval_results" / "run"
    candidate_path = run / "project" / "output.csv"
    question_path = repository / "evalsets" / "simulation" / "Q" / "data" / "input.xlsx"
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("project",),
        artifacts={
            "candidate": ArtifactSpec(
                role="candidate",
                source="candidate",
                path="project/canonical.csv",
                filenames=("output.csv",),
            ),
            "authority": ArtifactSpec(
                role="authority",
                source="question",
                path="data/input.xlsx",
            ),
        },
        components={},
        path=repository / "evalsets" / "simulation" / "Q" / "validator.yaml",
    )
    bundle = ArtifactBundle(
        run_dir=run,
        artifact_roots=(run / "project",),
        artifacts={
            "candidate": ArtifactResolution(
                role="candidate",
                status="SELECTED_FALLBACK",
                selected_path=candidate_path,
                candidates=(
                    ArtifactCandidate(
                        path=candidate_path,
                        required_coverage=1.0,
                        prompt_filename=True,
                        common_parent_suffix=1,
                        usable=True,
                    ),
                ),
                normalized={},
                resolution_diagnostics=(
                    {
                        "code": "ARTIFACT_PATH_MISMATCH",
                        "score_effect": "none",
                    },
                ),
            ),
            "authority": ArtifactResolution(
                role="authority",
                status="SELECTED_CANONICAL",
                selected_path=question_path,
                normalized={},
            ),
        },
    )

    payload = _artifact_resolutions_payload(bundle, profile, repository)
    by_role = {value["role"]: value for value in payload}

    assert by_role["candidate"]["selected_path"] == "project/output.csv"
    assert by_role["candidate"]["candidates"][0]["path"] == "project/output.csv"
    assert by_role["candidate"]["resolution_diagnostics"][0]["code"] == (
        "ARTIFACT_PATH_MISMATCH"
    )
    assert by_role["authority"]["selected_path"] == (
        "evalsets/simulation/Q/data/input.xlsx"
    )


def _record(tmp_path: Path) -> RunRecord:
    run = tmp_path / "run"
    run.mkdir()
    return RunRecord(
        run,
        "run",
        "EI",
        "Q",
        "gpt56",
        "codex",
        "noskill",
        ("2026-08-20", "0820A", ""),
        {},
    )


def _prepared(tmp_path: Path) -> PreparedQuestion:
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=("project",),
        artifacts={},
        components={},
        path=tmp_path / "validator.yaml",
    )
    return PreparedQuestion(
        question="Q",
        profile=profile,
        ruleset={
            "release": "4.13.0",
            "semantic_baseline": "ei-standard-v1",
            "checks": [],
        },
        aggregation_policy=AggregationPolicy(
            "4.13.0",
            "ei-standard",
            (),
        ),
        question_contract={
            "question_id": "Q",
            "question_kind": "evaluation",
            "question_root": "evalsets/simulation/Q",
            "files": {
                "validator": {"path": "evalsets/simulation/Q/validator.yaml"},
            },
            "question_inputs": [],
        },
        question_artifacts={},
        prepared_scorers={},
    )


def test_prepare_question_reuses_loaded_profile_for_blocked_contract_snapshot(
    tmp_path: Path,
) -> None:
    prepared = _prepared(tmp_path)
    blocked_profile = replace(
        prepared.profile,
        release_status="question-contract-incomplete",
        blocking_reasons=("missing authority",),
    )
    with (
        patch("simulation.ei.provider.load_ruleset", return_value=prepared.ruleset),
        patch(
            "simulation.ei.provider.load_aggregation_policy",
            return_value=prepared.aggregation_policy,
        ),
        patch("simulation.ei.provider.load_profile", return_value=blocked_profile),
        patch(
            "simulation.ei.provider.question_contract_snapshot",
            return_value=prepared.question_contract,
        ) as snapshot,
        patch("simulation.ei.provider.prepare_question_artifacts") as artifact_prep,
    ):
        result = prepare_question("Q", repository_root=tmp_path)

    snapshot.assert_called_once_with("Q", repo=tmp_path, profile=blocked_profile)
    artifact_prep.assert_not_called()
    assert result.profile is blocked_profile
    assert result.question_artifacts == {}


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("profile_release", "profile ruleset release"),
        ("policy_release", "aggregation policy ruleset release"),
        ("contract_question", "question contract"),
    ),
)
def test_score_record_rejects_injected_prepared_identity_mismatches(
    tmp_path: Path,
    change: str,
    message: str,
) -> None:
    record = _record(tmp_path)
    prepared = _prepared(tmp_path)
    if change == "profile_release":
        prepared = replace(
            prepared,
            profile=replace(prepared.profile, ruleset_release="4.10.0"),
        )
    elif change == "policy_release":
        prepared = replace(
            prepared,
            aggregation_policy=replace(
                prepared.aggregation_policy,
                ruleset_release="4.10.0",
            ),
        )
    else:
        prepared = replace(
            prepared,
            question_contract={
                **prepared.question_contract,
                "question_id": "OTHER",
            },
        )

    with (
        patch("simulation.ei.provider.score_run") as scorer,
        pytest.raises(ValueError, match=message),
    ):
        score_record(
            record,
            repository_root=tmp_path,
            score_id="20260820120000",
            created_at="2026-08-20T12:00:00+08:00",
            prepared_question=prepared,
        )
    scorer.assert_not_called()


def test_score_record_returns_a_complete_run_score_contract(tmp_path: Path) -> None:
    record = _record(tmp_path)
    prepared = _prepared(tmp_path)
    aggregates = tuple(
        AggregateMetric(metric_id, group, 100.0, "SCORED")
        for metric_id, group in (
            ("effectiveness.o2", "effectiveness"),
            ("key.raw", "key"),
            ("key.discrete", "key"),
            ("key.piecewise", "key"),
            ("all.raw", "all"),
        )
    )
    result = RunScore(
        "Q",
        "4.13.0",
        ArtifactBundle(record.run_dir, (), {}),
        (),
        100.0,
        "SCORED",
        aggregates=aggregates,
    )

    with patch("simulation.ei.provider.score_run", return_value=result):
        package = score_record(
            record,
            repository_root=tmp_path,
            score_id="20260820120000",
            created_at="2026-08-20T12:00:00+08:00",
            prepared_question=prepared,
        )

    assert package.payload["contract"]["document_type"] == "run-score"
    assert package.payload["score_id"] == "20260820120000"
    assert package.payload["created_at"] == "2026-08-20T12:00:00+08:00"
    assert package.payload["run"] == record.as_dict()
