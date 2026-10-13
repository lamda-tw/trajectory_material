"""Analyze only after all 540 fresh scores finish; never invoke a model."""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
import ast
import csv
import hashlib
import json
import re
import runpy
import time

from judge_protocol import audit_events, validate, command

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT.parent / "2026-10-12_appworld_step_rubric_pilot"


def read(path):
    return json.loads(path.read_text())


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def stamp():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def csv_write(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def extra_python_block(commentary):
    for code in re.findall(r"```(?:python|py)\s*\n(.*?)```", commentary, re.S | re.I):
        if code.strip():
            try:
                if ast.parse(code).body:
                    return True
            except SyntaxError:
                pass
    return False


def main():
    started_epoch = time.time()
    timer = read(ROOT / "TIMING.json")
    assert timer.get("scoring_finished_at"), "Scoring must finish before evaluation begins"
    evaluation = ROOT / "EVALUATION_TIMING.json"
    if not evaluation.exists():
        dump(evaluation, {"evaluation_started_at": stamp(), "evaluation_start_epoch": started_epoch,
                          "scoring_finished_at": timer["scoring_finished_at"], "phase": "analysis"})
    manifest = read(ROOT / "manifest.json")
    config = read(ROOT / "judge_config.json")
    frozen = read(ROOT / "runs/scoring/run_manifest.json")
    for path, expected in frozen["files"].items():
        assert sha(ROOT / path) == expected, path
    assert sha(ROOT / "review/semantic_sample_plan.json") == frozen["semantic_review_plan_sha256"]
    schema = read(ROOT / "assets/output_schema_v5.json")
    template = (ROOT / "assets/prompt_v5.txt").read_text()
    official = {s["id"]: s for s in read(ROOT / "research/official_outcomes.json")["samples"]}
    read_only = runpy.run_path(str(ROOT / "assets/pilot_analyzer_snapshot.py"))["read_only_code"]
    counts = {f"R{i}": Counter() for i in range(1, 9)}
    by_outcome = {key: {f"R{i}": Counter() for i in range(1, 9)} for key in ["success", "failure"]}
    steps, trajectories, anchors, attempts, candidates = [], [], [], [], []
    usage, matrices, all_reasons = Counter(), {}, Counter()
    for sample in manifest["samples"]:
        sid = sample["id"]
        folder = ROOT / "runs/scoring" / sid
        payload, result, meta = read(folder / "input.json"), read(folder / "judgement.json"), read(folder / "metadata.json")
        validate(result, payload, schema)
        assert sha(folder / "input.json") == sha(ROOT / sample["input"]) == sample["input_sha256"]
        assert sha(Path(sample["source"])) == sample["source_sha256"]
        assert (folder / "request.txt").read_text() == template.replace("{{TRAJECTORY_JSON}}", (folder / "input.json").read_text())
        assert set(payload) == {"trajectory_id", "task", "agent_instructions", "reference_api_docs", "steps", "termination"}
        assert meta["model"] == config["model"] and meta["reasoning_effort"] == config["reasoning_effort"]
        accepted = None
        for path in sorted(folder.glob("attempt_*")):
            record = read(path / "record.json")
            assert read(path / "command.json") == command(config, folder / "empty_cwd", path / "response.json")
            event_rows = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines() if line.strip()]
            completed = [e for e in event_rows if e.get("type") == "turn.completed"]
            reported = completed[-1].get("usage", {}) if completed else None
            if reported is not None:
                usage.update(reported)
            if record["status"] == "valid":
                audit_events(path / "events.jsonl")
                assert accepted is None, "Multiple valid attempts selected"
                assert read(path / "response.json") == result
                accepted = record
            attempts.append({"id": sid, "attempt": record["attempt"], "status": record["status"],
                             "elapsed_seconds": record["elapsed_seconds"], "usage_reported": reported,
                             "category": record.get("category"), "error": record.get("error")})
        assert accepted and accepted["attempt"] == meta["accepted_attempt"]
        outcome = official[sid]["official_evaluation"]
        success = outcome["success"]
        matrix = {row[0]: row for row in result["steps"]}
        matrices[sid] = matrix
        own_counts = {f"R{i}": Counter() for i in range(1, 9)}
        for inp in payload["steps"]:
            step, labels, reason = matrix[inp["id"]]
            row = {"id": sid, "task_id": sample["task_id"], "task_family": sample["task_id"].split("_")[0],
                   "official_success": success, "step": step, "trajectory_steps": len(matrix),
                   **{f"R{i+1}": label for i, label in enumerate(labels)}, "reason": reason}
            steps.append(row)
            for i, label in enumerate(labels):
                key = f"R{i+1}"
                counts[key][label] += 1
                by_outcome["success" if success else "failure"][key][label] += 1
                own_counts[key][label] += 1
            if reason:
                all_reasons[reason] += 1
            def anchor(rubric, expected, kind):
                observed = labels[int(rubric[1:])-1]
                anchors.append({"id": sid, "step": step, "rubric": rubric, "expected": expected,
                                "observed": observed, "matches": observed == expected, "kind": kind})
            if inp["observation"].startswith("Execution failed.") or (not inp["code"].strip() and step == payload["steps"][-1]["id"] and payload["termination"] == "no_python_code"):
                anchor("R1", "F", "explicit_execution_failure")
            elif inp["code"].strip() and not inp["observation"].startswith("Execution failed."):
                anchor("R1", "P", "normal_execution_observation")
            if read_only(inp["code"]):
                anchor("R5", "N", "conservative_read_only_ast")
            if inp["code"].strip() and extra_python_block(inp["commentary"]):
                anchor("R8", "F", "additional_nonempty_python_block")
            if any(labels[i] == "F" for i in [2, 3, 4]):
                candidates.append({"id": sid, "step": step, "kind": "business_or_factual_failure_candidate", "labels": labels,
                                   "reason": reason, "official_success_for_analysis_only": success, "training_weight": None})
            if labels[0] == "P" and labels[5] == "P":
                previous = [s for s in range(max(1, step-3), step) if matrix[s][1][0] == "F"]
                if previous:
                    candidates.append({"id": sid, "step": step, "kind": "execution_recovery_candidate", "previous_error_step": previous[-1],
                                       "labels": labels, "business_failure_still_present": any(labels[i] == "F" for i in [2, 3, 4]),
                                       "official_success_for_analysis_only": success, "training_weight": None})
        last = result["steps"][-1]
        applicable_r7 = [r for r in result["steps"] if r[1][6] != "N"]
        tr = {"id": sid, "task_id": sample["task_id"], "task_family": sample["task_id"].split("_")[0],
              "task": payload["task"].split("Task:")[-1].strip(), "official_success": success,
              "official_num_tests": outcome["num_tests"], "official_num_passes": outcome["num_passes"],
              "steps": len(matrix), "termination": payload["termination"], "last_R7": last[1][6],
              "latest_applicable_R7": applicable_r7[-1][1][6] if applicable_r7 else "N",
              "any_F_steps": sum("F" in row[1] for row in result["steps"]),
              "only_R8_F_steps": sum(row[1][7] == "F" and "F" not in row[1][:7] for row in result["steps"]),
              "first_F_step": next((row[0] for row in result["steps"] if "F" in row[1]), None),
              "input_characters": len((folder / "input.json").read_text()), "accepted_seconds": accepted["elapsed_seconds"],
              "attempts": len(meta["attempts"])}
        for i, c in own_counts.items():
            for label in "PFUN":
                tr[f"{i}_{label}"] = c[label]
            applicable = sum(c[k] for k in "PFU")
            tr[f"{i}_F_fraction_applicable"] = c["F"]/applicable if applicable else None
        trajectories.append(tr)
    assert len(trajectories) == 540 and len(steps) == 11254
    csv_write(ROOT / "analysis/trajectory_metrics.csv", trajectories)
    csv_write(ROOT / "analysis/step_labels.csv", steps)
    with (ROOT / "analysis/scored_trajectories.jsonl").open("w") as f:
        for sample in manifest["samples"]:
            f.write(json.dumps(read(ROOT / "runs/scoring" / sample["id"] / "judgement.json"), ensure_ascii=False)+"\n")
    with (ROOT / "analysis/step_candidates.jsonl").open("w") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False)+"\n")
    r7_table = {label: {"success": sum(t["official_success"] and t["last_R7"] == label for t in trajectories),
                         "failure": sum(not t["official_success"] and t["last_R7"] == label for t in trajectories)} for label in "PFUN"}
    tp, fp = r7_table["P"]["success"], r7_table["P"]["failure"]
    fn, tn = r7_table["F"]["success"], r7_table["F"]["failure"]
    r7 = {"table": r7_table, "decided_PF": tp+fp+fn+tn, "abstained_UN": sum(sum(r7_table[k].values()) for k in "UN"),
          "P_precision": tp/(tp+fp) if tp+fp else None, "P_recall_among_39_successes": tp/39,
          "PF_agreement_with_official": (tp+tn)/(tp+fp+fn+tn) if tp+fp+fn+tn else None,
          "F_precision": tn/(tn+fn) if tn+fn else None,
          "scope": "Terminal R7 compared with official whole-task outcome; this is not step-label accuracy. U/N are not converted to F. All-failure baseline is 501/540."}
    families = []
    for fam in sorted({t["task_family"] for t in trajectories}):
        rows = [t for t in trajectories if t["task_family"] == fam]
        families.append({"task_family": fam, "example_task": rows[0]["task"], "trajectories": len(rows),
                         "official_successes": sum(t["official_success"] for t in rows), "steps": sum(t["steps"] for t in rows),
                         **{f"R{i}_F": sum(t[f"R{i}_F"] for t in rows) for i in range(1, 9)}})
    csv_write(ROOT / "analysis/task_family_metrics.csv", families)
    mixed_differences = []
    for task in sorted({t["task_id"] for t in trajectories}):
        rows = [t for t in trajectories if t["task_id"] == task]
        good, bad = [t for t in rows if t["official_success"]], [t for t in rows if not t["official_success"]]
        if good and bad:
            item = {"task_id": task, "success_count": len(good), "failure_count": len(bad)}
            for i in range(1, 9):
                key = f"R{i}_F_fraction_applicable"
                a, b = [t[key] for t in good if t[key] is not None], [t[key] for t in bad if t[key] is not None]
                item[key+"_success_minus_failure"] = mean(a)-mean(b) if a and b else None
            mixed_differences.append(item)
    dump(ROOT / "analysis/within_task_comparison.json", mixed_differences)
    checks = []
    for name in ["v5_regression_checks.json", "v5_fresh_checks.json"]:
        for check in read(PILOT / "review" / name)["checks"]:
            observed = matrices[check["trajectory"]][check["step"]][1][int(check["rubric"][1:])-1]
            checks.append({**check, "observed": observed, "matches": observed in check["expected"]})
    repeats = []
    compared = 0
    for sample in read(PILOT / "v5_scored_index.json")["samples"]:
        sid = sample["id"]
        for step, labels, reason in read(PILOT / sample["judgement"])["steps"]:
            compared += 8
            for i, (a, b) in enumerate(zip(labels, matrices[sid][step][1])):
                if a != b:
                    repeats.append({"id": sid, "step": step, "rubric": f"R{i+1}", "pilot": a, "full": b})
    anchor_summary = {}
    for kind in sorted({a["kind"] for a in anchors}):
        items = [a for a in anchors if a["kind"] == kind]
        anchor_summary[kind] = {"matches": sum(a["matches"] for a in items), "total": len(items)}
    dump(ROOT / "analysis/mechanical_checks.json", {"summary": anchor_summary, "checks": anchors,
         "limitation": "Observable execution/format anchors; AST is conservative, not a general semantic oracle."})
    dump(ROOT / "analysis/frozen_development_checks.json", {"matches": sum(c["matches"] for c in checks), "total": len(checks), "checks": checks})
    dump(ROOT / "analysis/pilot_repeat_comparison.json", {"compared_cells": compared, "same_cells": compared-len(repeats),
         "F_switches": sum("F" in [r["pilot"], r["full"]] for r in repeats), "changes": repeats,
         "limitation": "Same inputs, model and prompt across dates and different concurrency; consistency is not accuracy."})
    dump(ROOT / "analysis/attempts.json", attempts)
    summary = {"generated_at": stamp(), "trajectories": 540, "steps": 11254, "cells": 11254*8,
               "official_successes": 39, "official_failures": 501, "label_counts": {k: dict(v) for k,v in counts.items()},
               "by_official_outcome": {g: {k: dict(v) for k,v in cs.items()} for g,cs in by_outcome.items()},
               "terminal_R7": r7, "attempts": len(attempts), "invalid_attempts": sum(a["status"] != "valid" for a in attempts),
               "unreported_usage_attempts": sum(a["usage_reported"] is None for a in attempts), "reported_token_usage": dict(usage),
               "scoring_wall_seconds": timer["scoring_wall_seconds"],
               "scoring_subprocess_seconds_sum": sum(a["elapsed_seconds"] for a in attempts),
               "accepted_latency_mean_seconds": mean(t["accepted_seconds"] for t in trajectories),
               "accepted_latency_median_seconds": median(t["accepted_seconds"] for t in trajectories),
               "candidate_counts": dict(Counter(c["kind"] for c in candidates)),
               "mechanical_checks": anchor_summary, "frozen_check_matches": sum(c["matches"] for c in checks),
               "frozen_checks_total": len(checks), "pilot_same_cells": compared-len(repeats), "pilot_compared_cells": compared,
               "analysis_compute_seconds": time.time()-started_epoch}
    dump(ROOT / "analysis/summary.json", summary)
    dump(ROOT / "analysis/validation.json", {"checked_at": stamp(), "all_540_source_hashes": True,
         "all_requests_exact_frozen_prompt_plus_input": True, "all_step_ids_exact_order": True,
         "all_schema_valid": True, "raw_responses_unchanged": True, "judge_tool_calls": 0,
         "no_official_outcome_in_judge_input": True, "scoring_timer_closed_before_analysis": True})
    sample_plan = read(ROOT / "review/semantic_sample_plan.json")
    lines = ["# 预先抽定12条完整轨迹：原始评分", "", "本文件只展示原始标签与短依据；不输出凭据或完整观察。", ""]
    for sid in sample_plan["ids"]:
        p = read(ROOT / "runs/scoring" / sid / "input.json")
        lines += [f"## {sid}", "", p["task"].split("Task:")[-1].strip(), "",
                  f"[完整输入]({ROOT / 'runs/scoring' / sid / 'input.json'}) · [原始评分]({ROOT / 'runs/scoring' / sid / 'judgement.json'})", "",
                  "| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for step, labels, reason in matrices[sid].values():
            lines.append("| " + " | ".join([str(step), *labels, reason.replace('|','\\|').replace('\n',' ')])+" |")
        lines.append("")
    (ROOT / "review/SEMANTIC_SAMPLE_RESULTS.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"label_counts", "by_official_outcome"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
