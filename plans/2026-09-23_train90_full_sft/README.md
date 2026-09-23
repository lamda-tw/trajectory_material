# AppWorld train90 全参数 SFT 准备方案

状态：**方案已完成，尚未启动训练；训练器改造与 GPU 验证待执行。**

用户要求先保存工作区，再准备训练，收到明确训练指令后才能开始。本轮没有加载 Qwen3 模型、执行 forward/backward/update、启动 torchrun 或 GPU smoke，也没有创建新的实验目录。

准备前的工作区基线：`ff977cc71f7a8b697d935507bcee6b9a44e34480`。方案提交已保留在 `main`，后续直接在 `main` 上用不同 commit 区分版本。

- [配置草案](training_plan.json)：描述拟采用的实验契约，**现有 launcher 尚不读取这个文件，不是已验证的启动配置**。
- [CPU 核验结果](preflight_cpu.json)：数据哈希、token 长度、模型参数数目与资源快照。

## 1. 实验目标和对照

从原始 `Qwen3-8B` 独立初始化，训练全部 **8,190,735,360** 个参数。使用与 90 条 Codex 轨迹 LoRA 相同的数据、chat template、监督范围、batch、样本顺序种子和 epoch 数；不加载或合并 LoRA，也不继续训练旧 67 条轨迹的模型。

参考记录：

- [train90 LoRA 报告](../../experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/REPORT.md)：90 个任务、1170 个决策样本、5 轮、2925 步；后续 Dev 为 23/57，test_normal 为 51/168。
- [67 条轨迹全量 SFT 报告](../../experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/REPORT.md)：640 个样本、最长 25070 tokens，训练完成。后续 epoch 2/5 的 Dev 都为 0/57，不能把训练成功或 loss 下降等同于能力提升。
- 旧全量 SFT 使用 `2e-4` 学习率。其退化原因没有被隔离证明；本次选用更保守的学习率作为起点，不声称已证明旧学习率是唯一原因。

本次全量 SFT 与 LoRA 的学习率、调度和数值精度策略存在差异，属于相同数据上的两套训练方案比较，不应宣称只改变了参数更新方式。

## 2. 已核实的数据与环境

2026-09-23 的 CPU 核验重新检查了 manifest 中的 **97 个文件哈希**，并使用本地 tokenizer 重新渲染全部 1170 个样本；模型参数数目从 safetensors 文件头统计，未载入权重张量。

| 项目 | 结果 |
|---|---|
| 数据目录 | `data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90` |
| train.jsonl SHA-256 | `1f5ea51ea22ce7ef6b84d3e16bbb25976179064f7c8d0483ab7dcb0118ed3220` |
| 任务 / 轨迹 / 决策样本 | 90 / 90 / 1170 |
| 难度 1 / 2 / 3 | 36 / 36 / 18 |
| 输入长度 min / p50 / p95 / max | 3181 / 7249 / 16040 / 37015 |
| 超过 32768 / 40960 tokens | 6 / 0 |
| completion 平均 / 最长 | 80.81 / 418 tokens |
| GPU | 2 × RTX PRO 6000 Blackwell Server Edition，每卡 97887 MiB |
| 容器内存上限 | 220 GiB；不能按宿主机约 1 TiB 的 MemTotal 估算可用 RAM |
| 磁盘当前可用 | 约 196.7 GiB，启动时需重新检查 |
| 本地运行时 | Python 3.12.3 / torch 2.8.0+cu128 / transformers 4.56.2 / accelerate 1.10.1 |

数据哈希与 LoRA 相同；当前数据仍有 6 条超过 32768 tokens，因此保持 **40960 上限、零 token 截断**。原始数据转换时已有 observation 脱敏及字符级裁剪策略；这里的“零截断”指不进一步裁剪转换后的 token 序列。不丢弃长样本，不引入 Dev/test 样本。

这次重新检查的是数据哈希、结构、chat-template prefix 和 token 长度；官方成功、敏感值扫描等信息来自原有验证报告，并非本轮重新运行 evaluator。

## 3. 拟采用的训练配置

| 参数 | 计划值 |
|---|---|
| 初始化 | `/root/autodl-tmp/models/Qwen3-8B` 原始基座 |
| 参数更新范围 | 100%，启动时断言 trainable == total |
| loss | 当前 assistant completion 的 causal cross entropy；prompt/padding 不监督 |
| chat template | `enable_thinking=False` |
| 最大上下文 | 40960；超长直接报错，不静默截断 |
| epoch / 每轮步数 / 总步数 | 5 / 585 / 2925 |
| 每卡 batch / 全局 batch / 梯度累积 | 1 / 2 / 1 |
| 随机种子 | 20260921，与 train90 LoRA 对齐 |
| 分布式 | 双卡 FSDP FULL_SHARD，按 Qwen3DecoderLayer 包装 |
| 精度 | BF16 前后向计算，FP32 主参数、梯度归约及 AdamW 状态（拟实施） |
| attention / cache | SDPA / `use_cache=False` |
| 显存策略 | gradient checkpointing + 只对被监督位置计算 logits |
| optimizer | AdamW，betas=(0.9, 0.999)，eps=1e-8，weight_decay=0 |
| 学习率 | 峰值 1e-5；88 步 linear warmup；cosine 衰减至 1e-6 |
| 梯度裁剪 | global norm 1.0 |
| activation CPU offload | 初始关闭；如需启用，须单独验证 RAM 峰值和稳定性 |

上述学习率是起始方案，不是经调参证明的最优值。预计耗时暂不承诺：LoRA 实测约 6 小时，旧 67 条全量 SFT 约 90 分钟，两者均不能直接外推本配置；后续用长短混合预检实测吞吐估算。

## 4. 最近失败的含义与内存改造

上一轮清理前已检查四个目录：`130919` 在第 61 步后 CUDA OOM；`132719` 在最长样本预检时 CUDA OOM；`133320` 在第 20 步后为调整 offload 主动中断；`134214` 在第 183 步后收到 SIGKILL。四者均未保存模型检查点。它们已按用户要求删除，本方案记录的是上轮检查结果，不能再引用不存在的日志文件。

**SIGKILL 的原因未确定。** 当前 cgroup 的 `oom_kill=0`，不能据此确认或排除历史其他层级 OOM；应在下次运行保存 cgroup 事件增量与进程 RSS。

### 4.1 先消除无监督位置的 logits 内存

当前 `full_sft_train_fsdp_scheduled.py` 调用 `model(**batch).loss`。本地 transformers 4.56.2 的 Qwen3 默认计算全部序列 logits，causal loss 再转换为 FP32，即使 prompt label 为 `-100`。

按最长样本 37015 和词表 151936 计算，一个完整 BF16 logits 张量约 **10.48 GiB**，对应 FP32 张量约 **20.95 GiB**，尚未计入反向临时张量。这是源码与形状计算指出的显存大项，不是对全部 OOM 原因的完整归因。

拟利用 Qwen3 的 `logits_to_keep` 索引接口，仅把预测 completion 的 hidden states 投影到词表：位置 `t` 的 logits 对齐 `labels[t+1]`，只保留非 `-100` 目标位置。所有上下文仍经过完整 transformer，梯度仍回传到全部参数；不裁剪 prompt，不 detach 上下文，不把任务变成只训练输出层。训练和诊断验证共用同一实现。

实现后需要对小型合成 Qwen3 检查完整 loss 与选定位置 loss 的数值及梯度一致性，覆盖第一个 completion token、EOS、padding、短 completion。**不能只传 `logits_to_keep` 而继续向默认 loss 提供未对齐的完整 labels。** 每卡 batch 固定为 1，若以后改变 batch，需要重审索引逻辑。

API 依据：[Transformers 4.56.2 Qwen3 文档](https://huggingface.co/docs/transformers/v4.56.2/en/model_doc/qwen3#transformers.Qwen3ForCausalLM.forward)；loss 移位和 FP32 转换已检查本地 `transformers/loss/loss_utils.py`。

### 4.2 区分计算精度和优化器状态精度

旧脚本直接以 BF16 加载主参数；本地 AdamW 用 `zeros_like(parameter)` 初始化一阶、二阶状态。FSDP 的 BF16 mixed precision 设置本身不代表已有 FP32 主参数。

本方案优先显式保留 FP32 主参数/优化器状态，前后向用 BF16，以保留小学习率的累积更新；这会增加状态内存，需要实测。仅 FP32 参数、梯度和两份 AdamW 状态，双卡分片后约 **61.03 GiB/卡**，不含激活、all-gather 临时量、通信及 allocator；不能据此保证一定装得下。

若预检仍超限，先定位 FSDP 包装、激活和临时分配，再单独评估受控 offload。不会静默改成量化训练、冻结参数、缩短上下文或丢弃数据。FSDP 精度语义参考 [PyTorch 2.8 文档](https://docs.pytorch.org/docs/2.8/fsdp.html#torch.distributed.fsdp.MixedPrecision)。

## 5. checkpoint 与磁盘预算

现有训练器只导出每轮 HF 模型，没有恢复 optimizer、scheduler、RNG、采样进度的能力。需要补充两类产物：

- 每轮导出 BF16 HF 完整模型，保留 epoch 1–5，用于后续评测；FP32 主参数的导出需显式转换副本，不能原位降低训练参数精度。
- 每 100 步及 epoch 边界保存一个可恢复状态：FP32 模型分片、AdamW 两份状态及 step、scheduler、各 rank RNG、epoch、该轮已消费 batch、global step、数据/配置哈希。使用分片保存及完成标记，新版本完成且校验后才替换旧版本；保存阶段最多一份旧状态加一份正在写入的新状态。

恢复时要求相同数据哈希、双卡拓扑和依赖版本，校验 scheduler/global step/样本顺序；恢复后不重置 warmup，不重新训练已完成 batch。预检期间需要完成一次保存、退出、重载及继续更新的一致性检查。技术依据：[PyTorch 2.8 Distributed Checkpoint](https://docs.pytorch.org/docs/2.8/distributed.checkpoint.html)。

空间估算（不依赖压缩率）：

| 项目 | 估算 |
|---|---:|
| 一个 BF16 HF 模型 | 15.26 GiB |
| 五个 BF16 epoch 模型 | 76.28 GiB |
| 一份 FP32 模型 + AdamW 状态 | 91.54 GiB |
| 旧状态 + 正在保存的新状态 | 183.08 GiB |
| 上述同时存在的峰值 | 259.36 GiB，另需日志/元数据和余量 |

建议训练输出存储预留 **至少 280 GiB 可用空间**。当前约 **196.7 GiB** 不满足这套完整保留和可靠续训方案；开训前必须扩充输出存储，或明确调整保留策略并重算最坏峰值。本轮不删除其他实验来腾空间，也不把“仅存模型权重”当作完整断点续训。

## 6. 收到训练指令后的执行顺序

1. 完成 logits、精度、checkpoint 与资源监控改造；同步准备器、launcher、报告生成器，统一默认学习率/seed。当前 trainer 的默认 LR 仍为 `2e-4`，不能脱离 launcher 直接按默认值运行。
2. 做 loss/梯度等价测试、scheduler 边界和 checkpoint 恢复测试，解决上面的存储预算。记录代码提交及未提交 diff。
3. 重新检查 GPU 可用性、磁盘、cgroup RAM 和数据哈希；新建一个带时间戳的实验目录。资源快照中 GPU0 曾显示 utilization=100% 但显存/进程列表为空，正式启动前需复核，不据此宣称 GPU 可用。
4. 双卡通信检查；确定性长序列压力预检：短样本初始化 AdamW，覆盖最长 6 条样本、最长 completion、16K/24K 附近长度及长短交替，两张卡交换长样本角色，至少 20 次更新，并测试诊断和 checkpoint 保存/重载。probe 使用显式索引顺序，不依赖某个随机种子恰好得到的四样本排列。
5. 仅预检通过后，从原始基座重新初始化正式训练；probe 权重和 optimizer 不进入正式训练。保持原定全局 batch、2925 步 scheduler 和 5 个连续 epoch。
6. 每步记录 loss/LR/grad norm、两个 rank 的实际长度及监督 token 数；定期记录 GPU allocated/reserved、进程 RSS、cgroup memory.current/peak/events、磁盘余量。建议 GPU 保留至少 5 GiB 余量，cgroup 使用低于上限 80%；无 NaN/Inf、无持续内存增长才放行。失败时记录阶段与退出码，不自动反复重启或换配置。
7. 完成各轮权重、最终模型重载生成检查、哈希、loss 图、中文报告。重载/生成检查失败单独标记，不用训练 loss 声称流程完全成功。

本轮仅完成第 1 步之前的方案和静态核查，以上 GPU 过程均未执行。

## 7. 后续能力评测

训练中的 90 个最后决策样本全部与训练集重叠，只用于拟合诊断。后续评测阶段先对 epoch 1–5 使用同一 Dev 57 题官方 evaluator；选择最高 TGC，平分时依次按 SGC、较早 epoch 决定。之后固定模型再评测 test_normal，测试反馈不进入训练或 checkpoint 选择。

与 train90 LoRA 对齐 ReAct prompt、无 reasoning parser 的输出接口、temperature=0、seed=100、最多 50 步、每次最多 3000 输出 tokens、推理 context=32000。训练 40960 上下文不意味着评测自动扩窗；若另测 40960，则双方同设定并单独报告。评测属于后续阶段，本轮未启动。

## 8. 准备验收

- 已提交原工作区基线。
- 已复核参考训练、97 个数据文件哈希、1170 个样本 token 化、模型参数和环境。
- 已给出配置草案、失败分析、实现清单、内存/存储预算、预检顺序和评测规则。
- 未更改现有训练脚本；方案中的优化与续训尚未实现，不标为可直接开跑。
- **等待用户明确训练指令；不会在本轮或后台自行开始训练。**

## 执行结果

用户授权后已完成五轮全参数 SFT。实际采用每轮保存一次、只保留最新续训状态及最终模型的策略，完整结果和与旧 67 轨迹的 loss 对比见 [中文报告](../../experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md)。
