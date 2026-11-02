"""CPU-only post-hoc sensitivity and exact token evidence, no model loading."""
from a_formal_review_tables import R, OUT, read
from a_analyze import comparison
import collections, csv, hashlib, json, math, statistics
from transformers import AutoTokenizer


def main():
    rows = list(csv.DictReader((OUT / 'candidate_metrics.csv').open()))
    for r in rows:
        for k in ['LR', 'strict_LR', 'executable_no_F', 'any_new_F', 'new_F_dimension_rate']:
            r[k] = float(r[k])
    fail = [r for r in rows if r['panel'] == 'formal_fail']
    good = [r for r in rows if r['panel'] == 'formal_good']
    sensitivities = []
    for name, rr in [('exclude_protocol_only', [r for r in fail if r['stratum'] != 'protocol_only']),
                     ('no_later_evidence', [r for r in fail if r['uses_later_evidence'] == 'False'])]:
        for a, b in [('C2_feedback', 'C0_original'), ('C2_feedback', 'C1_fail_labels'), ('C3_feedback_and_original_answer', 'C2_feedback')]:
            sensitivities.append({'subset': name, **comparison(rr, a, b, 'LR')})
    sensitivities.append({'subset': 'all_FAIL_strict_LR', **comparison(fail, 'C2_feedback', 'C0_original', 'strict_LR')})
    byid = {r['id']: r for r in rows}
    groups = collections.defaultdict(list)
    for x in read(R / 'phase_a/config/formal_blind_index.json'):
        pub = read(R / x['judge_input']); pub.pop('trajectory_id')
        h = hashlib.sha256(json.dumps(pub, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        groups[h].append(x['id'])
    duplicates = [ids for ids in groups.values() if len(ids) > 1]
    disagreements = [{'ids': ids, 'labels': [byid[i]['labels_v7'] for i in ids], 'LR': [byid[i]['LR'] for i in ids]} for ids in duplicates if len({byid[i]['labels_v7'] for i in ids}) > 1]
    consistency = {'identical_public_payload_groups': len(duplicates), 'candidates_in_groups': sum(map(len, duplicates)),
                   'groups_with_any_label_disagreement': len(disagreements), 'groups_with_LR_disagreement': sum(len({byid[i]['LR'] for i in ids}) > 1 for ids in duplicates),
                   'disagreements': disagreements}
    tokenizer = AutoTokenizer.from_pretrained('/root/autodl-tmp/models/Qwen3-8B', local_files_only=True)
    spans = []
    for f in sorted((R / 'phase_a/diagnostics/formal').glob('state*.json')):
        d = read(f)
        if not d['error_expression_spans']:
            continue
        p = read(R / 'phase_a/ready' / (d['state_id'] + '.json'))
        original = read(R / p['state']['policy_input'])
        safe_source = read(R / p['state']['input'])
        target = next(x for x in safe_source['steps'] if x['id'] == p['state']['target_step'])
        offsets = tokenizer(original['original_answer'], add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
        first_code = original['original_answer'].find('```python')
        for s in d['error_expression_spans']:
            tokens = []
            for i in s['token_positions']:
                start, end = offsets[i]
                tokens.append({'position': i, 'piece': tokenizer.decode([original['original_response_ids'][i]]),
                               'in_or_after_first_python_fence': first_code >= 0 and start >= first_code,
                               'probability': {a: math.exp(v['token_logprobs'][i]) for a, v in d['arms'].items()},
                               'delta': {a: v['token_logprobs'][i] - d['arms']['C0_original']['token_logprobs'][i] for a, v in d['arms'].items()}})
            spans.append({'state_id': d['state_id'], 'expression': s['expression'], 'tokens': tokens,
                          'original_code_redacted': target['code'], 'original_observation_redacted': target['observation'],
                          'feedback': p['feedback'], 'candidates': [{k:r[k] for k in ['id', 'arm', 'repeat', 'labels_v7', 'LR']} for r in fail if r['state_id'] == d['state_id']]})
    gs = collections.defaultdict(dict)
    for r in good:
        gs[r['state_id']].setdefault(r['arm'], []).append(r['LR'])
    control = [{'state_id': sid, 'C0': statistics.mean(v['C0_original']), 'C2': statistics.mean(v['C2_feedback']),
                'difference': statistics.mean(v['C2_feedback']) - statistics.mean(v['C0_original'])} for sid,v in gs.items()]
    later = []
    for sid in sorted({r['state_id'] for r in fail if r['uses_later_evidence'] == 'True'}):
        rr = [r for r in fail if r['state_id'] == sid]
        later.append({'state_id': sid, 'LR': {a: statistics.mean(r['LR'] for r in rr if r['arm'] == a) for a in sorted({r['arm'] for r in rr})}})
    result = {'post_hoc_sensitivity': sensitivities, 'identical_payload_judge_consistency': consistency,
              'good_control_state_differences': control, 'uses_later_evidence_states': later,
              'error_token_evidence': spans, 'no_model_loaded': True, 'training_started': False}
    (OUT / 'review_details.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'error_token_evidence'}, ensure_ascii=False, indent=2))
    print('SPAN_TOKENS', json.dumps([{k:v for k,v in s.items() if k in ['state_id','expression','tokens']} for s in spans], ensure_ascii=False))


if __name__ == '__main__':
    main()
