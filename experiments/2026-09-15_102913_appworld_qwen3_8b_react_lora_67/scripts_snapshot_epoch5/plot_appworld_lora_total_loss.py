#!/usr/bin/env python3
"""Combine epoch 1 and continuation histories and plot total five-epoch loss."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rolling_mean(values: list[float], window: int) -> list[float]:
    output: list[float] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        output.append(total / min(index + 1, window))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--window", type=int, default=50)
    args = parser.parse_args()
    exp = args.experiment_dir.resolve()
    epoch1 = json.loads((exp / "artifacts" / "metrics_epoch1.json").read_text(encoding="utf-8"))
    continuation = json.loads(
        (exp / "artifacts" / "continuation" / "metrics_epochs2_5.json").read_text(encoding="utf-8")
    )
    history1 = epoch1["training"]["history"]
    history2 = continuation["training"]["history"]
    if len(history1) != 320 or len(history2) != 1280:
        raise ValueError(f"expected 320 + 1280 steps, got {len(history1)} + {len(history2)}")
    combined: list[dict[str, float | int]] = []
    epoch1_duration = float(epoch1["training"]["duration_seconds"])
    for row in history1:
        combined.append(
            {
                "global_step": int(row["step"]),
                "epoch": int(row["epoch"]),
                "train_loss": float(row["train_loss"]),
                "cumulative_elapsed_seconds": float(row["elapsed_seconds"]),
            }
        )
    for row in history2:
        combined.append(
            {
                "global_step": int(row["step"]),
                "epoch": int(row["epoch"]),
                "train_loss": float(row["train_loss"]),
                "cumulative_elapsed_seconds": epoch1_duration + float(row["elapsed_seconds"]),
            }
        )
    if [int(row["global_step"]) for row in combined] != list(range(1, 1601)):
        raise ValueError("combined global steps are not contiguous 1..1600")

    metrics_dir = exp / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "loss_history_5epochs.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (metrics_dir / "loss_history_5epochs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)

    steps = [int(row["global_step"]) for row in combined]
    losses = [float(row["train_loss"]) for row in combined]
    smooth = rolling_mean(losses, args.window)
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=180)
    ax.plot(steps, losses, color="#76A5D4", alpha=0.28, linewidth=0.75, label="Per-step loss")
    ax.plot(
        steps,
        smooth,
        color="#C83E4D",
        linewidth=2.2,
        label=f"Causal moving average ({args.window} steps)",
    )
    for boundary in (320, 640, 960, 1280):
        ax.axvline(boundary, color="#555555", linestyle="--", linewidth=0.9, alpha=0.65)
    for epoch in range(1, 6):
        ax.text((epoch - 0.5) * 320, 0.985, f"Epoch {epoch}", transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=10, color="#333333")
    ax.set_title("Qwen3-8B AppWorld LoRA Training Loss — 5 Epochs", fontsize=16, pad=16)
    ax.set_xlabel("Global optimizer step (one synchronized update across 2 GPUs)", fontsize=12)
    ax.set_ylabel("Completion-only cross-entropy loss", fontsize=12)
    ax.set_xlim(1, 1600)
    ax.set_ylim(bottom=0)
    ax.grid(True, which="major", color="#D9D9D9", linewidth=0.7, alpha=0.7)
    ax.legend(loc="center right", frameon=True)
    fig.tight_layout()
    fig.savefig(metrics_dir / "loss_curve_total_5epochs.png", bbox_inches="tight")
    fig.savefig(metrics_dir / "loss_curve_total_5epochs.pdf", bbox_inches="tight")
    plt.close(fig)
    print(metrics_dir / "loss_curve_total_5epochs.png")


if __name__ == "__main__":
    main()
