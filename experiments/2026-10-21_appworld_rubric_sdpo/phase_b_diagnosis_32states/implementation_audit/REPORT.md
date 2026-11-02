# SDPO 论文、官方代码与本地 B 实现核查

日期：2026-10-24。仅源码阅读、已有数据分析与 CPU 小张量检查；新增模型 forward、GPU 任务、训练更新均为 0。原训练代码、配置、checkpoint 和概率数据未改动。

## 结论与对上一份诊断的修正

1. **原 SDPO 就沿学生原回答前缀蒸馏。** 本地这样做不是独有的实现错误；不应把“先生成验证后的新答案再训练”称为恢复原版 SDPO。
2. 原论文实际使用 Qwen3-8B，且依赖模型利用反馈的能力。不能由本次失败得出“8B 天生不能 SDPO”；尚未证明它在我们的长历史 AppWorld 状态、rubric 反馈与原回答前缀条件下足够可靠。
3. 核心 reverse-KL、共享原 response 前缀、学生 top-k、教师 stop-gradient 等与官方对应设置一致，未发现 KL 符号或 response 对齐错误。整体训练方案仍有显著改动，不能称为原论文配置的复现。
4. **此前将 `show_contacts` 两个末尾 token 的正向信号解释成整个错误调用被强化，证据不充分，现予更正。** 教师在更早的 `.phone` 分叉已强烈压制错误路径。重复 Venmo 文档的案例仍有真正动作分叉处的反向信号，但不能据此量化 SDPO 对全部退化的因果贡献。
5. 最初阶段 A 验证的是“自由重答能否修复”；B 需要的是“沿原回答各个分叉，反馈教师是否给出可靠的学习方向”。两者有关，但不能用前者代替后者。这是前期验证缺口。

## 1. 核查来源

- 论文采用 [Reinforcement Learning via Self-Distillation，arXiv v2](https://arxiv.org/html/2601.20802v2)，主要核对 §2、§4.1、§4.6、§7 和附录 E。
- 作者仓库固定到 [7c457fc1b1f636ae794eb0362ba37d4743b06fbc](https://github.com/lasgroup/SDPO/tree/7c457fc1b1f636ae794eb0362ba37d4743b06fbc)，也是原实验计划引用的版本；提交日期 2026-07-01。共保存 13 份源码/配置快照，见 `official/manifest.json` 的 URL 与 SHA256。
- 本地检查 `scripts/b_dataset.py`、`scripts/b_loss.py`、`scripts/b_train_batch.py`、`phase_b/config/run.json` 和实际 C2 模板。
- 证据取自已完成的 32 状态诊断；未生成新轨迹、未增加 Codex 调用。

## 2. 原方法究竟在学什么

学生在原状态 x 生成 y，教师看见额外反馈 f。双方在同一个 y 的历史前缀上预测下一 token，匹配两个分布；教师不需要另生成一份完整答案。论文 §2/表 2 及官方代码都明确这一点。[论文](https://arxiv.org/html/2601.20802v2#S2)

官方 `ray_trainer.py:762` 把反馈 prompt 与原 `responses` 拼接；`dp_actor.py:809` 继续传同一个 response，教师 forward 在 no_grad 中执行，并使用学生选择的 top-k token ID。本地 `b_loss.py:24–27,42–44` 对双方都使用同一个 response，正确截取 next-token 位置。[官方输入构造](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/ppo/ray_trainer.py#L749-L775)、[官方教师 forward](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/workers/actor/dp_actor.py#L808-L846)

这不等于要求学生模仿每一个原 token。反馈教师可以在一个较早分叉降低错误路径概率；在强制越过该分叉之后，又顺着错误路径补完后半段。只检查后半段，可能误判整个监督方向。

C2 不额外引用整份原答案，与“训练仍然 teacher-force 原答案前缀”可以同时成立。论文 §4.6 区分了这两件事，因此不应把加入 C3 的整份原答案引用当作补回原方法必需输入。[论文反馈消融](https://arxiv.org/html/2601.20802v2#S4.SS6)

## 3. 实现与运行设置对照

| 项目 | 作者丰富反馈运行配置/代码 | 本地 B | 判断 |
|---|---|---|---|
| 原回答前缀 | 教师/学生共享原 responses | 同一个 response_ids | 核心一致 |
| 目标 | 运行脚本 alpha=1，即 reverse-KL | reverse-KL | 一致；不能拿通用 YAML 的 alpha=0.5 来判本地错误 |
| 教师梯度 | no_grad | no_grad + detach | 一致 |
| token 选择 | 学生 top-k，同一组 ID 给教师，外加 tail | 同样做法 | 一致 |
| k | 丰富反馈脚本为 20 | 100 | 超参差异；本地历史样本的 top100 已几乎覆盖全 KL |
| tail | 由 top-k 质量补余量，含数值 clamp | 对遗漏 logits 做 logsumexp | 同一数学目标；极端尖锐分布可能有 clamp 数值差异 |
| 正确参考 | 从同题 rollout group 按 reward 找成功解；没有成功解可用反馈 | 每题仅一条，未提供成功修正版 | 重要信息条件差异，不是原方法必须有成功解才能运行 |
| 教师目标验收 | 以是否有 solution/feedback 决定 mask；不逐 token 保证正确 | 按 FAIL + 反馈 usable 路由 | 两者都不保证每个教师目标正确；本地 usable 是反馈可用，不是 Qwen 已纠对 |
| 问题数/采样 | 每批 32 题，每题 8 条 | 每批 5 题，每题 1 条完整 agent 轨迹 | 参考答案机会、独立状态多样性不同 |
| 优化次数 | minibatch 配置为 1 题，worker 乘 rollout.n；遍历 batch 后更新 EMA | 整批累积，一次 optimizer.step 后更新 EMA | 更新频率不同，不应只比较“batch”字面数字 |
| 教师 EMA 更新率 | 丰富反馈脚本 0.01 | 1−0.95=0.05 | 本地每次 EMA 跟随学生比例更高；不能直接等同实际漂移速度快 5 倍 |
| 参数/学习率 | 默认 LoRA rank=0，lr=1e-6 | LoRA rank=8，lr=5e-5 | 不可把两种参数化的学习率倍率直接解释成有效更新倍率 |
| LoRA 教师 | 默认实验为全参数 EMA | 分别平均 LoRA A/B | 合法适配，但平均因子乘积不等于合并权重更新量的精确 EMA，未证实是失败原因 |
| 聚合 | 默认 token-mean | 步内 token mean，分支内 step mean，再 SFT+SDPO | 短动作、长动作与两个分支的相对权重不同 |
| IS 校正 | 有 minibatch/off-policy 与 rollout 校正 | 保存旧 logprob，但 loss 不使用 | 本地同版本整批仅一次更新，批内没有参数陈旧；仍省略推理/训练后端差异校正 |
| SFT/SDPO 路由 | 官方 SDPO loss 路径没有我们这套 ZeroFail3 SFT 分支 | ZeroFail3 SFT + FAIL SDPO | 明确的研究扩展，需要对照，不能从原论文直接保证有效 |
| thinking | user.yaml 为 false | false | 一致，不能把失败归因于遗漏开启 thinking |

运行设置来源：[rich_feedback/run_sdpo.sh](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/experiments/rich_feedback/run_sdpo.sh)、[user.yaml](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/config/user.yaml)、[模型配置](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/config/model/hf_model.yaml)、[actor 配置](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/config/actor/actor.yaml)。

代码依据：[成功示例与 mask](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/ppo/ray_trainer.py#L636-L778)、[loss/IS](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/trainer/ppo/core_algos.py#L1085-L1189)、[EMA](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/workers/actor/dp_actor.py#L132-L153)、[EMA 更新时机](https://github.com/lasgroup/SDPO/blob/7c457fc1b1f636ae794eb0362ba37d4743b06fbc/verl/workers/actor/dp_actor.py#L913-L921)。

官方纯 SDPO 的 loss 分支本身也不要求另加 GRPO loss，尽管 trainer 会构造 advantages。因此不能把本地失败描述为“漏写原论文必需的强化学习 reward loss”。成功 reward 在这里的一项用途是选择正确参考。

## 4. 纯 CPU loss/梯度检查

`check_loss_and_prefix.py` 用 AST 提取官方原函数 `compute_self_distillation_loss`、`agg_loss`，与本地 `bucket_reverse_kl` 对照。没有导入训练 runtime 或实例化模型。设置相同 reverse-KL/top-k/tail、关闭 IS、每次一个 response，从而排除不同聚合策略的影响。

4 个 seed × 3 个 logit 尺度 × k={20,100}，共 24 个案例：

- loss 最大绝对差：3.8147e-6。
- 学生 logit 梯度最大绝对差：8.3819e-7。
- 所有结果有限；GPU 禁用。

差异与两种 tail 数值计算方式相符，不支持 KL 方向写反。该检查覆盖数学核，不等价于复现作者整个训练系统。此前历史 24 条真实 loss 的复算仍保留。

## 5. 完整动作检查：必须修正 phone 案例

这些数字直接读取原诊断的历史 student/teacher 概率，没有重新运行模型。完整代码 token 见 `complete_code_prefix_audit.json`。

### phone.show_contacts：更早位置已有正确压制

`R1_b025_29caf6f_3_s01`，原代码 `print(apis.phone.show_contacts())`。

| 位置 | 历史学生概率 | 历史 C2 教师概率 | 独立 logits 局部方向 |
|---|---:|---:|---|
| `.phone` | 81.7572% | 约 0.0058% | 强烈降低该错误路径 |
| `.show` | 95.2379% | 99.9565% | 提高该 token |
| `_contacts` | 76.8744% | 90.4612% | 提高该 token |

给定代码之前的原叙述，整段原代码的教师/学生条件概率比约为 **8.80e-5**。各代码位置独立 logits 下降时原 token logprob 导数之和约 **−0.505**；原回答所有位置之和约 **−0.359**。这不是模型实际参数更新，但足以推翻“只凭方法名后两 token 就断言整个错误调用被鼓励”的说法。

正确解释是：教师在前面的路口已经说不要走 phone 这条路；我们强制走过这个路口后，它又顺着补完方法名。这在 on-policy 蒸馏中并不矛盾。**此前报告和回答对这个案例的因果解释过强。**

### 重复 Venmo 文档：真实动作分叉仍有反向信号

`R6_b014_60d0b5b_1_s17`，应该读 `create_transaction` 的新规范，却重复 `show_api_descriptions`。

在决定 `show_api_descriptions` 的 `_des` 位置，历史学生概率 **26.80%**，历史 C2 教师 **73.03%**。此前代码前缀的 token 都接近确定，未出现 phone 案例那样更早的强压制；代码独立 logits 导数和约 **+0.571**，完整原回答约 **+1.589**。整段原代码的教师/学生条件概率比约 **2.73**。

初始和最终教师自由重答可以选择正确的新规范，沿旧叙述继续预测却支持重复查询。因此“自由生成能修复，不代表原前缀目标可靠”的证据依然成立。但这仍不等于已测出共享模型参数更新后错误动作频率上升，或者证明整体 dev 退化由 SDPO 单独造成。

### 重复 Supervisor 文档：代码信号弱，不能忽略叙述也能影响策略

`R6_b018_aa8502b_1_s05`，代码部分教师/学生条件概率比约 **0.99987**，两者近乎一致。此前“99.99975% KL 在代码前”的统计正确。

但必须补充：纠正前面的行动计划也可能改善之后生成的代码，KL 值占比也不是参数梯度占比。只能说本例代码部分缺乏明显纠错差异，不能仅凭这项统计判定整个 SDPO 样本无效。

## 6. 如何理解 Qwen3-8B 能力不足的假设

论文 §4.1/§7 明确讨论模型利用反馈的能力限制，并在默认实验使用 Qwen3-8B。它没有给出 AppWorld 长历史 agent 的结果，agentic 长程评估属于未来方向。[论文](https://arxiv.org/html/2601.20802v2#S4.SS1)、[局限与未来工作](https://arxiv.org/html/2601.20802v2#S7)

我们的证据更支持一个具体版本的假设：**Qwen3-8B 在部分 AppWorld 原错误前缀上，不能稳定把 rubric 反馈转成正确的动作分叉概率。** 不能替换成“它完全不会纠错”：同一组 24 状态自由生成时，初始 C2 有 15 个主要问题得到首步修复，训练后 EMA 有 12 个；均为事后逐例复核，不是完整 rubric 通过率。

可能的影响因素包括长历史、旧行动叙述的约束、需要重选动作或补前提而不只是改参数、只有一条轨迹导致缺少验证过的成功参考，以及后续训练分布与 EMA 漂移。它们是待区分的解释，不是本次已完成因果消融。

## 7. 下一步应如何验证（本次未执行）

1. 检查目标时追踪完整行动的最早有效分叉，不能只盯错误方法名末尾；保留能纠错和不能纠错的反例。
2. 若要检验“模型太弱”，在相同状态/反馈/前缀上比较更强教师，同时检查它自由生成和原前缀概率；更强模型尚未在本次运行。
3. 若要检验“缺少正确参考”，比较原 C2 与加入执行验证过的修正版，并检查同一个原回答前缀。需要保持学生状态不变，避免把两条不同环境状态下的正确动作直接互抄。
4. 若要区分 SFT 与 SDPO 导致的训练退化，需要固定数据/初始权重/教师的短程分支对照，不能只比较两个分支的 loss 数值。
5. 已验证修正版 y+ 的 SFT 仍是一个可行备选，但属于改变学习目标；不应宣称它已被证明优于原 SDPO，也不应说这是修复一个已证实的 KL 实现 bug。

目前最明确的结论：**核心蒸馏机制与作者一致；我们对其中一个反例的解释需要纠正；确有部分条件下教师信号不可靠，而整套 AppWorld 混合方案与作者实验存在多项未分离的差异。**
