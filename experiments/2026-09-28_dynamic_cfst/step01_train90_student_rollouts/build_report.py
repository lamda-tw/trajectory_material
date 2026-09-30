#!/usr/bin/env python3
"""Summarize the frozen train90 run without changing its original scoring records."""
from __future__ import annotations
import collections
import csv
import datetime
import hashlib
import json
import re
from pathlib import Path

STAGE = Path(__file__).resolve().parent
OUTPUT = STAGE / 'experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train'

def read_json(path):
    return json.loads(path.read_text())

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    manifest = read_json(STAGE / 'manifest.json')
    ids = (STAGE / 'config/task_ids.txt').read_text().splitlines()
    official_path = OUTPUT / 'evaluations/train.json'
    if not official_path.exists():
        raise SystemExit('Official aggregate is not available; no final results generated.')
    official = read_json(official_path)
    individual = official['individual']
    raw_status = read_jsonl(STAGE / 'task_status.jsonl')
    status_counts = collections.Counter(row['task_id'] for row in raw_status)
    status = {row['task_id']: row for row in raw_status}
    records, hashes, problems, protocol_errors = [], {}, [], []
    expected_request = {'model': manifest['served_adapter_name'], 'temperature': 0.0, 'seed': 100, 'max_completion_tokens': 3000}
    if len(ids) != 90 or len(set(ids)) != 90:
        problems.append('Expected exactly 90 unique task IDs.')
    if set(individual) != set(ids):
        problems.append('Official aggregate IDs differ from the frozen train90 list.')
    if set(status) != set(ids) or len(raw_status) != 90:
        problems.append('Per-task status coverage or uniqueness mismatch.')
    for task_id in ids:
        root = OUTPUT / 'tasks' / task_id
        logs = root / 'logs'
        item = individual.get(task_id, {})
        live = status.get(task_id, {})
        calls = read_jsonl(logs / 'lm_calls.jsonl')
        events = read_jsonl(logs / 'logger.jsonl')
        env_path = logs / 'environment_io.md'
        env_text = env_path.read_text() if env_path.exists() else ''
        finished = (root / 'misc/finished').exists()
        report_exists = (root / 'evaluation/report.md').exists()
        infra = not (finished and report_exists and task_id in individual and calls and env_text)
        if live.get('status') == 'evaluation_error':
            infra = True
        succeeded = item.get('success') if task_id in individual else None
        task_status = 'infrastructure_error' if infra else ('success' if succeeded else 'failed')
        if task_id in individual and live.get('status') in ('success','failed'):
            if (live['status'] == 'success') != succeeded:
                problems.append(f'{task_id}: live and aggregate success disagree')
            if live['passed_tests'] != len(item.get('passes', [])) or live['failed_tests'] != len(item.get('failures', [])):
                problems.append(f'{task_id}: assertion counts disagree')
        request_errors = []
        context_errors = []
        input_tokens = output_tokens = 0
        empty_responses = 0
        for index, call in enumerate(calls, 1):
            inp, out = call['input'], call['output']
            for key, expected in expected_request.items():
                if inp.get(key) != expected:
                    protocol_errors.append({'task_id':task_id,'call':index,'key':key,'expected':expected,'actual':inp.get(key)})
            usage = out.get('usage') or {}
            input_tokens += int(usage.get('prompt_tokens', 0) or 0)
            output_tokens += int(usage.get('completion_tokens', 0) or 0)
            error = out.get('error')
            if error:
                request_errors.append(str(error))
                if any(word in str(error).lower() for word in ['maximum context length','context length','max_tokens','max_completion_tokens','maximum model length','longer than']):
                    context_errors.append(str(error))
            choice = (out.get('choices') or [{}])[0]
            message = choice.get('message') or {}
            if not (message.get('content') or '').strip():
                empty_responses += 1
        actions = len(re.findall(r'^### Environment Interaction \d+', env_text, re.M))
        if task_status == 'infrastructure_error':
            reason = 'incomplete_or_missing_run_or_evaluation_artifact'
        elif succeeded:
            reason = 'official_success'
        elif context_errors:
            reason = 'context_window_limit'
        elif request_errors:
            reason = 'model_request_error'
        elif len(calls) >= 50 and not any('apis.supervisor.complete_task(' in str(event.get('content','')) for event in events if event.get('role') in ('agent', 'assistant')):
            reason = 'step_limit_without_submission'
        else:
            reason = 'official_tests_failed'
        row = {
            'task_id':task_id, 'scenario_id':task_id.rsplit('_',1)[0],
            'status':task_status, 'official_success':succeeded, 'difficulty':item.get('difficulty'),
            'lm_calls':len(calls), 'executed_steps':actions,
            'api_calls':len(read_jsonl(logs / 'api_calls.jsonl')),
            'passed_tests':len(item.get('passes',[])), 'failed_tests':len(item.get('failures',[])),
            'num_tests':item.get('num_tests'), 'elapsed_seconds':live.get('elapsed_seconds'),
            'input_tokens':input_tokens, 'output_tokens':output_tokens,
            'context_error_count':len(context_errors), 'request_error_count':len(request_errors),
            'empty_response_count':empty_responses,
            'has_python_execution_error':'execution failed. traceback' in env_text.lower(),
            'finished':finished, 'termination_category':reason,
            'trajectory_dir':str(root), 'lm_calls_path':str(logs / 'lm_calls.jsonl'),
            'environment_io_path':str(env_path), 'official_report_path':str(root / 'evaluation/report.md'),
        }
        records.append(row)
        required = ['logs/lm_calls.jsonl','logs/environment_io.md','logs/api_calls.jsonl','logs/logger.jsonl','misc/finished','evaluation/report.md']
        for name in required:
            path = root / name
            if not path.exists():
                problems.append(f'{task_id}: missing {name}')
            else:
                hashes[str(path.relative_to(STAGE))] = sha(path)
    success = [r['task_id'] for r in records if r['status']=='success']
    failed = [r['task_id'] for r in records if r['status']=='failed']
    infra = [r['task_id'] for r in records if r['status']=='infrastructure_error']
    for name, task_ids in [('success',success),('failed',failed),('infrastructure_error',infra)]:
        (STAGE / f'{name}_task_ids.txt').write_text(''.join(task+'\n' for task in task_ids))
    with (STAGE / 'task_results.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    with (STAGE / 'trajectory_index.jsonl').open('w') as stream:
        for row in records:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    grouped = collections.defaultdict(list)
    difficulty = collections.defaultdict(lambda: {'total':0,'success':0})
    for row in records:
        grouped[row['scenario_id']].append(row['status']=='success')
        difficulty[str(row['difficulty'])]['total'] += 1
        difficulty[str(row['difficulty'])]['success'] += row['status']=='success'
    scenarios_success = sum(all(values) for values in grouped.values())
    computed_tgc = round(100*len(success)/len(ids),1)
    computed_sgc = round(100*scenarios_success/len(grouped),1)
    if official['aggregate']['task_goal_completion'] != computed_tgc:
        problems.append('TGC aggregate mismatch')
    if official['aggregate']['scenario_goal_completion'] != computed_sgc:
        problems.append('SGC aggregate mismatch')
    adapter_hash = sha(Path(manifest['adapter'])/'adapter_model.safetensors')
    if adapter_hash != manifest['adapter_sha256']:
        problems.append('Adapter changed since preparation')
    reference = Path(manifest['reference_evaluation'])/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev.jsonnet'
    config = STAGE/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train.jsonnet'
    config_matches = config.read_text() == reference.read_text().replace('"dataset": "dev"','"dataset": "train"')
    if not config_matches:
        problems.append('Configuration differs beyond the dataset name')
    if protocol_errors:
        problems.append('Some actual model requests differ from the reference settings')
    if manifest.get('exit_code') != 0:
        problems.append('Run did not exit successfully')
    runtime_fields = ['lm_calls','executed_steps','api_calls','input_tokens','output_tokens','request_error_count','context_error_count','empty_response_count']
    started = datetime.datetime.fromisoformat(manifest['run_started_at'])
    finished_time = datetime.datetime.fromisoformat(manifest['run_finished_at'])
    summary = {
        'experiment':str(STAGE),'dataset':'train','task_count':90,'scenario_count':len(grouped),
        'success_count':len(success),'failure_count':len(failed),'infrastructure_error_count':len(infra),
        'success_ids':success,'failed_ids':failed,'infrastructure_error_ids':infra,
        'official_scores':official['aggregate'],'successful_scenario_count':scenarios_success,
        'evaluator_tests':{'passed':sum(r['passed_tests'] for r in records),'total':sum(r['num_tests'] or 0 for r in records)},
        'difficulty':dict(difficulty),'runtime':{k:sum(r[k] for r in records) for k in runtime_fields},
        'context_error_task_ids':[r['task_id'] for r in records if r['context_error_count']],
        'termination_categories':dict(collections.Counter(r['termination_category'] for r in records)),
        'duration_seconds':round((finished_time-started).total_seconds(),3),
        'run_started_at':manifest['run_started_at'],'run_finished_at':manifest['run_finished_at'],
        'new_training':False,'teacher_calls':0,'source_adapter_unchanged':adapter_hash==manifest['adapter_sha256'],
        'validation_passed':not problems and not infra,
    }
    validation = {
        'passed':summary['validation_passed'],'problems':problems,'protocol_errors':protocol_errors,
        'unique_dataset_tasks':len(set(ids)),'unique_status_tasks':len(status),'status_rows':len(raw_status),
        'official_tasks':len(individual),'complete_trajectory_count':sum(r['finished'] and r['lm_calls']>0 and r['executed_steps']>0 for r in records),
        'hashed_evidence_files':len(hashes),'config_matches_reference_except_dataset':config_matches,
        'adapter_sha256_verified':adapter_hash,'validated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    dump(STAGE/'summary.json',summary)
    dump(STAGE/'metrics/final_validation.json',validation)
    hashes[str(official_path.relative_to(STAGE))] = sha(official_path)
    dump(STAGE/'metrics/evidence_sha256.json',hashes)
    score=summary['official_scores']
    context_tasks=len(summary['context_error_task_ids'])
    report = f'''# 第一步结果：Qwen3-8B LoRA epoch5 的 train90 学生轨迹

本轮完成 {len(records)} 道训练任务的记录整理。官方成功 **{len(success)}/90（{score['task_goal_completion']}%）**，失败 **{len(failed)}**，运行或评分产物不完整 **{len(infra)}**。完整性核验：**{'通过' if validation['passed'] else '未通过，请查看 metrics/final_validation.json'}**。

## 本次运行做了什么

使用现有 Qwen3-8B 和 train90 LoRA 第 5 轮 adapter，按原 LoRA Dev 评测协议运行全部 train90。只采集学生轨迹与官方评分；没有训练新模型，没有调用 Codex 修复，没有根据结果重跑失败任务。

这些任务已用于原模型 SFT，本轮用于获取学生真实行为和失败现场，不作为未见任务泛化成绩。

- 开始：{manifest['run_started_at']}。
- 结束：{manifest['run_finished_at']}。
- 含模型服务启动的总耗时：{summary['duration_seconds']/60:.1f} 分钟。
- 基座：{manifest['model']}。
- Adapter：{manifest['adapter']}。
- 原协议：temperature=0、seed=100、每题最多50步、单次最多3000输出 tokens、上下文32000、无 reasoning parser、单 GPU 顺序执行。
- 固定提示词、任务顺序、运行配置和来源校验保存在 config/；实际每次模型请求均检查协议字段。

## 官方结果

| 项目 | 结果 |
| --- | --- |
| 成功任务 | {len(success)}/90 |
| 失败任务 | {len(failed)}/90 |
| 完整成功场景 | {scenarios_success}/{len(grouped)} |
| TGC / SGC | {score['task_goal_completion']} / {score['scenario_goal_completion']} |
| 通过官方测试项 | {summary['evaluator_tests']['passed']}/{summary['evaluator_tests']['total']} |
| 模型请求次数 | {summary['runtime']['lm_calls']} |
| 实际执行步骤 | {summary['runtime']['executed_steps']} |
| 上下文超限涉及任务 | {context_tasks} |
| 基础设施或评分产物异常 | {len(infra)} |

上下文超限保留为原协议下的实际结果，不扩窗重试，也不把它混同为服务崩溃。模型生成代码的执行报错仍保留在轨迹中，供下一步审查；本次不做能力标签或错误根因标注。

## 从哪里查看

- **逐题总表：** [task_results.csv](task_results.csv)，含成功/失败、官方断言数、执行步数、模型调用数、耗时和轨迹路径。
- **成功清单：** [success_task_ids.txt](success_task_ids.txt)。
- **失败清单：** [failed_task_ids.txt](failed_task_ids.txt)。
- **运行/评分异常清单：** [infrastructure_error_task_ids.txt](infrastructure_error_task_ids.txt)。
- **机器可读汇总：** [summary.json](summary.json)。
- **逐题轨迹索引：** [trajectory_index.jsonl](trajectory_index.jsonl)。
- **原始逐题即时评分：** [task_status.jsonl](task_status.jsonl)，与官方最终聚合逐题核对，保留原记录。
- **官方聚合评分：** [train.json](experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/evaluations/train.json)。
- **最终核验：** [final_validation.json](metrics/final_validation.json)。

每个任务的目录位于 experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/tasks/任务号/，其中：

| 文件 | 内容 |
| --- | --- |
| logs/lm_calls.jsonl | 每次真实模型请求（完整历史）与原始响应 |
| logs/environment_io.md | 按步骤排列的执行代码与环境返回 |
| logs/api_calls.jsonl | 实际工具/API 调用 |
| logs/logger.jsonl | 结构化 agent 交互及步骤编号 |
| dbs/ | 本轮任务环境产生的数据库状态 |
| misc/finished | 任务运行结束标记，成功与失败均可能有此标记 |
| evaluation/report.md | 官方逐题评估报告 |

原始轨迹、数据库、缓存和模型日志只保留本地。下一步在并列的 step02_error_analysis/ 下执行，本次尚未开始。
'''
    (STAGE/'REPORT.md').write_text(report)
    manifest['status'] = 'completed' if validation['passed'] else 'validation_failed'
    manifest['validated_at_utc'] = validation['validated_at_utc']
    dump(STAGE/'manifest.json',manifest)
    print(json.dumps({'success':len(success),'failed':len(failed),'infrastructure_errors':len(infra),'validated':validation['passed'],'problems':problems},ensure_ascii=False))
    if not validation['passed']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
