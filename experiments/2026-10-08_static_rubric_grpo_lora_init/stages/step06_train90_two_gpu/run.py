"""Launch both gradient workers, then commit exactly one shared policy update."""
import argparse
import fcntl
import importlib.metadata
import json
import os
import signal
import subprocess
import time
import two_gpu as q


def wait_for_gpus(gpus):
    while True:
        snapshots = [q.gpu_info(gpu) for gpu in gpus]
        if all(x['ready'] for x in snapshots):
            return
        q.status('waiting_gpu', resources=snapshots)
        time.sleep(30)


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def evaluate_target(manifest):
    info = q.checkpoint_info(manifest)
    cfg = q.p.load_config()
    q.p.atomic_json(q.RUN / 'evaluation_target.json', {
        'ready_for_evaluation': True, 'base_model': cfg['paths']['base_model'],
        'tokenizer': cfg['paths']['base_model'], 'adapter': str(q.RUN / 'checkpoint'),
        'policy_id': info['policy_id'], 'checkpoint_manifest': str(q.RUN / 'checkpoint/manifest.json'),
        'artifact_type': 'PEFT LoRA adapter; load with the Qwen3-8B base model',
        'adapter_files': {k: v for k, v in info['files'].items() if k != 'optimizer.pt'},
        'batch': str(q.BATCH), 'batch_sha256': manifest['batch_sha256'],
        'training_groups': 90, 'training_trajectories': 540, 'optimizer_steps': 1, 'ppo_epochs': 1,
        'gpus': ['0', '1'], 'enable_thinking': False, 'evaluation_executed': False,
        'created_at': q.stamp(), 'metrics': info['metrics']})
    q.status('complete', optimizer_steps=1, checkpoint=str(q.RUN / 'checkpoint'),
             evaluation_target=str(q.RUN / 'evaluation_target.json'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    if not args.execute:
        _, manifest = q.prepare()
        print(json.dumps({k: v for k, v in manifest.items() if k not in {'assignments', 'group_assignments'}}, indent=2))
        return
    def interrupted(signum, frame):
        raise InterruptedError('Training controller received a termination signal.')
    signal.signal(signal.SIGTERM, interrupted)
    q.RUN.mkdir(parents=True, exist_ok=True)
    children = []
    with (q.RUN / 'run.lock').open('a') as lock, (q.p.RUN / 'run.lock').open('a') as previous_lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(previous_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            batch, manifest = q.load_input()
            if (q.p.RUN / 'rubric/update_001/checkpoint').exists():
                raise ValueError('The old single-GPU execution already committed an update.')
            q.p.atomic_json(q.RUN / 'process.json', {'pid': os.getpid(), 'started_at': q.stamp(),
                'command': [q.p.load_config()['paths']['training_python'], str(q.STAGE / 'run.py'), '--execute']})
            if (q.RUN / 'checkpoint').exists():
                evaluate_target(manifest)
                return
            q.p.atomic_json(q.RUN / 'environment.json', {
                name: importlib.metadata.version(name) for name in ('torch', 'transformers', 'peft')})
            pending = []
            for rank in range(2):
                if (q.worker_dir(rank) / 'complete.json').exists():
                    q.completed_worker(rank, manifest)
                else:
                    pending.append(rank)
            wait_for_gpus([str(rank) for rank in pending])
            python = q.p.load_config()['paths']['training_python']
            for rank in pending:
                folder = q.worker_dir(rank)
                folder.mkdir(parents=True, exist_ok=True)
                command = [python, '-u', str(q.STAGE / 'worker.py'), '--rank', str(rank)]
                with (folder / 'training.log').open('a') as log:
                    child = subprocess.Popen(command, cwd=q.STAGE, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                children.append(child)
                q.p.atomic_json(folder / 'process.json', {'pid': child.pid, 'rank': rank, 'command': command, 'started_at': q.stamp()})
            while any(child.poll() is None for child in children):
                failures = [child.returncode for child in children if child.poll() not in (None, 0)]
                if failures:
                    raise RuntimeError(f'Gradient worker exited with errors: {failures}; see worker logs.')
                q.status('parallel_backward', optimizer_steps=0)
                time.sleep(15)
            if any(child.returncode != 0 for child in children):
                raise RuntimeError('A gradient worker failed; no optimizer update will run.')
            for rank in range(2):
                q.completed_worker(rank, manifest)
            wait_for_gpus(['0'])
            with (q.RUN / 'finalize.log').open('a') as log:
                child = subprocess.Popen([python, '-u', str(q.STAGE / 'finalize.py')],
                    cwd=q.STAGE, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            children.append(child)
            while child.poll() is None:
                q.status('merging_and_updating', optimizer_steps_committed=0)
                time.sleep(15)
            if child.returncode != 0:
                raise RuntimeError('Final update or checkpoint verification failed; see finalize.log.')
            evaluate_target(manifest)
        except BaseException as error:
            stop_children(children)
            q.status('failed', error=f'{type(error).__name__}: {error}')
            raise


if __name__ == '__main__':
    main()
