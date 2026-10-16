# 第一轮最终 LoRA 的 DEV57 评测

**已于2026-10-16 09:35（北京时间）完成：成功20/57，失败37/57，TGC=35.09%，SGC=2/19=10.53%。** 共1026个动作、175646个生成token，57次worker执行均正常返回，没有基础设施失败或重试。48条轨迹通过完成接口结束，9条达到上下文上限；全部按官方测试计分。总运行约22分25秒，含服务启动与关闭。

[独立核对](checks/dev57_final_audit.json)已通过：57题完整覆盖，逐题JSON/CSV/汇总一致，输入及代码哈希一致，评测前后LoRA权重不变。评测进程和自有vLLM服务均已退出，核实时GPU1显存占用为0。实验与计划README已更新。

2026-10-16，北京时间。用户在第一轮训练结束后新增授权：评测dev57，所有实验结果留在当前实验目录，不在workspace顶层的experiments下新建实验目录或散落文件。

第一轮15批已于03:55完成。此次评测于09:12启动，只加载 `artifacts/round_01_final_adapter`，权重SHA-256为 `c8f268b58dea9fc79ae53cfc362dede13edd965b604a4e702c2b6966ddf211d9`。评测前已核对导出权重、实际训练配置和第15批完整checkpoint的哈希；保留其smoke来源，不伪造未执行的formal冻结流程。

与训练前历史基线相比：TGC 23/57→20/57，SGC 4/19→2/19；初始LoRA身份已核实，但评测入口并非完全一致。详见 [基线对比与协议核对](evaluation/round_01_final/BASELINE_COMPARISON.md)。

## 查看结果与进度

- [逐题结果表 RESULTS.md](evaluation/round_01_final/RESULTS.md)：每完成一题刷新；包括待完成项、PASS/FAIL、官方测试通过数、步数和结束原因。
- [实时状态 STATUS.json](evaluation/round_01_final/STATUS.json)。
- [逐题 CSV](evaluation/round_01_final/task_results.csv)。
- [评测主日志](logs/dev57_round_01_final.log)；[vLLM服务日志](evaluation/round_01_final/server/vllm.log)。
- 全部57题完成后生成 `evaluation/round_01_final/SUMMARY.json`、`evaluation_complete.json` 与实验根目录 `DEV57_COMPLETE.json`。

统一进度查看命令仍可使用：

```bash
python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/show_progress.py --watch 5
```

## 固定协议

- AppWorld官方dev划分57题，已独立核对与 `config/dev57.txt` 完全一致，与train90无交集。
- 每题1条轨迹，temperature=0、初始seed=100（每步使用100+从零计数的步号）；最多50步，每动作最多3000生成token，上下文32000，thinking=False。
- 仅物理GPU1；按UUID固定设备，GPU阶段互斥，服务最多6条并发序列、6个任务worker。
- 沿用本实验采集器的agent prompt、代码解析、历史拼接及官方评估；这不代表与2026-09-21历史入口逐token一致，差异见基线对比。官方任务失败照实计入57题分母，只对基础设施异常最多重试3次。
- 汇总指标TGC=官方成功题数/57；SGC=场景内3题全部成功的场景数/19，补充计算见基线对比。此次只评测最终模型，没有补跑初始模型对照，因此不直接声称相对提升。
- 评测不更新任何模型参数，不启用前缀共享训练优化，不启动新一轮采集或训练。任务结束会关闭自己启动的vLLM服务并退出。

## 文件位置与恢复

评测配置、输入/代码哈希、任务job、逐题日志、轨迹JSON与尝试记录全部位于 `evaluation/round_01_final/`。AppWorld环境输出位于本实验内的 `runtime/appworld/experiments/outputs/joint_round_01_final_*`；没有新增workspace顶层的实验目录。启动进程记录为 `runtime/dev57_round_01_final_launch.json`，预检记录为 `checks/final_evaluation_preflight.json`。

若基础设施故障导致退出，先查看该目录的 `ERROR.json` 和日志；同一入口会严格核对模型、配置、代码及已有job身份，保留已经完成的成功与失败题，只补齐缺失结果。不要同时启动第二个评测实例。

```bash
/root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/gpu1_run.py -- /root/autodl-tmp/workspace-tw/.conda-training/bin/python -u /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/evaluate.py --label round_01_final --adapter /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/artifacts/round_01_final_adapter --execute
```
