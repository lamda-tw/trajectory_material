"""Versioned DRACO static reward -> on-policy GRPO; frozen collection stays intact."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'stages/step02_static_scores'))
from common import (atomic_json, check_training_ids, collection_fingerprint, digest,
                    file_sha, group_advantages, ids, load_config, load_rules,
                    read_json, rubric_rewards, validate_judgement, validate_tokens)
from initial_policy import adapter_path, policy_id, validate_adapter
import judge_transport as judge

RUN = ROOT / 'runs/step03_grpo_framework_v1'
COLLECTION = ROOT / 'runs/step01_train90_rollouts'


def settings():
    return read_json(STAGE / 'config.json')


def identity():
    cfg = load_config()
    sources = {p.name: file_sha(p) for p in sorted(STAGE.iterdir())
               if p.suffix in {'.py', '.json'}}
    return digest({'settings': settings(), 'sources': sources,
                   'collection': collection_fingerprint(cfg),
                   'adapter': validate_adapter(cfg),
                   'judge_compat': file_sha(ROOT / 'stages/step02_static_scores/judge_compat.py'),
                   'judge_transport': file_sha(ROOT / 'stages/step02_static_scores/judge_transport.py')})


def task_order():
    cfg, stage = load_config(), settings()
    tasks = sorted(ids(ROOT / cfg['training']['train_tasks']),
                   key=lambda t: hashlib.sha256((stage['task_order_prefix'] + t).encode()).hexdigest())
    offset = stage['task_order_offset']
    return tasks[offset:] + tasks[:offset]


def tasks_for(update):
    if update < 1:
        raise ValueError('Updates start at one.')
    tasks, count = task_order(), settings()['groups_per_update']
    return [tasks[((update - 1) * count + i) % len(tasks)] for i in range(count)]


def save_once(path, value):
    if Path(path).exists():
        if read_json(path) != value:
            raise ValueError(f'Frozen artifact changed: {path}')
    else:
        atomic_json(path, value)


def checkpoint_path(branch, update):
    if branch not in {'rubric', 'outcome'} or update < 1:
        raise ValueError('Invalid branch/update.')
    return RUN / branch / f'update_{update:03d}' / 'checkpoint'


def policy_info(branch, update):
    cfg = load_config()
    if update == 0:
        validate_adapter(cfg)
        return {'policy_id': policy_id(cfg), 'path': str(adapter_path(cfg)), 'update': 0}
    path = checkpoint_path(branch, update)
    info = read_json(path / 'manifest.json')
    if info['framework_fingerprint'] != identity() or info['branch'] != branch or info['update'] != update:
        raise ValueError('Checkpoint belongs to another framework/branch/update.')
    for name, sha in info['files'].items():
        if file_sha(path / name) != sha:
            raise ValueError(f'Checkpoint changed: {name}')
    return dict(info, path=str(path))


def prepare():
    cfg = load_config()
    value = {'framework_fingerprint': identity(), 'settings': settings(),
             'task_order': task_order(), 'first_update_tasks': tasks_for(1),
             'initial_policy_id': policy_id(cfg),
             'collection_index_sha256': file_sha(COLLECTION / 'trajectory_index.json'),
             'scope': 'one real optimizer update for engineering validation; no dev efficacy claim',
             'reference_policy': str(adapter_path(cfg)), 'gpu': settings()['execution_gpu'],
             'reward': 'official static 21 rules; keep iff any FAIL; 10*(P-F)/(P+F)',
             'initial_batch': 'original initial-policy trajectories, exactly one PPO epoch',
             'later_batches': 'fresh rollouts from the immediate parent checkpoint'}
    save_once(RUN / 'manifest.json', value)
    return value


def initial_jobs(tasks):
    index = read_json(COLLECTION / 'trajectory_index.json')
    jobs = []
    for task in tasks:
        rows = sorted((r for r in index if r['task_id'] == task), key=lambda r: r['sample'])
        if [r['sample'] for r in rows] != list(range(6)):
            raise ValueError('Initial group must contain all six samples.')
        for row in rows:
            if file_sha(row['trajectory']) != row['sha256']:
                raise ValueError('Frozen trajectory changed.')
            jobs.append(read_json(row['trajectory'])['job'])
    return jobs


def judgement_path(job, directory):
    uid = f"{job['task_id']}__{job['sample']:02d}"
    cfg = load_config()
    if job['policy_id'] == policy_id(cfg):
        cached = ROOT / settings()['initial_score_cache'] / uid / 'judgement.json'
        if cached.exists():
            return cached
    return Path(directory) / 'judgements' / uid / 'judgement.json'


def validated_scores(job, directory):
    cfg = load_config()
    path = judgement_path(job, directory)
    result = read_json(path)
    trajectory = read_json(job['output'])
    key = digest({'prompt': judge.build_prompt(cfg, trajectory), 'judge': cfg['judge'],
                  'schema_sha256': file_sha(ROOT / cfg['judge']['schema'])})
    if result['cache_key'] != key:
        raise ValueError('Scores from another prompt/config cannot enter this reward.')
    validate_judgement({'scores': result['scores']}, load_rules(cfg))
    attempt = result['attempts']
    if read_json(path.parent / f'response_{attempt}.json') != {'scores': result['scores']}:
        raise ValueError('Stored scores differ from the original response.')
    judge.audit_events((path.parent / f'events_{attempt}.jsonl').read_text())
    return path, result


def build_batch(jobs, directory, branch, update):
    cfg, stage = load_config(), settings()
    expected = policy_info(branch, update - 1)['policy_id']
    tasks = tasks_for(update)
    check_training_ids([j['task_id'] for j in jobs], cfg)
    if len(jobs) != len(tasks) * 6 or set(j['task_id'] for j in jobs) != set(tasks):
        raise ValueError('Incomplete or unscheduled batch.')
    groups, episodes = [], []
    for task in tasks:
        members = sorted((j for j in jobs if j['task_id'] == task), key=lambda j: j['sample'])
        if [j['sample'] for j in members] != list(range(6)):
            raise ValueError('Group has missing or duplicate samples.')
        trajectories = [read_json(j['output']) for j in members]
        for j, trajectory in zip(members, trajectories):
            if trajectory['job'] != j or j['mode'] != 'train' or j['policy_id'] != expected:
                raise ValueError('Stale/off-policy or non-training trajectory.')
            if j['fingerprint'] != collection_fingerprint(cfg) or trajectory['public_task']['task_id'] != task:
                raise ValueError('Wrong collection protocol or task.')
            if (update == 1 and j['update'] != 0) or (update > 1 and j['update'] != update):
                raise ValueError('Rollout generated for the wrong update.')
            if update > 1 and j.get('framework_fingerprint') != identity():
                raise ValueError('Fresh rollout belongs to another framework.')
            if not trajectory['steps']:
                raise ValueError('Empty rollout cannot silently be dropped.')
            for s in trajectory['steps']:
                validate_tokens(s['prompt_ids'], s['response_ids'], s['old_logprobs'])
        score_refs = [None] * 6
        if branch == 'rubric':
            verdicts = []
            for i, job in enumerate(members):
                path, result = validated_scores(job, directory)
                verdicts.append([{1: 'PASS', -1: 'FAIL', 0: 'NA'}[s['score']] for s in result['scores']])
                score_refs[i] = {'path': str(path), 'sha256': file_sha(path)}
            reward = rubric_rewards(verdicts, cfg['judge']['reward_scale'])
        elif branch == 'outcome':
            reward = {'rewards': [float(t['official_evaluation']['success']) for t in trajectories],
                      'kept_rule_ids': []}
        else:
            raise ValueError('Unknown reward branch.')
        advantages = group_advantages(reward['rewards'], stage['training']['advantage_epsilon'])
        groups.append({'task_id': task, **reward, 'advantages': advantages})
        for job, trajectory, r, adv, score in zip(members, trajectories, reward['rewards'], advantages, score_refs):
            episodes.append({'task_id': task, 'sample': job['sample'], 'trajectory': job['output'],
                             'trajectory_sha256': file_sha(job['output']), 'reward': r,
                             'advantage': adv, 'judgement': score,
                             'token_count': sum(len(s['response_ids']) for s in trajectory['steps'])})
    return {'framework_fingerprint': identity(), 'branch': branch, 'update': update,
            'policy_id': expected, 'reference_policy_id': policy_id(cfg),
            'training': stage['training'], 'groups': groups, 'episodes': episodes}


def validate_batch(path):
    batch = read_json(path)
    if batch['framework_fingerprint'] != identity():
        raise ValueError('Batch source/config changed.')
    jobs = [read_json(e['trajectory'])['job'] for e in batch['episodes']]
    rebuilt = build_batch(jobs, Path(path).parent, batch['branch'], batch['update'])
    if batch != rebuilt:
        raise ValueError('Batch rewards, inputs, or policy lineage changed.')
    return batch
