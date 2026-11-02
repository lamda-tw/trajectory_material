# B 阶段三组正式比较：混合 SFT + SDPO、纯 SDPO、纯 ZeroFail3 SFT

报告日期：2026-10-26（Asia/Shanghai）。范围：三组各两轮训练、六次 dev57 评估；仅复核已保存材料。本次新增训练、模型推理、Codex 评分调用均为 0。

## 可直接用于汇报的结论

**纯 SFT 已于 2026-10-25 23:17:40（UTC+8）全部完成：36/36 批、36 次实际更新、180 条在线训练轨迹，两轮各完成 57/57 题评估。三个分支均完整结束。**

本轮结果支持：**保留 ZeroFail3 SFT 作为当前基线，停止扩大现有 FAIL-SDPO 配方。** 同一底座、同一训练日程下，纯 SFT 的整题成功数从 7 升到 12；混合从 5 降到 1；纯 SDPO 从 2 降到 0。最严重的行为变化是模型不再推进任务，而是反复读取已见过的文档。纯 SDPO 第二轮所有 57 题都出现长文档循环；其 1,344 步中 1,322 步只查文档，剩余 14 个非文档 API 步骤也全部只是读取支付卡信息。

这使“退化主要与当前 SDPO 分支有关”的判断，比只有混合组时有了直接对照依据。但归因对象是**当前 SDPO 分支与在线采样、反馈教师、损失聚合共同组成的训练流程**；不是证明所有 SDPO 方法无效，也不是证明每条 FAIL loss 都在奖励错误。纯 SFT 仍只有 21.05% 整题成功，残余循环、内容遗漏和错误结束都值得继续解决。

![三组比较概览](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/three_arm_overview.png)

[下载 PNG](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/three_arm_overview.png) · [下载矢量 PDF 图](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/three_arm_overview.pdf)

## 1. 三组到底比较了什么

| 项目 | 三组共同设置 |
|---|---|
| 模型与训练参数 | 同一 Qwen3-8B 底座；新建 LoRA，r=8、alpha=16、dropout=0；底座冻结 |
| 数据与日程 | train90；每批 5 题、每题 1 条完整轨迹；每轮 18 批，共 2 轮、36 次更新机会 |
| 更新方式 | 收集完整批次并离线评分后，每批只执行 1 次 optimizer 更新；不在轨迹中间更新 |
| 评分 | 同一 Codex v7-feedback rubric，对完整轨迹逐步评分 |
| 训练超参 | seed=20261022；AdamW，峰值 lr=5e-5；前 5 次非空更新 warmup；梯度裁剪 1.0 |
| 采样 | temperature=1，thinking=false；最多 50 步；模型上下文 32,000；每步最多生成 3,000 tokens |
| dev 评估 | 每轮结束后同一 dev57；学生不带反馈；temperature=0、seed=100；官方终态 evaluator |
| 教师条件 | 涉及 SDPO 时使用 C2 反馈教师、EMA decay=0.95；不额外引用整份原回答，但教师和学生沿同一个原回答前缀计算分布 |

| 分支 | ZeroFail 且 PASS≥3 的步骤 | 含 FAIL 的步骤 | 其余步骤 |
|---|---|---|---|
| 混合 | 原回答 SFT | C2 条件下 SDPO | mask |
| 纯 SDPO | mask | 同样的 SDPO | mask |
| 纯 SFT | 同样的原回答 SFT | mask | mask |

ZeroFail3 不额外排除 U，沿用原 B 定义。mask 指当前步骤不贡献 loss，历史仍在上下文中。纯 SFT 中保留的 EMA 文件只用于检查点结构兼容，不参与教学或 loss。

混合损失是 `mean_step(SFT 的 token-mean CE) + 1.0 × mean_step(SDPO 的 token-mean reverse-KL)`；两个分支分别取平均。因此 **4,300 个 SDPO 步骤对 912 个 SFT 步骤，不代表 SDPO 权重自动为 SFT 的 4.7 倍**。纯分支只保留相应项。

首批对照复用同 5 条原轨迹与反馈；纯 SFT 使用相同的 20 个合格步骤、mask 48 个 FAIL 步骤，首批 SFT loss 与混合组对应项一致。第 2 批起，各学生自行采样，轨迹和标签自然不同。这里比较的是整套在线学习方法，而非固定同一训练数据上的梯度消融。

配置与冻结文件已复核：[配置审计](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/configuration_audit.json)；[纯 SFT 首批验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/first_batch_acceptance.json)。

## 2. 六次 dev57 的正式结果

| 分支 | 轮次 | 整题成功 | 成功率 TGC | 平均检查通过率 Macro | 通过检查总数 / 291 | 平均步骤 |
|---|---:|---:|---:|---:|---:|---:|

| SFT + SDPO | 1 | 5/57 | 8.77% | 41.28% | 112/291 | 26.86 |
| SFT + SDPO | 2 | 1/57 | 1.75% | 26.38% | 54/291 | 38.30 |
| 纯 SDPO | 1 | 2/57 | 3.51% | 31.42% | 73/291 | 25.93 |
| 纯 SDPO | 2 | 0/57 | 0.00% | 24.80% | 51/291 | 23.58 |
| 纯 ZeroFail3 SFT | 1 | 7/57 | 12.28% | 48.64% | 127/291 | 20.61 |
| 纯 ZeroFail3 SFT | 2 | 12/57 | 21.05% | 58.41% | 158/291 | 25.81 |
**第二轮相对第一轮：** 混合成功数 −4、Macro −14.90 个百分点；纯 SDPO 成功数 −2、Macro −6.62 个百分点；纯 SFT 成功数 +5、Macro +9.78 个百分点。纯 SFT 最终对混合高 19.30 个百分点 TGC、32.03 个百分点 Macro；对纯 SDPO 高 21.05 和 33.61 个百分点。

Macro 是每题“通过检查数 / 该题检查数”再对 57 题等权平均；总通过数除以 291 是另一项 Micro，不能与 Macro 混用。这些检查彼此相关，包含答案、数据库终态和不破坏原数据等要求，**不是独立的 291 道题，也不是业务完成百分比**。

尤其是纯 SDPO 第二轮：51 条通过项全部属于未删除、未误改数据等保护性要求，例如没有删除消息、没有移除原歌曲、没有改动无关文件。它没有完成任何整题。其 24.80% Macro 主要反映“不做事也不会触犯”的要求，不能当作保留了四分之一的执行能力。

历史原始底座曾得到 1/57、Macro 43.53%。这是早期已有记录，本次未重新评估；虽主要评估设置相同，但不是本轮新跑的同步基线。当前混合第二轮与它同为 1/57，却有明显更低的细粒度通过率，说明只看整题数会低估退化。早期离线 ZeroFail3 三种子为 10、8、12/57；本轮 12/57 与其中最好一次持平，不应宣布突破了历史最好结果。

[历史底座评估](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/../2026-10-16_appworld_rubric_selection_ablation/evaluation/base/SUMMARY.json)

### 同一道题配对后，改善是否只来自少数幸运成功？

| 比较（后者相对前者） | 新成功 / 丢失成功 | 检查数更多 / 更少 / 相同的题数 | 新通过检查 / 丢失检查 | 检查净变化 |
|---|---:|---:|---:|---:|

| 混合 E1 → E2 | 0 / 4 | 1 / 14 / 42 | 2 / 60 | -58 |
| 纯 SDPO E1 → E2 | 0 / 2 | 0 / 5 / 52 | 0 / 22 | -22 |
| 纯 SFT E1 → E2 | 7 / 2 | 24 / 9 / 24 | 61 / 30 | +31 |
| 混合 E2 → 纯 SFT E2 | 12 / 1 | 34 / 1 / 22 | 105 / 1 | +104 |
| 纯 SDPO E2 → 纯 SFT E2 | 12 / 0 | 35 / 0 / 22 | 107 / 0 | +107 |
纯 SFT 最终相对混合，在 34 题通过更多检查、1 题更少；相对纯 SDPO，在 35 题更多、没有更少。即使只看两组都未全对的题，SFT 对混合仍净多通过 69 条检查，对 SDPO 净多 71 条。因此优势不只是“多几题恰好跨过全对门槛”。这些子集是事后分组，只作描述。

纯 SFT 第二轮成功覆盖 7/19 个任务家族；混合覆盖 1/19，纯 SDPO 为 0。SFT 自身仍有 9 题检查数下降、2 题从成功变失败，不是逐题单调进步。混合最终唯一成功的 `23cf851_1`，纯 SFT 最终反而失败；不能说纯 SFT 在每一道题上都优于混合。

[逐条官方检查及原始报告路径](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/official_checks.csv)；[逐题配对得失](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/paired_checks.csv)；[全部家族比较](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/families.csv)。

## 3. 最主要的性能问题：从使用工具退化为循环读取说明书

| 分支 | 轮次 | 全部步骤 | 纯文档步骤 | 重复文档步骤 | 连续≥5次相同文档的题 | 上下文超限 | 达到50步上限 |
|---|---:|---:|---:|---:|---:|---:|---:|

| SFT + SDPO | 1 | 1531 | 696（45.46%） | 516（33.70%） | 24/57 | 24/57 | 14/57 |
| SFT + SDPO | 2 | 2183 | 1733（79.39%） | 1546（70.82%） | 47/57 | 26/57 | 30/57 |
| 纯 SDPO | 1 | 1478 | 1038（70.23%） | 924（62.52%） | 38/57 | 32/57 | 12/57 |
| 纯 SDPO | 2 | 1344 | 1322（98.36%） | 1250（93.01%） | 57/57 | 45/57 | 8/57 |
| 纯 ZeroFail3 SFT | 1 | 1175 | 240（20.43%） | 89（7.57%） | 5/57 | 7/57 | 9/57 |
| 纯 ZeroFail3 SFT | 2 | 1471 | 604（41.06%） | 244（16.59%） | 5/57 | 6/57 | 14/57 |
统计只使用实际生成步骤，不计 prompt 演示。“纯文档”指 Python 中静态识别出的 `apis.*` 调用全部属于 `apis.api_docs.*`；“重复文档”要求同轨迹此前已有完全相同 Python AST，分母是该次评估的全部步骤。“长循环”要求至少连续 5 步相同文档代码。改写变量名、不同代码查同份文档、交替重复、初始示例中已出现的文档可能漏计，因此这是可复算的行为指标，不等同完整 R6 判定。

查询文档本身是正常动作。问题在于文档已经提供，却重复查相同内容，没有进入下一步。混合的重复文档步从 516 增到 1,546；纯 SDPO 从 924 增到 1,250，最终占全部步骤的 93.01%。

纯 SDPO 平均步骤从 25.93 降到 23.58 **不是效率改善**：45/57 题因上下文耗尽而停止，反复返回长文档使其更早触及上下文预算。混合第二轮则 56/57 题以“上下文或步数到限”结束，只有 1 题通过完成接口结束。

| 行为层次 | 混合 E1 → E2 | 纯 SDPO E1 → E2 | 纯 SFT E1 → E2 |
|---|---:|---:|---:|

| 含非文档 API 代码的步骤 | 570 → 394 | 326 → 14 | 772 → 766 |
| 含业务 API 代码的步骤 | 404 → 112 | 246 → 0 | 458 → 538 |
| 至少出现业务 API 代码的题数 | 33 → 8 | 25 → 0 | 54 → 53 |
| 全程每一步均为纯文档的题数 | 19 → 33 | 27 → 47 | 1 → 3 |
| 调用完成接口结束的题数 | 14 → 1 | 7 → 0 | 34 → 34 |
这里进一步把文档、Supervisor 和 login/logout 排除后，称为“业务 API 代码”。它包括查询与修改业务数据，**只代表代码里出现了尝试，不保证执行成功或业务正确**。纯 SDPO 第二轮静态识别到的业务 API 步骤为 0；其 14 个非文档步骤全部是 `supervisor.show_payment_cards`，只涉及 2 题。纯 SFT 则仍在 53/57 题尝试业务 API，相关步骤从 458 增至 538。

**纯 SFT 也没有解决文档依赖。** 它的纯文档步从 240 增到 604，重复文档从 89 增到 244；长循环题虽然都是 5 题，但只有 `6171bbc_1` 两轮重合，其余是 4 题退出、4 题新增。不能把“数量不变”写成“原来的 5 题一直没修好”。第二轮 5 个长循环题贡献 126/244 个重复文档步，余下 118 个散布在其他题，问题不限于最严重的 5 题。

### 纯 SFT 第二轮剩余的 5 个长文档循环

| 题目 | 长循环行为 | 最长连续次数 | 全题步骤 | 官方检查通过 |
|---|---|---:|---:|---:|

| 37a8675_1 | Venmo：反复查 show_payment_cards 规范 | 37 | 50 | 0/6 |
| 4ec8de5_3 | Spotify：反复查 show_playlist_library 规范 | 42 | 44 | 1/2 |
| 50e1ac9_2 | Spotify：反复查 search_songs 规范 | 19 | 20 | 1/2 |
| 50e1ac9_3 | Spotify：多份规范间切换，最后重复 search_songs | 9 | 30 | 1/2 |
| 6171bbc_1 | Spotify：反复查完整 API 列表 | 12 | 13 | 1/7 |
[全部 342 条评估轨迹的行为表](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/dev_detailed.csv)；[逐题动作摘要（只保留接口和文档参数）](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/case_actions.json)。

## 4. 具体案例：究竟不会做什么了，又恢复了什么

### 案例 A：本来会关注艺人，后来只查 Spotify 接口列表

任务 `d4e9306_2`：关注自己曾点赞的全部歌曲、专辑对应的艺人。

| 分支 | 第一轮 | 第二轮 |
|---|---|---|
| 混合 | 11 步、6/6 检查，成功 | 13 步全部读取同一份 Spotify API 列表；1/6，因上下文耗尽停止 |
| 纯 SDPO | 12 步全部读列表；1/6 | 13 步全部读列表；1/6 |
| 纯 SFT | 50 步、2/6；会调用业务，但未完成目标 | 17 步、6/6，成功；6 个文档步骤，0 个重复文档步骤 |

混合第二轮和纯 SDPO 第二轮重复的是：

```python
print(apis.api_docs.show_api_descriptions(app_name='spotify'))
```

纯 SFT 第二轮经历补登录等步骤后，读取点赞歌曲、点赞专辑，整理艺人信息，并在第 14–16 步实际调用 `spotify.follow_artist`，第 17 步结束。官方不仅确认“未误删关注”，还确认目标关注集合满足要求。

这说明需要保留的是“查到足够信息后执行正确动作”的能力；不应为了压低文档比例，把本来有用的文档查询一起惩罚。

[SFT + SDPO E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b/runs/mixed/epoch_02_dev57/trajectories/d4e9306_2.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b/runs/mixed/epoch_02_dev57/runtime/d4e9306_2/experiments/outputs/dev_d4e9306_2/tasks/d4e9306_2/evaluation/report.md)；[纯 ZeroFail3 SFT E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/trajectories/d4e9306_2.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/runtime/d4e9306_2/experiments/outputs/dev_d4e9306_2/tasks/d4e9306_2/evaluation/report.md)

### 案例 B：反复看“当前歌曲怎么查”，却不真的切歌

任务 `b119b1f_2`：不断切换下一首，直到目标艺人的歌曲。

混合第一轮 23 步、6/6 成功；第二轮 50 步全部是文档，0/6，耗尽步数。纯 SDPO 第二轮也走满 50 个文档步骤，0/6。相同规范可能以不同变量赋值形式重复，因此 AST 精确重复数分别为 47、46，不能把 50 步全都称为同一代码。

纯 SFT 第二轮先查必要规范，再在第 8–16 步交替执行 `show_current_song` 和 `next_song`，17 步完成，6/6 全通过。这里业务 API 的重复是推进播放器状态所必需的，与重复查同一份静态文档性质不同。

[SFT + SDPO E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b/runs/mixed/epoch_02_dev57/trajectories/b119b1f_2.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b/runs/mixed/epoch_02_dev57/runtime/b119b1f_2/experiments/outputs/dev_b119b1f_2/tasks/b119b1f_2/evaluation/report.md)；[纯 ZeroFail3 SFT E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/trajectories/b119b1f_2.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/runtime/b119b1f_2/experiments/outputs/dev_b119b1f_2/tasks/b119b1f_2/evaluation/report.md)

### 案例 C：纯 SDPO 自己也丢失了已经获得的能力

任务 `396c5a2_1`：把指定艺人、播放次数超过阈值的歌曲加入队列。

纯 SDPO 第一轮用 11 步完成搜索与 `add_to_queue`，6/6 通过；第二轮连续 13 次查询 Spotify API 列表，0/6。**这不是“去掉 SFT 后从一开始就不会”，而是同一个纯 SDPO 运行继续训练后，从会做变成不再执行。**

纯 SFT 第二轮得到 5/6：队列内容、原队列保留、目标歌曲覆盖等所有状态检查均通过，但结束时回答了 `song added to queue`，官方要求无额外答案（null），所以严格整题仍算失败。这个例子说明“业务做对但结束方式不对”和“根本没做业务”会同样记作一题失败，必须读细粒度检查。

[纯 SDPO E1 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/runs/sdpo/epoch_01_dev57/trajectories/396c5a2_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/runs/sdpo/epoch_01_dev57/runtime/396c5a2_1/experiments/outputs/dev_396c5a2_1/tasks/396c5a2_1/evaluation/report.md)；[纯 SDPO E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/runs/sdpo/epoch_02_dev57/trajectories/396c5a2_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/runs/sdpo/epoch_02_dev57/runtime/396c5a2_1/experiments/outputs/dev_396c5a2_1/tasks/396c5a2_1/evaluation/report.md)；[纯 ZeroFail3 SFT E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/trajectories/396c5a2_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/runtime/396c5a2_1/experiments/outputs/dev_396c5a2_1/tasks/396c5a2_1/evaluation/report.md)

### 案例 D：纯 SFT 也会退步——文件名对了，正文却变成空的

任务 `6c2c621_1`：把全部 Simple Note 笔记导出为指定目录下的 Markdown 文件。

纯 SFT 第一轮 19 步、8/8 成功；第二轮 20 步、6/8。第二轮建好了目录与文件，名称和路径检查通过，但没有读取完整笔记正文，直接创建空文件。第 19 步的原代码注释明确写了“假定正文在 note 对象中”“先创建空文件”；实际 `create_file` 未传 content。

```python
# 第二轮相关调用的原样核心片段：未传正文
create_file_result = apis.file_system.create_file(
    file_path=file_path, access_token=file_system_access_token
)
```

官方失败的是“文件内容集合”和“路径到内容的对应关系”，生成内容集合为 `{''}`。这类退化发生在已进入业务执行之后，不能用禁止重复文档解决。混合第二轮该题为 1/8、45 步，主要重复 `search_notes` 规范；纯 SDPO 第二轮为 1/8、50 步，全程重复 Simple Note 列表。

纯 SFT 另一道丢失的成功题 `23cf851_1` 是 Venmo 点赞数统计：第一轮 2/2，第二轮 1/2，回答 9，官方期望 11；无数据库修改要求仍通过。这里只确认统计结果错误，不把未经进一步核验的分页或日期边界猜测写成确定根因。

[纯 ZeroFail3 SFT E1 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_01_dev57/trajectories/6c2c621_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_01_dev57/runtime/6c2c621_1/experiments/outputs/dev_6c2c621_1/tasks/6c2c621_1/evaluation/report.md)；[纯 ZeroFail3 SFT E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/trajectories/6c2c621_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/runtime/6c2c621_1/experiments/outputs/dev_6c2c621_1/tasks/6c2c621_1/evaluation/report.md)；[纯 ZeroFail3 SFT E2 轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/trajectories/23cf851_1.json)；[官方检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/runs/sft/epoch_02_dev57/runtime/23cf851_1/experiments/outputs/dev_23cf851_1/tasks/23cf851_1/evaluation/report.md)

## 5. 纯 SFT 剩余 45 道失败题，不能统称为“模型能力弱”

按结束方式可以无重叠地分为：

| 类别 | 题数 | 说明 |
|---|---:|---|
| 主动调用完成接口，但官方未全通过 | 22 | 可能是内容遗漏、答案错误、错误宣告结束，不能把 completion_api 当成功 |
| 达到步数或上下文上限 | 20 | 14 题步数到限、6 题上下文到限；长文档循环是其中的重要现象，但不是全部原因 |
| 输出没有可执行 Python，终止 | 3 | 生成/结束协议问题，也可能此前已经完成部分业务 |
| 合计 | 45 | 另有 12 题正式成功 |

其中有 **5 题的全部非答案状态检查已通过，仅答案要求失败**：

| 题目 | 官方检查通过 | 具体结束问题 |
|---|---:|---|

| 396c5a2_1 | 5/6 | 回答了 song added to queue，期望 null |
| 396c5a2_3 | 5/6 | 回答了 1，期望 null |
| 6171bbc_2 | 6/7 | 回答了播放列表名称，期望 null |
| b119b1f_1 | 5/6 | 回答了当前歌曲名，期望 null |
| df61dc5_1 | 6/7 | 没有按接口提交最终答案（not_given），期望 null |
这 5 题是后续结束协议核验的高价值对象，**本报告没有给它们补分、重跑或把成功率改成 17/57**。还有 11 道只缺“答案检查”的题属于纯查询任务，仅靠不修改数据库即可通过另一项检查，不能认为它们的业务已经完成。

残余问题至少包括：停止重复、正确使用已有状态、完整读取和处理业务数据、准确汇总答案、按协议结束。应按这些具体错误安排下一步，而不是直接增加训练轮数或统一归结为 8B 参数规模。

## 6. 在线训练过程怎样走向了不同结果

| 分支 | 轮次 | 采样步骤 | 用于 SFT | 用于 SDPO | mask | 训练轨迹重复文档步占比 | R6 FAIL 步骤 |
|---|---:|---:|---:|---:|---:|---:|---:|

| SFT + SDPO | 1 | 2048 | 404 | 1644 | 0 | 9.23% | 905 |
| SFT + SDPO | 2 | 3166 | 508 | 2656 | 2 | 42.51% | 2481 |
| 纯 SDPO | 1 | 2031 | 0 | 1685 | 346 | 10.73% | 1049 |
| 纯 SDPO | 2 | 2683 | 0 | 2437 | 246 | 61.98% | 2358 |
| 纯 ZeroFail3 SFT | 1 | 1954 | 311 | 0 | 1643 | 6.60% | 892 |
| 纯 ZeroFail3 SFT | 2 | 1891 | 650 | 0 | 1241 | 12.64% | 680 |
三组每轮都采 90 条完整轨迹。混合和纯 SDPO 的第二轮数据显著变长、重复增多；纯 SFT 第二轮总步骤反而从 1,954 降至 1,891，合格 SFT 步骤从 311 增至 650。训练轨迹不在本轮执行官方任务成功评估，因此这些计数不能冒充 train90 成功率。

R6 FAIL 不只包括本报告精确匹配到的文档重复，也包括其他低效重复动作。混合第二轮 2,656 个 SDPO 步骤中有 2,481 个带 R6 FAIL（93.41%）；纯 SDPO 为 2,358/2,437（96.76%）。训练后期大部分蒸馏样本已集中到重复/低效行为。

**具体训练例子：** 纯 SDPO batch025 的 `29caf6f_2` 共 50 步，全都查询同一份 Simple Note API 列表。第 1 步被 mask，第 2–50 步全部因 R6 FAIL 进入 SDPO。Codex 在第 2 步已明确指出：第 1 步已经拿到列表，再查没有新信息；应复用列表，查看相关接口的完整规范。该题单条重复轨迹贡献 49/179（27.37%）个 batch 内 SDPO 步骤。

这里没有证据说 Codex 鼓励了重复。问题是：**正确的文字反馈，不自动保证反馈教师沿原错误前缀提供可靠的纠错分布；大量相似失败状态又会在 step 平均中占据很大份额。** 此例 49 个步骤在一次批更新前一起计算，不能误写成“模型在一条轨迹内连续进行了 49 次参数更新”。也不能仅凭这些步骤的 loss 非零，就说它们都在强化原错误。

[该轨迹的原始反馈](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sdpo_only/runs/sdpo/batch_025/judging/b025_29caf6f_2/judgement.json)

### SFT 的选样也有偏向，值得单独改善

| 来自哪组 | 轮次 | SFT 监督步骤 | 其中纯文档 | 其中含业务 API 代码 |
|---|---:|---:|---:|---:|

| SFT + SDPO | 1 | 404 | 217（53.71%） | 84（20.79%） |
| SFT + SDPO | 2 | 508 | 347（68.31%） | 33（6.50%） |
| 纯 ZeroFail3 SFT | 1 | 311 | 201（64.63%） | 43（13.83%） |
| 纯 ZeroFail3 SFT | 2 | 650 | 411（63.23%） | 109（16.77%） |
纯 SFT 两轮 961 个监督步骤中，612 个（63.68%）是纯文档，152 个（15.82%）含业务 API 代码，其他是登录、Supervisor、局部计算等。ZeroFail3 能排除显式违规，但“没有违规且有多个 PASS”不等于“对最终任务最有训练价值”。必要查文档更容易满足这些局部规则，而复杂业务步骤更容易因其他问题被 mask。

混合第二轮 SFT 样本中，纯文档占 68.31%，业务 API 步仅 6.50%。这说明当在线策略逐渐停滞时，连 SFT 分支可收集到的正例也越来越偏向准备动作。它与失败闭环相符，但目前没有通过固定数据重加权消融证明它是独立根因。

因此结论不是“SFT 完全无关且已经完美”，而是：**纯 SFT 的问题是局部偏向与任务质量不完整；当前 SDPO 分支伴随的则是更严重、普遍的业务执行消失。**

[所有选中步骤的动作类型统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/selected_training_steps.csv)；[逐批训练指标](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/batches.csv)。

## 7. 数值是否异常？为什么纯 SFT 快很多？

| 分支 | 更新次数 | loss 范围 | 裁剪梯度批数 | 最大 allocated / reserved 显存 GiB |
|---|---:|---|---:|---:|

| SFT + SDPO | 36 | SFT 0.0658–0.2014; SDPO 0.0173–0.5602 | 2/36 | 37.78 / 92.47 |
| 纯 SDPO | 36 | SFT 0.0000–0.0000; SDPO 0.0121–0.7505 | 1/36 | 37.78 / 94.31 |
| 纯 ZeroFail3 SFT | 36 | SFT 0.0526–0.1495; SDPO 0.0000–0.0000 | 0/36 | 34.08 / 45.51 |
108 个已完成批次的损失和梯度范数均为有限数，学生参数更新非零，教师没有收到梯度；都记录为 GPU1。纯 SFT 没有空批次，SDPO loss 与加权 SDPO 梯度始终为 0；纯 SDPO 的 SFT loss/梯度始终为 0。纯 SFT 首批 loss=0.127830415、梯度范数=0.260153234，符合首批验收；整个运行梯度范数为 0.1917–0.4681，未触发裁剪。

纯 SDPO 的蒸馏 loss 从首批 0.4318 降至末批 0.01209，但成功率降至 0。由于在线样本和 EMA 教师在变，这并不是固定数据上的学习曲线；它至少说明“学生与反馈教师分布越来越接近”不能作为任务质量改善的验收标准。整体证据更符合学习目标/数据分布失效，而非 NaN、梯度未更新、SFT 没关闭这类技术故障。

| 分支 | 训练程序累计 | Codex 评审墙钟 | 两次 dev 评估 | 采样、启动及其余 | 全流程墙钟 |
|---|---:|---:|---:|---:|---:|

| SFT + SDPO | 18.51 h | 2.86 h | 1.14 h | 2.92 h | 25.43 h |
| 纯 SDPO | 18.44 h | 1.76 h | 0.67 h | 2.74 h | 23.62 h |
| 纯 ZeroFail3 SFT | 1.02 h | 2.99 h | 0.94 h | 2.53 h | 7.48 h |
纯 SFT 全流程约 7 小时 29 分，混合约 25 小时 26 分，纯 SDPO 约 23 小时 37 分。纯 SFT 相对混合总耗时减少约 70.6%，训练程序计时减少约 94.5%。

主要原因是纯 SFT 只对 961 个合格步骤做 CE，mask 2,884 个其他步骤；它不做每个 FAIL 的反馈教师 forward 和分布匹配。混合、纯 SDPO 分别处理 4,300、4,122 个蒸馏步骤，后期又有长历史循环。不能把这说成固定相同样本量上的算法吞吐快 18 倍；监督样本数、长度和计算路径都不同。

时间来自运行开始/完成标记、训练 metrics 和评审/评估事件。训练程序累计含模型载入等开销，不等于纯 GPU kernel 时间；评审墙钟按每批并发跨度计算，未把并行请求时长相加。纯 SFT 仍为完整新在线轨迹进行评分，除首批 5 条缓存外有 175 次初始评审、4 次格式修复。它的 Codex 评审约 2.99 小时，已超过训练本身的 1.02 小时；后续节约成本需要同时考虑评分流程。

## 8. 对退化原因，现在能说到什么程度

| 判断 | 证据与边界 |
|---|---|
| 当前严重退化主要与 SDPO 分支有关 | 纯 SFT 两轮改善；两组含 SDPO 都变差；纯 SDPO 最严重。支持当前配方不应扩大，而非证明一个孤立超参的因果作用 |
| SFT 不是造成全面文档循环的必要条件 | 纯 SDPO 没有 SFT 仍出现全部 57 题长循环；纯 SFT 同设置没有出现同等规模停滞 |
| 反馈教师目标可靠性存在缺口 | 旧固定状态诊断发现教师并非稳定纠错，部分原前缀信号很弱或反向；本轮没有重新对各控制组做教师概率诊断 |
| 不能把所有 SDPO 样本说成反向奖励错误 | 旧 8 个重复文档案例中只有 1 个明确反向动作分叉，4 个几乎无代码区分，3 个方向是在压制原动作 |
| 不能只归因于“Qwen3-8B 太弱” | 同一 8B 在纯 SFT 下取得更好终态，也存在能自由纠错的教师案例。具体难点是长历史和原错误前缀条件下目标是否可靠 |
| 没有证据证明 KL 符号或 response 对齐写错 | 既有论文/官方代码核查和 CPU 数值对照未发现这一类错误；本地整套训练配置与论文仍不同 |

旧 8 案例中，初始 C2 的有效首步修复为 4/8，最终混合组 EMA C2 为 2/8；首步仍含不必要旧文档查询由 2/8 增至 6/8。这说明“老师自己也会退化”确实在混合运行中被观察到。**它不等于已经证明教师退化是最初原因**：学生更新、EMA 跟随、在线数据变坏可以互相影响。

一个与现有证据相容的解释是：部分纠错目标不可靠或区分度不足 → 学生更易停留在熟悉的准备动作 → 在线采到更多重复失败 → 这些失败在后续 SDPO 中占更大份额，EMA 教师也跟随漂移。现有记录支持这条风险链的多个环节，但没有隔离每个环节的因果贡献，不能分摊“多少百分比是 SFT / SDPO / EMA 导致”。

本轮三组结果把“优先排查哪个分支”回答得更清楚；没有把机制层面的不确定性全部消除。

[原 8 案例完整分析](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/repeat_docs_8case_analysis/REPORT.md)；[既有论文与官方实现审计](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/implementation_audit/REPORT.md)

## 9. 下一步建议与是否继续投入

**建议暂停当前配方的任何大规模 SFT + FAIL-SDPO / 纯 SDPO 训练，也不直接进入该配方的阶段 C。** 两次含 SDPO 的完整运行已经给出一致的风险信号，继续堆轮数或加大 SDPO 权重缺乏依据。保存现有三组结果和纯 SFT E2 作为对照基线。

建议按以下顺序安排后续工作；本次只形成建议，未执行新推理或训练：

1. **先处理可明确定位的纯 SFT 缺口。** 从 5 个状态已正确但答案/结束失败的任务开始核对 completion 规范，再检查空文件这类“步骤看似合法但业务未完成”的案例。区分通用执行协议修正与训练改进；任何修正都应重新完整评估，不给旧结果事后补分。复核已有 5 个残余长循环及另外 118 个分散重复文档步，避免只修一个模板。
2. **如果预算只允许下一项训练研究，优先验证 ZeroFail3 SFT 的稳定性。** 新 seed 复验，并预先固定主要指标、停止标准和独立评估集。当前只有一个训练 seed；dev57 已反复用于探索，不宜把 12/57 当成已验证的泛化收益。不要因为第二轮提高就直接延长到更多轮，因为重复文档占比也已上升。
3. **FAIL 的利用可以继续研究，但要更换验证问题。** 先在固定状态上取得“反馈后实际执行通过”的修正版，检查它是否真的解决当前错误、是否引入新错误、有没有提供缺失信息。可研究验证后修正版 SFT，或仅对教师目标可信的状态蒸馏；二者都属于新的配方，不能冒称已经验证有效或只是修复原 SDPO bug。需同时保留干净状态，检查原本会做的动作有没有丢失。
4. **针对数据分布提出小规模可检验假设。** 比较按轨迹控制重复样本数量、按错误状态去重，以及文档/前提/业务执行步骤的抽样比例；当前按 step 平均会让长重复轨迹占更多份额。但不要直接把所有文档步骤删掉，成功案例也依赖必要文档。只有固定数据、固定初始权重的小实验排除了明显回归，才值得考虑新一轮在线训练。

建议下一次验收至少同时报告：官方整题成功、逐检查通过、重复文档占比、长循环题数、业务 API 尝试覆盖、错误完成数和干净状态能力保持。**loss 下降、教师有反馈、局部首步变好，都不足以单独批准长时间训练。**

用于主管的决策表述可以是：

> 本轮完成了三分支、两轮的正式对照。ZeroFail3 SFT 在当前种子下有效改善 AppWorld 表现；直接把所有 FAIL 步骤交给反馈教师做原前缀蒸馏，未转化为端到端收益，反而出现普遍文档循环和业务执行消失。我们建议停止扩大现有 SDPO 配方，保留 SFT 基线，先解决可定位的执行质量与教学目标可靠性问题，再决定是否重启 FAIL 利用方向。

## 10. 证据范围、限制与复核入口

三组同一训练 seed，第二批起数据独立在线生成；评分存在生成随机性，运行发生在不同时间。没有多 seed 置信范围，不把 57 个同家族变体当成完全独立样本；19 个家族各有 3 题。dev57 已多次用于方案选择，需另有独立评估确认泛化。代码静态分析识别的是调用尝试，可能漏掉间接调用；它不是新的 rubric 评分。

本次重新核验 540 条训练轨迹、342 条 dev 轨迹、108 份实际 dataset 的哈希和关联结果；解析并对齐了 342 份官方检查报告，每次 291 条检查。复核 602 个现存 checkpoint 文件哈希，以及三个 preparation manifest 的 163 个条目（包括重复引用的共享文件）。

有 46 个历史中间 `state.pt` 当前不存在（混合 13 个、纯 SDPO 33 个）；本次未核验这些缺失的优化器/恢复状态，也不推断其缺失原因。两组首批、第 18、36 批的状态仍在，所有现存学生/教师 adapter、训练 metrics、正式评估轨迹及报告均核验通过。这个限制影响部分中间点精确恢复，不改变已保存的六次正式评估数值。

主报告：[THREE_ARM_COMPARISON_REPORT.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/THREE_ARM_COMPARISON_REPORT.md)。

- [审计汇总、计时、缺失文件清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/summary.json)
- [逐检查与配对汇总](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/details_summary.json)
- [逐题行为与结果 CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/dev_detailed.csv)
- [逐条官方检查 CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/official_checks.csv)
- [逐题配对变化 CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/paired_checks.csv)
- [训练选样构成 CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/selected_training_steps.csv)
- [342 条轨迹动作摘要](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/case_actions.json)
- [配置一致性与冻结文件审计](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/configuration_audit.json)
- [评估 summary 和官方 report 的来源哈希](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/input_hashes.json)
- [原自动报告快照](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/automatic_report_snapshot.md)

复算仅使用 CPU 和本地已保存文件：

```bash
python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/analyze.py
python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/details.py
/root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/plot.py
python /root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_only/analysis/three_arm_review/write_report.py
```

报告不修改训练配置、权重、原评分或正式分数。

## 附录：全部 19 个家族的第二轮结果

同族包含 3 题。每个单元为“整题成功数 / 3；Macro 检查通过率”。

| 家族 | 混合 | 纯 SDPO | 纯 SFT |
|---|---:|---:|---:|

| 0d8a4ee | 0/3；20.00% | 0/3；20.00% | 0/3；60.00% |
| 23cf851 | 1/3；66.67% | 0/3；50.00% | 2/3；83.33% |
| 37a8675 | 0/3；0.00% | 0/3；0.00% | 0/3；0.00% |
| 383cbac | 0/3；50.00% | 0/3；50.00% | 0/3；50.00% |
| 396c5a2 | 0/3；0.00% | 0/3；0.00% | 0/3；55.56% |
| 3ab5b8b | 0/3；16.67% | 0/3；16.67% | 0/3；55.56% |
| 4ec8de5 | 0/3；50.00% | 0/3；50.00% | 0/3；50.00% |
| 4fab96f | 0/3；12.50% | 0/3；12.50% | 0/3；37.50% |
| 50e1ac9 | 0/3；50.00% | 0/3；50.00% | 0/3；50.00% |
| 530b157 | 0/3；10.00% | 0/3；10.00% | 0/3；33.33% |
| 57c3486 | 0/3；33.33% | 0/3；20.00% | 0/3；66.67% |
| 6171bbc | 0/3；14.29% | 0/3；14.29% | 1/3；66.67% |
| 68ee2c9 | 0/3；20.00% | 0/3；20.00% | 0/3；46.67% |
| 6bdbc26 | 0/3；50.00% | 0/3；50.00% | 3/3；100.00% |
| 6c2c621 | 0/3；12.50% | 0/3；12.50% | 1/3；62.50% |
| b119b1f | 0/3；0.00% | 0/3；0.00% | 1/3；88.89% |
| d4e9306 | 0/3；16.67% | 0/3；16.67% | 2/3；72.22% |
| df61dc5 | 0/3；28.57% | 0/3；28.57% | 0/3；47.62% |
| fac291d | 0/3；50.00% | 0/3；50.00% | 2/3；83.33% |

