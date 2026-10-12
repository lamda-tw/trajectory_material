# 为什么一次静态 rubric GRPO 更新不保证改进

本文件分析已完成的固定 train90 更新，不新增训练、不修改任何 reward；官方成功标签只用于事后诊断。test_normal 完整性能及配对失败见 [REPORT.md](REPORT.md)。

## 先给出能确认的判断

目前可以确认：训练实现确实完成了一次合法的、非零的 AdamW 更新；静态奖励整体与任务成功相关，但会强化部分失败轨迹、抑制部分成功轨迹；本次只有轨迹级 advantage，错误步骤不会被单独排除；第一次更新时 reference KL 的梯度为零。

这些事实能解释“为何有可能倒退”，不能单独证明每项导致了多少分下降。没有较小学习率、不同 credit 或多次在线更新的受控实验，就不能把原因确定为“学习率太大”“只训练一遍”或“judge 不可靠”。Dev 为 23/57 → 16/57；本次完整 test 为 51/168 → 37/168，TGC 下降 8.3 个百分点。Test 的 SGC 均为 16.1%，全部条件累计通过数为 598 → 594。21 道退化题都出现提交动作但未满足全部条件，其中 16 题仅差一个条件；没有一道退化题因上下文中断。这更具体地指向任务语义和约束满足的变化，不能据此叫作全面能力崩溃。

## 1. “一遍数据”与“一次更新”不是一回事

本次 90×6=540 条、9,886 个模型步骤、1,785,724 个生成 token 都参加了计算，但其梯度直到最后才合并，optimizer.step 只执行了一次。并不是 90 次更新，也不是分成多个 mini-batch 逐次更新一遍。

轨迹来自当前更新的初始 SFT LoRA，直到全部梯度累计完之前模型不变。因此，缓存轨迹这一事实并不使本次首次更新变成陈旧行为策略上的多轮离线训练。没有发生“更新五遍却一直沿用最初 old policy”的问题；本次缺少的是更新后的再次采样、反馈与修正。

DRACO 的静态无 credit 设置也使用反复采样/评分/更新：其 Qwen3.6-27B 训练 100 steps / 20 epochs，每个 rollout step 为 16 题×6；论文还报告 Qwen2.5-32B 的 75 steps / 15 epochs。PPO epoch=1 指每个新批次只用一遍，不是整个训练只更新一次。[原文 §4.1.2、§4.1.3、附录 D](https://arxiv.org/html/2609.04094v1#A4)

| 项目 | 论文主配置 | 本次实际 |
|---|---|---|
| 策略 | Qwen3.6-27B | Qwen3-8B + 既有 SFT LoRA |
| 采样批次 | 每步 16×6，后续重新采样 | 初始模型一次采 90×6 |
| 训练长度 | 100 steps / 20 epochs | 一个全批次 optimizer step |
| LoRA rank/alpha | 16/32 | 8/16 |
| Loss reduction | token-mean | 每条轨迹 token 平均，再对 540 条平均 |
| LR / weight decay | 5e-5 / 0.01 | 5e-5 / 0 |
| Judge | GPT-5.4 | GPT-5.6-sol，高推理强度 |

这不是论文的严格数值复现。尤其不能仅因同为 5e-5 就假设两种模型、批次和参数化有相同的更新强度。论文静态无 credit 基线本身也有提升，所以“没有 dynamic 或 step credit”不能被当作静态方法必然无效的证据。[原文表 2](https://arxiv.org/html/2609.04094v1#S4.T2)

## 2. 奖励大体有效，但和官方成功并不等价

本次完整 540 条的事后统计如下，全部从冻结 batch、原始 judgement 和已有官方终态读出，没有重打分。

| 检查 | 结果 |
|---|---:|
| 官方成功 | 186/540 |
| Reward 与成功的 Pearson 相关 | 0.731 |
| Reward 与官方条件通过比例的 Spearman 相关 | 0.775 |
| 混合组内成功/失败配对的 reward 顺序 | 正确 398/420；反向 19；相等 3 |
| 正优势 | 280 条，其中成功 158、失败 122 |
| 负优势 | 256 条，其中成功 27、失败 229 |
| 六条全失败 / 全成功 / 混合的题目组 | 23 / 4 / 63 |

**这些数字不支持“奖励完全错误”的说法。** 122 条被强化的失败轨迹中，67 条来自六条全失败的组，55 条来自混合组。GRPO 本来就会强化同组中相对较好的轨迹，即使它尚未完成任务；这种部分信用可能有用，不能直接把 122 条都算成错标。

同样，27 条被抑制的成功轨迹中，10 条来自全成功组、17 条来自混合组。全成功组仍可优化过程规范，但该信号与官方 TGC 没有对应变化。正优势总和的约 38.0% 分给官方失败轨迹；这只是 advantage 的标量质量比例，**不是实际梯度范数比例，也不是 38% 的更新有害**。

完整明细：[540 条 reward 与官方结果](metrics/training_reward_vs_outcome.csv) · [分组与逐规则统计](metrics/training_reward_diagnostics.json)。

### 直接证据 A：错误已经被识别，仍然得到很高的总 reward

`e7a10f8_3`、sample=4（第 5 次尝试）：用户问最长 Spotify 歌单的分钟数，模型把所有歌单里的歌曲时长加到一起，提交总时长，而非先分别求和再取 max。官方仅通过 1/2 条件。

Judge 并未漏看此错误：它在 selection logic 项明确给 FAIL，指出把整个库的时长当成最长歌单时长。但筛选后有 9 PASS、1 FAIL、3 NA，reward=(9−1)/(9+1)×10=8，组内 advantage=+0.549。任务关键错误被多个通用过程 PASS 稀释；错误聚合与提交答案的 token 都会被强化。这是具体的代理目标与最终成功不一致，**即使单项判定正确也会发生**。

[轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories/e7a10f8_3__04.json) · [逐条判定](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/judgements/e7a10f8_3__04/judgement.json)

### 直接证据 B：筛掉一致通过的规则后，只剩过程差异

`c901732_1`、sample=0：播放指定专辑里听得最少的歌，官方 6/6 通过。六条都成功，过滤后只剩 `Protects secret values` 一条；打印密码的三条 reward=-10，其余三条 +10。该成功轨迹 advantage=-0.913，整条轨迹的正确选歌与播放动作也被抑制。

这不说明保护凭据不合理，而是说明当前优化目标还包含官方 TGC 不直接衡量的过程要求；轨迹级统一权重不能把“应纠正的输出方式”和“应保留的正确业务动作”分开。

[轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories/c901732_1__00.json) · [逐条判定](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/judgements/c901732_1__00/judgement.json)

`cf6abd2_1`、sample=2 也成功通过 8/8 条件，但过滤后仅剩凭据保护与操作核验两项，均 FAIL，reward=-10、advantage=-1.633。Judge 对核验强度的要求比本次官方终态成功更严格。合理的过程批评不等同于应该降低整套正确解题行为的概率。

[轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories/cf6abd2_1__02.json) · [逐条判定](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/judgements/cf6abd2_1__02/judgement.json)

## 3. 本次近似一次带正负权重的 token 学习

当 new≈old 时，忽略很小的推理框架数值差异，本次 loss 的梯度近似为：

\[
g\approx-\frac{1}{540}\sum_i\frac{A_i}{N_i}\sum_t\nabla_\theta\log\pi_\theta(y_{i,t}\mid h_{i,t}).
\]

因此，每个 token 对目标梯度的贡献都使用相同的轨迹优势符号：正优势向提高其概率的方向贡献，负优势则相反。共享参数还会叠加其他 token 和轨迹的梯度，所以这不是对更新后每个 token 概率变化的逐项保证。这包括解释文字、查文档、正确步骤、错误步骤和提交；不是“只增强正确动作”。静态无 credit 基线就是这个结构，当前行为与实现目标一致。[GRPO 原始形式](https://arxiv.org/html/2402.03300v2#S4)

组内优势已中心化，所以起点 ratio≈1 时，正负项会使标量 policy loss 接近 0；但它们对应不同 token 的梯度，不会因此彼此抵消为零。当前 loss≈0.000112 不能用来判断是否学到了东西，也不表示梯度计算失效。

我们按每条轨迹的 token 数取平均，使每条轨迹的总权重不直接随长度增加；论文表中的 token-mean 是另一个 reduction 口径。两者不能简单当作仅差一个全局常数，因为不同轨迹长度不同。当前正优势轨迹平均约 1,944 tokens，其余轨迹约 4,775 tokens；reward 与长度的 Spearman 相关为 −0.629。短轨迹可能因为少犯错或更快完成而得高分，也可能较早提交；相关性本身不能证明模型学会了“偷懒”。

小幅改变一个早期 token 或 API 参数，就可能使后续观察和所有后续动作不同。最终 greedy 任务成功是离散的、需要多个条件同时满足；它不随这一局部代理目标的梯度保证单调上升。

## 4. KL=0 与 PPO clip 没有保证这一步足够保守

本次使用独立且冻结的初始 SFT reference。唯一一次 backward 时 policy 仍然是该初始模型，所以 `delta=logp_ref−logp_new=0`。采用的 k3 项为 `exp(delta)−delta−1`，在该点不仅值是 0，对 logp_new 的导数 `1−exp(delta)` 也是 0。因此 beta=0.01 在这一次 backward 上没有提供朝 reference 拉回的梯度。

同理，clip 只影响计算当前 loss 时的 importance ratio，不会在 optimizer.step 后自动把模型投影回一个概率区间。当前更新前 ratio_mean≈1.000019，clip_fraction≈0.0040，old/new logprob 的平均绝对差≈0.00869，来自 vLLM 采样与 Transformers 计算的数值差异。它们不等于更新后的 ratio 或 KL；本次没有保存全量更新后 KL，不能把日志里的 0 当作“没有漂移”。

随后增加了固定训练样本上的只读测量：按预先保存的 task/sample 哈希顺序选择 12 道训练题，取每条的首个与最后一个合格动作，最多保留 128 个 response tokens、8192 个 prompt tokens，共 24 个动作、1701 个预测位置。在同一冻结基座上切换初始/更新后 adapter，以完全相同的 token 前缀计算全词表分布。

| 检查 | 固定训练 probe 结果 |
|---|---:|
| 精确 KL(initial‖updated)，均值 | 0.002729 nats |
| 反向 KL(updated‖initial)，均值 | 0.002515 nats |
| greedy 下一 token 不同 | 15/1701 = 0.88% |
| 原记录 token 的概率比超出 [0.8,1.2] | 15/1701 = 0.88% |
| 按动作平均的 advantage × logprob 变化 | +0.001223 |

平均分布变化较小，个别位置不同；这些位置处在真实多步生成里时可能引发后续分叉。该结果确认了更新后分布不再等于初始分布，但**不支持仅凭参数变化就断言“步长明显过大”**。最后一行只描述小样本的局部代理方向，并不等于训练 reward、完整 PPO loss 或真实任务成功率提高。这里是固定旧轨迹前缀上的条件分布，不是更新后重新 rollout 所访问状态上的 KL，也不是完整 train90 的无偏估计。

[预先固定的样本计划](config/post_update_probe_plan.json) · [完整指标与逐位置数据](metrics/post_update_probe.json) · [只读测量脚本](scripts_snapshot/probe_post_update.py)。没有 backward、optimizer.step 或重新评分；模型文件 SHA 在测量前后相同。首次计算完成后，NumPy 对布尔数组求分位数时报错；修正为浮点统计后按同一计划完成只读复算，失败与恢复日志均保留。这不涉及正式 test 的重采样。

这也是一次新批次、单 PPO epoch 的正常特性，而不是 KL 代码失效。若要控制首次更新，应实际测更新后的分布变化，或在训练/Dev 上比较更小步长；单把 beta 从 0.01 调大，对起点处这个零梯度项没有作用。

## 5. 第一轮 AdamW 的实际变化已核验

两个 worker 的梯度按全局归一化后求和，合并范数 0.030232，小于裁剪阈值 1，故梯度裁剪未触发。新的 AdamW 状态从零开始，weight_decay=0。偏差校正后，第一步每个坐标满足：

\[
\Delta\theta_j\approx-\eta\frac{g_j}{|g_j|+\epsilon},\quad\eta=5\times10^{-5},\epsilon=10^{-8}.
\]

直接用保存的两个梯度文件重构这一步，与最终 adapter 的最大误差仅 **3.73e-9**。因此没有发现平均/求和错误、做了多次 step 或保存了另一个模型的证据。

- 21,823,488 个 LoRA 参数中 99.987% 实际发生变化。
- 平均绝对变化 4.84e-5；94.28% 坐标的变化至少为 0.9×学习率。
- 参数变化 L2 / 原 adapter 参数 L2 = 0.397%。
- 有效 LoRA 修正 `(alpha/r)BA` 的变化 L2 / 原 LoRA 修正 L2 = 0.545%。这两个比例都不是相对全部 8B 基座权重，也不是 policy KL。

累积 540 条并取平均并不会让这一步的每坐标幅度自动除以 540：当 |g| 大于 epsilon 时，Adam 首步对梯度尺度近似不敏感。于是“一次更新、loss 近零、梯度范数不大”不能被当成安全步长的充分证据。但这些参数变化比例也不足以证明学习率确实过大；仍需要较小步长的配对 Dev 实验。

来源：[更新重构与逐 tensor 指标](metrics/update_diagnostics.json) · [CPU 重构脚本](scripts_snapshot/analyze_update.py)。

## 6. 还有哪些限制，哪些说法目前不能成立

- **训练/评测条件差异**：训练 rollout 显式 enable_thinking=false，历史 dev/test 评测不覆盖该开关。首个训练 prompt token 已验证对应 false，默认渲染的后缀不同。本次按用户要求保持历史评测协议，前后 SFT/GRPO 的评测条件相同，因此这不是“给 GRPO 单独换了测试设置”。它可能影响训练改动向评测条件的迁移，需要同时在两个 checkpoint 上做开关配对消融才能确认。
- **没有观察到整体少做步骤**：test 的模型请求数为 3,429 → 3,521，输出 tokens 为 335,660 → 340,495。训练 reward 与轨迹长度负相关，不足以解释为更新后整体变得更短、更懒。
- **有限探索**：每题六条、只有初始策略的一批轨迹；23 题六条全失败，GRPO 只能在现有尝试里比较相对好坏。这为学习方向提供有限证据，增加 epoch 但不重新采样不会新增成功解。
- **不能直接叫灾难性遗忘**：目前没有通用能力前后测，只有该任务域的结果变化。
- **不能直接叫 reward hacking**：已看到代理奖励和任务目标冲突，但没有更新后 rollout 的同口径 rubric 分数，尚未证明模型提高 rubric 分同时主动损害成功率。
- **不能将所有差距归因于 judge**：总体相关性和组内排序较好；单项打分语义错误、汇总方式和轨迹 credit 是三个不同问题。
- **不能承诺多训几遍一定恢复**：相同静态分数重复优化也可能继续放大奖励与目标的偏差；本次没有进行这个实验。
- **不能排除所有执行因素**：模板、版本、权重与实际请求都会审计；历史对照未同期重跑，双卡分片改变了请求调度。固定 seed 的 GPU 推理也不应被当成跨调度的逐 bit 保证。

## 7. 建议的最小验证顺序（本次未执行新训练）

| 优先级 | 实验 | 能回答什么 |
|---|---|---|
| 1 | 从同一初始 LoRA、同一冻结梯度/数据，用 1e-5 或 5e-6 的单步对照；只在 Dev 比较，扩大训练 probe 的更新后 KL/ratio 检查 | 当前这一步是否过强；保存的梯度可用于同方向步长诊断，避免重新打分 |
| 2 | 在本次 12 题固定 probe 基础上扩大 token logprob/代理目标检查，另做初始模型同期 Dev 复评 | 是否沿预定代理目标改善，以及历史运行差异有多大 |
| 3 | 若小步长有效，再按较小任务 batch 做多次在线采样—评分—更新，保存中间模型 | 是否能把第一步的局部调整积累为稳定能力提升 |
| 4 | 保持 outcome-blind 范围，比较静态判据的关键错误表达、汇总与局部 credit；先用 train 例子核验 | 能否避免已知关键错误 token 被通用 PASS 淹没；不把官方标签直接偷换成训练 reward |
| 5 | 对初始与更新后模型共同做 thinking 开关配对 Dev 评测 | 条件差异是否影响迁移，不能只给其中一个模型换协议 |

较小步长优先是一项待验证的实验选择，不是已确认的修复。已有训练数据、梯度和 checkpoint 保持不变；这些诊断和测试反馈没有回写到训练。
