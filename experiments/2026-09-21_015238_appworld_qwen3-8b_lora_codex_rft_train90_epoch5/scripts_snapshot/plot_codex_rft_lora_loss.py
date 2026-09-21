#!/usr/bin/env python3
"""Plot the five-epoch Codex-RFT loss and compare it with the earlier 67-task run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def moving_mean(values: list[float], window: int) -> list[float]:
    result: list[float] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        result.append(total / min(index + 1, window))
    return result


def check_history(rows: list[dict], steps_per_epoch: int) -> None:
    if len(rows) != 5 * steps_per_epoch:
        raise ValueError(f"expected {5 * steps_per_epoch} steps, got {len(rows)}")
    for index, row in enumerate(rows, 1):
        expected_epoch = (index - 1) // steps_per_epoch + 1
        if int(row["step"]) != index or int(row["epoch"]) != expected_epoch:
            raise ValueError(f"non-contiguous or mislabelled history at step {index}")
        if not math.isfinite(float(row["loss"])) or float(row["loss"]) < 0:
            raise ValueError(f"invalid loss at step {index}")


def draw_single(rows: list[dict], output: Path) -> None:
    steps = [int(row["step"]) for row in rows]
    losses = [float(row["loss"]) for row in rows]
    smooth = moving_mean(losses, 50)
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=180)
    ax.plot(steps, losses, color="#76A5D4", alpha=0.28, linewidth=0.75,
            label="Per-step loss")
    ax.plot(steps, smooth, color="#C83E4D", linewidth=2.2,
            label="Causal moving average (50 steps)")
    for boundary in (585, 1170, 1755, 2340):
        ax.axvline(boundary, color="#555555", linestyle="--", linewidth=0.9, alpha=0.65)
    for epoch in range(1, 6):
        ax.text((epoch - 0.5) * 585, 0.985, f"Epoch {epoch}",
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=10, color="#333333")
    ax.set_title("Qwen3-8B AppWorld Codex-RFT LoRA Training Loss — 5 Epochs",
                 fontsize=16, pad=16)
    ax.set_xlabel("Global optimizer step (one synchronized update across 2 GPUs)", fontsize=12)
    ax.set_ylabel("Completion-only cross-entropy loss", fontsize=12)
    ax.set_xlim(1, 2925)
    ax.set_ylim(bottom=0)
    ax.grid(True, which="major", color="#D9D9D9", linewidth=0.7, alpha=0.7)
    ax.legend(loc="center right", frameon=True)
    fig.tight_layout()
    fig.savefig(output / "loss_curve_total_5epochs.png", bbox_inches="tight")
    fig.savefig(output / "loss_curve_total_5epochs.pdf", bbox_inches="tight")
    plt.close(fig)


def draw_comparison(new_rows: list[dict], old_rows: list[dict], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=180)
    series = [
        (old_rows, 320, "#C83E4D", "Earlier 67 tasks · 640 decisions"),
        (new_rows, 585, "#2867A1", "Codex-RFT 90 tasks · 1170 decisions"),
    ]
    for rows, steps_per_epoch, color, label in series:
        x = [int(row["step"]) / steps_per_epoch for row in rows]
        losses = [float(row["loss"]) for row in rows]
        window = round(0.1 * steps_per_epoch)
        ax.plot(x, moving_mean(losses, window), color=color, linewidth=2.4,
                label=f"{label} ({window}-step moving mean)")
    for boundary in (1, 2, 3, 4):
        ax.axvline(boundary, color="#777777", linestyle="--", linewidth=0.8, alpha=0.55)
    ax.set_title("Qwen3-8B AppWorld LoRA Training Loss — 5-Epoch Comparison",
                 fontsize=16, pad=16)
    ax.set_xlabel("Completed epochs (optimizer steps normalized within each run)", fontsize=12)
    ax.set_ylabel("Completion-only cross-entropy loss", fontsize=12)
    ax.set_xlim(0, 5)
    ax.set_ylim(bottom=0)
    ax.set_xticks(range(6))
    ax.grid(True, which="major", color="#D9D9D9", linewidth=0.7, alpha=0.7)
    ax.legend(loc="upper right", frameon=True)
    fig.text(0.5, 0.015,
             "Different training sets and run boundaries; training loss is not Dev/evaluator performance.",
             ha="center", va="bottom", fontsize=10, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output / "loss_curve_compare_67_vs_90_5epochs.png", bbox_inches="tight")
    fig.savefig(output / "loss_curve_compare_67_vs_90_5epochs.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--prior-experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    new_exp = args.experiment_dir.resolve()
    old_exp = args.prior_experiment_dir.resolve()
    new_path = new_exp / "artifacts" / "metrics.json"
    old_path = old_exp / "metrics" / "loss_history_5epochs.csv"
    new_metrics = json.loads(new_path.read_text(encoding="utf-8"))
    if new_metrics["status"] != "SUCCESS":
        raise ValueError("new experiment has not completed successfully")
    new_rows = [
        {"step": int(row["step"]), "epoch": int(row["epoch"]),
         "loss": float(row["train_loss"]), "elapsed_seconds": float(row["elapsed_seconds"])}
        for row in new_metrics["training"]["history"]
    ]
    with old_path.open(encoding="utf-8", newline="") as handle:
        old_rows = [
            {"step": int(row["global_step"]), "epoch": int(row["epoch"]),
             "loss": float(row["train_loss"])}
            for row in csv.DictReader(handle)
        ]
    check_history(new_rows, 585)
    check_history(old_rows, 320)

    output = new_exp / "metrics"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "loss_history_5epochs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("step", "epoch", "loss", "elapsed_seconds"))
        writer.writeheader()
        writer.writerows(new_rows)
    draw_single(new_rows, output)
    draw_comparison(new_rows, old_rows, output)

    summary = {
        "new_metrics_sha256": sha256(new_path),
        "prior_history_sha256": sha256(old_path),
        "new_steps_per_epoch": 585,
        "prior_steps_per_epoch": 320,
        "comparison_x_axis": "completed_epochs = global_step / steps_per_epoch",
        "comparison_smoothing": "causal moving average over 10% of one epoch (58 new, 32 prior steps)",
        "new_epoch_mean_loss": [sum(row["loss"] for row in new_rows[(e - 1) * 585:e * 585]) / 585
                                for e in range(1, 6)],
        "prior_epoch_mean_loss": [sum(row["loss"] for row in old_rows[(e - 1) * 320:e * 320]) / 320
                                  for e in range(1, 6)],
    }
    (output / "loss_comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
