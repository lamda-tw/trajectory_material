"""CPU-only feasibility audit. Does not select training data or launch jobs."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT = ROOT / "experiments/2026-10-16_appworld_rubric_selection_ablation"
LABELS = EXPERIMENT / "references/step_labels.csv"
PROMPT = EXPERIMENT / "config/scoring_prompt_v6_en_format.txt"
EXPECTED_PROMPT_SHA = "df4e8fb406551f2d90e38bbe83838db181bda18e01d947b236ee10a05c633109"
PRIMARY_SAMPLE_COUNT = 1358
TRAINING_SEEDS = [20261015, 20261016, 20261017]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_sha(keys):
    return hashlib.sha256(("\n".join(sorted(keys)) + "\n").encode()).hexdigest()


def main():
    assert sha(PROMPT) == EXPECTED_PROMPT_SHA
    with LABELS.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels = {f"{r['id']}:{r['step']}": tuple(r[f"R{i}"] for i in range(1, 9)) for r in rows}
    assert len(labels) == len(rows) == 11254
    assert all(set(v) <= set("PFUN") for v in labels.values())
    baseline = {k for k, v in labels.items() if v.count("P") >= 3 and "F" not in v}
    assert len(baseline) == 1710

    def pool(omit, remove_pass=False):
        return {
            key for key, values in labels.items()
            if sum(value == "P" for i, value in enumerate(values)
                   if not remove_pass or i not in omit) >= 3
            and all(value != "F" for i, value in enumerate(values) if i not in omit)
        }

    def describe(keys):
        added = keys - baseline
        return {
            "candidate_count": len(keys),
            "baseline_retained": len(keys & baseline),
            "added_vs_baseline": len(added),
            "removed_vs_baseline": len(baseline - keys),
            "same_ids_as_baseline": keys == baseline,
            "step_id_set_sha256": set_sha(keys),
            "expected_added_at_1358_uniform_draw": (
                PRIMARY_SAMPLE_COUNT * len(added) / len(keys)
                if len(keys) >= PRIMARY_SAMPLE_COUNT else None
            ),
            "feasible_at_1358_without_replacement": len(keys) >= PRIMARY_SAMPLE_COUNT,
            "expected_added_at_1710_uniform_draw": (
                1710 * len(added) / len(keys) if len(keys) >= 1710 else None
            ),
            "feasible_at_1710_without_replacement": len(keys) >= 1710,
        }

    dimensions = []
    for i in range(8):
        counts = Counter(labels[key][i] for key in baseline)
        remove_pass_only = {
            key for key in baseline
            if labels[key].count("P") - (labels[key][i] == "P") >= 3
        }
        dimensions.append({
            "dimension": f"R{i + 1}",
            "baseline_labels": {label: counts[label] for label in "PFUN"},
            "baseline_pass_percent": 100 * counts["P"] / len(baseline),
            "P_decisive_for_baseline_eligibility": len(baseline - remove_pass_only),
            "remove_P_only_keep_all_F_vetoes": describe(remove_pass_only),
            "relax_F_only": describe(pool({i})),
            "remove_dimension_from_P_and_F": describe(pool({i}, remove_pass=True)),
            "standalone_P_candidate_count": sum(values[i] == "P" for values in labels.values()),
        })
    relaxed_6 = pool({5})
    relaxed_8 = pool({7})
    relaxed_both = pool({5, 7})
    main_pools = {f"drop_r{i + 1}": pool({i}, remove_pass=True) for i in range(8)}
    aliases = {"drop_r7": "drop_r5"}
    assert all(len(keys) >= PRIMARY_SAMPLE_COUNT for keys in main_pools.values())
    assert all(main_pools[alias] == main_pools[source] for alias, source in aliases.items())
    assert main_pools["drop_r5"] == baseline
    actual_runs = (len(main_pools) - len(aliases)) * len(TRAINING_SEEDS)
    updates = PRIMARY_SAMPLE_COUNT // 2
    assert PRIMARY_SAMPLE_COUNT % 2 == 0
    report = {
        "status": "cpu_candidate_audit_only_script_does_not_launch_jobs",
        "source": str(LABELS.relative_to(ROOT)),
        "source_sha256": sha(LABELS),
        "scoring_prompt_sha256": sha(PROMPT),
        "source_rows": len(rows),
        "source_trajectories": len({r['id'] for r in rows}),
        "source_tasks": len({r['task_id'] for r in rows}),
        "predicates": {
            "baseline": "P over all 8 dimensions >= 3; no F in any dimension",
            "complete_removal_primary": "P over remaining 7 dimensions >= 3; no F in remaining 7 dimensions",
            "relax_F_only_extension": "original P >= 3; F veto retained outside omitted dimensions",
            "remove_P_only_extension": "P over remaining 7 dimensions >= 3; no F in any dimension",
            "random": "all source steps, no score predicate",
            "U_and_N": "unchanged; neither contributes P nor F",
        },
        "primary_experiment": {
            "status": "execution_authorized_see_experiment_status",
            "execution_status_source": "experiments/2026-10-18_appworld_rubric_dimension_ablation/STATUS_ALL.json",
            "gpu": "physical GPU1: seeds 20261015/20261016; physical GPU0: seed 20261017",
            "seeds": TRAINING_SEEDS,
            "samples_per_run": PRIMARY_SAMPLE_COUNT,
            "epochs": 1,
            "gradient_accumulation_steps": 2,
            "updates_per_run": updates,
            "sampling": "global uniform without replacement; only score predicates; no extra filters",
            "excluded_training_arms": ["zerofail3", "random"],
            "comparison_reference": "drop_r5: its candidate ID set equals the full eight-rubric pool; no extra baseline run",
            "reuse_policy": "drop_r7 reuses same-seed NEW drop_r5 selection/order/model/evaluation; never old 1710-step adapters",
            "report_groups": len(main_pools),
            "condition_seed_records": len(main_pools) * len(TRAINING_SEEDS),
            "distinct_recipes": len(main_pools) - len(aliases),
            "actual_training_runs": actual_runs,
            "total_updates": actual_runs * updates,
            "dev57_task_rollouts": actual_runs * 57,
            "same_state_models_including_raw_base": actual_runs + 1,
            "same_state_generation_calls_at_256_states": (actual_runs + 1) * 256,
            "arms": {
                arm: {
                    "candidate_count": len(keys),
                    "candidate_id_set_sha256": set_sha(keys),
                    "alias_of": aliases.get(arm),
                    "new_training_runs": 0 if arm in aliases else len(TRAINING_SEEDS),
                }
                for arm, keys in main_pools.items()
            },
        },
        "baseline": describe(baseline),
        "baseline_P_count_distribution": dict(sorted(Counter(
            labels[key].count("P") for key in baseline
        ).items())),
        "baseline_steps_with_U": sum("U" in labels[key] for key in baseline),
        "baseline_P_combinations": [
            {"P_dimensions": list(dims), "steps": count}
            for dims, count in sorted(Counter(
                tuple(f"R{i + 1}" for i, label in enumerate(labels[key]) if label == "P")
                for key in baseline
            ).items(), key=lambda pair: (-pair[1], pair[0]))
        ],
        "per_dimension": dimensions,
        "relax_R6_R8": describe(relaxed_both),
        "additional_only_when_both_relaxed": len(relaxed_both - relaxed_6 - relaxed_8),
    }
    output = HERE / "candidate_counts.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
