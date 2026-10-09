# LoRA 起点对照：已准备，尚未开始

增加一个起点：Qwen3-8B + 现有 train90 / epoch5 LoRA。原始模型的 540 条轨迹保留在原目录。本次只做了文件准备和离线检查，没有采样、Codex 评分、训练或 dev 评测。

## 下一步只做这一件事

**完整 train90，每题重新采 6 条，共 540 条。** 使用 GPU 0、独立端口 8129；先检查第一条真实轨迹，再最多 6 路并发。结束后自动验收 token、统计两分支的 train 采样差异，并追加主目录报告。

任务、六个 seed、prompt、parser、temperature=1、上下文 32000、最多 50 步、每步最多 3000 token，均与已完成的原始模型分支一致。不开 thinking。每条重置 AppWorld；成功、失败、无代码及预算耗尽的轨迹全部保留。

现在可以安全运行离线检查：

```bash
cd /root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init
python preflight.py --write
python step01_collect.py
python compare_collections.py
```

**等用户明确开始后**，采样入口是：

```bash
python -u step01_collect.py --execute
```

这个入口只采样，不会自动进入评分或 GRPO。中断后用同一命令恢复；配置或权重发生变化会拒绝混用旧结果。端口被占用或 GPU 0 空闲显存不足 80 GiB 时会报错，不会处理其他进程。

## 准备了什么

- 已复制并校验初始 adapter；rank 8、alpha 16，504 个张量的形状检查通过。保留原训练目录，服务使用本目录的冻结副本。
- 复制原分支的采样实现、21 条静态规则和 judge 接口；adapter 目录只放权重与配置，统一使用原始分支的基座 tokenizer。
- 540 个配对任务已写入 [planned_jobs.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/planned_jobs.json)。这些是任务计划，尚无新轨迹。
- 首条及全量轨迹验收、断点恢复、独立日志、两分支统计、主报告追加均已接好。
- [离线检查结果](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/readiness.json)。12 项隔离与调用回归测试通过；没有启动 vLLM，所以真实 LoRA 服务兼容性要在授权启动时验证。

实际数据将写到本目录的 runs/step01_train90_rollouts/。主报告继续使用 [RUBRIC_GRPO_EXPERIMENT_REPORT.md](/root/autodl-tmp/workspace-tw/RUBRIC_GRPO_EXPERIMENT_REPORT.md)，LoRA 有单独的进度区，不覆盖原始模型结果。

## 采完后怎么看

先看两边各有多少题属于“六次全失败 / 有成功也有失败 / 六次全成功”，再按同一静态规则评分，看 rubric 奖励是否有可靠的组内差异。全失败不一定没有 rubric 信号；更强的模型也可能出现全成功、奖励饱和。

之后比较各自训练前后的完整 dev57。具体对照表、历史结果和 LoRA 续训注意事项见 [COMPARISON.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/COMPARISON.md)。

当前准备范围是**第二个起点的采样、验收和后续对照协议**。GRPO 预算尚未确定，本目录没有训练入口；config 中继承的 updates=10 / groups_per_update=2 是旧原型占位，不能视为新实验预算。后续需按 COMPARISON.md 接入 adapter 续训与冻结 reference，不能直接调用旧目录的 train/all。
