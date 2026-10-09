"""Pinned LoRA initialization and paired train90 jobs. No inference on import."""
import json
import shutil
import struct
from pathlib import Path
from common import ROOT, atomic_json, digest, file_sha, ids, collection_fingerprint, read_json, sample_seed

RUNS = ROOT / 'runs'
DIRECTORY = RUNS / 'step01_train90_rollouts'

def adapter_path(config):
    return ROOT / config['initial_policy']['adapter']

def policy_id(config):
    return 'initial-lora:' + digest({'base': config['paths']['base_model'],
                                    'files': config['initial_policy']['files']})

def validate_adapter(config):
    path = adapter_path(config)
    init = config['initial_policy']
    if init['kind'] != 'peft_lora' or set(init['files']) != {'adapter_config.json', 'adapter_model.safetensors'}:
        raise ValueError('Require a pinned PEFT adapter, never silently fall back to the base.')
    if {p.name for p in path.iterdir()} != set(init['files']):
        raise ValueError('Staged adapter must contain only config and weights; use the frozen base tokenizer.')
    for name, expected in init['files'].items():
        if file_sha(path / name) != expected:
            raise ValueError(f'Initial adapter hash mismatch: {name}')
    a = read_json(path / 'adapter_config.json')
    base = read_json(Path(config['paths']['base_model']) / 'config.json')
    if Path(a['base_model_name_or_path']).resolve() != Path(config['paths']['base_model']).resolve():
        raise ValueError('Adapter belongs to another base.')
    for key in ('r', 'lora_alpha', 'lora_dropout', 'bias', 'task_type'):
        if a[key] != config['training']['lora'][key]:
            raise ValueError(f'Adapter structure mismatch: {key}')
    if (a['peft_type'] != 'LORA' or set(a['target_modules']) != set(config['training']['lora']['target_modules'])
        or a.get('modules_to_save') or a.get('rank_pattern') or a.get('alpha_pattern')
        or a.get('use_dora') or a.get('use_rslora')):
        raise ValueError('Unsupported adapter structure.')
    # Read only the safetensors header; never deserialize tensors or allocate CUDA memory.
    weights = path / 'adapter_model.safetensors'
    with weights.open('rb') as handle:
        length = struct.unpack('<Q', handle.read(8))[0]
        if length > 10_000_000:
            raise ValueError('Invalid safetensors header length.')
        header = json.loads(handle.read(length))
    h, mid, r = base['hidden_size'], base['intermediate_size'], a['r']
    head = base.get('head_dim', h // base['num_attention_heads'])
    out_q = base['num_attention_heads'] * head
    out_kv = base['num_key_value_heads'] * head
    dimensions = {'q_proj': (h, out_q), 'k_proj': (h, out_kv), 'v_proj': (h, out_kv),
                  'o_proj': (out_q, h), 'gate_proj': (h, mid), 'up_proj': (h, mid),
                  'down_proj': (mid, h)}
    expected_shapes = {}
    for layer in range(base['num_hidden_layers']):
        for module, (n_in, n_out) in dimensions.items():
            block = 'self_attn' if module in {'q_proj', 'k_proj', 'v_proj', 'o_proj'} else 'mlp'
            prefix = f'base_model.model.model.layers.{layer}.{block}.{module}'
            expected_shapes[prefix + '.lora_A.weight'] = [r, n_in]
            expected_shapes[prefix + '.lora_B.weight'] = [n_out, r]
    actual = {k: v for k, v in header.items() if k != '__metadata__'}
    if set(actual) != set(expected_shapes):
        raise ValueError('Adapter layers/modules are incomplete or unexpected.')
    elements = 0
    for name, shape in expected_shapes.items():
        tensor = actual[name]
        if tensor['shape'] != shape or tensor['dtype'] not in {'F32', 'BF16', 'F16'}:
            raise ValueError(f'Invalid adapter tensor: {name}')
        elements += shape[0] * shape[1]
    if max(v['data_offsets'][1] for v in actual.values()) + 8 + length != weights.stat().st_size:
        raise ValueError('Truncated or unexpected adapter payload.')
    return {'tensors': len(actual), 'parameters': elements, 'rank': r,
            'alpha': a['lora_alpha'], 'dtypes': sorted({v['dtype'] for v in actual.values()}),
            'policy_id': policy_id(config), 'weights_sha256': init['files']['adapter_model.safetensors']}

def verify_raw_reference(config):
    ref = config['comparison']
    raw = Path(ref['raw_experiment'])
    directory = raw / ref['raw_collection']
    for filename, key in [('collection_manifest.json', 'raw_manifest_sha256'),
                          ('trajectory_index.json', 'raw_index_sha256')]:
        if file_sha(directory / filename) != ref[key]:
            raise ValueError(f'Raw collection changed: {filename}')
    manifest = read_json(directory / 'collection_manifest.json')
    original = manifest['config']
    if manifest['fingerprint'] != ref['raw_fingerprint']:
        raise ValueError('Wrong raw reference.')
    # Compare against the archived raw collection source, not a mutable reporting entrypoint.
    snapshot = directory / 'source_snapshot'
    saved = read_json(directory / 'source_snapshot_manifest.json')
    for name, sha in saved['files'].items():
        if file_sha(snapshot / name) != sha:
            raise ValueError(f'Raw frozen source snapshot changed: {name}')
    assets = {str(p.relative_to(snapshot)): file_sha(p) for p in sorted((snapshot / 'assets').rglob('*')) if p.is_file()}
    code = {p.name: file_sha(p) for p in sorted(snapshot.glob('*.py')) if p.name != 'prepare_assets.py'}
    base = Path(original['paths']['base_model'])
    model = {name: file_sha(base / name) for name in ('config.json', 'tokenizer_config.json', 'model.safetensors.index.json')}
    if digest({'config': original, 'assets': assets, 'code': code, 'base': model}) != ref['raw_fingerprint']:
        raise ValueError('Raw frozen source/config fingerprint changed.')
    if config['paths'] != original['paths']:
        raise ValueError('Different model/environment executables or AppWorld data.')
    for key in ('agent', 'sampling', 'judge', 'evaluation', 'collection'):
        left, right = dict(config[key]), dict(original[key])
        if key == 'collection':
            left.pop('report', None)
            right.pop('report', None)
        if left != right:
            raise ValueError(f'Unpaired experimental protocol: {key}')
    for name, sha in assets.items():
        if file_sha(ROOT / name) != sha:
            raise ValueError(f'Paired asset changed: {name}')
    return manifest

def rollout_jobs(config, directory, task_ids, checkpoint=None, update=0):
    if checkpoint is not None or update != 0:
        raise ValueError('This entry collects only the pinned initial LoRA at update 0.')
    if task_ids != ids(ROOT / config['collection']['tasks']):
        raise ValueError('Require all train tasks in frozen order.')
    fingerprint = collection_fingerprint(config)
    jobs = []
    for task in task_ids:
        for sample in range(config['sampling']['group_size']):
            episode = f"lora_init__{directory.relative_to(RUNS).as_posix().replace('/', '__')}__{task}__{sample:02d}"
            jobs.append({'mode': 'train', 'task_id': task, 'seed': sample_seed(config, 0, task, sample),
                         'sample': sample, 'update': 0, 'episode_id': episode, 'runtime_name': 'appworld',
                         'model': config['server']['adapter_name'],
                         'output': str(directory / 'trajectories' / f'{task}__{sample:02d}.json'),
                         'fingerprint': fingerprint, 'policy_id': policy_id(config)})
    return jobs

def prepare_runtime(config):
    runtime = ROOT / 'runtime' / 'appworld'
    runtime.mkdir(parents=True, exist_ok=True)
    source, target = Path(config['paths']['appworld_data']), runtime / 'data'
    if target.exists() or target.is_symlink():
        if not target.samefile(source):
            raise ValueError('Unexpected runtime data link.')
    else:
        target.symlink_to(source, target_is_directory=True)
    if not (runtime / 'cache/tests').exists():
        shutil.copytree(config['paths']['appworld_test_cache'], runtime / 'cache/tests')
    return runtime

def ensure_manifest(config):
    validate_adapter(config)
    verify_raw_reference(config)
    jobs = rollout_jobs(config, DIRECTORY, ids(ROOT / config['collection']['tasks']))
    if read_json(ROOT / 'preparation/planned_jobs.json') != jobs:
        raise ValueError('Prepared jobs no longer match current code/config; repeat offline preflight.')
    target = RUNS / 'manifest.json'
    if target.exists():
        saved = read_json(target)
        old, live = json.loads(json.dumps(saved['config'])), json.loads(json.dumps(config))
        old['collection'].pop('report', None)
        live['collection'].pop('report', None)
        if old != live or saved['fingerprint'] != collection_fingerprint(config) or saved['policy_id'] != policy_id(config):
            raise ValueError('Frozen run identity or sampling protocol changed.')
        prepare_runtime(config)
        return saved['fingerprint']
    manifest = {'fingerprint': collection_fingerprint(config), 'config': config, 'policy_id': policy_id(config)}
    atomic_json(target, manifest)
    prepare_runtime(config)
    return manifest['fingerprint']
