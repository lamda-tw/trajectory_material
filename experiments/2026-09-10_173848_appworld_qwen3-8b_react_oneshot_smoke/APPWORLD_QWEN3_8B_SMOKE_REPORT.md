# Qwen3-8B 在 AppWorld Dev 上的初步验证报告

**实验日期：** 2026-09-10  
**实验性质：** 环境与端到端能力冒烟测试（smoke test），不是完整基准测试  
**模型：** 未经 AppWorld 专项训练的本地 Qwen3-8B  
**评测配置：** 官方 Simplified ReAct Code Agent + 官方 one-shot Prompt + 官方状态评测器

## 一、管理摘要

本次实验的首要目标，是确认本地 Qwen3-8B 能否在 AppWorld 中完成“读取任务—调用虚拟应用—提交答案—自动评分”的完整闭环，而不是直接给出模型在完整 AppWorld 上的最终能力结论。

结论如下：

1. **环境链路已经跑通。** Qwen3-8B 能通过 vLLM 启动，本地 OpenAI-compatible 服务、官方 ReAct Agent、AppWorld 虚拟应用、轨迹保存和官方评分均正常工作，全程不需要 Docker。
2. **该场景上的能力没有通过。** 本次选择 dev 中一个完整场景的 3 个参数化变体，3 题均失败，TGC=0.0%，SGC=0.0%。
3. **失败主要来自模型的工具使用和事实约束能力，而不是环境故障。** 模型可以登录 Spotify、分页读取播放列表、接收并部分修正 API 报错，但不能正确拆解任务、发现所需 API、覆盖歌曲/专辑/播放列表三个数据源，也会在知道信息不足时提交虚构占位答案。
4. **当前结果不能代表完整 dev。** 本地 dev 有 57 个 task、19 个 scenario；本次只有 3 个 task、1 个 scenario，而且三题都属于同一种 Spotify 聚合查询能力。
5. **下一步不建议立即大规模训练。** 应先用少量 dev 场景完成 Prompt、Agent 约束和模型规模的对照实验，确认瓶颈究竟来自 8B 模型容量、官方 one-shot 示例偏置，还是 Agent 缺少执行前后的验证机制，再决定 SFT 或强化学习方案。

## 二、AppWorld 是什么

AppWorld 是面向工具调用和交互式代码 Agent 的评测环境。它不是让模型只回答一道静态问题，而是给模型一个由多个虚拟应用、用户账户和数据库组成的世界。模型需要：

1. 理解自然语言任务；
2. 查询可用 API 及其参数；
3. 生成并执行 Python 代码；
4. 登录和操作虚拟应用；
5. 根据环境返回值或异常继续修正；
6. 最后调用 `apis.supervisor.complete_task(...)` 提交结果。

AppWorld 使用任务专用 Python 单元测试比较执行前后的数据库状态和最终答案。因此，同一道任务可以有多种合理的操作路径；评分器关注目标是否完成，以及是否造成了额外数据修改。该评分过程直接在本地数据库和 Python 环境中完成，不需要像 SWE-bench 一样为每题启动 Docker。

参考资料：

- 项目主页：https://appworld.dev/
- 官方仓库：https://github.com/StonyBrookNLP/appworld
- 论文：https://arxiv.org/abs/2407.18901

## 三、本次实验设计

### 3.1 范围

本次从 dev 中选择场景 `50e1ac9` 的全部 3 个变体。三个变体拥有相同的能力结构，但使用不同虚拟用户、音乐类型和 Top-K 数量：

| Task ID | 难度 | 任务摘要 |
|---|---:|---|
| `50e1ac9_1` | 2 | 从 Spotify 歌曲、专辑、播放列表库中找播放量最高的 4 首 R&B 歌曲 |
| `50e1ac9_2` | 2 | 从三个 Spotify 库中找播放量最高的 6 首 EDM 歌曲 |
| `50e1ac9_3` | 2 | 从三个 Spotify 库中找播放量最高的 3 首 Indie 歌曲 |

选择一个完整场景而不是随意抽三题，是为了同时验证：

- 单个 task 能否完成；
- 相同能力在不同参数和用户上是否稳定；
- scenario-level 指标能否正常计算。

### 3.2 模型与 Agent 配置

| 项目 | 配置 |
|---|---|
| 模型权重 | `/root/autodl-tmp/models/Qwen3-8B` |
| AppWorld | `0.2.0.dev0` |
| vLLM | `0.10.2` |
| PyTorch | `2.8.0+cu128` |
| Agent | 官方 `simplified_react_code_agent` |
| 模型 preset | 官方 `qwen3-8b-with-reasoning` |
| Prompt | 官方 ReAct Prompt，原样使用 |
| Prompt 类型 | one-shot，内含一个 Spotify 播放列表计数示例 |
| temperature | 0 |
| seed | 100 |
| 单次最大生成 | 3,000 token |
| 最大 Agent 步数 | 50 |
| 模型上下文 | 32K |
| 并行度 | 1，三题串行 |
| GPU | RTX PRO 6000 Blackwell，使用 GPU 0 |

这里的“base 模型”指没有做 AppWorld 专项训练的原始 Qwen3-8B 基线，不等同于对 Qwen3 整个模型系列的最终判断。

### 3.3 数据与目录隔离

原始 benchmark 和模型权重没有修改，也没有复制模型。实验目录中的 `data/api_docs`、`data/base_dbs`、`data/tasks` 是指向原始 AppWorld runtime data 的符号链接，不是完整数据副本。只有 `data/datasets/dev_smoke_50e1ac9.txt` 是新建的 3 行任务清单。

这样组织是因为官方 CLI 在指定 `--root` 后，会同时从 `<root>/data` 读取数据并向 `<root>/experiments/outputs` 写结果。使用分项符号链接既能满足官方目录约定，又能把所有可变输出隔离在本次实验目录内。

## 四、端到端数据流程

```text
dev_smoke_50e1ac9.txt 中的 Task ID
                ↓
读取 tasks 中的任务说明、用户身份和时间
                ↓
从 base_dbs 加载该用户的虚拟应用初始状态
                ↓
官方 one-shot ReAct Prompt + 当前真实任务
                ↓
本地 vLLM 将请求发送给 Qwen3-8B
                ↓
模型生成 reasoning + Python 代码
                ↓
AppWorld 提取代码并在虚拟世界执行
                ↓
代码通过 apis.* 调用 Spotify / Supervisor 等虚拟 API
                ↓
返回值、stdout 或 traceback 作为下一轮 observation
                ↓
模型继续生成代码，直到 complete_task 或达到步数限制
                ↓
保存模型调用、环境交互、API 调用和数据库变化
                ↓
任务专用 ground_truth/evaluation.py 执行状态单元测试
                ↓
汇总 task success、TGC 和 SGC
```

一次模型调用并不等于一次 API 调用。一轮模型可能生成一段包含多个 API 调用的 Python 代码；AppWorld 执行整段代码后，才把结果作为一个 observation 返回给模型。

## 五、总体结果

| Task ID | 模型调用 | API 调用 | 输入 Token | 输出 Token | 答案检查 | 无额外修改检查 | Task 成功 |
|---|---:|---:|---:|---:|---|---|---|
| `50e1ac9_1` | 2 | 1 | 6,556 | 2,370 | 失败 | 通过 | 否 |
| `50e1ac9_2` | 3 | 8 | 11,147 | 4,026 | 失败 | 通过 | 否 |
| `50e1ac9_3` | 6 | 22 | 25,098 | 7,399 | 失败 | 通过 | 否 |
| **合计** | **11** | **31** | **42,801** | **13,795** | — | — | **0/3** |

官方汇总：

| 指标 | 结果 | 含义 |
|---|---:|---|
| TGC | 0.0% | 三个 task 中没有一个通过全部测试 |
| SGC | 0.0% | 该 scenario 的三个变体没有全部成功 |

成功运行阶段约耗时 5 分钟，其中 Agent 执行三题约 244 秒。模型完成初始化后生成速度约 73–77 token/s。本地推理费用为 0，但保留了 token 用量记录。

## 六、三个任务的实际推理过程与失败原因

### 6.1 `50e1ac9_1`：过早判定不可完成

任务要求返回 Top 4 R&B 歌曲。

模型第一轮进行了较长的文字推理，但没有生成任何可执行代码。环境记录为：

```text
No code available to execute.
```

模型随后直接提交：

```python
apis.supervisor.complete_task(status="fail")
```

该题只有 1 次底层 API 调用，即最终向 Supervisor 提交失败；模型没有查询 API 文档、没有登录 Spotify，也没有读取任何歌曲、专辑或播放列表数据。

失败原因：

- 将“暂时不知道用哪个 API”误判为“任务不可能完成”；
- 没有使用 Prompt 中提供的 `apis.api_docs` 自助查询能力；
- 缺乏“失败前必须尝试工具发现”的约束；
- base 模型在复杂工具问题上表现出明显的低探索性和过早退出。

### 6.2 `50e1ac9_2`：能修正参数错误，但用占位符伪造答案

任务要求返回 Top 6 EDM 歌曲。

第一轮，模型完成了登录，并调用播放列表库：

```python
playlist_page = apis.spotify.show_playlist_library(
    access_token=spotify_access_token,
    sort_by="+like_count",
    page_index=0,
    page_limit=100
)
```

AppWorld 返回 422：`page_limit` 最大只能为 20。

第二轮，模型成功将 `page_limit` 改为 20，并完成分页。这说明模型具备一定的局部错误修复能力。但后续代码直接把整数 song ID 拼成虚假歌名：

```python
song_titles.append(f"EDM_Song_{song_id}")
```

最终提交：

```text
EDM_Song_100,EDM_Song_102,EDM_Song_104,
EDM_Song_168,EDM_Song_177,EDM_Song_262
```

评分器中的正确答案是六个真实歌曲标题，因此答案测试失败。

失败原因：

- 只读取了播放列表库，没有覆盖题目明确要求的歌曲库和专辑库；
- 把歌曲在播放列表中出现的次数错误当成播放次数；
- 没有查询 song ID 对应的真实标题、genre 和 play count；
- 没有验证歌曲是否属于 EDM；
- 明知代码使用 placeholder，仍调用 `complete_task` 提交；
- 直接违反官方 Prompt 中“Never invent or guess values”的明确要求。

这说明模型可以完成浅层 API 调用和局部报错修复，但缺乏从任务语义到数据字段的可靠映射，也缺乏最终答案的事实性校验。

### 6.3 `50e1ac9_3`：多轮尝试但没有形成正确恢复策略

任务要求返回 Top 3 Indie 歌曲。

第一轮，模型读取播放列表和 `song_ids`，随后把整数 song ID 当字符串检查：

```python
"indie" in song
```

环境返回：

```text
TypeError: argument of type 'int' is not iterable
```

第二轮，模型意识到需要查询歌曲详情，尝试：

```python
apis.spotify.show_song(
    access_token=spotify_access_token,
    song_id=song_id
)
```

但该 API 只允许 `song_id`，环境明确返回参数错误。模型没有调用 API 文档确认签名，而是第三轮改走 `show_playlist`，又错误假设返回中存在 `songs` 对象及歌曲标题。

第三轮代码虽然没有抛异常，却没有得到有效歌曲列表。之后连续两轮没有生成可执行代码，环境均返回：

```text
No code available to execute.
```

第六轮最终提交占位答案：

```python
apis.supervisor.complete_task(answer="song1,song2,song3")
```

失败原因：

- 对 API schema 进行猜测，没有查询官方 API 文档；
- 可以识别局部错误，却不能将错误转化为正确的下一步工具发现；
- 重复登录、重复分页，消耗大量 token 和 API 调用；
- 仍然只围绕播放列表处理，没有完整覆盖三个数据源；
- 用标题中是否含 `indie` 判断 genre，语义上不成立；
- 在没有任何证据支持的情况下提交 `song1,song2,song3`。

该题用了 6 次模型调用、22 次 API 调用和 32,497 token，仍未完成目标，说明当前问题不只是“推理步数不够”，而是推理方向、API grounding 和停止条件存在缺陷。

## 七、评分是如何完成的

推理结束后，`appworld run --with-evaluation` 自动调用：

```text
appworld/cli.py::evaluate
    → appworld/evaluator.py::evaluate_dataset
    → appworld/evaluator.py::evaluate_tasks
    → appworld/evaluator.py::evaluate_task
    → 当前任务的 ground_truth/evaluation.py::evaluate
```

通用评分器：

```text
/root/autodl-tmp/envs/appworld-0.2.0-py312/
lib/python3.12/site-packages/appworld/evaluator.py
```

本场景各变体都有自己的任务专用评分文件。例如 `50e1ac9_2` 使用：

```text
/root/autodl-tmp/data/benchmarks/appworld/runtime/data/tasks/
50e1ac9_2/ground_truth/evaluation.py
```

评分器加载任务初始数据库和实验输出中的最终数据库变化，然后执行两个断言：

1. 提交的歌曲标题集合与 ground truth 一致，比较时忽略顺序并进行文本归一化；
2. 查询型任务不得修改任何应用数据。

三个任务都通过了“无额外数据库修改”，但都没有通过“答案匹配”。AppWorld 对 task success 的定义是所有测试全部通过，而不是按测试通过比例给部分分，因此每题均记为失败。

TGC 是所有 task success 的平均值；SGC 先对同一 scenario 的变体取最小值，因此一个 scenario 只有全部变体成功才算成功。

## 八、如何理解当前 base 模型的问题

### 8.1 已证明具备的能力

- 本地模型服务和 32K 上下文正常；
- 能理解基本登录流程；
- 能生成可执行 Python；
- 能调用 Supervisor 和 Spotify API；
- 能根据明确的 422 错误修正 `page_limit`；
- 能进行基本分页；
- 没有对虚拟应用造成额外数据修改。

### 8.2 暴露出的核心短板

1. **API grounding 弱。** 模型依赖回忆和猜测 API 名称、参数与返回结构，而不是主动读取 `api_docs`。
2. **任务分解不完整。** 题目明确要求歌曲库、专辑库和播放列表库，模型始终主要处理播放列表。
3. **业务语义理解错误。** 播放列表出现频次不等于播放量，歌名包含 `indie` 也不等于歌曲 genre。
4. **幻觉抑制失败。** 模型知道信息不足，仍生成 `EDM_Song_<id>` 和 `song1` 等占位答案。
5. **错误恢复浅层化。** 能修改报错的单个参数，但不能重新规划数据获取路径。
6. **推理效率低。** 第三题消耗超过 3.2 万 token，包含重复认证、重复分页和无代码轮次，却没有增加有效证据。
7. **完成条件缺乏自检。** Agent 没有阻止模型在答案包含 placeholder 或没有真实歌曲记录时调用 `complete_task`。

### 8.3 Prompt 与 Agent 框架的影响

失败不能全部归因于模型权重。官方 one-shot 示例本身是一个“统计 Spotify 播放列表数量”的任务，主要演示 `show_playlist_library`。模型三题都强烈围绕播放列表 API 展开，可能受到了示例锚定。

此外，Simplified ReAct Agent 允许模型自由输出 Python，并默认相信模型的 `complete_task`。它没有强制：

- 在不确定 API 时先查询文档；
- 覆盖任务提到的所有数据源；
- 禁止 placeholder；
- 提交前验证答案数量、类型和证据来源。

因此，当前 0 分应理解为“Qwen3-8B + 当前官方 one-shot ReAct 配置”的结果，而不是单独对 Qwen3-8B 权重下结论。

## 九、建议的改进方向

### 优先级 P0：先改推理约束，不训练

1. 在 Prompt 中加入强制流程：
   - 未确认 API 签名前必须调用 `apis.api_docs`；
   - 明确列出任务涉及的数据源并逐项完成；
   - 禁止提交 placeholder、推测值和 mock 值；
   - `complete_task` 前检查结果数量、genre、play count 和真实标题来源。
2. 增加 Agent 侧的提交拦截：若答案包含 `song1`、`placeholder`、`EDM_Song_` 等模式，拒绝提交并要求继续查证。
3. 增加执行后验证步骤：将模型得到的候选歌曲重新查询一次，检查标题、genre、play count 和 Top-K 排序。
4. 对比官方 with-reasoning 与 without-reasoning。当前长推理并没有带来更好的工具使用，反而出现反复自我讨论。
5. 对比自由代码 ReAct 和结构化 function-calling Agent，判断严格工具 schema 是否能减少错误参数和虚构 API。

### 优先级 P1：建立模型容量基线

在相同 Prompt、相同 task、相同 seed 下，对比：

- Qwen3-8B；
- 更大规模 Qwen3；
- Qwen Coder 或更强工具调用模型。

如果更大模型无需训练即可完成，而 8B 持续失败，说明主要瓶颈是模型容量；如果所有模型都被同一示例和流程误导，则应优先改 Agent/Prompt，而不是训练。

### 优先级 P2：再进行 AppWorld 专项训练

若确定 8B 是部署目标，可在 AppWorld train split 上进行：

1. **SFT：** 使用成功轨迹训练 API 文档查询、任务分解、异常恢复和最终验证；
2. **错误对照训练：** 将本次 `EDM_Song_<id>`、`song1` 等失败轨迹作为负例，训练模型识别“无证据提交”；
3. **偏好优化：** 对“查询文档后得到真实结果”和“直接猜值”建立成对偏好数据；
4. **基于 evaluator 的强化学习：** 使用 task success 或测试通过情况作为回报，但应先解决 rollout 成本和长轨迹稳定性。

训练数据必须只使用 train split；dev 用于模型和 Prompt 选择，`test_normal` 应在方案冻结后一次性运行，避免测试集污染。

### 优先级 P3：逐步扩大评测范围

建议后续顺序：

| 阶段 | 建议范围 | 目标 |
|---|---|---|
| A | 当前 1 scenario / 3 tasks | 已完成：验证全链路 |
| B | dev 中 5–10 个不同类型 scenario | 比较 Prompt、Agent、模型规模 |
| C | 完整 dev：57 tasks / 19 scenarios | 选择最终配置并分析稳定性 |
| D | 完整 `test_normal`：168 tasks / 56 scenarios | 在配置冻结后报告正式性能 |

## 十、当前结论与决策建议

本次实验已经排除了“AppWorld 环境装不起来”“本地模型无法接入”“必须依赖 Docker”“评分器不能运行”等工程风险。当前主要风险转移到了模型和 Agent 层：Qwen3-8B 在复杂跨库查询中缺乏可靠的 API grounding、语义规划、错误恢复和答案自检。

建议近期目标不是直接跑完整 test，也不是马上投入大规模训练，而是先用少量代表性 dev 场景完成以下四组对照：

1. 官方 Prompt vs 增加强制 API discovery 的 Prompt；
2. reasoning vs without-reasoning；
3. 自由代码 ReAct vs 结构化 function calling；
4. Qwen3-8B vs 更大或更偏代码/工具调用的 Qwen 模型。

这些对照可以用较低成本判断：是继续优化 8B Agent、对 8B 做专项训练，还是直接换用更强基座更合理。

## 附录 A：结果与轨迹文件

实验根目录：

```text
/root/autodl-tmp/workspace-tw/experiments/
2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke
```

主要文件：

```text
README.md                                      实验范围简述
config/official_react_instructions.txt         本次使用的官方 Prompt
data/datasets/dev_smoke_50e1ac9.txt            三个 Task ID
logs/run.log                                   启动和运行总日志
experiments/outputs/.../configs/               最终 Agent/模型配置
experiments/outputs/.../model_server.log        vLLM 日志
experiments/outputs/.../evaluations/            TGC/SGC 汇总
experiments/outputs/.../tasks/<task_id>/logs/   每题轨迹
experiments/outputs/.../tasks/<task_id>/dbs/    每题最终数据库变化
experiments/outputs/.../tasks/<task_id>/evaluation/report.md
                                                每题评分明细
```

每题日志含义：

| 文件 | 含义 |
|---|---|
| `lm_calls.jsonl` | 每次模型请求的完整累计 messages、请求参数、原始响应和 token 用量 |
| `logger.jsonl` | 官方结构化 Agent 轨迹，按顺序交替记录 agent 与 environment |
| `logger.log` | 面向人工阅读的控制台格式轨迹 |
| `environment_io.md` | 每轮被执行的 Python 代码及 stdout/异常 |
| `api_calls.jsonl` | 代码执行过程中产生的底层 AppWorld API 请求 |
| `misc/usage.json` | 当前任务累计 token 与成本 |
| `misc/finished` | runner 完成标记，不代表答题成功 |

## 附录 B：可复现脚本

```text
/root/autodl-tmp/workspace-tw/scripts/
run_appworld_qwen3_react_smoke.sh
```

脚本已固定模型位置、Agent、数据集、Prompt preset、seed、temperature、vLLM 参数和缓存位置，并加入同模型服务冲突检查及退出清理。为了保护已有实验结果，官方配置会跳过带 `misc/finished` 标记的任务；做全新复现实验时应复制配置并使用新的时间戳实验目录。
