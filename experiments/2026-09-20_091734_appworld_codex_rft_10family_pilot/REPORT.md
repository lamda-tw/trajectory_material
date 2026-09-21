# AppWorld Codex RFT 10-Family Pilot

## Status

Complete and audited.

This experiment sampled 10 tasks from 10 distinct families in the 90-task
`train.txt` split. Each task allowed at most 3 independent full-trajectory
attempts and stopped immediately after the first terminal reward-1 trajectory.

## Configuration

- Selection: 10 family positions evenly spaced across the 30 ordered train families.
- Instance choice: rotated across `_1`, `_2`, and `_3`.
- Policy: Codex CLI, `gpt-5.6-sol`, high reasoning effort.
- Temperature: unavailable / null.
- Attempt isolation: one new persistent Codex thread per full attempt.
- Maximum attempts per task: 3.
- Maximum AppWorld interactions per attempt: 40.
- Acceptance: official AppWorld evaluator success only.
- Stop rule: first successful trajectory per task.
- Policy context: public AppWorld ReAct prompt, public task specification,
  the attempt's own prior actions, and credential-redacted observations.
- Hidden from policy: ground truth, solution, ground-truth API traces,
  evaluator assertions, and prior teacher trajectories.
- Ground truth use: terminal evaluator reward only.

## Aggregate result

- Distinct task families: 10
- Tasks accepted: 10 / 10
- Full attempts run: 10
- First-attempt successes: 10 / 10
- Second- or third-attempt runs: 0
- Total interaction steps: 124
- Steps per attempt: mean 12.4, median 12, range 9-16
- Evaluator checks: 59 / 59 passed
- Generation errors: 0
- Successful trajectories containing an execution failure and recovery: 1 / 10
- Unique Codex threads: 10 / 10 attempts
- Codex tool-event types observed: `agent_message` only
- Forbidden shell/file/Web/MCP actions: 0

## Per-task result

| Task | Attempt accepted | Steps | Execution failures | Evaluator |
|---|---:|---:|---:|---:|
| 82e2fac_2 | 1 | 12 | 0 | 2/2 |
| 6104387_3 | 1 | 16 | 1 | 10/10 |
| 287e338_1 | 1 | 9 | 0 | 2/2 |
| b7a9ee9_2 | 1 | 12 | 0 | 4/4 |
| ce359b5_3 | 1 | 12 | 0 | 8/8 |
| 7d7fbf6_1 | 1 | 15 | 0 | 8/8 |
| 60d0b5b_2 | 1 | 10 | 0 | 7/7 |
| cf6abd2_3 | 1 | 14 | 0 | 8/8 |
| c901732_1 | 1 | 10 | 0 | 6/6 |
| aa8502b_2 | 1 | 14 | 0 | 4/4 |

## Natural failure recovery

Task `6104387_3` failed at interaction 10 because AppWorld rejected
`csv.writer`. The next policy action used the error observation to implement
CSV escaping manually, then completed the requested backup and account
termination. The final evaluator passed all 10 tests. This trajectory remains
in the accepted set because rejection is applied to the full trajectory, not
to an individual erroneous step.

## Credential boundary audit

Raw observations remain local for environment reproducibility. Before any
observation is sent to Codex, sensitive JSON fields and token-like strings are
redacted. The model-visible version is stored separately as
`policy_observation`; downstream SFT export should use that field rather than
the local raw `observation`.

- Actual credential values audited: 14 (9 password values, 5 access tokens)
- Values found in model-visible observations: 0
- Redaction markers written across model-visible observations: 68

## Codex usage

- Input tokens: 18,079,562
- Cached input tokens: 14,605,184
- Cached/input ratio: 80.78%
- Output tokens: 113,458
- Reasoning output tokens: 34,302
- Wall time across attempts: approximately 25.3 minutes

The input-token counter includes the growing persistent thread context on each
turn. Persistent threads enabled substantial prefix caching and avoided
client-side replay of the full transcript.

## Interpretation

This pilot validates the planned mechanics, but it does not estimate the retry
cap: every selected task succeeded on its first attempt, so the configured
three-attempt limit was never exercised.

It also shows that increasing the retry cap alone will not create many recovery
examples under a first-success stopping rule. Natural API/document exploration
appears in all trajectories, but only 1 of 10 accepted trajectories contains an
execution error followed by recovery. If later experiments require a larger
recovery subset, that should be designed as a separate collection phase rather
than mislabeled as the same LOOP-style RFT sample.

## Primary artifacts

- `accepted_trajectories.jsonl`: 10 accepted reward-1 trajectories.
- `attempts.jsonl`: all 10 completed attempts.
- `task_results.jsonl`: one terminal record per selected task.
- `summary.json`: task-level aggregate.
- `manifest.json`: provenance, configuration, and data boundary.
- `attempts/<task>__attempt_01/`: per-turn Codex events and full trajectory.
