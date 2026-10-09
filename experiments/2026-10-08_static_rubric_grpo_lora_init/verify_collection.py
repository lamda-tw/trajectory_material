"""Offline token audit, used after the first real rollout and after collection."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from common import ROOT, atomic_json, file_sha, collection_fingerprint, load_config, read_json, validate_tokens
from initial_policy import DIRECTORY, policy_id, validate_adapter, verify_raw_reference

def verify_episode(config, job, tokenizer, raw_initial):
    record = read_json(job['output'])
    if record['job'] != job or job['policy_id'] != policy_id(config):
        raise ValueError('Wrong rollout policy/job.')
    if record['public_task']['task_id'] != job['task_id'] or not 1 <= len(record['steps']) <= config['agent']['max_steps']:
        raise ValueError('Wrong task/step count.')
    if record['initial_messages'] != raw_initial:
        raise ValueError('Initial prompt differs from the paired raw trajectory.')
    messages = [dict(m) for m in record['initial_messages']]
    for n, step in enumerate(record['steps'], 1):
        if step['step'] != n:
            raise ValueError('Non-contiguous steps.')
        validate_tokens(step['prompt_ids'], step['response_ids'], step['old_logprobs'])
        if (len(step['prompt_ids']) + len(step['response_ids']) > config['agent']['max_model_len']
            or len(step['response_ids']) > config['agent']['max_new_tokens']):
            raise ValueError('Token budget exceeded.')
        if tokenizer.decode(step['response_ids'], skip_special_tokens=True) != step['text']:
            raise ValueError('Response IDs do not decode to the saved sample.')
        if tokenizer.apply_chat_template(messages, add_generation_prompt=True, enable_thinking=False, tokenize=True) != step['prompt_ids']:
            raise ValueError('Prompt IDs do not reconstruct from the frozen base tokenizer.')
        messages.append({'role': 'assistant', 'content': step['history_assistant_text'] + '\n\n'})
        if step['code']:
            fence = chr(96) * 3
            messages.append({'role': 'user', 'content': 'Output:\n' + fence + '\n' + step['observation'].rstrip() + '\n' + fence + '\n\n'})
    official = record['official_evaluation']
    if type(official['success']) is not bool or official['num_tests'] <= 0:
        raise ValueError('Invalid terminal evaluation.')
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-job', type=Path, help='Audit a single first rollout before parallel collection.')
    args = parser.parse_args()
    config = load_config()
    validate_adapter(config)
    reference = verify_raw_reference(config)
    if args.first_job:
        jobs = [read_json(args.first_job)]
        index = None
    else:
        manifest = read_json(DIRECTORY / 'collection_manifest.json')
        if manifest['fingerprint'] != collection_fingerprint(config) or manifest['policy'] != 'Qwen3-8B_train90_codex_sft_epoch5':
            raise ValueError('Collection manifest mismatch.')
        jobs = manifest['jobs']
        index = {r['trajectory']: r for r in read_json(DIRECTORY / 'trajectory_index.json')}
        if len(jobs) != 540 or len(index) != 540 or len({(j['task_id'], j['sample']) for j in jobs}) != 540:
            raise ValueError('Require all 540 unique trajectories.')
        if read_json(DIRECTORY / 'summary.json')['status'] != 'complete':
            raise ValueError('Collection is not complete.')
    maintenance_path = ROOT / 'recovery/2026-10-09/maintenance.json'
    maintenance = read_json(maintenance_path)
    retained = {row['trajectory']: row for row in read_json(ROOT / 'recovery/2026-10-09/before/runs/step01_train90_rollouts/trajectory_index.json')}
    for path, row in retained.items():
        if file_sha(path) != row['sha256']:
            raise ValueError('A pre-recovery complete trajectory changed.')
    planned = {(j['task_id'], j['sample']): j for j in read_json(ROOT / 'preparation/planned_jobs.json')}
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(config['paths']['base_model'], local_files_only=True)
    raw = {(j['task_id'], j['sample']): j for j in reference['jobs']}
    counts, groups, raw_prompts = Counter(), defaultdict(list), {}
    for i, job in enumerate(jobs, 1):
        pair = (job['task_id'], job['sample'])
        if planned[pair] != job:
            raise ValueError('Job not in frozen plan.')
        path = Path(job['output'])
        if path.with_suffix('.partial.json').exists() or (index is not None and file_sha(path) != index[str(path)]['sha256']):
            raise ValueError('Partial/corrupt trajectory.')
        if job['task_id'] not in raw_prompts:
            raw_prompts[job['task_id']] = read_json(raw[pair]['output'])['initial_messages']
        record = verify_episode(config, job, tokenizer, raw_prompts[job['task_id']])
        if str(path) not in retained:
            provenance = record.get('execution_provenance', {})
            if (provenance.get('runtime_fingerprint') != maintenance['approved_runtime_fingerprint']
                or provenance.get('maintenance_sha256') != file_sha(maintenance_path)):
                raise ValueError('New rollout lacks the audited runtime provenance.')
        counts['steps'] += len(record['steps'])
        counts['generated_tokens'] += sum(len(s['response_ids']) for s in record['steps'])
        counts['official_successes'] += record['official_evaluation']['success']
        groups[job['task_id']].append(record['official_evaluation']['success'])
        if i % 30 == 0:
            print(f'verified {i}/{len(jobs)}', flush=True)
    if not args.first_job and (len(groups) != 90 or any(len(v) != 6 for v in groups.values())):
        raise ValueError('Incomplete groups.')
    report = {'passed': True, 'rollouts': len(jobs), 'tasks': len(groups), 'counts': counts,
              'policy_id': policy_id(config), 'fingerprint': collection_fingerprint(config),
              'all_response_ids_decode_exactly': True, 'all_prompt_ids_reconstruct_exactly': True,
              'initial_prompts_match_raw_branch': True, 'all_old_logprobs_aligned_and_finite': True,
              'success_count_histogram_per_task': dict(Counter(sum(v) for v in groups.values())),
              'pre_recovery_trajectories_unchanged': len(retained),
              'runtime_fingerprint': maintenance['approved_runtime_fingerprint'],
              'new_rollout_runtime_provenance_verified': True}
    name = 'first_rollout_validation.json' if args.first_job else 'collection_validation.json'
    atomic_json(DIRECTORY / name, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
