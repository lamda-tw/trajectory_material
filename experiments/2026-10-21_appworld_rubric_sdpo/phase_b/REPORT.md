# B 阶段报告：ZeroFail3 SFT ＋ C2 反馈条件 SDPO

生成时间：2026-10-23T23:48:28.362431+08:00。状态：两轮训练与两次 dev57 评估全部完成。

已完成 36/36 个 batch、36 次实际更新、180/180 条训练轨迹。默认 C2 教师；仅运行 mixed，未运行 SFT 对照。

## dev57 官方评估

每轮结束后使用该轮学生 adapter，完整运行相同的 57 道 dev 题。学生不带反馈；temperature=0、seed=100、最多 50 步，AppWorld 官方评价保留本地。两个 checkpoint 均预先指定，不根据 dev 结果选择或更改训练参数。

| 轮次 / checkpoint | 整题成功数 | TGC | 每题测试通过率的平均值 | 平均步骤 |
|---|---:|---:|---:|---:|
| 第 1 轮 / batch 18 | 5/57 | 8.77% | 41.28% | 26.86 |
| 第 2 轮 / batch 36 | 1/57 | 1.75% | 26.38% | 38.30 |

第 2 轮相对第 1 轮 TGC 变化 **-7.02 个百分点**；新增成功 0 题，退步 4 题。
新增成功 task ID：无。
退步 task ID：6c2c621_1, 6c2c621_2, b119b1f_2, d4e9306_2。
完整逐题配对结果见 [dev57_paired_results.csv](analysis/dev57_paired_results.csv)。

## 首批验收与训练稳定性

首批 5 题共 68 步：SFT 20、SDPO 48。SFT loss=0.127830，SDPO loss=0.431796，总 loss=0.559627。
首批两分支梯度范数 0.260103/0.499550，总梯度 0.568567，参数变化范数 0.033269，教师无梯度。
已完成批次中，最大训练 allocated/reserved 显存分别为 37.78/92.47 GiB；2/36 批触发 norm=1 裁剪。这些显存值不包含 vLLM 预留的 KV cache。
SFT loss 范围 0.065793–0.201350；SDPO loss 范围 0.017315–0.560213。不同批次为不同在线轨迹，loss 变化不能单独作为效果提升证据。
逐批 loss、梯度、裁剪、显存及样本数见 [training_metrics.csv](analysis/training_metrics.csv)；首批检查见 [first_batch_acceptance.json](analysis/first_batch_acceptance.json)。

## 训练数据与反馈利用

已提交轨迹共 5214 步，SFT 912、SDPO 4300、mask 2；监督回答 token 共 487092。
屏蔽原因：{'zero_fail_P_below_3': 2}。无 FAIL 步骤按 PASS 数量分布：{'2': 2, '3': 496, '4': 180, '5': 222, '6': 12, '7': 2}。
选中步骤含 U 的数量为 166；SDPO 反馈引用后来证据的步骤为 43/4300。评分调用共 184 次，其中格式修复 1 次；有效评分缓存复用，不因结果差重新抽样。

## 方法与配置

每批 5 道 train90 题、每题采 1 条完整轨迹；整批政策固定。轨迹结束后统一使用冻结 v7-feedback prompt，为每步打分并为全部 FAIL 步骤产生反馈。F=0 且 P≥3 做原回答 SFT；含 F 且反馈可用的步骤做 C2 条件自蒸馏；其他步骤保留历史、屏蔽当前回答 loss。
C2 教师输入为原动作前历史＋FAIL 规则＋具体诊断与修正建议，不额外引用完整原回答。教师是 Qwen3-8B 的 EMA LoRA；Codex 提供反馈。学生与教师在相同原回答前缀上比较分布。
`L = mean_steps(mean_tokens(SFT CE)) + 1.0 × mean_steps(mean_tokens(KL_bucket(student || stopgrad(C2 teacher))))`。top-100＋tail 桶，两项独立归一化；整批梯度累计后只更新一次。
Qwen3-8B 冻结底座；LoRA r=8/alpha=16/dropout=0；AdamW lr=5e-5，前 5 次非空更新线性 warmup（首次 1e-5）；EMA=0.95；gradient norm clip=1；bf16＋fp32 概率计算；物理 GPU1。学生/教师上下文限制为 32000/32768；超限不截断，按规则屏蔽。
配置、题目顺序和版本摘要见 [config](config/run.json)、[schedule](config/schedule.json)、[版本摘要](config/preparation_manifest.json)。

## 结论边界

首批数值验收证明训练管线可运行、两分支提供有限且非零的梯度，不等于证明反馈提高了任务完成率。两轮 dev57 可以比较这两个 checkpoint；本轮没有匹配的底座 dev57 和在线 SFT 对照，因此不能将其差异直接归因于 SDPO，也不能声称相对基线提升。
A 阶段已经验证的局部反馈纠错收益与这里的完整任务指标分开报告。C2 在原错误回答前缀上的教师分布可能保留错误倾向，该限制不会因为训练无 NaN 而自动消失。dev57 不是新的未见测试集。

运行状态见 [STATUS.json](STATUS.json)，后台日志见 [supervisor.log](runs/mixed/supervisor.log)。
