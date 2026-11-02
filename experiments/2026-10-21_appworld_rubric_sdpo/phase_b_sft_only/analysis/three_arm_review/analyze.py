"""CPU-only post-run audit. Reads completed artifacts; starts no model or judge."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import ast
import csv
import hashlib
import json
import math
import statistics

OUT = Path(__file__).resolve().parent
B = OUT.parents[1]
R = B.parent
ROOTS = {'mixed': R / 'phase_b/runs/mixed', 'sdpo': R / 'phase_b_sdpo_only/runs/sdpo', 'sft': B / 'runs/sft'}
verified = Counter()
missing_intermediate_state = []


def read(p):
    return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check(p, expected, category):
    assert sha(p) == expected, str(p)
    verified[category] += 1


def dt(s):
    return datetime.fromisoformat(s)


def seconds(a, b):
    return (dt(b) - dt(a)).total_seconds()


def csv_write(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def trajectory_stats(t):
    c = Counter(trajectories=1, steps=len(t['steps']))
    seen = set(); code_counts = Counter(); code_text = {}
    last = None; streak = 0; longest = 0
    for s in t['steps']:
        code = (s.get('code') or '').strip()
        try:
            tree = ast.parse(code)
            sig = ast.dump(tree, include_attributes=False)
            names = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
        except SyntaxError:
            sig = code; names = []
        apis = [n for n in names if n.startswith('apis.')]
        docs = bool(apis) and all(n.startswith('apis.api_docs.') for n in apis)
        repeated = bool(code) and sig in seen
        c['docs_only'] += docs
        c['repeated_code'] += repeated
        c['repeated_docs_code'] += docs and repeated
        c['non_doc_api_steps'] += any(not n.startswith('apis.api_docs.') for n in apis)
        c['response_tokens'] += len(s['response_ids'])
        c['prompt_tokens'] += len(s['prompt_ids'])
        c['observation_chars'] += len(s.get('observation', ''))
        c['generation_seconds_sum'] += s.get('elapsed_seconds', 0)
        if code: seen.add(sig)
        if docs:
            code_counts[sig] += 1; code_text[sig] = code
            streak = streak + 1 if sig == last else 1
            longest = max(longest, streak)
        else:
            streak = 0
        last = sig if docs else None
    c['elapsed_seconds_sum'] = t['elapsed_seconds']
    top = code_counts.most_common(1)
    return dict(c), {'longest_consecutive_docs': longest,
        'most_frequent_docs_count': top[0][1] if top else 0,
        'most_frequent_docs_code': code_text[top[0][0]] if top else ''}


def summarize_trajectories(rows):
    counts = Counter()
    for row in rows: counts.update(row['counts'])
    return {'counts': dict(counts), 'terminations': dict(Counter(x['termination'] for x in rows)),
        'mean_steps': counts['steps'] / len(rows),
        'mean_response_tokens_per_step': counts['response_tokens'] / counts['steps'],
        'docs_only_fraction': counts['docs_only'] / counts['steps'],
        'repeated_docs_fraction': counts['repeated_docs_code'] / counts['steps'],
        'repeated_code_fraction': counts['repeated_code'] / counts['steps'],
        'trajectories_with_5_consecutive_identical_docs': sum(x['longest_consecutive_docs'] >= 5 for x in rows)}


def main():
    result = {}; all_train_rows = []; all_dev_rows = []; batches = []
    for arm, root in ROOTS.items():
        complete = read(root / 'COMPLETE.json')
        assert complete['batches'] == complete['optimizer_updates'] == 36
        launch = read(root / 'launch.json')
        start = launch.get('started_at', launch.get('launched_at'))
        elapsed = seconds(start, complete['completed_at'])
        metrics = []; train_rows = []; dev_rows = []; judge_seconds = 0
        judge_counts = Counter(); example_counts = Counter(); token_counts = Counter()
        processing = Counter(); rule_counts = {1: Counter(), 2: Counter()}
        branch_by_epoch = {1: Counter(), 2: Counter()}
        for num in range(1, 37):
            folder = root / f'batch_{num:03d}'; epoch = (num - 1) // 18 + 1
            checkpoint = read(folder / 'checkpoint/COMPLETE.json')
            assert checkpoint['batch'] == num and checkpoint['arm'] == arm
            for name, h in checkpoint['files'].items():
                fp = folder / 'checkpoint' / name
                if not fp.exists() and name == 'state.pt' and num not in (1, 18, 36):
                    missing_intermediate_state.append(str(fp.relative_to(R)))
                else:
                    check(fp, h, 'checkpoint_files')
            data = read(folder / 'dataset.json')
            check(folder / 'dataset.json', checkpoint['identity']['dataset_sha256'], 'datasets')
            m = read(folder / 'checkpoint/metrics.json'); metrics.append(m)
            assert not m['teacher_received_gradient'] and m['student_parameter_delta_norm'] > 0
            assert m['physical_gpu_uuid'] == 'GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
            assert all(math.isfinite(m[k]) for k in ['sft_loss', 'sdpo_loss', 'total_loss', 'grad_norm_before_clip', 'grad_norm_after_clip'])
            if arm == 'sdpo': assert m['sft_loss'] == m['sft_grad_norm'] == m['counts'].get('sft', 0) == 0
            if arm == 'sft': assert m['sdpo_loss'] == m['weighted_sdpo_grad_norm'] == m['counts'].get('sdpo', 0) == 0
            example_counts.update(m['counts']); branch_by_epoch[epoch].update(m['counts'])
            for x in data['examples']:
                branch = x['branch']; token_counts[branch] += len(x['response_ids'])
                if branch != 'mask':
                    processing['student_input_tokens'] += len(x['prompt_ids']) + len(x['response_ids']) - 1
                if branch == 'sdpo':
                    processing['teacher_input_tokens'] += len(x['teacher_prompt_ids']) + len(x['response_ids']) - 1
                for i, label in enumerate(x['labels'], 1):
                    if label == 'F': rule_counts[epoch][f'R{i}'] += 1
            collection = read(folder / 'collection.json')
            assert len(collection['trajectories']) == 5
            group = []; judge_starts = []; judge_ends = []
            for item in collection['trajectories']:
                p = folder / item['path']; check(p, item['sha256'], 'training_trajectories')
                t = read(p); assert t['job']['policy_identity'] == collection['policy_identity']
                c, docs = trajectory_stats(t)
                row = {'arm': arm, 'epoch': epoch, 'batch': num, 'task_id': t['job']['task_id'],
                    'path': str(p.relative_to(R)), 'termination': t['termination'], 'counts': c, **docs}
                train_rows.append(row); group.append(row)
                md = read(folder / 'judging' / item['id'] / 'metadata.json')
                assert md['status'] == 'valid'
                # First SDPO batch reuses old cached judging, not a new call.
                if not (arm in ('sdpo', 'sft') and num == 1):
                    judge_starts.append(md['started_at']); judge_ends.append(md['completed_at'])
                    for attempt in md['attempts']:
                        judge_counts['calls'] += 1
                        judge_counts[attempt['kind']] += 1
                        judge_counts['serial_seconds_sum'] += attempt['seconds']
                        usage = attempt.get('audit', {}).get('usage', {})
                        for key in ['input_tokens', 'output_tokens', 'cached_input_tokens']:
                            judge_counts[key] += usage.get(key, 0)
            if judge_starts:
                judge_seconds += seconds(min(judge_starts), max(judge_ends))
            s = summarize_trajectories(group)
            batches.append({'arm': arm, 'batch': num, 'epoch': epoch, 'steps': s['counts']['steps'],
                'response_tokens': s['counts']['response_tokens'], 'docs_only_fraction': s['docs_only_fraction'],
                'repeated_docs_fraction': s['repeated_docs_fraction'], 'sft_steps': m['counts'].get('sft', 0),
                'sdpo_steps': m['counts'].get('sdpo', 0), 'sft_loss': m['sft_loss'], 'sdpo_loss': m['sdpo_loss'],
                'training_seconds': m['seconds'], 'grad_norm': m['grad_norm_before_clip']})
        eval_summary = {}; eval_seconds = 0
        heartbeats = [json.loads(line) for line in (root / 'resources.jsonl').read_text().splitlines()]
        for epoch in (1, 2):
            folder = root / f'epoch_{epoch:02d}_dev57'; summ = read(folder / 'summary.json')
            expected_tasks = set((root.parents[1] / 'config/dev57.txt').read_text().split())
            assert len(summ['results']) == 57 and {x['task_id'] for x in summ['results']} == expected_tasks
            starts = [h['stage']['updated_at'] for h in heartbeats if h.get('stage', {}).get('stage') == 'dev57_evaluation'
                and h['stage'].get('epoch') == epoch]
            assert starts
            wall = seconds(min(starts), summ['completed_at']); eval_seconds += wall
            group = []
            for x in summ['results']:
                p = folder / 'trajectories' / (x['task_id'] + '.json'); check(p, x['trajectory_sha256'], 'evaluation_trajectories')
                t = read(p); assert t['official_evaluation']['success'] == x['success']
                c, docs = trajectory_stats(t)
                row = {'arm': arm, 'epoch': epoch, **x, 'path': str(p.relative_to(R)), 'counts': c, **docs}
                dev_rows.append(row); group.append(row)
            eval_summary[epoch] = {k: v for k, v in summ.items() if k != 'results'}
            eval_summary[epoch].update(summarize_trajectories(group))
            eval_summary[epoch]['wall_seconds'] = wall
            eval_summary[epoch]['successful_tasks'] = [x['task_id'] for x in group if x['success']]
        train_seconds = sum(m['seconds'] for m in metrics)
        result[arm] = {'start': start, 'end': complete['completed_at'],
            'timing': {'total_wall_seconds': elapsed, 'training_seconds': train_seconds,
                'judge_wall_seconds': judge_seconds, 'evaluation_wall_seconds': eval_seconds,
                'other_wall_seconds': elapsed - train_seconds - judge_seconds - eval_seconds},
            'judge_calls': dict(judge_counts), 'counts': dict(example_counts), 'response_tokens_by_branch': dict(token_counts),
            'processed_tokens': dict(processing), 'rule_failures_by_epoch': rule_counts,
            'branches_by_epoch': branch_by_epoch, 'train': {e: summarize_trajectories([x for x in train_rows if x['epoch'] == e]) for e in (1, 2)},
            'dev': eval_summary,
            'technical': {'updates': len(metrics), 'clipped_batches': sum(m['clipped'] for m in metrics),
                'sft_loss_min': min(m['sft_loss'] for m in metrics), 'sft_loss_max': max(m['sft_loss'] for m in metrics), 'grad_norm_min': min(m['grad_norm_before_clip'] for m in metrics), 'grad_norm_max': max(m['grad_norm_before_clip'] for m in metrics),
                'sdpo_loss_min': min(m['sdpo_loss'] for m in metrics), 'sdpo_loss_max': max(m['sdpo_loss'] for m in metrics),
                'first_sdpo_loss': metrics[0]['sdpo_loss'], 'last_sdpo_loss': metrics[-1]['sdpo_loss'],
                'first_batch_seconds': metrics[0]['seconds'],
                'peak_allocated_gib': max(m['peak_allocated_gib'] for m in metrics),
                'peak_reserved_gib': max(m['peak_reserved_gib'] for m in metrics)}}
        all_train_rows += train_rows; all_dev_rows += dev_rows
        print(arm, 'verified and analyzed', flush=True)
    comparisons = {}
    for epoch in (1, 2):
        left = {x['task_id']: x for x in all_dev_rows if x['arm'] == 'mixed' and x['epoch'] == epoch}
        right = {x['task_id']: x for x in all_dev_rows if x['arm'] == 'sdpo' and x['epoch'] == epoch}
        assert left.keys() == right.keys()
        comparisons[epoch] = {'both_success': [], 'mixed_only_success': [], 'sdpo_only_success': [],
            'both_fail': [], 'sdpo_more_tests': [], 'sdpo_fewer_tests': [], 'same_tests': []}
        for task in left:
            a, b = left[task], right[task]
            key = 'both_success' if a['success'] and b['success'] else 'mixed_only_success' if a['success'] else 'sdpo_only_success' if b['success'] else 'both_fail'
            comparisons[epoch][key].append(task)
            assert a['num_tests'] == b['num_tests']
            key = 'sdpo_more_tests' if b['num_passes'] > a['num_passes'] else 'sdpo_fewer_tests' if b['num_passes'] < a['num_passes'] else 'same_tests'
            comparisons[epoch][key].append(task)
    result['paired_comparisons'] = comparisons
    result['verification'] = dict(verified)
    result['missing_intermediate_state_files'] = missing_intermediate_state
    for name, obj in [('summary.json', result), ('training_trajectories.json', all_train_rows), ('dev_trajectories.json', all_dev_rows)]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    csv_write(OUT / 'batches.csv', batches)
    flat = [{k: v for k, v in x.items() if k not in ('counts', 'most_frequent_docs_code')} | x['counts'] for x in all_dev_rows]
    csv_write(OUT / 'dev_task_behavior.csv', flat)
    print(json.dumps(result['verification'], ensure_ascii=False))


if __name__ == '__main__':
    main()
