#!/usr/bin/env python3
"""Validate AppWorld Qwen3 ReAct completion-only SFT data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


CODE_RE = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
FORBIDDEN_DYNAMIC_PATTERNS = {
    "access_token_literal": re.compile(r"['\"]access_token['\"]\s*:\s*['\"](?!fake_access_token)[^'\"]+['\"]"),
    "password_literal": re.compile(r"['\"]password['\"]\s*:\s*['\"](?!dummy_)[^'\"]+['\"]"),
    "private_data": re.compile(r"\bprivate_data\b"),
    "test_data": re.compile(r"\btest_data\b"),
    "evaluator_module": re.compile(r"\bevaluation\.py\b|\bevaluator\b"),
    "solution_module": re.compile(r"\b(?:compiled_)?solution\.py\b"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    output.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise AssertionError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return output


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * q)]


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for relative, expected in manifest["output_sha256"].items():
        path = (data_dir / relative).resolve()
        assert path.is_relative_to(data_dir), f"hash path escapes dataset: {relative}"
        assert path.is_file(), f"missing output: {relative}"
        assert sha256_file(path) == expected, f"hash mismatch: {relative}"

    train = read_jsonl(data_dir / "train.jsonl")
    full = read_jsonl(data_dir / "full_trajectories.jsonl")
    task_files = sorted((data_dir / "tasks").glob("*.json"))
    assert len(full) == manifest["counts"]["tasks"] == 67
    assert len(task_files) == manifest["counts"]["per_task_json_files"] == 67
    assert len(train) == manifest["counts"]["decision_samples"]
    ids = [row["id"] for row in train]
    assert len(ids) == len(set(ids)), "duplicate decision sample IDs"
    full_by_task = {row["id"]: row for row in full}
    assert len(full_by_task) == 67, "duplicate full trajectory IDs"

    task_file_sample_ids: set[str] = set()
    for path in task_files:
        samples = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(samples, list) and samples, f"empty task shard: {path.name}"
        assert {sample["metadata"]["task_id"] for sample in samples} == {path.stem}
        for sample in samples:
            assert sample["id"] not in task_file_sample_ids, f"duplicate shard sample: {sample['id']}"
            task_file_sample_ids.add(sample["id"])
    assert task_file_sample_ids == set(ids), "task shards do not exactly cover train.jsonl"

    dynamic_findings: Counter[str] = Counter()
    full_lengths: list[int] = []
    prompt_lengths: list[int] = []
    completion_lengths: list[int] = []
    limits = [4096, 8192, 16384, 32768]
    over_limit = {str(limit): 0 for limit in limits}

    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("transformers is required for tokenizer validation") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model.resolve()), trust_remote_code=False, local_files_only=True
    )

    for sample in train:
        sample_id = sample["id"]
        prompt = sample.get("prompt")
        completion = sample.get("completion")
        assert isinstance(prompt, list) and prompt, f"{sample_id}: empty prompt"
        assert isinstance(completion, list) and len(completion) == 1
        assert completion[0].get("role") == "assistant"
        assert sample.get("tools") is None
        content = completion[0].get("content", "")
        matches = CODE_RE.findall(content)
        assert len(matches) == 1 and matches[0].strip(), f"{sample_id}: expected one Python block"
        metadata = sample["metadata"]
        task_id = metadata["task_id"]
        full_row = full_by_task[task_id]
        target_index = metadata["target_message_index"]
        assert prompt == full_row["messages"][:target_index], f"{sample_id}: prompt is not full prefix"
        assert completion[0] == full_row["messages"][target_index], f"{sample_id}: target mismatch"
        assert metadata["official_evaluation_success"] is True
        assert metadata["clean_replay_success"] is True

        num_instruction_messages = full_row["metadata"]["num_instruction_messages"]
        dynamic_messages = prompt[num_instruction_messages:] + completion
        dynamic_blob = json.dumps(dynamic_messages, ensure_ascii=False)
        for name, pattern in FORBIDDEN_DYNAMIC_PATTERNS.items():
            if pattern.search(dynamic_blob):
                dynamic_findings[name] += 1

        prompt_ids = tokenizer.apply_chat_template(
            prompt,
            tools=None,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        full_ids = tokenizer.apply_chat_template(
            prompt + completion,
            tools=None,
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        assert full_ids[: len(prompt_ids)] == prompt_ids, f"{sample_id}: chat-template prefix mismatch"
        assert len(full_ids) > len(prompt_ids), f"{sample_id}: zero-token completion"
        prompt_lengths.append(len(prompt_ids))
        full_lengths.append(len(full_ids))
        completion_lengths.append(len(full_ids) - len(prompt_ids))
        for limit in limits:
            over_limit[str(limit)] += int(len(full_ids) > limit)

    split_dir = data_dir / "splits" / "task_holdout_60_7"
    split_train = read_jsonl(split_dir / "train.jsonl")
    split_validation = read_jsonl(split_dir / "validation.jsonl")
    split_train_tasks = {row["metadata"]["task_id"] for row in split_train}
    split_validation_tasks = {row["metadata"]["task_id"] for row in split_validation}
    assert split_train_tasks.isdisjoint(split_validation_tasks), "task leakage in monitor split"
    assert split_train_tasks | split_validation_tasks == set(full_by_task), "incomplete monitor split"
    assert len(split_train_tasks) == 60 and len(split_validation_tasks) == 7
    assert {row["id"] for row in split_train + split_validation} == set(ids)

    result = {
        "status": "PASS" if not dynamic_findings else "FAIL",
        "schema_version": manifest["schema_version"],
        "task_count": len(full),
        "decision_sample_count": len(train),
        "per_task_json_count": len(task_files),
        "source_verification": {
            "official_evaluator_success_tasks": len(full),
            "clean_replay_success_tasks": len(full),
            "credential_leak_tasks": 0,
            "privileged_context_leak_tasks": 0,
        },
        "structure": {
            "unique_sample_ids": len(set(ids)),
            "task_shards_exactly_cover_train": True,
            "completion_python_block_count": 1,
            "chat_template_prefix_invariant": True,
            "monitor_split_task_disjoint": True,
            "monitor_train_tasks": len(split_train_tasks),
            "monitor_validation_tasks": len(split_validation_tasks),
        },
        "dynamic_leak_scan_findings": dict(dynamic_findings),
        "tokenizer": {
            "model_path": str(args.model.resolve()),
            "enable_thinking": False,
            "min_full_tokens": min(full_lengths),
            "p50_full_tokens": percentile(full_lengths, 0.50),
            "p95_full_tokens": percentile(full_lengths, 0.95),
            "max_full_tokens": max(full_lengths),
            "max_prompt_tokens": max(prompt_lengths),
            "max_completion_tokens": max(completion_lengths),
            "samples_over_limit": over_limit,
        },
    }
    validation_path = data_dir / "validation.json"
    validation_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["validation_sha256"] = sha256_file(validation_path)
    manifest["validation_status"] = result["status"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
