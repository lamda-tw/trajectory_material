"""Analyze eight existing R6 states; standard library only, no model or GPU work."""
import ast
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

A = Path(__file__).resolve().parent
D = A.parent

NOTES = {
    'R6_b001_7d7fbf6_1_s10': ('Supervisor 接口列表', 'repeat', 'repeat', 'code_near_agreement', 'neither_repaired', '_des'),
    'R6_b013_229360a_3_s20': ('Spotify 歌曲库规范', 'repeat', 'repeat', 'code_near_agreement', 'neither_repaired', '_song'),
    'R6_b014_60d0b5b_1_s17': ('Venmo 接口列表', 'repair', 'repair', 'encourages_repeat_at_action_fork', 'repair_retained', '_des'),
    'R6_b018_aa8502b_1_s05': ('Supervisor 接口列表→凭据规范', 'repair', 'repair', 'code_near_agreement', 'repair_retained', '_des'),
    'R6_b031_c901732_1_s14': ('Spotify 相册检索规范', 'repair', 'repeat', 'suppresses_original_code', 'repair_lost', '.api'),
    'R6_b032_771d8fc_3_s35': ('Supervisor 凭据接口规范', 'repair', 'repeat', 'suppresses_original_code', 'repair_lost', '.api'),
    'R6_b033_b0a8eae_2_s19': ('Simple Note 登录规范', 'new_error', 'repeat', 'suppresses_original_code', 'error_to_repeat', 'print'),
    'R6_b035_302c169_3_s21': ('Phone 登录规范', 'new_error', 'repeat', 'code_near_agreement', 'error_to_repeat', '_doc'),
}


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def doc_calls(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    result = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = ast.unparse(n.func)
        if name not in ['apis.api_docs.show_api_doc', 'apis.api_docs.show_api_descriptions']:
            continue
        try:
            kwargs = {x.arg: ast.literal_eval(x.value) for x in n.keywords}
        except (ValueError, TypeError):
            continue
        result.append((name, tuple(sorted(kwargs.items()))))
    return result


def analyze():
    audit_path = D / 'analysis/case_audit_sanitized.json'
    cases = {x['state_id']: x for x in read(audit_path) if x['stratum'] == 'R6'}
    reviews_path = D / 'analysis/manual_first_step_review.json'
    reviews = {(x['state_id'], x['condition']): x for x in read(reviews_path)['rows']}
    rows, sources = [], [{'path': str(audit_path.relative_to(D)), 'sha256': sha(audit_path)},
                         {'path': str(reviews_path.relative_to(D)), 'sha256': sha(reviews_path)}]
    assert set(cases) == set(NOTES)
    for sid, (title, base, final, signal, change, key) in NOTES.items():
        sp, pp = D / 'states' / (sid + '.json'), D / 'probabilities' / (sid + '.json')
        s, p, a = read(sp), read(pp), cases[sid]
        assert s['example']['branch'] == 'sdpo' and 'R6' in s['feedback']['failed_rules']
        assert p['text_token_alignment'] and p['parameter_updates'] == 0
        assert (base == 'repair') == (reviews[(sid, 'base_C2')]['targeted_first_step_repair'] == 'Y')
        assert (final == 'repair') == (reviews[(sid, 'ema36_C2')]['targeted_first_step_repair'] == 'Y')
        for path in [sp, pp]:
            sources.append({'path': str(path.relative_to(D)), 'sha256': sha(path)})
        sig = p['signals']['historical_B_loss']
        code_ids = sorted({i for span in p['spans'] if span['kind'] == 'whole_code' for i in span['positions']})
        token_rows = []
        for i, token in enumerate(p['decoded_tokens']):
            token_rows.append({'position': i, 'token': token, 'in_code': i in code_ids,
                'p_historical_student': math.exp(p['conditions']['historical_student_C0']['original_token_logprobs'][i]),
                'q_historical_teacher_C2': math.exp(p['conditions']['historical_teacher_C2']['original_token_logprobs'][i]),
                'q_base_C2': math.exp(p['conditions']['base_C2']['original_token_logprobs'][i]),
                'q_ema36_C2': math.exp(p['conditions']['ema36_C2']['original_token_logprobs'][i]),
                'KL': sig['reverse_KL_top100_tail'][i],
                'old_token_logit_gradient': sig['original_token_logit_gradient'][i],
                'old_token_logprob_descent_derivative': sig['original_token_logprob_descent_derivative'][i]})
        keys = [x for x in token_rows if x['in_code'] and x['token'] == key]
        assert keys
        # For b013 use the actual API-name argument, not its earlier comment.
        key_row = keys[-1] if sid.startswith('R6_b013') else keys[0]
        old_calls = set(doc_calls(s['original']['code']))
        prior_steps = [h['step'] for h in s['history'] if old_calls.intersection(doc_calls(h.get('code', '')))]
        conditions = {}
        for name in ['base_C0', 'base_C2', 'ema36_C0', 'ema36_C2', 'student36_C0']:
            actions = a['conditions'][name]['actions']
            conditions[name] = {'first_code': actions[0]['code'],
                'first_error': actions[0]['observation'].splitlines()[-1] if actions[0]['execution_error'] else None,
                'first_calls': actions[0]['api_calls'],
                'actions': [{'code': z['code'], 'error': z['observation'].splitlines()[-1] if z['execution_error'] else None,
                             'api_calls': z['api_calls']} for z in actions]}
        row = {'state_id': sid, 'title': title, 'batch': s['batch'], 'source_epoch': s['epoch'],
            'step': s['target_step'], 'prompt_tokens': len(s['example']['prompt_ids']),
            'original_code': s['original']['code'], 'original_plan': s['original']['text'].split('```')[0].strip(),
            'prior_identical_document_steps': prior_steps, 'feedback': s['feedback'],
            'base_C2_outcome': base, 'ema36_C2_outcome': final, 'teacher_change': change,
            'historical_code_signal_category': signal,
            'historical_KL_step_mean': sum(sig['reverse_KL_top100_tail']) / len(token_rows),
            'historical_code_KL_mean': sum(token_rows[i]['KL'] for i in code_ids) / len(code_ids),
            'historical_code_local_dlogp_sum': sum(token_rows[i]['old_token_logprob_descent_derivative'] for i in code_ids),
            'historical_answer_local_dlogp_sum': sum(x['old_token_logprob_descent_derivative'] for x in token_rows),
            'historical_code_log_q_over_p': sum(sig['original_token_logprob_delta'][i] for i in code_ids),
            'key_token': key_row, 'all_response_tokens': token_rows, 'conditions': conditions,
            'source_loss_reproduction': p['historical_training_reproduction']}
        if signal == 'code_near_agreement':
            assert row['historical_code_KL_mean'] < 1e-4
        if signal == 'encourages_repeat_at_action_fork':
            assert key_row['old_token_logprob_descent_derivative'] > .1
            assert row['historical_code_local_dlogp_sum'] > .1
        if signal == 'suppresses_original_code':
            assert row['historical_code_local_dlogp_sum'] < 0
        rows.append(row)
    summary = {'states': len(rows), 'base_C2': dict(Counter(x['base_C2_outcome'] for x in rows)),
        'ema36_C2': dict(Counter(x['ema36_C2_outcome'] for x in rows)),
        'teacher_change': dict(Counter(x['teacher_change'] for x in rows)),
        'historical_code_signal': dict(Counter(x['historical_code_signal_category'] for x in rows)),
        'base_correct_states': [x['state_id'] for x in rows if x['base_C2_outcome'] == 'repair'],
        'method': 'Post-hoc unblinded review of existing greedy rollouts; first action only for repair labels. Historical signal uses actual pre-batch student and EMA teacher. Whole response and code tokens inspected.',
        'limits': 'Signal categories describe direct code-position differences, not total shared-parameter training effects. The three questions overlap. No population-rate or causal attribution to a loss branch.',
        'new_model_forward_calls': 0, 'new_codex_calls': 0, 'new_optimizer_updates': 0, 'new_gpu_tasks': 0}
    (A / 'evidence.json').write_text(json.dumps({'summary': summary, 'cases': rows}, ensure_ascii=False, indent=2) + '\n')
    with (A / 'summary.csv').open('w', newline='') as f:
        fields = ['state_id', 'title', 'base_C2_outcome', 'ema36_C2_outcome', 'teacher_change',
                  'historical_code_signal_category', 'historical_code_KL_mean', 'historical_code_local_dlogp_sum']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        w.writerows({k: x[k] for k in fields} for x in rows)
    assert all(sha(D / x['path']) == x['sha256'] for x in sources)
    (A / 'verification.json').write_text(json.dumps({'sources_unchanged': True, 'sources': sources,
        'analysis_script_sha256': sha(Path(__file__)), **summary}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for x in rows:
        t = x['key_token']
        print(x['state_id'], 'old_docs', len(x['prior_identical_document_steps']), 'codeKL', x['historical_code_KL_mean'],
              'key', t['token'], t['p_historical_student'], t['q_historical_teacher_C2'])


if __name__ == '__main__':
    analyze()
