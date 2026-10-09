"""One isolated AppWorld rollout, called only after explicit --execute."""
from __future__ import annotations
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from common import collection_fingerprint, execution_provenance, ROOT, atomic_json, check_training_ids, ids, load_config, parse_code, text_to_messages
from policy_server import sample_step

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--job', type=Path, required=True)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    if not args.execute:
        ap.error('No rollout without --execute; wait for the user to start the experiment.')
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    config = load_config()
    job = json.loads(args.job.read_text())
    if job['fingerprint'] != collection_fingerprint(config):
        raise ValueError('Job and frozen collection identity differ.')
    provenance = execution_provenance(config)
    if job['mode'] == 'train':
        check_training_ids([job['task_id']], config)
    elif job['mode'] != 'dev' or job['task_id'] not in ids(ROOT / config['evaluation']['tasks']):
        raise ValueError('Unknown split/task.')
    runtime = ROOT / 'runtime' / job['runtime_name']
    os.environ['APPWORLD_ROOT'] = str(runtime)
    from appworld import AppWorld, update_root
    update_root(str(runtime))
    from appworld_log_compat import install_request_log_compatibility
    log_compat = install_request_log_compatibility()
    from appworld.task import Task
    from appworld.apps.lib.models.db import CachedDBHandler
    from jinja2 import StrictUndefined, Template
    task = Task.load(task_id=job['task_id'], load_ground_truth=False)
    try:
        rendered = Template((ROOT / config['agent']['prompt']).read_text().lstrip(), undefined=StrictUndefined).render(
            instruction=task.instruction, main_user=task.supervisor,
            app_descriptions=json.dumps([{'name': k, 'description': v} for k, v in task.app_descriptions.items()], ensure_ascii=False, indent=1))
        public = {'task_id': task.id, 'instruction': task.instruction,
                  'supervisor': {k: getattr(task.supervisor, k) for k in ('first_name', 'last_name', 'email', 'phone_number')},
                  'datetime': task.datetime.isoformat()}
    finally:
        task.close()
        CachedDBHandler.reset()
    initial_messages = text_to_messages(rendered)
    messages = [dict(m) for m in initial_messages]
    steps = []
    termination = 'step_limit'
    output = Path(job['output'])
    # Hidden tests stay inside AppWorld; policy and judge see only public allowlists.
    with AppWorld(task_id=job['task_id'], experiment_name=job['episode_id'],
                  max_interactions=config['agent']['max_steps'], load_ground_truth=True,
                  ground_truth_mode='minimal', raise_on_failure=True) as world:
        for turn in range(config['agent']['max_steps']):
            sample = sample_step(config, job['model'], messages,
                                 (job['seed'] + turn) % (2**31 - 1), evaluation=job['mode'] == 'dev')
            if sample is None:
                termination = 'context_limit'
                break
            code, fixed_text = parse_code(sample['text'])
            observation = world.execute(code) if code else ''
            steps.append(dict(sample, step=turn + 1, code=code, observation=observation,
                              history_assistant_text=fixed_text))
            atomic_json(output.with_suffix('.partial.json'), {'job': job, 'steps': steps})
            messages.append({'role': 'assistant', 'content': fixed_text + '\n\n'})
            if not code:
                termination = 'no_python_code'
                break
            fence = chr(96) * 3
            messages.append({'role': 'user', 'content': 'Output:\n' + fence + '\n' + observation.rstrip() + '\n' + fence + '\n\n'})
            if world.task_completed():
                termination = 'completion_api'
                break
        tracker = world.evaluate(suppress_errors=True)
        evaluation = {'success': bool(tracker.success), 'num_tests': int(tracker.num_tests),
                      'num_passes': int(tracker.pass_count), 'num_failures': int(tracker.fail_count)}
        if evaluation['num_tests'] <= 0:
            raise RuntimeError('Evaluator returned no tests: infrastructure failure, not reward=0.')
    CachedDBHandler.reset()
    atomic_json(output, {'format_version': 1, 'job': job, 'public_task': public,
                         'initial_messages': initial_messages, 'steps': steps,
                         'termination': termination, 'official_evaluation': evaluation,
                         'started_at_utc': started_at, 'elapsed_seconds': time.monotonic() - started,
                         'execution_provenance': provenance, 'log_compatibility': log_compat})
    output.with_suffix('.partial.json').unlink(missing_ok=True)
    print(json.dumps({'task': job['task_id'], 'steps': len(steps), 'termination': termination, 'success': evaluation['success']}))

if __name__ == '__main__':
    main()
