# 第 1、2 步执行结果

日期：2026-10-14，北京时间。第 1 步完成于 2026-10-14T14:39:50.670546+08:00；第 2 步完成于 2026-10-14T14:40:54.026163+08:00。

本次仅执行用户指定的第 1、2 步。未构建编码训练样本，未进行模型加载、GPU 显存分配、新 judge 调用、评测或参数更新。

## 第 1 步：已完成

独立目录：[本次实验](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft)。

- 重新校验 540 个原始轨迹、540 个 judge 输入、540 个有效 judgement 的哈希；9,886 行 CSV 与有序步骤/有效原始评分逐一一致。
- 校验冻结 prompt、配置、schema 和评分汇总输出哈希；初始 adapter SHA-256 与原 epoch5 SFT 起点一致（r=8、alpha=16）。
- 基座配置、tokenizer 等文件已记录哈希；5 个基座权重 shard 校验存在性和大小，未计算完整基座权重文件哈希。
- 官方 train90、DEV57 与原采集列表一致且无交集；147 个任务的 specs、dbs、ground_truth 目录存在。未启动 AppWorld 环境或执行官方任务测试。
- 训练、AppWorld、vLLM 三个 Python 环境均通过 import 检查，CUDA initialized 均为 false。导入通过不代表后续 GPU 模型运行已验证。

[预检验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/checks/preflight.json) · [来源清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/references/input_inventory.json) · [环境版本](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/references/environment.json) · [模型清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/references/model_inventory.json)

## GPU 与磁盘

**仅物理 GPU1，GPU0 留给同事，即使空闲也不使用。**

GPU1：NVIDIA RTX PRO 6000 Blackwell Server Edition；UUID `GPU-35170b76-56ce-240a-19c0-0c092a3e8501`。预检时总显存 97,887 MiB、可用 97,251 MiB、进程占用 0 MiB。磁盘可用约 52.50 GiB。这些是 2026-10-14T14:39:50.662968+08:00 的快照，不是未来资源保证或完整训练容量证明。

[设备硬限制](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/config/resource_policy.json) 固定 CUDA_VISIBLE_DEVICES 为 GPU1 UUID；进程内 cuda:0 对应物理 GPU1。world_size=1、tensor_parallel_size=1，DDP 禁用。[启动器](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/gpu1_run.py) 先核实 GPU1 UUID 再传递限制，CPU 子进程检查已通过。后续所有 GPU 入口必须使用该启动器且不得在子进程覆盖限制；本次未加载 GPU 模型进行实测。

[资源快照](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/references/resources.json)。完整训练显存、最长上下文、磁盘需求与耗时仍需第 3/6 步测量。

## 第 2 步：已完成

唯一条件：score = count(P) − count(F)，score≥4。U/N 各为 0。未按代码、观察、官方成败、长度、结束动作或内容重复增加任何质量筛选。

| 项目 | 实际结果 |
| --- | ---: |
| 全量步骤 | 9,886 |
| 入选 / 未选 | 2,623 / 7,263 |
| 入选占比 | 26.53% |
| 覆盖任务 / 轨迹 | 88 / 431 |
| 含 F / 含 U 的入选步骤 | 106 / 41 |
| 入选分数 4 / 5 / 6 / 7 | 1,760 / 652 / 195 / 16 |

含 F/U 的步骤按总分原样保留。包括 R1=F 的 6 步；执行异常没有在评分之外成为否决条件。所有 9,886 行已用另一种等价求和实现独立复算，并核对落盘选中集合恰好等于 score≥4 的集合。

- [正式入选清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/selected_steps.jsonl)
- [全量决定清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/data/selection_decisions.jsonl)
- [冻结筛选规则](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/config/selection_policy.json)
- [筛选验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/checks/selection.json)

selected_steps.jsonl 含身份、八维标签、总分、唯一入选原因及源文件/评分哈希；它不是 tokenizer 编码后的 SFT 数据。training_samples_built=0，T_SFT 尚未知。后续完整原始响应与 mask 的构建属于第 3 步，本次没有提前执行。

## 已实现入口

第 1 步：`python scripts/01_preflight.py --config config/draft.json`。

第 2 步：`python scripts/02_select_steps.py --threshold 4`。

工作目录均为本次实验目录。上述命令为已实现接口；预检命令本次采用等价默认配置参数。具体依赖环境探测与启动器验证记录见实验 commands.jsonl。

## 下一步

第 3 步：基于正式 2,623 步清单，从原始 rollout 构建完整历史/目标、编码并验收 loss mask，统计 T_SFT。训练参数仍为候选，GPU1 单卡限制已确定；不以本次预检完成声称训练已经就绪。
