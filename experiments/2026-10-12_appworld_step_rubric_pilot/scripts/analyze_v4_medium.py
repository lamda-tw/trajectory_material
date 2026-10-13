"""Summarize the bounded medium-effort repeat probe separately from the main study."""
from collections import Counter
from pathlib import Path
from statistics import mean
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    summarize = runpy.run_path(str(ROOT / "scripts/analyze_v4.py"))["summarize"]
    checks = read(ROOT / "review/v4_regression_checks.json")["checks"]
    first, a = summarize("v4_medium", "manifest_v4_medium_probe.json", checks)
    second, b = summarize("v4_medium_repeat", "manifest_v4_medium_probe.json", checks)
    changes = []
    for sid, steps in a.items():
        assert (ROOT / "runs/v4_medium" / sid / "request.txt").read_bytes() == (ROOT / "runs/v4_medium_repeat" / sid / "request.txt").read_bytes()
        for step, labels in steps.items():
            for i, (left, right) in enumerate(zip(labels, b[sid][step])):
                if left != right:
                    changes.append({"trajectory": sid, "step": step, "rubric": f"R{i+1}", "first": left, "repeat": right})
    high = read(ROOT / "review/v4_comparison.json")
    ids = set(a)
    high_changes = [c for c in high["repeat"]["changed_cells"] if c["trajectory"] in ids]
    high_samples = [s for group in ["regression", "repeat"] for s in high[group]["samples"] if s["id"] in ids]
    all_medium_samples = first["samples"] + second["samples"]
    attempts = first["attempts"] + second["attempts"]
    usage = Counter()
    for attempt in attempts:
        usage.update(attempt["reported_usage"] or {})
    result = {"first": first, "repeat": second, "same_cells": first["cells"]-len(changes),
              "cells": first["cells"], "changed_cells": changes,
              "f_switches": [c for c in changes if "F" in [c["first"], c["repeat"]]],
              "mean_medium_seconds": mean(s["seconds"] for s in all_medium_samples),
              "same_pair_high_same_cells": first["cells"]-len(high_changes),
              "same_pair_high_f_switches": sum("F" in [c["first"], c["repeat"]] for c in high_changes),
              "mean_same_pair_high_seconds": mean(s["seconds"] for s in high_samples),
              "attempts": len(attempts), "completed_calls": sum(a["completed"] for a in attempts),
              "reported_usage": dict(usage),
              "caveat": "Two development trajectories, two repeats per setting; effort is the intended variable, while service/cache/session effects were not controlled. Consistency is not accuracy."}
    (ROOT / "review/v4_medium_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: result[k] for k in ["same_cells", "cells", "f_switches", "mean_medium_seconds", "same_pair_high_same_cells", "same_pair_high_f_switches", "mean_same_pair_high_seconds", "completed_calls"]}, ensure_ascii=False, indent=2))
    print("checks", [(d["check_matches"], d["checks_total"]) for d in [first, second]])
    print("mismatches", json.dumps([c for d in [first, second] for c in d["checks"]+d["anchors"] if not c["matches"]], ensure_ascii=False))


if __name__ == "__main__":
    main()
