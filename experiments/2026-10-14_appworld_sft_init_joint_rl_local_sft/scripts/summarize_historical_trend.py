"""CPU-only report builder; --watch publishes reports as historical evaluations finish."""
import argparse
import csv
import json
import os
from pathlib import Path
import time
from collections import defaultdict
from common import ROOT, WORKSPACE, now, read, dump, sha

D=ROOT/'evaluation/historical_protocol_trend'
ORDER=[0,1,5,10,15]
REL=Path('simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')

def csv_write(path,rows):
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def build():
    points={step:read(D/f'step_{step:05d}/SUMMARY.json') for step in ORDER if (D/f'step_{step:05d}/SUMMARY.json').exists()}
    if not points:return
    task_data={step:read(D/f'step_{step:05d}/experiments/outputs'/REL/'evaluations/dev.json')['individual'] for step in points}
    baseline=task_data[0]
    historical_root=Path(read(D/'INPUT_MANIFEST.json')['historical_baseline'])
    historical_official=read(historical_root/'experiments/outputs'/REL/'evaluations/dev.json')
    historical_tasks=historical_official['individual']
    historical_gained=sorted(t for t in baseline if baseline[t]['success'] and not historical_tasks[t]['success'])
    historical_lost=sorted(t for t in baseline if historical_tasks[t]['success'] and not baseline[t]['success'])
    historical_comparison=dict(historical_TGC_successes=sum(t['success'] for t in historical_tasks.values()),
        current_TGC_successes=points[0]['successes'],historical_SGC_successes=4,
        current_SGC_successes=points[0]['successful_scenarios'],
        historical_evaluator_passed=sum(len(t['passes']) for t in historical_tasks.values()),
        current_evaluator_passed=points[0]['passed_tests'],gained_task_ids=historical_gained,lost_task_ids=historical_lost)
    dump(D/'HISTORICAL_BASELINE_COMPARISON.json',historical_comparison)
    evaluator_rows=[]
    condition_maps={}
    difficulty_rows=[]
    for step,tasks in task_data.items():
        conditions={}
        by_difficulty=defaultdict(list)
        for tid,task in sorted(tasks.items()):
            by_difficulty[task['difficulty']].append(task)
            assert len(task['passes'])+len(task['failures'])==task['num_tests']
            for passed,key in [(True,'passes'),(False,'failures')]:
                for condition in task[key]:
                    identity=(tid,condition['requirement'],condition.get('label',''))
                    assert identity not in conditions, ('Ambiguous evaluator condition',identity)
                    conditions[identity]=passed
                    evaluator_rows.append(dict(step=step,task_id=tid,scenario_id=tid.rsplit('_',1)[0],
                        difficulty=task['difficulty'],task_success=task['success'],
                        requirement=condition['requirement'],label=condition.get('label',''),
                        condition_passed=passed,failure_trace=condition.get('trace',''),
                        official_source=str(D/f'step_{step:05d}/experiments/outputs'/REL/'evaluations/dev.json')))
        condition_maps[step]=conditions
        assert set(conditions)==set(condition_maps[0]), 'Evaluator condition set differs between checkpoints'
        for difficulty,tasks_in_group in sorted(by_difficulty.items()):
            successes=sum(t['success'] for t in tasks_in_group)
            passed=sum(len(t['passes']) for t in tasks_in_group)
            total=sum(t['num_tests'] for t in tasks_in_group)
            difficulty_rows.append(dict(step=step,difficulty=difficulty,tasks=len(tasks_in_group),
                successes=successes,TGC_percent=100*successes/len(tasks_in_group),
                evaluator_passed=passed,evaluator_failed=total-passed,evaluator_total=total,
                evaluator_pass_percent=100*passed/total))
    csv_write(D/'evaluator_test_results.csv',evaluator_rows)
    with (D/'evaluator_test_results.jsonl').open('w') as handle:
        for row in evaluator_rows:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    csv_write(D/'difficulty_results.csv',difficulty_rows)
    summaries=[]
    for step,s in points.items():
        gained=sorted(t for t in baseline if task_data[step][t]['success'] and not baseline[t]['success'])
        lost=sorted(t for t in baseline if baseline[t]['success'] and not task_data[step][t]['success'])
        gained_conditions=[dict(task_id=k[0],requirement=k[1],label=k[2]) for k,v in condition_maps[step].items() if v and not condition_maps[0][k]]
        lost_conditions=[dict(task_id=k[0],requirement=k[1],label=k[2]) for k,v in condition_maps[step].items() if not v and condition_maps[0][k]]
        summaries.append(dict(step=step,successes=s['successes'],tasks=57,TGC_percent=s['TGC_percent'],
            successful_scenarios=s['successful_scenarios'],scenarios=19,SGC_percent=s['SGC_percent'],
            passed_tests=s['passed_tests'],failed_tests=s['total_tests']-s['passed_tests'],total_tests=s['total_tests'],
            evaluator_pass_percent=100*s['passed_tests']/s['total_tests'],
            task_mean_test_pass_percent=sum(100*len(t['passes'])/t['num_tests'] for t in task_data[step].values())/57,
            zero_test_pass_tasks=sum(not t['passes'] for t in task_data[step].values()),
            partial_test_pass_tasks=sum(bool(t['passes']) and bool(t['failures']) for t in task_data[step].values()),
            gained_count=len(gained),lost_count=len(lost),gained_task_ids=gained,lost_task_ids=lost,
            gained_evaluator_conditions=len(gained_conditions),lost_evaluator_conditions=len(lost_conditions),
            gained_evaluator_details=gained_conditions,lost_evaluator_details=lost_conditions))
    csv_write(D/'trend.csv',[{k:v for k,v in row.items() if not isinstance(v,list)} for row in summaries])
    task_rows=[]
    for tid in sorted(baseline):
        row=dict(task_id=tid,scenario_id=tid.rsplit('_',1)[0],num_tests=baseline[tid]['num_tests'])
        for step in ORDER:
            item=task_data.get(step,{}).get(tid)
            row[f'step_{step}_success']=item['success'] if item else ''
            row[f'step_{step}_passed_tests']=len(item['passes']) if item else ''
        task_rows.append(row)
    csv_write(D/'paired_task_results.csv',task_rows)
    scenario_rows=[]
    for sid in sorted({t.rsplit('_',1)[0] for t in baseline}):
        row=dict(scenario_id=sid)
        tids=[t for t in baseline if t.rsplit('_',1)[0]==sid]
        for step in ORDER:
            row[f'step_{step}_successful_tasks']=sum(task_data[step][t]['success'] for t in tids) if step in points else ''
            row[f'step_{step}_scenario_success']=all(task_data[step][t]['success'] for t in tids) if step in points else ''
        scenario_rows.append(row)
    csv_write(D/'scenario_results.csv',scenario_rows)
    result=dict(at=now(),complete=len(points)==5 and (D/'COMPLETE.json').exists(),points=summaries,
        historical_baseline_comparison=historical_comparison,
        baseline_reproduction=read(D/'BASELINE_REPRODUCTION.json') if (D/'BASELINE_REPRODUCTION.json').exists() else None,
        source_summaries=[dict(path=str(D/f'step_{s:05d}/SUMMARY.json'),sha256=sha(D/f'step_{s:05d}/SUMMARY.json')) for s in points])
    dump(D/'COMPARISON.json',result)
    os.environ['MPLCONFIGDIR']=str(D/'plot_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,key,title,color in [(axes[0],'TGC_percent','Task goal completion (DEV57)','#2563eb'),
                               (axes[1],'SGC_percent','Scenario goal completion (19 scenarios)','#b45309')]:
        ax.plot([s['step'] for s in summaries],[s[key] for s in summaries],marker='o',color=color)
        for s in summaries:ax.annotate(f'{s[key]:.2f}%',(s['step'],s[key]),textcoords='offset points',xytext=(0,8),ha='center',fontsize=9)
        ax.set(xticks=ORDER,xlabel='Optimizer updates',ylabel='Percent',ylim=(0,65),title=title)
        ax.grid(alpha=.25)
    fig.suptitle('Same historical evaluation protocol; GPU1; temperature=0')
    fig.savefig(D/'trend.png',dpi=180)
    plt.close(fig)
    lines=['# 同历史协议的训练过程性能对照','',f'更新时间：{now()}；完成 {len(points)}/5 个模型。',
        '', '每个点均为同一DEV57、原始AppWorld agent和历史Chat Completions配置；仅替换LoRA权重。step 0为本次在GPU1复测的初始模型。',
        '', '| 更新次数 | TGC | SGC | evaluator通过/总数 | evaluator失败数 | evaluator通过率 | 新增成功题 | 丢失成功题 |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f'| {s["step"]} | {s["successes"]}/57 = {s["TGC_percent"]:.2f}% | {s["successful_scenarios"]}/19 = {s["SGC_percent"]:.2f}% | {s["passed_tests"]}/{s["total_tests"]} | {s["failed_tests"]} | {s["evaluator_pass_percent"]:.2f}% | {s["gained_count"]} | {s["lost_count"]} |')
    if len(points)==5:
        initial,final=summaries[0],summaries[-1]
        best_tgc=max(s['successes'] for s in summaries);best_sgc=max(s['successful_scenarios'] for s in summaries)
        tgc_steps=[s['step'] for s in summaries if s['successes']==best_tgc]
        sgc_steps=[s['step'] for s in summaries if s['successful_scenarios']==best_sgc]
        trend_values=[s['successes'] for s in summaries]
        monotonic_up=all(a<=b for a,b in zip(trend_values,trend_values[1:]))
        monotonic_down=all(a>=b for a,b in zip(trend_values,trend_values[1:]))
        trend='五点TGC相同' if monotonic_up and monotonic_down else ('TGC随更新次数非递减' if monotonic_up else ('TGC随更新次数非递增' if monotonic_down else 'TGC随更新次数存在上升和下降'))
        lines += ['', '## 本次观测结论','',
            f'最终step 15相对step 0：成功题数{final["successes"]-initial["successes"]:+d}，TGC {final["TGC_percent"]-initial["TGC_percent"]:+.2f}个百分点；全对场景数{final["successful_scenarios"]-initial["successful_scenarios"]:+d}，SGC {final["SGC_percent"]-initial["SGC_percent"]:+.2f}个百分点；evaluator通过条件数{final["passed_tests"]-initial["passed_tests"]:+d}。',
            '',f'{trend}。观测到的最高TGC为{best_tgc}/57，出现在step '+ '、'.join(map(str,tgc_steps)) + f'；最高SGC为{best_sgc}/19，出现在step '+ '、'.join(map(str,sgc_steps))+'。',
            '', '这是每个checkpoint各一次完整DEV57的观测曲线。它能显示本次更新过程的表现变化；没有重复运行或消融，不能单独确定RL、SFT或KL的因果贡献，也不据此声称统计显著。']
    lines += ['', '![TGC and SGC by optimizer update](trend.png)', '',
              '[57题配对结果](paired_task_results.csv) · [19场景结果](scenario_results.csv) · [指标CSV](trend.csv) · [JSON](COMPARISON.json)',
              '', '[完整评测协议与运行记录](../../HISTORICAL_DEV57_RUN.md) · [模型/数据/代码哈希](INPUT_MANIFEST.json) · [检查点更新次数及SFT消耗](TRAINING_CHECKPOINTS.json) · [独立最终验收](FINAL_AUDIT.json)（五点完成后生成）',
              '', '[逐条evaluator测试及完整失败trace CSV](evaluator_test_results.csv) · [同内容JSONL](evaluator_test_results.jsonl) · [按难度统计](difficulty_results.csv)',
              '', 'TGC要求某题全部测试通过；SGC要求一个场景的三题全部成功。evaluator通过率为全部测试条件中通过的比例（微平均），不是TGC或SGC。另在CSV/JSON中给出先对每题测试通过率计算、再对57题平均的宏平均，避免混淆口径。新增/丢失均相对本次step 0。',
              '', '历史23/57仅作复现参照；本次各checkpoint的收益与损失均相对同环境重测的step 0计算。此前另一入口的20/57不进入此图。',
              '',f'同一A0模型的历史/本次实测：TGC 23/57→{points[0]["successes"]}/57；SGC 4/19→{points[0]["successful_scenarios"]}/19；evaluator 206/291→{points[0]["passed_tests"]}/291。逐题新增成功{len(historical_gained)}题、丢失成功{len(historical_lost)}题，详见 [历史A0与本次A0对照](HISTORICAL_BASELINE_COMPARISON.json)。这部分差异不计作训练收益。',
              '', '本次和历史请求均使用seed=100、temperature=0，不能将差异直接归因于换了随机种子。协议校验与历史逐题差异记录见 [step 0复现审计](BASELINE_REPRODUCTION.json)；用户已接受输出差异。推理复现的限制参见 [vLLM官方文档](https://docs.vllm.ai/en/v0.10.2/usage/reproducibility.html)。',
              '', '该曲线描述这一次联合训练沿途的表现，不区分RL/SFT/KL的独立贡献。',
              '', '## evaluator条件变化与部分完成情况','',
              '| 更新次数 | 新增通过条件 | 丢失通过条件 | 全部通过题 | 部分通过题 | 零通过题 | 每题通过率宏平均 |',
              '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f'| {s["step"]} | {s["gained_evaluator_conditions"]} | {s["lost_evaluator_conditions"]} | {s["successes"]} | {s["partial_test_pass_tasks"]} | {s["zero_test_pass_tasks"]} | {s["task_mean_test_pass_percent"]:.2f}% |')
    lines += ['', '## 按任务难度统计', '', '| 更新次数 | 难度 | 成功题/总题 | TGC | evaluator通过/总数 | evaluator通过率 |',
              '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in difficulty_rows:
        lines.append(f'| {s["step"]} | {s["difficulty"]} | {s["successes"]}/{s["tasks"]} | {s["TGC_percent"]:.2f}% | {s["evaluator_passed"]}/{s["evaluator_total"]} | {s["evaluator_pass_percent"]:.2f}% |')
    lines += ['', '## 57题逐题evaluator通过数', '', '表中为通过条件数/总条件数；全部通过才计入该题成功。', '',
              '| 题目 | step 0 | step 1 | step 5 | step 10 | step 15 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in task_rows:
        values=[f'{r[f"step_{step}_passed_tests"]}/{r["num_tests"]}' if step in points else '待完成' for step in ORDER]
        lines.append('| '+r['task_id']+' | '+' | '.join(values)+' |')
    lines += ['', '## 19个场景的三题完成情况', '', '| 场景 | step 0 | step 1 | step 5 | step 10 | step 15 |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in scenario_rows:
        values=[f'{r[f"step_{step}_successful_tasks"]}/3' if step in points else '待完成' for step in ORDER]
        lines.append('| '+r['scenario_id']+' | '+' | '.join(values)+' |')
    for s in summaries[1:]:
        lines += ['',f'## step {s["step"]} 相对 step 0','',
                  '新增成功：'+('、'.join(s['gained_task_ids']) or '无')+'。',
                  '丢失成功：'+('、'.join(s['lost_task_ids']) or '无')+'。',
                  '', '新增通过的evaluator条件：']
        lines += ['']+['- `'+r['task_id']+'`：'+r['requirement']+'（'+r['label']+'）' for r in s['gained_evaluator_details']]
        if not s['gained_evaluator_details']:lines.append('无。')
        lines += ['', '丢失通过的evaluator条件：','']
        lines += ['- `'+r['task_id']+'`：'+r['requirement']+'（'+r['label']+'）' for r in s['lost_evaluator_details']]
        if not s['lost_evaluator_details']:lines.append('无。')
    (D/'COMPARISON.md').write_text('\n'.join(lines)+'\n')
    if result['complete']:
        concise='；'.join(f'step {s["step"]}: TGC {s["successes"]}/57、SGC {s["successful_scenarios"]}/19' for s in summaries)
        plan=WORKSPACE/'plans/2026-10-13_appworld_sft_init_local_sft_online_rl'
        for path,link in [(ROOT/'README.md','evaluation/historical_protocol_trend/COMPARISON.md'),
                          (plan/'README.md',str(D/'COMPARISON.md')),(plan/'PLAN.md',str(D/'COMPARISON.md'))]:
            content=path.read_text()
            marker='> **同历史协议五点评测已完成**'
            if marker not in content:
                head,body=content.split('\n\n',1)
                path.write_text(head+'\n\n'+marker+'（'+now()+'）：'+concise+'。详见 [五点趋势与逐题对照]('+link+')。\n\n'+body)
        path=ROOT/'HISTORICAL_DEV57_RUN.md'
        content=path.read_text();head,body=content.split('\n\n',1)
        if '**五点均已完成**' not in content:
            path.write_text(head+'\n\n**五点均已完成**：'+concise+'。详见 [对照报告](evaluation/historical_protocol_trend/COMPARISON.md)。\n\n'+body)
        dump(D/'REPORT_COMPLETE.json',dict(at=now(),report=str(D/'COMPARISON.md'),report_sha256=sha(D/'COMPARISON.md'),
            points=len(points),tasks=285,comparison_sha256=sha(D/'COMPARISON.json')))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    signature=None
    while True:
        current=tuple((s,(D/f'step_{s:05d}/SUMMARY.json').exists()) for s in ORDER)+(('complete',(D/'COMPLETE.json').exists()),)
        if current!=signature:
            build();signature=current
        if not args.watch or (D/'COMPLETE.json').exists():return
        if (D/'ERROR.json').exists():
            build()
            print('Evaluation requires attention; report watcher exits without changing scores.',flush=True)
            return
        time.sleep(10)

if __name__=='__main__':main()
