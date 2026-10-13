"""Review completed v4 runs, exact repeats and cheap execution/applicability anchors."""
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
import ast
import hashlib
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_only_code(code):
    """Conservative anchor, not a general AppWorld program verifier."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    if not code.strip() or any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.With)) for n in ast.walk(tree)):
        return False
    safe_functions = {"print", "len", "range", "list", "dict", "set", "tuple", "int", "float", "str", "bool", "type", "sum", "max", "min", "round", "sorted", "enumerate", "zip", "any", "all"}
    safe_methods = {"append", "extend", "add", "update", "union", "get", "keys", "values", "items", "split", "strip", "lower", "upper", "replace", "endswith", "startswith", "strftime", "strptime", "now", "today"}
    api_apps = {"api_docs", "supervisor", "phone", "spotify", "venmo", "simple_note", "file_system"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = ast.unparse(node.func)
        if function.startswith("apis."):
            parts = function.split(".")
            if len(parts) != 3 or parts[1] not in api_apps:
                return False
            app, name = parts[1:]
            if app == "api_docs" and name.startswith("show_"):
                continue
            if app == "supervisor" and name == "complete_task":
                continue
            if name.startswith(("show_", "search_")) or name in {"login", "directory_exists", "file_exists", "get_current_date_and_time"}:
                continue
            return False
        if isinstance(node.func, ast.Name) and node.func.id in safe_functions:
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in safe_methods:
            continue
        return False
    return True


def summarize(run_name, manifest_name, checks):
    run = ROOT / "runs" / run_name
    funcs = runpy.run_path(str(ROOT / "scripts/run_judge_v4.py"))
    expected = read(run / "run_manifest.json")
    assert sha(ROOT / manifest_name) == expected["manifest_sha256"]
    assert sha(run / "prompt.txt") == expected["prompt_sha256"]
    assert (run / "prompt.txt").read_bytes() == (ROOT / "snapshots/prompt_v4.txt").read_bytes()
    schema = read(run / "schema.json")
    samples, matrices, anchors, attempts = [], {}, [], []
    counts = {f"R{i+1}": Counter() for i in range(8)}
    usage = Counter()
    by_id = {s["id"]: s for s in read(ROOT / manifest_name)["samples"]}
    for sid in expected["ids"]:
        sample = by_id[sid]
        folder = run / sid
        result, payload = read(folder / "judgement.json"), read(folder / "input.json")
        funcs["validate"](result, payload, schema)
        assert sha(Path(sample["source"])) == sample["source_sha256"]
        assert sha(folder / "input.json") == sample["input_sha256"]
        assert (folder / "request.txt").read_text() == (run / "prompt.txt").read_text().replace("{{TRAJECTORY_JSON}}", (folder / "input.json").read_text())
        assert set(payload) == {"trajectory_id", "task", "agent_instructions", "reference_api_docs", "steps", "termination"}
        meta = read(folder / "metadata.json")
        for attempt in meta["attempts"]:
            attempt_dir = folder / f"attempt_{attempt['attempt']}"
            event_list = [json.loads(line) for line in (attempt_dir / "events.jsonl").read_text().splitlines() if line.strip()]
            completed = [event for event in event_list if event.get("type") == "turn.completed"]
            errors = [event for event in event_list if event.get("type") in {"error", "turn.failed"}]
            if completed:
                audit = funcs["audit_events"](attempt_dir / "events.jsonl")
                assert not audit["tool_items"]
                usage.update(audit["usage"] or {})
            if attempt["status"] == "valid":
                assert read(attempt_dir / "response.json") == result
            attempts.append({"trajectory": sid, "attempt": attempt["attempt"], "status": attempt["status"],
                             "seconds": attempt["elapsed_seconds"], "completed": bool(completed),
                             "reported_usage": completed[-1].get("usage") if completed else None, "errors": errors})
        valid_attempt = next(a for a in meta["attempts"] if a["status"] == "valid")
        matrices[sid] = {step: labels for step, labels, reason in result["steps"]}
        for step, labels, reason in result["steps"]:
            for i, label in enumerate(labels):
                counts[f"R{i+1}"][label] += 1
        for step in payload["steps"]:
            if step["observation"].startswith("Execution failed.") or (not step["code"].strip() and payload["termination"] == "no_python_code" and step == payload["steps"][-1]):
                anchors.append({"trajectory": sid, "step": step["id"], "rubric": "R1", "expected": "F", "observed": matrices[sid][step["id"]][0]})
            if read_only_code(step["code"]):
                anchors.append({"trajectory": sid, "step": step["id"], "rubric": "R5", "expected": "N", "observed": matrices[sid][step["id"]][4]})
        samples.append({"id": sid, "steps": len(result["steps"]), "input_characters": len((folder / "input.json").read_text()),
                        "seconds": valid_attempt["elapsed_seconds"], "seconds_including_retries": meta["elapsed_seconds"],
                        "official_success_for_researcher_only": sample["official_success_for_researcher_only"],
                        "attempts": len(meta["attempts"]), "response_characters": len((folder / f"attempt_{valid_attempt['attempt']}" / "response.json").read_text())})
    outcomes = []
    for check in checks:
        if check["trajectory"] in matrices:
            label = matrices[check["trajectory"]][check["step"]][int(check["rubric"][1:])-1]
            outcomes.append({**check, "observed": label, "matches": label in check["expected"]})
    for anchor in anchors:
        anchor["matches"] = anchor["expected"] == anchor["observed"]
    return {"run": run_name, "valid": len(samples), "steps": sum(s["steps"] for s in samples),
            "cells": sum(s["steps"] for s in samples)*8, "samples": samples, "attempts": attempts,
            "mean_seconds": mean(s["seconds"] for s in samples), "median_seconds": median(s["seconds"] for s in samples),
            "usage": dict(usage), "label_counts": {r: dict(c) for r, c in counts.items()},
            "checks": outcomes, "check_matches": sum(c["matches"] for c in outcomes), "checks_total": len(outcomes),
            "anchors": anchors, "anchor_matches": sum(c["matches"] for c in anchors), "anchors_total": len(anchors)}, matrices


def main():
    result, matrices = {}, {}
    for key, run, manifest, check_file in [
        ("regression", "v4_regression", "manifest_v4_regression.json", "v4_regression_checks.json"),
        ("fresh", "v4_fresh", "manifest_v4_fresh.json", "v4_fresh_checks.json"),
        ("repeat", "v4_repeat", "manifest_v4_repeat.json", "v4_regression_checks.json")]:
        if not (ROOT / "runs" / run / "summary.json").exists():
            continue
        checks = read(ROOT / "review" / check_file)["checks"]
        result[key], matrices[key] = summarize(run, manifest, checks)
    if "repeat" in result:
        changed = []
        for sid, rows in matrices["repeat"].items():
            original_key = "regression" if sid in matrices["regression"] else "fresh"
            original_run = result[original_key]["run"]
            assert (ROOT / "runs" / original_run / sid / "request.txt").read_bytes() == (ROOT / "runs/v4_repeat" / sid / "request.txt").read_bytes()
            for step, labels in rows.items():
                for i, (a, b) in enumerate(zip(matrices[original_key][sid][step], labels)):
                    if a != b:
                        changed.append({"trajectory": sid, "step": step, "rubric": f"R{i+1}", "first": a, "repeat": b})
        result["repeat"].update(changed_cells=changed, same_cells=result["repeat"]["cells"]-len(changed),
                               f_switches=[c for c in changed if "F" in [c["first"], c["repeat"]]])
    result["generated_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    (ROOT / "review/v4_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    for key in ["regression", "fresh", "repeat"]:
        if key in result:
            d = result[key]
            print(key, json.dumps({k: d[k] for k in ["valid", "steps", "check_matches", "checks_total", "anchor_matches", "anchors_total", "mean_seconds"]}, ensure_ascii=False))
            print("mismatches", json.dumps([c for c in d["checks"]+d["anchors"] if not c["matches"]], ensure_ascii=False))
            if key == "repeat":
                print("repeat_changes", json.dumps(d["changed_cells"], ensure_ascii=False))


if __name__ == "__main__":
    main()
