# B 阶段纯 ZeroFail3 SFT 对照

用户授权：使用 GPU1，其他设置保持一致；首批检查 loss 和梯度，通过后继续两轮，每轮在 dev57 评估，最后与 mixed、SDPO-only 比较。

唯一训练方法变化是屏蔽全部 FAIL 步骤的 SDPO loss，只训练原有 F=0 且 P≥3 的 SFT 步骤。U 不额外排除；历史步骤保留；不改变评分 prompt、模型起点、采样设置、数据顺序、学习率或 loss 归一化。

每批 5 题，每题一条完整轨迹。轨迹结束后统一使用原 Codex v7-feedback 评分。首批复用原 mixed 初始模型的 5 条轨迹和评分，只学习相同 20 个 ZeroFail3 步骤；第二批起独立在线采样。首批 SFT loss/梯度需与原 mixed 首批 SFT 分支匹配，SDPO loss/梯度需为零。

共 36 个更新机会，空批次不补采样，不更新 optimizer/EMA/warmup。batch18、36 分别执行完整 dev57。保留教师/EMA 检查点结构便于沿用原训练器，但纯 SFT 不调用教师 forward、不使用教师作为目标。

只使用物理 GPU1，UUID 为 `GPU-35170b76-56ce-240a-19c0-0c092a3e8501`。共用工作区 GPU1 互斥锁，服务端口 8194，所有输出在本目录；两组历史实验只读。

监督进程每 30 秒记录心跳，校验已提交检查点后可续跑，有限次重试传输/资源中断；确定性或数值错误停止并保留日志，不替换失败任务。首批通过后自动继续训练和两次评估。

```bash
CUDA_VISIBLE_DEVICES='' USE_TORCH=1 USE_TF=0 /root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/scripts/b_supervise.py --execute
```

三组比较持续写入 `REPORT.md`、`analysis/b_report.json` 和 `analysis/three_way_dev57.csv`。`STATUS.json` 与 `runs/sft/heartbeat.json` 为运行状态；`analysis/first_batch_acceptance.json` 为首批验收；`runs/sft/supervisor.log` 为主日志。

最终报告包含两轮成功题数、平均检查通过率、重复文档行为、空批次、实际更新次数、loss/梯度/显存和逐题得失。三组是单种子在线对照，第二批起轨迹自然分化，不能解释为固定相同数据上的纯梯度因果实验。
