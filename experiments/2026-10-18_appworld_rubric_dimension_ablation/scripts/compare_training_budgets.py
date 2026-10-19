"""Audit old ZeroFail3-1710 versus current full-rule-equivalent SFT-1358. CPU only."""
import csv
import hashlib
import statistics as st
from collections import Counter
from experiment_utils import R, read, dump, sha, jsonl, now
from analyze_final_results import parse_report, SEEDS, root, TYPES

OLD=R.parent/'2026-10-16_appworld_rubric_selection_ablation'
O=R/'analysis_three_seeds'


def rows(path):
    return list(csv.DictReader(path.open()))


def save_csv(name,data):
    with (O/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)


def main():
    oldcfg=read(OLD/'config/training.json');newcfg=read(R/'config/training.json')
    budget_fields={'arms','protocol_revision','samples_per_epoch','seeds','selection','updates_per_epoch'}
    assert {k:v for k,v in oldcfg.items() if k not in budget_fields}=={k:v for k,v in newcfg.items() if k not in budget_fields}
    equal_files=['scripts/train.py','runtime_code/rollout_worker.py','runtime_code/policy_server.py',
        'config/agent_prompt.txt','config/dev.txt','config/scoring_prompt_v6_en_format.txt','references/step_labels.csv']
    for p in equal_files:assert sha(OLD/p)==sha(R/p),p
    oldeval=read(OLD/'config/evaluation.json');neweval=read(R/'config/evaluation.json')
    for k in ['paths','agent','sampling','worker_count']:assert oldeval[k]==neweval[k]
    for k in ['temperature','seed','tasks','primary_metric','rubric_on_dev']:assert oldeval['evaluation'][k]==neweval['evaluation'][k]
    oldchecks=[x for x in rows(OLD/'analysis/evaluator_checks.csv') if x['arm']=='zerofail3']
    newchecks=[x for x in rows(O/'evaluator_checks.csv') if x['arm']=='drop_r5']
    old_lookup={(int(x['seed']),x['task_id'],x['requirement']):int(x['passed']) for x in oldchecks}
    assert set(old_lookup)=={(int(x['seed']),x['task_id'],x['requirement']) for x in newchecks}
    old_tasks={};audit=[];missing_rows=[]
    for seed in SEEDS:
        oldsel=jsonl(OLD/f'data/zerofail3/seed_{seed}/selection.jsonl')
        newsel=jsonl(root(seed)/f'data/drop_r5/seed_{seed}/selection.jsonl')
        oldindex={x['id']:x for x in oldsel};newids={x['id'] for x in newsel}
        assert len(oldsel)==1710 and len(newsel)==1358 and all(x==oldindex[x['id']] for x in newsel)
        missing=[x for x in oldsel if x['id'] not in newids];assert len(missing)==352
        missing_rows.extend(dict(seed=seed,id=x['id'],labels=x['labels'],task_id=x['task_id'],
            response_tokens=x['response_tokens'],source=x['source'],step=x['step']) for x in missing)
        oldinit=read(OLD/f'training/zerofail3/seed_{seed}/INITIALIZATION.json')
        newinit=read(root(seed)/f'training/drop_r5/seed_{seed}/INITIALIZATION.json')
        assert oldinit['initial_adapter_tensor_sha256']==newinit['initial_adapter_tensor_sha256']
        summary=read(OLD/f'evaluation/zerofail3/seed_{seed}/epoch_01/SUMMARY.json')
        run=f'zerofail3__seed_{seed}__epoch_01'
        for t in summary['results']:
            task=t['task_id'];path=OLD/f'evaluation/zerofail3/seed_{seed}/epoch_01/trajectories/{task}.json'
            raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==t['sha256']
            import json
            official=json.loads(raw)['official_evaluation']
            report=OLD/f'runtime/{run}/experiments/outputs/{run}__dev__{task}/tasks/{task}/evaluation/report.md'
            parsed=parse_report(report.read_text())
            assert len(parsed)==t['tests']==official['num_tests']
            assert sum(parsed.values())==t['passes']==official['num_passes']
            assert all(parsed.values())==t['success']==official['success']
            assert parsed=={d:bool(v) for (s,tt,d),v in old_lookup.items() if s==seed and tt==task}
            old_tasks[seed,task]=t
        audit.append({'seed':seed,'old_samples':1710,'new_samples':1358,'omitted':352,
            'old_updates':855,'new_updates':679,'same_initial_adapter':True,'subset_metadata_identical':True,
            'old_successes':summary['successes'],'old_macro':summary['mean_test_pass_fraction'],
            'old_supervised_tokens':sum(x['response_tokens'] for x in oldsel),'new_supervised_tokens':sum(x['response_tokens'] for x in newsel),
            'omitted_R5_P':sum(x['labels'][4]=='P' for x in missing),'omitted_R7_P':sum(x['labels'][6]=='P' for x in missing)})
    pairs=[]
    for x in newchecks:
        old=old_lookup[int(x['seed']),x['task_id'],x['requirement']];new=int(x['passed'])
        pairs.append({**{k:x[k] for k in ['seed','task_id','family','requirement','category']},
            'old_1710_passed':old,'new_1358_passed':new,'delta':new-old})
    save_csv('budget_check_pairs.csv',pairs);save_csv('budget_omitted_steps.csv',missing_rows)
    categories=[]
    for category,name in TYPES.items():
        xx=[x for x in pairs if x['category']==category]
        categories.append({'category':category,'name':name,'checks':len(xx),
            'old_passes':sum(x['old_1710_passed'] for x in xx),'new_passes':sum(x['new_1358_passed'] for x in xx),
            'gains':sum(x['delta']==1 for x in xx),'losses':sum(x['delta']==-1 for x in xx),
            'net':sum(x['delta'] for x in xx),'seed_net':[sum(x['delta'] for x in xx if int(x['seed'])==s) for s in SEEDS]})
    save_csv('budget_evaluator_types.csv',categories)
    families=[];current_tasks={(int(x['seed']),x['task_id']):x for x in rows(O/'evaluator_tasks.csv') if x['arm']=='drop_r5'}
    for family in sorted({x['family'] for x in pairs}):
        xx=[x for x in pairs if x['family']==family];keys={(int(x['seed']),x['task_id']) for x in xx}
        families.append({'family':family,'old_macro':st.mean(old_tasks[k]['passes']/old_tasks[k]['tests'] for k in keys),
            'new_macro':st.mean(float(current_tasks[k]['fraction']) for k in keys),
            'old_successes':sum(old_tasks[k]['success'] for k in keys),'new_successes':sum(current_tasks[k]['success']=='True' for k in keys),
            'old_passes':sum(x['old_1710_passed'] for x in xx),'new_passes':sum(x['new_1358_passed'] for x in xx),
            'net_checks':sum(x['delta'] for x in xx)})
    save_csv('budget_evaluator_families.csv',families)
    result={'at_beijing':now(),'old_reports_revalidated':171,'old_checks_revalidated':873,
        'equal_file_hashes':{p:sha(R/p) for p in equal_files},'same_training_recipe_except_scope_and_budget':True,
        'same_agent_and_evaluation_settings':True,'eval_runner_difference':'arm/seed validation and 855->config update count; evaluation seed remains 100',
        'device_difference':'old all seeds on GPU1; current third seed on GPU0','per_seed':audit,
        'new_vs_old_gains':sum(x['delta']==1 for x in pairs),'new_vs_old_losses':sum(x['delta']==-1 for x in pairs),
        'new_vs_old_net_checks':sum(x['delta'] for x in pairs),'categories':categories,'families':families,
        'causal_limit':'Cross-budget observation jointly changes unique samples, optimizer updates, ordering, and third-seed device; not an isolated rule-deletion comparison.'}
    dump(O/'budget_comparison.json',result)
    section=['<a id="baseline-and-budget"></a>','### 1.1 Base、ZeroFail3 与 DropR5/DropR7：相同的是规则池，不是训练模型','',
        '**这里的“基准”应准确称为“全规则 SFT-1358 对照”，不能简称 Base。** Base 是未经本轮 SFT 的原始 Qwen3-8B；旧 ZeroFail3 是全规则池全部 1,710 步训练出的模型；本轮 DropR5/DropR7 是同一个池抽取 1,358 步的新模型，R7 复用 R5。候选集等价，不意味着不同训练预算的权重或成绩等价。此前只强调“不必补同预算 NoDrop”而没有并排展示旧 ZeroFail3，容易造成混淆。','',
        '| 模型/条件 | 候选与实际使用 | 更新数 | 三 seed 成功数 | 平均成功题数/57 | evaluator Macro | Micro |',
        '| --- | --- | ---: | --- | ---: | ---: | --- |',
        '| 原始 Base（旧实验单次评测） | 未做这次 SFT | 0 | 单次 1/57 | 单次 1/57 | 43.53% | 120/291 |',
        '| 旧 ZeroFail3-1710 | 全规则池 1,710，全部使用 | 855 | 10 / 8 / 12 | **10/57** | **51.05%** | **406/873** |',
        '| 本轮全规则 SFT-1358（DropR5/DropR7） | 相同 1,710 池，每次抽 1,358 | 679 | 6 / 7 / 2 | **5/57** | **41.57%** | **320/873** |',
        '| 本轮 DropR1-1358（跨预算观察） | 删除 R1 后的池抽 1,358 | 679 | 10 / 10 / 16 | 12/57 | 57.14% | 473/873 |',
        '| 本轮 DropR2-1358（跨预算观察） | 删除 R2 后的池抽 1,358 | 679 | 9 / 10 / 10 | 9.67/57 | 53.49% | 426/873 |','',
        '**用户指出的下降成立。** 旧 ZeroFail3 平均 10/57，本轮全规则对照只有 5/57；Macro 低 9.48 个百分点，Micro 少通过 86 条。相对旧模型，本轮新增通过 105、丢失通过 191 条检查。三个 seed 的整题差为 −4/−1/−10，Macro 差为 −7.63/−1.52/−19.29 个百分点；前两次同在 GPU1 也下降，不能全归因于 GPU0。Base 的单次旧评测仅作背景，不作为三个 seed 的新重复。','',
        '**已排查的设置差异。** 两轮 `train.py` 完全相同；LR=2e-4、LoRA、优化器、loss、精度及最大长度等训练参数相同，同 seed 初始 adapter tensor 哈希也相同。评分 CSV、评分 prompt、agent prompt、DEV57 清单、执行 worker 的文件哈希一致；解码温度、评测 seed=100 与交互预算相同。评测入口的修改是读取新组名/seed、校验样本数与更新数；没有换评分标准。端口、adapter 名称、GPU0 UUID 处理属于运行隔离。','',
        '**确定发生的变化。** 每次减少 352 个不同步骤（20.58%）与 176 次更新（20.58%），目标 token 从 131,957 降到平均 104,703；旧 ZeroFail3 三次都看完整同一集合，本轮三次看到不同子集。子集采样和长度变化也改变训练顺序，第三 seed 的物理卡不同。因此，当前只能说“这三次从 1,710 全集到 1,358 子集的训练方案表现下降”，不能断言全部下降由少 352 步、某类样本遗漏或某一个规则单独造成。','',
        '全规则集合本身没有改变；本轮只是使用更少的样本训练。每个 seed 丢掉了少量原本就稀疏的 R5=P/R7=P 步骤，遗漏 ID 已保存，但不能根据它们与退化共现，就认定某条样本造成某个 DEV 家族失败。','',
        '**这不会取消本轮同预算对照的意义，但限制了结论。** “DropR1/R2 优于全规则 SFT-1358”回答固定 1,358 步预算的问题；它不是“所有删除方案都优于旧 ZeroFail3-1710”。例如 DropR2 整题均值略低于旧 ZeroFail3、细项 Macro 却更高。DropR1 的跨预算观察也较好，但要解释为删除 R1 的作用，仍应以本轮同预算对照为主。','',
        '#### 跨预算下降具体体现在哪些 evaluator 要求','',
        '下表按与旧报告第 1.2 节相同的八类要求整理，数值是旧 ZeroFail3-1710 → 本轮全规则 SFT-1358；不是 DropR1 对照。','',
        '| 检查类型 | 旧 1,710 步通过/总数 | 本轮 1,358 步通过/总数 | 新增/丢失 | 净变化 | 三 seed 净变化 |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for c in categories:
        section.append(f"| {c['name']} | {c['old_passes']}/{c['checks']} | {c['new_passes']}/{c['checks']} | {c['gains']} / {c['losses']} | {c['net']:+d} | {' / '.join(f'{x:+d}' for x in c['seed_net'])} |")
    section+=['',
        '最大的一类退化是完整名单与对应关系（42→10，净少 32 条），其次为空答案提交（51→29，净少 22 条）；实质答案也从 14/54 降到 8/54。不是只在整题指标上恰好少对了几道。','',
        'd4e9306“关注已点赞歌曲与专辑的全部艺术家”尤其突出：三个关键集合检查各从旧模型的 8/9 降到 1/9；家族总检查从 49/54 降到 17/54，贡献全部净减少的 32/86（37.2%），整题成功从 8/9 降到 1/9，贡献总减少的 7/15。其余家族合计仍净少 54 条检查，不能把下降全部归结为这个案例。播放列表、播放器位置和文件备份也有退化；另有交易点赞范围等家族改善。完整家族对比见 [budget_evaluator_families.csv](analysis_three_seeds/budget_evaluator_families.csv)。','',
        '**针对这次疑问，更直接的后续实验是全规则预算/子集复核。** 可先固定一份现有 1,358 步选择及顺序，让它在多个初始化 seed 下重复，再用预先固定的其他子集重复，区分抽样组成与优化波动。若要单独比较 679/855 次更新，需要明确另立“额外曝光”实验：在同一子集上额外训练会重复样本并超过一轮，不能悄悄塞进原单轮对照。它与“补一个同预算 NoDrop 名称”不是一件事；本次没有启动新实验。','',
        '依据：[旧最终报告](../2026-10-16_appworld_rubric_selection_ablation/REPORT.md)、[设置与结果核验](analysis_three_seeds/budget_comparison.json)、[跨预算逐检查项配对](analysis_three_seeds/budget_check_pairs.csv)、[遗漏步骤索引](analysis_three_seeds/budget_omitted_steps.csv)。复现：`python scripts/compare_training_budgets.py`。','']
    (O/'budget_comparison_section.md').write_text('\n'.join(section))
    print('PASS: 171 old reports revalidated, same recipe/prompt/init confirmed; 105 gains, 191 losses across budgets.')


if __name__=='__main__':
    main()
