#!/usr/bin/env python3
"""Build a concise report for the 67-task AppWorld LoRA run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment_dir.resolve()
    config = json.loads((exp / "config" / "training_config.json").read_text(encoding="utf-8"))
    metrics = json.loads((exp / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    generation = json.loads((exp / "metrics" / "generation_smoke.json").read_text(encoding="utf-8"))
    history = metrics["training"]["history"]
    first = mean([float(row["train_loss"]) for row in history[:20]])
    last = mean([float(row["train_loss"]) for row in history[-20:]])
    ranks = metrics["distributed"]["ranks"]
    train = metrics["data"]["train"]
    adapter = exp / "artifacts" / "adapter"
    adapter_model = adapter / "adapter_model.safetensors"
    report = f"""# AppWorld 67-task Qwen3-8B LoRA training report

Status: **{metrics['status']}**. The adapter was trained on all {config['train_tasks']} verified
AppWorld train tasks ({config['train_decision_samples']} completion-only decision samples) with two
NCCL/DDP ranks and reloaded successfully for an AppWorld ReAct-format generation check.

## Training

- Base model: `{config['base_model']}`
- Method: LoRA r={config['lora_r']}, alpha={config['lora_alpha']}; q/k/v/o and gate/up/down projections
- Precision/attention: {config['dtype']} / {config['attention']}
- Context: {config['max_length']} tokens; truncated train samples: {train['truncated_samples']}
- Epochs / optimizer steps: {config['epochs']} / {metrics['training']['global_steps']}
- Per-GPU batch / global batch: {config['per_gpu_batch_size']} / {config['global_batch_size']}
- Learning rate: {config['learning_rate']}
- First 20-step mean loss: {first:.6f}
- Last 20-step mean loss: {last:.6f}
- Training plus diagnostic validation time: {metrics['training']['duration_seconds']:.2f} seconds

The recorded validation loss ({metrics['validation']['loss']:.6f}) is a runtime diagnostic. Its seven
tasks are included in the all-67 training input, so it is not a generalization estimate. The held-out
AppWorld Dev evaluator is the model-quality test.

## Dual-GPU evidence

| rank | GPU | peak allocated | peak reserved |
|---:|---|---:|---:|
| 0 | {ranks[0]['device_name']} | {ranks[0]['peak_allocated_gib']:.2f} GiB | {ranks[0]['peak_reserved_gib']:.2f} GiB |
| 1 | {ranks[1]['device_name']} | {ranks[1]['peak_allocated_gib']:.2f} GiB | {ranks[1]['peak_reserved_gib']:.2f} GiB |

The full time series is stored in `logs/gpu_usage.csv`.

## Adapter verification

- Reload status: {generation['status']}
- Sample: `{generation['sample_id']}`
- Generated tokens: {generation['generated_tokens']}
- Non-empty fenced Python blocks: {generation['python_block_count']}
- Adapter weights: `{adapter_model}`
- Adapter SHA-256: `{sha256_file(adapter_model)}`

The adapter and tokenizer under `artifacts/adapter/` can be loaded with PEFT for AppWorld Dev, or
served by a LoRA-capable vLLM process with the unchanged local Qwen3-8B base model. This experiment
did not run the full Dev benchmark.
"""
    (exp / "REPORT.md").write_text(report, encoding="utf-8")
    print(exp / "REPORT.md")


if __name__ == "__main__":
    main()
