"""Compare the frozen v3 run with historical versions; never synthesize rewards."""
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
import hashlib
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(run_name, manifest_name, checks):
    run = ROOT / "runs" / run_name
    manifest = read(ROOT / manifest_name)
    schema = read(run / "schema.json")
    funcs = runpy.run_path(str(ROOT / "scripts/run_judge_v3.py"))
    samples, matrices = [], {}
    counts = {f"R{i+1}": Counter() for i in range(8)}
    usage = Counter()
    for sample in manifest["samples"]:
        folder = run / sample["id"]
        if not folder.exists():
            continue
        payload = read(folder / "input.json")
        result = read(folder / "judgement.json")
        funcs["validate"](result, payload, schema)
        assert sha(folder / "input.json") == sample["input_sha256"]
        assert sha(Path(sample["source"])) == sample["source_sha256"]
        assert (folder / "request.txt").read_text() == (run / "prompt.txt").read_text().replace(
            "{{TRAJECTORY_JSON}}", (folder / "input.json").read_text())
        assert set(payload) == {"trajectory_id", "task", "agent_instructions", "reference_api_docs", "steps", "termination"}
        meta = read(folder / "metadata.json")
        attempt = next(a for a in meta["attempts"] if a["status"] == "valid")
        audit = funcs["audit_events"](folder / f"attempt_{attempt['attempt']}" / "events.jsonl")
        assert audit["tool_items"] == []
        usage.update(audit["usage"] or {})
        matrices[sample["id"]] = {row[0]: row[1] for row in result["steps"]}
        for step, labels, reason in result["steps"]:
            for i, label in enumerate(labels):
                counts[f"R{i+1}"][label] += 1
        samples.append({"id": sample["id"], "steps": len(result["steps"]),
                        "official_success_for_researcher_only": sample["official_success_for_researcher_only"],
                        "seconds": attempt["elapsed_seconds"], "usage": audit["usage"],
                        "attempts": len(meta["attempts"]),
                        "response_characters": len((folder / f"attempt_{attempt['attempt']}" / "response.json").read_text())})
    outcomes = []
    for check in checks:
        if check["trajectory"] not in matrices:
            continue
        label = matrices[check["trajectory"]][check["step"]][int(check["rubric"][1:])-1]
        outcomes.append({**check, "observed": label, "matches": label in check["expected"]})
    return {"run": run_name, "valid_trajectories": len(samples), "steps": sum(s["steps"] for s in samples),
            "cells": sum(s["steps"] for s in samples)*8, "samples": samples,
            "mean_call_seconds": mean(s["seconds"] for s in samples),
            "median_call_seconds": median(s["seconds"] for s in samples),
            "completed_call_usage": dict(usage), "label_counts": {r: dict(c) for r, c in counts.items()},
            "check_matches": sum(c["matches"] for c in outcomes), "checks_total": len(outcomes),
            "checks": outcomes}, matrices


def main():
    checks = read(ROOT / "review/evidence_checks.json")["checks"]
    primary, matrices = summarize("v3_test", "manifest_v3.json", checks)
    historical = read(ROOT / "review/comparison.json")
    changes = []
    for sid, rows in matrices.items():
        old = read(ROOT / "runs/v2_audit" / sid / "judgement.json")
        for step, labels in old["steps"]:
            for i, (v2, v3) in enumerate(zip(labels, rows[step])):
                if v2 != v3:
                    changes.append({"trajectory": sid, "step": step, "rubric": f"R{i+1}", "v2": v2, "v3": v3})
    result = {"generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "primary": primary,
              "v2_to_v3_changes": changes, "historical": {v: {k: d[k] for k in [
                  "valid_trajectories", "steps", "cells", "development_check_matches", "development_checks_total", "completed_call_usage"]}
                  for v, d in historical["versions"].items()},
              "caveats": ["Original 28 checks are development checks, not independent accuracy.",
                          "Labels are never converted into totals, rewards or training weights.",
                          "Latency depends on reasoning and service conditions as well as prompt length."]}
    repeat_run = ROOT / "runs/v3_repeat/summary.json"
    if repeat_run.exists():
        repeated, new_matrix = summarize("v3_repeat", "manifest_v3.json", checks)
        changed = []
        for sid, rows in new_matrix.items():
            assert (ROOT / "runs/v3_test" / sid / "request.txt").read_bytes() == (ROOT / "runs/v3_repeat" / sid / "request.txt").read_bytes()
            for step, labels in rows.items():
                for i, (first, second) in enumerate(zip(matrices[sid][step], labels)):
                    if first != second:
                        changed.append({"trajectory": sid, "step": step, "rubric": f"R{i+1}", "first": first, "repeat": second})
        repeated["changed_cells"] = changed
        repeated["same_cells"] = repeated["cells"] - len(changed)
        result["repeat"] = repeated
    if (ROOT / "runs/v3_unseen/summary.json").exists():
        new_checks = read(ROOT / "review/v3_unseen_checks.json")["checks"]
        result["unseen"], _ = summarize("v3_unseen", "manifest_v3_unseen.json", new_checks)
    (ROOT / "review/v3_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"primary": {k: primary[k] for k in ["valid_trajectories", "steps", "check_matches", "checks_total", "mean_call_seconds", "completed_call_usage"]},
                      "changed_cells_vs_v2": len(changes), "failed_checks": [c for c in primary["checks"] if not c["matches"]]}, ensure_ascii=False, indent=2))
    for key in ["repeat", "unseen"]:
        if key in result:
            d = result[key]
            print(key, json.dumps({k: d[k] for k in ["valid_trajectories", "steps", "cells", "check_matches", "checks_total"]},ensure_ascii=False))
            if key == "repeat": print("repeat_changed_cells", json.dumps(d["changed_cells"], ensure_ascii=False))


if __name__ == "__main__":
    main()
