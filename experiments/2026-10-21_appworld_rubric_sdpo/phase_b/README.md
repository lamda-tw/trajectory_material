# 阶段 B：在线 ZeroFail3 SFT ＋ C2 条件自蒸馏

2026-10-24：两轮训练与两次 dev57 已完成，详见 [最终运行报告](REPORT.md)。第二轮出现严重文档查询循环，事后全量统计、具体退化案例与下一步建议见 [失败诊断](DIAGNOSIS.md)。本次诊断未启动新训练。

2026-10-22 22:22（北京时间）：**已按用户授权启动 GPU1 的 C2 混合分支。** 首批于 22:35 通过验收，已自动继续 2 轮、36 个更新机会。用户随后追加授权：**第 1 轮（batch 18）和第 2 轮（batch 36）各做一次 dev57 官方评估，最后生成 B 阶段报告**。SFT 对照及 C 阶段未启动。实时进度见 [STATUS.json](STATUS.json)、[心跳与显存](runs/mixed/heartbeat.json)、[监督日志](runs/mixed/supervisor.log)，报告持续更新至 [REPORT.md](REPORT.md)。

用户选择以局部 step 改善为当前目标运行 B，并用两次 dev57 衡量完整任务效果。A 的多步效果与错误前缀分布限制保留为研究边界。授权见 [训练启动](config/start_authorization.json) 和 [两轮评估及报告追加授权](config/epoch_evaluation_authorization.json)。追加评估没有修改已经开始的训练配置；是否自动评估由执行开关中的 `automatic_epoch_evaluation` 与 `evaluation_batches` 控制，覆盖准备期 `run.json` 中关闭最终自动评估的默认值。

**实际流程**

1. 同一 Qwen3-8B 底座、新 LoRA，不加载历史 SFT adapter。默认 `mixed`，在线 `sft` 对照有独立入口，不自动把两个分支都跑一遍。
2. 每批5道不同题，每题当前学生采1条完整轨迹；最多3条并发，整批学生参数固定。每条最多50步，实际由完成、无代码、上下文上限决定，不预设固定step数。
3. 轨迹全部结束后，每条一次正常 Codex 请求，给所有实际step打R1–R8标签，并为全部F步骤提供反馈。正常每批5个请求，不是每个FAIL一个请求；仅有限的传输重试和格式修复另计。动作循环中不调用Codex。
4. 精确重建动作前历史并核对采样prompt token IDs，再按下表分流。
5. 每个选中step作为microbatch累计梯度，整批选中步骤算完后只做一次optimizer.step，再更新一次教师LoRA EMA；下一批用新学生重新采样。

| step标签/反馈 | mixed | sft对照 |
|---|---|---|
| F=0，P≥3 | 原回答SFT | 相同SFT |
| F≥1，反馈可用且预算允许 | C2自蒸馏 | mask |
| F=0，P<3 | mask，保留上下文 | 同左 |
| F≥1，但反馈不可用、过长或教师超限 | mask并记录原因 | mask |

ZeroFail3不额外要求U=0，保持原冻结计划；记录U率。PASS再多，只要有F就不能进入正向SFT。mask不等于删除后续历史中的步骤。

**默认教师就是A的C2**

学生看原始动作前历史h；教师看h＋FAIL规则及名称＋Diagnosis/Correction。复用A的精确C2消息，不额外完整引用原回答，不给F=0步骤附中性诊断。两者在相同原学生回答前缀a_<j上计算分布；不重复完整原回答，不等于teacher-forcing时没有原回答前缀。

教师不是Codex本身，也不是A阶段训练出的checkpoint。Codex提供文本反馈，Qwen3-8B的冻结教师adapter提供分布。教师初始化完整复制学生LoRA，后续更新LoRA参数EMA。允许反馈使用完整轨迹的后来证据，记录uses_later_evidence；学生不看这些额外证据。

现有v7-feedback模板已规定：省略feedback_step_ids时反馈覆盖所有F步骤。B没有修改rubric或重写feedback prompt，只省略A的目标步骤筛选字段。

**损失与初始配置**

```text
G = {F=0 and P>=3}
D = {F>=1 and feedback usable and teacher input fits}
L_SFT = mean_G mean_response_tokens [-log p_student(original_token)]
L_SD  = mean_D mean_response_tokens [KL_bucket(p_student || stopgrad(q_teacher,C2))]
L     = L_SFT + lambda * L_SD
```

每步先按回答token平均，再分别按G/D步数平均。不是用全部步骤数统一相除，也不是让FAIL数量自然放大蒸馏权重。只监督当前assistant回答，task/history/observation/反馈不作为输出标签。一项为空则该项为0；两项均空则跳过optimizer、EMA及warmup计数，记录空更新机会。

KL用学生选择的同一组top-100 token IDs加一个tail桶，教师无梯度。B以logsumexp计算剩余词表的tail概率质量，避免A诊断中1−mass的极小尾部消减误差。分桶KL仍非全词表精确KL，不对top-k单独重归一化。

| 项目 | 初始配置 |
|---|---|
| GPU | 只允许物理GPU1，UUID固定；共享互斥锁，忙时不抢占 |
| 底座 | /root/autodl-tmp/models/Qwen3-8B，冻结 |
| LoRA | r=8，alpha=16，dropout=0，q/k/v/o/gate/up/down |
| 优化器 | AdamW，betas=(0.9,0.999)，eps=1e−8，weight_decay=0 |
| 学习率 | 5e−5；前5次非空更新线性warmup，之后恒定；首次1e−5 |
| 蒸馏权重λ | 1.0，两项独立归一化后的权重 |
| 教师EMA | 0.95旧教师＋0.05更新后学生，仅LoRA参数 |
| 梯度裁剪 | 全局norm=1.0 |
| 数值/显存 | bf16底座、fp32概率和EMA；gradient checkpointing；LM head每128token分块 |
| 上下文 | 学生最多32000，教师训练最多32768；不截历史，超限mask该步 |
| 采样 | temperature=1，top_p=1，top_k=−1，thinking关闭，每动作最多3000token |
| 种子 | 20261022；分支匹配初始化、题目顺序和采样seed规则 |
| 预算 | 每分支2轮train90，180条轨迹，36次更新机会 |

教师32768低于本地模型配置40960，为C2消息留出768token空间；比旧计划40960候选值更保守，实际显存待GPU验证。以上是工程起点，A没有验证其最优性。逐批记录两项loss、SFT梯度norm、加权SDPO梯度norm、方向余弦、裁剪、G/D/mask数量及原因。非有限loss/梯度、摘要不一致时停止，不自动改λ、截历史或丢弃长样本。

**CPU验证与运行边界**

- 14项合成数值/微型随机模型测试：KL数值与梯度、全词表形式、自身零KL、极小tail、teacher stop-gradient、分支归一化/梯度累计、分流边界、warmup/EMA、格式修复保留标签、PEFT双adapter的response对齐和梯度、仅导出学生adapter、GPU环境隔离恢复。没有加载Qwen3-8B，没有执行optimizer.step。
- A的100个缓存FAIL状态，C2输入逐token完全一致。
- 三条历史完整轨迹共150步，学生历史token全部一致，目标教师C2一致。缺少非目标反馈的位置仅在CPU夹具中标记不可用，没有伪造Codex反馈或写入训练数据；夹具mask比例不是B真实比例。
- 不完整的all-step反馈会被拒绝，SFT对照不会接收FAIL步骤。
- 关闭的gate会在采集、评分或训练开始前拒绝执行；尚无B运行目录。

启动前新增首批验收及其测试，合计 16 项 CPU 测试通过。真实 Qwen3-8B 显存、全轨迹评分、反向传播及更新由首批检验；结果写入 `analysis/first_batch_acceptance.json` 后才继续下一批。A 的错误前缀反向信号仍是研究风险，不能声称已由技术验收解决。

**启动与恢复入口**

当前只授权 mixed。监督进程使用下列入口，持有单实例锁；已有提交 checkpoint、完整轨迹及有效评分均按摘要恢复。勿在监督进程存活时重复启动。

```bash
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_supervise.py --execute
```

监督器每 30 秒记录 GPU1 显存和磁盘余量；首批必须覆盖 SFT/SDPO 且各自梯度非零，损失/梯度有限、裁剪正常、学生参数实际变化、教师无梯度。每批继续验证 checkpoint。GPU1 被占用时等待，不抢占；可识别的临时基础设施错误有限重试，确定性错误保留现场。磁盘少于 8 GiB 时停止，不删除历史数据。

底层手动恢复入口如下；SFT 对照未授权。两次评估由监督器按顺序运行，占用同一 GPU1，与训练互斥。

```bash
# 混合分支：同次授权内先检查首批，再按缓存继续，不需要每批重复确认。
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_run.py --arm mixed --until-batch 1 --execute
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_run.py --arm mixed --until-batch 36 --execute

# 独立在线SFT对照，不被上面命令自动启动。
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_run.py --arm sft --until-batch 36 --execute

# 每轮预先指定checkpoint的dev57评估，学生不带反馈。
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_evaluate.py --arm mixed --batch 18
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/b_evaluate.py --arm mixed --batch 36
```

评分期间vLLM退出并释放GPU1。更新时同底座两个adapter，完成后退出。每批保存学生adapter、教师EMA、优化器、计数、RNG；已完成轨迹、评分和提交checkpoint按摘要复用，不因效果差重抽。未提交的训练失败使用前一checkpoint和原已保存数据批恢复。分支目录隔离。

每次评估均完整运行同一组 57 题，temperature=0、seed=100、最多 50 步，无教师反馈，不调用 Codex 评分。官方整题成功率、测试通过率和逐题结果分别存于 `runs/mixed/epoch_01_dev57`、`epoch_02_dev57`。评估后原 checkpoint 继续训练，不根据 dev 结果挑选 checkpoint 或改超参数。dev57 不是新未见测试集；没有本轮匹配的底座/SFT 对照，不能从两轮比较单独推导 SDPO 的因果增益。

`scripts/b_report.py` 每批及每次评估后刷新 `REPORT.md`、`analysis/b_report.json`、`analysis/training_metrics.csv`，两轮评估完成后写入 `analysis/dev57_paired_results.csv`。只有 36 批及两次 57 题评估全部完成，报告才标记完成。首批 SFT/SDPO loss 为 0.127830/0.431796，总梯度 norm 为 0.568567，训练峰值 allocated/reserved 显存为 23.34/29.71 GiB，首次更新及 EMA checkpoint 审计通过。

**文件入口**

- [运行配置](config/run.json)、[执行开关](config/execution_gate.json)、[固定批次](config/schedule.json)、[版本摘要](config/preparation_manifest.json)
- [CPU预检](analysis/preflight.json)、[数值测试](analysis/cpu_numerical_tests.log)
- [运行器](../scripts/b_run.py)、[数据分流](../scripts/b_dataset.py)、[整轨迹评分](../scripts/b_judge.py)
- [损失](../scripts/b_loss.py)、[更新与EMA](../scripts/b_train_batch.py)、[最终评估](../scripts/b_evaluate.py)
