# Three-task mini-SWE-agent patch-generation smoke test

## Scope

This run used mini-SWE-agent 2.4.6 (source commit `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`) with the local `/root/autodl-tmp/models/Qwen3-8B` checkpoint served by vLLM 0.10.2. It generated patches in local Git worktrees without Docker. No official SWE-bench evaluation was run on this server.

Dataset snapshot SHA-256: `d3f6b8890aa5bcbd3f300447adaea5e89ca196be42138ba7332420e1fc10f00e`

## Results

| Instance | Base commit | mini exit status | Submitted patch |
| --- | --- | --- | --- |
| `marshmallow-code__marshmallow-1343` | `2be2d83a1a9a6d3d9b85804f3ab545cecc409bb0` | `LimitsExceeded` | empty |
| `marshmallow-code__marshmallow-1359` | `b40a0f4e33823e6d0f341f7e8684e359a99060d1` | `LimitsExceeded` | empty |
| `pvlib__pvlib-python-1072` | `04a523fafbd61bc2e49420963b84ed8e2bd1b3cf` | `Submitted` | 730 bytes |

The pvlib submission is a one-file Git diff for `pvlib/temperature.py`. It passes `git apply --check` against the exact base commit. This is only a patch-integrity check, not a correctness score.

## Environment findings

- The patch-generation chain works: mini-SWE-agent can call LiteLLM, the local vLLM OpenAI-compatible endpoint, Qwen3-8B, and shell commands in a task worktree.
- Docker is not required for generating patches. The official mini-SWE-agent SWE-bench batch configuration uses Docker task images by default, but this run replaced that layer with local worktrees and isolated Python environments.
- The local task Python environments are not faithful SWE-bench grading environments. In particular, the pvlib run installed current NumPy/Pandas/SciPy versions and encountered compatibility problems unrelated to the target task. Therefore these environments should not be used to claim official pass/fail results.
- The first two records intentionally contain empty `model_patch` values because the agent never executed the required submission command. Unsubmitted worktree diffs were not silently promoted into predictions.

## Output files

- `predictions.jsonl`: three scorer-style JSONL records.
- `preds.json`: the same three records in mini-SWE-agent's native keyed JSON format.
- `outputs/*.submitted.patch`: exact submitted patch per instance; empty files represent empty submissions.
- `trajectories/*.traj.json`: complete agent trajectories.
- `logs/*.log`: console logs.
- `metadata/task_statuses.json`: compact exit-status summary.
- `metadata/marshmallow-code__marshmallow-1359.unsubmitted-worktree.patch`: archived failed worktree diff; it is diagnostic only and is not a prediction.

Runtime worktrees are intentionally excluded from the parent repository. The failed `marshmallow-code__marshmallow-1359` source tree remains on disk for inspection, but is not tracked as a nested Git repository.

The prediction files contain generated answers only. They contain no score. Move `predictions.jsonl` to a machine with a compatible SWE-bench grading environment to evaluate it.
