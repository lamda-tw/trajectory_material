"""One isolated online training trajectory, no within-trajectory judge calls."""
from b_common import R, B, read, write_json, config, authorize, CPU, file_sha
from a_common import parse_code
from a_policy_server import sample_step
import argparse
import json
import os
import re
import time
from pathlib import Path


def main(job_path):
    cfg = config(); job = read(job_path); mode=job.get('mode','train')
    assert mode in ('train','dev')
    authorize('evaluation_allowed' if mode=='dev' else 'rollout_allowed')
    assert job['task_id'] in (B / ('config/dev57.txt' if mode=='dev' else 'config/train90.txt')).read_text().split()
    assert job['config_sha256'] == file_sha(B / 'config/run.json')
    runtime = Path(job['runtime']); runtime.mkdir(parents=True, exist_ok=True)
    for relative, source in [('data', cfg['paths']['appworld_data']), ('cache/tests', cfg['paths']['appworld_test_cache'])]:
        path = runtime / relative; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.symlink_to(source, target_is_directory=True)
    os.environ.update(CPU, APPWORLD_ROOT=str(runtime), APPWORLD_CACHE=str(runtime/'cache'))
    os.chdir(runtime)
    from appworld import AppWorld, update_root
    from appworld.task import Task
    from appworld.apps.lib.models.db import CachedDBHandler
    from jinja2 import Template, StrictUndefined
    from b_appworld_log_compat import install_request_log_compatibility
    update_root(str(runtime)); log_compat = install_request_log_compatibility()
    task = Task.load(task_id=job['task_id'], load_ground_truth=False)
    try:
        rendered = Template((R / cfg['agent']['prompt']).read_text().lstrip(), undefined=StrictUndefined).render(
            instruction=task.instruction, main_user=task.supervisor,
            app_descriptions=json.dumps([{'name': k, 'description': v} for k,v in task.app_descriptions.items()], ensure_ascii=False, indent=1))
    finally:
        task.close(); CachedDBHandler.reset()
    parts = re.split(r'(?:^|\n)(USER|ASSISTANT|SYSTEM):\n', rendered.lstrip())
    assert not parts[0].strip() and len(parts) >= 3
    initial = [{'role': parts[i].lower(), 'content': parts[i+1].strip()} for i in range(1,len(parts),2)]
    messages = [dict(m) for m in initial]; steps = []; termination = 'step_limit'; started = time.monotonic()
    output = Path(job['output'])
    with AppWorld(task_id=job['task_id'], experiment_name=job['episode_id'], max_interactions=cfg['agent']['max_steps'],
                  load_ground_truth=True, ground_truth_mode='minimal', random_seed=100, raise_on_failure=True) as world:
        for turn in range(cfg['agent']['max_steps']):
            sample = sample_step(cfg, job['model'], messages, (job['seed']+turn) % (2**31-1), evaluation=mode=='dev')
            if sample is None: termination='context_limit'; break
            code, history = parse_code(sample['text'])
            observation = world.execute(code) if code else ''
            steps.append({**sample, 'step': turn+1, 'code': code, 'observation': observation, 'history_assistant_text': history})
            write_json(output.with_suffix('.partial.json'), {'job':job, 'initial_messages':initial, 'steps':steps})
            messages.append({'role':'assistant', 'content':history+'\n\n'})
            if not code: termination='no_python_code'; break
            messages.append({'role':'user','content':'Output:\n```\n'+observation.rstrip()+'\n```\n\n'})
            if world.task_completed(): termination='completion_api'; break
        # Official evaluation stays local and is used ONLY by the separate final dev run.
        evaluation=None
        if mode=='dev':
            tracker=world.evaluate(suppress_errors=True)
            assert tracker.num_tests>0,'Evaluator returned no tests'
            evaluation={'success':bool(tracker.success),'num_tests':int(tracker.num_tests),'num_passes':int(tracker.pass_count),'num_failures':int(tracker.fail_count)}
    CachedDBHandler.reset()
    assert steps, 'No sampled action; infrastructure/context failure, do not replace the task'
    write_json(output, {'format_version':1,'job':job,'initial_messages':initial,'steps':steps,'termination':termination,
                        'elapsed_seconds':time.monotonic()-started,'official_evaluation':evaluation,'log_compatibility':log_compat})
    print(json.dumps({'task':job['task_id'],'steps':len(steps),'termination':termination}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    main(parser.parse_args().job)
