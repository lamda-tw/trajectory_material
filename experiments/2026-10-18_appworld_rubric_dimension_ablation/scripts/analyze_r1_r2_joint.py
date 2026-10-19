"""Compare frozen R1/R2 selections on CPU; no sampling or training changes."""
import csv
import hashlib
import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from experiment_utils import R, dump, jsonl, now, read, set_sha

O = R / 'analysis_three_seeds'
SEEDS = [20261015, 20261016, 20261017]
ARMS = ['drop_r5', 'drop_r1', 'drop_r2']


def main():
    inv = jsonl(R / 'data/step_inventory.jsonl')
    index = {x['id']: x for x in inv}
    assert len(index) == len(inv) == 11254

    def pool(ignore=None):
        return {x['id'] for x in inv
                if sum(v == 'P' for i, v in enumerate(x['labels']) if i != ignore) >= 3
                and all(v != 'F' for i, v in enumerate(x['labels']) if i != ignore)}

    b, d1, d2 = pool(), pool(0), pool(1)
    common_removed = (b - d1) & (b - d2)
    assert b - d2 == common_removed and len(common_removed) == 359
    assert (d1 & d2) == (b & d1) and len(d1 & d2) == 1276
    hashes = read(R / 'references/source_hashes.json')
    source_rows = defaultdict(list)
    for x in inv:
        source_rows[x['source']].append(x)
    features = {}
    for source, rows in source_rows.items():
        raw = Path(source).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == hashes[source]
        trace = json.loads(raw)
        for x in rows:
            step = trace['steps'][x['step'] - 1]
            assert step['step'] == x['step']
            features[x['id']] = {
                'doc': 'apis.api_docs.' in step['code'],
                'error': step['observation'].startswith('Execution failed.'),
                'apis': sorted(set(re.findall(r'apis\.([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*\(', step['code']))),
            }

    def describe(ids):
        xs = [index[k] for k in sorted(ids)]
        return dict(count=len(xs), id_set_sha256=set_sha(ids),
                    labels=dict(sorted(Counter(x['labels'] for x in xs).items())),
                    R3=dict(Counter(x['labels'][2] for x in xs)),
                    R6=dict(Counter(x['labels'][5] for x in xs)),
                    doc=sum(features[k]['doc'] for k in ids),
                    execution_error=sum(features[k]['error'] for k in ids),
                    api_step_counts=dict(Counter(api for k in ids for api in features[k]['apis'])),
                    R3P_R6P=sum(x['labels'][2] == 'P' and x['labels'][5] == 'P' for x in xs),
                    R3P_R6N=sum(x['labels'][2] == 'P' and x['labels'][5] == 'N' for x in xs))

    parts = {'full_rule': b, 'drop_r1': d1, 'drop_r2': d2, 'common_removed': common_removed,
             'common_candidates': d1 & d2, 'r1_only': d1 - d2, 'r2_only': d2 - d1,
             'r1_extra_removed': (b - d1) - common_removed, 'r2_added': d2 - b}
    stats = {name: describe(ids) for name, ids in parts.items()}
    selected, selected_stats, overlaps = {}, [], []
    for seed in SEEDS:
        root = R / 'gpu0_seed_20261017' if seed == 20261017 else R
        for arm in ARMS:
            rows = jsonl(root / f'data/{arm}/seed_{seed}/selection.jsonl')
            ids = {x['id'] for x in rows}
            assert len(ids) == len(rows) == 1358
            assert all(index[x['id']] == x for x in rows)
            assert ids <= {'drop_r5': b, 'drop_r1': d1, 'drop_r2': d2}[arm]
            selected[arm, seed] = ids
            selected_stats.append(dict(arm=arm, seed=seed, **describe(ids),
                                       common_removed_selected=len(ids & common_removed)))
        shared = selected['drop_r1', seed] & selected['drop_r2', seed]
        overlaps.append(dict(seed=seed, intersection=len(shared), fraction_of_each=len(shared) / 1358,
                             union=len(selected['drop_r1', seed] | selected['drop_r2', seed])))
    summary = read(O / 'evaluator_summary.json')['groups']
    checks = list(csv.DictReader((O / 'evaluator_checks.csv').open()))
    lookup = {(x['arm'], x['seed'], x['task_id'], x['requirement']): int(x['passed']) for x in checks}
    gain_loss = {}
    for sign, name in [(1, 'gains'), (-1, 'losses')]:
        sets = {arm: {(x['seed'], x['task_id'], x['requirement']) for x in checks
                      if x['arm'] == arm and sign * (int(x['passed']) - lookup['drop_r5', x['seed'], x['task_id'], x['requirement']]) > 0}
                for arm in ['drop_r1', 'drop_r2']}
        gain_loss[name] = dict(common=len(sets['drop_r1'] & sets['drop_r2']),
                               r1_only=len(sets['drop_r1'] - sets['drop_r2']),
                               r2_only=len(sets['drop_r2'] - sets['drop_r1']))
    families = list(csv.DictReader((O / 'evaluator_families.csv').open()))
    common_improved = [x['family'] for x in families
                       if all(float(x[a + '_macro']) > float(x['drop_r5_macro']) + 1e-12 for a in ['drop_r1', 'drop_r2'])]
    reasons = {(x['id'], int(x['step'])): x['reason'] for x in csv.DictReader((R / 'references/step_labels.csv').open())}
    added_r2 = [dict(id=k, labels=index[k]['labels'], apis=features[k]['apis'],
                     reason=reasons[index[k]['trajectory_id'], index[k]['step']]) for k in sorted(d2 - b)]
    result = dict(at_beijing=now(), validated_source_trajectories=len(source_rows),
                  scope='Read-only analysis of frozen v6 labels; no training or rescoring.',
                  candidate_parts=stats, selected_by_seed=selected_stats, r1_r2_overlap=overlaps,
                  evaluator_overlap=gain_loss, jointly_improved_families=common_improved,
                  added_r2_steps=added_r2)
    dump(O / 'r1_r2_joint_analysis.json', result)
    with (O / 'r1_r2_candidate_membership.csv').open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=['id', 'labels', 'source', 'step', 'in_full_rule', 'in_r1', 'in_r2', 'common_removed', 'doc', 'execution_error'])
        writer.writeheader()
        for k in sorted(b | d1 | d2):
            x = index[k]
            writer.writerow(dict(id=k, labels=x['labels'], source=x['source'], step=x['step'],
                                 in_full_rule=int(k in b), in_r1=int(k in d1), in_r2=int(k in d2),
                                 common_removed=int(k in common_removed), doc=int(features[k]['doc']),
                                 execution_error=int(features[k]['error'])))

    def mean(arm, fn):
        return st.mean(fn(x) for x in selected_stats if x['arm'] == arm)

    lines = ['<a id="r1-r2-joint-analysis"></a>',
             '#### 4.3 联合分析 DropR1/DropR2：共同的预算重分配，比单独归因 R6 更有依据', '',
             f'补充核验时间：{now()}（北京时间）。已核对 540 条原轨迹哈希、候选 ID 及三个 seed 的实际训练步骤；仅 CPU 分析，没有改变训练样本或启动实验。', '',
             '**更新判断：两组共同排除一批只靠 R1/R2/R8 三个 P 入选的步骤，提高 R3/R6 正例的训练暴露；R6 是重要候选解释，但现有比较没有分离 R3、R6、文档调用与具体内容的作用。** DropR2 并不需要大量新增执行失败候选就能获得改善；不能把两组的共同收益都归因于 DropR1 独有的 109 条执行失败样本。', '',
             '| 候选层面的变化 | DropR1 | DropR2 |', '| --- | ---: | ---: |',
             '| 原全规则池 | 1,710 | 1,710 |', '| 共同移除 | 359 | 359 |',
             '| 在共同移除之外，再移除 | 75 | 0 |', '| 新增 | 109 | 8 |',
             '| 最终池 | 1,385 | 1,359 |', '| 新增候选中 R6=P | 102 | 2 |',
             '| 全池 R6=P（原池945） | 1,040 | 947 |', '',
             '**共同移除的 359 步究竟是什么？** 全部恰好只有 R1/R2/R8 为 P，R6 全为 N；R3 为 354 个 N、5 个 U，没有 R3=P。350 步含文档调用，其中 show_api_descriptions 为 200 步、show_api_doc 为 124 步、show_app_descriptions 为 26 步。它们可以是合法、有用的读取，N 不是差评；当前证据支持“有限训练预算可能给这类步骤过多曝光”的假设，不支持断言这些步骤本身错误或应永远排除。', '',
             '**DropR2 的 R6 富集主要来自重新分配预算。** 它保留了原池全部 945 条 R6=P，仅新增 2 条，候选 R6=P 从 945/1710（55.3%）变成 947/1359（69.7%）。在固定 1,358 步预算下，原有正例被选中的比例提高。DropR1 则额外移除 75 步（其中 68 个 R6=N、7 个 R6=P），新增 109 步（其中 102 个 R6=P）。二者不是同一种新增样本路径。', '',
             '**两组高度重叠，不能视为两份独立的 R6 因果验证。** 候选共有 1,276 步，占两组各 92.1%/93.9%；实际同 seed 训练步骤交集为 ' + ' / '.join(str(x['intersection']) for x in overlaps) + '，约占各组 92%。它们更像在很接近的共同样本上做少量不同替换。', '',
             '| 实际训练暴露：三个 seed 平均/1358 | 全规则对照 | DropR1 | DropR2 |',
             '| --- | ---: | ---: | ---: |']
    metrics = [('R3=P', lambda x: x['R3'].get('P', 0)), ('R6=P', lambda x: x['R6'].get('P', 0)),
               ('同时 R3=P、R6=P', lambda x: x['R3P_R6P']),
               ('R3=P、R6=N', lambda x: x['R3P_R6N']), ('含文档调用', lambda x: x['doc']),
               ('属于共同移除的359步', lambda x: x['common_removed_selected']),
               ('当前执行失败', lambda x: x['execution_error'])]
    for name, fn in metrics:
        lines.append('| ' + name + ' | ' + ' | '.join(f'{mean(a, fn):.1f}（{mean(a, fn)/1358:.1%}）' for a in ARMS) + ' |')
    lines += ['',
              'DropR2 的 R3=P、R6=N 从平均 311.3 增至 408.0，说明它不仅增加恢复类正例，也增加不涉及恢复、但有状态/数据忠实性正向评分的步骤。R3/R6 同时为 P 则从 711.3 增至 892.3；DropR1 达到 971.7。两项共现很强，当前无法把共同增益独占归给 R6。标签只用于选样，SFT 学习的是原始响应，不是 R6 字样。', '',
              '**DropR2 新增的八条不能默认视为有益。** 四条是与获取 token 无关的文档读取；其余涉及读错交易来源、播放列表查询对象/过滤条件不合目标、最长播放列表未核实。原始理由与 ID 见 JSON。它们没有当前执行报错，提示“能运行”和“证据合适”是不同维度；数量虽少，也不能仅凭数量排除其影响。', '',
              '**输出行为与 evaluator 是否也共享改善？** R1/R2 在 19 个家族中共同有 ' + str(len(common_improved)) + ' 个 Macro 高于全规则对照；同 seed、同题、同断言相对对照共同新增通过 ' + str(gain_loss['gains']['common']) + ' 条，另分别独有 ' + str(gain_loss['gains']['r1_only']) + '/' + str(gain_loss['gains']['r2_only']) + ' 条新增通过，也共同丢失 ' + str(gain_loss['losses']['common']) + ' 条。检查项不是独立样本，这只是收益分布的描述。', '',
              '| 结果或自然 rollout 行为 | 全规则对照 | DropR1 | DropR2 |',
              '| --- | ---: | ---: | ---: |']
    for name, fn, fmt in [
        ('平均整题成功/57', lambda x: st.mean(x['seed_successes']), '.2f'),
        ('evaluator Macro', lambda x: x['macro'], '.2%'),
        ('含文档调用的评测步占比', lambda x: x['doc_step_rate'], '.2%'),
        ('相同代码重复占比', lambda x: x['repeated_code_rate'], '.2%'),
        ('执行错误占比', lambda x: x['execution_error_rate'], '.2%'),
    ]:
        lines.append('| ' + name + ' | ' + ' | '.join(format(fn(summary[a]), fmt) for a in ARMS) + ' |')
    lines += ['',
              '这与“减少停留在文档/重复步骤，更多推进任务”相容；自然 rollout 的访问状态不同，不能当作同状态恢复能力验证。DropR2 在 seed 20261016 的 Macro 高于 R1（56.77% 对 49.87%），而其 R6=P 更少。DropR8 的 R6=P 平均958、略高于R2的946，但 Macro 只有46.60%、低于R2的53.49%。这些不是反证 R6 无用，却足以说明不能仅按 R6 正例数量给全部模型排序。', '',
              '**下一步优先级随之调整。**', '',
              '1. 共同状态比较必须同时纳入全规则、DropR1、DropR2：预先区分反馈/恢复状态和普通读取/状态使用状态，观察两组是否都减少无效重复、是否正确利用状态，以及收益是否集中在恢复场景。保持相同输入与可恢复的执行环境，仍报告完整 evaluator；诊断分组不用于训练过滤。',
              '2. 若追加训练，优先检验共同的选择机制：将全规则池与“仅移除这359条三P组合”的池比较。后者有1351条，新增任何F候选都不需要；可统一1350步、1轮、同初始化seed重新训练两组。移除谓词只由评分定义，不能用实际文档调用或执行结果过滤。这个实验检验该样本替换策略，不单独识别R3/R6作用；不能直接复用现有1358步模型作为1350步对照。',
              '3. 如果目标仍是单独检验R6，沿用上一轮提出的评分配对实验：两组各1358步，共享1158步，另200步以R6=N/P配对替换、其余七项评分完全相同，得到700与900个R6=P。它更直接控制R3评分分布，但仍不控制内容/任务/长度。与上一个两组实验择一优先，不需要同时铺开全部消融；另做R3匹配对照可作为后续，而非现在就把收益归给R6。', '',
              '更新后的研究假设是：**当前三P阈值使一批正常执行、有效读取、符合协议的步骤占据较多训练预算；移除其中任一计分来源后，共同减少这批步骤，增加带状态使用与反馈处理证据的样本暴露，并可能改善任务推进。** 已确认的是集合与暴露变化；“恢复学习导致成功提高”仍待验证。', '',
              '依据：[联合统计与R2新增样本](analysis_three_seeds/r1_r2_joint_analysis.json)、[全部相关候选成员及原轨迹路径](analysis_three_seeds/r1_r2_candidate_membership.csv)、[复算脚本](scripts/analyze_r1_r2_joint.py)。本节所有选样分析沿用冻结v6评分，不混用之后的prompt版本。本次没有追加训练或修改正式执行计划。', '']
    (O / 'r1_r2_joint_section.md').write_text('\n'.join(lines))
    print(json.dumps({'parts': {k: {'n': v['count'], 'R6': v['R6']} for k, v in stats.items()},
                      'selected_overlap': overlaps, 'evaluator_overlap': gain_loss,
                      'common_improved_families': len(common_improved)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
