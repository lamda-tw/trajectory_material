"""Read-only experiment comparison; writes reports only inside this SFT control."""
from b_common import *
from datetime import datetime
import ast
import collections
import csv

ROOTS = {'mixed': R/'phase_b/runs/mixed', 'sdpo': R/'phase_b_sdpo_only/runs/sdpo', 'sft': run_dir('sft')}
LABELS = {'mixed': 'SFT + SDPO', 'sdpo': '仅 SDPO', 'sft': '仅 ZeroFail3 SFT'}


def paired_results(first, second):
    left={x['task_id']:x for x in first['results']};right={x['task_id']:x for x in second['results']}
    assert len(left)==len(right)==57 and set(left)==set(right)
    return [{'task_id':task,'epoch_1_success':left[task]['success'],'epoch_2_success':right[task]['success'],
        'epoch_1_test_fraction':left[task]['num_passes']/left[task]['num_tests'],
        'epoch_2_test_fraction':right[task]['num_passes']/right[task]['num_tests'],
        'epoch_1_steps':left[task]['steps'],'epoch_2_steps':right[task]['steps'],
        'epoch_1_termination':left[task]['termination'],'epoch_2_termination':right[task]['termination']}
        for task in sorted(left)]


def write_csv(path, rows):
    if rows:
        with path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def trajectory_behavior(t):
    c=collections.Counter(trajectories=1,steps=len(t['steps']))
    seen=set();last=None;streak=0;longest=0
    for s in t['steps']:
        code=(s.get('code') or '').strip()
        try:
            tree=ast.parse(code);signature=ast.dump(tree,include_attributes=False)
            calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        except SyntaxError:
            signature=code;calls=[]
        calls=[n for n in calls if n.startswith('apis.')]
        docs=bool(calls) and all(n.startswith('apis.api_docs.') for n in calls)
        repeated=bool(code) and signature in seen
        c['docs_only']+=docs;c['repeated_code']+=repeated;c['repeated_docs_code']+=docs and repeated
        c['non_doc_api_steps']+=any(not n.startswith('apis.api_docs.') for n in calls)
        c['response_tokens']+=len(s['response_ids'])
        if code:seen.add(signature)
        streak=streak+1 if docs and signature==last else int(docs)
        longest=max(longest,streak);last=signature if docs else None
    c['trajectories_with_5_consecutive_docs']=int(longest>=5)
    return dict(c),longest


def collection_behavior(folder, arm):
    identity=file_sha(folder/'collection.json');cache=B/'analysis/behavior_cache'/arm/(folder.name+'.json')
    if cache.exists():
        old=read(cache);assert old['source_sha256']==identity;return old
    counts=collections.Counter();terminations=collections.Counter()
    for item in read(folder/'collection.json')['trajectories']:
        path=folder/item['path'];assert file_sha(path)==item['sha256']
        t=read(path);c,_=trajectory_behavior(t);counts.update(c);terminations[t['termination']]+=1
    value={'source_sha256':identity,'counts':dict(counts),'terminations':dict(terminations)}
    write_json(cache,value);return value


def dev_behavior(folder,arm):
    identity=file_sha(folder/'summary.json');cache=B/'analysis/behavior_cache'/arm/(folder.name+'.json')
    if cache.exists():
        old=read(cache);assert old['source_sha256']==identity;return old
    summary=read(folder/'summary.json');counts=collections.Counter();terminations=collections.Counter();rows=[]
    assert len(summary['results'])==57
    for item in summary['results']:
        path=folder/'trajectories'/(item['task_id']+'.json');assert file_sha(path)==item['trajectory_sha256']
        t=read(path);c,longest=trajectory_behavior(t);counts.update(c);terminations[t['termination']]+=1
        rows.append({**item,'docs_only':c['docs_only'],'repeated_docs_code':c['repeated_docs_code'],
                     'longest_consecutive_docs':longest,'path':str(path.relative_to(R))})
    value={'source_sha256':identity,'counts':dict(counts),'terminations':dict(terminations),'tasks':rows}
    write_json(cache,value);return value


def timing(root,metrics):
    launch=root/'launch.json';end=root/'COMPLETE.json'
    value={'training_seconds':sum(m['seconds'] for m in metrics)}
    if launch.exists():
        started=read(launch);start=started.get('started_at',started.get('launched_at'))
        stop=read(end)['completed_at'] if end.exists() else now()
        value.update(start=start,measured_until=stop,wall_seconds=(datetime.fromisoformat(stop)-datetime.fromisoformat(start)).total_seconds(),
                     complete=end.exists())
    return value


def main():
    analysis=B/'analysis';analysis.mkdir(exist_ok=True)
    records={};evaluations={};train_stats={};dev_stats={};timings={};branches={}
    for arm,root in ROOTS.items():
        records[arm]=[];evaluations[arm]={};train_stats[arm]={};dev_stats[arm]={};branches[arm]=collections.Counter()
        for number in range(1,37):
            folder=root/f'batch_{number:03d}'
            if not (folder/'checkpoint/COMPLETE.json').exists():continue
            m=read(folder/'checkpoint/metrics.json');records[arm].append(m);branches[arm].update(m['counts'])
            if arm=='sft':
                assert m['counts'].get('sdpo',0)==0 and m['sdpo_loss']==m['weighted_sdpo_grad_norm']==0
            epoch=str((number-1)//18+1)
            entry=train_stats[arm].setdefault(epoch,{'counts':collections.Counter(),'terminations':collections.Counter(),'batches':0})
            value=collection_behavior(folder,arm)
            entry['counts'].update(value['counts']);entry['terminations'].update(value['terminations']);entry['batches']+=1
        for epoch in ('1','2'):
            folder=root/f'epoch_{int(epoch):02d}_dev57'
            if (folder/'summary.json').exists():
                evaluations[arm][epoch]=read(folder/'summary.json');dev_stats[arm][epoch]=dev_behavior(folder,arm)
        timings[arm]=timing(root,records[arm])
    metrics=records['sft'];complete=len(metrics)==36 and len(evaluations['sft'])==2
    summary={'generated_at':now(),'complete':complete,'arm':'sft','completed_batches':len(metrics),
        'optimizer_updates':metrics[-1]['optimizer_updates'] if metrics else 0,
        'skipped_empty_batches':[m['batch'] for m in metrics if not m['optimizer_step_performed']],
        'branch_counts':{a:dict(v) for a,v in branches.items()},'evaluations':evaluations,
        'training_behavior':train_stats,'dev_behavior':dev_stats,'timing':timings,
        'only_training_intervention':'Mask all FAIL responses; retain original ZeroFail3 SFT targets, step normalization, optimizer and schedule.',
        'teacher_used_in_loss':False,'first_batch_exact_source_reuse':True}
    write_json(analysis/'b_report.json',summary)
    fields=['batch','lr','sft_loss','sdpo_loss','total_loss','sft_grad_norm','weighted_sdpo_grad_norm',
        'grad_norm_before_clip','grad_norm_after_clip','student_parameter_delta_norm','peak_allocated_gib',
        'peak_reserved_gib','seconds','optimizer_updates','optimizer_step_performed']
    write_csv(analysis/'training_metrics.csv',[{k:m[k] for k in fields} for m in metrics])
    comparisons=[]
    for epoch in ('1','2'):
        if epoch not in evaluations['sft']:continue
        maps={a:{x['task_id']:x for x in evaluations[a][epoch]['results']} for a in ROOTS}
        assert len(maps['sft'])==57 and all(set(maps[a])==set(maps['sft']) for a in ROOTS)
        for task in sorted(maps['sft']):
            row={'epoch':int(epoch),'task_id':task}
            for a in ROOTS:
                v=maps[a][task];row.update({a+'_success':v['success'],a+'_test_fraction':v['num_passes']/v['num_tests'],
                    a+'_steps':v['steps'],a+'_termination':v['termination']})
            comparisons.append(row)
    write_csv(analysis/'three_way_dev57.csv',comparisons)
    lines=['# B 阶段纯 ZeroFail3 SFT 对照与三组比较','',
        f"更新时间：{summary['generated_at']}。状态：{'两轮训练和两次 dev57 全部完成' if complete else '运行中，未完成结果不作最终结论'}。",
        f"纯 SFT 已提交 {len(metrics)}/36 批，实际更新 {summary['optimizer_updates']} 次；空批次 {summary['skipped_empty_batches']}。",'',
        '## dev57 官方评估','',
        '| 分支 | 轮次 | 整题成功 | TGC | 平均测试通过率 | 平均步骤 |','|---|---:|---:|---:|---:|---:|']
    for arm in ROOTS:
        for epoch in ('1','2'):
            v=evaluations[arm].get(epoch)
            if v:
                mean_steps=sum(x['steps'] for x in v['results'])/57
                lines.append(f"| {LABELS[arm]} | {epoch} | {v['successes']}/57 | {v['task_goal_completion']:.2%} | {v['macro_test_pass_fraction']:.2%} | {mean_steps:.2f} |")
            else:lines.append(f'| {LABELS[arm]} | {epoch} | 待完成 | — | — | — |')
    lines+=['','测试通过率包含不破坏数据等检查，不等于业务完成百分比。三组同题配对结果见 [three_way_dev57.csv](analysis/three_way_dev57.csv)。','',
        '## dev 的重复文档行为','',
        '| 分支 | 轮次 | 总步骤 | 纯文档步 | 重复文档代码 | 连续≥5次相同文档的题数 | 上下文超限 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm in ROOTS:
        for epoch,v in sorted(dev_stats[arm].items()):
            c=v['counts'];n=c['steps']
            lines.append(f"| {LABELS[arm]} | {epoch} | {n} | {c['docs_only']/n:.2%} | {c['repeated_docs_code']/n:.2%} | {c['trajectories_with_5_consecutive_docs']}/57 | {v['terminations'].get('context_limit',0)}/57 |")
    lines+=['','纯文档步指所有 apis 调用均为 api_docs；重复按同轨迹此前已有相同 Python AST 判定。不计 prompt 示例，不等同完整 R6 判定。','',
        '## 训练数据与稳定性','',
        '| 分支 | 已完成批次 | SFT 步数 | SDPO 步数 | mask 步数 | 训练程序累计时间 |', '|---|---:|---:|---:|---:|---:|']
    for arm in ROOTS:
        c=branches[arm]
        lines.append(f"| {LABELS[arm]} | {len(records[arm])}/36 | {c['sft']} | {c['sdpo']} | {c['mask']} | {timings[arm]['training_seconds']/3600:.2f} 小时 |")
    if metrics:
        f=metrics[0]
        lines+=['',f"首批 SFT loss={f['sft_loss']:.9f}、SFT 梯度 norm={f['sft_grad_norm']:.9f}；SDPO loss/梯度均为 0。",
            f"首批峰值 allocated/reserved 显存 {f['peak_allocated_gib']:.2f}/{f['peak_reserved_gib']:.2f} GiB；已完成批次的最大值 {max(m['peak_allocated_gib'] for m in metrics):.2f}/{max(m['peak_reserved_gib'] for m in metrics):.2f} GiB。",
            f"SFT loss 范围 {min(m['sft_loss'] for m in metrics):.6f}–{max(m['sft_loss'] for m in metrics):.6f}；{sum(m['clipped'] for m in metrics)}/{len(metrics)} 批裁剪梯度。数值正常不等于任务改善。"]
    lines+=['','## 结果解释','']
    if complete:
        v=evaluations['sft']['2'];first=evaluations['sft']['1'];a=evaluations['mixed']['2'];z=evaluations['sdpo']['2']
        lines.append(f"纯 SFT 两轮成功数 {first['successes']}/57 → {v['successes']}/57；最终相对 mixed 净差 {v['successes']-a['successes']:+d} 题，相对 SDPO 净差 {v['successes']-z['successes']:+d} 题。")
        if v['successes']>max(a['successes'],z['successes']) and v['macro_test_pass_fraction']>max(a['macro_test_pass_fraction'],z['macro_test_pass_fraction']):
            lines.append('本次纯 SFT 在第二轮整题成功和平均检查通过率均高于两种含 SDPO 的组。这支持优先保留 ZeroFail3 选样，并停止扩大当前 SDPO 配方；不能据单种子在线实验宣称所有 SDPO 都有害。')
        else:
            lines.append('当前结果未同时满足“纯 SFT 最终整题成功和平均检查通过率都高于另两组”。应结合下述逐题得失和重复行为判断；不能只挑一项指标宣称 SFT 已解决问题。')
        for ref in ('mixed','sdpo'):
            pairs=paired_results(evaluations[ref]['2'],v)
            gained=[x['task_id'] for x in pairs if x['epoch_2_success'] and not x['epoch_1_success']]
            lost=[x['task_id'] for x in pairs if x['epoch_1_success'] and not x['epoch_2_success']]
            lines.append(f"相对 {LABELS[ref]} 第二轮：新增成功 {len(gained)} 题（{', '.join(gained) or '无'}）；丢失成功 {len(lost)} 题（{', '.join(lost) or '无'}）。")
        pairs=paired_results(first,v)
        lost=[x['task_id'] for x in pairs if x['epoch_1_success'] and not x['epoch_2_success']]
        gained=[x['task_id'] for x in pairs if x['epoch_2_success'] and not x['epoch_1_success']]
        lines.append(f"纯 SFT 第二轮相对第一轮：新增成功 {', '.join(gained) or '无'}；丢失成功 {', '.join(lost) or '无'}。")
        lines+=['','逐题轨迹与重复统计保存在 `analysis/b_report.json` 的 dev_behavior.sft；具体退步题可直接对照两个 epoch 的 trajectories。']
    else:lines.append('等待纯 SFT 两轮评估完成后，再比较任务成功、细粒度通过率和重复文档行为；不依据中间 loss 调整实验配方。')
    lines+=['','## 固定协议与结论边界','',
        '从相同 Qwen3-8B 和 seed 的新 LoRA 开始；首批复用原 mixed 的同 5 条轨迹与评分，只使用相同 20 个 ZeroFail3 步骤。第二批起由纯 SFT 学生独立在线采样。',
        '每批 5 题、每题一条完整轨迹；同一 Codex v7-feedback prompt 统一评审全部步骤。仅 F=0 且 P≥3 做原回答 CE；其余当前步骤 loss 为零，历史保留。含 U 不额外排除，与原 B 一致。',
        'LoRA r8/alpha16/dropout0；lr=5e-5，前 5 次非空更新 warmup，clip=1，步内 token mean、合格 step 间平均；每批只更新一次。教师分支不参与 loss，保留的 EMA 状态仅兼容已有检查点结构。',
        '无合格步骤的批次跳过 optimizer/EMA/warmup 计数，不补采样或填充其他步骤。共 36 个更新机会；batch18/36 评估相同 dev57，无反馈学生、temperature0、seed100。只使用 GPU1。',
        '三组均为单种子，第二批起在线数据自然分化。因此比较的是整个学习流程；不能当作固定相同数据上的纯梯度因果实验。旧离线 ZeroFail3 的 855 次更新也不能代替这次在线对照。',
        '原始底座的历史 dev57 可作参考；本次未额外启动底座重评或其他训练。dev 已用于多次探索，结果不代表新的独立测试集。','',
        '[状态](STATUS.json)；[首批验收](analysis/first_batch_acceptance.json)；[逐批数值](analysis/training_metrics.csv)；[完整三组统计](analysis/b_report.json)；[监督日志](runs/sft/supervisor.log)。']
    path=B/'REPORT.md';tmp=path.with_suffix('.md.tmp');tmp.write_text('\n'.join(lines)+'\n');tmp.replace(path)
    return summary


if __name__=='__main__':main()
