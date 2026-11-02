# ZeroFail3 SFT：从第二轮继续到第五轮

本次按用户授权使用 GPU1，继承 `../phase_b_sft_only/runs/sft/batch_036/checkpoint/state.pt` 的完整状态。仅扩展训练日程和增加恢复核验、存储管理、面板与报告；损失、选样、prompt、LoRA、学习率等保持一致。

- [五轮实时报告](REPORT.md)
- [执行状态](STATUS.json)
- [续训授权与来源](config/continuation.json)
- [存储策略](config/retention.json)
- [TensorBoard 导出状态](monitoring/status.json)
- [首批恢复验收](analysis/first_batch_acceptance.json)

autopanel/TensorBoard 中选择 `appworld-rubric-ZeroFail3-SFT-5epochs`。主要指标：`loss/sft`、`grad/sft_norm`、`optimizer/learning_rate`、`optimizer/updates`、`eval/dev57_tgc`、`behavior/repeated_docs_fraction`。曲线补齐前36批，续接第37–90批；每个batch提交后更新。

自动运行入口：`.conda-training/bin/python scripts/b_supervise.py --execute`。中断后可使用同一入口恢复，已完成轨迹、评分和checkpoint不重复生成；不能重新运行原两轮supervisor作为此次恢复入口，因为旧中间模型可能已按授权清理。不要同时启动两个supervisor。

只清理明确列出的中间模型blob，保留原始证据和每轮末模型，清理凭证为各checkpoint的 `RETENTION.json`。第37批验收通过后才清理原SFT中间模型；第3、4、5轮评估后自动更新五轮报告和根目录对比报告。完成第5轮后停止，不启动额外训练。
