# CFST第7b步：1epoch模型在冻结检查30题上的评测

**已完成三个新分支各30题，共90条完整新轨迹及官方评分；原epoch5的17/30经核验复用。旧模型、旧评测结果均保留。** 本步未调用教师、生成训练答案、训练模型或运行Dev57。

| 模型 | 官方成功 | 成功率 | 新增成功 | 退步 | 相对原epoch5净改善 | 旧版到1epoch |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 原epoch5（复用） | 17/30 | 56.7% | — | — | — | — |
| CFST-state-1epoch | 17/30 | 56.7% | 5 | 5 | +0 | 13/30 → 17/30（+4） |
| CFST-Action-1epoch | 19/30 | 63.3% | 5 | 3 | +2 | 14/30 → 19/30（+5） |
| CFST-Mixed-1epoch | 15/30 | 50.0% | 6 | 8 | -2 | 14/30 → 15/30（+1） |

新增成功和退步均相对原epoch5；最右列对比此前约8,000监督tokens版本。

预设选择结果：**CFST-Action-1epoch进入候选**。
候选只通过了检查30题的选择门槛，尚未替代当前学生；是否接受更新仍需之后单独执行Dev57。本次不启动Dev57。

## 协议和数据边界

三支来自第6b步：State 12条/6次更新、Action 8条/4次更新、Mixed 20条/10次更新，各完整训练一轮。所有任务从初始环境开始，没有注入Codex动作或重放旧学生响应。

temperature=0、seed=100、最大32,000上下文、每次最多3,000输出tokens、每题最多50步、无reasoning parser、相同simplified ReAct运行器和官方evaluator。两个独立GPU并行跑State和Action，先空闲的卡接着跑Mixed；分支内部逐题单进程运行。

来源60题与检查30题及其任务族划分保持冻结。每支隔离目录的train.txt仅包含同一30题；原数据文件保持不变。原epoch5的180个证据文件、模型权重、提示词和运行器已重新核验；新轨迹的第一次模型输入逐字匹配同题基线。

沿用旧第7步已经验证的日志序列化修复：只在保存API日志时将Python Ellipsis写成类型标记，不改变动作、环境返回或评分。本次未启用任何前缀重放；实际触发记录见summary.json。首次后台监督程序在任何分支启动之前退出，相关状态保存在startup_supervisor_abort；未产生模型调用或任务重试。

## 逐题变化（相对原epoch5）

- **CFST-state-1epoch**：新增成功 `afc0fce_1, e7a10f8_1, 6ea6792_2, 6ea6792_3, aa8502b_1`；退步 `b7a9ee9_2, b7a9ee9_3, 3c13f5a_1, e7a10f8_2, aa8502b_2`。
- **CFST-Action-1epoch**：新增成功 `afc0fce_1, 229360a_2, e7a10f8_1, 6ea6792_2, 6ea6792_3`；退步 `b7a9ee9_3, 07b42fd_1, cf6abd2_2`。
- **CFST-Mixed-1epoch**：新增成功 `ce359b5_1, 229360a_2, e7a10f8_1, 6ea6792_2, 6ea6792_3, aa8502b_1`；退步 `afc0fce_3, b7a9ee9_3, ce359b5_3, 07b42fd_1, 3c13f5a_1, cf6abd2_2, e7a10f8_2, 6ea6792_1`。

## 难度、任务族与运行成本

| 模型 | 难度1 | 难度2 | 难度3 | 全部成功任务族 | 上下文超限题数 | 模型调用数 | 输入tokens | 输出tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 原epoch5（复用） | 9/12 | 6/12 | 2/6 | 3/10 | 1 | 588 | 6,003,025 | 58,160 |
| CFST-state-1epoch | 11/12 | 4/12 | 2/6 | 3/10 | 2 | 626 | 6,703,234 | 59,205 |
| CFST-Action-1epoch | 10/12 | 6/12 | 3/6 | 2/10 | 1 | 475 | 4,452,160 | 46,878 |
| CFST-Mixed-1epoch | 8/12 | 7/12 | 0/6 | 1/10 | 4 | 636 | 7,066,369 | 63,814 |

## 如何解释

- CFST-state-1epoch：相对旧版成功数变化+4题；相对原epoch5新增成功5题、退步5题，净变化+0题。
- CFST-Action-1epoch：相对旧版成功数变化+5题；相对原epoch5新增成功5题、退步3题，净变化+2题。
- CFST-Mixed-1epoch：相对旧版成功数变化+1题；相对原epoch5新增成功6题、退步8题，净变化-2题。

先区分“比旧版更好”和“超过原epoch5”两件事。最终选择按后者的新增成功减退步执行；所有分支及全部任务均报告，不挑选有利结果。

这轮保持评测协议，只把训练改为每条样本学一次。样本数、监督tokens和更新次数因此不同，专项组与Mixed的差异不能单独证明能力分类合理。检查30题曾参与最初train90 SFT，且本次方案是在看到旧检查结果后提出；这里只能作为开发实验，不能当作未见任务泛化或单独锁定退步原因的证据。

## 产物

- task_comparison.csv：原epoch5与三个1epoch分支的逐题结果。
- task_comparison_with_previous.csv / comparison_vs_previous.csv：加入旧版分支的逐题及汇总对照。
- family_comparison.csv：10个任务族结果。
- summary.json / selection.json：完整指标与冻结规则的候选判断。
- 各分支trajectory_index.jsonl、task_results.csv及成功/失败/新增成功/退步清单：逐题索引；experiments/outputs/.../tasks/保留完整交互和官方评分。
- validation.json：3496项核验全部通过，覆盖90条新轨迹、实际请求协议及707个既有保护文件未变化。
- baseline_reuse_validation.json / evidence_sha256.json / artifact_sha256.json：基线复用与归档证据。

