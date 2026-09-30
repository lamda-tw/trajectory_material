# Dynamic Capability-Frontier Step Training：数据、算法与创新性审查

原文日期：2026-09-28。下文保留当时的研究方案和文献审查，最新执行状态见下一段。

**2026-09-29最新结果：** Action-1epoch在Dev57上成功31/57（54.4%），测试条件通过215/291（73.88%）。通过既有接受门槛，可在后续第8步使用该候选；本次未启动来源60题刷新。[第7c步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md)。

**此前执行进展：** 旧第6–7步已完成并保留；第6b步三个分支各训练1轮及第7b步检查30题均已完成，State 17/30、Action 19/30、Mixed 15/30。按冻结规则选择CFST-Action-1epoch作为Dev57候选，尚未接受为新学生；Dev57未运行。详见 [1epoch计划](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/STEP06_ONE_EPOCH_PLAN.md) 与 [滚动待办](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md)。下文保留原始文献审查，不作为最新执行参数。

后续已将方法收敛为“跨任务修复收益驱动的选择”，第一实验以 [METHOD_PROPOSAL.md](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md) 为准；本文保留为原始拆解与文献审查。

本文读取了聊天《AppWorld方法调研探索》中的完整 CFST 讨论，查阅本项目 train90 数据、LoRA/FFT 训练与评测记录，并核对下列论文原文。本文不是重新包装既有结果：已有实验事实、手工解释性标注、拟议算法、尚待验证的假设分别注明。

最值得验证的问题是：**在相同训练预算下，按“当前模型缺什么，以及学习某一步能否改善其他任务”选择监督步骤，是否比按步骤重要性或高 loss 选择更有效？** 现在还不能宣称方法新颖性成立，更不能宣称能够提升 AppWorld 分数。

## 1. 当前项目到底已经完成了什么

### 1.1 数据与训练单位

源文件是 [train.jsonl](/root/autodl-tmp/workspace-tw/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/train.jsonl)。它包含 90 条 Codex 最终成功轨迹、30 个 task family、1,170 个下一步决策样本，每个任务 7–28 步，平均 13 步。

**当前已经是 step-level completion-only SFT。** 每行有 `id / metadata / prompt / completion / tools`；`prompt` 是官方 one-shot 提示、实际任务和截至该步之前的完整模型可见交互，`completion` 是当前一步的可见 reasoning 与 Python 代码。历史消息和 observation 的 label 为 `-100`，只监督当前 completion。原始 observation 已脱敏，并沿用采样时的每次 24,000 字符截断；不是无损全环境日志。

所以“把 90 条轨迹拆成 steps”不是新工作。CFST 要改变的是 **1,170 个现有正目标的准入、选择和权重**。历史中的未选步骤仍保留为上下文。每一步后面才得到的 observation 不能提前放进该步 prompt。

统计依据：数据 [README](/root/autodl-tmp/workspace-tw/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/README.md)、[validation.json](/root/autodl-tmp/workspace-tw/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/validation.json)、转换器及训练器；本次复核结果在 [data_audit.json](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/data_audit.json)。数据 SHA-256：`1f5ea51ea22ce7ef6b84d3e16bbb25976179064f7c8d0483ab7dcb0118ed3220`。

| 实际数据特征 | 数值 | 能说明什么 |
|---|---:|---|
| 每遍 completion tokens | 94,553 | 来自既有 tokenizer 逐样本统计，包含当前目标的 reasoning、代码及模板目标部分 |
| 仅直接调用文档 API 的动作 | 560/1170，47.9% | 静态动作类别，不是“理解文档”能力占比 |
| 上述动作的目标 tokens | 30,415/94,553，32.2% | 说明按步数选 30% 不等于按监督 tokens 选 30% |
| 含其他直接 API 调用的动作 | 575；58,573 目标 tokens | 包括读取、认证、提交、修改；不能等同于正确业务操作 |
| 无直接 `apis.*` 调用的 Python 动作 | 35；5,565 目标 tokens | 可能包括本地计算、函数封装与间接调用 |
| 最长完整训练样本 | 37,015 tokens | 训练窗口 40,960 下无额外 token 截断 |
| 成功轨迹内执行报错的动作 | 9 个，分属 9 条轨迹 | 这些动作也进入了当前 SFT 的 completion 正目标 |

分类是 Python AST 的直接调用统计，无法识别所有别名、动态调用、实际状态变化。**不能由 47.9% 推出文档步骤应该删除。** 模型可能需要学习查文档，也可能需要学习何时停止查询。

90/90 是原采样轨迹官方 evaluator 成功；JSONL 的 `clean_replay_success` 为 `null`。因此不能把当前数据描述成“每个前缀都已独立干净重放验证”。分支实验还需验证状态恢复。

### 1.2 已有模型结果

| 模型 | Dev TGC | Test-normal TGC | Test-normal SGC |
|---|---:|---:|---:|
| train90 LoRA 第5轮 | 23/57，40.4% | 51/168，30.4% | 9/56，16.1% |
| train90 FFT 第5轮 | 12/57，21.1% | 28/168，16.7% | 3/56，5.4% |
| train90 FFT 两轮重训，沿五轮学习率路径提前停止 | 本轮未见对应 Dev 报告 | 28/168，16.7% | 5/56，8.9% |

依据：[LoRA Dev](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/REPORT.md)、[LoRA Test](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/REPORT.md)、[FFT Dev](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md)、[FFT Test](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md)、[FFT 两轮对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md)。

这里必须保留四条解释边界：

1. LoRA 是 rank 8、alpha 16、LR 2e-4；FFT 是全参数、峰值 LR 1e-5、warmup+cosine，且主参数/优化器精度等不同。不是只改变参数更新范围的消融。
2. FFT 第5轮平均训练 loss 0.016795，但闭环分数低于 LoRA；这支持“拟合教师不等于完成任务”，不证明原因就是学了无效步骤。
3. FFT 两轮和五轮 Test 总成功数相同，各自还有 11 个独有成功任务；不能用这两点宣布“第五轮过拟合”，也不能宣布“过拟合被排除”。两轮是重训，不是同一次训练保存的原第2轮权重。
4. train90 模型评测协议为无 reasoning parser、32,000 context、50 turns、每轮 3,000 输出 tokens。历史 base 分数使用不同解析协议，不能直接作为严格权重消融。论文中的 Dev60 也不能替代本项目真实的 Dev57。

“部分 SFT”有两条独立轴：**选择哪些训练样本/目标 tokens** 与 **更新哪些参数**。CFST 讨论前者；LoRA/FFT 讨论后者。选步骤并不意味着找到“专管状态理解”的神经元，也不是逐能力更新不同参数块。

## 2. 先用真实数据解释 CFST

### 2.1 Spotify 清理任务：哪些步骤可能值得学

真实任务 `229360a_3`：歌库保留已点赞或已下载的歌；专辑库保留已点赞或全部歌曲都已下载的专辑；歌单库保持不变。原始轨迹有 10 步，见 [逐任务数据](/root/autodl-tmp/workspace-tw/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/tasks/229360a_3.json)。

下表的能力是本次阅读数据后的**解释性草案**，不是经过实验验证的能力标签；“候选处理”不是已生成的选择结果。

| 步骤 | 真实动作 | 可能涉及的能力 | CFST 会进一步问什么 |
|---|---|---|---|
| 1–2 | 找 Spotify API，读认证规格 | 文档使用、工具选择 | 当前模型在相同状态已能稳定做到吗？ |
| 3 | 取凭据并登录，保存 access token | 参数绑定、状态维护 | 是否缺少这类能力，还是已经掌握？ |
| 4 | 读取列库、点赞、下载、移除等规格 | 文档使用、计划 | 查的是必要的新文档，还是重复已知信息？ |
| 5 | 全分页读取，计算要删的歌曲/专辑集合 | 状态理解、集合逻辑、参数绑定、计划 | 是否正确实现 OR、全集分页、专辑全下载条件？ |
| 6–7 | 按计算出的 ID 删除歌曲和专辑 | 工具选择、grounding、状态修改 | 是否仅影响目标对象并保留受保护状态？ |
| 8 | 再次全分页读取，核验剩余集合 | 验证、状态理解 | 会不会重新读状态核验，而非只看 API 未报错？ |
| 9–10 | 读完成接口并提交 | 文档使用、终止判断 | 是否已经满足目标；完成动作的参数能否复用？ |

第5步关键片段来自真实 completion：

```python
song_ids_to_keep = liked_song_ids | downloaded_song_ids
songs_to_remove = [song for song in song_library
                   if song["song_id"] not in song_ids_to_keep]
albums_to_remove = [
    album for album in album_library
    if album["album_id"] not in liked_album_ids
    and not set(album["song_ids"]).issubset(downloaded_song_ids)
]
```

训练这个目标，期望学会的是“把自然语言的保留条件转成正确集合运算，并把结果用于后续动作”。是否真的学会，要看它能否在其他 family 中正确处理类似逻辑。不能因为代码中有集合运算就把目标标成“能迁移”。这一步本身是 418 个目标 tokens，而第8步为 213 tokens，预算不能按两个等价的“步”粗略计算。

举一个**纯示意、未测量**的判断过程：若当前 Qwen 在登录状态上 8/8 次成功，在构造保留集合时仅 2/8 次正确，且训练后能改善其他 family 的集合筛选，则第5步可能比第3步更值得进入本轮监督。下一轮若第5步已掌握，就可能把预算移向验证/恢复步骤。实际不能只靠 8 次采样认定掌握；应保留样本量和区间，并检查确定性生成与不同有效实现。

### 2.2 更能说明“能力”的错误恢复例子

`76f2c72_1` 第16步调用 Gmail 查询，传了 `archived=None`，环境报参数类型错误；第17步去掉该可选参数并重新分页。原始第16步目前也被当作正 completion 训练。CFST 的质量检查应将明确错误的目标排除或送审，而保留它在第17步历史中的位置；第17步才是待评估的恢复正例。

`ce359b5_2` 第7步更有意思：删除循环执行后，**打印含 tuple 字典键的结果**时发生序列化错误；第8步选择重新查询当前状态，而不是盲目重跑删除循环。这个例子同时涉及“报错发生在哪个阶段”“哪些状态修改已经生效”“是否需要重试”。因此不能把每个报错动作全部判为语义无用，也不能把 `Exception` 自动等同于状态未变。

这些真实目标、样本 ID、token 数及待填字段保存在 [annotation_examples.json](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/annotation_examples.json)。所有 deficit、transfer、criticality、selection 都是 `null`，防止把示意当实测。

## 3. 数据上新增什么，而不是只新增一个名字

第一版保留原 `train.jsonl` 不变，为每个 `sample_id` 增加外部记录：

```json
{
  "id": "229360a_3::assistant-0005",
  "task_family": "229360a",
  "capability_labels": ["state", "ground", "plan"],
  "label_status": "manual_draft",
  "target_quality": "requires_local_verification",
  "checkpoint_id": null,
  "local_verifier_id": null,
  "local_successes": null,
  "local_rollouts": null,
  "transfer_probe_split": null,
  "transfer_proxy": null,
  "measured_transfer": null,
  "round": null,
  "selected": null,
  "completion_tokens": 418
}
```

正式记录还要包含：源文件哈希、标注依据的历史 message/代码位置、标注置信度、验证器版本、重放环境版本、采样 seed/temperature、分支预算、模型/adapter/优化器状态标识、评分时间和评分成本。相同 step 在不同模型/轮次上的测量必须另存，不能覆盖成一个“永久难度”。

训练时最简单的实现是按 `selected_id` 导出原行的子集：**整行原 prompt + 原 completion**。不把能力标签或未来 evaluator 结果附加到模型 prompt，也不把不同任务的片段拼在一起。若以后用权重，则训练器需显式读取权重；仅在 JSON 增加字段不会自动改变 loss。

离线选择可以先只利用现有正轨迹。动态扩充还需另外采集当前 Qwen 在 **train tasks** 上的真实成功、失败与修复分支：专家成功状态不覆盖 Qwen 自己走偏后的所有状态，反复给同一个固定池打分并不能解决这种分布差异。

## 4. 算法模块：每项的输入、输出和证据强度

定义 `x_i=(q,h_i,a_i,e_i,o_i)`：任务 q、动作前的模型可见历史 h、目标动作 a、可恢复的执行前环境状态 e、执行后的 observation o。SFT 只学习 `a_i | q,h_i`；e/o 用于离线审计或执行评分，不能泄露到动作前输入。

```mermaid
flowchart LR
    A[教师步骤池和当前模型训练任务轨迹] --> B[目标有效性检查]
    B --> C[能力与证据标注]
    C --> D[当前模型局部执行诊断]
    D --> E[跨任务迁移估计和小规模训练核验]
    E --> F[固定预算选步骤]
    F --> G[保留历史的选择式 LoRA SFT]
    G --> H[独立评估与新一轮训练任务 rollout]
    H --> D
```

### M0：目标有效性与状态恢复

输入是现有行与源采样日志，输出是 `valid / invalid / uncertain` 和证据。最终成功不保证每一步都适合作为正目标。明确的错误调用默认不作为正目标；有部分有效副作用的错误步骤送审，保留其历史供后续恢复学习。未知不应伪标正确。

执行诊断必须重建当时的**数据库状态、REPL 变量、认证会话、时间/随机状态**。把历史文本发给模型并不等于恢复了 Python 变量。MVP 可以为每个分支新建任务环境，依次重放前 i−1 个动作，核对模型可见 observation 后再执行候选；后续再做 snapshot 优化。脱敏凭据应在环境内部通过正常 API 重新取得，不从脱敏文本还原。

这会有成本：仅把现有每条轨迹所有前缀分别重放一次，就要执行 `sum_q L_q(L_q−1)/2` 次历史动作，分支会再乘采样次数。必须计入总预算。第一个纯离线分析阶段不需要运行这些分支。

### M1：能力签名 z

沿用原讨论的八类作为工作分类：

| 标签 | 可观察决策 | 容易混淆之处 |
|---|---|---|
| plan | 选择下一个子目标和依赖顺序 | 推理文本说有计划，不代表实际执行正确 |
| doc | 找到所需规格并正确利用 | 调用了文档 API，不代表理解规格 |
| tool | 选择适合目标的 API | 函数名相同，不保证状态适用 |
| ground | 从历史绑定正确 ID、时间、对象和参数 | 不能只检查参数类型 |
| state | 理解返回结构、集合条件、分页及已发生副作用 | Python 未报错不等于状态理解正确 |
| crossapp | 不同应用间实体匹配和信息组合 | 仅完成跨应用登录不等于业务组合 |
| recover | 按错误来源改变动作并考虑已生效操作 | 机械重试不等于恢复 |
| verify | 检查约束、完成程度和终止条件 | 调用 complete_task 不等于任务成功 |

上下文追踪是多类共享的依赖轴：ground/state/recover 等都可能用到较早 observation。额外记录“依赖哪条历史证据、距离多少 tokens”，比把一切读历史都塞进第九个类别更可操作。一项 completion 可有多个标签，八类并不互斥，也不是已证明独立的潜在能力。

第一阶段用人工审查与代码/日志证据标注，不以 LLM 标签充当因果结论。对一批样本双人独立标注、报告一致性和不确定项；无法稳定分开的类先合并。

### M2：当前模型的能力缺口 D

便宜诊断是目标平均 NLL：`−log p_theta(a_i|h_i)/|a_i|`。它能衡量不熟悉教师写法，但不能直接衡量动作正确性。变量重命名、不同有效 API 路径、reasoning 风格均会改变 NLL。

更可靠的局部指标是：从相同真实前缀状态采样 K 个候选，执行后用该局部子目标的检查器验收，得到 `p_hat_i=successes/K`、`D_i=1−p_hat_i`。检查应区分语法、schema、目标参数、状态不变量和子目标，而不是只做字符串匹配或“能运行”。

例：第5步检查分页完整、保留/删除集合是否正确、是否提前误改状态；第8步检查是否真的读取了当前状态并正确判断目标。局部验证器需要另行构建和审查，AppWorld 最终 evaluator 不会自动提供所有正确的逐步标签。纯文档读取和只读规划可能使最终断言通过率保持不变，不能据此给它零价值。

尚无合格验证器的样本保留 unknown；NLL、强模型判分只能叫 proxy。当前 90 条教师成功记录中没有 Qwen 的这些局部成功率。

### M3：任务相关性 C 与能力依赖探针

原讨论称 C 为 causal importance。第一版可以先统一 `C=1`（通过质量检查的候选），或使用明确标注为 heuristic 的相关性评分。不要默认每条样本都有因果重要性真值。

若估计干预效果，需从同一个状态分别执行专家动作与指定替代动作，再让**同一个固定 continuation policy**继续，比较期望成功率。结果依赖替代动作、续跑策略、预算和环境；不能把删掉一行后固定后缀出现变量未定义称为干净的因果证据。读取文档的作用还通过 agent 可见历史发生，不能只干预数据库而忽略信息状态。

上下文遮蔽实验 `L(a|h_without_evidence)−L(a|h)` 测到的是**对被移除信息的敏感性**。遮掉 docs/error/history 往往同时改变多个因素并制造不自然输入；它不直接证明模型获得了某个独立能力，更不证明训练该步会提升该能力。

更合理的辅助探针包括：相关证据遮蔽对照等长度无关证据遮蔽；多种扰动复测；实体 ID 做一致双射替换时，同时变换输入、动作目标和可执行环境。只替换历史 ID、仍要求原 ID 答案，测到的是目标不一致。上述探针是诊断证据，主要创新仍需通过实际训练干预与跨 family 评估建立。

### M4：跨任务训练效用 T——最应当验证的模块

先定义想测的量，再选近似计算方式。对于来自其他 family 的能力 c 探针，理想量是：

\[
\Delta_{i,c}=J_c\bigl(\operatorname{Update}(\theta_t,\{x_i\},B)\bigr)-J_c(\theta_t),
\]

其中 Update 的优化器、步数和 token 预算 B 都固定，J 是其他任务上的局部执行正确率或闭环成功率。实际中单一样本效果小且噪声大，优先测同能力的一小组样本，再与长度/领域/初始难度匹配的随机组比较。每个分支从相同模型与优化器状态出发，多个 seed 重复。训练作用依赖样本组合与当前参数，不是每个 step 固有、可简单相加的价值。

为了降低逐个重训的成本，可用 LoRA 参数空间的梯度估计：设 \(g_i=\nabla_\phi\ell_i\)，\(g_p=\nabla_\phi\ell_p\)。小学习率 SGD 下，探针 loss 的一阶下降预测为 \(\eta g_p^\top g_i\)；原讨论的 cosine 是方向相似性，忽略梯度模长，只能称作排序 proxy。

建议记录：

\[
\widehat T_{i,c}=\frac1{|\mathcal P_c|}\sum_{p\in\mathcal P_c}\cos(g_p,u_i),
\]

u 是训练样本的拟议下降方向；SGD 时为 g，AdamW 时需明确如何利用当前动量和预条件器。不要把两个 Adam 预条件梯度的 cosine 自动解释成 probe loss 下降。更忠实的预测是 \(g_p^\top u_i\)，并应核对它是否预测真实小步更新的效果。

这直接借鉴 [LESS](https://arxiv.org/html/2402.04333v2) 的 optimizer-aware、LoRA 梯度与目标能力数据选择，不能作为新发明。需要独立报告 feature 提取/投影成本、梯度缓存使用哪个 checkpoint、是否在每轮重算。LoRA 初始化时某个因子为零，会造成另一因子的初始梯度退化；不要直接跨随机 adapter 坐标比较梯度。

务实做法是所有对照共享一个仅在候选训练 family 上得到的小规模 warmup 检查点，先验证“warmup 后怎样选择后续训练数据”。warmup tokens 与成本计入每组总预算，不能再宣称全程仅监督30%。若要做从原始 base 开始的选择实验，需要单独设计评分模型与训练初始化关系，不能把二者混写。

真正的迁移证据必须同时满足：跨 family、避免近重复代码/实体模板泄漏、在另一个未参与选择的审计集合上有效、改善行为指标而非只有教师目标 NLL。还应看同能力异 API 与同 API 异能力两个对照，区分能力迁移和 API 模板记忆。

### M5：Frontier 选择器

原讨论的工作公式是：

\[
U_t(i)=C_iD_t(i)T_t(i).
\]

它是直观拆解，不是已经成立的理论：难度最高可能是错误目标或暂时学不动；三个估计量的尺度与噪声不同；transfer 可以是负数；直接相乘还会抹去必要的信息获取步骤。论文不能只把三项相乘当作贡献。

一个可实现、但仍待消融的完整版本如下：

1. Q_i 为正目标准入标志。invalid 不进正例池，uncertain 进入待审池。
2. 由多次局部执行得到 p_i 及不确定度，用 \(F_i=4p_i(1-p_i)\) 表示中间难度偏好。它只是 frontier proxy，不是普适最优法则；全失败不等于学不动，全成功不等于已牢固掌握。可用带先验的概率估计，并保留难样本探索预算。
3. 各能力的权重 w_c 从选择用 probe 的能力缺口计算，标准化后限制极端值，避免稀疏小样本能力支配训练。
4. 计算跨能力 transfer 向量；同时保留对其他能力的负面预测。用目标能力的正迁移减去其他能力的负迁移惩罚，得到净效用 \(V_i\)。只展示正 cosine 会掩盖遗忘和干扰。
5. 主排序用 \(\widehat U_i=Q_iF_iV_i\)。C 可以作为可选相关性权重/过滤器加入，但第一版取1，并单独消融；这防止把尚未测出的“因果重要性”硬塞进主方法。
6. 在目标 token 预算下选样，加入能力覆盖、family 数量上限及近重复去重。不能只取同一 family 的大量近似步骤。

为避免净效用定义含糊，可预先固定

\[
V_i=\sum_c w_c z_{i,c}\widehat T_{i,c}-\lambda\sum_c r_c[-\widehat T_{i,c}]_+,
\]

其中 z 是归一化的多标签权重，w 表示希望改善的能力，r 表示需要保留的能力，lambda 控制负迁移惩罚。这只是一个可复现的候选规则，lambda 和权重上限须在内部开发数据上固定。主选择池要求净效用为正；明显预测有害的步骤不因预算剩余而强行补入。另设探索池处理未测量/不确定样本。

主池的离散优化目标为在总目标tokens不超过预算、满足family上限与能力覆盖的条件下，最大化选中样本的效用和。使用固定的贪心或背包近似并记录实际预算偏差；这忽略了样本间更新交互，属于选择近似，不声称全局训练最优。


一种明确的初始预算分配可设为：80% 按净效用选择，10% 给有效但高不确定/全失败的候选探索，10% 为此前掌握能力的 replay。比例只是预注册起点；随机、静态与动态对照也要有相同的探索/replay 预算，才能隔离选择器作用。能力标签多重计数时要规范化覆盖贡献，不能凭多贴标签得到更多配额。

若 V 尚未计算，只能称为 deficit/capability-balanced proxy baseline，不能称完整 CFST。若 F 不预测真实学习增益，应更换或去掉它。所谓 frontier 必须由数据支持，不能先宣布中等难度一定最好。

### M6：选择式 SFT 更新

为保持与当前训练器可比，第一版每个选中样本仍对自身 completion token 求平均，再对样本平均：

\[
\mathcal L(\phi)=\frac{1}{|\mathcal S_t|}\sum_{i\in\mathcal S_t}\frac{-1}{n_i}\sum_{k=1}^{n_i}\log p_{\theta,\phi}(a_{i,k}\mid h_i,a_{i,<k}).
\]

如果采用权重，改成 \(\sum_iw_i\ell_i/\sum_iw_i\)，并同步全部 baseline。改成全局 token-mean 又是一个变量，不能在选择器组中单独更改归约方式。

第一版保留 reasoning+code 的目标定义；仅监督代码、屏蔽固定套话或引入 span-level mask 可以作为后续独立消融，不混进首个对照。一个 Python turn 可能含多次 API 调用、循环和计算；现在的“step”明确指一个 assistant 决策 turn，不等于单个 API call。

选择不会切断上下文的梯度路径：历史 tokens 不直接作为预测标签，但 transformer 仍处理它们，参数可通过选中 completion 的 loss 得到梯度。保留长历史会带来大量算力开销，30% 目标 tokens 不意味着30% GPU时间。

### M7：动态重评分与数据扩充

静态版只在 \(\theta_0\) 选择一次；动态版每个预定阶段后更新 D/T/w，保存每轮选中 ID、能力分布与退出/进入原因。已掌握步骤降低优先级，但保留 replay，不保证永久移除。

动态扩充时，在训练 family 上由当前 Qwen 采样 K 条完整轨迹。失败分支中请教师在**该真实失败状态**提出替代动作，从恢复后的同一状态执行并由 Qwen 续跑验证。成功分支可以贡献修复正例，原错误 action 可存为 preference negative；终局失败中的中间步骤仍需局部验证，不能一概作为负例。

不能拿教师轨迹第10步强行接到学生失败轨迹第10步：两者变量、对象 ID、数据库状态和历史可能不同。只有状态兼容、依赖可用并重新执行验证的目标才入池。偏好训练也必须是相同 h/e 下的正负对。

这部分大量借鉴 CSO。区别只能由“哪些修复经验能迁移、怎样按变化的能力缺口配置训练”建立，不能靠把 DPO 换成 SFT 建立。

### M8：闭环审计、保留与停止

每轮报告局部能力指标、完整任务 TGC/SGC、旧能力保留、额外采集量和全流程计算成本。停止策略在训练内部的 audit/validation 上预设，不用 test_normal 逐轮挑选最优 checkpoint。无法验证 target 的步骤暂停进入正监督，不能用强模型自称正确替代结果。

~~~text
输入：有效教师步骤池、按 family 划分的数据、统一 warmup 模型与优化器
固定：标签规范、局部验证器、轮次数、各类预算、采样与评测协议
每轮 t：
    在训练任务采集/补充当前 policy 的经验（静态实验可关闭）
    审计候选目标和执行前状态，标记能力及证据
    测当前模型局部成功率、能力缺口和不确定性
    用选择用 probes 估计跨 family transfer 与干扰
    按预算、能力覆盖和重复限制选择步骤，加入探索与 replay
    读取选中原行；保留完整历史；执行固定预算的 LoRA SFT
    在独立审计集合评估，记录能力变化与选择集合变化
最终：固定模型和协议，再做正式 Dev/Test 评测
~~~

## 5. 与八篇指定工作的逐项 novelty 对照

以下是对论文方法的概括与本文的判断。表中的差异是**拟议实验需要建立的差异**，不是证明“作者没有考虑泛化”，也不是穷尽全部已有工作。

| 方法与一手来源 | 论文实际做法 | CFST 重叠部分 | 仍可能区分的部分与必要证据 |
|---|---|---|---|
| [ATLAS，2025](https://arxiv.org/html/2503.02197v2)，§3/§4 | 强模型按计划、关键观察、关键动作、自我纠正等类别，从专家轨迹选步骤；保留上下文，mask 其他监督；研究跨任务/环境泛化 | 步骤分类、保留上下文、选择式 SFT 都已有；高 perplexity 选择也在其对照中 | 用当前 learner 的执行缺口及**训练后的跨任务增益**选择；需胜过 ATLAS 及高 loss 对照，而非只增加标签数 |
| [CSO，2026](https://arxiv.org/html/2602.03412v1)，§3.2–3.3 | 从 policy 失败轨迹出发，专家给替代动作、PRM 筛选，学生续跑验证能否变成功，构成 step DPO；明确有 iterative online refinement | policy-relative 缺陷、可达修复、局部监督、动态循环高度重叠；原实验主要是 GAIA/XBench，并非 AppWorld 复现 | 相同修复池中，按跨 family 学习增益筛选是否优于 outcome flip；不能把“CSO静态/只在原任务有效”作为对照论据 |
| [SALT，2025预印本／EACL2026](https://arxiv.org/html/2510.20022v1)，§3 | 同一任务多 rollout 构图，按状态—动作—后状态合并边；共享边的 advantage 跨轨迹平均，差异边保留差异；信号来自最终 reward | step credit、同任务成功/失败对比已有；不是每步调用额外 verifier | CFST 是更新数据选择，跨任务参数更新效用不是 SALT 的图边 advantage。若实验只重分配奖励，就会回到它的范围 |
| [ProCredit，2026-09-23](https://arxiv.org/html/2609.27532v1)，§3 | 执行验收条件给进度势函数；相邻进度差产生 reward；组合 trajectory 和 undiscounted turn advantage | AppWorld 验证进度与 turn credit 已有，不能称为新 verifier reward | 检验“进度贡献大”与“训练价值高”是否分离；需量化学习后其他任务的改善。只读动作即时reward为0并不意味着它的最终 advantage 为0 |
| [CANOPY，2026-09-01](https://arxiv.org/html/2609.01245v1)，§3 | 扩大同任务探索以得到成败混合组；严格每批一次 on-policy 更新、KL约束、动作token平均，测试时加交互预算 | 在线改进、动作mask、能力变化/探索困难不是空白 | 它是强 outcome-only 对照。CFST 需展示相同总成本下选择有收益；不同模型、窗口、turn预算的榜单分数不能直接横比 |
| [AgentEvolver，2025](https://arxiv.org/html/2511.10395v1)，§3–5 | 自主出题、经验引导探索、整条轨迹回看标 GOOD/BAD，把过程与结果信号组合进入 RL | 自我进化、经验重用、步骤归因已有 | 可检验的跨任务更新效用，与 LLM 对过程好坏的评分不同。只多加 capability 标签无法形成强区分 |
| [Skill-SD，2026-04](https://arxiv.org/html/2604.10674v1)，§3 | 成败轨迹总结为自然语言 skills，只给 teacher，student 以普通 prompt rollout；GRPO结合重要性加权 reverse-KL，自同步 teacher | skills/能力指导、动态自蒸馏、参数内化已有 | CFST 选择具体 state-conditioned 训练样本；skills 不是额外 teacher prompt。若未来也加 skill-conditioned distillation，应作为已知组件并与原法比较 |
| [ProST，2025](https://aclanthology.org/2025.ijcnlp-long.179.pdf)，§3/Fig.2 | Orchestrator/Executor/Critic 多角色；按预定轮次渐增子任务，省去错误步骤监督、保留修正步骤 | 子任务课程、错误mask、选择监督均已有；不能把排除错误目标独立称为贡献 | 模型测量驱动的非单调重选与跨任务效用，区别于预定子任务进度表；需保持相同 agent 架构，避免多agent脚手架混杂 |

### 5.1 按模块再检查一次

| 拟议模块 | 最直接的既有模块 | 当前判断 |
|---|---|---|
| M0 屏蔽错误 completion，保留恢复历史 | ProST 等错误mask方法 | 数据质量控制，不是新贡献 |
| M1 步骤能力类别 | ATLAS 类别、Agent-FLAN 数据分解 | 分类规范有实用价值；多加四个标签不足以创新 |
| M2 learner-specific deficit | CSO 当前失败、ATLAS perplexity 对照 | 必要成分，但单独很弱 |
| M3 文本遮蔽和分支效果 | CSO verified branching；ASSAY 的技能随机遮蔽思想 | 需区分信息依赖、技能上下文作用和参数学习效果 |
| M4 能力 probe + 梯度选择 | LESS | 梯度公式直接借鉴；单纯搬到 agent steps 创新风险高 |
| M5 缺口、迁移和干扰联合选样 | targeted data selection / curriculum 的组合 | 候选贡献；要有机制证据及简单组合强基线 |
| M6 completion loss mask | ATLAS 与项目现有 completion-only 管线 | 明确已有 |
| M7 动态循环和修复池 | CSO、AgentEvolver、Skill-SD | 明确已有，需证明动态 transfer 重测的增量 |
| M8 独立闭环审计和预算控制 | 标准实验方法 | 必须做，不能包装成算法贡献 |

### 5.2 不能漏掉的额外近邻

[LESS](https://arxiv.org/abs/2402.04333) 是最危险的近邻之一：目标能力示例、LoRA 梯度、optimizer-aware influence 和小数据选择都已经存在。必须加入“对 AppWorld step 直接应用 LESS”的强对照；还要加入动态 LESS-style 重评分，才能检查能力分组/执行验证是否有独立价值。

[Agent-FLAN](https://arxiv.org/abs/2403.12881) 已研究 agent 数据中的不同能力学习速度、数据解耦和负样本。它使“不同能力需要不同训练”这一宽泛表述无法成为主贡献。

[ASSAY / Not All Skills Help](https://arxiv.org/html/2606.15390v1) 测自然语言技能在推理上下文中的因果作用与任务异质性，无权重更新。CFST 若讨论“训练 step 的效用”，干预对象应是**参数更新的数据**，不能把 inference-time skill masking 与 training-time data attribution 混为一谈。

[DRACO](https://arxiv.org/html/2609.04094v1) 随 policy 能力动态生成 rubrics，并将轨迹评价分到相关步骤，在无 ground-truth outcome 的设置中训练。它进一步限制了“动态能力感知 + step advantage”的泛泛新颖性。

原聊天还提到了 LOOP、WebRL、CuES、ESAT、SGCD、SAGE、ReMe、G2PO 以及 agentic-data 综述。它们不是本表八篇的替代项；本次重点核查八篇及上述四个近邻，不能据此声称相关文献已穷尽。未核实唯一书目信息的简称不用于排除创新性。后续若加入合成任务、技能库、蒸馏或新奖励，就需要扩大对应文献核查。

### 5.3 怎样的贡献才可能站得住

较弱的说法是：“首次结合能力标签、关键步骤和self-improvement。”这只是组合描述，且多个组件已明确出现。

更可检验的研究主张是：**在交互型 agent 中，任务执行贡献与参数学习贡献存在可测量的分离；基于跨 family 行为探针校准的、随 learner 更新的 step 训练效用，可以在固定预算下提高迁移和能力保留。**

该主张至少需要三组证据：

1. **排序分离**：任务 criticality 高的步骤不总是训练增益高；控制长度、API、family 和当前难度后仍有差异。
2. **能力迁移与特异性**：学习某能力步骤改善其他 family 的相关决策，且超过随机/高loss/ATLAS/LESS-style 选择；同时检查对其他能力的干扰。
3. **动态增益**：模型更新后排序变化确实有用；动态版优于静态版以及等成本的随机重采样/动态LESS，并非仅因为额外 rollouts 或更长训练。

若只有分数小幅上涨而无法建立这些证据，结论应降为“有效的选样工程方案”。若上述简单基线已经一样好，就应删掉无增益模块，而不是加更多概念。

## 6. 先做哪些实验，怎样避免把对照做歪

### 6.1 三层数据分工

在 **原始 base 重新开始** 的机制实验中，可先将30个 family 分成18/6/6个，对应54/18/18个任务，分别用作候选训练池、选择用 probe、独立审计集。这是建议，尚未生成划分；需兼顾能力覆盖，family 内三个变体必须同组。若能力分布稀疏，改为预注册的 grouped cross-validation，并报告每类覆盖量。

选择用 probe 的答案、梯度或正确率影响了数据选择，所以它已经是训练/选择信息，不能再当成最终未接触的测试集。所有方法得到相同的 probe 访问权限，报告查询预算。独立审计集用于核验 proxy 和小规模选择；若据其反馈调方法，它也成为开发信息，最终结论需要另外锁定的评测集。

已有 LoRA90/FFT90 见过全部30个 family；可以用来诊断当前模型能力缺口，但不能支持“train90 内留出的 family 从未见过”的主张。正式全90训练时，另以预定义的训练内交叉拟合/保留 probe 策略评分；从未见过的最终迁移结论放到独立 Dev/Test。

此前 test_normal 已被多次评测和案例分析，本文只复述历史发现，不把测试轨迹转成训练修复数据、能力模板或选择 probes。后续研究使用内部开发划分固定设计，并透明报告已有测试暴露；有条件时再用未用于开发的隐藏评测验证。

### 6.2 首个最小实验矩阵

所有选择方法先用相同 LoRA 配置与初始模型，不把 FFT 引入第一轮选择机制实验。

| 组别 | 目的 |
|---|---|
| A 全步骤 SFT | 现有方法基准；新实验需同协议复跑对应数据划分 |
| B 只排除明确坏目标 | 区分质量清洗与复杂选样的收益 |
| C 匹配预算的随机步骤 | 检查是否仅靠减少监督就有效 |
| D ATLAS-style 关键步骤 | 与重要性选择比较；AppWorld 适配需注明 |
| E 高NLL / 高执行缺口 | 检查是否简单难例挖掘足够 |
| F 能力均衡 | 检查收益是否仅来自类比例变化 |
| G 静态LESS-style + 动态LESS-style | 检查能力标签、frontier 与执行验证的增量 |
| H 静态CFST / 动态CFST | 在相同输入池、采集量与预算下比较重评分价值 |

初期可以按 A/B/C/D/E 顺序推进，再加 F/G/H，避免一开始运行大量复杂组合。首轮有正信号后，消融能力标签、transfer、动态重评分、干扰控制。如坏目标清洗已足够解释收益，不能归功于 capability frontier。

CSO/SALT/ProCredit/CANOPY/AgentEvolver/Skill-SD/ProST 属于更完整的训练或系统方法。机制初验无需立刻复现全部，但论文宣称优于它们时必须同底座、相同数据访问和资源约束做适配实验，不能拿原论文排行榜代替。

### 6.3 30% 预算怎么定义

当前完整数据每遍是94,553个监督tokens，30%约28,366。它不是351个步骤，更不是27条轨迹。完整step不宜为凑整数token任意截半，可选最接近预算的集合并报告误差。

“同epoch、同batch、同步数、同目标tokens、又只用30%不同长度样本”不能不加设计地同时成立。建议拆成两种有明确目的的实验：

- **固定数据遍数**：比较100%与30%子集各训练相同遍数；记录真实token量和更新数，回答数据效率问题，不称算力完全等同。
- **固定优化预算**：所有方法在相同初始模型上，用相同总目标token预算B、相同更新次数S，每次按约B/S的目标token量累积样本后更新；固定按更新索引的LR路径和loss归约。全数据组在全部候选中采样，选择组在子集中采样；两者重复率不同，必须报告。离散样本的预算偏差预先限定。

固定目标tokens仍不等于固定计算量，因为prompt长度和分支采集不同。再报告输入tokens、总前后向tokens/GPU时间、教师调用、rollout tokens、环境步数、验证器成本。所谓“更省计算”需要这些总账支持，不能只报选中了30%步骤。

动态版必须有“同等新增轨迹，但随机/静态选择”的对照。否则改进可能只是额外数据。小样本探针重复使用也可能过拟合，需要检查其收益是否在独立审计集成立。

### 6.4 如何验证“学会某种能力”

保留三个层面的证据：

1. 教师状态上的离线NLL：便宜，但只说明目标拟合。
2. 其他family真实状态上的局部执行：验证集合逻辑、参数绑定、恢复、终止等行为；不是端到端完成率。
3. 从任务初态开始的完整rollout：官方TGC/SGC；验证局部改善是否能在模型实际访问的状态分布中发挥作用。

同时记录被选步骤的能力分布、初始p分布、长度、文档/业务动作比例及family覆盖，避免“能力法”只是选了更长代码或更少文档。对 matched subsets 做短程 LoRA 分支更新，可以得到“训练能力c后，能力d变化多少”的迁移矩阵；其因果解释仍限定在这些数据组、更新配方和评估分布。

训练seed至少做多个重复；任务统计按scenario/family分组，不把同一family的三个变体当独立随机试验。置信区间应区分任务组成不确定性和训练随机性。

## 7. 当前可以下的结论与交付边界

可以下的结论：现有数据适合做选择式监督的机制研究，管线已具备step训练单位；成功轨迹含错误动作与多类决策；ATLAS/CSO/LESS等已覆盖多数基础组件。真正值得优先尝试的是**能否测到跨任务学习效用，并证明它比重要性或难度更会选样**。

还不能下的结论：八类能力已经被可靠分离、某一步已经具有高迁移价值、动态frontier一定优于全步骤SFT、FFT差距由无效步骤造成、CFST已具备足够论文新颖性。

本次新增三个轻量文件：本说明、data_audit.json、annotation_examples.json。执行的是现有JSON/日志/论文的读取与静态统计；没有生成伪造模型分数，没有启动GPU训练或新的AppWorld rollout，也没有修改训练数据、脚本、checkpoint和历史实验。下一步最小可检验工作是：审查少量跨family候选与局部验证器，先测高/低预测迁移组的实际短程更新效果，再决定是否扩为完整动态算法。

