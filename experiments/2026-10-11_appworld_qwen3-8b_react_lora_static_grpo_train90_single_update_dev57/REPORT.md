# 静态 rubric GRPO 单次更新：dev57 官方评测

本次最终模型成功 **16/57**，TGC **28.1%**，SGC **10.5%**。相对更新前 SFT LoRA 历史评测，成功任务变化 **-7**，TGC 变化 **-12.3 个百分点**。

| 模型 | 成功任务 | TGC | SGC | 完整成功场景 | 通过条件 |
|---|---:|---:|---:|---:|---:|
| 更新前 train90 SFT LoRA（历史评测） | 23/57 | 40.4% | 21.1% | 4/19 | 206/291 |
| 静态 rubric GRPO：单次更新 | 16/57 | 28.1% | 10.5% | 2/19 | 172/291 |
| train90 全参数 SFT（历史评测） | 12/57 | 21.1% | 0.0% | 0/19 | 163/291 |

TGC：一题所有官方测试条件通过；SGC：一个场景的三道题全部通过。

## 模型来源与训练完成核验

初始模型为 Qwen3-8B + train90 成功轨迹 SFT 五轮的 LoRA。在完整 90 题 × 6 = 540 条轨迹上完成静态 rubric 评分，每题内部计算 reward/advantage；两卡累计全部梯度后执行一个 PPO epoch、一次 optimizer step。未做后续重采样或第二次更新。

- 最终 adapter：`/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/checkpoint`；与 `/root/autodl-tmp/models/Qwen3-8B` 一起加载。
- policy ID：`c0894f1560ce153461a745aed1416ca6a7032ddb1e0017d017c499d26e425eeb`。
- adapter_config、adapter 权重与 optimizer 文件的 SHA-256 在评测前后均通过核验。
- policy 确实改变，reference 保持冻结；训练保存重载的真实 logprob 最大误差为 0。

## 逐题与难度变化

| 难度 | 本次成功/总数 | 更新前成功/总数 |
|---|---:|---:|
| 1 | 11/30 | 14/30 |
| 2 | 5/24 | 9/24 |
| 3 | 0/3 | 0/3 |

共同成功 12 题，新增成功 4 题，退化 11 题，两者均失败 30 题。

新增成功：50e1ac9_2、6bdbc26_3、6c2c621_2、df61dc5_1

退化：23cf851_1、37a8675_1、50e1ac9_1、50e1ac9_3、57c3486_1、57c3486_3、6bdbc26_2、b119b1f_1、b119b1f_2、df61dc5_3、fac291d_2

[完整逐题对照](task_comparison.csv) · [逐题输入输出入口](TASKS.md) · [JSON 索引](trajectory_index.json)

## 评测设置与完整性

- 官方 dev57、19 个场景、291 条测试条件，train90 与 dev57 无交集；每题一次轨迹，按历史顺序运行。
- 同历史实验 ReAct 提示词和执行器；temperature=0，seed=100，max_steps=50，max_completion_tokens=3000，max_model_len=32000。
- vLLM 直接加载基座与 LoRA；无 reasoning parser，不覆盖 enable_thinking。此处严格沿用历史 dev 协议，与训练轨迹采集显式 enable_thinking=false 有区别。
- 推理环境版本与历史参考一致：torch 2.8.0+cu128、transformers 4.56.2、vLLM 0.10.2；AppWorld 0.2.0.dev0。tokenizer 词表、特殊 token、聊天模板及首题完整输入 token IDs 均与历史 LoRA 一致。
- 57/57 首次请求的完整 messages 同时匹配历史 LoRA 和全参数 SFT；所有请求的模型、温度、seed、输出上限均通过检查。
- 逐题状态与官方聚合的任务集合、成功结果和测试条件计数均核对；不按表现重采，不修改窗口来重试失败任务。
- 模型执行异常：0 题；请求错误：7 次，其中上下文溢出 7 次。
- 正常模型回复空内容 0 次、无 Python fenced code 0 次；输出达到上限 0 次。
- 运行审计异常：无。

## 耗时与解释边界

本次用时 31.0 分钟（含加载与官方聚合），LM 请求 986 次，输入 9,917,558 / 输出 87,285 tokens，AppWorld API 调用 4,571 次。

更新前对照引用 2026-09-21 的既有 LoRA 评测，其 adapter SHA 与本次初始模型一致；全参数 SFT 仅作用户指定的历史参考。本次没有重新运行初始模型或多 seed 重复评测，因此这是一次固定协议下的观察，不足以证明稳定增益。当前实验仅验证静态方法的首次完整更新，不代表 DRACO 论文完整训练效果。

## 产物

- `summary.json`：官方指标、难度、逐题变化、调用统计与审计。
- `trajectory_index.json`：57 题的模型输入输出、环境交互和目录索引；模型交互见逐题 `logs/lm_calls.jsonl`，可读轨迹见 `logs/environment_io.md`。
- 官方聚合：`experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/evaluations/dev.json`。
- `task_status.jsonl`：每题完成后的即时官方评分；`task_comparison.csv`：逐题对照。
- `config/`、`scripts_snapshot/`、`logs/`：模型校验、配置、执行脚本与日志。
