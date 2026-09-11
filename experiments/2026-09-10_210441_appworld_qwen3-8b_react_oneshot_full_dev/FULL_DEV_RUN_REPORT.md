# AppWorld Qwen3-8B one-shot 完整 dev 运行报告

## 一、结论摘要

完整 dev 的推理与评分链路已跑通。

- dev 清单：57 条，57 个唯一 task，19 个 scenario。
- 实际启动：57/57；产生 LM 调用：57/57；产生环境交互：57/57。
- 正常写入 `misc/finished`：57/57；成功完成 task-specific evaluation：57/57。
- 官方成功任务：5；模型/Agent 失败：52；基础设施或评分链路失败：0。
- 成功 task IDs：fac291d_1, 23cf851_2, 68ee2c9_3, 6c2c621_1, 6c2c621_2。
- TGC：8.8；SGC：0.0；最终运行退出码：0。
- 需要重跑的任务：无。

这里把“任务答错”和“系统没有跑完”严格分开：只要任务进入 Agent、写入 finished，并成功执行官方 evaluator，即使得分为 0，也算推理/评分基础设施链路完成。

## 二、实验范围与固定配置

| 项目 | 配置 |
|---|---|
| 模型 | `/root/autodl-tmp/models/Qwen3-8B`，原权重只读 |
| Agent | 官方 `simplified_react_code_agent` |
| Prompt | 官方 ReAct code-agent instructions，包含一个 worked example，因此属于 one-shot |
| 模型 preset | `qwen3-8b-with-reasoning` |
| temperature / seed | 0.0 / 100 |
| max completion | 3000 tokens/LM call |
| max steps | 50/task |
| vLLM context | 32000（与 smoke 实际命令一致） |
| 调度 | 1 个 AppWorld 进程，任务顺序执行，GPU0 |
| AppWorld | 0.2.0.dev0，Python 3.12.3 |
| vLLM / PyTorch / CUDA | 0.10.2 / 2.8.0+cu128 / 12.8 |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition，97887 MiB |

本次没有训练、微调或修改模型权重。原始 `api_docs`、`base_dbs`、`tasks`、`dev.txt` 通过符号链接复用，没有复制大体积数据。官方自动生成的 Agent config 被隔离到本实验 `config/agent_configs`，没有写入已安装 Python 环境。需要说明：普通符号链接并不提供文件系统级只读保护；官方 evaluator 动态导入 task-specific evaluation.py 时，在原始 tasks/*/ground_truth/__pycache__ 下生成了 54 个 .pyc 缓存文件。审计未发现其他类型的原始数据文件在正式运行期间被写入，模型目录和旧 smoke 实验也没有本次运行产生的新文件。已有 .pyc 按不再修改原始目录的约束保留、不做删除；复现脚本现已加入 PYTHONDONTWRITEBYTECODE=1，防止后续运行再次生成此类缓存。

## 三、数据流与执行链路

```text
data/datasets/dev.txt
        │ 读取 57 个 task_id
        ▼
Task.load(task_id) + 初始 base DB
        │
        ▼
官方 one-shot instructions + 当前任务描述
        │ OpenAI-compatible Chat Completions
        ▼
本地 vLLM / Qwen3-8B
        │ reasoning_content + Python code
        ▼
simplified ReAct Agent 提取代码
        │
        ▼
AppWorld Python sandbox 执行
        │ apis.<app>.<method>(...)
        ▼
模拟应用 API 与任务私有数据库
        │ 返回值、异常、DB 变化反馈给下一轮模型
        ├─────────────── 回到模型，最多 50 steps
        ▼
Supervisor 最终 task state + 输出 DB changes
        │
        ▼
appworld.evaluator.evaluate_dataset/evaluate_task
        │ 动态加载 data/tasks/<task_id>/ground_truth/evaluation.py
        ▼
逐任务 success → TGC / 按 scenario 最弱变体聚合的 SGC
```

`logger.jsonl` 是最接近顺序轨迹的结构化日志；`lm_calls.jsonl` 保存完整模型请求/响应；`environment_io.md` 保存代码与执行反馈；`api_calls.jsonl` 保存底层 API 请求；`dbs/` 保存状态变化；`evaluation/report.md` 是评分报告。不存在一个天然包含全部层次的单一文件，训练轨迹若需要无损重建，应按 task_id 和 step 顺序组合这些来源。

## 四、完整性核对

| 检查项 | 数量 | 期望 |
|---|---:|---:|
| dev 唯一 task | 57 | 57 |
| 创建 task 输出目录 | 57 | 57 |
| 至少一次 LM 调用 | 57 | 57 |
| 环境交互日志非空 | 57 | 57 |
| finished 标记 | 57 | 57 |
| task-specific evaluation | 57 | 57 |
| 官方 success | 5 | 仅作能力观测 |
| 模型/Agent 失败 | 52 | 不计为基础设施失败 |
| 基础设施/评分失败 | 0 | 0 |

机器可读明细见 `/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/task_status.jsonl`。

## 五、评分结果与口径

- TGC = 100 × 全部 task success 的均值；本次为 `8.8`。
- SGC 先把同一 scenario 的三个 task 组合，并取三个 success 的最小值，再跨 scenario 求均值；本次为 `0.0`。
- task success 只有布尔值：task-specific tests 必须全部通过，没有部分任务分。
- 评分调用链：`appworld run --with-evaluation` → `appworld.cli.evaluate()` → `appworld.evaluator.evaluate_dataset()` → `evaluate_tasks()` → `evaluate_task()` → `data/tasks/<task_id>/ground_truth/evaluation.py`。
- 评分比较运行前任务数据库与本实验结束数据库，并检查 Supervisor 最终答案；不依赖 Docker。

最常见的 evaluator 失败要求：

| requirement | tasks |
|---|---:|
| assert answers match. | 33 |
| assert model changes match spotify.MusicPlayer. | 6 |
| assert the added transaction has amount private_data.grocery_cost. | 3 |
| assert spotify.MusicPlayer has 1 updated using models.changed_records | 3 |
| assert this music player record has updated only in the cursor_position using models.changed_field_names | 3 |
| assert the currently playing song has ID private_data.song_id in the end state. | 3 |
| assert music player's cursor is on the song by private_data.artist_id in the end state. | 3 |
| assert model changes match spotify.UserArtistFollowing. | 3 |
| assert private_data.to_be_followed_artist_ids_by_songs artists have been newly followed. | 3 |
| assert private_data.to_be_followed_artist_ids_by_albums artists have been newly followed. | 3 |
| assert artist_ids from added artists match union of private_data.to_be_followed_artist_ids_by_songs and private_data.to_be_followed_artist_ids_by_albums. | 3 |
| assert receiver_ids of added global text messages match exactly to private_data.no_account_phone_user_ids (ignore order). | 3 |

## 六、模型行为与失败信号

以下信号来自每个任务的执行轨迹，只用于定位 base 模型/Agent 行为，不等同于基础设施失败；同一任务可命中多个信号。

| 轨迹信号 | 涉及任务数 |
|---|---:|
| python_execution_error | 35 |
| no_executable_code | 34 |
| api_validation_error | 14 |
| max_steps_reached | 4 |

Qwen3-8B 当前主要风险通常位于长程 Agent 能力，而不是单轮自然语言生成：需要正确发现 API、理解参数 schema、分页汇总、维护跨轮中间状态、根据异常修正代码、避免臆造结果，并在真正取得答案后准确调用 Supervisor 完成任务。官方 one-shot 示例还可能造成任务策略锚定；本实验保持 Prompt 不变，是为了与 smoke 结果可比。

## 七、运行资源、时间与产物

- 正式推理开始：2026-09-10T21:15:07+08:00。
- 正式推理结束：2026-09-10T23:36:55+08:00。
- 正式运行墙钟时间：2h 21m 48s。
- LM calls：688；底层 API calls：4190。
- LM calls 最多的任务：b119b1f_2=50, b119b1f_1=50, 50e1ac9_2=50, 23cf851_3=50, 23cf851_1=44。
- API calls 最多的任务：57c3486_3=2184, 4fab96f_2=1000, 68ee2c9_3=177, 6c2c621_2=107, 6c2c621_1=76。
- 输入 tokens：3,923,913；输出 tokens：622,880；合计：4,546,793。
- 按每次 LM response 的 start/end 时间累计计算，输出吞吐约 74.74 tokens/s。该值排除了 AppWorld API 和 Python 执行时间。
- 实验目录实际文件占用（不跟随数据符号链接）：275.98 MiB。

关键位置：

- 实验根：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev`
- 实验配置：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev.jsonnet`
- 渲染后配置：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/configs/dev.json`
- 模型服务日志：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/model_server.log`
- aggregate evaluation：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/evaluations/dev.json`
- 每任务产物：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/tasks/<task_id>/`
- 状态清单：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/task_status.jsonl`
- 总运行日志：`/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/logs/run.log`

## 八、基础设施事件与恢复

正式推理前共记录到 2 次 exit=1 的隔离启动检查失败：第一次缺少新 `APPWORLD_CACHE` 下的 evaluator test assets；第二次缺少隔离 config overlay 下的官方 `_generator` 模板。处理方式分别是复制 2.4 MiB 的已验证 tests cache，以及只读符号链接官方 `_generator`。两次均发生在模型服务和任务运行之前，没有形成或覆盖任务轨迹。第三次启动保持模型、Prompt 和 Agent 参数不变。

正式评分阶段还暴露了一个只读边界问题：由于 tasks 是指向原始数据的普通符号链接，Python 导入 57 个 task-specific evaluator 时，对尚无对应缓存的 54 个任务生成了 .pyc。这些文件只是解释器字节码缓存，不参与任务输入、数据库状态或评分语义，因此不改变本次分数；但它们属于对原始数据树的意外写入。按不再修改原始目录的约束，本次保留现场、不做删除；后续脚本通过 PYTHONDONTWRITEBYTECODE=1 阻止同类写入。

由于官方配置含 `skip_if_finished=true`，如进程中断，可使用同一个实验根重新运行：

```bash
/root/autodl-tmp/workspace-tw/scripts/run_appworld_qwen3_react_full_dev.sh /root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev
```

runner 会跳过已有 `misc/finished` 的 task，只执行未完成任务；不要使用 `--clear-first`。

## 九、最终判断

完整 dev 的推理与评分链路已跑通。

能力分数只说明当前 8B base 模型在固定 one-shot ReAct scaffold 下的端到端任务成功率；它不应与基础设施可用性混为一谈。后续模型改进应优先考虑高质量工具轨迹 SFT、API schema/分页/状态管理专项数据、执行反馈驱动的纠错训练，以及在冻结 dev/test 前建立小规模可迭代诊断集。
