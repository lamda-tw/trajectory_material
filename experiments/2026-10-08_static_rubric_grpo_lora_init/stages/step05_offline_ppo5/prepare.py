"""Read-only input audit and local manifests; no judge, model, or GPU calls."""
import json
import shutil
import pipeline as p


def prepare():
    cfg, stage = p.load_config(), p.settings()
    fingerprint = p.identity()
    policy = p.policy_info('rubric', 0)
    tasks = p.tasks_for(1)
    allowed = p.ids(p.ROOT / cfg['training']['train_tasks'])
    if len(tasks) != 90 or len(set(tasks)) != 90 or set(tasks) != set(allowed):
        raise ValueError('Expected exactly the frozen train90, without replacement.')
    p.check_training_ids(tasks, cfg)
    index = p.read_json(p.COLLECTION / 'trajectory_index.json')
    if len(index) != 540 or len({(r['task_id'], r['sample']) for r in index}) != 540:
        raise ValueError('Expected exactly 540 unique frozen trajectories.')
    rows = {(r['task_id'], r['sample']): r for r in index}
    collection = p.collection_fingerprint(cfg)
    jobs, inventory, cached = [], [], []
    directory = p.RUN / 'fixed_batch'
    max_context = cfg['agent']['max_model_len']
    for task in tasks:
        for sample in range(6):
            row = rows[(task, sample)]
            if p.file_sha(row['trajectory']) != row['sha256']:
                raise ValueError('Frozen trajectory hash changed.')
            trajectory = p.read_json(row['trajectory'])
            job = trajectory['job']
            if (job['task_id'] != task or job['sample'] != sample
                    or job['mode'] != 'train' or job['update'] != 0
                    or job['policy_id'] != policy['policy_id']
                    or job['fingerprint'] != collection
                    or job['output'] != row['trajectory']
                    or trajectory['public_task']['task_id'] != task):
                raise ValueError('Wrong task, policy, update, or collection identity.')
            if not trajectory['steps']:
                raise ValueError('Empty trajectories cannot be dropped or trained.')
            for step in trajectory['steps']:
                p.validate_tokens(step['prompt_ids'], step['response_ids'], step['old_logprobs'])
                if len(step['prompt_ids']) + len(step['response_ids']) > max_context:
                    raise ValueError('Trajectory exceeds the frozen model context limit.')
            jobs.append(job)
            inventory.append({
                'task_id': task, 'sample': sample, 'trajectory': row['trajectory'],
                'sha256': row['sha256'], 'steps': len(trajectory['steps']),
                'action_tokens': sum(len(s['response_ids']) for s in trajectory['steps']),
                'max_context_tokens': max(len(s['prompt_ids']) + len(s['response_ids'])
                                          for s in trajectory['steps'])})
            if p.judgement_path(job, directory).exists():
                path, result = p.validated_scores(job, directory)
                cached.append({'task_id': task, 'sample': sample, 'path': str(path),
                               'sha256': p.file_sha(path), 'cache_key': result['cache_key']})
    p.save_once(p.RUN / 'jobs.json', jobs)
    p.save_once(p.RUN / 'input_inventory.json', inventory)
    source_paths = sorted(path for path in p.STAGE.iterdir() if path.suffix in {'.py', '.json'})
    sources = {path.name: p.file_sha(path) for path in source_paths}
    manifest = {
        'framework_fingerprint': fingerprint, 'settings': stage,
        'task_order': tasks, 'groups': 90, 'trajectories': 540,
        'group_size': 6, 'rules_per_trajectory': len(p.load_rules(cfg)),
        'initial_policy_id': policy['policy_id'], 'initial_adapter': policy['path'],
        'reference_policy_id': policy['policy_id'], 'optimizer_initialization': 'fresh AdamW',
        'optimizer_steps': 5, 'ppo_epochs': 5,
        'gradient_accumulation': 'all 540 trajectories before one optimizer.step() per epoch; five epochs',
        'reward_and_advantage_scope': 'each task independently, exactly six trajectories',
        'reward': 'official static 21 rules; keep iff any FAIL; 10*(P-F)/(P+F)',
        'gpu': stage['execution_gpu'], 'jobs_sha256': p.file_sha(p.RUN / 'jobs.json'),
        'inventory_sha256': p.file_sha(p.RUN / 'input_inventory.json'),
        'collection_index_sha256': p.file_sha(p.COLLECTION / 'trajectory_index.json'),
        'total_steps': sum(r['steps'] for r in inventory),
        'action_tokens': sum(r['action_tokens'] for r in inventory),
        'max_context_tokens': max(r['max_context_tokens'] for r in inventory),
        'sources': sources,
        'scope': 'offline fixed train90 trajectories/rewards/advantages/behavior logprobs; five full-batch epochs from initial SFT',
        'execution_instruction': 'Scoring may run; GPU training is explicitly on hold until a new user instruction. No automatic GPU queue.'}
    p.save_once(p.RUN / 'manifest.json', manifest)
    snapshot = p.RUN / 'source_snapshot'
    snapshot.mkdir(exist_ok=True)
    for path in source_paths:
        target = snapshot / path.name
        if target.exists() and p.file_sha(target) != sources[path.name]:
            raise ValueError('Source snapshot changed.')
        if not target.exists():
            shutil.copyfile(path, target)
    readiness = {
        'input_validation_passed': True, 'framework_fingerprint': fingerprint,
        'groups': 90, 'trajectories': 540, 'valid_cached_scores': len(cached),
        'pending_scores': 540 - len(cached), 'cached_scores': cached,
        'batch_exists': (directory / 'batch.json').exists(),
        'checkpoint_exists': p.checkpoint_path('rubric', 5).exists(),
        'this_check_judge_calls': 0, 'this_check_model_loads': 0,
        'this_check_optimizer_steps': 0}
    p.atomic_json(p.RUN / 'readiness.json', readiness)
    return manifest, readiness


if __name__ == '__main__':
    manifest, status = prepare()
    print(json.dumps({k: v for k, v in status.items() if k != 'cached_scores'}, indent=2))
