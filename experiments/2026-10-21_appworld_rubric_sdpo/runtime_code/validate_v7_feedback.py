"""Validate v7-feedback response structure locally, not semantic correctness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def feedback_text(item):
    """The exact text whose 256-token budget is checked before teacher rendering."""
    return "Diagnosis: " + item["diagnosis"] + "\nCorrection: " + item["correction"]


def validate(payload, result, token_count=None):
    require(set(result) == {"trajectory_id", "rubric_version", "steps", "feedback_version", "feedback"}, "Unexpected top-level fields")
    require(result["trajectory_id"] == payload["trajectory_id"], "Trajectory ID mismatch")
    require(result["rubric_version"] == "appworld-step-v7", "Wrong rubric version")
    require(result["feedback_version"] == "appworld-step-v7-feedback-v1", "Wrong feedback version")
    ids = [s["id"] for s in payload["steps"]]
    require(all(type(i) is int and i > 0 for i in ids) and len(ids) == len(set(ids)), "Invalid input step IDs")
    pos = {step_id: n for n, step_id in enumerate(ids)}
    requested = payload.get("feedback_step_ids")
    if requested is None:
        requested = ids
    require(isinstance(requested, list) and all(type(i) is int for i in requested)
            and len(requested) == len(set(requested)) and set(requested) <= set(ids), "Invalid feedback_step_ids")
    require(isinstance(result["steps"], list) and len(result["steps"]) == len(ids), "Wrong score coverage")
    scores = {}
    for expected_id, row in zip(ids, result["steps"]):
        require(isinstance(row, list) and len(row) == 3, "Score row must retain three columns")
        step_id, labels, reason = row
        require(type(step_id) is int and step_id == expected_id, "Wrong step order")
        require(isinstance(labels, str) and len(labels) == 8 and set(labels) <= set("PFUN"), "Invalid labels")
        require(isinstance(reason, str) and len(reason) <= 60, "Invalid short reason")
        require(bool(reason.strip()) if ("F" in labels or "U" in labels) else reason == "", "Short reason does not match labels")
        scores[step_id] = labels
    expected = [i for i in ids if i in requested and "F" in scores[i]]
    require(isinstance(result["feedback"], list) and len(result["feedback"]) == len(expected), "Wrong feedback coverage")
    keys = {"step_id", "failed_rules", "diagnosis", "correction", "evidence_steps", "uses_later_evidence", "usable", "unusable_reason"}
    for step_id, item in zip(expected, result["feedback"]):
        require(isinstance(item, dict) and set(item) == keys, "Wrong feedback fields")
        require(type(item["step_id"]) is int and item["step_id"] == step_id, "Wrong feedback order")
        require(item["failed_rules"] == [f"R{i+1}" for i, x in enumerate(scores[step_id]) if x == "F"], "Feedback rules must match ALL F labels")
        evidence = item["evidence_steps"]
        require(isinstance(evidence, list) and evidence and all(type(i) is int for i in evidence)
                and set(evidence) <= set(ids) and evidence == sorted(set(evidence)), "Invalid evidence step IDs")
        uses_later = any(pos[i] > pos[step_id] for i in evidence)
        require(type(item["uses_later_evidence"]) is bool and item["uses_later_evidence"] == uses_later, "Incorrect later-evidence flag")
        require(all(isinstance(item[k], str) for k in ("diagnosis", "correction", "unusable_reason")), "Feedback text must be strings")
        require(bool(item["diagnosis"].strip()), "Missing diagnosis")
        require(type(item["usable"]) is bool, "usable must be boolean")
        if item["usable"]:
            require(bool(item["correction"].strip()) and item["unusable_reason"] == "", "Usable feedback needs a correction and no refusal reason")
            if token_count:
                require(token_count(feedback_text(item)) <= 256, "Feedback exceeds 256 Qwen tokens")
        else:
            require(item["correction"] == "" and bool(item["unusable_reason"].strip()), "Unusable feedback requires a reason and empty correction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("response", type=Path)
    parser.add_argument("--tokenizer-json", type=Path, help="Optional local Qwen tokenizer; no model loading")
    args = parser.parse_args()
    count = None
    if args.tokenizer_json:
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(args.tokenizer_json))
        count = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
    validate(json.loads(args.input.read_text()), json.loads(args.response.read_text()), count)
    print("PASS: structural/coverage checks; semantic quality not validated; token budget " + ("checked" if count else "NOT checked (no tokenizer supplied)"))


if __name__ == "__main__":
    main()
