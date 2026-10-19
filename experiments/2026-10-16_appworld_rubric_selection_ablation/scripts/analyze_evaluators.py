"""Analyze saved official requirement reports; no inference or evaluator reruns."""
import csv
import hashlib
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R / 'analysis'
NAMES = dict(random='Random', net3='Net3', pass4='Pass4', zerofail3='ZeroFail3', highfail3='HighFail3', base='Base')


def csv_write(name, rows):
    with (O / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze():
    cfg = json.loads((R / 'config/training.json').read_text())
    arms, seeds = cfg['arms'], cfg['seeds']
    task_rows, checks, schemas = [], [], {}
    for arm in [*arms, 'base']:
        for seed in (seeds if arm != 'base' else [None]):
            run = f'{arm}__seed_{seed}__epoch_01' if seed else 'base'
            folder = R / 'evaluation' / arm
            if seed:
                folder /= f'seed_{seed}/epoch_01'
            summary = json.loads((folder / 'SUMMARY.json').read_text())
            assert len(summary['results']) == 57
            for row in summary['results']:
                task = row['task_id']
                trajectory = folder / 'trajectories' / f'{task}.json'
                assert hashlib.sha256(trajectory.read_bytes()).hexdigest() == row['sha256']
                official = json.loads(trajectory.read_text())['official_evaluation']
                report = R / 'runtime' / run / 'experiments/outputs' / f'{run}__dev__{task}' / 'tasks' / task / 'evaluation/report.md'
                text = report.read_text()
                parsed = {}
                for match in re.finditer(r'>> (Passed|Failed) Requirement\n(.*?)(?=>> (?:Passed|Failed) Requirement|\Z)', text, re.S):
                    description = match[2].split('```')[0]
                    description = '\n'.join(l for l in description.splitlines() if not l.startswith('─') and l.strip() != 'None')
                    description = ' '.join(description.split())
                    if description == 'assert user_id to message mapping from notifications match private_data.venmo_user_id_to_notification_messages':
                        # Official report repeats this label for two different assertions.
                        assert match[1] == 'Failed', report
                        snippet = match[2].split('```python', 1)[1]
                        identity = re.findall(r'(venmo_user_id_to_notification_(?:messages|payment_request_ids)) =', snippet)
                        assert len(identity) == 1, report
                        description += ' [code: ' + identity[0] + ']'
                    assert description and description not in parsed, (report, description)
                    parsed[description] = match[1] == 'Passed'
                assert len(parsed) == row['tests'] == official['num_tests'], report
                assert sum(parsed.values()) == row['passes'] == official['num_passes'], report
                assert official['num_failures'] == len(parsed) - sum(parsed.values())
                assert all(parsed.values()) == row['success'] == official['success'], report
                if task in schemas:
                    assert set(parsed) == schemas[task], (report, set(parsed) ^ schemas[task])
                schemas[task] = set(parsed)
                task_rows.append(dict(arm=arm, seed=seed, task_id=task, family=task.rsplit('_', 1)[0], passes=row['passes'], tests=row['tests'], fraction=row['passes']/row['tests'], success=row['success']))
                for description, passed in sorted(parsed.items()):
                    checks.append(dict(arm=arm, seed=seed, task_id=task, family=task.rsplit('_', 1)[0], requirement=description, passed=int(passed), source=str(report.relative_to(R))))
            current = [t for t in task_rows if t['arm'] == arm and t['seed'] == seed]
            assert abs(st.mean(t['fraction'] for t in current) - summary['mean_test_pass_fraction']) < 1e-12
    task_ids = set(schemas)
    assert len(task_ids) == 57
    for arm in [*arms, 'base']:
        for seed in (seeds if arm != 'base' else [None]):
            assert {t['task_id'] for t in task_rows if t['arm'] == arm and t['seed'] == seed} == task_ids
    csv_write('evaluator_checks.csv', checks)
    csv_write('evaluator_tasks.csv', task_rows)
    groups = {}
    for arm in [*arms, 'base']:
        rows = [t for t in task_rows if t['arm'] == arm]
        groups[arm] = dict(macro=st.mean(t['fraction'] for t in rows), micro=sum(t['passes'] for t in rows)/sum(t['tests'] for t in rows), passes=sum(t['passes'] for t in rows), tests=sum(t['tests'] for t in rows), seed_macro=[st.mean(t['fraction'] for t in rows if t['seed'] == s) for s in (seeds if arm != 'base' else [None])], zero=sum(t['passes'] == 0 for t in rows), partial=sum(0 < t['passes'] < t['tests'] for t in rows), full=sum(t['success'] for t in rows))
    lookup = {(c['arm'], c['seed'], c['task_id'], c['requirement']): c['passed'] for c in checks}
    tasks = {(t['arm'], t['seed'], t['task_id']): t for t in task_rows}
    pairs = []
    for arm in arms:
        if arm == 'random':
            continue
        for seed in seeds:
            for task in sorted(task_ids):
                a, b = tasks[arm, seed, task], tasks['random', seed, task]
                gains = sum(lookup[arm, seed, task, d] > lookup['random', seed, task, d] for d in schemas[task])
                losses = sum(lookup[arm, seed, task, d] < lookup['random', seed, task, d] for d in schemas[task])
                pairs.append(dict(arm=arm, seed=seed, task_id=task, family=a['family'], gains=gains, losses=losses, net=gains-losses, macro_delta=a['fraction']-b['fraction'], both_failed=not a['success'] and not b['success']))
    csv_write('evaluator_pairs.csv', pairs)
    families = []
    for family in sorted({t['family'] for t in task_rows}):
        row = dict(family=family)
        for arm in [*arms, 'base']:
            rows = [t for t in task_rows if t['family'] == family and t['arm'] == arm]
            row[arm] = st.mean(t['fraction'] for t in rows)
        row['zerofail3_delta_pp'] = 100*(row['zerofail3']-row['random'])
        pp = [p for p in pairs if p['family'] == family and p['arm'] == 'zerofail3']
        row['zerofail3_net_checks'] = sum(p['net'] for p in pp)
        families.append(row)
    csv_write('evaluator_families.csv', families)
    # Aggregate only identical requirement text within the same task family.
    requirements = []
    grouped = defaultdict(list)
    for c in checks:
        grouped[c['family'], c['requirement']].append(c)
    for (family, description), rows in sorted(grouped.items()):
        row = dict(family=family, requirement=description)
        for arm in [*arms, 'base']:
            aa = [c for c in rows if c['arm'] == arm]
            row[arm + '_passes'] = sum(c['passed'] for c in aa)
            row[arm + '_tests'] = len(aa)
        row['zerofail3_net'] = row['zerofail3_passes']-row['random_passes']
        requirements.append(row)
    csv_write('evaluator_requirements.csv', requirements)
    output = dict(groups=groups, validated_reports=len(task_rows), distinct_task_checks=sum(map(len, schemas.values())), requirement_families=len(requirements))
    (O/'evaluator_summary.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    return groups, pairs, families, requirements, seeds


def render():
    groups, pairs, families, requirements, seeds = analyze()
    lines = ['## 1.1 官方 evaluator 检查项对比（2026-10-19 补充）', '',
        '此前报告主要统计整题全通过，只在个别轨迹案例中列出测试通过数；这里补充全部正式运行的逐检查项比较。数据来自保存的官方 `evaluation/report.md`，不是训练用 R1–R8 rubric，也不是重新生成的评分。分析核对了 15 次微调评测和 1 次原始模型评测的 912 份报告，与轨迹 SHA256、官方通过数、整题成功状态和 SUMMARY 的平均通过比例逐一一致；同一题在所有运行中的检查项集合也一致。', '',
        '**口径。** Macro 是先算每题通过检查数/总检查数，再对 57 题和三个 seed 等权平均；Micro 是全部通过检查数/全部检查数，会给检查较多的题更大权重。下表逐 seed 使用 Macro。检查项属于终态要求，彼此相关，不当作独立样本做显著性检验；通过率不是官方整题成功率，也不一定等于业务完成百分比。Base 只有一次评测，不复制成三个 seed。', '',
        '| 组别 | seed 20261015 | seed 20261016 | seed 20261017 | Macro | 对 Random | Micro（通过/总数） |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, g in groups.items():
        ss = [f'{v:.2%}' for v in g['seed_macro']] if arm != 'base' else ['—']*3
        lines.append(f"| {NAMES[arm]} | {' | '.join(ss)} | {g['macro']:.2%} | {(g['macro']-groups['random']['macro'])*100:+.2f} pp | {g['micro']:.2%}（{g['passes']}/{g['tests']}） |")
    lines += ['', '每次 DEV57 包含 291 条检查（不同题为 2–10 条），三次共 873 条检查结果。以下按同 seed、同题、规范化空白后的同一 requirement 文本配对；新增通过与丢失通过可以发生在同一道题中，净增不等于新增通过。`4fab96f` 家族有两条官方描述相同的检查，分别核验消息映射和 payment_request_id 映射；已用报告内失败代码区分身份，48 份报告中这两条均失败，未按通过/失败展示顺序硬配对。', '',
        '| 对 Random | 新增通过检查 | 丢失通过检查 | 净增 | 两组都失败的题数 | 这些题内净增检查 | 这些题的平均通过率差 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm in list(groups)[1:-1]:
        pp = [p for p in pairs if p['arm'] == arm]
        failed = [p for p in pp if p['both_failed']]
        lines.append(f"| {NAMES[arm]} | {sum(p['gains'] for p in pp)} | {sum(p['losses'] for p in pp)} | {sum(p['net'] for p in pp):+d} | {len(failed)}/171 | {sum(p['net'] for p in failed):+d} | {st.mean(p['macro_delta'] for p in failed)*100:+.2f} pp |")
    lines += ['', '“两组都失败”是各比较事后形成的不同子集，只用于描述整题指标隐藏的进退，不能跨组当作共同测试集排名。完整的逐 seed、逐题新增/丢失检查保存在配对 CSV。', '',
        '### 部分通过和家族分布', '', '| 组别 | 零检查通过 | 部分检查通过 | 全部通过 |', '| --- | ---: | ---: | ---: |']
    for arm, g in groups.items():
        lines.append(f"| {NAMES[arm]} | {g['zero']} | {g['partial']} | {g['full']} |")
    lines += ['', '微调各组分母为 171 个题次，Base 为 57。下表列出全部 19 个家族的 Macro 检查通过率，每个微调单元含 3 题 × 3 seed，Base 含 3 题。最后一列是 ZeroFail3 对 Random 的检查通过数净增。', '',
        '| 家族 | Random | Net3 | Pass4 | ZeroFail3 | HighFail3 | Base | ZeroFail3 差值 | 净增检查 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for f in sorted(families, key=lambda f: -f['zerofail3_delta_pp']):
        rates = ' | '.join(f'{f[a]:.1%}' for a in groups)
        lines.append(f"| {f['family']} | {rates} | {f['zerofail3_delta_pp']:+.2f} pp | {f['zerofail3_net_checks']:+d} |")
    lines += ['', '### 具体是哪条检查改变了', '', '以下分别列出 ZeroFail3 相对 Random 净增最多和净减最多的 5 条家族内 requirement（并列按家族和文本排序）。同族的不同题只有 requirement 文本相同时才合并；每个单元为通过次数/检查次数。完整 CSV 包含所有组及所有 requirement。', '',
        '| 家族 | 官方 requirement | Random | ZeroFail3 | 净增 |', '| --- | --- | ---: | ---: | ---: |']
    top = sorted([r for r in requirements if r['zerofail3_net'] > 0], key=lambda r: (-r['zerofail3_net'], r['family'], r['requirement']))[:5]
    bottom = sorted([r for r in requirements if r['zerofail3_net'] < 0], key=lambda r: (r['zerofail3_net'], r['family'], r['requirement']))[:5]
    for q in top + bottom:
        desc = q['requirement'].replace('|', '\\|')
        lines.append(f"| {q['family']} | {desc} | {q['random_passes']}/{q['random_tests']} | {q['zerofail3_passes']}/{q['zerofail3_tests']} | {q['zerofail3_net']:+d} |")
    lines += ['', '''**这层证据如何改变解释：**

1. ZeroFail3 的 Macro 从 Random 的 40.75% 升至 51.05%（+10.29 pp），Micro 从 35.28% 升至 46.51%（+11.23 pp），三个 seed 的 Macro 都更高。新增通过 174 条、丢失 76 条，净增 98 条；两组都失败的 133 个题次内仍净增 36 条、平均通过率高 4.44 pp。因此收益不仅体现为少数题跨过“全通过”门槛，也包括未完成任务中的部分要求改善。
2. Net3 虽然整题成功率与 Random 相同，Macro 低 1.99 pp、净少通过 14 条，提示整题指标掩盖了部分完成度下降。Pass4 只有 +1.88 pp，逐 seed 为两次低于 Random、一次高于 Random，仍不稳定。
3. HighFail3 的 Macro 为 34.61%，低于 Random 的 40.75%，也低于 Base 的 43.53%；Micro 同样低于二者。原报告“整题成功率未低于原始模型”的观察仍成立，但不能据此推断细粒度能力未退化。事实上，除 ZeroFail3 外，其余微调组的平均 Macro 和 Micro 均低于这次 Base；Base 只有一次运行，该比较仍是描述性的。
4. ZeroFail3 在 12/19 个家族的 Macro 上升、4 个持平、3 个下降。d4e9306 贡献 34/98（34.7%）的净增检查，仍有集中性，但其余家族合计也净增 64 条。该家族三个关键业务要求——按歌曲关注、按专辑关注、关注集合恰好为二者并集——均由 0/9 升至 8/9；说明改善确实触及业务终态覆盖。另一方面，57c3486 的改动的数据类型检查由 9/9 降至 5/9，且 3ab5b8b 的下载歌曲范围检查也退化，不能说 ZeroFail3 对所有业务要求都更好。
5. 部分通过不必然代表推进了业务。例如 383cbac、4ec8de5、50e1ac9 在所有组中均为 50%：不修改数据库的要求通过，答案检查全部失败。必须结合具体 requirement 理解通过率，不能把这 50% 当作完成了一半业务；本分析也未证明每条通过检查是模型行动带来的新增进展。''', '',
        '可复核文件：[汇总](analysis/evaluator_summary.json)、[逐题部分完成度](analysis/evaluator_tasks.csv)、[逐条检查及原始报告路径](analysis/evaluator_checks.csv)、[同 seed 配对得失](analysis/evaluator_pairs.csv)、[全部家族](analysis/evaluator_families.csv)、[全部 requirement](analysis/evaluator_requirements.csv)。复现：依次运行 `python scripts/analyze_evaluators.py`、`python scripts/analyze_evaluator_rubric_links.py`、`python scripts/write_final_report.py`（工作目录为本实验目录）。只做本地 CPU 分析，不重跑模型或 evaluator。', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    (O/'evaluator_report_section.md').write_text(render())
    print((O/'evaluator_summary.json').read_text())
