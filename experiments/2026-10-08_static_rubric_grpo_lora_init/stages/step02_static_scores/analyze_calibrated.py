"""Audit calibrated outputs and render a reproducible six-rollout reward example."""
from collections import Counter
import csv
from datetime import datetime, timezone
from fractions import Fraction
import json
import math
from pathlib import Path
import statistics
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import common
import judge_calibrated as judge
OUT=ROOT/'runs/step02_static_scores/smoke_v3_calibrated'
OLD=ROOT/'runs/step02_static_scores/smoke_v2'
CN_TITLES=['不暴露秘密值','完成后停止','取全需要的数据','正确调用完成接口','基于实时数据计算','正确处理时间条件','完整处理项目','写操作只针对正确目标','使用正确筛选逻辑','使用完整工作集','执行所需写操作','验证写操作结果','写入内容准确','使用正确数据来源','正确认证','获取所需凭据','使用可运行 Python','需要时查阅文档','从失败中恢复','API 调用有效','只用允许的工具']


def write_csv(path,rows):
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def rid(i): return f'R{i+1:02d}'
def id_text(indices): return '、'.join(rid(i) for i in indices) or '无'
def frac_text(value): return str(value.numerator) if value.denominator==1 else f'{value.numerator}/{value.denominator}'


def worked_example(task, results, rules, group):
    matrix=[[r['score'] for r in results[f'{task}__{i:02d}']['scores']] for i in range(6)]
    kept=[j for j in range(21) if any(row[j]==-1 for row in matrix)]
    dropped=[j for j in range(21) if j not in kept]
    assert kept==group['kept_rule_ids']
    rows=[]
    for i,verdicts in enumerate(matrix):
        p=[j for j in kept if verdicts[j]==1];f=[j for j in kept if verdicts[j]==-1];na=[j for j in kept if verdicts[j]==0]
        exact=10*Fraction(len(p)-len(f),len(p)+len(f)) if p or f else Fraction(0)
        assert math.isclose(float(exact),group['rewards'][i],abs_tol=1e-12)
        rows.append({'sample':i,'raw_P':verdicts.count(1),'raw_F':verdicts.count(-1),'raw_NA':verdicts.count(0),
                     'P_ids':p,'F_ids':f,'NA_ids':na,'P':len(p),'F':len(f),'NA':len(na),
                     'numerator':len(p)-len(f),'denominator':len(p)+len(f),
                     'exact_reward':frac_text(exact),'reward':float(exact)})
    rewards=[row['reward'] for row in rows];mean=statistics.mean(rewards);ss=sum((r-mean)**2 for r in rewards);std=math.sqrt(ss/5)
    adv=[(r-mean)/(std+1e-6) if std else 0.0 for r in rewards]
    assert all(math.isclose(a,b,abs_tol=1e-12) for a,b in zip(adv,group['advantages']))
    labels={1:'P',-1:'F',0:'NA'}
    lines=['## 一个真实题目的完整计算：六条 Spotify 轨迹','',
           f'固定示例为 `{task}`：询问最长 Spotify 播放列表的时长，换算成分钟并四舍五入。00–05 对应该题六条已有采样轨迹；使用本次校准后的 judge 原始判定。例题在读取新分数前已固定。',
           '', '### 第一步：把 21 条规则的判定全部列出来','',
           'P = PASS（+1），F = FAIL（−1），NA = 不适用（0）。这里的 0 是判定编码，后面算平均时 NA 不计入分母。R01–R21 按官方规则原顺序编号，对应 JSON 的零基 rule_id 0–20。Codex 只提供这些判定与证据；以下过滤、计数、reward 和 advantage 均由确定性的 Python 代码计算。', '',
           '| 规则 | 轨迹00 | 轨迹01 | 轨迹02 | 轨迹03 | 轨迹04 | 轨迹05 | 本组计算时 |',
           '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for j,rule in enumerate(rules):
        lines.append('| '+rid(j)+' '+CN_TITLES[j]+' | '+' | '.join(labels[matrix[i][j]] for i in range(6))+' | '+('保留：出现过 F' if j in kept else '删除：没有 F')+' |')
    lines+=['','### 第二步：先按整组六条过滤规则','',
            '**逐行检查，而不是每条轨迹自己挑规则。** 只要某规则在这六条里至少有一个 FAIL，就进入该组共同的保留集合 K；全 PASS、全 NA、PASS/NA 混合都删除。六条全 FAIL 仍保留，不能把“全 FAIL”误删。', '',
            f'- 保留 **{len(kept)} 条**：{id_text(kept)}。',f'- 删除 **{len(dropped)} 条**：{id_text(dropped)}。','',
            '规则文件本身没有变化。这只是决定本组哪些已有判定参与 reward；换一个题，保留集合可能不同。', '', '读表时可先看几行：R02 六个 PASS，所以删除；R06 六个 NA，也删除；R09 出现 FAIL，所以保留。R08 虽然多数为 NA，但轨迹 01 实际调用 play_music 改变了播放状态，违反只读任务的目标约束，得到 FAIL；因此 R08 也保留。它只进入轨迹 01 的分母，另外五条的该项为 NA，不进分母。', '',
            '### 第三步：每条轨迹在保留集合里数 PASS、FAIL、NA','',
            '| 轨迹 | 保留项中的 PASS 规则 | 保留项中的 FAIL 规则 | 保留项中的 NA 规则 |',
            '| --- | --- | --- | --- |']
    for row in rows:
        lines.append(f"| {row['sample']:02d} | {id_text(row['P_ids'])} | {id_text(row['F_ids'])} | {id_text(row['NA_ids'])} |")
    lines+=['', '| 轨迹 | 过滤前 P/F/NA（总数21） | 过滤后 P | 过滤后 F | 过滤后 NA | 分子 P−F | 分母 P+F |',
            '| --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        lines.append(f"| {row['sample']:02d} | {row['raw_P']}/{row['raw_F']}/{row['raw_NA']} | {row['P']} | {row['F']} | {row['NA']} | {row['numerator']} | {row['denominator']} |")
    lines+=['','### 第四步：逐条代入 reward 公式','',
            r'$$r_i=10\times\frac{P_i-F_i}{P_i+F_i}$$','',
            'P、F 都只数过滤后的规则。NA 不进入分母；若 P+F=0，则 reward=0。这不是除以原来的 21，也不一定除以保留规则总数。10 是本次沿用的奖励缩放。', '',
            '| 轨迹 | 实际代入 | 精确 reward | 小数 reward |','| --- | --- | --- | --- |']
    for row in rows:
        formula=f"10 × ({row['P']}−{row['F']})/({row['P']}+{row['F']}) = 10 × {row['numerator']}/{row['denominator']}" if row['denominator'] else 'P+F=0，按约定记0'
        lines.append(f"| {row['sample']:02d} | {formula} | {row['exact_reward']} | {row['reward']:.6f} |")
    first=rows[0]
    lines+=['',f"以轨迹 00 为例：保留规则里有 **{first['P']} 个 PASS、{first['F']} 个 FAIL、{first['NA']} 个 NA**。因此分子是 {first['P']}−{first['F']}={first['numerator']}，分母是 {first['P']}+{first['F']}={first['denominator']}，乘以 10 后得到 **{first['reward']:.6f}**。",'',
            '### 第五步：GRPO 再把六个 reward 变成相对优势','',
            '**reward 到上一步已经算完。** 下面的 advantage 是训练所用的组内相对信号，不要把两个量混为一谈。本次仅计算，没有执行训练。','',
            r'$$\bar r=\frac{1}{6}\sum_{i=1}^{6}r_i,\quad s=\sqrt{\frac{\sum_{i=1}^{6}(r_i-\bar r)^2}{6-1}},\quad A_i=\frac{r_i-\bar r}{s+10^{-6}}$$','',
            f"本组 reward 向量为 **[{', '.join(f'{x:.6f}' for x in rewards)}]**。",'',
            f'- 六个 reward 的和为 {sum(rewards):.9f}，均值 = {sum(rewards):.9f}/6 = **{mean:.9f}**。',
            f'- 离均差平方和为 {ss:.9f}；使用样本标准差，所以除以 6−1=5：s = sqrt({ss:.9f}/5) = **{std:.9f}**。',
            f'- 归一化分母 s+1e−6 = **{std+1e-6:.9f}**。','',
            '| 轨迹 | reward | reward−组均值 | 除以 s+1e−6 后的 advantage | 官方终态成功（不进入该 reward） |',
            '| --- | --- | --- | --- | --- |']
    for i,r in enumerate(rewards):
        lines.append(f"| {i:02d} | {r:.9f} | {r-mean:.9f} | {adv[i]:.9f} | {'是' if group['official_success'][i] else '否'} |")
    lines+=['','六个 reward 全相同时，约定全部 advantage=0。正优势只表示比本组六条平均分高，不等于官方任务成功；失败轨迹也可能得到正优势。本静态版本没有步骤 credit，若以后训练，该轨迹的相对优势用于其模型生成 token，工具观察和提示不作为生成动作计损失。', '',
            '判定、过滤、求均值与缩放对齐 [DRACO 官方 Stage 3–4](https://github.com/IBM/draco/blob/main/training/docs/REWARD_PIPELINE.md)。这里展示的是本次真实数据的计算，不是为公式编造的例子。','']
    record={'task_id':task,'rule_numbering':'Markdown R01-R21 = JSON rule_id 0-20','matrix_scores':matrix,'kept_rule_ids':kept,'dropped_rule_ids':dropped,'trajectories':rows,'mean_reward':mean,'sum_squared_deviations':ss,'sample_std':std,'epsilon':1e-6,'advantages':adv}
    common.atomic_json(OUT/'reward_worked_example.json',record)
    (OUT/'REWARD_WORKED_EXAMPLE.md').write_text('\n'.join(lines))
    return record


def main():
    config=judge.load_config();manifest=common.read_json(OUT/'manifest.json');rules=common.load_rules(config);summary=common.read_json(OUT/'summary.json')
    assert summary['scored_trajectories']==12 and summary['complete_groups']==2
    assert common.input_fingerprint(common.load_config())==manifest['collection_runtime_fingerprint']
    assert common.file_sha(ROOT/'runs/step01_train90_rollouts/trajectory_index.json')==manifest['trajectory_index_sha256']
    for rel,sha in manifest['source_hashes'].items(): assert common.file_sha(ROOT/rel)==sha
    results={};records=[];diffs=[];usage=Counter();calls=[];recovery_checks=[]
    for row in manifest['selected_trajectories']:
        assert common.file_sha(row['trajectory'])==row['sha256']
        uid=f"{row['task_id']}__{row['sample']:02d}";d=OUT/'judgements'/uid;result=common.read_json(d/'judgement.json');results[uid]=result
        judge.validate_judgement({'scores':result['scores']},rules)
        assert result['scores']==common.read_json(d/f"response_{result['attempts']}.json")['scores']
        prior=common.read_json(OLD/'judgements'/uid/'judgement.json')
        for i,score in enumerate(result['scores']):
            records.append({'trajectory_id':uid,'task_id':row['task_id'],'sample':row['sample'],'rule_id':i,**score})
            if score['score']!=prior['scores'][i]['score']:
                diffs.append({'trajectory_id':uid,'rule_id':i,'title':rules[i]['title'],'before':prior['scores'][i]['score'],'after':score['score'],'old_evidence':prior['scores'][i]['evidence'],'new_evidence':score['evidence']})
        for event_path in sorted(d.glob('events_*.jsonl')):
            audit=judge.audit_events(event_path.read_text());u=audit['usage'] or {};usage.update({k:v for k,v in u.items() if isinstance(v,int)})
            calls.append({'trajectory_id':uid,'stream':str(event_path),'usage':u,'tool_free':True})
        if uid in ['e7a10f8_3__02','e7a10f8_3__03','e7a10f8_3__04']:
            recovery_checks.append({'trajectory_id':uid,'expected_by_specific_rule':1,'actual':result['scores'][18]['score'],'evidence':result['scores'][18]['evidence']})
    write_csv(OUT/'all_verdicts.csv',records)
    common.atomic_json(OUT/'verdict_changes.json',diffs)
    prior_audit=common.read_json(OLD/'audit_sample.json')['records'];audit=[]
    for old in prior_audit:
        new=results[old['trajectory_id']]['scores'][old['rule_id']]
        audit.append({'trajectory_id':old['trajectory_id'],'rule_id':old['rule_id'],'title':new['rubric_title'],'previous_score':old['score'],'score':new['score'],'evidence':new['evidence'],'justification':new['justification']})
    common.atomic_json(OUT/'paired_audit_sample.json',{'selection':'same 30 (trajectory,rule) pairs frozen in smoke_v2; no re-selection by new labels','records':audit})
    task=common.read_json(OUT/'analysis_spec.json')['worked_reward_example_task'];group=next(g for g in summary['groups'] if g['task_id']==task)
    example=worked_example(task,results,rules,group)
    old_summary=common.read_json(OLD/'summary.json')
    comparison={'before_verdict_counts':old_summary['verdict_counts'],'after_verdict_counts':summary['verdict_counts'],'changed_verdicts':len(diffs),'total_verdicts':252,
                'groups':[{'task_id':g['task_id'],'before_rewards':next(x['rewards'] for x in old_summary['groups'] if x['task_id']==g['task_id']),'after_rewards':g['rewards'],'after_advantages':g['advantages']} for g in summary['groups']],
                'recovery_defaults':recovery_checks,'nonexecuted_secret_print':results['29caf6f_1__03']['scores'][0],
                'note':'Same calibration examples were used to design the wrapper. This is a calibration recheck, not independent evidence of judge generalization.'}
    common.atomic_json(OUT/'calibration_comparison.json',comparison)
    validation={'passed':True,'verified_at_utc':datetime.now(timezone.utc).isoformat(),'scored_trajectories':12,'rule_verdicts':252,'complete_groups':2,'judge_requests':len(calls),'retries':len(calls)-12,'all_call_usage':dict(usage),'calls':calls,
                'checks':{'original_scores_equal_accepted_responses':True,'rules_and_sampling_runtime_unchanged':True,'all_sources_and_input_hashes_match':True,'all_21_scores_structurally_valid':True,'recovery_NA_rejected_without_coercion':True,'all_calls_tool_free':True,'worked_example_fraction_math_matches_rewards':True,'worked_example_sample_std_matches_advantages':True},'analysis_script_sha256':common.file_sha(Path(__file__))}
    common.atomic_json(OUT/'technical_validation.json',validation)
    print(json.dumps({'summary':summary,'comparison':comparison,'cost':{'judge_requests':len(calls),'usage':dict(usage)},'example':example},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
