from pathlib import Path
from datetime import datetime
import json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dur(s):return f'{round(s)//3600}小时{round(s)%3600//60}分{round(s)%60}秒'
s=read('analysis/summary.json');cfg=read('config/training.json');t=s['training'];res=s['results'];cmp=s['comparisons']['rubric_epoch1_old_recipe'];state=read('STATUS.json')
verdict='高于' if cmp['delta_tasks']>0 else '低于' if cmp['delta_tasks']<0 else '等于'
result_rows='\n'.join(f"| {name} | {res[key]['successes']}/57 | {100*res[key]['TGC']:.2f}% | {origin} |" for key,name,origin in [('base','原始Qwen3-8B','复用上一实验同协议base验证'),('rubric_epoch1_old_recipe','rubric原一轮配置','历史结果'),('uniform_epoch1_old_recipe','uniform原一轮配置','历史结果；无五轮对应组'),('rubric_epoch1_new_recipe','本次配方第1轮','本次连续训练检查点'),('rubric_epoch3','本次配方第3轮','本次连续训练检查点'),('rubric_epoch5','本次配方第5轮','本次原定最终检查点')])
epoch_rows='\n'.join(f"| {e['epoch']} | {e['updates']} | {e['samples']} | {e['supervised_tokens']:,} | {e['mean_step_loss']:.6f} | {e['token_weighted_loss']:.6f} |" for e in s['epochs'])
gpu_rows='\n'.join(f"| {d['rank']} | {d['device']} | {d['peak_allocated_gib']:.2f} | {d['peak_reserved_gib']:.2f} |" for d in t['distributed_ranks'])
rows='\n'.join(f"| 对比 {a} | {len(c['new_successes'])} | {len(c['regressions'])} | {c['delta_tasks']:+d} | {100*c['delta_TGC']:+.2f} pp |" for a,c in s['comparisons'].items())
within1=s['comparisons']['rubric_epoch1_new_recipe'];within3=s['comparisons']['rubric_epoch3'];diag=s['diagnostics'];d5=diag['rubric_epoch5']
termination_rows='\n'.join(f"| {name} | {diag[key]['termination_counts'].get('no_python_code',0)} | {diag[key]['termination_counts'].get('step_limit',0)} | {diag[key]['termination_counts'].get('context_limit',0)} | {diag[key]['termination_counts'].get('completion_api',0)} | {diag[key]['completion_api_but_failed']} |" for key,name in [('base','原始base'),('rubric_epoch1_new_recipe','本次第1轮'),('rubric_epoch3','本次第3轮'),('rubric_epoch5','本次第5轮')])
n1=res['rubric_epoch1_new_recipe']['successes'];n3=res['rubric_epoch3']['successes'];n5=res['rubric_epoch5']['successes']
if n5<n1:
 checkpoint_conclusion=f'在同一训练配置内，第5轮成功{n5}/57，低于第1轮的{n1}/57；第3轮为{n3}/57。训练loss持续下降，任务成功率却没有随轮数单调改善。因此本次结果不支持继续增加相同目标的训练轮数就会更好。该现象与对局部目标过度拟合、行为分布偏移等解释相容，但单次DEV结果不能区分这些机制，也不能排除任务级波动。'
elif n5==n1:
 checkpoint_conclusion=f'同一配置的第1轮和第5轮均为{n5}/57，第3轮为{n3}/57。loss下降没有转化为最终成功题数的净增加；仍需逐题检查获益和退化，不能据此声称多训四轮更有效。'
else:
 checkpoint_conclusion=f'同一配置内，第5轮{n5}/57，高于第1轮{n1}/57，第3轮为{n3}/57。这说明当前配方下增加训练轮数有正向观察，但只有一次训练和57题DEV，不能把差异直接视为稳定收益；仍须检查新增成功和退化。'
report=f'''# Rubric 原动作：重新进行五轮双卡 LoRA SFT / DEV57

本次从原始Qwen3-8B重新初始化LoRA，使用原先同一批rubric目标，按用户指定的历史SFT配方完成全部5轮，再运行DEV57。**本次第1、3、5轮的官方成功分别为 {res['rubric_epoch1_new_recipe']['successes']}/57、{res['rubric_epoch3']['successes']}/57、{res['rubric_epoch5']['successes']}/57；第5轮成功率为 {100*res['rubric_epoch5']['TGC']:.2f}%。** 没有续训旧一轮adapter，没有训练新的uniform组，没有外部模型重新评分或替换动作。

**1．DEV57结果**

| 模型 | 成功题数 | 官方TGC | 来源 |
| --- | ---: | ---: | --- |
{result_rows}

本次第1、3、5轮检查点均在五轮全部完成后分别验证，轮次在看到本次DEV结果前由用户指定。它们属于同一连续训练过程，适合观察轮数变化；不要把旧实验一轮与本次配方一轮混为一谈。

本次第5轮相对本次第1轮新增成功{len(within1['new_successes'])}题、退化{len(within1['regressions'])}题，净变化{within1['delta_tasks']:+d}题；相对第3轮新增成功{len(within3['new_successes'])}题、退化{len(within3['regressions'])}题，净变化{within3['delta_tasks']:+d}题。这里训练配方和选中目标相同，只观察同一连续训练的不同检查点。

相对历史rubric一轮，新成功{len(cmp['new_successes'])}题、退化{len(cmp['regressions'])}题，净变化{cmp['delta_tasks']:+d}题。新增题：`{', '.join(cmp['new_successes']) or '无'}`；退化题：`{', '.join(cmp['regressions']) or '无'}`。

| 本次五轮相对其他检查点或历史模型 | 新成功 | 退化 | 净题数 | TGC变化 |
| --- | ---: | ---: | ---: | ---: |
{rows}

逐题官方结果见 [task_comparison.csv]({R/'analysis/task_comparison.csv'})；配对统计见 [summary.json]({R/'analysis/summary.json'})。同一训练seed、57题且有任务家族相关性，不能把小差距当作稳定收益。与旧实验的比较是历史同推理协议的描述性比较，不是只改变epoch数的消融；本次1/3/5轮比较保持同一配方和连续优化器状态。仍未提供rubric五轮对uniform五轮的公平结论。

**终止行为与成功覆盖**

| 模型 | 无可执行代码终止 | 达50步上限 | 达上下文上限 | 调用完成API | 调用完成但官方失败 |
| --- | ---: | ---: | ---: | ---: | ---: |
{termination_rows}

第5轮的{res['rubric_epoch5']['successes']}个成功任务分布在{d5['families_with_any_success']}/{d5['task_families']}个任务家族，其中{d5['families_with_all_success']}个家族的3个变体全部成功。成功仍集中在少数家族，不代表普遍解决长任务。相比base，无代码终止从{diag['base']['termination_counts'].get('no_python_code',0)}题降到{d5['termination_counts'].get('no_python_code',0)}题；但第5轮仍有{d5['completion_api_but_failed']}题调用完成API后未通过官方测试，另有{d5['termination_counts'].get('step_limit',0)+d5['termination_counts'].get('context_limit',0)}题耗尽步骤或上下文。以上是日志统计，不等同于对具体失败原因的逐步因果判定。调用完成API也不能当作成功标签。详见 [终止方式与任务家族统计]({R/'analysis/termination_and_family_diagnostics.json'})。

**少量轨迹核对（第5轮；用于解释现象，不是重新打分）**

- [6bdbc26_1]({R/'evaluation/rubric/trajectories/6bdbc26_1.json'})：查询Spotify当前歌曲对应艺术家的关注者数。第8步打印当前歌曲，第9步依据artist_id查询艺术家，第10步提交follower_count，官方2/2通过；这个家族三个变体全部成功。
- [23cf851_1]({R/'evaluation/rubric/trajectories/23cf851_1.json'})：汇总本月发出的Venmo交易点赞数。第7步按方向、时间范围分页查询并累加like_count，第8步提交11，官方2/2通过；这个家族也三个变体全部成功。两例说明本次确实出现了可完成的查询/聚合流程。
- [b119b1f_2]({R/'evaluation/rubric/trajectories/b119b1f_2.json'})：切歌直到指定艺术家。第5步把artist当作单字段导致KeyError，第6步查schema，第7步改为遍历artists后执行成功，第8步直接调用完成API；末两步没有重新读取当前播放状态，官方仅4/6通过。这表明修复执行错误与满足任务终态仍有差距；仅凭这段日志不把缺少复查认定为唯一根因。
- [50e1ac9_1]({R/'evaluation/rubric/trajectories/50e1ac9_1.json'})：跨歌曲、专辑、歌单库找播放最多的R&B歌曲。第47—50步重复同一段构造rnb_songs的代码，每次都执行成功，最终达到50步上限，官方1/2通过。局部执行无异常并不能保证持续推进任务。

这些例子与“基础执行形式有所改善，但长链条覆盖、状态核验和退出循环仍有问题”的判断相容。它们是有限的事后检查，不证明哪个rubric维度造成了收益，也没有据此改动本次训练或重新评测。

**2．如何落实“重新训练五轮”**

- 从`/root/autodl-tmp/models/Qwen3-8B`加载基座，重新建立LoRA；初始全部LoRA B矩阵为零、两卡初始化张量哈希一致，未加载旧adapter或旧optimizer。
- 选中目标和`selected_end`与上一实验逐一一致：2,440个步骤，覆盖90题；2,352条完整响应与88条配额末尾部分响应保持原mask。
- 每轮每个目标恰好出现一次；两个rank分片不重叠，没有DDP补齐或drop。每轮196,608个监督token，5轮983,040个监督token，总12,200次样本呈现、6,100次更新。
- 只监督已有assistant响应，保留原始行动前历史；当前及未来反馈不进入输入。继续沿用v5评分和原筛选规则，未重新打分或改变目标动作。
- 五轮连续保留AdamW状态；每25步可恢复，每轮保存adapter。训练期间不运行DEV；全部五轮结束后评测用户指定的第1、3、5轮，全部保留，不按成绩改训练。

输入和目标验证见 [FIVE_EPOCH_VALIDATION.json]({R/'data/FIVE_EPOCH_VALIDATION.json'})，初始化证据见 [INITIALIZATION.json]({R/'training/rubric/INITIALIZATION.json'})。

**3．与历史SFT配方和上一轮的区别**

| 项目 | 上一轮rubric实验 | 本次五轮 | 2026-09-21历史五轮 |
| --- | --- | --- | --- |
| 目标来源 | 原Qwen3轨迹的rubric步骤 | 同一批、同监督区间 | 90条Codex成功轨迹的1,170个决策 |
| LoRA r / alpha | 16 / 32 | 8 / 16 | 8 / 16 |
| 学习率 | 5e-5，warmup+cosine | 固定2e-4 | 固定2e-4 |
| 全局batch | 每更新4,096监督token | 每更新2个步骤 | 每更新2个步骤 |
| loss归一化 | 更新内token平均 | 两个步骤各自token平均后取平均 | 同本次 |
| 更新次数 | 48 | 6,100 | 2,925 |
| epoch | 1 | 5 | 5 |
| seed | 20261013 | 20260921 | 20260921 |
| 优化器 / 裁剪 | AdamW / norm1 | AdamW / 无裁剪 | AdamW / 无裁剪 |
| 训练长度上限 | 32,000 | 40,960，无实际新增输入 | 40,960 |

本次遵照“仿照之前LoRA SFT做法”使用历史核心训练参数；不是简单把上一轮48次更新改成240次。学习率、更新频率和归一化都发生变化，所以改善或退化不能全部归因于多训四轮。当前任务使用的是学生自己的局部动作，并未拿历史Codex轨迹混入训练；原轨迹消息格式和历史教师数据整理方式也不同。

采用bf16、SDPA、梯度检查点，注入q/k/v/o/gate/up/down，21,823,488个可训练参数。为节省显存，仅计算监督区间的词表logits；两卡小模型loss/梯度已与标准completion-only CE逐项对照，最长两条实际样本也通过真实双卡更新检查。probe独立、权重丢弃，正式训练重新初始化。

**4．五轮拟合与双卡证据**

| epoch | 更新 | 样本呈现 | 监督tokens | 样本平均CE | token加权CE |
| --- | ---: | ---: | ---: | ---: | ---: |
{epoch_rows}

![五轮loss]({R/'analysis/loss_5epochs.png'})

浅蓝线是每次同步优化器更新的原始loss，红线是只使用当前及此前49次更新的滑动平均，虚线标记每轮边界。横轴为全局优化器更新次数，不是环境行动步骤。图表参考用户指定的历史五轮loss图，保留完整波动，不截断尖峰。另存 [PDF](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/analysis/loss_5epochs.pdf) 和 [逐步CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/analysis/loss_history.csv)。

曲线只描述训练数据拟合，不能替代DEV任务能力。样本平均CE是本次优化目标；token加权CE用于补充诊断，不能混为同一个指标。

| rank | GPU | 峰值allocated GiB | 峰值reserved GiB |
| --- | --- | ---: | ---: |
{gpu_rows}

每轮结束都核对两卡adapter张量哈希一致，全部通过。资源采样位于logs/gpu_usage.csv（每10秒一条）。

**5．验证协议与用时**

DEV57使用与上一实验相同的agent prompt、关闭thinking、temperature0、seed100、50步、32,000上下文、每步最多3,000生成token、3个隔离worker；不截断历史，使用官方终态测试。每题只保留完整有效的官方评测，基础设施异常不作为失败填零。模型从最终保存的adapter由vLLM重新加载。

正式五轮训练墙钟：**{dur(t['training_wall_seconds'])}**。第5轮DEV57墙钟：**{dur(res['rubric_epoch5']['elapsed_current_invocation_seconds'])}**；第1轮为{dur(res['rubric_epoch1_new_recipe']['elapsed_current_invocation_seconds'])}，第3轮为{dur(res['rubric_epoch3']['elapsed_current_invocation_seconds'])}。第1、3轮使用独立GPU并行验证，阶段用时不能直接相加作为总墙钟。最长样本probe和后续分析不计入正式训练时间。全部阶段的开始/结束及中断重试见 [TIMING.json]({R/'TIMING.json'})。

**6．结论边界**

本次补充了历史SFT配方下第1、3、5轮的实际验证证据，避免只用旧配方一轮结果评价整个方向。{checkpoint_conclusion}

所有指定检查点都完整报告并保留；不根据DEV成绩回改本次训练，也不把DEV中成绩最高的一轮当作已经获得独立测试验证的最佳方案。具体结果只适用于此数据选择和训练设置，不能把训练loss、v5标签合理性、最终任务成功率相互替代，也不能据此证明某个rubric维度具有因果贡献。

原始数据、v5标签及既有实验保持不变；本次没有更新prompt。后续决策应结合完整DEV逐题变化；若需要回答“rubric是否比uniform更有效”，还需要相同训练配方、数据预算及第1/3/5轮检查点的uniform对照，本次按用户要求未启动该组。

- [第1轮adapter]({R/'training/rubric/epoch_01_adapter'})
- [第3轮adapter]({R/'training/rubric/epoch_03_adapter'})
- [第5轮adapter]({R/'training/rubric/epoch_05_adapter'})
- [检查点哈希]({R/'CHECKPOINTS_135.json'})
- [最终adapter]({R/'training/rubric/adapter'})
- [冻结方案]({R/'PLAN.md'})
- [训练配置]({R/'config/training.json'})
- [结果与检查]({R/'analysis/summary.json'})
- [完整DEV轨迹]({R/'evaluation/rubric/trajectories'})
- [执行冻结清单]({R/'EXECUTION_MANIFEST.json'})
'''
(R/'REPORT.md').write_text(report);print(R/'REPORT.md')
