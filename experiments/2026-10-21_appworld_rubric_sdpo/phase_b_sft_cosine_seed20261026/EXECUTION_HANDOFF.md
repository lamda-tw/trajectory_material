# 余弦学习率三轮实验交接

这是用户明确授权的 GPU1 长时间无人值守任务。用户要求相同 seed、从头开始三轮、只有学习率改变，尽量少保存模型，自行处理困难和错误。不得退回此前“旧第二轮追加18批”的建议；本次必须从 base 训练54批，并在18/36/54后各评dev57。没有15小时时间限制，不额外加第四轮。

目录为当前 phase_b_sft_cosine_seed20261026。对照是 phase_b_sft_seed20261026，而不是更早的 seed20261022。训练seed20261026、dev seed100/temperature0、任务顺序与派生采样seed保持一致；不导入旧LoRA/Adam、轨迹或Codex评分。

学习率唯一训练变化：前5次有效更新线性warmup到5e-5，其后基于已提交的optimizer_updates使用余弦降至第54次5e-6。公式在scripts/b_learning_rate.py，纯函数无进程内scheduler状态；空batch不推进。b_loss.py的所有loss函数AST与基线一致，b_train_batch.py、b_dataset.py、b_run.py、b_judge.py、b_rollout_worker.py均与基线字节相同。没有新的SDPO训练。

先验证首批loss/梯度/显存/基础模型来源，之后监督程序自动进行其余批次。每批都断言学习率符合计划和Adam更新计数连续。逐批COMPLETE.json原子提交并有哈希校验，采样/评分/训练缓存可复用，禁止重复更新或静默替换任务。

监督进程见runs/sft/launch.json；锁为supervisor.lock/runner.lock，GPU1还有共享锁。运行正常时不得重复启动。若需恢复，只启动此目录的b_supervise.py --execute；它会识别已提交批次、恢复Adam/RNG与学习率进度。已删除权重的历史批次通过RETENTION.json验明；已完成评估无需重跑。

评分沿用修复后的网络恢复：优先读取并校验有效回复，超时终止自己进程组，已识别的网络故障冷却5/10/15分钟后重试。保留所有attempt；协议/鉴权/额度/确定性或数值错误不假装成功，不擅自改rubric、学习率或采样配置。若出现故障，自行查看已有证据，修复基础设施后继续；算法变化仍须有用户指令。

保存策略：只保留当前最新完整检查点及已评估最优轮次，先比较successes再比较Macro，同分保留较早轮次。首批不永久保留，但保留验收、哈希、轨迹/评分/指标。最后仍保留最新模型以及最优模型（可能同一份）。不删除旧实验任何文件。下一批提交前上一批完整Adam仍存在；新提交并通过验收后才回收旧权重。

当前脚本/配置/测试已在preparation_manifest.json冻结，修改任何冻结代码前保留审计，修改后明确核对唯一训练因素。新配置与原配置的差异只有experiment/输出路径和training.lr_schedule；模型保留与报告属于管理性改动。

监控：PROGRESS.md约30秒刷新中文进度，STATUS.json为阶段信息，heartbeat.json记录进程、GPU和空间；AutoPanel run为appworld-rubric-ZeroFail3-SFT-cosine-seed20261026，CPU导出器每30秒采已提交指标。全局TensorBoard不能停止或重复创建。

自动报告REPORT.md对比同seed恒定和余弦三轮成功、Macro、重复文档、业务动作、无代码终止与固定案例。仅loss下降不能说明有效，重复占比下降也可能来自更早无代码终止。训练和评估均全部完成后程序停止，最终进行数据解释。
