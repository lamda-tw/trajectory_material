#!/usr/bin/env python3
"""Validate converted AppWorld Codex-RFT Qwen completion-only SFT data."""

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
    "ground_truth": re.compile(r"\bground_truth\b", re.IGNORECASE),
    "private_data": re.compile(r"\bprivate_data\b", re.IGNORECASE),
    "test_data": re.compile(r"\btest_data\b", re.IGNORECASE),
    "solution_module": re.compile(r"\b(?:compiled_)?solution\.py\b", re.IGNORECASE),
    "evaluation_module": re.compile(r"\bevaluation\.py\b", re.IGNORECASE),
    "access_token_literal": re.compile(
        r"['\"]access_token['\"]\s*:\s*['\"](?!<REDACTED>)[^'\"]+['\"]",
        re.IGNORECASE,
    ),
    "password_literal": re.compile(
        r"['\"]password['\"]\s*:\s*['\"](?!<REDACTED>)[^'\"]+['\"]",
        re.IGNORECASE,
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "bearer": re.compile(r"\bBearer\s+(?!<REDACTED>)[A-Za-z0-9._~+/-]{12,}=*", re.IGNORECASE),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=40960)
    return parser.parse_args()


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
                raise AssertionError(f"{path}:{line_number}: invalid JSON") from exception
            if not isinstance(value, dict):
                raise AssertionError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows


def percentile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * q)] if ordered else 0


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    model = args.model.resolve()
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for relative, expected in manifest["output_sha256"].items():
        path = (data_dir / relative).resolve()
        assert path.is_relative_to(data_dir), f"hash path escapes data directory: {relative}"
        assert path.is_file(), f"missing output: {relative}"
        assert sha256_file(path) == expected, f"hash mismatch: {relative}"

    train = read_jsonl(data_dir / "train.jsonl")
    full = read_jsonl(data_dir / "full_trajectories.jsonl")
    task_files = sorted((data_dir / "tasks").glob("*.json"))
    expected_tasks = int(manifest["counts"]["tasks"])
    expected_samples = int(manifest["counts"]["decision_samples"])
    assert len(full) == expected_tasks == 90
    assert len(task_files) == expected_tasks
    assert len(train) == expected_samples
    assert sum(int(row["metadata"]["step_count"]) for row in full) == len(train)

    sample_ids = [row["id"] for row in train]
    assert len(set(sample_ids)) == len(sample_ids), "duplicate decision sample IDs"
    full_by_task = {row["id"]: row for row in full}
    assert len(full_by_task) == expected_tasks, "duplicate full trajectory task IDs"
    source_threads = [row["metadata"]["source_codex_thread_id"] for row in full]
    assert len(set(source_threads)) == len(source_threads), "source thread IDs are not unique"

    shard_ids: set[str] = set()
    for path in task_files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(rows, list) and rows, f"empty task shard: {path.name}"
        assert {row["metadata"]["task_id"] for row in rows} == {path.stem}
        for row in rows:
            assert row["id"] not in shard_ids, f"duplicate shard sample: {row['id']}"
            shard_ids.add(row["id"])
    assert shard_ids == set(sample_ids), "task shards do not exactly cover train.jsonl"

    difficulty = json.loads((data_dir / "difficulty_summary.json").read_text(encoding="utf-8"))
    assert difficulty["counts"] == {"1": 36, "2": 36, "3": 18}
    difficulty_task_ids = sum(difficulty["task_ids"].values(), [])
    assert len(difficulty_task_ids) == len(set(difficulty_task_ids)) == expected_tasks
    assert set(difficulty_task_ids) == set(full_by_task)

    from transformers import AutoTokenizer

    model_config = json.loads((model / "config.json").read_text(encoding="utf-8"))
    assert int(model_config["max_position_embeddings"]) >= args.max_length
    assert manifest["conversion"]["context_window"]["training_max_length"] == args.max_length
    tokenizer = AutoTokenizer.from_pretrained(
        model, trust_remote_code=False, local_files_only=True, use_fast=True
    )
    full_lengths: list[int] = []
    prompt_lengths: list[int] = []
    completion_lengths: list[int] = []
    limits = sorted({4096, 8192, 16384, 32768, args.max_length})
    over_limit = {str(limit): 0 for limit in limits}
    dynamic_findings: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    redaction_markers = 0

    for sample in train:
        sample_id = str(sample["id"])
        prompt = sample.get("prompt")
        completion = sample.get("completion")
        assert isinstance(prompt, list) and prompt, f"{sample_id}: empty prompt"
        assert isinstance(completion, list) and len(completion) == 1
        assert completion[0].get("role") == "assistant"
        assert sample.get("tools") is None
        assert sample["metadata"]["observation_policy"] == (
            "credential_redacted_then_24000_char_head_tail_truncated"
        )
        assert sample["metadata"]["official_evaluation_success"] is True
        assert sample["metadata"]["clean_replay_success"] is None

        content = str(completion[0].get("content", ""))
        code_matches = CODE_RE.findall(content)
        assert len(code_matches) == 1 and code_matches[0].strip(), (
            f"{sample_id}: completion must contain exactly one Python block"
        )

        task_id = str(sample["metadata"]["task_id"])
        full_row = full_by_task[task_id]
        target_index = int(sample["metadata"]["target_message_index"])
        assert prompt == full_row["messages"][:target_index], f"{sample_id}: non-prefix prompt"
        assert completion[0] == full_row["messages"][target_index], (
            f"{sample_id}: completion mismatch"
        )
        instruction_count = int(full_row["metadata"]["num_instruction_messages"])
        dynamic_messages = prompt[instruction_count:] + completion
        dynamic_blob = json.dumps(dynamic_messages, ensure_ascii=False)
        redaction_markers += dynamic_blob.count("<REDACTED")
        for name, pattern in FORBIDDEN_DYNAMIC_PATTERNS.items():
            if pattern.search(dynamic_blob):
                dynamic_findings[name] += 1
        for message in prompt + completion:
            role_counts[str(message.get("role"))] += 1

        prompt_ids = tokenizer.apply_chat_template(
            prompt,
            tools=None,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        combined_ids = tokenizer.apply_chat_template(
            prompt + completion,
            tools=None,
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        assert combined_ids[: len(prompt_ids)] == prompt_ids, (
            f"{sample_id}: Qwen chat-template prefix invariant failed"
        )
        completion_length = len(combined_ids) - len(prompt_ids)
        assert completion_length > 0, f"{sample_id}: zero-token completion"
        full_lengths.append(len(combined_ids))
        prompt_lengths.append(len(prompt_ids))
        completion_lengths.append(completion_length)
        for limit in limits:
            over_limit[str(limit)] += int(len(combined_ids) > limit)

    status = "PASS" if not dynamic_findings and over_limit[str(args.max_length)] == 0 else "FAIL"
    result = {
        "status": status,
        "schema_version": manifest["schema_version"],
        "task_count": len(full),
        "decision_sample_count": len(train),
        "per_task_json_count": len(task_files),
        "source_verification": {
            "official_evaluator_success_tasks": len(full),
            "unique_codex_threads": len(set(source_threads)),
            "raw_observations_included": False,
            "ground_truth_in_model_messages": False,
            "sensitive_value_occurrences_checked": manifest["counts"][
                "sensitive_value_occurrences_checked"
            ],
            "sensitive_value_leaks": manifest["counts"]["sensitive_value_leaks"],
        },
        "difficulty": difficulty["counts"],
        "structure": {
            "unique_sample_ids": len(set(sample_ids)),
            "task_shards_exactly_cover_train": True,
            "completion_python_block_count": 1,
            "chat_template_prefix_invariant": True,
            "loss_policy": "assistant_completion_only",
            "role_counts": dict(role_counts),
        },
        "dynamic_leak_scan_findings": dict(dynamic_findings),
        "policy_redaction_markers_seen_across_expanded_prefixes": redaction_markers,
        "tokenizer": {
            "model_path": str(model),
            "enable_thinking": False,
            "validated_max_length": args.max_length,
            "model_native_max_position_embeddings": model_config["max_position_embeddings"],
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
    validation_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest["validation_sha256"] = sha256_file(validation_path)
    manifest["validation_status"] = status
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
