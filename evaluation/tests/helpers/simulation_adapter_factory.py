from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from simulation.ei.core.adapters import resolve_artifacts
from simulation.ei.core.models import ArtifactSpec, QuestionProfile


CORPUS_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "validator"
    / "simulation"
    / "adapters"
    / "corpus_manifest.json"
)


def load_corpus() -> dict[str, Any]:
    value = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    value["discovery_topologies"] = [
        value["primary_discovery_topology"],
        *value["discovery_topologies"],
    ]
    value["products"] = {
        **value["wide_and_ledger_products"],
        **value["products"],
    }
    return value


def product_cases(product: str) -> list[dict[str, Any]]:
    return list(load_corpus()["products"][product]["cases"])


def product_case_params(product: str) -> list[Any]:
    params: list[Any] = []
    for case in product_cases(product):
        known_gap = case.get("expected", {}).get("known_gap")
        marks = (
            pytest.mark.xfail(reason=known_gap, strict=True)
            if known_gap
            else ()
        )
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


def build_layout(base: Path) -> tuple[Path, Path, Path]:
    repository = base / "repo"
    question = repository / "evalsets" / "simulation" / "Q"
    run = repository / "eval_results" / "run"
    question.mkdir(parents=True)
    run.mkdir(parents=True)
    return repository, question, run


def write_csv_case(path: Path, case: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if "raw_csv" in case:
        path.write_text(str(case["raw_csv"]), encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(case["headers"])
        for row in case.get("rows", []):
            if isinstance(row, dict):
                writer.writerow([row.get(header, "") for header in case["headers"]])
            else:
                writer.writerow(row)


def write_xlsx_case(path: Path, case: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(case.get("rows", []), columns=case["headers"])
    frame.to_excel(path, index=False, sheet_name=case.get("sheet_name", "Sheet1"))


def write_case(path: Path, case: dict[str, Any]) -> None:
    if case.get("format", "csv") == "xlsx":
        write_xlsx_case(path, case)
    else:
        write_csv_case(path, case)


def make_profile(
    base: Path,
    *,
    role: str,
    schema: str,
    artifact_roots: tuple[str, ...],
    canonical_path: str,
    filenames: tuple[str, ...],
    schema_options: dict[str, Any] | None = None,
    source: str = "candidate",
) -> QuestionProfile:
    path = base / "profile.yaml"
    path.write_text("test", encoding="utf-8")
    return QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=artifact_roots,
        artifacts={
            role: ArtifactSpec(
                role=role,
                source=source,
                path=canonical_path,
                filenames=filenames if source == "candidate" else (),
                schema=schema,
                required=True,
                schema_options=dict(schema_options or {}),
            )
        },
        components={},
        path=path,
    )


def resolve_case(base: Path, product: str, case: dict[str, Any]):
    corpus_product = load_corpus()["products"][product]
    repository, _, run = build_layout(base)
    relative_path = case.get(
        "candidate_path",
        f"56TESTPK/MaterialCycleEI/data-pipeline/model_output/{case['filename']}",
    )
    write_case(run / relative_path, case)
    profile = make_profile(
        base,
        role=product,
        schema=corpus_product["schema"],
        artifact_roots=tuple(case.get("artifact_roots", ["56TESTPK/MaterialCycleEI"])),
        canonical_path=case.get("canonical_path", relative_path),
        filenames=tuple(case.get("filenames", [case["filename"]])),
        schema_options={
            **corpus_product.get("schema_options", {}),
            **case.get("schema_options", {}),
        },
    )
    return resolve_artifacts(profile, run, repository).get(product)


def issue_codes(result: Any) -> set[str]:
    return {str(value["code"]) for value in result.validation_issues}


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
    return str(value)


def assert_case_contract(result: Any, case: dict[str, Any]) -> None:
    expected = case.get("expected", {})
    assert result is not None
    assert result.status == expected.get("status", "SELECTED_CANONICAL")
    if result.table is not None and "headers" in case:
        assert tuple(result.table.attrs["source_headers"]) == tuple(case["headers"])
        rows = case.get("rows", ())
        assert len(result.table) == len(rows)
        for row_index, expected_row in enumerate(rows):
            expected_values = (
                [expected_row.get(header, "") for header in case["headers"]]
                if isinstance(expected_row, dict)
                else expected_row
            )
            assert [_cell_text(value) for value in result.table.iloc[row_index].tolist()] == [
                _cell_text(value) for value in expected_values
            ]
    assert set(expected.get("issue_codes", ())).issubset(issue_codes(result))
    assert set(expected.get("forbidden_issue_codes", ())).isdisjoint(
        issue_codes(result)
    )
    if "quantity_error_count" in expected:
        assert result.quantity_error_count == expected["quantity_error_count"]
    if "normalized_keys" in expected:
        assert set(result.normalized) == {
            tuple(value) for value in expected["normalized_keys"]
        }
