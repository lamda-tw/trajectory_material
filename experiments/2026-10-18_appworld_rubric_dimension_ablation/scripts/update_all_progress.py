"""CPU-only observer for both isolated queues; preserves frozen GPU1 artifacts."""
import argparse
import csv
import fcntl
import json
import random
import statistics
import time
import traceback
from collections import defaultdict
from experiment_utils import R, now, read, dump

START = '<!-- ALL_PROGRESS_START -->'
END = '<!-- ALL_PROGRESS_END -->'


def optional(path):
    return read(path) if path.exists() else {}


def summarize(extension):
    actual, rows = {}, []
    arms = read(R / 'config/training.json')['arms']
    for lane in extension['lanes']:
        root = R / lane['root']
        for seed in lane['seeds']:
            for arm in arms:
                path = root / f'evaluation/{arm}/seed_{seed}/epoch_01/SUMMARY.json'
                if path.exists():
                    result = read(path)
                    assert result['tasks'] == 57 and result['seed'] == seed and result['arm'] == arm
                    actual[arm, seed] = result
            for i in range(1, 9):
                arm = f'drop_r{i}'
                source = extension['aliases'].get(arm, arm)
                if (source, seed) not in actual:
                    continue
                result = actual[source, seed]
                rows.append({'arm': arm, 'seed': seed, 'physical_gpu': lane['physical_gpu'],
                    'source_arm': source, 'independent_run': arm == source,
                    'tasks': 57, 'successes': result['successes'], 'TGC': result['TGC'],
                    'steps': result['steps'], 'generated_tokens': result['generated_tokens'],
                    'source_summary': str((root / f'evaluation/{source}/seed_{seed}/epoch_01/SUMMARY.json').relative_to(R))})
    comparisons = []
    for arm in arms:
        if arm == 'drop_r5':
            continue
        pairs = []
        for seed in extension['all_seeds']:
            if (arm, seed) in actual and ('drop_r5', seed) in actual:
                a = {x['task_id']: x['success'] for x in actual[arm, seed]['results']}
                b = {x['task_id']: x['success'] for x in actual['drop_r5', seed]['results']}
                assert set(a) == set(b) and len(a) == 57
                pairs.append({'seed': seed, 'differences': {t: int(a[t]) - int(b[t]) for t in a}})
        if not pairs:
            continue
        avg = {t: statistics.mean(p['differences'][t] for p in pairs) for t in pairs[0]['differences']}
        families = defaultdict(list)
        for task, value in avg.items():
            families[task.rsplit('_', 1)[0]].append(value)
        rng = random.Random(20261022)
        keys = sorted(families)
        samples = sorted(statistics.mean(v for k in rng.choices(keys, k=len(keys)) for v in families[k])
                         for _ in range(5000))
        comparisons.append({'arm': arm, 'reference': 'drop_r5', 'pairs': pairs,
            'mean_difference': statistics.mean(avg.values()), 'completed_seed_pairs': len(pairs),
            'family_bootstrap_95': [samples[125], samples[4874]],
            'scope': 'Descriptive; conditional on available seeds. GPU0 is used only for seed 20261017; no significance claim.'})
    dump(R / 'analysis_three_seeds/results.json', rows)
    dump(R / 'analysis_three_seeds/comparisons.json', comparisons)
    if rows:
        path = R / 'analysis_three_seeds/results.csv'
        with path.with_suffix('.tmp').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        path.with_suffix('.tmp').replace(path)
    body = '# 三 seed 逐项删除消融汇总\n\n'
    body += f'更新时间：{now()}。DEV57 已完成 **{len(actual)}/21** 次独立模型评测；缺失结果不填零。\n\n'
    body += '每组 1,358 步、1 epoch、679 更新；仅按评分选样。GPU1：20261015/20261016；GPU0：20261017。DropR7 复用同 seed DropR5，不计独立训练或重复证据。\n\n'
    body += '| 组 | seed | GPU | 成功 | TGC | 来源 |\n| --- | ---: | ---: | ---: | ---: | --- |\n'
    for row in rows:
        source = '独立训练' if row['independent_run'] else '复用 DropR5'
        body += f"| {row['arm']} | {row['seed']} | {row['physical_gpu']} | {row['successes']}/57 | {row['TGC']:.2%} | [{source}]({row['source_summary']}) |\n"
    body += '\n| 组 | 已完成 seed | 平均 TGC | 各 seed 成功数 |\n| --- | ---: | ---: | --- |\n'
    for i in range(1, 9):
        selected = [r for r in rows if r['arm'] == f'drop_r{i}']
        if selected:
            value = statistics.mean(r['TGC'] for r in selected)
            counts = '；'.join(f"{r['seed']}: {r['successes']}/57" for r in selected)
            body += f'| DropR{i} | {len(selected)}/3 | {value:.2%} | {counts} |\n'
    body += '\n主比较是同 seed 的 DropRi 对 DropR5，仅使用两侧均完成的配对；逐题差异、家族 bootstrap 描述区间见 [comparisons.json](analysis_three_seeds/comparisons.json)。完成 seed 数不同的临时均值不能直接排名。三个 seed 仍不足以完整刻画训练随机性；seed 与物理卡没有交叉实验，卡间差异未单独估计。\n\n没有同预算 Random，不据此声称优于随机选样。同状态动作诊断尚未运行，当前报告不声称学习机制已经验证。原 REPORT.md 是 GPU1 两轮分队列报告，此文件才是全三轮汇总。\n'
    analysis = R / 'analysis_three_seeds/final_analysis_section.md'
    if analysis.exists():
        body = body.replace('# 三 seed 逐项删除消融汇总\n', '# 三 seed 逐项删除消融汇总\n\n**已补充细项与机制分析：** [Base/ZeroFail3/DropR5 与跨预算下降](#baseline-and-budget) · [R5/R7 的 PASS 正例](#r5-r7-positive-examples) · [DropR1/R2 联合样本分析](#r1-r2-joint-analysis) · [evaluator 总表](#evaluator-overview) · [八类检查汇总](#evaluator-types) · [全部19个家族](#evaluator-all-families) · [每组逐类别及三个 seed 得失](#evaluator-type-details)。\n', 1)
        body += '\n' + analysis.read_text()
    path = R / 'REPORT_THREE_SEEDS.md'
    path.with_suffix('.tmp').write_text(body)
    path.with_suffix('.tmp').replace(path)


def refresh():
    extension = read(R / 'GPU0_EXTENSION.json')
    lanes = []
    trained = evaluated = 0
    for lane in extension['lanes']:
        state = optional(R / lane['root'] / 'STATUS.json')
        lanes.append({**lane, 'status': state})
        trained += state.get('training_completed', 0)
        evaluated += state.get('evaluation_completed', 0)
    snapshot = {'updated_at_beijing': now(), 'training_completed': trained, 'training_planned': 21,
        'evaluation_completed': evaluated, 'evaluation_planned': 21, 'lanes': lanes,
        'all_seeds': extension['all_seeds'], 'aliases': extension['aliases'],
        'same_state_diagnostics': 'not_started'}
    dump(R / 'STATUS_ALL.json', snapshot)
    block = f'{START}\n## 三个 seed 总进度\n\n更新时间：{now()}（北京时间）；每 15 秒刷新。实际训练 **{trained}/21**，DEV57 **{evaluated}/21**。每次 1,358 步、1 epoch；DropR7 引用同 seed DropR5。\n\n'
    block += '| GPU | seed | 当前阶段 | 训练完成 | DEV57 完成 |\n| --- | --- | --- | ---: | ---: |\n'
    for lane in lanes:
        s = lane['status']
        stage = s.get('stage', '准备选样和校验')
        if s.get('phase') == 'error':
            stage = '已停止：' + s.get('error', '见日志')
        elif s.get('phase') == 'running' and not s.get('pipeline_alive', True):
            stage = '调度器已退出，最后阶段：' + stage
        block += f"| {lane['physical_gpu']} | {', '.join(map(str, lane['seeds']))} | {stage} | {s.get('training_completed', 0)}/{lane['actual_runs']} | {s.get('evaluation_completed', 0)}/{lane['actual_runs']} |\n"
    block += '\n### GPU0 新增轮：20261017\n\n| 组 | 训练更新 | DEV57 | 成功数 |\n| --- | --- | --- | --- |\n'
    for record in lanes[1]['status'].get('records', []):
        alias = '复用 DropR5：' if record.get('alias_of') else ''
        value = '—' if record.get('successes') is None else f"{record['successes']}/57"
        block += f"| DropR{record['arm'][-1]} | {alias}{record['updates_completed']}/679 | {alias}{record['dev57_completed_tasks']}/57 | {value} |\n"
    block += '\nGPU0 最近节点：\n\n'
    journal = R / lanes[1]['root'] / 'runtime/progress_nodes.jsonl'
    if journal.exists():
        for line in journal.read_text().splitlines()[-8:]:
            event = json.loads(line)
            block += f"- {event['observed_at_beijing']}：{event['event']}。\n"
    block += '\n[三 seed 状态](STATUS_ALL.json) · [三 seed 结果报告](REPORT_THREE_SEEDS.md) · [GPU0 完整进度](gpu0_seed_20261017/README.md) · [GPU0 节点记录](gpu0_seed_20261017/runtime/progress_nodes.jsonl)\n\n下方原进度块仅统计 GPU1 的两个 seed。\n' + END
    # The active GPU1 observer uses this same lock and preserves outside its own block.
    with (R / 'runtime/progress.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = R / 'README.md'
        original = path.read_text()
        if START in original:
            before, rest = original.split(START, 1)
            _, after = rest.split(END, 1)
            text = before + block + after
        else:
            text = original.replace('<!-- AUTO_PROGRESS_START -->', block + '\n\n<!-- AUTO_PROGRESS_START -->', 1)
        temporary = path.with_name('README.md.all_progress.tmp')
        temporary.write_text(text)
        temporary.replace(path)
    return all(lane['status'].get('phase') in ('error', 'training_eval_complete') for lane in lanes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    with (R / 'runtime/all_progress.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = None
        while True:
            try:
                terminal = refresh()
                extension = read(R / 'GPU0_EXTENSION.json')
                signature = tuple(sorted((str(p), p.stat().st_mtime_ns) for lane in extension['lanes']
                    for p in (R / lane['root'] / 'evaluation').glob('*/seed_*/epoch_01/SUMMARY.json')))
                if signature != previous:
                    summarize(extension)
                    previous = signature
                if terminal or not args.watch:
                    break
            except Exception:
                dump(R / 'runtime/all_progress_error.json', {'at_beijing': now(), 'traceback': traceback.format_exc()})
                traceback.print_exc()
                if not args.watch:
                    raise
            time.sleep(15)


if __name__ == '__main__':
    main()
