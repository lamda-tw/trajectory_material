"""Entry point: plan/preflight are safe; pilot/train/evaluate/all require --execute."""
from __future__ import annotations
import argparse
import csv
import fcntl
import json
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from common import (ROOT, atomic_json, digest, file_sha, group_advantages, ids, input_fingerprint,
                    load_config, load_rules, read_json, rubric_rewards, sample_seed, schedule)
from judge import score
from policy_server import model_name, owned_server

RUNS = ROOT / 'runs'
CHECKPOINTS = ROOT / 'checkpoints'

def prepare_runtime(config):
    runtime = ROOT / 'runtime' / 'appworld'
    runtime.mkdir(parents=True, exist_ok=True)
    source = Path(config['paths']['appworld_data'])
    target = runtime / 'data'
    if target.exists() or target.is_symlink():
        if not target.samefile(source):
            raise RuntimeError('Unexpected AppWorld runtime data link.')
    else:
        target.symlink_to(source, target_is_directory=True)
    tests = runtime / 'cache' / 'tests'
    if not tests.exists():
        shutil.copytree(config['paths']['appworld_test_cache'], tests)
    return runtime

def checkpoint_info(config, checkpoint):
    fingerprint = input_fingerprint(config)
    if checkpoint is None:
        return {'policy_id': 'base:' + fingerprint, 'fingerprint': fingerprint, 'update': 0}
    checkpoint = Path(checkpoint).resolve()
    if not checkpoint.is_relative_to(CHECKPOINTS.resolve()):
        raise ValueError('Only checkpoints from this experiment are accepted; old adapters are excluded.')
    info = read_json(checkpoint / 'manifest.json')
    if info['fingerprint'] != fingerprint:
        raise RuntimeError('Checkpoint uses changed experiment inputs.')
    for name, expected in info['files'].items():
        if file_sha(checkpoint / name) != expected:
            raise RuntimeError(f'Checkpoint file changed: {name}')
    return info

def ensure_manifest(config):
    manifest = {'fingerprint': input_fingerprint(config), 'config': config}
    target = RUNS / 'manifest.json'
    if target.exists() and read_json(target) != manifest:
        raise RuntimeError('Inputs changed after this run started. Preserve the run and create a new experiment directory.')
    atomic_json(target, manifest)
    prepare_runtime(config)
    return manifest['fingerprint']

def rollout_jobs(config, directory, task_ids, checkpoint, update=0, pilot=False, evaluation=False):
    policy = checkpoint_info(config, checkpoint)
    jobs = []
    for task in task_ids:
        count = 1 if evaluation else config['sampling']['group_size']
        for sample in range(count):
            episode_id = f"{directory.relative_to(RUNS).as_posix().replace('/', '__')}__{task}__{sample:02d}"
            output = directory / 'trajectories' / f'{task}__{sample:02d}.json'
            seed = config['evaluation']['seed'] if evaluation else sample_seed(config, update, task, sample, pilot)
            jobs.append({'mode': 'dev' if evaluation else 'train', 'task_id': task,
                         'seed': seed, 'sample': sample, 'update': update, 'episode_id': episode_id,
                         'runtime_name': 'appworld', 'model': model_name(config, checkpoint),
                         'output': str(output), 'fingerprint': policy['fingerprint'], 'policy_id': policy['policy_id']})
    return jobs

def collect_rollouts(config, jobs, directory, checkpoint=None):
    pending = []
    for job in jobs:
        output = Path(job['output'])
        if output.exists():
            if read_json(output)['job'] != job:
                raise RuntimeError('Cached rollout belongs to another policy/configuration.')
        else:
            pending.append(job)
    if pending:
        with owned_server(config, directory, checkpoint):
            for job in pending:
                job_path = directory / 'jobs' / (job['episode_id'] + '.json')
                atomic_json(job_path, job)
                log_path = job_path.with_suffix('.log')
                print(f"rollout {job['episode_id']}", flush=True)
                with log_path.open('a') as log:
                    result = subprocess.run([config['paths']['appworld_python'], str(ROOT / 'rollout_worker.py'),
                                             '--job', str(job_path), '--execute'], cwd=ROOT,
                                            stdout=log, stderr=subprocess.STDOUT,
                                            timeout=config['agent']['max_steps'] * (config['server']['request_timeout_seconds'] + 60))
                if result.returncode:
                    raise RuntimeError(f'Rollout infrastructure failed; no reward assigned. See {log_path}')
                if not Path(job['output']).exists():
                    raise RuntimeError('Worker did not commit a complete trajectory.')
    return [read_json(job['output']) for job in jobs]

def reward_groups(config, jobs, branch, directory):
    by_task = defaultdict(list)
    for job in jobs:
        by_task[job['task_id']].append(job)
    episodes, groups, all_judgements = [], [], []
    for task, task_jobs in by_task.items():
        if len(task_jobs) != config['sampling']['group_size']:
            raise ValueError('Incomplete rollout group.')
        trajectories = [read_json(job['output']) for job in task_jobs]
        if branch == 'rubric':
            verdicts = []
            for job, trajectory in zip(task_jobs, trajectories):
                result = score(config, trajectory, directory / 'judge' / Path(job['output']).stem, execute=True)
                verdicts.append([{1: 'PASS', -1: 'FAIL', 0: 'NA'}[row['score']] for row in result['scores']])
                all_judgements.append({'task': task, 'trajectory': job['output'], **result})
            reward_info = rubric_rewards(verdicts, config['judge']['reward_scale'])
        elif branch == 'outcome':
            reward_info = {'rewards': [float(t['official_evaluation']['success']) for t in trajectories], 'kept_rule_ids': []}
        else:
            raise ValueError('Unknown branch.')
        advantages = group_advantages(reward_info['rewards'], config['training']['advantage_epsilon'])
        groups.append({'task_id': task, **reward_info, 'advantages': advantages,
                       'zero_advantage': all(a == 0 for a in advantages),
                       'official_successes': sum(t['official_evaluation']['success'] for t in trajectories)})
        for job, reward, advantage in zip(task_jobs, reward_info['rewards'], advantages):
            episodes.append({'task_id': task, 'trajectory': job['output'], 'trajectory_sha256': file_sha(job['output']),
                             'reward': reward, 'advantage': advantage})
    return episodes, groups, all_judgements

def pilot(config):
    directory = RUNS / 'pilot'
    jobs = rollout_jobs(config, directory, ids(ROOT / 'assets/splits/train_pilot_8.txt'), None, pilot=True)
    collect_rollouts(config, jobs, directory)
    _, groups, judgements = reward_groups(config, jobs, 'rubric', directory)
    rule_counts = {r['title']: Counter() for r in load_rules(config)}
    audit_candidates = []
    for judgement in judgements:
        for row in judgement['scores']:
            rule_counts[row['rubric_title']][str(row['score'])] += 1
            audit_candidates.append({'task_id': judgement['task'], 'trajectory': judgement['trajectory'], **row})
    # Up to 10 from each verdict, then fill to 30 without replacement.
    ordered = sorted(audit_candidates, key=digest)
    chosen = []
    for value in (-1, 0, 1):
        chosen += [row for row in ordered if row['score'] == value][:10]
    known = {digest(row) for row in chosen}
    for row in ordered:
        if len(chosen) >= 30:
            break
        if digest(row) not in known:
            chosen.append(row)
            known.add(digest(row))
    audit_path = directory / 'audit_30.csv'
    # Preserve reviewers' notes on resume.
    if not audit_path.exists():
        with audit_path.open('w', newline='') as handle:
            fields = ['task_id', 'trajectory', 'rubric_title', 'score', 'evidence', 'justification', 'review_score', 'review_note']
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(chosen)
    report = {'trajectories': len(jobs), 'verdicts': len(jobs) * len(rule_counts), 'groups': groups,
              'rule_counts': rule_counts, 'nonzero_advantage_groups': sum(not g['zero_advantage'] for g in groups),
              'audit_file': str(audit_path), 'human_audit_complete': False,
              'note': 'Reward variance is a mechanical check, not proof that the judge is correct.'}
    atomic_json(directory / 'report.json', report)
    print(json.dumps({'pilot_trajectories': len(jobs), 'nonzero_advantage_groups': report['nonzero_advantage_groups'], 'audit_file': str(audit_path)}))
    return report

def train(config, branch):
    pilot_report = RUNS / 'pilot' / 'report.json'
    if branch == 'rubric' and (not pilot_report.exists() or read_json(pilot_report)['nonzero_advantage_groups'] == 0):
        raise RuntimeError('Run the pilot first; rubric training requires at least one nonzero-advantage pilot group.')
    previous = None
    for update in range(1, config['training']['updates'] + 1):
        checkpoint = CHECKPOINTS / branch / f'update_{update:03d}'
        directory = RUNS / branch / f'update_{update:03d}'
        batch_path = directory / 'batch.json'
        if checkpoint.exists():
            info = checkpoint_info(config, checkpoint)
            expected_parent = checkpoint_info(config, previous)['policy_id']
            if info['branch'] != branch or info['update'] != update or info['parent_policy_id'] != expected_parent or info['batch_sha256'] != file_sha(batch_path):
                raise RuntimeError('Checkpoint lineage or training batch changed.')
            previous = checkpoint
            continue
        jobs = rollout_jobs(config, directory, schedule(config, update), previous, update=update)
        collect_rollouts(config, jobs, directory, previous)
        episodes, groups, _ = reward_groups(config, jobs, branch, directory)
        batch = {'fingerprint': input_fingerprint(config), 'branch': branch, 'update': update,
                 'policy_id': checkpoint_info(config, previous)['policy_id'], 'episodes': episodes, 'groups': groups}
        atomic_json(batch_path, batch)
        command = [config['paths']['training_python'], str(ROOT / 'train_grpo.py'), '--batch', str(batch_path),
                   '--output', str(checkpoint), '--execute']
        if previous:
            command += ['--previous', str(previous)]
        print(f'train {branch} update {update}/{config["training"]["updates"]}', flush=True)
        with (directory / 'training.log').open('a') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'Training failed; see {directory / "training.log"}')
        checkpoint_info(config, checkpoint)
        previous = checkpoint
    return previous

def evaluation_metrics(trajectories, expected_ids):
    task_ids = [t['public_task']['task_id'] for t in trajectories]
    if len(task_ids) != len(set(task_ids)) or set(task_ids) != set(expected_ids):
        raise ValueError('Dev report must cover exactly the complete frozen dev split.')
    successes = {t['public_task']['task_id']: bool(t['official_evaluation']['success']) for t in trajectories}
    families = defaultdict(list)
    for task, success in successes.items():
        families[task.rsplit('_', 1)[0]].append(success)
    return {'n_tasks': len(task_ids), 'n_success': sum(successes.values()),
            'task_goal_completion': 100 * sum(successes.values()) / len(successes),
            'n_scenarios': len(families),
            'scenario_goal_completion': 100 * sum(all(v) for v in families.values()) / len(families),
            'task_success': successes}

def evaluate(config, target):
    checkpoint = None if target == 'base' else CHECKPOINTS / target / f'update_{config["training"]["updates"]:03d}'
    info = checkpoint_info(config, checkpoint)
    if target != 'base' and (info['branch'] != target or info['update'] != config['training']['updates']):
        raise ValueError('Evaluate only the preselected final checkpoint.')
    directory = RUNS / 'dev' / target
    expected = ids(ROOT / config['evaluation']['tasks'])
    jobs = rollout_jobs(config, directory, expected, checkpoint, evaluation=True)
    trajectories = collect_rollouts(config, jobs, directory, checkpoint)
    metrics = evaluation_metrics(trajectories, expected)
    metrics.update(policy_id=info['policy_id'], fingerprint=info['fingerprint'], split='official_dev')
    atomic_json(directory / 'metrics.json', metrics)
    print(json.dumps({k: v for k, v in metrics.items() if k != 'task_success'}))
    return metrics

def comparison():
    reports = {name: read_json(RUNS / 'dev' / name / 'metrics.json') for name in ('base', 'outcome', 'rubric') if (RUNS / 'dev' / name / 'metrics.json').exists()}
    atomic_json(RUNS / 'comparison.json', reports)
    if reports:
        with (RUNS / 'comparison.csv').open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['model', 'n_tasks', 'n_success', 'TGC_percent', 'SGC_percent'])
            for name, report in reports.items():
                writer.writerow([name, report['n_tasks'], report['n_success'], report['task_goal_completion'], report['scenario_goal_completion']])

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', nargs='?', default='plan', choices=['plan', 'preflight', 'pilot', 'train', 'evaluate', 'all', 'report'])
    ap.add_argument('--branch', choices=['outcome', 'rubric'])
    ap.add_argument('--model', choices=['base', 'outcome', 'rubric'], default='base')
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    config = load_config()
    if args.command == 'plan':
        print(json.dumps({'status': 'prepared_only', 'pilot_rollouts': 48, 'training_rollouts_per_branch': 120,
                          'dev_tasks_per_model': len(ids(ROOT / config['evaluation']['tasks'])),
                          'updates': config['training']['updates'], 'base_model': config['paths']['base_model'],
                          'judge': config['judge']['model'], 'train_schedule': [schedule(config, i) for i in range(1, 11)]}, indent=2))
        return
    if args.command == 'preflight':
        from preflight import run
        run(config)
        return
    if args.command == 'report':
        comparison()
        return
    if not args.execute:
        ap.error('Experiment execution is disabled. Wait for “开始实验”, then add --execute.')
    if args.command == 'train' and not args.branch:
        ap.error('train requires --branch outcome or --branch rubric.')
    # Single orchestrator owns server, sampling and checkpoint writes.
    RUNS.mkdir(exist_ok=True)
    with (RUNS / '.execution.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another experiment command is already running.')
        ensure_manifest(config)
        if args.command == 'pilot':
            pilot(config)
        elif args.command == 'train':
            train(config, args.branch)
        elif args.command == 'evaluate':
            evaluate(config, args.model)
        elif args.command == 'all':
            pilot(config)
            evaluate(config, 'base')
            for branch in ('outcome', 'rubric'):
                train(config, branch)
                evaluate(config, branch)
            comparison()

if __name__ == '__main__':
    main()
