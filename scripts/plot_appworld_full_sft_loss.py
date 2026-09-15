#!/usr/bin/env python3
"""Plot all five epochs of full-SFT completion-only training loss."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--expected-steps", type=int, default=1600)
    parser.add_argument("--steps-per-epoch", type=int, default=320)
    parser.add_argument("--moving-average", type=int, default=50)
    args = parser.parse_args()

    experiment = args.experiment.resolve()
    history_path = experiment / "metrics" / "training_history.jsonl"
    rows = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != args.expected_steps:
        raise ValueError(f"expected {args.expected_steps} loss rows, found {len(rows)}")
    steps = np.asarray([int(row["step"]) for row in rows], dtype=np.int64)
    losses = np.asarray([float(row["train_loss"]) for row in rows], dtype=np.float64)
    epochs = np.asarray([int(row["epoch"]) for row in rows], dtype=np.int64)
    if not np.array_equal(steps, np.arange(1, args.expected_steps + 1)):
        raise ValueError("global optimizer steps are not contiguous from 1")
    if not np.isfinite(losses).all():
        raise ValueError("loss history contains non-finite values")
    for epoch in range(1, 6):
        count = int((epochs == epoch).sum())
        if count != args.steps_per_epoch:
            raise ValueError(f"epoch {epoch}: expected {args.steps_per_epoch} rows, found {count}")

    window = args.moving_average
    cumulative = np.cumsum(np.insert(losses, 0, 0.0))
    moving = np.empty_like(losses)
    for index in range(len(losses)):
        start = max(0, index + 1 - window)
        moving[index] = (cumulative[index + 1] - cumulative[start]) / (index + 1 - start)

    metrics_dir = experiment / "metrics"
    csv_path = metrics_dir / "loss_history_5epochs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["global_optimizer_step", "epoch", "train_loss", "causal_moving_average_50"])
        for step, epoch, loss, smoothed in zip(steps, epochs, losses, moving):
            writer.writerow([int(step), int(epoch), float(loss), float(smoothed)])

    summary = {
        "global_steps": len(rows),
        "steps_per_epoch": args.steps_per_epoch,
        "moving_average_window": window,
        "x_axis": "Global optimizer step (one synchronized update across 2 GPUs)",
        "y_axis": "Completion-only cross-entropy loss",
        "epoch_summaries": [],
    }
    for epoch in range(1, 6):
        values = losses[epochs == epoch]
        summary["epoch_summaries"].append(
            {
                "epoch": epoch,
                "steps": int(values.size),
                "mean_loss": float(values.mean()),
                "first_20_mean_loss": float(values[:20].mean()),
                "last_20_mean_loss": float(values[-20:].mean()),
                "min_loss": float(values.min()),
                "max_loss": float(values.max()),
            }
        )
    (metrics_dir / "loss_summary_5epochs.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fig, ax = plt.subplots(figsize=(14, 8), dpi=180)
    ax.plot(steps, losses, color="#8EBAD9", linewidth=0.55, alpha=0.28, label="Per-step loss")
    ax.plot(
        steps,
        moving,
        color="#C73E4D",
        linewidth=2.3,
        label=f"Causal moving average ({window} steps)",
    )
    for boundary in range(args.steps_per_epoch, args.expected_steps, args.steps_per_epoch):
        ax.axvline(boundary, color="#888888", linestyle="--", linewidth=0.9, alpha=0.75)
    top = max(float(losses.max()), float(moving.max())) * 1.08
    for epoch in range(1, 6):
        center = (epoch - 0.5) * args.steps_per_epoch
        ax.text(center, top * 0.975, f"Epoch {epoch}", ha="center", va="top", color="#4A4A4A")
    ax.set_title("Qwen3-8B AppWorld Full-Parameter SFT Training Loss — 5 Epochs", fontsize=16)
    ax.set_xlabel("Global optimizer step (one synchronized update across 2 GPUs)", fontsize=12)
    ax.set_ylabel("Completion-only cross-entropy loss", fontsize=12)
    ax.set_xlim(1, args.expected_steps)
    ax.set_ylim(0, top)
    ax.grid(True, color="#D9D9D9", linewidth=0.7, alpha=0.7)
    ax.legend(loc="center right", frameon=True)
    fig.tight_layout()
    fig.savefig(metrics_dir / "loss_curve_total_5epochs.png", bbox_inches="tight")
    fig.savefig(metrics_dir / "loss_curve_total_5epochs.pdf", bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
