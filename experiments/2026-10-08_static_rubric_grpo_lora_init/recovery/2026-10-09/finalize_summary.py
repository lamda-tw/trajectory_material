"""Finalize recovery diagnostics after the complete collection passes its token audit."""
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'runs/step01_train90_rollouts'
read = lambda p: json.loads(Path(p).read_text())

def main():
    validation = read(DIRECTORY / 'collection_validation.json')
    status = read(ROOT / 'runs/unattended_status.json')
    if not validation['passed'] or validation['rollouts'] != 540 or status['status'] != 'complete':
        raise RuntimeError('Finalize only a completed and validated collection.')
    rows = read(DIRECTORY / 'trajectory_index.json')
    groups, revisions = defaultdict(list), Counter()
    logging_fix_episodes = []
    old_failures = []
    for row in rows:
        groups[row['task_id']].append(row)
        trajectory = read(row['trajectory'])
        revisions[trajectory.get('execution_provenance', {}).get('runtime_fingerprint', 'original_frozen_runtime')] += 1
        if trajectory.get('log_compatibility', {}).get('ellipsis_log_encodings', 0):
            logging_fix_episodes.append({'task_id': row['task_id'], 'sample': row['sample'],
                                        'success': row['success'], 'steps': row['steps']})
        if (row['task_id'], row['sample']) in {('60d0b5b_1', 4), ('b0a8eae_1', 5)}:
            old_failures.append({'task_id': row['task_id'], 'sample': row['sample'],
                                 'success': row['success'], 'steps': row['steps'],
                                 'termination': row['termination']})
    successes = sum(r['success'] for r in rows)
    histogram = Counter(sum(r['success'] for r in group) for group in groups.values())
    previous = read(ROOT / 'recovery/2026-10-09/before/runs/unattended_status.json')
    summary = {
        'recorded_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
        'complete_trajectories': len(rows), 'complete_groups': len(groups),
        'official_successful_rollouts': successes, 'train_sampling_success_percent': successes / 540 * 100,
        'tasks_with_any_success': sum(any(r['success'] for r in group) for group in groups.values()),
        'success_count_histogram': {str(i): histogram[i] for i in range(7)},
        'all_fail_groups': histogram[0], 'mixed_outcome_groups': sum(histogram[i] for i in range(1, 6)),
        'all_success_groups': histogram[6],
        'total_steps': sum(r['steps'] for r in rows), 'generated_tokens': sum(r['generated_tokens'] for r in rows),
        'prompt_tokens': sum(r['prompt_tokens'] for r in rows),
        'median_steps': statistics.median(r['steps'] for r in rows),
        'mean_steps': statistics.mean(r['steps'] for r in rows),
        'termination_counts': dict(Counter(r['termination'] for r in rows)),
        'runtime_revisions': dict(revisions), 'episodes_exercising_logging_fix': logging_fix_episodes,
        'previously_failed_jobs_now_complete': old_failures,
        'pre_recovery_rollouts_unchanged': validation['pre_recovery_trajectories_unchanged'],
        'recovery_elapsed_seconds': status['elapsed_seconds'],
        'active_invocation_seconds_including_previous_failures': previous['elapsed_seconds'] + status['elapsed_seconds'],
        'root_report_absent': not (ROOT.parent.parent / 'RUBRIC_GRPO_EXPERIMENT_REPORT.md').exists(),
        'rubric_calls': 0, 'optimizer_updates': 0, 'dev_rollouts': 0}
    assert summary['root_report_absent'] and len(rows) == 540 and len(groups) == 90
    assert summary['pre_recovery_rollouts_unchanged'] == 342
    path = ROOT / 'recovery/2026-10-09/final_diagnostics.json'
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    report = ROOT / 'RUBRIC_GRPO_EXPERIMENT_REPORT.md'
    text = report.read_text()
    text = text.replace('**新增分支已授权启动**', '**新增分支已完成并验收**')
    text = text.replace('随后已授权无人值守采样；后续 GRPO 预算在相应步骤确定。',
                        '已完成采样及本次故障恢复验收；后续 GRPO 预算在相应步骤确定。')
    if '## 2026-10-09 恢复完成：最终验收' not in text:
        text += (
            '\n## 2026-10-09 恢复完成：最终验收\n\n'
            f'最终 **540/540 条、90/90 个六条组**。官方 train 终态成功 **{successes}/540（{successes/540*100:.2f}%）**，'
            f'{summary["tasks_with_any_success"]}/90 题至少一次成功。这是训练内随机采样诊断，不是 dev 成绩，也没有进行 rubric 评分或 GRPO 更新。\n\n'
            f'原有 **342 条完整轨迹 SHA256 全部保持一致**，新增 **198 条**均保存恢复版本信息。全部 540 条完成 token 重建、真实旧策略 logprob 对齐和数据完整性验收。'
            f'有 {len(logging_fix_episodes)} 条新轨迹实际触发了 Ellipsis 日志兼容编码；模型的原动作、真实错误反馈与官方评价均保留。\n\n'
            f'全失败组 {histogram[0]} 个，混合成功/失败组 {summary["mixed_outcome_groups"]} 个，全成功组 {histogram[6]} 个；'
            '对应 0/1 结果奖励的有效组仅为混合组。rubric 是否提供更多可靠差异，仍待实际评分。\n\n'
            f'本次恢复耗时 {status["elapsed_seconds"]/60:.1f} 分钟；含昨夜失败尝试的累计运行时间约 '
            f'{summary["active_invocation_seconds_including_previous_failures"]/60:.1f} 分钟，不含中间无人运行的间隔。\n\n'
            f'详细统计：[final_diagnostics.json]({path})。报告现仅位于本实验目录，工作区根目录原报告已移除。\n')
    report.write_text(text)
    p = ROOT / 'README.md'
    text = p.read_text()
    start = text.index('**最新状态：')
    end = text.index('\n\n下文', start)
    text = text[:start] + (
        '**最新状态：2026-10-09，LoRA 的完整 train90 × 6 已完成并通过验收。** '
        f'共 540 条，官方 train 终态成功 {successes}/540；原有 342 条保持不变，本次补齐 198 条。'
        '本轮只完成采样与验收，尚未进行规则评分、GRPO 或 dev 评测。\n\n'
        f'结果与故障修复记录见 [实验报告]({report})。报告已移入本目录；当前入口只向 experiments 内写入。'
        '恢复证据、原始清单与源码备份位于 recovery/2026-10-09/。') + text[end:]
    text = text.replace('已启动的后台 supervisor 会在基础设施失败时最多恢复 3 次；不要重复启动第二个 supervisor。',
                        '后台采样已结束，无需重复启动。历史 supervisor 的基础设施重试上限为 3 次。')
    text = text.replace('当前已有后台任务运行，不要重复启动', '当前已完成，无需重复启动')
    p.write_text(text)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
