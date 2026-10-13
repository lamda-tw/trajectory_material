"""Static report figures from completed scoring; no model calls."""
from pathlib import Path
import csv
import json
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    summary = json.loads((ROOT / "analysis/summary.json").read_text())
    timer = json.loads((ROOT / "TIMING.json").read_text())
    output = ROOT / "analysis/figures"
    output.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"P": "#3c9169", "F": "#c65451", "U": "#d9a441", "N": "#bfc7ce"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True, constrained_layout=True)
    for axis, group, title in zip(axes, ["success", "failure"], ["Official success (39 trajectories)", "Official failure (501 trajectories)"]):
        counts = summary["by_official_outcome"][group]
        bottom = np.zeros(8)
        for label in ["P", "F", "U", "N"]:
            values = np.array([100*counts[f"R{i}"].get(label, 0)/sum(counts[f"R{i}"].values()) for i in range(1, 9)])
            axis.bar([f"R{i}" for i in range(1, 9)], values, bottom=bottom, color=colors[label], label=label, width=.7)
            bottom += values
        axis.set_title(title)
        axis.set_ylim(0, 100)
        axis.set_ylabel("Share of step labels (%)")
    axes[-1].legend(ncol=4, loc="upper center", bbox_to_anchor=(.5, -.12))
    fig.savefig(output / "rubric_distribution.png", dpi=180)
    fig.savefig(output / "rubric_distribution.svg")
    plt.close(fig)
    events = [json.loads(line) for line in (ROOT / "logs/scoring_events.jsonl").read_text().splitlines() if line.strip()]
    completions = [e for e in events if e["event"] == "valid"]
    completions.sort(key=lambda e: e["at"])
    hours = [(datetime.fromisoformat(e["at"]).timestamp()-timer["scoring_start_epoch"])/3600 for e in completions]
    fig, axis = plt.subplots(figsize=(9, 4), constrained_layout=True)
    axis.step([0]+hours, list(range(len(hours)+1)), where="post", color="#326a9c", linewidth=2)
    axis.set(xlabel="Hours since first scoring request", ylabel="Validated trajectories", title="Full v5 scoring throughput", ylim=(0, 545))
    axis.axhline(540, color="#9aa4ad", linestyle="--", linewidth=.7)
    for e in events:
        if e["event"] == "concurrency_changed":
            x = (datetime.fromisoformat(e["at"]).timestamp()-timer["scoring_start_epoch"])/3600
            axis.axvline(x, color="#a7adb4", linewidth=.6, alpha=.5)
    fig.savefig(output / "scoring_throughput.png", dpi=180)
    fig.savefig(output / "scoring_throughput.svg")
    plt.close(fig)
    with (ROOT / "analysis/trajectory_metrics.csv").open() as f:
        rows = list(csv.DictReader(f))
    seconds = [float(row["accepted_seconds"]) for row in rows]
    fig, axis = plt.subplots(figsize=(8, 4), constrained_layout=True)
    axis.hist(seconds, bins=30, color="#326a9c", edgecolor="white")
    axis.axvline(np.median(seconds), color="#d08a30", linestyle="--", label=f"Median {np.median(seconds):.1f}s")
    axis.set(xlabel="Seconds per accepted scoring call", ylabel="Trajectories", title="Scoring call latency (retry time reported separately)")
    axis.legend()
    fig.savefig(output / "call_latency.png", dpi=180)
    fig.savefig(output / "call_latency.svg")
    plt.close(fig)
    print(str(output))


if __name__ == "__main__":
    main()
