# AppWorld Codex-RFT train90 Qwen3-8B 全参数 SFT：57 题 Dev 评测报告

## 结论

本次五轮全参数 SFT 模型在 57 道 Dev 题上完成真实 ReAct 推理与官方 evaluator 评分，成功 **12/57**，TGC=**21.1**，SGC=**0.0**。
与相同 90 条训练轨迹、五轮训练的 LoRA 相比，成功任务数变化为 **-11**，TGC 变化 **-19.3 个百分点**，SGC 变化 **-21.1 个百分点**。
训练 loss 衡量训练集拟合，本报告以 Dev 端到端官方评分衡量任务完成能力。TGC 要求任务所有测试条件通过；SGC 要求同一场景的三个任务全部成功。

## 官方指标

| 系统 | 成功任务 | TGC | SGC | 完整成功场景 | 通过测试条件 |
|---|---:|---:|---:|---:|---:|
| 原始 Qwen3-8B（历史接口） | 5/57 | 8.8 | 0.0 | 0/19 | 114/291 |
| 旧67轨迹全参数 SFT epoch5 | 0/57 | 0.0 | 0.0 | 0/19 | 86/291 |
| train90 LoRA | 23/57 | 40.4 | 21.1 | 4/19 | 206/291 |
| 本次 train90 全参数 SFT | 12/57 | 21.1 | 0.0 | 0/19 | 163/291 |

| 难度 | train90 LoRA 成功/总数 (TGC) | train90 全参数 SFT 成功/总数 (TGC) |
|---:|---:|---:|
| 1 | 14/30 (46.7%) | 6/30 (20.0%) |
| 2 | 9/24 (37.5%) | 6/24 (25.0%) |
| 3 | 0/3 (0.0%) | 0/3 (0.0%) |

## 成功任务变化

相对 train90 LoRA：共同成功 7 题，全参数 SFT 新增成功 5 题，退化 16 题，两者均失败 29 题。

本次成功任务：23cf851_1、37a8675_2、396c5a2_2、396c5a2_3、3ab5b8b_1、4ec8de5_3、6171bbc_1、6c2c621_1、6c2c621_3、d4e9306_1、fac291d_1、fac291d_3

新增成功：37a8675_2、3ab5b8b_1、4ec8de5_3、6171bbc_1、6c2c621_1

退化任务：23cf851_3、37a8675_1、396c5a2_1、4ec8de5_2、50e1ac9_1、50e1ac9_3、57c3486_1、57c3486_2、57c3486_3、6bdbc26_2、b119b1f_1、b119b1f_2、d4e9306_2、d4e9306_3、df61dc5_3、fac291d_2

完整成功场景：无

完整 57 题难度、通过条件、成功状态及相对 LoRA 的变化见 [逐题 CSV](task_comparison.csv)。

## 完整性与执行通道审计

- Dev 清单、逐题状态与官方聚合结果均覆盖 57 个唯一任务；逐题测试条件和成功状态一致，正式进程退出码为 0。
- 官方测试条件通过 163/291（56.0%）；逐题 evaluator 错误为 0。
- 57/57 题第一次 LM 请求的完整 messages 与 LoRA 历史日志一致；共核对 1,003 次请求的模型名、temperature、seed、输出上限和接口类型，全部符合协议。
- LM 请求 1,003 次，其中正常回复 994 次；服务拒绝 9 次。日志中的 9 条空字符串是 AppWorld 为失败请求写入的占位记录，附有 error 和零 token 用量，并非模型生成了空回复。
- 正常模型回复中，空内容 0 次、无 Python fenced code 0 次；content=null 0 次。
- finish_reason=length 的回复：0 次；最终模型 5 个 safetensors 文件的 SHA-256 校验全部通过。
- No code available observation：0；AppWorld API 调用：3,205。
- 含 complete_task action 的任务：47/57；达到 50 次 LM 调用的任务：2。
- 含 Python 执行错误的任务：37；含语法错误的任务：5。这些是任务轨迹中的模型行为，不等同于评分器故障。
- 上下文溢出终止任务：9；任务 ID：37a8675_3、383cbac_1、396c5a2_1、4fab96f_2、530b157_2、57c3486_1、6171bbc_3、b119b1f_1、b119b1f_2。
- 上下文拒绝中，输入本身超过 32000 的请求有 5 次；输入加预留 3000 输出超限有 4 次。按原协议保留这些失败，没有扩窗或换提示词重试。
- 模型执行异常任务：无；正式运行审计异常：无。

## 运行成本

| 项目 | train90 LoRA | train90 全参数 SFT |
|---|---:|---:|
| LM 请求（含被拒绝请求） | 1,014 | 1,003 |
| AppWorld API 调用 | 5,991 | 3,205 |
| 输入 tokens | 10,443,515 | 9,437,194 |
| 输出 tokens | 91,658 | 75,783 |
| 总 tokens | 10,535,173 | 9,512,977 |

本次正式评测墙钟时间：**23.3 分钟**，包含本次成功启动的模型加载和最终官方评分；不含此前失败的服务启动。LoRA 历史墙钟时间为 31.1 分钟。

首次启动因工作区内临时 Unix socket 路径超过 107 字节而失败，尚未开始任何任务；将 TMPDIR 改为工作区内的短路径后重新启动。原始日志保存在 `logs/startup_attempt_01/`。正式 57 题运行没有因这次启动问题重做已完成任务。

## 协议与比较边界

- 两次 train90 实验使用相同训练任务和数据转换版本，均训练五轮；90 个训练任务与这 57 个 Dev 任务无交集。
- 使用相同官方 Dev 任务顺序、ReAct 提示词、AppWorld 执行环境及 evaluator；temperature=0、seed=100、每题最多 50 步、单次输出最多 3000 tokens、max_model_len=32000。
- vLLM 不启用 reasoning parser，完整模型直接加载，无 LoRA adapter；对 reasoning_content=null 仅转换为空字符串供日志处理，不改写模型输出或 Python action。生成配置文件中的默认服务命令会被启动器覆盖，实际命令以 `command.txt`、脚本快照和运行日志为准。
- 本次评测固定最终 epoch 5 模型；未根据 Dev 结果选取中间 checkpoint，也未运行 test_normal。
- 全参数训练采用峰值 LR=1e-5 的 warmup/cosine 调度及 FP32 主参数/优化器状态；LoRA 的训练设置不同。结果比较的是两套具体训练方案，不能单独归因于参数更新范围。
- 旧 67 轨迹全参数实验的数据量、学习率和数值实现不同，仅供历史参考。原始基座历史结果启用了 deepseek_r1 parser，与当前无 parser 的接口不同，不能视为严格的纯权重对照。

## 模型与产物

- 最终模型：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/artifacts/model`，8,190,735,360 参数，BF16 HF 权重；评测不复制或修改权重。
- 训练实验：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5`。
- `summary.json`：官方得分、难度、逐题转移、调用统计和完整性审计。
- `manifest.json`、`config/protocol_preflight.json`：模型来源、Dev/提示词/配置哈希、依赖版本及运行协议。
- `task_status.jsonl`、`task_comparison.csv`：逐题官方评分与 LoRA 对照。
- `experiments/outputs/.../evaluations/dev.json`：官方聚合结果；`tasks/` 保留逐题交互与 evaluator 证据。
- `logs/run.log`、`scripts_snapshot/`、`artifacts.sha256`：运行日志、实际脚本及文件校验清单。
