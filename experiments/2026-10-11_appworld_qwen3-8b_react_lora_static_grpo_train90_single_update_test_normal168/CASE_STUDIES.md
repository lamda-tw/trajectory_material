# test_normal 成对轨迹案例

以下题目均来自本次唯一一次正式评测及更新前 SFT LoRA 的历史原始轨迹。选例用于展示实际行为差异，不用于估计各错误的总体占比，也不能把某条训练轨迹直接归因为某道测试题的变化。全量成对结果见 [REPORT.md](REPORT.md) 与 [task_comparison.csv](task_comparison.csv)。

每个 `lm_calls.jsonl` 的一行对应一次模型请求和响应：`input.messages` 是完整输入，`output.choices[0].message.content` 是模型输出。链接行号就是本文的模型步骤号；执行反馈可在下一次请求末尾及 `environment_io.md` 查阅。

## 退化一：内容正确，但遗漏必须保留的属性

题目 `d6ac34d_2` 要创建今天的习惯日志，与昨天相同，仅把冥想改为未完成。

| 模型 | 官方条件 | 模型调用 |
|---|---:|---:|
| 更新前 SFT LoRA | 9/9，成功 | 15 |
| GRPO 一次更新 | 8/9，失败 | 16 |

初始模型创建笔记时显式传入 `tags=[], pinned=True`。GRPO 第 14 步只传 `access_token, title, content`，未保留置顶属性，得到 `pinned=False`。官方唯一未通过条件正是新笔记必须置顶。两者的前五次模型输出相同；后续执行分叉。标题、日期、内容等条件仍然通过。

这是业务约束遗漏，不是评测器、GPU 或上下文故障。调用 `create_note` 成功和最后提交完成，不能替代全部任务条件满足；也不能据此断言某一条静态判据直接造成了属性丢失。

[GRPO 第 14 步](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/d6ac34d_2/logs/lm_calls.jsonl:14) · [初始 LoRA 第 13 步](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/d6ac34d_2/logs/lm_calls.jsonl:13) · [GRPO 环境反馈](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/d6ac34d_2/logs/environment_io.md) · [GRPO 官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/d6ac34d_2/evaluation/report.md) · [初始官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/d6ac34d_2/evaluation/report.md)

## 退化二：只看到数量，却提交了没有依据的姓名

题目 `cef9191_1` 问“我关注的 Spotify 艺人中，谁的粉丝最多？”

| 模型 | 官方条件 | 模型调用 |
|---|---:|---:|
| 更新前 SFT LoRA | 2/2，成功 | 10 |
| GRPO 一次更新 | 1/2，失败 | 8 |

初始模型用 `show_following_artists` 查询用户关注集合，遍历分页后计算 `max(..., key=follower_count)` 并打印结果，实际观察到 `Eliana Harper`、29 个粉丝，再提交这个姓名。

GRPO 改用全局 `search_artists`，既未限定“我关注的”，又只打印了列表长度。第 6 步实际反馈只有数字 `36`；第 7 步却声称最多粉丝为 1,234,567、姓名为 `Artist A`，第 8 步把这个姓名作为最终答案。原始观察不支持这个结论，官方答案也不匹配。

该例同时涉及查询范围错误与回答缺乏依据。模型仍会先查文档、登录、分页、提交，外观上保留了很多正确流程，但决定任务成功的关键事实出错。它与“通用过程分不等于业务正确性”的风险一致，尚不能证明训练后 rubric 分数上升或发生 reward hacking，因为没有给更新后的轨迹重新打同口径 rubric 分。

[GRPO 第 6 步](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/cef9191_1/logs/lm_calls.jsonl:6) · [初始 LoRA 第 8 步](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/cef9191_1/logs/lm_calls.jsonl:8) · [GRPO 环境反馈](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/cef9191_1/logs/environment_io.md) · [GRPO 官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/cef9191_1/evaluation/report.md) · [初始官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/cef9191_1/evaluation/report.md)

## 退化三：环境时间相同，模型推断了错误的星期

题目 `afc4005_1` 问 Simple Note 计划中今天的健身时长。

初始模型通过 2/2 条件；GRPO 通过 1/2。两者都读取了计划，并在第 10 步调用 `datetime.now()`，都得到完全相同的模拟环境时间 `2023-05-18T12:00:00`。初始模型判断为星期四，提交 60 分钟；GRPO 第 11 步误称星期五，提交 70 分钟。官方要求 60。

因此，这一题不是跨日期运行使“今天”改变，也不是笔记缺失或截断。错误发生在日期到星期、再到计划条目的推断。一次局部概率更新可以改变这种离散答案选择，不能指望代理 loss 的下降保证答案正确率单调提升。

[GRPO 第 11 步](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/afc4005_1/logs/lm_calls.jsonl:11) · [初始 LoRA 第 11 步](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/afc4005_1/logs/lm_calls.jsonl:11) · [GRPO 环境反馈](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/afc4005_1/logs/environment_io.md) · [GRPO 官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/afc4005_1/evaluation/report.md) · [初始官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/afc4005_1/evaluation/report.md)

## 改进案例：从本地变量检查变为实际推进应用状态

题目 `325d6ec_1` 要不断播放上一首歌，直到遇到已点赞的歌。

| 模型 | 官方条件 | 模型调用 |
|---|---:|---:|
| 更新前 SFT LoRA | 4/5，失败 | 11 |
| GRPO 一次更新 | 5/5，成功 | 23 |

初始模型调用一次 `previous_song` 后，真实游标停在歌曲 48。第 9 步把局部 `current_position` 设为 0，检查缓存队列里的歌曲是否已点赞，然后退出循环；这段代码没有再次调用 `previous_song`，本地检查没有推进播放器，官方游标条件失败。

GRPO 后续继续实际调用 `previous_song`，最终在第 21 步到达要求的歌曲 33，全部官方条件通过。它的一些中间文字解释并不严密，不能将成功解释为每句推理都正确；此处能确认的是应用状态实际发生了足够次数的推进。

这也说明更新并非让每道题都退步。该题成功轨迹反而更长，不能仅凭训练 reward 与长度负相关就断言所有变化都是模型变懒。评测总差额必须同时计入新增成功与退化。

[GRPO 第 21 步](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_1/logs/lm_calls.jsonl:21) · [初始 LoRA 第 9 步](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_1/logs/lm_calls.jsonl:9) · [GRPO 环境反馈](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_1/logs/environment_io.md) · [GRPO 官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_1/evaluation/report.md) · [初始官方判分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_1/evaluation/report.md)

## 这些案例支持的结论边界

同一初始 prompt、相同任务条件下，单次更新后可出现不同 API 选择、属性遗漏、无依据答案、推断错误，也可修复实际执行不足。这里展示的是结果变化的位置。训练侧更具体的风险是：静态条目总分与官方目标并不等价、整条轨迹共享 advantage，以及首步 KL 没有非零约束梯度。对应证据见 [TRAINING_DIAGNOSIS.md](TRAINING_DIAGNOSIS.md)。

要确认哪个因素造成多少性能变化，仍需要在 Dev 上进行同数据、同起点的受控对照；本次没有追加训练或利用 test 结果选择模型。
