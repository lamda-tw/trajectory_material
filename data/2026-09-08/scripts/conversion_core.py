#!/usr/bin/env python3
"""Convert seven high-O2 EI agent trajectories into Qwen3-8B SFT data.

All outputs are written below this script's parent dataset directory.  Source
files are read-only and are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


DATASET_DATE = "2026-09-08"
TARGET_MODEL = "Qwen/Qwen3-8B"
CONTEXT_CHAR_BUDGET = 24_000
ROOT_USER_CHAR_LIMIT = 16_000
TOOL_RESULT_CHAR_LIMIT = 10_000
COMPLETION_CHAR_LIMIT = 16_000

SELECTED = {
    "EI-56TESTPK0010-easy-v1.2": {"split": "validation", "family": "0010"},
    "EI-56TESTPK0010-medium-v1.2": {"split": "validation", "family": "0010"},
    "EI-56TESTPK0006-easy-v1.2": {"split": "train", "family": "0006"},
    "EI-56TESTPK0007-medium-v1.2": {"split": "train", "family": "0007"},
    "EI-56TESTPK0008-easy-v1.2": {"split": "train", "family": "0008"},
    "EI-56TESTPK0008-medium-v1.2": {"split": "train", "family": "0008"},
    "EI-56TESTPK0009-medium-v1.2": {"split": "train", "family": "0009"},
}

STABLE_SYSTEM_PROMPT = """你是一个面向 EI 排程与物料推演的工具型智能体。请严格依据用户需求、工作区文件和工具返回执行任务；先理解约束，再选择必要工具，持续维护当前任务状态。不得编造文件、执行结果或业务数据。遇到失败时应根据工具证据修正方案。在宣布完成前，必须检查正式产物、关键字段和验证结果，并向用户清楚说明已完成内容与仍存在的限制。"""

TOOL_DESCRIPTIONS = {
    "Skill": "加载并执行与当前任务匹配的工作流技能。",
    "TodoWrite": "创建或更新当前任务的进度列表。",
    "Read": "读取工作区内指定文件的内容。",
    "Write": "在工作区内写入指定文件。",
    "Edit": "编辑工作区内已有文件。",
    "Bash": "在工作区内运行 shell 命令并返回输出。",
    "Glob": "按照 glob 模式查找工作区文件。",
    "Grep": "在工作区文件中搜索文本。",
    "Agent": "把边界明确的子任务委派给子智能体。",
    "AskUserQuestion": "在缺少关键决策信息时向用户提问。",
    "present_files": "向用户呈现已生成的最终文件。",
}


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_output = script_path.parents[1]
    default_workspace = script_path.parents[4]
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=default_workspace)
    parser.add_argument("--output", type=Path, default=default_output)
    return parser.parse_args()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_runtime_text(text: str) -> str:
    text = text.replace("\\r\\n", "\\n")
    text = re.sub(r"/workspace/\.agent-work/s-[0-9a-fA-F-]+", ".agent-work/<SESSION>", text)
    text = text.replace("/workspace/data/", "data/")
    text = text.replace("/workspace/data", "data")
    text = text.replace("/workspace/", "./")
    text = text.replace("/workspace", ".")
    return text


def truncate_text(text: str, limit: int, label: str) -> tuple[str, int]:
    if len(text) <= limit:
        return text, 0
    omitted = len(text) - limit
    head_len = int(limit * 0.7)
    tail_len = limit - head_len
    digest = sha256_bytes(text.encode("utf-8"))[:16]
    marker = f"\n\n[<{label}_TRUNCATED omitted_chars={omitted} sha256={digest}>]\n\n"
    usable = max(limit - len(marker), 100)
    head_len = int(usable * 0.7)
    tail_len = usable - head_len
    return text[:head_len] + marker + text[-tail_len:], omitted


def flatten_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def iter_content_blocks(message: dict[str, Any]) -> Iterable[dict[str, Any]]:
    content = message.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                yield block
            else:
                yield {"type": "text", "text": flatten_content(block)}
    elif isinstance(content, str):
        yield {"type": "text", "text": content}
    elif content is not None:
        yield {"type": "text", "text": flatten_content(content)}


def normalize_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"value": normalize_runtime_text(value)}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def normalize_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_runtime_text(value)
    if isinstance(value, list):
        return [normalize_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_json_strings(item) for key, item in value.items()}
    return value


def flush_assistant(pending: dict[str, Any] | None, output: list[dict[str, Any]]) -> None:
    if not pending:
        return
    content = "\n\n".join(part.strip() for part in pending["text_parts"] if part.strip()).strip()
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if pending["tool_calls"]:
        message["tool_calls"] = pending["tool_calls"]
    if content or pending["tool_calls"]:
        output.append(message)


def normalize_trajectory(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, list[dict[str, Any]]]]:
    messages: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    counters: Counter[str] = Counter()
    observed_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    call_names: dict[str, str] = {}

    for source_message in raw.get("messages", []):
        role = source_message.get("role")
        if role == "assistant":
            if pending is None:
                pending = {"text_parts": [], "tool_calls": []}
            for block in iter_content_blocks(source_message):
                block_type = block.get("type")
                if block_type == "thinking":
                    thinking = flatten_content(block.get("thinking", block.get("text", "")))
                    counters["thinking_blocks_dropped"] += 1
                    counters["thinking_chars_dropped"] += len(thinking)
                elif block_type == "text":
                    text = normalize_runtime_text(flatten_content(block.get("text", "")))
                    if text.strip():
                        pending["text_parts"].append(text)
                        counters["assistant_text_blocks_kept"] += 1
                elif block_type == "tool_use":
                    tool_name = str(block.get("name", "")).strip()
                    tool_id = str(block.get("id", "")).strip()
                    arguments = normalize_json_strings(normalize_arguments(block.get("input")))
                    if not tool_name or not tool_id:
                        counters["invalid_tool_calls_dropped"] += 1
                        continue
                    pending["tool_calls"].append(
                        {
                            "id": tool_id,
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    )
                    observed_calls[tool_name].append(arguments)
                    call_names[tool_id] = tool_name
                    counters["tool_calls_kept"] += 1
                else:
                    counters["unsupported_assistant_blocks_dropped"] += 1
            continue

        flush_assistant(pending, messages)
        pending = None

        if role in {"system", "user"}:
            parts = []
            for block in iter_content_blocks(source_message):
                if block.get("type") == "text":
                    parts.append(normalize_runtime_text(flatten_content(block.get("text", ""))))
            text = "\n\n".join(part.strip() for part in parts if part.strip()).strip()
            if role == "system":
                if not messages or messages[0].get("role") != "system":
                    messages.append({"role": "system", "content": STABLE_SYSTEM_PROMPT})
                    counters["source_system_messages_replaced"] += 1
            elif text:
                messages.append({"role": "user", "content": text})
            continue

        if role == "tool":
            for block in iter_content_blocks(source_message):
                if block.get("type") != "tool_result":
                    counters["unsupported_tool_blocks_dropped"] += 1
                    continue
                call_id = str(block.get("tool_use_id", source_message.get("tool_call_id", ""))).strip()
                tool_name = call_names.get(call_id, str(source_message.get("name", "")).strip())
                result_text = normalize_runtime_text(flatten_content(block.get("content", "")))
                result_text, omitted = truncate_text(result_text, TOOL_RESULT_CHAR_LIMIT, "TOOL_RESULT")
                if omitted:
                    counters["tool_result_chars_omitted"] += omitted
                    counters["tool_results_truncated"] += 1
                status = "error" if block.get("is_error") else "ok"
                prefix = f"[tool_result status={status}"
                if tool_name:
                    prefix += f" name={tool_name}"
                prefix += "]\n"
                tool_message: dict[str, Any] = {
                    "role": "tool",
                    "content": prefix + result_text,
                }
                if call_id:
                    tool_message["tool_call_id"] = call_id
                if tool_name:
                    tool_message["name"] = tool_name
                messages.append(tool_message)
                counters["tool_results_kept"] += 1
            continue

        counters["unsupported_messages_dropped"] += 1

    flush_assistant(pending, messages)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": STABLE_SYSTEM_PROMPT})
    return messages, dict(counters), observed_calls


def value_schema(values: list[Any]) -> dict[str, Any]:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return {}
    types = set()
    for value in non_null:
        if isinstance(value, bool):
            types.add("boolean")
        elif isinstance(value, int):
            types.add("integer")
        elif isinstance(value, float):
            types.add("number")
        elif isinstance(value, str):
            types.add("string")
        elif isinstance(value, list):
            types.add("array")
        elif isinstance(value, dict):
            types.add("object")
    if len(types) != 1:
        return {"type": sorted(types)}
    kind = next(iter(types))
    schema: dict[str, Any] = {"type": kind}
    if kind == "object":
        objects = [value for value in non_null if isinstance(value, dict)]
        keys = sorted({key for obj in objects for key in obj})
        schema["properties"] = {
            key: value_schema([obj[key] for obj in objects if key in obj]) for key in keys
        }
        required = [key for key in keys if all(key in obj for obj in objects)]
        if required:
            schema["required"] = required
        schema["additionalProperties"] = True
    elif kind == "array":
        items = [item for value in non_null if isinstance(value, list) for item in value]
        schema["items"] = value_schema(items) if items else {}
    return schema


def build_tools(observed_calls: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    tools = []
    for name in sorted(observed_calls, key=str.casefold):
        calls = observed_calls[name]
        parameters = value_schema(calls)
        if parameters.get("type") != "object":
            parameters = {"type": "object", "additionalProperties": True}
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": TOOL_DESCRIPTIONS.get(
                        name,
                        f"源轨迹中观察到的 {name} 工具；参数结构由高 O2 轨迹归纳。",
                    ),
                    "parameters": parameters,
                },
            }
        )
    return tools


def message_chars(message: dict[str, Any]) -> int:
    return len(canonical_json(message))


def root_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    roots: list[dict[str, Any]] = []
    index = 0
    if messages and messages[0].get("role") == "system":
        roots.append(deepcopy(messages[0]))
        index = 1
    if index < len(messages) and messages[index].get("role") == "user":
        user = deepcopy(messages[index])
        user["content"], _ = truncate_text(user.get("content", ""), ROOT_USER_CHAR_LIMIT, "ROOT_USER")
        roots.append(user)
        index += 1
    return roots, index


def group_history(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    blocks: list[list[dict[str, Any]]] = []
    for message in messages:
        if message.get("role") == "assistant":
            blocks.append([message])
        elif message.get("role") == "tool" and blocks and blocks[-1][0].get("role") == "assistant":
            blocks[-1].append(message)
        else:
            blocks.append([message])
    return blocks


def classify_target(target: dict[str, Any], is_last_assistant: bool, prompt: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    tool_calls = target.get("tool_calls", [])
    if tool_calls:
        tags.append("tool_call")
        blob = canonical_json(tool_calls).casefold()
        # Keep task ids such as "TESTPK0008" from being misclassified as
        # verification. Underscores and punctuation remain valid separators for
        # command/file names such as validate_dataset.py.
        if re.search(
            r"(?<![a-z0-9])(?:verify|validate|validation|check|pytest|unittest|tests?)(?![a-z0-9])|验收|校验|核对",
            blob,
        ):
            tags.append("verification")
    if target.get("content", "").strip():
        tags.append("assistant_text")
    if is_last_assistant and not tool_calls:
        tags.append("final_answer")
    if prompt and prompt[-1].get("role") == "tool" and "status=error" in prompt[-1].get("content", ""):
        tags.append("recovery_after_tool_error")
    return tags or ["other"]


def make_samples(
    trajectory_id: str,
    split: str,
    family: str,
    o2: float,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    roots, start = root_messages(messages)
    assistant_indices = [i for i, message in enumerate(messages) if i >= start and message.get("role") == "assistant"]
    last_assistant = assistant_indices[-1] if assistant_indices else -1
    samples: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for ordinal, target_index in enumerate(assistant_indices, start=1):
        target = deepcopy(messages[target_index])
        completion_chars = message_chars(target)
        sample_id = f"{trajectory_id}::assistant-{ordinal:04d}"
        if completion_chars > COMPLETION_CHAR_LIMIT:
            rejected.append(
                {
                    "sample_id": sample_id,
                    "trajectory_id": trajectory_id,
                    "reason": "completion_too_large",
                    "completion_chars": completion_chars,
                }
            )
            continue

        history = messages[start:target_index]
        blocks = group_history(history)
        base_chars = sum(message_chars(message) for message in roots)
        selected_blocks: list[list[dict[str, Any]]] = []
        used_chars = base_chars
        for block in reversed(blocks):
            block_chars = sum(message_chars(message) for message in block)
            if used_chars + block_chars > CONTEXT_CHAR_BUDGET:
                continue
            selected_blocks.append(block)
            used_chars += block_chars
        selected_blocks.reverse()
        prompt = deepcopy(roots)
        for block in selected_blocks:
            prompt.extend(deepcopy(block))

        tags = classify_target(target, target_index == last_assistant, prompt)
        sample = {
            "id": sample_id,
            "prompt": prompt,
            "completion": [target],
            "tools": tools,
            "metadata": {
                "trajectory_id": trajectory_id,
                "task_family": family,
                "split": split,
                "o2": o2,
                "target_model": TARGET_MODEL,
                "reasoning_policy": "source_thinking_dropped",
                "loss_policy": "completion_only",
                "target_tags": tags,
                "source_assistant_ordinal": ordinal,
                "prompt_chars": sum(message_chars(message) for message in prompt),
                "completion_chars": completion_chars,
                "history_blocks_available": len(blocks),
                "history_blocks_kept": len(selected_blocks),
                "history_truncated": len(selected_blocks) < len(blocks),
                "requires_tokenizer_length_check": True,
            },
        }
        samples.append(sample)
    return samples, rejected


def find_case_run(source_root: Path, case: str) -> tuple[Path, Path]:
    case_dir = source_root / case
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Missing case directory: {case_dir}")
    trajectories = sorted(case_dir.glob("*/trajectory/conversation_trajectory.json"))
    scores = sorted(case_dir.glob("*/scores/*/score.json"))
    if len(trajectories) != 1 or not scores:
        raise RuntimeError(
            f"Expected one trajectory and at least one score for {case}; "
            f"found trajectories={len(trajectories)}, scores={len(scores)}"
        )
    return trajectories[0], scores[-1]


def load_score_fields(path: Path) -> tuple[float, str]:
    with path.open("r", encoding="utf-8") as handle:
        score = json.load(handle)
    release = str(score.get("ruleset", {}).get("release", ""))
    aggregates = score.get("result", {}).get("aggregates", [])
    for aggregate in aggregates:
        if aggregate.get("id") == "effectiveness.o2":
            return float(aggregate["score"]), release
    raise RuntimeError(f"effectiveness.o2 not found in {path}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * quantile)]


def sample_statistics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_chars = [int(sample["metadata"]["prompt_chars"]) for sample in samples]
    completion_chars = [int(sample["metadata"]["completion_chars"]) for sample in samples]
    by_trajectory = Counter(sample["metadata"]["trajectory_id"] for sample in samples)
    tags = Counter(
        tag
        for sample in samples
        for tag in sample["metadata"].get("target_tags", [])
    )
    target_tools = Counter(
        call["function"]["name"]
        for sample in samples
        for message in sample["completion"]
        for call in message.get("tool_calls", [])
    )

    def length_summary(values: list[int]) -> dict[str, int]:
        return {
            "min": min(values, default=0),
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "max": max(values, default=0),
        }

    return {
        "sample_count": len(samples),
        "by_trajectory": dict(sorted(by_trajectory.items())),
        "target_tag_counts": dict(sorted(tags.items())),
        "target_tool_call_counts": dict(sorted(target_tools.items())),
        "history_truncated_samples": sum(
            bool(sample["metadata"].get("history_truncated")) for sample in samples
        ),
        "prompt_chars": length_summary(prompt_chars),
        "completion_chars": length_summary(completion_chars),
    }


def main() -> None:
    args = parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    source_root = workspace / "simulation_0731-YunChou-0827_skill0813_0829"
    allowed_root = workspace / "taowen"
    if allowed_root != output and allowed_root not in output.parents:
        raise RuntimeError(f"Output must stay inside {allowed_root}; got {output}")
    output.mkdir(parents=True, exist_ok=True)

    normalized_by_case: dict[str, list[dict[str, Any]]] = {}
    counters_by_case: dict[str, dict[str, int]] = {}
    source_by_case: dict[str, dict[str, Any]] = {}
    all_observed_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case, config in SELECTED.items():
        trajectory_path, score_path = find_case_run(source_root, case)
        o2, ruleset_release = load_score_fields(score_path)
        raw = json.loads(trajectory_path.read_text(encoding="utf-8"))
        messages, counters, observed = normalize_trajectory(raw)
        normalized_by_case[case] = messages
        counters_by_case[case] = counters
        for name, calls in observed.items():
            all_observed_calls[name].extend(calls)
        source_by_case[case] = {
            "trajectory_id": case,
            "task_family": config["family"],
            "split": config["split"],
            "o2": o2,
            "ruleset_release": ruleset_release,
            "source_schema_version": raw.get("schema_version"),
            "source_model": raw.get("model"),
            "source_num_turns": raw.get("num_turns"),
            "source_message_count": len(raw.get("messages", [])),
            "normalized_message_count": len(messages),
            "source_trajectory": trajectory_path.relative_to(workspace).as_posix(),
            "source_score": score_path.relative_to(workspace).as_posix(),
            "source_trajectory_sha256": sha256_file(trajectory_path),
            "source_score_sha256": sha256_file(score_path),
            "normalization_counters": counters,
        }

    tools = build_tools(all_observed_calls)
    write_json(output / "tools.inferred.json", tools)

    full_rows: list[dict[str, Any]] = []
    train_full: list[dict[str, Any]] = []
    validation_full: list[dict[str, Any]] = []
    train_samples: list[dict[str, Any]] = []
    validation_samples: list[dict[str, Any]] = []
    rejected_samples: list[dict[str, Any]] = []

    for case, config in SELECTED.items():
        meta = source_by_case[case]
        full_row = {
            "id": case,
            "messages": normalized_by_case[case],
            "tools": tools,
            "metadata": {
                "task_family": config["family"],
                "split": config["split"],
                "o2": meta["o2"],
                "ruleset_release": meta["ruleset_release"],
                "target_model": TARGET_MODEL,
                "reasoning_policy": "source_thinking_dropped",
                "note": "Audit representation; use prompt/completion split files for completion-only SFT.",
            },
        }
        full_rows.append(full_row)
        (train_full if config["split"] == "train" else validation_full).append(full_row)
        samples, rejected = make_samples(
            case,
            config["split"],
            config["family"],
            meta["o2"],
            normalized_by_case[case],
            tools,
        )
        for sample in samples:
            sample["metadata"]["trajectory_sample_weight"] = 1.0 / max(len(samples), 1)
        if config["split"] == "train":
            train_samples.extend(samples)
        else:
            validation_samples.extend(samples)
        rejected_samples.extend(rejected)
        meta["decision_sample_count"] = len(samples)
        meta["rejected_sample_count"] = len(rejected)

    write_jsonl(output / "full_trajectories.jsonl", full_rows)
    write_jsonl(output / "train.full.jsonl", train_full)
    write_jsonl(output / "validation.full.jsonl", validation_full)
    write_jsonl(output / "train.jsonl", train_samples)
    write_jsonl(output / "validation.jsonl", validation_samples)
    write_jsonl(output / "rejected_samples.jsonl", rejected_samples)

    validation_tasks = []
    for row in validation_full:
        root, _ = root_messages(row["messages"])
        validation_tasks.append(
            {
                "id": row["id"],
                "messages": root,
                "tools": tools,
                "metadata": row["metadata"],
            }
        )
    write_jsonl(output / "validation_tasks.jsonl", validation_tasks)

    split_families: dict[str, list[str]] = defaultdict(list)
    for case, config in SELECTED.items():
        split_families[config["split"]].append(config["family"])
    for split in split_families:
        split_families[split] = sorted(set(split_families[split]))

    tag_counts = Counter()
    for sample in train_samples + validation_samples:
        tag_counts.update(sample["metadata"]["target_tags"])

    manifest = {
        "dataset_name": "ei-high-o2-qwen3-8b-sft",
        "dataset_date": DATASET_DATE,
        "target_model": TARGET_MODEL,
        "source_trajectory_count": len(SELECTED),
        "split_policy": "grouped_by_task_family",
        "split_families": dict(split_families),
        "reasoning_policy": "drop_source_thinking",
        "loss_policy": "completion_only",
        "context_char_budget": CONTEXT_CHAR_BUDGET,
        "root_user_char_limit": ROOT_USER_CHAR_LIMIT,
        "tool_result_char_limit": TOOL_RESULT_CHAR_LIMIT,
        "completion_char_limit": COMPLETION_CHAR_LIMIT,
        "tool_schema_policy": "inferred_from_observed_high_o2_calls; replace or verify against deployment runtime",
        "counts": {
            "train_full_trajectories": len(train_full),
            "validation_full_trajectories": len(validation_full),
            "train_decision_samples": len(train_samples),
            "validation_decision_samples": len(validation_samples),
            "validation_rollout_tasks": len(validation_tasks),
            "rejected_oversized_completions": len(rejected_samples),
            "observed_tools": len(tools),
        },
        "target_tag_counts": dict(sorted(tag_counts.items())),
        "sample_statistics": {
            "all": sample_statistics(train_samples + validation_samples),
            "train": sample_statistics(train_samples),
            "validation": sample_statistics(validation_samples),
        },
        "trajectories": [source_by_case[case] for case in SELECTED],
    }

    output_files = [
        "full_trajectories.jsonl",
        "train.full.jsonl",
        "validation.full.jsonl",
        "train.jsonl",
        "validation.jsonl",
        "validation_tasks.jsonl",
        "rejected_samples.jsonl",
        "tools.inferred.json",
    ]
    manifest["output_sha256"] = {name: sha256_file(output / name) for name in output_files}
    write_json(output / "manifest.json", manifest)
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit("Library module only; run scripts/convert_trajectories.py instead.")
