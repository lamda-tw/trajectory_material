# 原始模型与 SFT LoRA：双起点的静态 rubric 对照

## 为什么值得做

原始 Qwen3-8B 已采完 train90 × 6：39/540 条成功，70/90 题六次全失败。结果奖励只有 20 个组有方差。这确实可能使只看最终成功的 GRPO 信号稀疏。

用户指定的 LoRA 有独立历史 dev57 记录：23/57 成功，TGC 40.4%，SGC 21.1%。出处为 [历史 dev summary](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/summary.json)，其 adapter SHA256 与本次副本一致。它支持“用更强起点再试一次”的可行性判断，不代替本次统一协议的 dev 基线。旧评测虽然多项预算相同，运行器和协议细节仍需完整对齐，因此本次两个起点都重新跑 dev57。

更强起点可能增加成功/失败混合组，也可能让部分题六次全成功。我们要测的是**奖励是否提供有用的相对信号**，而不是预设 LoRA 一定更适合 RL。原始模型全失败的组也可能在规则遵循上有差异；反过来，judge 造成的噪声差异不能当成有效信号。

可以把这一轮的研究问题写成：

> 静态规则反馈在不同初始策略水平下，能覆盖哪些最终结果奖励无法区分的行为？已有 SFT 能否帮助模型把规则反馈转化为自主执行能力的进一步提升？

这只是一个可验证的起点对照；两种初始化本身不足以构成新方法。以后再引入 self-improvement、步骤归因、修复和训练方式分配，需要在这个基线上证明额外价值。

## 两个起点怎么固定

| 项目 | Raw 起点 | LoRA 起点 |
| --- | --- | --- |
| 策略 | 原始 Qwen3-8B | 同一基座 + train90 / epoch5 adapter |
| train 采样 | 已完成 90 × 6 | 准备完成，尚未开始 90 × 6 |
| 任务、采样 seed | 已冻结 | 逐题逐 sample 完全配对 |
| prompt / parser / 解码 / 步数 / 上下文 | 原采样配置 | 完全相同 |
| 运行位置 | 原实验目录、端口 8128 | 新实验目录、端口 8129 |
| GPU | 0 | 0，分时运行 |
| 本次新增 Codex 求解示范 | 0 | 0；但初始 adapter 已含历史 Codex SFT |
| 评价 | 完整官方 dev57 | 同一完整官方 dev57 |

不同策略即使 seed 相同也不会得到相同轨迹；这里的配对用于控制任务和采样配置。并发调度等也可能影响逐 token 的复现，不宣称位级确定性。

初始 adapter 源：
/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter

冻结副本：本目录 preparation/initial_adapter，仅复制 adapter_config.json 和 adapter_model.safetensors。权重 SHA256：

    c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938

它在同一 train90 上用 90 条 Codex 成功轨迹、1170 个决策样本训练过 5 轮。因此 train90 重采样属于训练内诊断；“没有这轮新增求解示范”不等于“没有教师知识”。不能把两个起点的绝对成绩差解释为 rubric 效果，也不能声称总监督数据预算相同。

## 先采样，再评分，最后才训练

1. **先只采 LoRA 的 540 条。** 不改变原始 540 条；不筛失败、不为了凑成功补采某一边。每条仍保存真实采样 token IDs、旧策略 logprobs、动作、反馈和官方终态诊断。首条先做 prompt/response token 重建以及与 raw 初始 prompt 配对检查，通过后再并发。
2. **之后两边用相同 21 条规则评分。** 同一版本 judge、提示和 schema；一条完整轨迹判 21 个 PASS/FAIL/NA，不是每步 21 项。judge 看不到初始化名称、policy_id、官方成功标签、测试答案或私有解法。完整保留全部判定和证据，失败调用不填 NA。当前未调用 judge。
3. **检查信号与证据。** 先确认两边评分确实可用，再确定一次 GRPO 阶段的预算和评测点。不能把“分数有方差”直接当成“模型能学好”。
4. **每个起点独立更新、独立继续采样。** Raw 轨迹不能拿去当 LoRA 起点的 on-policy 数据，反之亦然。旧 logprob 必须来自生成该条轨迹的策略。每轮约定的 PPO/GRPO 更新阶段结束后，下一轮从新策略重采；不把初始 540 条无限复用为在线 RL。
5. **dev57 无提示复评。** 原始起点、LoRA 起点和各自训练后 checkpoint 都使用同一协议，不提供规则提示、错误定位或修复帮助；dev 数据不回流训练。

评分沿用冻结的 DRACO 静态流程：同一题的六条为一组，各规则若全组没有 FAIL 则在本组 reward 中移除；保留项中 reward = 10 × (P − F) / (P + F)，NA 不进分母，分母为零则 reward=0。组内采用样本标准差与 epsilon=1e-6 算优势；reward 全同则优势为零。不加入官方成功奖励。规则文件、judge.py、common.py 均从 raw 分支复制，准备时核对内容一致。

若给两边全部打分：共 1080 条轨迹、180 个组、22680 个规则判定；通常每条轨迹一次 judge 请求，实际调用次数还要加上重试。评分可缓存，不能为了获得更“满意”的答案反复挑分。建议两分支在同一个评分阶段交错安排请求并记录时间、用量，降低服务随时间变化的影响。

## 怎么比较才有解释力

最小方案需要四个 dev 结果：

| 起点 | 不做本轮 RL | 静态 rubric GRPO 后 |
| --- | --- | --- |
| Raw | R0 | R1 |
| 现有 SFT LoRA | L0 | L1 |

先报 R1−R0、L1−L0，以及各自的绝对成功题数。L1−R1 是整体系统表现差，不是 rubric 独立贡献。若资源允许，两个起点都增加“官方 0/1 outcome GRPO”，形成两个起点 × 三种状态（未更新 / outcome RL / rubric RL），才能比较 rubric 相对于稀疏结果反馈的增益。

统一的 dev 协议：完整官方 57 题、temperature=0、seed=100、相同初始 prompt、不开 thinking、相同 parser、50 步、32000 上下文、3000 单步生成上限；官方 TGC 为主，SGC 和逐题成功/失败变化为辅。提前固定训练预算和最终 checkpoint，不为不同分支挑各自最高的 dev 点。当前不使用 test；dev 上的选型结果不能包装成未参与开发的测试结果。

训练前后除了 dev 成功率，同时报告：

- train 六次成功数的 0–6 直方图，特别是全失败、混合、全成功组比例。
- outcome 与 rubric 各自零优势组比例、组内 reward 方差、过滤后规则数和 NA 比例；单独看全失败组是否有可信 rubric 信号。
- 抽查相同数量、按固定种子选取的 PASS/FAIL/NA 与证据；发现错误先统一修正规则适配或提示并重新冻结，不能只对一边调分。
- 步数、token、环境调用、judge 成本、GPU 时间、采样组数、实际优化器更新数；两边使用相同新增训练预算。
- 精确代码序列去重率仅作粗略采样多样性诊断，不把文本不同当作策略语义不同。

已准备的 compare_collections.py 只计算 train 采样统计；缺少 LoRA 数据会明确显示 NOT_COLLECTED，缺少 rubric 判定显示未评分，绝不填成“0 分”。

## 真正做 GRPO 前必须正确接入的部分

**这一阶段未实现或运行 LoRA 续训入口。** 原目录的旧 train/all 原型默认新建 rank16 adapter，并将禁用 adapter 的基座作为 reference。直接套用到本分支会改变实验含义。

后续实现应遵守以下固定约定：

- Raw 分支新建 rank8、alpha16 的零增量 LoRA；LoRA 分支加载本次 rank8、alpha16 初始权重继续训练。七个注入模块、可训练参数量、优化器和新增预算对齐。原始采样时没有 adapter；新建零增量 LoRA 与该初始策略函数相同，所以不用重采原始 540 条。
- 两边都新建本轮优化器，不恢复历史 SFT 的 optimizer state。输入 adapter 副本只读，所有新 checkpoint 写新路径。
- Raw 分支冻结 reference 为原始基座。LoRA 分支冻结 reference 为“基座 + 本次初始 SFT adapter”，不能通过 disable_adapter 得到后者。
- 推荐使用两份独立 adapter：policy 可训练，reference 从初始权重加载且冻结，评分 reference 时显式选择后者并 no_grad。确认两份参数不共享存储，reference 永不更新，且不混入 optimizer。处理 gradient checkpointing 时，要确保 backward 重算使用正确的 policy adapter。
- 训练前先用小模型检查 reference 不变、policy 参数确实更新、保存重载一致，以及启动时 rollout logprob 与训练 forward 的可接受一致性。此处只是实现约定，不能将离线采样检查解释成 GRPO 已验证。
- vLLM 只加载当前 policy 的单个 adapter；采样服务退出、显存释放后再在 GPU 0 上训练。不是在旧 adapter 上随意叠加另一个 LoRA，更不覆盖历史 adapter。
- 原 config 里的 10 次更新 / 每次 2 题仍是旧原型占位。看完两份采样和评分诊断，再固定两边共同的新增训练预算，记录无优势组处理及实际有效更新数。

当前的可执行下一步就是 LoRA 采样。全量验收后停止，供用户决定下一步评分；不会自动启动上述训练或 dev。
