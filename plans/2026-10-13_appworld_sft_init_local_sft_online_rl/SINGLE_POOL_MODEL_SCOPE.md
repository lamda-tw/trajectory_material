# 当前执行范围：完成已有单轮，保存模型后结束

2026-10-15，北京时间。用户最新指令：“本次试跑，是否会保存最终更新的第一轮模型，如果会的话可以跑一遍，得到最终模型后结束”。本指令覆盖此前“整池试跑→冻结→初始DEV57→从A0重跑正式第一轮→第一轮DEV57”的自动链。

## 执行内容

1. 继续当前 `smoke/full_pool_15` 中的同一个训练进程，完整用完540条RL轨迹与2623个固定SFT步骤，各一遍；共15次联合更新。每批更新后保存checkpoint。没有增加筛选条件。
2. 保持现有参数、optimizer、学习率函数、数据顺序和数值检查；不在中途重新初始化。学习率仍是原75次更新计划的前15次，不能事后把本次结果描述成“15次内完整衰减到最低学习率”。
3. 更新的仍是90条轨迹SFT得到的同一套LoRA，基座冻结。原始adapter只读。
4. 完成15批后核对各批身份、540条轨迹和2623步的单遍覆盖、205238个SFT目标token、checkpoint校验和及最终权重有限性。
5. 将最后一批LoRA导出到实验目录的 `artifacts/round_01_final_adapter/`，保存 `adapter_model.safetensors`、`adapter_config.json`、实际配置和来源清单。使用原Qwen3-8B基座加该adapter加载。完整optimizer/RNG继续保留在来源checkpoint。
6. 输出 `ROUND_01_COMPLETE.json` 并结束。没有后续正式重跑、5批备选重跑、DEV57评测或第2轮采集。未执行DEV57，不声明训练效果提升。

## 当前状态与目录

接管时已提交5/15批，正在第6/15批。原GPU1训练进程PID 684724保持不变；只替换外层CPU调度器，新调度器PID 751146。第6批从RL继续进入SFT，未重算这一批、未丢弃累计梯度。

- 实际训练目录：`smoke/full_pool_15/`。保留历史smoke标签以记录来源，里面保存的都是实际更新后的权重；不伪造成此前尚未运行的formal实验。
- 最终来源checkpoint：`smoke/full_pool_15/step_00015/`（完成后存在）。
- 最终交付adapter：`artifacts/round_01_final_adapter/`（完成并验收后创建）。
- 最新范围控制：`runtime/finish_current_pool.json`。
- 只执行到模型保存的监督器：`scripts/finish_current_pool.py --execute`。
- 接管与导出测试：`checks/finish_current_pool_tests.json`；接管核查：`checks/single_pool_handoff.json`。
- 进度：`STATUS.json`、`ROUND_01_RUN.md`、`runtime/round1_run/heartbeat.json`。

原CPU调度器被单独终止，以取消其后续自动重跑；GPU训练进程的PID、启动标识和显存工作保持不变。恢复入口 `scripts/run_round1.py --execute` 现在检测上述范围控制并转入单轮监督器，避免误启动旧自动链。故障时只能恢复当前配置的未提交批；数值或来源问题保留现场，不改成另一次实验。

所有GPU工作仍严格限制物理GPU1，GPU0留给同事。

查看实时进度：

```bash
python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/show_progress.py --watch 5
```

按Ctrl+C只停止查看，不停止训练。
