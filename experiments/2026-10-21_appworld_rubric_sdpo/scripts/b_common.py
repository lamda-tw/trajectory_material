"""Phase B helpers. Importing this module starts no work."""
from common import R, W, read, write_json, frozen_json, digest, now
from a_common import file_sha, require_free_gpu, GPU, CPU
from contextlib import contextmanager
from pathlib import Path
import fcntl
import os

B = R / 'phase_b'


def config():
    return read(B / 'config/run.json')


def check_preparation():
    manifest = read(B / 'config/preparation_manifest.json')
    for name, expected in manifest['files'].items():
        if file_sha(R / name) != expected:
            raise ValueError(f'Phase B prepared dependency changed: {name}')


def authorize(capability):
    gate = read(B / 'config/execution_gate.json')
    if not gate.get(capability, False):
        raise PermissionError(f'Phase B {capability} is disabled: user requested preparation only. No work started.')
    assert gate['physical_gpu'] == 1 and gate['gpu_uuid'] == GPU
    check_preparation()


def run_dir(arm):
    assert arm in ('mixed', 'sft')
    return B / 'runs' / arm


def status(stage, **values):
    write_json(B / 'STATUS.json', {'updated_at': now(), 'stage': stage, **values})


@contextmanager
def gpu_lock(capability):
    authorize(capability)
    path = W / 'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_free_gpu(GPU, config()['server']['minimum_free_gpu_gib'])
        overrides={'CUDA_VISIBLE_DEVICES':GPU,'USE_TORCH':'1','USE_TF':'0'}
        old={key:os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        try:
            yield
        finally:
            for key,value in old.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
            fcntl.flock(handle, fcntl.LOCK_UN)


def batch_dir(arm, number):
    assert 1 <= number <= len(read(B / 'config/schedule.json')['batches'])
    return run_dir(arm) / f'batch_{number:03d}'


def previous_checkpoint(arm, number):
    if number == 1:
        return None
    folder = batch_dir(arm, number - 1) / 'checkpoint'
    saved = read(folder / 'COMPLETE.json')
    assert saved['batch'] == number - 1 and saved['arm'] == arm
    for relative, expected in saved['files'].items():
        assert file_sha(folder / relative) == expected, relative
    return folder


def policy_identity(checkpoint):
    if checkpoint is None:
        return {'kind': 'base_with_zero_initialized_LoRA', 'base_manifest_sha256': file_sha(R / 'phase_a/config/model_manifest.json'),
                'initialization_seed': config()['training']['seed']}
    return {'kind': 'student_adapter', 'checkpoint_complete_sha256': file_sha(checkpoint / 'COMPLETE.json')}
