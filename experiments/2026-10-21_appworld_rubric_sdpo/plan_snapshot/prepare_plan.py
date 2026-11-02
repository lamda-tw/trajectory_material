"""Build or verify a deterministic diagnostic sample using local files only.

No model imports, network requests, environment replay, inference, or training.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
SOURCE = WORKSPACE / "experiments/2026-10-16_appworld_rubric_selection_ablation"
SEED = "20261021:rubric_sdpo_A:v1"
STRATA = ("semantic", "execution", "recovery", "protocol_only")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stratum(row):
    fails = {i + 1 for i, label in enumerate(row["labels"]) if label == "F"}
    if fails & {2, 3, 4, 5, 7}:
        return "semantic"
    if 1 in fails:
        return "execution"
    if 6 in fails:
        return "recovery"
    if 8 in fails:
        return "protocol_only"
    if row["P"] >= 3 and row["U"] == 0:
        return "good_control"
    return "uncertain"


def read_candidates():
    inventory_path = SOURCE / "data/step_inventory.jsonl"
    rows = [json.loads(line) for line in inventory_path.read_text().splitlines()]
    label_rows = list(csv.DictReader((SOURCE / "references/step_labels.csv").open()))
    labels = {(r["id"], int(r["step"])): r for r in label_rows}
    assert len(rows) == len(labels) == 11254
    by_source = collections.defaultdict(list)
    for row in rows:
        old = labels[(row["trajectory_id"], row["step"])]
        assert row["labels"] == "".join(old[f"R{i}"] for i in range(1, 9))
        assert all(row[k] == row["labels"].count(k) for k in ("P", "F", "U"))
        by_source[row["source"]].append(row)
    for source, selected_rows in sorted(by_source.items()):
        raw = Path(source).read_bytes()
        trajectory = json.loads(raw)
        source_hash = hashlib.sha256(raw).hexdigest()
        for row in selected_rows:
            step = trajectory["steps"][row["step"] - 1]
            assert step["step"] == row["step"]
            assert len(step["prompt_ids"]) == row["prompt_tokens"]
            assert len(step["response_ids"]) == row["response_tokens"]
            row.update(
                family=row["task_id"].split("_")[0],
                stratum=stratum(row),
                prompt_ids_sha256=digest(step["prompt_ids"]),
                original_response_ids_sha256=digest(step["response_ids"]),
                original_text_sha256=hashlib.sha256(step["text"].encode()).hexdigest(),
                source_sha256=source_hash,
                history_band=("short" if row["prompt_tokens"] <= 4096 else
                              "medium" if row["prompt_tokens"] <= 8192 else "long"),
            )
    return rows


def choose_fail(rows, count_per_stratum, panel, used_prefixes, used_trajectories,
                task_cap, family_cap):
    chosen = []
    task_counts, family_counts, band_counts = (collections.Counter() for _ in range(3))
    for round_index in range(count_per_stratum):
        # Rotate the first stratum to avoid giving one category permanent priority.
        order = STRATA[round_index % 4:] + STRATA[:round_index % 4]
        for group in order:
            candidates = [r for r in rows if r["stratum"] == group
                          and r["prompt_ids_sha256"] not in used_prefixes
                          and r["trajectory_id"] not in used_trajectories
                          and task_counts[r["task_id"]] < task_cap
                          and family_counts[r["family"]] < family_cap]
            if not candidates:
                raise RuntimeError(f"Cannot fill {panel}/{group}; no silent quota relaxation")
            row = min(candidates, key=lambda r: (
                task_counts[r["task_id"]], family_counts[r["family"]],
                band_counts[(group, r["history_band"])],
                digest([SEED, panel, r["id"]]),
            ))
            chosen.append(dict(row, panel=panel))
            used_prefixes.add(row["prompt_ids_sha256"])
            used_trajectories.add(row["trajectory_id"])
            task_counts[row["task_id"]] += 1
            family_counts[row["family"]] += 1
            band_counts[(group, row["history_band"])] += 1
    return chosen


def choose_controls(rows, used_prefixes, used_trajectories):
    chosen = []
    for family in sorted({r["family"] for r in rows}):
        candidates = [r for r in rows if r["family"] == family
                      and r["stratum"] == "good_control"
                      and r["prompt_ids_sha256"] not in used_prefixes
                      and r["trajectory_id"] not in used_trajectories]
        if not candidates:
            raise RuntimeError(f"No independent good control for {family}")
        row = min(candidates, key=lambda r: digest([SEED, "good_control", r["id"]]))
        chosen.append(dict(row, panel="formal_good"))
        used_prefixes.add(row["prompt_ids_sha256"])
        used_trajectories.add(row["trajectory_id"])
    return chosen


FIELDS = ["panel", "public_state_id", "id", "task_id", "family", "trajectory_id",
          "step", "stratum", "labels", "P", "F", "U", "history_band",
          "prompt_tokens", "response_tokens", "source", "source_sha256",
          "prompt_ids_sha256", "original_response_ids_sha256", "original_text_sha256"]


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue()


def summary(rows):
    return {"states": len(rows), "tasks": len({r["task_id"] for r in rows}),
            "families": len({r["family"] for r in rows}),
            "trajectories": len({r["trajectory_id"] for r in rows}),
            "strata": dict(sorted(collections.Counter(r["stratum"] for r in rows).items())),
            "history_bands": dict(sorted(collections.Counter(r["history_band"] for r in rows).items())),
            "max_states_per_task": max(collections.Counter(r["task_id"] for r in rows).values()),
            "max_states_per_family": max(collections.Counter(r["family"] for r in rows).values())}


def build():
    rows = read_candidates()
    used_prefixes, used_trajectories = set(), set()
    formal_fail = choose_fail(rows, 25, "formal_fail", used_prefixes, used_trajectories, 2, 4)
    formal_good = choose_controls(rows, used_prefixes, used_trajectories)
    calibration = choose_fail(rows, 2, "calibration_fail", used_prefixes, used_trajectories, 1, 2)
    for row in formal_fail + formal_good + calibration:
        row["public_state_id"] = "state_" + digest([SEED, row["id"]])[:16]
    all_selected = formal_fail + formal_good + calibration
    assert len(all_selected) == len({r["prompt_ids_sha256"] for r in all_selected}) == 138
    assert len({r["trajectory_id"] for r in all_selected}) == 138
    artifacts = {
        "states_selected.csv": csv_text(formal_fail + formal_good),
        "calibration_states.csv": csv_text(calibration),
    }
    counts = collections.Counter(r["stratum"] for r in rows)
    audit = {
        "status": "cpu_index_only_no_replay_no_inference_no_scoring_no_training",
        "sampling_seed": SEED,
        "source_steps": len(rows), "source_trajectories": 540, "source_tasks": 90,
        "candidate_strata": dict(sorted(counts.items())),
        "f0_p_histogram": dict(sorted(collections.Counter(r["P"] for r in rows if r["F"] == 0).items())),
        "formal_fail": summary(formal_fail), "formal_good": summary(formal_good),
        "calibration": summary(calibration),
        "global_unique_prefixes": len(used_prefixes),
        "global_unique_trajectories": len(used_trajectories),
        "quota_relaxations": [],
        "source_files": {str(p.relative_to(WORKSPACE)): file_sha(p) for p in [
            SOURCE / "data/step_inventory.jsonl", SOURCE / "references/step_labels.csv",
            SOURCE / "config/scoring_prompt_v6_en_format.txt", SOURCE / "config/agent_prompt.txt",
        ]},
        "selection_artifact_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in artifacts.items()},
        "excluded_information": ["official_success", "future_outcome", "new_model_output", "new_judge_output"],
        "dedup_note": "Exact saved prompt-token identity; not a claim of complete hidden-state equivalence.",
    }
    artifacts["selection_audit.json"] = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return artifacts, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true", help="Write only absent or byte-identical local plan artifacts")
    modes.add_argument("--check", action="store_true", help="Rebuild in memory and compare with saved artifacts")
    args = parser.parse_args()
    artifacts, audit = build()
    for name, value in artifacts.items():
        path = ROOT / name
        if path.exists():
            if path.read_bytes() != value.encode():
                raise RuntimeError(f"Existing artifact differs: {path}; inspect instead of overwriting")
        elif args.check:
            raise FileNotFoundError(path)
    if args.write:
        for name, value in artifacts.items():
            path = ROOT / name
            if not path.exists():
                path.write_text(value)
    print(json.dumps({k: audit[k] for k in ["status", "candidate_strata", "formal_fail", "formal_good", "calibration"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
