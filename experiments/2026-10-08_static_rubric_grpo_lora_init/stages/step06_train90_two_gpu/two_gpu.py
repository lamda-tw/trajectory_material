"""Versioned execution of the frozen train90 batch on two independent GPU workers."""
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[1]
sys.path.insert(0, str(ROOT / 'stages/step04_train90_single_update'))
import pipeline as p


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


core = module('draco_single_update_core', p.STAGE / 'train.py')
recovery_path = ROOT / 'stages/step05_offline_ppo5/offline_state.py'
recovery = module('draco_gradient_recovery', recovery_path)
RUN = ROOT / 'runs/step06_train90_two_gpu_v1'
BATCH = p.RUN / 'rubric/update_001/batch.json'


def stamp():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def settings():
    cfg = p.read_json(STAGE / 'config.json')
    if (cfg['gpus'] != ['0', '1'] or cfg['world_size'] != 2 or cfg['groups'] != 90
            or cfg['group_size'] != 6 or cfg['ppo_epochs'] != 1 or cfg['optimizer_steps'] != 1
            or cfg['gradient_recovery_every_episodes'] != 6):
        raise ValueError('Only the approved two-GPU, one-update experiment is supported.')
    return cfg


def identity():
    return p.digest({'sources': {x.name: p.file_sha(x) for x in sorted(STAGE.iterdir())
                                  if x.suffix in {'.py', '.json'}},
                     'source_framework': p.identity(), 'batch': p.file_sha(BATCH),
                     'recovery_helper': p.file_sha(recovery_path), 'settings': settings()})


def partition(costs):
    if not costs or len(costs) % 2:
        raise ValueError('An even, nonzero number of groups is required.')
    groups, loads = [[], []], [0, 0]
    cap = len(costs) // 2
    for group in sorted(range(len(costs)), key=lambda i: (-costs[i], i)):
        candidates = [rank for rank in range(2) if len(groups[rank]) < cap]
        rank = min(candidates, key=lambda r: (loads[r], r))
        groups[rank].append(group)
        loads[rank] += costs[group]
    return [sorted(group) for group in groups], loads


def check_partition(assignments, total):
    all_indices = [i for shard in assignments for i in shard]
    if len(assignments) != 2 or not all(assignments) or sorted(all_indices) != list(range(total)):
        raise ValueError('Shards must cover every episode exactly once without overlap.')


def prepare():
    cfg = settings()
    batch = p.validate_batch(BATCH)
    if len(batch['groups']) != 90 or len(batch['episodes']) != 540:
        raise ValueError('All 90 complete scored groups are required.')
    costs = []
    for offset in range(0, 540, 6):
        cost = 0
        for episode in batch['episodes'][offset:offset + 6]:
            trajectory = p.read_json(episode['trajectory'])
            for step in trajectory['steps']:
                length = len(step['prompt_ids']) + len(step['response_ids'])
                cost += length * length + 8192 * length
        costs.append(cost)
    groups, loads = partition(costs)
    assignments = [[i for group in shard for i in range(group * 6, group * 6 + 6)] for shard in groups]
    check_partition(assignments, 540)
    manifest = {'execution_fingerprint': identity(), 'source_framework_fingerprint': p.identity(),
                'settings': cfg, 'batch': str(BATCH), 'batch_sha256': p.file_sha(BATCH),
                'parent_policy_id': batch['policy_id'], 'reference_policy_id': batch['reference_policy_id'],
                'groups': 90, 'episodes': 540, 'assignments': assignments, 'group_assignments': groups,
                'estimated_costs': loads, 'action_tokens': [sum(batch['episodes'][i]['token_count'] for i in shard)
                                                           for shard in assignments],
                'optimizer_steps': 1, 'ppo_epochs': 1, 'checkpoint': str(RUN / 'checkpoint')}
    p.save_once(RUN / 'manifest.json', manifest)
    snapshot = RUN / 'source_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for source in sorted(STAGE.iterdir()):
        if source.suffix not in {'.py', '.json'}:
            continue
        target = snapshot / source.name
        if target.exists() and p.file_sha(target) != p.file_sha(source):
            raise ValueError('Frozen execution snapshot changed.')
        if not target.exists():
            shutil.copyfile(source, target)
    return batch, manifest


def load_input():
    manifest = p.read_json(RUN / 'manifest.json')
    if manifest['execution_fingerprint'] != identity() or manifest['batch_sha256'] != p.file_sha(BATCH):
        raise ValueError('Frozen execution or batch changed.')
    batch = p.read_json(BATCH)
    check_partition(manifest['assignments'], len(batch['episodes']))
    return batch, manifest


def signature(manifest, rank):
    return {'execution': manifest['execution_fingerprint'], 'batch': manifest['batch_sha256'],
            'parent': manifest['parent_policy_id'], 'reference': manifest['reference_policy_id'],
            'rank': rank, 'episode_indices': manifest['assignments'][rank], 'optimizer_steps': 0}


def worker_dir(rank):
    return RUN / f'worker_{rank}'


def completed_worker(rank, manifest):
    folder = worker_dir(rank)
    record = p.read_json(folder / 'complete.json')
    if (record['signature'] != signature(manifest, rank)
            or record['completed_episodes'] != len(manifest['assignments'][rank])
            or record['gradients_sha256'] != p.file_sha(folder / 'gradients.pt')
            or not record['policy_unchanged'] or not record['reference_unchanged']
            or record['optimizer_steps'] != 0):
        raise ValueError('Worker result is incomplete or from another execution.')
    return record


def gpu_info(gpu):
    import csv
    import io
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.free', '--format=csv,noheader,nounits'],
                            text=True, capture_output=True, check=True, timeout=15)
    row = next(r for r in csv.reader(io.StringIO(result.stdout)) if r[0].strip() == str(gpu))
    active = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'],
                            text=True, capture_output=True, check=True, timeout=15)
    processes = [int(r[1].strip()) for r in csv.reader(io.StringIO(active.stdout)) if r and r[0].strip() == row[1].strip()]
    free = int(row[2].strip())
    return {'gpu': str(gpu), 'free_mib': free, 'compute_pids': processes,
            'ready': not processes and free >= p.load_config()['training']['minimum_free_gpu_gib'] * 1024}


def configure_gpu(gpu):
    info = gpu_info(gpu)
    if not info['ready']:
        raise RuntimeError(f'GPU is not idle: {info}')
    os.environ.update(CUDA_VISIBLE_DEVICES=str(gpu), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')


def status(phase, **kwargs):
    workers = []
    for rank in range(2):
        path = worker_dir(rank) / 'progress.json'
        workers.append(p.read_json(path) if path.exists() else {'rank': rank, 'completed_episodes': 0})
    record = {'phase': phase, 'updated_at': stamp(), 'pid': os.getpid(), 'gpus': ['0', '1'],
              'valid_scores': 540, 'complete_groups': 90, 'target_optimizer_steps': 1,
              'workers': workers, 'completed_episodes': sum(w.get('completed_episodes', 0) for w in workers), **kwargs}
    p.atomic_json(RUN / 'status.json', record)
    message = (f'# train90 两卡单次更新\n\n检查时间：{record["updated_at"]}。\n\n'
               f'阶段：**{phase}**。评分 540/540，完整题目组 90/90。\n\n'
               f'已完成梯度计算的轨迹：{record["completed_episodes"]}/540。'
               '两卡只累计梯度，全部完成后合并、裁剪并执行一次 optimizer step。\n\n')
    for rank, worker in enumerate(workers):
        message += f'- GPU {rank}：{worker.get("completed_episodes", 0)}/270 条；阶段 {worker.get("phase", "waiting")}。\n'
    if 'error' in kwargs:
        message += '\n错误：' + kwargs['error'] + '\n'
    temp = RUN / 'STATUS.md.tmp'
    temp.write_text(message)
    temp.replace(RUN / 'STATUS.md')
    # Preserve the status links already shared with the user. The old monitor is stopped.
    legacy = ROOT / 'runs/step05_offline_ppo5_v1/monitoring'
    if legacy.exists():
        mirror = legacy / 'STATUS.md.tmp'
        mirror.write_text(message + '\n当前两卡运行目录：' + str(RUN) + '\n')
        mirror.replace(legacy / 'STATUS.md')
        p.atomic_json(legacy / 'latest.json', {**record, 'health': phase, 'remaining': 0, 'target': 540, 'active_run': str(RUN)})
    return record


def checkpoint_info(manifest):
    path = RUN / 'checkpoint'
    info = p.read_json(path / 'manifest.json')
    if (info['execution_fingerprint'] != manifest['execution_fingerprint']
            or info['batch_sha256'] != manifest['batch_sha256']
            or info['parent_policy_id'] != manifest['parent_policy_id']
            or info['reference_policy_id'] != manifest['reference_policy_id']
            or info['optimizer_steps'] != 1):
        raise ValueError('Checkpoint belongs to another execution or update.')
    for name, sha in info['files'].items():
        if p.file_sha(path / name) != sha:
            raise ValueError('Committed checkpoint changed.')
    return info
