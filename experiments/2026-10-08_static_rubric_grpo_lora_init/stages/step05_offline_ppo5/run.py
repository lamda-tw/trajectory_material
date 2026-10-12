"""Prepare now. Only explicit --execute starts future scoring or training."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import pipeline as p
from prepare import prepare


def recover_completed(job, folder):
    """Keep the earliest valid completed response after an interrupted scorer."""
    cfg = p.load_config()
    prompt = p.judge.build_prompt(cfg, p.read_json(job['output']))
    if not (folder / 'prompt.txt').exists():
        return False
    if (folder / 'prompt.txt').read_text() != prompt:
        raise ValueError('Existing request belongs to another prompt.')
    for events in sorted(folder.glob('events_*.jsonl'), key=lambda x: int(x.stem.split('_')[-1])):
        attempt = int(events.stem.split('_')[-1])
        response = folder / f'response_{attempt}.json'
        if not response.exists():
            continue
        try:
            stream = events.read_text()
            audit = p.judge.audit_events(stream)
            scores = p.validate_judgement(p.read_json(response), p.load_rules(cfg))
            messages = [e['item']['text'] for line in stream.splitlines() if line.strip()
                        and (e := json.loads(line)).get('type') == 'item.completed'
                        and e.get('item', {}).get('type') == 'agent_message']
            if not messages or json.loads(messages[-1]) != {'scores': scores}:
                continue
        except (ValueError, KeyError):
            continue
        p.atomic_json(folder / 'judgement.json', {
            'cache_key': p.digest({'prompt': prompt, 'judge': cfg['judge'],
                                  'schema_sha256': p.file_sha(p.ROOT / cfg['judge']['schema'])}),
            'scores': scores, 'audit': audit, 'attempts': attempt,
            'model': cfg['judge']['model'], 'reasoning_effort': cfg['judge']['reasoning_effort'],
            'started_at_utc': datetime.fromtimestamp((folder / 'prompt.txt').stat().st_mtime,
                                                     timezone.utc).isoformat(),
            'recovered_earliest_completed_response': True})
        return True
    return False


def score_one(job, directory):
    path = p.judgement_path(job, directory)
    if not path.exists():
        folder = path.parent
        folder.mkdir(parents=True, exist_ok=True)
        if not recover_completed(job, folder):
            # An explicit restart can retry technical failures, preserving every old log.
            old = [x for x in folder.iterdir() if x.name != 'technical_failures']
            if old:
                archive = folder / 'technical_failures'
                archive.mkdir(exist_ok=True)
                attempt_dir = archive / f'invocation_{len(list(archive.iterdir())) + 1:04d}'
                attempt_dir.mkdir(exist_ok=False)
                for item in old:
                    shutil.move(str(item), str(attempt_dir / item.name))
            p.judge.score(p.load_config(), p.read_json(job['output']), folder, execute=True)
    p.validated_scores(job, directory)
    print(json.dumps({'scored': Path(job['output']).stem}), flush=True)


def score_all(jobs, directory):
    iterator = iter(jobs)
    workers = p.settings()['judge_workers']
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = set()
        for _ in range(workers):
            job = next(iterator, None)
            if job is not None:
                futures.add(pool.submit(score_one, job, directory))
        while futures:
            done, futures = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
            for _ in done:
                job = next(iterator, None)
                if job is not None:
                    futures.add(pool.submit(score_one, job, directory))


def build_batch(jobs, directory):
    batch = p.build_batch(jobs, directory, 'rubric', 1)
    p.save_once(directory / 'batch.json', batch)
    p.atomic_json(directory / 'reward_summary.json', {
        'groups': 90, 'trajectories': 540, 'groups_with_nonzero_advantage':
        sum(any(a != 0 for a in g['advantages']) for g in batch['groups']),
        'group_rewards': batch['groups'], 'optimizer_steps': 0})
    return directory / 'batch.json'


def train_five_epochs(batch_path):
    p.validate_batch(batch_path)
    for epoch in range(1, 6):
        checkpoint = p.checkpoint_path('rubric', epoch)
        if checkpoint.exists():
            info = p.policy_info('rubric', epoch)
            if info['batch_sha256'] != p.file_sha(batch_path):
                raise ValueError('All epochs must use the same immutable dataset.')
            print(json.dumps({'already_complete_epoch': epoch}), flush=True)
            continue
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        p.atomic_json(p.RUN / 'status.json', {'phase': 'training', 'epoch': epoch,
                                             'target_epochs': 5, 'batch': str(batch_path)})
        with (checkpoint.parent / 'training.log').open('a') as log:
            subprocess.run([p.load_config()['paths']['training_python'], str(p.STAGE / 'train.py'),
                            '--batch', str(batch_path), '--output', str(checkpoint),
                            '--epoch', str(epoch), '--execute', '--allow-gpu'],
                           cwd=p.ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({'epoch': epoch, 'checkpoint': str(checkpoint),
                          'metrics': p.policy_info('rubric', epoch)['metrics']}), flush=True)
    p.atomic_json(p.RUN / 'status.json', {'phase': 'training_complete', 'completed_epochs': 5,
                                         'optimizer_steps': 5, 'new_rollouts': 0})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['prepare', 'score', 'build-batch', 'train'])
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--allow-gpu', action='store_true', help='Use only after the user explicitly releases the GPU hold.')
    args = ap.parse_args()
    if args.allow_gpu and args.command != 'train':
        ap.error('--allow-gpu is valid only for train.')
    if args.command == 'train' and args.execute and not args.allow_gpu:
        ap.error('GPU use is on hold. A new user instruction and --allow-gpu are required.')
    p.RUN.mkdir(parents=True, exist_ok=True)
    with (p.RUN / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # The earlier, frozen scorer can finish first; never score the same data concurrently.
        shared = None
        if args.command == 'score' and args.execute:
            p.atomic_json(p.RUN / 'status.json', {'phase': 'waiting_for_existing_scorer',
                                                 'gpu_training': 'on_hold'})
            shared = (p.ROOT / 'runs/step04_train90_single_update_v1/run.lock').open('a')
            fcntl.flock(shared, fcntl.LOCK_EX)
        _, status = prepare()
        print(json.dumps({k: v for k, v in status.items() if k != 'cached_scores'}, indent=2), flush=True)
        if args.command == 'prepare' or (args.command != 'build-batch' and not args.execute):
            return
        directory = p.RUN / 'fixed_batch'
        directory.mkdir(parents=True, exist_ok=True)
        jobs = p.read_json(p.RUN / 'jobs.json')
        if args.command == 'score':
            p.atomic_json(p.RUN / 'status.json', {'phase': 'scoring', 'target_trajectories': 540,
                                                 'gpu_training': 'on_hold'})
            score_all(jobs, directory)
        if args.command in {'score', 'build-batch'}:
            batch_path = build_batch(jobs, directory)
            p.atomic_json(p.RUN / 'status.json', {'phase': 'scoring_complete_training_on_hold',
                         'scored_trajectories': 540, 'groups': 90, 'batch': str(batch_path),
                         'completed_epochs': 0, 'optimizer_steps': 0, 'gpu_training': 'on_hold'})
        if args.command == 'train':
            train_five_epochs(directory / 'batch.json')
        if shared is not None:
            shared.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        p.atomic_json(p.RUN / 'last_error.json', failure)
        p.atomic_json(p.RUN / 'status.json', {'phase': 'failed', 'error': failure})
        raise
