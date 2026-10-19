"""Only score predicates determine pools. Uniform sampling; no quality gates."""
import csv
import hashlib
import json
import random
import shutil
from collections import Counter
from experiment_utils import R, read, dump, sha, set_sha, jsonl, now


def main():
    assert not (R / 'EXECUTION_MANIFEST.json').exists(), 'Frozen run must not rebuild datasets'
    cfg = read(R / 'config/training.json')
    plan = read(R / 'config/experiment_plan.json')
    assert plan['execution_authorized']
    assert cfg['samples_per_epoch'] == 1358 and cfg['epochs'] == 1
    assert cfg['seeds'] == [20261015, 20261016]
    prior = read(R / 'references/prior_DATA_MANIFEST.json')
    for rel in ['data/tokens.bin', 'data/token_index.json', 'data/step_inventory.jsonl']:
        assert sha(R / rel) == prior['artifacts'][rel], rel
    assert sha(R / 'references/step_labels.csv') == plan['source_labels_sha256']
    assert sha(R / 'config/scoring_prompt_v6_en_format.txt') == plan['scoring_prompt_sha256']
    rows = jsonl(R / 'data/step_inventory.jsonl')
    with (R / 'references/step_labels.csv').open(newline='') as handle:
        scored = {f"{r['id']}:{r['step']}": ''.join(r[f'R{i}'] for i in range(1, 9))
                  for r in csv.DictReader(handle)}
    index = read(R / 'data/token_index.json')
    assert len(rows) == len(scored) == len(index) == 11254
    assert {r['id'] for r in rows} == set(scored) == set(index)
    for row in rows:
        assert row['labels'] == scored[row['id']]
        assert row['selected_end'] == row['response_tokens'] > 0
        assert row['prompt_tokens'] > 0
        # Integrity/resource assertions STOP the run; they never drop a step.
        assert row['prompt_tokens'] + row['response_tokens'] <= cfg['max_length']
    pools = {}
    for i in range(1, 9):
        arm = f'drop_r{i}'
        pool = []
        for row in rows:
            other = row['labels'][:i-1] + row['labels'][i:]
            if other.count('P') >= 3 and 'F' not in other:
                pool.append(row)
        pool.sort(key=lambda r: r['id'])
        expected = plan['candidate_pools'][arm]
        assert len(pool) == expected['candidate_count'] >= 1358
        assert set_sha(r['id'] for r in pool) == expected['candidate_id_set_sha256']
        pools[arm] = pool
        dump(R / f'data/{arm}/CANDIDATE_POOL.json', {
            'arm': arm, 'ignored_dimension': i, 'remaining_P_min': 3, 'remaining_F_max': 0,
            'candidate_count': len(pool), 'ids': [r['id'] for r in pool],
            'id_set_sha256': expected['candidate_id_set_sha256'], 'quality_filters': False})
    assert pools['drop_r5'] == pools['drop_r7']
    summaries, union = {}, set()
    for seed in cfg['seeds']:
        for arm in cfg['arms']:
            seed_value = int(hashlib.sha256(f'{seed}:{arm}:selection'.encode()).hexdigest()[:16], 16)
            selected = random.Random(seed_value).sample(pools[arm], 1358)
            assert len(selected) == len({r['id'] for r in selected}) == 1358
            folder = R / f'data/{arm}/seed_{seed}'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'selection.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in selected))
            order = list(range(1358))
            random.Random(seed + 100000).shuffle(order)
            dump(folder / 'orders.json', {'orders': [order]})
            union.update(r['id'] for r in selected)
            summaries[f'{arm}/seed_{seed}'] = {
                'candidate_count': len(pools[arm]), 'selected_steps': 1358,
                'sampling': 'global uniform without replacement', 'selection_seed': seed_value,
                'inclusion_probability': 1358 / len(pools[arm]), 'task_quotas_used': False,
                'supervised_tokens': sum(r['response_tokens'] for r in selected),
                'prompt_tokens': sum(r['prompt_tokens'] for r in selected),
                'max_sequence': max(r['prompt_tokens'] + r['response_tokens'] for r in selected),
                'with_ignored_dimension_F': sum(r['labels'][int(arm[-1])-1] == 'F' for r in selected),
                'dimension_counts': {f'R{i+1}': dict(Counter(r['labels'][i] for r in selected)) for i in range(8)},
                'task_distribution_post_selection_only': dict(sorted(Counter(r['task_id'] for r in selected).items()))}
        alias = R / f'data/drop_r7/seed_{seed}'
        source = R / f'data/drop_r5/seed_{seed}'
        alias.mkdir(parents=True, exist_ok=True)
        for name in ['selection.jsonl', 'orders.json']:
            shutil.copy2(source / name, alias / name)
        dump(alias / 'ALIAS.json', {'alias_of': 'drop_r5', 'seed': seed,
             'source': str(source.relative_to(R)), 'selection_sha256': sha(source / 'selection.jsonl'),
             'orders_sha256': sha(source / 'orders.json'), 'independent_replicate': False})
        summaries[f'drop_r7/seed_{seed}'] = {**summaries[f'drop_r5/seed_{seed}'], 'alias_of': 'drop_r5'}
    dump(R / 'data/SELECTION_SUMMARY.json', summaries)
    dump(R / 'data/selected_union.json', sorted(union))
    train = set((R / 'config/train_all.txt').read_text().split())
    dev = set((R / 'config/dev.txt').read_text().split())
    assert train == {r['task_id'] for r in rows} and len(train) == 90 and len(dev) == 57
    assert not {t.rsplit('_', 1)[0] for t in train} & {t.rsplit('_', 1)[0] for t in dev}
    artifacts = {str(p.relative_to(R)): sha(p) for name in ['config', 'data', 'references']
                 for p in (R / name).rglob('*') if p.is_file() and p.name != 'DATA_MANIFEST.json'
                 and 'before_execution' not in p.parts}
    dump(R / 'data/DATA_MANIFEST.json', {'at_beijing': now(), 'all_steps': 11254,
         'selected_union': len(union), 'mechanical_quality_filters': False,
         'source': 'raw Qwen3-8B 540 trajectories, frozen English v6 format labels',
         'actual_training_runs': 14, 'report_condition_records': 16,
         'cache_reuse': 'read-only exact token cache verified against previous manifest',
         'artifacts': artifacts})
    print(json.dumps({'candidates': {k: len(v) for k, v in pools.items()},
                     'unique_selected': len(union), 'actual_runs': 14}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
