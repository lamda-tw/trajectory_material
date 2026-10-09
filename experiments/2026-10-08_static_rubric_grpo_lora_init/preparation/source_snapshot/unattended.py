"""Unattended collection supervisor. Explicit execution; up to three infrastructure attempts."""
import argparse
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from common import ROOT, atomic_json, input_fingerprint, load_config, read_json

REPORT = ROOT.parent.parent / 'RUBRIC_GRPO_EXPERIMENT_REPORT.md'
RUNS = ROOT / 'runs'

def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')

def append_report(text):
    with REPORT.open('a') as handle:
        handle.write('\n' + text.rstrip() + '\n')

def final_report(state):
    path = ROOT / 'preparation/collection_comparison.json'
    comparison = read_json(path)
    a, b = comparison['raw'], comparison['lora']
    if a['status'] != 'COMPLETE' or b['status'] != 'COMPLETE':
        raise ValueError('Final comparison must cover both complete collections.')
    validation = read_json(RUNS / 'step01_train90_rollouts/collection_validation.json')
    if not validation['passed'] or validation['rollouts'] != 540:
        raise ValueError('Full token validation did not pass.')
    append_report(
        '## 无人值守 LoRA 采样完成\n\n'
        f'开始：{state["started_at"]}；结束：{now()}。共 {state["attempt"]} 次运行尝试，'
        f'总耗时 {(time.monotonic() - state["_started_monotonic"]) / 60:.1f} 分钟。\n\n'
        '| train 随机采样诊断 | 原始 Qwen3-8B | 现有 SFT LoRA |\n'
        '| --- | --- | --- |\n'
        f'| 完整轨迹 | 540 | 540 |\n'
        f'| 官方终态成功 | {a["official_successful_rollouts"]}/540 | {b["official_successful_rollouts"]}/540 |\n'
        f'| 六次全失败的题 | {a["all_fail_groups"]} | {b["all_fail_groups"]} |\n'
        f'| 成功/失败混合的题 | {a["mixed_outcome_groups"]} | {b["mixed_outcome_groups"]} |\n'
        f'| 六次全成功的题 | {a["all_success_groups"]} | {b["all_success_groups"]} |\n'
        f'| 总生成步骤 | {a["total_steps"]} | {b["total_steps"]} |\n'
        f'| 生成 token | {a["generated_tokens"]} | {b["generated_tokens"]} |\n\n'
        '这张表只说明两个初始化在 train 上的采样情况。LoRA 已用 train90 示范训练过，'
        '不能将差值解释为本轮 rubric 收益，也不是 dev 结果。\n\n'
        '全部 LoRA 轨迹的校验值、response token 解码、prompt 重建、旧策略 logprob 对齐及初始 prompt 配对均通过。'
        '采样服务已退出；本轮没有 rubric 评分、GRPO 权重更新或 dev 评测。\n\n'
        f'产物：[LoRA 轨迹索引]({RUNS / "step01_train90_rollouts/trajectory_index.json"})、'
        f'[完整验收]({RUNS / "step01_train90_rollouts/collection_validation.json"})、'
        f'[两分支采样统计]({path})。\n\n'
        '下一步是两分支统一静态 rubric 评分，检查奖励与证据质量后再进入 GRPO。')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Unattended collection requires --execute.')
    config = load_config()
    RUNS.mkdir(exist_ok=True)
    target = RUNS / 'unattended_status.json'
    # The collector owns its own execution lock; this supervisor never starts scoring or training.
    state = {'status': 'running', 'started_at': now(), 'pid': os.getpid(), 'gpu': '0',
             'scope': 'LoRA train90 x 6 collection and validation only', 'max_attempts': 3,
             'fingerprint': input_fingerprint(config), 'attempt': 0, 'attempts': [],
             '_started_monotonic': time.monotonic()}
    def save():
        public = {k: v for k, v in state.items() if not k.startswith('_')}
        public['updated_at'] = now()
        public['elapsed_seconds'] = time.monotonic() - state['_started_monotonic']
        atomic_json(target, public)
    append_report(f'- {now()}：用户授权无人值守启动 LoRA 采样；仅 GPU 0。基础设施异常最多恢复 3 次，已完成且身份一致的轨迹保留。')
    save()
    try:
        for attempt in range(1, state['max_attempts'] + 1):
            state['attempt'] = attempt
            attempt_started = now()
            save()
            env = dict(os.environ, CUDA_VISIBLE_DEVICES='0', PYTHONUNBUFFERED='1',
                       HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            result = subprocess.run([config['paths']['appworld_python'], '-u',
                                     str(ROOT / 'step01_collect.py'), '--execute'], cwd=ROOT, env=env)
            state['attempts'].append({'attempt': attempt, 'started_at': attempt_started,
                                      'finished_at': now(), 'exit_code': result.returncode})
            if result.returncode == 0:
                final_report(state)
                state['status'] = 'complete'
                save()
                print(json.dumps({k: v for k, v in state.items() if not k.startswith('_')}, ensure_ascii=False), flush=True)
                return
            append_report(f'- {now()}：LoRA 采样尝试 {attempt} 返回 {result.returncode}；记录日志，不把基础设施异常作为模型失败。')
            save()
            if attempt < state['max_attempts']:
                time.sleep(30)
        raise RuntimeError('Three collection attempts failed; see runs/unattended.log and per-job logs.')
    except BaseException as error:
        state['status'] = 'failed'
        state['error'] = f'{type(error).__name__}: {error}'
        save()
        append_report(f'- {now()}：无人值守采样未完成：{state["error"]}。已完成数据保留；详情见 {target}。')
        raise

if __name__ == '__main__':
    main()
