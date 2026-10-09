# The rubric reward pipeline

How a trajectory becomes a scalar reward, for every setting that uses an LLM judge
(static, dynamic, and their credit variants). All of it lives in
[`src/verl_appworld/rubric_reward.py`](../src/verl_appworld/rubric_reward.py).

Read this before [CREDIT.md](CREDIT.md) — credit assignment is a stage of this pipeline,
not a separate mechanism.

## Rollout groups

GRPO samples a **group** of rollouts for the same task and normalizes advantage within
that group. Group size is 6 in all the runs here (`APPWORLD_GROUP_SIZE=6`).

The group is not just a normalization unit — it is the unit the rubric pipeline operates
on. Two stages below need every member of the group to have finished before they can run,
which is why the code has a group barrier and a barrier timeout.

## The stages

### Stage 1 — obtain candidate rubrics

Which rubrics a trajectory is scored against depends on `APPWORLD_RUBRIC_MODE`.

**Static mode** (`discriminative`): rubrics are read from a fixed JSON file, the same set
for every task and every step. No generation, no LLM call. The file used here is
[`rubrics/static_rubrics_qwen36_27b_mece.json`](../rubrics/), pointed at by
`APPWORLD_RUBRIC_STATIC_FILE`.

**Dynamic mode** (`dynamic`): the judge generates rubrics **per rollout**, from the task
prompt and — when `APPWORLD_UNION_INCLUDE_TRAJECTORIES=1`, which all the dynamic runs here
set — from that rollout's trajectory as well. Prompt:
[`rubric_prompts/generate_rubrics_from_trajectory.txt`](../src/verl_appworld/rubric_prompts/).

So in dynamic mode, stage 1 produces **six different candidate rubric sets** for a group of
six, one per member.

### Stage 2 — union the group's rubrics (dynamic mode only)

Six different rubric sets cannot be used as-is. If each member were scored only against
rubrics generated from its own trajectory, a rollout that did little would be scored
against an easy rubric set and a rollout that attempted more would be scored against a
harder one — and their advantages are about to be compared directly against each other.

The **union stage** fixes this. All members' candidate rubrics go to the judge in one call,
which merges them into a single shared set: deduplicating rubrics that say the same thing
in different words, and keeping the distinct ones. Every member of the group is then scored
against that same merged set.

- Prompt: [`rubric_prompts/union_rubrics.txt`](../src/verl_appworld/rubric_prompts/)
- Logged to: `percall_logs/group_union_calls.jsonl` — member rubrics, the full candidate
  pool, and the merged output
- This stage is **why the group barrier exists**: the union cannot run until all six
  members have produced candidates. `APPWORLD_GROUP_BARRIER_TIMEOUT_S` is the deadlock
  backstop for that wait. In the self-judge setting it is raised to 7200s, because a
  timeout would make the group fall back to scoring members individually — losing the
  shared-rubric property the whole stage exists to provide.

These are the largest LLM calls in the pipeline. A union prompt carrying six trajectories
has been measured at up to about 148,500 tokens, with the 95th percentile near 115,000.
That is why the self-judge setting asserts a minimum judge context window and refuses to
start below it: a truncated union prompt yields malformed rubric JSON rather than a call
that visibly fails.

In static mode there is no union stage — the rubric set is already shared by construction.

### Stage 3 — score each trajectory

The judge scores one trajectory against the shared rubric set, returning a verdict per
rubric:

| Verdict | Value |
|---|---|
| PASS | `+1` |
| NOT APPLICABLE | `0` |
| FAIL | `-1` |

Prompt: [`rubric_prompts/score_rubrics.txt`](../src/verl_appworld/rubric_prompts/) (the
self-judge setting uses `score_rubrics_self.txt`). Logged per call to
`percall_logs/judge_calls.jsonl`.

### Stage 3b — drop rubrics that no member failed

Before any reward is computed, the group's verdicts are pooled and a rubric is **dropped**
unless at least one member of the group actually failed it.

```
A rubric is KEPT   iff  some member scored it -1 (FAIL)
A rubric is DROPPED iff  no member failed it  (all PASS, or all N/A, or a mix of the two)
```

Implemented in `_non_discriminative_indices`, and applied in both the static path
(`compute_group_discriminative_reward`) and the dynamic union path
(`compute_group_union_reward`).

**Why.** A rubric that every member passes cannot separate a good rollout from a bad one.
GRPO learns from *differences* within the group, so such a rubric contributes no signal —
it only inflates the denominator and dilutes the rubrics that do discriminate. Dropping it
concentrates the reward on the rubrics where the group actually differed.

Two details that are easy to get wrong:

- **All-FAIL rubrics are kept.** Only the *absence of any failure* triggers a drop. A
  rubric every member failed is real signal (the whole group missed something) and stays in
  the denominator. The test is "was there at least one FAIL", not "was there a mix".
- **Dropping requires a group.** This stage needs the whole group's verdicts, so it is the
  second reason the group barrier exists. It also means the drop is a *group-level*
  operation: the same rubric may be kept for one group and dropped for another on a
  different task.

Bookkeeping goes to `judge_calls.jsonl` as one summary row per group, recording
`n_rubrics_dropped`, `dropped_rubric_indices`, and `dropped_rubric_titles`, plus the
before/after counts — so the effect of this stage is auditable per group rather than
inferred.

### Stage 4 — reward from the surviving verdicts

Over the rubrics that survived stage 3b and are applicable (verdict not `0`):

```
rubric_avg = ( sum of verdicts ) / ( number of surviving applicable rubrics )
reward     = rubric_avg * APPWORLD_RUBRIC_REWARD_SCALE          # scale default 10.0
```

`rubric_avg` therefore lies in `[-1, +1]`: `+1` if every surviving rubric passed, `-1` if
every one failed.

If the denominator is empty — every rubric was either dropped or not applicable — the
reward is `0.0`.

### Stage 5 — credit assignment (credit settings only)

For `APPWORLD_REWARD_MODE=rubric_credit`, one further judge call asks which trajectory
steps were causally responsible for each rubric outcome, and the resulting per-step
qualities redistribute the advantage across the trajectory's tokens.

Fully documented in [CREDIT.md](CREDIT.md).

## Summary by setting

| Setting | Stage 1 rubrics | Stage 2 union | Stage 3b drop | Stage 5 credit |
|---|---|---|---|---|
| sparse | — no judge at all | — | — | — |
| static | fixed file | not needed | yes | — |
| dynamic | generated per rollout | yes | yes | — |
| static + credit | fixed file | not needed | yes | yes |
| dynamic + credit | generated per rollout | yes | yes | yes |
| self-judge dynamic + credit | generated per rollout, by the policy itself | yes | yes | yes |
| Qwen2.5 dynamic + credit | generated per rollout | yes | yes | yes |

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `APPWORLD_RUBRIC_REWARD_SCALE` | `10.0` | Multiplier on `rubric_avg` |
| `APPWORLD_GROUP_SIZE` | set to `6` by the launchers | Rollouts per GRPO group |
| `APPWORLD_GROUP_BARRIER_TIMEOUT_S` | set to `1800` by the launchers | Deadlock backstop on the wait for all group members. Not a performance knob — lowering it makes groups fall back to individual scoring |
| `APPWORLD_JUDGE_REQUEST_TIMEOUT_S` | `300`, set to `7200` by the launchers for a served judge | Per-call timeout on a served judge. Must accommodate a ~148k-token union prompt |
| `APPWORLD_RUBRIC_STATIC_FILE` | — | Required in `discriminative` mode, which is what the two fixed-rubric settings use |
| `APPWORLD_UNION_INCLUDE_TRAJECTORIES` | unset, meaning off | `1` lets rubric generation see the trajectory, not only the task prompt. The launchers set it for every dynamic setting |
| `APPWORLD_RUBRIC_MAX_TOKENS` | per-stage table | One blanket output ceiling, replacing the measured per-stage values. See [SELF_JUDGE.md](SELF_JUDGE.md#output-token-ceilings) |

These are bounds and diagnostics rather than tuning knobs. Each has a working default, and none
is set by a launcher:

| Variable | Default | What it bounds |
|---|---|---|
| `APPWORLD_JUDGE_RETRY_DELAY_S` | 3 | first delay in the retry ladder after a failed judge call |
| `APPWORLD_JUDGE_RETRY_MAX_DELAY_S` | 180 | ceiling that ladder backs off to |
| `APPWORLD_STAGE3_DEADLINE_S` | 1800 | the scoring stage for one rollout, past which it raises rather than returning a reward it cannot stand behind |
| `APPWORLD_ADAPTER_DEADLINE_S` | 5400 | the wait for a served judge to publish its URL, for the self-judge settings |
| `APPWORLD_OUTAGE_DEADLINE_S` | 7200 | how long a judge endpoint may stay unreachable before the run stops waiting |
| `APPWORLD_JUDGE_OUTAGE_PROBE_S` | 60 | seconds between probes while an endpoint is unreachable |
| `APPWORLD_VAL_BARRIER_TIMEOUT_S` | 300 | the group barrier during a validation pass, which is shorter than the training one because a validation group is scored solo on timeout without affecting training |
| `APPWORLD_TRAIN_TIME_VAL` | `0` | `1` when in-run validation is on, which changes how unvalidated rows are recorded |
| `APPWORLD_LLM_PRICE_INPUT_PER_M`, `APPWORLD_LLM_PRICE_OUTPUT_PER_M` | 2.50, 15.00 | the per-million-token prices used to cost judge calls in the logs. Reporting only; no effect on training |
| `APPWORLD_POOLTRACE` | `0` | `1` prints judge thread-pool activity, for diagnosing a slow judge phase |
| `APPWORLD_JUDGE_BASE_ONLY` | `0` | `1` freezes a served judge at the base model instead of tracking the policy. A different experiment; no setting sets it |

## Where to look when a number seems wrong

| Question | File |
|---|---|
| What rubrics did this group end up with? | `percall_logs/group_union_calls.jsonl` |
| Which rubrics were dropped, and why? | `percall_logs/judge_calls.jsonl`, group summary rows |
| What verdict did each rubric get per rollout? | `percall_logs/judge_calls.jsonl` |
| What did credit assignment do? | `percall_logs/credit_calls.jsonl` |
| Did the task actually succeed, independent of the reward? | `percall_logs/shadoweval.jsonl` |

That last one matters most for interpreting results. A rubric reward can rise while task
success does not — for instance if the judge grows lenient, or if the surviving rubric set
shrinks. `shadoweval.jsonl` records AppWorld's own task-success verdict for every rollout
in every setting, and it is never fed back as reward.
