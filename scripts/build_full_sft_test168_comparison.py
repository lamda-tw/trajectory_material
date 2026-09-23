#!/usr/bin/env python3
"""Build a paired AppWorld test_normal report without changing evaluation outputs."""
from __future__ import annotations
import argparse
import collections
import csv
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from analyze_appworld_matched_rollouts import analyze, OUTPUT, read_json
from build_appworld_full_sft_aligned_dev_report import (
    load_score_snapshot, load_task_ids, audit_task_status, audit_run, transition, sha256,
)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def joined(values): return '、'.join(values) or '无'


def paired_analysis(full, lora, ids):
    f, l = full['per_task'], lora['per_task']
    won = [t for t in ids if f[t]['success'] and not l[t]['success']]
    lost = [t for t in ids if l[t]['success'] and not f[t]['success']]
    common = [t for t in ids if f[t]['success'] and l[t]['success']]
    neither = [t for t in ids if not f[t]['success'] and not l[t]['success']]
    no_context = [t for t in ids if not f[t]['signals']['context_error'] and not l[t]['signals']['context_error']]
    by_terminal = collections.defaultdict(list)
    for t in lost: by_terminal[f[t]['terminal_group']].append(t)
    shared_cost = {label:{k:sum(rows[t]['counts'].get(k,0) for t in common)
                         for k in ['lm_requests','api_calls','input_tokens','output_tokens','total_tokens']}
                   for label, rows in [('full_sft',f),('lora',l)]}
    # Resample whole three-task scenarios, preserving within-scenario dependence.
    import numpy as np
    families = sorted({t.rsplit('_',1)[0] for t in ids})
    differences = np.array([sum(int(f[t]['success'])-int(l[t]['success']) for t in ids if t.rsplit('_',1)[0]==family)/3 for family in families])
    assert len(families)==56
    scenario_outcomes=[]
    for family in families:
        members=[t for t in ids if t.rsplit('_',1)[0]==family]
        assert len(members)==3
        fs=sum(f[t]['success'] for t in members); ls=sum(l[t]['success'] for t in members)
        scenario_outcomes.append({'scenario_id':family,'task_ids':members,'full_sft_success_count':fs,'lora_success_count':ls,'delta':fs-ls})
    rng=np.random.default_rng(20260923)
    bootstrap=rng.choice(differences,size=(20000,len(families)),replace=True).mean(axis=1)*100
    interval=np.percentile(bootstrap,[2.5,97.5]).tolist()
    return {'scenario_outcomes':scenario_outcomes,'both_success':common,'full_sft_only_success':won,'lora_only_success':lost,'both_failed':neither,
            'regressions_by_terminal':dict(by_terminal),
            'both_without_context_error':{'task_ids':no_context,'task_count':len(no_context),
                                          'full_sft_success':sum(f[t]['success'] for t in no_context),
                                          'lora_success':sum(l[t]['success'] for t in no_context)},
            'regressions_with_full_context_error':[t for t in lost if f[t]['signals']['context_error']],
            'regressions_without_full_context_error':[t for t in lost if not f[t]['signals']['context_error']],
            'shared_success_cost':shared_cost,
            'scenario_bootstrap':{'seed':20260923,'resamples':20000,'unit':'56 scenarios, each with 3 tasks',
                                  'tgc_delta_percentage_points':float(differences.mean()*100),
                                  'percentile_95_interval':interval,
                                  'scope':'Descriptive uncertainty over scenario composition; not training-seed uncertainty or a causal estimate.'}}


def plot_figures(exp, summary):
    os.environ.setdefault('MPLCONFIGDIR',str(exp/'cache/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    metrics=exp/'metrics'
    colors=['#2878B5','#D65A3A']
    full,lora=summary['target'],summary['lora']
    fig,axes=plt.subplots(1,2,figsize=(11.2,4.2),layout='constrained')
    labels=['All','Level 1','Level 2','Level 3']; x=np.arange(4); w=.35
    for item,offset,color,label in [(lora,-w/2,colors[0],'LoRA'),(full,w/2,colors[1],'Full SFT')]:
        values=[item['aggregate']['task_goal_completion']]+[item['difficulty'][str(k)]['tgc'] for k in [1,2,3]]
        bars=axes[0].bar(x+offset,values,w,label=label,color=color)
        axes[0].bar_label(bars,fmt='%.1f',padding=3,fontsize=8)
    axes[0].set(xticks=x,xticklabels=labels,ylabel='Task goal completion (%)',ylim=(0,70),title='test_normal: 168 tasks')
    axes[0].legend(frameon=False); axes[0].grid(axis='y',alpha=.18); axes[0].set_axisbelow(True)
    p=summary['paired']
    counts=[len(p[k]) for k in ['both_success','lora_only_success','full_sft_only_success','both_failed']]
    bars=axes[1].bar(['Both\nsuccess','LoRA\nonly','Full SFT\nonly','Both\nfail'],counts,color=['#449D76',colors[0],colors[1],'#A0A5AC'])
    axes[1].bar_label(bars,padding=3)
    axes[1].set(ylabel='Number of tasks',ylim=(0,max(counts)*1.22+1),title='Paired outcomes on identical tasks')
    axes[1].grid(axis='y',alpha=.18);axes[1].set_axisbelow(True)
    for suffix in ['png','pdf']: fig.savefig(metrics/f'performance_comparison.{suffix}',dpi=170)
    plt.close(fig)
    training=summary['training_comparison']
    fig,ax=plt.subplots(figsize=(8.5,4.5),layout='constrained')
    for field,color,label in [('lora_mean_loss',colors[0],'LoRA'),('full_sft_mean_loss',colors[1],'Full SFT')]:
        ax.plot([r['epoch'] for r in training['epochs']],[r[field] for r in training['epochs']],marker='o',lw=2.3,label=label,color=color)
    ax.set(xticks=[1,2,3,4,5],xlabel='Completed training epoch',ylabel='Mean completion-only training loss',yscale='log',title='Same train90 data: fitting is not task completion')
    ax.grid(alpha=.2);ax.legend(frameon=False)
    for suffix in ['png','pdf']: fig.savefig(metrics/f'training_loss_comparison.{suffix}',dpi=170)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--experiment',type=Path,required=True)
    args=parser.parse_args()
    exp=args.experiment.resolve(); ws=exp.parent.parent
    assert ws==Path('/root/autodl-tmp/workspace-tw')
    manifest=read_json(exp/'manifest.json')
    assert manifest['status'] in ['EVALUATION_FINISHED','SUCCESS'] and manifest['exit_code']==0
    ids=load_task_ids(exp/'data/datasets/test_normal.txt',168)
    lora_exp=Path(manifest['reference_lora_experiment'])
    target=load_score_snapshot('本次 train90 全参数 SFT',exp,ids,OUTPUT,'test_normal')
    lora=load_score_snapshot('train90 LoRA',lora_exp,ids,OUTPUT,'test_normal')
    baseline=load_score_snapshot('原始 Qwen3-8B（历史接口）',ws/'experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal',ids,OUTPUT,'test_normal')
    assert lora['success_count']==51 and baseline['success_count']==12
    for item in [target,lora,baseline]:
        assert item['aggregate']['task_goal_completion']==round(100*item['success_count']/168,1)
        assert item['aggregate']['scenario_goal_completion']==round(100*item['successful_scenario_count']/56,1)
    status=audit_task_status(exp/'task_status.jsonl',ids,target['individual'])
    assert status['strictly_one_row_per_task'] and status['latest_rows_cover_dataset']
    for key in ['malformed_line_numbers','evaluation_error_task_ids','status_success_mismatch_ids','test_count_mismatch_ids']: assert not status[key],(key,status[key])
    status_rows=[json.loads(line) for line in (exp/'task_status.jsonl').read_text().splitlines() if line.strip()]
    assert all(row['status'] in ['success','failed'] for row in status_rows), 'Unexpected per-task execution/evaluation status'
    assert all((exp/'experiments/outputs'/OUTPUT/'tasks'/t/'misc/finished').is_file() for t in ids)
    run=audit_run(exp,status)
    assert run['final_exit_code']==0
    full_analysis=analyze(exp,ids,target['individual'],'appworld-qwen3-8b-codex-rft-train90-epoch5')
    lora_analysis=analyze(lora_exp,ids,lora['individual'],'appworld-codex-rft-train90-epoch5')
    for data in [full_analysis,lora_analysis]:
        assert not data['request_parameter_mismatches']
        counts=data['totals']
        assert counts['lm_requests']==counts['model_responses']+counts.get('error_responses',0)
        assert counts.get('other',0)==0, 'Non-context model errors require separate investigation'
    prompt_matches=[t for t in ids if full_analysis['per_task'][t]['first_prompt_sha256']==lora_analysis['per_task'][t]['first_prompt_sha256']]
    assert len(prompt_matches)==168
    for t in ids:
        a,b=full_analysis['per_task'][t],lora_analysis['per_task'][t]
        assert a['first_prompt_tokens']==b['first_prompt_tokens'] and a['first_prompt_tokens']>0,t
        assert a['fixed_request_parameter_hashes']==b['fixed_request_parameter_hashes'],t
    assert sha256(exp/'data/datasets/test_normal.txt')==manifest['dataset_sha256']
    relative=Path('config/agent_configs')/(OUTPUT+'.jsonnet')
    assert (exp/relative).read_bytes()==(lora_exp/relative).read_bytes()
    assert read_json(exp/'config/model_integrity.json')['status']=='PASS'
    inventory=read_json(exp/'config/model_file_inventory.json');model=Path(manifest['model'])
    assert inventory['files']=={p.name:{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in model.iterdir() if p.is_file()}
    pair=paired_analysis(full_analysis,lora_analysis,ids)
    training=read_json(exp/'metrics/training_comparison.json')
    summary={'experiment':str(exp),'task_count':168,'scenario_count':56,'target':target,'lora':lora,'baseline':baseline,
             'paired':pair,'runtime':full_analysis['totals'],'lora_runtime':lora_analysis['totals'],
             'full_sft_signals':{k:full_analysis[k] for k in ['all_tasks','failed_tasks','successful_tasks','terminal_groups','answer_failure_kinds','failure_categories','exception_types']},
             'lora_signals':{k:lora_analysis[k] for k in ['all_tasks','failed_tasks','successful_tasks','terminal_groups','answer_failure_kinds','failure_categories','exception_types']},
             'run_audit':run,'task_status_audit':status,'first_prompt_match_count':168,'first_prompt_token_count_matches':168,'fixed_request_parameters_match':True,'training_comparison':training,
             'lora_duration_seconds':read_json(lora_exp/'summary.json')['duration_seconds']}
    rows=[]
    for task_id in ids:
        a,b=full_analysis['per_task'][task_id],lora_analysis['per_task'][task_id]
        change={(True,True):'共同成功',(True,False):'FFT新增成功',(False,True):'FFT退化',(False,False):'共同失败'}[(a['success'],b['success'])]
        rows.append({'task_id':task_id,'difficulty':a['difficulty'],'full_sft_success':a['success'],'lora_success':b['success'],'change':change,
                     'full_sft_passed_tests':a['passed_tests'],'lora_passed_tests':b['passed_tests'],'total_tests':a['num_tests'],
                     'full_sft_terminal':a['terminal_group'],'lora_terminal':b['terminal_group'],
                     'full_sft_lm_requests':a['counts']['lm_requests'],'lora_lm_requests':b['counts']['lm_requests'],
                     'full_sft_context_error':a['signals']['context_error'],'lora_context_error':b['signals']['context_error'],
                     'full_sft_python_error':a['signals']['python_error'],'lora_python_error':b['signals']['python_error'],
                     'full_sft_answer_failure_kind':a['answer_failure_kind'],'lora_answer_failure_kind':b['answer_failure_kind'],
                     'full_sft_failure_categories':'; '.join(a['failure_categories']),'lora_failure_categories':'; '.join(b['failure_categories'])})
    with (exp/'scenario_comparison.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        scenario_rows=[{**r,'task_ids':';'.join(r['task_ids'])} for r in pair['scenario_outcomes']]
        writer=csv.DictWriter(handle,fieldnames=list(scenario_rows[0]));writer.writeheader();writer.writerows(scenario_rows)
    with (exp/'task_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for item in [target,lora,baseline]: item.pop('individual')
    write_json(exp/'metrics/full_sft_rollout_analysis.json',full_analysis)
    write_json(exp/'metrics/lora_rollout_analysis.json',lora_analysis)
    write_json(exp/'summary.json',summary)
    plot_figures(exp,summary)
    manifest.update(status='SUCCESS',report_created_at_utc=datetime.now(timezone.utc).isoformat(),
                    official_scores=target['aggregate'],success_count=target['success_count'],first_prompt_match_count=168,
                    official_evaluation_sha256=target['evaluation_sha256'],lora_official_evaluation_sha256=lora['evaluation_sha256'])
    write_json(exp/'manifest.json',manifest)
    (exp/'REPORT.md').write_text(render_report(exp,summary,manifest))
    (exp/'STATUS.txt').write_text(f"SUCCESS test_normal168 success={target['success_count']}/168 TGC={target['aggregate']['task_goal_completion']} SGC={target['aggregate']['scenario_goal_completion']}\n")
    paths=[exp/name for name in ['REPORT.md','summary.json','manifest.json','STATUS.txt','command.txt','RUN_PLAN.md','task_comparison.csv','scenario_comparison.csv','task_status.jsonl','logs/run.log','logs/run_exit_code.txt','logs/model_weight_hash_verify.log']]
    paths += [Path(target['evaluation_path'])]
    paths += [p for folder in ['metrics','config','scripts_snapshot'] for p in (exp/folder).rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts]
    if (exp/'CASE_STUDIES.md').exists(): paths.append(exp/'CASE_STUDIES.md')
    (exp/'artifacts.sha256').write_text(''.join(f'{sha256(p)}  {p.relative_to(exp)}\n' for p in sorted(set(paths))))
    print(json.dumps({'status':'SUCCESS','success_count':target['success_count'],'official_scores':target['aggregate'],'paired':pair,'signals':full_analysis['all_tasks']['signals']},ensure_ascii=False,indent=2))


def render_report(exp, s, m):
    full,lora,base=s['target'],s['lora'],s['baseline']
    pair=s['paired']; fstats=s['full_sft_signals']; lstats=s['lora_signals']
    fc,lc=s['runtime'],s['lora_runtime']; training=s['training_comparison']
    delta=full['aggregate']['task_goal_completion']-lora['aggregate']['task_goal_completion']
    lower=full['success_count']<lora['success_count']
    verdict='本次全参数 SFT 的最终性能低于同数据、同轮数的 LoRA。' if lower else '本次全参数 SFT 并未低于同数据、同轮数的 LoRA，应以实际分数为准。'
    table=['| 系统 | 成功任务 | TGC | SGC | 完整成功场景 | 通过测试条件 |','|---|---:|---:|---:|---:|---:|']
    for item in [base,lora,full]:
        a=item['aggregate'];e=item['evaluator_tests']
        table.append(f"| {item['label']} | {item['success_count']}/168 | {a['task_goal_completion']:.1f} | {a['scenario_goal_completion']:.1f} | {item['successful_scenario_count']}/56 | {e['passed']}/{e['total']} ({e['pass_percentage']:.1f}%) |")
    difficulty=[]
    for key in ['1','2','3']:
        a,b=full['difficulty'][key],lora['difficulty'][key]
        difficulty.append(f"| {key} | {a['total']} | {b['successes']} ({b['tgc']:.1f}%) | {a['successes']} ({a['tgc']:.1f}%) | {a['successes']-b['successes']:+d} |")
    categories=[]
    union=set(fstats['failure_categories'])|set(lstats['failure_categories'])
    for key in sorted(union,key=lambda k:-(fstats['failure_categories'].get(k,{}).get('task_count',0)-lstats['failure_categories'].get(k,{}).get('task_count',0))):
        a=fstats['failure_categories'].get(key,{}).get('task_count',0);b=lstats['failure_categories'].get(key,{}).get('task_count',0)
        categories.append(f'| {key} | {b} | {a} | {a-b:+d} |')
    terminals=[]
    for key in ['成功','上下文请求被拒绝','达到50步上限','出现提交动作但未满足官方条件','无提交动作的其他终止']:
        terminals.append(f"| {key} | {lstats['terminal_groups'].get(key,0)} | {fstats['terminal_groups'].get(key,0)} |")
    scenario_rows=[]
    for r in sorted(pair['scenario_outcomes'],key=lambda r:(r['delta'],r['scenario_id'])):
        if abs(r['delta'])>=2:
            scenario_rows.append(f"| `{r['scenario_id']}` | {r['lora_success_count']}/3 | {r['full_sft_success_count']}/3 | {r['delta']:+d} |")
    signal_rows=[]
    for label,key in [('上下文中断','context_error'),('出现 Python 执行/语法错误','python_error'),('达到50次LM请求','max_50_requests'),('代码未出现提交调用','no_complete_task_action'),('出现完全相同代码的重复','repeated_identical_code')]:
        signal_rows.append(f"| {label} | {lstats['failed_tasks']['signals'][key]}/{lstats['failed_tasks']['task_count']} | {fstats['failed_tasks']['signals'][key]}/{fstats['failed_tasks']['task_count']} | {lstats['successful_tasks']['signals'][key]}/{lora['success_count']} | {fstats['successful_tasks']['signals'][key]}/{full['success_count']} |")
    exception_rows=[]
    exception_keys=set(fstats['exception_types'])|set(lstats['exception_types'])
    for key in sorted(exception_keys,key=lambda k:-fstats['exception_types'].get(k,{}).get('task_count',0))[:10]:
        exception_rows.append(f"| `{key}` | {lstats['exception_types'].get(key,{}).get('task_count',0)} | {fstats['exception_types'].get(key,{}).get('task_count',0)} |")
    costs=[]
    for label,key in [('LM请求（含拒绝）','lm_requests'),('正常模型回复','model_responses'),('AppWorld API调用','api_calls'),('API文档查询','api_docs_calls'),('输入tokens','input_tokens'),('输出tokens','output_tokens'),('总tokens','total_tokens'),('重复的相同代码动作','repeated_identical_code_actions')]:
        costs.append(f"| {label} | {lc.get(key,0):,} | {fc.get(key,0):,} |")
    loss_rows=[f"| {r['epoch']} | {r['lora_mean_loss']:.6f} | {r['full_sft_mean_loss']:.6f} |" for r in training['epochs']]
    subset=pair['both_without_context_error'];ci=pair['scenario_bootstrap']['percentile_95_interval']
    model_config=f"| 可训练参数 | 21,823,488（LoRA r=8，alpha=16） | 8,190,735,360（约375.3倍） |"
    cases=(exp/'CASE_STUDIES.md').read_text() if (exp/'CASE_STUDIES.md').exists() else '代表轨迹案例将在完整评分审计后补入；逐题证据已保存在 `metrics/*_rollout_analysis.json`。'
    return '\n'.join([
        '# AppWorld test_normal 168 题：train90 全参数 SFT 与 LoRA 详细对照报告','',
        '## 结论','',
        f"固定第5轮全参数模型完成全部 **168/168** 道 test_normal 题和官方评分：**{full['success_count']}/168 成功，TGC={full['aggregate']['task_goal_completion']:.1f}，SGC={full['aggregate']['scenario_goal_completion']:.1f}**。LoRA 为 **51/168，TGC=30.4，SGC=16.1**。成功任务相差 **{full['success_count']-51:+d}**，TGC 相差 **{delta:+.1f} 个百分点**。",'',
        verdict+'两组使用相同训练数据与相同评测协议，差异没有被任务清单、提示词、输出解析器或权重损坏解释。','',
        f"最直接的退化证据是：{len(pair['lora_only_success'])}道LoRA成功而FFT失败的题中，{len(pair['regressions_by_terminal'].get('出现提交动作但未满足官方条件',[]))}道出现提交动作但业务条件仍不满足，{len(pair['regressions_by_terminal'].get('达到50步上限',[]))}道耗尽步数，{len(pair['regressions_with_full_context_error'])}道上下文中断。差距涉及任务约束理解、日期/筛选/聚合、返回结构和状态变更，也涉及错误后的修正；仅扩大窗口不能解释大部分已观察到的差额。",'',
        '综合判断：当前结果更支持优先检查“小规模轨迹数据上的过度适配、更新范围与优化配置、纠错和状态核验训练不足”。这些是与证据相容的机制假设；已被直接确认的是业务结果与执行轨迹的退化，尚未用消融确定各机制的贡献。','',
        '**关于“是不是5轮太多”：目前不能下定论。** 全参数模型训练拟合更强、Dev 表现却更弱，符合过度适配的可能表现；但本次只保留第5轮权重，没有同一训练过程第1/2/3轮的 Dev 曲线，不能证明第2轮更好，更不能把全部差距归因于轮数。下文将已观察到的失败、机制假设和需要的消融分开列出。','',
        '## 1. 评测协议与完整性','',
        '- 模型固定为本次 train90 全参数 SFT 的 epoch5 / step2925，使用独立 BF16 HF 导出权重；未加载或合并 LoRA，未在测试期间更新参数。',
        '- 官方 test_normal：168题、56个场景；与 train、dev 无任务交集。对照使用 LoRA 原始完整168题结果，不以之后24题扩窗诊断结果替换。',
        '- ReAct agent、任务顺序、temperature=0、seed=100、每题最多50步、单次最多3000输出tokens、总上下文32000、无 reasoning parser；GPU0单进程顺序运行，与 LoRA 一致。',
        '- 168/168 题的首次完整 messages 哈希和服务端输入token数逐题相同；所有请求的固定字段在排除模型名、服务地址、凭据后也一致，模型名另按预定目标核验。生成的 agent 配置逐字一致，实际模型服务参数由启动器覆盖；以日志和脚本快照为准。',
        '- 5个模型权重分片 SHA-256 校验通过，文件大小及修改时间与 Dev 使用版本一致；模型的词表和 chat template 已在前次 Dev 审计中核验一致。',
        f"- 官方聚合、逐题记录和CSV覆盖相同168个唯一任务；本次进程退出码0，评分器错误0。运行审计异常：{joined(s['run_audit']['anomalies'])}。",'',
        '## 2. 官方性能、难度与逐题变化','',*table,'',
        'TGC 要求一个任务的全部条件通过；SGC 要求同一场景的三个任务全部成功。测试条件通过率可反映部分完成，不替代 TGC。原始基座行来自历史接口，仅提供背景；严格对齐的主要对照为本次 FFT 与 train90 LoRA。','',
        '| 难度 | 题数 | LoRA成功数（TGC） | 全参数成功数（TGC） | 成功数变化 |','|---:|---:|---:|---:|---:|',*difficulty,'',
        '![性能与逐题对照](metrics/performance_comparison.png)','',
        f"共同成功 **{len(pair['both_success'])}** 题，FFT 新增成功 **{len(pair['full_sft_only_success'])}** 题，FFT 退化 **{len(pair['lora_only_success'])}** 题，两者均失败 **{len(pair['both_failed'])}** 题。完整168题见 [CSV](task_comparison.csv)。",'',
        'FFT新增成功：'+joined(pair['full_sft_only_success']),'',
        'FFT退化：'+joined(pair['lora_only_success']),'',
        '同一场景成功数相差至少2题的情况如下；完整56场景见 `scenario_comparison.csv`。三个变体共享场景结构，因此下方置信区间按场景整体重采样。','',
        '| 场景 | LoRA成功 | FFT成功 | 变化 |','|---|---:|---:|---:|',*scenario_rows,'',
        f"按56个场景为单位做20,000次配对 bootstrap，TGC 差值（FFT−LoRA）的95%百分位区间为 **[{ci[0]:.1f}, {ci[1]:.1f}] 个百分点**。这只描述场景组成变化下的统计不确定性，不代表训练随机种子方差，也不证明差距的因果来源。随机种子和原始统计见 `summary.json`。",'',
        '## 3. 性能差异具体发生在哪里','',
        '### 3.1 官方未满足条件','',
        '下表对两组使用与原 LoRA 报告相同的分类规则，统计未通过某类条件的任务数。一个任务可以属于多个类别，各行不能相加；分类描述业务结果，并非模型内部根因。','',
        '| 未通过条件类别 | LoRA | 全参数SFT | 全参数−LoRA |','|---|---:|---:|---:|',*categories,'',
        f"答案不匹配进一步拆开：LoRA 有 {lstats['answer_failure_kinds'].get('not_given_marker',0)} 题在官方trace中标记 `<<not_given>>`，另有 {lstats['answer_failure_kinds'].get('other_answer_mismatch',0)} 题为其他答案不匹配；FFT 分别为 {fstats['answer_failure_kinds'].get('not_given_marker',0)} 和 {fstats['answer_failure_kinds'].get('other_answer_mismatch',0)}。前者通常伴随未完成提交，不能全解释成数值计算能力；后者仍需逐题看日期、筛选、聚合或回答内容。",'',
        '### 3.2 轨迹终止与执行信号','',
        '为避免重复计数，终止分组按“上下文拒绝→50步上限→代码出现提交调用→其他”优先级统计。代码中出现 `complete_task` 不保证该语句实际运行成功，更不保证业务条件满足。','',
        '| 终止分组 | LoRA | 全参数SFT |','|---|---:|---:|',*terminals,'',
        '| 伴随信号 | LoRA失败题 | 全参数失败题 | LoRA成功题 | 全参数成功题 |','|---|---:|---:|---:|---:|',*signal_rows,'',
        'FFT有1题在第50次请求同时发生上下文拒绝，因此终止分组记为上下文中断；这解释了50次请求信号为20题、50步终止组为19题的差别。','',
        'Python错误有时会被后续修复，因此不能把“出现错误”直接当作失败原因。完全相同代码重复也可能是合理查询；需要结合反复相同报错、耗尽预算及最终状态判断。','',
        '| 环境反馈的异常类型（任务数） | LoRA | 全参数SFT |','|---|---:|---:|',*exception_rows,'',
        '### 3.3 上下文限制能解释多少差距','',
        f"全参数模型有 **{fstats['all_tasks']['signals']['context_error']}** 题遇到上下文拒绝，LoRA 为 **{lstats['all_tasks']['signals']['context_error']}** 题。全参数请求中，输入自身超32000有 **{fc.get('input_exceeds_context',0)}** 次，输入加预留3000输出超限有 **{fc.get('input_plus_output_exceeds_context',0)}** 次。",'',
        f"在 **{len(pair['lora_only_success'])}** 道 LoRA 成功、FFT 失败题中，**{len(pair['regressions_with_full_context_error'])}** 道伴随 FFT 上下文中断，另外 **{len(pair['regressions_without_full_context_error'])}** 道没有该中断。因此应分别讨论窗口问题和未超窗的业务/执行失败。",'',
        f"两组都没有上下文错误的共同子集有 **{subset['task_count']}** 题：FFT 成功 **{subset['full_sft_success']}**，LoRA 成功 **{subset['lora_success']}**。这是已观察轨迹的描述性子集，不能当作“修好上下文后”的反事实分数，正式成绩仍使用完整168题。",'',
        '训练窗口40960而评测32000是与 LoRA 对齐时共同保留的限制，不是本次单独缩短 FFT 的条件。训练转换设置24000字符的 observation 裁剪阈值，记录中有9次裁剪，而评测会遇到很长的原始返回；简单扩大总窗口不保证解决错误调用或一次打印过多数据的问题。两组都存在这个分布差异，只有配对轨迹才能说明其与差距的关联。','',
        '### 3.4 输出接口是否失效','',
        f"FFT 记录 **{fc['lm_requests']:,}** 次LM请求，其中 **{fc['model_responses']:,}** 次正常回复、**{fc.get('error_responses',0)}** 次错误响应。正常回复中空内容 **{fc.get('unexplained_empty_model_responses',0)}** 次、无Python代码 **{fc.get('no_python_model_responses',0)}** 次、输出长度截断 **{fc.get('length_truncated_responses',0)}** 次；No code available observation **{fc.get('no_code_observations',0)}** 次。",'',
        '上下文被拒绝时，AppWorld 会保存带 error、零token用量和空content的占位记录；这不是模型真实生成空白，也不是 reasoning parser 吞掉代码。正常回复和被拒绝请求已分开统计。','',
        '## 4. 代表性配对轨迹证据','',cases,'',
        '## 5. 训练配置差异与“5轮是否太多”','',
        '| 配置 | LoRA | 全参数SFT |','|---|---|---|',model_config,
        '| 更新范围 | q/k/v/o、gate/up/down的低秩adapter；基座冻结 | 全部参数，包括embedding与输出层 |',
        '| 数据/监督 | 90条成功轨迹、1170条决策样本；只监督当前completion | 相同数据SHA-256与监督目标 |',
        '| 轮数/步数/全局batch | 5 / 2925 / 2 | 5 / 2925 / 2 |',
        '| 学习率 | 2e-4，固定 | 峰值1e-5；88步warmup；cosine至1e-6 |',
        '| Weight decay / dropout | 0 / LoRA dropout=0 | 0 / 未新增dropout正则 |',
        '| 梯度裁剪 | 记录的训练循环未显式裁剪 | 全局norm=1.0 |',
        '| 参数与计算精度 | 基座BF16、保存adapter为FP32；BF16 autocast | FP32主参数/AdamW状态、BF16计算与导出 |',
        '| 分布式/内存实现 | DDP、标准completion掩码loss | FSDP、仅计算completion位置logits |','',
        '| epoch | LoRA平均训练loss | 全参数平均训练loss |','|---:|---:|---:|',*loss_rows,'',
        '![相同训练数据上的五轮loss](metrics/training_loss_comparison.png)','',
        '图的纵轴为对数尺度；训练loss只是监督completion的交叉熵，不是任务错误率。两份实际训练快照的 `render_record` 函数AST一致；本次FFT训练前也通过了选定logits与完整loss的数值/逐参数梯度等价测试。详见 `config/training_objective_audit.json`。这些核验降低了明显掩码或标签移位错误的可能性，但不能排除所有训练实现影响。','',
        f"两组每轮都是585步，训练数据哈希相同。第5轮平均loss分别为 **{training['epochs'][-1]['lora_mean_loss']:.6f}** 与 **{training['epochs'][-1]['full_sft_mean_loss']:.6f}**；90个训练内末步诊断的loss分别为 **{training['lora_diagnostic']['loss']:.6f}** 与 **{training['full_sft_diagnostic']['loss']:.6f}**。诊断样本全部参加过训练，不能作为独立验证集。",'',
        '### 已有证据能支持什么','',
        '1. **全参数模型对这批数据拟合更充分，但拟合并不等于闭环泛化。** 90条轨迹产生1170个高度相关的下一步样本，不能当作1170个独立任务；这些轨迹只覆盖30个场景，一轮约94,553个被监督completion tokens；重复5遍没有增加独立任务覆盖。先前同协议Dev已是FFT 12/57、LoRA 23/57，说明低训练loss没有转化为更强的未见任务完成能力。',
        '2. **5轮对两种方法不是等强度的训练。** 可训练参数约375倍、可改变的层和更新约束不同；全参数模型后两轮继续迅速降低训练loss，早停是值得验证的假设。但没有各轮Dev结果，不能说性能恰好从第3轮或第5轮开始下降。',
        '3. **不能用学习率数字直接比较更新强弱。** FFT并没有照搬LoRA的2e-4，而是更低的1e-5加衰减；同时参数化、梯度裁剪、精度与优化路径都不同。现有对照无法分离学习率、轮数与参数更新范围的作用。',
        '4. **示范状态与自主执行后的状态不相同。** 数据有90条成功轨迹，仅9条包含错误恢复；SFT在老师的历史和观察上预测下一步，评测则在学生自己行为产生的状态上继续。小错误、漏查状态或误读返回结构会改变后续输入。报告中的代码错误、重复动作和业务遗漏是可观察信号；这些信号与训练分布偏移相容，但不是单独证明机制的实验。','',
        'LoRA 的定义是冻结基座并注入低秩可训练矩阵；这限制了参数变化方式，但不能据此保证任何任务上都优于全参数训练。[LoRA原论文](https://arxiv.org/abs/2106.09685)。序列模仿学习中，后续观察依赖模型先前动作，是经典的训练/执行分布偏移问题；本实验没有额外运行相应算法来证明它能解决差距。[Ross等，2011](https://proceedings.mlr.press/v15/ross11a.html)。','',
        f"训练任务难度1/2/3的数量为36/36/18，难度3占20%；test_normal难度3为{full['difficulty']['3']['total']}/168（{100*full['difficulty']['3']['total']/168:.1f}%）。这提示复杂任务覆盖不足是两组共有的数据限制，不能单独解释FFT相对LoRA的差额，也不能据测试题内容回填训练。",'',
        '### 目前不能下的结论','',
        '- **不能确认“2轮一定比5轮好”。** 本次第2轮权重已滚动清理；旧67轨迹实验第2轮和第5轮Dev都为0/57，但其数据、学习率和数值策略不同，不能替代本次中间轮次消融。',
        '- **不能直接宣称灾难性遗忘。** 当前只有任务域内评测，没有通用能力前后测；低秩约束可能有帮助属于合理假设，仍需对照。',
        '- **不能把所有差距归咎于窗口、BF16或格式。** 窗口对两组一致，本文单列没有超窗的共同任务；FFT训练采用FP32主参数/状态，训练loss和权重核验正常；格式问题要依据正常回复统计而非错误占位记录。',
        '- **不能认为更低loss就是更好的checkpoint。** 验证依据应是未参与训练的任务完成率，而非这90条训练内诊断样本。','',
        '## 6. 下一步如何验证原因','',
        '| 要验证的问题 | 建议的受控对照 | 固定条件/判据 |','|---|---|---|',
        '| 是否训练过久 | 同一训练过程保存第1/2/3/5轮独立HF模型，在Dev逐轮评分 | 保持本次5轮共2925步的LR计划；早期只导出，不把epochs改为2来缩短cosine，否则同时改变了学习率轨迹 |',
        '| 是否更新空间过大 | 在同数据、预先选定训练预算下对照LoRA、部分层解冻、全参数 | 比较Dev任务/场景成功率与训练loss的分离，不能只看拟合 |',
        '| 学习率或正则是否不合适 | 固定轮次、分别改变LR或weight decay，先在train内留出的独立任务/Dev验证 | 一次控制一个主要因素，使用多种子或报告波动 |',
        '| 错误恢复与状态核验不足 | 只在训练任务上增加学生错误状态下的纠错、分页、提交前状态核验轨迹 | 不复制test轨迹或私有evaluator信息回训练 |',
        '| 长返回导致超窗 | 在train/Dev上比较受控输出、结构化摘要与更长窗口 | 单列窗口拒绝率及剩余业务失败；不把窗口变大等同于能力提升 |','',
        '为兼顾存储，后续可逐轮完成Dev评测后只保留最佳轮和最终轮的独立BF16推理模型，完整续训状态继续滚动保留；这样无需长期保存每轮的optimizer大文件，也不会在尚未评测时丢失早期候选。','',
        '本次没有执行上述额外训练或调参。这里是固定模型测试后的诊断，后续超参选择使用train/Dev；已经观察过本测试集的详细失败后，应避免把反复针对这些题改动后的复测当成新的未经观察盲测。','',
        '## 7. 运行成本与产物','',
        '| 项目 | LoRA | 全参数SFT |','|---|---:|---:|',*costs,'',
        f"正式评测墙钟时间：FFT **{s['run_audit']['duration_seconds']/60:.1f}分钟**，LoRA **{s['lora_duration_seconds']/60:.1f}分钟**。运行时间包含模型启动、官方聚合评分和服务收尾；不同轨迹、加载方式与缓存命中均可能影响墙钟。token数是API记录的逻辑用量，不等于实际计算量；本次未做独立的推理速度基准。",'',
        f"两者共同成功的 {len(pair['both_success'])} 题上，总token开销：FFT {pair['shared_success_cost']['full_sft']['total_tokens']:,}，LoRA {pair['shared_success_cost']['lora']['total_tokens']:,}。这是同一成功子集的描述性成本；总体API调用少可能只是更早失败，不能自动解释为效率更高。",'',
        '- `task_comparison.csv`：168题逐题结果、条件通过数、主要终止类型和LoRA差异；`scenario_comparison.csv`：56场景的配对成功数。',
        '- `metrics/full_sft_rollout_analysis.json`、`metrics/lora_rollout_analysis.json`：相同规则生成的逐题执行信号和证据路径。',
        '- `summary.json`：官方指标、配对转移、难度、场景bootstrap与训练对照。',
        '- `CASE_STUDIES.md`：配对轨迹案例；`metrics/*.png`、`metrics/*.pdf`：性能与训练loss图。',
        '- `experiments/outputs/.../evaluations/test_normal.json`：官方结果；`tasks/`保留实际交互、环境和evaluator证据，仅本地保存。',
        '- `manifest.json`、`config/`、`scripts_snapshot/`、`artifacts.sha256`：固定模型来源、协议、代码快照与校验。',
        f"- 模型路径：`{m['model']}`。评测目录不复制模型权重。",
        f"- 关联记录：[本次训练报告]({m['training_experiment']}/REPORT.md)、[前次Dev57报告]({m['reference_full_sft_dev_experiment']}/REPORT.md)、[LoRA原始test报告]({m['reference_lora_experiment']}/REPORT.md)。",'',
    ])


if __name__=='__main__':
    main()
