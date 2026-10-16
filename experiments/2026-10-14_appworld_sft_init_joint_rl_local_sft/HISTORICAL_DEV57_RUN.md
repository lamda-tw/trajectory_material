# 同历史基线协议的 step 0、1、5、10、15 评测

**五点均已完成**：step 0: TGC 25/57、SGC 4/19；step 1: TGC 18/57、SGC 3/19；step 5: TGC 18/57、SGC 2/19；step 10: TGC 20/57、SGC 3/19；step 15: TGC 23/57、SGC 3/19。详见 [对照报告](evaluation/historical_protocol_trend/COMPARISON.md)。

2026-10-16（北京时间），用户授权执行。已于10:00启动，全部结果放在本实验的 `evaluation/historical_protocol_trend/` 内，仅使用物理 GPU1。按 step 0→1→5→10→15 串行评测，每个模型完成完整 DEV57，共285次任务运行。

## 结果与进度

- [实时进度与五点指标表](evaluation/historical_protocol_trend/RESULTS.md)
- [机器可读实时状态](evaluation/historical_protocol_trend/STATUS.json)
- [总日志](logs/historical_dev57_trend.log)
- [输入、脚本、模型权重及环境代码哈希](evaluation/historical_protocol_trend/INPUT_MANIFEST.json)
- [step 0历史复现检查](evaluation/historical_protocol_trend/BASELINE_REPRODUCTION.json)（step 0完成后生成）

各点的 `step_00000/`、`step_00001/`、`step_00005/`、`step_00010/`、`step_00015/` 内分别保存原始 AppWorld 输出、`logs/run.log`、`task_status.jsonl`、`task_results.csv`、`SUMMARY.json`。目录名中的 step 是本轮已完成的优化器更新次数。

最终对比报告另包含57题逐题通过数、19场景和难度分组、每条evaluator条件及完整失败trace、相对step 0的条件得失。每个模型通常对应291条测试条件，最终以官方原始记录核算。检查点累计固定SFT步骤消耗为0、175、875、1750、2623，见 [检查点上下文](evaluation/historical_protocol_trend/TRAINING_CHECKPOINTS.json)。

## 固定评测协议

基线来源：`2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57`。逐字节复用其 Python launcher `appworld_run_isolated_lora_config.py` 和 `dev.jsonnet`；原 shell 作为来源快照保存，不执行其中写死的GPU0绑定及宽泛的pkill。

- 使用原始 AppWorld `simplified_react_code_agent` 和 Chat Completions；保留历史提示中的空白、历史拼接、代码提取、结束条件和上下文错误处理。
- `qwen3-8b-with-reasoning`配置，`reasoning_parser=none`，保留历史对 `reasoning_content=null` 的空字符串兼容；不额外设置 `enable_thinking=False`。
- temperature=0；每次请求seed=100；每题最多50步；每次请求max_completion_tokens=3000；上下文32000。 原始usage tracker的每题输出预算100000 token、AppWorld random_seed=100及raise_on_extra_parameters=true也保持不变。
- 单任务串行，AppWorld `num_processes=1`；vLLM `max_num_seqs=3`。沿用历史默认generation config、编译/CUDA graph和工具解析参数；不使用之前新采集器的eager/并发6设置。
- 使用同一基座、tokenizer、提示、DEV57数据、官方测试和当前同一组Python环境。软件版本清单与关键代码哈希保存，五个点之间检查一致。
- 五个推理adapter目录使用同一套基线tokenizer及adapter配置文件，仅权重链接不同。各checkpoint的配置与基线仅target_modules列表顺序不同，已验证语义相同；原checkpoint不修改。
- 唯一硬件位置变化是历史GPU0→本次GPU1；两张卡历史日志均记录为RTX PRO 6000 Blackwell Server Edition。通过GPU1 UUID固定设备，复用NVML UUID索引兼容补丁，不影响采样设置。输出、缓存路径隔离；只清理本次拥有的进程。

## 校验和判定

1. 先校验原始模型及四个checkpoint的权重哈希、更新次数、LoRA配置；冻结输入清单。
2. 每个任务首次请求后，将完整初始messages对象（包含空白及元数据）和采样参数与历史同题日志逐项比较。配置自动生成后也必须与历史文件逐字节一致。
3. step 0完成后比较历史逐题成功标志、完整官方评分记录、TGC及SGC；如不一致，记录差异并排查协议。用户随后明确接受同模型结果波动，因此在协议检查通过后，以本次step 0作为对照继续后续四点；不强行声称复现23/57。原协调器的结果一致性门槛由单独续跑器处理，冻结的评测代码和设置不变。
4. 对每个点核对57题覆盖、19组×3题、原始官方结果与逐题状态一致，计算TGC与SGC。任务失败照实保留，不进行成功样本筛选。
5. 全部完成后复核代码/输入未变化，保存完成记录、五点趋势和逐题对照；不启动新的训练。

先前 `evaluation/round_01_final/` 的20/57使用另一入口，保留为历史记录，不混入本次五点趋势曲线。

本次启动命令：

```bash
/root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/gpu1_run.py -- /root/autodl-tmp/workspace-tw/.conda-training/bin/python -u /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/evaluate_historical_trend.py --execute
```

运行期间不要重复启动。统一进度查看器为 `scripts/show_progress.py --watch 5`。
