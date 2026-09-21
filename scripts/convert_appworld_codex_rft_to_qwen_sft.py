#!/usr/bin/env python3
"""Convert accepted Codex AppWorld RFT trajectories to Qwen completion-only SFT data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Template


SCHEMA_VERSION = "appworld-codex-rft-qwen-sft-v1"
TARGET_MODEL = "Qwen/Qwen3-8B"
SOURCE_KIND = "accepted_codex_loop_style_rft_trajectory"
SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "card_number",
    "security_code",
    "cvv",
    "pin",
)
PLACEHOLDERS = {
    "string",
    "bearer",
    "integer",
    "number",
    "null",
    "none",
    "<redacted>",
    "<redacted_jwt>",
}
FORBIDDEN_DYNAMIC_PATTERNS = {
    "ground_truth": re.compile(r"\bground_truth\b", re.IGNORECASE),
    "private_data": re.compile(r"\bprivate_data\b", re.IGNORECASE),
    "test_data": re.compile(r"\btest_data\b", re.IGNORECASE),
    "solution_module": re.compile(r"\b(?:compiled_)?solution\.py\b", re.IGNORECASE),
    "evaluation_module": re.compile(r"\bevaluation\.py\b", re.IGNORECASE),
    "evaluator_assertions": re.compile(r"\bevaluator_assertions\b", re.IGNORECASE),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-list", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--prompt-template", type=Path, required=True)
    parser.add_argument("--max-observation-chars", type=int, default=24000)
    parser.add_argument("--training-max-length", type=int, default=40960)
    parser.add_argument("--expected-tasks", type=int, default=90)
    return parser.parse_args()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exception:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exception
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")


def text_to_messages(prompt: str) -> list[dict[str, str]]:
    messages: list[dict[str, str | None]] = []
    last_start = 0
    for match in re.finditer(r"(USER|ASSISTANT|SYSTEM):\n", prompt, flags=re.IGNORECASE):
        marker_start = match.span()[0]
        if not messages and marker_start != 0:
            raise ValueError("official prompt has content before its first role marker")
        if messages:
            messages[-1]["content"] = prompt[last_start:marker_start]
        messages.append({"role": match.group(1).lower(), "content": None})
        last_start = match.span()[1]
    if not messages:
        raise ValueError("official prompt contains no role markers")
    messages[-1]["content"] = prompt[last_start:]
    return [{"role": str(item["role"]), "content": str(item["content"])} for item in messages]


def assistant_message(reasoning: str, code: str) -> dict[str, str]:
    reasoning = reasoning.strip()
    code = code.strip()
    if not reasoning or not code:
        raise ValueError("empty reasoning or code")
    if "```" in code:
        raise ValueError("executed code unexpectedly contains a markdown fence")
    return {
        "role": "assistant",
        "content": f"{reasoning}\n\n```python\n{code}\n```\n\n",
    }


def observation_message(observation: str) -> dict[str, str]:
    newline = "" if observation.endswith("\n") else "\n"
    return {"role": "user", "content": f"Output:\n```\n{observation}{newline}```\n\n"}


def truncate_observation(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return text[:head] + "\n...[OBSERVATION TRUNCATED FOR POLICY CONTEXT]...\n" + text[-tail:]


def sensitive_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                any(fragment in str(key).lower() for fragment in SENSITIVE_KEY_FRAGMENTS)
                and isinstance(item, str)
                and len(item) >= 6
                and item.lower() not in PLACEHOLDERS
            ):
                found.append(item)
            else:
                found.extend(sensitive_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(sensitive_values(item))
    return found


def validate_source(row: dict[str, Any]) -> None:
    task_id = str(row.get("task", {}).get("task_id", "<missing>"))
    if row.get("schema_version") != "appworld-codex-rft-attempt-v2":
        raise ValueError(f"{task_id}: unexpected source schema")
    if row.get("accepted") is not True or row.get("evaluation", {}).get("success") is not True:
        raise ValueError(f"{task_id}: source is not official-evaluator successful")
    if row.get("generation_error") is not None:
        raise ValueError(f"{task_id}: accepted source has generation error")
    if row.get("task_completed") is not True:
        raise ValueError(f"{task_id}: accepted source did not call complete_task")
    if row.get("policy", {}).get("ground_truth_visible_to_policy") is not False:
        raise ValueError(f"{task_id}: ground-truth visibility invariant failed")
    if row.get("policy", {}).get("thread_mode") != "persistent_one_thread_per_attempt":
        raise ValueError(f"{task_id}: unexpected thread mode")
    thread_id = row.get("policy", {}).get("codex_thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise ValueError(f"{task_id}: missing Codex thread ID")
    steps = row.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > 40:
        raise ValueError(f"{task_id}: invalid step count")
    for index, step in enumerate(steps, 1):
        if step.get("interaction") != index:
            raise ValueError(f"{task_id}: non-contiguous interaction index")
        for key in ("reasoning", "code", "observation", "policy_observation"):
            if not isinstance(step.get(key), str):
                raise ValueError(f"{task_id}:{index}: invalid {key}")
        item_types = set(step.get("codex_event_item_types", []))
        if item_types - {"agent_message"}:
            raise ValueError(f"{task_id}:{index}: forbidden Codex event types {item_types}")


def render_public_messages(
    task_id: str, prompt_template: str, source_task: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    from appworld.task import Task

    task = Task.load(task_id=task_id, load_ground_truth=False)
    try:
        public_task = {
            "task_id": task.id,
            "instruction": task.instruction,
            "supervisor": {
                "first_name": task.supervisor.first_name,
                "last_name": task.supervisor.last_name,
                "email": task.supervisor.email,
                "phone_number": task.supervisor.phone_number,
            },
            "datetime": task.datetime.isoformat(),
        }
        if public_task != source_task:
            raise ValueError(f"{task_id}: public Task.load fields differ from source trajectory")
        descriptions = json.dumps(
            [{"name": key, "description": value} for key, value in task.app_descriptions.items()],
            ensure_ascii=False,
            indent=1,
        )
        rendered = Template(prompt_template.lstrip()).render(
            instruction=task.instruction,
            main_user=task.supervisor,
            app_descriptions=descriptions,
        )
    finally:
        task.close()
    return text_to_messages(rendered + "\n\n"), public_task


def output_hashes(root: Path, relative_paths: list[str]) -> dict[str, str]:
    return {relative: sha256_file(root / relative) for relative in sorted(relative_paths)}


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    train_list = args.train_list.resolve()
    runtime_root = args.runtime_root.resolve()
    prompt_path = args.prompt_template.resolve()
    staging = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    if output.exists() or staging.exists():
        raise FileExistsError(f"refusing to overwrite output or staging directory: {output}")

    rows = read_jsonl(source)
    if len(rows) != args.expected_tasks:
        raise ValueError(f"expected {args.expected_tasks} accepted tasks, found {len(rows)}")
    for row in rows:
        validate_source(row)

    train_ids = [line.strip() for line in train_list.read_text().splitlines() if line.strip()]
    if len(train_ids) != args.expected_tasks or len(set(train_ids)) != args.expected_tasks:
        raise ValueError("train.txt is not the expected unique 90-task list")
    by_task = {str(row["task"]["task_id"]): row for row in rows}
    if len(by_task) != len(rows) or set(by_task) != set(train_ids):
        raise ValueError("accepted source task IDs do not exactly match train.txt")
    rows = [by_task[task_id] for task_id in train_ids]
    thread_ids = [str(row["policy"]["codex_thread_id"]) for row in rows]
    if len(set(thread_ids)) != len(thread_ids):
        raise ValueError("accepted trajectories do not have unique Codex thread IDs")

    os.environ["APPWORLD_ROOT"] = str(runtime_root)
    from appworld import update_root

    update_root(str(runtime_root))
    prompt_template = prompt_path.read_text(encoding="utf-8")
    staging.mkdir(parents=True)
    (staging / "tasks").mkdir()
    (staging / "scripts").mkdir()

    all_samples: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    task_files: list[str] = []
    source_row_hashes: dict[str, str] = {}
    source_attempts: dict[str, str] = {}
    sensitive_checked = 0
    sensitive_leaks = 0
    redaction_markers = 0
    observation_truncations = 0
    forbidden_findings: Counter[str] = Counter()
    execution_recovery_tasks = 0

    for row in rows:
        task_id = str(row["task"]["task_id"])
        base_messages, public_task = render_public_messages(
            task_id, prompt_template, dict(row["task"])
        )
        history = deepcopy(base_messages)
        instruction_message_count = len(base_messages)
        row_sha = sha256_bytes(canonical_json(row).encode("utf-8"))
        source_row_hashes[task_id] = row_sha
        source_attempts[task_id] = str(row["attempt_id"])
        task_samples: list[dict[str, Any]] = []
        execution_recovery_tasks += int(row.get("execution_failure_count", 0) > 0)

        for step in row["steps"]:
            index = int(step["interaction"])
            target = assistant_message(step["reasoning"], step["code"])
            policy_observation = str(step["policy_observation"])
            model_observation = truncate_observation(policy_observation, args.max_observation_chars)
            observation_truncations += int(model_observation != policy_observation)
            redaction_markers += model_observation.count("<REDACTED")

            try:
                raw_value = json.loads(step["observation"])
            except json.JSONDecodeError:
                raw_value = None
            if raw_value is not None:
                for secret in sensitive_values(raw_value):
                    sensitive_checked += 1
                    if secret in model_observation:
                        sensitive_leaks += 1

            dynamic_blob = target["content"] + "\n" + model_observation
            for name, pattern in FORBIDDEN_DYNAMIC_PATTERNS.items():
                if pattern.search(dynamic_blob):
                    forbidden_findings[name] += 1

            sample = {
                "id": f"{task_id}::assistant-{index:04d}",
                "prompt": deepcopy(history),
                "completion": [deepcopy(target)],
                "tools": None,
                "metadata": {
                    "schema_version": SCHEMA_VERSION,
                    "task_id": task_id,
                    "task_family": task_id.rsplit("_", 1)[0],
                    "split": "train",
                    "step_index": index,
                    "source": SOURCE_KIND,
                    "source_attempt_id": row["attempt_id"],
                    "source_trajectory_sha256": row_sha,
                    "target_model": TARGET_MODEL,
                    "chat_protocol": "appworld_simplified_react_code_agent",
                    "loss_policy": "assistant_completion_only",
                    "reasoning_policy": "codex_visible_rationale_preserved",
                    "observation_policy": "credential_redacted_then_24000_char_head_tail_truncated",
                    "prompt_message_count": len(history),
                    "target_message_index": len(history),
                    "official_evaluation_success": True,
                    "clean_replay_success": None,
                },
            }
            task_samples.append(sample)
            all_samples.append(sample)
            history.append(target)
            history.append(observation_message(model_observation))

        full_rows.append(
            {
                "id": task_id,
                "messages": history,
                "tools": None,
                "metadata": {
                    "schema_version": SCHEMA_VERSION,
                    "task_id": task_id,
                    "task_family": task_id.rsplit("_", 1)[0],
                    "split": "train",
                    "source": SOURCE_KIND,
                    "source_attempt_id": row["attempt_id"],
                    "source_trajectory_sha256": row_sha,
                    "source_codex_thread_id": row["policy"]["codex_thread_id"],
                    "target_model": TARGET_MODEL,
                    "chat_protocol": "appworld_simplified_react_code_agent",
                    "num_instruction_messages": instruction_message_count,
                    "step_count": len(row["steps"]),
                    "official_evaluation_success": True,
                    "clean_replay_success": None,
                    "raw_observations_included": False,
                    "ground_truth_in_model_messages": False,
                    "max_observation_chars": args.max_observation_chars,
                },
            }
        )
        relative_task_file = f"tasks/{task_id}.json"
        write_json(staging / relative_task_file, task_samples)
        task_files.append(relative_task_file)

    if sensitive_leaks:
        raise ValueError(f"source policy observations contain {sensitive_leaks} sensitive leaks")
    if forbidden_findings:
        raise ValueError(f"privileged dynamic-context findings: {dict(forbidden_findings)}")

    write_jsonl(staging / "train.jsonl", all_samples)
    write_jsonl(staging / "full_trajectories.jsonl", full_rows)
    (staging / "task_ids.txt").write_text("\n".join(train_ids) + "\n", encoding="utf-8")

    difficulty_tasks: dict[str, list[str]] = {"1": [], "2": [], "3": []}
    for task_id in train_ids:
        metadata_path = runtime_root / "data" / "tasks" / task_id / "ground_truth" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        difficulty = str(metadata["difficulty"])
        if difficulty not in difficulty_tasks:
            raise ValueError(f"{task_id}: unexpected difficulty {difficulty}")
        difficulty_tasks[difficulty].append(task_id)
    difficulty_summary = {
        "purpose": "post-hoc analysis only; this file is not model input",
        "appworld_field": "ground_truth.metadata.difficulty",
        "labels": {"1": "easy", "2": "medium", "3": "hard"},
        "counts": {key: len(value) for key, value in difficulty_tasks.items()},
        "task_ids": difficulty_tasks,
    }
    write_json(staging / "difficulty_summary.json", difficulty_summary)

    readme = f"""# AppWorld Codex LOOP-style RFT → Qwen3-8B SFT（train90）

本数据集把 {len(rows)} 条官方 evaluator 成功的 Codex RFT 轨迹转换成
{len(all_samples)} 条决策级 completion-only SFT 样本。`train.jsonl` 可直接由本仓库
`scripts/minimal_sft_train.py` / `scripts/continue_appworld_react_lora.py` 读取。

## 核心文件

- `train.jsonl`：全部 {len(all_samples)} 个下一步 assistant 决策；训练主文件。
- `full_trajectories.jsonl`：90 条完整对话，仅用于审计。
- `tasks/<task_id>.json`：逐题决策样本。
- `difficulty_summary.json`：AppWorld 难度后验统计；不进入模型输入。
- `manifest.json`：来源、哈希、转换策略和计数。
- `validation.json`：运行 Qwen tokenizer 校验脚本后生成。

## 与 ground-truth 教师轨迹的差异

这些动作由 Codex 在真实环境 observation 上闭环产生，不使用 solution、隐藏 evaluator
断言或 ground-truth API 序列。它们包含真实文档探索、状态检查、冗余动作，以及
{execution_recovery_tasks} 条成功轨迹中的执行错误恢复。模型消息只使用采样时 Codex 实际
看到的脱敏 `policy_observation`；raw observation 不进入本数据集。
每轮 observation 还复现采样时的 24,000 字符前后截断，因此不会误纳入 Codex 未看到的内容。

但这不是“保证提升”的数据：90 条成功轨迹只有一个任务曾触发 RFT 拒绝重采，策略风格
仍主要来自单一强教师 Codex。建议先做受控 LoRA，对比相同基座、相同超参数的旧数据、
本数据和混合数据，并以 held-out AppWorld Dev 的官方闭环指标为准。

## 训练契约

每行使用 Qwen chat template，`enable_thinking=False`；prompt 与 padding label 设为 -100，
仅单条 assistant completion 参与 loss。不要把 `full_trajectories.jsonl` 当作整轨迹 target。
推荐 `max_length={args.training_max_length}`，即 Qwen3-8B 的原生上下文上限。
"""
    (staging / "README.md").write_text(readme, encoding="utf-8")
    shutil.copy2(Path(__file__).resolve(), staging / "scripts" / Path(__file__).name)
    validator_source = Path(__file__).with_name("validate_appworld_codex_rft_qwen_sft.py")
    if not validator_source.is_file():
        raise FileNotFoundError(validator_source)
    shutil.copy2(validator_source, staging / "scripts" / validator_source.name)

    hashed_paths = [
        "README.md",
        "train.jsonl",
        f"scripts/{validator_source.name}",
        "full_trajectories.jsonl",
        "task_ids.txt",
        "difficulty_summary.json",
        f"scripts/{Path(__file__).name}",
        *task_files,
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "train_list_path": str(train_list),
        "train_list_sha256": sha256_file(train_list),
        "official_prompt_template_path": str(prompt_path),
        "official_prompt_template_sha256": sha256_file(prompt_path),
        "source_row_sha256": source_row_hashes,
        "source_attempt_ids": source_attempts,
        "conversion": {
            "sample_unit": "one next-assistant-decision per row",
            "loss_policy": "assistant completion only",
            "history_policy": "full public prompt plus all prior model-visible observations",
            "reasoning_policy": "preserve Codex visible rationale",
            "action_policy": "preserve exact executed Python in one fenced code block",
            "observation_policy": "use redacted policy_observation with the same 24000-character head/tail truncation used during Codex sampling; exclude raw observation",
            "context_window": {
                "training_max_length": args.training_max_length,
                "history_truncation": "none after per-observation truncation",
                "model_native_max_position_embeddings": 40960,
            },
            "student_excluded": [
                "ground_truth API calls",
                "solution source",
                "evaluator assertions",
                "raw observations",
                "credential values",
                "failed attempt afc0fce_2__attempt_01",
            ],
            "enable_thinking": False,
        },
        "counts": {
            "tasks": len(rows),
            "decision_samples": len(all_samples),
            "task_families": len({task_id.rsplit("_", 1)[0] for task_id in train_ids}),
            "per_task_json_files": len(task_files),
            "source_execution_recovery_tasks": execution_recovery_tasks,
            "sensitive_value_occurrences_checked": sensitive_checked,
            "sensitive_value_leaks": sensitive_leaks,
            "policy_redaction_markers": redaction_markers,
            "observation_truncations": observation_truncations,
            "difficulty_1": len(difficulty_tasks["1"]),
            "difficulty_2": len(difficulty_tasks["2"]),
            "difficulty_3": len(difficulty_tasks["3"]),
        },
        "output_sha256": output_hashes(staging, hashed_paths),
        "validation_status": "NOT_RUN",
    }
    write_json(staging / "manifest.json", manifest)
    os.replace(staging, output)
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
