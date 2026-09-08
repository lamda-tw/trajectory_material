"""Unified, discoverable command-line entry point for evaluation scoring."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

from simulation.app.commands import (
    DEFAULT_SCORE_JOBS,
    MAX_SCORE_JOBS,
    report_selection,
    score_batch,
    score_one,
)
from simulation.app.selection import (
    SelectorSpec,
    load_selector,
    record_from_run,
    select_runs,
)
from simulation.ei.core.config import discover_questions, repository_root


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    pass


METRIC_LABELS = {
    "effectiveness.o2": "O2成效",
    "key.raw": "关键·原始",
    "key.discrete": "关键·离散",
    "key.piecewise": "关键·分段",
    "all.raw": "全项·原始",
}


def _score_text(scores: object, *, compact: bool = False) -> str:
    if not isinstance(scores, Mapping):
        return ""
    metric_ids = tuple(METRIC_LABELS)
    values = []
    for metric_id in metric_ids:
        if compact and metric_id not in {"effectiveness.o2", "key.piecewise", "all.raw"}:
            continue
        value = scores.get(metric_id)
        formatted = "--" if value is None else f"{float(value):.2f}"
        label = (
            {
                "effectiveness.o2": "O2",
                "key.piecewise": "分段",
                "all.raw": "全项",
            }[metric_id]
            if compact
            else METRIC_LABELS[metric_id]
        )
        values.append(f"{label}={formatted}")
    return " | ".join(values)


def _shorten(value: object, limit: int = 42) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


class ConsoleProgress:
    """Render structured progress to stderr while stdout remains valid JSON."""

    def __init__(self, *, quiet: bool = False) -> None:
        self.quiet = quiet
        self._lock = RLock()
        self._interactive = bool(getattr(sys.stderr, "isatty", lambda: False)())
        self._bar_open = False
        self._last_bar_length = 0

    def _finish_bar(self) -> None:
        with self._lock:
            if self._interactive and self._bar_open:
                print(file=sys.stderr, flush=True)
            self._bar_open = False
            self._last_bar_length = 0

    def _write(self, message: str) -> None:
        if not self.quiet:
            with self._lock:
                self._finish_bar()
                print(message, file=sys.stderr, flush=True)

    def _render_bar(
        self,
        label: str,
        current: int,
        total: int,
        latest: str,
    ) -> None:
        if self.quiet:
            return
        safe_total = max(total, 1)
        bounded = min(max(current, 0), safe_total)
        ratio = bounded / safe_total
        width = 24
        filled = min(width, int(ratio * width))
        bar = "█" * filled + "░" * (width - filled)
        message = (
            f"{label} [{bar}] {current}/{total} {ratio * 100:5.1f}% | "
            f"最新完成：{latest}"
        )
        with self._lock:
            if self._interactive:
                padding = " " * max(0, self._last_bar_length - len(message))
                print(
                    f"\r{message}{padding}",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
                self._bar_open = True
                self._last_bar_length = len(message)
            else:
                print(message, file=sys.stderr, flush=True)

    def __call__(self, event: str, details: Mapping[str, Any]) -> None:
        if self.quiet:
            return
        if event == "selection_started":
            self._write(f"[选择] 正在扫描运行：{details['source']}")
        elif event == "selection_completed":
            self._write(
                "[选择] 扫描完成："
                f"发现 {details['discovered_count']} 个，"
                f"筛选后 {details['filtered_count']} 个，"
                f"最终选中 {details['selected_run_count']} 个运行 / "
                f"{details['group_count']} 个分组，repeat={details['repeat']}"
            )
        elif event == "preview_completed":
            self._write("[预览] 已输出选择结果；未执行评分或报告写入。")
        elif event == "score_single_started":
            self._write(f"[评分] 正在识别并评分单个运行：{details['run_dir']}")
        elif event == "score_single_identified":
            self._write(
                f"[评分] 题目={details['question']} | 模型={details['model']} | "
                f"Harness={details['harness']} | skill={details['skill']}"
            )
        elif event == "score_single_completed":
            self._write(f"[完成] 单运行评分完成：status={details['status']}")
            self._write(f"       {_score_text(details['scores'])}")
            self._write(f"       score_id={details['score_id']}")
            self._write(f"       分数文件={details['score_path']}")
        elif event == "score_batch_started":
            self._write(
                f"[评分] 开始批量评分 {details['total']} 个运行，"
                f"请求并行度={details['jobs']}。"
            )
        elif event == "score_batch_allocated":
            self._write(
                f"[评分] score_id={details['score_id']} | "
                f"实际题目并行度={details['jobs']}"
            )
            self._write(f"       选择快照={details['selection_path']}")
            self._render_bar("评分", 0, int(details["total"]), "等待首个结果")
        elif event == "score_run_started":
            return
        elif event == "score_run_completed":
            self._render_bar(
                "评分",
                int(details["completed_count"]),
                int(details["total"]),
                f"{_shorten(details['run'])} | "
                f"{_score_text(details['scores'], compact=True)}",
            )
        elif event == "score_run_failed":
            self._render_bar(
                "评分",
                int(details["completed_count"]),
                int(details["total"]),
                f"失败：{_shorten(details['run'], 32)} | "
                f"{_shorten(details['error'], 48)}",
            )
        elif event == "score_batch_persisted":
            self._finish_bar()
            self._write(
                "[评分] 批次已落盘："
                f"成功 {details['completed_count']}，"
                f"执行失败 {details['failure_count']}，"
                f"结果异常 {details['error_result_count']}"
            )
            self._write(f"       批次结果={details['results_path']}")
        elif event == "score_batch_completed":
            self._write(f"[完成] 批量评分结束：score_id={details['score_id']}")
        elif event == "report_started":
            self._write(
                f"[报告] 开始读取 {details['run_count']} 个运行的分数，"
                f"score_id={details['score_id']}"
            )
        elif event == "report_allocated":
            self._write(
                f"[报告] report_id={details['report_id']} | "
                f"目录={details['report_dir']}"
            )
        elif event == "aggregation_started":
            self._write(
                f"[聚合] 正在处理 {details['run_count']} 个运行 / "
                f"{details['group_count']} 个分组，repeat={details['repeat']}"
            )
            self._render_bar(
                "聚合",
                0,
                int(details["group_count"]),
                "等待首个结果",
            )
        elif event == "aggregation_group_started":
            return
        elif event == "aggregation_group_completed":
            self._render_bar(
                "聚合",
                int(details["index"]),
                int(details["total"]),
                f"{_shorten(details['question'], 30)} | "
                f"{details['harness']}/{details['model']} | "
                f"{_score_text(details['metrics'], compact=True)}",
            )
        elif event == "aggregation_completed":
            self._finish_bar()
            self._write(
                f"[聚合] 完成：{details['model_count']} 个模型身份，"
                f"{details['question_row_count']} 个单题聚合行。"
            )
        elif event == "workbook_started":
            self._write(
                f"[XLSX] 正在生成并渲染 {details['sheet_count']} 个 Sheet，"
                "这一步可能需要几十秒……"
            )
            self._write(f"       目标文件={details['workbook']}")
        elif event == "workbook_completed":
            self._write(
                f"[XLSX] 生成完成：{details['workbook']} | "
                f"Sheet={', '.join(str(value) for value in details['sheets'])}"
            )
        elif event == "report_artifacts_completed":
            self._write(f"[报告] 审计文件={details['manifest']}")
        elif event == "report_completed":
            self._write(f"[完成] 报告生成完成：report_id={details['report_id']}")
            if details.get("workbook"):
                self._write(f"       XLSX={details['workbook']}")
            if details.get("report_dir"):
                self._write(f"       报告目录={details['report_dir']}")
        elif event == "report_failed":
            self._write(f"[失败] 报告生成失败：{details['error']}")
            self._write(f"       失败记录={details['failure_path']}")
        elif event == "report_skipped":
            self._write(f"[跳过] 未生成报告：{details['reason']}")
        elif event == "command_failed":
            self._write(f"[失败] {details['error']}")


def _add_selection(parser: argparse.ArgumentParser) -> None:
    source = parser.add_argument_group("运行来源（二选一）")
    source.add_argument(
        "--root",
        type=Path,
        action="append",
        default=[],
        metavar="DIR",
        help="扫描目录；可重复。省略时扫描 <repo>/eval_results。",
    )
    source.add_argument(
        "--selector",
        type=Path,
        metavar="YAML",
        help="使用 selector YAML；不可再传 --root/筛选项/--repeat。",
    )
    filters = parser.add_argument_group(
        "运行筛选（字段之间 AND，同字段多值 OR；支持 * ? 通配符）"
    )
    for option, label in (
        ("task", "子任务，如 EI 或 OPT"),
        ("question", "题目及版本"),
        ("model", "模型"),
        ("harness", "Harness"),
        ("skill", "skill版本，含 noskill"),
        ("run", "运行目录名"),
    ):
        filters.add_argument(
            f"--{option}", action="append", default=[], metavar="PATTERN", help=label
        )
    parser.add_argument(
        "--repeat",
        choices=("latest", "average"),
        default=None,
        help="同题/模型/Harness/skill重复运行：取最新或平均；默认 latest。",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="只打印最终选择，不评分、不写报告。",
    )


def _add_quiet(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="关闭人读进度提示，仅在 stdout 输出最终 JSON。",
    )


def _jobs(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("jobs must be an integer") from exc
    if not 1 <= parsed <= MAX_SCORE_JOBS:
        raise argparse.ArgumentTypeError(f"jobs must be between 1 and {MAX_SCORE_JOBS}")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval",
        formatter_class=HelpFormatter,
        description="统一评测打分工具。当前注册能力：simulation/ei。",
        epilog=(
            "常用示例：\n"
            "  eval score run RUN_DIR\n"
            "  eval score batch --task EI --model gpt56 --repeat latest --jobs 6\n"
            "  eval score batch --selector selectors/ei.yaml --report\n"
            "  eval report --task EI --skill noskill --repeat average --score-id latest\n"
            "  eval report --selector selectors/ei.yaml --score-id 20260814153045\n"
            "\n选择器 YAML：\n"
            "  schema_version: '1.0'\n"
            "  roots: [../eval_results]  # 相对 selector YAML 所在目录\n"
            "  include: {task: [EI], model: [gpt56, k3], skill: [noskill]}\n"
            "  exclude: {run: ['*broken*']}\n"
            "  repeat: latest"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    score = commands.add_parser("score", help="执行规则打分并写入 <run>/scores。")
    score_commands = score.add_subparsers(dest="score_command", required=True)
    run = score_commands.add_parser(
        "run",
        help="评分单个运行；直接回显五项总分，不生成 XLSX。",
        description="评分一个 RUN_DIR。题目、模型、Harness、skill 均从运行目录及元数据读取。",
    )
    run.add_argument("run_dir", type=Path, metavar="RUN_DIR")
    _add_quiet(run)

    batch = score_commands.add_parser(
        "batch",
        help="按共用选择器评分一批运行。",
        formatter_class=HelpFormatter,
        description="选择一批运行，使用同一精确时间 score_id 写入每个 <run>/scores。",
    )
    _add_selection(batch)
    _add_quiet(batch)
    batch.add_argument(
        "--jobs",
        type=_jobs,
        default=DEFAULT_SCORE_JOBS,
        metavar="N",
        help=(
            f"并行处理的题目数；默认 {DEFAULT_SCORE_JOBS}，范围 1–{MAX_SCORE_JOBS}。"
            "同题运行串行执行并复用权威输入。"
        ),
    )
    batch.add_argument(
        "--report",
        action="store_true",
        help="评分成功后立即生成独立 report_id 的 EI推演打分.xlsx。",
    )

    report = commands.add_parser(
        "report",
        help="从已有分数聚合并生成 EI推演打分.xlsx。",
        formatter_class=HelpFormatter,
        description="重新选择任意运行集合，读取指定评分版本，聚合并生成报告。",
    )
    _add_selection(report)
    _add_quiet(report)
    report.add_argument(
        "--score-id",
        default="latest",
        metavar="ID|latest",
        help="每个运行读取的评分版本；默认 latest，也可指定 YYYYMMDDHHMMSS[-NN]。",
    )
    return parser


def _selection(args: argparse.Namespace, repo: Path):
    filter_names = ("task", "question", "model", "harness", "skill", "run")
    if args.selector:
        conflicting = bool(args.root or args.repeat) or any(
            getattr(args, name) for name in filter_names
        )
        if conflicting:
            raise ValueError(
                "--selector cannot be combined with --root, CLI filters, or --repeat"
            )
        spec = load_selector(args.selector)
    else:
        roots = tuple(path.resolve() for path in args.root) or (repo / "eval_results",)
        include = {
            name: tuple(getattr(args, name))
            for name in filter_names
            if getattr(args, name)
        }
        spec = SelectorSpec(roots, include, {}, args.repeat or "latest")
    return select_runs(spec, question_ids=discover_questions(include_blocked=True))


def _print(payload: object, *, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    repo = repository_root()
    progress = ConsoleProgress(quiet=args.quiet)
    try:
        if args.command == "score" and args.score_command == "run":
            progress("score_single_started", {"run_dir": args.run_dir.resolve().as_posix()})
            record = record_from_run(
                args.run_dir,
                question_ids=discover_questions(include_blocked=True),
            )
            progress(
                "score_single_identified",
                {
                    "question": record.question,
                    "model": record.model,
                    "harness": record.harness,
                    "skill": record.skill,
                },
            )
            result = score_one(record, repository_root=repo)
            progress("score_single_completed", result)
            _print(result)
            return 0 if result["status"] not in {"EVALUATOR_ERROR", "QUESTION_CONTRACT_INCOMPLETE"} else 2

        source = (
            args.selector.resolve().as_posix()
            if args.selector
            else ", ".join(path.resolve().as_posix() for path in args.root)
            or (repo / "eval_results").as_posix()
        )
        progress("selection_started", {"source": source})
        plan = _selection(args, repo)
        progress(
            "selection_completed",
            {
                "discovered_count": plan.discovered_count,
                "filtered_count": plan.filtered_count,
                "selected_run_count": len(plan.runs),
                "group_count": len(plan.groups),
                "repeat": plan.repeat,
            },
        )
        if args.preview:
            progress("preview_completed", {})
            _print(plan.as_dict())
            return 0
        if args.command == "score":
            progress(
                "score_batch_started",
                {"total": len(plan.runs), "jobs": args.jobs},
            )
            result = score_batch(
                plan,
                repository_root=repo,
                progress=progress,
                jobs=args.jobs,
            )
            progress("score_batch_completed", result)
            if (
                args.report
                and result["failure_count"] == 0
                and result["error_result_count"] == 0
            ):
                progress(
                    "report_started",
                    {"run_count": len(plan.runs), "score_id": result["score_id"]},
                )
                result["report"] = report_selection(
                    plan,
                    repository_root=repo,
                    score_id=result["score_id"],
                    progress=progress,
                )
                progress("report_completed", result["report"])
            if args.report and "report" not in result:
                result["report_skipped"] = "one or more runs have no complete numeric aggregate set"
                progress("report_skipped", {"reason": result["report_skipped"]})
            _print(result)
            return 0 if result["failure_count"] == 0 and result["error_result_count"] == 0 else 2
        progress(
            "report_started",
            {"run_count": len(plan.runs), "score_id": args.score_id},
        )
        result = report_selection(
            plan,
            repository_root=repo,
            score_id=args.score_id,
            progress=progress,
        )
        progress("report_completed", result)
        _print(result)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        progress("command_failed", {"error": f"{type(exc).__name__}: {exc}"})
        _print({"error": f"{type(exc).__name__}: {exc}"}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
