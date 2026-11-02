"""Reproducible B report from committed training and official dev57 artifacts."""
from b_common import *
import collections
import csv
import statistics


def paired_results(first,second):
    left={x['task_id']:x for x in first['results']};right={x['task_id']:x for x in second['results']}
    assert len(left)==len(right)==57 and set(left)==set(right)
    rows=[]
    for task in sorted(left):
        a,b=left[task],right[task]
        rows.append({'task_id':task,'epoch_1_success':a['success'],'epoch_2_success':b['success'],
            'epoch_1_test_fraction':a['num_passes']/a['num_tests'],'epoch_2_test_fraction':b['num_passes']/b['num_tests'],
            'epoch_1_steps':a['steps'],'epoch_2_steps':b['steps'],'epoch_1_termination':a['termination'],'epoch_2_termination':b['termination']})
    return rows


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    cfg=config();root=run_dir('mixed');analysis=B/'analysis';analysis.mkdir(exist_ok=True)
    metrics=[];counts=collections.Counter();masks=collections.Counter();zero_fail_p=collections.Counter()
    later=0;selected_U=0;examples_total=0;supervised_tokens=0;trajectories=0;judge_attempts=0;judge_repairs=0
    for number in range(1,37):
        folder=batch_dir('mixed',number)
        if not (folder/'checkpoint/COMPLETE.json').exists():continue
        m=read(folder/'checkpoint/metrics.json');metrics.append(m)
        data=read(folder/'dataset.json');counts.update(data['counts']);masks.update(data['mask_reasons'])
        examples_total+=len(data['examples']);supervised_tokens+=m['supervised_tokens'];trajectories+=len(data['sources'])
        for e in data['examples']:
            if 'F' not in e['labels']:zero_fail_p[str(e['labels'].count('P'))]+=1
            if e['branch']=='sdpo':later+=e['uses_later_evidence']
            if e['branch']!='mask':selected_U+=('U' in e['labels'])
        for path in (folder/'judging').glob('*/metadata.json'):
            attempts=read(path).get('attempts',[]);judge_attempts+=len(attempts)
            judge_repairs+=sum(a['kind']=='format_repair' for a in attempts)
    evaluations={}
    for epoch in (1,2):
        path=root/f'epoch_{epoch:02d}_dev57/summary.json'
        if path.exists():evaluations[str(epoch)]=read(path)
    complete=len(metrics)==36 and len(evaluations)==2
    paired=paired_results(evaluations['1'],evaluations['2']) if len(evaluations)==2 else []
    improvements=[x['task_id'] for x in paired if not x['epoch_1_success'] and x['epoch_2_success']]
    regressions=[x['task_id'] for x in paired if x['epoch_1_success'] and not x['epoch_2_success']]
    summary={'generated_at':now(),'complete':complete,'arm':'mixed','teacher':'C2_feedback','completed_batches':len(metrics),
        'optimizer_updates':metrics[-1]['optimizer_updates'] if metrics else 0,'training_trajectories':trajectories,
        'steps':examples_total,'branch_counts':dict(counts),'mask_reasons':dict(masks),'zero_FAIL_PASS_histogram':dict(zero_fail_p),
        'supervised_response_tokens':supervised_tokens,'sdpo_steps_using_later_evidence':later,'selected_steps_with_U':selected_U,
        'judge_attempts':judge_attempts,'format_repair_attempts':judge_repairs,'evaluations':evaluations,
        'epoch_2_gains':improvements,'epoch_2_regressions':regressions,'sft_control_run':False,'matched_base_model_dev57_run':False}
    write_json(analysis/'b_report.json',summary)
    training_rows=[{k:m[k] for k in ['batch','lr','sft_loss','sdpo_loss','total_loss','sft_grad_norm','weighted_sdpo_grad_norm',
        'branch_grad_cosine','grad_norm_before_clip','grad_norm_after_clip','clipped','student_parameter_delta_norm',
        'peak_allocated_gib','peak_reserved_gib','seconds','optimizer_updates']}|{
            'sft_steps':m['counts'].get('sft',0),'sdpo_steps':m['counts'].get('sdpo',0),'masked_steps':m['counts'].get('mask',0)} for m in metrics]
    write_csv(analysis/'training_metrics.csv',training_rows);write_csv(analysis/'dev57_paired_results.csv',paired)
    lines=['# B 阶段报告：ZeroFail3 SFT ＋ C2 反馈条件 SDPO','',
        f"生成时间：{summary['generated_at']}。状态：{'两轮训练与两次 dev57 评估全部完成' if complete else '运行中；以下仅为已提交结果'}。",'',
        f"已完成 {len(metrics)}/36 个 batch、{summary['optimizer_updates']} 次实际更新、{trajectories}/180 条训练轨迹。默认 C2 教师；仅运行 mixed，未运行 SFT 对照。",'',
        '## dev57 官方评估','',
        '每轮结束后使用该轮学生 adapter，完整运行相同的 57 道 dev 题。学生不带反馈；temperature=0、seed=100、最多 50 步，AppWorld 官方评价保留本地。两个 checkpoint 均预先指定，不根据 dev 结果选择或更改训练参数。','',
        '| 轮次 / checkpoint | 整题成功数 | TGC | 每题测试通过率的平均值 | 平均步骤 |',
        '|---|---:|---:|---:|---:|']
    for epoch in (1,2):
        e=evaluations.get(str(epoch))
        if e:lines.append(f"| 第 {epoch} 轮 / batch {18*epoch} | {e['successes']}/57 | {e['task_goal_completion']:.2%} | {e['macro_test_pass_fraction']:.2%} | {statistics.mean(x['steps'] for x in e['results']):.2f} |")
        else:lines.append(f'| 第 {epoch} 轮 / batch {18*epoch} | 待完成 | — | — | — |')
    if paired:
        delta=(evaluations['2']['task_goal_completion']-evaluations['1']['task_goal_completion'])*100
        lines+=['',f'第 2 轮相对第 1 轮 TGC 变化 **{delta:+.2f} 个百分点**；新增成功 {len(improvements)} 题，退步 {len(regressions)} 题。',
            f"新增成功 task ID：{', '.join(improvements) or '无'}。",f"退步 task ID：{', '.join(regressions) or '无'}。",
            '完整逐题配对结果见 [dev57_paired_results.csv](analysis/dev57_paired_results.csv)。']
    lines+=['','## 首批验收与训练稳定性','']
    if metrics:
        first=metrics[0]
        lines += [f"首批 5 题共 {sum(first['counts'].values())} 步：SFT {first['counts'].get('sft',0)}、SDPO {first['counts'].get('sdpo',0)}。SFT loss={first['sft_loss']:.6f}，SDPO loss={first['sdpo_loss']:.6f}，总 loss={first['total_loss']:.6f}。",
            f"首批两分支梯度范数 {first['sft_grad_norm']:.6f}/{first['weighted_sdpo_grad_norm']:.6f}，总梯度 {first['grad_norm_before_clip']:.6f}，参数变化范数 {first['student_parameter_delta_norm']:.6f}，教师无梯度。",
            f"已完成批次中，最大训练 allocated/reserved 显存分别为 {max(m['peak_allocated_gib'] for m in metrics):.2f}/{max(m['peak_reserved_gib'] for m in metrics):.2f} GiB；{sum(m['clipped'] for m in metrics)}/{len(metrics)} 批触发 norm=1 裁剪。这些显存值不包含 vLLM 预留的 KV cache。",
            f"SFT loss 范围 {min(m['sft_loss'] for m in metrics):.6f}–{max(m['sft_loss'] for m in metrics):.6f}；SDPO loss 范围 {min(m['sdpo_loss'] for m in metrics):.6f}–{max(m['sdpo_loss'] for m in metrics):.6f}。不同批次为不同在线轨迹，loss 变化不能单独作为效果提升证据。",
            '逐批 loss、梯度、裁剪、显存及样本数见 [training_metrics.csv](analysis/training_metrics.csv)；首批检查见 [first_batch_acceptance.json](analysis/first_batch_acceptance.json)。']
    lines+=['','## 训练数据与反馈利用','',
        f"已提交轨迹共 {examples_total} 步，SFT {counts['sft']}、SDPO {counts['sdpo']}、mask {counts['mask']}；监督回答 token 共 {supervised_tokens}。",
        f"屏蔽原因：{dict(masks)}。无 FAIL 步骤按 PASS 数量分布：{dict(sorted(zero_fail_p.items()))}。",
        f"选中步骤含 U 的数量为 {selected_U}；SDPO 反馈引用后来证据的步骤为 {later}/{counts['sdpo']}。评分调用共 {judge_attempts} 次，其中格式修复 {judge_repairs} 次；有效评分缓存复用，不因结果差重新抽样。",'',
        '## 方法与配置','',
        '每批 5 道 train90 题、每题采 1 条完整轨迹；整批政策固定。轨迹结束后统一使用冻结 v7-feedback prompt，为每步打分并为全部 FAIL 步骤产生反馈。F=0 且 P≥3 做原回答 SFT；含 F 且反馈可用的步骤做 C2 条件自蒸馏；其他步骤保留历史、屏蔽当前回答 loss。',
        'C2 教师输入为原动作前历史＋FAIL 规则＋具体诊断与修正建议，不额外引用完整原回答。教师是 Qwen3-8B 的 EMA LoRA；Codex 提供反馈。学生与教师在相同原回答前缀上比较分布。',
        '`L = mean_steps(mean_tokens(SFT CE)) + 1.0 × mean_steps(mean_tokens(KL_bucket(student || stopgrad(C2 teacher))))`。top-100＋tail 桶，两项独立归一化；整批梯度累计后只更新一次。',
        'Qwen3-8B 冻结底座；LoRA r=8/alpha=16/dropout=0；AdamW lr=5e-5，前 5 次非空更新线性 warmup（首次 1e-5）；EMA=0.95；gradient norm clip=1；bf16＋fp32 概率计算；物理 GPU1。学生/教师上下文限制为 32000/32768；超限不截断，按规则屏蔽。',
        '配置、题目顺序和版本摘要见 [config](config/run.json)、[schedule](config/schedule.json)、[版本摘要](config/preparation_manifest.json)。',
        '', '## 结论边界','',
        '首批数值验收证明训练管线可运行、两分支提供有限且非零的梯度，不等于证明反馈提高了任务完成率。两轮 dev57 可以比较这两个 checkpoint；本轮没有匹配的底座 dev57 和在线 SFT 对照，因此不能将其差异直接归因于 SDPO，也不能声称相对基线提升。',
        'A 阶段已经验证的局部反馈纠错收益与这里的完整任务指标分开报告。C2 在原错误回答前缀上的教师分布可能保留错误倾向，该限制不会因为训练无 NaN 而自动消失。dev57 不是新的未见测试集。',
        '', '运行状态见 [STATUS.json](STATUS.json)，后台日志见 [supervisor.log](runs/mixed/supervisor.log)。']
    (B/'REPORT.md.tmp').write_text('\n'.join(lines)+'\n');(B/'REPORT.md.tmp').replace(B/'REPORT.md')
    return summary


if __name__=='__main__':main()
