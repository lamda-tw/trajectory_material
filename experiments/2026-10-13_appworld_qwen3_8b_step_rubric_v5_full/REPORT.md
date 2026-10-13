# 原始 Qwen3-8B / AppWorld 540 条轨迹：冻结 prompt_v5 全量评分报告

本次实验已完成 **540/540 条完整轨迹、11,254 个 step、90,032 个 rubric 分项**的全新评分。冻结 v5 全程未修改；所有成功和失败轨迹均使用同一 prompt、同一输出结构。纯评分墙钟时间为 **6,771.025 秒，即 1 小时 52 分 51 秒**，不包含评分后的官方结果对照、语义复核或报告撰写。

**结论：v5 可以继续作为离线诊断与候选 step 筛选的固定基线，现在应进入受控的学习实验。** 本次没有理由推倒重做，也没有证据支持把八维标签直接视为精确 reward 或训练真值。最需要控制的是结束判断、局部取证的适用范围、确定错误与证据不足的混淆，以及若干可用程序直接识别的协议漏判。无需为追求完美 prompt 再全量重跑。

**1．数据、冻结对象与运行方式**

数据来自 `/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts`，是原始 Qwen3-8B base 的采样结果，**不是 LoRA SFT 后的另一组轨迹**。共 90 题，每题 6 条，按 task ID 前缀分为 30 个任务家族。官方成功 39 条、失败 501 条，轨迹成功率 7.22%；只有 20 题至少有一条成功轨迹。成功轨迹合计 501 步，失败轨迹合计 10,753 步。

终止类型：completion_api 312 条、no_python_code 111 条、step_limit 97 条、context_limit 20 条。后两种预算终止不自动使最后一个正常动作变成错误；调用 complete_task 也不自动意味着业务成功。

冻结 prompt SHA256：`bc6335bf245b1c0991970662bad230cd30d6ae04c0e7e8fb8af0e1d57c70de4b`。正文 2,111 字符，保留 R1—R8 的 P/F/U/N 和每步一句短依据，不合成总分、不分 audit/batch 模式、不赋固定权重。未来修改必须另建版本。

一条完整轨迹对应一次评分请求，而非每个 step 单独重复发送全历史。输入沿用 prepare_input_v3：实际 code、其余生成文本 commentary、执行 observation、任务与运行协议、初始参考文档。模型是 **gpt-5.6-sol，reasoning_effort=high**；Codex CLI 0.162.0，独立临时会话、空工作目录、只读沙箱、禁用工具与网页访问。模型按 prompt 直接阅读输入并输出 JSON，不能查询工作区或官方答案。实际并发从 2 升至 4，再升至 8；00:33:51 后保持 8。

全部 540 条重新调用，没有复用 pilot 的评分。最长单条准备输入为 527,852 字符，仍完整提交并获得有效结果，没有为通过接口而截断轨迹。这里的“完整”指统一适配器保留的全部步骤与观察，不包含用于采样训练的 token IDs/logprobs 等非 judge 字段。

**2．账号、时间与 token 成本**

本次批量评分调用使用**服务器上 Codex CLI 已登录的 ChatGPT 账号**，脱敏标识为 `qz***@gmail.com`，账号指纹 `62515d09c7e4`；本地认证记录的计划标识为 pro，未使用 API key。调用读取服务器 `/root/.codex/auth.json` 的登录状态。电脑端账号身份无法从这里核对；若电脑端恰好登录同一账号，则可能共享相应账号额度，不能仅按“服务器/电脑”判断为两份独立额度。[官方认证说明](https://learn.chatgpt.com/docs/auth)。本实验没有读取到可靠的实际扣费金额或剩余额度，因此不套用 API 单价估算账单。

以下时间均为 **Asia/Shanghai（UTC+8）**：

| 项目 | 记录 |
| --- | --- |
| 实验准备时间 | 2026-10-13 00:15:53.998 |
| 纯评分开始 | 2026-10-13 00:20:33.110 |
| 540 条全部校验并落盘 | 2026-10-13 02:13:24.135 |
| **纯评分墙钟用时** | **6,771.025 秒 / 1 小时 52 分 51 秒** |
| 独立评估开始 | 2026-10-13 02:13:37.755 |
| 所有评分子进程耗时之和 | 49,510.256 秒，约 13 小时 45 分 10 秒 |
| 首次有效调用的平均 / 中位耗时 | 91.48 秒 / 84.22 秒 |

墙钟计时从第一次评分子进程启动前开始，到全部 540 条通过结构与步骤覆盖校验并保存后结束。包括 CLI 启动、推理、校验、落盘和失败重试；排除前期准备与后续评价。子进程耗时之和含并发重叠，**既不是用户实际等待时间，也不是实测串行运行基线**。评估及报告阶段单独记录在 [EVALUATION_TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/EVALUATION_TIMING.json)，不回填或延长评分计时。

共 542 次评分调用，其中 540 次有效、2 次格式失败；失败项各用**完全相同请求**重试一次后成功：`287e338_3__03` 的 JSON 缺分隔符，`07b42fd_3__02` 的八字符标签中多了空格。没有更换 prompt 或模型，没有耗尽重试的轨迹，没有服务、认证、限流或上下文容量故障。首次结构通过率 538/540 = 99.63%。

| CLI 报告的 token 项 | 全部 542 次调用合计 |
| --- | ---: |
| Input tokens | 11,754,719 |
| 其中 cached input | 3,892,352 |
| Output tokens | 2,555,901 |
| 其中 reasoning output | 2,295,362 |
| Input + output | 14,310,620 |

cached input 是 input 子集，reasoning output 是 output 子集，不能再次相加。两次无效调用已包含在总数内，合计 input 31,486、output 4,501。以上是评分 CLI 的用量，**不含当前电脑端对话、我的后续证据复核和报告写作 token**。记录来源见 [AUTH_PROVENANCE.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/AUTH_PROVENANCE.json)、[TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/TIMING.json)、[逐次调用统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/attempts.json)。

**3．全量输出揭示了什么**

P=证据支持满足，F=明确违反，U=必要证据不足，N=不适用。每一行分母均为 11,254 步。

| Rubric | P | F | U | N |
| --- | ---: | ---: | ---: | ---: |
| R1 执行契约 | 6,069 | 5,185 | 0 | 0 |
| R2 证据与覆盖 | 3,906 | 2,171 | 687 | 4,490 |
| R3 状态与数据保真 | 3,886 | 3,626 | 697 | 3,045 |
| R4 决策与计算 | 320 | 2,633 | 326 | 7,975 |
| R5 操作与实际效果 | 92 | 501 | 201 | 10,460 |
| R6 反馈与恢复 | 2,977 | 5,464 | 0 | 2,813 |
| R7 结束与交付 | 39 | 460 | 60 | 10,695 |
| R8 授权与交互协议 | 3,567 | 7,330 | 0 | 357 |

![成功和失败轨迹的各维标签分布](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/figures/rubric_distribution.png)

图中分别按成功组 501 步、失败组 10,753 步归一化；它描述相关性，不证明某类标签造成任务失败。

9,596 步至少有一个 F，其中 **1,384 步仅 R8 为 F**；所有八维均无 F/U 的只有 1,592 步。如果把“任意 F”直接作为丢弃条件，许多业务正确但未先查 API 规格的步骤也会被丢弃。R8 很常见，不能让它的数量淹没业务学习信号。多个维度还可能描述同一错误链，简单求和会重复惩罚。

39 条官方成功轨迹中仍有 121 个 R1=F、60 个 R4=F、247 个 R8=F；失败轨迹中仍有 5,689 个 R1=P、2,774 个 R6=P。这与“先出错再恢复”“整体失败但局部有效”相符，支持同时使用成功、失败轨迹做局部分析。这里的标签本身有噪声，因此不能把这些计数全解释为已确认的真实错误或正确行为。

进一步只比较同一道题内部的成功与失败采样：先计算每条轨迹在适用项 P/F/U 中的 F 比例，再分别平均成功、失败组。20 道可比较题中，成功组的 R2 错误比例更低有 16 题，R3 有 15 题，R4 有 17 题，R6 有 16 题；R8 只有 11 题。这支持业务与恢复维度具有筛选价值，但样本少、题目选择有偏，不能据此拟合出可靠的固定权重。见 [同题比较](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/within_task_comparison.json)。

**4．质量检查：哪些已确认，哪些还不能确认**

完整性检查全部通过：540 条源文件哈希、输入哈希、冻结 prompt 与请求一致性、step 顺序和覆盖、JSON 结构、原始有效响应与保存结果一致性、官方成败未进入 judge 输入。官方结果是在评分后加入研究分析表的；这些附加字段不是 prompt 的一部分。详见 [完整性检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/validation.json)。

机械核对使用可见执行反馈和保守 AST/代码块检查，不依赖另一轮模型打分：

| 可核对事件 | 对应判定符合数 | 解释 |
| --- | ---: | --- |
| 明确执行失败或无代码导致终止 → R1=F | 5,184 / 5,184 | 执行契约基本可靠 |
| 有代码且观察非执行失败 → R1=P | 6,069 / 6,070 | 唯一反例已人工式证据复核确认 |
| 保守识别的纯读取/计算代码 → R5=N | 8,826 / 8,826 | 能较好区分计划文本与实际修改 |
| 实际代码之外还有非空 Python 块 → R8=F | 961 / 1,209 | **248 次漏判：196 个 P、52 个 N** |

不能把大量容易判 N 的条目汇总为“整体准确率接近 100%”。这些只验证明确可机械核对的局部规则；尤其多代码块漏判说明，规则可以直接计算时不必全靠 judge 注意到它。完整记录见 [mechanical_checks.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/mechanical_checks.json)。

评分开始前冻结了另一组 12 条完整轨迹，覆盖此前 v4/v5 开发未使用的 12 个任务家族，含 3 成功、9 失败，共 176 步、1,408 分项。我在评分完成后逐步阅读完整输入和 judge 输出，记录明确错误与可争议边界。**这是主助手证据复核，能看到原评分，不是独立人工金标，也不是按全量出现频率随机抽样。**

1,408 项中有 617 个 N。为了避免大量“不适用”稀释问题，以 791 个非 N 项，加复核认为需要讨论适用性的 6 个 N 项，得到分析分母 797。发现 **27 项明确错误、21 项存在合理争议**：

- 未发现明确错误的比例为 770/797 = **96.61%**。
- 把争议项也排除后为 749/797 = **93.98%**。
- 176 步中，**25 步至少含一项明确错误**；40 步至少有一项明确错误或争议。
- 另有 2 处短理由表述问题；它们独立记录，没有额外叠加为分项错误。

这说明“大多数局部判断可用”，但**不能宣布 540 条上的真实准确率超过 95%**，也不能把分项层面的 96.61% 理解为每步八维同时正确的比例。27 个明确错误中含 11 次已有 F 的误判、9 次应判 F 的漏判，其余为适用性或 P/U 等问题。

| 维度 | 明确错误项 | 争议项 |
| --- | ---: | ---: |
| R1 | 0 | 0 |
| R2 | 4 | 5 |
| R3 | 6 | 2 |
| R4 | 1 | 2 |
| R5 | 2 | 7 |
| R6 | 3 | 2 |
| R7 | 4 | 0 |
| R8 | 7 | 3 |

全部 176 步覆盖记录和逐项依据见 [MANUAL_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/MANUAL_REVIEW.md)、[机器可读复核](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/manual_review.json)。后续针对官方不一致结果定向检查的 10 条记录单独放在 [补充复核](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/SUPPLEMENTAL_REVIEW.md)，**没有混入上述分母**。

最后，用本次新输出与 pilot 相同 12 条、201 步做一致性比较：1,608 项中 1,475 项相同，**91.73% 一致**；133 项不同，其中 51 项发生 F 与非 F 切换。R3 变化 49 项、R2 28 项、R6 20 项，是主要波动来源。原有开发检查本次符合 85/91（pilot 为 86/91）。这些是重复性和开发回归，不是独立准确率；说明固定 prompt 也不会消除模型波动，不应对一次标签的小差异赋予过大训练意义。

**5．官方成败对照：R7 不是最终成功的替代品**

将每条轨迹最后一步的 R7 与官方结果交叉统计：

| 最后一步 R7 | 官方成功 | 官方失败 |
| --- | ---: | ---: |
| P | 26 | 13 |
| F | 8 | 321 |
| U | 5 | 55 |
| N | 0 | 112 |

只看 P/F 的 368 条，表面一致率为 347/368 = 94.29%，另有 172 条 U/N 未作二分类。但全数据中失败本来就占 92.78%，两个比例又不是同一覆盖集合，所以这个数字不能证明高准确率，更不能作为 step 评分质量。

尤其要保留提交状态：13 条“官方失败但 R7=P”中，**4 条实际使用 status="fail"**。v5 明确允许诚实报告失败，P 在这里描述结束行为，并不表示业务完成。其余 9 条是默认成功提交。只在默认成功提交且 R7=P 的 35 条里，官方成功为 26 条，即 **74.29%**。这仍不足以把 R7=P 直接作为成功奖励。分类代码只静态分析实际末步代码，详见 [结束状态分析](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/terminal_submission_analysis.json)。

官方成功而 R7=F 的 8 条，也不能机械地将 F 全部改 P：官方可能接受了正确答案，但 judge 评的是轨迹可见证据与交付行为。反过来，官方失败也不证明每个中间 step 错误。本次源文件的官方评测只有 success 和测试通过/失败计数，没有逐项失败断言；报告不虚构具体失败原因，也未重新执行环境。

**6．具体轨迹中的有效判断与剩余问题**

| 例子 | 可见证据与 v5 表现 | 对后续使用的含义 |
| --- | --- | --- |
| `ccb4494_1__02` step 8 | 队列观察显示当前位置为 5，却对全部 10 首歌点赞；后续尚未播放的歌曲也被修改。业务规则与实际效果 F 有依据。 | 当状态充分可见时，可以定位具体业务错误，而不只是看 Python 是否执行成功。 |
| `3c13f5a_2__04` step 48 | 任务要求分摊账单并请求付款，实际却向三人各发送整笔 182。接口参数修复了，但金额、方向和对象依据仍错。 | “修复执行错误”与“业务正确”必须分开。不能只凭 R6=P 挑正向 SFT 目标。 |
| `229360a_3__02` | commentary 中有删除方案，但实际执行代码只读取/计算；结束却声称已经清理。 | R5=N 和结束虚假完成可以同时成立；未执行计划不能当真实修改。 |
| `e85d92a_1__00` step 10 | 局部可见样本支持候选，但全局覆盖不足；judge 在前面记 U，结束却给 F。 | 更合适的是 R7=U，除非出现真实反例；“尚未证明正确”不能自动变成“已证明错误”。 |
| `ccb4494_1__03` 等 4 条 | 未打印的队列确实保存在变量里，但日志看不到当前位置；循环全队列，写入 R5=U，结束 R7=P。 | 未解决的必要状态不确定性也不能自动升级成 P。下一轮采样应保留关键 API 返回和状态。 |
| `6ea6792_3__00` step 6—7 | 26 条 pending 请求确已批准，但没有查联系人关系来证明都是朋友/同事；R5=U 后结束 R7=P。 | 执行成功只能证明发生了批准，不能证明对象集合符合任务。 |
| `229360a_3__02` steps 4/7/8 | 有效的首次局部读取被记 R2=U，原因混入尚未作出的全局完成要求。 | 中间取证应按本步子目标评价，别提前承担最终完整性。 |
| `6ea6792_1__03` step 8；`e3d6c94_3__05` step 8 | 认证/参数校验在业务修改前失败，R5 被给 F。 | 没有实际业务效果的明确前置失败宜为 N；不能让 R1 错误重复污染 R5。部分执行后的失败则另论。 |
| `ce359b5_1__00` steps 8/10/12/14/16 | 一个 step 生成额外非空 Python 代码块，R8 却为 P。 | 使用程序记录协议标志更稳定；原始 v5 标签保留。 |
| `34d9492_1__01` step 17 | 修正移动参数后 13 次 move_file 正常返回，R1 却为 F。 | 执行维度偶尔被业务错误污染；这是全量机械检查发现的单个反例。 |

笔记任务还有另一种边界：`cf6abd2_1__00`、`cf6abd2_1__05`、`cf6abd2_2__00` 的目标 checkbox 修改有可见依据，但操作类任务结束时给了不应有的非空 answer。judge 给 R8=F、R7=P，官方失败。R7 的“规定交付”与 R8 协议边界尚不完全稳定；源文件无失败断言，不能断言该 answer 是官方失败的唯一原因，更不能据官方失败否认前面正确的局部修改。

这些例子表明 AppWorld 的难点不只是自然语言：**同一步同时有决策、代码、返回状态和部分副作用，且日志可见性不完整**。原始 step 字段没有独立的逐 API 调用返回或数据库差分；仅赋值而不打印的返回，在 judge 输入中往往只留下“Execution successful.”。未打印不等于变量不存在，但缺失的关键值确实限制语义判定。扩大 prompt 无法凭空恢复这些值。

**7．对 prompt 的判断，以及必要时应如何改进**

v5 的结构是合理的：固定八维、成功失败同标准、实际代码与未执行文本分开、保留 U/N、要求短依据。这些选择让一次全轨迹评分可完成，避免把 11,254 步拆成同样多的外部请求。实测完成率和样本证据支持继续使用它。

局部缺陷也明确存在。**本轮保持 v5 与所有原始评分不变；下列是后续有需要时的修改方向，不是已上线的 v6。** 若再改版本，直接整合到唯一 Evaluation Rubrics 模块，以短句替换现有边界，避免追加长补丁：

- R2：只核对已经采用的当前子目标；未来尚未作出的“全部/最大”结论不前置到正常局部读取。
- R5：将“业务调用在修改前明确被拒绝”与“实际发生错误修改”分开；运行异常后的部分副作用仍需结合反馈。
- R6：成功修复旧的执行问题可以通过，但这不覆盖 R3—R5 的业务错误。
- R7：对任务必要条件未解除的 U 保持 U；正确的失败报告与成功交付在消费数据时保留提交状态；明确交付格式由 R7 检查，API 文档/代码块约束由 R8 检查。
- R8：对多代码块等可确定事件增加独立程序检查；这比单纯加重措辞更可控。

R1/R8 的程序结果宜作为独立的 `mechanical_flags` 使用，附检测器版本和证据，不静默覆盖本次原始标签，也不与语言模型输出混成未经标识的新真值。当前已保存逐条 mechanical_checks，可直接追溯；未另外花模型 token 全量重评。

**8．下一步如何从“打分”走向“找到值得学习的 step”**

现在已有可落地的候选集：

| 候选规则 | 记录数 | 用途与限制 |
| --- | ---: | --- |
| R3/R4/R5 任一为 F | 4,733 | 事实或业务错误候选，适合定位待修复问题；原错误动作不能直接作为正向 SFT 目标 |
| 当前 R1=P、R6=P，且前 3 步内存在 R1=F | 1,884 | 执行恢复候选；只是邻近启发式，不保证严格因果对应 |
| 两类合并去重 | 6,381 个不同 step | 两类重叠 236 步 |

1,884 个恢复候选中 **236 个仍有 R3/R4/R5 的 F**，且 **1,742 个来自最终失败轨迹**。这既支持保留失败轨迹，也直接说明“恢复成功”不是完整的正确行动标签。候选导出在 [step_candidates.jsonl](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/step_candidates.jsonl)，`training_weight` 全部为 null，没有预设权重；官方成败字段显式标注仅供分析。

建议下一个实验只回答一个问题：**在相同训练 token 预算下，rubric 定位的局部训练数据能否比均匀抽样更有效？** 优先做规模可控的局部 SFT 对照，较容易分辨数据筛选是否有效，再考虑 reward 合成或整体 RL。这是下一步建议，本次没有启动训练或额外批量修复。

可按以下顺序准备：

1. **定位问题与确认目标分开。** F 标记待诊断位置，U 保留未知。需要正向训练时，从同状态下经过核验的成功动作、已有正确轨迹的可对齐状态，或修正后回放通过的动作取得目标。不同轨迹的第 k 步不能直接互换；变量、对象集合和已发生副作用可能不同。
2. **训练样本保留必要前缀。** 使用行动前可用历史作为输入、正确 action 作为监督；执行观察可用于验证目标，但不能泄漏进同一个动作的行动前输入。判断单位可用 `(history_before, action, observation_after)`，训练输入则是其中的行动前部分。
3. **先比较简单选择策略。** 相同可训练目标池、相同 token 预算下，对比均匀选 step 与 rubric 定位后选 step；另报告整条成功轨迹 SFT 基线。若一组使用新修复目标，另一组也必须有等价可用目标，否则无法区分筛选收益与教师数据收益。
4. **把当前模型能力放到选择阶段。** 在核验后的正确目标上计算当前 checkpoint 的条件 NLL/难度，区分已掌握和仍难的行为；以后随模型更新重算。无需在这次离线标注中固化权重，更不能用高 NLL 自动证明某个未核验动作值得学。
5. **以环境结果检验价值。** 使用事先固定的验证/测试题；至少按题划分，测试跨任务泛化时进一步按任务家族划分，避免同题 6 条轨迹跨训练与验证。比较官方成功率、运行成本及恢复能力，不只比较被训练过的 rubric 分数。当前这 90 题全是训练集，不能用它们单独证明泛化提升。

未来采样优先改善日志可观测性：保留关键 API 调用参数/返回、分页终止证据、队列当前位置、联系人关系、修改前后对象状态；先对高价值字段做精简记录，避免为所有 API 无差别倾倒数据。对候选修复轨迹再做环境回放验证，通常比反复让 judge 猜缺失状态更有价值。

若目标是论文级“超过 95% 的评分准确率”声明，仍需另建独立人工标注/裁决集，按任务和错误类型报告分项与整步一致率；本次主助手复核不能替代它。但这不应阻止当前用冻结 v5 开始有对照的学习实验。

**9．产物与复现**

| 文件 | 内容 |
| --- | --- |
| [assets/prompt_v5.txt](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/assets/prompt_v5.txt) | 本次实际使用的冻结 prompt |
| [run_manifest.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/run_manifest.json) | 冻结文件哈希、运行器配置及抽样计划哈希 |
| [scored_trajectories.jsonl](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/scored_trajectories.jsonl) | 540 条评分 JSON 汇总 |
| [step_labels.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/step_labels.csv) | 11,254 行逐 step 八维标签和短理由 |
| [trajectory_metrics.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/trajectory_metrics.csv) | 540 行轨迹统计及评分后加入的官方结果 |
| [summary.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/summary.json) | 全量标签、时间和 token 汇总 |
| [report_metrics.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/report_metrics.json) | 同题趋势、候选交集、重试成本等补充统计 |
| [MANUAL_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/MANUAL_REVIEW.md) | 预先选定的 12 条完整轨迹复核 |
| [SUPPLEMENTAL_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/SUPPLEMENTAL_REVIEW.md) | 评分后按异常定向诊断，独立于抽样质量率 |
| [TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/TIMING.json) / [EVALUATION_TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/EVALUATION_TIMING.json) | 评分与后续评估分别计时 |

每条 `runs/scoring/<id>/` 中保留真实 request、input、judge 输出、metadata 和所有 attempt 的原始事件/响应；失败尝试也保留。分析脚本均不调用模型、不执行轨迹代码、不改原始评分。重新生成统计可依次运行 `analyze_full.py`、`analyze_terminal_status.py`、`summarize_semantic_review.py`、`report_metrics.py` 和 `render_report_assets.py`；正式评分无需重跑。最终文件哈希和完成检查见 `COMPLETION_CHECK.json`。

可以向主管汇报：**已经用固定 v5 在约 1 小时 53 分钟内完成 540 条轨迹的逐步评价，获得可追溯的八维标签和候选步骤。多数局部判断有用，主要噪声来自证据不完整与维度边界；下一阶段的核心验证应是“筛选后的正确局部训练数据是否提升模型”，而不是继续追求零误差 prompt。当前尚未证明学习收益，也未证明总体标注准确率超过 95%。**
