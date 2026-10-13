# 版本记录

2026-10-12 用户明确要求：**改变 prompt 必须建立新版本。** 任何评分指令、rubric 定义或输出约定的修改，都写入新的 `prompt_vN.txt`；旧版与既有实验快照保持不变。每版记录来源版本、原因、改动及验证结果。schema 若随输出版本改变，也另存为版本文件。

| 类型 | 版本 | 状态与变更 |
| --- | --- | --- |
| Prompt | v1 / appworld-step-v1 | 原始 8 维 P/F/U/N 设计；首轮 baseline；SHA256 `8c80e5480fd925eff89aa887a903c34b89bf3650e5e0ab0073624287fc8bec1a` |
| 输入适配器 | v1 / prepare_input.py | 原始实现，保留 |
| 输入适配器 | v2 / prepare_input_v2.py | 按采集器提取 Python 围栏，避免孤立通用围栏吞掉真正执行的代码；评分语义不变 |

运行日志与版本比较放在 [独立实验目录](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/README.md)。本文件是版本登记，不是 judge 输入。

## Prompt v2 / appworld-step-v2

来源 v1；保持八维、四标签、无权重与 audit/batch 格式。新增五条边界：局部取证与全集消费、已知执行失败与 U 的区别、认证准备不计业务效果、API 规格协议的一致性、分页证据来源。依据首轮实际输出建立；使用同六条完整输入重评，结果见实验目录。

文件：[prompt_v2.txt](prompt_v2.txt)、[output_schema_v2.json](output_schema_v2.json)。v1 不覆盖。

### 试验结果

v1/v2 各 6/6 条、66/66 步有效；28 个开发检查点符合数分别为 24、27，非独立准确率。v2 修正四处但在重复搜索的 R6 判定上回退一处，状态为 **pilot candidate with known regression**。详见 [报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/REPORT.md)。后续改动新建 v3，不覆写 v2。

## Prompt v3 / appworld-step-v3

2026-10-12，按用户审查意见整体重写，不再叠加补丁。规则和适用边界合并进唯一的 Evaluation Rubrics 模块；删除 audit/batch 与 output_mode。小样本和全量使用同一协议。

保留八维 P/F/U/N 与无权重设计。输出改为 `[step_id, 八字符标签, 简短依据]`，含 F/U 的步骤只说明主要问题，不再要求每个 F/U 分项分别生成证据条目。R6 直接纳入忽略相关证据、无信息变化或验证需要的无效重复；不加入具体题目案例。

文件：[prompt_v3.txt](prompt_v3.txt)、[output_schema_v3.json](output_schema_v3.json)、[prepare_input_v3.py](prepare_input_v3.py)、[validate_output_v3.py](validate_output_v3.py)。输入证据与 v2 一致，仅删除模式字段；调用方可指定带数据来源的 trajectory_id。

prompt 字符数：v2 为 5,578，v3 为 1,786，减少约 68%。SHA256：`1743b4b6cd6082c809bbde4791c087ff00428233b914dd5e359f745e48e40151`。

初始状态为本地格式检查通过；之后按用户要求完成下列模型实测。此次重写并非语义等价变换，旧 prompt、旧 schema 和已有实验输出全部保留。


### v3 模型实测（2026-10-12）

v3 原文及 SHA256 保持不变。使用与 v1/v2 相同的 `gpt-5.6-sol / high`，完成原六条、新增两条、两条相同输入重复评分，共 10 次调用、8 条不同轨迹、99 个不同步骤。全部首试通过格式和覆盖验收。

原开发检查点 28/28，新任务调用前冻结的检查点 18/19；均不代表独立准确率。重复评分 216/224 标签一致（96.4%），其中 3 处涉及 F 与非 F 切换。原六条平均调用 78.2 秒，v2 为 87.2 秒。

状态：**小规模候选可用，存在已知语义问题**。新任务发现提交被判为 R5 错误、未确认部分成功便重试的漏判，以及短依据过度推断；不直接视为全量训练真值。完整证据、成本与限制见 [v3 实测报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V3_REPORT.md)。本次没有修改 prompt 或创建 v4。


## Prompt v4 / appworld-step-v4

2026-10-12，依据 v3 实测反例，在唯一 Evaluation Rubrics 模块中修订适用性和各维度边界；明确 R5 排除提交/只读、R6 部分执行后不安全重试优先、R2/R7 区分未知与已知错误。输出仍为八维 PFUN 与一句短依据，无模式、总分或权重。输入适配器继续使用 v3，未更改其证据内容。

文件：[prompt_v4.txt](prompt_v4.txt)、[output_schema_v4.json](output_schema_v4.json)、[validate_output_v4.py](validate_output_v4.py)。正文 2,152 字符；SHA256 `90bdf0447b228d8699f11e9ec4fcea9e23474d591a778fa59a84c04a5f38756a`。整个测试期间未修改 v4。

### 实测与状态

主实验 gpt-5.6-sol / high，15 条不同轨迹、13 道题、12 类任务、279 步，加三条重复评分，共 18 次有效调用；另对相同两条轨迹作 medium 各两次诊断，共 22 次完成、23 次尝试。一次服务容量失败保留原始记录。

回归检查 48/50，新任务 40/43，执行/适用性机械检查 312/312。原 v3 重复样本对在 v4 high 中一致性为 204/224（v3 为 216/224）；medium 为 197/224。不能把局部反例修复当成整体质量提高。

状态：**候选版本；流程可处理全量输入，语义稳定性仍未验证到推荐正式全量使用的程度。** 540 条本地输入已准备，最长 527,852 字符和 50 步轨迹均已完整实测；剩余 525 条未调用。未训练、未生成 reward 或权重，没有把重复评分中的较好结果替换为原结果。

详情见 [v4 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V4_REPORT.md)。后续若修订应新建 v5，不覆盖本版。


## Prompt v5 / appworld-step-v5

2026-10-12，依据v4反例进一步明确事实、业务决策、实际效果与恢复边界，纳入无前置异常的重复查询以及刷新状态后的有效重试。正文2,111字符；SHA256 `bc6335bf245b1c0991970662bad230cd30d6ae04c0e7e8fb8af0e1d57c70de4b`。沿用v3输入适配器、统一八维PFUN短输出与gpt-5.6-sol/high，测试期间prompt保持不变。

12条不同完整轨迹、201步，成功7条、失败5条，另对原v3/v4同一对输入重复评分，共14次有效调用。相同52项回归v4为47/52，v5为50/52；新增检查36/39，合计86/91。219/219执行与只读锚点符合。重复一致性207/224，F/非F切换3处；不把一致性等同准确率。

本助手逐步证据复核全部1608个分项，发现26个明确误判、11个边界争议；不是独立人工真值，也未证实总体95%准确率。采用用户允许少量噪声的标准，状态为**可用的全量离线探索标注基线**。当前v5已评分12条，528条未评分；未启动全量、训练或reward/权重合成。

见[v5完整报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V5_REPORT.md)和[逐步原始结果](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/V5_TRAJECTORIES.md)。不要继续覆盖v5来修孤立反例；后续修改另建v6。


## v6：2026-10-13，后续评分版本

依据540条v5实测中发现的边界问题，直接整合进原Evaluation Rubrics模块：R2按当前子目标；R5明确修改前校验拒绝为N；R6修复执行不抵消业务错误；R7保留未解除的关键未知并检查规定交付格式；R8明确额外代码块。输出仍为8字符标签及一句短依据，没有权重、总分或模式。

v6未进行外部模型评分实测，不声称优于v5；后续新数据可使用该版本并明确记录。已有540条仍为v5，本次局部SFT筛选只消费v5，不重评、不覆盖旧结果。
