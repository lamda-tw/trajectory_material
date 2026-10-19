"""Independently rebuild predicates from labels and reproduce each uniform draw."""
import csv
import hashlib
import random
from experiment_utils import R, read, dump, jsonl, sha


def main():
    cfg = read(R / 'config/training.json')
    with (R / 'references/step_labels.csv').open(newline='') as handle:
        labels = list(csv.DictReader(handle))
    records = []
    for arm in cfg['arms']:
        ignored = int(arm[-1])
        # Separate implementation from prepare_data: explicit seven dimensions.
        keys = sorted(f"{r['id']}:{r['step']}" for r in labels
                      if sum(r[f'R{i}'] == 'P' for i in range(1, 9) if i != ignored) >= 3
                      and all(r[f'R{i}'] != 'F' for i in range(1, 9) if i != ignored))
        for seed in cfg['seeds']:
            folder = R / f'data/{arm}/seed_{seed}'
            actual = [r['id'] for r in jsonl(folder / 'selection.jsonl')]
            number = int(hashlib.sha256(f'{seed}:{arm}:selection'.encode()).hexdigest()[:16], 16)
            expected = random.Random(number).sample(keys, 1358)
            assert actual == expected and len(set(actual)) == 1358
            order = read(folder / 'orders.json')['orders']
            assert len(order) == 1 and sorted(order[0]) == list(range(1358))
            records.append({'arm': arm, 'seed': seed, 'candidates': len(keys),
                            'selected': len(actual), 'uniform_draw_reproduced': True})
    for seed in cfg['seeds']:
        for name in ['selection.jsonl', 'orders.json']:
            assert sha(R / f'data/drop_r7/seed_{seed}/{name}') == sha(R / f'data/drop_r5/seed_{seed}/{name}')
    dump(R / 'checks/global_sampling.json', {'passed': True, 'runs': records,
         'only_score_predicate': True, 'no_task_quotas': True, 'no_redistribution': True,
         'no_outcome_filter': True, 'no_content_deduplication': True,
         'aliases_verified': {'drop_r7': 'drop_r5'}})
    print('PASS: 14 global samples reproduced, alias data identical; no quotas or extra filters.', flush=True)


if __name__ == '__main__':
    main()
