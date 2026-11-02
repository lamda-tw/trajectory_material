# B 阶段单 SDPO 对照报告

更新时间：2026-10-25T15:02:24.155886+08:00。状态：两轮训练与两次 dev57 已完成。
已提交 36/36 批，实际更新 36 次。SFT 步数、loss、梯度必须始终为 0。

## 与原混合实验的比较

| 轮次 | 原 SFT+SDPO 成功题数 | 单 SDPO 成功题数 | 单 SDPO 平均测试通过率 |
|---|---:|---:|---:|
| 1 | 5/57 | 2/57 | 31.42% |
| 2 | 1/57 | 0/57 | 24.80% |

## 重复查询行为

以下两组都用同一个静态代码统计函数：纯文档步指代码中的所有 apis 调用均为 api_docs；重复代码指同轨迹此前已有相同 AST 的代码。不是完整 rubric 判定或成功业务调用计数。未完成轮次的比例不能直接当作整轮对照。

| 分支 | 轮次 | 总步骤 | 纯文档步骤 | 重复代码 | 重复的纯文档代码 |
|---|---:|---:|---:|---:|---:|
| mixed | 1 | 2048 | 19.78% | 40.48% | 9.23% |
| mixed | 2 | 3166 | 53.41% | 77.54% | 42.51% |
| sdpo | 1 | 2031 | 20.97% | 48.35% | 10.73% |
| sdpo | 2 | 2683 | 69.21% | 87.36% | 61.98% |

## 技术验收

首批 SDPO loss=0.43179612；SFT loss=0.0；SDPO 梯度 norm=0.49952134；SFT 梯度 norm=0.0。
首批训练峰值 allocated/reserved 显存 23.34/29.56 GiB。首批与原混合实验的 SDPO loss/梯度在匹配容差内方可继续。
当前监督 SDPO 步数 4122；mask 步数 592。数值正常不等于任务效果改善。

## 固定实验设置与结论边界

从原 B 相同 Qwen3-8B 与 LoRA 初始化开始；首批复用原初始模型的相同 5 条轨迹和原 Codex 反馈，第二批起用新学生独立在线采样。每批 5 题、每题 1 条、两轮 train90，共 36 个更新机会。
唯一训练干预：原 ZeroFail3 SFT 步骤改为 mask；所有 FAIL 的原准入规则、C2 prompt、原回答前缀、reverse-KL top100+tail、SDPO 权重与归一化保持不变。mask 步骤仍保留在后续上下文。
LoRA r=8/alpha=16；AdamW lr=5e-5、前5次非空更新 warmup；EMA=0.95；clip norm=1；仅 GPU1。首批缓存使第一次更新的监督输入精确匹配。
每轮 batch18/36 用无反馈学生评估同一 dev57，temperature=0、seed=100，不根据 dev 结果调参。
该在线对照检验加入/去掉 SFT 后整个学习过程的区别；第二批起轨迹自然分化，不能视为固定同一数据上两种 loss 的纯梯度因果比较。单种子，Codex 评分存在变异。较好结果不证明 SDPO 每条目标正确，较差结果也不能单独证明 SFT 有害。
状态：[STATUS.json](STATUS.json)；首批：[first_batch_acceptance.json](analysis/first_batch_acceptance.json)；逐批：[training_metrics.csv](analysis/training_metrics.csv)；后台：[supervisor.log](runs/sdpo/supervisor.log)。
