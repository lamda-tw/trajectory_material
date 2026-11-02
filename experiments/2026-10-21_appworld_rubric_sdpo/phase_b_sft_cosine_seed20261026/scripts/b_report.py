"""Read committed artifacts; compare constant and cosine learning rates at the same seed."""
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


def no_code(v):
    return v['behavior']['terminations'].get('no_python_code', 0)


def plot(baseline, epochs, metrics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    settings = [('Successes / 57', lambda x: x['successes']),
        ('Macro test pass (%)', lambda x: 100*x['macro_test_pass_fraction']),
        ('Repeated documentation (%)', lambda x: 100*x['behavior']['repeated_docs_fraction']),
        ('No executable Python / 57', no_code),
        ('Business API steps', lambda x: x['behavior']['business_api_steps'])]
    for ax, (title, fn) in zip(axes.flat, settings):
        for label, values in [('Constant 5e-5', baseline), ('Cosine to 5e-6', epochs)]:
            if values:
                keys=sorted(values,key=int)
                ax.plot([int(k) for k in keys],[fn(values[k]) for k in keys],'o-',label=label)
        ax.set_xticks([1,2,3]); ax.set_title(title); ax.grid(alpha=.2); ax.legend()
    ax=axes.flat[5]
    ax.plot([m['batch'] for m in metrics],[m['sft_loss'] for m in metrics])
    ax.set_title('SFT loss: changing online samples'); ax.set_xlabel('Batch'); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(B/'analysis/lr_comparison.png',dpi=150); plt.close(fig)


def main():
    from b_learning_rate import learning_rate
    batches=[batch_record(n) for n in range(1,55) if (batch_dir('sft',n)/'checkpoint/COMPLETE.json').exists()]
    metrics=[b['metrics'] for b in batches]
    epochs={str(e):v for e in range(1,4) if (v:=epoch_record(e)) is not None}
    baseline=read(B/'config/baseline_results.json')['epochs']
    complete=len(batches)==54 and len(epochs)==3
    train_epochs={}
    for e in range(1,4):
        group=[b for b in batches if b['epoch']==e]
        if not group:continue
        counts=Counter()
        for item in group:counts.update(item['counts'])
        train_epochs[str(e)]={'completed_batches':len(group),**counts,
            'batch_mean_sft_loss':sum(b['metrics']['sft_loss'] for b in group)/len(group),
            'lr_first':group[0]['metrics']['lr'],'lr_last':group[-1]['metrics']['lr']}
    cross=[];within=[];deltas={}
    for e,v in epochs.items():
        cross += [{'comparison':'constant_to_cosine',**row} for row in paired(baseline[e],v)]
        deltas[e]={'success_delta':v['successes']-baseline[e]['successes'],
            'macro_delta':v['macro_test_pass_fraction']-baseline[e]['macro_test_pass_fraction'],
            'repeated_docs_fraction_delta':v['behavior']['repeated_docs_fraction']-baseline[e]['behavior']['repeated_docs_fraction'],
            'business_steps_delta':v['behavior']['business_api_steps']-baseline[e]['behavior']['business_api_steps'],
            'no_python_code_tasks_delta':no_code(v)-no_code(baseline[e])}
    for e in (2,3):
        if str(e-1) in epochs and str(e) in epochs:within+=paired(epochs[str(e-1)],epochs[str(e)])
    summary={'updated_at':now(),'complete':complete,'seed':20261026,'baseline_seed':20261026,
        'baseline_schedule':'constant_after_warmup','schedule':config()['training']['lr_schedule'],
        'only_training_factor_changed':'learning_rate_schedule','from_base':True,
        'completed_batches':len(batches),'optimizer_updates':metrics[-1]['optimizer_updates'] if metrics else 0,
        'epochs':epochs,'training_epochs':train_epochs,'same_epoch_deltas':deltas,
        'epochs_planned':3,'wall_time_limit':None}
    write_json(B/'analysis/lr_summary.json',summary)
    csv_write(B/'analysis/training_metrics.csv',[{k:m.get(k) for k in ['batch','lr','sft_loss','sdpo_loss','sft_grad_norm','grad_norm_before_clip','grad_norm_after_clip','clipped','seconds','optimizer_updates','student_parameter_delta_norm']} for m in metrics])
    csv_write(B/'analysis/train_behavior.csv',[{'batch':b['batch'],'epoch':b['epoch'],**b['counts']} for b in batches])
    csv_write(B/'analysis/paired_schedules.csv',cross);csv_write(B/'analysis/paired_epochs.csv',within)
    csv_write(B/'analysis/dev_tasks.csv',[{'epoch':int(e),**{k:v for k,v in row.items() if k!='checks'}} for e,val in epochs.items() for row in val['results']])
    rows=['# 同 seed 纯 ZeroFail3 SFT：恒定学习率与余弦衰减对照','',
        f"更新时间：{summary['updated_at']}。{'三轮训练和三次 dev57 评估全部完成。' if complete else '进行中；尚未完成的轮次不作效果结论。'}",
        f"已提交 {len(batches)}/54 批，优化器更新 {summary['optimizer_updates']} 次。GPU1，无时间上限，三轮完成后停止。",'',
        '## 唯一主动改变的训练因素','',
        '基线为 phase_b_sft_seed20261026，训练 seed 同为 20261026。从原始 Qwen3-8B 初始化新的 LoRA 和 Adam，不加载旧检查点、不复用轨迹或评分。90题/轮、5题/批、每题一条在线完整轨迹，18批/轮；沿用相同任务顺序及派生 rollout seed。Codex 使用相同 v7 rubric prompt，仅 F=0 且 P>=3 的步骤进入 SFT。LoRA、loss、生成和评估配置保持一致。',
        '前5次有效更新与基线完全相同：1e-5、2e-5、3e-5、4e-5、5e-5。之后按有效更新次数平滑余弦衰减，第54次为5e-6。没有 warm restart；空 batch 不更新优化器，也不推进衰减。每轮更新进度以检查点中的 optimizer_updates 为准，重启进程不会重置曲线。',
        '`lr(u)=5e-6+(5e-5-5e-6)*(1+cos(pi*(u-5)/49))/2`，用于 u=6..54。若出现空 batch，54批内实际有效更新少于54，则终值尚未达到5e-6；不为凑终值添加训练批次。',
        '网络恢复使用基线实验修复后的流程。仅监控、报告和模型保留策略有管理性变更，不改变梯度或采样分布。Codex 无可固定的评分 seed；相同训练 seed 也不能保证外部评分和 GPU 计算逐位一致。模型分叉后在线轨迹自然变化，属于学习率变化的下游结果。','',
        '## 学习率计划','', '| 更新次数 | 阶段 | 学习率 |','|---:|---|---:|']
    for u,label in [(1,'首次更新'),(5,'warmup结束'),(18,'第一轮末'),(36,'第二轮末'),(54,'第三轮末')]:
        rows.append(f'| {u} | {label} | {learning_rate(u,config()["training"]):.9g} |')
    rows+=['','## 同 seed 正式 dev57 对照','',
        '| 学习率 | 轮次 | 成功题数 | Macro | 通过检查 | 纯文档占比 | 重复文档占比 | 业务步骤 | 无代码终止 | 平均步骤 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for label,values in [('恒定',baseline),('余弦',epochs)]:
        for e in range(1,4):
            v=values.get(str(e))
            if not v:rows.append(f'| {label} | {e} | 待完成 | — | — | — | — | — | — | — |');continue
            c=v['behavior'];rows.append(f"| {label} | {e} | {v['successes']}/57 | {v['macro_test_pass_fraction']:.2%} | {v['passes']}/{v['tests']} | {c['docs_fraction']:.2%} | {c['repeated_docs_fraction']:.2%} | {c['business_api_steps']} | {no_code(v)}/57 | {v['mean_steps']:.2f} |")
    rows+=['','全部评估使用 dev57、temperature=0、seed=100、无反馈学生策略和官方终态检查。重复文档按同一轨迹中相同 Python AST 计数；业务动作排除文档、Supervisor 和 login/logout。出现 API 代码不保证调用成功。','',
        '## 入选训练样本','',
        '| 轮次 | 批数 | 全步骤 | SFT步骤 | 文档SFT | 业务SFT | 重复文档SFT | 平均batch loss |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for e,c in train_epochs.items():
        rows.append(f"| {e} | {c['completed_batches']}/18 | {c['steps']} | {c['sft_steps']} | {c.get('sft_docs_steps',0)} | {c.get('sft_business_steps',0)} | {c.get('sft_repeated_docs_steps',0)} | {c['batch_mean_sft_loss']:.6f} |")
    rows+=['','每轮数据在线重采，loss不是固定验证集指标；不根据训练loss判断任务能力。','',
        '## 同轮次逐题比较','']
    for e,d in deltas.items():
        pairs=[x for x in cross if x['to_epoch']==int(e)]
        rows.append(f"第{e}轮余弦相对恒定：成功 {d['success_delta']:+d} 题，Macro {100*d['macro_delta']:+.2f} 个百分点，重复文档 {100*d['repeated_docs_fraction_delta']:+.2f} 个百分点，业务步骤 {d['business_steps_delta']:+d}，无代码终止 {d['no_python_code_tasks_delta']:+d} 题；新增成功 {sum(x['success_gained'] for x in pairs)}、丢失成功 {sum(x['success_lost'] for x in pairs)}，检查新增 {sum(x['checks_gained'] for x in pairs)}、丢失 {sum(x['checks_lost'] for x in pairs)}。")
    if not deltas:rows.append('尚无余弦分支正式 dev57 结果。')
    rows+=['','即使较恒定学习率更好，也需同时判断是否保留早期能力、是否仅延迟退化。该实验同时降低了后期学习率和累计学习率，不能单独证明余弦形状优于所有低恒定学习率。单个seed与57题不足以确立稳定泛化收益。','',
        '## 固定案例','', '| 分支 | 案例 | 第1轮：检查；重复/全部步；终止 | 第2轮 | 第3轮 |','|---|---|---|---|---|']
    for label,values in [('恒定',baseline),('余弦',epochs)]:
        for task in ['b119b1f_2','d4e9306_2','6c2c621_1','396c5a2_1','23cf851_1']:
            cells=[]
            for e in range(1,4):
                if str(e) not in values:cells.append('待完成');continue
                x=next(x for x in values[str(e)]['results'] if x['task_id']==task)
                cells.append(f"{x['num_passes']}/{x['num_tests']}；{x['repeated_docs_steps']}/{x['steps']}；{x['termination']}")
            rows.append(f'| {label} | {task} | '+' | '.join(cells)+' |')
    rows+=['','## 验收和保存','']
    first=B/'analysis/first_batch_acceptance.json'
    if first.exists():
        m=read(first)['metrics'];rows.append(f"首批已验收：loss={m['sft_loss']:.6f}，梯度={m['sft_grad_norm']:.6f}，lr={m['lr']:.1e}，SDPO loss/梯度=0，显存峰值={m['peak_allocated_gib']:.2f} GiB。")
    rows+=['只保留最新完整检查点及已评估最优轮次（先比较成功题数，再比较Macro，同分选更早轮次），重合时只保留一份；写入新检查点期间会短暂多一份。全部轨迹、评分、dataset、指标与官方报告保留。仅清理本余弦实验的权重，原实验不动。',
        f"[实时状态]({B/'STATUS.json'}) · [心跳]({run_dir('sft')/'heartbeat.json'}) · [预检]({B/'analysis/preflight.json'}) · [汇总]({B/'analysis/lr_summary.json'}) · [逐批指标]({B/'analysis/training_metrics.csv'}) · [同轮逐题比较]({B/'analysis/paired_schedules.csv'})",'',
        f"![学习率对照]({B/'analysis/lr_comparison.png'})"]
    (B/'REPORT.md').write_text('\n'.join(rows)+'\n');plot(baseline,epochs,metrics)
    return summary


if __name__=='__main__':main()
