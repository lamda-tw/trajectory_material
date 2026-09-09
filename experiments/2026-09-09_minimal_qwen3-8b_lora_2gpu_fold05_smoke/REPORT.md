# 最小双卡 Qwen3-8B SFT 闭环实验报告

## 1. 结论

本次最小验证已完整跑通，状态为 **SUCCESS**：从推荐单折抽取微型数据、使用 Qwen 官方 tokenizer/chat template 做精确编码、执行 completion-only LoRA SFT、双卡 NCCL/DDP 同步、验证 loss、保存适配器，再从磁盘重载适配器完成单样本生成。生成重载检查状态为 **PASS**。

这是一场工程 smoke test，只证明训练管线和产物链路可工作。训练集只有 8 条、验证集只有 4 条、仅 4 个优化步，因此本报告不评价 O2，也不把 loss 或生成文本解释为模型质量提升。

## 2. 实验范围与选择

- 工作区：`/root/autodl-tmp/workspace-tw`
- 基座：`/root/autodl-tmp/models/Qwen3-8B`（本地文件，未在线下载模型）
- 数据版本：`data/2026-09-08`
- 单折：`fold_05_holdout_0010`，训练 families 0006/0007/0008/0009，验证 family 0010
- 微型规模：train=8，validation=4
- 抽样：先按 trajectory 分组，各组内按序列化字符数从短到长，再轮询各 trajectory；固定 tie-break，结果可复现
- 方法：LoRA，r=8，alpha=16，目标模块 q/k/v/o + gate/up/down projections
- dtype：bfloat16；attention：SDPA；最大长度：8192 tokens
- batch：每卡 1，双卡全局 batch 2；epoch=1；AdamW；lr=0.0002
- 隐藏思维：`enable_thinking=False`
- loss 边界：prompt 与 padding 的 labels 均为 -100，仅 completion token 参与 loss

远端真实仓库路径是 `/root/autodl-tmp/workspace-tw`；用户描述中的 `/autodl-tmp/workspace-tw` 在该主机上不存在。

## 3. 流程与门禁

1. 检查两张 GPU、CUDA、模型分片和磁盘。
2. 创建 `.conda-training`，从 base 克隆现有 CUDA/PyTorch 包后独立安装 Transformers、Tokenizers、PEFT、Accelerate；未修改 base。
3. 从 fold 05 生成 `data/train.jsonl` 与 `data/validation.jsonl`，保存源/输出 SHA-256 与样本清单。
4. 使用两进程 `torchrun` 执行 NCCL all-reduce 探针；必须 world size=2 且通信和为 3。
5. 两个 rank 各加载一份 Qwen3-8B，注入 LoRA，执行 DDP 训练。
6. 跨 rank 聚合 completion-token 加权验证 loss。
7. rank 0 保存 LoRA adapter 与 tokenizer，并写结构化指标。
8. 退出 DDP 后重新从磁盘加载 base + adapter，在 GPU 0 进行一次 greedy generation。
9. 生成本报告、环境快照、GPU 监控 CSV 与产物校验和。

## 4. 双卡使用证据

NCCL world size 为 2，训练指标记录了两个独立 rank。两卡峰值显存如下：

| rank | local rank | GPU | 峰值 allocated | 峰值 reserved |
|---:|---:|---|---:|---:|
| 0 | 0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 29.10 GiB | 39.96 GiB |
| 1 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 27.97 GiB | 46.12 GiB |

`logs/gpu_usage.csv` 还保存了按秒采样的 GPU 利用率和显存。由于这是 8 条样本、4 个优化步的最小验证，主要时间花在双份基座加载和初始化上，不能据此评估长期吞吐或卡间扩展效率。

## 5. 数据与 tokenizer 结果

训练 token 数：min=4140，max=6761，mean=5369.50；completion token：min=73，max=468，mean=284.25；发生左侧 prompt token 裁剪的训练样本为 0 条，共裁剪 0 tokens。

验证 token 数：min=4171，max=6301，mean=5233.50；completion token：min=63，max=130，mean=97.00；发生左侧 prompt token 裁剪的验证样本为 0 条，共裁剪 0 tokens。

训练样本：

- `EI-56TESTPK0006-easy-v1.2::assistant-0001`（family 0006，源第 1 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0001`（family 0007，源第 167 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0001`（family 0008，源第 297 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0001`（family 0008，源第 466 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0001`（family 0009，源第 731 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0002`（family 0006，源第 2 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0002`（family 0007，源第 168 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0002`（family 0008，源第 298 行）

验证样本：

- `EI-56TESTPK0010-easy-v1.2::assistant-0001`（family 0010，源第 1 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0001`（family 0010，源第 456 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0002`（family 0010，源第 2 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0002`（family 0010，源第 457 行）

## 6. 训练与验证结果

- 可训练参数：21,823,488 / 8,212,558,848（0.2657%）
- 优化步：4
- 训练阶段用时：13.46 秒
- 验证 completion target tokens：388
- 验证 loss：1.284305
- 验证 perplexity：3.6122

| step | 双 rank 平均 train loss | 累计时间 |
|---:|---:|---:|
| 1 | 1.388753 | 3.03 s |
| 2 | 1.356443 | 6.61 s |
| 3 | 1.075371 | 8.91 s |
| 4 | 0.919102 | 12.01 s |

这些数值仅用于检查 loss 有限、反向传播和验证归约能够完成。样本极少且训练步数极短，不能用于超参数比较或效果判断。

## 7. 适配器重载与生成检查

- 样本：`EI-56TESTPK0010-easy-v1.2::assistant-0001`
- 输入 tokens：4108
- 新生成 tokens：64
- 状态：PASS

```text
### 任务理解与规划

根据用户提供的需求，我需要完成以下任务：

1. **生成 `sites_material_list.csv`**：从 `Input4-Site-BOM_for Pak_Option3_去掉ER+天线不跨区+去掉R2_2026072
```

该检查的验收条件是 adapter 能从磁盘重载、前向与 generation 无异常、产生非空 token；不要求内容正确，也不做 O2 评分。

## 8. 产物说明

- `STATUS.txt`：最终 SUCCESS/FAILED 状态
- `command.txt`：本次入口命令
- `environment.txt`：GPU、系统、Python、pip freeze、Git 状态
- `data/`：微型 train/validation、选择 manifest 与 SHA-256
- `artifacts/adapter/`：LoRA 权重、配置、tokenizer
- `artifacts/metrics.json`：结构化训练、验证、token 与双卡峰值信息
- `metrics/generation_smoke.json`：适配器重载生成结果
- `logs/`：准备、DDP、训练、重载生成及 GPU 按秒监控日志
- `scripts_snapshot/`：本次用到脚本的快照
- `artifacts.sha256`：实验目录关键文件校验和

## 9. 复现

在仓库根目录执行：

```bash
bash scripts/run_minimal_sft.sh experiments/2026-09-09_minimal_qwen3-8b_lora_2gpu_fold05_smoke
```

脚本使用固定 seed `20260909` 与确定性抽样。GPU 浮点内核和 DDP 时序仍可能造成末位差异。

## 10. 限制与下一步

1. 当前只做 8/4 条微型数据和 4 个优化步，不代表一次有统计意义的训练。
2. 最大长度为 8192；若有裁剪，下一阶段应根据显存与吞吐测试 8192/16384，并优先保证完整 assistant-tool 块。
3. 当前 tool schema 是从全部 7 条轨迹推断的，不是正式 runtime contract。
4. 当前验证只有 teacher-forced completion loss 与非空生成，尚未做 tool-call JSON 结构正确率、工具名准确率、端到端 rollout 或 O2。
5. 轨迹归一权重字段本次未启用；正式小样本实验应对是否使用该权重做明确选择。
6. 下一安全台阶建议保持 fold 05，先扩大到 64–128 条、20–50 个优化步，并增加结构化 tool-call 验证；稳定后再跑完整 952 条训练集。

## 11. 最终验收清单

- [x] 推荐单折且无 task-family 泄漏
- [x] Qwen chat template + `enable_thinking=False`
- [x] completion-only labels
- [x] 两张 RTX PRO 6000、两个 NCCL rank
- [x] LoRA 反向传播与 optimizer step
- [x] 跨卡验证 loss 聚合
- [x] adapter/tokenizer 落盘
- [x] adapter 从磁盘重载并生成非空输出
- [x] 日志、配置、环境、结果、脚本快照与报告集中归档
