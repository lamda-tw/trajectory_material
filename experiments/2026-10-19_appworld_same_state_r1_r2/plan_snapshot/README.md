# AppWorld Rubric 学习机制计划

**最新状态：2026-10-19，仅更新设计，未开始实验。后续仅用GPU1。**

当前顺序为：先比较本轮全规则 SFT-1358（DropR5）、DropR1、DropR2的同状态动作；再把旧ZeroFail3-1710接入同一套状态与评价方法。三组各三个seed，共9个已有模型，不追加训练。旧22模型方案已被收敛；1350步共同移除训练暂缓。

- [当前计划入口](PLAN.md)
- [完整同状态设计：状态、恢复、评价、解释与预算](SAME_STATE_PLAN.md)
- [怎样判断动作好坏](STATE_JUDGING.md)
- [状态选择与实际覆盖](STATE_SELECTION.md)
- [299个正式状态的逐条ID与替换步号](states_selected.csv)
- [1428个来源状态索引](state_inventory.csv)
- [9个已有模型的路径与哈希](same_state_models.json)
- [CPU审计、校准ID和可选续跑ID](same_state_audit.json)

正式状态包括171个主状态（57题×早中晚各一个）和四类各32个补充状态；共2691次计划单步生成。可选固定策略续跑提前选定16个状态，尚未执行。所有后续模型推理、重放相关本地GPU服务和续跑仅使用GPU1；历史路径中的gpu0只是已有权重位置。

已完成的工作仅是读取已有轨迹、核验来源/权重哈希、冻结状态索引和编写设计。**未运行环境、未生成新动作、未调用评委、未启动训练。** 状态token重建和可重放性要在实验正式开始后验证。

[已完成的三seed消融报告](../../experiments/2026-10-18_appworld_rubric_dimension_ablation/REPORT_THREE_SEEDS.md) · [旧计划归档](archive/PLAN_before_same_state_2026-10-19.md)
