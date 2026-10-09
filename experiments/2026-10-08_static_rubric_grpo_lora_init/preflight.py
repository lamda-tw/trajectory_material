"""Offline preparation: metadata, hashes, pairing. No model, network, or CUDA calls."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from common import ROOT, atomic_json, file_sha, ids, collection_fingerprint, load_config, load_rules, read_json
from initial_policy import DIRECTORY, rollout_jobs, validate_adapter, verify_raw_reference
from policy_server import server_command

def inspect(config):
    adapter = validate_adapter(config)
    reference = verify_raw_reference(config)
    train = ids(ROOT / config['collection']['tasks'])
    dev = ids(ROOT / config['evaluation']['tasks'])
    data = Path(config['paths']['appworld_data'])
    if (len(train) != 90 or len(set(train)) != 90 or train != ids(data / 'datasets/train.txt')
        or len(dev) != 57 or len(set(dev)) != 57 or dev != ids(data / 'datasets/dev.txt') or set(train) & set(dev)):
        raise ValueError('Require exactly official train90 and dev57, without overlap.')
    if config['server']['gpu'] != '0' or config['training']['gpu'] != '0':
        raise ValueError('This branch is configured for GPU 0.')
    if config['collection']['workers'] != 6 or config['collection']['rollouts_per_task'] != 6:
        raise ValueError('Require the paired six-way collection protocol.')
    if len(load_rules(config)) != 21:
        raise ValueError('Wrong static rubric count.')
    for name in ('appworld_python', 'training_python', 'vllm_python', 'codex'):
        if not Path(config['paths'][name]).is_file():
            raise ValueError(f'Missing executable: {name}')
    base = Path(config['paths']['base_model'])
    index = read_json(base / 'model.safetensors.index.json')
    if any(not (base / name).is_file() for name in set(index['weight_map'].values())):
        raise ValueError('Base weight shard missing.')
    jobs = rollout_jobs(config, DIRECTORY, train)
    def pair(job):
        return (job['task_id'], job['sample'], job['seed'], job['update'], job['mode'])
    if list(map(pair, jobs)) != list(map(pair, reference['jobs'])) or len(jobs) != 540:
        raise ValueError('Task/sample/seed pairing differs from the collected raw branch.')
    if any(j['model'] != config['server']['adapter_name'] or not j['policy_id'].startswith('initial-lora:') for j in jobs):
        raise ValueError('A job would query the raw base instead of the adapter.')
    raw_outputs = {j['output'] for j in reference['jobs']}
    if any(j['output'] in raw_outputs or not Path(j['output']).is_relative_to(DIRECTORY) for j in jobs):
        raise ValueError('Output isolation failed.')
    raw_dir = Path(config['comparison']['raw_experiment']) / config['comparison']['raw_collection']
    rows = read_json(raw_dir / 'trajectory_index.json')
    if len(rows) != 540 or any(file_sha(row['trajectory']) != row['sha256'] for row in rows):
        raise ValueError('Raw trajectories no longer match their frozen index.')
    command = server_command(config, ROOT / config['initial_policy']['adapter'])
    if '--enable-lora' not in command or command[command.index('--max-lora-rank') + 1] != '8':
        raise ValueError('Incorrect adapter serving command.')
    if config['server']['port'] == reference['config']['server']['port']:
        raise ValueError('LoRA and raw server ports must be isolated.')
    report = {'status': 'OFFLINE_READY_NOT_EXECUTED', 'checked_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
              'scope': 'initial-policy full-train collection only; live vLLM/PEFT integration is untested',
              'fingerprint': collection_fingerprint(config), 'adapter': adapter,
              'paired_rollouts': 540, 'train_tasks': 90, 'dev_tasks': 57, 'static_rules': 21,
              'raw_trajectory_checksums_verified': len(rows), 'gpu': '0', 'port': config['server']['port'],
              'server_command_preview': command, 'model_requests_by_preflight': 0,
              'optimizer_updates_by_preflight': 0, 'codex_calls_by_preflight': 0,
              'new_branch_rollouts_present': len(list((DIRECTORY / 'trajectories').glob('*.json'))),
              'readiness_limit': 'Does not allocate GPU memory or verify a live LoRA server; runtime checks remain for the authorized launch.'}
    return report, jobs

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Save the validated plan and readiness report; no execution.')
    args = parser.parse_args()
    report, jobs = inspect(load_config())
    if args.write:
        atomic_json(ROOT / 'preparation/planned_jobs.json', jobs)
        atomic_json(ROOT / 'preparation/readiness.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
