# Fold 05 全量双卡 Qwen3-8B SFT 实验报告

## 1. 结论

本次 fold 05 全量训练已完整跑通，状态为 **SUCCESS**：读取 fold 05 全量数据、使用 Qwen 官方 tokenizer/chat template 做精确编码、执行 completion-only LoRA SFT、双卡 NCCL/DDP 同步、验证 loss、保存适配器，再从磁盘重载适配器完成单样本生成。生成重载检查状态为 **PASS**。

本次使用 fold 05 的全部 952 条训练样本和全部 675 条验证样本，完成 1 个 epoch、476 个优化步。本报告记录训练与验证结果，但暂不评价 O2；O2 需要独立的端到端工具 rollout 产物。

## 2. 实验范围与选择

- 工作区：`/root/autodl-tmp/workspace-tw`
- 基座：`/root/autodl-tmp/models/Qwen3-8B`（本地文件，未在线下载模型）
- 数据版本：`data/2026-09-08`
- 单折：`fold_05_holdout_0010`，训练 families 0006/0007/0008/0009，验证 family 0010
- 全量规模：train=952，validation=675
- 数据副本顺序：按 trajectory 轮询并使用固定 tie-break；952/675 条源样本全部保留
- 方法：LoRA，r=8，alpha=16，目标模块 q/k/v/o + gate/up/down projections
- dtype：bfloat16；attention：SDPA；最大长度：20480 tokens
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
| 0 | 0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 52.83 GiB | 93.16 GiB |
| 1 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 43.12 GiB | 92.39 GiB |

`logs/gpu_usage.csv` 还保存了按秒采样的 GPU 利用率和显存。本次为 fold 05 全量单 epoch 训练；上述证据用于确认双卡均实际参与计算，不能据此评估更多卡的扩展效率。

## 5. 数据与 tokenizer 结果

训练 token 数：min=4140，max=18557，mean=10141.11；completion token：min=28，max=6828，mean=253.30；发生左侧 prompt token 裁剪的训练样本为 0 条，共裁剪 0 tokens。

验证 token 数：min=4171，max=13806，mean=10013.29；completion token：min=17，max=4176，mean=191.09；发生左侧 prompt token 裁剪的验证样本为 0 条，共裁剪 0 tokens。

训练样本：

- `EI-56TESTPK0006-easy-v1.2::assistant-0001`（family 0006，源第 1 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0001`（family 0007，源第 167 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0001`（family 0008，源第 297 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0001`（family 0008，源第 466 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0001`（family 0009，源第 731 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0002`（family 0006，源第 2 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0002`（family 0007，源第 168 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0002`（family 0008，源第 298 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0002`（family 0008，源第 467 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0002`（family 0009，源第 732 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0003`（family 0006，源第 3 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0008`（family 0007，源第 174 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0003`（family 0008，源第 299 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0007`（family 0008，源第 472 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0003`（family 0009，源第 733 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0004`（family 0006，源第 4 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0005`（family 0007，源第 171 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0007`（family 0008，源第 303 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0008`（family 0008，源第 473 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0004`（family 0009，源第 734 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0006`（family 0006，源第 6 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0010`（family 0007，源第 176 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0004`（family 0008，源第 300 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0004`（family 0008，源第 469 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0005`（family 0009，源第 735 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0009`（family 0006，源第 9 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0006`（family 0007，源第 172 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0006`（family 0008，源第 302 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0012`（family 0008，源第 477 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0006`（family 0009，源第 736 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0014`（family 0006，源第 14 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0003`（family 0007，源第 169 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0010`（family 0008，源第 306 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0009`（family 0008，源第 474 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0022`（family 0009，源第 752 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0012`（family 0006，源第 12 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0015`（family 0007，源第 181 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0008`（family 0008，源第 304 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0005`（family 0008，源第 470 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0019`（family 0009，源第 749 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0011`（family 0006，源第 11 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0009`（family 0007，源第 175 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0011`（family 0008，源第 307 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0013`（family 0008，源第 478 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0024`（family 0009，源第 754 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0008`（family 0006，源第 8 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0033`（family 0007，源第 199 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0019`（family 0008，源第 315 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0014`（family 0008，源第 479 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0009`（family 0009，源第 739 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0029`（family 0006，源第 29 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0007`（family 0007，源第 173 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0016`（family 0008，源第 312 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0010`（family 0008，源第 475 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0020`（family 0009，源第 750 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0030`（family 0006，源第 30 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0021`（family 0007，源第 187 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0021`（family 0008，源第 317 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0011`（family 0008，源第 476 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0046`（family 0009，源第 776 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0028`（family 0006，源第 28 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0089`（family 0007，源第 255 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0020`（family 0008，源第 316 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0003`（family 0008，源第 468 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0041`（family 0009，源第 771 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0159`（family 0006，源第 159 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0030`（family 0007，源第 196 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0028`（family 0008，源第 324 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0020`（family 0008，源第 485 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0051`（family 0009，源第 781 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0088`（family 0006，源第 88 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0101`（family 0007，源第 267 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0043`（family 0008，源第 339 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0016`（family 0008，源第 481 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0049`（family 0009，源第 779 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0129`（family 0006，源第 129 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0092`（family 0007，源第 258 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0017`（family 0008，源第 313 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0057`（family 0008，源第 522 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0045`（family 0009，源第 775 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0040`（family 0006，源第 40 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0091`（family 0007，源第 257 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0009`（family 0008，源第 305 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0064`（family 0008，源第 529 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0023`（family 0009，源第 753 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0109`（family 0006，源第 109 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0044`（family 0007，源第 210 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0054`（family 0008，源第 350 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0056`（family 0008，源第 521 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0048`（family 0009，源第 778 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0069`（family 0006，源第 69 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0065`（family 0007，源第 231 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0073`（family 0008，源第 369 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0087`（family 0008，源第 552 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0028`（family 0009，源第 758 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0023`（family 0006，源第 23 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0048`（family 0007，源第 214 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0027`（family 0008，源第 323 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0006`（family 0008，源第 471 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0013`（family 0009，源第 743 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0048`（family 0006，源第 48 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0086`（family 0007，源第 252 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0095`（family 0008，源第 391 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0033`（family 0008，源第 498 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0092`（family 0009，源第 822 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0136`（family 0006，源第 136 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0087`（family 0007，源第 253 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0138`（family 0008，源第 434 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0119`（family 0008，源第 584 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0094`（family 0009，源第 824 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0148`（family 0006，源第 148 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0019`（family 0007，源第 185 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0030`（family 0008，源第 326 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0038`（family 0008，源第 503 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0033`（family 0009，源第 763 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0046`（family 0006，源第 46 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0088`（family 0007，源第 254 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0046`（family 0008，源第 342 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0228`（family 0008，源第 693 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0008`（family 0009，源第 738 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0122`（family 0006，源第 122 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0103`（family 0007，源第 269 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0072`（family 0008，源第 368 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0058`（family 0008，源第 523 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0072`（family 0009，源第 802 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0042`（family 0006，源第 42 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0036`（family 0007，源第 202 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0152`（family 0008，源第 448 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0159`（family 0008，源第 624 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0086`（family 0009，源第 816 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0155`（family 0006，源第 155 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0052`（family 0007，源第 218 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0099`（family 0008，源第 395 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0025`（family 0008，源第 490 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0183`（family 0009，源第 913 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0161`（family 0006，源第 161 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0013`（family 0007，源第 179 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0032`（family 0008，源第 328 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0229`（family 0008，源第 694 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0055`（family 0009，源第 785 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0113`（family 0006，源第 113 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0004`（family 0007，源第 170 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0022`（family 0008，源第 318 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0047`（family 0008，源第 512 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0123`（family 0009，源第 853 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0027`（family 0006，源第 27 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0034`（family 0007，源第 200 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0087`（family 0008，源第 383 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0106`（family 0008，源第 571 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0047`（family 0009，源第 777 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0144`（family 0006，源第 144 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0011`（family 0007，源第 177 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0045`（family 0008，源第 341 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0029`（family 0008，源第 494 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0043`（family 0009，源第 773 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0017`（family 0006，源第 17 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0022`（family 0007，源第 188 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0079`（family 0008，源第 375 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0210`（family 0008，源第 675 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0025`（family 0009，源第 755 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0139`（family 0006，源第 139 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0035`（family 0007，源第 201 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0116`（family 0008，源第 412 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0093`（family 0008，源第 558 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0195`（family 0009，源第 925 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0026`（family 0006，源第 26 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0051`（family 0007，源第 217 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0110`（family 0008，源第 406 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0018`（family 0008，源第 483 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0133`（family 0009，源第 863 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0142`（family 0006，源第 142 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0117`（family 0007，源第 283 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0114`（family 0008，源第 410 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0072`（family 0008，源第 537 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0170`（family 0009，源第 900 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0130`（family 0006，源第 130 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0095`（family 0007，源第 261 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0039`（family 0008，源第 335 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0015`（family 0008，源第 480 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0039`（family 0009，源第 769 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0160`（family 0006，源第 160 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0102`（family 0007，源第 268 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0131`（family 0008，源第 427 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0126`（family 0008，源第 591 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0164`（family 0009，源第 894 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0025`（family 0006，源第 25 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0062`（family 0007，源第 228 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0026`（family 0008，源第 322 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0214`（family 0008，源第 679 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0169`（family 0009，源第 899 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0099`（family 0006，源第 99 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0128`（family 0007，源第 294 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0051`（family 0008，源第 347 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0092`（family 0008，源第 557 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0112`（family 0009，源第 842 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0086`（family 0006，源第 86 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0090`（family 0007，源第 256 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0042`（family 0008，源第 338 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0131`（family 0008，源第 596 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0030`（family 0009，源第 760 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0049`（family 0006，源第 49 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0121`（family 0007，源第 287 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0067`（family 0008，源第 363 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0079`（family 0008，源第 544 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0058`（family 0009，源第 788 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0019`（family 0006，源第 19 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0037`（family 0007，源第 203 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0053`（family 0008，源第 349 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0045`（family 0008，源第 510 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0093`（family 0009，源第 823 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0151`（family 0006，源第 151 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0017`（family 0007，源第 183 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0147`（family 0008，源第 443 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0164`（family 0008，源第 629 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0204`（family 0009，源第 934 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0016`（family 0006，源第 16 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0112`（family 0007，源第 278 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0038`（family 0008，源第 334 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0080`（family 0008，源第 545 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0154`（family 0009，源第 884 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0100`（family 0006，源第 100 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0123`（family 0007，源第 289 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0074`（family 0008，源第 370 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0155`（family 0008，源第 620 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0111`（family 0009，源第 841 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0138`（family 0006，源第 138 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0058`（family 0007，源第 224 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0090`（family 0008，源第 386 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0108`（family 0008，源第 573 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0139`（family 0009，源第 869 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0058`（family 0006，源第 58 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0049`（family 0007，源第 215 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0040`（family 0008，源第 336 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0215`（family 0008，源第 680 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0064`（family 0009，源第 794 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0072`（family 0006，源第 72 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0028`（family 0007，源第 194 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0048`（family 0008，源第 344 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0212`（family 0008，源第 677 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0218`（family 0009，源第 948 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0065`（family 0006，源第 65 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0079`（family 0007，源第 245 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0153`（family 0008，源第 449 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0230`（family 0008，源第 695 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0054`（family 0009，源第 784 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0039`（family 0006，源第 39 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0094`（family 0007，源第 260 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0113`（family 0008，源第 409 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0202`（family 0008，源第 667 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0119`（family 0009，源第 849 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0067`（family 0006，源第 67 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0060`（family 0007，源第 226 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0066`（family 0008，源第 362 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0174`（family 0008，源第 639 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0062`（family 0009，源第 792 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0051`（family 0006，源第 51 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0043`（family 0007，源第 209 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0154`（family 0008，源第 450 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0176`（family 0008，源第 641 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0091`（family 0009，源第 821 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0075`（family 0006，源第 75 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0084`（family 0007，源第 250 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0077`（family 0008，源第 373 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0127`（family 0008，源第 592 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0132`（family 0009，源第 862 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0077`（family 0006，源第 77 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0080`（family 0007，源第 246 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0151`（family 0008，源第 447 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0118`（family 0008，源第 583 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0011`（family 0009，源第 741 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0127`（family 0006，源第 127 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0081`（family 0007，源第 247 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0098`（family 0008，源第 394 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0078`（family 0008，源第 543 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0077`（family 0009，源第 807 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0156`（family 0006，源第 156 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0012`（family 0007，源第 178 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0130`（family 0008，源第 426 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0251`（family 0008，源第 716 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0104`（family 0009，源第 834 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0092`（family 0006，源第 92 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0074`（family 0007，源第 240 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0084`（family 0008，源第 380 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0115`（family 0008，源第 580 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0188`（family 0009，源第 918 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0102`（family 0006，源第 102 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0078`（family 0007，源第 244 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0050`（family 0008，源第 346 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0191`（family 0008，源第 656 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0148`（family 0009，源第 878 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0073`（family 0006，源第 73 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0097`（family 0007，源第 263 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0083`（family 0008，源第 379 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0181`（family 0008，源第 646 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0083`（family 0009，源第 813 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0038`（family 0006，源第 38 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0098`（family 0007，源第 264 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0097`（family 0008，源第 393 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0069`（family 0008，源第 534 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0179`（family 0009，源第 909 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0097`（family 0006，源第 97 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0068`（family 0007，源第 234 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0047`（family 0008，源第 343 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0146`（family 0008，源第 611 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0007`（family 0009，源第 737 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0066`（family 0006，源第 66 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0122`（family 0007，源第 288 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0068`（family 0008，源第 364 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0091`（family 0008，源第 556 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0209`（family 0009，源第 939 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0043`（family 0006，源第 43 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0085`（family 0007，源第 251 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0146`（family 0008，源第 442 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0068`（family 0008，源第 533 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0186`（family 0009，源第 916 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0050`（family 0006，源第 50 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0118`（family 0007，源第 284 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0091`（family 0008，源第 387 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0116`（family 0008，源第 581 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0140`（family 0009，源第 870 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0044`（family 0006，源第 44 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0119`（family 0007，源第 285 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0078`（family 0008，源第 374 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0231`（family 0008，源第 696 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0032`（family 0009，源第 762 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0137`（family 0006，源第 137 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0050`（family 0007，源第 216 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0057`（family 0008，源第 353 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0109`（family 0008，源第 574 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0068`（family 0009，源第 798 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0114`（family 0006，源第 114 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0071`（family 0007，源第 237 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0093`（family 0008，源第 389 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0070`（family 0008，源第 535 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0182`（family 0009，源第 912 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0121`（family 0006，源第 121 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0115`（family 0007，源第 281 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0143`（family 0008，源第 439 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0128`（family 0008，源第 593 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0031`（family 0009，源第 761 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0115`（family 0006，源第 115 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0111`（family 0007，源第 277 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0031`（family 0008，源第 327 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0022`（family 0008，源第 487 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0021`（family 0009，源第 751 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0059`（family 0006，源第 59 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0126`（family 0007，源第 292 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0061`（family 0008，源第 357 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0075`（family 0008，源第 540 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0193`（family 0009，源第 923 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0064`（family 0006，源第 64 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0047`（family 0007，源第 213 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0100`（family 0008，源第 396 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0241`（family 0008，源第 706 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0056`（family 0009，源第 786 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0024`（family 0006，源第 24 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0041`（family 0007，源第 207 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0124`（family 0008，源第 420 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0094`（family 0008，源第 559 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0109`（family 0009，源第 839 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0041`（family 0006，源第 41 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0110`（family 0007，源第 276 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0055`（family 0008，源第 351 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0059`（family 0008，源第 524 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0085`（family 0009，源第 815 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0118`（family 0006，源第 118 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0029`（family 0007，源第 195 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0157`（family 0008，源第 453 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0204`（family 0008，源第 669 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0098`（family 0009，源第 828 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0116`（family 0006，源第 116 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0059`（family 0007，源第 225 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0112`（family 0008，源第 408 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0060`（family 0008，源第 525 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0149`（family 0009，源第 879 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0063`（family 0006，源第 63 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0127`（family 0007，源第 293 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0049`（family 0008，源第 345 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0105`（family 0008，源第 570 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0067`（family 0009，源第 797 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0120`（family 0006，源第 120 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0075`（family 0007，源第 241 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0075`（family 0008，源第 371 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0040`（family 0008，源第 505 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0135`（family 0009，源第 865 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0062`（family 0006，源第 62 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0069`（family 0007，源第 235 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0111`（family 0008，源第 407 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0169`（family 0008，源第 634 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0117`（family 0009，源第 847 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0126`（family 0006，源第 126 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0116`（family 0007，源第 282 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0018`（family 0008，源第 314 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0051`（family 0008，源第 516 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0124`（family 0009，源第 854 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0140`（family 0006，源第 140 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0031`（family 0007，源第 197 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0082`（family 0008，源第 378 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0043`（family 0008，源第 508 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0014`（family 0009，源第 744 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0103`（family 0006，源第 103 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0064`（family 0007，源第 230 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0076`（family 0008，源第 372 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0101`（family 0008，源第 566 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0061`（family 0009，源第 791 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0061`（family 0006，源第 61 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0046`（family 0007，源第 212 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0115`（family 0008，源第 411 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0150`（family 0008，源第 615 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0130`（family 0009，源第 860 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0141`（family 0006，源第 141 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0082`（family 0007，源第 248 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0081`（family 0008，源第 377 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0114`（family 0008，源第 579 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0099`（family 0009，源第 829 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0089`（family 0006，源第 89 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0109`（family 0007，源第 275 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0104`（family 0008，源第 400 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0248`（family 0008，源第 713 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0118`（family 0009，源第 848 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0047`（family 0006，源第 47 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0023`（family 0007，源第 189 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0144`（family 0008，源第 440 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0238`（family 0008，源第 703 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0171`（family 0009，源第 901 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0111`（family 0006，源第 111 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0020`（family 0007，源第 186 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0102`（family 0008，源第 398 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0036`（family 0008，源第 501 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0208`（family 0009，源第 938 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0128`（family 0006，源第 128 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0067`（family 0007，源第 233 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0080`（family 0008，源第 376 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0139`（family 0008，源第 604 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0141`（family 0009，源第 871 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0084`（family 0006，源第 84 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0100`（family 0007，源第 266 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0105`（family 0008，源第 401 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0180`（family 0008，源第 645 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0035`（family 0009，源第 765 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0070`（family 0006，源第 70 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0018`（family 0007，源第 184 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0118`（family 0008，源第 414 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0242`（family 0008，源第 707 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0194`（family 0009，源第 924 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0085`（family 0006，源第 85 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0104`（family 0007，源第 270 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0088`（family 0008，源第 384 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0190`（family 0008，源第 655 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0173`（family 0009，源第 903 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0154`（family 0006，源第 154 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0113`（family 0007，源第 279 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0126`（family 0008，源第 422 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0037`（family 0008，源第 502 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0088`（family 0009，源第 818 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0149`（family 0006，源第 149 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0014`（family 0007，源第 180 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0160`（family 0008，源第 456 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0110`（family 0008，源第 575 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0158`（family 0009，源第 888 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0091`（family 0006，源第 91 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0099`（family 0007，源第 265 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0092`（family 0008，源第 388 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0034`（family 0008，源第 499 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0103`（family 0009，源第 833 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0117`（family 0006，源第 117 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0105`（family 0007，源第 271 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0094`（family 0008，源第 390 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0055`（family 0008，源第 520 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0153`（family 0009，源第 883 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0162`（family 0006，源第 162 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0032`（family 0007，源第 198 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0117`（family 0008，源第 413 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0090`（family 0008，源第 555 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0134`（family 0009，源第 864 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0074`（family 0006，源第 74 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0070`（family 0007，源第 236 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0137`（family 0008，源第 433 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0123`（family 0008，源第 588 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0152`（family 0009，源第 882 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0106`（family 0006，源第 106 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0027`（family 0007，源第 193 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0064`（family 0008，源第 360 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0243`（family 0008，源第 708 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0197`（family 0009，源第 927 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0045`（family 0006，源第 45 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0125`（family 0007，源第 291 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0056`（family 0008，源第 352 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0074`（family 0008，源第 539 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0199`（family 0009，源第 929 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0146`（family 0006，源第 146 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0073`（family 0007，源第 239 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0106`（family 0008，源第 402 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0083`（family 0008，源第 548 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0066`（family 0009，源第 796 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0071`（family 0006，源第 71 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0042`（family 0007，源第 208 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0156`（family 0008，源第 452 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0158`（family 0008，源第 623 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0100`（family 0009，源第 830 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0060`（family 0006，源第 60 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0096`（family 0007，源第 262 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0063`（family 0008，源第 359 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0112`（family 0008，源第 577 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0120`（family 0009，源第 850 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0108`（family 0006，源第 108 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0083`（family 0007，源第 249 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0109`（family 0008，源第 405 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0196`（family 0008，源第 661 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0207`（family 0009，源第 937 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0057`（family 0006，源第 57 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0120`（family 0007，源第 286 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0096`（family 0008，源第 392 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0234`（family 0008，源第 699 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0201`（family 0009，源第 931 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0068`（family 0006，源第 68 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0124`（family 0007，源第 290 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0033`（family 0008，源第 329 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0160`（family 0008，源第 625 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0191`（family 0009，源第 921 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0007`（family 0006，源第 7 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0076`（family 0007，源第 242 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0108`（family 0008，源第 404 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0245`（family 0008，源第 710 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0190`（family 0009，源第 920 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0055`（family 0006，源第 55 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0077`（family 0007，源第 243 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0029`（family 0008，源第 325 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0117`（family 0008，源第 582 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0101`（family 0009，源第 831 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0133`（family 0006，源第 133 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0063`（family 0007，源第 229 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0150`（family 0008，源第 446 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0199`（family 0008，源第 664 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0074`（family 0009，源第 804 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0135`（family 0006，源第 135 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0045`（family 0007，源第 211 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0129`（family 0008，源第 425 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0208`（family 0008，源第 673 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0017`（family 0009，源第 747 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0035`（family 0006，源第 35 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0114`（family 0007，源第 280 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0168`（family 0008，源第 464 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0133`（family 0008，源第 598 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0150`（family 0009，源第 880 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0010`（family 0006，源第 10 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0061`（family 0007，源第 227 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0103`（family 0008，源第 399 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0213`（family 0008，源第 678 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0095`（family 0009，源第 825 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0112`（family 0006，源第 112 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0129`（family 0007，源第 295 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0044`（family 0008，源第 340 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0032`（family 0008，源第 497 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0138`（family 0009，源第 868 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0021`（family 0006，源第 21 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0130`（family 0007，源第 296 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0162`（family 0008，源第 458 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0142`（family 0008，源第 607 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0160`（family 0009，源第 890 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0104`（family 0006，源第 104 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0066`（family 0007，源第 232 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0149`（family 0008，源第 445 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0236`（family 0008，源第 701 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0187`（family 0009，源第 917 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0080`（family 0006，源第 80 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0093`（family 0007，源第 259 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0037`（family 0008，源第 333 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0148`（family 0008，源第 613 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0161`（family 0009，源第 891 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0125`（family 0006，源第 125 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0072`（family 0007，源第 238 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0065`（family 0008，源第 361 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0125`（family 0008，源第 590 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0063`（family 0009，源第 793 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0107`（family 0006，源第 107 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0108`（family 0007，源第 274 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0161`（family 0008，源第 457 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0205`（family 0008，源第 670 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0189`（family 0009，源第 919 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0036`（family 0006，源第 36 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0055`（family 0007，源第 221 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0085`（family 0008，源第 381 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0233`（family 0008，源第 698 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0034`（family 0009，源第 764 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0145`（family 0006，源第 145 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0057`（family 0007，源第 223 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0086`（family 0008，源第 382 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0096`（family 0008，源第 561 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0089`（family 0009，源第 819 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0034`（family 0006，源第 34 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0024`（family 0007，源第 190 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0125`（family 0008，源第 421 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0089`（family 0008，源第 554 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0137`（family 0009，源第 867 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0090`（family 0006，源第 90 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0106`（family 0007，源第 272 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0140`（family 0008，源第 436 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0099`（family 0008，源第 564 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0078`（family 0009，源第 808 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0078`（family 0006，源第 78 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0025`（family 0007，源第 191 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0025`（family 0008，源第 321 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0082`（family 0008，源第 547 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0080`（family 0009，源第 810 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0022`（family 0006，源第 22 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0016`（family 0007，源第 182 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0139`（family 0008，源第 435 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0264`（family 0008，源第 729 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0040`（family 0009，源第 770 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0081`（family 0006，源第 81 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0107`（family 0007，源第 273 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0034`（family 0008，源第 330 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0194`（family 0008，源第 659 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0174`（family 0009，源第 904 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0020`（family 0006，源第 20 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0054`（family 0007，源第 220 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0164`（family 0008，源第 460 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0178`（family 0008，源第 643 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0070`（family 0009，源第 800 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0033`（family 0006，源第 33 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0039`（family 0007，源第 205 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0024`（family 0008，源第 320 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0095`（family 0008，源第 560 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0110`（family 0009，源第 840 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0079`（family 0006，源第 79 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0040`（family 0007，源第 206 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0015`（family 0008，源第 311 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0039`（family 0008，源第 504 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0121`（family 0009，源第 851 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0150`（family 0006，源第 150 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0056`（family 0007，源第 222 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0155`（family 0008，源第 451 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0222`（family 0008，源第 687 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0084`（family 0009，源第 814 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0131`（family 0006，源第 131 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0053`（family 0007，源第 219 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0128`（family 0008，源第 424 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0028`（family 0008，源第 493 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0082`（family 0009，源第 812 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0163`（family 0006，源第 163 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0038`（family 0007，源第 204 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0142`（family 0008，源第 438 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0044`（family 0008，源第 509 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0116`（family 0009，源第 846 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0153`（family 0006，源第 153 行）
- `EI-56TESTPK0007-medium-v1.2::assistant-0026`（family 0007，源第 192 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0166`（family 0008，源第 462 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0240`（family 0008，源第 705 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0165`（family 0009，源第 895 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0105`（family 0006，源第 105 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0136`（family 0008，源第 432 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0081`（family 0008，源第 546 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0059`（family 0009，源第 789 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0087`（family 0006，源第 87 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0107`（family 0008，源第 403 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0198`（family 0008，源第 663 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0166`（family 0009，源第 896 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0093`（family 0006，源第 93 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0052`（family 0008，源第 348 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0100`（family 0008，源第 565 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0181`（family 0009，源第 911 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0166`（family 0006，源第 166 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0135`（family 0008，源第 431 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0097`（family 0008，源第 562 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0108`（family 0009，源第 838 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0083`（family 0006，源第 83 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0036`（family 0008，源第 332 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0187`（family 0008，源第 652 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0162`（family 0009，源第 892 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0165`（family 0006，源第 165 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0158`（family 0008，源第 454 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0197`（family 0008，源第 662 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0122`（family 0009，源第 852 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0013`（family 0006，源第 13 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0023`（family 0008，源第 319 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0111`（family 0008，源第 576 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0052`（family 0009，源第 782 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0005`（family 0006，源第 5 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0005`（family 0008，源第 301 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0165`（family 0008，源第 630 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0096`（family 0009，源第 826 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0134`（family 0006，源第 134 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0035`（family 0008，源第 331 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0201`（family 0008，源第 666 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0163`（family 0009，源第 893 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0037`（family 0006，源第 37 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0014`（family 0008，源第 310 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0152`（family 0008，源第 617 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0097`（family 0009，源第 827 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0056`（family 0006，源第 56 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0141`（family 0008，源第 437 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0249`（family 0008，源第 714 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0192`（family 0009，源第 922 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0123`（family 0006，源第 123 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0165`（family 0008，源第 461 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0049`（family 0008，源第 514 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0126`（family 0009，源第 856 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0031`（family 0006，源第 31 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0069`（family 0008，源第 365 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0067`（family 0008，源第 532 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0053`（family 0009，源第 783 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0124`（family 0006，源第 124 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0145`（family 0008，源第 441 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0153`（family 0008，源第 618 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0147`（family 0009，源第 877 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0158`（family 0006，源第 158 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0159`（family 0008，源第 455 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0088`（family 0008，源第 553 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0198`（family 0009，源第 928 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0052`（family 0006，源第 52 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0163`（family 0008，源第 459 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0250`（family 0008，源第 715 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0073`（family 0009，源第 803 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0132`（family 0006，源第 132 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0089`（family 0008，源第 385 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0124`（family 0008，源第 589 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0102`（family 0009，源第 832 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0098`（family 0006，源第 98 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0167`（family 0008，源第 463 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0144`（family 0008，源第 609 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0168`（family 0009，源第 898 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0082`（family 0006，源第 82 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0012`（family 0008，源第 308 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0223`（family 0008，源第 688 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0012`（family 0009，源第 742 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0164`（family 0006，源第 164 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0132`（family 0008，源第 428 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0073`（family 0008，源第 538 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0203`（family 0009，源第 933 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0018`（family 0006，源第 18 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0013`（family 0008，源第 309 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0050`（family 0008，源第 515 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0210`（family 0009，源第 940 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0119`（family 0006，源第 119 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0101`（family 0008，源第 397 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0132`（family 0008，源第 597 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0214`（family 0009，源第 944 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0110`（family 0006，源第 110 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0133`（family 0008，源第 429 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0157`（family 0008，源第 622 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0069`（family 0009，源第 799 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0101`（family 0006，源第 101 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0071`（family 0008，源第 367 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0259`（family 0008，源第 724 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0087`（family 0009，源第 817 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0157`（family 0006，源第 157 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0120`（family 0008，源第 416 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0145`（family 0008，源第 610 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0196`（family 0009，源第 926 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0096`（family 0006，源第 96 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0041`（family 0008，源第 337 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0048`（family 0008，源第 513 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0206`（family 0009，源第 936 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0147`（family 0006，源第 147 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0127`（family 0008，源第 423 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0042`（family 0008，源第 507 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0114`（family 0009，源第 844 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0152`（family 0006，源第 152 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0134`（family 0008，源第 430 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0235`（family 0008，源第 700 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0142`（family 0009，源第 872 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0054`（family 0006，源第 54 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0169`（family 0008，源第 465 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0063`（family 0008，源第 528 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0129`（family 0009，源第 859 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0143`（family 0006，源第 143 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0119`（family 0008，源第 415 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0085`（family 0008，源第 550 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0075`（family 0009，源第 805 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0094`（family 0006，源第 94 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0121`（family 0008，源第 417 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0084`（family 0008，源第 549 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0115`（family 0009，源第 845 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0076`（family 0006，源第 76 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0070`（family 0008，源第 366 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0031`（family 0008，源第 496 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0065`（family 0009，源第 795 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0015`（family 0006，源第 15 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0060`（family 0008，源第 356 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0260`（family 0008，源第 725 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0202`（family 0009，源第 932 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0095`（family 0006，源第 95 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0148`（family 0008，源第 444 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0162`（family 0008，源第 627 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0090`（family 0009，源第 820 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0053`（family 0006，源第 53 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0123`（family 0008，源第 419 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0149`（family 0008，源第 614 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0071`（family 0009，源第 801 行）
- `EI-56TESTPK0006-easy-v1.2::assistant-0032`（family 0006，源第 32 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0062`（family 0008，源第 358 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0030`（family 0008，源第 495 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0216`（family 0009，源第 946 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0122`（family 0008，源第 418 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0098`（family 0008，源第 563 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0167`（family 0009，源第 897 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0059`（family 0008，源第 355 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0200`（family 0008，源第 665 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0076`（family 0009，源第 806 行）
- `EI-56TESTPK0008-easy-v1.2::assistant-0058`（family 0008，源第 354 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0129`（family 0008，源第 594 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0044`（family 0009，源第 774 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0216`（family 0008，源第 681 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0211`（family 0009，源第 941 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0156`（family 0008，源第 621 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0060`（family 0009，源第 790 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0041`（family 0008，源第 506 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0205`（family 0009，源第 935 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0137`（family 0008，源第 602 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0057`（family 0009，源第 787 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0161`（family 0008，源第 626 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0175`（family 0009，源第 905 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0163`（family 0008，源第 628 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0050`（family 0009，源第 780 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0102`（family 0008，源第 567 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0156`（family 0009，源第 886 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0189`（family 0008，源第 654 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0081`（family 0009，源第 811 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0209`（family 0008，源第 674 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0213`（family 0009，源第 943 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0188`（family 0008，源第 653 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0018`（family 0009，源第 748 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0185`（family 0008，源第 650 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0079`（family 0009，源第 809 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0141`（family 0008，源第 606 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0176`（family 0009，源第 906 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0113`（family 0008，源第 578 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0016`（family 0009，源第 746 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0027`（family 0008，源第 492 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0177`（family 0009，源第 907 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0066`（family 0008，源第 531 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0127`（family 0009，源第 857 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0035`（family 0008，源第 500 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0172`（family 0009，源第 902 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0244`（family 0008，源第 709 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0125`（family 0009，源第 855 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0052`（family 0008，源第 517 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0015`（family 0009，源第 745 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0138`（family 0008，源第 603 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0212`（family 0009，源第 942 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0221`（family 0008，源第 686 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0010`（family 0009，源第 740 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0246`（family 0008，源第 711 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0105`（family 0009，源第 835 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0021`（family 0008，源第 486 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0036`（family 0009，源第 766 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0147`（family 0008，源第 612 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0178`（family 0009，源第 908 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0184`（family 0008，源第 649 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0037`（family 0009，源第 767 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0211`（family 0008，源第 676 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0159`（family 0009，源第 889 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0206`（family 0008，源第 671 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0157`（family 0009，源第 887 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0107`（family 0008，源第 572 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0131`（family 0009，源第 861 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0130`（family 0008，源第 595 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0222`（family 0009，源第 952 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0247`（family 0008，源第 712 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0180`（family 0009，源第 910 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0054`（family 0008，源第 519 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0042`（family 0009，源第 772 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0103`（family 0008，源第 568 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0215`（family 0009，源第 945 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0104`（family 0008，源第 569 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0155`（family 0009，源第 885 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0077`（family 0008，源第 542 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0217`（family 0009，源第 947 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0256`（family 0008，源第 721 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0184`（family 0009，源第 914 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0121`（family 0008，源第 586 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0219`（family 0009，源第 949 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0086`（family 0008，源第 551 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0151`（family 0009，源第 881 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0239`（family 0008，源第 704 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0128`（family 0009，源第 858 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0258`（family 0008，源第 723 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0145`（family 0009，源第 875 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0220`（family 0008，源第 685 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0200`（family 0009，源第 930 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0062`（family 0008，源第 527 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0185`（family 0009，源第 915 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0226`（family 0008，源第 691 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0220`（family 0009，源第 950 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0237`（family 0008，源第 702 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0221`（family 0009，源第 951 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0171`（family 0008，源第 636 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0136`（family 0009，源第 866 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0026`（family 0008，源第 491 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0038`（family 0009，源第 768 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0134`（family 0008，源第 599 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0027`（family 0009，源第 757 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0252`（family 0008，源第 717 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0026`（family 0009，源第 756 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0076`（family 0008，源第 541 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0144`（family 0009，源第 874 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0224`（family 0008，源第 689 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0107`（family 0009，源第 837 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0195`（family 0008，源第 660 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0146`（family 0009，源第 876 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0203`（family 0008，源第 668 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0106`（family 0009，源第 836 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0120`（family 0008，源第 585 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0113`（family 0009，源第 843 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0261`（family 0008，源第 726 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0143`（family 0009，源第 873 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0263`（family 0008，源第 728 行）
- `EI-56TESTPK0009-medium-v1.2::assistant-0029`（family 0009，源第 759 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0225`（family 0008，源第 690 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0053`（family 0008，源第 518 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0255`（family 0008，源第 720 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0257`（family 0008，源第 722 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0019`（family 0008，源第 484 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0177`（family 0008，源第 642 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0219`（family 0008，源第 684 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0227`（family 0008，源第 692 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0024`（family 0008，源第 489 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0023`（family 0008，源第 488 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0183`（family 0008，源第 648 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0218`（family 0008，源第 683 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0122`（family 0008，源第 587 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0154`（family 0008，源第 619 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0207`（family 0008，源第 672 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0232`（family 0008，源第 697 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0170`（family 0008，源第 635 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0262`（family 0008，源第 727 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0135`（family 0008，源第 600 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0217`（family 0008，源第 682 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0192`（family 0008，源第 657 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0175`（family 0008，源第 640 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0265`（family 0008，源第 730 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0193`（family 0008，源第 658 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0186`（family 0008，源第 651 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0166`（family 0008，源第 631 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0071`（family 0008，源第 536 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0017`（family 0008，源第 482 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0179`（family 0008，源第 644 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0182`（family 0008，源第 647 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0065`（family 0008，源第 530 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0254`（family 0008，源第 719 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0253`（family 0008，源第 718 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0143`（family 0008，源第 608 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0172`（family 0008，源第 637 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0046`（family 0008，源第 511 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0151`（family 0008，源第 616 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0168`（family 0008，源第 633 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0140`（family 0008，源第 605 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0173`（family 0008，源第 638 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0167`（family 0008，源第 632 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0061`（family 0008，源第 526 行）
- `EI-56TESTPK0008-medium-v1.2::assistant-0136`（family 0008，源第 601 行）

验证样本：

- `EI-56TESTPK0010-easy-v1.2::assistant-0001`（family 0010，源第 1 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0001`（family 0010，源第 456 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0002`（family 0010，源第 2 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0002`（family 0010，源第 457 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0003`（family 0010，源第 3 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0003`（family 0010，源第 458 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0004`（family 0010，源第 4 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0004`（family 0010，源第 459 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0005`（family 0010，源第 5 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0005`（family 0010，源第 460 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0008`（family 0010，源第 8 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0006`（family 0010，源第 461 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0006`（family 0010，源第 6 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0023`（family 0010，源第 478 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0017`（family 0010，源第 17 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0008`（family 0010，源第 463 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0014`（family 0010，源第 14 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0026`（family 0010，源第 481 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0007`（family 0010，源第 7 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0007`（family 0010，源第 462 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0012`（family 0010，源第 12 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0029`（family 0010，源第 484 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0031`（family 0010，源第 31 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0010`（family 0010，源第 465 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0058`（family 0010，源第 58 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0021`（family 0010，源第 476 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0074`（family 0010，源第 74 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0039`（family 0010，源第 494 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0090`（family 0010，源第 90 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0050`（family 0010，源第 505 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0113`（family 0010，源第 113 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0033`（family 0010，源第 488 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0065`（family 0010，源第 65 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0020`（family 0010，源第 475 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0095`（family 0010，源第 95 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0068`（family 0010，源第 523 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0119`（family 0010，源第 119 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0156`（family 0010，源第 611 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0089`（family 0010，源第 89 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0097`（family 0010，源第 552 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0107`（family 0010，源第 107 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0028`（family 0010，源第 483 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0044`（family 0010，源第 44 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0103`（family 0010，源第 558 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0068`（family 0010，源第 68 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0104`（family 0010，源第 559 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0072`（family 0010，源第 72 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0191`（family 0010，源第 646 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0064`（family 0010，源第 64 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0190`（family 0010，源第 645 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0136`（family 0010，源第 136 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0111`（family 0010，源第 566 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0075`（family 0010，源第 75 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0046`（family 0010，源第 501 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0062`（family 0010，源第 62 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0083`（family 0010，源第 538 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0383`（family 0010，源第 383 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0076`（family 0010，源第 531 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0018`（family 0010，源第 18 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0011`（family 0010，源第 466 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0103`（family 0010，源第 103 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0055`（family 0010，源第 510 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0061`（family 0010，源第 61 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0047`（family 0010，源第 502 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0325`（family 0010，源第 325 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0173`（family 0010，源第 628 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0111`（family 0010，源第 111 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0082`（family 0010，源第 537 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0127`（family 0010，源第 127 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0096`（family 0010，源第 551 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0176`（family 0010，源第 176 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0086`（family 0010，源第 541 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0120`（family 0010，源第 120 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0101`（family 0010，源第 556 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0049`（family 0010，源第 49 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0059`（family 0010，源第 514 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0011`（family 0010，源第 11 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0108`（family 0010，源第 563 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0344`（family 0010，源第 344 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0194`（family 0010，源第 649 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0055`（family 0010，源第 55 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0062`（family 0010，源第 517 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0412`（family 0010，源第 412 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0163`（family 0010，源第 618 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0168`（family 0010，源第 168 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0089`（family 0010，源第 544 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0010`（family 0010，源第 10 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0165`（family 0010，源第 620 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0400`（family 0010，源第 400 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0069`（family 0010，源第 524 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0167`（family 0010，源第 167 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0186`（family 0010，源第 641 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0091`（family 0010，源第 91 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0042`（family 0010，源第 497 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0343`（family 0010，源第 343 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0070`（family 0010，源第 525 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0375`（family 0010，源第 375 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0049`（family 0010，源第 504 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0046`（family 0010，源第 46 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0012`（family 0010，源第 467 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0081`（family 0010，源第 81 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0167`（family 0010，源第 622 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0083`（family 0010，源第 83 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0056`（family 0010，源第 511 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0444`（family 0010，源第 444 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0120`（family 0010，源第 575 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0082`（family 0010，源第 82 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0022`（family 0010，源第 477 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0225`（family 0010，源第 225 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0100`（family 0010，源第 555 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0032`（family 0010，源第 32 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0152`（family 0010，源第 607 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0255`（family 0010，源第 255 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0044`（family 0010，源第 499 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0237`（family 0010，源第 237 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0091`（family 0010，源第 546 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0099`（family 0010，源第 99 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0107`（family 0010，源第 562 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0071`（family 0010，源第 71 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0187`（family 0010，源第 642 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0027`（family 0010，源第 27 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0168`（family 0010，源第 623 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0134`（family 0010，源第 134 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0141`（family 0010，源第 596 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0403`（family 0010，源第 403 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0078`（family 0010，源第 533 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0158`（family 0010，源第 158 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0063`（family 0010，源第 518 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0009`（family 0010，源第 9 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0045`（family 0010，源第 500 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0191`（family 0010，源第 191 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0066`（family 0010，源第 521 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0038`（family 0010，源第 38 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0155`（family 0010，源第 610 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0078`（family 0010，源第 78 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0142`（family 0010，源第 597 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0359`（family 0010，源第 359 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0092`（family 0010，源第 547 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0171`（family 0010，源第 171 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0081`（family 0010，源第 536 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0330`（family 0010，源第 330 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0110`（family 0010，源第 565 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0178`（family 0010，源第 178 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0065`（family 0010，源第 520 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0215`（family 0010，源第 215 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0158`（family 0010，源第 613 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0231`（family 0010，源第 231 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0074`（family 0010，源第 529 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0270`（family 0010，源第 270 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0212`（family 0010，源第 667 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0019`（family 0010，源第 19 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0075`（family 0010，源第 530 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0390`（family 0010，源第 390 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0114`（family 0010，源第 569 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0087`（family 0010，源第 87 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0149`（family 0010，源第 604 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0066`（family 0010，源第 66 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0153`（family 0010，源第 608 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0121`（family 0010，源第 121 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0213`（family 0010，源第 668 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0219`（family 0010，源第 219 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0109`（family 0010，源第 564 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0094`（family 0010，源第 94 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0054`（family 0010，源第 509 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0070`（family 0010，源第 70 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0027`（family 0010，源第 482 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0128`（family 0010，源第 128 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0038`（family 0010，源第 493 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0203`（family 0010，源第 203 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0146`（family 0010，源第 601 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0264`（family 0010，源第 264 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0051`（family 0010，源第 506 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0093`（family 0010，源第 93 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0157`（family 0010，源第 612 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0389`（family 0010，源第 389 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0064`（family 0010，源第 519 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0163`（family 0010，源第 163 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0084`（family 0010，源第 539 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0067`（family 0010，源第 67 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0085`（family 0010，源第 540 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0182`（family 0010，源第 182 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0196`（family 0010，源第 651 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0290`（family 0010，源第 290 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0040`（family 0010，源第 495 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0244`（family 0010，源第 244 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0077`（family 0010，源第 532 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0268`（family 0010，源第 268 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0144`（family 0010，源第 599 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0419`（family 0010，源第 419 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0145`（family 0010，源第 600 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0135`（family 0010，源第 135 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0139`（family 0010，源第 594 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0155`（family 0010，源第 155 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0162`（family 0010，源第 617 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0345`（family 0010，源第 345 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0048`（family 0010，源第 503 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0170`（family 0010，源第 170 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0189`（family 0010，源第 644 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0440`（family 0010，源第 440 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0201`（family 0010，源第 656 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0342`（family 0010，源第 342 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0177`（family 0010，源第 632 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0224`（family 0010，源第 224 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0067`（family 0010，源第 522 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0108`（family 0010，源第 108 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0035`（family 0010，源第 490 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0319`（family 0010，源第 319 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0175`（family 0010，源第 630 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0392`（family 0010，源第 392 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0052`（family 0010，源第 507 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0377`（family 0010，源第 377 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0133`（family 0010，源第 588 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0258`（family 0010，源第 258 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0041`（family 0010，源第 496 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0205`（family 0010，源第 205 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0072`（family 0010，源第 527 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0184`（family 0010，源第 184 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0138`（family 0010，源第 593 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0186`（family 0010，源第 186 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0113`（family 0010，源第 568 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0160`（family 0010，源第 160 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0122`（family 0010，源第 577 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0352`（family 0010，源第 352 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0140`（family 0010，源第 595 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0283`（family 0010，源第 283 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0209`（family 0010，源第 664 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0350`（family 0010，源第 350 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0036`（family 0010，源第 491 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0353`（family 0010，源第 353 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0105`（family 0010，源第 560 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0381`（family 0010，源第 381 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0169`（family 0010，源第 624 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0432`（family 0010，源第 432 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0102`（family 0010，源第 557 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0159`（family 0010，源第 159 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0043`（family 0010，源第 498 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0278`（family 0010，源第 278 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0170`（family 0010，源第 625 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0122`（family 0010，源第 122 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0025`（family 0010，源第 480 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0253`（family 0010，源第 253 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0079`（family 0010，源第 534 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0269`（family 0010，源第 269 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0192`（family 0010，源第 647 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0043`（family 0010，源第 43 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0172`（family 0010，源第 627 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0194`（family 0010，源第 194 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0159`（family 0010，源第 614 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0306`（family 0010，源第 306 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0030`（family 0010，源第 485 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0356`（family 0010，源第 356 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0161`（family 0010，源第 616 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0365`（family 0010，源第 365 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0073`（family 0010，源第 528 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0443`（family 0010，源第 443 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0093`（family 0010，源第 548 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0421`（family 0010，源第 421 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0053`（family 0010，源第 508 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0406`（family 0010，源第 406 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0080`（family 0010，源第 535 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0166`（family 0010，源第 166 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0174`（family 0010，源第 629 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0435`（family 0010，源第 435 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0106`（family 0010，源第 561 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0272`（family 0010，源第 272 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0017`（family 0010，源第 472 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0281`（family 0010，源第 281 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0179`（family 0010，源第 634 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0030`（family 0010，源第 30 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0195`（family 0010，源第 650 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0240`（family 0010，源第 240 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0013`（family 0010，源第 468 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0034`（family 0010，源第 34 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0188`（family 0010，源第 643 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0429`（family 0010，源第 429 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0118`（family 0010，源第 573 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0251`（family 0010，源第 251 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0018`（family 0010，源第 473 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0123`（family 0010，源第 123 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0071`（family 0010，源第 526 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0211`（family 0010，源第 211 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0009`（family 0010，源第 464 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0172`（family 0010，源第 172 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0112`（family 0010，源第 567 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0331`（family 0010，源第 331 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0099`（family 0010，源第 554 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0357`（family 0010，源第 357 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0123`（family 0010，源第 578 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0348`（family 0010，源第 348 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0180`（family 0010，源第 635 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0416`（family 0010，源第 416 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0210`（family 0010，源第 665 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0355`（family 0010，源第 355 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0219`（family 0010，源第 674 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0035`（family 0010，源第 35 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0211`（family 0010，源第 666 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0079`（family 0010，源第 79 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0181`（family 0010，源第 636 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0125`（family 0010，源第 125 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0037`（family 0010，源第 492 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0300`（family 0010，源第 300 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0116`（family 0010，源第 571 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0088`（family 0010，源第 88 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0185`（family 0010，源第 640 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0229`（family 0010，源第 229 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0119`（family 0010，源第 574 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0271`（family 0010，源第 271 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0208`（family 0010，源第 663 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0133`（family 0010，源第 133 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0060`（family 0010，源第 515 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0410`（family 0010，源第 410 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0024`（family 0010，源第 479 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0433`（family 0010，源第 433 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0166`（family 0010，源第 621 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0201`（family 0010，源第 201 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0218`（family 0010，源第 673 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0246`（family 0010，源第 246 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0117`（family 0010，源第 572 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0048`（family 0010，源第 48 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0164`（family 0010，源第 619 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0366`（family 0010，源第 366 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0216`（family 0010，源第 671 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0059`（family 0010，源第 59 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0090`（family 0010，源第 545 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0441`（family 0010，源第 441 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0121`（family 0010，源第 576 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0216`（family 0010，源第 216 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0016`（family 0010，源第 471 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0181`（family 0010，源第 181 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0150`（family 0010，源第 605 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0131`（family 0010，源第 131 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0151`（family 0010，源第 606 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0317`（family 0010，源第 317 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0015`（family 0010，源第 470 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0394`（family 0010，源第 394 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0019`（family 0010，源第 474 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0349`（family 0010，源第 349 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0215`（family 0010，源第 670 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0378`（family 0010，源第 378 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0160`（family 0010，源第 615 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0222`（family 0010，源第 222 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0014`（family 0010，源第 469 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0227`（family 0010，源第 227 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0135`（family 0010，源第 590 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0249`（family 0010，源第 249 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0143`（family 0010，源第 598 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0259`（family 0010，源第 259 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0198`（family 0010，源第 653 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0263`（family 0010，源第 263 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0171`（family 0010，源第 626 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0050`（family 0010，源第 50 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0098`（family 0010，源第 553 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0036`（family 0010，源第 36 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0129`（family 0010，源第 584 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0200`（family 0010，源第 200 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0184`（family 0010，源第 639 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0448`（family 0010，源第 448 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0094`（family 0010，源第 549 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0414`（family 0010，源第 414 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0034`（family 0010，源第 489 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0106`（family 0010，源第 106 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0057`（family 0010，源第 512 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0152`（family 0010，源第 152 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0154`（family 0010，源第 609 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0098`（family 0010，源第 98 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0205`（family 0010，源第 660 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0288`（family 0010，源第 288 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0176`（family 0010，源第 631 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0073`（family 0010，源第 73 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0088`（family 0010，源第 543 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0085`（family 0010，源第 85 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0032`（family 0010，源第 487 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0209`（family 0010，源第 209 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0204`（family 0010，源第 659 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0257`（family 0010，源第 257 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0207`（family 0010，源第 662 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0040`（family 0010，源第 40 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0124`（family 0010，源第 579 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0175`（family 0010，源第 175 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0217`（family 0010，源第 672 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0241`（family 0010，源第 241 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0137`（family 0010，源第 592 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0427`（family 0010，源第 427 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0214`（family 0010，源第 669 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0114`（family 0010，源第 114 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0127`（family 0010，源第 582 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0372`（family 0010，源第 372 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0115`（family 0010，源第 570 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0418`（family 0010，源第 418 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0134`（family 0010，源第 589 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0016`（family 0010，源第 16 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0136`（family 0010，源第 591 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0217`（family 0010，源第 217 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0148`（family 0010，源第 603 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0286`（family 0010，源第 286 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0132`（family 0010，源第 587 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0126`（family 0010，源第 126 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0193`（family 0010，源第 648 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0185`（family 0010，源第 185 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0128`（family 0010，源第 583 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0266`（family 0010，源第 266 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0197`（family 0010，源第 652 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0454`（family 0010，源第 454 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0206`（family 0010，源第 661 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0104`（family 0010，源第 104 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0178`（family 0010，源第 633 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0223`（family 0010，源第 223 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0220`（family 0010，源第 675 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0202`（family 0010，源第 202 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0147`（family 0010，源第 602 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0415`（family 0010，源第 415 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0130`（family 0010，源第 585 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0318`（family 0010，源第 318 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0200`（family 0010，源第 655 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0316`（family 0010，源第 316 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0095`（family 0010，源第 550 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0302`（family 0010，源第 302 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0202`（family 0010，源第 657 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0423`（family 0010，源第 423 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0203`（family 0010，源第 658 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0340`（family 0010，源第 340 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0199`（family 0010，源第 654 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0333`（family 0010，源第 333 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0183`（family 0010，源第 638 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0169`（family 0010，源第 169 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0182`（family 0010，源第 637 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0393`（family 0010，源第 393 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0061`（family 0010，源第 516 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0045`（family 0010，源第 45 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0126`（family 0010，源第 581 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0276`（family 0010，源第 276 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0131`（family 0010，源第 586 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0179`（family 0010，源第 179 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0087`（family 0010，源第 542 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0368`（family 0010，源第 368 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0058`（family 0010，源第 513 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0187`（family 0010，源第 187 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0125`（family 0010，源第 580 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0165`（family 0010，源第 165 行）
- `EI-56TESTPK0010-medium-v1.2::assistant-0031`（family 0010，源第 486 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0060`（family 0010，源第 60 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0156`（family 0010，源第 156 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0138`（family 0010，源第 138 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0324`（family 0010，源第 324 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0434`（family 0010，源第 434 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0405`（family 0010，源第 405 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0346`（family 0010，源第 346 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0109`（family 0010，源第 109 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0130`（family 0010，源第 130 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0180`（family 0010，源第 180 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0341`（family 0010，源第 341 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0157`（family 0010，源第 157 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0387`（family 0010，源第 387 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0129`（family 0010，源第 129 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0105`（family 0010，源第 105 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0351`（family 0010，源第 351 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0242`（family 0010，源第 242 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0282`（family 0010，源第 282 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0338`（family 0010，源第 338 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0369`（family 0010，源第 369 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0284`（family 0010，源第 284 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0289`（family 0010，源第 289 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0063`（family 0010，源第 63 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0339`（family 0010，源第 339 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0092`（family 0010，源第 92 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0304`（family 0010，源第 304 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0280`（family 0010，源第 280 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0188`（family 0010，源第 188 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0204`（family 0010，源第 204 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0221`（family 0010，源第 221 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0153`（family 0010，源第 153 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0239`（family 0010，源第 239 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0254`（family 0010，源第 254 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0364`（family 0010，源第 364 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0022`（family 0010，源第 22 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0373`（family 0010，源第 373 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0407`（family 0010，源第 407 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0084`（family 0010，源第 84 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0144`（family 0010，源第 144 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0367`（family 0010，源第 367 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0151`（family 0010，源第 151 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0195`（family 0010，源第 195 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0279`（family 0010，源第 279 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0303`（family 0010，源第 303 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0408`（family 0010，源第 408 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0086`（family 0010，源第 86 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0235`（family 0010，源第 235 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0218`（family 0010，源第 218 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0056`（family 0010，源第 56 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0228`（family 0010，源第 228 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0147`（family 0010，源第 147 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0198`（family 0010，源第 198 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0321`（family 0010，源第 321 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0069`（family 0010，源第 69 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0247`（family 0010，源第 247 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0232`（family 0010，源第 232 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0124`（family 0010，源第 124 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0132`（family 0010，源第 132 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0267`（family 0010，源第 267 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0291`（family 0010，源第 291 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0025`（family 0010，源第 25 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0077`（family 0010，源第 77 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0145`（family 0010，源第 145 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0273`（family 0010，源第 273 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0076`（family 0010，源第 76 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0436`（family 0010，源第 436 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0102`（family 0010，源第 102 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0424`（family 0010，源第 424 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0347`（family 0010，源第 347 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0037`（family 0010，源第 37 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0112`（family 0010，源第 112 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0173`（family 0010，源第 173 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0139`（family 0010，源第 139 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0376`（family 0010，源第 376 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0430`（family 0010，源第 430 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0226`（family 0010，源第 226 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0052`（family 0010，源第 52 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0447`（family 0010，源第 447 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0039`（family 0010，源第 39 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0051`（family 0010，源第 51 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0298`（family 0010，源第 298 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0397`（family 0010，源第 397 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0141`（family 0010，源第 141 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0250`（family 0010，源第 250 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0446`（family 0010，源第 446 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0015`（family 0010，源第 15 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0252`（family 0010，源第 252 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0233`（family 0010，源第 233 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0322`（family 0010，源第 322 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0285`（family 0010，源第 285 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0360`（family 0010，源第 360 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0146`（family 0010，源第 146 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0382`（family 0010，源第 382 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0230`（family 0010，源第 230 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0275`（family 0010，源第 275 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0143`（family 0010，源第 143 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0162`（family 0010，源第 162 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0150`（family 0010，源第 150 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0362`（family 0010，源第 362 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0234`（family 0010，源第 234 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0154`（family 0010，源第 154 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0256`（family 0010，源第 256 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0315`（family 0010，源第 315 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0374`（family 0010，源第 374 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0023`（family 0010，源第 23 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0110`（family 0010，源第 110 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0307`（family 0010，源第 307 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0248`（family 0010，源第 248 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0336`（family 0010，源第 336 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0189`（family 0010，源第 189 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0190`（family 0010，源第 190 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0326`（family 0010，源第 326 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0401`（family 0010，源第 401 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0057`（family 0010，源第 57 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0149`（family 0010，源第 149 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0391`（family 0010，源第 391 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0323`（family 0010，源第 323 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0097`（family 0010，源第 97 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0449`（family 0010，源第 449 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0174`（family 0010，源第 174 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0413`（family 0010，源第 413 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0142`（family 0010，源第 142 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0033`（family 0010，源第 33 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0261`（family 0010，源第 261 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0439`（family 0010，源第 439 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0161`（family 0010，源第 161 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0220`（family 0010，源第 220 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0361`（family 0010，源第 361 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0137`（family 0010，源第 137 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0308`（family 0010，源第 308 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0386`（family 0010，源第 386 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0385`（family 0010，源第 385 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0238`（family 0010，源第 238 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0358`（family 0010，源第 358 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0210`（family 0010，源第 210 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0243`（family 0010，源第 243 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0311`（family 0010，源第 311 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0047`（family 0010，源第 47 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0262`（family 0010，源第 262 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0363`（family 0010，源第 363 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0299`（family 0010，源第 299 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0277`（family 0010，源第 277 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0379`（family 0010，源第 379 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0327`（family 0010，源第 327 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0287`（family 0010，源第 287 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0354`（family 0010，源第 354 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0260`（family 0010，源第 260 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0335`（family 0010，源第 335 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0148`（family 0010，源第 148 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0101`（family 0010，源第 101 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0328`（family 0010，源第 328 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0380`（family 0010，源第 380 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0314`（family 0010，源第 314 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0301`（family 0010，源第 301 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0337`（family 0010，源第 337 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0294`（family 0010，源第 294 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0080`（family 0010，源第 80 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0332`（family 0010，源第 332 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0177`（family 0010，源第 177 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0404`（family 0010，源第 404 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0305`（family 0010，源第 305 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0028`（family 0010，源第 28 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0438`（family 0010，源第 438 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0442`（family 0010，源第 442 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0274`（family 0010，源第 274 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0265`（family 0010，源第 265 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0041`（family 0010，源第 41 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0320`（family 0010，源第 320 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0100`（family 0010，源第 100 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0313`（family 0010，源第 313 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0371`（family 0010，源第 371 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0208`（family 0010，源第 208 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0370`（family 0010，源第 370 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0199`（family 0010，源第 199 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0024`（family 0010，源第 24 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0297`（family 0010，源第 297 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0428`（family 0010，源第 428 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0020`（family 0010，源第 20 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0329`（family 0010，源第 329 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0334`（family 0010，源第 334 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0388`（family 0010，源第 388 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0140`（family 0010，源第 140 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0021`（family 0010，源第 21 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0053`（family 0010，源第 53 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0164`（family 0010，源第 164 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0450`（family 0010，源第 450 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0453`（family 0010，源第 453 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0245`（family 0010，源第 245 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0455`（family 0010，源第 455 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0029`（family 0010，源第 29 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0310`（family 0010，源第 310 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0183`（family 0010，源第 183 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0312`（family 0010，源第 312 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0309`（family 0010，源第 309 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0096`（family 0010，源第 96 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0207`（family 0010，源第 207 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0197`（family 0010，源第 197 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0212`（family 0010，源第 212 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0292`（family 0010，源第 292 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0431`（family 0010，源第 431 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0054`（family 0010，源第 54 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0417`（family 0010，源第 417 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0115`（family 0010，源第 115 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0236`（family 0010，源第 236 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0116`（family 0010，源第 116 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0117`（family 0010，源第 117 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0399`（family 0010，源第 399 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0213`（family 0010，源第 213 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0437`（family 0010，源第 437 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0451`（family 0010，源第 451 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0013`（family 0010，源第 13 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0426`（family 0010，源第 426 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0384`（family 0010，源第 384 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0214`（family 0010，源第 214 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0425`（family 0010，源第 425 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0026`（family 0010，源第 26 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0452`（family 0010，源第 452 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0402`（family 0010，源第 402 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0420`（family 0010，源第 420 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0118`（family 0010，源第 118 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0295`（family 0010，源第 295 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0193`（family 0010，源第 193 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0396`（family 0010，源第 396 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0422`（family 0010，源第 422 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0409`（family 0010，源第 409 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0296`（family 0010，源第 296 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0445`（family 0010，源第 445 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0196`（family 0010，源第 196 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0395`（family 0010，源第 395 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0411`（family 0010，源第 411 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0293`（family 0010，源第 293 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0398`（family 0010，源第 398 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0206`（family 0010，源第 206 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0192`（family 0010，源第 192 行）
- `EI-56TESTPK0010-easy-v1.2::assistant-0042`（family 0010，源第 42 行）

## 6. 训练与验证结果

- 可训练参数：21,823,488 / 8,212,558,848（0.2657%）
- 优化步：476
- 训练阶段用时：3929.61 秒
- 验证 completion target tokens：129046
- 验证 loss：0.741419
- 验证 perplexity：2.0989

| step | 双 rank 平均 train loss | 累计时间 |
|---:|---:|---:|
| 1 | 1.304241 | 7.31 s |
| 2 | 1.854931 | 14.72 s |
| 3 | 0.901811 | 22.50 s |
| 4 | 0.742411 | 29.06 s |
| 5 | 0.963795 | 36.47 s |
| 6 | 1.228386 | 44.46 s |
| 7 | 1.030016 | 50.28 s |
| 8 | 0.420403 | 59.58 s |
| 9 | 1.333092 | 66.84 s |
| 10 | 0.292791 | 76.10 s |
| 11 | 1.606871 | 83.51 s |
| 12 | 0.906561 | 91.02 s |
| 13 | 1.009777 | 97.95 s |
| 14 | 1.083581 | 108.31 s |
| 15 | 0.749889 | 116.57 s |
| 16 | 0.852040 | 123.10 s |
| 17 | 0.233821 | 129.61 s |
| 18 | 0.644563 | 136.59 s |
| 19 | 0.862233 | 143.25 s |
| 20 | 0.706729 | 150.20 s |
| 21 | 0.846196 | 156.99 s |
| 22 | 0.549466 | 163.84 s |
| 23 | 0.331797 | 170.35 s |
| 24 | 1.398388 | 178.28 s |
| 25 | 0.931067 | 186.09 s |
| 26 | 0.548296 | 192.29 s |
| 27 | 0.325320 | 198.54 s |
| 28 | 0.377810 | 205.55 s |
| 29 | 1.468883 | 211.76 s |
| 30 | 0.431153 | 219.96 s |
| 31 | 0.815160 | 227.80 s |
| 32 | 0.692296 | 234.88 s |
| 33 | 0.616351 | 242.67 s |
| 34 | 0.701574 | 252.06 s |
| 35 | 0.297069 | 258.85 s |
| 36 | 0.490580 | 267.17 s |
| 37 | 0.583800 | 275.88 s |
| 38 | 1.010257 | 281.71 s |
| 39 | 0.708179 | 289.08 s |
| 40 | 1.388166 | 296.62 s |
| 41 | 1.541639 | 305.01 s |
| 42 | 1.060945 | 312.83 s |
| 43 | 0.673035 | 319.32 s |
| 44 | 0.626864 | 325.08 s |
| 45 | 0.906203 | 331.92 s |
| 46 | 0.383245 | 338.55 s |
| 47 | 0.507641 | 345.46 s |
| 48 | 0.911742 | 353.24 s |
| 49 | 0.655418 | 361.37 s |
| 50 | 0.734797 | 367.62 s |
| 51 | 0.339262 | 373.40 s |
| 52 | 0.720760 | 379.86 s |
| 53 | 0.719850 | 385.73 s |
| 54 | 0.497443 | 394.11 s |
| 55 | 0.866317 | 402.37 s |
| 56 | 0.589141 | 410.09 s |
| 57 | 1.235495 | 418.02 s |
| 58 | 0.594090 | 424.82 s |
| 59 | 0.301563 | 431.21 s |
| 60 | 0.749956 | 439.09 s |
| 61 | 0.601609 | 444.44 s |
| 62 | 1.187901 | 450.98 s |
| 63 | 0.926203 | 456.62 s |
| 64 | 0.597285 | 464.14 s |
| 65 | 0.398375 | 472.79 s |
| 66 | 0.747056 | 478.84 s |
| 67 | 1.307728 | 487.17 s |
| 68 | 0.223676 | 493.71 s |
| 69 | 0.953886 | 499.86 s |
| 70 | 0.721419 | 507.32 s |
| 71 | 0.463519 | 514.11 s |
| 72 | 0.263115 | 520.73 s |
| 73 | 0.681810 | 527.34 s |
| 74 | 1.448582 | 535.14 s |
| 75 | 0.388514 | 543.09 s |
| 76 | 0.803172 | 549.35 s |
| 77 | 0.864071 | 555.86 s |
| 78 | 0.823840 | 562.75 s |
| 79 | 0.608145 | 569.24 s |
| 80 | 1.065708 | 575.81 s |
| 81 | 0.167876 | 583.07 s |
| 82 | 0.414040 | 592.95 s |
| 83 | 0.959176 | 599.63 s |
| 84 | 0.790850 | 605.03 s |
| 85 | 0.848648 | 612.94 s |
| 86 | 0.675318 | 621.27 s |
| 87 | 0.966173 | 627.93 s |
| 88 | 0.117269 | 636.09 s |
| 89 | 0.684878 | 643.99 s |
| 90 | 1.530401 | 652.79 s |
| 91 | 0.975360 | 659.40 s |
| 92 | 0.409904 | 666.02 s |
| 93 | 0.404467 | 673.28 s |
| 94 | 0.715218 | 681.86 s |
| 95 | 0.415361 | 687.90 s |
| 96 | 0.686464 | 695.79 s |
| 97 | 0.752952 | 702.23 s |
| 98 | 0.515399 | 708.08 s |
| 99 | 0.920740 | 718.27 s |
| 100 | 0.788669 | 725.96 s |
| 101 | 0.314088 | 733.34 s |
| 102 | 0.456358 | 739.13 s |
| 103 | 0.631014 | 745.16 s |
| 104 | 0.780405 | 751.74 s |
| 105 | 1.016462 | 759.16 s |
| 106 | 0.379432 | 765.99 s |
| 107 | 0.740455 | 773.70 s |
| 108 | 0.567062 | 783.38 s |
| 109 | 1.081231 | 791.32 s |
| 110 | 0.266763 | 798.27 s |
| 111 | 0.571851 | 805.73 s |
| 112 | 0.758445 | 812.71 s |
| 113 | 0.381123 | 819.56 s |
| 114 | 0.842807 | 827.83 s |
| 115 | 0.462141 | 835.68 s |
| 116 | 0.661115 | 842.72 s |
| 117 | 0.932001 | 850.18 s |
| 118 | 0.678278 | 857.64 s |
| 119 | 0.376923 | 863.80 s |
| 120 | 0.360675 | 869.96 s |
| 121 | 0.185983 | 878.21 s |
| 122 | 0.071786 | 885.00 s |
| 123 | 0.752482 | 892.79 s |
| 124 | 0.423680 | 899.76 s |
| 125 | 1.004210 | 905.63 s |
| 126 | 0.850486 | 912.67 s |
| 127 | 0.361268 | 918.71 s |
| 128 | 0.569082 | 924.03 s |
| 129 | 1.090432 | 930.46 s |
| 130 | 0.726183 | 936.58 s |
| 131 | 0.293230 | 944.80 s |
| 132 | 0.835965 | 950.96 s |
| 133 | 0.843852 | 958.34 s |
| 134 | 1.026546 | 967.56 s |
| 135 | 0.754928 | 974.24 s |
| 136 | 0.172426 | 980.01 s |
| 137 | 0.356628 | 986.13 s |
| 138 | 0.783944 | 993.95 s |
| 139 | 0.850214 | 1002.67 s |
| 140 | 0.167801 | 1008.71 s |
| 141 | 0.671971 | 1015.39 s |
| 142 | 0.826798 | 1021.64 s |
| 143 | 1.336669 | 1030.18 s |
| 144 | 0.425849 | 1037.56 s |
| 145 | 0.851638 | 1044.83 s |
| 146 | 0.381954 | 1052.16 s |
| 147 | 0.583796 | 1059.67 s |
| 148 | 0.786501 | 1066.31 s |
| 149 | 0.841650 | 1072.56 s |
| 150 | 0.685635 | 1079.17 s |
| 151 | 0.425817 | 1086.87 s |
| 152 | 0.903556 | 1095.05 s |
| 153 | 0.598531 | 1101.48 s |
| 154 | 0.581939 | 1107.55 s |
| 155 | 1.056728 | 1115.04 s |
| 156 | 0.898801 | 1123.21 s |
| 157 | 0.836223 | 1130.20 s |
| 158 | 0.722867 | 1137.20 s |
| 159 | 0.899124 | 1143.64 s |
| 160 | 0.956687 | 1151.79 s |
| 161 | 0.519067 | 1158.24 s |
| 162 | 0.526933 | 1166.50 s |
| 163 | 0.975142 | 1175.87 s |
| 164 | 0.561525 | 1182.88 s |
| 165 | 0.890960 | 1189.91 s |
| 166 | 0.375096 | 1196.86 s |
| 167 | 0.393291 | 1204.19 s |
| 168 | 0.508198 | 1211.89 s |
| 169 | 0.615415 | 1219.30 s |
| 170 | 0.246349 | 1226.66 s |
| 171 | 0.352221 | 1234.49 s |
| 172 | 0.884982 | 1242.86 s |
| 173 | 0.645884 | 1251.02 s |
| 174 | 0.414050 | 1257.20 s |
| 175 | 0.694162 | 1263.82 s |
| 176 | 1.045011 | 1270.78 s |
| 177 | 0.849705 | 1280.72 s |
| 178 | 1.184358 | 1286.18 s |
| 179 | 0.563114 | 1293.07 s |
| 180 | 0.115785 | 1301.91 s |
| 181 | 0.654311 | 1308.31 s |
| 182 | 0.620740 | 1315.97 s |
| 183 | 0.703811 | 1321.80 s |
| 184 | 0.504701 | 1328.01 s |
| 185 | 0.613068 | 1334.67 s |
| 186 | 0.644070 | 1340.83 s |
| 187 | 1.039931 | 1351.52 s |
| 188 | 0.217876 | 1356.90 s |
| 189 | 1.087406 | 1363.36 s |
| 190 | 0.670653 | 1373.73 s |
| 191 | 0.885019 | 1379.62 s |
| 192 | 0.416438 | 1385.66 s |
| 193 | 0.881734 | 1392.31 s |
| 194 | 0.805517 | 1400.54 s |
| 195 | 0.541967 | 1407.50 s |
| 196 | 0.564609 | 1414.05 s |
| 197 | 0.457487 | 1421.31 s |
| 198 | 0.324968 | 1428.23 s |
| 199 | 0.502703 | 1435.55 s |
| 200 | 0.271560 | 1444.12 s |
| 201 | 0.458334 | 1452.52 s |
| 202 | 0.876964 | 1459.82 s |
| 203 | 0.491274 | 1466.05 s |
| 204 | 0.517224 | 1472.69 s |
| 205 | 0.685944 | 1479.72 s |
| 206 | 0.637401 | 1485.61 s |
| 207 | 0.945203 | 1495.47 s |
| 208 | 0.512400 | 1503.13 s |
| 209 | 0.674368 | 1509.79 s |
| 210 | 0.384768 | 1517.99 s |
| 211 | 0.642058 | 1525.81 s |
| 212 | 0.414268 | 1532.68 s |
| 213 | 1.229475 | 1540.51 s |
| 214 | 0.878134 | 1548.89 s |
| 215 | 0.791816 | 1555.03 s |
| 216 | 0.088408 | 1566.40 s |
| 217 | 0.546623 | 1574.72 s |
| 218 | 0.685293 | 1581.71 s |
| 219 | 0.776369 | 1588.61 s |
| 220 | 0.954834 | 1595.45 s |
| 221 | 0.733563 | 1598.28 s |
| 222 | 0.218924 | 1606.21 s |
| 223 | 0.908654 | 1612.66 s |
| 224 | 1.134985 | 1621.41 s |
| 225 | 0.215978 | 1627.65 s |
| 226 | 0.472532 | 1635.16 s |
| 227 | 0.803617 | 1643.27 s |
| 228 | 0.497195 | 1650.07 s |
| 229 | 0.945902 | 1656.22 s |
| 230 | 0.538173 | 1662.05 s |
| 231 | 0.589226 | 1675.67 s |
| 232 | 0.986215 | 1683.61 s |
| 233 | 0.726401 | 1691.47 s |
| 234 | 0.979987 | 1698.02 s |
| 235 | 0.559023 | 1705.48 s |
| 236 | 0.417361 | 1713.83 s |
| 237 | 0.699736 | 1720.78 s |
| 238 | 0.396772 | 1727.43 s |
| 239 | 1.374303 | 1736.16 s |
| 240 | 0.542281 | 1742.36 s |
| 241 | 0.465134 | 1750.22 s |
| 242 | 0.350763 | 1756.29 s |
| 243 | 0.429560 | 1763.66 s |
| 244 | 0.785485 | 1770.60 s |
| 245 | 0.879201 | 1776.85 s |
| 246 | 0.121306 | 1783.25 s |
| 247 | 0.726732 | 1790.24 s |
| 248 | 0.458716 | 1798.06 s |
| 249 | 0.864352 | 1805.07 s |
| 250 | 0.639714 | 1811.88 s |
| 251 | 1.198378 | 1821.26 s |
| 252 | 0.440595 | 1828.10 s |
| 253 | 0.569857 | 1834.95 s |
| 254 | 1.133434 | 1843.66 s |
| 255 | 0.675522 | 1849.29 s |
| 256 | 0.563204 | 1856.23 s |
| 257 | 0.446614 | 1862.63 s |
| 258 | 0.123688 | 1869.16 s |
| 259 | 1.139344 | 1876.62 s |
| 260 | 0.752585 | 1884.95 s |
| 261 | 0.524435 | 1891.38 s |
| 262 | 1.416077 | 1898.80 s |
| 263 | 0.439030 | 1906.63 s |
| 264 | 0.787099 | 1913.07 s |
| 265 | 0.252782 | 1922.54 s |
| 266 | 0.497179 | 1931.79 s |
| 267 | 0.989270 | 1938.59 s |
| 268 | 0.511509 | 1946.05 s |
| 269 | 0.676284 | 1952.55 s |
| 270 | 1.164094 | 1962.39 s |
| 271 | 0.511630 | 1967.84 s |
| 272 | 0.785782 | 1974.31 s |
| 273 | 0.874959 | 1982.01 s |
| 274 | 0.920901 | 1988.17 s |
| 275 | 0.634496 | 1991.52 s |
| 276 | 0.744306 | 2000.35 s |
| 277 | 0.518476 | 2007.32 s |
| 278 | 0.255100 | 2013.47 s |
| 279 | 0.631623 | 2019.63 s |
| 280 | 0.624240 | 2026.90 s |
| 281 | 0.595136 | 2033.16 s |
| 282 | 0.772750 | 2041.82 s |
| 283 | 0.842484 | 2050.23 s |
| 284 | 0.381358 | 2057.54 s |
| 285 | 0.638503 | 2068.20 s |
| 286 | 1.247847 | 2077.40 s |
| 287 | 0.407265 | 2084.40 s |
| 288 | 0.670335 | 2090.20 s |
| 289 | 0.714808 | 2093.55 s |
| 290 | 0.466273 | 2100.38 s |
| 291 | 0.278355 | 2109.58 s |
| 292 | 0.506118 | 2116.38 s |
| 293 | 0.579748 | 2122.62 s |
| 294 | 0.255382 | 2129.16 s |
| 295 | 0.332562 | 2136.15 s |
| 296 | 0.941956 | 2143.55 s |
| 297 | 0.432778 | 2152.72 s |
| 298 | 0.901377 | 2159.66 s |
| 299 | 0.399150 | 2166.97 s |
| 300 | 0.237328 | 2174.75 s |
| 301 | 0.481142 | 2181.64 s |
| 302 | 0.946516 | 2187.92 s |
| 303 | 0.198831 | 2196.23 s |
| 304 | 0.312309 | 2203.22 s |
| 305 | 0.816173 | 2209.82 s |
| 306 | 0.460753 | 2217.76 s |
| 307 | 0.921242 | 2225.61 s |
| 308 | 0.793270 | 2233.31 s |
| 309 | 0.300680 | 2239.84 s |
| 310 | 0.455949 | 2246.24 s |
| 311 | 0.335326 | 2252.83 s |
| 312 | 0.557134 | 2259.43 s |
| 313 | 0.272196 | 2266.85 s |
| 314 | 0.334847 | 2273.51 s |
| 315 | 0.173790 | 2282.10 s |
| 316 | 0.895289 | 2289.89 s |
| 317 | 0.762588 | 2298.10 s |
| 318 | 0.214745 | 2306.36 s |
| 319 | 0.341361 | 2312.88 s |
| 320 | 0.435173 | 2319.28 s |
| 321 | 0.821713 | 2325.90 s |
| 322 | 0.625439 | 2332.04 s |
| 323 | 0.089471 | 2340.70 s |
| 324 | 0.672601 | 2349.00 s |
| 325 | 1.172751 | 2356.82 s |
| 326 | 0.525143 | 2365.62 s |
| 327 | 0.872430 | 2372.56 s |
| 328 | 1.098949 | 2380.95 s |
| 329 | 0.183216 | 2389.71 s |
| 330 | 0.358789 | 2397.81 s |
| 331 | 0.248489 | 2405.68 s |
| 332 | 0.352324 | 2411.94 s |
| 333 | 0.136365 | 2419.35 s |
| 334 | 0.940638 | 2427.03 s |
| 335 | 0.468818 | 2433.82 s |
| 336 | 0.408128 | 2440.31 s |
| 337 | 0.687213 | 2450.38 s |
| 338 | 0.438834 | 2456.59 s |
| 339 | 0.165069 | 2465.17 s |
| 340 | 0.112653 | 2472.89 s |
| 341 | 0.776249 | 2478.72 s |
| 342 | 0.110117 | 2486.04 s |
| 343 | 0.239226 | 2494.58 s |
| 344 | 0.670557 | 2501.19 s |
| 345 | 0.334960 | 2507.63 s |
| 346 | 0.693809 | 2513.43 s |
| 347 | 0.175999 | 2519.59 s |
| 348 | 0.262993 | 2526.44 s |
| 349 | 0.149993 | 2537.57 s |
| 350 | 0.399338 | 2544.17 s |
| 351 | 0.457597 | 2552.83 s |
| 352 | 0.525338 | 2558.98 s |
| 353 | 0.720826 | 2565.76 s |
| 354 | 0.731441 | 2571.40 s |
| 355 | 1.026887 | 2579.71 s |
| 356 | 0.262914 | 2585.05 s |
| 357 | 0.372237 | 2591.47 s |
| 358 | 0.862192 | 2598.30 s |
| 359 | 0.927413 | 2604.78 s |
| 360 | 0.743167 | 2613.99 s |
| 361 | 0.556310 | 2620.47 s |
| 362 | 0.361953 | 2626.38 s |
| 363 | 0.839227 | 2632.91 s |
| 364 | 0.491616 | 2641.01 s |
| 365 | 0.417298 | 2648.47 s |
| 366 | 0.546153 | 2656.40 s |
| 367 | 0.506323 | 2663.91 s |
| 368 | 1.420353 | 2672.76 s |
| 369 | 0.801122 | 2678.88 s |
| 370 | 0.150193 | 2685.87 s |
| 371 | 0.526787 | 2692.09 s |
| 372 | 1.043133 | 2698.63 s |
| 373 | 0.565115 | 2706.87 s |
| 374 | 0.492526 | 2713.54 s |
| 375 | 0.770502 | 2719.30 s |
| 376 | 0.889523 | 2725.35 s |
| 377 | 0.279523 | 2730.70 s |
| 378 | 0.357413 | 2733.49 s |
| 379 | 0.417782 | 2740.04 s |
| 380 | 0.892648 | 2747.50 s |
| 381 | 0.463520 | 2753.30 s |
| 382 | 0.469112 | 2760.10 s |
| 383 | 0.354663 | 2766.15 s |
| 384 | 0.639987 | 2769.56 s |
| 385 | 0.818940 | 2778.34 s |
| 386 | 0.433445 | 2784.88 s |
| 387 | 0.624059 | 2792.24 s |
| 388 | 0.313773 | 2799.61 s |
| 389 | 0.390055 | 2805.77 s |
| 390 | 0.628713 | 2814.57 s |
| 391 | 0.539190 | 2821.49 s |
| 392 | 0.582759 | 2828.12 s |
| 393 | 0.629163 | 2836.21 s |
| 394 | 0.404690 | 2844.79 s |
| 395 | 0.569318 | 2852.24 s |
| 396 | 0.758994 | 2858.43 s |
| 397 | 0.983582 | 2865.49 s |
| 398 | 1.111763 | 2872.87 s |
| 399 | 0.809078 | 2876.36 s |
| 400 | 1.041043 | 2883.26 s |
| 401 | 0.431348 | 2890.79 s |
| 402 | 0.442693 | 2897.64 s |
| 403 | 0.415029 | 2904.91 s |
| 404 | 1.187402 | 2912.61 s |
| 405 | 0.100391 | 2920.27 s |
| 406 | 0.155625 | 2928.09 s |
| 407 | 0.534691 | 2934.21 s |
| 408 | 0.863100 | 2937.49 s |
| 409 | 0.257973 | 2945.64 s |
| 410 | 1.246917 | 2953.06 s |
| 411 | 0.781109 | 2961.00 s |
| 412 | 0.516965 | 2969.60 s |
| 413 | 1.131040 | 2977.29 s |
| 414 | 0.364114 | 2995.91 s |
| 415 | 0.855073 | 3004.23 s |
| 416 | 0.551140 | 3013.49 s |
| 417 | 0.349568 | 3021.69 s |
| 418 | 0.357061 | 3029.05 s |
| 419 | 1.180507 | 3036.55 s |
| 420 | 0.451467 | 3049.29 s |
| 421 | 0.693031 | 3055.96 s |
| 422 | 0.406978 | 3062.46 s |
| 423 | 0.503893 | 3068.90 s |
| 424 | 0.324529 | 3075.80 s |
| 425 | 0.505808 | 3089.25 s |
| 426 | 0.571421 | 3096.07 s |
| 427 | 0.120780 | 3102.12 s |
| 428 | 0.541362 | 3110.04 s |
| 429 | 1.242573 | 3116.09 s |
| 430 | 0.382063 | 3123.92 s |
| 431 | 0.691714 | 3132.71 s |
| 432 | 0.454011 | 3140.95 s |
| 433 | 0.461041 | 3148.85 s |
| 434 | 0.497999 | 3154.90 s |
| 435 | 0.380939 | 3161.32 s |
| 436 | 0.484760 | 3167.94 s |
| 437 | 0.432661 | 3175.38 s |
| 438 | 1.270963 | 3181.39 s |
| 439 | 0.307328 | 3187.89 s |
| 440 | 0.232155 | 3195.66 s |
| 441 | 0.332596 | 3203.53 s |
| 442 | 0.882561 | 3213.29 s |
| 443 | 0.296224 | 3219.84 s |
| 444 | 0.216424 | 3227.11 s |
| 445 | 0.479892 | 3234.82 s |
| 446 | 0.631427 | 3243.63 s |
| 447 | 0.562800 | 3252.91 s |
| 448 | 0.320689 | 3258.67 s |
| 449 | 0.793850 | 3264.47 s |
| 450 | 0.323525 | 3272.34 s |
| 451 | 0.403140 | 3278.76 s |
| 452 | 0.097582 | 3287.50 s |
| 453 | 0.526459 | 3294.53 s |
| 454 | 0.023150 | 3302.23 s |
| 455 | 0.603089 | 3309.03 s |
| 456 | 0.355688 | 3314.29 s |
| 457 | 0.543259 | 3320.52 s |
| 458 | 0.281432 | 3329.06 s |
| 459 | 0.831158 | 3335.67 s |
| 460 | 0.902266 | 3343.18 s |
| 461 | 0.454539 | 3349.79 s |
| 462 | 0.820059 | 3358.98 s |
| 463 | 0.192297 | 3366.67 s |
| 464 | 0.629964 | 3372.73 s |
| 465 | 0.595195 | 3379.60 s |
| 466 | 0.841856 | 3385.61 s |
| 467 | 1.022248 | 3393.12 s |
| 468 | 0.287263 | 3399.56 s |
| 469 | 0.229741 | 3405.25 s |
| 470 | 0.494416 | 3413.13 s |
| 471 | 0.968259 | 3421.06 s |
| 472 | 0.934598 | 3428.00 s |
| 473 | 0.666975 | 3436.21 s |
| 474 | 0.181270 | 3444.87 s |
| 475 | 0.704775 | 3452.14 s |
| 476 | 0.498983 | 3458.75 s |

这些数值证明全量单折训练与验证归约能够完成；但本次只有一个 fold、一个 epoch，不能单独用于超参数比较或泛化效果判断。

## 7. 适配器重载与生成检查

- 样本：`EI-56TESTPK0010-easy-v1.2::assistant-0001`
- 输入 tokens：4108
- 新生成 tokens：40
- 状态：PASS

```text
<tool_call>
{"name": "Read", "arguments": {"file_path": "./.agent-sdk/skills/EIAgent-requirement-docs/reference/02-数据加工.md"}}
</tool_call><|im_end|>
```

该检查的验收条件是 adapter 能从磁盘重载、前向与 generation 无异常、产生非空 token；不要求内容正确，也不做 O2 评分。

## 8. 产物说明

- `STATUS.txt`：最终 SUCCESS/FAILED 状态
- `command.txt`：本次入口命令
- `environment.txt`：GPU、系统、Python、pip freeze、Git 状态
- `data/`：fold 05 全量 train/validation、选择 manifest 与 SHA-256
- `artifacts/adapter/`：LoRA 权重、配置、tokenizer
- `artifacts/metrics.json`：结构化训练、验证、token 与双卡峰值信息
- `metrics/generation_smoke.json`：适配器重载生成结果
- `logs/`：准备、DDP、训练、重载生成及 GPU 按秒监控日志
- `scripts_snapshot/`：本次用到脚本的快照
- `artifacts.sha256`：实验目录关键文件校验和

## 9. 复现

在仓库根目录执行：

```bash
bash scripts/run_full_fold05_sft.sh experiments/2026-09-09_full_qwen3-8b_lora_2gpu_fold05_epoch1
```

脚本使用固定 seed `20260909` 与确定性抽样。GPU 浮点内核和 DDP 时序仍可能造成末位差异。

## 10. Task 2：端到端推理 / O2 CSV 就绪性

### 判定

**当前状态：BLOCKED，本次不执行端到端推理，也不生成伪造 CSV。** 适配器重载后的单轮 generation 只能证明模型可以从磁盘加载并生成 token，不等同于带工具的 agent rollout。

目前能够确认的输入包括两个 `validation_tasks`（easy/medium）、从历史轨迹推断出的 11 个工具 schema，以及 `raw_data` 中历史运行使用过的源文件。历史目录同时包含高分运行留下的脚本、CSV 和答案；若直接复制或复用这些内容，会造成 holdout 答案泄漏，不能作为本模型的推理结果。

正式推理仍需外部提供或确认：

1. 可执行的 `agent_core` / `cowork` 推理 harness，以及加载“本地 Qwen3-8B + 本次 LoRA adapter”的接入方式。
2. 完整且只读的 `.agent-sdk/skills/OptAgent`、`.agent-sdk/skills/EIAgent-requirement-docs` 及其 phases、references、scripts；现有轨迹只保留了截断后的技能文本，无法还原正式技能行为。
3. 11 个工具的安全沙箱执行器，而不仅是 JSON schema；至少包括 AskUserQuestion、Bash、Edit、get_goal、Glob、Grep、present_files、Read、Skill、TodoWrite、Write。
4. 与历史答案分离的干净任务包：每个 validation task 的原始 input 文件、允许读取的数据目录、输出目录及应提交的 CSV 文件名/列 schema。
5. rollout 合同：最大步数、超时、工具失败策略、停止条件，以及 evaluator 要求的 `run_metadata`、trajectory 和模型/harness 命名格式。

条件具备后，建议分别创建 easy/medium 的全新隔离工作目录，只读挂载输入数据和技能，加载 base+adapter 执行工具循环，校验 CSV 文件存在、列名和数据类型，再用官方 `eval score run` 评分。整个流程不得读取历史运行生成的脚本或 CSV。

## 11. 限制与下一步

1. 本次只完成 fold 05 单折的 1 个 epoch；它是一次完整训练运行，但仍不足以单独建立统计结论。
2. 最大长度为 20480；若有裁剪应根据下一阶段显存实测提高到 24576 或更高，并优先保证完整 assistant-tool 块。
3. 当前 tool schema 是从全部 7 条轨迹推断的，不是正式 runtime contract。
4. 当前验证只有 teacher-forced completion loss 与非空生成，尚未做 tool-call JSON 结构正确率、工具名准确率、端到端 rollout 或 O2。
5. 轨迹归一权重字段本次未启用；正式 fold 训练应对是否使用该权重做明确选择。
6. 下一阶段应在冻结的推理 harness 中执行两个 holdout validation tasks，验证 tool-call 结构、CSV 合同和端到端 O2；之后再决定是否增加 epoch 或跑其余四折。

## 12. 最终验收清单

- [x] 推荐单折且无 task-family 泄漏
- [x] Qwen chat template + `enable_thinking=False`
- [x] completion-only labels
- [x] 两张 RTX PRO 6000、两个 NCCL rank
- [x] LoRA 反向传播与 optimizer step
- [x] 跨卡验证 loss 聚合
- [x] adapter/tokenizer 落盘
- [x] adapter 从磁盘重载并生成非空输出
- [x] 日志、配置、环境、结果、脚本快照与报告集中归档
- [x] Task 2 推理依赖审计完成；因缺少正式 harness/skills/runtime 且存在历史答案泄漏风险，按要求暂不执行
