# AppWorld Codex-RFT train90 Qwen3-8B LoRA：57 题 Dev 评测报告

## 结论

本次五轮 LoRA 在 57 道 Dev 题上完成真实 ReAct 推理与官方 evaluator 评分，成功 23/57，TGC=40.4，SGC=21.1。旧 67 题 LoRA 成功 5/57，原始基座成功 5/57。
训练 loss 不能代替这项端到端评测；本报告以官方 evaluator 输出为准。

## 官方指标

| 系统 | 成功任务 | TGC | SGC | 完整成功场景 |
|---|---:|---:|---:|---:|
| 原始 Qwen3-8B | 5/57 | 8.8 | 0.0 | 0/19 |
| 旧 67 题 LoRA | 5/57 | 8.8 | 5.3 | 1/19 |
| 本次 Codex-RFT 90 题 LoRA | 23/57 | 40.4 | 21.1 | 4/19 |

| 难度 | 原始模型成功/总数 (TGC) | 旧 LoRA | 本次 LoRA |
|---:|---:|---:|---:|
| 1 | 2/30 (6.7%) | 3/30 (10.0%) | 14/30 (46.7%) |
| 2 | 3/24 (12.5%) | 2/24 (8.3%) | 9/24 (37.5%) |
| 3 | 0/3 (0.0%) | 0/3 (0.0%) | 0/3 (0.0%) |

## 成功任务变化

本次成功任务：23cf851_1、23cf851_3、37a8675_1、396c5a2_1、396c5a2_2、396c5a2_3、4ec8de5_2、50e1ac9_1、50e1ac9_3、57c3486_1、57c3486_2、57c3486_3、6bdbc26_2、6c2c621_3、b119b1f_1、b119b1f_2、d4e9306_1、d4e9306_2、d4e9306_3、df61dc5_3、fac291d_1、fac291d_2、fac291d_3

相对旧 LoRA：共同成功 4 题，新增成功 19 题，退化 1 题。
新增成功：23cf851_1、23cf851_3、37a8675_1、396c5a2_1、396c5a2_2、396c5a2_3、4ec8de5_2、50e1ac9_3、57c3486_1、57c3486_2、57c3486_3、6bdbc26_2、6c2c621_3、b119b1f_1、b119b1f_2、df61dc5_3、fac291d_1、fac291d_2、fac291d_3
退化：6171bbc_1

相对原始基座：共同成功 1 题，新增成功 22 题，退化 4 题。

## 完整性与执行通道审计

- Dev 清单与逐题官方 evaluator 均覆盖 57/57 题；最终进程退出码为 0。
- 测试条件通过 206/291；逐题 evaluator 错误为 0。
- LM 调用 1,014，content 非空 1,014，content=null 0。
- No code available observation：0；真实 AppWorld API 调用：5,991。
- 含 complete_task action 的任务：51/57；达到 50 次 LM 调用的任务：1。
- 含 Python 执行错误的任务：39。

## 运行成本

| 项目 | 原始模型 | 旧 67 题 LoRA | 本次 Codex-RFT LoRA |
|---|---:|---:|---:|
| LM 调用 | 688 | 1,628 | 1,014 |
| AppWorld API 调用 | 4,190 | 36,999 | 5,991 |
| 输入 tokens | 3,923,913 | 13,057,976 | 10,443,515 |
| 输出 tokens | 622,880 | 243,041 | 91,658 |
| 总 tokens | 4,546,793 | 13,301,017 | 10,535,173 |
本次墙钟时间：31.1 分钟。

## 协议与比较边界

- 三组使用相同的 57 题官方 Dev 清单、ReAct agent 和 evaluator。
- 本次沿用旧 LoRA 已验证的无 reasoning parser 输出接口，使非 thinking 格式的 fenced Python 保留在 message.content；对 reasoning_content=null 仅做空字符串兼容。
- 本次推理配置为 temperature=0、seed=100、每题最多 50 步、单次输出最多 3000 tokens、vLLM max_model_len=32000。实际训练最大上下文为 40960；推理的 32000 上限用于与旧评测协议对齐。
- 旧 LoRA 与本次 LoRA 可以在相同推理接口下比较；原始基座历史结果使用 deepseek_r1 parser，因此与基座的差别同时含输出协议影响，不能解释为纯权重消融。

## 产物

- summary.json：机器可读的官方分数、难度、任务转移和调用统计。
- manifest.json：adapter、Dev 清单哈希与推理协议。
- task_status.jsonl：逐题官方 evaluator 摘要。
- experiments/outputs/.../evaluations/dev.json：官方聚合结果。
- experiments/outputs/.../tasks/：逐题交互及 evaluator 证据；包含运行环境数据，仅本地保存。
- logs/run.log：完整运行日志；scripts_snapshot/：本次实际执行脚本。
