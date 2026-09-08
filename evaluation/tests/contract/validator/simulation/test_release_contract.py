from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from simulation.ei.core.adapters import (
    _normalize_reuse_summary,
    material_quantity,
    resolve_artifacts,
)
from simulation.ei.scoring.contracts import (
    _artifact_roles_for_checks,
    validate_release_contracts,
)
from simulation.ei.core.config import (
    ConfigurationError,
    discover_questions,
    load_profile,
    load_ruleset,
    repository_root,
)
from simulation.ei.core.engine import score_components, score_run
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    CheckResult,
    ComponentConfig,
    ComponentResult,
    QuestionProfile,
    RunScore,
    RuleContext,
)
from simulation.ei.core.reporting import write_run_score
from simulation.ei.provider import prepare_question
from simulation.ei.rules.ei_standard.reuse import score_reuse
from simulation.ei.rules.ei_standard.scheduling import _candidate_plan


RECOVERED_0817_O2_EXPECTATIONS = {
    # status, substitution, authority actions, Drop, interval anchor/lag,
    # master format, week-to-month mode, exact-column contract family
    "EI-56TESTPK-VAR01-v1.2": (
        "active", "identity-only", ("install", "dismantle"), 0.0,
        "batch-finish", 4, "standard", "calendar", "A",
    ),
    "EI-56TESTPK-VAR02-v1.2": (
        "active", "identity-only", ("install",), 0.0,
        "not-applicable", None, "standard", "calendar", "A",
    ),
    "EI-56TESTPK-VAR03-v1.2": (
        "question-contract-incomplete", "identity-only",
        ("install", "dismantle"), 0.05, "batch-finish", 2,
        "standard", "calendar", "A",
    ),
    "EI-56TESTPK-VAR04-v1.2": (
        "active", "identity-only", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "standard", "calendar", "A",
    ),
    "EI-56TESTPK-VAR05-v1.2": (
        "active", "identity-only", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "standard", "calendar", "A",
    ),
    "EI-56TESTPK0002-VAR02-v1.3": (
        "active", "legacy-combination", ("install",), 0.0,
        "not-applicable", None, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR03-v1.3": (
        "question-contract-incomplete", "legacy-combination",
        ("install", "dismantle"), 0.05, "batch-finish", 2,
        "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR04-v1.3": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR05-v1.2": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR06-v1.3": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 4, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR07-v1.3": (
        "active", "identity-only", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "C",
    ),
    "EI-56TESTPK0002-VAR08-v1.2": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR09-v1.2": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR10-v1.2": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
    "EI-56TESTPK0002-VAR11-v1.2": (
        "active", "legacy-combination", ("install", "dismantle"), 0.0,
        "batch-finish", 2, "pip-city-wise", "four-week-project", "B",
    ),
}


CURRENT_NESTED_VARIANT_QUESTIONS = frozenset(
    {
        *(f"EI-56TESTPK-VAR{index:02d}-v1.2" for index in range(1, 8)),
        *(f"EI-56TESTPK0002-VAR{index:02d}-v1.2" for index in range(2, 12)),
        "EI-56TESTPK0005-VAR02-v1.2",
        "EI-56TESTPK0005-VAR03-v1.2",
        "EI-56TESTPK0005-VAR08-v1.2",
        "EI-56TESTPK0006-easy-VAR01-v1.2",
        "EI-56TESTPK0006-easy-VAR02-v1.2",
        "EI-56TESTPK0006-easy-VAR04-v1.2",
    }
)


VAR_O2_QUESTIONS = frozenset(
    {
        "EI-56TESTPK0002-VAR01-v1.2",
        "EI-56TESTPK0002-VAR02-v1.2",
        "EI-56TESTPK0002-VAR03-v1.2",
        "EI-56TESTPK0002-VAR04-v1.2",
        "EI-56TESTPK0002-VAR06-v1.2",
        "EI-56TESTPK0002-VAR07-v1.2",
        "EI-56TESTPK0005-VAR02-v1.2",
        "EI-56TESTPK0005-VAR02-v1.3",
        "EI-56TESTPK0005-VAR03-v1.2",
        "EI-56TESTPK0005-VAR03-v1.4",
        "EI-56TESTPK0005-VAR05-v1.2",
        "EI-56TESTPK0005-VAR05-v1.3",
        "EI-56TESTPK0005-VAR08-v1.2",
        "EI-56TESTPK0005-VAR08-v1.3",
        "EI-56TESTPK0006-easy-VAR01-v1.2",
        "EI-56TESTPK0006-easy-VAR01-v1.3",
        "EI-56TESTPK0006-easy-VAR02-v1.2",
        "EI-56TESTPK0006-easy-VAR03-v1.2",
        "EI-56TESTPK0006-easy-VAR03-v1.3",
        "EI-56TESTPK0006-easy-VAR04-v1.2",
        "EI-56TESTPK0006-easy-VAR04-v1.3",
        "EI-56TESTPK0006-hard-VAR02-v1.2",
        "EI-56TESTPK0006-hard-VAR03-v1.2",
        "EI-56TESTPK0006-hard-VAR04-v1.2",
    }
) | frozenset(RECOVERED_0817_O2_EXPECTATIONS) | CURRENT_NESTED_VARIANT_QUESTIONS
VAR_O2_BLOCKED = frozenset(
    {
        "EI-56TESTPK0006-easy-VAR03-v1.2",
        "EI-56TESTPK0006-hard-VAR02-v1.2",
        "EI-56TESTPK0006-hard-VAR03-v1.2",
        "EI-56TESTPK0006-hard-VAR04-v1.2",
        "EI-56TESTPK0002-VAR03-v1.3",
    }
)
FORMAL_EI_QUESTIONS = frozenset(
    {
        "EI-56TESTPK-v1.2",
        "EI-56TESTPK0002-v1.2",
        "EI-56TESTPK0005-v1.2",
        "EI-56TESTPK0006-easy-v1.2",
        "EI-56TESTPK0006-hard-v1.2",
        "EI-56TESTPK0006-hell-v1.2",
        "EI-56TESTPK0006-medium-v1.2",
        "EI-56TESTPK0007-easy-v1.2",
        "EI-56TESTPK0007-hard-v1.2",
        "EI-56TESTPK0007-medium-v1.2",
        "EI-56TESTPK0008-easy-v1.2",
        "EI-56TESTPK0008-hard-v1.2",
        "EI-56TESTPK0008-medium-v1.2",
        "EI-56TESTPK0009-easy-v1.2",
        "EI-56TESTPK0009-hard-v1.2",
        "EI-56TESTPK0009-medium-v1.2",
        "EI-56TESTPK0010-easy-v1.2",
        "EI-56TESTPK0010-hard-v1.2",
        "EI-56TESTPK0010-medium-v1.2",
        "EI-56TESTTH-v1.2",
    }
)
VAR_FULL_PROFILE_QUESTION = "EI-56TESTPK0005-VAR03-v1.3"
EXTERNAL_VARIANT_QUESTIONS = VAR_O2_QUESTIONS | {VAR_FULL_PROFILE_QUESTION}


def _normalize_query_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _derive_noskill_query(value: str) -> str:
    query = _normalize_query_newlines(value)
    prefix_offset = len("### 题目\n") if query.startswith("### 题目\n") else 0
    for skill_reference in (
        "请调用 /EIAgent-requirement-docs，",
        "请调用 /EIAgent-requirement-docs ",
    ):
        if query.startswith(skill_reference, prefix_offset):
            return (
                query[:prefix_offset]
                + query[prefix_offset + len(skill_reference) :]
            )
    return query


def requires_dataset_questions(*question_ids: str):
    """Skip external-asset freezes when the ignored datasets root is not hydrated."""

    root = repository_root() / "datasets"
    return unittest.skipUnless(
        all((root / question_id / "validator.yaml").is_file() for question_id in question_ids),
        "external datasets question package is not hydrated",
    )


class ReleaseContractTests(unittest.TestCase):
    def test_formal_ei_inputs_use_one_skill_free_query(self) -> None:
        simulation_root = repository_root() / "evalsets" / "simulation"
        questions = sorted(
            path.name
            for path in simulation_root.iterdir()
            if path.is_dir() and path.name.startswith("EI-")
        )
        self.assertEqual(set(questions), FORMAL_EI_QUESTIONS)

        aggregate_records = []
        for question in questions:
            question_dir = simulation_root / question
            prompt_files = sorted((question_dir / "prompt").glob("*.txt"))
            self.assertEqual(len(prompt_files), 1, question)
            prompt = prompt_files[0].read_text(encoding="utf-8-sig")
            self.assertFalse(
                prompt.startswith("请调用 /EIAgent-requirement-docs"),
                question,
            )

            input_dir = question_dir / "input"
            self.assertEqual(
                {path.name for path in input_dir.glob("*.jsonl")},
                {f"{question}.jsonl"},
                question,
            )
            record = json.loads(
                (input_dir / f"{question}.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(
                list(record),
                ["id", "question_type", "data_folder_name", "original_query"],
                question,
            )
            self.assertEqual(record["id"], 1, question)
            self.assertEqual(record["question_type"], "主观题", question)
            self.assertEqual(record["data_folder_name"], question, question)
            self.assertEqual(
                _normalize_query_newlines(record["original_query"]),
                _normalize_query_newlines(prompt),
                question,
            )
            aggregate_records.append(
                {
                    "id": question,
                    "question_type": "主观题",
                    "data_folder_name": question,
                    "original_query": _normalize_query_newlines(prompt),
                }
            )

        aggregate_dir = simulation_root / "input"
        self.assertEqual(
            {path.name for path in aggregate_dir.glob("*.jsonl")},
            {"simulation_20.jsonl"},
        )
        actual_aggregate = [
            json.loads(line)
            for line in (aggregate_dir / "simulation_20.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        for record in actual_aggregate:
            record["original_query"] = _normalize_query_newlines(
                record["original_query"]
            )
        self.assertEqual(actual_aggregate, aggregate_records)

    def test_formal_ei_data_excludes_duplicate_archives_and_runtime_results(
        self,
    ) -> None:
        evalsets_root = repository_root() / "evalsets"
        forbidden_suffixes = {".zip", ".rar", ".7z", ".tar", ".gz"}
        forbidden_names = {"manifest.yaml"}
        forbidden_parts = {
            "lightopt_runtime",
            "reference_answer",
            "runs",
            "scores",
            "trajectory",
        }

        for question in FORMAL_EI_QUESTIONS:
            question_dir = evalsets_root / "simulation" / question
            data_dir = question_dir / "data"
            self.assertTrue(data_dir.is_dir(), question_dir)
            prompt_text = "\n".join(
                path.read_text(encoding="utf-8-sig")
                for path in sorted((question_dir / "prompt").glob("*.txt"))
            )
            for path in data_dir.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(data_dir)
                self.assertNotIn(path.suffix.lower(), forbidden_suffixes, path)
                self.assertFalse(path.name.startswith("~$"), path)
                self.assertNotIn(path.name, forbidden_names, path)
                self.assertFalse(forbidden_parts & set(relative.parts), path)
                if "model_output" in relative.parts:
                    self.assertIn("只读模板包", prompt_text, path)
                    self.assertEqual(path.suffix.lower(), ".csv", path)
                    self.assertLess(path.stat().st_size, 4096, path)
                    self.assertLessEqual(
                        len(path.read_text(encoding="utf-8-sig").splitlines()),
                        8,
                        path,
                    )

    @requires_dataset_questions(*RECOVERED_0817_O2_EXPECTATIONS)
    def test_recovered_0817_profiles_freeze_identity_and_o2_modes(self) -> None:
        dataset_root = repository_root() / "datasets"
        exact_columns = {
            "A": {
                "site_plan": [
                    "site_name", "region", "mocn_batch", "site_action",
                    "project_week", "week_start", "status", "site_count",
                ],
                "final_material": [
                    "site_name", "region", "site_action", "item_code",
                    "required_qty", "project_week",
                ],
            },
            "B": {
                "site_plan": [
                    "site_name", "site_action", "mos_weekly_plan", "week_num",
                    "region", "site_count",
                ],
                "final_material": [
                    "site_name", "install_month", "install_wk_label",
                    "dismantle_month", "dismantle_wk_label", "item_code",
                    "required_qty", "region", "action",
                ],
            },
            "C": {
                "site_plan": [
                    "site_name", "site_action", "mos_weekly_plan", "week_num",
                    "region", "site_count",
                ],
                "final_material": [
                    "site_name", "install_month", "install_wk_label",
                    "dismantle_month", "dismantle_wk_label", "item_code",
                    "required_qty", "region", "action",
                ],
            },
        }

        for question, expected in RECOVERED_0817_O2_EXPECTATIONS.items():
            (
                release_status,
                substitution_mode,
                authority_actions,
                skip_rate,
                interval_anchor,
                interval_lag,
                master_format,
                week_to_month,
                contract_family,
            ) = expected
            with self.subTest(question=question):
                question_dir = dataset_root / question
                profile = load_profile(question)
                self.assertEqual(profile.question_id, question)
                self.assertEqual(profile.path, question_dir / "validator.yaml")
                self.assertEqual(profile.question_dir, question_dir)
                self.assertEqual(profile.question_kind, "variant")
                self.assertEqual(profile.release_status, release_status)
                self.assertEqual(
                    bool(profile.blocking_reasons),
                    release_status == "question-contract-incomplete",
                )
                self.assertEqual(set(profile.components), {"effective-delivery"})
                component = profile.components["effective-delivery"]
                self.assertEqual(component.scorer, "ei.effective-delivery")
                self.assertEqual(
                    tuple(check.check_id for check in component.checks),
                    ("effective-delivery.O2",),
                )

                parameters = component.parameters
                self.assertEqual(parameters["o2_plan_mode"], "candidate-scheduled")
                self.assertEqual(parameters["o2_site_scope"], "batch_intersection")
                self.assertEqual(parameters["o2_target_curve_mode"], "master-distribution")
                self.assertEqual(parameters["o2_substitution_mode"], substitution_mode)
                self.assertEqual(tuple(parameters["o2_authority_actions"]), authority_actions)
                self.assertEqual(float(parameters["o2_skip_rate"]), skip_rate)
                self.assertEqual(parameters["o2_master_format"], master_format)
                self.assertEqual(parameters["o2_week_to_month"], week_to_month)
                interval = parameters["o2_interval_contract"]
                self.assertEqual(interval["anchor"], interval_anchor)
                if interval_lag is None:
                    self.assertEqual(set(interval), {"anchor"})
                else:
                    self.assertEqual(interval["lag_weeks"], interval_lag)
                    self.assertEqual(interval["relation"], "minimum")

                for role in ("site_plan", "final_material"):
                    self.assertEqual(
                        profile.artifacts[role].schema_options["exact_columns"],
                        exact_columns[contract_family][role],
                    )
                self.assertEqual(
                    "substitution_source" in profile.artifacts,
                    contract_family == "B",
                )

                manifest = json.loads(
                    (question_dir / "manifest.json").read_text(encoding="utf-8")
                )
                eval_id, version_suffix = question.rsplit("-v", 1)
                self.assertEqual(manifest["eval_id"], eval_id)
                self.assertEqual(manifest["evalset_version"], f"v{version_suffix}")
                self.assertEqual(manifest["question_kind"], "variant")
                self.assertEqual(len(manifest["sources"]["runs"]), 1)
                run_source = manifest["sources"]["runs"][0]
                run_dir = question_dir / run_source["path"]
                self.assertTrue(run_dir.is_dir())
                metadata = json.loads(
                    (run_dir / "run_metadata.json").read_text(encoding="utf-8")
                )
                self.assertEqual(metadata["run_name"], run_dir.name)
                self.assertEqual(metadata["eval_id"], eval_id)
                self.assertEqual(metadata["evalset_version"], f"v{version_suffix}")

                prompt = (
                    question_dir / manifest["sources"]["prompt"]
                ).read_text(encoding="utf-8-sig")
                regular = json.loads(
                    (question_dir / "input" / f"{question}.jsonl").read_text(
                        encoding="utf-8"
                    )
                )
                noskill = json.loads(
                    (
                        question_dir
                        / "input"
                        / f"{question}_noskill.jsonl"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    _normalize_query_newlines(regular["original_query"]),
                    _normalize_query_newlines(prompt),
                )
                self.assertEqual(
                    _normalize_query_newlines(noskill["original_query"]),
                    _derive_noskill_query(regular["original_query"]),
                )
                self.assertEqual(regular["data_folder_name"], question)
                self.assertEqual(noskill["data_folder_name"], question)

    def test_all_profiles_use_v412_contract_and_active_checks_are_reachable(self) -> None:
        forbidden = {
            "reuse-accounting.R1",
            "reuse-accounting.R2",
            "reuse-accounting.R4",
            "reuse-target.O2",
        }
        required = {
            "effective-delivery.O2",
            "simulation.S4",
            "simulation.S5",
            "simulation.S6",
        }
        ruleset = load_ruleset()
        expected_checks = (
            "scheduling.C1",
            "scheduling.C2",
            "scheduling.C3",
            "scheduling.C4",
            "scheduling.C5",
            "scheduling.C6a",
            "scheduling.C6b",
            "scheduling-pacing.O1",
            "effective-delivery.O2",
            "simulation.S1",
            "simulation.S2",
            "simulation.S3",
            "simulation.S4",
            "simulation.S5",
            "simulation.S6",
            "reuse-accounting.R3",
            "reuse-accounting.R5",
            "reuse-accounting.R6",
        )
        self.assertEqual(
            ruleset["contract"],
            {
                "id": "simulation.ei",
                "schema_revision": 2,
                "document_type": "ruleset",
            },
        )
        self.assertEqual(ruleset["release"], "4.13.0")
        self.assertEqual(
            ruleset["semantic_baseline"],
            "20260829-release-and-source-path-contract",
        )
        contracts_dir = (
            repository_root()
            / "evaluation"
            / "src"
            / "simulation"
            / "ei"
            / "contracts"
        )
        schema_path = contracts_dir / "ei-contract.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$defs"]["contractHeader"]["properties"]["id"]["const"],
            "simulation.ei",
        )
        self.assertEqual(
            schema["$defs"]["contractHeader"]["properties"]["schema_revision"]["const"],
            2,
        )
        self.assertEqual(
            set(
                schema["$defs"]["contractHeader"]["properties"]["document_type"][
                    "enum"
                ]
            ),
            {
                "ruleset",
                "question-profile",
                "run-score",
                "component-result",
                "question-contract-snapshot",
                "report-aggregation",
                "report-manifest",
            },
        )
        for definition in (
            "rulesetDocument",
            "questionProfileDocument",
            "runScoreDocument",
            "componentResultDocument",
            "questionContractSnapshotDocument",
            "reportAggregationDocument",
            "reportManifestDocument",
        ):
            self.assertIn(definition, schema["$defs"])
        for retired_schema in (
            "aggregation-config.schema.json",
            "question-validator.schema.json",
            "result.schema.json",
            "run-score.schema.json",
        ):
            self.assertFalse((contracts_dir / retired_schema).exists(), retired_schema)
        self.assertEqual(tuple(ruleset["checks"]), expected_checks)
        aggregation = ruleset["aggregation"]
        self.assertEqual(aggregation["policy_id"], "ei-five-metric-aggregate")
        self.assertEqual(
            aggregation["effectiveness"]["check_id"],
            "effective-delivery.O2",
        )
        self.assertEqual(
            tuple(aggregation["key"]["rules"]),
            (
                "scheduling.C2",
                "scheduling.C6a",
                "scheduling-pacing.O1",
                "simulation.S1",
                "simulation.S5",
            ),
        )
        self.assertEqual(
            set(aggregation["all"]["rules"]),
            set(expected_checks) - {"effective-delivery.O2"},
        )
        self.assertFalse(forbidden & set(ruleset["checks"]))
        self.assertTrue(required <= set(ruleset["checks"]))
        questions = discover_questions()
        all_questions = discover_questions(include_blocked=True)
        question_kinds: dict[str, str] = {}
        blocked_questions: set[str] = set()
        profile_counts = {
            "effective-delivery.O2": 0,
            "simulation.S1": 0,
            "simulation.S4": 0,
            "simulation.S5": 0,
            "simulation.S6": 0,
        }
        absolute_quantity_questions = {
            f"EI-56TESTPK{family:04d}-{difficulty}-v1.2"
            for family in range(6, 11)
            for difficulty in ("easy", "medium", "hard")
        } | {"EI-56TESTPK0006-hell-v1.2"}
        for question in all_questions:
            profile = load_profile(question)
            question_kinds[question] = profile.question_kind
            if profile.release_status != "active":
                blocked_questions.add(question)
            self.assertEqual(profile.ruleset_release, ruleset["release"], question)
            profile_payload = yaml.safe_load(
                profile.path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                profile_payload["contract"],
                {
                    "id": "simulation.ei",
                    "schema_revision": 2,
                    "document_type": "question-profile",
                },
                question,
            )
            self.assertEqual(
                profile_payload["ruleset_release"], ruleset["release"], question
            )
            self.assertNotIn("profile_revision", profile_payload, question)
            self.assertNotIn("schema_version", profile_payload, question)
            if question in CURRENT_NESTED_VARIANT_QUESTIONS:
                self.assertEqual(profile.release_status, "active", question)
                self.assertEqual(profile.blocking_reasons, (), question)
            self.assertNotIn("total", profile.components)
            self.assertNotIn("reuse-target", profile.components)
            check_ids = {
                check.check_id
                for component in profile.components.values()
                for check in component.checks
            }
            self.assertFalse(forbidden & check_ids, question)
            for component in profile.components.values():
                for check in component.checks:
                    self.assertRegex(check.prompt_refs[0], r"prompt/.+\.txt:L\d+")
            self.assertTrue(
                all(not hasattr(component, "weight") for component in profile.components.values())
            )
            if profile.question_kind == "variant":
                if profile.release_status == "active":
                    self.assertIn("effective-delivery", profile.components)
                continue
            for check_id in profile_counts:
                profile_counts[check_id] += int(check_id in check_ids)
            simulation_parameters = profile.components["simulation"].parameters
            if question in absolute_quantity_questions:
                self.assertEqual(
                    simulation_parameters["final_bom_quantity_mode"],
                    "absolute",
                    question,
                )
                self.assertIs(
                    simulation_parameters["s6_require_inactive_time_blank"],
                    False,
                    question,
                )
            else:
                self.assertEqual(
                    simulation_parameters["final_bom_quantity_mode"],
                    "signed-action",
                    question,
                )
                self.assertIs(
                    simulation_parameters["s6_require_inactive_time_blank"],
                    True,
                    question,
                )
        self.assertEqual(
            profile_counts,
            {
                "effective-delivery.O2": 20,
                "simulation.S1": 19,
                "simulation.S4": 20,
                "simulation.S5": 20,
                "simulation.S6": 20,
            },
        )

        for question in all_questions:
            profile = load_profile(question)
            if "effective-delivery" not in profile.components:
                self.assertNotEqual(profile.release_status, "active", question)
                continue
            component = profile.components["effective-delivery"]
            self.assertEqual(component.scorer, "ei.effective-delivery")
            self.assertEqual(
                tuple(check.check_id for check in component.checks),
                ("effective-delivery.O2",),
            )
            expected_mode = component.parameters["o2_plan_mode"]
            if profile.question_kind != "variant":
                expected_mode = (
                    "fixed-authority"
                    if "-easy-" in question
                    else "candidate-scheduled"
                )
            self.assertEqual(
                component.parameters.get("o2_plan_mode", "candidate-scheduled"),
                expected_mode,
            )
            parameters = component.parameters
            if expected_mode == "candidate-scheduled":
                self.assertEqual(
                    parameters.get("o2_monthly_capacity_mode"),
                    "hard-limit",
                    question,
                )
            else:
                self.assertNotIn("o2_monthly_capacity_mode", parameters, question)
                self.assertNotIn("o2_capacity_factor", parameters, question)
            self.assertTrue(
                {
                    "o2_plan_mode",
                    "o2_group_by",
                    "o2_delivery_action",
                    "o2_planning_year",
                    "o2_site_scope",
                    "o2_project_week_source",
                    "o2_delivery_month_source",
                    "o2_site_plan_required_fields",
                    "o2_week_to_month",
                    "o2_substitution_mode",
                    "o2_traceability_mode",
                    "o2_region_scope",
                    "o2_scope_material_mode",
                    "o2_final_bom_quantity_mode",
                }
                <= set(parameters),
                question,
            )
            self.assertEqual(parameters["o2_group_by"], "region", question)
            self.assertEqual(parameters["o2_delivery_action"], "install", question)
            if profile.question_kind == "variant":
                self.assertIn(
                    parameters["o2_target_curve_mode"],
                    {"fixed-plan", "master-distribution", "completion-by-deadline"},
                    question,
                )
                self.assertIn(
                    "install",
                    parameters.get(
                        "o2_authority_actions", ("install", "dismantle")
                    ),
                    question,
                )
                roles = set(
                    _artifact_roles_for_checks(profile, ("effective-delivery.O2",))
                )
                self.assertTrue(
                    {"site_plan", "scope_input", "final_material"} <= roles,
                    question,
                )
                if expected_mode == "candidate-scheduled":
                    self.assertTrue({"master_plan", "batch_input"} <= roles, question)
                else:
                    self.assertEqual(profile.artifacts["site_plan"].source, "question")
                continue
            expected_delivery_month_source = (
                "week-start"
                if question == "EI-56TESTPK-v1.2"
                else "schedule-week"
                if question in {
                    "EI-56TESTPK0002-v1.2",
                    "EI-56TESTPK0005-v1.2",
                    "EI-56TESTPK0005-VAR03-v1.2",
                    "EI-56TESTPK0005-VAR03-v1.3",
                }
                else "week-label"
            )
            self.assertEqual(
                parameters["o2_delivery_month_source"],
                expected_delivery_month_source,
                question,
            )
            expected_site_plan_fields = (
                [
                    "site_id",
                    "region",
                    "action",
                    "project_week",
                    "week_start",
                    "status",
                    "site_count",
                    "mocn_batch_id",
                ]
                if question == "EI-56TESTPK-v1.2"
                else [
                    "site_id",
                    "action",
                    "week_label",
                    "week_num",
                    "region",
                ]
                if question in {
                    "EI-56TESTPK0005-v1.2",
                    "EI-56TESTPK0005-VAR03-v1.2",
                    "EI-56TESTPK0005-VAR03-v1.3",
                }
                else [
                    "site_id",
                    "action",
                    "week_label",
                    "week_num",
                    "region",
                    "site_count",
                ]
            )
            self.assertEqual(
                parameters["o2_site_plan_required_fields"],
                expected_site_plan_fields,
                question,
            )
            roles = set(
                _artifact_roles_for_checks(
                    profile,
                    ("effective-delivery.O2",),
                )
            )
            if "substitution_source" in roles:
                self.assertEqual(
                    profile.artifacts["substitution_source"].source,
                    "question",
                    question,
                )
            if expected_mode == "fixed-authority":
                self.assertEqual(
                    roles,
                    {
                        "site_plan",
                        "scope_input",
                        "final_material",
                        "substitution_source",
                    },
                )
                self.assertEqual(profile.artifacts["site_plan"].source, "question")
            else:
                scheduling = profile.components["scheduling"].parameters
                simulation = profile.components["simulation"].parameters
                self.assertTrue(
                    {
                        "o2_batch_kind",
                        "o2_skip_rate",
                        "o2_skip_pool_scope",
                        "o2_monthly_capacity_mode",
                        "o2_interval_contract",
                        "o2_master_format",
                        "o2_master_sheet_hint",
                    }
                    <= set(parameters),
                    question,
                )
                self.assertEqual(
                    parameters["o2_monthly_capacity_mode"],
                    "hard-limit",
                    question,
                )
                expected_o2_planning_year = (
                    2023
                    if question == "EI-56TESTTH-v1.2"
                    else scheduling["planning_year"]
                )
                self.assertEqual(
                    parameters["o2_planning_year"],
                    expected_o2_planning_year,
                    question,
                )
                self.assertEqual(
                    parameters["o2_batch_kind"], scheduling["batch_kind"], question
                )
                self.assertEqual(
                    parameters["o2_skip_rate"], scheduling["skip_rate"], question
                )
                self.assertEqual(
                    parameters["o2_skip_pool_scope"],
                    scheduling["skip_pool_scope"],
                    question,
                )
                c6a_contract = scheduling["c6a_contract"]
                expected_anchor = (
                    "site-install"
                    if c6a_contract.get("scope", "batch") == "site"
                    else "batch-finish"
                )
                self.assertEqual(
                    parameters["o2_interval_contract"],
                    {
                        "anchor": expected_anchor,
                        "relation": c6a_contract["relation"],
                        "lag_weeks": c6a_contract["lag_weeks"],
                    },
                    question,
                )
                self.assertEqual(
                    parameters["o2_master_format"],
                    scheduling.get("master_format", "standard"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_master_sheet_hint"],
                    scheduling.get("master_sheet_hint", ""),
                    question,
                )
                self.assertEqual(
                    parameters["o2_project_week_source"],
                    scheduling.get("project_week_source", "reconcile"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_week_to_month"],
                    scheduling.get("week_to_month", "calendar"),
                    question,
                )
                if parameters["o2_week_to_month"] == "four-week-project":
                    self.assertEqual(
                        parameters["o2_project_start_month"],
                        scheduling["project_start_month"],
                        question,
                    )
                self.assertEqual(
                    parameters["o2_substitution_mode"],
                    simulation.get("s1_substitution_mode", "identity-only"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_traceability_mode"],
                    simulation.get("s1_traceability_mode", "aggregate-feasible"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_region_scope"],
                    simulation.get("s1_region_scope", "exact"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_scope_material_mode"],
                    simulation.get("s5_scope_material_mode", "raw"),
                    question,
                )
                self.assertEqual(
                    parameters["o2_final_bom_quantity_mode"],
                    simulation["final_bom_quantity_mode"],
                    question,
                )
                self.assertTrue({"master_plan", "batch_input"} <= roles)

        # Formal questions remain a frozen inventory.  Training variants live
        # outside Git by contract, so locally synchronized variant packages are
        # validated above but must not make the formal release gate fail.
        self.assertEqual(
            {
                question
                for question, kind in question_kinds.items()
                if kind == "evaluation"
            },
            FORMAL_EI_QUESTIONS,
        )
        self.assertEqual(
            set(all_questions) - set(questions),
            blocked_questions,
        )

    def test_o2_policy_is_frozen_in_the_atomic_ruleset_contract(self) -> None:
        rules_path = (
            repository_root()
            / "evaluation"
            / "src"
            / "simulation"
            / "ei"
            / "rules.md"
        )
        contract = rules_path.read_text(encoding="utf-8")
        self.assertIn("`effective-delivery.O2`", contract)
        self.assertNotIn("`effective-delivery.O2` revision", contract)
        self.assertIn("ruleset release `4.13.0`", contract)
        self.assertIn("`contracts/ei-contract.schema.json`", contract)
        self.assertIn("规则和聚合不再维护独立 revision", contract)
        self.assertIn("`dismantle-absolute`", contract)
        self.assertIn("`o2_skip_pool_scope`", contract)
        self.assertIn("`o2_monthly_capacity_mode`", contract)
        self.assertIn("`MONTHLY_CAPACITY_EXCEEDED`", contract)
        self.assertIn("`anchor=site-install`", contract)
        self.assertIn("显式年份不等于 `planning_year`", contract)
        self.assertIn(
            "calendar_week = planning_year * 100 + week_num",
            contract,
        )
        self.assertIn("跨年题不得推断", contract)
        self.assertIn("`document_type=component-result`", contract)
        self.assertIn("`document_type=run-score`", contract)

    def test_s4_mode_parameters_are_rejected_by_fixed_role_gate(self) -> None:
        question = "EI-56TESTPK0006-easy-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        payload["components"]["simulation"]["parameters"][
            "s4_evidence_mode"
        ] = "warehouse"

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_with_removed_parameter(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(
            config_module,
            "_load_yaml",
            side_effect=load_with_removed_parameter,
        ):
            with self.assertRaisesRegex(ConfigurationError, "unsupported S4 parameters"):
                load_profile(question)

    def test_o2_rejects_parameters_from_other_rule_contracts(self) -> None:
        question = "EI-56TESTPK-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        payload["components"]["effective-delivery"]["parameters"][
            "c6a_contract"
        ] = {"relation": "minimum", "lag_weeks": 2}

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_with_foreign_o2_parameter(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(
            config_module,
            "_load_yaml",
            side_effect=load_with_foreign_o2_parameter,
        ):
            with self.assertRaisesRegex(
                ConfigurationError,
                r"O2 contains unsupported parameters.*c6a_contract",
            ):
                load_profile(question)

    def test_o2_variant_action_target_and_material_source_contracts_are_strict(
        self,
    ) -> None:
        question = "EI-56TESTPK-v1.2"
        profile = load_profile(question)
        original_payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        cases = (
            (
                {"o2_authority_actions": ["dismantle"]},
                r"authority_actions must be",
            ),
            (
                {"o2_target_curve_mode": "fixed-plan"},
                r"candidate-scheduled O2 cannot use",
            ),
            (
                {"o2_monthly_capacity_mode": "implicit"},
                r"requires explicit o2_monthly_capacity_mode",
            ),
            (
                {
                    "o2_monthly_capacity_mode": "not-applicable",
                    "o2_capacity_factor": 1.1,
                },
                r"may declare o2_capacity_factor only when",
            ),
            (
                {"o2_interval_contract": {"anchor": "not-applicable"}},
                r"not-applicable requires authority_actions",
            ),
            (
                {"o2_material_source_contract": {}},
                r"material-source contract must be a non-empty",
            ),
            (
                {"o2_material_source_contract": {"install": ["NEW", " new "]}},
                r"normalized-unique strings",
            ),
            (
                {"o2_material_source_missing_effect": "optional"},
                r"material-source missing effect must be blocking or diagnostic",
            ),
            (
                {"o2_material_source_missing_effect": "diagnostic"},
                r"material-source missing effect requires o2_material_source_contract",
            ),
            (
                {
                    "o2_authority_actions": ["install"],
                    "o2_material_source_contract": {"dismantle": ["DISMANTLE"]},
                },
                r"contains unscored actions",
            ),
        )

        from simulation.ei.core import config as config_module

        original_loader = config_module._load_yaml
        for updates, message in cases:
            with self.subTest(updates=updates):
                payload = yaml.safe_load(yaml.safe_dump(original_payload))
                payload["components"]["effective-delivery"]["parameters"].update(
                    updates
                )

                def load_with_invalid_variant(path: Path):
                    if path.name == "validator.yaml":
                        return payload
                    return original_loader(path)

                with patch.object(
                    config_module,
                    "_load_yaml",
                    side_effect=load_with_invalid_variant,
                ):
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_profile(question)

    def test_o2_and_scheduling_share_one_monthly_capacity_factor(self) -> None:
        question = "EI-56TESTPK0005-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        payload["components"]["effective-delivery"]["parameters"][
            "o2_capacity_factor"
        ] = 1.0

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_with_mismatched_capacity_factor(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(
            config_module,
            "_load_yaml",
            side_effect=load_with_mismatched_capacity_factor,
        ):
            with self.assertRaisesRegex(
                ConfigurationError,
                r"must use the same monthly capacity factor",
            ):
                load_profile(question)

    def test_o2_requires_a_valid_question_site_plan_contract(self) -> None:
        question = "EI-56TESTPK-v1.2"
        profile = load_profile(question)
        original_payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml
        cases = (
            (None, r"parameters are incomplete.*o2_site_plan_required_fields"),
            (["site_id", "region", "action", "unknown"], r"unique canonical"),
            (["site_id", "region", "action"], r"lacks a week field"),
        )
        for fields, message in cases:
            with self.subTest(fields=fields):
                payload = yaml.safe_load(yaml.safe_dump(original_payload))
                parameters = payload["components"]["effective-delivery"]["parameters"]
                if fields is None:
                    parameters.pop("o2_site_plan_required_fields")
                else:
                    parameters["o2_site_plan_required_fields"] = fields

                def load_with_contract(path: Path):
                    if path.name == "validator.yaml":
                        return payload
                    return original(path)

                with patch.object(
                    config_module,
                    "_load_yaml",
                    side_effect=load_with_contract,
                ):
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_profile(question)

    def test_o2_rejects_an_unknown_delivery_month_source(self) -> None:
        question = "EI-56TESTPK-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        payload["components"]["effective-delivery"]["parameters"][
            "o2_delivery_month_source"
        ] = "implicit-calendar"

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_with_unknown_source(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(
            config_module,
            "_load_yaml",
            side_effect=load_with_unknown_source,
        ):
            with self.assertRaisesRegex(
                ConfigurationError,
                "invalid delivery_month_source",
            ):
                load_profile(question)

    @requires_dataset_questions(VAR_FULL_PROFILE_QUESTION)
    def test_o2_and_scheduling_reject_unknown_anchor_and_drop_pool_scopes(
        self,
    ) -> None:
        question = "EI-56TESTPK0005-VAR03-v1.3"
        profile = load_profile(question)
        original_payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        cases = (
            ("o2_skip_pool_scope", "site", "o2_skip_pool_scope"),
            ("o2_interval_anchor", "site-finish", "invalid interval anchor"),
            ("skip_pool_scope", "site", "skip_pool_scope"),
            ("c6a_scope", "cluster", "c6a_contract.scope"),
        )

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml
        for field, value, message in cases:
            with self.subTest(field=field):
                payload = yaml.safe_load(yaml.safe_dump(original_payload))
                if field == "o2_interval_anchor":
                    payload["components"]["effective-delivery"]["parameters"][
                        "o2_interval_contract"
                    ]["anchor"] = value
                elif field == "c6a_scope":
                    payload["components"]["scheduling"]["parameters"][
                        "c6a_contract"
                    ]["scope"] = value
                elif field.startswith("o2_"):
                    payload["components"]["effective-delivery"]["parameters"][
                        field
                    ] = value
                else:
                    payload["components"]["scheduling"]["parameters"][field] = value

                def load_with_invalid_contract(path: Path):
                    if path.name == "validator.yaml":
                        return payload
                    return original(path)

                with patch.object(
                    config_module,
                    "_load_yaml",
                    side_effect=load_with_invalid_contract,
                ):
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_profile(question)

    def test_o2_time_sources_require_their_declared_site_plan_fields(self) -> None:
        from simulation.ei.core import config as config_module

        original = config_module._load_yaml
        cases = (
            (
                "EI-56TESTPK-v1.2",
                "week_start",
                r"delivery_month_source=week-start requires week_start",
            ),
            (
                "EI-56TESTTH-v1.2",
                "week_num",
                r"project_week_source=week_num requires week_num",
            ),
        )
        for question, removed_field, message in cases:
            with self.subTest(question=question, field=removed_field):
                profile = load_profile(question)
                payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
                fields = payload["components"]["effective-delivery"]["parameters"][
                    "o2_site_plan_required_fields"
                ]
                fields.remove(removed_field)

                def load_with_missing_time_field(path: Path):
                    if path.name == "validator.yaml":
                        return payload
                    return original(path)

                with patch.object(
                    config_module,
                    "_load_yaml",
                    side_effect=load_with_missing_time_field,
                ):
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_profile(question)

    def test_o2_rejects_candidate_substitution_source(self) -> None:
        question = "EI-56TESTPK0006-easy-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        payload["artifacts"]["substitution_source"]["source"] = "candidate"
        payload["artifacts"]["substitution_source"]["filenames"] = [
            Path(payload["artifacts"]["substitution_source"]["path"]).name
        ]

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_with_candidate_substitution_source(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(
            config_module,
            "_load_yaml",
            side_effect=load_with_candidate_substitution_source,
        ):
            with self.assertRaisesRegex(
                ConfigurationError,
                r"O2 substitution_source.*question",
            ):
                load_profile(question)

    def test_fixed_authority_o2_does_not_require_candidate_schedule_roles(
        self,
    ) -> None:
        question = "EI-56TESTPK0006-easy-v1.2"
        profile = load_profile(question)
        payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))
        component = payload["components"]["effective-delivery"]
        self.assertNotIn("o2_interval_contract", component["parameters"])
        self.assertNotIn("o2_batch_kind", component["parameters"])
        self.assertNotIn("o2_skip_pool_scope", component["parameters"])
        self.assertNotIn("master_plan", payload["artifacts"])
        self.assertNotIn("batch_input", payload["artifacts"])

        from simulation.ei.core import config as config_module

        original = config_module._load_yaml

        def load_fixed_contract(path: Path):
            if path.name == "validator.yaml":
                return payload
            return original(path)

        with patch.object(config_module, "_load_yaml", side_effect=load_fixed_contract):
            loaded = load_profile(question)
        self.assertEqual(
            loaded.components["effective-delivery"].parameters["o2_plan_mode"],
            "fixed-authority",
        )

    def test_s1_s5_s6_contract_parameters_are_validated(self) -> None:
        question = "EI-56TESTPK0006-easy-v1.2"
        profile = load_profile(question)
        original_payload = yaml.safe_load(profile.path.read_text(encoding="utf-8"))

        from simulation.ei.core import config as config_module

        original_loader = config_module._load_yaml
        missing = object()
        cases = (
            (
                "final_bom_quantity_mode",
                "unknown",
                "valid final_bom_quantity_mode",
            ),
            (
                "s6_require_inactive_time_blank",
                "false",
                "s6_require_inactive_time_blank",
            ),
            (
                "final_bom_quantity_mode",
                missing,
                "valid final_bom_quantity_mode",
            ),
            (
                "s6_require_inactive_time_blank",
                missing,
                "s6_require_inactive_time_blank",
            ),
        )
        for parameter, value, expected_error in cases:
            with self.subTest(parameter=parameter):
                payload = json.loads(json.dumps(original_payload))
                simulation_parameters = payload["components"]["simulation"][
                    "parameters"
                ]
                if value is missing:
                    simulation_parameters.pop(parameter)
                else:
                    simulation_parameters[parameter] = value

                def load_with_invalid_parameter(path: Path):
                    if path.name == "validator.yaml":
                        return payload
                    return original_loader(path)

                with patch.object(
                    config_module,
                    "_load_yaml",
                    side_effect=load_with_invalid_parameter,
                ):
                    with self.assertRaisesRegex(ConfigurationError, expected_error):
                        load_profile(question)

    def test_pk0002_project_month_origin_is_consistent_across_components(self) -> None:
        profile = load_profile("EI-56TESTPK0002-v1.2")
        for component_name in ("scheduling", "scheduling-pacing", "simulation"):
            self.assertEqual(
                profile.components[component_name].parameters["project_start_month"],
                1,
                component_name,
            )
        self.assertEqual(
            profile.components["simulation"].parameters["blackout_weeks"],
            8,
        )

    def test_release_preflight_uses_profiles_without_dynamic_implementations(self) -> None:
        questions = discover_questions()
        report = validate_release_contracts(repository_root(), questions)
        self.assertTrue(report["passed"], report["errors"])
        for question in questions:
            payload = yaml.safe_load(load_profile(question).path.read_text(encoding="utf-8"))
            self.assertNotIn("adapter", payload)
            self.assertNotIn("checks", payload)
            self.assertNotIn("prompt_score_contract", payload)
            self.assertNotIn("implementation", json.dumps(payload))

    @requires_dataset_questions("EI-56TESTPK0006-hard-VAR02-v1.2")
    def test_blocked_o2_profile_skips_artifact_preparation_and_keeps_five_metrics(
        self,
    ) -> None:
        question = "EI-56TESTPK0006-hard-VAR02-v1.2"
        with patch("simulation.ei.provider.prepare_question_artifacts") as artifact_prep:
            prepared = prepare_question(
                question,
                repository_root=repository_root(),
            )
        artifact_prep.assert_not_called()

        with patch("simulation.ei.core.engine.resolve_artifacts") as resolver:
            result = score_run(
                question,
                Path("missing-run"),
                repo=repository_root(),
                aggregation_policy=prepared.aggregation_policy,
                question_profile=prepared.profile,
                prepared_question_artifacts=prepared.question_artifacts,
                prepared_scorers=prepared.prepared_scorers,
                release=str(prepared.ruleset["release"]),
            )
        resolver.assert_not_called()
        self.assertEqual(result.status, "QUESTION_CONTRACT_INCOMPLETE")
        self.assertEqual(len(result.aggregates), 5)
        self.assertTrue(
            all(
                value.status == "QUESTION_CONTRACT_INCOMPLETE"
                and value.score is None
                and value.error
                for value in result.aggregates
            )
        )

    def test_pk_profile_accepts_prompt_compatible_warehouse_aliases(self) -> None:
        profile = load_profile("EI-56TESTPK-v1.2")
        self.assertEqual(
            profile.artifacts["scope_input"].schema_options["sheet_name"],
            "Solution Item",
        )
        self.assertEqual(
            profile.artifacts["batch_input"].schema_options["sheet_name"],
            "全表",
        )
        self.assertIn(
            "weekly_dismantle_warehouse.csv",
            profile.artifacts["reuse_warehouse"].filenames,
        )
        self.assertIn(
            "weekly_new_warehouse.csv",
            profile.artifacts["new_warehouse"].filenames,
        )

    def test_pk0002_profile_freezes_year_and_pip_region_authorities(self) -> None:
        profile = load_profile("EI-56TESTPK0002-v1.2")

        self.assertEqual(
            profile.artifacts["scope_input"].schema_options["included_years"],
            ["Y1", ""],
        )
        self.assertEqual(
            profile.artifacts["batch_input"].schema_options["sheet_name"],
            "Site Level -PIP",
        )

    @requires_dataset_questions(
        "EI-56TESTPK0005-VAR03-v1.2",
        VAR_FULL_PROFILE_QUESTION,
    )
    def test_var03_profile_and_evalset_freeze_the_site_level_prompt_contract(
        self,
    ) -> None:
        historical_question = "EI-56TESTPK0005-VAR03-v1.2"
        historical_profile = load_profile(historical_question)
        historical_effective = historical_profile.components[
            "effective-delivery"
        ].parameters
        self.assertEqual(historical_profile.ruleset_release, "4.13.0")
        self.assertEqual(
            set(historical_profile.components),
            {"effective-delivery"},
        )
        self.assertEqual(
            historical_effective["o2_final_bom_quantity_mode"],
            "signed-action",
        )
        self.assertEqual(
            historical_effective["o2_authority_actions"],
            ["install", "dismantle"],
        )
        self.assertEqual(historical_effective["o2_skip_pool_scope"], "region")
        self.assertEqual(
            historical_effective["o2_interval_contract"],
            {"anchor": "site-install", "relation": "minimum", "lag_weeks": 0},
        )
        self.assertEqual(historical_effective["o2_delivery_month_source"], "schedule-week")
        self.assertEqual(historical_effective["o2_week_to_month"], "calendar")
        historical_question_dir = (
            repository_root()
            / "datasets"
            / historical_question
        )
        historical_prompt = (
            historical_question_dir
            / "prompt"
            / "TESTPK0005-VAR03_prompt.txt"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "安装 `required_qty` 为正，拆除为负",
            historical_prompt,
        )
        historical_regular = json.loads(
            (
                historical_question_dir
                / "input"
                / f"{historical_question}.jsonl"
            ).read_text(encoding="utf-8")
        )
        historical_noskill = json.loads(
            (
                historical_question_dir
                / "input"
                / f"{historical_question}_noskill.jsonl"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            historical_regular["original_query"],
            historical_prompt.rstrip("\n"),
        )
        self.assertEqual(
            historical_noskill["original_query"],
            historical_regular["original_query"].removeprefix(
                "请调用 /EIAgent-requirement-docs，"
            ),
        )
        self.assertEqual(
            historical_regular["data_folder_name"],
            historical_question,
        )

        question = "EI-56TESTPK0005-VAR03-v1.3"
        profile = load_profile(question)
        effective = profile.components["effective-delivery"].parameters
        scheduling = profile.components["scheduling"].parameters
        simulation = profile.components["simulation"].parameters

        self.assertEqual(profile.ruleset_release, "4.13.0")
        self.assertEqual(
            effective["o2_final_bom_quantity_mode"],
            "dismantle-absolute",
        )
        self.assertEqual(
            simulation["final_bom_quantity_mode"],
            "dismantle-absolute",
        )
        self.assertEqual(effective["o2_skip_pool_scope"], "region")
        self.assertEqual(
            effective["o2_interval_contract"],
            {"anchor": "site-install", "relation": "minimum", "lag_weeks": 0},
        )
        self.assertEqual(effective["o2_delivery_month_source"], "schedule-week")
        self.assertEqual(effective["o2_week_to_month"], "calendar")
        self.assertEqual(scheduling["skip_pool_scope"], "region")
        self.assertEqual(
            scheduling["c6a_contract"],
            {
                "scope": "site",
                "direction": "install_then_dismantle",
                "relation": "minimum",
                "lag_weeks": 0,
            },
        )
        self.assertEqual(scheduling["week_to_month"], "calendar")
        self.assertEqual(simulation["repair_weeks"], 6)
        self.assertEqual(
            profile.artifacts["site_plan"].schema_options["exact_columns"],
            ["site_name", "site_action", "mos_weekly_plan", "week_num", "region"],
        )

        question_dir = repository_root() / "datasets" / question
        prompt = (
            question_dir / "prompt" / "TESTPK0005-VAR03_prompt.txt"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "拆除在 `action=dismantle` 已明确时，允许用正数绝对量或负数方向量表示",
            prompt,
        )
        manifest = json.loads(
            (question_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["eval_id"], "EI-56TESTPK0005-VAR03")
        self.assertEqual(manifest["evalset_version"], "v1.3")
        self.assertEqual(
            manifest["covered_point_count"],
            len(manifest["covered_points"]),
        )
        regular = json.loads(
            (
                question_dir / "input" / f"{question}.jsonl"
            ).read_text(encoding="utf-8")
        )
        noskill = json.loads(
            (
                question_dir
                / "input"
                / f"{question}_noskill.jsonl"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(regular["original_query"], prompt)
        self.assertEqual(
            noskill["original_query"],
            regular["original_query"].removeprefix(
                "请调用 /EIAgent-requirement-docs，"
            ),
        )
        self.assertEqual(
            regular["data_folder_name"],
            question,
        )
        data_dir = question_dir / "data"
        self.assertEqual(
            {path.name for path in data_dir.iterdir() if path.is_file()},
            {
                "Input1-新发仓库可存储物料清单_20260715a.xlsx",
                "Input2-拆除仓库可存储物料清单_20260715a.xlsx",
                "Input3-区域-Cluster-Site_全量_20260713a.xlsx",
                "Input4-Site-BOM_for Pak_Option1_20270711a.xlsx",
                "Input5-物料替代关系表_20260714a.xlsx",
                "Input6-交付主计划_全量6个月_20260714a.xlsx",
            },
        )

    @requires_dataset_questions(
        "EI-56TESTPK0005-VAR03-v1.3",
        "EI-56TESTPK0005-VAR03-v1.4",
    )
    def test_var03_v14_freezes_o2_diagnostic_contract_and_input_hashes(
        self,
    ) -> None:
        question = "EI-56TESTPK0005-VAR03-v1.4"
        profile = load_profile(question)

        self.assertEqual(profile.ruleset_release, "4.13.0")
        self.assertEqual(profile.release_status, "active")
        self.assertEqual(profile.blocking_reasons, ())
        self.assertEqual(set(profile.components), {"effective-delivery"})
        self.assertEqual(
            set(profile.artifacts),
            {
                "site_plan",
                "final_material",
                "scope_input",
                "master_plan",
                "batch_input",
                "substitution_source",
            },
        )
        self.assertEqual(
            profile.artifacts["site_plan"].schema_options["exact_columns"],
            [
                "site_name",
                "site_action",
                "mos_weekly_plan",
                "week_num",
                "region",
            ],
        )
        self.assertEqual(
            profile.artifacts["final_material"].schema_options["exact_columns"],
            [
                "site_name",
                "cluster_id",
                "install_month",
                "install_wk_label",
                "dismantle_month",
                "dismantle_wk_label",
                "item_code",
                "required_qty",
                "region",
                "action",
                "material_source",
            ],
        )
        effective = profile.components["effective-delivery"]
        parameters = effective.parameters
        self.assertEqual(
            parameters["o2_final_bom_quantity_mode"],
            "dismantle-absolute",
        )
        self.assertEqual(
            parameters["o2_material_source_contract"],
            {
                "install": ["NEW", "REUSE"],
                "dismantle": ["DISMANTLE"],
            },
        )
        self.assertEqual(
            parameters["o2_material_source_missing_effect"],
            "diagnostic",
        )
        self.assertNotIn("o2_material_source_effect", parameters)
        self.assertEqual(
            parameters["o2_interval_contract"],
            {"anchor": "site-install", "relation": "minimum", "lag_weeks": 0},
        )
        self.assertEqual(parameters["o2_skip_pool_scope"], "region")
        self.assertEqual(
            parameters["o2_authority_actions"],
            ["install", "dismantle"],
        )
        self.assertTrue(
            any(":L162 " in value for value in effective.checks[0].prompt_refs),
            effective.checks[0].prompt_refs,
        )

        question_dir = repository_root() / "datasets" / question
        historical_dir = (
            repository_root() / "datasets" / "EI-56TESTPK0005-VAR03-v1.3"
        )
        prompt_path = question_dir / "prompt" / "TESTPK0005-VAR03_prompt.txt"
        prompt = prompt_path.read_text(encoding="utf-8")
        historical_prompt = (
            historical_dir / "prompt" / "TESTPK0005-VAR03_prompt.txt"
        ).read_text(encoding="utf-8")
        prompt_lines = prompt.splitlines()
        historical_lines = historical_prompt.splitlines()
        diagnostic_line = (
            "- `cluster_id` 与 `material_source` 仍是强制交付格式要求；"
            "但在本题 O2 评分中，`cluster_id` 整列缺失，以及 "
            "`material_source` 整列缺失或值为空时，仅记录格式诊断，"
            "不使对应物料行或站点失效，也不影响有效交付站点判定；"
            "非空但不属于上述允许值的 `material_source` 仍使对应动作物料无效。"
        )
        self.assertEqual(prompt_lines[161], diagnostic_line)
        self.assertEqual(prompt_lines[:161], historical_lines[:161])
        self.assertIn(
            "`WK<n>` 与 `2027WK<n>` 视为同一兼容周表示",
            prompt_lines[162],
        )
        self.assertIn(
            "O2 严格消费当前 `action` 对应的周标签",
            prompt_lines[163],
        )
        self.assertEqual(prompt_lines[164:], historical_lines[161:])
        self.assertFalse(prompt.endswith("\n"))

        regular = json.loads(
            (question_dir / "input" / f"{question}.jsonl").read_text(
                encoding="utf-8"
            )
        )
        noskill = json.loads(
            (question_dir / "input" / f"{question}_noskill.jsonl").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(regular["original_query"], prompt)
        self.assertEqual(regular["data_folder_name"], question)
        self.assertEqual(
            noskill["original_query"],
            regular["original_query"].removeprefix(
                "请调用 /EIAgent-requirement-docs，"
            ),
        )
        self.assertEqual(noskill["data_folder_name"], question)

        manifest = json.loads(
            (question_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["eval_id"], "EI-56TESTPK0005-VAR03")
        self.assertEqual(manifest["evalset_version"], "v1.4")
        self.assertEqual(
            manifest["sources"]["prompt"],
            "prompt/TESTPK0005-VAR03_prompt.txt",
        )
        self.assertEqual(manifest["covered_point_count"], 25)
        self.assertEqual(
            manifest["covered_point_count"],
            len(manifest["covered_points"]),
        )

        data_dir = question_dir / "data"
        self.assertEqual(
            {path.name for path in data_dir.iterdir() if path.is_file()},
            {
                "Input1-新发仓库可存储物料清单_20260715a.xlsx",
                "Input2-拆除仓库可存储物料清单_20260715a.xlsx",
                "Input3-区域-Cluster-Site_全量_20260713a.xlsx",
                "Input4-Site-BOM_for Pak_Option1_20270711a.xlsx",
                "Input5-物料替代关系表_20260714a.xlsx",
                "Input6-交付主计划_全量6个月_20260714a.xlsx",
            },
        )

    @requires_dataset_questions(
        "EI-56TESTPK0005-VAR02-v1.3",
        "EI-56TESTPK0005-VAR05-v1.3",
        "EI-56TESTPK0005-VAR08-v1.3",
    )
    def test_var02_var05_var08_v13_freeze_o2_format_diagnostic_contracts(
        self,
    ) -> None:
        expected_data_files = {
            "Input1-新发仓库可存储物料清单_20260715a.xlsx",
            "Input2-拆除仓库可存储物料清单_20260715a.xlsx",
            "Input3-区域-Cluster-Site_全量_20260713a.xlsx",
            "Input4-Site-BOM_for Pak_Option1_20270711a.xlsx",
            "Input5-物料替代关系表_20260714a.xlsx",
            "Input6-交付主计划_全量6个月_20260714a.xlsx",
        }
        cases = {
            "VAR02": {
                "quantity_mode": "dismantle-absolute",
                "source_contract": {
                    "install": ["NEW", "REUSE"],
                    "dismantle": ["DISMANTLE"],
                },
                "covered_point_count": 23,
                "quantity_line": 158,
                "format_line": 160,
                "week_line": 161,
                "time_line": 162,
            },
            "VAR05": {
                "quantity_mode": "signed-action",
                "source_contract": {"install": ["NEW"]},
                "covered_point_count": 22,
                "quantity_line": 153,
                "format_line": 154,
                "week_line": 155,
                "time_line": 156,
            },
            "VAR08": {
                "quantity_mode": "dismantle-absolute",
                "source_contract": {
                    "install": ["NEW", "REUSE"],
                    "dismantle": ["DISMANTLE"],
                },
                "covered_point_count": 25,
                "quantity_line": 160,
                "format_line": 162,
                "week_line": 163,
                "time_line": 164,
            },
        }
        expected_site_plan_columns = [
            "site_name",
            "site_action",
            "mos_weekly_plan",
            "week_num",
            "region",
        ]
        expected_final_columns = [
            "site_name",
            "cluster_id",
            "install_month",
            "install_wk_label",
            "dismantle_month",
            "dismantle_wk_label",
            "item_code",
            "required_qty",
            "region",
            "action",
            "material_source",
        ]

        for variant, expected in cases.items():
            with self.subTest(variant=variant):
                question = f"EI-56TESTPK0005-{variant}-v1.3"
                profile = load_profile(question)
                self.assertEqual(profile.question_id, question)
                self.assertEqual(profile.ruleset_release, "4.13.0")
                self.assertEqual(profile.release_status, "active")
                self.assertEqual(profile.blocking_reasons, ())
                self.assertEqual(set(profile.components), {"effective-delivery"})
                self.assertEqual(
                    set(profile.artifacts),
                    {
                        "site_plan",
                        "final_material",
                        "scope_input",
                        "master_plan",
                        "batch_input",
                        "substitution_source",
                    },
                )
                self.assertEqual(
                    profile.artifacts["site_plan"].schema_options["exact_columns"],
                    expected_site_plan_columns,
                )
                self.assertEqual(
                    profile.artifacts["final_material"].schema_options["exact_columns"],
                    expected_final_columns,
                )
                effective = profile.components["effective-delivery"]
                parameters = effective.parameters
                self.assertEqual(
                    parameters["o2_final_bom_quantity_mode"],
                    expected["quantity_mode"],
                )
                self.assertEqual(
                    parameters["o2_material_source_contract"],
                    expected["source_contract"],
                )
                self.assertEqual(
                    parameters["o2_material_source_missing_effect"],
                    "diagnostic",
                )
                self.assertEqual(parameters["o2_skip_pool_scope"], "region")
                self.assertTrue(
                    any(
                        f":L{expected['format_line']} " in value
                        for value in effective.checks[0].prompt_refs
                    ),
                    effective.checks[0].prompt_refs,
                )

                question_dir = repository_root() / "datasets" / question
                prompt_name = f"TESTPK0005-{variant}_prompt.txt"
                prompt = (question_dir / "prompt" / prompt_name).read_text(
                    encoding="utf-8"
                )
                lines = prompt.splitlines()
                quantity_line = lines[int(expected["quantity_line"]) - 1]
                if expected["quantity_mode"] == "dismantle-absolute":
                    self.assertIn(
                        "允许用正数绝对量或负数方向量表示",
                        quantity_line,
                    )
                else:
                    self.assertIn("`required_qty` 为正", quantity_line)
                format_line = lines[int(expected["format_line"]) - 1]
                self.assertIn("额外的 `site_count`", format_line)
                self.assertIn("`cluster_id` 整列缺失", format_line)
                self.assertIn("`material_source` 整列缺失或值为空", format_line)
                self.assertIn("非空但不属于本题允许值", format_line)
                self.assertIn(
                    "`WK<n>` 与 `2027WK<n>` 视为同一兼容周表示",
                    lines[int(expected["week_line"]) - 1],
                )
                self.assertIn(
                    "O2 严格消费当前 `action` 对应的周标签",
                    lines[int(expected["time_line"]) - 1],
                )
                self.assertFalse(prompt.endswith("\n"))

                expected_files = {
                    "manifest.json",
                    "validator.yaml",
                    f"input/{question}.jsonl",
                    f"input/{question}_noskill.jsonl",
                    f"prompt/{prompt_name}",
                }
                actual_files = {
                    path.relative_to(question_dir).as_posix()
                    for path in question_dir.rglob("*")
                    if path.is_file()
                }
                self.assertTrue(expected_files <= actual_files)
                regular = json.loads(
                    (question_dir / "input" / f"{question}.jsonl").read_text(
                        encoding="utf-8"
                    )
                )
                noskill = json.loads(
                    (
                        question_dir
                        / "input"
                        / f"{question}_noskill.jsonl"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(regular["original_query"], prompt)
                self.assertEqual(regular["data_folder_name"], question)
                self.assertEqual(
                    noskill["original_query"],
                    regular["original_query"].removeprefix(
                        "请调用 /EIAgent-requirement-docs，"
                    ),
                )
                self.assertEqual(noskill["data_folder_name"], question)

                manifest = json.loads(
                    (question_dir / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["schema_version"], "1.0")
                self.assertEqual(
                    manifest["eval_id"],
                    f"EI-56TESTPK0005-{variant}",
                )
                self.assertEqual(manifest["evalset_version"], "v1.3")
                self.assertEqual(
                    manifest["sources"]["prompt"],
                    f"prompt/{prompt_name}",
                )
                self.assertEqual(
                    manifest["covered_point_count"],
                    expected["covered_point_count"],
                )
                self.assertEqual(
                    manifest["covered_point_count"],
                    len(manifest["covered_points"]),
                )

                data_dir = question_dir / "data"
                self.assertEqual(
                    {path.name for path in data_dir.iterdir() if path.is_file()},
                    expected_data_files,
                )

    @requires_dataset_questions(
        "EI-56TESTPK0006-easy-VAR01-v1.2",
        "EI-56TESTPK0006-easy-VAR01-v1.3",
        "EI-56TESTPK0006-easy-VAR03-v1.2",
        "EI-56TESTPK0006-easy-VAR03-v1.3",
        "EI-56TESTPK0006-easy-VAR04-v1.2",
        "EI-56TESTPK0006-easy-VAR04-v1.3",
    )
    def test_easy_var_v13_freezes_final_dismantle_magnitude_without_changing_inputs(
        self,
    ) -> None:
        cases = {
            "VAR01": {"prepared_quantity_line": 97, "final_quantity_line": 162},
            "VAR03": {"prepared_quantity_line": 98, "final_quantity_line": 163},
            "VAR04": {"prepared_quantity_line": 98, "final_quantity_line": 163},
        }
        final_contract = (
            "安装 `required_qty` 必须为正数；当 `action=dismantle` 已明确时，"
            "拆除 `required_qty` 可用正数幅值或负数方向量表示，评分按绝对数量核算。"
        )

        for variant, lines in cases.items():
            with self.subTest(variant=variant):
                historical_question = f"EI-56TESTPK0006-easy-{variant}-v1.2"
                question = f"EI-56TESTPK0006-easy-{variant}-v1.3"
                prompt_name = f"TESTPK0006-easy-{variant}_prompt.txt"
                historical_dir = repository_root() / "datasets" / historical_question
                question_dir = repository_root() / "datasets" / question

                historical_profile = load_profile(historical_question)
                profile = load_profile(question)
                historical_effective = historical_profile.components[
                    "effective-delivery"
                ]
                effective = profile.components["effective-delivery"]
                self.assertEqual(
                    historical_profile.release_status,
                    "question-contract-incomplete",
                )
                self.assertEqual(profile.release_status, "active")
                self.assertEqual(profile.blocking_reasons, ())
                self.assertEqual(profile.ruleset_release, "4.13.0")
                self.assertEqual(set(profile.components), {"effective-delivery"})
                self.assertEqual(
                    effective.parameters["o2_final_bom_quantity_mode"],
                    "dismantle-absolute",
                )
                self.assertEqual(effective.parameters, historical_effective.parameters)
                self.assertTrue(
                    any(
                        f":L{lines['final_quantity_line']}" in reference
                        for reference in effective.checks[0].prompt_refs
                    ),
                    effective.checks[0].prompt_refs,
                )

                historical_prompt = (
                    historical_dir / "prompt" / prompt_name
                ).read_text(encoding="utf-8")
                prompt = (question_dir / "prompt" / prompt_name).read_text(
                    encoding="utf-8"
                )
                historical_lines = historical_prompt.splitlines()
                prompt_lines = prompt.splitlines()
                self.assertEqual(len(prompt_lines), len(historical_lines))
                self.assertEqual(
                    [
                        index + 1
                        for index, (old, new) in enumerate(
                            zip(historical_lines, prompt_lines, strict=True)
                        )
                        if old != new
                    ],
                    [lines["final_quantity_line"]],
                )
                self.assertEqual(
                    prompt_lines[lines["prepared_quantity_line"] - 1],
                    historical_lines[lines["prepared_quantity_line"] - 1],
                )
                self.assertIn(
                    "安装为正数，拆除为负数",
                    prompt_lines[lines["prepared_quantity_line"] - 1],
                )
                self.assertIn(
                    final_contract,
                    prompt_lines[lines["final_quantity_line"] - 1],
                )

                regular = json.loads(
                    (question_dir / "input" / f"{question}.jsonl").read_text(
                        encoding="utf-8"
                    )
                )
                noskill = json.loads(
                    (
                        question_dir
                        / "input"
                        / f"{question}_noskill.jsonl"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(regular["original_query"], prompt)
                self.assertEqual(regular["data_folder_name"], question)
                self.assertEqual(
                    noskill["original_query"],
                    regular["original_query"].removeprefix(
                        "请调用 /EIAgent-requirement-docs，"
                    ),
                )
                self.assertEqual(noskill["data_folder_name"], question)

                historical_manifest = json.loads(
                    (historical_dir / "manifest.json").read_text(encoding="utf-8")
                )
                manifest = json.loads(
                    (question_dir / "manifest.json").read_text(encoding="utf-8")
                )
                historical_manifest["evalset_version"] = "v1.3"
                historical_manifest["sources"].pop("runs", None)
                manifest["sources"].pop("runs", None)
                self.assertEqual(manifest, historical_manifest)
                self.assertEqual(
                    manifest["covered_point_count"],
                    len(manifest["covered_points"]),
                )

                historical_data = historical_dir / "data"
                data_dir = question_dir / "data"
                historical_files = {
                    path.name: path.read_bytes()
                    for path in historical_data.iterdir()
                    if path.is_file()
                }
                current_files = {
                    path.name: path.read_bytes()
                    for path in data_dir.iterdir()
                    if path.is_file()
                }
                self.assertEqual(current_files, historical_files)

    def test_th_profile_uses_prompt_continuous_project_week_coordinate(self) -> None:
        profile = load_profile("EI-56TESTTH-v1.2")
        scheduling = profile.components["scheduling"]
        simulation = profile.components["simulation"]

        self.assertEqual(profile.ruleset_release, "4.13.0")
        self.assertEqual(scheduling.parameters["project_week_source"], "week_num")
        self.assertEqual(simulation.parameters["project_week_source"], "week_num")
        self.assertEqual(simulation.parameters["s6_week_kind"], "iso")
        for check_id in ("scheduling.C6a", "scheduling.C6b"):
            check = next(item for item in scheduling.checks if item.check_id == check_id)
            self.assertTrue(
                any(":L125" in reference for reference in check.prompt_refs),
                check.prompt_refs,
            )


class QuantityContractTests(unittest.TestCase):
    def test_decimal_semantic_integer_is_accepted_without_tolerance(self) -> None:
        self.assertEqual(material_quantity(12), 12)
        self.assertEqual(material_quantity(12.0), 12)
        self.assertEqual(material_quantity("12.000"), 12)
        self.assertEqual(material_quantity("-3.0"), -3)

    def test_fraction_blank_nan_and_infinity_are_rejected(self) -> None:
        for value in (12.5, "12.0001", "", float("nan"), float("inf"), "x"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    material_quantity(value)


class ArtifactResolverContractTests(unittest.TestCase):
    def _profile(self, root: Path, schema: str = "ei.site-plan") -> QuestionProfile:
        path = root / "profile.yaml"
        path.write_text("test", encoding="utf-8")
        return QuestionProfile(
            question_id="Q",
            ruleset_release="4.13.0",
            artifact_roots=("project/model_output",),
            artifacts={
                "candidate": ArtifactSpec(
                    role="candidate",
                    source="candidate",
                    path="project/model_output/canonical/site_plan.csv",
                    filenames=("site_plan.csv", "plan.xlsx"),
                    schema=schema,
                    required=True,
                )
            },
            components={},
            path=path,
        )

    def _layout(self, base: Path) -> tuple[Path, Path]:
        repo = base / "repo"
        run = repo / "eval_results" / "run"
        (repo / "evalsets" / "simulation" / "Q").mkdir(parents=True)
        (run / "project" / "model_output").mkdir(parents=True)
        return repo, run

    def test_search_is_bounded_to_configured_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            base = Path(value)
            repo, run = self._layout(base)
            outside = run / "unrelated"
            outside.mkdir()
            pd.DataFrame({"site_name": ["outside"], "site_action": ["install"]}).to_csv(
                outside / "site_plan.csv", index=False
            )
            resolution = resolve_artifacts(self._profile(base), run, repo).get("candidate")
            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.status, "MISSING")
            self.assertEqual(resolution.candidates, ())

    def test_complete_fallbacks_use_filename_before_directory_rank(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            base = Path(value)
            repo, run = self._layout(base)
            output = run / "project" / "model_output"
            exact = output / "far"
            exact.mkdir()
            frame = pd.DataFrame({"site_name": ["x"], "site_action": ["install"]})
            frame.to_csv(exact / "site_plan.csv", index=False)
            canonical_parent = output / "canonical"
            canonical_parent.mkdir()
            frame.to_excel(canonical_parent / "plan.xlsx", index=False)
            resolution = resolve_artifacts(self._profile(base), run, repo).get("candidate")
            self.assertEqual(resolution.status, "SELECTED_FALLBACK")
            self.assertEqual(
                resolution.selected_path,
                (exact / "site_plan.csv").resolve(),
            )
            self.assertEqual(
                resolution.resolution_diagnostics[0]["code"],
                "ARTIFACT_PATH_MISMATCH",
            )

    def test_header_only_candidate_is_not_usable(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            base = Path(value)
            repo, run = self._layout(base)
            path = run / "project" / "model_output" / "site_plan.csv"
            pd.DataFrame(columns=["site_name", "site_action"]).to_csv(path, index=False)
            resolution = resolve_artifacts(self._profile(base), run, repo).get("candidate")
            self.assertEqual(resolution.status, "HEADER_ONLY")
            self.assertIsNone(resolution.selected_path)

    def test_warehouse_duplicate_key_is_not_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            base = Path(value)
            repo, run = self._layout(base)
            frame = pd.DataFrame(
                {
                    "item_code": ["A", "A"],
                    "project_week": [1, 1],
                    "opening": [1, 1],
                    "inbound": [0, 0],
                    "outbound": [0, 0],
                    "closing": [1, 1],
                }
            )
            frame.to_csv(run / "project" / "model_output" / "site_plan.csv", index=False)
            resolution = resolve_artifacts(self._profile(base, "ei.warehouse"), run, repo).get("candidate")
            self.assertEqual(resolution.normalized, {})
            self.assertTrue(resolution.usable)
            self.assertIn("DUPLICATE_KEY", {issue["code"] for issue in resolution.validation_issues})


class BusinessRuleContractTests(unittest.TestCase):
    def test_invalid_action_row_is_retained_as_candidate_evidence(self) -> None:
        frame = pd.DataFrame(
            {
                "site_name": ["A", "B"],
                "site_action": ["install", "invalid"],
                "region": ["R", "R"],
            }
        )
        plan = _candidate_plan(frame)
        self.assertEqual(len(plan), 2)
        self.assertIn("r|b|invalid", set(plan["action_key"]))

    def _r6_context(
        self,
        frame: pd.DataFrame,
    ) -> RuleContext:
        component = ComponentConfig(
            name="reuse-accounting",
            scorer="ei.reuse",
            checks=(CheckConfig("reuse-accounting.R6", ("prompt.txt:L1",)),),
            parameters={},
        )
        profile = QuestionProfile(
            question_id="Q",
            ruleset_release="4.13.0",
            artifact_roots=("output",),
            artifacts={},
            components={"reuse-accounting": component},
            path=Path("profile.yaml"),
        )
        resolution = ArtifactResolution(
            role="reuse_by_region",
            status="SELECTED_CANONICAL",
            selected_path=Path("reuse_by_region.csv"),
            table=frame,
            normalized=_normalize_reuse_summary(frame),
        )
        return RuleContext(
            question=profile,
            component=component,
            artifacts=ArtifactBundle(Path("run"), (), {"reuse_by_region": resolution}),
        )

    def test_r6_scores_both_rate_families_for_each_item_and_ignores_summary(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5 + ["B"] * 5 + ["Grand Summary"] * 5,
                "metric": [
                    "Dismantled", "Inter-Site Reuse", "New Proposal",
                    "reuse rate (拆除重部署率)",
                    "all scope reuse rate (整体Scope利旧率)",
                ] * 3,
                "Region-1": [10, 5, 15, None, None, 4, 1, 3, None, None, 999, 1, 1, None, None],
                "Total": [10, 5, 15, "50%", "25%", 4, 1, 3, "25%", "25%", 999, 1, 1, "99%", "99%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 100.0)
        self.assertEqual(result[0].status, "PASS")
        self.assertEqual(result[0].evidence["item_count"], 2)
        self.assertEqual(result[0].evidence["summary_rows_ignored"], 5)

    def test_r6_scores_primary_and_all_scope_as_two_equal_continuous_halves(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5 + ["B"] * 5,
                "metric": [
                    "Dismantled", "Inter-Site Reuse", "New Proposal",
                    "reuse rate (拆除重部署率)",
                    "all scope reuse rate (整体Scope利旧率)",
                ] * 2,
                "Total": [10, 5, 15, "50%", "99%", 4, 1, 3, "25%", "25%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 75.0)
        families = result[0].evidence["families"]
        self.assertEqual(families["primary_rate"]["score_contribution"], 50.0)
        self.assertEqual(families["all_scope_rate"]["score_contribution"], 25.0)

    def test_r6_candidate_display_precision_cannot_create_large_tolerance(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5,
                "metric": [
                    "Dismantled",
                    "Inter-Site Reuse",
                    "New Proposal",
                    "reuse rate (拆除重部署率)",
                    "all scope reuse rate (整体Scope利旧率)",
                ],
                "Total": [3, 1, 2, "33%", "33%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 0.0)
        self.assertTrue(
            all(value["tolerance"] <= 0.0001 for value in result[0].evidence["failures"])
        )

    def test_r6_missing_or_unrelated_rate_rows_fail_the_affected_item_family(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5,
                "metric": [
                    "Dismantled", "Inter-Site Reuse", "New Proposal",
                    "reuse rate forecast",
                    "all scope reuse rate (整体Scope利旧率)",
                ],
                "Total": [10, 5, 15, "50%", "25%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 50.0)
        self.assertEqual(result[0].evidence["failures"][0]["status"], "MISSING_RATE_ROW")

    def test_r6_duplicate_correct_rate_rows_still_fail_that_item_family(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 6,
                "metric": [
                    "Dismantled", "Inter-Site Reuse", "New Proposal",
                    "reuse rate (拆除重部署率)",
                    "reuse rate (拆除重部署率)",
                    "all scope reuse rate (整体Scope利旧率)",
                ],
                "Total": [10, 5, 15, "50%", "50%", "25%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 50.0)
        self.assertEqual(result[0].evidence["failures"][0]["status"], "DUPLICATE_RATE_ROW")

    def test_r6_does_not_guess_that_bare_50_means_50_percent(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5,
                "metric": ["Dismantled", "Inter-Site Reuse", "New Proposal", "reuse rate (拆除重部署率)", "all scope reuse rate (整体Scope利旧率)"],
                "Total": [10, 5, 15, 50, "25%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 50.0)

    def test_r6_invalid_quantity_total_only_fails_the_affected_item_formulas(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5 + ["B"] * 5,
                "metric": [
                    "Dismantled", "Inter-Site Reuse", "New Proposal",
                    "reuse rate (拆除重部署率)",
                    "all scope reuse rate (整体Scope利旧率)",
                ] * 2,
                "Total": [10, 5, 15, 0.5, 0.25, "bad", 1, 2, "50%", "33.33%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 75.0)
        failures = result[0].evidence["failures"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["item"], "b")
        self.assertEqual(failures[0]["family"], "primary_rate")

    def test_r6_zero_denominators_are_not_applicable_per_item(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["A"] * 5,
                "metric": ["Dismantled", "Inter-Site Reuse", "New Proposal", "reuse rate (拆除重部署率)", "all scope reuse rate (整体Scope利旧率)"],
                "Total": [0, 0, 0, None, None],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 100.0)
        families = result[0].evidence["families"]
        self.assertEqual(families["primary_rate"]["not_applicable_coordinates"], 1)
        self.assertEqual(families["all_scope_rate"]["not_applicable_coordinates"], 1)

    def test_r6_grand_summary_without_item_rows_is_missing_item_evidence(self) -> None:
        frame = pd.DataFrame(
            {
                "item_code": ["Grand Summary"] * 5,
                "metric": ["Dismantled", "Inter-Site Reuse", "New Proposal", "reuse rate (拆除重部署率)", "all scope reuse rate (整体Scope利旧率)"],
                "Total": [10, 5, 15, "50%", "25%"],
            }
        )
        result = score_reuse(self._r6_context(frame))
        self.assertEqual(result[0].score, 0.0)
        self.assertEqual(result[0].reason_code, "MISSING_ITEM_RATE_EVIDENCE")


class EngineAndReportingContractTests(unittest.TestCase):
    def test_missing_unrelated_required_artifact_does_not_preempt_component(self) -> None:
        component = ComponentConfig(
            "simulation",
            "ei.simulation",
            (CheckConfig("simulation.S3", ("prompt/x.txt:L1",)),),
            {},
        )
        profile = QuestionProfile(
            "Q",
            "4.13.0",
            ("output",),
            {
                "unrelated": ArtifactSpec(
                    "unrelated",
                    "candidate",
                    "unrelated.csv",
                    ("unrelated.csv",),
                    required=True,
                )
            },
            {"simulation": component},
            Path("profile.yaml"),
        )
        bundle = ArtifactBundle(
            Path("run"),
            (),
            {
                "unrelated": ArtifactResolution(
                    "unrelated",
                    "MISSING",
                    None,
                    error="missing",
                )
            },
        )
        scored = (
            CheckResult(
                "simulation.S3",
                "S3",
                100,
                "PASS",
                "",
                "ok",
            ),
        )

        with patch.dict(
            "simulation.ei.core.engine.SCORERS",
            {"ei.simulation": lambda _context: scored},
        ):
            result = score_components(profile, bundle)

        self.assertEqual(result[0].status, "SCORED")
        self.assertEqual(result[0].checks[0].score, 100)

    def test_medium_contract_enters_artifact_resolution(self) -> None:
        bundle = ArtifactBundle(Path("run"), (), {})
        with (
            patch(
                "simulation.ei.core.engine.resolve_artifacts",
                return_value=bundle,
            ) as resolver,
            patch("simulation.ei.core.engine.score_components", return_value=()),
        ):
            result = score_run(
                "EI-56TESTPK0006-medium-v1.2",
                Path("run"),
            )

        resolver.assert_called_once()
        self.assertEqual(result.status, "EVALUATOR_ERROR")
        self.assertIsNone(result.total_score)
        self.assertEqual(result.components, ())

    def test_score_run_resolves_artifacts_once(self) -> None:
        profile = load_profile("EI-56TESTPK0005-v1.2")
        bundle = ArtifactBundle(Path("run"), (), {})
        component = ComponentResult(
            question_id=profile.question_id,
            component="reuse-accounting",
            checks=(
                CheckResult(
                    check_id="reuse-accounting.R6",
                    name="R6",
                    score=100,
                    status="PASS",
                    reason_code="",
                    explanation="ok",
                ),
            ),
            status="SCORED",
        )
        with (
            patch("simulation.ei.core.engine.load_profile", return_value=profile),
            patch("simulation.ei.core.engine.resolve_artifacts", return_value=bundle) as resolver,
            patch("simulation.ei.core.engine.score_components", return_value=(component,)),
            patch("simulation.ei.core.engine.load_ruleset", return_value={"release": "4.13.0"}),
        ):
            result = score_run(
                profile.question_id,
                Path("run"),
                components=("reuse-accounting",),
            )
        resolver.assert_called_once()
        self.assertIsNone(result.total_score)

    def test_reporting_writes_canonical_component_and_total_pairs(self) -> None:
        check = CheckResult("reuse-accounting.R6", "R6", 100, "PASS", "", "ok")
        component = ComponentResult("Q", "reuse-accounting", (check,), "SCORED")
        score = RunScore("Q", "4.13.0", ArtifactBundle(Path("run"), (), {}), (component,), 100, "SCORED")
        with tempfile.TemporaryDirectory() as value:
            paths = write_run_score(score, Path(value))
            self.assertEqual(set(paths), {"reuse-accounting.json", "reuse-accounting.md", "total.json", "total.md"})
            payload = json.loads(paths["reuse-accounting.json"].read_text(encoding="utf-8"))
            self.assertEqual(
                payload["contract"],
                {
                    "id": "simulation.ei",
                    "schema_revision": 2,
                    "document_type": "component-result",
                },
            )
            self.assertEqual(payload["meta"]["ruleset_release"], "4.13.0")
            self.assertNotIn("schema_version", payload)
            self.assertNotIn("validator_release", payload["meta"])
            self.assertFalse(payload["meta"]["runtime_gt_access"])
            self.assertEqual(payload["result"]["checks"][0]["id"], "reuse-accounting.R6")
            self.assertEqual(payload["result"]["checks"][0]["prompt_refs"], [])

    def test_reporting_keeps_all_adapter_issues_and_prompt_references(self) -> None:
        issues = tuple(
            {"code": "X", "affected_unit_ids": [f"unit:{index}"]}
            for index in range(25)
        )
        resolution = ArtifactResolution(
            "warehouse",
            "SELECTED_CANONICAL",
            Path("run/warehouse.csv"),
            table=pd.DataFrame({"x": [1]}),
            normalized={},
            validation_issues=issues,
        )
        check = CheckResult(
            "simulation.S3",
            "S3",
            50,
            "PARTIAL",
            "WAREHOUSE_VALIDATION_ISSUES",
            "partial",
            {
                "cells": 25,
                "valid": 24,
                "failures": [{"unit": "unit:0"}],
                "formula_evidence": {
                    "numerator": 1,
                    "denominator": 3,
                    "expected": 1 / 3,
                },
            },
            ("prompt/x.txt:L10",),
        )
        component = ComponentResult("Q", "simulation", (check,), "SCORED")
        score = RunScore(
            "Q",
            "4.13.0",
            ArtifactBundle(Path("run"), (), {"warehouse": resolution}),
            (component,),
            50,
            "SCORED",
        )
        with tempfile.TemporaryDirectory() as value:
            paths = write_run_score(score, Path(value))
            payload = json.loads(paths["simulation.json"].read_text(encoding="utf-8"))
            markdown = paths["simulation.md"].read_text(encoding="utf-8")

        self.assertEqual(len(payload["artifacts"][0]["validation_issues"]), 25)
        self.assertEqual(
            payload["result"]["checks"][0]["prompt_refs"],
            ["prompt/x.txt:L10"],
        )
        self.assertIn("prompt/x.txt:L10", markdown)
        self.assertIn("产物解析", markdown)
        self.assertIn("warehouse.csv", markdown)
        self.assertIn("证据摘要", markdown)
        self.assertIn("formula_evidence", markdown)

if __name__ == "__main__":
    unittest.main()
