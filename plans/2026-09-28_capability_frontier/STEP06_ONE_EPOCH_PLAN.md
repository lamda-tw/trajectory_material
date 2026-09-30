# 第6步重做计划：三个LoRA分支各训练1轮

**状态：第6b步训练及282项核验已完成；后续按新执行指令完成第7b步检查30题，State 17/30、Action 19/30、Mixed 15/30。** 产物见 [第6b步训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md)；执行前的原始计划保存在 [计划快照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/PLAN_SNAPSHOT.md)。

**后续Dev57结果：** Action-1epoch在Dev57上成功31/57（54.4%），测试条件通过215/291（73.88%）。通过既有接受门槛，可在后续第8步使用该候选；本次未启动来源60题刷新。详见 [第7c步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md)。
这次验证一个明确的问题：**现有修复数据每条只学一遍，是否比此前循环凑到8,000监督tokens，更能保住原有成功并带来新增成功？** 1轮是这次预先确定的尝试，不提前声称它一定更好。

第1步与第7步使用相同评测协议，现有四模型结果仍作为有效的同协议比较。本次保持评测设置，不把共同设置当作分支下降的已证实原因，也不把改thinking模式或额外诊断设为本次重训的前置步骤。

## 1. 从哪个模型开始

三个分支都重新从同一个 **Qwen3-8B + train90 LoRA第5轮adapter** 开始：

- Qwen3-8B：`/root/autodl-tmp/models/Qwen3-8B`。
- 原epoch5 adapter：[原adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter)。
- 三支分别建立全新的AdamW优化器；继承模型权重，不继承旧优化器状态。
- 不从上一版CFST-State、CFST-Action或CFST-Mixed接着训练。旧adapter及旧评测结果保留。

## 2. 每个分支具体训练多少

直接复用第5步冻结的三个唯一数据包，不重新修复、不改标签、不增加旧样本或学生续跑后缀。

| 新分支 | 训练数据 | 训练轮数 | 全程训练样本次数 | 全局batch | 更新步数 | 实际监督tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| CFST-State-1epoch | 状态构建12条 | 1 | 12 | 2 | 6 | 1,826 |
| CFST-Action-1epoch | 动作落地8条 | 1 | 8 | 2 | 4 | 1,493 |
| CFST-Mixed-1epoch | 全部20条 | 1 | 20 | 2 | 10 | 3,319 |

**“1轮”就是每条样本在实际参数更新中恰好使用一次。** 例如State有12条，每次更新用2条，因此完整走一遍就是6次更新；不是只更新1次，也不是训练到loss很小才结束。

这些token数量来自第5步已冻结的tokenizer统计，只记录实际训练量，不作为需要补齐的目标。State、Action、Mixed的数据量、更新步数和监督tokens自然不同。输入历史长度也不同，报告另记计算tokens和耗时，不把样本数比例直接当作算力比例。

每条数据仍是“原始历史作为输入、一个教师修复动作作为答案”。loss只计算修复动作，前缀和修复后的学生续跑不参与监督。训练后的无梯度检查不更新权重，不增加训练轮数。

## 3. 这次只改变训练量规则

| 设置 | 新计划 |
| --- | --- |
| 停止条件 | 每条唯一数据训练一次，完成1个epoch后立即停止 |
| 数据重复 | 禁止为凑tokens重复抽样；12/8/20条各只出现一次 |
| 学习率 | 继续用2e-4，本轮不同时降低学习率 |
| 优化器与调度 | AdamW，weight decay=0，恒定学习率，无warmup；与旧第6步相同 |
| LoRA | 继续训练原adapter，r=8、alpha=16、dropout=0 |
| batch | 双卡，每卡1条，梯度累积1次，全局batch=2 |
| 训练精度与窗口 | BF16、SDPA、最大40,960；沿用既有处理方式，不截断样本 |
| 模板和loss | 与旧第6步一致，enable_thinking=False，completion-only loss |
| 随机种子 | 20260928，固定单轮shuffle，三支各自独立初始化 |
| 保存模型 | 每支只以完整1轮结束的adapter作为本次产物，不根据检查题或训练loss挑中间权重 |

保持学习率等设置，是为了先看减少重复学习后的变化。此前建议过的更小学习率、混入旧成功步骤、改推理模式等，本次均不加入。

## 4. 本次已经完成的执行步骤

1. **准备新实验目录。** 已使用总实验目录下的 `step06b_lora_one_epoch/`，与旧第6、7步并列，未覆盖旧结果。
2. **核对起点与数据。** 校验原epoch5 adapter、第5步三份train.jsonl的哈希；确认来源60题、检查30题和Dev57的边界保持原样。
3. **生成只含唯一数据的训练清单。** State 12行、Action 8行、Mixed 20行；单轮内无重复、无遗漏。两卡按不重叠索引划分，当前样本数均能被2整除，不需要补齐或丢弃样本。
4. **修改新的执行入口。** 在新目录复制并适配旧第6步程序，把“循环到8,000监督tokens”改为“唯一数据遍历1轮”；移除预算补齐、token超额统计和三支预算相等检查。不能直接运行旧run_step06.sh，也不能继续使用旧54/44/50条的重复训练清单。旧脚本保留用于复现历史结果。
5. **分别训练三支。** 各自从原epoch5启动，执行6/4/10次更新，分别保存独立adapter。某支失败时保留记录，不通过多训其他分支来补偿。
6. **核验和写报告。** 检查各样本实际进入更新的次数都为1、优化器步数正确、权重正常更新且可重新加载。写明每支loss、样本曝光、监督tokens、输入tokens、耗时和显存。完成本步后停止，不自动执行第7步。

以上步骤现已全部完成：三支各训练一轮，三个adapter已保存并真实重载通过；样本次数、配置、哈希等282项检查通过。底层训练程序沿用旧版，新清单与执行入口不再补齐token预算。训练后已停止，未运行评测。

## 5. 实际产物及验收

```text
experiments/2026-09-28_dynamic_cfst/
  step06_lora_branches/          # 旧版，保留
  step07_check30_evaluation/     # 旧版结果，保留
  step06b_lora_one_epoch/        # 已完成训练与核验
    CFST-state/adapter/
    CFST-Action/adapter/
    CFST-Mixed/adapter/
    README.md
    summary.json
    validation.json
```

各分支同时保存配置、实际样本使用记录和训练报告。验收以**12/8/20次样本使用、6/4/10次参数更新、每条恰好一次、三个可加载adapter**为准，不要求三支loss相同或监督tokens相同。

## 6. 检查30题已执行，结果与后续判断

后续按用户执行指令完成评测，结果见 [第7b步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07b_check30_one_epoch/README.md)。按冻结规则选择Action候选后，后续Dev57已完成并达到31/57，通过接受门槛。下面保留训练前确定的比较规则。

未来进入第7步时，仍用同一份冻结检查30题和原评测协议：temperature=0、seed=100、32,000窗口、单次3,000输出tokens、每题50步、无reasoning parser、官方评分。原epoch5的17/30结果经同样核验后继续复用；只为三个1epoch新分支生成新结果，另存计划中的 `step07b_check30_one_epoch/`。

届时比较两件事：新分支相对原epoch5是否有净收益，以及相对旧版同名分支是否减少了退步。旧版State/Action/Mixed分别为13/14/14题成功。仍按新增成功、退步和净改善评判，不用训练loss选模型。

- 若1轮版本优于旧版，但仍不超过原模型：说明减少训练量有改善迹象，尚不能接受模型更新。
- 若某支相对原模型有正净收益：按原候选规则，再决定进入Dev57接受检查。
- 若仍无正净收益：如实保留结果，不自动加训、换学习率或继续采教师样本。

这次是在看过旧结果后明确提出的一次训练方案修订；同一检查30题上的后续比较属于开发实验，不宣称是全新独立测试。Dev57仍不提供训练答案、不用于选超参数。

**本次比较的是不同数据包各学一遍的结果，不是相同总训练量下的分类消融。** 不能仅凭专项组与Mixed的差异证明能力划分合理；先完成这个更简单的训练尝试。
