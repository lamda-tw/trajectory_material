"""Machine-checkable score parity gate for architecture migrations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compare_records(
    baseline_records: list[dict[str, Any]],
    candidate_records: list[dict[str, Any]],
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    baseline = {str(row["run"]): row for row in baseline_records}
    candidate = {str(row["run"]): row for row in candidate_records}
    missing = sorted(set(baseline) - set(candidate))
    extra = sorted(set(candidate) - set(baseline))
    differences: list[dict[str, Any]] = []
    for run in sorted(set(baseline) & set(candidate)):
        before = baseline[run]
        after = candidate[run]
        fields: dict[str, tuple[float, float]] = {
            "total_score": (
                float(before.get("total_score", before.get("weighted_total", 0.0))),
                float(after.get("total_score", after.get("weighted_total", 0.0))),
            ),
        }
        for field, (before_value, after_value) in fields.items():
            delta = abs(before_value - after_value)
            if delta > tolerance:
                differences.append(
                    {
                        "run": run,
                        "question": after.get("question") or before.get("question"),
                        "field": field,
                        "baseline": before_value,
                        "candidate": after_value,
                        "absolute_delta": delta,
                    }
                )
    return {
        "tolerance": tolerance,
        "baseline_run_count": len(baseline),
        "candidate_run_count": len(candidate),
        "missing_runs": missing,
        "extra_runs": extra,
        "difference_count": len(differences),
        "max_absolute_delta": max(
            (row["absolute_delta"] for row in differences), default=0.0
        ),
        "differences": differences,
        "passed": not missing and not extra and not differences,
    }


def compare_report_files(
    baseline_path: Path,
    candidate_records: list[dict[str, Any]],
    *,
    tolerance: float = 1e-6,
    candidate_scope_only: bool = False,
) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    records = payload.get("runs")
    if not isinstance(records, list):
        raise ValueError(f"baseline report has no runs array: {baseline_path}")
    source_count = len(records)
    if candidate_scope_only:
        candidate_runs = {str(row["run"]) for row in candidate_records}
        records = [row for row in records if str(row.get("run")) in candidate_runs]
    result = compare_records(records, candidate_records, tolerance=tolerance)
    result["baseline_path"] = baseline_path.resolve().as_posix()
    result["parity_scope"] = "candidate-runs" if candidate_scope_only else "exact-full-set"
    result["baseline_source_run_count"] = source_count
    return result


def write_parity_report(report_dir: Path, result: dict[str, Any]) -> None:
    json_path = report_dir / "score_parity.json"
    markdown_path = report_dir / "score_parity.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Simulation validator 分数等价性",
        "",
        f"- 结论：**{'PASS' if result['passed'] else 'FAIL'}**",
        f"- 容差：`{result['tolerance']}`",
        f"- 基线运行：{result['baseline_run_count']}",
        f"- 新框架运行：{result['candidate_run_count']}",
        f"- 缺失运行：{len(result['missing_runs'])}",
        f"- 新增运行：{len(result['extra_runs'])}",
        f"- 超差评分项：{result['difference_count']}",
        f"- 最大绝对差：`{result['max_absolute_delta']}`",
        "",
    ]
    if result["differences"]:
        lines.extend(
            [
                "| Run | Field | Baseline | Candidate | Delta |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for row in result["differences"][:100]:
            lines.append(
                f"| `{row['run']}` | `{row['field']}` | {row['baseline']} | "
                f"{row['candidate']} | {row['absolute_delta']} |"
            )
        lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
