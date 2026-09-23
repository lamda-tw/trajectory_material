#!/usr/bin/env python3
"""Render Chinese reports from audited scores, without choosing another checkpoint."""
import csv,json
from pathlib import Path
E=Path(__file__).resolve().parent.parent
M=json.loads((E/'manifest.json').read_text());T=Path(M['training_experiment'])
def load(p):return json.loads(p.read_text())
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def main():
    s=load(E/'summary.json');models=s['models'];diag=s['diagnostics'];p=s['epoch2_vs_epoch5'];pl=s['epoch2_vs_lora'];tr=s['training_prefix_audit']
    a,b,l=[models[k] for k in ['epoch2','epoch5','lora']]
    inventory=load(T/'metrics/model_inventory.json')
    model_size_gib={k:sum(v['bytes'] for v in item['files'].values())/1024**3 for k,item in inventory.items()}
    delta=a['success_count']-b['success_count'];pp=100*delta/168
    positive_interval=p['scenario_bootstrap']['percentile_95_interval']
    positive_caveat=('但场景配对bootstrap区间包含0，证据有限，尚不能确认五轮过拟合。' if positive_interval[0]<=0<=positive_interval[1] else '且差值方向在本次场景重采样下较稳定；仍需保留重训差异与单次实验的限制。')
    if delta>0:
        verdict=f"两轮模型成功 {a['success_count']}/168，比五轮模型多 {delta} 题，TGC 提高 {pp:.2f} 个百分点。分数方向与‘继续训练到第5轮可能损害任务泛化’的猜想一致，{positive_caveat}"
        interpretation='五轮模型的训练拟合更强，而本次两轮模型的闭环任务成功率更高；这个方向与过度训练/过拟合一致。但由于这是重训对照，不能把全部分差严格归因于多出的三轮，也不能据此确定第2轮是最优轮次。'
    elif delta<0:
        verdict=f"两轮模型成功 {a['success_count']}/168，比五轮模型少 {-delta} 题，TGC 下降 {-pp:.2f} 个百分点。本次结果不支持‘把5轮缩短到2轮就能提升test_normal表现’这一具体预测。"
        interpretation='训练更少没有带来更高的总体成功率。不能仅凭五轮训练loss较低就断言五轮过拟合，也不能反过来据此证明完全没有过拟合；最佳停止点可能在别处，而本实验只比较用户预先指定的2轮和既有5轮。'
    else:
        verdict=f"两轮与五轮均成功 {a['success_count']}/168，总体TGC持平。本次没有观察到任务成功率的提升。"
        interpretation='总成功数相同不等于行为相同，需要看新增成功、丢失成功和完整场景。这个两点比较既不能确认五轮过拟合，也不能排除其他轮次存在更好的停止点。'
    verdict += f"完整成功场景为两轮{a['successful_scenario_count']}/56、五轮{b['successful_scenario_count']}/56。"
    perf=table(['模型','成功任务','TGC %','完整成功场景','SGC %','通过测试条件'],[[v['label'],f"{v['success_count']}/168",f"{v['aggregate']['task_goal_completion']:.1f}",f"{v['successful_scenario_count']}/56",f"{v['aggregate']['scenario_goal_completion']:.1f}",f"{v['evaluator_tests']['passed']}/1077"] for v in [a,b,l]])
    difficulty=table(['难度','题数','两轮成功','五轮成功','LoRA成功','两轮－五轮'],[[d,a['difficulty'][d]['total'],a['difficulty'][d]['successes'],b['difficulty'][d]['successes'],l['difficulty'][d]['successes'],a['difficulty'][d]['successes']-b['difficulty'][d]['successes']] for d in ['1','2','3']])
    terminals=table(['互斥终止分类','两轮','五轮','LoRA'],[[g]+[diag[k]['terminal_groups'].get(g,0) for k in ['epoch2','epoch5','lora']] for g in ['成功','上下文请求被拒绝','达到50步上限','出现提交动作但未满足官方条件','无提交动作的其他终止']])
    signal_names={'context_error':'有上下文拒绝的任务','python_error':'出现Python/执行异常的任务','max_50_requests':'达到50次模型请求的任务','repeated_identical_code':'出现重复代码的任务'}
    signals=table(['观察信号（可重叠）','两轮','五轮','LoRA'],[[name]+[diag[k]['all_tasks']['signals'][field] for k in ['epoch2','epoch5','lora']] for field,name in signal_names.items()])
    cost_names={'lm_requests':'模型请求总数','model_responses':'实际正常模型回复','error_responses':'错误响应占位记录','api_calls':'API尝试调用','api_docs_calls':'API文档查询','repeated_identical_code_actions':'重复代码动作数','input_tokens':'输入tokens（含逻辑缓存token）','output_tokens':'输出tokens','length_truncated_responses':'输出达到长度上限','unexplained_empty_model_responses':'正常响应为空','no_python_model_responses':'正常响应无Python代码块'}
    costs=table(['指标','两轮','五轮','LoRA'],[[name]+[diag[k]['totals'].get(field,0) for k in ['epoch2','epoch5','lora']] for field,name in cost_names.items()])
    mixes=s['action_mix']['distributions']
    mix_names={'train90_teacher':'训练教师目标（1170条）','epoch2':'全参数第2轮','epoch5':'全参数第5轮','lora':'LoRA第5轮'}
    mix_table=table(['来源','动作数','仅文档API直调','其他API直调','无API直调的Python','静态解析失败','无Python'],[[mix_names[k],v['normal_action_count'],str(v['counts']['docs_without_other_api_call'])+' ('+format(v['percentages']['docs_without_other_api_call'],'.1f')+'%)',str(v['counts']['other_api_call'])+' ('+format(v['percentages']['other_api_call'],'.1f')+'%)',v['counts']['python_without_direct_api_call'],v['counts']['python_parse_error'],v['counts']['no_python']] for k,v in mixes.items()])
    cats=sorted(set().union(*(diag[k]['failure_categories'] for k in diag)))
    categories=table(['官方失败条件类别（可重叠）','两轮','五轮','LoRA'],[[cat]+[diag[k]['failure_categories'].get(cat,{}).get('task_count',0) for k in ['epoch2','epoch5','lora']] for cat in cats])
    losses=table(['轮次','本次两轮：该轮平均loss','旧五轮：该轮平均loss'],[[r['epoch'],'—' if r['epoch2_run_mean_loss'] is None else f"{r['epoch2_run_mean_loss']:.6f}",f"{r['epoch5_run_mean_loss']:.6f}"] for r in tr['epochs']])
    reviewed=load(E/'metrics/case_review.json')['cases']
    type_labels={'epoch2_regression':'两轮退化','epoch2_gain':'两轮新增成功','shared_failure_wrong_goal':'共同失败：目标理解','shared_failure_valid_documentation_loop':'共同失败：重复文档查询','shared_context_failure':'共同失败：上下文限制','shared_state_failure':'共同失败：业务状态','epoch2_gain_note_import':'两轮新增成功：内容导入'}
    task_detail=load(E/'metrics/epoch2_rollout_analysis.json')['per_task']
    case_table=table(['人工核对案例','类型','两轮通过条件','五轮通过条件'],[[c['task_id'],type_labels.get(c['type'],c['type']),str(c['epoch2_passed_tests'])+'/'+str(task_detail[c['task_id']]['num_tests']),str(c['epoch5_passed_tests'])+'/'+str(task_detail[c['task_id']]['num_tests'])] for c in reviewed])
    ci=p['scenario_bootstrap']['percentile_95_interval'];nc=p['both_without_context_error'];ncl=pl['both_without_context_error']
    interval_note = '区间包含0，表明差值对场景组成较敏感，单次分数差不宜解释为稳健结论。' if ci[0]<=0<=ci[1] else '区间不包含0，差值方向在本次场景重采样下较稳定，但仍不覆盖重训数值差异和训练种子不确定性。'
    gains=len(p['a_only_success']);loss=len(p['b_only_success']);both=len(p['both_success']);neither=len(p['both_failed'])
    with (E/'scenario_comparison.csv').open(encoding='utf-8-sig') as handle:
        scenario_rows=list(csv.DictReader(handle))
    full_scenarios={key:{r['scenario_id'] for r in scenario_rows if int(r[key+'_success'])==3} for key in ['epoch2','epoch5']}
    scenario_delta_note='两轮新增完整成功场景：'+('、'.join(sorted(full_scenarios['epoch2']-full_scenarios['epoch5'])) or '无')+'；丢失完整成功场景：'+('、'.join(sorted(full_scenarios['epoch5']-full_scenarios['epoch2'])) or '无')+'。这解释了TGC相同而SGC不同：成功任务在场景中的分布发生了变化。'
    result_readout=f"通过条件从五轮的{b['evaluator_tests']['passed']}/1077降至两轮的{a['evaluator_tests']['passed']}/1077（{b['evaluator_tests']['pass_percentage']:.1f}%→{a['evaluator_tests']['pass_percentage']:.1f}%）。难度1新增4题成功，但难度2和3分别减少3题和1题。因此两轮在部分场景更完整，在较难任务和部分进展指标上却更弱，不能概括为总体更好。"
    report=f'''# 两轮全参数SFT与五轮对照：test_normal 168题中文报告

## 1. 结论

{verdict}

{interpretation}

{result_readout}

相对LoRA第5轮（51/168），本次两轮全参数模型的成功任务差为 **{a['success_count']-51:+d}题**。停止轮次对照和FFT/LoRA方法对照是两个问题：后者还涉及可训练参数范围、学习率、裁剪及保存精度等差异，不能只归因为训练轮数。本次缩短训练没有缩小与LoRA的任务成功数差距，因此尚不能把该差距的主要原因归结为‘多训了三轮’。

## 2. 实验问题与控制条件

用户在观察旧五轮结果后，预先指定重训至第2轮并评测test_normal。本次从原始Qwen3-8B初始化，使用同一train90数据（90条成功轨迹、30个任务家族、1170个下一步决策样本）。不从五轮权重继续训练，不使用LoRA初始化。训练2轮共1170次optimizer更新，双卡总batch=2，全部8,190,735,360个参数参与训练。

沿用FP32主参数、FP32 AdamW状态和梯度归约、BF16前向/反向计算、completion-only监督、max_length=40960、SDPA、reentrant梯度检查点、全局梯度裁剪1.0、weight decay=0、seed=20260921。每轮监督token总量为94,553；1170个长输入样本并不代表1170条独立任务轨迹。

**固定原五轮学习率路径，只提前停止。** warmup仍为88步，峰值1e-5，cosine总跨度2925步、最低比例0.1；实际只执行前1170步。最终更新使用学习率约7.14116e-6。若把cosine压缩到1170步，会同时改变学习率与训练时长，本次没有做这种变更。因此本模型应理解为“五轮配方走完前两轮后停止”，不是重新设计过的两轮退火方案。

每轮仅导出一份BF16推理模型：第1轮位于`artifacts/checkpoints/epoch_1_model`，最终第2轮位于`artifacts/model`；没有保存巨大的optimizer重启文件。最终第2轮模型占{model_size_gib['artifacts/model']:.2f}GiB，两份模型合计{sum(model_size_gib.values()):.2f}GiB。本次只评测预先指定的第2轮，不依据test得分在检查点中择优。

## 3. 重训路径与可复现性核验

数据SHA-256：`1f5ea51ea22ce7ef6b84d3e16bbb25976179064f7c8d0483ab7dcb0118ed3220`。训练损失函数、样本构造、参数更新循环及HF导出实现与旧训练一致；新快照仅增加独立的学习率总跨度参数。

1170步学习率最大绝对差 **{tr['lr_max_abs_difference']}**；每卡样本长度与completion token序列匹配 **{tr['rank_length_and_completion_order_matches']}/1170步**。这些长度记录用于核对样本次序特征，并不是每一条样本内容的单独哈希；内容一致性由同一数据文件、相同构造函数与随机种子共同约束。

实际loss不是逐位相同：最大绝对差 **{tr['train_loss_max_abs_difference']:.6f}**，平均绝对差 **{tr['train_loss_mean_abs_difference']:.6f}**，完全相同 **{tr['train_loss_exact_matches']}/1170步**；首次差异出现在第 **{tr['first_loss_difference_step']}** 步。梯度范数最大绝对差为 **{tr['grad_norm_max_abs_difference']:.6f}**，它是未裁剪范数，不能直接等同于参数更新量差异。

首步前向loss相同而梯度已有数值差异，说明同seed不等于当前GPU混合精度/分布式执行逐位确定。具体数值差异来源没有单独隔离验证。旧训练还包含一次严格恢复，本次连续完成；旧第2轮权重已不存在，无法对权重逐位比较。因此以下结果是固定配方的重训对照，不能当作同一组权重在第2轮和第5轮的严格干预实验。

{losses}

![两轮与五轮实际训练loss]({T}/metrics/loss_comparison.png)

图中曲线为50步滑动平均，右图为整轮平均。训练输出中的diagnostic validation取每个训练任务的最后一步，90个样本全部与训练重叠；本次该loss为 **{tr['train_overlap_diagnostic']['loss']:.6f}**。它只反映拟合情况，不是独立dev泛化loss，不应把它下降当作模型变好的证据。

## 4. 评测协议与完整性

三个模型均使用test_normal固定168题（56个场景，每场景3个变体），简化ReAct代码agent，temperature=0、seed=100、50步上限、每次最多3000输出tokens、服务端context=32000、无reasoning parser、逐题执行。服务端引擎初始化seed沿用默认0，请求seed为100；实际启动日志中的13项引擎设置与旧五轮评测一致。`with-reasoning`是沿用的配置名称；实际parser关闭，以运行参数和请求日志为准。

本次168题全部运行结束，每题一个状态记录，completed_index连续1–168；官方evaluator、逐题状态和测试条件数量一致。进程退出码0，无OOM、服务崩溃或连接失败。三组首轮messages、首轮输入token数及固定请求字段逐题一致；生成的agent配置也一致。衔接训练与评测时恢复了独立评测的环境变量，避免继承训练专用分配器和NCCL覆盖；记录见`config/evaluation_environment_isolation.json`及对应patch。全部官方评分依据任务环境状态和答案核验，不以模型自称“完成”为成功标准。

测试任务清单SHA-256：`{M['dataset_sha256']}`。评测耗时 **{s['run_audit']['duration_seconds']/60:.1f}分钟**（含服务启动），计时不等同于纯生成吞吐对比。模型结构、BF16权重分片完整性及SHA-256已经校验，重载生成检查通过。

## 5. 官方总体结果与难度分层

{perf}

TGC为任务完全成功比例，SGC为同一场景三个任务全部成功的比例；通过测试条件是部分进展指标，不能代替TGC。完整成功场景为两轮{a['successful_scenario_count']}个、五轮{b['successful_scenario_count']}个（差值{a['successful_scenario_count']-b['successful_scenario_count']:+d}），两项指标应一起看。{scenario_delta_note}

{difficulty}

![性能及逐题配对结果]({E}/metrics/performance_comparison.png)

## 6. 同题配对：改善和退化分别在哪里

两轮与五轮：共同成功 **{both}** 题，两轮独有成功 **{gains}** 题，五轮独有成功 **{loss}** 题，共同失败 **{neither}** 题。因此净变化为 **{gains}−{loss}={delta:+d}题**，不能把净增/净减当作所有题都沿同一方向变化。

两轮新增成功对应旧五轮的终止分类：`{json.dumps(p['a_gains_by_b_terminal'],ensure_ascii=False)}`。两轮丢失成功自身的终止分类：`{json.dumps({k:len(v) for k,v in p['a_regressions_by_terminal'].items()},ensure_ascii=False)}`。

在双方都没有上下文拒绝的共同子集（{nc['task_count']}题）中，两轮成功{nc['a_success']}题、五轮成功{nc['b_success']}题。这个子集是事后诊断，不是新的官方分数，也不是扩大窗口后的反事实成绩；仍可帮助判断差异是否只集中在超窗任务。

与LoRA配对：共同成功{len(pl['both_success'])}题，两轮独有成功{len(pl['a_only_success'])}题，LoRA独有成功{len(pl['b_only_success'])}题。双方均无上下文拒绝子集{ncl['task_count']}题，两轮成功{ncl['a_success']}题、LoRA成功{ncl['b_success']}题。

按56个完整场景做配对bootstrap（20,000次、seed=20260923），两轮减五轮TGC差为 **{pp:+.2f}个百分点**，95%百分位区间 **[{ci[0]:+.2f}, {ci[1]:+.2f}]**。同一场景的三题成组抽样，避免把相关变体当作独立样本。这个区间只描述对场景组成的敏感性，不覆盖训练随机性，不是对训练时长因果效应的置信区间；当前固定168题的实际分差没有抽样不确定性。{interval_note}

完整的168题、56场景结果见[逐题CSV]({E}/task_comparison.csv)与[场景CSV]({E}/scenario_comparison.csv)。具体执行过程见[配对案例]({E}/CASE_STUDIES.md)。案例用于解释行为，不用于估算全体错误原因占比。

{case_table}

其中，好友同步任务显示两轮会丢失五轮已完成的流程；月度转账题显示两轮也能修正五轮的日期范围错误；Spotify案例则揭示目标理解取反、反复查有效文档但不操作等问题。失败并不只有一种机制，也不一定伴随Python异常。

## 7. 失败行为、格式与资源限制

{terminals}

上述终止分类互斥，优先级为成功、上下文拒绝、50步上限、出现提交动作但未成功、其他；“出现提交动作”只说明环境日志存在相应代码，最终是否完成仍由官方评分决定。

{signals}

{costs}

两轮模型的上下文拒绝任务从29增至44，50步终止从19增至35，出现重复代码的任务从68增至101。它并没有因更早停止训练而自动减少循环或更稳定地推进任务。结合人工案例，重复查文档、难以从错误反馈中恢复和过量打印观察，在两轮阶段已经存在；这排除了‘这些现象只在训练到五轮后才出现’的解释，却不能定位它们何时首次出现，也不能单凭这些信号区分过拟合、学得不足和目标函数不匹配。

### 7.1 文档查询是否占据了过多动作

{mix_table}

这里按一条正常助手回复计数，并提取其中Python代码分类，训练侧按1170条监督目标各计一次，**不是监督token占比，也不是实际API请求次数**。文档类别表示代码至少直接调用一次`apis.api_docs.*`，且没有其他`apis.*`直调；仍可能包含本地Python计算。其他API类别包括读、登录、提交和修改，不等于成功执行了业务变更。别名、动态调用和运行结果不由这一静态统计推断；完整分类保存在`metrics/action_mix.json`。静态解析失败是在统一提取规则下无法通过Python AST解析的动作数，不等于运行日志中的SyntaxError次数；包含代码块也不保证代码语法正确。

两轮文档类别占比为 **{mixes['epoch2']['percentages']['docs_without_other_api_call']:.1f}%**，五轮为 **{mixes['epoch5']['percentages']['docs_without_other_api_call']:.1f}%**，教师目标为 **{mixes['train90_teacher']['percentages']['docs_without_other_api_call']:.1f}%**。比例本身不能区分必要探索和无效重复，要与连续40步交替查询相同文档等轨迹证据结合。不同模型经历的状态和轨迹长度不同，因此这描述执行策略差异，不证明某种训练机制是唯一原因。

较少tokens或API调用也可能只是提前终止或没有执行关键操作，不能单独解释为效率更高。异常出现过不代表一定失败：模型可能根据反馈恢复。重复代码按规范化AST计数，重复查询有时合理，不自动等于无效循环。API日志记录尝试调用，不保证成功返回；文档查询次数多也不能单独证明能力更强。

上下文超限错误里的空content是服务拒绝后的占位记录，必须与真实模型空回复分开。终止于上下文限制，也不意味着扩大窗口就能完成；此前可能已发生错误检索、重复执行或过量打印。训练窗口40960与评测窗口32000的差异为三组共用的实验条件，本次没有改变它，也没有测量扩大窗口的收益。

{categories}

失败类别直接由官方失败条件按固定关键词规则分组，一个任务可属于多类，不能相加成失败总题数。这是表现分类，不能直接当作“过拟合”“遗忘”等内部机制的标签。

## 8. 对过拟合猜想的判断边界

{interpretation}

本实验能回答的是：在现有数据、原五轮学习率路径和固定测试协议下，一次两轮重训是否优于既有五轮模型。它不能单独回答所有FFT是否劣于LoRA、哪一轮最优、降低学习率是否更好，或某个失败到底来自记忆化还是基础能力遗忘。

小数据全参数更新是需要考虑的解释：训练集只有30个任务家族、每遍约9.46万监督tokens，却更新约81.9亿参数；成功教师轨迹的teacher-forcing目标是预测下一步代码，不直接优化学生在自己错误历史上的闭环恢复。训练loss下降、代码格式正确与新任务成功是不同指标。参数更新范围、轨迹覆盖、错误恢复样本和执行目标偏差都可能影响结果；这些是结合设置与行为提出的解释，本次没有逐项消融，不能写成已证实的唯一原因。

LoRA是方法参考，不能充当只改变轮次的控制组。旧67轨迹实验的数据、优化设置也不同，不用于当前两轮对五轮的归因。

test_normal在上次五轮评测时已经观察过，这次是用户指定轮次的诊断性复验，不是新的盲测。除用户在观察旧五轮结果后预先指定改为两轮外，本次没有根据新两轮模型的test结果再调整超参数、重跑失败题择优或评测第1轮后挑模型。若后续继续研究停止点，应在独立dev上预先固定选择规则，在同一次训练中同时保留第2轮与第5轮模型，并重复训练种子；之后再用未参与选择的数据核验。该建议不代表本次已启动额外训练。

## 9. 文件与复现入口

- 训练目录：`{T}`。
- 两轮最终模型：`{T}/artifacts/model`；第1轮模型：`{T}/artifacts/checkpoints/epoch_1_model`。
- 训练启动与自动衔接评测：训练目录`scripts/run_pipeline.py`，精确训练命令见`command.txt`；复现时应创建新的实验目录，脚本会拒绝覆盖已存在的训练历史。
- 评测命令：本目录`command.txt`，原始逐题交互与官方评分位于`experiments/outputs/{OUTPUT_PLACEHOLDER}`。
- 路径审计：训练目录`metrics/prefix_replay_audit.json`；模型清单与哈希：`metrics/model_inventory.json`、`metrics/final_model_weights.sha256`。
- 本报告的结构化依据：`summary.json`、`metrics/epoch2_rollout_analysis.json`、逐题CSV；[性能图PDF]({E}/metrics/performance_comparison.pdf)与[loss图PDF]({T}/metrics/loss_comparison.pdf)均已保存。
- 最终核验记录：`metrics/final_validation.json`；原始任务证据哈希：`metrics/task_evidence_sha256.json`；目录归档清单：`artifacts.sha256`。

所有新实验产物在workspace-tw内。原始基座、外部envs和旧实验均只读；评测短临时目录和GPU锁位于workspace-tw/tmp下。此报告由固定结果生成并经原始轨迹复核。
'''
    report=report.replace('{OUTPUT_PLACEHOLDER}','simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal')
    (E/'REPORT.md').write_text(report)
    train_report=f'''# train90 全参数SFT两轮训练报告

本次训练已完成 **2轮、1170次更新**，全参数参与更新，共8,190,735,360个参数。以原始Qwen3-8B重新初始化，沿用五轮实验的前1170步学习率路径；warmup88步，计划总跨度2925步。全部实际配置见`config/training_config.json`，精确命令见`command.txt`。

训练耗时约 **{tr['elapsed_seconds']/60:.1f}分钟**（以训练器计时为准），状态SUCCESS；重载生成检查PASS。每轮导出一份BF16推理模型，保留epoch1和最终epoch2，不存储optimizer重启分片。

{losses}

![loss对比]({T}/metrics/loss_comparison.png)

前1170步学习率完全一致，样本长度与监督token序列一致；loss平均绝对差{tr['train_loss_mean_abs_difference']:.6f}、最大绝对差{tr['train_loss_max_abs_difference']:.6f}。这是同设置重训，不是旧第2轮权重的逐位恢复。训练重叠诊断loss为{tr['train_overlap_diagnostic']['loss']:.6f}，不代表独立验证集泛化。

{verdict}

完整评测、控制条件、具体案例和归因边界见[中文评测报告]({E}/REPORT.md)。正式test_normal仅评测epoch2；未据test选择检查点。
'''
    (T/'REPORT.md').write_text(train_report)
    print('Rendered Chinese training and evaluation reports.')
if __name__=='__main__':
    OUTPUT_PLACEHOLDER='{OUTPUT_PLACEHOLDER}'
    main()
