"""DRACO static baseline on new train tasks; original protocol adaptation only."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common import (atomic_json, collection_fingerprint, digest, file_sha,
                    group_advantages, ids, input_fingerprint, load_config,
                    load_rules, read_json, rubric_rewards, validate_judgement)
import common as frozen_common
import judge_compat as judge

OUT = ROOT / 'runs/step02_static_scores/draco_baseline_newtasks_v1'
COLLECTION = ROOT / 'runs/step01_train90_rollouts'
SELECTION_PREFIX = 'static-score-v1:20261009:'


def now():
    return datetime.now(timezone.utc).isoformat()


def prepare(config):
    base_config = frozen_common.load_config()
    all_ids = ids(ROOT / config['collection']['tasks'])
    tasks = sorted(all_ids, key=lambda s: hashlib.sha256((SELECTION_PREFIX + s).encode()).hexdigest())[2:5]
    assert len(all_ids) == 90 and not set(tasks) & set(ids(ROOT / config['evaluation']['tasks']))
    index = read_json(COLLECTION / 'trajectory_index.json')
    assert len(index) == 540 and read_json(COLLECTION / 'collection_validation.json')['passed']
    rows = [row for task in tasks for row in sorted(index, key=lambda x: x['sample']) if row['task_id'] == task]
    assert len(rows) == 18
    for task in tasks:
        assert [row['sample'] for row in rows if row['task_id'] == task] == list(range(6))
    rules = load_rules(config)
    assert len(rules) == 21
    prompt_metadata = []
    for row in rows:
        path = Path(row['trajectory'])
        assert path.parent == COLLECTION / 'trajectories'
        assert file_sha(path) == row['sha256']
        trajectory = read_json(path)
        assert trajectory['public_task']['task_id'] == row['task_id']
        prompt = judge.build_prompt(config, trajectory)
        # Canary: metadata changes must not affect the evidence sent to the judge.
        altered = dict(trajectory, official_evaluation={'success': 'HIDDEN_LABEL_CANARY'},
                       job={'policy_id': 'HIDDEN_POLICY_CANARY'},
                       execution_provenance={'runtime': 'HIDDEN_RUNTIME_CANARY'})
        assert judge.build_prompt(config, altered) == prompt
        prompt_metadata.append({'task_id': row['task_id'], 'sample': row['sample'],
                                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                                'prompt_chars': len(prompt)})
    source_paths = [ROOT / 'config.json', ROOT / 'common.py', ROOT / 'judge.py', Path(__file__).resolve(), Path(__file__).with_name('judge_compat.py'),
                    ROOT / config['judge']['rules'], ROOT / config['judge']['official_prompt'],
                    ROOT / config['judge']['wrapper'], ROOT / config['judge']['schema'],
                    ROOT / config['collection']['tasks'], ROOT / config['evaluation']['tasks']]
    source_hashes = {str(p.relative_to(ROOT)): file_sha(p) for p in source_paths}
    version = subprocess.run([config['paths']['codex'], '--version'], check=True,
                             capture_output=True, text=True).stdout.strip()
    manifest = {'phase': 'step02_new_task_diagnostic', 'previous_stage': 'smoke_v2', 'initialization': 'train90_codex_sft_epoch5',
                'selection': {'method': 'sha256 ascending', 'prefix': SELECTION_PREFIX,
                              'reads_outcome_labels': False, 'slice': [2, 5], 'tasks': tasks},
                'collection_fingerprint': collection_fingerprint(base_config),
                'collection_runtime_fingerprint': input_fingerprint(base_config),
                'trajectory_index_sha256': file_sha(COLLECTION / 'trajectory_index.json'),
                'source_hashes': source_hashes, 'judge': config['judge'], 'codex_version': version,
                'group_size': 6, 'reward': '10*(P-F)/(P+F); NA excluded; keep rule iff any FAIL',
                'advantage': 'group sample std + 1e-6; equal rewards -> zero',
                'selected_trajectories': rows, 'prompts': prompt_metadata,
                'scope': {'judge_requests': 18, 'rule_verdicts': 378,
                          'new_rollouts': 0, 'optimizer_updates': 0, 'dev_rollouts': 0}}
    prior_path = ROOT / 'runs/step02_static_scores/smoke_v2/manifest.json'
    prior = read_json(prior_path)
    assert not set(tasks) & set(prior['selection']['tasks'])
    assert config['judge'] == prior['judge'], 'Freeze judge settings, not only model alias.'
    for rel, sha in prior['source_hashes'].items():
        assert file_sha(ROOT / rel) == sha, f'Previous frozen source changed: {rel}'
    manifest['previous_manifest_sha256'] = file_sha(prior_path)
    manifest['prompt_changed_from_v2'] = False
    manifest['uses_calibration_v3'] = False
    manifest['semantic_score_constraints'] = []
    manifest['judge_config_change'] = False
    manifest['audit_spec_sha256'] = file_sha(OUT / 'analysis_spec.json')
    manifest['fingerprint'] = digest(manifest)
    manifest_path = OUT / 'manifest.json'
    if manifest_path.exists():
        assert read_json(manifest_path) == manifest, 'Stage inputs changed; use a new stage version.'
    else:
        for path in source_paths:
            destination = OUT / 'source_snapshot' / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        atomic_json(manifest_path, manifest)
    return manifest, rows, rules


def summarize(config, manifest, rows, rules):
    scored = []
    for row in rows:
        uid = f"{row['task_id']}__{row['sample']:02d}"
        path = OUT / 'judgements' / uid / 'judgement.json'
        if path.exists():
            trajectory = read_json(row['trajectory'])
            result = read_json(path)
            expected = digest({'prompt': judge.build_prompt(config, trajectory), 'judge': config['judge'],
                               'schema_sha256': file_sha(ROOT / config['judge']['schema'])})
            assert result['cache_key'] == expected
            validate_judgement({'scores': result['scores']}, rules)
            scored.append((row, result))
    lookup = {(row['task_id'], row['sample']): result for row, result in scored}
    verdict_map = {-1: 'FAIL', 0: 'NA', 1: 'PASS'}
    groups = []
    trajectory_rows = []
    for task in manifest['selection']['tasks']:
        members = [row for row in rows if row['task_id'] == task]
        if any((task, row['sample']) not in lookup for row in members):
            continue
        verdicts = [[verdict_map[s['score']] for s in lookup[(task, row['sample'])]['scores']] for row in members]
        reward = rubric_rewards(verdicts, config['judge']['reward_scale'])
        advantages = group_advantages(reward['rewards'])
        outcomes = [int(row['success']) for row in members]
        group = {'task_id': task, 'samples': [row['sample'] for row in members],
                 'official_success': outcomes, **reward, 'advantages': advantages,
                 'rubric_std': statistics.stdev(reward['rewards']),
                 'outcome_std': statistics.stdev(outcomes),
                 'outcome_advantages': group_advantages(outcomes),
                 'kept_rule_titles': [rules[i]['title'] for i in reward['kept_rule_ids']]}
        groups.append(group)
        for row, verdict, r, adv in zip(members, verdicts, reward['rewards'], advantages):
            retained = [verdict[i] for i in reward['kept_rule_ids']]
            trajectory_rows.append({'task_id': task, 'sample': row['sample'],
                                    'official_success': row['success'], 'steps': row['steps'],
                                    'reward': r, 'advantage': adv,
                                    'retained_pass': retained.count('PASS'),
                                    'retained_fail': retained.count('FAIL'),
                                    'retained_na': retained.count('NA')})
    counts = Counter(verdict_map[s['score']] for _, result in scored for s in result['scores'])
    usage = Counter()
    for _, result in scored:
        usage.update({k: v for k, v in (result['audit']['usage'] or {}).items() if isinstance(v, int)})
    attempts = list((OUT / 'judgements').glob('*/events_*.jsonl'))
    summary = {'status': 'scored' if len(scored) == len(rows) else 'partial', 'updated_at_utc': now(),
               'stage_fingerprint': manifest['fingerprint'], 'selected_tasks': manifest['selection']['tasks'],
               'scored_trajectories': len(scored), 'target_trajectories': len(rows),
               'complete_groups': len(groups), 'rule_verdicts': sum(counts.values()),
               'verdict_counts': dict(counts), 'successful_call_usage': dict(usage),
               'recorded_attempt_streams': len(attempts),
               'sum_successful_call_elapsed_seconds': sum(result['elapsed_seconds'] for _, result in scored),
               'rubric_nonzero_advantage_groups': sum(g['rubric_std'] > 0 for g in groups),
               'outcome_nonzero_advantage_groups': sum(g['outcome_std'] > 0 for g in groups),
               'groups': groups, 'evidence_review': 'pending',
               'new_rollouts': 0, 'optimizer_updates': 0, 'dev_rollouts': 0}
    atomic_json(OUT / 'summary.json', summary)
    atomic_json(OUT / 'group_rewards.json', groups)
    rule_stats = [{'rule_id': i, 'title': rule['title'],
                   **dict(Counter(verdict_map[result['scores'][i]['score']] for _, result in scored))}
                  for i, rule in enumerate(rules)]
    atomic_json(OUT / 'rule_statistics.json', rule_stats)
    if trajectory_rows:
        with (OUT / 'trajectory_rewards.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(trajectory_rows[0])); writer.writeheader(); writer.writerows(trajectory_rows)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--limit', type=int, default=18)
    parser.add_argument('--workers', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    assert 1 <= args.limit <= 18
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / 'run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = load_config(); manifest, rows, rules = prepare(config)
    print(json.dumps({'prepared': len(rows), 'tasks': manifest['selection']['tasks'], 'execute': args.execute}), flush=True)
    if not args.execute:
        return
    started = time.monotonic()
    invocation = {'started_at_utc': now(), 'workers': args.workers, 'limit': args.limit}
    invocation_path = OUT / ('invocation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
    try:
        def run(row):
            uid = f"{row['task_id']}__{row['sample']:02d}"
            print(json.dumps({'starting': uid, 'time': now()}), flush=True)
            audit_dir = OUT / 'judgements' / uid
            if not (audit_dir / 'judgement.json').exists() and list(audit_dir.glob('events_*.jsonl')):
                raise RuntimeError(f'Prior failed attempts exist for {uid}; preserve and audit before retrying.')
            result = judge.score(config, read_json(row['trajectory']), audit_dir, execute=True)
            print(json.dumps({'scored': uid, 'verdicts': len(result['scores']), 'attempts': result['attempts']}), flush=True)
            return uid
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = [executor.submit(run, row) for row in rows[:args.limit]]
            for future in as_completed(pending):
                future.result()
                summary = summarize(config, manifest, rows, rules)
                print(json.dumps({'progress': summary['scored_trajectories'], 'groups': summary['complete_groups']}), flush=True)
        invocation['status'] = 'complete'
    except Exception as error:
        invocation.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        summary = summarize(config, manifest, rows, rules)
        invocation.update(finished_at_utc=now(), wall_seconds=time.monotonic()-started,
                          scored_trajectories=summary['scored_trajectories'])
        atomic_json(invocation_path, invocation)
    print(json.dumps({'status': summary['status'], 'scored': summary['scored_trajectories']}), flush=True)


if __name__ == '__main__':
    main()
