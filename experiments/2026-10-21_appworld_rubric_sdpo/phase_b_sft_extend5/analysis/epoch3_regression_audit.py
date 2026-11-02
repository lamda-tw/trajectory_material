"""Independent CPU-only audit; never imports training or changes frozen run files."""
import ast
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

B = Path(__file__).resolve().parents[1]
R = B.parent
OLD = R / 'phase_b_sft_only'
OUT = B / 'analysis/epoch3_regression_audit'
OUT.mkdir(exist_ok=True)
CAP = 59

def read(p):
    return json.loads(p.read_text())

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def classify(code):
    code = (code or '').strip()
    try:
        tree = ast.parse(code)
        sig = ast.dump(tree, include_attributes=False)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        api = [(ast.unparse(n.func), n) for n in calls if ast.unparse(n.func).startswith('apis.')]
    except SyntaxError:
        sig, api = code, []
    docs = bool(api) and all(n.startswith('apis.api_docs.') for n, _ in api)
    business = any(not n.startswith(('apis.api_docs.', 'apis.supervisor.')) and n.rsplit('.', 1)[-1] not in ('login', 'logout') for n, _ in api)
    safe = [ast.unparse(n) if name.startswith('apis.api_docs.') else name for name, n in api]
    return sig, docs, business, safe

def main():
    verified = Counter()
    manifest = read(B / 'config/preparation_manifest.json')
    for p, h in manifest['files'].items():
        assert sha(R / p) == h, p
        verified['frozen_dependencies'] += 1
    orig_cfg, new_cfg = (read(p / 'config/run.json') for p in (OLD, B))
    changes = []
    def diff(a, b, prefix=''):
        for k in sorted(a.keys() | b.keys()):
            if a.get(k) == b.get(k):
                continue
            if isinstance(a.get(k), dict) and isinstance(b.get(k), dict):
                diff(a[k], b[k], prefix + k + '.')
            else:
                changes.append({'key': prefix + k, 'old': a.get(k), 'new': b.get(k)})
    diff(orig_cfg, new_cfg)
    assert {x['key'] for x in changes} == {'experiment', 'training.epochs', 'training.update_opportunities', 'collection.tasks', 'evaluation.tasks'}
    for name in ['b_loss.py', 'b_dataset.py', 'b_judge.py', 'b_rollout_worker.py']:
        assert sha(OLD / 'scripts' / name) == sha(B / 'scripts' / name)
        verified['unchanged_core_scripts'] += 1
    for name in ['train90.txt', 'dev57.txt']:
        assert sha(OLD / 'config' / name) == sha(B / 'config' / name)
    schedule = read(B / 'config/schedule.json')['batches']
    assert schedule[:36] == read(OLD / 'config/schedule.json')['batches']
    train = set((B / 'config/train90.txt').read_text().split())
    dev = set((B / 'config/dev57.txt').read_text().split())
    assert len(train) == 90 and len(dev) == 57 and not train & dev
    for epoch in range(1, 6):
        tasks = [t['task_id'] for b in schedule[(epoch-1)*18:epoch*18] for t in b['tasks']]
        assert len(tasks) == len(set(tasks)) == 90 and set(tasks) == train
    batches, step_rows, repeat_examples, epoch_stats = [], [], [], {}
    for number in range(1, CAP + 1):
        epoch = (number - 1) // 18 + 1
        phase = OLD if number <= 36 else B
        folder = phase / f'runs/sft/batch_{number:03d}'
        cp = folder / 'checkpoint'
        complete = read(cp / 'COMPLETE.json')
        data = read(folder / 'dataset.json')
        m = read(cp / 'metrics.json')
        assert sha(folder / 'dataset.json') == complete['identity']['dataset_sha256']
        assert sha(cp / 'metrics.json') == complete['files']['metrics.json']
        assert sha(cp / 'step_metrics.json') == complete['files']['step_metrics.json']
        assert complete['identity']['config_sha256'] == sha(phase / 'config/run.json')
        assert complete['batch'] == m['batch'] == complete['optimizer_updates'] == m['optimizer_updates'] == number
        assert m['arm'] == 'sft' and m['sdpo_loss'] == m['weighted_sdpo_grad_norm'] == m['counts'].get('sdpo', 0) == 0
        assert m['teacher_received_gradient'] is False
        assert all(math.isfinite(m[k]) for k in ['sft_loss','total_loss','grad_norm_before_clip','grad_norm_after_clip','student_parameter_delta_norm'])
        assert m['student_parameter_delta_norm'] > 0 and m['optimizer_step_performed']
        assert abs(m['lr'] - 5e-5 * min(1, number / 5)) < 1e-12
        assert m['grad_norm_after_clip'] < 1.00001
        if number > 1:
            prev_phase = OLD if number <= 37 else B
            prev = prev_phase / f'runs/sft/batch_{number-1:03d}/checkpoint'
            assert complete['identity']['parent_policy'] == {'kind':'student_adapter','checkpoint_complete_sha256':sha(prev/'COMPLETE.json')}
        if number >= 37:
            assert m['restored_optimizer_updates'] == m['optimizer_step_min_before'] == m['optimizer_step_max_before'] == number - 1
            assert m['optimizer_state_entries'] == 504 and m['restored_optimizer_lr'] == 5e-5
            assert m['resume_checkpoint_sha256'] == sha(prev / 'COMPLETE.json')
            assert Path(m['resume_checkpoint']) == prev
            verified['continuation_parent_and_optimizer_links'] += 1
        if number in (36, 54):
            for name, h in complete['files'].items():
                assert sha(cp / name) == h, (number, name)
                verified['protected_checkpoint_files'] += 1
        if 37 <= number < 54:
            receipt = read(cp / 'RETENTION.json')
            assert receipt['complete_sha256'] == sha(cp / 'COMPLETE.json') and receipt['status'] == 'complete'
            for name, h in complete['files'].items():
                if (cp / name).exists():
                    assert sha(cp / name) == h
                else:
                    assert receipt['removed_files'][name]['sha256'] == h
            verified['documented_pruned_checkpoints'] += 1
        count = Counter(batches=1)
        collection = read(folder / 'collection.json')
        assert collection['schedule'] == schedule[number-1]
        assert collection['policy_identity'] == data['policy_identity'] == complete['identity']['parent_policy']
        examples = {(x['trajectory_id'], x['step']): x for x in data['examples']}
        for item in collection['trajectories']:
            p = folder / item['path']
            assert sha(p) == item['sha256']
            t = read(p)
            assert t['job']['policy_identity'] == collection['policy_identity']
            count['trajectories'] += 1
            seen = {}
            for s in t['steps']:
                x = examples[(item['id'], s['step'])]
                sig, docs, business, safe = classify(s.get('code'))
                repeat = docs and sig in seen
                chosen = x['branch'] == 'sft'
                assert x['response_ids'] == s['response_ids'] and x['prompt_ids'] == s['prompt_ids']
                if chosen:
                    assert 'F' not in x['labels'] and x['labels'].count('P') >= 3
                count['steps'] += 1
                count['docs'] += docs
                count['repeat_docs'] += repeat
                count['business'] += business
                count['R6_FAIL'] += x['labels'][5] == 'F'
                if chosen:
                    count['sft'] += 1
                    count['sft_docs'] += docs
                    count['sft_repeat_docs'] += repeat
                    count['sft_business'] += business
                    count['sft_tokens'] += len(x['response_ids'])
                    count['sft_U'] += 'U' in x['labels']
                row = {'epoch': epoch, 'batch': number, 'task_id': x['task_id'], 'trajectory_id':item['id'],
                    'step':s['step'], 'branch':x['branch'], 'labels':x['labels'], 'docs':docs,
                    'repeat_docs':repeat, 'business':business, 'response_tokens':len(x['response_ids'])}
                step_rows.append(row)
                if chosen and repeat:
                    repeat_examples.append({**row,'previous_identical_step':seen[sig], 'calls':safe, 'trajectory':str(p),
                        'judgment':str(folder/'judging'/item['id']/'judgement.json')})
                if (s.get('code') or '').strip():
                    seen.setdefault(sig, s['step'])
            verified['training_trajectories'] += 1
        assert count['sft'] == m['counts']['sft'] and count['steps'] == len(data['examples'])
        epoch_stats.setdefault(epoch, Counter()).update(count)
        batches.append({'epoch':epoch, 'batch':number, **count, **{k:m[k] for k in ['sft_loss','lr','grad_norm_before_clip','grad_norm_after_clip','clipped','student_parameter_delta_norm','seconds']}})
        if number % 18 == 0 or number == CAP:
            print('audited batch',number,'epoch counts',dict(epoch_stats[epoch]),flush=True)
    for e, c in epoch_stats.items():
        bs = [x for x in batches if x['epoch'] == e]
        c.update({})
        c = dict(c)
        c['sft_docs_fraction'] = c['sft_docs']/c['sft']
        c['sft_repeat_docs_fraction'] = c['sft_repeat_docs']/c['sft']
        c['mean_step_length'] = c['sft_tokens']/c['sft']
        c['batch_mean_sft_loss'] = statistics.mean(x['sft_loss'] for x in bs)
        c['loss_min_max'] = [min(x['sft_loss'] for x in bs), max(x['sft_loss'] for x in bs)]
        c['grad_norm_min_max'] = [min(x['grad_norm_before_clip'] for x in bs), max(x['grad_norm_before_clip'] for x in bs)]
        c['clipped_batches'] = sum(x['clipped'] for x in bs)
        c['parameter_delta_min_max'] = [min(x['student_parameter_delta_norm'] for x in bs),max(x['student_parameter_delta_norm'] for x in bs)]
        c['batch_mean_docs_weight'] = statistics.mean(x['sft_docs']/x['sft'] for x in bs)
        epoch_stats[e] = c
    dev_epochs, dev_cases = {}, []
    cached = read(B / 'analysis/five_epoch_summary.json')
    for e in (1, 2, 3):
        record = cached['epochs'][str(e)]
        summary_path = Path(record['summary_path'])
        summ = read(summary_path)
        assert sha(summary_path) == record['source_sha256']
        phase = OLD if e <= 2 else B
        assert summ['policy_identity']['checkpoint_complete_sha256'] == sha(phase/f'runs/sft/batch_{e*18:03d}/checkpoint/COMPLETE.json')
        assert summ['temperature'] == 0 and summ['seed'] == 100 and summ['student_without_feedback']
        assert {x['task_id'] for x in summ['results']} == dev
        for row in record['results']:
            assert sha(Path(row['trajectory'])) == row['trajectory_sha256']
            assert sha(Path(row['official_report'])) == row['official_report_sha256']
            t = read(Path(row['trajectory']))
            assert t['official_evaluation']['success'] == row['success']
            verified['dev_trajectories_and_official_reports'] += 1
            if row['task_id'] in ['d4e9306_2','b119b1f_2','6c2c621_1']:
                seq=[]; seen={}
                for s in t['steps']:
                    sig, docs, business, safe=classify(s.get('code'))
                    seq.append({'step':s['step'],'calls':safe, 'docs':docs,'repeat_of':seen.get(sig) if docs else None,
                        'business':business,'observation_chars':len(s.get('observation',''))})
                    seen.setdefault(sig,s['step'])
                dev_cases.append({'epoch':e,'task_id':row['task_id'],'success':row['success'],
                    'passes':row['num_passes'],'tests':row['num_tests'],'termination':row['termination'],
                    'steps':row['steps'],'repeat_docs':row['repeated_docs_steps'], 'sequence':seq,'trajectory':row['trajectory']})
        dev_epochs[e] = {k:v for k,v in record.items() if k != 'results'}
        dev_epochs[e]['successful_tasks']=[x['task_id'] for x in record['results'] if x['success']]
    write('summary.json',{'audited_at_utc':datetime.now(timezone.utc).isoformat(),'committed_batch_cap':CAP,
        'verified':verified,'config_changes':changes,'train_epochs':epoch_stats,'dev_epochs':dev_epochs,
        'first_batch_restore':read(B/'analysis/first_batch_acceptance.json'),
        'note':'Epoch 4 training statistics cover only batches 55-59. No GPU work or training mutation performed.'})
    write('selected_repeated_docs.json',repeat_examples)
    write('dev_case_sequences.json',dev_cases)
    for name,rows in [('batches.csv',batches),('steps.csv',step_rows)]:
        with (OUT/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({'verified':verified,'train_epochs':epoch_stats,'selected_repeated_docs':len(repeat_examples)},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
