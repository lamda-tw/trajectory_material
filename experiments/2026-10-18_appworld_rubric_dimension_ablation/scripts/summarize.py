"""Summarize actual runs and explicit aliases; compare paired tasks to DropR5."""
import csv
import random
import statistics
from collections import defaultdict
from experiment_utils import R, read, dump, now


def main():
    plan = read(R / 'config/experiment_plan.json')
    cfg = read(R / 'config/training.json')
    actual, rows = {}, []
    for seed in cfg['seeds']:
        for arm in cfg['arms']:
            path = R / f'evaluation/{arm}/seed_{seed}/epoch_01/SUMMARY.json'
            if path.exists():
                actual[arm, seed] = read(path)
        for arm in plan['report_arms']:
            source = plan['aliases'].get(arm, arm)
            result = actual.get((source, seed))
            if result:
                rows.append({'arm': arm, 'seed': seed, 'source_arm': source,
                             'independent_run': arm == source, 'tasks': 57,
                             'successes': result['successes'], 'TGC': result['TGC'],
                             'steps': result['steps'], 'generated_tokens': result['generated_tokens']})
    dump(R / 'analysis/results.json', rows)
    if rows:
        with (R / 'analysis/results.csv').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    comparisons = []
    for arm in cfg['arms']:
        if arm == 'drop_r5':
            continue
        pairs = []
        for seed in cfg['seeds']:
            if (arm, seed) in actual and ('drop_r5', seed) in actual:
                a = {x['task_id']: x['success'] for x in actual[arm, seed]['results']}
                b = {x['task_id']: x['success'] for x in actual['drop_r5', seed]['results']}
                assert set(a) == set(b) and len(a) == 57
                pairs.append({'seed': seed, 'differences': {t: int(a[t]) - int(b[t]) for t in a}})
        if pairs:
            avg = {t: statistics.mean(p['differences'][t] for p in pairs) for t in pairs[0]['differences']}
            families = defaultdict(list)
            for task, value in avg.items():
                families[task.rsplit('_', 1)[0]].append(value)
            rng = random.Random(20261022)
            keys = sorted(families)
            samples = sorted(statistics.mean(v for key in rng.choices(keys, k=len(keys)) for v in families[key])
                             for _ in range(5000))
            comparisons.append({'arm': arm, 'reference': 'drop_r5', 'pairs': pairs,
                                'mean_difference': statistics.mean(avg.values()),
                                'completed_seed_pairs': len(pairs),
                                'family_bootstrap_95': [samples[125], samples[4874]],
                                'scope': 'Descriptive interval conditional on completed training seeds; not a significance claim.'})
    dump(R / 'analysis/comparisons.json', comparisons)
    text = '# Rubric 完整删除消融运行结果\n\n'
    text += f'更新时间：{now()}（北京时间）。实际训练对应的 DEV57 已完成 {len(actual)}/14；未完成结果不填为零。\n\n'
    text += '八个报告组各 1,358 步、1 epoch、两个 seed，仅按剩余七项 P≥3 且 F=0 选样。DropR7 复用同 seed 新 DropR5，不计独立证据。没有 Random/ZeroFail3 训练项目；DropR5 的候选集合恰好等价于全规则集合。\n\n'
    text += '| 组 | seed | 成功 | TGC | 来源 |\n| --- | ---: | ---: | ---: | --- |\n'
    for row in rows:
        source = '独立训练' if row['independent_run'] else '复用 DropR5'
        text += f"| {row['arm']} | {row['seed']} | {row['successes']}/57 | {row['TGC']:.2%} | {source} |\n"
    text += '\n逐题配对见 [comparisons.json](analysis/comparisons.json)，选样分布见 [SELECTION_SUMMARY.json](data/SELECTION_SUMMARY.json)。两个 seed 的区间不完整覆盖训练随机性，无同预算随机对照，不能证明普遍优于随机选样。相同历史动作探测尚未运行，当前报告不声称学习机制已被验证。\n'
    temporary = R / 'REPORT.tmp.md'
    temporary.write_text(text)
    temporary.replace(R / 'REPORT.md')


if __name__ == '__main__':
    main()
