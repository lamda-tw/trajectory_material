import json
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.ei.reports import service as report_service
from simulation.app.contracts import (
    RunRecord,
    ScorePackage,
    SelectionGroup,
    SelectionPlan,
)
from simulation.app.persistence import ScoreStore
from simulation.ei.core.config import contract_header
from simulation.ei.reports.service import (
    SHEET_NAMES,
    _node_command,
    _render_workbook,
    _report_environment,
    _workbook_sheets,
    build_report,
    freeze_aggregation,
    validate_report_runtime,
)


METRICS = (
    "effectiveness.o2",
    "key.raw",
    "key.discrete",
    "key.piecewise",
    "all.raw",
)

EXPECTED_SHEETS = (
    "O2目标分天梯图",
    "五项分段分天梯图",
    "五项分段分详表",
    "五项离散分天梯图",
    "五项离散分详表",
    "五项原始分天梯图",
    "五项原始分详表",
    "全项原始分天梯图",
    "全项原始分详表",
)

RULESET_IDENTITY = {
    "release": "4.13.0",
    "semantic_baseline": "20260820-test-baseline",
}


def _question_contract(question: str) -> dict[str, object]:
    return {
        "question_id": question,
        "question_kind": "evaluation",
        "question_root": f"evalsets/simulation/{question}",
        "files": {
            "validator": {
                "path": f"evalsets/simulation/{question}/validator.yaml",
            },
            "manifest": {
                "path": f"evalsets/simulation/{question}/manifest.json",
            },
        },
        "question_inputs": [
            {
                "role": "source",
                "path": f"evalsets/simulation/{question}/data/source.xlsx",
            }
        ],
    }


def _record(
    tmp_path: Path,
    question: str,
    name: str,
    *,
    model: str = "gpt56",
) -> RunRecord:
    run = tmp_path / name
    run.mkdir()
    return RunRecord(
        run, name, "EI", question, model, "codex", "noskill",
        ("2026-08-14", name, ""), {},
    )


def _package(
    question: str,
    score: float,
    *,
    ruleset: dict[str, str] | None = None,
    question_contract: dict[str, object] | None = None,
) -> ScorePackage:
    key_contributions = [
        {
            "check_id": "scheduling.C2",
            "raw_score": score,
            "transformed_score": score,
            "weight": 1,
            "supported": True,
            "filled": False,
        }
    ]
    all_contributions = [
        {
            "check_id": "scheduling.C1",
            "raw_score": score,
            "transformed_score": score,
            "weight": 1,
            "supported": True,
            "filled": False,
        }
    ]
    aggregates = []
    for metric_id in METRICS:
        contributions = (
            all_contributions if metric_id == "all.raw"
            else key_contributions if metric_id.startswith("key.")
            else [{**key_contributions[0], "check_id": "effective-delivery.O2"}]
        )
        aggregates.append(
            {
                "id": metric_id,
                "group": metric_id.split(".")[0],
                "score": score,
                "max_score": 100.0,
                "status": "SCORED",
                "error": "",
                "contributions": contributions,
            }
        )
    payload = {
        "contract": contract_header("run-score"),
        "provider_id": "simulation.ei",
        "question": question,
        "ruleset": dict(ruleset or RULESET_IDENTITY),
        "question_contract": question_contract or _question_contract(question),
        "artifacts": [],
        "result": {
            "status": "SCORED",
            "error": "",
            "aggregates": aggregates,
            "components": [],
            "checks": [],
        },
    }
    return ScorePackage(
        "simulation.ei", question, "SCORED",
        tuple((metric_id, score) for metric_id in METRICS), payload,
    )


def _package_with_nulls(
    question: str,
    null_statuses: dict[str, str],
    *,
    result_status: str = "SCORED",
    result_error: str = "",
) -> ScorePackage:
    package = _package(question, 80)
    package.payload["result"]["status"] = result_status
    package.payload["result"]["error"] = result_error
    for aggregate in package.payload["result"]["aggregates"]:
        metric_id = aggregate["id"]
        if metric_id in null_statuses:
            aggregate["score"] = None
            aggregate["status"] = null_statuses[metric_id]
            aggregate["error"] = result_error
            aggregate["contributions"] = []
    totals = tuple(
        (aggregate["id"], aggregate["score"])
        for aggregate in package.payload["result"]["aggregates"]
    )
    return ScorePackage(
        "simulation.ei",
        question,
        result_status,
        totals,
        package.payload,
    )


def _write_score(
    store: ScoreStore,
    record: RunRecord,
    score_id: str,
    package: ScorePackage,
) -> None:
    package.payload["score_id"] = score_id
    package.payload["created_at"] = "now"
    package.payload["run"] = record.as_dict()
    store.write(record, score_id, package, created_at="now")


def test_report_averages_repeats_before_giving_each_question_one_vote(tmp_path: Path) -> None:
    q1a = _record(tmp_path, "EI-Q1-v1.2", "q1a")
    q1b = _record(tmp_path, "EI-Q1-v1.2", "q1b")
    q2 = _record(tmp_path, "EI-Q2-v1.2", "q2")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(store, q1a, score_id, _package(q1a.question, 100))
    _write_score(store, q1b, score_id, _package(q1b.question, 0))
    _write_score(store, q2, score_id, _package(q2.question, 100))
    plan = SelectionPlan(
        "average",
        (
            SelectionGroup(q1a.repeat_key, (q1a, q1b)),
            SelectionGroup(q2.repeat_key, (q2,)),
        ),
        3,
        3,
    )

    events: list[str] = []
    frozen = freeze_aggregation(
        plan,
        store,
        score_id=score_id,
        progress=lambda event, _details: events.append(event),
    )

    assert [value["metrics"]["key.raw"] for value in frozen["question_rows"]] == [50, 100]
    assert frozen["model_rows"][0]["metrics"]["key.raw"] == 75
    assert frozen["model_rows"][0]["question_count"] == 2
    assert {value["check_id"] for value in frozen["all_rows"]} == {"scheduling.C1"}
    assert {value["check_id"] for value in frozen["key_rows"]} == {"scheduling.C2"}
    assert frozen["ruleset"] == RULESET_IDENTITY
    assert frozen["question_contracts"] == [
        _question_contract(question)
        for question in ("EI-Q1-v1.2", "EI-Q2-v1.2")
    ]
    assert events == [
        "aggregation_started",
        "aggregation_group_started",
        "aggregation_group_completed",
        "aggregation_group_started",
        "aggregation_group_completed",
        "aggregation_completed",
    ]


def test_report_rejects_mixed_ruleset_identities(tmp_path: Path) -> None:
    first = _record(tmp_path, "EI-Q1-v1.2", "first")
    second = _record(tmp_path, "EI-Q2-v1.2", "second")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(store, first, score_id, _package(first.question, 80))
    different_ruleset = {
        "release": "4.13.0",
        "semantic_baseline": "20260820-next-baseline",
    }
    _write_score(
        store,
        second,
        score_id,
        _package(second.question, 80, ruleset=different_ruleset),
    )
    plan = SelectionPlan(
        "latest",
        (
            SelectionGroup(first.repeat_key, (first,)),
            SelectionGroup(second.repeat_key, (second,)),
        ),
        2,
        2,
    )

    with pytest.raises(ValueError, match="report mixes ruleset identities"):
        freeze_aggregation(plan, store, score_id=score_id)


@pytest.mark.parametrize("changed_field", ["question_root", "question_inputs"])
def test_report_rejects_mixed_question_contract_identity(
    tmp_path: Path,
    changed_field: str,
) -> None:
    first = _record(tmp_path, "EI-SAME-v1.2", "first")
    second = _record(
        tmp_path,
        "EI-SAME-v1.2",
        "second",
        model="dsv4" if changed_field == "question_inputs" else "gpt56",
    )
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(store, first, score_id, _package(first.question, 80))
    changed_contract = _question_contract(second.question)
    if changed_field == "question_inputs":
        changed_contract[changed_field] = [
            {
                "role": "source",
                "path": "evalsets/simulation/EI-SAME-v1.2/data/other.xlsx",
            }
        ]
    else:
        changed_contract[changed_field] = "evalsets/simulation/OTHER"
    _write_score(
        store,
        second,
        score_id,
        _package(
            second.question,
            80,
            question_contract=changed_contract,
        ),
    )
    groups = (
        (
            SelectionGroup(first.repeat_key, (first,)),
            SelectionGroup(second.repeat_key, (second,)),
        )
        if changed_field == "question_inputs"
        else (SelectionGroup(first.repeat_key, (first, second)),)
    )
    plan = SelectionPlan("average", groups, 2, 2)

    with pytest.raises(ValueError, match="question contract identity mismatch"):
        freeze_aggregation(plan, store, score_id=score_id)


def test_report_rejects_legacy_score_without_contract_metadata(tmp_path: Path) -> None:
    record = _record(tmp_path, "EI-LEGACY-v1.2", "legacy")
    store = ScoreStore()
    score_id = "20260814120000"
    package = _package(record.question, 80)
    package.payload.pop("contract")
    package.payload.pop("ruleset")
    package.payload.pop("question_contract")
    package.payload["schema_version"] = "ei-run-score.v1"
    _write_score(store, record, score_id, package)
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )

    with pytest.raises(ValueError, match="score contract mismatch"):
        freeze_aggregation(plan, store, score_id=score_id)


def test_report_rejects_noncanonical_rule_contribution(tmp_path: Path) -> None:
    record = _record(tmp_path, "EI-BAD-CONTRIBUTION-v1.2", "bad-contribution")
    store = ScoreStore()
    score_id = "20260814120000"
    package = _package(record.question, 80)
    package.payload["result"]["aggregates"][0]["contributions"][0].pop("filled")
    _write_score(store, record, score_id, package)
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )

    with pytest.raises(ValueError, match="invalid rule contribution"):
        freeze_aggregation(plan, store, score_id=score_id)


def test_unified_schema_freezes_report_locks_and_rule_contributions() -> None:
    schema_path = (
        Path(__file__).parents[5]
        / "src"
        / "simulation"
        / "ei"
        / "contracts"
        / "ei-contract.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    report = definitions["reportAggregationDocument"]
    contribution = definitions["ruleContribution"]

    assert {"ruleset", "question_contracts"} <= set(report["required"])
    assert report["properties"]["ruleset"] == {
        "$ref": "#/$defs/rulesetRunIdentity"
    }
    assert report["properties"]["question_contracts"]["items"] == {
        "$ref": "#/$defs/questionContractIdentity"
    }
    assert set(contribution["required"]) == {
        "check_id",
        "raw_score",
        "transformed_score",
        "weight",
        "supported",
        "filled",
    }
    assert contribution["additionalProperties"] is False
    assert definitions["aggregateResult"]["properties"]["contributions"][
        "items"
    ] == {"$ref": "#/$defs/ruleContribution"}


def test_report_keeps_o2_only_all_raw_not_applicable_blank(tmp_path: Path) -> None:
    record = _record(tmp_path, "EI-O2-v1.2", "o2-only")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(
        store,
        record,
        score_id,
        _package_with_nulls(record.question, {"all.raw": "NOT_APPLICABLE"}),
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )

    frozen = freeze_aggregation(plan, store, score_id=score_id)

    assert frozen["per_run"][0]["result_status"] == "SCORED"
    assert frozen["per_run"][0]["result_error"] == ""
    assert frozen["per_run"][0]["metric_statuses"]["all.raw"] == "NOT_APPLICABLE"
    assert frozen["question_rows"][0]["metrics"]["all.raw"] is None
    assert frozen["question_rows"][0]["metric_statuses"]["all.raw"] == [
        "NOT_APPLICABLE"
    ]
    assert frozen["model_rows"][0]["metrics"]["all.raw"] is None
    all_ladder = next(
        sheet for sheet in frozen["workbook_sheets"]
        if sheet.get("metric_id") == "all.raw"
    )
    assert all_ladder["values"] == [[None]]
    assert all_ladder["row_averages"] == [None]
    assert all_ladder["column_averages"] == [None]
    assert all_ladder["overall_average"] is None
    all_detail = next(
        sheet for sheet in frozen["workbook_sheets"]
        if sheet["name"] == "全项原始分详表"
    )
    assert all_detail["rows"] == []


def test_report_keeps_question_contract_incomplete_metrics_blank(tmp_path: Path) -> None:
    record = _record(tmp_path, "EI-QCI-v1.2", "qci")
    store = ScoreStore()
    score_id = "20260814120000"
    error = "Prompt does not define the scoring authority"
    _write_score(
        store,
        record,
        score_id,
        _package_with_nulls(
            record.question,
            {metric_id: "QUESTION_CONTRACT_INCOMPLETE" for metric_id in METRICS},
            result_status="QUESTION_CONTRACT_INCOMPLETE",
            result_error=error,
        ),
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )

    frozen = freeze_aggregation(plan, store, score_id=score_id)

    assert frozen["per_run"][0]["result_status"] == "QUESTION_CONTRACT_INCOMPLETE"
    assert frozen["per_run"][0]["result_error"] == error
    assert frozen["question_rows"][0]["result_statuses"] == [
        "QUESTION_CONTRACT_INCOMPLETE"
    ]
    assert frozen["question_rows"][0]["result_errors"] == [error]
    assert all(
        value is None for value in frozen["question_rows"][0]["metrics"].values()
    )
    assert all(value is None for value in frozen["model_rows"][0]["metrics"].values())
    ladder_sheets = [
        sheet for sheet in frozen["workbook_sheets"] if sheet["kind"] == "ladder"
    ]
    assert all(sheet["values"] == [[None]] for sheet in ladder_sheets)
    assert all(sheet["overall_average"] is None for sheet in ladder_sheets)


@pytest.mark.parametrize("status", ["EVALUATOR_ERROR", "SCORED"])
def test_report_rejects_unexplained_null_metric(tmp_path: Path, status: str) -> None:
    record = _record(tmp_path, "EI-BROKEN-v1.2", f"broken-{status}")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(
        store,
        record,
        score_id,
        _package_with_nulls(record.question, {"all.raw": status}),
    )
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )

    with pytest.raises(ValueError, match="unexplained null aggregate"):
        freeze_aggregation(plan, store, score_id=score_id)


def test_report_rejects_numeric_null_mixing_inside_repeat_group(tmp_path: Path) -> None:
    numeric = _record(tmp_path, "EI-MIX-v1.2", "numeric")
    nullable = _record(tmp_path, "EI-MIX-v1.2", "nullable")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(
        store,
        numeric,
        score_id,
        _package(numeric.question, 80),
    )
    _write_score(
        store,
        nullable,
        score_id,
        _package_with_nulls(nullable.question, {"all.raw": "NOT_APPLICABLE"}),
    )
    plan = SelectionPlan(
        "average",
        (SelectionGroup(numeric.repeat_key, (numeric, nullable)),),
        2,
        2,
    )

    with pytest.raises(ValueError, match="mixes numeric and null aggregate"):
        freeze_aggregation(plan, store, score_id=score_id)


def test_workbook_contract_builds_nine_ranked_numeric_sheets() -> None:
    def question_row(identity: str, question: str, o2: float, piecewise: float) -> dict:
        return {
            "identity": identity,
            "question": question,
            "metrics": {
                "effectiveness.o2": o2,
                "key.piecewise": piecewise,
                "key.discrete": piecewise - 5,
                "key.raw": piecewise + 5,
                "all.raw": piecewise + 10,
            },
        }

    question_rows = [
        question_row("codex / A", "Q1", 60.0, 70.0),
        question_row("codex / B", "Q1", 90.0, 80.0),
        question_row("codex / A", "Q2", 100.0, 90.0),
        question_row("codex / B", "Q2", 50.0, 60.0),
    ]
    key_rows = [
        {"check_id": "C2", "question": "Q1", "identity": "codex / A", "raw": 45, "discrete": 35, "piecewise": 40},
        {"check_id": "C2", "question": "Q1", "identity": "codex / B", "raw": 85, "discrete": 75, "piecewise": 80},
        {"check_id": "C2", "question": "Q2", "identity": "codex / A", "raw": 95, "discrete": 85, "piecewise": 90},
        {"check_id": "C2", "question": "Q2", "identity": "codex / B", "raw": 75, "discrete": 65, "piecewise": 70},
        {"check_id": "C6a", "question": "Q1", "identity": "codex / A", "raw": 55, "discrete": 45, "piecewise": 50},
        {"check_id": "C6a", "question": "Q1", "identity": "codex / B", "raw": 45, "discrete": 35, "piecewise": 40},
    ]
    all_rows = [
        {"check_id": row["check_id"], "question": row["question"], "identity": row["identity"], "raw": row["raw"]}
        for row in key_rows
    ]

    sheets = _workbook_sheets(
        {"question_rows": question_rows, "key_rows": key_rows, "all_rows": all_rows}
    )

    assert SHEET_NAMES == EXPECTED_SHEETS
    assert tuple(sheet["name"] for sheet in sheets) == EXPECTED_SHEETS
    o2 = sheets[0]
    assert o2["models"] == ["codex / A", "codex / B"]
    assert o2["row_averages"] == [80.0, 70.0]
    assert all(
        value is None or isinstance(value, float)
        for row in o2["values"]
        for value in row
    )
    detail = sheets[2]
    assert [row["check_id"] for row in detail["rows"]] == ["C2", "C2", "C6a"]
    assert [row["question"] for row in detail["rows"][:2]] == ["Q2", "Q1"]
    assert detail["models"] == ["codex / B", "codex / A"]
    assert detail["model_averages"] == [63.33, 60.0]


def test_build_report_emits_workbook_and_artifact_progress(tmp_path: Path) -> None:
    record = _record(tmp_path, "EI-Q1-v1.2", "q1")
    store = ScoreStore()
    score_id = "20260814120000"
    _write_score(store, record, score_id, _package(record.question, 80))
    plan = SelectionPlan(
        "latest",
        (SelectionGroup(record.repeat_key, (record,)),),
        1,
        1,
    )
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    events: list[str] = []

    def fake_render(_payload: Path, output: Path) -> tuple[str, ...]:
        output.write_bytes(b"synthetic workbook")
        return SHEET_NAMES

    with patch(
        "simulation.ei.reports.service._render_workbook",
        side_effect=fake_render,
    ):
        artifacts = build_report(
            plan,
            report_id="0814A",
            report_dir=report_dir,
            score_id=score_id,
            score_store=store,
            progress=lambda event, _details: events.append(event),
        )

    assert artifacts["workbook"].is_file()
    assert artifacts["manifest"].is_file()
    manifest = json.loads(artifacts["manifest"].read_text(encoding="utf-8"))
    assert manifest["artifacts"] == {
        "workbook": artifacts["workbook"].name,
        "aggregation": artifacts["aggregation"].name,
        "selection": "selection.json",
    }
    assert events[-3:] == [
        "workbook_started",
        "workbook_completed",
        "report_artifacts_completed",
    ]


def test_report_runtime_accepts_configured_artifact_tool(tmp_path: Path) -> None:
    modules = tmp_path / "node_modules"
    entry = modules / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"
    entry.parent.mkdir(parents=True)
    entry.write_text("export {};", encoding="utf-8")

    with (
        patch.dict("os.environ", {"EVAL_NODE_MODULES": str(modules)}, clear=False),
        patch("simulation.ei.reports.service._node_command", return_value="node"),
    ):
        validate_report_runtime()


def test_report_runtime_auto_discovers_codex_bundle(tmp_path: Path) -> None:
    modules = tmp_path / "dependencies" / "node" / "node_modules"
    entry = modules / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"
    entry.parent.mkdir(parents=True)
    entry.write_text("export {};", encoding="utf-8")
    node = modules.parent / "bin" / "node.exe"
    node.parent.mkdir(parents=True)
    node.write_bytes(b"")

    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "simulation.ei.reports.service._bundled_node_modules_candidates",
            return_value=(modules,),
        ),
    ):
        environment = _report_environment()
        assert environment["EVAL_NODE_MODULES"] == str(modules.resolve())
        assert _node_command(environment) == str(node.resolve())
        validate_report_runtime()


def test_report_runtime_fails_fast_with_actionable_dependency_error() -> None:
    completed = type("Completed", (), {"returncode": 1})()
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "simulation.ei.reports.service._bundled_node_modules_candidates",
            return_value=(),
        ),
        patch("simulation.ei.reports.service._node_command", return_value="node"),
        patch("simulation.ei.reports.service.subprocess.run", return_value=completed),
    ):
        try:
            validate_report_runtime()
        except RuntimeError as exc:
            assert "EVAL_NODE_MODULES" in str(exc)
        else:
            raise AssertionError("missing artifact-tool must fail before aggregation")


def test_workbook_export_survives_native_preview_failure_with_excel_fallback(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "aggregation.json"
    payload.write_text("{}", encoding="utf-8")
    output = tmp_path / "report.xlsx"
    operations: list[str] = []

    def fake_builder(
        _payload: Path,
        *,
        operation: str,
        environment: dict[str, str],
        output: Path | None = None,
        preview: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del environment, preview
        operations.append(operation)
        if operation == "export":
            assert output is not None
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("xl/workbook.xml", "<workbook />")
            return subprocess.CompletedProcess([], 0, "", "")
        return subprocess.CompletedProcess([], -1073741819, "", "native crash")

    def fake_excel(
        _payload: Path,
        _output: Path,
        preview: Path,
        *,
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        del environment
        for sheet_name in SHEET_NAMES:
            (preview / f"{sheet_name}.png").write_bytes(b"preview")
        return subprocess.CompletedProcess([], 0, "", "")

    with (
        patch(
            "simulation.ei.reports.service._report_environment",
            return_value={},
        ),
        patch(
            "simulation.ei.reports.service._run_workbook_builder",
            side_effect=fake_builder,
        ),
        patch(
            "simulation.ei.reports.service._render_previews_with_excel",
            side_effect=fake_excel,
        ),
    ):
        rendered = _render_workbook(payload, output)

    assert operations == ["export", "preview"]
    assert rendered == SHEET_NAMES
    assert output.is_file()
    assert not (tmp_path / ".ei-report-preview").exists()


def test_excel_preview_fallback_script_has_a_valid_powershell_preamble() -> None:
    script = Path(report_service.__file__).with_name(
        "render_ei_report_preview.ps1"
    ).read_text(encoding="utf-8")

    assert script.startswith("[CmdletBinding()]\nparam(")
    assert "eval.exe report" not in script
    assert "CopyPicture" not in script
    assert "ExportAsFixedFormat" in script
    assert "EVAL_PDFTOPPM" in script
