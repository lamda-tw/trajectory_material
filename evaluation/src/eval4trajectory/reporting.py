from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .catalog import INDICATORS
from .models import IndicatorStatus, TrajectoryReport


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temp = Path(handle.name)
    os.replace(temp, path)


def _markdown(report: TrajectoryReport) -> str:
    verdict = "达标" if report.passed else "未达标"
    normalized = (
        f"{report.normalized_score:.2f}" if report.normalized_score is not None else "不可计算"
    )
    lines = [
        "# 轨迹诊断评分报告",
        "",
        "## 1. 总览",
        "",
        f"- 轨迹：`{report.trajectory_file}`",
        f"- 原始得分：**{report.raw_score:.2f} / {report.max_score:.0f}**",
        f"- 已评价满分：**{report.evaluated_max_score:.2f}**",
        f"- 归一化得分：**{normalized} / 100**",
        f"- 证据覆盖率：**{report.coverage:.2%}**",
        f"- 结论：**{verdict}**",
        "",
    ]
    if report.gate_failures:
        lines.extend(["硬性门槛失败：", ""])
        lines.extend(
            f"- `{item.check_id}` {item.conclusion}" for item in report.gate_failures
        )
        lines.append("")
    lines.extend(
        [
            "## 2. 12 项指标",
            "",
            "| ID | 维度 | 检查项 | 得分 | 状态 | 失败事件 | 诊断 |",
            "|---|---|---|---:|---|---:|---|",
        ]
    )
    for item in report.results:
        lines.append(
            f"| {item.check_id} | {item.dimension} | {item.title} | "
            f"{item.score:.2f}/{item.max_score:.0f} | {item.status.value} | "
            f"{item.e} | {item.summary} |"
        )
    lines.extend(["", "## 3. 负反馈与根因证据", ""])
    for item in report.results:
        if not item.evidence:
            continue
        lines.extend([f"### {item.check_id} {item.title}", ""])
        for evidence in item.evidence:
            recurrence = "；同类问题复发" if evidence.recurrence else ""
            lines.extend(
                [
                    f"- `{evidence.trajectory_time}` 消息 {evidence.message_index}{recurrence}",
                    f"  - 结论：{evidence.conclusion}",
                    f"  - 轨迹证据：{evidence.excerpt}",
                    f"  - 期望：{evidence.expected}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
        temp = Path(handle.name)
    os.replace(temp, path)


def write_report_bundle(report: TrajectoryReport, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        output / "score_result.json",
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_text(output / "business_report.md", _markdown(report) + "\n")
    _atomic_text(
        output / "gate_failures.json",
        json.dumps(
            [item.as_dict() for item in report.gate_failures],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    evidences = [evidence for item in report.results for evidence in item.evidence]
    _write_csv(
        output / "feedback_trace.csv",
        [
            "feedback_time", "message_index", "check_id", "failure_tag",
            "signal_labels", "feedback_excerpt", "first_completion_index",
            "repair_index", "repair_excerpt", "recurrence",
        ],
        [
            [
                item.trajectory_time, item.message_index, item.check_id,
                item.failure_tag, ";".join(item.signal_labels), item.excerpt,
                item.previous_completion_index or "", item.repair_index or "",
                item.repair_excerpt, item.recurrence,
            ]
            for item in evidences
            if item.check_id != "I3"
        ],
    )
    _write_csv(
        output / "evidence_detail.csv",
        [
            "check_id", "failure_tag", "trajectory_time", "message_index", "role",
            "conclusion", "expected", "actual_excerpt", "previous_completion_excerpt",
            "repair_excerpt", "recurrence",
        ],
        [
            [
                item.check_id, item.failure_tag, item.trajectory_time,
                item.message_index, item.role, item.conclusion, item.expected,
                item.excerpt, item.previous_completion_excerpt,
                item.repair_excerpt, item.recurrence,
            ]
            for item in evidences
        ],
    )
    regressions = [
        item.as_dict()
        for item in evidences
        if item.recurrence and item.check_id != "I3"
    ]
    _atomic_text(
        output / "regression_cases.json",
        json.dumps(regressions, ensure_ascii=False, indent=2) + "\n",
    )
    actions = []
    for item in report.results:
        if item.status in {IndicatorStatus.FAILED, IndicatorStatus.PARTIAL}:
            action = next(
                (
                    definition.recommendation
                    for definition in INDICATORS
                    if definition.check_id == item.check_id
                ),
                "为该检查项补齐根因、锚点、全量回归和交付状态证据。",
            )
            if action not in actions:
                actions.append(action)
    _atomic_text(
        output / "improvement_actions.md",
        "# 改进建议\n\n"
        + ("\n".join(f"{i}. {text}" for i, text in enumerate(actions, 1)) or "无。")
        + "\n",
    )
