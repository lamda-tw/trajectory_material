"""Shared, standard-library-only experiment primitives."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read_json(path):
    return json.loads(Path(path).read_text())

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def ids(path):
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip() and not line.startswith('#')]

def load_config():
    config = read_json(ROOT / 'config.json')
    assert config['sampling']['group_size'] == 6
    assert config['sampling']['temperature'] == config['sampling']['top_p'] == 1.0
    assert config['sampling']['top_k'] == -1 and config['sampling']['repetition_penalty'] == 1.0
    assert config['training']['ppo_epochs_per_batch'] == 1
    assert config['agent']['enable_thinking'] is False
    assert config['evaluation']['checkpoints'] == [0, config['training']['updates']]
    assert config['judge']['filter_no_fail'] is True
    return config

def load_rules(config):
    raw = read_json(ROOT / config['judge']['rules'])
    raw = raw['rubrics'] if isinstance(raw, dict) else raw
    return [dict(id=i, **{key: rule[key] for key in ('title', 'description', 'evaluator_instruction')}) for i, rule in enumerate(raw)]

def input_fingerprint(config):
    assets = {str(path.relative_to(ROOT)): file_sha(path) for path in sorted((ROOT / 'assets').rglob('*')) if path.is_file()}
    code = {path.name: file_sha(path) for path in sorted(ROOT.glob('*.py')) if path.name != 'prepare_assets.py'}
    base = Path(config['paths']['base_model'])
    model = {name: file_sha(base / name) for name in ('config.json', 'tokenizer_config.json', 'model.safetensors.index.json')}
    return digest({'config': config, 'assets': assets, 'code': code, 'base': model})

def check_training_ids(task_ids, config):
    allowed = set(ids(ROOT / config['training']['train_tasks']))
    dev = set(ids(ROOT / config['evaluation']['tasks']))
    if not task_ids or not set(task_ids) <= allowed or set(task_ids) & dev:
        raise ValueError('Training may use only frozen train task IDs; dev is evaluation-only.')

def schedule(config, update):
    tasks = ids(ROOT / config['training']['train_tasks'])
    n = config['training']['groups_per_update']
    return [tasks[((update - 1) * n + index) % len(tasks)] for index in range(n)]

def sample_seed(config, update, task_id, sample, pilot=False):
    base = config['sampling']['pilot_seed' if pilot else 'seed']
    return int(digest([base, update, task_id, sample])[:8], 16) % (2**31 - 1)

def group_advantages(rewards, epsilon=1e-6):
    if len(rewards) < 2 or any(not math.isfinite(x) for x in rewards):
        raise ValueError('A group needs >= 2 finite rewards.')
    std = statistics.stdev(rewards)
    if std == 0:
        return [0.0] * len(rewards)
    mean = statistics.mean(rewards)
    return [(r - mean) / (std + epsilon) for r in rewards]

def rubric_rewards(verdicts, scale=10.0):
    if not verdicts or not verdicts[0] or any(len(row) != len(verdicts[0]) for row in verdicts):
        raise ValueError('Expected a rectangular group-by-rule verdict matrix.')
    if any(v not in {'PASS', 'FAIL', 'NA'} for row in verdicts for v in row):
        raise ValueError('Unknown verdict; missing/invalid scores are never NA.')
    kept = [i for i in range(len(verdicts[0])) if any(row[i] == 'FAIL' for row in verdicts)]
    rewards = []
    for row in verdicts:
        p = sum(row[i] == 'PASS' for i in kept)
        f = sum(row[i] == 'FAIL' for i in kept)
        rewards.append(scale * (p - f) / (p + f) if p + f else 0.0)
    return {'kept_rule_ids': kept, 'rewards': rewards}

def validate_judgement(value, rules):
    if not isinstance(value, dict) or set(value) != {'scores'} or not isinstance(value['scores'], list) or len(value['scores']) != len(rules):
        raise ValueError('Judge must return exactly one score for each rule.')
    rows = value['scores']
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('Every rubric score must be an object.')
    if [row.get('rubric_title') for row in rows] != [r['title'] for r in rules]:
        raise ValueError('Missing, duplicated, or reordered rubric titles.')
    for row in rows:
        if set(row) != {'rubric_title', 'score', 'evidence', 'justification'} or type(row['score']) is not int or row['score'] not in {-1, 0, 1} or any(not isinstance(row[k], str) or not row[k].strip() for k in ('evidence', 'justification')):
            raise ValueError('Malformed rubric score.')
    return rows

def public_judge_payload(trajectory):
    # Deliberate allowlist. Never serialize evaluator output, rewards, or private tests.
    return {
        'task': trajectory['public_task'],
        'agent_instructions_and_demonstration': trajectory['initial_messages'],
        'actual_rollout': [
            {'step': step['step'], 'assistant': step['text'], 'executed_code': step['code'], 'observation': step['observation']}
            for step in trajectory['steps']
        ],
        'termination': trajectory['termination'],
    }

def text_to_messages(text):
    parts = re.split(r'(?:^|\n)(USER|ASSISTANT|SYSTEM):\n', text.lstrip())
    if parts[0].strip() or len(parts) < 3:
        raise ValueError('Expected a role-delimited AppWorld prompt.')
    return [{'role': parts[i].lower(), 'content': parts[i + 1].strip()} for i in range(1, len(parts), 2)]

def parse_code(text):
    match = re.search(r'```python\n(.*?)```', text, flags=re.DOTALL)
    if match:
        return match.group(1).strip(), text
    match = re.search(r'```python\n(.*)', text, flags=re.DOTALL)
    if match:
        return match.group(1).strip(), text.rstrip() + '\n```'
    return '', text

def validate_tokens(prompt_ids, response_ids, old_logprobs):
    if not prompt_ids or not response_ids or len(response_ids) != len(old_logprobs):
        raise ValueError('Missing or misaligned exact sampled token IDs/logprobs.')
    if any(type(token) is not int or token < 0 for token in prompt_ids + response_ids):
        raise ValueError('Invalid token IDs.')
    if any(type(x) not in (int, float) or not math.isfinite(x) or x > 1e-5 for x in old_logprobs):
        raise ValueError('Invalid sampled log probabilities.')

def collection_fingerprint(config):
    """Keep frozen job identity only for the explicitly audited maintenance revision."""
    current = input_fingerprint(config)
    path = ROOT / 'recovery/2026-10-09/maintenance.json'
    if not path.exists():
        return current
    maintenance = read_json(path)
    if current != maintenance['approved_runtime_fingerprint']:
        raise RuntimeError('Runtime source/config differs from the audited recovery revision.')
    original_path = ROOT / 'recovery/2026-10-09/before/config.json'
    if file_sha(original_path) != maintenance['original_config_sha256']:
        raise RuntimeError('Recovery source configuration changed.')
    original, live = read_json(original_path), json.loads(json.dumps(config))
    original['collection'].pop('report')
    live['collection'].pop('report')
    if original != live:
        raise RuntimeError('Recovery may change the report destination, never the sampling protocol.')
    return maintenance['collection_fingerprint']

def execution_provenance(config):
    return {'runtime_fingerprint': input_fingerprint(config),
            'maintenance_sha256': file_sha(ROOT / 'recovery/2026-10-09/maintenance.json'),
            'logging_patch': 'request_tracker_ellipsis_log_encoding_only'}
