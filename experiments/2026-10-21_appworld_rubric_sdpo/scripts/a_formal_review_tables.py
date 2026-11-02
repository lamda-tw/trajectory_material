"""Post-run descriptive audit; never changes frozen inputs, labels, or training state."""
import collections
import csv
import hashlib
import json
import statistics
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / 'phase_a/analysis/formal'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = list(csv.DictReader((OUT / 'candidate_metrics.csv').open()))
    index = read(R / 'phase_a/config/formal_blind_index.json')
    byid = {r['id']: r for r in rows}
    bystate = collections.defaultdict(list)
    checks = collections.Counter()
    attempts = collections.Counter()
    errors = []
    supplementary = []
    for x in index:
        bystate[x['state_id']].append(x)
        public = read(R / x['judge_input'])
        ex = read(R / x['execution'])
        g = read(R / x['generation'])
        m = read(R / 'phase_a/judging/candidate_formal' / x['id'] / 'base/metadata.json')
        assert sha(R / x['judge_input']) == x['judge_input_sha256']
        assert sha(R / x['generation']) == x['generation_sha256']
        assert x['execution_valid'] and ex['all_observations_exact'] and ex['environment_supported']
        assert m['status'] == 'valid'
        assert public['steps'][-1]['id'] == x['target_step']
        assert len(public['steps']) == x['target_step']
        checks['valid_inputs_and_executions'] += 1
        attempts['logical_requests'] += 1
        attempts['cli_attempts'] += len(m['attempts'])
        for a in m['attempts']:
            attempts['status_' + a['status']] += 1
            attempts['kind_' + a['kind']] += 1
            if a.get('audit', {}).get('tool_items'):
                errors.append({'id': x['id'], 'reason': 'tool_items'})
        target = public['steps'][-1]
        previous_docs = '\n'.join(public['reference_api_docs']) + '\n' + '\n'.join(t['observation'] for t in public['steps'][:-1])
        doc_calls = []
        for a in ex['candidate']['local_api_responses']:
            if a['app_name'] == 'api_docs':
                args = a['arguments']
                if isinstance(args, dict) and set(args) == {'dict'}:
                    args = dict(args['dict'])
                # Literal prior specification evidence is conservative: not a progress score.
                name = args.get('api_name') if isinstance(args, dict) else None
                prior_spec = bool(name and any(
                    ('"api_name": "' + name + '"') in obs and
                    ('"app_name": "' + args.get('app_name', '') + '"') in obs
                    for obs in public['reference_api_docs'] + [t['observation'] for t in public['steps'][:-1]]))
                doc_calls.append({'api': a['api_name'], 'arguments': args, 'spec_name_seen_in_prior_observations_or_reference': prior_spec})
        r = byid[x['id']]
        supplementary.append({
            'id': x['id'], 'state_id': x['state_id'], 'arm': x['arm'], 'panel': r['panel'],
            'stratum': r['stratum'], 'LR': int(r['LR']), 'documentation_requests': doc_calls,
            'any_doc_spec_previously_seen': any(a['spec_name_seen_in_prior_observations_or_reference'] for a in doc_calls),
            'doc_only': bool(doc_calls) and all(a['app_name'] == 'api_docs' for a in ex['candidate']['local_api_responses']),
            'feedback_revealed_in_commentary': any(w in target['commentary'].lower() for w in ['feedback', 'reviewer', 'diagnosis', 'failed rule']),
            'length_termination': g['finish_reason'] == 'length',
        })
    gate = read(R / 'phase_a/config/calibration_execution_gate.json')
    frozen = gate['frozen_execution_files']
    frozen_checks = {name: sha(R / name) == digest for name, digest in frozen.items()}
    assert all(frozen_checks.values()), frozen_checks
    counts = collections.Counter((r['panel'], r['arm']) for r in rows)
    aggregates = []
    for panel, arm in sorted(counts):
        rr = [r for r in rows if r['panel'] == panel and r['arm'] == arm]
        ss = [s for s in supplementary if s['panel'] == panel and s['arm'] == arm]
        metrics = ['LR', 'strict_LR', 'executable_no_F', 'old_F_to_U', 'any_U', 'execution_error', 'exact_code_repeat', 'completion_api', 'db_changed', 'length_termination', 'any_new_F']
        aggregates.append({'panel': panel, 'arm': arm, 'n': len(rr),
            **{k: sum(float(r[k]) for r in rr) for k in metrics},
            'per_rule_F': {f'R{i+1}': sum(r['labels_v7'][i] == 'F' for r in rr) for i in range(8)},
            **{k: sum(s[k] for s in ss) for k in ['doc_only', 'any_doc_spec_previously_seen', 'feedback_revealed_in_commentary']},
            'LR_doc_only': sum(s['LR'] and s['doc_only'] for s in ss),
            'LR_prior_doc_spec': sum(s['LR'] and s['any_doc_spec_previously_seen'] for s in ss)})
    paired = []
    for a, b in [('C2_feedback', 'C0_original'), ('C2_feedback', 'C1_fail_labels'), ('C3_feedback_and_original_answer', 'C2_feedback')]:
        deltas = []
        for sid, items in bystate.items():
            if byid[items[0]['id']]['panel'] != 'formal_fail':
                continue
            means = {arm: statistics.mean(int(byid[x['id']]['LR']) for x in items if x['arm'] == arm) for arm in [a, b]}
            deltas.append(means[a] - means[b])
        paired.append({'arm': a, 'baseline': b, 'better': sum(d > 0 for d in deltas), 'tie': sum(d == 0 for d in deltas), 'worse': sum(d < 0 for d in deltas)})
    diags = [read(p) for p in sorted((R / 'phase_a/diagnostics/formal').glob('state*.json'))]
    ds = {'states': len(diags), 'all_no_grad': all(d['no_grad'] for d in diags), 'parameter_updates': sum(d['parameter_updates'] for d in diags),
          'self_KL_max_abs': max(d['self_reverse_KL_max_abs'] for d in diags), 'all_token_alignment_verified': all(d['text_token_alignment_verified'] for d in diags),
          'vllm_logprob_mae_mean': statistics.mean(d['original_vllm_logprob_mean_abs_difference'] for d in diags),
          'vllm_logprob_mae_max': max(d['original_vllm_logprob_mean_abs_difference'] for d in diags),
          'student_top100_mass_min': min(d['student_top100_mass'] for d in diags),
          'student_tail_mass_max': max(d['student_tail_mass'] for d in diags), 'arms': {}}
    span_rows = []
    for d in diags:
        for s in d['error_expression_spans']:
            span_rows.append({'state_id': d['state_id'], **s})
    for a in diags[0]['arms']:
        values = [d['arms'][a] for d in diags]
        ds['arms'][a] = {k: {'mean': statistics.mean(v[k] for v in values), 'median': statistics.median(v[k] for v in values), 'min': min(v[k] for v in values), 'max': max(v[k] for v in values)}
                           for k in ['mean_logprob_delta_vs_C0', 'reverse_KL_student_to_conditioned_full_vocab', 'reverse_KL_top100_plus_tail']}
        ds['arms'][a]['original_answer_logprob_increased_states'] = sum(v['mean_logprob_delta_vs_C0'] > 0 for v in values)
        ds['arms'][a]['span_deltas'] = {'n': len(span_rows), 'negative': sum(s['delta_by_arm'][a] < 0 for s in span_rows), 'positive': sum(s['delta_by_arm'][a] > 0 for s in span_rows), 'mean': statistics.mean(s['delta_by_arm'][a] for s in span_rows) if span_rows else None}
    result = {'integrity': dict(checks), 'frozen_execution_files': frozen_checks, 'judge_attempts': dict(attempts), 'audit_errors': errors,
              'raw_counts': aggregates, 'state_paired_direction': paired, 'distribution': ds, 'error_expression_spans': span_rows,
              'scope': 'Post-run descriptive diagnostics. Does not change preregistered labels or metrics. Documentation matches are heuristic, not progress labels.'}
    (OUT / 'supplementary_analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'candidate_behavior_diagnostics.json').write_text(json.dumps(supplementary, ensure_ascii=False, indent=2) + '\n')
    audit = list(csv.DictReader((R / 'phase_a/config/manual_audit_states.csv').open()))
    for stratum in sorted({r['stratum'] for r in audit}):
        packet = []
        for state in (r for r in audit if r['stratum'] == stratum):
            sid = state['public_state_id']
            if sid not in bystate:
                packet.append({'state_id': sid, 'ineligible_not_replaced': True}); continue
            ready = read(R / 'phase_a/ready' / (sid + '.json'))
            source = read(R / ready['state']['input'])
            original = next(s for s in source['steps'] if s['id'] == ready['state']['target_step'])
            item = {'state_id': sid, 'task': source['task'].split('Task:')[-1].strip(), 'source_labels': ready['source_labels_v7'],
                    'feedback': ready['feedback'], 'original': original, 'candidates': []}
            item['original']['observation'] = item['original']['observation'][:800]
            for x in sorted(bystate[sid], key=lambda x: (x['arm'], x['repeat'])):
                pub = read(R / x['judge_input']); t = pub['steps'][-1]; r = byid[x['id']]
                behavior = next(s for s in supplementary if s['id'] == x['id'])
                item['candidates'].append({'id': x['id'], 'arm': x['arm'], 'repeat': x['repeat'], 'labels': r['labels_v7'], 'LR': int(r['LR']), 'reason': r['reason'],
                                           'commentary': t['commentary'], 'code': t['code'], 'observation_excerpt': t['observation'][:900],
                                           'doc_requests': behavior['documentation_requests']})
            packet.append(item)
        (OUT / ('review_packet_' + stratum + '.json')).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
