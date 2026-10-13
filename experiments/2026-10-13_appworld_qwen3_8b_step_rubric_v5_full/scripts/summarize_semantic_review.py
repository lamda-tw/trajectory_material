"""Summarize the primary assistant's complete-trajectory evidence review.

This is not an independent gold-label evaluation. Never modify judge outputs.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    plan = read(ROOT / "review/semantic_sample_plan.json")
    review = read(ROOT / "review/manual_review.json")
    covered = {c["id"]: c for c in review["coverage"]}
    assert set(covered) == set(plan["ids"])
    labels, counts, per_rubric = {}, Counter(), defaultdict(Counter)
    for sid in plan["ids"]:
        result = read(ROOT / "runs/scoring" / sid / "judgement.json")
        expected_steps = [s[0] for s in result["steps"]]
        assert covered[sid]["steps_reviewed"] == expected_steps
        for step, codes, reason in result["steps"]:
            for i, code in enumerate(codes, 1):
                labels[sid, step, f"R{i}"] = code
                counts[code] += 1
                per_rubric[f"R{i}"][code] += 1
    findings = review["findings"]
    keys = [(f["id"], f["step"], f["rubric"]) for f in findings]
    assert len(set(keys)) == len(keys), "Repeated cell findings"
    for f, key in zip(findings, keys):
        assert labels[key] == f["observed"]
        assert f["kind"] in {"clear_error", "debatable"}
        assert f["preferred"] and set(f["preferred"]) <= set("PFUN")
        assert f["observed"] not in f["preferred"]
        assert f["evidence"].strip()
    clear = [f for f in findings if f["kind"] == "clear_error"]
    debated = [f for f in findings if f["kind"] == "debatable"]
    missing_applicability = [f for f in findings if f["observed"] == "N" and any(x != "N" for x in f["preferred"])]
    denominator = sum(counts[k] for k in "PFU") + len(missing_applicability)
    rubric_stats = {}
    for rubric in sorted(per_rubric):
        own = [f for f in findings if f["rubric"] == rubric]
        rubric_stats[rubric] = {
            "observed_labels": dict(per_rubric[rubric]),
            "clear_error_cells": sum(f["kind"] == "clear_error" for f in own),
            "debatable_cells": sum(f["kind"] == "debatable" for f in own),
            "identified_N_missing_applicability": sum(f in missing_applicability for f in own),
        }
    summary = {
        "scope": "Primary assistant evidence review; purposeful stratified sample, no independent human gold. These are audit findings, not population accuracy estimates.",
        "trajectories_reviewed": len(covered),
        "steps_reviewed": sum(len(c["steps_reviewed"]) for c in covered.values()),
        "cells_reviewed": len(labels), "observed_labels": dict(counts),
        "clear_error_cells": len(clear), "debatable_cells": len(debated),
        "identified_N_missing_applicability": len(missing_applicability),
        "applicable_audit_denominator": denominator,
        "no_clear_error_fraction_applicable": (denominator-len(clear))/denominator,
        "no_clear_or_debatable_fraction_applicable": (denominator-len(findings))/denominator,
        "steps_with_clear_error": len({(f["id"], f["step"]) for f in clear}),
        "steps_with_any_label_concern": len({(f["id"], f["step"]) for f in findings}),
        "clear_errors_observed_F": sum(f["observed"] == "F" for f in clear),
        "clear_errors_missing_F": sum("F" in f["preferred"] and len(f["preferred"]) == 1 for f in clear),
        "debatable_observed_F": sum(f["observed"] == "F" for f in debated),
        "reason_findings": len(review.get("reason_findings", [])),
        "by_rubric": rubric_stats,
    }
    assert summary["steps_reviewed"] == plan["steps"]
    (ROOT / "analysis/semantic_review_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    lines = ["# 完整轨迹证据复核", "", review["method"], "",
             "本复核不修改原始评分。明确误判和有争议边界分开记录，不能将本表当独立人工金标。", ""]
    for sid in plan["ids"]:
        lines += [f"## {sid}", "", covered[sid]["note"], "",
                  f"[完整输入]({ROOT / 'runs/scoring' / sid / 'input.json'}) · [原始评分]({ROOT / 'runs/scoring' / sid / 'judgement.json'})", ""]
        own = [f for f in findings if f["id"] == sid]
        if own:
            lines += ["| step | 维度 | 原标签 | 建议 | 类型 | 证据 |", "| --- | --- | --- | --- | --- | --- |"]
            for f in own:
                lines.append("| " + " | ".join([str(f["step"]), f["rubric"], f["observed"], "/".join(f["preferred"]), f["kind"], f["evidence"].replace("|", "\\|").replace("\n", " ")]) + " |")
        else:
            lines.append("逐步复核后未记录明确标签误判或需要单列的边界争议。")
        lines.append("")
        for f in review.get("reason_findings", []):
            if f["id"] == sid:
                lines += [f"短依据问题（step {f['step']}）：{f['evidence']}", ""]
    (ROOT / "review/MANUAL_REVIEW.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
