# 当前要做：两份轨迹统一静态 rubric 评分

更新：2026-10-09。**下一步先评分和检查信号，再进入 GRPO。** 当前对齐 DRACO 的 static 基线，不加步骤 credit、动态规则或自修复。

两边的完整 train90 × 6 都已经采完并验收：原始 Qwen3-8B 成功 39/540，现有 SFT LoRA 成功 186/540。它们是 train 采样统计，不是 dev 成绩；本轮还没有评分、训练或新 dev 评测。实际记录见 [实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。

## 接下来怎么做

1. **先试评分 24 条。** 固定选同样两道 train 题，两种初始化各取每题的全部六条。复用已有轨迹，检查调用、21 项输出、判分依据和分组计算。这个小检查不替代后面的全量实验。
2. **再评分全部 1,080 条。** 同一 judge、同一提示、同一套 21 条规则；每条完整轨迹判一次，得到 21 个 PASS/FAIL/NA。规则文件固定，不让 judge 临时改规则。
3. **看分数有没有可信的区别。** 同题六条组成一个组，两种初始化分别算。特别看原始模型的 70 个全失败组、LoRA 的 23 个全失败组，rubric 是否能区分它们，以及依据是否站得住。
4. **评分可用后再接 GRPO。** 补齐 LoRA 续训和冻结参考策略，统一跑训练前的完整 dev57，再做训练与完整 dev57 复评。旧训练原型还不能直接用于这个双起点对照。

分数照 DRACO：组内没有任何 FAIL 的规则不参与本组奖励；保留项中，`reward = 10 × (PASS−FAIL)/(PASS+FAIL)`。NA 不进分母，分母为零则记 0。六条分数完全相同，就没有 GRPO 相对优势。[官方流程](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/training/docs/REWARD_PIPELINE.md)

## 文档放哪里

- [EXPERIMENT_PLAN.md](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)：评分细节、训练准备、对照与统一 dev 协议。
- [RESEARCH_IDEA.md](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/RESEARCH_IDEA.md)：后续自修复、SFT/OPD 和多轮自改进的研究设想。
- experiments 中保留实际运行所需的代码与配置、来源快照、结果和报告；总体规划集中在这里。

本次只更新计划和整理文档，没有启动评分或训练。
