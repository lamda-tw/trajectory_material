#!/usr/bin/env python3
"""Audit the completed train90 experiment without allocating GPU memory."""
import argparse
import hashlib
import json
import math
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def model_headers(directory):
    directory = Path(directory)
    index = load(directory / 'model.safetensors.index.json')
    tensors = {}
    for filename in sorted(set(index['weight_map'].values())):
        path = directory / filename
        with path.open('rb') as f:
            length = struct.unpack('<Q', f.read(8))[0]
            header = json.loads(f.read(length))
        payload_bytes = path.stat().st_size - 8 - length
        end = 0
        for name, entry in header.items():
            if name == '__metadata__':
                continue
            assert name not in tensors and index['weight_map'][name] == filename
            assert 0 <= entry['data_offsets'][0] <= entry['data_offsets'][1] <= payload_bytes
            end = max(end, entry['data_offsets'][1])
            tensors[name] = entry
        assert end == payload_bytes, f'Incomplete or extra payload: {path}'
    assert set(tensors) == set(index['weight_map'])
    return index, tensors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment', type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment.resolve()
    workspace = exp.parent.parent
    cfg = load(exp / 'config/training_config.json')
    metrics = load(exp / 'metrics/metrics.json')
    history = [json.loads(line) for line in (exp / 'metrics/training_history.jsonl').read_text().splitlines() if line.strip()]
    tr = metrics['training']
    assert metrics['status'] == 'SUCCESS' and tr['epochs_completed'] == 5 and tr['global_steps'] == 2925
    assert [r['step'] for r in history] == list(range(1, 2926))
    assert history == tr['history']
    assert all(r['epoch'] == (r['step'] - 1) // 585 + 1 for r in history)
    assert all(math.isfinite(r[k]) for r in history for k in ('train_loss', 'learning_rate', 'grad_norm'))
    assert metrics['model']['trainable_parameters'] == metrics['model']['total_parameters'] == 8190735360
    assert tr['checkpoint_every'] == cfg['checkpoint_every'] == 585
    assert not metrics['arguments']['resume_allow_code_change']
    assert sha256(cfg['train_json']) == cfg['train_sha256']
    root = exp / 'artifacts/restart'
    cleanup_path = exp / 'metrics/checkpoint_cleanup.json'
    cleanup = load(cleanup_path) if cleanup_path.exists() else None
    if cleanup is not None:
        assert cleanup['status'] == 'COMPLETE' and cleanup['global_step'] == 2925
        assert not (root / 'latest.json').exists()
        assert not root.exists() or not list(root.iterdir())
        complete = load(exp / 'config/final_checkpoint_metadata.json')
        assert sha256(exp / 'config/final_checkpoint_metadata.json') == cleanup['metadata_sha256']
        retained_steps, verified_checkpoint_sizes = [], {}
    else:
        latest = load(root / 'latest.json')
        assert latest == {'directory': 'step_002925', 'global_step': 2925}
        assert sorted(p.name for p in root.iterdir() if p.is_dir()) == ['step_002925']
        complete = load(root / latest['directory'] / 'COMPLETE.json')
        assert all((root / latest['directory'] / name).stat().st_size == size for name, size in complete['files'].items())
        retained_steps, verified_checkpoint_sizes = [2925], complete['files']
    progress = complete['progress']
    assert (progress['global_step'], progress['epoch_index'], progress['consumed_batches']) == (2925, 5, 0)
    assert complete['world_size'] == 2
    assert set(complete['files']) == {'rank_0.pt', 'rank_1.pt'}
    source_hashes = {}
    for key, filename in [('trainer_sha256', 'full_sft_train_fsdp_scheduled.py'), ('runtime_sha256', 'full_sft_runtime.py')]:
        digest = sha256(workspace / 'scripts' / filename)
        assert digest == complete['contract'][key]
        source_hashes[filename] = digest
    assert complete['contract']['train_sha256'] == cfg['train_sha256']
    assert sha256(Path(cfg['base_model']) / 'config.json') == complete['contract']['model_config_sha256']
    assert sha256(exp / 'config/diagnostic_last_step_per_task.jsonl') == complete['contract']['validation_sha256']
    events = []
    for filename in ['04_train_full_sft.log', '04b_train_full_sft_resume.log']:
        for line in (exp / 'logs' / filename).read_text().splitlines():
            if line.startswith('{'):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    saves = [r['global_step'] for r in events if r.get('event') == 'restart_saved']
    assert saves == [100, 585, 1170, 1755, 2340, 2925], saves
    assert [r['global_step'] for r in events if r.get('event') == 'restart_loaded'] == [100]
    exported_config = load(exp / 'artifacts/model/config.json')
    assert exported_config['dtype'] == exported_config['torch_dtype'] == 'bfloat16'
    index, weights = model_headers(exp / 'artifacts/model')
    _, base_weights = model_headers(cfg['base_model'])
    assert set(weights) == set(base_weights)
    assert all(entry['shape'] == base_weights[name]['shape'] for name, entry in weights.items())
    assert all(entry['dtype'] == 'BF16' for entry in weights.values())
    count = sum(math.prod(entry['shape']) for entry in weights.values())
    assert count == 8190735360 and index['metadata']['total_size'] == count * 2
    assert all(entry['data_offsets'][1] - entry['data_offsets'][0] == math.prod(entry['shape']) * 2 for entry in weights.values())
    assert not list((exp / 'artifacts').glob('*.tmp'))
    result = subprocess.run(['sha256sum', '-c', str(exp / 'metrics/final_model_weights.sha256')], check=True, capture_output=True, text=True)
    (exp / 'logs/09_final_model_hash_verify.log').write_text(result.stdout)
    generation = load(exp / 'metrics/generation_smoke.json')
    output = {
        'status': 'PASS' if generation['status'] == 'PASS' else 'PASS_WITH_GENERATION_WARNING',
        'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'epochs': 5, 'steps': 2925, 'steps_per_epoch': 585,
        'epoch_mean_loss': [sum(r['train_loss'] for r in history if r['epoch'] == e) / 585 for e in range(1, 6)],
        'training_history_matches_metrics': True,
        'final_model_tensor_count': len(weights), 'final_model_parameters': count,
        'final_model_dtype': 'BF16', 'base_tensor_names_and_shapes_match': True,
        'weight_sha256_verified': True, 'dataset_and_source_hashes_verified': True,
        'training_source_sha256': source_hashes,
        'runtime_versions': {k: complete['contract'][k] for k in ('torch', 'transformers')},
        'checkpoint_saved_steps': saves,
        'checkpoint_retained_steps': retained_steps,
        'checkpoint_file_sizes_verified': verified_checkpoint_sizes,
        'checkpoint_cleanup_record': 'metrics/checkpoint_cleanup.json' if cleanup is not None else None,
        'generation_format_check': generation['status'],
        'dev_or_test_evaluation_run': False,
    }
    (exp / 'metrics/final_artifact_validation.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
