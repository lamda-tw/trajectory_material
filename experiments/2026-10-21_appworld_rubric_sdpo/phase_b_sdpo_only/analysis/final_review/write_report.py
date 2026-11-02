"""Write the final Chinese analysis from audited artifacts; no training."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv
import json

O = Path(__file__).resolve().parent
B = O.parents[1]
R = B.parent
read = lambda p: json.loads(p.read_text())
s = read(O / 'summary.json')
config_audit = read(O / 'configuration_audit.json')
dev_rows = read(O / 'dev_trajectories.json')
batches = list(csv.DictReader((O / 'batches.csv').open()))
m, d = s['mixed'], s['sdpo']


def duration(value):
    value = round(value)
    return f'{value//3600}小时{value%3600//60:02d}分{value%60:02d}秒'


def pct(value):
    return f'{value:.2%}'


def evidence_link(path, label):
    return f'[{label}](../{path})'


lines = ['# B 阶段单 SDPO 对照：最终结果与下一步建议', '',
    f"复核时间：{datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}。所有时间均为北京时间。",
    '本报告基于已完成的训练、Codex 反馈与官方 dev57 结果，仅做 CPU 分析；没有启动新的训练、模型推理或评分。', '',
    '## 1. 明确结论', '',
    '**这次正常完成，但效果不理想。关闭 SFT 后，当前 SDPO 流程仍会退化到重复查询文档，且观察到的最终行为比混合组更严重。下一步值得做匹配的纯 ZeroFail3 SFT 对照，不建议直接扩大或续训现有 SDPO 配方。**', '',
    '- 36/36 个 batch、36 次实际参数更新、180 条训练轨迹、两次各 57 题 dev 评估全部完成；2026-10-25 15:02 正常结束。检查时已无实验训练/采样进程，GPU1 空闲。',
    '- 单 SDPO 两轮整题成功数为 **2/57 → 0/57**；原混合组为 **5/57 → 1/57**。',
    '- 单 SDPO 第二轮 dev57 的 **98.36% 步骤仅查询文档，93.01% 步骤为重复的文档代码**；57/57 道题都出现至少连续 5 次相同文档代码。',
    '- 去掉 SFT 没有解决问题。SFT 不是出现这种退化的必要条件；混合组较好与“SFT 起到一定缓冲作用”相符，但单种子在线对照还不能证明其独立贡献。',
    '- 总耗时约 23小时37分，比原混合的 25小时26分缩短 **7.14%**。训练计算只少约 4 分钟，主要省在 Codex 评分和 dev 评估；不能将提速解释为学习效率提高。', '',
    f'![实验结果、重复文档、loss 与耗时对照]({O / "overview.png"})', '',
    '## 2. 实验是否确实只关闭了 SFT', '',
    '从相同原始 Qwen3-8B 和相同 LoRA 初始化重新开始。每批 5 题，每题 1 条完整轨迹；结束后使用冻结 v7-feedback prompt 逐步评分；合格 FAIL 步骤使用 C2 条件 EMA 教师，沿原回答前缀做 reverse-KL top100+tail 蒸馏。ZeroFail 步骤保留在历史中，但当前步骤 loss 为零。',
    '原 B 的题目顺序、采样 seed、采样参数、agent prompt、学习率 5e-5、5 次 warmup、LoRA r8/alpha16、EMA=0.95、clip=1、每批一次更新均保持相同。训练/agent/sampling/paths 配置逐项相等，schedule、train90、dev57、judge 配置哈希相等。',
    '首批直接复用原初始模型的相同 5 条轨迹和 Codex 结果：48 个 SDPO 步骤完全相同，20 个原 SFT 步骤改为 mask。第二批起各自在线采样，数据会随着模型不同自然分化；独立输出目录与服务端口不属于训练方法改动。', '',
    '| 首批验收 | 原混合 | 单 SDPO |', '|---|---:|---:|',
    '| SFT / SDPO 步数 | 20 / 48 | 0 / 48 |',
    '| SDPO loss | 0.4317961181 | 0.4317961181 |',
    '| SFT 梯度 norm | 0.260103 | 0 |',
    '| SDPO 梯度 norm | 0.499550 | 0.499521 |',
    '| 学生参数变化 norm | 0.033269 | 0.033262 |', '',
    '首批 SDPO 梯度差在预设数值容差内；混合组是从累计梯度中减去 SFT 梯度得到分支 norm。整个单 SDPO 运行的 SFT 样本数、loss、梯度始终为 0，教师始终无梯度。配置核对见 [configuration_audit.json](analysis/final_review/configuration_audit.json)。', '',
    '## 3. dev57 正式结果', '',
    '| 模型 | 轮次 | 整题成功 | TGC | 逐题平均测试通过率 | 平均步骤 |', '|---|---:|---:|---:|---:|---:|']
for arm, label in [('mixed', 'SFT + SDPO'), ('sdpo', '仅 SDPO')]:
    for e in ('1', '2'):
        v = s[arm]['dev'][e]
        lines.append(f"| {label} | {e} | {v['successes']}/57 | {pct(v['task_goal_completion'])} | {pct(v['macro_test_pass_fraction'])} | {v['mean_steps']:.2f} |")
lines += ['',
    '单 SDPO 第 1 轮相对混合少 3 题，TGC 低 5.26 个百分点，平均测试通过率低 9.86 个百分点；第 2 轮少 1 题，平均测试通过率低 1.58 个百分点。',
    '同题比较：第 1 轮两组成功题没有重叠（混合独有 5 题、单 SDPO 独有 2 题）；单 SDPO 测试通过数提高 4 题、降低 14 题、相同 39 题。第 2 轮单 SDPO 没有更多通过检查的题，2 题更少、55 题相同。不能把 5 对 2 解读为混合逐题支配单 SDPO。',
    '单 SDPO 首轮成功题为 `396c5a2_1`、`b119b1f_3`，第二轮全部丢失，没有新增成功题。',
    '**测试通过率不是业务完成百分比。** 部分官方检查会奖励不破坏数据等条件；即使模型只查询文档，也可能通过部分检查。第二轮的 24.80% 不能解释成完成了四分之一任务。', '',
    '历史参考：2026-10-16 选样实验的底座为 1/57、平均测试通过率 43.53%。本次核对其底座模型路径、环境路径、agent 配置、prompt 哈希、dev 题集、temperature=0、seed=100 与 B 主要设置一致。因此不能说“没有任何可比较底座”。但它来自早期运行器和运行批次，本次尚未在 B 运行器下重新执行零更新模型；不把它写成这次新增的严格同期对照。',
    '旧 ZeroFail3 的 10/57、8/57、12/57 来自不同离线数据和训练预算（每次 855 次更新、lr=2e-4），不能代替当前 36 次在线更新的纯 SFT 对照。', '',
    '## 4. 失败集中在反复查询文档', '',
    '统计定义：纯文档步指代码中所有 `apis.*` 调用均属于 `apis.api_docs.*`；重复代码按同轨迹之前已有相同 Python AST 判定，不计注释和格式差异。仅统计本次轨迹动作，不把 prompt 中的演示算进历史；因此这不是完整 R6 rubric 的替代。', '',
    '| dev57 模型 / 轮次 | 总步骤 | 纯文档步骤 | 重复文档代码 | 连续≥5次相同文档的题数 | 上下文超限题数 |',
    '|---|---:|---:|---:|---:|---:|']
for arm in ('mixed', 'sdpo'):
    for e in ('1', '2'):
        v = s[arm]['dev'][e]
        lines.append(f"| {arm} / {e} | {v['counts']['steps']} | {pct(v['docs_only_fraction'])} | {pct(v['repeated_docs_fraction'])} | {v['trajectories_with_5_consecutive_identical_docs']}/57 | {v['terminations'].get('context_limit', 0)}/57 |")
lines += ['',
    '单 SDPO 第二轮 1,344 步中有 1,322 步只查询文档，重复文档代码为 1,250 步；只有 14 步包含非文档 API 调用（这也不保证产生正确业务进展）。57 题全部出现长重复段，45 题因上下文超限结束、8 题达到步数上限、4 题因无 Python 代码结束，0 题调用完成接口结束。', '',
    '| 训练阶段 | 轮次 | 步数 | SDPO 步数 | SFT / mask 步数 | 重复文档代码占比 | 上下文超限轨迹 |', '|---|---:|---:|---:|---:|---:|---:|']
for arm in ('mixed', 'sdpo'):
    for e in ('1', '2'):
        v = s[arm]['train'][e]; c = s[arm]['branches_by_epoch'][e]
        lines.append(f"| {arm} | {e} | {v['counts']['steps']} | {c.get('sdpo',0)} | {c.get('sft',0)} / {c.get('mask',0)} | {pct(v['repeated_docs_fraction'])} | {v['terminations'].get('context_limit',0)}/90 |")
lines += ['',
    '单 SDPO 第二轮 2,437 个 SDPO 步骤中，2,358 个带 R6 FAIL（96.76%）。训练样本越来越集中于重复相关的失败状态，而这些反馈没有阻止最终学生形成文档循环。这里说明训练分布和行为一起恶化，尚未定位每个 token 或每次更新的因果方向。', '',
    '## 5. 三组可以直接复核的案例', '',
    '### A. 两道已经成功的题，第二轮都退回文档循环', '',
    '| dev 任务 | 单 SDPO 第 1 轮 | 单 SDPO 第 2 轮 |', '|---|---|---|']
cases = []
for task in ['396c5a2_1', 'b119b1f_3']:
    a = next(x for x in dev_rows if x['arm']=='sdpo' and x['epoch']==1 and x['task_id']==task)
    z = next(x for x in dev_rows if x['arm']=='sdpo' and x['epoch']==2 and x['task_id']==task)
    assert a['success'] and not z['success'] and z['longest_consecutive_docs']==13
    lines.append(f"| `{task}` | {a['num_passes']}/{a['num_tests']} 检查通过，{a['steps']} 步完成；{evidence_link(a['path'],'轨迹')} | {z['num_passes']}/{z['num_tests']} 通过，连续 13 次相同 Spotify 文档查询后上下文超限；{evidence_link(z['path'],'轨迹')} |")
    cases.append({'task_id':task,'epoch_1':a,'epoch_2':z})
lines += ['', '第二轮重复动作均为：', '',
    '```python', "print(apis.api_docs.show_api_descriptions(app_name='spotify'))", '```', '',
    '这说明丢失的是已在第一轮评估中展示过的整题能力，并且具体表现为停止推进任务、只重复读文档。', '',
    '### B. Codex 明确指出重复，步骤也确实进入了蒸馏', '',
    '训练 `batch_025 / 29caf6f_2`：50 步全部执行同一条 Simple Note API 列表查询，最终达到 50 步上限。第 1 步无 FAIL 被 mask；第 2–50 步共 49 个步骤带 R6 FAIL，进入 SDPO。', '',
    '```python', "print(apis.api_docs.show_api_descriptions(app_name='simple_note'))", '```', '',
    'Codex 的反馈含义是：第 1 步已经给出 API 列表，重复查询没有新信息；应复用列表，读取相关接口（例如 `search_notes`）的具体规范，再推进取回笔记。第 2 步实际 SDPO loss 为 0.424669。',
    '这条轨迹排除了“Codex 根本没识别重复”或“反馈步骤没进入 loss”这两种解释。它不证明该步梯度必然鼓励重复；非零 KL 只能证明存在分布差异，不能证明纠错方向有效。',
    '[原轨迹](runs/sdpo/batch_025/trajectories/b025_29caf6f_2.json)、[Codex 原反馈](runs/sdpo/batch_025/judging/b025_29caf6f_2/judgement.json)、[逐步 loss](runs/sdpo/batch_025/checkpoint/step_metrics.json)。', '',
    '### C. 更少步骤也可能是更早失败', '',
    '`0d8a4ee_1` 第二轮连续 38 次查询相同 Phone API 列表，随后上下文超限；只通过 1/5 项检查。上面的两个 Spotify 案例仅 13 次重复就因大段文档输出填满上下文而结束。步数少和评估更快不能当作效率收益。',
    '[Phone 轨迹](runs/sdpo/epoch_02_dev57/trajectories/0d8a4ee_1.json)。', '',
    '## 6. 为什么感觉这次更快', '',
    '| 耗时口径 | 原混合 | 单 SDPO | 节省 |', '|---|---:|---:|---:|']
for key, label in [('total_wall_seconds','启动至训练和两次评估全部结束'),('training_seconds','训练程序累计计时'),
                   ('judge_wall_seconds','各批 Codex 评分并发墙钟时间之和'),('evaluation_wall_seconds','两次 dev57 墙钟时间之和'),
                   ('other_wall_seconds','采样、服务启动、存盘、调度等剩余时间')]:
    a,z=m['timing'][key],d['timing'][key]
    lines.append(f'| {label} | {duration(a)} | {duration(z)} | {duration(a-z)} |')
lines += ['',
    '总时间缩短 1小时48分55秒（7.14%）。训练程序累计只缩短 3分47秒（0.34%）。首批相同数据的训练确实由 281 秒降到 209 秒，省去 SFT 有实际效果；但整段在线训练没有保持这个同比例提速。',
    '原因可以分开看：', '',
    '1. **Codex 评分更快，是最大的时间差。** 本次 176 次新调用，原混合 184 次；首批复用省去 5 条原始评分调用，其余差异来自重试/格式修复。评分输出 token 由 1,044,263 降为 894,844；输入 token 则由 6,035,771 升为 6,199,483，因此不能简单归因于“输入更短”。请求长度、重复结构、缓存和服务时延都可能影响耗时，现有数据不能精确拆分各自贡献。',
    '2. **dev 变快伴随行为恶化。** 第二轮评估生成 token 由混合的 131,017 降到单 SDPO 的 64,628，平均步骤由 38.30 降到 23.58；上下文超限由 26/57 升到 45/57。模型输出更短的重复查询，大段文档占满上下文后较早结束。',
    '3. **SDPO 的长上下文计算仍占主要成本。** 两轮 SDPO 步数仅从 4,300 降至 4,122；教师实际处理的输入 token 总量约 5,745 万 → 5,769 万，几乎没有降低。去掉 SFT 后，长历史的教师 forward 与学生 forward/backward 仍保留，不能按输出 token 或 SFT 步数直接估计耗时。', '',
    '计时定义：总时长使用最初 launch 到 COMPLETE，原混合不使用后来交接监督进程的启动时间；训练使用每批 metrics.seconds；评分取每批最早实际请求开始到最后完成，不能把并发请求耗时简单求和；评估起点取资源日志中保存的阶段开始时间；剩余项是总时长扣除以上三项。首批 SDPO 缓存的旧评分时间不计入新实验。这里不是固定数据上的吞吐 benchmark。', '',
    '## 7. 如何归因：已知和仍未知', '',
    '**已知：** 当前单 SDPO 配方独立运行也出现严重文档循环；关闭 SFT 不能修复。两轮平均测试通过率下降、已成功任务退步，以及 dev 的重复行为都支持当前训练过程没有把反馈转化为稳定的任务收益。',
    '**有依据但未证明的解释：** 混合组较好，可能是 ZeroFail3 的正向示例在一定程度上维持了可用行为；重复 FAIL 占据训练数据，也可能使学习越来越集中于同一种失败上下文。',
    '**不能直接断言：** SFT 完全无害；每一条 SDPO 目标都在奖励错误；EMA 是唯一原因；Qwen3-8B 天生不能自蒸馏；原论文 SDPO 对所有任务无效。当前对照保留了反馈选择、长历史、教师 EMA、学习率和聚合方式等多项因素。',
    '本次没有对单 SDPO 最终 EMA 教师重新做自由纠错或固定前缀概率诊断，因此不能把“本轮学生退化”直接写成“本轮已测得教师纠错率下降”。之前 8 个案例是原混合模型的证据，应保留这个来源边界。',
    f"单 SDPO 最后一批 KL 为 {d['technical']['last_sdpo_loss']:.6f}，比首批 {d['technical']['first_sdpo_loss']:.6f} 更低，但终态任务成功率为 0。不同批次输入和教师都在变化，KL 变小可以只是师生在失败模式上更接近，不是任务进展指标。", '',
    '## 8. 下一步：做一次匹配的纯 SFT 对照', '',
    '**建议做，目标是补齐归因，不是扩大超参数搜索。** 当前已经有 mixed 和 SDPO-only；缺少 SFT-only，无法判断 ZeroFail3 在线自采样本身是否稳定，也无法衡量加入 SDPO 相对纯 SFT 的作用。', '',
    '| 项目 | 建议固定的做法 |', '|---|---|',
    '| 初始化 | 相同原始 Qwen3-8B、全新同 seed LoRA，不接续退化 checkpoint |',
    '| 采样与评分 | 相同 train90、顺序、seed、5题/批、1轨迹/题、完整轨迹后 Codex v7 评分 |',
    '| 首批 | 复用相同首批轨迹与评分，只训练原来的 20 个 ZeroFail3 步骤 |',
    '| 选步 | 仅 F=0 且 P≥3 计算原回答 SFT；其他步骤当前 loss 全部 mask |',
    '| 优化 | 保持 lr、warmup、LoRA、步内/步间归一化、clip 和每批一次更新；取消 SDPO 计算 |',
    '| 教师 | 纯 SFT 不需要教师 forward；EMA 即使保留为兼容状态，也不参与目标 |',
    '| 预算与评估 | 两轮、36个更新机会，batch18/36 同一 dev57；无合格步骤的批次跳过更新并记录，不补采样、不填充 |',
    '| 观察指标 | 整题成功、平均检查通过率、重复文档比例、上下文超限、合格 SFT 步数与实际更新次数 |',
    '| 初始参考 | 可用同一 B 运行器顺带复核一次零更新 dev57；已有历史基线作参考，不必为它再训练模型 |', '',
    '不要复用 mixed 或 SDPO 后期的全部轨迹来冒充在线纯 SFT：那些状态由不同模型生成。首批可以严格复用；后续应由纯 SFT 当前模型独立采样。若另做固定数据的梯度对照，应单独命名和解释。', '',
    '预先约定解释：纯 SFT 若稳定且明显优于两种含 SDPO 的组，优先停止当前 SDPO 目标的规模化投入，保留 rubric 选样，并把后续探索转向经过执行验证的修正动作等小实验；纯 SFT 若也退化，则进一步检查在线数据分布、正例质量、步权重和学习率，不能把责任都归给 SDPO；若只有轻微差异或仍在 0–2/57 波动，应报告证据不足，避免继续加轮数追结果。',
    '这是单种子、相互关联的 57 道 dev 题，且 dev 已多次用于探索。一次消融用于决定研究方向，不作为已证明普适优劣的结论。**本次未启动纯 SFT 或其他新训练。**', '',
    '## 9. 完整性与复核文件', '',
    f"已校验两组共 {s['verification']['checkpoint_files']} 个 checkpoint 文件、{s['verification']['datasets']} 个冻结 dataset、{s['verification']['training_trajectories']} 条训练轨迹、{s['verification']['evaluation_trajectories']} 条评估轨迹的 SHA256；两组准备清单累计 {config_audit['prepared_dependency_hashes_verified']} 项文件哈希通过。未发现漏批、漏评估、NaN、教师反传或单 SDPO 混入 SFT。",
    f"单 SDPO 最大 allocated/reserved 显存为 {d['technical']['peak_allocated_gib']:.2f}/{d['technical']['peak_reserved_gib']:.2f} GiB，{d['technical']['clipped_batches']}/36 批触发梯度裁剪；所有 36 批学生参数均实际改变。数值正常不能代替效果验证。", '',
    '- [完整统计与时间分解](analysis/final_review/summary.json)',
    '- [配置和历史基线核对](analysis/final_review/configuration_audit.json)',
    '- [逐批统计](analysis/final_review/batches.csv)、[逐题 dev 行为](analysis/final_review/dev_task_behavior.csv)',
    '- [训练轨迹行为索引](analysis/final_review/training_trajectories.json)、[dev 轨迹行为索引](analysis/final_review/dev_trajectories.json)',
    '- [跨轮成功退步案例](analysis/final_review/cases.json)',
    '- [静态图 PNG](analysis/final_review/overview.png)、[PDF](analysis/final_review/overview.pdf)',
    '- [原自动报告快照](analysis/final_review/automatic_report_snapshot.md)',
    '- CPU 复现：依次执行本目录下 `analysis/final_review/analyze.py`、`plot.py`、`write_report.py`。配置核对结果另存于上述 JSON。原训练源码、配置、checkpoint 均未修改。', '']
(O / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n')
snapshot = O / 'automatic_report_snapshot.md'
if not snapshot.exists(): snapshot.write_text((B / 'REPORT.md').read_text())
(B / 'REPORT.md').write_text('\n'.join(lines))
print(B / 'REPORT.md')
