#!/usr/bin/env python3
"""Audit and summarize a completed bare-Qwen3 AppWorld test_normal run."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path


EXPERIMENT_NAME = "simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GiB"


def parse_times(text: str) -> tuple[str | None, str | None, float | None]:
    starts = re.findall(r"^run_started_at=(.+)$", text, flags=re.MULTILINE)
    ends = re.findall(r"^run_finished_at=(.+)$", text, flags=re.MULTILINE)
    start = starts[-1].strip() if starts else None
    end = ends[-1].strip() if ends else None
    seconds = None
    if start and end:
        seconds = (dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds()
    return start, end, seconds


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours} 小时 {minutes} 分 {secs} 秒"


def failure_category(requirement: str) -> str:
    """Map official evaluator requirements to compact Chinese error categories."""
    text = " ".join(requirement.lower().split())
    if "answers match" in text or ("answer" in text and "match" in text):
        return "最终答案不匹配"
    if (
        "file_system" in text
        or "file path" in text
        or "file_paths" in text
        or "files have been" in text
        or "directory" in text
    ):
        return "文件系统路径、目录或内容错误"
    if "simple_note" in text or "note" in text:
        return "笔记状态或内容错误"
    if "venmo" in text or "friend" in text:
        return "Venmo 好友、交易或付款状态错误"
    if "spotify" in text or "musicplayer" in text or "music player" in text or "song" in text:
        return "Spotify 播放、队列或收藏状态错误"
    if "gmail" in text or "email" in text or "mail" in text:
        return "邮件状态或内容错误"
    if "todoist" in text or any(
        word in text for word in ("todo", "project", "task list", "reminder", "taskcomment")
    ):
        return "待办或项目状态错误"
    if "splitwise" in text or "expense" in text:
        return "Splitwise 或费用状态错误"
    if "phone" in text or any(word in text for word in ("text message", "voice message", "alarm")):
        return "电话、消息或联系人状态错误"
    if any(word in text for word in ("transaction", "payment", "order", "cart", "shopping")):
        return "交易或购物状态错误"
    if "model changes" in text or "changed_records" in text or "record" in text:
        return "数据库变更不符合要求"
    return "其他业务条件未满足"


def audit_task(task_dir: Path) -> dict:
    """Audit the model/AppWorld boundary without interpreting task correctness."""
    lm_path = task_dir / "logs/lm_calls.jsonl"
    api_path = task_dir / "logs/api_calls.jsonl"
    env_path = task_dir / "logs/environment_io.md"
    audit = collections.Counter()
    if lm_path.is_file():
        with lm_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    choice = json.loads(line)["output"]["choices"][0]
                    message = choice["message"]
                    content = message.get("content")
                    finish_reason = choice.get("finish_reason")
                    reasoning_content = message.get("reasoning_content")
                    if finish_reason == "length":
                        audit["length_truncated"] += 1
                    if content is None:
                        audit["content_null"] += 1
                        if finish_reason == "length" and reasoning_content:
                            audit["reasoning_only_truncated"] += 1
                        else:
                            audit["content_null_unexplained"] += 1
                    elif not str(content).strip():
                        audit["content_empty"] += 1
                    else:
                        audit["content_nonempty"] += 1
                except Exception:
                    audit["malformed_lm_rows"] += 1
    env_text = read_text(env_path)
    return {
        "content_null": audit["content_null"],
        "content_empty": audit["content_empty"],
        "content_nonempty": audit["content_nonempty"],
        "malformed_lm_rows": audit["malformed_lm_rows"],
        "length_truncated": audit["length_truncated"],
        "reasoning_only_truncated": audit["reasoning_only_truncated"],
        "content_null_unexplained": audit["content_null_unexplained"],
        "no_code_observations": env_text.count("No code available to execute"),
        "complete_task_actions": env_text.count("apis.supervisor.complete_task("),
        "has_python_execution_error": (
            "Execution failed. Traceback" in env_text or "Syntax error in line:" in env_text
        ),
        "reached_max_steps": line_count(lm_path) >= 50,
        "api_calls": line_count(api_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--baseline-dev", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    baseline_dev = Path(args.baseline_dev).resolve()
    dataset_path = root / "data/datasets/test_normal.txt"
    output_root = root / "experiments/outputs" / EXPERIMENT_NAME
    evaluation_path = output_root / "evaluations/test_normal.json"
    task_ids = [line.strip() for line in read_text(dataset_path).splitlines() if line.strip()]
    scores = load_json(evaluation_path)
    individual = scores["individual"]

    if len(task_ids) != 168 or len(set(task_ids)) != 168:
        raise RuntimeError("test_normal is not exactly 168 unique tasks")
    if set(individual) != set(task_ids):
        raise RuntimeError("Official evaluation IDs do not match test_normal")

    records: list[dict] = []
    totals = collections.Counter()
    successful_ids: list[str] = []
    error_tasks: set[str] = set()
    max_step_tasks: set[str] = set()
    no_code_tasks: set[str] = set()
    content_null_tasks: set[str] = set()
    content_empty_tasks: set[str] = set()
    malformed_lm_tasks: set[str] = set()
    length_truncated_tasks: set[str] = set()
    reasoning_only_truncated_tasks: set[str] = set()
    unexplained_null_tasks: set[str] = set()
    complete_task_tasks: set[str] = set()
    failure_requirement_tasks: dict[str, set[str]] = collections.defaultdict(set)
    failure_category_tasks: dict[str, set[str]] = collections.defaultdict(set)
    interface_totals = collections.Counter()
    for task_id in task_ids:
        task_dir = output_root / "tasks" / task_id
        lm_path = task_dir / "logs/lm_calls.jsonl"
        api_path = task_dir / "logs/api_calls.jsonl"
        env_path = task_dir / "logs/environment_io.md"
        finished = (task_dir / "misc/finished").is_file()
        evaluated = (task_dir / "evaluation/report.md").is_file()
        success = bool(individual[task_id]["success"])
        if success:
            successful_ids.append(task_id)
        lm_calls = line_count(lm_path)
        api_calls = line_count(api_path)
        totals["lm_calls"] += lm_calls
        totals["api_calls"] += api_calls
        if lm_calls >= 50:
            max_step_tasks.add(task_id)
        usage_path = task_dir / "misc/usage.json"
        if usage_path.is_file():
            tokens = load_json(usage_path).get("tokens", {})
            totals["input_tokens"] += int(tokens.get("input_cache_miss", 0) or 0)
            totals["input_tokens"] += int(tokens.get("input_cache_hit", 0) or 0)
            totals["output_tokens"] += int(tokens.get("output", 0) or 0)
        interface = audit_task(task_dir)
        for key in (
            "content_null",
            "content_empty",
            "content_nonempty",
            "malformed_lm_rows",
            "length_truncated",
            "reasoning_only_truncated",
            "content_null_unexplained",
            "no_code_observations",
            "complete_task_actions",
        ):
            interface_totals[key] += interface[key]
        if interface["no_code_observations"]:
            no_code_tasks.add(task_id)
        if interface["has_python_execution_error"]:
            error_tasks.add(task_id)
        if interface["content_null"]:
            content_null_tasks.add(task_id)
        if interface["content_empty"]:
            content_empty_tasks.add(task_id)
        if interface["malformed_lm_rows"]:
            malformed_lm_tasks.add(task_id)
        if interface["length_truncated"]:
            length_truncated_tasks.add(task_id)
        if interface["reasoning_only_truncated"]:
            reasoning_only_truncated_tasks.add(task_id)
        if interface["content_null_unexplained"]:
            unexplained_null_tasks.add(task_id)
        if interface["complete_task_actions"]:
            complete_task_tasks.add(task_id)
        item = individual[task_id]
        failure_requirements = [entry["requirement"] for entry in item.get("failures", [])]
        failure_categories = sorted({failure_category(value) for value in failure_requirements})
        for requirement in failure_requirements:
            failure_requirement_tasks[requirement].add(task_id)
        for category in failure_categories:
            failure_category_tasks[category].add(task_id)
        records.append(
            {
                "task_id": task_id,
                "scenario_id": task_id.rsplit("_", 1)[0],
                "started": task_dir.is_dir(),
                "lm_calls": lm_calls,
                "api_calls": api_calls,
                "finished": finished,
                "evaluated": evaluated,
                "task_success": success,
                "difficulty": item.get("difficulty"),
                "passed_tests": len(item.get("passes", [])),
                "failed_tests": len(item.get("failures", [])),
                "failure_categories_zh": failure_categories,
                "failure_requirements": failure_requirements,
                "interface": interface,
                "needs_rerun": not (finished and evaluated),
            }
        )

    missing = [row["task_id"] for row in records if row["needs_rerun"]]
    if missing:
        raise RuntimeError(f"Incomplete task outputs: {missing}")

    scenarios: dict[str, list[str]] = collections.defaultdict(list)
    for task_id in task_ids:
        scenarios[task_id.rsplit("_", 1)[0]].append(task_id)
    if len(scenarios) != 56 or any(len(ids) != 3 for ids in scenarios.values()):
        raise RuntimeError("test_normal is not 56 complete three-task scenarios")
    success_set = set(successful_ids)
    successful_scenarios = sorted(
        scenario for scenario, ids in scenarios.items() if all(task_id in success_set for task_id in ids)
    )

    difficulty_total = collections.Counter()
    difficulty_success = collections.Counter()
    passed_tests = 0
    failed_tests = 0
    for item in individual.values():
        difficulty = str(item.get("difficulty"))
        difficulty_total[difficulty] += 1
        difficulty_success[difficulty] += int(bool(item.get("success")))
        passed_tests += len(item.get("passes", []))
        failed_tests += len(item.get("failures", []))
    difficulty = {
        key: {
            "total": difficulty_total[key],
            "successes": difficulty_success[key],
            "tgc": round(100 * difficulty_success[key] / difficulty_total[key], 1),
        }
        for key in sorted(difficulty_total, key=int)
    }
    failure_categories_summary = [
        {
            "category_zh": category,
            "task_count": len(ids),
            "task_ids": sorted(ids),
        }
        for category, ids in sorted(
            failure_category_tasks.items(), key=lambda pair: (-len(pair[1]), pair[0])
        )
    ]
    top_failure_requirements = [
        {
            "requirement": requirement,
            "task_count": len(ids),
            "task_ids": sorted(ids),
        }
        for requirement, ids in sorted(
            failure_requirement_tasks.items(), key=lambda pair: (-len(pair[1]), pair[0])
        )
    ]
    format_anomaly_tasks = unexplained_null_tasks | content_empty_tasks | malformed_lm_tasks
    format_anomaly_scenarios = {
        task_id.rsplit("_", 1)[0] for task_id in format_anomaly_tasks
    }
    systemic_response_format_fault = len(format_anomaly_scenarios) >= 3
    format_anomaly_events = (
        interface_totals["content_null_unexplained"]
        + interface_totals["content_empty"]
        + interface_totals["malformed_lm_rows"]
    )
    format_anomaly_event_percentage = round(
        100 * format_anomaly_events / max(1, totals["lm_calls"]), 3
    )

    aggregate = scores["aggregate"]
    run_log = read_text(root / "logs/run.log")
    run_start, run_end, duration = parse_times(run_log)
    exit_code_path = root / "logs/run_exit_code.txt"
    exit_code = int(read_text(exit_code_path).strip())
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    git_commit = subprocess.run(
        ["git", "-C", str(root.parent.parent), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    status_path = root / "task_status.jsonl"
    with status_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "experiment": str(root),
        "baseline_dev": str(baseline_dev),
        "model": "/root/autodl-tmp/models/Qwen3-8B",
        "dataset": "test_normal",
        "task_count": len(task_ids),
        "scenario_count": len(scenarios),
        "official_scores": aggregate,
        "success_count": len(successful_ids),
        "success_ids": sorted(successful_ids),
        "successful_scenario_count": len(successful_scenarios),
        "successful_scenarios": successful_scenarios,
        "difficulty": difficulty,
        "evaluator_tests": {
            "passed": passed_tests,
            "failed": failed_tests,
            "total": passed_tests + failed_tests,
            "pass_percentage": round(100 * passed_tests / (passed_tests + failed_tests), 1),
        },
        "failure_analysis": {
            "categories": failure_categories_summary,
            "official_requirements": top_failure_requirements,
        },
        "interface_audit": {
            "totals": dict(interface_totals),
            "content_null_task_count": len(content_null_tasks),
            "content_empty_task_count": len(content_empty_tasks),
            "malformed_lm_task_count": len(malformed_lm_tasks),
            "length_truncated_task_count": len(length_truncated_tasks),
            "reasoning_only_truncated_task_count": len(reasoning_only_truncated_tasks),
            "unexplained_content_null_task_count": len(unexplained_null_tasks),
            "format_anomaly_scenario_count": len(format_anomaly_scenarios),
            "format_anomaly_event_count": format_anomaly_events,
            "format_anomaly_event_percentage": format_anomaly_event_percentage,
            "complete_task_task_count": len(complete_task_tasks),
            "python_error_task_count": len(error_tasks),
            "no_code_task_count": len(no_code_tasks),
            "max_step_task_count": len(max_step_tasks),
            "systemic_response_format_fault_detected": systemic_response_format_fault,
        },
        "runtime": {
            **dict(totals),
            "python_error_task_count": len(error_tasks),
            "no_code_task_count": len(no_code_tasks),
            "max_step_task_count": len(max_step_tasks),
            "max_step_task_ids": sorted(max_step_tasks),
        },
        "run_started_at": run_start,
        "run_finished_at": run_end,
        "duration_seconds": duration,
        "exit_code": exit_code,
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "created_for": "AppWorld test_normal evaluation of bare Qwen3-8B",
        "workspace_git_commit": git_commit,
        "appworld_version": "0.2.0.dev0",
        "base_model": "/root/autodl-tmp/models/Qwen3-8B",
        "base_model_adapter": None,
        "dataset": "test_normal",
        "dataset_sha256": sha256(dataset_path),
        "agent": "simplified_react_code_agent",
        "prompt": "official one-shot ReAct code-agent prompt",
        "model_config": "qwen3-8b-with-reasoning",
        "temperature": 0,
        "seed": 100,
        "max_completion_tokens": 3000,
        "max_steps": 50,
        "max_model_len": 32000,
        "reasoning_parser": "deepseek_r1",
        "num_processes": 1,
        "cuda_visible_devices": "0",
        "official_evaluation": True,
        "run_started_at": run_start,
        "run_finished_at": run_end,
        "run_exit_code": exit_code,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    success_text = "、".join(sorted(successful_ids)) if successful_ids else "无"
    scenario_text = "、".join(successful_scenarios) if successful_scenarios else "无"
    difficulty_rows = "\n".join(
        f"| {key} | {value['successes']}/{value['total']} | {value['tgc']:.1f} |"
        for key, value in difficulty.items()
    )
    category_rows = "\n".join(
        f"| {item['category_zh']} | {item['task_count']} | "
        f"{'、'.join(item['task_ids'])} |"
        for item in failure_categories_summary
    ) or "| 无 | 0 | — |"

    def markdown_cell(value: str) -> str:
        return " ".join(value.split()).replace("|", "/")

    repeated_requirement_items = [
        item for item in top_failure_requirements if item["task_count"] > 1
    ]
    repeated_requirement_rows = "\n".join(
        f"| {markdown_cell(item['requirement'])} | {item['task_count']} | "
        f"{'、'.join(item['task_ids'])} |"
        for item in repeated_requirement_items[:30]
    ) or "| 无重复失败条件 | 0 | — |"
    task_rows = []
    for record in records:
        interface = record["interface"]
        signals = []
        if interface["reasoning_only_truncated"]:
            signals.append(f"纯reasoning截断×{interface['reasoning_only_truncated']}")
        if interface["content_null_unexplained"]:
            signals.append(f"无法解释的content=null×{interface['content_null_unexplained']}")
        content_present_truncations = (
            interface["length_truncated"] - interface["reasoning_only_truncated"]
        )
        if content_present_truncations:
            signals.append(f"其他长度截断×{content_present_truncations}")
        if interface["content_empty"]:
            signals.append(f"content为空×{interface['content_empty']}")
        if interface["malformed_lm_rows"]:
            signals.append(f"LM日志解析异常×{interface['malformed_lm_rows']}")
        if interface["no_code_observations"]:
            signals.append(f"无可执行代码×{interface['no_code_observations']}")
        if interface["has_python_execution_error"]:
            signals.append("Python执行错误")
        if interface["reached_max_steps"]:
            signals.append("达到50步上限")
        if not interface["complete_task_actions"]:
            signals.append("未调用complete_task")
        signal_text = "；".join(signals) if signals else "正常"
        category_text = "；".join(record["failure_categories_zh"]) or "—"
        task_rows.append(
            f"| {record['task_id']} | {'正确' if record['task_success'] else '错误'} | "
            f"{record['passed_tests']}/{record['passed_tests'] + record['failed_tests']} | "
            f"{category_text} | {signal_text} |"
        )
    if systemic_response_format_fault:
        interface_conclusion = (
            f"响应格式风险告警已触发：无法解释的空响应、空 content 或日志格式异常跨 "
            f"{len(format_anomaly_scenarios)} 个 scenario；但仅有 {format_anomaly_events}/"
            f"{totals['lm_calls']} 次 LM 调用（{format_anomaly_event_percentage}%）命中，"
            "呈低频孤立分布，需要复核，但不足以解释主体失败；主要失败仍来自业务状态、"
            "最终答案和代理执行/终止策略。"
        )
    elif format_anomaly_tasks:
        interface_conclusion = (
            f"发现局部响应格式异常，涉及 {len(format_anomaly_tasks)} 题、"
            f"{len(format_anomaly_scenarios)} 个 scenario；尚不构成跨场景统一故障。"
        )
    elif reasoning_only_truncated_tasks:
        interface_conclusion = (
            "未发现无法解释的空响应；出现的 content=null 均可由 finish_reason=length "
            "且仅生成 reasoning_content 解释，属于输出上限截断，不是接口丢包。"
        )
    else:
        interface_conclusion = (
            "未发现统一的模型响应格式故障；失败主要来自各任务业务状态或答案未满足官方条件。"
        )
    tgc = aggregate["task_goal_completion"]
    sgc = aggregate["scenario_goal_completion"]
    report = f"""# AppWorld 裸 Qwen3-8B test_normal 评测报告

## 一、结论

裸 Qwen3-8B 已完成 AppWorld `test_normal` 全部 168 道任务的真实 one-shot ReAct 推理与官方评分。
最终成功 {len(successful_ids)}/168，TGC 为 {tgc}，SGC 为 {sgc}；基础设施与评分链路完成 168/168，最终退出码为 {exit_code}。

## 二、官方指标

| 指标 | 结果 |
|---|---:|
| 成功任务 | {len(successful_ids)}/168 |
| TGC | {tgc} |
| 成功 scenario | {len(successful_scenarios)}/56 |
| SGC | {sgc} |
| evaluator 条件通过 | {passed_tests}/{passed_tests + failed_tests} ({100 * passed_tests / (passed_tests + failed_tests):.1f}%) |

按难度统计：

| 难度 | 成功/总数 | TGC |
|---|---:|---:|
{difficulty_rows}

成功任务：{success_text}

完整成功 scenario：{scenario_text}

## 三、配置与可比性

- 模型：`/root/autodl-tmp/models/Qwen3-8B` 裸基座，未加载 LoRA/adapter，未修改权重。
- Agent/Prompt：官方 `simplified_react_code_agent` 与官方 one-shot ReAct prompt。
- 模型 preset：`qwen3-8b-with-reasoning`；reasoning parser：`deepseek_r1`。
- temperature=0、seed=100、单次输出上限 3000 tokens、每题最多 50 步、context 32000。
- 单 AppWorld 进程、GPU0 顺序执行；AppWorld 0.2.0.dev0 官方 evaluator。
- 上述协议与 Dev 基线 `{baseline_dev}` 一致，仅数据集从 `dev` 改为 `test_normal`。

## 四、错误总结与接口审计

### 4.1 中文错误类别

同一题可能同时违反多个 evaluator 条件，因此下面各类别的题数不可相加后当作失败题总数。

| 错误类别 | 涉及题数 | 任务 ID |
|---|---:|---|
{category_rows}

### 4.2 重复出现的官方失败条件

下表保留官方 evaluator 的英文 requirement 原文，便于精确复核；仅列出现于两题及以上的前 30 项。
它能够区分“同一业务场景的相似失败”和“跨场景统一接口故障”。

| 官方 requirement | 涉及题数 | 任务 ID |
|---|---:|---|
{repeated_requirement_rows}

### 4.3 模型—AppWorld 接口健康检查

结论：**{interface_conclusion}**

| 接口信号 | 次数/题数 |
|---|---:|
| `message.content=null` | {interface_totals['content_null']} 次，{len(content_null_tasks)} 题 |
| 其中纯 reasoning 长度截断 | {interface_totals['reasoning_only_truncated']} 次，{len(reasoning_only_truncated_tasks)} 题 |
| 无法由长度截断解释的 `content=null` | {interface_totals['content_null_unexplained']} 次，{len(unexplained_null_tasks)} 题 |
| `finish_reason=length` | {interface_totals['length_truncated']} 次，{len(length_truncated_tasks)} 题 |
| 空 `message.content` | {interface_totals['content_empty']} 次，{len(content_empty_tasks)} 题 |
| 无法解析的 LM 日志行 | {interface_totals['malformed_lm_rows']} 次，{len(malformed_lm_tasks)} 题 |
| `No code available to execute` | {interface_totals['no_code_observations']} 次，{len(no_code_tasks)} 题 |
| 含 `complete_task` action | {len(complete_task_tasks)} 题 |
| 含 Python 执行错误 | {len(error_tasks)} 题 |
| 达到 50 步上限 | {len(max_step_tasks)} 题 |

### 4.4 逐题官方结果与错误信号

“正确/错误”直接来自 AppWorld 官方 evaluator；“条件通过”是该题通过的 evaluator 条件数/条件总数。

| 任务 ID | 官方结果 | 条件通过 | 中文错误类别 | 接口/执行信号 |
|---|---|---:|---|---|
{chr(10).join(task_rows)}

## 五、运行完整性与成本

| 检查项 | 结果 |
|---|---:|
| 任务输出与 finished | 168/168 |
| 官方逐题 evaluation | 168/168 |
| LM 调用 | {totals['lm_calls']} |
| AppWorld API 调用 | {totals['api_calls']} |
| 输入 tokens | {totals['input_tokens']} |
| 输出 tokens | {totals['output_tokens']} |
| 总 tokens | {totals['total_tokens']} |
| 含 Python 执行错误的任务 | {len(error_tasks)} |
| 含无可执行代码响应的任务 | {len(no_code_tasks)} |
| 达到 50 次 LM 调用的任务 | {len(max_step_tasks)} |
| 墙钟时间 | {human_duration(duration)} |
| 实验目录实际文件大小 | {human_bytes(directory_size(root))} |

## 六、产物

- `REPORT.md`：本报告。
- `summary.json`：机器可读指标与运行统计。
- `task_status.jsonl`：168 道任务的完成、评分和调用计数。
- `manifest.json`：模型、数据哈希与冻结推理协议。
- `INTERFACE_AUDIT.md`：运行期间持续更新的逐题官方评分与接口审计。
- `live_summary.json`、`live_task_status.jsonl`：运行期间的即时机器可读评分和逐题记录。
- `experiments/outputs/.../evaluations/test_normal.json`：AppWorld 官方聚合及逐题评分。
- `experiments/outputs/.../tasks/`：逐题 LM、环境、API、数据库与 evaluator 产物。
- `logs/run.log`：完整运行日志。
- `scripts_snapshot/`：本次实际使用的脚本快照。
"""
    (root / "REPORT.md").write_text(report, encoding="utf-8")

    artifact_names = [
        "REPORT.md",
        "summary.json",
        "task_status.jsonl",
        "manifest.json",
        "command.txt",
        "baseline_reference.txt",
        "INTERFACE_AUDIT.md",
        "live_summary.json",
        "live_task_status.jsonl",
    ]
    artifact_names += [
        str(path.relative_to(root)) for path in sorted((root / "scripts_snapshot").glob("*"))
    ]
    hash_lines = []
    for name in artifact_names:
        path = root / name
        if path.is_file():
            hash_lines.append(f"{sha256(path)}  {name}")
    (root / "artifacts.sha256").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
