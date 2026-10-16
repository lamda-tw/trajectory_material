# 第一轮最终 LoRA

基座：/root/autodl-tmp/models/Qwen3-8B

加载本目录的 adapter_model.safetensors 和 adapter_config.json 即可在原基座上使用。仅 LoRA，无全量基座合并。

来源：/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/smoke/full_pool_15/step_00015

已完成15次联合更新、540条RL轨迹与2623个SFT步骤各一遍。未执行DEV57，不声称评测效果。完整optimizer/RNG保留在来源checkpoint的resume.pt。
