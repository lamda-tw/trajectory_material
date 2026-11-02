"""SDPO-only control report and matched historical mixed-arm comparison."""
from b_common import *
import ast
import collections
import csv
import statistics


def paired_results(first, second):
    left = {x['task_id']: x for x in first['results']}
    right = {x['task_id']: x for x in second['results']}
    assert len(left) == len(right) == 57 and set(left) == set(right)
    return [{'task_id': task, 'epoch_1_success': left[task]['success'],
        'epoch_2_success': right[task]['success'],
        'epoch_1_test_fraction': left[task]['num_passes'] / left[task]['num_tests'],
        'epoch_2_test_fraction': right[task]['num_passes'] / right[task]['num_tests'],
        'epoch_1_steps': left[task]['steps'], 'epoch_2_steps': right[task]['steps'],
        'epoch_1_termination': left[task]['termination'], 'epoch_2_termination': right[task]['termination']}
        for task in sorted(left)]


def write_csv(path, rows):
    if rows:
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)


def behavior(folder, arm):
    collection = folder / 'collection.json'
    identity = file_sha(collection)
    cache = B / 'analysis/behavior_cache' / arm / (folder.name + '.json')
    if cache.exists():
        old = read(cache)
        assert old['collection_sha256'] == identity
        return old['counts']
    counts = collections.Counter()
    for item in read(collection)['trajectories']:
        path = folder / item['path']; assert file_sha(path) == item['sha256']
        seen = set()
        for step in read(path)['steps']:
            code = step.get('code', '').strip(); counts['steps'] += 1
            try:
                tree = ast.parse(code)
                signature = ast.dump(tree, include_attributes=False)
                names = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
            except SyntaxError:
                signature = code; names = []
            calls = [n for n in names if n.startswith('apis.')]
            doc_only = bool(calls) and all(n.startswith('apis.api_docs.') for n in calls)
            repeated = bool(code) and signature in seen
            counts['docs_only'] += doc_only
            counts['repeated_code'] += repeated
            counts['repeated_docs_code'] += doc_only and repeated
            if code: seen.add(signature)
    write_json(cache, {'collection_sha256': identity, 'counts': dict(counts)})
    return dict(counts)


def main():
    analysis = B / 'analysis'; analysis.mkdir(exist_ok=True)
    roots = {'mixed': R / 'phase_b/runs/mixed', 'sdpo': run_dir('sdpo')}
    records, evaluations, behavior_totals = {}, {}, {}
    for arm, root in roots.items():
        records[arm] = []; evaluations[arm] = {}; epoch_counts = {}
        for number in range(1, 37):
            folder = root / f'batch_{number:03d}'
            if not (folder / 'checkpoint/COMPLETE.json').exists(): continue
            metrics = read(folder / 'checkpoint/metrics.json'); records[arm].append(metrics)
            if arm == 'sdpo':
                assert metrics['counts'].get('sft', 0) == 0
                assert metrics['sft_loss'] == metrics['sft_grad_norm'] == 0
            epoch = str((number - 1) // 18 + 1)
            epoch_counts.setdefault(epoch, collections.Counter()).update(behavior(folder, arm))
        behavior_totals[arm] = {k: dict(v) for k, v in epoch_counts.items()}
        for epoch in (1, 2):
            path = root / f'epoch_{epoch:02d}_dev57/summary.json'
            if path.exists(): evaluations[arm][str(epoch)] = read(path)
    metrics = records['sdpo']
    complete = len(metrics) == 36 and len(evaluations['sdpo']) == 2
    counts = collections.Counter()
    for m in metrics: counts.update(m['counts'])
    summary = {'generated_at': now(), 'complete': complete, 'arm': 'sdpo', 'teacher': 'C2_feedback',
        'completed_batches': len(metrics), 'optimizer_updates': metrics[-1]['optimizer_updates'] if metrics else 0,
        'branch_counts': dict(counts), 'evaluations': evaluations, 'behavior': behavior_totals,
        'first_batch_exact_source_reuse': True, 'sft_control_run': False,
        'only_training_intervention': 'Mask all zero-FAIL responses; retain original FAIL eligibility, SDPO loss and all hyperparameters.'}
    write_json(analysis / 'b_report.json', summary)
    fields = ['batch', 'lr', 'sft_loss', 'sdpo_loss', 'total_loss', 'sft_grad_norm',
        'weighted_sdpo_grad_norm', 'grad_norm_before_clip', 'grad_norm_after_clip',
        'student_parameter_delta_norm', 'peak_allocated_gib', 'peak_reserved_gib', 'seconds', 'optimizer_updates']
    write_csv(analysis / 'training_metrics.csv', [{k: m[k] for k in fields} for m in metrics])
    comparisons = []
    for epoch in ('1', '2'):
        if epoch in evaluations['sdpo']:
            mixed = evaluations['mixed'][epoch]; control = evaluations['sdpo'][epoch]
            rows = paired_results(mixed, control)
            comparisons.extend({'epoch': int(epoch), 'task_id': x['task_id'],
                'mixed_success': x['epoch_1_success'], 'sdpo_success': x['epoch_2_success'],
                'mixed_test_fraction': x['epoch_1_test_fraction'], 'sdpo_test_fraction': x['epoch_2_test_fraction']}
                for x in rows)
    write_csv(analysis / 'mixed_vs_sdpo_dev57.csv', comparisons)
    lines = ['# B 阶段单 SDPO 对照报告', '',
        f"更新时间：{summary['generated_at']}。状态：{'两轮训练与两次 dev57 已完成' if complete else '运行中'}。",
        f"已提交 {len(metrics)}/36 批，实际更新 {summary['optimizer_updates']} 次。SFT 步数、loss、梯度必须始终为 0。", '',
        '## 与原混合实验的比较', '',
        '| 轮次 | 原 SFT+SDPO 成功题数 | 单 SDPO 成功题数 | 单 SDPO 平均测试通过率 |',
        '|---|---:|---:|---:|']
    for epoch in ('1', '2'):
        old = evaluations['mixed'][epoch]; new = evaluations['sdpo'].get(epoch)
        lines.append(f"| {epoch} | {old['successes']}/57 | " +
            (f"{new['successes']}/57 | {new['macro_test_pass_fraction']:.2%} |" if new else '待完成 | — |'))
    lines += ['', '## 重复查询行为', '',
        '以下两组都用同一个静态代码统计函数：纯文档步指代码中的所有 apis 调用均为 api_docs；重复代码指同轨迹此前已有相同 AST 的代码。不是完整 rubric 判定或成功业务调用计数。未完成轮次的比例不能直接当作整轮对照。', '',
        '| 分支 | 轮次 | 总步骤 | 纯文档步骤 | 重复代码 | 重复的纯文档代码 |', '|---|---:|---:|---:|---:|---:|']
    for arm, epochs in behavior_totals.items():
        for epoch, c in sorted(epochs.items()):
            lines.append(f"| {arm} | {epoch} | {c['steps']} | {c['docs_only']/c['steps']:.2%} | {c['repeated_code']/c['steps']:.2%} | {c['repeated_docs_code']/c['steps']:.2%} |")
    lines += ['', '## 技术验收', '']
    if metrics:
        first = metrics[0]
        lines += [f"首批 SDPO loss={first['sdpo_loss']:.8f}；SFT loss={first['sft_loss']:.1f}；SDPO 梯度 norm={first['weighted_sdpo_grad_norm']:.8f}；SFT 梯度 norm={first['sft_grad_norm']:.1f}。",
            f"首批训练峰值 allocated/reserved 显存 {first['peak_allocated_gib']:.2f}/{first['peak_reserved_gib']:.2f} GiB。首批与原混合实验的 SDPO loss/梯度在匹配容差内方可继续。",
            f"当前监督 SDPO 步数 {counts['sdpo']}；mask 步数 {counts['mask']}。数值正常不等于任务效果改善。"]
    lines += ['', '## 固定实验设置与结论边界', '',
        '从原 B 相同 Qwen3-8B 与 LoRA 初始化开始；首批复用原初始模型的相同 5 条轨迹和原 Codex 反馈，第二批起用新学生独立在线采样。每批 5 题、每题 1 条、两轮 train90，共 36 个更新机会。',
        '唯一训练干预：原 ZeroFail3 SFT 步骤改为 mask；所有 FAIL 的原准入规则、C2 prompt、原回答前缀、reverse-KL top100+tail、SDPO 权重与归一化保持不变。mask 步骤仍保留在后续上下文。',
        'LoRA r=8/alpha=16；AdamW lr=5e-5、前5次非空更新 warmup；EMA=0.95；clip norm=1；仅 GPU1。首批缓存使第一次更新的监督输入精确匹配。',
        '每轮 batch18/36 用无反馈学生评估同一 dev57，temperature=0、seed=100，不根据 dev 结果调参。',
        '该在线对照检验加入/去掉 SFT 后整个学习过程的区别；第二批起轨迹自然分化，不能视为固定同一数据上两种 loss 的纯梯度因果比较。单种子，Codex 评分存在变异。较好结果不证明 SDPO 每条目标正确，较差结果也不能单独证明 SFT 有害。',
        '状态：[STATUS.json](STATUS.json)；首批：[first_batch_acceptance.json](analysis/first_batch_acceptance.json)；逐批：[training_metrics.csv](analysis/training_metrics.csv)；后台：[supervisor.log](runs/sdpo/supervisor.log)。']
    (B / 'REPORT.md.tmp').write_text('\n'.join(lines) + '\n')
    (B / 'REPORT.md.tmp').replace(B / 'REPORT.md')
    return summary


if __name__ == '__main__':
    main()
