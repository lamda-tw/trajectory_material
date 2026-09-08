#!/usr/bin/env python3
"""Build five grouped-CV Qwen3-8B SFT folds from seven high-O2 trajectories."""
from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

WORKSPACE = Path("/root/autodl-tmp/workspace-tw").resolve()
OUTPUT = (WORKSPACE / "data" / "2026-09-08").resolve()
RAW_ROOT = Path("/root/autodl-tmp/data/raw_data").resolve()
SOURCE_ROOT = RAW_ROOT / "simulation_0731-YunChou-0827_skill0813_0829"
MODEL = "Qwen/Qwen3-8B"
FAMILIES = ("0006", "0007", "0008", "0009", "0010")
CASES = (
    ("EI-56TESTPK0006-easy-v1.2", "0006"),
    ("EI-56TESTPK0007-medium-v1.2", "0007"),
    ("EI-56TESTPK0008-easy-v1.2", "0008"),
    ("EI-56TESTPK0008-medium-v1.2", "0008"),
    ("EI-56TESTPK0009-medium-v1.2", "0009"),
    ("EI-56TESTPK0010-easy-v1.2", "0010"),
    ("EI-56TESTPK0010-medium-v1.2", "0010"),
)
DEFAULT_FOLD = "fold_05_holdout_0010"


def load_core():
    path = OUTPUT / "scripts" / "conversion_core.py"
    spec = importlib.util.spec_from_file_location("conversion_core", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_core()


def check_boundaries() -> None:
    if not OUTPUT.is_relative_to(WORKSPACE):
        raise RuntimeError(f"Unsafe output: {OUTPUT}")
    if not SOURCE_ROOT.is_relative_to(RAW_ROOT) or not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"Invalid read-only source: {SOURCE_ROOT}")


def find_source(case: str) -> tuple[Path, Path]:
    case_dir = SOURCE_ROOT / case
    trajectories = sorted(case_dir.glob("*/trajectory/conversation_trajectory.json"))
    scores = sorted(case_dir.glob("*/scores/*/score.json"))
    if len(trajectories) != 1 or len(scores) != 1:
        raise RuntimeError(
            f"{case}: expected exactly one trajectory and one score; "
            f"got {len(trajectories)} and {len(scores)}"
        )
    return trajectories[0], scores[0]


def load_o2(path: Path) -> tuple[float, str, str]:
    score = json.loads(path.read_text(encoding="utf-8"))
    hits = [
        item for item in score.get("result", {}).get("aggregates", [])
        if str(item.get("id", "")).casefold() == "effectiveness.o2"
    ]
    if len(hits) != 1:
        raise RuntimeError(f"{path}: effectiveness.o2 must occur exactly once")
    ruleset = score.get("ruleset", {})
    return float(hits[0]["score"]), str(ruleset.get("release", "")), str(ruleset.get("bundle_sha256", ""))


def sum_counters(items: Iterable[dict[str, int]]) -> dict[str, int]:
    result: Counter[str] = Counter()
    for item in items:
        result.update(item)
    return dict(sorted(result.items()))


def as_fold_row(sample: dict[str, Any], fold_id: str, split: str) -> dict[str, Any]:
    return {
        "id": sample["id"],
        "prompt": sample["prompt"],
        "completion": sample["completion"],
        "tools": sample["tools"],
        "metadata": {**sample["metadata"], "fold_id": fold_id, "split": split},
    }


def fold_readme(record: dict[str, Any]) -> str:
    return f"""# {record['fold_id']}

- 训练任务族：{', '.join(record['train_families'])}
- 验证任务族：{record['holdout_family']}
- 训练轨迹/决策样本：{record['train_trajectory_count']} / {record['train_sample_count']}
- 验证轨迹/决策样本：{record['validation_trajectory_count']} / {record['validation_sample_count']}
- rollout 验证任务：{record['validation_task_count']}
- 推荐单次划分：{'是' if record['recommended_default_single_split'] else '否'}

使用本目录的 `train.jsonl` 与 `validation.jsonl`。通过目标 Qwen tokenizer 的
`apply_chat_template` 渲染 `prompt + completion` 和 `tools`，只对
`completion` token 计算 loss。该 fold 是一场从同一基座重新开始的独立训练实验，
不是一个 epoch。
"""


def main() -> None:
    check_boundaries()
    located = {case: find_source(case) for case, _ in CASES}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    canonical_dir = OUTPUT / "canonical"
    folds_dir = OUTPUT / "folds"
    canonical_dir.mkdir(exist_ok=True)
    folds_dir.mkdir(exist_ok=True)

    normalized: dict[str, list[dict[str, Any]]] = {}
    source_meta: dict[str, dict[str, Any]] = {}
    observed_all: dict[str, list[dict[str, Any]]] = {}
    counters_by_case: dict[str, dict[str, int]] = {}

    for case, family in CASES:
        trajectory_path, score_path = located[case]
        o2, release, bundle = load_o2(score_path)
        if o2 < 80:
            raise RuntimeError(f"{case}: selected positive trajectory has O2={o2}")
        raw = json.loads(trajectory_path.read_text(encoding="utf-8"))
        messages, counters, observed = core.normalize_trajectory(raw)
        normalized[case] = messages
        counters_by_case[case] = counters
        for name, calls in observed.items():
            observed_all.setdefault(name, []).extend(calls)
        source_meta[case] = {
            "trajectory_id": case,
            "task_family": family,
            "o2": o2,
            "ruleset_release": release,
            "ruleset_bundle_sha256": bundle,
            "source_schema_version": raw.get("schema_version"),
            "source_model": raw.get("model"),
            "source_num_turns": raw.get("num_turns"),
            "source_message_count": len(raw.get("messages", [])),
            "normalized_message_count": len(messages),
            "source_trajectory": str(trajectory_path),
            "source_score": str(score_path),
            "source_trajectory_sha256": core.sha256_file(trajectory_path),
            "source_score_sha256": core.sha256_file(score_path),
            "normalization_counters": counters,
        }

    tools = core.build_tools(observed_all)
    core.write_json(OUTPUT / "tools.inferred.json", tools)
    full_rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rollout: list[dict[str, Any]] = []

    for case, family in CASES:
        meta = source_meta[case]
        full_rows.append({
            "id": case,
            "messages": normalized[case],
            "tools": tools,
            "metadata": {
                "task_family": family,
                "o2": meta["o2"],
                "ruleset_release": meta["ruleset_release"],
                "target_model": MODEL,
                "reasoning_policy": "source_thinking_dropped",
                "representation": "canonical_audit",
            },
        })
        case_samples, case_rejected = core.make_samples(
            case, "canonical", family, meta["o2"], normalized[case], tools
        )
        weight = 1.0 / max(len(case_samples), 1)
        for sample in case_samples:
            sample["metadata"]["trajectory_sample_weight"] = weight
            sample["metadata"]["split"] = "canonical"
        samples.extend(case_samples)
        rejected.extend(case_rejected)
        meta["decision_sample_count"] = len(case_samples)
        meta["rejected_sample_count"] = len(case_rejected)
        roots, _ = core.root_messages(normalized[case])
        rollout.append({
            "id": case,
            "messages": roots,
            "tools": tools,
            "metadata": {
                "task_family": family,
                "o2": meta["o2"],
                "ruleset_release": meta["ruleset_release"],
                "target_model": MODEL,
                "split": "canonical",
            },
        })

    core.write_jsonl(canonical_dir / "full_trajectories.jsonl", full_rows)
    core.write_jsonl(canonical_dir / "decision_samples.jsonl", samples)
    core.write_jsonl(canonical_dir / "rollout_tasks.jsonl", rollout)
    core.write_jsonl(canonical_dir / "rejected_samples.jsonl", rejected)

    by_family = {
        family: [sample for sample in samples if sample["metadata"]["task_family"] == family]
        for family in FAMILIES
    }
    full_by_family = {
        family: [row for row in full_rows if row["metadata"]["task_family"] == family]
        for family in FAMILIES
    }
    rollout_by_family = {
        family: [row for row in rollout if row["metadata"]["task_family"] == family]
        for family in FAMILIES
    }
    for family in FAMILIES:
        core.write_jsonl(canonical_dir / f"family_{family}.jsonl", by_family[family])

    fold_records: list[dict[str, Any]] = []
    for index, holdout in enumerate(FAMILIES, 1):
        fold_id = f"fold_{index:02d}_holdout_{holdout}"
        fold_dir = folds_dir / fold_id
        fold_dir.mkdir(exist_ok=True)
        train_families = [family for family in FAMILIES if family != holdout]
        train_samples = [sample for family in train_families for sample in by_family[family]]
        validation_samples = by_family[holdout]
        train_count = core.write_jsonl(
            fold_dir / "train.jsonl",
            (as_fold_row(sample, fold_id, "train") for sample in train_samples),
        )
        validation_count = core.write_jsonl(
            fold_dir / "validation.jsonl",
            (as_fold_row(sample, fold_id, "validation") for sample in validation_samples),
        )
        validation_tasks = []
        for task in rollout_by_family[holdout]:
            item = deepcopy(task)
            item["metadata"] = {**item["metadata"], "fold_id": fold_id, "split": "validation"}
            validation_tasks.append(item)
        core.write_jsonl(fold_dir / "validation_tasks.jsonl", validation_tasks)

        record = {
            "fold_id": fold_id,
            "path": f"folds/{fold_id}",
            "holdout_family": holdout,
            "train_families": train_families,
            "train_trajectory_count": sum(len(full_by_family[f]) for f in train_families),
            "validation_trajectory_count": len(full_by_family[holdout]),
            "train_sample_count": train_count,
            "validation_sample_count": validation_count,
            "validation_task_count": len(validation_tasks),
            "recommended_default_single_split": fold_id == DEFAULT_FOLD,
        }
        record["data_sha256"] = {
            "train.jsonl": core.sha256_file(fold_dir / "train.jsonl"),
            "validation.jsonl": core.sha256_file(fold_dir / "validation.jsonl"),
            "validation_tasks.jsonl": core.sha256_file(fold_dir / "validation_tasks.jsonl"),
        }
        core.write_json(fold_dir / "split.json", record)
        (fold_dir / "README.md").write_text(fold_readme(record), encoding="utf-8")
        fold_records.append(record)

    registry = {
        "policy": "5-fold grouped cross-validation by task_family",
        "all_families": list(FAMILIES),
        "recommended_default_single_split": DEFAULT_FOLD,
        "note": "One fold is one independent run from the same base checkpoint, not one epoch.",
        "folds": fold_records,
    }
    core.write_json(OUTPUT / "fold_registry.json", registry)

    rules_path = SOURCE_ROOT / "rules.md"
    rules_doc: dict[str, Any] = {"path": str(rules_path), "exists": rules_path.is_file()}
    if rules_path.is_file():
        rules_text = rules_path.read_text(encoding="utf-8")
        rules_doc.update({
            "sha256": core.sha256_file(rules_path),
            "declared_releases": sorted(set(re.findall(
                r"ruleset release[ \`]*([0-9]+\.[0-9]+\.[0-9]+)", rules_text, flags=re.I
            ))),
        })

    totals = sum_counters(counters_by_case.values())
    manifest: dict[str, Any] = {
        "dataset_name": "ei-high-o2-qwen3-8b-grouped-cv",
        "dataset_date": "2026-09-08",
        "target_model": MODEL,
        "source_root": str(SOURCE_ROOT),
        "output_root": str(OUTPUT),
        "source_policy": "read_only",
        "quality_field": "result.aggregates[id=effectiveness.o2].score",
        "selection_policy": "seven user-selected high-O2 trajectories; status ignored",
        "source_trajectory_count": len(CASES),
        "task_families": list(FAMILIES),
        "split_policy": "5-fold grouped cross-validation by task_family",
        "recommended_default_single_split": DEFAULT_FOLD,
        "reasoning_policy": "drop_source_thinking",
        "loss_policy": "completion_only",
        "context_char_budget": core.CONTEXT_CHAR_BUDGET,
        "root_user_char_limit": core.ROOT_USER_CHAR_LIMIT,
        "tool_result_char_limit": core.TOOL_RESULT_CHAR_LIMIT,
        "completion_char_limit": core.COMPLETION_CHAR_LIMIT,
        "tool_schema_policy": "inferred from all seven trajectories; verify against runtime",
        "score_ruleset_releases": sorted({item["ruleset_release"] for item in source_meta.values()}),
        "provided_rules_document": rules_doc,
        "tokenizer_validation": {
            "status": "not_run_by_converter",
            "reason": "Use validator --model with an existing local tokenizer; never auto-download.",
        },
        "counts": {
            "full_trajectories": len(full_rows),
            "decision_samples": len(samples),
            "rejected_samples": len(rejected),
            "observed_tools": len(tools),
            "thinking_blocks_dropped": totals.get("thinking_blocks_dropped", 0),
            "thinking_chars_dropped": totals.get("thinking_chars_dropped", 0),
            "tool_calls_kept": totals.get("tool_calls_kept", 0),
            "tool_results_kept": totals.get("tool_results_kept", 0),
            "tool_results_truncated": totals.get("tool_results_truncated", 0),
            "tool_result_chars_omitted": totals.get("tool_result_chars_omitted", 0),
        },
        "normalization_counters": totals,
        "sample_statistics": {
            "all": core.sample_statistics(samples),
            "by_family": {
                family: core.sample_statistics(by_family[family]) for family in FAMILIES
            },
        },
        "folds": fold_records,
        "trajectories": [source_meta[case] for case, _ in CASES],
    }
    manifest["output_sha256"] = {
        str(path.relative_to(OUTPUT)): core.sha256_file(path)
        for path in sorted(OUTPUT.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    core.write_json(OUTPUT / "manifest.json", manifest)
    print(json.dumps({
        "status": "BUILT",
        "output": str(OUTPUT),
        "full_trajectories": len(full_rows),
        "decision_samples": len(samples),
        "folds": [
            {
                "fold_id": row["fold_id"],
                "train": row["train_sample_count"],
                "validation": row["validation_sample_count"],
                "validation_tasks": row["validation_task_count"],
            }
            for row in fold_records
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
