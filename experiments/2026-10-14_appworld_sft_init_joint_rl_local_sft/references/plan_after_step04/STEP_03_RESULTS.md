# 第 3 步：完整局部 SFT 数据构建与验收

完成时间：2026-10-14T15:10:26.079308+08:00（北京时间）。本次仅构建与验收数据；没有启动 SFT/RL、模型评测或 GPU 模型加载。

## 可用于训练的产物

- [data_manifest.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/data_manifest.json)：2,623 个样本的源身份、编码文件、token 边界及哈希。
- [sft_samples.jsonl](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/sft_samples.jsonl)：完整历史 messages 和原始 target_response，便于检查。
- [encoded/](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/encoded)：逐样本 NPZ，含 input_ids、labels、attention_mask、loss_mask。
- [sft_dataset.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/sft_dataset.py)：LocalSFTDataset 与右侧 padding 的 CompletionCollator，可供后续 trainer 读取；不加载模型。
- [token_mask.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/checks/token_mask.json)：独立全量验收。
- [length_statistics.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/length_statistics.json)：长度与监督量统计。

| 项目 | 实际值 |
| --- | ---: |
| 样本 / 来源轨迹 / 任务 | 2,623 / 431 / 88 |
| 单遍目标 token：T_SFT | 205,238 |
| 5 遍累计目标 token | 1,026,190 |
| 单遍完整输入加目标 token 总和 | 22,230,093 |
| 最长完整输入加目标 | 31,814 |
| 目标长度范围 | 25—443 |
| 超过 32,000 token 的样本 | 0 |
| 截断 / 去重 / 新增质量排除 | 0 / 0 / 0 |

205,238 是目标监督量；历史虽然不计 loss，仍参与前向计算，因此不能用目标 token 数代表全部训练成本。

## 构建方法

根据原始 initial_messages 和先前真实 history_assistant_text/observation 重建上下文；保留原始采集协议中的 assistant 尾随换行和 user Output 包装。历史里原有 parser 修复仍保留，因为它正是下一步实际见过的输入；当前目标则是未修复的完整原始 text，不取代为执行代码。

使用本地 Qwen3 tokenizer 与 `enable_thinking=False` 的原始模板，逐一比较重建 prompt_ids 与采样记录。目标直接采用原始 response_ids，并确认去掉特殊 token 后的解码文本与原始 text 完全一致。未重新拼接目标文本编码来猜边界，未补写 EOS；全部 2,623 条原始响应本来就有 EOS，EOS 属于监督目标。

NPZ 中 labels 未预先移位：整个 prompt 为 -100，目标区等于原始 token IDs。模型的标准 causal loss 或等价 loss 实现负责移位一次。右侧 padding 的 labels=-100、attention_mask=0；loader 返回 int64 张量供模型读取。目标说明文字、多个代码块、尾随空白、F/U 步骤与结束调用全部保留。

## 验收证据

所有 2,623 个身份与正式选样清单逐一一致；431 个源文件哈希重验通过。独立脚本重新从源轨迹构建当前步之前的历史，核对输入、目标、边界及所有落盘 token/mask。当前动作后的观察、后续步骤、官方成败和裁判标签均未加到训练输入。

loader 全量读取通过；最短/最长样本共同 padding 后未多出监督 token。小型 CPU 合成 logits 的 completion-only CE 与逐目标 token 计算完全相等（两者为 14.91015816），非监督预测位置梯度为零。另人工查看首次动作、R1=F、含 U、多代码块结束动作及最长样本，未重评标签或改写目标。

CPU 构建初次运行发现每个 token 重复查询词表大小的开销，缓存不变词表大小后重建；先前 156 个部分编码文件保存在独立归档目录，不列入 manifest、不供训练读取。该优化没有改变选样或编码语义。

数据层验收不代替真实模型 loss/梯度和单卡显存 smoke。GPU1 限制持续有效，GPU0 未用于本次任务。

## 学习率与参数更新的明确约定

续训已有 train90 epoch5 LoRA 的副本，冻结原 Qwen3 基座，不新增并联 adapter，也不先合并旧 adapter 再建新 adapter。文件头包含 504 个 A/B 张量、21,823,488 个参数；后续 loader 必须验证仅这些 LoRA 参数可训练。

联合运行创建新的 optimizer/scheduler，从已有 LoRA 权重开始；不沿用已结束历史 SFT 的 optimizer 状态。运行内部跨轮保留 optimizer/scheduler 状态。RL 与局部 SFT 共用同一组 LoRA 和一个 optimizer，没有两个独立学习率；lambda 控制 SFT 梯度相对系数，候选仍为 1。

候选全局调度：前 4 次联合更新 warmup 至 5e-6，此后连续余弦衰减到第 75 次的 5e-7；每轮边界不重启。按当前每轮 15 次更新预算，各轮末学习率约为 4.739e-6、3.668e-6、2.208e-6、9.777e-7、5e-7。scheduler 具体 off-by-one 行为必须在训练器实现中验证。实际总更新数若变化，先重算并冻结整条调度。

[历史五轮报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md) 记录固定学习率 2e-4，第 1/3/5 轮分别 13/57、10/57、8/57。其起点、样本、更新次数和训练目标与本次不同，不能断言本次只要降低学习率就不会退化。五轮只是候选预算，不保证越训越好；第 1/3/5 轮评测照实记录，以预定终点评价，不看结果后反复调阈值或挑最好一轮。

下一步：实现并验证联合 trainer（执行手册第 4 步），之后才编排消费计划、单 GPU1 工程试跑、冻结配置、建立基线并正式训练。
