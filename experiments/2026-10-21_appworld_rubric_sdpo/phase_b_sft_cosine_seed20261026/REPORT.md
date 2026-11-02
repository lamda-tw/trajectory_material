# 同 seed 纯 ZeroFail3 SFT：余弦衰减与恒定学习率三轮正式对照

人工复核更新：2026-10-28T11:09:44+08:00。本报告所有时间均为北京时间。

## 1. 完成状态与主要结论

余弦实验已于 **2026-10-28 09:44:17** 正常完成：**54/54 批、54 次优化器更新、3/3 次 dev57 评估**。本次仅分析已有文件，没有启动训练、模型推理、环境重评估或新的 Codex 评分。

**本次余弦方案明显好于同 seed 恒定学习率，并且在三轮内避免了原先第三轮的大面积无代码终止；但重复查询文档仍随轮次增加，第三轮已出现局部能力回退。按完整任务成功数和 Macro 选择，当前应使用第二轮，而不是第三轮。**

- 完整任务成功：恒定 **6→8→1 /57**；余弦 **13→15→14 /57**。
- 第三轮无代码终止：**50/57→0/57**；有业务 API 代码的任务：**10/57→51/57**。
- 余弦内部重复文档占比：**9.75%→22.95%→26.95%**，未得到根治。
- 第二轮到第三轮，余弦新增成功 4 题、丢失成功 5 题；通过检查从 **156 降至 145**，不是只有一题发生变化。
- 这是单次同 seed 的在线训练对照。第一次更新前，两次采样已不完全相同；因此不能把全部差异视为余弦曲线的确定因果收益，也不能证明余弦形状优于较低的恒定学习率。

## 2. 实验是否按原计划执行

对照为 `phase_b_sft_seed20261026`，本次为 `phase_b_sft_cosine_seed20261026`。两者训练 seed 都为 **20261026**，从原始 **Qwen3-8B** 分别初始化新 LoRA 与 AdamW，不续接旧模型。仍是 **LoRA SFT**：r=8、alpha=16、dropout=0，七类线性层；基础模型冻结。

每轮训练 90 题，每批 5 题，每题在线采一条完整轨迹，18 批/轮。完整轨迹由同一 v7 rubric 流程打分，仅 **FAIL=0 且 PASS≥3** 的步骤用于 SFT；SDPO 权重为零。任务顺序与派生 rollout seed 相同，采样 temperature=1。每轮 dev57 都是无反馈学生模型，temperature=0、seed=100，50 步上限、32000 上下文与相同输出限制，使用官方终态检查。

唯一主动改变的训练超参数是学习率日程；模型保留、进度报告属于管理性改动。实际训练数据在线重采，因此不能把它理解为固定数据上仅改学习率的逐样本配对试验。

前 5 次有效更新均为 `1e-5, 2e-5, 3e-5, 4e-5, 5e-5`。之后恒定分支保持 `5e-5`；余弦分支按有效更新次数平滑下降，无 warm restart：

`lr(u) = 5e-6 + (5e-5 - 5e-6) × [1 + cos(π × (u-5)/49)] / 2`，`u=6,…,54`。


| 更新位置 | 恒定学习率 | 余弦学习率 |
| --- | --- | --- |
| 首次更新 | 1.0e-5 | 1.0e-5 |
| 第5次，warmup结束 | 5.0e-5 | 5.0e-5 |
| 第18次，第1轮末 | 5.0e-5 | 4.262677e-5 |
| 第36次，第2轮末 | 5.0e-5 | 1.839237e-5 |
| 第54次，第3轮末 | 5.0e-5 | 5.0e-6 |

核对了两个分支共 **108 个已提交 batch** 的完成标记、checkpoint 父链、优化器更新次数、配置身份、逐批学习率及验收记录；保留的模型文件和已清理 checkpoint 的保留凭据也通过检查。全部 SFT loss、梯度和参数变化指标有限，未触发梯度裁剪；SDPO loss/梯度始终为 0。没有发现错误重启 warmup、优化器更新计数回退或评估错用模型的证据。

另外核对了 **342 条 dev 轨迹与 342 份官方报告** 的哈希、任务清单、检查项、行为统计及所用 checkpoint，均与汇总一致。

## 3. 三轮 dev57 正式结果

完整成功要求任务全部官方检查通过。Macro 是先求每题检查通过比例、再对 57 题等权平均；“通过检查”是把 291 项直接相加，两者权重不同。部分检查也可能是约束检查，不应把通过项数解释成完成了同样数量的业务动作。

| 学习率 | 轮次 | 完整成功 | TGC | Macro | 通过检查 /291 |
| --- | --- | --- | --- | --- | --- |
| 恒定 | 1 | 6/57 | 10.53% | 42.34% | 106 |
| 恒定 | 2 | 8/57 | 14.04% | 40.49% | 103 |
| 恒定 | 3 | 1/57 | 1.75% | 26.73% | 55 |
| 余弦 | 1 | 13/57 | 22.81% | 57.24% | 158 |
| 余弦 | 2 | 15/57 | 26.32% | 58.06% | 156 |
| 余弦 | 3 | 14/57 | 24.56% | 54.41% | 145 |

相对同轮恒定学习率，余弦第 1、2、3 轮分别多成功 **7、7、13 题**。第二轮是余弦的最高完整成功率：**15/57=26.32%**。第一轮通过的检查总数最多（158），但完整成功数和 Macro 均低于第二轮，因此“最好”需明确选择指标。

### 同一道题、同一项检查的配对变化


| 轮次（余弦相对恒定） | 新增成功题 | 丢失成功题 | 净增成功题 | 新增通过检查 | 丢失通过检查 | 检查净增 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 9 | 2 | 7 | 69 | 17 | 52 |
| 2 | 8 | 1 | 7 | 69 | 16 | 53 |
| 3 | 13 | 0 | 13 | 90 | 0 | 90 |

第三轮恒定分支通过的 **55 项检查被余弦全部保留，并额外通过 90 项**；恒定唯一成功的题也被保留。这说明第三轮的改善不只是平均值被少数不同任务抬高。

### 余弦内部是否还在进步


| 轮次变化 | 新增成功 | 丢失成功 | 新增通过检查 | 丢失通过检查 | 检查净变 |
| --- | --- | --- | --- | --- | --- |
| 1→2 | 6 | 4 | 35 | 37 | -2 |
| 2→3 | 4 | 5 | 39 | 50 | -11 |

第 2→3 轮完整成功 **15→14**、Macro **58.06%→54.41%（-3.65 个百分点）**、通过检查 **156→145**。其中丢失成功的 5 题是 `6171bbc_2, b119b1f_3, df61dc5_1, fac291d_1, fac291d_2`；新增成功的 4 题是 `6c2c621_1, b119b1f_1, b119b1f_2, d4e9306_1`。

这属于不同题之间的能力更替和局部退化，尚未发生恒定分支那样的整体崩溃；第三轮也没有形成全面提升。

## 4. 三类行为问题是否改善

### 4.1 重复查询文档：第二轮改善明显，第三轮仍存在循环

“纯文档步骤”指该步直接出现的 API 调用全属于 `apis.api_docs`；“重复文档”指同轨迹内已出现过相同 Python AST 的纯文档代码，首次出现不算重复。它既能统计连续重复，也能统计交替查询；仅换空格不逃过统计，但改写代码或参数顺序可能不被识别。并非所有重复都必然错误，需要结合案例判断。以下占比均以**全部生成步骤**为分母，不是以文档步骤为分母。


| 学习率 | 轮次 | 总步骤 | 纯文档步骤（占比） | 重复文档步骤（占比） | 重复文档≥5步的题数 /57 |
| --- | --- | --- | --- | --- | --- |
| 恒定 | 1 | 1414 | 370（26.17%） | 242（17.11%） | 12 |
| 恒定 | 2 | 1773 | 1335（75.30%） | 947（53.41%） | 37 |
| 恒定 | 3 | 769 | 598（77.76%） | 213（27.70%） | 11 |
| 余弦 | 1 | 1251 | 346（27.66%） | 122（9.75%） | 7 |
| 余弦 | 2 | 1490 | 679（45.57%） | 342（22.95%） | 20 |
| 余弦 | 3 | 1603 | 811（50.59%） | 432（26.95%） | 20 |

“重复文档≥5步”是本报告为衡量覆盖面增加的描述性指标，不是官方成功指标，也不要求这些重复连续出现。

- 第二轮重复文档由恒定的 **947/1773=53.41%** 降到余弦的 **342/1490=22.95%**；有至少 5 个重复文档步骤的题由 **37 降至 20**。这部分改善明确。
- 第三轮重复占比为 **27.70% vs 26.95%**，接近；绝对重复数余弦反而更多（**432 vs 213**）。不能据此说余弦第三轮已经解决文档循环。恒定第三轮有 50 题过早无代码终止，很多题根本没有继续循环的机会，分母和执行长度都被截短。
- 余弦自身从第一轮到第三轮，纯文档占比 **27.66%→45.57%→50.59%**，重复占比 **9.75%→22.95%→26.95%**；平均执行长度 **21.95→26.14→28.12 步**。模型仍逐渐把更多步骤花在文档上。

### 4.2 无代码提前结束：第三轮问题在本次评估中消失

“无代码终止”对应执行器的 `no_python_code`：模型回答中没有可被执行器识别的 Python 代码，不等于正常完成任务。


| 学习率 | 轮次 | 无代码终止 | 主动调用完成接口 | 达到50步上限 | 达到上下文上限 |
| --- | --- | --- | --- | --- | --- |
| 恒定 | 1 | 8 | 23 | 16 | 10 |
| 恒定 | 2 | 3 | 17 | 16 | 21 |
| 恒定 | 3 | 50 | 2 | 3 | 2 |
| 余弦 | 1 | 3 | 38 | 9 | 7 |
| 余弦 | 2 | 1 | 35 | 11 | 10 |
| 余弦 | 3 | 0 | 36 | 11 | 10 |

恒定第三轮的 50 个无代码终止，末次输出都不是空字符串，均为正常 `stop` 而非 `length`，仅 **13–55 个 response tokens**。其中 2 个有代码围栏，但仍没有执行器认可的 Python。因此这批失败不能解释为全部撞到单次生成长度上限，也不能全部称为“空输出”；实际表现是模型停止提供可执行动作。

余弦第三轮 **0/57** 无代码终止，说明这一具体退化在本次 dev57 上被避免。它仍有 **11 题步数耗尽、10 题上下文耗尽**；另外 36 题主动调用完成接口，只有 14 题真正成功，余下 **22 题声称完成但未通过全部检查**。最终 43 个失败 = 21 个耗尽预算 + 22 个错误完成，失败方式已经发生变化，但任务能力仍远未充分。

### 4.3 业务执行：不只多写代码，正式终态也更好

业务步骤按代码中直接调用业务 API 计数，排除 `api_docs`、`supervisor` 与 `login/logout`。一个步骤可能包含多次调用，调用也可能失败或处于未执行到的代码分支；因此这是**业务动作尝试的结构性代理指标**，不是成功 API 调用次数。真实完成情况须结合上面的官方检查和后面的案例。


| 学习率 | 轮次 | 业务步骤 | 占全部步骤 | 出现业务 API 的任务 /57 |
| --- | --- | --- | --- | --- |
| 恒定 | 1 | 553 | 39.11% | 54 |
| 恒定 | 2 | 131 | 7.39% | 32 |
| 恒定 | 3 | 20 | 2.60% | 10 |
| 余弦 | 1 | 574 | 45.88% | 56 |
| 余弦 | 2 | 348 | 23.36% | 49 |
| 余弦 | 3 | 391 | 24.39% | 51 |

第三轮，余弦的业务步骤 **391 vs 20**，有业务动作的题 **51 vs 10**，完整成功 **14 vs 1**，通过检查 **145 vs 55**。这组互相印证的指标说明改善不仅是生成变长，而是更多任务进入了实际业务并获得正确终态。

但余弦相比自身第一轮，第三轮业务步骤仍由 **574 降至 391**、覆盖面由 **56 降至 51 题**。第二轮到第三轮业务步骤虽回升 **348→391**，检查却减少 **156→145**，也说明“动作更多”并不等于“执行更正确”。

## 5. 具体案例：改善与残留问题

案例按改善、单一文档循环、错误恢复循环选取，用于解释现象，不代表全部 57 题的随机样本；总体发生率以上表为准。

### 案例 A：d4e9306_2，能继续执行关注歌手，而不是取得账号信息后停止

恒定三轮检查为 **2/6→1/6→1/6**；余弦为 **6/6→6/6→6/6**。

恒定第三轮共 7 步：查询文档、取得账号信息后，第 7 步没有可执行代码，业务步骤为 **0**。余弦第三轮共 18 步：第 10、11 步读取收藏歌曲和专辑，第 16 步查询 `follow_artist` 文档，第 17 步发出 `apis.spotify.follow_artist` 业务调用，第 18 步完成；官方 **6/6** 通过。余弦并非完全不查文档，而是查完后仍能执行目标动作。


[恒定 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/runs/sft/epoch_03_dev57/trajectories/d4e9306_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/runs/sft/epoch_03_dev57/runtime/d4e9306_2/experiments/outputs/dev_d4e9306_2/tasks/d4e9306_2/evaluation/report.md)；[余弦 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/trajectories/d4e9306_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/runtime/d4e9306_2/experiments/outputs/dev_d4e9306_2/tasks/d4e9306_2/evaluation/report.md)

### 案例 B：6c2c621_1，笔记导出最后真正创建了文件

恒定三轮都只有 **1/8** 检查通过；第三轮 23 步后无代码终止。余弦为 **6/8→6/8→8/8**。余弦第三轮第 15、16 步查询/读取笔记，第 26 步 `create_directory`，第 27、28 步 `create_file`，29 步完成，最终 **8/8**。

它仍有 15 个文档步骤、4 个重复文档步骤；因此“仍查较多文档”与“能完成任务”可以同时存在。不能把所有文档查询一概视为坏动作。


[恒定 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/runs/sft/epoch_03_dev57/trajectories/6c2c621_1.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/runs/sft/epoch_03_dev57/runtime/6c2c621_1/experiments/outputs/dev_6c2c621_1/tasks/6c2c621_1/evaluation/report.md)；[余弦 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/trajectories/6c2c621_1.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/runtime/6c2c621_1/experiments/outputs/dev_6c2c621_1/tasks/6c2c621_1/evaluation/report.md)

### 案例 C：b119b1f_2，第三轮恢复推进播放流程，但跨轮不稳定

恒定检查 **6/6→0/6→0/6**：第二轮 23 步中 18 个重复文档步骤，第三轮 7 步后无代码终止。余弦检查 **6/6→0/6→6/6**：第二轮也陷入文档循环（14 步、11 个重复文档步骤），第三轮恢复到 21 步、仅 1 个重复文档步骤，出现 10 个业务步骤，反复调用 `next_song` 与 `show_current_song` 来推进播放任务，最终 **6/6**。

这解释了为什么不能只用“15→14”判断所有题都略微变差：确有题在第三轮恢复成功。


[余弦 E2轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/trajectories/b119b1f_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/runtime/b119b1f_2/experiments/outputs/dev_b119b1f_2/tasks/b119b1f_2/evaluation/report.md)；[余弦 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/trajectories/b119b1f_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/runtime/b119b1f_2/experiments/outputs/dev_b119b1f_2/tasks/b119b1f_2/evaluation/report.md)

### 案例 D：df61dc5_1，第二轮成功，第三轮反复查询同一份联系人文档

余弦第二轮 **7/7**：33 步，10 个业务步骤；查询联系人、查询 Venmo 交易，最后执行 `like_transaction`。

第三轮退到 **2/7**：50 步中 **46 个纯文档步骤、36 个重复文档步骤、0 个业务步骤**。第 14 步已经取得 `phone.search_contacts` 文档，第 16–50 步又连续 35 次查询这份文档。保存的这 35 次返回内容哈希完全一致，每次 1566 字符，未发现 Error/Exception 类标记；也没有实际调用 `phone.search_contacts`。第 50 步耗尽预算。

这是最清楚的残留问题：文档已经拿到，模型却不转换为业务调用。余弦降低了总体退化程度，没有阻止这个题从会做到循环。


[余弦 E2轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/trajectories/df61dc5_1.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/runtime/df61dc5_1/experiments/outputs/dev_df61dc5_1/tasks/df61dc5_1/evaluation/report.md)；[余弦 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/trajectories/df61dc5_1.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/runtime/df61dc5_1/experiments/outputs/dev_df61dc5_1/tasks/df61dc5_1/evaluation/report.md)

### 案例 E：6171bbc_2，执行出错后，查文档与相同错误交替出现

余弦第二轮 **7/7**：19 步，完成 `create_playlist` 与 `add_song_to_playlist`。第三轮仅 **1/7**：39 步、14 个重复文档步骤、3 个业务步骤，最后上下文耗尽。

第三轮第 13、15、17 步读取播放列表/歌曲，随后第 **18、21、25、29、33、37** 步出现相同观察哈希的 `KeyError`，中间反复查询 `show_playlist`、`show_song` 文档。此后没有执行创建列表、添加歌曲的核心动作。

它与案例 D 不同：已开始部分业务，但无法从错误中恢复，反复查文档也没有修正代码。这说明剩余问题还包括错误后的行动选择和代码修复，单纯改变学习率不一定足够。


[余弦 E2轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/trajectories/6171bbc_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_02_dev57/runtime/6171bbc_2/experiments/outputs/dev_6171bbc_2/tasks/6171bbc_2/evaluation/report.md)；[余弦 E3轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/trajectories/6171bbc_2.json) / [官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/epoch_03_dev57/runtime/6171bbc_2/experiments/outputs/dev_6171bbc_2/tasks/6171bbc_2/evaluation/report.md)

## 6. 为什么改善，以及为什么还没有解决根本问题

### 已观察到：后期更新实际变小，并保留了更多业务行为

两者都完成 54 次有效更新。恒定分支第三轮仍保持峰值学习率，余弦第三轮从 `1.709289e-5` 降到 `5e-6`。三轮学习率之和为恒定的 **56.73%**；这只是日程强度的描述，不是参数距离或性能归因比例。


| 轮次 | 恒定：逐批参数变化范数之和 | 余弦：逐批参数变化范数之和 |
| --- | --- | --- |
| 1 | 1.521289 | 1.474795 |
| 2 | 1.388268 | 0.877034 |
| 3 | 1.247839 | 0.236437 |

第三轮余弦的该指标仅为恒定的约 **18.95%**，说明实际后期权重更新幅度确实减小。这里是逐次变化范数的加和，即路径长度，**不是最终模型相对初始化的净距离**。

与之同时发生的是：恒定第三轮无代码终止激增、业务动作几乎消失；余弦保留了较多执行能力。这支持“较小的后期更新可以缓解训练把策略推坏”的解释，但还不能从相关性确定具体受损参数或唯一机制。

### 仍然存在：ZeroFail3 入选样本偏向文档


| 学习率 | 轮次 | 生成总步骤 | 入选SFT步骤 | 文档SFT（占入选） | 业务SFT（占入选） | 重复文档SFT | 平均batch loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 恒定 | 1 | 1817 | 295 | 184（62.37%） | 40（13.56%） | 4 | 0.131321 |
| 恒定 | 2 | 1763 | 726 | 459（63.22%） | 116（15.98%） | 10 | 0.143534 |
| 恒定 | 3 | 2400 | 1212 | 701（57.84%） | 160（13.20%） | 11 | 0.061844 |
| 余弦 | 1 | 1703 | 363 | 229（63.09%） | 49（13.50%） | 7 | 0.129586 |
| 余弦 | 2 | 1783 | 670 | 451（67.31%） | 88（13.13%） | 18 | 0.110632 |
| 余弦 | 3 | 2346 | 1119 | 598（53.44%） | 215（19.21%） | 24 | 0.101671 |

余弦第二轮 **67.31%** 的入选 SFT 步骤是纯文档步骤，业务步骤只有 **13.13%**；第三轮文档仍占 **53.44%**，业务为 **19.21%**。这些是步骤比例，不是 token 比例，也不能直接等同为各类别的梯度贡献。

入选样本中“完全相同的重复文档”只有 7、18、24 步，不能说训练主要在直接复制大量重复步骤。更值得怀疑的是：大量局部无错、能拿到多项 PASS 的文档动作不断被奖励，而从文档转入业务、修正错误、完整完成任务的行为覆盖不足。即使每次文档查询单独看合理，学出的策略也可能整体偏向“继续查文档”。这是数据分布与行为变化共同支持的工作假设，尚未做分支干预证明因果。

第三轮训练采样也呈现不同状态：恒定有 **1416/2400** 个文档步骤、**709** 个重复文档步骤、**380** 个业务步骤；余弦为 **913/2346、319、690**。较温和更新可能减少了“采到更多文档→继续学文档”的反馈放大，但在线采样差异也可能参与这一过程。

训练 loss 不能用来选最佳模型。恒定第三轮 loss **0.061844** 更低，但只有 **1/57** 成功；余弦第三轮 loss **0.101671** 更高，却有 **14/57** 成功。每轮都重新采样并筛选，loss 比的是不断变化的数据，不是固定验证集能力。

### 因果边界：同 seed 不等于相同训练样本

准备时保存的首批对照显示：第一次模型更新之前，5 道题的 sampling seed、初始消息均相同，但 5 条完整回答 token 序列都不完全相同。训练温度为 1，执行与采样存在尚未完全定位的非逐位确定性；Codex 评分也没有固定评分 seed。不能把这些最早的数据差异解释为学习率变化的下游结果。

因此，本次可以下结论：**在现有流程下，这一次余弦运行表现更好，三轮内没有复现恒定方案的严重第三轮崩溃。** 不能下结论：全部收益都由余弦形状造成、问题永久解决、任意 seed 都会同样改善，或仅凭本对照证明优于未训练 base。日程形状与累计更新强度也同时变化，不能区分“余弦特别好”还是“后期/总体更新小一些就够了”。

## 7. 下一步判断与模型保留

**当前建议使用余弦第二轮 batch036 作为本对照的最佳模型。暂不继续第四、五轮，不启动新训练。** 第三轮有局部能力回退、文档占比继续上升，不能因未崩溃就默认更多轮会更好。停止在较早验证最优点有现实意义。

这个结果使纯 ZeroFail3 SFT 仍有进一步小规模验证的价值：第三轮大面积崩溃不是在这套流程下必然发生。但当前最高仅 **15/57** 成功，文档偏向、错误恢复和错误宣告完成仍限制能力，不应期待只调学习率就解决全部问题。

如以后继续，建议按问题分开做，避免同时改多个因素：

1. 若目标是确认这次学习率收益是否稳定：优先在另一个已有恒定基线的 seed 上复现同一余弦日程；若目标是区分曲线形状与更新强度，再比较更低恒定学习率/接近累计学习率的方案。无需直接展开大规模网格。
2. 若目标是解决重复文档：在保留当前日程的前提下，只改变一种数据机制，例如对重复文档去重、限制文档样本占比，或更重视文档到业务的有效推进；同时监控是否损害必要的前提查询。先做小规模对照验证上述分布假设。
3. 持续以完整任务成功、Macro、无代码终止、重复文档、业务覆盖面联合判定，并保留固定的正反案例；不要依赖训练 loss 或完成接口调用数。

以上是后续建议，本次均未执行。

本余弦实验当前只保留 **batch036（第二轮，最佳）与 batch054（第三轮，最新）** 两个完整检查点（LoRA + optimizer 等恢复状态）；模型状态文件合计约 **0.81 GiB**，不含共享基础模型和其他实验。其余中间权重已按运行时既定策略清理，全部轨迹、评分、数据集、指标、官方报告及保留凭据仍在。本次分析没有新增模型副本，也没有额外清理旧实验。

## 8. 可复核材料


- [最终完成状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/STATUS.json)
- [逐轮原始汇总](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/lr_summary.json)
- [本次独立核对汇总](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/audit_summary.json)
- [342条评估轨迹的行为明细](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/dev_tasks.csv)
- [108批学习率、loss与梯度](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/batch_metrics.csv)
- [六组正式汇总CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/epoch_comparison.csv)
- [逐题逐检查配对变化](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/paired_schedules.csv)
- [余弦内部逐轮配对变化](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/paired_epochs.csv)
- [脱敏后的案例API序列](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/case_sequences.json)
- [案例观察哈希与错误类别](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/case_observations.json)
- [首批采样一致性检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/first_batch_sampling_comparison.json)
- [CPU核对脚本](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/analyze.py)
- [报告生成脚本](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/write_report.py)
- [更新前自动报告备份](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/final_comparison_20261028/REPORT_auto_before_review.md)

![三轮学习率对照图](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/lr_comparison.png)
