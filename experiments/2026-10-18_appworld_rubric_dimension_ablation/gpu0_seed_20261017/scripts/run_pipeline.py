"""Explicitly authorized serial GPU0 SFT/DEV57 runner, with durable node updates."""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from experiment_utils import R, W, now, read, dump, sha
from update_readme_progress import refresh


def gpu_info():
    line = subprocess.check_output(['nvidia-smi', '--id=0',
        '--query-gpu=uuid,pci.bus_id,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], text=True)
    uuid, pci, memory, utilization = [s.strip() for s in line.strip().split(',')]
    return {'uuid': uuid, 'pci': pci, 'memory_used_mib': int(memory), 'utilization_percent': int(utilization)}


def require_idle(uuid):
    # Allow delayed release by our immediately preceding process, never preempt anyone.
    for _ in range(30):
        info = gpu_info()
        assert info['uuid'] == uuid and info['pci'] == '00000000:B8:00.0', info
        if info['memory_used_mib'] < 500:
            return info
        time.sleep(2)
    raise RuntimeError(f'GPU0 occupied; refusing to preempt any process: {info}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assert args.execute
    plan = read(R / 'config/experiment_plan.json')
    cfg = read(R / 'config/training.json')
    ec = read(R / 'config/evaluation.json')
    assert plan['execution_authorized']
    assert cfg['seeds'] == [20261017]
    assert cfg['arms'] == [f'drop_r{i}' for i in [1, 2, 3, 4, 5, 6, 8]]
    assert cfg['samples_per_epoch'] == 1358 and cfg['updates_per_epoch'] == 679 and cfg['epochs'] == 1
    assert plan['aliases'] == {'drop_r7': 'drop_r5'}
    assert cfg['gpu_uuid'] == 'GPU-2044de33-9504-3cdf-451a-e9196cbdb21a'
    lock = (W / plan['resources']['lock_path']).open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    own = (R / 'runtime/pipeline.lock').open('a+')
    fcntl.flock(own, fcntl.LOCK_EX | fcntl.LOCK_NB)
    start_gpu = require_idle(cfg['gpu_uuid'])
    for check in ['loss_math.json', 'data_validation.json', 'global_sampling.json']:
        assert read(R / 'checks' / check)['passed'], check
    for rel, expected in read(R / 'data/DATA_MANIFEST.json')['artifacts'].items():
        assert sha(R / rel) == expected, rel
    frozen = R / 'EXECUTION_MANIFEST.json'
    if frozen.exists():
        for rel, expected in read(frozen)['files'].items():
            assert sha(R / rel) == expected, rel
    else:
        paths = [p for directory in ['scripts', 'runtime_code', 'config', 'checks']
                 for p in (R / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        paths += [R / 'data/DATA_MANIFEST.json', R / 'runtime/execution_scope.json',
                  R / 'references/approved_plan_snapshot.md']
        dump(frozen, {'at_beijing': now(), 'user_authorized': True,
             'files': {str(p.relative_to(R)): sha(p) for p in paths},
             'training_arms': cfg['arms'], 'seeds': cfg['seeds'], 'aliases': plan['aliases'],
             'steps_per_run': 1358, 'updates_per_run': 679, 'epochs': 1,
             'score_only': True, 'no_quality_filters': True, 'single_gpu': cfg['gpu_uuid']})
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=cfg['gpu_uuid'], CUDA_DEVICE_ORDER='PCI_BUS_ID',
        WORLD_SIZE='1', LOCAL_WORLD_SIZE='1', LOCAL_RANK='0', RANK='0', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4',
        PYTHONUNBUFFERED='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false',
        PYTHONDONTWRITEBYTECODE='1', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
    state = {'phase': 'running', 'execution_authorized': True, 'pid': os.getpid(),
             'started_at': now(), 'physical_gpu': 0, 'gpu_uuid': cfg['gpu_uuid'], 'start_gpu': start_gpu,
             'stage': 'starting', 'seeds': cfg['seeds'], 'training_arms': cfg['arms'],
             'same_state_diagnostics': 'not_started'}
    stop = threading.Event()
    mutex = threading.RLock()
    observer_errors = []

    def publish(**changes):
        with mutex:
            state.update(changes)
            state['heartbeat_at'] = now()
            dump(R / 'runtime/pipeline_state.json', dict(state))
        refresh()

    def heartbeat():
        while not stop.wait(15):
            try:
                publish()
            except BaseException as error:
                observer_errors.append(repr(error))
                dump(R / 'runtime/progress_error.json', {'at': now(), 'error': repr(error)})

    def interrupted(signum, _frame):
        raise KeyboardInterrupt(f'pipeline received signal {signum}')

    signal.signal(signal.SIGTERM, interrupted)
    publish()
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

    def stage(name, command, gpu=False):
        if observer_errors:
            raise RuntimeError(f'Progress publication failed: {observer_errors[-1]}')
        if gpu:
            require_idle(cfg['gpu_uuid'])
        log = R / 'logs' / f'{name}.log'
        publish(stage=name, stage_started_at=now(), active_log=str(log))
        with log.open('a') as handle:
            child = subprocess.Popen(command, cwd=R, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                     start_new_session=True, pass_fds=(lock.fileno(), own.fileno()))
            publish(child_pid=child.pid)
            try:
                while child.poll() is None:
                    if observer_errors:
                        raise RuntimeError(f'Progress publication failed: {observer_errors[-1]}')
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        continue
                code = child.returncode
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)
                    try:
                        child.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                publish(child_pid=None)
        if code:
            raise RuntimeError(f'{name} exited {code}; inspect {log}. No recipe/data changes applied.')
        publish(last_completed_stage=name)

    def register_alias(seed):
        source = R / f'training/drop_r5/seed_{seed}'
        evaluation = R / f'evaluation/drop_r5/seed_{seed}/epoch_01'
        assert read(source / 'epoch_01.json')['samples'] == 1358
        assert read(evaluation / 'SUMMARY.json')['tasks'] == 57
        files = [source / 'INITIALIZATION.json', source / 'epoch_01.json',
                 source / 'epoch_01_adapter/adapter_model.safetensors', evaluation / 'SUMMARY.json',
                 R / f'data/drop_r5/seed_{seed}/selection.jsonl', R / f'data/drop_r5/seed_{seed}/orders.json']
        dump(R / f'aliases/drop_r7/seed_{seed}.json', {'at_beijing': now(), 'alias_of': 'drop_r5',
             'seed': seed, 'independent_run': False, 'candidate_sets_identical': True,
             'source_training': str(source.relative_to(R)), 'source_evaluation': str(evaluation.relative_to(R)),
             'source_files': {str(p.relative_to(R)): sha(p) for p in files}})
        publish(stage=f'register_alias_drop_r7_{seed}')

    try:
        probe = R / 'probe/drop_r1/seed_20261017/COMPLETE.json'
        if not probe.exists():
            stage('probe', [cfg['training_python'], '-u', str(R / 'scripts/train.py'),
                           '--arm', 'drop_r1', '--seed', '20261017', '--probe'], gpu=True)
        assert read(probe)['probe'] and read(probe)['samples'] == 2
        serving = R / 'checks/serving_preflight.json'
        if not serving.exists():
            stage('serving_preflight', [ec['paths']['appworld_python'], '-u',
                  str(R / 'scripts/preflight_serving.py'), '--execute'], gpu=True)
        assert read(serving)['passed'] and read(serving)['evaluation_config_sha256'] == sha(R / 'config/evaluation.json')
        for seed in cfg['seeds']:
            for arm in cfg['arms']:
                publish(arm=arm, seed=seed, target_epoch=1)
                folder = R / f'training/{arm}/seed_{seed}'
                if not (folder / 'epoch_01.json').exists():
                    stage(f'train_{arm}_{seed}', [cfg['training_python'], '-u', str(R / 'scripts/train.py'),
                          '--arm', arm, '--seed', str(seed), '--until-epoch', '1'], gpu=True)
                complete = read(folder / 'epoch_01.json')
                assert complete['samples'] == 1358 and complete['updates'] == 679 and not complete['probe']
                for name, expected in complete['adapter_files'].items():
                    assert sha(folder / 'epoch_01_adapter' / name) == expected
                init = read(folder / 'INITIALIZATION.json')
                for other in cfg['arms']:
                    path = R / f'training/{other}/seed_{seed}/INITIALIZATION.json'
                    if path.exists():
                        assert read(path)['initial_adapter_tensor_sha256'] == init['initial_adapter_tensor_sha256']
                evaluation = R / f'evaluation/{arm}/seed_{seed}/epoch_01/SUMMARY.json'
                if not evaluation.exists():
                    stage(f'eval_{arm}_{seed}', [ec['paths']['appworld_python'], '-u', str(R / 'scripts/evaluate.py'),
                          '--arm', arm, '--seed', str(seed), '--epoch', '1', '--execute'], gpu=True)
                assert read(evaluation)['policy_id'] == sha(folder / 'epoch_01_adapter/adapter_model.safetensors')
                if arm == 'drop_r5':
                    register_alias(seed)
                stage('summarize', [sys.executable, str(R / 'scripts/summarize.py')])
        result = {'phase': 'training_eval_complete', 'finished_at': now(), 'actual_training_runs': 7,
                  'samples_per_run': 1358, 'updates_per_run': 679, 'epochs': 1, 'seeds': cfg['seeds'],
                  'aliases': plan['aliases'], 'same_state_diagnostics': 'not_started'}
        dump(R / 'TRAINING_EVAL_COMPLETE.json', result)
        publish(**result, stage='training_eval_complete', active_log=None)
    except BaseException as error:
        publish(phase='error', error=repr(error), traceback=traceback.format_exc(), finished_at=now())
        raise
    finally:
        stop.set()
        thread.join(timeout=20)
        publish()


if __name__ == '__main__':
    main()
