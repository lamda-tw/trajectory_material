"""Read-only train diagnostics; missing LoRA data is pending, never a zero score."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from common import ROOT, atomic_json, digest, file_sha, ids, load_config, read_json
from initial_policy import DIRECTORY, verify_raw_reference

def describe(directory, expected_tasks):
    path = directory / 'trajectory_index.json'
    if not path.exists():
        return {'status': 'NOT_COLLECTED', 'completed_rollouts': 0}
    rows = read_json(path)
    groups, actions = defaultdict(list), defaultdict(set)
    for row in rows:
        if row['task_id'] not in expected_tasks or file_sha(row['trajectory']) != row['sha256']:
            raise ValueError('Unexpected task or modified trajectory.')
        groups[row['task_id']].append(row)
        record = read_json(row['trajectory'])
        actions[row['task_id']].add(digest([step['code'] for step in record['steps']]))
    if len(rows) != 540 or set(groups) != set(expected_tasks) or any(
            sorted(r['sample'] for r in group) != list(range(6)) for group in groups.values()):
        return {'status': 'INCOMPLETE', 'completed_rollouts': len(rows)}
    hist = Counter(sum(r['success'] for r in group) for group in groups.values())
    return {'status': 'COMPLETE', 'completed_rollouts': 540,
            'official_successful_rollouts': sum(r['success'] for r in rows),
            'official_success_fraction_train_sampling': sum(r['success'] for r in rows) / 540,
            'all_fail_groups': hist[0], 'mixed_outcome_groups': sum(hist[i] for i in range(1, 6)),
            'all_success_groups': hist[6], 'success_count_histogram': {str(i): hist[i] for i in range(7)},
            'total_steps': sum(r['steps'] for r in rows),
            'generated_tokens': sum(r['generated_tokens'] for r in rows),
            'mean_distinct_code_sequences_per_group': sum(map(len, actions.values())) / 90,
            'rubric_nonzero_advantage_groups': None,
            'rubric_status': 'NOT_SCORED_BY_THIS_STAGE'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    config = load_config()
    verify_raw_reference(config)
    tasks = ids(ROOT / config['collection']['tasks'])
    raw = Path(config['comparison']['raw_experiment']) / config['comparison']['raw_collection']
    report = {'scope': 'train sampling diagnostics, not dev generalization',
              'raw': describe(raw, tasks), 'lora': describe(DIRECTORY, tasks),
              'interpretation': 'All-fail outcome groups can still vary under rubric rewards; rubric metrics await actual scoring.'}
    if args.write:
        atomic_json(ROOT / 'preparation/collection_comparison.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
