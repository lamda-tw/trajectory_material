#!/usr/bin/env python3
"""Audit a completed AppWorld dev run and write status JSONL plus a Markdown report."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
from pathlib import Path


EXPERIMENT_NAME = "simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev"


def nonempty_line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def extract_run_times(run_log: str) -> tuple[dt.datetime | None, dt.datetime | None]:
    starts = re.findall(r"^run_started_at=(.+)$", run_log, flags=re.MULTILINE)
    ends = re.findall(r"^run_finished_at=(.+)$", run_log, flags=re.MULTILINE)
    # The first two attempts were pre-inference setup failures. The last start is
    # the actual run start and the last end is the completed run end.
    start = parse_iso(starts[-1].strip()) if starts else None
    end = parse_iso(ends[-1].strip()) if ends else None
    return start, end


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes}m {secs}s"


def directory_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            pass
    return total


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TiB"


def usage_for_task(task_dir: Path) -> tuple[int, int]:
    usage = load_json(task_dir / "misc" / "usage.json").get("tokens", {})
    input_tokens = int(usage.get("input_cache_miss", 0) or 0)
    input_tokens += int(usage.get("input_cache_hit", 0) or 0)
    output_tokens = int(usage.get("output", 0) or 0)
    return input_tokens, output_tokens


def lm_timing(task_dir: Path) -> tuple[int, float]:
    path = task_dir / "logs" / "lm_calls.jsonl"
    tokens = 0
    seconds = 0.0
    if not path.is_file():
        return tokens, seconds
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                output = json.loads(line).get("output", {})
                tokens += int(output.get("usage", {}).get("completion_tokens", 0) or 0)
                timestamps = output.get("timestamps", {})
                start = parse_iso(timestamps.get("start"))
                end = parse_iso(timestamps.get("end"))
                if start and end:
                    seconds += max(0.0, (end - start).total_seconds())
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return tokens, seconds


def evaluator_summary(item: dict) -> str:
    requirements = [str(x.get("requirement", "")).strip() for x in item.get("failures", [])]
    requirements = [x for x in requirements if x]
    return "; ".join(requirements) if requirements else "official evaluator marked task unsuccessful"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dataset_path = root / "data" / "datasets" / "dev.txt"
    output_root = root / "experiments" / "outputs" / EXPERIMENT_NAME
    task_root = output_root / "tasks"
    aggregate_path = output_root / "evaluations" / "dev.json"
    run_log_path = root / "logs" / "run.log"

    task_ids = [line.strip() for line in read_text(dataset_path).splitlines() if line.strip()]
    aggregate = load_json(aggregate_path)
    individual = aggregate.get("individual", {})
    records: list[dict] = []
    signal_counts: collections.Counter[str] = collections.Counter()
    failed_requirements: collections.Counter[str] = collections.Counter()
    total_input_tokens = 0
    total_output_tokens = 0
    total_lm_calls = 0
    total_api_calls = 0
    timed_output_tokens = 0
    lm_seconds = 0.0

    for task_id in task_ids:
        task_dir = task_root / task_id
        lm_path = task_dir / "logs" / "lm_calls.jsonl"
        env_path = task_dir / "logs" / "environment_io.md"
        api_path = task_dir / "logs" / "api_calls.jsonl"
        finished_path = task_dir / "misc" / "finished"
        report_path = task_dir / "evaluation" / "report.md"
        item = individual.get(task_id, {})
        started = task_dir.is_dir()
        lm_calls = nonempty_line_count(lm_path)
        api_calls = nonempty_line_count(api_path)
        has_environment = env_path.is_file() and env_path.stat().st_size > 0
        finished = finished_path.is_file()
        evaluated = report_path.is_file() and task_id in individual
        success = bool(item.get("success")) if evaluated else None

        input_tokens, output_tokens = usage_for_task(task_dir)
        timed_tokens, seconds = lm_timing(task_dir)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_lm_calls += lm_calls
        total_api_calls += api_calls
        timed_output_tokens += timed_tokens
        lm_seconds += seconds

        combined = (read_text(env_path) + "\n" + read_text(task_dir / "logs" / "logger.log")).lower()
        if "no code available to execute" in combined:
            signal_counts["no_executable_code"] += 1
        if "response status code is 422" in combined or "validation error" in combined:
            signal_counts["api_validation_error"] += 1
        if "execution failed. traceback" in combined:
            signal_counts["python_execution_error"] += 1
        if "maximum number of steps" in combined or "max steps" in combined:
            signal_counts["max_steps_or_budget"] += 1
        if lm_calls >= 50:
            signal_counts["max_steps_reached"] += 1

        if success:
            category = "success"
            summary = "official evaluator success"
            rerun = False
        elif not started:
            category = "infrastructure_not_started"
            summary = "no task output directory"
            rerun = True
        elif not finished:
            category = "infrastructure_incomplete"
            summary = "task started but official finished marker is absent"
            rerun = True
        elif not evaluated:
            category = "evaluation_missing"
            summary = "task finished but task-specific evaluation result is absent"
            rerun = True
        else:
            category = "model_or_agent_failure"
            summary = evaluator_summary(item)
            rerun = False
            for failure in item.get("failures", []):
                requirement = str(failure.get("requirement", "unknown requirement")).strip()
                failed_requirements[requirement] += 1

        records.append(
            {
                "task_id": task_id,
                "scenario_id": task_id.rsplit("_", 1)[0],
                "started": started,
                "has_lm_calls": lm_calls > 0,
                "lm_calls": lm_calls,
                "has_environment_interaction": has_environment,
                "api_calls": api_calls,
                "finished": finished,
                "evaluated": evaluated,
                "task_success": success,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "failure_category": category,
                "failure_summary": summary,
                "needs_rerun": rerun,
            }
        )

    status_path = root / "task_status.jsonl"
    with status_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = collections.Counter(record["failure_category"] for record in records)
    started_count = sum(record["started"] for record in records)
    lm_count = sum(record["has_lm_calls"] for record in records)
    env_count = sum(record["has_environment_interaction"] for record in records)
    finished_count = sum(record["finished"] for record in records)
    evaluated_count = sum(record["evaluated"] for record in records)
    success_count = sum(record["task_success"] is True for record in records)
    model_failure_count = counts["model_or_agent_failure"]
    infra_count = sum(
        counts[name]
        for name in ("infrastructure_not_started", "infrastructure_incomplete", "evaluation_missing")
    )
    pipeline_complete = (
        len(records) == len(set(task_ids))
        and started_count == len(task_ids)
        and lm_count == len(task_ids)
        and finished_count == len(task_ids)
        and evaluated_count == len(task_ids)
        and infra_count == 0
    )

    run_log = read_text(run_log_path)
    run_start, run_end = extract_run_times(run_log)
    duration = (run_end - run_start).total_seconds() if run_start and run_end else None
    throughput = timed_output_tokens / lm_seconds if lm_seconds else 0.0
    aggregate_scores = aggregate.get("aggregate", {})
    tgc = aggregate_scores.get("task_goal_completion", "unavailable")
    sgc = aggregate_scores.get("scenario_goal_completion", "unavailable")
    run_exit_codes = re.findall(r"^run_exit_code=(\d+)$", run_log, flags=re.MULTILINE)
    final_exit = run_exit_codes[-1] if run_exit_codes else "unavailable"

    missing_ids = [r["task_id"] for r in records if r["needs_rerun"]]
    requirement_rows = "\n".join(
        f"| {' '.join(requirement.split()).replace('|', '/')} | {count} |"
        for requirement, count in failed_requirements.most_common(12)
    ) or "| none | 0 |"
    signal_rows = "\n".join(
        f"| {name} | {count} |" for name, count in signal_counts.most_common()
    ) or "| none detected | 0 |"

    conclusion = (
        "完整 dev 的推理与评分链路已跑通。"
        if pipeline_complete
        else "完整 dev 尚不能判定为全部跑通；存在未启动、未结束或未评分任务。"
    )
    missing_text = ", ".join(missing_ids) if missing_ids else "无"
    success_ids = [r["task_id"] for r in records if r["task_success"] is True]
    success_ids_text = ", ".join(success_ids) if success_ids else "无"
    top_lm = sorted(((r["lm_calls"], r["task_id"]) for r in records), reverse=True)[:5]
    top_api = sorted(((r["api_calls"], r["task_id"]) for r in records), reverse=True)[:5]
    top_lm_text = ", ".join(f"{task_id}={count}" for count, task_id in top_lm)
    top_api_text = ", ".join(f"{task_id}={count}" for count, task_id in top_api)
    pre_inference_incidents = run_log.count("run_exit_code=1")

    report = f"""# AppWorld Qwen3-8B one-shot 完整 dev 运行报告

## 一、结论摘要

{conclusion}

- dev 清单：{len(task_ids)} 条，{len(set(task_ids))} 个唯一 task，{len(set(r['scenario_id'] for r in records))} 个 scenario。
- 实际启动：{started_count}/{len(task_ids)}；产生 LM 调用：{lm_count}/{len(task_ids)}；产生环境交互：{env_count}/{len(task_ids)}。
- 正常写入 `misc/finished`：{finished_count}/{len(task_ids)}；成功完成 task-specific evaluation：{evaluated_count}/{len(task_ids)}。
- 官方成功任务：{success_count}；模型/Agent 失败：{model_failure_count}；基础设施或评分链路失败：{infra_count}。
- 成功 task IDs：{success_ids_text}。
- TGC：{tgc}；SGC：{sgc}；最终运行退出码：{final_exit}。
- 需要重跑的任务：{missing_text}。

这里把“任务答错”和“系统没有跑完”严格分开：只要任务进入 Agent、写入 finished，并成功执行官方 evaluator，即使得分为 0，也算推理/评分基础设施链路完成。

## 二、实验范围与固定配置

| 项目 | 配置 |
|---|---|
| 模型 | `/root/autodl-tmp/models/Qwen3-8B`，原权重只读 |
| Agent | 官方 `simplified_react_code_agent` |
| Prompt | 官方 ReAct code-agent instructions，包含一个 worked example，因此属于 one-shot |
| 模型 preset | `qwen3-8b-with-reasoning` |
| temperature / seed | 0.0 / 100 |
| max completion | 3000 tokens/LM call |
| max steps | 50/task |
| vLLM context | 32000（与 smoke 实际命令一致） |
| 调度 | 1 个 AppWorld 进程，任务顺序执行，GPU0 |
| AppWorld | 0.2.0.dev0，Python 3.12.3 |
| vLLM / PyTorch / CUDA | 0.10.2 / 2.8.0+cu128 / 12.8 |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition，97887 MiB |

本次没有训练、微调或修改模型权重。原始 `api_docs`、`base_dbs`、`tasks`、`dev.txt` 通过符号链接复用，没有复制大体积数据。官方自动生成的 Agent config 被隔离到本实验 `config/agent_configs`，没有写入已安装 Python 环境。需要说明：普通符号链接并不提供文件系统级只读保护；官方 evaluator 动态导入 task-specific evaluation.py 时，在原始 tasks/*/ground_truth/__pycache__ 下生成了 54 个 .pyc 缓存文件。审计未发现其他类型的原始数据文件在正式运行期间被写入，模型目录和旧 smoke 实验也没有本次运行产生的新文件。已有 .pyc 按不再修改原始目录的约束保留、不做删除；复现脚本现已加入 PYTHONDONTWRITEBYTECODE=1，防止后续运行再次生成此类缓存。

## 三、数据流与执行链路

```text
data/datasets/dev.txt
        │ 读取 57 个 task_id
        ▼
Task.load(task_id) + 初始 base DB
        │
        ▼
官方 one-shot instructions + 当前任务描述
        │ OpenAI-compatible Chat Completions
        ▼
本地 vLLM / Qwen3-8B
        │ reasoning_content + Python code
        ▼
simplified ReAct Agent 提取代码
        │
        ▼
AppWorld Python sandbox 执行
        │ apis.<app>.<method>(...)
        ▼
模拟应用 API 与任务私有数据库
        │ 返回值、异常、DB 变化反馈给下一轮模型
        ├─────────────── 回到模型，最多 50 steps
        ▼
Supervisor 最终 task state + 输出 DB changes
        │
        ▼
appworld.evaluator.evaluate_dataset/evaluate_task
        │ 动态加载 data/tasks/<task_id>/ground_truth/evaluation.py
        ▼
逐任务 success → TGC / 按 scenario 最弱变体聚合的 SGC
```

`logger.jsonl` 是最接近顺序轨迹的结构化日志；`lm_calls.jsonl` 保存完整模型请求/响应；`environment_io.md` 保存代码与执行反馈；`api_calls.jsonl` 保存底层 API 请求；`dbs/` 保存状态变化；`evaluation/report.md` 是评分报告。不存在一个天然包含全部层次的单一文件，训练轨迹若需要无损重建，应按 task_id 和 step 顺序组合这些来源。

## 四、完整性核对

| 检查项 | 数量 | 期望 |
|---|---:|---:|
| dev 唯一 task | {len(set(task_ids))} | {len(task_ids)} |
| 创建 task 输出目录 | {started_count} | {len(task_ids)} |
| 至少一次 LM 调用 | {lm_count} | {len(task_ids)} |
| 环境交互日志非空 | {env_count} | {len(task_ids)} |
| finished 标记 | {finished_count} | {len(task_ids)} |
| task-specific evaluation | {evaluated_count} | {len(task_ids)} |
| 官方 success | {success_count} | 仅作能力观测 |
| 模型/Agent 失败 | {model_failure_count} | 不计为基础设施失败 |
| 基础设施/评分失败 | {infra_count} | 0 |

机器可读明细见 `{status_path}`。

## 五、评分结果与口径

- TGC = 100 × 全部 task success 的均值；本次为 `{tgc}`。
- SGC 先把同一 scenario 的三个 task 组合，并取三个 success 的最小值，再跨 scenario 求均值；本次为 `{sgc}`。
- task success 只有布尔值：task-specific tests 必须全部通过，没有部分任务分。
- 评分调用链：`appworld run --with-evaluation` → `appworld.cli.evaluate()` → `appworld.evaluator.evaluate_dataset()` → `evaluate_tasks()` → `evaluate_task()` → `data/tasks/<task_id>/ground_truth/evaluation.py`。
- 评分比较运行前任务数据库与本实验结束数据库，并检查 Supervisor 最终答案；不依赖 Docker。

最常见的 evaluator 失败要求：

| requirement | tasks |
|---|---:|
{requirement_rows}

## 六、模型行为与失败信号

以下信号来自每个任务的执行轨迹，只用于定位 base 模型/Agent 行为，不等同于基础设施失败；同一任务可命中多个信号。

| 轨迹信号 | 涉及任务数 |
|---|---:|
{signal_rows}

Qwen3-8B 当前主要风险通常位于长程 Agent 能力，而不是单轮自然语言生成：需要正确发现 API、理解参数 schema、分页汇总、维护跨轮中间状态、根据异常修正代码、避免臆造结果，并在真正取得答案后准确调用 Supervisor 完成任务。官方 one-shot 示例还可能造成任务策略锚定；本实验保持 Prompt 不变，是为了与 smoke 结果可比。

## 七、运行资源、时间与产物

- 正式推理开始：{run_start.isoformat() if run_start else 'unknown'}。
- 正式推理结束：{run_end.isoformat() if run_end else 'unknown'}。
- 正式运行墙钟时间：{human_duration(duration)}。
- LM calls：{total_lm_calls}；底层 API calls：{total_api_calls}。
- LM calls 最多的任务：{top_lm_text}。
- API calls 最多的任务：{top_api_text}。
- 输入 tokens：{total_input_tokens:,}；输出 tokens：{total_output_tokens:,}；合计：{total_input_tokens + total_output_tokens:,}。
- 按每次 LM response 的 start/end 时间累计计算，输出吞吐约 {throughput:.2f} tokens/s。该值排除了 AppWorld API 和 Python 执行时间。
- 实验目录实际文件占用（不跟随数据符号链接）：{human_bytes(directory_size(root))}。

关键位置：

- 实验根：`{root}`
- 实验配置：`{root}/config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev.jsonnet`
- 渲染后配置：`{output_root}/configs/dev.json`
- 模型服务日志：`{output_root}/model_server.log`
- aggregate evaluation：`{output_root}/evaluations/dev.json`
- 每任务产物：`{task_root}/<task_id>/`
- 状态清单：`{status_path}`
- 总运行日志：`{run_log_path}`

## 八、基础设施事件与恢复

正式推理前共记录到 {pre_inference_incidents} 次 exit=1 的隔离启动检查失败：第一次缺少新 `APPWORLD_CACHE` 下的 evaluator test assets；第二次缺少隔离 config overlay 下的官方 `_generator` 模板。处理方式分别是复制 2.4 MiB 的已验证 tests cache，以及只读符号链接官方 `_generator`。两次均发生在模型服务和任务运行之前，没有形成或覆盖任务轨迹。第三次启动保持模型、Prompt 和 Agent 参数不变。

正式评分阶段还暴露了一个只读边界问题：由于 tasks 是指向原始数据的普通符号链接，Python 导入 57 个 task-specific evaluator 时，对尚无对应缓存的 54 个任务生成了 .pyc。这些文件只是解释器字节码缓存，不参与任务输入、数据库状态或评分语义，因此不改变本次分数；但它们属于对原始数据树的意外写入。按不再修改原始目录的约束，本次保留现场、不做删除；后续脚本通过 PYTHONDONTWRITEBYTECODE=1 阻止同类写入。

由于官方配置含 `skip_if_finished=true`，如进程中断，可使用同一个实验根重新运行：

```bash
/root/autodl-tmp/workspace-tw/scripts/run_appworld_qwen3_react_full_dev.sh {root}
```

runner 会跳过已有 `misc/finished` 的 task，只执行未完成任务；不要使用 `--clear-first`。

## 九、最终判断

{conclusion}

能力分数只说明当前 8B base 模型在固定 one-shot ReAct scaffold 下的端到端任务成功率；它不应与基础设施可用性混为一谈。后续模型改进应优先考虑高质量工具轨迹 SFT、API schema/分页/状态管理专项数据、执行反馈驱动的纠错训练，以及在冻结 dev/test 前建立小规模可迭代诊断集。
"""

    report_path = root / "FULL_DEV_RUN_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({
        "tasks": len(records),
        "started": started_count,
        "finished": finished_count,
        "evaluated": evaluated_count,
        "success": success_count,
        "model_or_agent_failure": model_failure_count,
        "infrastructure_failure": infra_count,
        "pipeline_complete": pipeline_complete,
        "tgc": tgc,
        "sgc": sgc,
        "report": str(report_path),
        "status": str(status_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
