#!/usr/bin/env python3
"""Convert verified AppWorld ReAct trajectories into Qwen3 completion-only SFT data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Template


SCHEMA_VERSION = "appworld-react-sft-v1"
TARGET_MODEL = "Qwen/Qwen3-8B"
SOURCE_KIND = "verified_codex_react_trajectory"
ASSISTANT_CODE_RE = re.compile(r"```python\n(.*?)\n```", re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-list", type=Path, required=True)
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--prompt-template", type=Path, required=True)
    parser.add_argument("--expected-tasks", type=int, default=67)
    parser.add_argument("--monitor-tasks", type=int, default=7)
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
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            rows.append(row)
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
        last_end = match.span()[0]
        if not messages and last_end != 0:
            raise ValueError("official prompt has content before its first role marker")
        if messages:
            messages[-1]["content"] = prompt[last_start:last_end]
        messages.append({"role": match.group(1).lower(), "content": None})
        last_start = match.span()[1]
    if not messages:
        raise ValueError("official prompt contains no role markers")
    messages[-1]["content"] = prompt[last_start:]
    return [{"role": str(m["role"]), "content": str(m["content"])} for m in messages]


def app_descriptions_json() -> str:
    from appworld.apps import get_all_apps, get_app_to_description

    app_to_description = get_app_to_description()
    return json.dumps(
        [
            {"name": app_name, "description": app_to_description[app_name]}
            for app_name in get_all_apps(skip_admin=True)
        ],
        indent=1,
    )


def render_instruction_messages(
    prompt_template: str,
    instruction: str,
    supervisor: dict[str, Any],
    descriptions: str,
) -> list[dict[str, str]]:
    rendered = Template(prompt_template.lstrip()).render(
        instruction=instruction,
        main_user=supervisor,
        app_descriptions=descriptions,
    )
    return text_to_messages(rendered + "\n\n")


def assistant_message(reasoning: str, action_code: str) -> dict[str, str]:
    reasoning = reasoning.strip()
    action_code = action_code.strip()
    if not reasoning:
        raise ValueError("empty reasoning")
    if not action_code:
        raise ValueError("empty action_code")
    if "```" in action_code:
        raise ValueError("action_code unexpectedly contains a markdown fence")
    return {
        "role": "assistant",
        "content": f"{reasoning}\n\n```python\n{action_code}\n```\n\n",
    }


def observation_message(observation: str) -> dict[str, str]:
    observation = str(observation)
    newline = "" if observation.endswith("\n") else "\n"
    return {"role": "user", "content": f"Output:\n```\n{observation}{newline}```\n\n"}


def assert_verified_source(row: dict[str, Any]) -> None:
    task_id = row.get("task_id", "<missing>")
    assert row.get("final_status") == "success", f"{task_id}: final_status is not success"
    assert row.get("evaluation", {}).get("success") is True, f"{task_id}: evaluator failed"
    assert row.get("replay_verified") is True, f"{task_id}: replay not verified"
    if "replay_evaluation" in row:
        assert row["replay_evaluation"].get("success") is True, f"{task_id}: replay evaluator failed"
    assert row.get("credential_leaks") == 0, f"{task_id}: credential leak finding"
    assert row.get("privileged_context_leaks") == 0, f"{task_id}: privileged leak finding"
    steps = row.get("steps")
    assert isinstance(steps, list) and steps, f"{task_id}: no steps"
    for index, step in enumerate(steps, 1):
        assert step.get("step_index") == index, f"{task_id}: non-contiguous step_index"
        assert isinstance(step.get("reasoning"), str), f"{task_id}: invalid reasoning at {index}"
        assert isinstance(step.get("action_code"), str), f"{task_id}: invalid action at {index}"
        assert isinstance(step.get("observation"), str), f"{task_id}: invalid observation at {index}"


def task_specs(tasks_root: Path, task_id: str) -> tuple[dict[str, Any], Path]:
    path = tasks_root / task_id / "specs.json"
    specs = json.loads(path.read_text(encoding="utf-8"))
    return specs, path


def source_sha(row: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(row).encode("utf-8"))


def output_hashes(output: Path, relative_paths: list[str]) -> dict[str, str]:
    return {relative: sha256_file(output / relative) for relative in sorted(relative_paths)}


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    train_list = args.train_list.resolve()
    tasks_root = args.tasks_root.resolve()
    prompt_path = args.prompt_template.resolve()

    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    (output / "tasks").mkdir()
    (output / "splits" / "task_holdout_60_7").mkdir(parents=True)
    (output / "scripts").mkdir()

    rows = read_jsonl(source)
    if len(rows) != args.expected_tasks:
        raise ValueError(f"expected {args.expected_tasks} source tasks, found {len(rows)}")
    task_ids = [str(row.get("task_id", "")) for row in rows]
    if len(task_ids) != len(set(task_ids)) or any(not task_id for task_id in task_ids):
        raise ValueError("source task IDs are missing or duplicated")
    train_ids = {
        line.split(":", 1)[0].strip()
        for line in train_list.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    missing_from_train = sorted(set(task_ids) - train_ids)
    if missing_from_train:
        raise ValueError(f"source contains non-train tasks: {missing_from_train}")

    prompt_template = prompt_path.read_text(encoding="utf-8")
    descriptions = app_descriptions_json()
    all_samples: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    task_files: list[str] = []
    specs_hashes: dict[str, str] = {}
    source_row_hashes: dict[str, str] = {}

    for row in rows:
        assert_verified_source(row)
        task_id = str(row["task_id"])
        specs, specs_path = task_specs(tasks_root, task_id)
        if specs.get("instruction") != row.get("instruction"):
            raise ValueError(f"{task_id}: instruction differs from specs.json")
        spec_supervisor = specs.get("supervisor", specs.get("main_user"))
        if spec_supervisor != row.get("supervisor"):
            raise ValueError(f"{task_id}: supervisor differs from specs.json")
        if specs.get("datetime") != row.get("datetime"):
            raise ValueError(f"{task_id}: datetime differs from specs.json")

        base_messages = render_instruction_messages(
            prompt_template,
            str(row["instruction"]),
            dict(row["supervisor"]),
            descriptions,
        )
        num_instruction_messages = len(base_messages)
        history = deepcopy(base_messages)
        samples: list[dict[str, Any]] = []
        row_sha = source_sha(row)
        source_row_hashes[task_id] = row_sha
        specs_hashes[task_id] = sha256_file(specs_path)

        for step in row["steps"]:
            step_index = int(step["step_index"])
            target = assistant_message(step["reasoning"], step["action_code"])
            sample = {
                "id": f"{task_id}::assistant-{step_index:04d}",
                "prompt": deepcopy(history),
                "completion": [deepcopy(target)],
                "tools": None,
                "metadata": {
                    "schema_version": SCHEMA_VERSION,
                    "task_id": task_id,
                    "task_family": str(row.get("task_family", "")),
                    "split": "train",
                    "step_index": step_index,
                    "source": SOURCE_KIND,
                    "source_trajectory_sha256": row_sha,
                    "target_model": TARGET_MODEL,
                    "chat_protocol": "appworld_simplified_react_code_agent",
                    "loss_policy": "assistant_completion_only",
                    "reasoning_policy": "codex_concise_visible_rationale_preserved",
                    "prompt_message_count": len(history),
                    "target_message_index": len(history),
                    "official_evaluation_success": True,
                    "clean_replay_success": True,
                },
            }
            samples.append(sample)
            all_samples.append(sample)
            history.append(target)
            history.append(observation_message(step["observation"]))

        full_row = {
            "id": task_id,
            "messages": history,
            "tools": None,
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "task_id": task_id,
                "task_family": str(row.get("task_family", "")),
                "split": "train",
                "source": SOURCE_KIND,
                "source_trajectory_sha256": row_sha,
                "specs_sha256": specs_hashes[task_id],
                "target_model": TARGET_MODEL,
                "chat_protocol": "appworld_simplified_react_code_agent",
                "num_instruction_messages": num_instruction_messages,
                "step_count": len(row["steps"]),
                "official_evaluation_success": True,
                "clean_replay_success": True,
                "credential_leaks": 0,
                "privileged_context_leaks": 0,
            },
        }
        full_rows.append(full_row)
        relative_task_file = f"tasks/{task_id}.json"
        write_json(output / relative_task_file, samples)
        task_files.append(relative_task_file)

    all_samples.sort(key=lambda sample: (sample["metadata"]["task_id"], sample["metadata"]["step_index"]))
    full_rows.sort(key=lambda row: row["id"])
    task_ids_sorted = sorted(task_ids)
    write_jsonl(output / "train.jsonl", all_samples)
    write_jsonl(output / "full_trajectories.jsonl", full_rows)
    (output / "task_ids.txt").write_text("\n".join(task_ids_sorted) + "\n", encoding="utf-8")

    holdout_order = sorted(task_ids_sorted, key=lambda item: sha256_bytes(f"monitor:{item}".encode()))
    monitor_ids = set(holdout_order[: args.monitor_tasks])
    monitor_train = [sample for sample in all_samples if sample["metadata"]["task_id"] not in monitor_ids]
    monitor_validation = [sample for sample in all_samples if sample["metadata"]["task_id"] in monitor_ids]
    split_dir = output / "splits" / "task_holdout_60_7"
    write_jsonl(split_dir / "train.jsonl", monitor_train)
    write_jsonl(split_dir / "validation.jsonl", monitor_validation)
    (split_dir / "validation_task_ids.txt").write_text(
        "\n".join(sorted(monitor_ids)) + "\n", encoding="utf-8"
    )

    readme = f"""# AppWorld Qwen3-8B ReAct SFT data (67 verified train tasks)

This dataset converts {len(rows)} official-evaluator-successful and clean-replay-successful AppWorld
trajectories into the completion-only chat format consumed by
`scripts/minimal_sft_train.py` and by standard Hugging Face/TRL PEFT trainers.

## Files

- `train.jsonl`: all {len(all_samples)} assistant decisions from all {len(rows)} tasks. Each row has
  `id`, `prompt`, one-message `completion`, `tools: null`, and metadata.
- `tasks/<task_id>.json`: 67 per-task JSON arrays containing the same direct SFT records.
- `full_trajectories.jsonl`: one complete AppWorld chat trajectory per task, including real
  observations after every action.
- `splits/task_holdout_60_7/`: deterministic task-disjoint 60-task train / 7-task validation
  monitor split. This is useful for pipeline checks; official Dev remains the final evaluation.
- `manifest.json`: input provenance, hashes, counts, and conversion policy.
- `validation.json`: structural, tokenizer, prefix, and leak-surface validation results.

## Training contract

Render each row with the Qwen3 chat template using `enable_thinking=False`. Mask every prompt token
with label `-100` and apply loss only to the single assistant completion. No OpenAI function-tool
schema is used: AppWorld expects visible rationale followed by exactly one fenced Python code block.

For a task-disjoint monitored run with the existing trainer:

```bash
/root/autodl-tmp/workspace-tw/.conda-training/bin/python scripts/minimal_sft_train.py \\
  --train-json {output}/splits/task_holdout_60_7/train.jsonl \\
  --validation-json {output}/splits/task_holdout_60_7/validation.jsonl \\
  --model /root/autodl-tmp/models/Qwen3-8B \\
  --output-dir experiments/<timestamp>_appworld_qwen3_8b_react_lora
```

`train.jsonl` intentionally contains all 67 tasks for a final all-data fit before the held-out
AppWorld Dev evaluation. The conversion does not start Qwen, vLLM, SFT, or LoRA training.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")

    copied_converter = output / "scripts" / Path(__file__).name
    copied_converter.write_bytes(Path(__file__).read_bytes())

    hashed_paths = [
        "README.md",
        "train.jsonl",
        "full_trajectories.jsonl",
        "task_ids.txt",
        "scripts/convert_appworld_react_sft.py",
        "splits/task_holdout_60_7/train.jsonl",
        "splits/task_holdout_60_7/validation.jsonl",
        "splits/task_holdout_60_7/validation_task_ids.txt",
        *task_files,
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "source_task_count": len(rows),
        "source_decision_count": len(all_samples),
        "train_list_path": str(train_list),
        "train_list_sha256": sha256_file(train_list),
        "official_prompt_template_path": str(prompt_path),
        "official_prompt_template_sha256": sha256_file(prompt_path),
        "source_row_sha256": source_row_hashes,
        "specs_sha256": specs_hashes,
        "conversion": {
            "sample_unit": "one next-assistant-decision per row",
            "loss_policy": "assistant completion only",
            "history_policy": "lossless real observations; no summarization or truncation",
            "reasoning_policy": "preserve concise Codex rationale as visible assistant text",
            "action_policy": "preserve exact executed Python in one fenced code block",
            "student_excluded": [
                "ground_truth api_calls",
                "private_data",
                "test_data",
                "evaluator assertions",
                "solution source",
            ],
            "enable_thinking": False,
        },
        "counts": {
            "tasks": len(rows),
            "decision_samples": len(all_samples),
            "task_families": len({str(row.get("task_family", "")) for row in rows}),
            "per_task_json_files": len(task_files),
            "monitor_train_tasks": len(set(task_ids_sorted) - monitor_ids),
            "monitor_validation_tasks": len(monitor_ids),
            "monitor_train_samples": len(monitor_train),
            "monitor_validation_samples": len(monitor_validation),
        },
        "output_sha256": output_hashes(output, hashed_paths),
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
