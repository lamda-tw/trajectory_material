"""Summarize completed versions without converting labels to a reward."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import collections
import hashlib
import json
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    checks = json.loads((ROOT / "review/evidence_checks.json").read_text())["checks"]
    validate = runpy.run_path(str(ROOT / "scripts/run_judge.py"))["validate"]
    versions = {}
    for version, name in [("v1", "v1_audit_recovered"), ("v2", "v2_audit")]:
        run = ROOT / "runs" / name
        if not (run / "summary.json").exists():
            continue
        schema = json.loads((run / "schema.json").read_text())
        matrices, samples = {}, []
        labels = {f"R{i+1}": collections.Counter() for i in range(8)}
        usage = collections.Counter()
        for sample in manifest["samples"]:
            folder = run / sample["id"]
            result = json.loads((folder / "judgement.json").read_text())
            payload = json.loads((folder / "input.json").read_text())
            validate(result, payload, schema)
            assert hashlib.sha256((folder / "input.json").read_bytes()).hexdigest() == sample["input_sha256"]
            assert hashlib.sha256(Path(sample["source"]).read_bytes()).hexdigest() == sample["source_sha256"]
            metadata = json.loads((folder / "metadata.json").read_text())
            if "reused_from" in metadata:
                audit = metadata["audit"]
                old_attempt = ROOT / metadata["reused_from"]
                seconds = json.loads((old_attempt / "failure.json").read_text())["elapsed_seconds"]
                attempt_path = str(old_attempt.relative_to(ROOT))
            else:
                successful = next(a for a in metadata["attempts"] if a["status"] == "valid")
                audit = successful["audit"]
                seconds = successful["elapsed_seconds"]
                attempt_path = str((folder / f"attempt_{successful['attempt']}").relative_to(ROOT))
            usage.update(audit["usage"] or {})
            matrices[sample["id"]] = dict(result["steps"])
            for step, string in result["steps"]:
                for i, label in enumerate(string):
                    labels[f"R{i+1}"][label] += 1
            samples.append({"id": sample["id"], "steps": len(result["steps"]),
                            "official_success_for_researcher_only": sample["official_success_for_researcher_only"],
                            "seconds": seconds, "usage": audit["usage"],
                            "notes": len(result["notes"]), "attempt": attempt_path,
                            "judgement": str((folder / "judgement.json").relative_to(ROOT))})
        outcomes = []
        for check in checks:
            observed = matrices[check["trajectory"]][check["step"]][int(check["rubric"][1:])-1]
            outcomes.append({**check, "observed": observed, "matches": observed in check["expected"]})
        versions[version] = {"valid_trajectories": len(samples), "steps": sum(s["steps"] for s in samples),
                             "cells": sum(s["steps"] for s in samples)*8,
                             "label_counts": {r: dict(c) for r, c in labels.items()},
                             "completed_call_usage": dict(usage), "samples": samples,
                             "development_check_matches": sum(x["matches"] for x in outcomes),
                             "development_checks_total": len(outcomes), "development_checks": outcomes}
    changes = []
    if len(versions) == 2:
        for sample in manifest["samples"]:
            a = json.loads((ROOT / "runs/v1_audit_recovered" / sample["id"] / "judgement.json").read_text())
            b = json.loads((ROOT / "runs/v2_audit" / sample["id"] / "judgement.json").read_text())
            for (step, old), (step2, new) in zip(a["steps"], b["steps"]):
                assert step == step2
                for i, (left, right) in enumerate(zip(old, new)):
                    if left != right:
                        changes.append({"trajectory": sample["id"], "step": step, "rubric": f"R{i+1}", "v1": left, "v2": right})
    attempts = []
    for command in sorted((ROOT / "runs").glob("*/*/attempt_*/command.json")):
        events = command.parent / "events.jsonl"
        parsed = []
        for line in events.read_text().splitlines():
            try:
                parsed.append(json.loads(line))
            except ValueError:
                pass
        completed = [e for e in parsed if e.get("type") == "turn.completed"]
        attempts.append({"path": str(command.parent.relative_to(ROOT)), "completed": bool(completed),
                         "reported_usage": completed[-1].get("usage") if completed else None})
    summary = {"generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "versions": versions,
               "changed_cells": changes, "attempts": attempts,
               "caveats": ["Development checks were chosen from these trajectories; not independent accuracy.",
                           "One judgement per input per prompt version; no repeatability measurement.",
                           "Cancelled calls lack completed usage; do not interpret missing usage as zero.",
                           "No reward, weight, trajectory replay, training, or claim of downstream improvement."]}
    write(ROOT / "review/comparison.json", summary)
    print(json.dumps({"versions": {v: {k: d[k] for k in ["valid_trajectories", "steps", "development_check_matches", "development_checks_total", "completed_call_usage"]} for v, d in versions.items()},
                      "changed_cells": len(changes), "actual_attempts": len(attempts)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
