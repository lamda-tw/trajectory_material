# 英文 v6 小规模验证

实验已完成。完整结论、版本比较、留出检查和局限见 [REPORT.md](REPORT.md)。

36 条唯一原始轨迹，12 条开发、24 条家族隔离留出；含提示词迭代和重复评分计划 84 次调用，实际 84 次有效、0 次失败。只使用远程 judge，未启动本地 GPU 推理、未修改 LoRA SFT、未进行全量 540 条评分。

最终候选为 [assets/prompt_v6_en_format.txt](assets/prompt_v6_en_format.txt)：保留原英文 v6 判定语义，仅优化短理由输出。P/F/U/N 在 Evaluation Evidence 中解释，实际标签用缩写。不要把格式改善或定向检查匹配率当作整体准确率证明。

授权见 REMOTE_AUTHORIZATION.json，完整性检查见 FINAL_VALIDATION.json，所有尝试含失败响应保存在 runs/。配置和抽样清单中的 prepared/status/planned 字段保留的是各自冻结时信息；实际完成状态以 STATUS.json 和 FINAL_VALIDATION.json 为准。
