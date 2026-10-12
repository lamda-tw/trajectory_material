"""prepare / score / cycle / evaluate. Only --execute starts models or judges."""
from __future__ import annotations
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
import fcntl
import json
from pathlib import Path
import subprocess
import pipeline as p


def fresh_jobs(branch, update, directory, evaluation=False):
    from common import sample_seed
    cfg = p.load_config()
    parent = p.policy_info(branch, update - 1)
    tasks = p.ids(p.ROOT / cfg['evaluation']['tasks']) if evaluation else p.tasks_for(update)
    jobs = []
    for task in tasks:
        for sample in range(1 if evaluation else 6):
            episode = f"draco_framework__{branch}__{update:03d}__{'dev' if evaluation else 'train'}__{task}__{sample:02d}"
            jobs.append({'mode': 'dev' if evaluation else 'train', 'task_id': task, 'sample': sample,
                         'seed': cfg['evaluation']['seed'] if evaluation else sample_seed(cfg, update, task, sample),
                         'update': update, 'episode_id': episode, 'runtime_name': 'appworld',
                         'model': cfg['server']['adapter_name'],
                         'output': str(directory / 'trajectories' / f'{task}__{sample:02d}.json'),
                         'fingerprint': p.collection_fingerprint(cfg), 'policy_id': parent['policy_id'],
                         'framework_fingerprint': p.identity()})
    return jobs


def collect(jobs, directory, checkpoint):
    from policy_server import owned_server
    cfg = p.load_config()
    cfg['server']['gpu'] = p.settings()['execution_gpu']
    pending = []
    for job in jobs:
        if Path(job['output']).exists():
            if p.read_json(job['output'])['job'] != job:
                raise ValueError('Existing rollout has a different policy identity.')
        else:
            pending.append(job)
    if not pending:
        return
    def rollout(job):
        job_path = directory / 'jobs' / (job['episode_id'] + '.json')
        p.save_once(job_path, job)
        with job_path.with_suffix('.log').open('a') as log:
            subprocess.run([cfg['paths']['appworld_python'], str(p.ROOT / 'rollout_worker.py'),
                            '--job', str(job_path), '--execute'], cwd=p.ROOT,
                           stdout=log, stderr=subprocess.STDOUT, check=True,
                           timeout=cfg['agent']['max_steps'] * (cfg['server']['request_timeout_seconds'] + 60))
        if not Path(job['output']).exists():
            raise ValueError('Rollout did not commit an output.')
        print(json.dumps({'rollout_complete': job['episode_id']}), flush=True)
    with owned_server(cfg, directory, checkpoint):
        with ThreadPoolExecutor(max_workers=p.settings()['rollout_workers']) as pool:
            for future in as_completed([pool.submit(rollout, job) for job in pending]):
                future.result()


def score(jobs, directory):
    cfg = p.load_config()
    def one(job):
        path = p.judgement_path(job, directory)
        if not path.exists():
            p.judge.score(cfg, p.read_json(job['output']), path.parent, execute=True)
        p.validated_scores(job, directory)
        print(json.dumps({'scored': Path(job['output']).stem}), flush=True)
    iterator = iter(jobs)
    with ThreadPoolExecutor(max_workers=p.settings()['judge_workers']) as pool:
        futures = set()
        for _ in range(p.settings()['judge_workers']):
            job = next(iterator, None)
            if job is not None:
                futures.add(pool.submit(one, job))
        while futures:
            done, futures = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
            for _ in done:
                job = next(iterator, None)
                if job is not None:
                    futures.add(pool.submit(one, job))


def score_all_initial():
    directory = p.RUN / 'initial_train90_scores'
    groups = []
    for task in p.task_order():
        jobs = p.initial_jobs([task])
        score(jobs, directory)
        verdicts = [[{1: 'PASS', -1: 'FAIL', 0: 'NA'}[s['score']]
                     for s in p.validated_scores(j, directory)[1]['scores']] for j in jobs]
        reward = p.rubric_rewards(verdicts, p.load_config()['judge']['reward_scale'])
        groups.append({'task_id': task, **reward, 'advantages': p.group_advantages(reward['rewards'])})
        p.atomic_json(directory / 'summary.json', {'scored_trajectories': len(groups) * 6,
                      'complete_groups': len(groups), 'target_trajectories': 540,
                      'optimizer_updates': 0, 'groups': groups})


def cycle(branch, updates):
    cfg = p.load_config()
    for update in range(1, updates + 1):
        directory = p.RUN / branch / f'update_{update:03d}'
        checkpoint = p.checkpoint_path(branch, update)
        batch_path = directory / 'batch.json'
        if checkpoint.exists():
            info = p.policy_info(branch, update)
            if info['batch_sha256'] != p.file_sha(batch_path):
                raise ValueError('Committed checkpoint training batch changed.')
            p.validate_batch(batch_path)
            continue
        parent = p.policy_info(branch, update - 1)
        jobs = p.initial_jobs(p.tasks_for(update)) if update == 1 else fresh_jobs(branch, update, directory)
        if update > 1:
            collect(jobs, directory, parent['path'])
        if branch == 'rubric':
            score(jobs, directory)
        p.save_once(batch_path, p.build_batch(jobs, directory, branch, update))
        with (directory / 'training.log').open('a') as log:
            subprocess.run([cfg['paths']['training_python'], str(p.STAGE / 'train.py'),
                            '--batch', str(batch_path), '--output', str(checkpoint), '--execute'],
                           cwd=p.ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({'checkpoint': str(checkpoint), 'metrics': p.policy_info(branch, update)['metrics']}), flush=True)


def evaluate(branch, update):
    cfg = p.load_config()
    parent = p.policy_info(branch, update)
    directory = p.RUN / branch / f'dev_update_{update:03d}'
    jobs = fresh_jobs(branch, update + 1, directory, evaluation=True)
    collect(jobs, directory, parent['path'])
    trajectories = [p.read_json(job['output']) for job in jobs]
    expected = p.ids(p.ROOT / cfg['evaluation']['tasks'])
    successes = {t['public_task']['task_id']: bool(t['official_evaluation']['success']) for t in trajectories}
    if len(trajectories) != 57 or set(successes) != set(expected):
        raise ValueError('Evaluation must include exactly dev57.')
    families = {}
    for task, success in successes.items():
        families.setdefault(task.rsplit('_', 1)[0], []).append(success)
    metrics = {'policy_id': parent['policy_id'], 'n_tasks': 57, 'n_success': sum(successes.values()),
               'TGC': sum(successes.values()) / 57,
               'SGC': sum(all(v) for v in families.values()) / len(families),
               'task_success': successes, 'rubric_judge_calls': 0}
    p.save_once(directory / 'metrics.json', metrics)
    print(json.dumps(metrics), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['prepare', 'score', 'cycle', 'evaluate'])
    ap.add_argument('--branch', choices=['rubric', 'outcome'], default='rubric')
    ap.add_argument('--updates', type=int, default=1)
    ap.add_argument('--checkpoint-update', type=int, default=0)
    ap.add_argument('--all-train', action='store_true', help='Score all 540 frozen initial trajectories; does not train.')
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    if args.all_train and args.command != 'score':
        ap.error('--all-train is valid only for score.')
    if args.updates < 1 or args.checkpoint_update < 0:
        ap.error('Invalid update count.')
    manifest = p.prepare()
    if args.command == 'prepare' or not args.execute:
        print(json.dumps({'prepared': manifest, 'execute': False}, ensure_ascii=False, indent=2))
        return
    # Shared lock covers the entire collect->score->train cycle and dev evaluation.
    lock = (p.RUN / 'run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.command == 'cycle':
        cycle(args.branch, args.updates)
    elif args.command == 'score':
        if args.all_train:
            score_all_initial()
        else:
            score(p.initial_jobs(p.tasks_for(1)), p.RUN / args.branch / 'update_001')
    else:
        evaluate(args.branch, args.checkpoint_update)


if __name__ == '__main__':
    main()
