# 第一轮联合训练与训练前 DEV57 历史基线对比

核对日期：2026-10-16。仅分析已有结果，没有启动 GPU 推理、重训或下一轮实验。

**本次实测结果下降：TGC 从 23/57 降至 20/57，SGC 从 4/19 降至 2/19。** 这是与历史基线的比较；评测入口存在差异，尚不能把下降完全归因于模型训练。

用户指定基线：[2026-09-21 原始 summary.json](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/summary.json)、[官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/evaluations/dev.json)。其 LoRA 权重 SHA-256 与本次训练起点 A0 完全相同：`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。

当前模型：第 15 次联合更新后的最终 LoRA。两次都是同一批 57 道 DEV 任务，19 个场景，每场景 3 道题，逐题官方测试数量一致。

| 指标 | 训练前历史基线 | 第一轮联合训练后 | 变化 |
| --- | ---: | ---: | ---: |
| TGC：任务全部达成 | 23/57 = 40.35% | 20/57 = 35.09% | −3 题；−5.26 个百分点 |
| SGC：场景内三题全部达成 | 4/19 = 21.05% | 2/19 = 10.53% | −2 场景；−10.53 个百分点 |
| 官方测试条件通过数（辅助统计） | 206/291 = 70.79% | 184/291 = 63.23% | −22 条；−7.56 个百分点 |

SGC 按 AppWorld 官方 Metric 的定义复算：对每个场景取各题成功标志的最小值，再对场景平均。官方一位小数显示为 TGC 40.4→35.1、SGC 21.1→10.5；变化使用未舍入数值计算。测试条件通过比例不是 SGC。

## 逐题变化

保留成功 14 题，新增成功 6 题，丢失成功 9 题，两次都失败 28 题。

新增成功：`3ab5b8b_3`、`6171bbc_1`、`68ee2c9_1`、`6bdbc26_3`、`6c2c621_1`、`df61dc5_1`。

| 从成功变为失败的题目 | 训练前通过条件 | 训练后通过条件 | 本次结束原因 |
| --- | ---: | ---: | --- |
| `23cf851_1` | 2/2 | 1/2 | completion_api |
| `37a8675_1` | 6/6 | 0/6 | completion_api |
| `4ec8de5_2` | 2/2 | 1/2 | completion_api |
| `50e1ac9_1` | 2/2 | 1/2 | completion_api |
| `57c3486_1` | 5/5 | 1/5 | context_limit |
| `6bdbc26_2` | 2/2 | 1/2 | completion_api |
| `b119b1f_2` | 6/6 | 5/6 | completion_api |
| `d4e9306_2` | 6/6 | 2/6 | completion_api |
| `df61dc5_3` | 7/7 | 2/7 | context_limit |

9 道退步题中，2 道以 context_limit 结束，另外 7 道调用完成接口后仍未通过官方测试；不能将全部退步解释为上下文耗尽。

训练前全对的 4 个场景：`396c5a2`、`57c3486`、`d4e9306`、`fac291d`。本次保留 `396c5a2`、`fac291d`；`57c3486_1` 与 `d4e9306_2` 失败分别使另外两个场景失去 SGC 成功资格。

## 评测协议核对与结论边界

- 相同：初始 LoRA 身份、DEV57 题目集合及测试数量、temperature=0、每题一次、最多 50 步、标称动作上限 3000 token、上下文上限 32000。
- 57 题的初始消息角色及正文，在去掉首尾空白后全部一致；原始消息对象全部不完全相同。旧入口保留末尾空白，新入口对初始消息执行 strip，旧末条消息另有 cache_control 元数据。
- 旧请求走 chat completions，没有显式设置 enable_thinking=False；当前走 tokenize + raw completions，显式设置 False，已保存的提示 token 包含空 thinking 块。旧请求没有保存 prompt token IDs，不能认定两者 token 级一致，也不能仅由 reasoning_parser=none 推断旧版关闭了 thinking。
- 旧请求始终指定 3000 个输出 token；当前按剩余上下文缩小输出预算，无空间时记 context_limit。
- 旧请求每步 seed=100；当前为 100+从零计数的步号。两者 temperature=0。任务并发、服务调度及 generation config 设置也不完全一致。
- 因此本报告确认历史对比中的数值下降，不能单凭这次比较判定下降全部由联合训练造成，更不能区分 RL、SFT、KL 或学习率的贡献。

下一步若要验证训练效果，应先以同一入口、相同配置复测 A0 和最终模型；本次未执行该复测。归因还需逐题轨迹分析或有控制的消融。本轮尚未证明优于初始 SFT 模型。

## 可复核产物

- [机器可读比较、来源哈希及协议审计](baseline_comparison.json)
- [57 题逐题对照 CSV](paired_task_comparison.csv)
- [19 个场景对照 CSV](scenario_comparison.csv)
- [本次原始汇总](SUMMARY.json) 与 [逐题结果](RESULTS.md)
- [本机官方 SGC 实现](/root/autodl-tmp/envs/appworld-0.2.0-py312/lib/python3.12/site-packages/appworld/evaluator.py:324)

此次补充没有改写已完成评测的 SUMMARY.json、INPUT_MANIFEST.json、代码或权重；原始哈希链保持不变。
