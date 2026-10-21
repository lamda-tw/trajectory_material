"""Post-run audit of saved artifacts; no model/API/evaluator calls or outcome replacement."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import csv, hashlib, json, statistics as st

R = Path(__file__).resolve().parents[1]

def read(p):
    return json.loads(p.read_text())

def rows(name):
    return list(csv.DictReader((R / 'analysis' / name).open()))

def sha(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def dump(name, value):
    (R / 'analysis' / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    gate = read(R / 'config/calibration_accepted.json')
    for p, digest in gate['frozen_files'].items():
        assert hashlib.sha256((R / p).read_bytes()).hexdigest() == digest, p
    behavior = rows('behavior_rows.csv')
    continuation = rows('continuation_common_rows.csv')
    assert len(behavior) == 1152 and len({r['state_id'] for r in behavior}) == 128
    assert len(continuation) == 1080
    by_source = defaultdict(list)
    for r in continuation:
        by_source[r['source']].append(r)
    assert len(by_source) == 540
    context = defaultdict(list)
    count = 0
    for path, rr in by_source.items():
        d = read(Path(path))
        assert all(d[k] for k in ('first_action_replay_exact', 'all_observations_exact', 'environment_supported'))
        assert d['performed_followup_steps'] == len(d['followup_steps']) <= 12
        count += len(d['followup_steps'])
        for r in rr:
            ep = R / 'results/evaluators/continuation' / r['receiver'] / d['job']['first_model'] / (r['state_id'].replace(':', '__') + '.h' + r['horizon'] + '.json')
            ev = read(ep)
            assert ev['source_replay'] == path and ev['state_id'] == r['state_id']
            assert abs(ev['num_passes'] / ev['num_tests'] - float(r['pass_fraction'])) < 1e-12
            assert bool(ev['success']) == bool(int(r['task_success']))
        h12 = next(r for r in rr if r['horizon'] == '12')
        for step in d['followup_steps']:
            assert step['receiver_sha256'] == d['job']['receiver_sha256'] and step['physical_gpu'] == 1
            k = (d['job']['receiver'], step['receiver_sha256'], sha(step['prompt_ids']), step['sampling_seed'])
            context[k].append(dict(state_id=d['state_id'], first_model=d['job']['first_model'],
                followup_step=step['followup_step'], sampling_context_sha256=step['sampling_context_sha256'],
                response_sha256=sha(step['response_ids']), text_sha256=sha(step['text']),
                code_sha256=sha(step['code']), h12_pass_fraction=float(h12['pass_fraction']), source=path))
    assert count == 5145
    duplicate = [(k, v) for k, v in context.items() if len(v) > 1]
    divergent = [(k, v) for k, v in duplicate if len({x['response_sha256'] for x in v}) > 1]
    first_duplicate = [(k, [x for x in v if x['followup_step'] == 1]) for k, v in duplicate]
    first_duplicate = [(k, v) for k, v in first_duplicate if len(v) > 1]
    first_divergent = [(k, v) for k, v in first_duplicate if len({x['response_sha256'] for x in v}) > 1]
    affected = sorted({x['state_id'] for _, v in divergent for x in v})
    audit_context = dict(
        definition='Same receiver identity and adapter SHA256, exact prompt token IDs, sampling seed, frozen temperature=0 and generation configuration. Observational duplicate-context audit, not a new repeat experiment.',
        all_calls=count, unique_contexts=len(context), duplicate_context_clusters=len(duplicate),
        divergent_response_clusters=len(divergent),
        divergent_text_clusters=sum(len({x['text_sha256'] for x in v}) > 1 for _, v in divergent),
        divergent_code_clusters=sum(len({x['code_sha256'] for x in v}) > 1 for _, v in divergent),
        first_followup_duplicate_clusters=len(first_duplicate), first_followup_divergent_clusters=len(first_divergent),
        affected_states=affected,
        affected_branches=len({x['source'] for _, v in divergent for x in v}),
        divergent_clusters=[dict(receiver=k[0], receiver_sha256=k[1], prompt_ids_sha256=k[2], sampling_seed=k[3], members=v) for k, v in divergent],
        interpretation='Fixed seed and greedy decoding did not ensure token-level identical output for all repeated inputs. Underlying cause not identified; no saved output changed or resampled. Counts are among observed repeated contexts and are not an estimate of all-run noise probability.')
    dump('continuation_reproducibility_audit.json', audit_context)
    core = [r for r in continuation if r['horizon'] == '12' and r['panel'] == 'core']
    assert len(core) == 486 and len({r['state_id'] for r in core}) == 18
    assert set(Counter(r['state_id'] for r in core).values()) == {27}
    def group_summary(rr):
        result = {}
        for g in ('random', 'net3', 'zerofail3'):
            x = [r for r in rr if r['group'] == g]
            result[g] = dict(n=len(x), mean_pass_fraction=st.mean(float(r['pass_fraction']) for r in x),
                             goal_completions=sum(int(r['task_success']) for r in x))
        result['zerofail3_minus_random_pp'] = 100 * (result['zerofail3']['mean_pass_fraction'] - result['random']['mean_pass_fraction'])
        result['zerofail3_minus_net3_pp'] = 100 * (result['zerofail3']['mean_pass_fraction'] - result['net3']['mean_pass_fraction'])
        return result
    state_deltas = []
    for sid in sorted({r['state_id'] for r in core}):
        s = group_summary([r for r in core if r['state_id'] == sid])
        state_deltas.append(dict(state_id=sid, **s))
    sensitivity = {}
    for label, ids in [('exclude_observed_divergent_context_states', set(affected)),
                       ('exclude_d4e9306', {r['state_id'] for r in core if r['family'] == 'd4e9306'})]:
        selected = [r for r in core if r['state_id'] not in ids]
        sensitivity[label] = dict(note='Post-hoc descriptive state-equal mean, with three first-policy seeds and three receivers equally weighted. Different state/source/stage composition from the frozen primary estimand; not an unbiased noise correction.',
            remaining_states=len({r['state_id'] for r in selected}), excluded_states=sorted(ids), result=group_summary(selected))
    audit = dict(checked_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), frozen_files_verified=len(gate['frozen_files']),
        action_rows=len(behavior), continuation_readout_rows=len(continuation),
        complete_branches=len(by_source), evaluated_readouts_verified=len(continuation),
        all_replay_flags_true=True, followup_generations=count, physical_gpu=1,
        core_h12=group_summary(core), core_state_deltas=state_deltas,
        posthoc_sensitivity=sensitivity,
        reproducibility_audit='continuation_reproducibility_audit.json',
        status='saved_data_integrity_passed_with_declared_generation_reproducibility_limitation')
    dump('FINAL_AUDIT.json', audit)
    print(json.dumps({k: v for k, v in audit.items() if k != 'core_state_deltas'}, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in audit_context.items() if k != 'divergent_clusters'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
