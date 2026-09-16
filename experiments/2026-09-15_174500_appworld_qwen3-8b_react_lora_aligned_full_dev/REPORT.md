# AppWorld Qwen3-8B LoRA 对齐接口后的完整 Dev 评测报告

## 一、结论

修正输出通道后，五轮 LoRA 模型已在 57 道 Dev 题上完成真实 ReAct 推理和官方评测。
最终成功 5/57，TGC 为 8.8，与原始模型的 5/57、TGC 8.8 持平；SGC 从 0.0 提高到 5.3。

成功总数相同，但成功题完全不同：共同成功 0 题，LoRA 新增成功 5 题，同时丢失原模型成功的 5 题。
LoRA 将 d4e9306 场景的三个任务全部完成，因此获得 1/19 场景成功，对应 SGC 5.3；原模型没有完整完成任何一个三任务场景。

这个结果说明接口问题已经消除，当前分数可以用于观察端到端能力。67 条轨迹的五轮 LoRA 没有提高总体 TGC，但改变了能力分布，并提高了场景级完整完成率。

## 二、官方指标

| 指标 | 原始 Qwen3-8B | 五轮 LoRA | 变化 |
|---|---:|---:|---:|
| 成功任务 | 5/57 | 5/57 | +0 |
| TGC | 8.8 | 8.8 | +0.0 |
| SGC | 0.0 | 5.3 | +5.3 |
| 成功 scenario | 0/19 | 1/19 | +1 |

按难度统计：

| 难度 | 原始模型 成功/总数（TGC） | LoRA 成功/总数（TGC） |
|---|---:|---:|
| 1 | 2/30 (6.7) | 3/30 (10.0) |
| 2 | 3/24 (12.5) | 2/24 (8.3) |
| 3 | 0/3 (0.0) | 0/3 (0.0) |

## 三、成功题与任务转移

LoRA 成功任务：

- 50e1ac9_1
- 6171bbc_1
- d4e9306_1
- d4e9306_2
- d4e9306_3

原始模型成功任务：

- 23cf851_2
- 68ee2c9_3
- 6c2c621_1
- 6c2c621_2
- fac291d_1

| 转移 | 数量 |
|---|---:|
| 原始成功 → LoRA 成功 | 0 |
| 原始失败 → LoRA 成功 | 5 |
| 原始成功 → LoRA 失败 | 5 |
| 原始失败 → LoRA 失败 | 47 |

LoRA 新增成功： 50e1ac9_1、6171bbc_1、d4e9306_1、d4e9306_2、d4e9306_3

LoRA 退化任务： 23cf851_2、68ee2c9_3、6c2c621_1、6c2c621_2、fac291d_1

## 四、接口与运行完整性审计

| 检查项 | 结果 |
|---|---:|
| Dev 任务完成 | 57/57 |
| 逐题官方 evaluator 错误 | 0 |
| 最终进程退出码 | 0 |
| LM 调用 | 1,628 |
| message.content 非空 | 1,628 |
| message.content=null | 0 |
| No code available observation | 0 |
| 真实 AppWorld API 调用 | 36,999 |
| 含 complete_task action 的任务 | 34/57 |
| complete_task action 出现次数 | 81 |
| 含 Python 执行错误的任务 | 53 |
| 达到 50 次 LM 调用的任务 | 22 |

全部模型响应均进入可执行 content，content=null 和 No code available 均为 0。本次产生 36,999 次真实 API 调用，因此不再是此前代码被 reasoning parser 吞掉的无效评测。

逐题 evaluator 共通过 105/291 个测试条件（36.1%）。TGC 要求一道题的所有条件全部通过，因此部分完成不会计为任务成功。

## 五、推理配置与对照边界

- Dev split、任务顺序、ReAct Agent、Prompt、temperature=0、seed=100、单次输出上限 3000、每题 50 步、上下文 32000 和官方 evaluator 与原模型实验保持一致。
- 使用原始 Qwen3-8B 基座，并加载 epoch-5 LoRA adapter。
- 关闭 vLLM reasoning parser，使 LoRA 生成的理由和 fenced Python 保留在 message.content 中。
- 对 AppWorld Agents 的 reasoning_content=null 做空字符串规范化；该修复只处理字段类型，不修改模型文本或 Python action。

由于原模型历史基线使用 deepseek_r1 reasoning parser，而 LoRA 必须关闭该 parser 才能执行其训练格式，这里最可靠的含义是两个可运行端到端系统的对比。若要得到严格的纯权重消融，还应额外用相同的无 parser 接口评测原始模型。

## 六、运行成本

| 指标 | 原始 Qwen3-8B | 五轮 LoRA |
|---|---:|---:|
| LM 调用 | 688 | 1,628 |
| AppWorld API 调用 | 4,190 | 36,999 |
| 输入 tokens | 3,923,913 | 13,057,976 |
| 输出 tokens | 622,880 | 243,041 |
| 总 tokens | 4,546,793 | 13,301,017 |
| 本次墙钟时间 | — | 1 小时 12 分 51 秒 |
| 本次实验目录大小 | — | 338.95 MiB |

## 七、产物

- REPORT.md：本中文报告
- task_status.jsonl：每题完成后即时写入的官方评分摘要
- summary.json：机器可读汇总与新旧任务转移
- manifest.json：模型、adapter、数据和推理协议
- command.txt：正式运行命令
- baseline_reference.txt：原模型基线目录
- scripts_snapshot/：本次实际使用的启动和报告脚本快照
- experiments/outputs/.../evaluations/dev.json：AppWorld 官方聚合与逐题评测
- experiments/outputs/.../tasks/：每题 LM、环境、API、数据库和 evaluator 产物
- logs/run.log：完整运行日志

## 八、建议

下一步不应根据同为 5/57 就断言 LoRA 没有学习。它学出了五个新的成功任务和一个完整成功场景，同时发生五个退化，说明主要问题是覆盖面和稳定性。
建议先分析新增成功与退化任务的轨迹差异，再扩大训练轨迹覆盖、加入 Dev 不可见的验证划分，并对长循环、分页和数据结构错误做针对性训练。
同时补跑原始模型的无 parser 对照，可将输出协议影响与 LoRA 权重影响严格分离。
