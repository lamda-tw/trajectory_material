# 五轮纯 SFT 续训恢复记录

启动时间：2026-10-26T10:04:23.188273+08:00。GPU1，supervisor PID 840131。新数据保存在本目录；前两轮保存在 ../phase_b_sft_only，不复制底座模型。

先读 STATUS.json、runs/sft/heartbeat.json、runs/sft/supervisor.log 及 monitoring/status.json。完整状态从原 batch036/state.pt 恢复，首批续训验收位于 analysis/first_batch_acceptance.json；该文件出现 passed=true 后才清理原SFT的非关键模型。

范围：batch037–090；batch054/072/090 自动评估 dev57；每轮结束和每批训练后更新 REPORT.md 及根目录 THREE_ARM_COMPARISON_REPORT.md。原两轮对比快照为 analysis/two_epoch_comparison_snapshot.md。

原SFT保留001/018/036完整模型，续训保留054/072/090和最近两批完整模型。只删除 policy 允许的 state.pt 与 adapter_model.safetensors；RETENTION.json 记录删除前哈希与大小。所有原始轨迹、评分、dataset 和 metrics 保留。不得将已清理的中间点作为续训来源。

监控曲线：autopanel/TensorBoard 的 `appworld-rubric-ZeroFail3-SFT-5epochs`；前36批已通过HTTP读取确认。导出器约每30秒检查已提交 metrics；采样和Codex评分期间没有新loss点属于正常情况。日志导出只使用CPU。

恢复supervisor前先确认旧supervisor/runner和所拥有的推理server是否仍在，禁止重复启动或抢占其他GPU进程。正常入口是 .conda-training/bin/python 本目录/scripts/b_supervise.py --execute；完成标记和锁使已完成batch不会重新训练。先排查明确错误再恢复，不能为了绕过失败改变选样、损失、lr、prompt或正式评分。

原训练模板 teacher_condition=C2 仍保留，但纯SFT不调用教师前向、不计算SDPO。LoRA r8、alpha16、dropout0；底座冻结；lr5e-5；恢复optimizer update=36，不重新warmup。第五轮完成后停止。
