#!/usr/bin/env python3
"""Validate canonical and five grouped-CV Qwen SFT datasets."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1]
EXPECTED_FAMILIES = {"0006", "0007", "0008", "0009", "0010"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def message_chars(message: dict[str, Any]) -> int:
    return len(json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def validate_sample(
    row: dict[str, Any],
    tool_names: set[str],
    prompt_limit: int,
    completion_limit: int,
    expected_fold: str | None = None,
    expected_split: str | None = None,
) -> str:
    row_id = row.get("id")
    assert isinstance(row_id, str) and row_id, "sample missing id"
    prompt = row.get("prompt")
    completion = row.get("completion")
    assert isinstance(prompt, list) and len(prompt) >= 2, f"{row_id}: invalid prompt"
    assert prompt[0].get("role") == "system", f"{row_id}: prompt must begin with system"
    assert prompt[1].get("role") == "user", f"{row_id}: second message must be user"
    assert isinstance(completion, list) and len(completion) == 1, f"{row_id}: one completion required"
    assert completion[0].get("role") == "assistant", f"{row_id}: completion must be assistant"

    metadata = row.get("metadata", {})
    if expected_fold is not None:
        assert metadata.get("fold_id") == expected_fold, f"{row_id}: fold mismatch"
    if expected_split is not None:
        assert metadata.get("split") == expected_split, f"{row_id}: split mismatch"
    family = str(metadata.get("task_family"))
    assert family in EXPECTED_FAMILIES, f"{row_id}: invalid family {family}"
    assert float(metadata.get("o2", 0)) >= 80, f"{row_id}: low O2 in positive SFT"

    prompt_chars = sum(message_chars(message) for message in prompt)
    completion_chars = sum(message_chars(message) for message in completion)
    assert metadata.get("prompt_chars") == prompt_chars, f"{row_id}: prompt char metadata mismatch"
    assert metadata.get("completion_chars") == completion_chars, f"{row_id}: completion char metadata mismatch"
    assert prompt_chars <= prompt_limit, f"{row_id}: prompt exceeds char budget"
    assert completion_chars <= completion_limit, f"{row_id}: completion exceeds char budget"

    blob = json.dumps(row, ensure_ascii=False)
    assert '"thinking"' not in blob, f"{row_id}: source thinking leaked"
    assert '"reasoning_content"' not in blob, f"{row_id}: reasoning_content leaked"

    seen_call_ids: set[str] = set()
    for message in prompt + completion:
        if message.get("role") == "tool":
            call_id = message.get("tool_call_id")
            assert isinstance(call_id, str) and call_id, f"{row_id}: tool result lacks id"
            assert call_id in seen_call_ids, f"{row_id}: orphan tool result {call_id}"
        for call in message.get("tool_calls", []):
            call_id = call.get("id")
            function = call.get("function", {})
            assert isinstance(call_id, str) and call_id, f"{row_id}: call lacks id"
            assert call_id not in seen_call_ids, f"{row_id}: duplicate call id {call_id}"
            seen_call_ids.add(call_id)
            assert function.get("name") in tool_names, f"{row_id}: undefined tool {function.get('name')}"
            assert isinstance(function.get("arguments"), dict), f"{row_id}: arguments must be object"
    return family


def validate_unique(rows: list[dict[str, Any]], label: str) -> set[str]:
    ids = [row.get("id") for row in rows]
    assert all(isinstance(item, str) and item for item in ids), f"{label}: missing id"
    assert len(ids) == len(set(ids)), f"{label}: duplicate ids"
    return set(ids)


def tokenizer_check(rows: list[dict[str, Any]], model: str, max_length: int) -> dict[str, int]:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("transformers is not installed in /root/miniconda3") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        model,
        trust_remote_code=False,
        local_files_only=True,
    )
    longest = 0
    over_limit = 0
    for row in rows:
        token_ids = tokenizer.apply_chat_template(
            row["prompt"] + row["completion"],
            tools=row["tools"],
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        length = len(token_ids)
        longest = max(longest, length)
        over_limit += int(length > max_length)
    return {"longest_tokens": longest, "over_limit": over_limit, "max_length": max_length}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--model", help="Existing local Qwen model/tokenizer path; network download is disabled")
    parser.add_argument("--max-length", type=int, default=16384)
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    allowed = Path("/root/autodl-tmp/workspace-tw").resolve()
    assert data_dir.is_relative_to(allowed), f"data dir outside workspace-tw: {data_dir}"

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest.get("output_sha256", {}).items():
        path = (data_dir / relative).resolve()
        assert path.is_relative_to(data_dir), f"hash target outside data dir: {{relative}}"
        assert path.is_file(), f"missing hashed output: {{relative}}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"output hash mismatch: {{relative}}"
    registry = json.loads((data_dir / "fold_registry.json").read_text(encoding="utf-8"))
    tools = json.loads((data_dir / "tools.inferred.json").read_text(encoding="utf-8"))
    tool_names = {tool["function"]["name"] for tool in tools}
    assert len(tool_names) == len(tools), "duplicate tool definitions"

    canonical = read_jsonl(data_dir / "canonical" / "decision_samples.jsonl")
    canonical_ids = validate_unique(canonical, "canonical decision samples")
    full = read_jsonl(data_dir / "canonical" / "full_trajectories.jsonl")
    rollout = read_jsonl(data_dir / "canonical" / "rollout_tasks.jsonl")
    assert len(full) == 7, f"expected 7 full trajectories, got {len(full)}"
    assert len(rollout) == 7, f"expected 7 rollout tasks, got {len(rollout)}"
    validate_unique(full, "full trajectories")
    validate_unique(rollout, "rollout tasks")

    prompt_limit = int(manifest["context_char_budget"])
    completion_limit = int(manifest["completion_char_limit"])
    canonical_families: dict[str, set[str]] = {family: set() for family in EXPECTED_FAMILIES}
    for row in canonical:
        family = validate_sample(row, tool_names, prompt_limit, completion_limit)
        assert row["metadata"].get("split") == "canonical", f"{row['id']}: canonical split mismatch"
        canonical_families[family].add(row["id"])
    assert set().union(*canonical_families.values()) == canonical_ids

    for family in EXPECTED_FAMILIES:
        shard = read_jsonl(data_dir / "canonical" / f"family_{family}.jsonl")
        assert validate_unique(shard, f"family {family}") == canonical_families[family]

    folds = registry.get("folds", [])
    assert len(folds) == 5, f"expected 5 folds, got {len(folds)}"
    assert {row["holdout_family"] for row in folds} == EXPECTED_FAMILIES
    assert sum(bool(row.get("recommended_default_single_split")) for row in folds) == 1
    assert registry.get("recommended_default_single_split") == "fold_05_holdout_0010"
    holdout_counts: Counter[str] = Counter()
    result_folds: list[dict[str, Any]] = []

    full_family_by_id = {row["id"]: str(row["metadata"]["task_family"]) for row in full}
    for record in folds:
        fold_id = record["fold_id"]
        holdout = str(record["holdout_family"])
        holdout_counts[holdout] += 1
        train_families = set(map(str, record["train_families"]))
        assert train_families == EXPECTED_FAMILIES - {holdout}
        fold_dir = data_dir / record["path"]
        train = read_jsonl(fold_dir / "train.jsonl")
        validation = read_jsonl(fold_dir / "validation.jsonl")
        validation_tasks = read_jsonl(fold_dir / "validation_tasks.jsonl")
        train_ids = validate_unique(train, f"{fold_id} train")
        validation_ids = validate_unique(validation, f"{fold_id} validation")
        assert train_ids.isdisjoint(validation_ids), f"{fold_id}: id leakage"
        assert train_ids | validation_ids == canonical_ids, f"{fold_id}: incomplete coverage"

        observed_train = {
            validate_sample(row, tool_names, prompt_limit, completion_limit, fold_id, "train")
            for row in train
        }
        observed_validation = {
            validate_sample(row, tool_names, prompt_limit, completion_limit, fold_id, "validation")
            for row in validation
        }
        assert observed_train == train_families, f"{fold_id}: train family mismatch"
        assert observed_validation == {holdout}, f"{fold_id}: validation family mismatch"
        assert len(train) == record["train_sample_count"]
        assert len(validation) == record["validation_sample_count"]

        task_ids = validate_unique(validation_tasks, f"{fold_id} validation tasks")
        expected_task_ids = {item for item, family in full_family_by_id.items() if family == holdout}
        assert task_ids == expected_task_ids, f"{fold_id}: rollout task mismatch"
        for task in validation_tasks:
            assert [message.get("role") for message in task["messages"]] == ["system", "user"]
            assert task["metadata"].get("split") == "validation"
            assert task["metadata"].get("fold_id") == fold_id
        assert len(validation_tasks) == record["validation_task_count"]

        result_folds.append({
            "fold_id": fold_id,
            "train": len(train),
            "validation": len(validation),
            "validation_tasks": len(validation_tasks),
        })

    assert all(holdout_counts[family] == 1 for family in EXPECTED_FAMILIES)
    assert sum(len(canonical_families[family]) for family in EXPECTED_FAMILIES) == len(canonical)
    result: dict[str, Any] = {
        "status": "PASS",
        "canonical_full_trajectories": len(full),
        "canonical_decision_samples": len(canonical),
        "families": sorted(EXPECTED_FAMILIES),
        "observed_tools": len(tools),
        "folds": result_folds,
    }
    if args.model:
        result["tokenizer_check"] = tokenizer_check(canonical, args.model, args.max_length)
        if result["tokenizer_check"]["over_limit"]:
            result["status"] = "TOKEN_LENGTH_REVIEW_REQUIRED"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
