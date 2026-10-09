"""Only LoRA comparison step 1: full train90 x 6. Dry run by default; no judge/training/dev."""
import argparse
import csv
import fcntl
import json
import os
import signal
import subprocess
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from common import input_fingerprint, ROOT, atomic_json, file_sha, ids, collection_fingerprint, load_config, read_json, validate_tokens
from policy_server import owned_server
from initial_policy import RUNS, adapter_path, ensure_manifest, rollout_jobs

DIRECTORY = RUNS / 'step01_train90_rollouts'
REPORT = ROOT / 'RUBRIC_GRPO_EXPERIMENT_REPORT.md'
START, END = '<!-- LORA_STEP01_PROGRESS_START -->', '<!-- LORA_STEP01_PROGRESS_END -->'

def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')

def compact_record(job):
    path = Path(job['output'])
    trajectory = read_json(path)
    if trajectory['job'] != job or trajectory['public_task']['task_id'] != job['task_id']:
        raise ValueError('Trajectory identity/policy/config mismatch.')
    steps = trajectory['steps']
    if not steps:
        raise ValueError('Completed trajectory must include action tokens.')
    for step in steps:
        validate_tokens(step['prompt_ids'], step['response_ids'], step['old_logprobs'])
    official = trajectory['official_evaluation']
    if type(official['success']) is not bool or official['num_tests'] <= 0:
        raise ValueError('Missing official terminal evaluation.')
    return {'task_id': job['task_id'], 'sample': job['sample'], 'seed': job['seed'],
            'trajectory': str(path), 'sha256': file_sha(path), 'steps': len(steps),
            'generated_tokens': sum(len(s['response_ids']) for s in steps),
            'prompt_tokens': sum(len(s['prompt_ids']) for s in steps),
            'success': official['success'], 'termination': trajectory['termination'],
            'elapsed_seconds': trajectory['elapsed_seconds'], 'policy_id': job['policy_id']}

def initialize_report(config):
    if REPORT.exists() and START in REPORT.read_text():
        return
    with REPORT.open('a') as handle:
        handle.write('\n## LoRA 起点：完整 train90 采样\n\n'
                     '从固定的 train90/epoch5 adapter 开始；独立目录、同任务和种子。\n\n'
                     + START + '\n尚未开始。\n' + END + '\n')

def progress(config, records, status, started_at, elapsed, error=None):
    tasks = ids(ROOT / config['collection']['tasks'])
    groups = defaultdict(list)
    for row in records.values():
        groups[row['task_id']].append(row)
    n = len(records)
    summary = {'phase': 'lora_step01_collection_only', 'initialization': 'train90_codex_sft_epoch5', 'status': status, 'started_at': started_at,
               'updated_at': now(), 'elapsed_seconds_current_invocation': elapsed,
               'fingerprint': collection_fingerprint(config), 'runtime_fingerprint': input_fingerprint(config), 'target_tasks': len(tasks), 'target_rollouts': len(tasks) * 6,
               'completed_rollouts': n, 'completed_groups': sum(len(v) == 6 for v in groups.values()),
               'complete_group_success_histogram': dict(Counter(str(sum(r['success'] for r in v)) for v in groups.values() if len(v) == 6)), 'tasks_with_any_rollout': len(groups), 'official_successful_rollouts': sum(r['success'] for r in records.values()),
               'completed_groups_with_any_success': sum(len(v) == 6 and any(r['success'] for r in v) for v in groups.values()),
               'termination_counts': Counter(r['termination'] for r in records.values()),
               'total_steps': sum(r['steps'] for r in records.values()),
               'generated_tokens': sum(r['generated_tokens'] for r in records.values()),
               'prompt_tokens': sum(r['prompt_tokens'] for r in records.values()),
               'codex_calls': 0, 'optimizer_updates': 0, 'dev_rollouts': 0, 'error': error}
    atomic_json(DIRECTORY / 'progress.json', summary)
    atomic_json(DIRECTORY / 'trajectory_index.json', sorted(records.values(), key=lambda r: (tasks.index(r['task_id']), r['sample'])))
    with (DIRECTORY / 'task_summary.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['task_id', 'completed_rollouts', 'official_successes', 'total_steps', 'generated_tokens'])
        for task in tasks:
            group = groups.get(task, [])
            writer.writerow([task, len(group), sum(r['success'] for r in group),
                             sum(r['steps'] for r in group), sum(r['generated_tokens'] for r in group)])
    state = {'running': '运行中', 'complete': '已完成', 'failed': '遇到问题，待恢复'}[status]
    body = (f'更新时间：{summary["updated_at"]}。状态：**{state}**。\n\n'
            '| 项目 | 当前值 |\n| --- | --- |\n'
            f'| 完整轨迹 | {n} / {len(tasks) * 6} |\n'
            f'| 已收齐 6 条的任务 | {summary["completed_groups"]} / {len(tasks)} |\n'
            f'| 官方终态成功的轨迹 | {summary["official_successful_rollouts"]} / {n} |\n'
            f'| 完整组中至少一条成功的任务 | {summary["completed_groups_with_any_success"]} / {summary["completed_groups"]} |\n'
            f'| 模型生成步骤 | {summary["total_steps"]} |\n'
            f'| 生成 token | {summary["generated_tokens"]} |\n'
            '| Codex 调用 / GRPO 更新 / dev 轨迹 | 0 / 0 / 0 |\n\n'
            '终止原因计数：' + json.dumps(summary['termination_counts'], ensure_ascii=False) + '。\n\n'
            '产物：[逐任务统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/task_summary.csv)、'
            '[轨迹索引与校验值](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectory_index.json)、'
            '[进度 JSON](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/progress.json)。\n\n'
            '**上述成功比例来自 train 随机采样，只用于数据诊断，不能当成 dev 成绩。**\n')
    if error:
        body += '\n运行问题：' + error + '\n'
    text = REPORT.read_text()
    before, remainder = text.split(START, 1)
    _, after = remainder.split(END, 1)
    temporary = REPORT.with_suffix('.md.tmp')
    temporary.write_text(before + START + '\n' + body + END + after)
    temporary.replace(REPORT)
    return summary

def execute(config):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    fingerprint = ensure_manifest(config)
    tasks = ids(ROOT / config['collection']['tasks'])
    if tasks != ids(Path(config['paths']['appworld_data']) / 'datasets/train.txt') or len(tasks) != 90:
        raise ValueError('Step 1 requires the complete official train90.')
    if config['collection']['rollouts_per_task'] != 6 or config['sampling']['group_size'] != 6:
        raise ValueError('Step 1 requires six rollouts per task.')
    jobs = rollout_jobs(config, DIRECTORY, tasks, None, update=0)
    manifest_path = DIRECTORY / 'collection_manifest.json'
    if manifest_path.exists():
        saved = read_json(manifest_path)
        if saved['jobs'] != jobs or saved['fingerprint'] != fingerprint:
            raise ValueError('Existing collection jobs changed.')
    else:
        atomic_json(manifest_path, {'fingerprint': fingerprint, 'config': config,
                    'task_ids': tasks, 'jobs': jobs, 'policy': 'Qwen3-8B_train90_codex_sft_epoch5',
                    'initial_adapter': config['initial_policy'], 'judge_enabled': False, 'training_enabled': False})
    initialize_report(config)
    records, pending = {}, []
    for job in jobs:
        if Path(job['output']).exists():
            records[job['episode_id']] = compact_record(job)
        else:
            pending.append(job)
    if not pending and (DIRECTORY / 'summary.json').exists():
        subprocess.run([config['paths']['training_python'], str(ROOT / 'verify_collection.py')], cwd=ROOT, check=True)
        subprocess.run([config['paths']['appworld_python'], str(ROOT / 'compare_collections.py'), '--write'], cwd=ROOT, check=True)
        print('All 540 LoRA rollouts complete and validated; preserving the original summary.')
        return
    started_at, started = now(), time.monotonic()
    progress(config, records, 'running', started_at, 0)
    active, process_lock = {}, threading.Lock()
    def one(job):
        job_path = DIRECTORY / 'jobs' / (job['episode_id'] + '.json')
        atomic_json(job_path, job)
        log_path = job_path.with_suffix('.log')
        with log_path.open('a') as log:
            process = subprocess.Popen([config['paths']['appworld_python'], '-u', str(ROOT / 'rollout_worker.py'),
                                        '--job', str(job_path), '--execute'], cwd=ROOT,
                                       env=dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONUNBUFFERED='1'),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            with process_lock:
                active[process.pid] = process
            try:
                result = process.wait(timeout=config['agent']['max_steps'] * (config['server']['request_timeout_seconds'] + 60))
                if result:
                    raise RuntimeError(f'Worker failed ({result}); see {log_path}')
                return compact_record(job)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                with process_lock:
                    active.pop(process.pid, None)
    def accept(job, row):
        records[job['episode_id']] = row
        progress(config, records, 'running', started_at, time.monotonic() - started)
        print(f'{now()} completed={len(records)}/{len(jobs)} task={row["task_id"]} sample={row["sample"]} steps={row["steps"]} success={row["success"]}', flush=True)
    try:
        if pending:
            if records:
                completed = next(j for j in jobs if j['episode_id'] in records)
                subprocess.run([config['paths']['training_python'], str(ROOT / 'verify_collection.py'),
                                '--first-job', str(DIRECTORY / 'jobs' / (completed['episode_id'] + '.json'))],
                               cwd=ROOT, check=True)
            with owned_server(config, DIRECTORY, adapter_path(config)):
                if not records:
                    first = pending.pop(0)
                    accept(first, one(first))
                    subprocess.run([config['paths']['training_python'], str(ROOT / 'verify_collection.py'),
                                    '--first-job', str(DIRECTORY / 'jobs' / (first['episode_id'] + '.json'))],
                                   cwd=ROOT, check=True)
                executor = ThreadPoolExecutor(max_workers=config['collection']['workers'])
                futures, iterator = {}, iter(pending)
                try:
                    for _ in range(config['collection']['workers']):
                        job = next(iterator, None)
                        if job is not None:
                            futures[executor.submit(one, job)] = job
                    while futures:
                        done, _ = wait(futures, return_when=FIRST_COMPLETED)
                        for future in done:
                            job = futures.pop(future)
                            accept(job, future.result())
                            next_job = next(iterator, None)
                            if next_job is not None:
                                futures[executor.submit(one, next_job)] = next_job
                finally:
                    with process_lock:
                        for process in active.values():
                            if process.poll() is None:
                                try:
                                    os.killpg(process.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                    executor.shutdown(wait=True, cancel_futures=True)
        if len(records) != len(jobs) or any(sum(r['task_id'] == t for r in records.values()) != 6 for t in tasks):
            raise ValueError('Incomplete collection.')
        summary = progress(config, records, 'complete', started_at, time.monotonic() - started)
        atomic_json(DIRECTORY / 'summary.json', summary)
        subprocess.run([config['paths']['training_python'], str(ROOT / 'verify_collection.py')], cwd=ROOT, check=True)
        subprocess.run([config['paths']['appworld_python'], str(ROOT / 'compare_collections.py'), '--write'], cwd=ROOT, check=True)
        with REPORT.open('a') as handle:
            handle.write(f'\n- {now()}：LoRA 对照分支第一步完成，540 条轨迹、90 个完整组。未执行规则评分或 GRPO。\n')
    except BaseException as error:
        progress(config, records, 'failed', started_at, time.monotonic() - started, f'{type(error).__name__}: {error}')
        raise

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    if not args.execute:
        from preflight import inspect
        report, _ = inspect(load_config())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    config = load_config()
    RUNS.mkdir(exist_ok=True)
    with (RUNS / '.execution.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(config)

if __name__ == '__main__':
    main()
