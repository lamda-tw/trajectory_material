# 现有 v5 标签选择原始 step：LoRA SFT / DEV57 对照结果

**本轮未观察到 rubric 筛选优于均匀抽样；rubric 组更低。** rubric 与 uniform 的官方 DEV57 成功数相差 **-2 题（-3.51 个百分点）**。这是一个事先冻结选择规则、单训练 seed、同题/同监督 token 预算的对照；不是对所有 rubric 选择方式或 RL 方法的最终判断。整个实验没有调用新的外部 judge，也没有生成、替换训练动作。

**1．主要结果**

| 模型 | 官方成功 | TGC | 平均步数 | 总生成 tokens |
| --- | ---: | ---: | ---: | ---: |
| base | 3/57 | 5.26% | 23.37 | 170,055 |
| uniform | 6/57 | 10.53% | 27.98 | 160,353 |
| rubric | 4/57 | 7.02% | 23.53 | 136,891 |

本次 base 是按同一协议新跑的原始 Qwen3-8B；没有把使用不同 thinking 设置的历史 DEV 成绩混入对照。所有任务各跑一次，使用官方终态测试。train/dev 的任务ID与任务家族前缀均不重叠（30个训练家族、19个DEV家族）。单个任务内部测试通过比例保存在 summary 中，作为描述指标，不把它未经核实地命名为 AppWorld 的正式 SGC 指标。

| 比较（前者相对后者） | 新增成功 | 退化 | TGC 净变化 | 精确 McNemar 双侧 p |
| --- | ---: | ---: | ---: | ---: |
| rubric_vs_uniform | 1 | 3 | -3.51 pp | 0.6250 |
| rubric_vs_base | 2 | 1 | +1.75 pp | 1.0000 |
| uniform_vs_base | 3 | 0 | +5.26 pp | 0.2500 |

rubric vs uniform 按任务家族配对 bootstrap 的 95% 区间为 **[-12.28, +3.51] pp**。McNemar 数字仅作为小样本描述，任务相关性和单个训练 seed 限制推断；bootstrap 也不能弥补没有多 seed 训练的限制。本轮没有根据 DEV 成绩修改阈值、追加训练或挑选 checkpoint。

新增成功题：`6bdbc26_1`。退化题：`4ec8de5_2, b119b1f_1, b119b1f_3`。完整逐题配对见 [task_comparison.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/task_comparison.csv)。

**2．为什么选局部 SFT，怎样决定该不该训**

只有原动作和评价标签时，F 可以帮助排除不合适的模仿目标，却没有提供该状态下正确替代动作。故本轮选择正向局部 SFT，没有构造跨状态 DPO 对，也没有对共享语法、API 名称或整条失败响应施加负向 token loss。另查已有数据可构造67个完全相同初始prompt上的486个候选偏好对，但全部只覆盖第1步，且未验证结果翻转；因此“缺少配对”指缺少覆盖后续状态的配对，而非一个都没有。固定离线数据做 RL 并非理论上不可能，但会额外引入 reward、优势、离线偏移和更新强度等因素，不能干净回答这次的数据选择问题。

判断分两层：共同机械准入 + rubric 组的语义筛选。

| 维度/因素 | 本轮规则 | 原因 |
| --- | --- | --- |
| 实际执行和生成格式 | 两组都要求执行未报错、一个闭合Python块、生成未截断、≤32000上下文 | 均匀基线不故意包含已知运行失败或格式坏样本 |
| R1 | rubric 组要求 P | 有效运行是正向模仿的基础 |
| R2/R3/R4/R5/R6 | rubric 组要求各项为 P 或 N；任一 F/U 不选 | 不让若干 P 抵消业务 F；U 暂不作为正向目标，N 不罚分 |
| R7 | 实际 complete_task 两组均排除；rubric 另要求 R7=N | 已知结束判定噪声大；uniform 不使用语义标签，仍可能抽到未提交却声称完成的文本 |
| R8 | 不作为整项硬门槛，保留诊断；明确多代码块已由共同条件排除 | R8 混合多种协议，未先查文档独自作否决会几乎清空业务写入目标 |
| 官方 train 成败 | 不参与筛选、配额或训练 | 同时利用成功与失败轨迹中的局部行为 |
| 标签权重 | 没有连续权重，只有确定的选/不选 | 此轮不引入任意重要性系数 |

不能简单取“PASS 总数最高”：不同步骤的适用维度数量不同，N 不应被当成差；多个次要 P 也不应抵消错误对象、金额或操作方向。八维全 P/N 的严格交集虽然有1,592步，R5=P却只有4步，说明全维一致并不是一个无代价的过滤条件。

这套规则只定义“当前证据下较适合正向模仿的已有行为”，**没有证明它们最难、最重要，或能因果改变结局**。训练数据中的复杂正确业务步骤依然有限：rubric所选2,440步中，R4=P或R5=P的并集仅87步（约3.6%），其中R5=P仅19步；这是标签定义下的数量，不代表其余步骤全无价值。若不再生成替代动作，能做的是从现有行为中选择、强化和组合，不能凭空得到数据从未包含的解决策略。

**3．数据与预算对齐**

共同候选池5,234步，rubric候选池2,580步，均覆盖90题。按rubric候选的每题response token量分配固定配额；uniform在同题共同池中无放回均匀排列并取样，使用相同每题配额。故这是“同题token配额匹配的uniform”对照。两组监督token严格相同，step数量和输入前缀计算量不强行相等。

| 组 | 涉及step | 监督tokens | 前向input tokens | 训练墙钟 | 峰值allocated显存 |
| --- | ---: | ---: | ---: | --- | ---: |
| uniform | 2,239 | 196,608 | 17,011,194 | 3小时9分13秒 | 37.90 GiB |
| rubric | 2,440 | 196,608 | 14,004,028 | 2小时2分22秒 | 37.91 GiB |

表中前向input tokens按实际backbone输入计算：保存的序列长度减去每个片段末尾仅作目标的1个token；冻结数据清单中的forward_input_tokens字段保留了完整序列长度，二者统计口径在此明确。两组均48次optimizer update，每次4,096监督token；每道题总监督token也相同。为精确对齐配额，最后一个响应只监督必要的原始token前缀；更新边界可将同一响应分为连续loss区间，每个目标token最多监督一次。没有把这种loss mask当成改写后的可执行动作，没有制造EOS，没有删除模型看到的必要历史。

rubric组2,221个目标来自最终失败轨迹，uniform组为2,045个；官方标签只在冻结选择后用于统计。540条均进入筛选检查，最终rubric组的目标来自529条轨迹，uniform组来自517条；不强行为每条轨迹安排一个目标。rubric组有1,463个R6=P，包含反馈利用和恢复；但没有仅凭R6=P纳入R3—R5仍有错误的动作。

所有3,506个不同目标的prompt IDs均按初始消息和此前实际历史重新构造并逐一一致验证；目标IDs与原采样一致，不包含当前/未来执行反馈。掩码CE和LoRA梯度已在小模型上与标准causal LM实现对照通过。两组初始LoRA张量哈希相同，基座参数不训练。

**4．训练和评测配置**

原始Qwen3-8B上新建LoRA，rank16、alpha32、dropout0，q/k/v/o/gate/up/down，43,646,976可训练参数；bf16、SDPA、梯度检查点。AdamW，最高lr5e-5，4次warmup，cosine至5e-6，weight_decay0，梯度裁剪1。仅原始当前assistant响应计算交叉熵，历史和工具观察不监督；没有reward加权、KL或负向loss。

DEV57：temperature0、seed100、enable_thinking=false、50步、32000窗口、单步3000生成token，三组使用相同提示、解析器、环境、官方测试和3个隔离worker。预算耗尽、代码错误、无代码终止均照实保留，基础设施错误不作为业务失败填零。没有使用DEV的rubric评价挑结果。

![训练损失](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/training_loss.png)

两条曲线来自不同目标数据；loss大小不能直接当作谁的能力更强，DEV官方成功率才是本次主要结果。监督token预算相同也不等于GPU计算量相同，均匀组的历史前缀更长；实际用时单独报告。

机械行为诊断如下；“重复代码”仅表示本轨迹曾执行过相同文本，不能自动判为无效，刷新状态也可能合理。

| 模型 | 执行异常步 / 总步数 | 异常比例 | 多非空Python块步骤 | 曾执行过的相同代码 |
| --- | ---: | ---: | ---: | ---: |
| base | 641 / 1332 | 48.12% | 168 | 673 |
| rubric | 595 / 1341 | 44.37% | 49 | 686 |
| uniform | 557 / 1595 | 34.92% | 46 | 928 |

各组DEV57用时如下，包含该组评测服务启动及全部57题；训练用时已在前表独立记录。两条GPU执行通道并行，不能把各阶段用时直接相加当作总墙钟。完整时间戳见 [TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/TIMING.json)。

| DEV57组 | 评测墙钟 |
| --- | --- |
| base | 0小时20分11秒 |
| uniform | 0小时34分12秒 |
| rubric | 0小时28分24秒 |

详细异常类型与终止原因见 [mechanical_dev_behaviors.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/mechanical_dev_behaviors.json)。这些是解释性指标，没有调用新的rubric judge。

差异案例复核见 [CASE_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/CASE_REVIEW.md)。rubric在`6bdbc26_1`中最终提取并提交艺人关注数，uniform反复查文档直到上下文耗尽；但在`b119b1f_3`中，uniform完成逐首切歌，rubric只读取歌单后报告失败。`b119b1f_1`显示即使调用同一API，`song_id`与`queue_position`也对应不同队列状态变化。不能把“读取成功”或“最终不再报错”当成业务推进。

还有一个需要保留的反例：uniform在`4ec8de5_2`官方通过，但代码用日期接口不存在的`year`字段与歌单中不存在的`release_year`字段作比较，过程并未可靠实现“今年”的筛选。其官方成功仍计入主要结果，不事后改分；同时不能把该轨迹当作流程完全正确的证据。rubric在同题也将日期中的18误当年份。官方终态正确和局部过程正确需要分别评价。

**5．与 CSO、DRACO 的关系**

[CSO](https://arxiv.org/html/2602.03412v1#S3.SS2) 的专家替代动作、学生续跑验证与局部DPO需要额外动作来源；按用户要求，本轮只借鉴局部选择粒度，不采用该数据构造方式。[DRACO](https://arxiv.org/html/2609.04094v1#S3.SS3) 用步骤质量重新分配轨迹优势，其正负方向仍来自轨迹相对优势；这不是直接按八维PASS数给SFT目标设重要性。本轮仍使用标准token平均CE，所以较长目标自然包含更多监督token，不声称每步梯度等权。当前方案是可解释的教师评价辅助自模仿实验，不声称复现两篇论文或已提出新的完整方法。

**6．新版 prompt**

之前540条实验没有改写v5，报告仅列出改进建议。本轮另存了 [prompt_v6.txt](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/prompt_v6.txt)：在原rubric模块内收紧R2当前子目标、R5修改前拒绝、R6恢复与业务错误、R7未解除未知及规定交付、R8额外代码块。输出结构和短理由不变，无新模式或权重。

v6尚未做新的外部模型评分实测，不能声称更准。当前540条和本轮训练均保持v5，不用v6改写已有标签。新版本和schema/validator可供后续新数据调用。

**7．证据范围与后续**

本次结果首先说明的是“该固定筛选规则在这个预算下”的效果，不能替代多seed确认，也不能推导所有rubric选择一定优于均匀抽样。筛选同时改变了步骤深度、历史长度和动作类型，因此它检验的是整套选择规则，不能把差异单独归因于某一个rubric维度。本轮没有观察到改善，应优先检查复杂正确业务动作的覆盖，以及局部读取/修复能否组合成业务推进。全局排除含complete_task的代码块也会丢掉与结束调用写在同一块中的计算或操作；这项共同限制缩小了实验结论的适用范围。没有采用多seed，本轮差异可能包含训练随机性，不能按这57题反复调门槛。

现有logprob显示所选目标在原策略下的token平均NLL：rubric为0.128786、uniform为0.097626；更高置信不等于更正确。数据内候选同状态DPO对全部位于第1步，可另做首步偏好实验，但不能冒充覆盖全轨迹的CSO。详情见analysis/STRATEGY_SUPPLEMENT.md。

本轮最直接的认识是：**质量准入不等于学习价值，训练不优也不直接证明v5判错。** 不建议直接把当前硬筛选当成默认数据管线，也不应靠随意放大R4或R5权重解释失败。下一轮优先保留相同质量条件，事前规定文档/认证、局部读取、业务决策/操作、反馈恢复的类型配额，再让uniform在相同类型与任务配额下抽样，以区分语义筛选与类型分布的影响。随后才考虑根据当前checkpoint对**已准入目标**的NLL识别仍未掌握的行为。目前可确认的业务正例稀少，既可能来自原策略能力不足，也可能来自U门槛和混合代码块过滤，尚不能把两者分开。若某类不足，就报告缺口、缩小共同预算，不复制样本来伪装新增证据。NLL高不自动证明动作正确；这些都应另立对照，不能事后改本轮门槛。任何下一轮都继续遵守不由Codex替换动作的约束。

| 产物 | 位置 |
| --- | --- |
| 事前策略 | [PLAN.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/PLAN.md) |
| 冻结执行/数据清单 | [EXECUTION_MANIFEST.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/EXECUTION_MANIFEST.json) / [DATA_MANIFEST.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/data/DATA_MANIFEST.json) |
| 数据与loss对齐验证 | [VALIDATION.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/data/VALIDATION.json) |
| rubric LoRA | [adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/training/rubric/adapter) |
| uniform LoRA | [adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/training/uniform/adapter) |
| 完整量化结果 | [summary.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/summary.json) |
| 逐题比较 | [task_comparison.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/task_comparison.csv) |

训练原始日志、逐更新可恢复状态及每题完整DEV轨迹均保留。原始v5评分与历史实验未修改。
