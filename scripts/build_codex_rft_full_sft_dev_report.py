#!/usr/bin/env python3
"""Audit train90 full-SFT Dev57 against the matching LoRA run and report in Chinese."""
from __future__ import annotations
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from build_appworld_full_sft_aligned_dev_report import (
    DEFAULT_APPWORLD_EXPERIMENT, atomic_write_json, atomic_write_text,
    audit_run, audit_task_status, collect_runtime, load_score_snapshot,
    load_task_ids, read_json, read_jsonl, sha256, transition,
)


def joined(values):
    return '、'.join(values) or '无'


def audit_protocol(exp, lora, ids, manifest):
    root = Path('experiments/outputs') / DEFAULT_APPWORLD_EXPERIMENT
    preflight = read_json(exp / 'config/protocol_preflight.json')
    assert preflight['status'] == 'PASS' and not preflight['training_dev_task_overlap']
    model_integrity = read_json(exp / 'config/model_integrity.json')
    assert model_integrity['status'] == 'PASS' and model_integrity['weight_files_verified'] == 5
    assert sha256(exp / 'data/datasets/dev.txt') == manifest['dev_split_sha256']
    config = Path('config/agent_configs') / (DEFAULT_APPWORLD_EXPERIMENT + '.jsonnet')
    assert sha256(exp / config) == sha256(lora / config) == preflight['agent_config_sha256']
    prompt_matches, request_count, mismatches = [], 0, []
    empty_content, finish_reasons = 0, {}
    error_responses = []
    unexplained_empty, successful_without_python = 0, 0
    for task_id in ids:
        relative = root / 'tasks' / task_id / 'logs/lm_calls.jsonl'
        current, malformed = read_jsonl(exp / relative)
        reference, reference_malformed = read_jsonl(lora / relative)
        assert not malformed and not reference_malformed and current and reference, task_id
        if current[0]['input']['messages'] == reference[0]['input']['messages']:
            prompt_matches.append(task_id)
        for row in current:
            request = row['input']
            request_count += 1
            expected = {'temperature': 0, 'seed': 100, 'max_completion_tokens': 3000,
                        'api_type': 'chat_completions', 'client_name': 'openai',
                        'model': 'appworld-qwen3-8b-codex-rft-train90-epoch5'}
            for key, value in expected.items():
                if request.get(key) != value:
                    mismatches.append({'task_id': task_id, 'field': key, 'actual': request.get(key)})
            choice = row['output']['choices'][0]
            content = choice['message'].get('content')
            empty_content += content == ''
            error = row['output'].get('error')
            if error:
                match = re.search(r'request has (\d+) input tokens', error)
                input_tokens = int(match.group(1)) if match else None
                kind = ('input_exceeds_context' if input_tokens is not None and input_tokens > 32000
                        else 'input_plus_output_exceeds_context' if 'maximum context length' in error else 'other')
                error_responses.append({'task_id': task_id, 'kind': kind, 'input_tokens': input_tokens,
                                        'placeholder_content_empty': content == '',
                                        'usage_tokens': row['output']['usage']['total_tokens']})
            else:
                unexplained_empty += not bool(content)
                successful_without_python += not bool(re.search(r'```python\s+.+?(?:```|$)', content or '', re.DOTALL))
            reason = str(choice.get('finish_reason'))
            finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
    assert len(prompt_matches) == 57, 'Initial prompts differ: ' + joined(sorted(set(ids)-set(prompt_matches)))
    assert not mismatches, mismatches[:10]
    # Generated config files precede runtime overrides; audit the actual server log as well.
    text = (exp / 'logs/run.log').read_text(errors='replace')
    server_lines = [line for line in text.splitlines() if line.startswith('--served-model-name ')]
    assert len(server_lines) == 1 and '--max-model-len 32000' in server_lines[0]
    assert '--reasoning-parser' not in server_lines[0] and '--enable-lora' not in server_lines[0]
    return {'status': 'PASS', 'first_prompt_identical_tasks': len(prompt_matches),
            'request_count': request_count, 'request_parameter_mismatches': mismatches,
            'content_empty_string_count': empty_content, 'finish_reasons': finish_reasons,
            'error_responses': error_responses, 'successful_responses': request_count-len(error_responses),
            'unexplained_empty_model_responses': unexplained_empty,
            'successful_responses_without_python': successful_without_python,
            'actual_server_options': server_lines[0], 'preflight': preflight, 'model_integrity': model_integrity}


def render(summary, manifest):
    target, lora = summary['target'], summary['lora']
    runtime, old_runtime = summary['runtime'], summary['lora_runtime']
    change, run = summary['vs_lora'], summary['run_audit']
    items = [*summary['references'], lora, target]
    metric_rows = []
    for item in items:
        a, tests = item['aggregate'], item['evaluator_tests']
        metric_rows.append(f"| {item['label']} | {item['success_count']}/57 | {a['task_goal_completion']:.1f} | {a['scenario_goal_completion']:.1f} | {item['successful_scenario_count']}/19 | {tests['passed']}/{tests['total']} |")
    difficulty_rows = []
    for key in sorted(target['difficulty'], key=int):
        a, b = lora['difficulty'][key], target['difficulty'][key]
        difficulty_rows.append(f"| {key} | {a['successes']}/{a['total']} ({a['tgc']:.1f}%) | {b['successes']}/{b['total']} ({b['tgc']:.1f}%) |")
    runtime_rows = []
    for label, key in [('LM 请求（含被拒绝请求）','lm_calls'),('AppWorld API 调用','api_calls'),('输入 tokens','input_tokens'),('输出 tokens','output_tokens'),('总 tokens','total_tokens')]:
        runtime_rows.append(f"| {label} | {old_runtime.get(key,0):,} | {runtime.get(key,0):,} |")
    delta = target['aggregate']['task_goal_completion'] - lora['aggregate']['task_goal_completion']
    sgc_delta = target['aggregate']['scenario_goal_completion'] - lora['aggregate']['scenario_goal_completion']
    tests = target['evaluator_tests']
    protocol = summary['protocol_audit']
    recovery = manifest.get('startup_recovery')
    recovery_text = ('首次启动因工作区内临时 Unix socket 路径超过 107 字节而失败，尚未开始任何任务；将 TMPDIR 改为工作区内的短路径后重新启动。原始日志保存在 `logs/startup_attempt_01/`。正式 57 题运行没有因这次启动问题重做已完成任务。' if recovery else '未发生启动恢复。')
    return '\n'.join([
        '# AppWorld Codex-RFT train90 Qwen3-8B 全参数 SFT：57 题 Dev 评测报告', '',
        '## 结论', '',
        f"本次五轮全参数 SFT 模型在 57 道 Dev 题上完成真实 ReAct 推理与官方 evaluator 评分，成功 **{target['success_count']}/57**，TGC=**{target['aggregate']['task_goal_completion']:.1f}**，SGC=**{target['aggregate']['scenario_goal_completion']:.1f}**。",
        f"与相同 90 条训练轨迹、五轮训练的 LoRA 相比，成功任务数变化为 **{target['success_count']-lora['success_count']:+d}**，TGC 变化 **{delta:+.1f} 个百分点**，SGC 变化 **{sgc_delta:+.1f} 个百分点**。",
        '训练 loss 衡量训练集拟合，本报告以 Dev 端到端官方评分衡量任务完成能力。TGC 要求任务所有测试条件通过；SGC 要求同一场景的三个任务全部成功。', '',
        '## 官方指标', '',
        '| 系统 | 成功任务 | TGC | SGC | 完整成功场景 | 通过测试条件 |',
        '|---|---:|---:|---:|---:|---:|', *metric_rows, '',
        '| 难度 | train90 LoRA 成功/总数 (TGC) | train90 全参数 SFT 成功/总数 (TGC) |',
        '|---:|---:|---:|', *difficulty_rows, '',
        '## 成功任务变化', '',
        f"相对 train90 LoRA：共同成功 {change['both_success']} 题，全参数 SFT 新增成功 {change['target_only_success']} 题，退化 {change['comparison_only_success']} 题，两者均失败 {change['both_failed']} 题。", '',
        '本次成功任务：'+joined(target['success_ids']), '',
        '新增成功：'+joined(change['gained_task_ids']), '',
        '退化任务：'+joined(change['regressed_task_ids']), '',
        '完整成功场景：'+joined(target['successful_scenarios']), '',
        '完整 57 题难度、通过条件、成功状态及相对 LoRA 的变化见 [逐题 CSV](task_comparison.csv)。', '',
        '## 完整性与执行通道审计', '',
        '- Dev 清单、逐题状态与官方聚合结果均覆盖 57 个唯一任务；逐题测试条件和成功状态一致，正式进程退出码为 0。',
        f"- 官方测试条件通过 {tests['passed']}/{tests['total']}（{tests['pass_percentage']:.1f}%）；逐题 evaluator 错误为 0。",
        f"- 57/57 题第一次 LM 请求的完整 messages 与 LoRA 历史日志一致；共核对 {protocol['request_count']:,} 次请求的模型名、temperature、seed、输出上限和接口类型，全部符合协议。",
        f"- LM 请求 {runtime['lm_calls']:,} 次，其中正常回复 {protocol['successful_responses']:,} 次；服务拒绝 {len(protocol['error_responses'])} 次。日志中的 {protocol['content_empty_string_count']} 条空字符串是 AppWorld 为失败请求写入的占位记录，附有 error 和零 token 用量，并非模型生成了空回复。",
        f"- 正常模型回复中，空内容 {protocol['unexplained_empty_model_responses']} 次、无 Python fenced code {protocol['successful_responses_without_python']} 次；content=null {runtime['content_null']} 次。",
        f"- finish_reason=length 的回复：{protocol['finish_reasons'].get('length',0):,} 次；最终模型 5 个 safetensors 文件的 SHA-256 校验全部通过。",
        f"- No code available observation：{runtime['no_code_observations']:,}；AppWorld API 调用：{runtime['api_calls']:,}。",
        f"- 含 complete_task action 的任务：{runtime['complete_task_task_count']}/57；达到 50 次 LM 调用的任务：{runtime['max_step_task_count']}。",
        f"- 含 Python 执行错误的任务：{runtime['python_error_task_count']}；含语法错误的任务：{runtime['syntax_error_task_count']}。这些是任务轨迹中的模型行为，不等同于评分器故障。",
        f"- 上下文溢出终止任务：{run['context_overflow_task_count']}；任务 ID：{joined(run['context_overflow_task_ids'])}。",
        f"- 上下文拒绝中，输入本身超过 32000 的请求有 {sum(r['kind']=='input_exceeds_context' for r in protocol['error_responses'])} 次；输入加预留 3000 输出超限有 {sum(r['kind']=='input_plus_output_exceeds_context' for r in protocol['error_responses'])} 次。按原协议保留这些失败，没有扩窗或换提示词重试。",
        f"- 模型执行异常任务：{joined(summary['model_execution_error_task_ids'])}；正式运行审计异常：{joined(run['anomalies'])}。", '',
        '## 运行成本', '',
        '| 项目 | train90 LoRA | train90 全参数 SFT |', '|---|---:|---:|', *runtime_rows, '',
        f"本次正式评测墙钟时间：**{run['duration_seconds']/60:.1f} 分钟**，包含本次成功启动的模型加载和最终官方评分；不含此前失败的服务启动。LoRA 历史墙钟时间为 {summary['lora_duration_seconds']/60:.1f} 分钟。", '',
        recovery_text, '',
        '## 协议与比较边界', '',
        '- 两次 train90 实验使用相同训练任务和数据转换版本，均训练五轮；90 个训练任务与这 57 个 Dev 任务无交集。',
        '- 使用相同官方 Dev 任务顺序、ReAct 提示词、AppWorld 执行环境及 evaluator；temperature=0、seed=100、每题最多 50 步、单次输出最多 3000 tokens、max_model_len=32000。',
        '- vLLM 不启用 reasoning parser，完整模型直接加载，无 LoRA adapter；对 reasoning_content=null 仅转换为空字符串供日志处理，不改写模型输出或 Python action。生成配置文件中的默认服务命令会被启动器覆盖，实际命令以 `command.txt`、脚本快照和运行日志为准。',
        '- 本次评测固定最终 epoch 5 模型；未根据 Dev 结果选取中间 checkpoint，也未运行 test_normal。',
        '- 全参数训练采用峰值 LR=1e-5 的 warmup/cosine 调度及 FP32 主参数/优化器状态；LoRA 的训练设置不同。结果比较的是两套具体训练方案，不能单独归因于参数更新范围。',
        '- 旧 67 轨迹全参数实验的数据量、学习率和数值实现不同，仅供历史参考。原始基座历史结果启用了 deepseek_r1 parser，与当前无 parser 的接口不同，不能视为严格的纯权重对照。', '',
        '## 模型与产物', '',
        f"- 最终模型：`{manifest['model']}`，8,190,735,360 参数，BF16 HF 权重；评测不复制或修改权重。",
        f"- 训练实验：`{manifest['training_experiment']}`。",
        '- `summary.json`：官方得分、难度、逐题转移、调用统计和完整性审计。',
        '- `manifest.json`、`config/protocol_preflight.json`：模型来源、Dev/提示词/配置哈希、依赖版本及运行协议。',
        '- `task_status.jsonl`、`task_comparison.csv`：逐题官方评分与 LoRA 对照。',
        '- `experiments/outputs/.../evaluations/dev.json`：官方聚合结果；`tasks/` 保留逐题交互与 evaluator 证据。',
        '- `logs/run.log`、`scripts_snapshot/`、`artifacts.sha256`：运行日志、实际脚本及文件校验清单。', '',
    ])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--experiment',type=Path,required=True)
    args=p.parse_args()
    exp=args.experiment.resolve()
    ws=exp.parent.parent
    assert ws==Path('/root/autodl-tmp/workspace-tw') and exp.parent.name=='experiments'
    manifest=read_json(exp/'manifest.json')
    assert manifest['status'] in ('EVALUATION_FINISHED','SUCCESS') and manifest['exit_code']==0
    ids=load_task_ids(exp/'data/datasets/dev.txt',57)
    lora_exp=Path(manifest['reference_lora_experiment'])
    target=load_score_snapshot('本次 train90 全参数 SFT',exp,ids,DEFAULT_APPWORLD_EXPERIMENT,'dev')
    lora=load_score_snapshot('train90 LoRA',lora_exp,ids,DEFAULT_APPWORLD_EXPERIMENT,'dev')
    references=[]
    for label,name in [('原始 Qwen3-8B（历史接口）','2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev'),('旧67轨迹全参数 SFT epoch5','2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev')]:
        references.append(load_score_snapshot(label,ws/'experiments'/name,ids,DEFAULT_APPWORLD_EXPERIMENT,'dev'))
    for item in [target,lora,*references]:
        assert item['aggregate']['task_goal_completion']==round(100*item['success_count']/57,1)
        assert item['aggregate']['scenario_goal_completion']==round(100*item['successful_scenario_count']/19,1)
    status=audit_task_status(exp/'task_status.jsonl',ids,target['individual'])
    assert status['strictly_one_row_per_task'] and status['latest_rows_cover_dataset']
    for key in ['malformed_line_numbers','evaluation_error_task_ids','status_success_mismatch_ids','test_count_mismatch_ids']:
        assert not status[key], (key,status[key])
    rows,bad=read_jsonl(exp/'task_status.jsonl')
    assert not bad and not any('evaluation_error' in row['status'] for row in rows)
    run=audit_run(exp,status)
    assert run['final_exit_code']==0 and run['run_attempt_count']==run['run_finish_count']==1
    runtime=collect_runtime(Path(target['output_root']),ids)
    for key in ['missing_task_dir_ids','missing_lm_log_ids','malformed_lm_log_rows','malformed_api_log_rows','malformed_usage_files']:
        assert not runtime[key],(key,runtime[key])
    protocol=audit_protocol(exp,lora_exp,ids,manifest)
    assert protocol['request_count']==runtime['lm_calls']
    assert {r['task_id'] for r in protocol['error_responses']}==set(run['context_overflow_task_ids'])
    assert all(r['kind']!='other' and r['placeholder_content_empty'] and r['usage_tokens']==0 for r in protocol['error_responses'])
    lora_summary=read_json(lora_exp/'summary.json')
    summary={'experiment':str(exp),'task_count':57,'scenario_count':19,'target':target,'lora':lora,'references':references,
             'vs_lora':transition(target,lora),'runtime':runtime,'lora_runtime':lora_summary['runtime'],
             'lora_duration_seconds':lora_summary['duration_seconds'],'task_status_audit':status,'run_audit':run,
             'protocol_audit':protocol,'model_execution_error_task_ids':[r['task_id'] for r in rows if 'model_execution' in r['status']]}
    with (exp/'task_comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f)
        writer.writerow(['task_id','difficulty','full_sft_success','lora_success','change','full_sft_passed_tests','lora_passed_tests','total_tests','full_sft_failed_conditions'])
        for task_id in ids:
            a,b=target['individual'][task_id],lora['individual'][task_id]
            change={ (True,True):'共同成功',(True,False):'新增成功',(False,True):'退化',(False,False):'共同失败'}[(bool(a['success']),bool(b['success']))]
            writer.writerow([task_id,a['difficulty'],a['success'],b['success'],change,len(a['passes']),len(b['passes']),a['num_tests'],json.dumps(a['failures'],ensure_ascii=False)])
    for item in [target,lora,*references]: item.pop('individual')
    atomic_write_json(exp/'summary.json',summary)
    manifest.update(status='SUCCESS',report_created_at_utc=datetime.now(timezone.utc).isoformat(),
                    official_scores=target['aggregate'],success_count=target['success_count'],
                    protocol_audit_status=protocol['status'],initial_prompt_match_count=protocol['first_prompt_identical_tasks'],
                    target_evaluation_sha256=target['evaluation_sha256'],lora_evaluation_sha256=lora['evaluation_sha256'],
                    versions=protocol['preflight']['versions'],report_builder_sha256=sha256(Path(__file__)))
    atomic_write_json(exp/'manifest.json',manifest)
    atomic_write_text(exp/'REPORT.md',render(summary,manifest))
    atomic_write_text(exp/'STATUS.txt',f"SUCCESS dev57 success={target['success_count']}/57 TGC={target['aggregate']['task_goal_completion']} SGC={target['aggregate']['scenario_goal_completion']}\n")
    paths=[exp/name for name in ['REPORT.md','summary.json','manifest.json','STATUS.txt','task_status.jsonl','task_comparison.csv','command.txt','RUN_PLAN.md','logs/run.log','logs/run_exit_code.txt','logs/model_weight_hash_verify.log','logs/startup_attempt_01/run.log']]
    paths += [Path(target['evaluation_path'])]
    paths += [p for dirname in ['config','scripts_snapshot'] for p in (exp/dirname).rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts]
    atomic_write_text(exp/'artifacts.sha256',''.join(f'{sha256(path)}  {path.relative_to(exp)}\n' for path in sorted(set(paths))))
    print(json.dumps({'status':'SUCCESS','success_count':target['success_count'],'official_scores':target['aggregate'],'vs_lora':summary['vs_lora'],'runtime':runtime,'protocol_audit':'PASS'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
