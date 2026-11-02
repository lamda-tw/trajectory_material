# B 阶段单 SDPO 对照

本实验根据用户指令“因为现在 GPU1 空闲，可以跑一个单 SDPO 对照”启动，用于检验原混合实验去掉 SFT 后的训练表现。与 `../phase_b` 隔离保存，沿用原 B 的两轮 train90、每轮 dev57 验证和 C2 教师。

## 固定设置

- 从原始 Qwen3-8B 与相同 LoRA 初始化开始，不接续已经退化的混合模型。
- 每批 5 题，每题一条完整轨迹；轨迹结束后统一交给 Codex 逐步评分并生成 FAIL 反馈。
- FAIL 步骤的准入条件、C2 反馈 prompt、原回答前缀上的 SDPO、归一化与权重沿用原 B；所有 ZeroFail 步骤仅保留为上下文，训练 loss 为零。
- LoRA r=8、alpha=16；AdamW 最大学习率 5e-5，前 5 次非空更新 warmup，EMA=0.95，梯度裁剪 1；共 36 个批次更新机会。其他参数见 `config/run.json`。
- 首批复用原 B 初始策略的 5 条轨迹及 Codex 评分，第二批起由单 SDPO 当前学生独立在线采样。首批所有 SDPO 样本的 prompt、response、teacher prompt 与原实验逐项相等，区别仅为 SFT 步骤被 mask。缓存来源和哈希见 `config/first_batch_reuse.json`。
- 每轮结束（batch18、36）以无反馈学生评估同一 dev57，temperature=0、seed=100，不根据 dev 结果调参。
- 仅使用物理 GPU1，按 UUID 锁定；使用共享 GPU1 互斥锁，独立端口 8193。

## 验收与后台执行

首批需确认 SDPO loss 和梯度有限且与原混合首批对应数值在容差内，SFT 样本数、loss、梯度均为零，教师无梯度、学生参数确实更新。通过后监督进程继续第二批直至两轮完成，并自动执行两次评估。

监督进程记录每 30 秒资源心跳；已有完整检查点通过哈希校验后可续跑。传输或资源中断有限次重试，确定性错误或数值异常停止并写入状态；不会将失败样本替换成其他任务。

```bash
CUDA_VISIBLE_DEVICES='' USE_TORCH=1 USE_TF=0 /root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/scripts/b_supervise.py --execute
```

启动授权保存在 `config/start_authorization.json` 与 `config/execution_gate.json`。代码及配置校验保存在 `config/preparation_manifest.json`。

## 查看进度与结果

- `STATUS.json`、`runs/sdpo/heartbeat.json`：当前阶段、资源和训练进度。
- `REPORT.md`：逐批更新的报告，最终包含两轮 dev57 与原混合结果比较。
- `analysis/preflight.json`、`analysis/first_batch_acceptance.json`：CPU 输入一致性检查、GPU 首批验收。
- `analysis/training_metrics.csv`：每批 loss、梯度、显存和更新次数。
- `analysis/mixed_vs_sdpo_dev57.csv`：两组同题评估结果。
- `runs/sdpo/supervisor.log`：监督主日志；各批次 `training.log` 为训练日志。

## 结论边界

这是在线单种子对照。首批输入严格匹配；第二批起模型和采样轨迹会自然分化。结果能帮助判断原混合流程是否从 SFT 获益，以及仅 SDPO 是否仍会出现反复查询文档，不能单凭这个对照断言某个 loss 是全部退化的唯一原因。
