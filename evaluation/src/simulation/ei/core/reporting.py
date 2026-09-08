"""Canonical and atomic result persistence for Simulation validator v4.13."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import contract_header
from .models import ArtifactBundle, ComponentResult, RunScore


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _relative(path: Path | None, bundle: ArtifactBundle) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(bundle.run_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _artifacts_payload(bundle: ArtifactBundle) -> list[dict[str, Any]]:
    output = []
    for role, value in bundle.artifacts.items():
        output.append(
            {
                "role": role,
                "status": value.status,
                "selected_path": _relative(value.selected_path, bundle),
                "error": value.error,
                "validation_issue_count": len(value.validation_issues),
                "validation_issues": _jsonable(value.validation_issues),
                "quantity_error_count": value.quantity_error_count,
                "quantity_errors": _jsonable(value.quantity_errors),
                "resolution_diagnostics": _jsonable(
                    value.resolution_diagnostics
                ),
                "candidates": [
                    {
                        "path": _relative(candidate.path, bundle),
                        "required_coverage": candidate.required_coverage,
                        "prompt_filename": candidate.prompt_filename,
                        "common_parent_suffix": candidate.common_parent_suffix,
                        "usable": candidate.usable,
                        "error": candidate.error,
                        "canonical": candidate.canonical,
                    }
                    for candidate in value.candidates
                ],
            }
        )
    return output


def component_payload(
    score: RunScore,
    component: ComponentResult,
    *,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "contract": contract_header("component-result"),
        "meta": {
            "question_id": score.question_id,
            "component": component.component,
            "ruleset_release": score.release,
            "runtime_gt_access": False,
        },
        "artifacts": (
            _artifacts_payload(score.artifacts)
            if artifacts is None
            else _jsonable(artifacts)
        ),
        "result": {
            "status": component.status,
            "error": component.error,
            "checks": [
                {
                    "id": value.check_id,
                    "name": value.name,
                    "score": value.score,
                    "status": value.status,
                    "reason_code": value.reason_code,
                    "explanation": value.explanation,
                    "prompt_refs": list(value.prompt_refs),
                    "evidence": _jsonable(value.evidence),
                }
                for value in component.checks
            ],
        },
    }


def total_payload(score: RunScore) -> dict[str, Any]:
    aggregates = [value.as_dict() for value in score.aggregates]
    return {
        "contract": contract_header("component-result"),
        "meta": {
            "question_id": score.question_id,
            "component": "total",
            "ruleset_release": score.release,
            "runtime_gt_access": False,
        },
        "result": {
            "status": score.status,
            "total_score": score.total_score,
            "total_max": 100.0,
            "error": score.error,
            "aggregates": aggregates,
            "components": [
                {
                    "id": value.component,
                    "status": value.status,
                }
                for value in score.components
            ],
        },
    }


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _component_markdown(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    result = payload["result"]
    lines = [
        f"# {meta['question_id']} · {meta['component']} · Ruleset {meta['ruleset_release']}",
        "",
        f"- 状态：{result['status']}",
        "- 运行期读取 GT：否",
        "",
        "## 产物解析",
        "",
        "| 角色 | 状态 | 选中文件 | 结构问题 | 数量问题 |",
        "|---|---|---|---:|---:|",
    ]
    for artifact in payload.get("artifacts", []):
        lines.append(
            f"| {artifact['role']} | {artifact['status']} | "
            f"{artifact.get('selected_path') or ''} | "
            f"{artifact.get('validation_issue_count', 0)} | "
            f"{artifact.get('quantity_error_count', 0)} |"
        )
    lines.extend(
        [
        "",
        "## 检查项",
        "",
        "| ID | 得分 | 状态 | 原因 | Prompt 依据 |",
        "|---|---:|---|---|---|",
        ]
    )
    for value in result.get("checks", []):
        refs = "<br>".join(value.get("prompt_refs", []))
        lines.append(
            f"| {value['id']} | {value['score']} | {value['status']} | {value['reason_code']} | {refs} |"
        )

    for value in result.get("checks", []):
        evidence = value.get("evidence", {})
        if not isinstance(evidence, dict):
            continue
        summary = {
            key: item
            for key, item in evidence.items()
            if isinstance(item, (str, int, float, bool))
            or item is None
            or key in {"formula_evidence", "failure_type_counts", "summary_quantity_rows"}
        }
        if summary:
            lines.extend(
                [
                    "",
                    f"### {value['id']} 证据摘要",
                    "",
                    "```json",
                    json.dumps(summary, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        for field, title in (
            ("failures", "失败样例"),
            ("violations", "违规样例"),
            ("region_errors", "区域错误样例"),
            ("material_source_warehouse_mismatches", "来源对账错误样例"),
        ):
            samples = evidence.get(field, [])
            if not isinstance(samples, list) or not samples:
                continue
            lines.extend(
                [
                    "",
                    f"### {value['id']} {title}",
                    "",
                    "```json",
                    json.dumps(samples[:10], ensure_ascii=False, indent=2),
                    "```",
                ]
            )
    return "\n".join(lines) + "\n"


def write_component_score(
    score: RunScore,
    component: ComponentResult,
    output_dir: Path,
    *,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Persist one canonical component report without any component aggregate."""

    output = output_dir.resolve()
    prefix = f"validator_{component.component.replace('-', '_')}"
    payload = component_payload(score, component, artifacts=artifacts)
    json_path = output / f"{prefix}.json"
    markdown_path = output / f"{prefix}.md"
    _write_json(json_path, payload)
    _atomic_text(markdown_path, _component_markdown(payload))
    return {
        f"{component.component}.json": json_path,
        f"{component.component}.md": markdown_path,
    }


def write_run_score(
    score: RunScore,
    output_dir: Path,
    *,
    include_total: bool = True,
) -> dict[str, Path]:
    """Persist one RunScore; no score is recomputed from written reports."""

    output = output_dir.resolve()
    paths: dict[str, Path] = {}
    for component in score.components:
        paths.update(write_component_score(score, component, output))
    if include_total:
        payload = total_payload(score)
        total_json = output / "validator_total.json"
        total_md = output / "validator_total.md"
        _write_json(total_json, payload)
        _atomic_text(
            total_md,
            "\n".join(
                [
                    f"# {score.question_id} · total · Ruleset {score.release}",
                    "",
                    f"- 状态：{score.status}",
                    f"- 得分：{score.total_score} / 100",
                    f"- 错误：{score.error or '无'}",
                    "",
                ]
            ),
        )
        paths["total.json"] = total_json
        paths["total.md"] = total_md
    return paths


def write_total_score(score: RunScore, output_dir: Path) -> dict[str, Path]:
    """Persist only the aggregate report after inherited checks are merged."""

    output = output_dir.resolve()
    payload = total_payload(score)
    total_json = output / "validator_total.json"
    total_md = output / "validator_total.md"
    _write_json(total_json, payload)
    _atomic_text(
        total_md,
        "\n".join(
            [
                f"# {score.question_id} · total · Ruleset {score.release}",
                "",
                f"- 状态：{score.status}",
                f"- 得分：{score.total_score} / 100",
                f"- 错误：{score.error or '无'}",
                "",
            ]
        ),
    )
    return {"total.json": total_json, "total.md": total_md}
