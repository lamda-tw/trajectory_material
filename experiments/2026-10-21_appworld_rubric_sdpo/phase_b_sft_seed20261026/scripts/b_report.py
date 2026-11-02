"""Read committed artifacts only; compare the two seeds without changing training."""
from b_report_helpers import *


def batch_record(number):
    folder = batch_dir('sft', number)
    cp = folder / 'checkpoint'
    done = read(cp / 'COMPLETE.json')
    cached = B / 'analysis/batch_cache' / f'{number:03d}.json'
    h = file_sha(cp / 'COMPLETE.json')
    if cached.exists():
        value = read(cached); assert value['checkpoint_sha256'] == h
        return value
    data = read(folder / 'dataset.json'); metrics = read(cp / 'metrics.json')
    assert file_sha(folder / 'dataset.json') == done['identity']['dataset_sha256']
    assert file_sha(cp / 'metrics.json') == done['files']['metrics.json']
    assert metrics['arm'] == 'sft' and metrics['sdpo_loss'] == metrics['weighted_sdpo_grad_norm'] == 0
    chosen = {(x['trajectory_id'], x['step']) for x in data['examples'] if x['branch'] == 'sft'}
    assert all('F' not in x['labels'] and x['labels'].count('P') >= 3 for x in data['examples'] if x['branch'] == 'sft')
    counts = Counter(sft_steps=len(chosen))
    collection = read(folder / 'collection.json')
    assert collection['policy_identity'] == data['policy_identity'] == done['identity']['parent_policy']
    for item in collection['trajectories']:
        path = folder / item['path']; assert file_sha(path) == item['sha256']
        t = read(path); c = behavior(t)
        counts.update({k: v for k, v in c.items() if k != 'longest_docs_streak'})
        seen = set()
        for step in t['steps']:
            code = (step.get('code') or '').strip()
            try:
                sig = ast.dump(ast.parse(code), include_attributes=False)
            except SyntaxError:
                sig = code
            if (item['id'], step['step']) in chosen:
                one = behavior({'steps': [step]})
                counts['sft_docs_steps'] += one['docs_steps']
                counts['sft_business_steps'] += one['business_api_steps']
                counts['sft_repeated_docs_steps'] += bool(one['docs_steps']) and sig in seen
            if code:
                seen.add(sig)
    value = {'checkpoint_sha256': h, 'batch': number, 'epoch': (number-1)//18+1, 'counts': dict(counts), 'metrics': metrics}
    write_json(cached, value)
    return value


def plot(old, new, metrics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    settings = [('Successes / 57', lambda x: x['successes']),
        ('Macro test pass (%)', lambda x: 100*x['macro_test_pass_fraction']),
        ('Repeated documentation steps (%)', lambda x: 100*x['behavior']['repeated_docs_fraction'])]
    for ax, (title, fn) in zip(axes.flat, settings):
        for label, epochs in [('seed 20261022', old), ('seed 20261026', new)]:
            if epochs:
                keys=sorted(epochs,key=int); ax.plot([int(k) for k in keys], [fn(epochs[k]) for k in keys], 'o-', label=label)
        ax.set_xticks([1,2,3]); ax.set_title(title); ax.grid(alpha=.2); ax.legend()
    ax=axes.flat[3]
    ax.plot([m['batch'] for m in metrics], [m['sft_loss'] for m in metrics]); ax.set_title('SFT loss: changing online samples')
    ax.set_xlabel('Batch'); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(B/'analysis/seed_comparison.png',dpi=150); plt.close(fig)


def main():
    batches = [batch_record(n) for n in range(1,55) if (batch_dir('sft',n)/'checkpoint/COMPLETE.json').exists()]
    metrics = [b['metrics'] for b in batches]
    epochs = {str(e): v for e in range(1,4) if (v := epoch_record(e)) is not None}
    baseline = read(B/'config/baseline_results.json')['epochs']
    complete = len(batches)==54 and len(epochs)==3
    pairs=[]
    for e in (2,3):
        if str(e-1) in epochs and str(e) in epochs:
            pairs += paired(epochs[str(e-1)], epochs[str(e)])
    train_epochs={}
    for e in range(1,4):
        group=[b for b in batches if b['epoch']==e]
        if not group:continue
        c=Counter()
        for b in group:c.update(b['counts'])
        train_epochs[str(e)]={'completed_batches':len(group),**c,'batch_mean_sft_loss':sum(b['metrics']['sft_loss'] for b in group)/len(group)}
    summary={'updated_at':now(),'complete':complete,'seed':20261026,'baseline_seed':20261022,
        'completed_batches':len(batches),'optimizer_updates':metrics[-1]['optimizer_updates'] if metrics else 0,
        'epochs':epochs,'training_epochs':train_epochs,'from_base':True,'only_training_factor_changed':'seed',
        'wall_time_limit':None,'epochs_planned':3}
    if '2' in epochs and '3' in epochs:
        two,three=epochs['2'],epochs['3']
        summary['epoch3_vs_epoch2']={'success_delta':three['successes']-two['successes'],
            'macro_delta':three['macro_test_pass_fraction']-two['macro_test_pass_fraction'],
            'repeated_docs_fraction_delta':three['behavior']['repeated_docs_fraction']-two['behavior']['repeated_docs_fraction'],
            'business_steps_delta':three['behavior']['business_api_steps']-two['behavior']['business_api_steps']}
    write_json(B/'analysis/seed_summary.json',summary)
    csv_write(B/'analysis/training_metrics.csv',[{k:m.get(k) for k in ['batch','lr','sft_loss','sdpo_loss','sft_grad_norm','grad_norm_before_clip','grad_norm_after_clip','clipped','seconds','optimizer_updates','student_parameter_delta_norm']} for m in metrics])
    csv_write(B/'analysis/train_behavior.csv',[{'batch':b['batch'],'epoch':b['epoch'],**b['counts']} for b in batches])
    csv_write(B/'analysis/paired_epochs.csv',pairs)
    csv_write(B/'analysis/dev_tasks.csv',[{'epoch':int(e),**{k:v for k,v in row.items() if k!='checks'}} for e,val in epochs.items() for row in val['results']])
    rows=['# 纯 ZeroFail3 SFT 新 seed 三轮复现实验','',f"更新时间：{summary['updated_at']}。{'三轮训练和 dev57 评估全部完成。' if complete else '进行中；未完成轮次不作结论。'}",
        f"已提交 {len(batches)}/54 批；优化器更新 {summary['optimizer_updates']} 次。用户已取消时间上限，三轮完成后停止。",'',
        '## 实验设置','',
        '从原始 Qwen3-8B 初始化新的 LoRA（r=8、alpha=16），不加载旧训练检查点，不复用旧首批轨迹或 Codex 评分。训练 seed 从 20261022 改为 20261026，作用于 LoRA 初始化、每轮题目顺序及派生的 rollout 采样种子。dev57 评估 seed 保持 100、temperature=0。Codex 外部评审没有可固定的随机 seed，属于保留的运行噪声。',
        '每轮90题，每批5题，每题1条完整在线轨迹，轨迹结束后用原 Codex v7 prompt 逐步评分。仅 F=0 且 P>=3 做 SFT，所有 FAIL 均 mask；SDPO loss 与梯度必须为0。前5次有效更新 warmup 至5e-5，此后恒定，不使用学习率衰减。每轮18批，三轮54批；基础模型、数据划分、prompt、LoRA、优化器、loss归一化、上下文和生成参数保持原配方。',
        '## 两个 seed 的正式 dev57 结果','',
        '| seed | 轮次 | 成功题数 | TGC | Macro | 通过检查 | 纯文档步占比 | 重复文档步占比 | 业务API步骤 | 平均步骤 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for seed, values in [(20261022,baseline),(20261026,epochs)]:
        for e in range(1,4):
            v=values.get(str(e))
            if not v:rows.append(f'| {seed} | {e} | 待完成 | — | — | — | — | — | — | — |');continue
            c=v['behavior'];rows.append(f"| {seed} | {e} | {v['successes']}/57 | {v['task_goal_completion']:.2%} | {v['macro_test_pass_fraction']:.2%} | {v['passes']}/{v['tests']} | {c['docs_fraction']:.2%} | {c['repeated_docs_fraction']:.2%} | {c['business_api_steps']} | {v['mean_steps']:.2f} |")
    rows+=['','重复文档口径：同一轨迹中此前已经出现过相同 Python AST 的纯文档动作，包含交替查多份文档。业务 API 排除文档、Supervisor 和 login/logout；代码出现不保证执行成功。Macro 是每题检查通过比例的平均，不能等同业务任务完成率。','',
        '## 入选 SFT 样本的动作分布','',
        '| 轮次 | 已完成批数 | 全步骤 | SFT步骤 | SFT文档步骤 | SFT业务步骤 | SFT重复文档步骤 | 平均batch loss |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for e,c in train_epochs.items():
        n=c['sft_steps'];rows.append(f"| {e} | {c['completed_batches']}/18 | {c['steps']} | {n} | {c.get('sft_docs_steps',0)}（{c.get('sft_docs_steps',0)/max(1,n):.2%}） | {c.get('sft_business_steps',0)} | {c.get('sft_repeated_docs_steps',0)} | {c['batch_mean_sft_loss']:.6f} |")
    rows+=['','每轮样本重新采集，loss 不能当作固定验证集曲线；重复文档样本也可能属于合理重新查阅，不能仅凭 AST 相同认定评分错误。','',
        '## 第三轮趋势与逐题变化','']
    if 'epoch3_vs_epoch2' in summary:
        delta=summary['epoch3_vs_epoch2'];pp=[x for x in pairs if x['from_epoch']==2]
        rows += [f"新 seed 第三轮相对第二轮：成功题数 {delta['success_delta']:+d}，Macro {100*delta['macro_delta']:+.2f} 个百分点，重复文档占比 {100*delta['repeated_docs_fraction_delta']:+.2f} 个百分点，业务步骤 {delta['business_steps_delta']:+d}。",
            f"新增成功 {sum(x['success_gained'] for x in pp)} 题，丢失成功 {sum(x['success_lost'] for x in pp)} 题；新通过检查 {sum(x['checks_gained'] for x in pp)} 项，丢失检查 {sum(x['checks_lost'] for x in pp)} 项。"]
        same=delta['success_delta']<0 and delta['macro_delta']<0 and delta['repeated_docs_fraction_delta']>0
        rows += ['新 seed 也出现“整题成功下降、Macro下降、重复文档增加”的共同方向，支持原问题不是旧 seed 独有；这仍不是对学习率或筛选偏差的因果归因。' if same else '新 seed 没有同时出现上述三个方向，不能说第三轮退化完整复现；也不能据此判定配方没有问题，应结合三轮全程与具体失败案例。']
    else:rows+=['第三轮尚未完成，暂不判断原 seed 的退化是否复现。']
    rows+=['','## 固定案例','', '| seed | 案例 | 第1轮：检查；重复/全部步 | 第2轮 | 第3轮 |','|---|---|---|---|---|']
    for seed,values in [(20261022,baseline),(20261026,epochs)]:
        for task in ['b119b1f_2','d4e9306_2','6c2c621_1','396c5a2_1','23cf851_1']:
            cells=[]
            for e in range(1,4):
                if str(e) not in values:cells.append('待完成');continue
                x=next(x for x in values[str(e)]['results'] if x['task_id']==task)
                cells.append(f"{x['num_passes']}/{x['num_tests']}；{x['repeated_docs_steps']}/{x['steps']}")
            rows.append(f'| {seed} | {task} | '+' | '.join(cells)+' |')
    rows+=['','## 验收、保存与复核','']
    first=B/'analysis/first_batch_acceptance.json'
    if first.exists():
        m=read(first)['metrics'];rows+=[f"首批通过验收：SFT loss={m['sft_loss']:.6f}，梯度={m['sft_grad_norm']:.6f}，lr={m['lr']:.1e}，SDPO loss/梯度为0；峰值已分配显存={m['peak_allocated_gib']:.2f} GiB。"]
    rows+=['保留本实验首批、每轮末及最近两批完整模型；只清理本实验其余中间模型权重，并保留哈希记录。全部轨迹、评分、样本、loss和正式评估报告保留。旧实验保持暂停，不修改其模型和数据。',
        '新 seed 同时改变初始化随机数、任务顺序和采样随机数；这是整套配方的 seed 复现，不能将差异单独归因于其中一种随机来源。两个 seed 仍不足以确定总体稳定性。',
        f"[汇总]({B/'analysis/seed_summary.json'})；[逐批loss与梯度]({B/'analysis/training_metrics.csv'})；[训练行为]({B/'analysis/train_behavior.csv'})；[逐题变化]({B/'analysis/paired_epochs.csv'})；[dev轨迹和官方报告索引]({B/'analysis/dev_tasks.csv'})。",'',
        f"![两seed走势]({B/'analysis/seed_comparison.png'})"]
    (B/'REPORT.md').write_text('\n'.join(rows)+'\n')
    plot(baseline,epochs,metrics)
    return summary


if __name__=='__main__':main()
