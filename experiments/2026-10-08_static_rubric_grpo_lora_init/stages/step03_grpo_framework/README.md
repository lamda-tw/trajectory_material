# DRACO 静态评分 → reward → GRPO

采用官方 21 条静态规则和评分正文，仅保留本地交互协议适配。每条完整轨迹获得 PASS/FAIL/NA；同题六条中至少一次 FAIL 的规则进入 reward：`10*(P-F)/(P+F)`，NA 不计分母，空分母为 0。优势使用组内样本标准差加 1e-6。无动态规则、步骤 credit 或混合 outcome 奖励。

首次工程更新固定为 afc0fce_1 的完整六条初始轨迹，选择不读取评分或成功标签。一个 PPO epoch、一次 AdamW step，lr=5e-5、KL=0.01、clip=0.2；先按轨迹内生成 token 平均，再按轨迹平均。工具观察和 prompt 不计损失。零优势组保留并应用 KL。

policy 从冻结 train90/epoch5 SFT LoRA 起步；reference 单独加载同一初始 SFT 模型，参数不共享且全冻结。第 2 次及以后必须从上一次 checkpoint 重新采样，不得切分旧 540 条冒充后续 on-policy 数据。每次 checkpoint 保存 optimizer、来源和 batch hash，并验证保存重载一致。

本次用户明确允许 GPU 1。原采样配置、轨迹、adapter、评分正文和历史结果均保留。正式比较前仍需冻结训练预算并完成对应初始模型的 dev57；一次更新不代表效果结论。

## 命令

从 /root/autodl-tmp/workspace-tw 运行，入口为 experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/run.py。

- `python <入口> prepare`：准备/校验，不加载模型。
- `python <入口> cycle --branch rubric --updates 1 --execute`：评分、计算奖励、真实一次更新；可恢复。
- `python <入口> cycle --branch rubric --updates 2 --execute`：从新 checkpoint 重新采样并继续第 2 次更新。
- `python <入口> score --all-train --execute`：对初始 540 条轨迹评分，不训练。
- `python <入口> evaluate --checkpoint-update 0 --execute`：初始模型完整 dev57。
- `python <入口> evaluate --checkpoint-update 1 --execute`：第 1 次更新完整 dev57。
- `--branch outcome` 提供独立最终结果奖励对照。
- 不带 `--execute` 只准备，不推理、不调用 judge、不训练。

运行产物在 experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1。manifest.json 固定配置/代码；batch.json 记录逐轨迹分数、优势、SHA256 和 policy ID；checkpoint/manifest.json 记录真实训练指标。目录内 preflight_8b.json 是独立真实 8B 前向预检。

离线测试：`.conda-training/bin/python experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/test_framework.py`。直接提取官方归档 reward 函数，对 829 组六条矩阵比对；另测 clipping、生成 token 对齐、梯度、reference 冻结、保存重载、缺样本/过期策略/dev 拒绝，以及传输恢复事件。

评分器仅接受最终完成的单个禁工具回合；独立 judge_transport.py 接纳已确认的传输重连文案。保留最早有效响应和全部请求日志，不因不满意重抽评分。官方来源：IBM/draco commit cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b。这是 Qwen3-8B 静态基线框架，不是完整 DRACO 或论文数值复现。
