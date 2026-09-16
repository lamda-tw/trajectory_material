#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

EXPERIMENT_NAME = "simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


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


def parse_run_times(text: str) -> tuple[str | None, str | None, float | None]:
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
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours} 小时 {minutes} 分 {secs} 秒"


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GiB"


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def collect_runtime(output_root: Path, task_ids: list[str]) -> dict:
    totals = collections.Counter()
    error_tasks = set()
    max_step_tasks = set()
    for task_id in task_ids:
        task_dir = output_root / "tasks" / task_id
        lm_path = task_dir / "logs" / "lm_calls.jsonl"
        api_path = task_dir / "logs" / "api_calls.jsonl"
        env_path = task_dir / "logs" / "environment_io.md"
        usage_path = task_dir / "misc" / "usage.json"
        lm_calls = line_count(lm_path)
        api_calls = line_count(api_path)
        totals["lm_calls"] += lm_calls
        totals["api_calls"] += api_calls
        if lm_calls >= 50:
            max_step_tasks.add(task_id)
        if usage_path.is_file():
            tokens = load_json(usage_path).get("tokens", {})
            totals["input_tokens"] += int(tokens.get("input_cache_miss", 0) or 0)
            totals["input_tokens"] += int(tokens.get("input_cache_hit", 0) or 0)
            totals["output_tokens"] += int(tokens.get("output", 0) or 0)
        if lm_path.is_file():
            with lm_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        message = record["output"]["choices"][0]["message"]
                        if message.get("content") is None:
                            totals["content_null"] += 1
                        else:
                            totals["content_non_null"] += 1
                    except Exception:
                        totals["malformed_lm_log_rows"] += 1
        if api_path.is_file():
            with api_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        url = str(json.loads(line).get("url", ""))
                        if url.endswith("/complete_task"):
                            totals["complete_task_calls"] += 1
                    except Exception:
                        totals["malformed_api_log_rows"] += 1
        if env_path.is_file():
            text = env_path.read_text(encoding="utf-8", errors="replace")
            totals["no_code_observations"] += text.count("No code available to execute")
            complete_task_actions = text.count("apis.supervisor.complete_task(")
            totals["complete_task_action_count"] += complete_task_actions
            if complete_task_actions:
                totals["complete_task_task_count"] += 1
            if "Execution failed. Traceback" in text or "Syntax error in line:" in text:
                error_tasks.add(task_id)
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return {
        **dict(totals),
        "python_error_task_count": len(error_tasks),
        "max_step_task_count": len(max_step_tasks),
        "max_step_task_ids": sorted(max_step_tasks),
    }


def difficulty_stats(individual: dict) -> dict[str, dict[str, int | float]]:
    totals = collections.Counter()
    successes = collections.Counter()
    for item in individual.values():
        key = str(item.get("difficulty"))
        totals[key] += 1
        successes[key] += int(bool(item.get("success")))
    return {
        key: {
            "total": totals[key],
            "successes": successes[key],
            "tgc": round(100 * successes[key] / totals[key], 1),
        }
        for key in sorted(totals, key=int)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()

    experiment = Path(args.experiment).resolve()
    baseline = Path(args.baseline).resolve()
    adapter = Path(args.adapter).resolve()
    workspace = Path(args.workspace).resolve()
    output_root = experiment / "experiments" / "outputs" / EXPERIMENT_NAME
    baseline_output_root = baseline / "experiments" / "outputs" / EXPERIMENT_NAME
    evaluation_path = output_root / "evaluations" / "dev.json"
    baseline_evaluation_path = baseline_output_root / "evaluations" / "dev.json"
    task_ids = [
        line.strip()
        for line in (experiment / "data" / "datasets" / "dev.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scores = load_json(evaluation_path)
    baseline_scores = load_json(baseline_evaluation_path)
    individual = scores["individual"]
    baseline_individual = baseline_scores["individual"]
    per_task = load_jsonl(experiment / "task_status.jsonl")

    if len(task_ids) != 57 or len(set(task_ids)) != 57:
        raise RuntimeError("Dev split is not exactly 57 unique tasks")
    if len(per_task) != 57 or len({row["task_id"] for row in per_task}) != 57:
        raise RuntimeError("Per-task status JSONL is not exactly 57 unique tasks")
    if set(individual) != set(task_ids) or set(baseline_individual) != set(task_ids):
        raise RuntimeError("Evaluation task IDs do not match Dev split")
    if any(row["status"] == "evaluation_error" for row in per_task):
        raise RuntimeError("Per-task evaluator error detected")

    success_ids = sorted(task_id for task_id, item in individual.items() if item["success"])
    baseline_success_ids = sorted(
        task_id for task_id, item in baseline_individual.items() if item["success"]
    )
    success_set = set(success_ids)
    baseline_success_set = set(baseline_success_ids)
    common_successes = sorted(success_set & baseline_success_set)
    gained = sorted(success_set - baseline_success_set)
    regressed = sorted(baseline_success_set - success_set)
    both_failed = sorted(set(task_ids) - success_set - baseline_success_set)

    scenarios = collections.defaultdict(list)
    for task_id in task_ids:
        scenarios[task_id.rsplit("_", 1)[0]].append(task_id)
    success_scenarios = sorted(
        scenario for scenario, ids in scenarios.items() if all(item in success_set for item in ids)
    )
    baseline_success_scenarios = sorted(
        scenario
        for scenario, ids in scenarios.items()
        if all(item in baseline_success_set for item in ids)
    )

    runtime = collect_runtime(output_root, task_ids)
    baseline_runtime = collect_runtime(baseline_output_root, task_ids)
    pass_total = sum(int(row["passed_tests"]) for row in per_task)
    fail_total = sum(int(row["failed_tests"]) for row in per_task)
    run_log = (experiment / "logs" / "run.log").read_text(encoding="utf-8", errors="replace")
    run_start, run_end, duration_seconds = parse_run_times(run_log)
    exit_code = (experiment / "logs" / "run_exit_code.txt").read_text().strip()
    if exit_code != "0":
        raise RuntimeError(f"Run exit code is {exit_code}")

    summary = {
        "experiment": str(experiment),
        "baseline": str(baseline),
        "adapter": str(adapter),
        "task_count": len(task_ids),
        "scenario_count": len(scenarios),
        "official_scores": scores["aggregate"],
        "baseline_official_scores": baseline_scores["aggregate"],
        "success_count": len(success_ids),
        "success_ids": success_ids,
        "baseline_success_count": len(baseline_success_ids),
        "baseline_success_ids": baseline_success_ids,
        "transition_counts": {
            "baseline_success_to_lora_success": len(common_successes),
            "baseline_failure_to_lora_success": len(gained),
            "baseline_success_to_lora_failure": len(regressed),
            "baseline_failure_to_lora_failure": len(both_failed),
        },
        "gained_task_ids": gained,
        "regressed_task_ids": regressed,
        "common_success_task_ids": common_successes,
        "successful_scenarios": success_scenarios,
        "baseline_successful_scenarios": baseline_success_scenarios,
        "difficulty": difficulty_stats(individual),
        "baseline_difficulty": difficulty_stats(baseline_individual),
        "evaluator_tests": {
            "passed": pass_total,
            "failed": fail_total,
            "total": pass_total + fail_total,
            "pass_percentage": round(100 * pass_total / (pass_total + fail_total), 1),
        },
        "runtime": runtime,
        "baseline_runtime": baseline_runtime,
        "run_started_at": run_start,
        "run_finished_at": run_end,
        "duration_seconds": duration_seconds,
        "exit_code": int(exit_code),
        "interface_audit": {
            "reasoning_parser": "none",
            "null_reasoning_content_normalized_to_empty_string": True,
            "content_null_count": runtime.get("content_null", 0),
            "no_code_observation_count": runtime.get("no_code_observations", 0),
            "per_task_evaluation_errors": 0,
        },
    }
    (experiment / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    snapshot_dir = experiment / "scripts_snapshot"
    snapshot_dir.mkdir(exist_ok=True)
    script_names = [
        "appworld_run_isolated_lora_config.py",
        "run_appworld_qwen3_react_lora_full_dev.sh",
        "build_appworld_lora_aligned_dev_report.py",
    ]
    for name in script_names:
        shutil.copy2(workspace / "scripts" / name, snapshot_dir / name)

    command = (
        "scripts/run_appworld_qwen3_react_lora_full_dev.sh "
        + str(experiment)
        + " "
        + str(adapter)
        + " qwen3-8b-with-reasoning - none\n"
    )
    (experiment / "command.txt").write_text(command, encoding="utf-8")
    (experiment / "baseline_reference.txt").write_text(str(baseline) + "\n", encoding="utf-8")

    git_commit = subprocess.check_output(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
    ).strip()
    import appworld
    manifest = {
        "created_for": "AppWorld Dev evaluation of epoch-5 Qwen3-8B LoRA adapter",
        "workspace_git_commit": git_commit,
        "appworld_version": appworld.__version__,
        "base_model": "/root/autodl-tmp/models/Qwen3-8B",
        "adapter": str(adapter),
        "adapter_model_sha256": sha256(adapter / "adapter_model.safetensors"),
        "dev_split_sha256": sha256(experiment / "data" / "datasets" / "dev.txt"),
        "agent": "simplified_react_code_agent",
        "model_config": "qwen3-8b-with-reasoning",
        "temperature": 0,
        "seed": 100,
        "max_completion_tokens": 3000,
        "max_steps": 50,
        "max_model_len": 32000,
        "reasoning_parser": None,
        "compatibility_normalization": "Convert returned reasoning_content null to empty string before AppWorld logger handling",
        "per_task_official_evaluation": True,
        "final_official_dataset_evaluation": True,
        "run_started_at": run_start,
        "run_finished_at": run_end,
        "run_exit_code": int(exit_code),
    }
    (experiment / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    new_tgc = scores["aggregate"]["task_goal_completion"]
    new_sgc = scores["aggregate"]["scenario_goal_completion"]
    base_tgc = baseline_scores["aggregate"]["task_goal_completion"]
    base_sgc = baseline_scores["aggregate"]["scenario_goal_completion"]
    diff_rows = []
    new_diff = difficulty_stats(individual)
    base_diff = difficulty_stats(baseline_individual)
    for key in sorted(new_diff, key=int):
        diff_rows.append(
            f"| {key} | {base_diff[key]['successes']}/{base_diff[key]['total']} ({base_diff[key]['tgc']}) "
            f"| {new_diff[key]['successes']}/{new_diff[key]['total']} ({new_diff[key]['tgc']}) |"
        )

    report_lines = [
        "# AppWorld Qwen3-8B LoRA 对齐接口后的完整 Dev 评测报告",
        "",
        "## 一、结论",
        "",
        "修正输出通道后，五轮 LoRA 模型已在 57 道 Dev 题上完成真实 ReAct 推理和官方评测。",
        f"最终成功 {len(success_ids)}/57，TGC 为 {new_tgc}，与原始模型的 {len(baseline_success_ids)}/57、TGC {base_tgc} 持平；"
        f"SGC 从 {base_sgc} 提高到 {new_sgc}。",
        "",
        "成功总数相同，但成功题完全不同：共同成功 0 题，LoRA 新增成功 5 题，同时丢失原模型成功的 5 题。",
        "LoRA 将 d4e9306 场景的三个任务全部完成，因此获得 1/19 场景成功，对应 SGC 5.3；原模型没有完整完成任何一个三任务场景。",
        "",
        "这个结果说明接口问题已经消除，当前分数可以用于观察端到端能力。67 条轨迹的五轮 LoRA 没有提高总体 TGC，但改变了能力分布，并提高了场景级完整完成率。",
        "",
        "## 二、官方指标",
        "",
        "| 指标 | 原始 Qwen3-8B | 五轮 LoRA | 变化 |",
        "|---|---:|---:|---:|",
        f"| 成功任务 | {len(baseline_success_ids)}/57 | {len(success_ids)}/57 | {len(success_ids)-len(baseline_success_ids):+d} |",
        f"| TGC | {base_tgc} | {new_tgc} | {new_tgc-base_tgc:+.1f} |",
        f"| SGC | {base_sgc} | {new_sgc} | {new_sgc-base_sgc:+.1f} |",
        f"| 成功 scenario | {len(baseline_success_scenarios)}/19 | {len(success_scenarios)}/19 | {len(success_scenarios)-len(baseline_success_scenarios):+d} |",
        "",
        "按难度统计：",
        "",
        "| 难度 | 原始模型 成功/总数（TGC） | LoRA 成功/总数（TGC） |",
        "|---|---:|---:|",
        *diff_rows,
        "",
        "## 三、成功题与任务转移",
        "",
        "LoRA 成功任务：",
        "",
        *[f"- {task_id}" for task_id in success_ids],
        "",
        "原始模型成功任务：",
        "",
        *[f"- {task_id}" for task_id in baseline_success_ids],
        "",
        "| 转移 | 数量 |",
        "|---|---:|",
        f"| 原始成功 → LoRA 成功 | {len(common_successes)} |",
        f"| 原始失败 → LoRA 成功 | {len(gained)} |",
        f"| 原始成功 → LoRA 失败 | {len(regressed)} |",
        f"| 原始失败 → LoRA 失败 | {len(both_failed)} |",
        "",
        "LoRA 新增成功： " + "、".join(gained),
        "",
        "LoRA 退化任务： " + "、".join(regressed),
        "",
        "## 四、接口与运行完整性审计",
        "",
        "| 检查项 | 结果 |",
        "|---|---:|",
        f"| Dev 任务完成 | {len(per_task)}/57 |",
        f"| 逐题官方 evaluator 错误 | 0 |",
        f"| 最终进程退出码 | {exit_code} |",
        f"| LM 调用 | {runtime.get('lm_calls', 0):,} |",
        f"| message.content 非空 | {runtime.get('content_non_null', 0):,} |",
        f"| message.content=null | {runtime.get('content_null', 0):,} |",
        f"| No code available observation | {runtime.get('no_code_observations', 0):,} |",
        f"| 真实 AppWorld API 调用 | {runtime.get('api_calls', 0):,} |",
        f"| 含 complete_task action 的任务 | {runtime.get('complete_task_task_count', 0)}/57 |",
        f"| complete_task action 出现次数 | {runtime.get('complete_task_action_count', 0):,} |",
        f"| 含 Python 执行错误的任务 | {runtime.get('python_error_task_count', 0)} |",
        f"| 达到 50 次 LM 调用的任务 | {runtime.get('max_step_task_count', 0)} |",
        "",
        f"全部模型响应均进入可执行 content，content=null 和 No code available 均为 0。"
        f"本次产生 {runtime.get('api_calls', 0):,} 次真实 API 调用，因此不再是此前代码被 reasoning parser 吞掉的无效评测。",
        "",
        "逐题 evaluator 共通过 "
        f"{pass_total}/{pass_total + fail_total} 个测试条件（{summary['evaluator_tests']['pass_percentage']}%）。"
        "TGC 要求一道题的所有条件全部通过，因此部分完成不会计为任务成功。",
        "",
        "## 五、推理配置与对照边界",
        "",
        "- Dev split、任务顺序、ReAct Agent、Prompt、temperature=0、seed=100、单次输出上限 3000、每题 50 步、上下文 32000 和官方 evaluator 与原模型实验保持一致。",
        "- 使用原始 Qwen3-8B 基座，并加载 epoch-5 LoRA adapter。",
        "- 关闭 vLLM reasoning parser，使 LoRA 生成的理由和 fenced Python 保留在 message.content 中。",
        "- 对 AppWorld Agents 的 reasoning_content=null 做空字符串规范化；该修复只处理字段类型，不修改模型文本或 Python action。",
        "",
        "由于原模型历史基线使用 deepseek_r1 reasoning parser，而 LoRA 必须关闭该 parser 才能执行其训练格式，"
        "这里最可靠的含义是两个可运行端到端系统的对比。若要得到严格的纯权重消融，还应额外用相同的无 parser 接口评测原始模型。",
        "",
        "## 六、运行成本",
        "",
        "| 指标 | 原始 Qwen3-8B | 五轮 LoRA |",
        "|---|---:|---:|",
        f"| LM 调用 | {baseline_runtime.get('lm_calls', 0):,} | {runtime.get('lm_calls', 0):,} |",
        f"| AppWorld API 调用 | {baseline_runtime.get('api_calls', 0):,} | {runtime.get('api_calls', 0):,} |",
        f"| 输入 tokens | {baseline_runtime.get('input_tokens', 0):,} | {runtime.get('input_tokens', 0):,} |",
        f"| 输出 tokens | {baseline_runtime.get('output_tokens', 0):,} | {runtime.get('output_tokens', 0):,} |",
        f"| 总 tokens | {baseline_runtime.get('total_tokens', 0):,} | {runtime.get('total_tokens', 0):,} |",
        f"| 本次墙钟时间 | — | {human_duration(duration_seconds)} |",
        f"| 本次实验目录大小 | — | {human_bytes(directory_size(experiment))} |",
        "",
        "## 七、产物",
        "",
        "- REPORT.md：本中文报告",
        "- task_status.jsonl：每题完成后即时写入的官方评分摘要",
        "- summary.json：机器可读汇总与新旧任务转移",
        "- manifest.json：模型、adapter、数据和推理协议",
        "- command.txt：正式运行命令",
        "- baseline_reference.txt：原模型基线目录",
        "- scripts_snapshot/：本次实际使用的启动和报告脚本快照",
        "- experiments/outputs/.../evaluations/dev.json：AppWorld 官方聚合与逐题评测",
        "- experiments/outputs/.../tasks/：每题 LM、环境、API、数据库和 evaluator 产物",
        "- logs/run.log：完整运行日志",
        "",
        "## 八、建议",
        "",
        "下一步不应根据同为 5/57 就断言 LoRA 没有学习。它学出了五个新的成功任务和一个完整成功场景，同时发生五个退化，说明主要问题是覆盖面和稳定性。",
        "建议先分析新增成功与退化任务的轨迹差异，再扩大训练轨迹覆盖、加入 Dev 不可见的验证划分，并对长循环、分页和数据结构错误做针对性训练。",
        "同时补跑原始模型的无 parser 对照，可将输出协议影响与 LoRA 权重影响严格分离。",
        "",
    ]
    report_path = experiment / "REPORT.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    artifact_paths = [
        report_path,
        experiment / "task_status.jsonl",
        experiment / "summary.json",
        experiment / "manifest.json",
        experiment / "command.txt",
        experiment / "baseline_reference.txt",
        evaluation_path,
        experiment / "logs" / "run.log",
        *[snapshot_dir / name for name in script_names],
    ]
    checksum_lines = [
        f"{sha256(path)}  {path.relative_to(experiment)}"
        for path in artifact_paths
        if path.is_file()
    ]
    (experiment / "artifacts.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
