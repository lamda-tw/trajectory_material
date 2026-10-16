# 逐步执行手册：净分筛选与 LoRA 联合训练

> **2026-10-15 用户缩减本次执行范围：保留当前单轮训练模型并结束。** 本次仅继续已有15批，不再从头正式重跑或自动评测；五轮设计保留为后续研究计划。最新执行依据：[SINGLE_POOL_MODEL_SCOPE.md](SINGLE_POOL_MODEL_SCOPE.md)。
> 第一轮自动执行入口已实现：`scripts/run_round1.py --execute`。最新运行约定见 [ROUND_01_EXECUTION.md](ROUND_01_EXECUTION.md)，事实状态见 [ROUND_01_RUN.md](ROUND_01_RUN.md)。本次授权范围止于第1轮DEV57；第2—5轮不由该入口启动。下文历史的“待实现”应以此入口及实际状态为准。

更新：2026-10-14，北京时间。**本文件记录执行步骤与当前事实：第 1—3 步已完成；正式筛选 2,623 步已构建完整训练样本，单遍 205,238 个目标 token。第 4 步代码与 CPU/GPU1 基础试跑已完成；整池稳定性试跑、配置冻结、基线与正式训练待执行。**

总设计与数据依据见 [PLAN.md](PLAN.md)。候选数值配置见 [TRAINING_CONFIG_DRAFT.json](TRAINING_CONFIG_DRAFT.json)。本手册规定实际执行顺序、每一步产物和通过条件；不能以“后续补齐”为由跳过验收进入训练。

## 0. 路径、完成状态与执行约定

路径缩写仅用于本文件：

| 名称 | 绝对路径 / 含义 |
| --- | --- |
| W | `/root/autodl-tmp/workspace-tw` |
| P | `W/plans/2026-10-13_appworld_sft_init_local_sft_online_rl`，本计划目录 |
| J | `W/experiments/2026-10-14_appworld_sft_init_step_rubric_v6_gpt61_sol`，已完成评分，只读 |
| R | `W/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories`，原始轨迹，只读 |
| A0 | `W/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/initial_adapter`，初始 SFT adapter，只读 |
| M | `/root/autodl-tmp/models/Qwen3-8B`，基座，只读 |
| E | **已建立** `W/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft`，本次执行的全部产物 |

评分已完成：540 条、9,886 步、79,088 个标签。第 1、2 步已完成：正式 selection_decisions、selected_steps 和 selection_policy 已落盘并通过验收。编码数据与 mask 已验收，T_SFT=205,238；联合 trainer/collector 已实现；基线与正式冻结配置尚待形成。见 [前两步记录](STEP_01_02_RESULTS.md) 与 [第三步记录](STEP_03_RESULTS.md)。

E 已创建，IDENTITY.json 与 STATUS.json 记录本实验身份和第 1—3 步完成状态。继续时先核对身份和哈希，不能覆盖或误接其他实验。第 4 步已在物理 GPU1 执行隔离模型/采集/更新试跑；未进行正式训练。

`scripts/01_preflight.py`、`02_select_steps.py`、`common.py`、`env_probe.py` 和 `gpu1_run.py` 已实现；第 1、2 步已运行。`03_build_sft.py`、`03_validate_sft.py`、`sft_dataset.py` 也已实现，完整数据与 mask 验收通过。joint_core.py、joint_trainer.py、round_data.py、collect_round.py、rollout_worker.py、policy_server.py、04_check_joint_math.py、04_gpu_probe.py、04_gpu_joint_smoke.py、05_build_schedule.py 已实现；其余脚本仍是**拟实现的接口名称**。后续实现并验证后，才执行对应命令并写入 E/commands.jsonl。手册命令以 E 为工作目录；本次 CPU 准备入口使用系统 Python 并以绝对脚本路径启动，三个专用环境另有导入验证。后续训练使用核实的训练 Python，环境采样进程使用核实的 AppWorld Python。所有输出带北京时间、阶段和 policy_version。

**GPU 硬限制：仅物理 GPU1。** E/config/resource_policy.json 固定 GPU1 UUID；GPU0 保留给同事，禁止自动选用。GPU 入口统一经 `python scripts/gpu1_run.py -- <executable> <arguments...>` 启动，子进程不得覆盖其 CUDA_VISIBLE_DEVICES。进程内 cuda:0 对应物理 GPU1，world_size=1、tensor_parallel_size=1；DDP 禁用。资源不足不能借用 GPU0。启动器已经用 CPU 子进程验证环境传递，已通过 GPU1 实际分配与进程锁测试。vLLM 0.10.2 的 UUID/NVML 兼容在本实验 scripts/vllm_uuid_compat/sitecustomize.py 中修复，CUDA_VISIBLE_DEVICES 仍为 GPU1 UUID，不修改共享环境。

目录设计（目前仅建准备阶段所需目录）：

~~~text
E/
  config/                 # draft、frozen、selection、evaluation、任务列表
  references/             # 计划、来源索引、脚本快照、哈希及依赖版本
  scripts/                # 本实验独立入口与最小测试
  data/                   # scores、selection、原始样本、编码、消费计划
  checks/                 # 来源、mask、数学、smoke、冻结、预算验收
  smoke/                  # 独立试跑输出，不计正式预算
  rollout/round_XX/pool.json   # 整轮池索引，540 条、reward、old log-prob；首轮只读引用旧轨迹
  training/               # 指标、恢复 checkpoint、每轮 adapter
  evaluation/initial/     # 初始 DEV57
  evaluation/round_01/    # 第 1/3/5 轮 DEV57
  logs/
  STATUS.json
  ledger.jsonl            # 各批状态与已提交更新账本
  REPORT.md
~~~

## 1. 建立独立目录，核实输入和资源（已完成）

**操作顺序：**

1. 建立 E，复制本计划和 draft 配置；记录启动时间与实验标识。
2. 读取 J/score_manifest.json、manifest.json、analysis/validation.json。重新校验评分 CSV、540 个有效 judgement、原始来源与输入哈希；只读检查，不重新调用 judge。
3. 校验 A0 的 `adapter_model.safetensors` SHA-256：`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。记录基座配置、adapter_config、tokenizer 文件哈希。
4. 检查 adapter 为既有 r=8、alpha=16 的 SFT 起点，记录实际 target_modules/dropout；后续保持原结构，不新建随机 adapter，不加载其他 GRPO checkpoint。
5. 核实 `.conda-training/bin/python`、AppWorld Python 与推理环境的存在性和依赖版本，执行 import 检查；不先升级依赖。
6. 检查 GPU 型号、空闲显存、运行中的任务、磁盘余量、AppWorld 数据和 train90/DEV57 列表。只允许物理 GPU1，并记录其 UUID、显存与运行状态。GPU0 仅可只读查询，不加载任何模型或分配显存，不结束其他实验进程。

**入口：** `python scripts/01_preflight.py --config config/draft.json`

**产物：** references/input_inventory.json、resources.json、environment.json、checks/preflight.json。

**通过条件：** 来源完整且哈希一致；540/9,886 身份正确；初始 adapter 唯一明确；train90 与 DEV57 不交叉；所需环境可用。资源暂不可用就保持 prepared/waiting 状态，不绕过检查训练。

## 2. 生成正式评分筛选清单（CPU，已完成）

**操作顺序：**

1. 只读取 J/analysis/step_labels.csv，按唯一 `(trajectory_id, step_id)` 建立 9,886 行全量表。
2. 每行计算 P/F/U/N 数量与 `score=P_count-F_count`。
3. `selected = (score >= 4)`；无其他谓词，不读取代码/观察来决定入选。
4. 保存全量 selection_decisions.jsonl；每行包含原始身份、八维标签、总分、布尔决定、唯一原因 `score_ge_4` 或 `score_lt_4`。
5. 输出 selected_steps.jsonl，并写 selection_policy.json：标签输入哈希、公式、阈值、无额外筛选、无内容去重。
6. 生成描述统计，但不根据统计改变名单。

**入口：** `python scripts/02_select_steps.py --labels <J>/analysis/step_labels.csv --threshold 4`

**产物：** data/selection_decisions.jsonl、data/selected_steps.jsonl、config/selection_policy.json、checks/selection.json。

**通过条件：** 恰好 2,623 个不同步骤身份，未选 7,263；覆盖 88 题、431 条轨迹；106 个含 F、41 个含 U 均按阈值保留。对所有 9,886 行独立复算并确认 selected 与唯一条件完全等价。

**失败处理：** 数量不符先追查输入、版本或实现；不增加补样、去重、R1=P、无异常或其他门槛来修正数量。

## 3. 从原始轨迹构建完整局部 SFT 样本（CPU，已完成）

**操作顺序：**

1. 经 J/manifest.json 映射到 R 中的原始轨迹；原文件中真实保存的 prompt/messages/assistant 输出是重建依据，judge 脱敏输入不替代训练原文。
2. 对入选步骤重建动作产生前的完整可见消息：系统/工具协议、题目、先前 assistant 动作及已返回的观察；当前动作和后续信息不进入输入。
3. 目标保留该步完整原始 assistant 响应，包括原本的说明文字、代码块和错误；不只提取实际执行的第一段代码，不合成替代动作。
4. 使用与 A0 对应的 tokenizer、chat template、thinking 设置编码。明确提示结束与目标开始位置，核对因果 shift 和结束 token；不能未经验证用两次独立编码长度相减推断边界。
5. 保存 input_ids、目标边界、loss mask 和可追溯原始身份。历史/工具/padding 不监督；目标的每一个实际训练 token 恰好监督一次。
6. 统计每步 prompt/target/总长度、最大长度、单遍 `T_SFT` 和前向 token 开销。2,623 个完整目标的 token 总和才是 T_SFT。
7. 对所有样本机械核对文本/身份/编码边界；人工检查正常、含 F/U、包含结束调用、多代码块、长上下文和连续两步等代表样本，只验重建是否忠实，不重新裁判质量或删样。

**已实现入口：** 经 GPU1 启动器使用训练 Python 运行 `scripts/03_build_sft.py`，再运行 `scripts/03_validate_sft.py`，均为 CPU 处理；默认参数指向本实验正式清单与只读来源快照。实际执行与数据使用见 STEP_03_RESULTS.md。

**产物：** data/sft_samples.jsonl、data/encoded/、data/data_manifest.json、checks/token_mask.json、data/length_statistics.json。

**通过条件：** 2,623 个身份逐一对应；无后续信息泄漏；目标完整，mask 无错位；源响应与模板还原一致；T_SFT 可复算。

**失败处理：** 原始消息缺失时追查同次采集日志；无法忠实重建则停止于该问题并报告。长上下文超当前容量先调整显存计算方案；必要时采用正确前缀下的目标 span 累积，不能删样或裁历史。span 只能降低部分计算开销，不宣称它能解决所有注意力长度限制；超模型支持范围且无法完整处理时标记阻塞。

## 4. 实现联合训练器与新轨迹采集（先测试，不正式训练）

已实现 `scripts/joint_trainer.py` 和 `scripts/collect_round.py`，复用记录见 references/step04_source_reuse.json。评测入口仍属于后续实现。实际基础验收见 STEP_04_RESULTS.md，不能将小规模试跑视为整池稳定性证明。

### 已核实的参考代码与必须改变的地方

| 参考 | 可参考部分 | 不直接沿用的部分 |
| --- | --- | --- |
| `W/experiments/2026-10-08_static_rubric_grpo_lora_init/rollout_worker.py`、`policy_server.py` | AppWorld 环境、模型服务、轨迹落盘 | 固定旧模型路径、旧 reward/judge 调用、旧实验目录 |
| 同目录 `stages/step06_train90_two_gpu/` | 分组、梯度累积/合并和恢复实现 | 旧 540 条离线训练、全部数据只更新一次、旧静态 rubric reward；不能当成本次在线 trainer |
| `W/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/scripts/train_local.py` | response_loss_sum 与正确因果前缀下的目标 span loss | 全新 rank16 adapter、旧样本/预算、旧机械过滤与部分响应截取 |
| `W/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/scripts/train_ddp.py`、`test_ddp_loss.py` | DDP loss 归一化与检查方式 | 旧候选数据、旧起点和训练超参数 |
| 同目录 `scripts/evaluate_checkpoint.py` | 评测编排、输出完整性 | 旧 checkpoint 与输出路径；初始和训练后统一用本次协议 |

### 数学及实现约定

本轮候选 G=6、B=6、在线轮数 E_online=5、K=1，因此每轮 15 批、总计 75 次联合更新、2,700 条正式 RL 消费轨迹，其中首轮旧 540、新采 2,160。最终 B 如因资源改变，预算和消费计划必须在正式训练前重新生成。

每题用官方二值 reward，组内总体标准差（ddof=0）、epsilon=1e-8；全等组优势显式置零。全等组保留原预算与归约分母，不跳过 SFT。

RL 主损失候选采用**先每轨迹生成 token 平均，再对本批轨迹平均**：

~~~text
rho_i,t = exp(log_pi_theta(a_i,t|h_i,t) - old_log_pi_i,t)
L_RL = - mean_i mean_t min(rho_i,t*A_i,
                           clip(rho_i,t, 1-eps_clip, 1+eps_clip)*A_i)
~~~

KL 候选采用采样动作上的非负估计：`d=log_pi_ref-log_pi_theta; k=exp(d)-d-1`，同样先轨迹内再批内平均。记录估计器及梯度实现，不混用精确全词表 KL；检查指数有限性，不暗中截断异常值。reference 是 A0，而不是裸基座或上一批模型。

局部 SFT 按用户要求固定为**每个原始步骤内部先对目标 token 平均，再对该次更新的步骤平均**：

~~~text
M = 本次 optimizer update 实际消费的原始步骤数
T_s = 步骤 s 的完整目标 token 数（含原始 EOS，不含历史和 padding）
L_SFT = (1/M) * sum_s [(1/T_s) * sum_t CE(s,t)]
~~~

每个步骤权重相同，均为 1/M；不是把全部目标 token 混在一起平均，也不以 rubric 净分加权。微批或长响应分段时，每段 CE 总和乘 `1/(M*T_s)` 后累积梯度；T_s 始终是原始完整步骤长度，分段不会产生新的步骤。尾批使用实际 M，不能简单平均大小不同的微批 loss。HF 默认标量 causal loss 不应直接作为本目标，须取得逐 token CE 后显式执行上述归约；因果移位仅一次。现有数据和 mask 无需重建，trainer 中的实现及基础数值验收已通过。本次 SFT 规则不改动上文基于轨迹奖励的 RL/KL 归约。

总损失 `L_RL + beta*L_KL + lambda*L_SFT`。分别累积两类梯度，统一裁剪并只更新一次 LoRA；不能把 6 题分别 optimizer.step 后仍称为一批联合更新。

行为 old log-prob 必须来自采样版本，在该池任何参数更新前保存；整轮保持冻结，不在 batch 边界重新采样或覆盖。新旧 log-prob 对齐同一生成 token、上下文、温度及可采样支持集；包含 sampler 的特殊 token 限制等差异要核实并记录。候选采样 temperature=1、top_p=1、不做 top_k 截断以简化一致性；不能以另一分布的概率假装实际行为概率。逐步完整历史用于计算各动作概率；工具观察不计 RL loss。

### 最小验证项（须输出数值，不只标记“通过”）

1. 人工构造 reward `[0,0,0,0,0,0]`、全 1 和成败混合组，检查优势、均值、零组处理。
2. 在小模型/小张量 FP32 上核对“损失加和 backward”与“分别 backward 后梯度相加”；相对误差目标 ≤1e-5（近零用绝对容差），固定随机状态。
3. 验证可变目标长度下，整批步骤平均与微批/分段梯度累积的 loss 和梯度一致；覆盖不等微批大小、尾批、历史/padding 排除和原始 EOS。构造短步骤 1 个 token、CE=1，长步骤 3 个 token、各 CE=3，步骤平均应为 2，而全部 token 平均为 2.5；真实张量测试须核对梯度。CPU 小张量先验算，真实模型仅 GPU1，world_size=1，不启用 DDP。
4. 核对每池第 1 次更新前 ratio≈1；后续批次相对固定 old policy 的偏离是被测量的量，不强制为 1。初始同后端测试要求（同实现 FP32 最大 log-prob 差 ≤1e-5）；真实服务与训练端的数值偏差单独量化并设容差，不能复用 FP32 阈值掩盖后端差异。
5. 验证 reference 输出/哈希不变，LoRA 有梯度且基座无梯度；lambda=0 与非零的受控测试能确认 SFT 分支实际接入。
6. 测试一次更新只有一次 optimizer/scheduler step、只有一次梯度裁剪；SFT 数据游标仅在更新提交后前进。
7. 比较中断恢复与连续执行的小批结果，验证 optimizer、scheduler、RNG、数据游标和行为版本完整恢复。

**入口：** `python scripts/04_check_joint_math.py`

**产物：** 源码快照、checks/joint_math.json、checks/logprob_alignment.json、checks/resume_test.json。

## 5. 编排 5 遍 SFT 消费与候选训练预算

1. N=2,623 不变；用固定 seed 对每遍样本身份做独立随机排列，共 5 遍，合计 13,115 次完整目标消费、1,026,190 个监督 token。
2. 当 B=6 时，每遍 15 次更新；固定 seed 随机排列后优先按步骤数均分：13 批各 175 步、2 批各 174 步，轮换小批位置，避免以 token 配额造成步骤数大幅不同。每次更新内再做长度分组/微批以控制显存，不改变步骤权重。样本不丢弃、不重复、不按质量排序；具体调度文件仍在本步骤生成。
3. 每次更新内可微批/分段累积；各目标 token 在该遍恰好贡献一次。记录实际步骤数 M、各完整目标长度 T_s，以及 CE_sum/(M*T_s) 的分母。总 token 数只用于监督预算和成本核算，不作为 SFT 全局 loss 分母。
4. 写出每次更新的 round、任务组、采样种子、SFT 样本身份/目标 span、token 数、预期策略版本与 checkpoint 路径。
5. 全量验算：每个原始目标恰好 5 遍、总监督 token=5×T_SFT、每轮 train90 恰好遍历一次、每题每轮 G=6。

**入口：** `python scripts/05_build_schedule.py`

**产物：** data/sft_schedule_candidate.jsonl、checks/schedule_candidate.json；正式冻结时生成最终 schedule/budget。候选 75 次更新必须全部带 SFT 消费；不得发生末尾 SFT 已用尽但仍称联合更新。

## 6. 独立工程试跑，补齐并冻结正式配置

1. 复制 A0 到独立 smoke 工作目录，建立新的 optimizer/scheduler。按固定任务列表顺序选 2 个 train 任务、每题 6 条；不选 DEV，不按结果挑“容易成功”的任务。
2. 已完成小规模采样、环境奖励、服务释放、reference log-prob、SFT 前后向、两次隔离联合更新与保存重载。接着实测完整 540 池的一遍更新阶段，特别是第 10—15 批（若候选保留 15 批）的策略偏离，以及轮间换模型后的新采样；SFT 试跑覆盖普通与最长目标/上下文，后者可单独测显存。
3. 如果这两题全等奖励，保留真实结果；RL 非零梯度的数学正确性用步骤 4 的合成测试验证，不反复换题直至出现成功。
4. 默认按阶段释放推理服务再训练，整轮训练完才重启/刷新服务，避免服务与训练争抢显存。确有足够资源才保留共驻；设备固定为物理 GPU1、world_size=1；不得改用 GPU0 或扩成双卡。具体时分复用布局写入正式配置。
5. 记录显存峰值、每条/每批/整池耗时、训练前后两种 loss、未缩放与缩放梯度范数、ratio/clip fraction、KL、保存重载差异，估算全程磁盘和时长。
6. 优先通过微批、梯度检查点、精度、计算分段与设备布局解决 OOM，不删除样本；必须改变 B 时重新生成步骤 5。学习率/beta/lambda 的候选值若出现数值故障或单分支完全失效，先排实现问题；任何修改写入 config_decisions.json，不根据 DEV 搜索参数。
7. 生成实际 `training_config.json`：不允许 pending/null 参数，包括真实 T_SFT、设备、环境、上下文支持、attention、log-prob 容差、保存策略和预算。保存代码、数据、配置、计划哈希到 FREEZE.json。
8. 正式运行重新从 A0、初始 optimizer/scheduler、正式 seed、零游标开始；smoke 的模型和数据不混入正式预算。

**入口：** `python scripts/06_smoke.py --config config/draft.json`；随后 `python scripts/07_freeze.py --smoke smoke/report.json`。

**通过条件：** 无未解释 NaN/Inf、token 错位、概率分布错配、错误 adapter 或漏样；所有数学/数据检查通过，配置具体且可复算。试跑只支持工程判断，不声称证明训练有效。

## 7. 建立初始 DEV57 基线

1. 加载 A0，核对实际服务版本；读取已冻结 DEV57 身份与评测协议。
2. 每题独立初始环境、temperature=0、固定 seed=100、50 步上限、每次最大新 token=3,000、在线/评测上下文上限候选 32,000、thinking=False。这些设置在步骤 6 核对模型支持后冻结，初始和后续完全一致。
3. 保存原始轨迹、官方结果和技术故障记录；模型自身异常照实计结果，基础设施故障在恢复后重试同题，不凭成败挑结果。
4. 验收 57 个任务各有一个有效评测结果，输出初始成功数和成功率。

**入口：** `python scripts/evaluate.py --checkpoint initial --config config/training_config.json --output evaluation/initial`

**通过条件：** baseline_complete.json 通过；不能以历史成绩替代本次同协议基线。基线成绩不用于修改筛选阈值或训练配置。

## 8. 准备完整第 1 轮池并执行首批更新

步骤 1—7 的正式验收通过后执行。首轮池已由 `scripts/round_data.py --import-initial` 建立，只读引用旧 540 条，没有重采或重评分。

1. **POOL_READY：** 校验完整 90×6、A0 身份、源哈希、行为概率、官方奖励，生成固定组内优势；按冻结计划分成优化 batch。保存行为版本及原始概率，后续不可覆盖。
2. **REFERENCE_READY：** 仅 GPU1 加载 base+A0，在 no_grad 下计算 reference 概率并缓存。续训时切换同一组 LoRA 参数到当前已提交权重；不以禁用 adapter 的裸基座代替 A0。
3. **BATCH_PREPARED：** 读取首批任务组和 SFT 样本索引，验证全池/配置/样本哈希与零游标。
4. **GRADIENTS_READY：** 在当前参数上微批累积 RL/KL 与 SFT 梯度；SFT 逐步骤平均；中间无参数更新。
5. **UPDATE_COMMITTED：** 统一裁剪，执行一次 optimizer.step；学习率函数使用全局 update 编号。原子提交 adapter、optimizer、RNG、调度位置及 SFT 游标。
6. 直接读取同一池的第二批，**不重启推理、不采新轨迹**。每批均有独立 checkpoint。

拟正式入口（FREEZE 与 baseline 缺失时拒绝执行）：
`python scripts/gpu1_run.py -- <training_python> scripts/joint_trainer.py --config config/training_config.json --pool rollout/round_01/pool.json --output training/round_01 --mode formal --execute`

每批记录 actor 更新编号、固定行为版本、reference 身份、任务/轨迹/SFT 身份、各 loss、梯度范数、ratio 范围/越界比例、KL、学习率、时间、显存与提交状态。当前实现记录 RL+加权 KL 的合并梯度及加权 SFT 梯度；单独 KL 梯度和真实分布熵的深入诊断仍需在整池试跑补充，不能把 sampled_action_nll 误称为策略熵。

## 9. 用完第 1 轮池并保存 A1

1. 逐批读取同一份旧 540 池，每批更新一次参数。old log-prob 始终对应 A0，不随 batch 刷新。
2. 候选 15 批时，验算 540 条各用于 RL 一次、2,623 步各用于 SFT 一次、监督 token=205,238。
3. 保存 round_01 最终 adapter（A1）和完整恢复状态；按冻结协议执行 DEV57。
4. 完成该轮后才进入新采样。不能把轮末保存模型误写为轮末才更新参数。

## 10. 第 2—5 轮：整池新采样与单遍联合更新

1. 固定上一轮最终模型 Ar，在 90 题各采 6 条，完整写入下一轮池。采集阶段模型不变，使用 GPU1 上的一个 vLLM 服务持续处理任务。
2. 新池凑齐并通过身份/概率/官方奖励验收后，停止服务，进入本轮 trainer。轮内不混入其他轮 RL 轨迹。
3. 沿用同一 optimizer 状态和连续学习率。固定 SFT 2,623 步每轮重新排列并完整学习一遍，不新增评分/筛选。
4. 第 2、4 轮保存模型与预算；第 3、5 轮另做 DEV57。第 5 轮为主要终点，不挑最好一轮。
5. 候选 15 批时：总 75 次更新、旧 540+新 2,160=2,700 条 RL 消费、13,115 次 SFT 步骤消费、1,026,190 监督 token。完整池试跑若改变批次数，正式训练前重算更新数与学习率，样本覆盖不变。

采集入口：`scripts/collect_round.py --adapter <上一轮最后一个已提交 checkpoint> --round <2..5> --output rollout/round_XX --mode formal --execute`，必须经 GPU1 launcher；仅接受已完成上一轮的正式 checkpoint。轮间编排与评测自动化仍待实现，不能把当前可调用模块声称为无人值守正式全程已验收。

## 11. 故障与恢复（适用于步骤 8—10）

| 情况 | 处理方法 |
| --- | --- |
| 模型代码异常、步数或协议预算耗尽 | 属于实际 rollout 结果，走官方检查；不能作为“坏数据”删掉重采 |
| worker/服务/机器基础设施故障 | 保留失败记录，恢复同一行为模型与任务采样状态；重试技术失败的槽位。无法复原随机状态则记录新 attempt/seed，禁止按结果挑选 |
| 参数未更新但采样已完成 | 校验哈希后复用该轮已完成池/已有采集槽位，不重新获取更好的 reward |
| 累积梯度时崩溃 | 从最近已提交 checkpoint 重算该未提交批的梯度；不依赖不完整内存梯度 |
| optimizer.step 后尚未原子提交就崩溃 | 恢复上一个已提交 checkpoint，按保存的该批 rollout/随机状态重算一次；提交账本保证一次批次只产生一个已承认更新 |
| checkpoint 已提交、后续阶段未开始 | 不重复更新；轮内读取下一批，轮末才同步服务采下一池 |
| OOM | 清理本实验临时资源、调整等价计算布局；保留样本和目标，变更记录入账。改变优化目标/预算必须修订计划，不能静默继续 |
| NaN/Inf、概率错位或来源哈希冲突 | 停止参数推进，保存诊断，定位实现/数值问题，恢复可信状态。不能直接跳过该批 |
| 第 1/3 轮 DEV 下降 | 照实记录，按冻结计划继续至第 5 轮；不事后早停挑最好结果 |

完整恢复状态包括 adapter、optimizer、scheduler、精度 scaler（若使用）、CPU/CUDA/Python/NumPy RNG、任务与 SFT 游标、更新计数、未提交批引用、行为版本和 freeze 哈希。不能仅加载 adapter 就声称精确恢复。

监控检查进程、心跳、磁盘、长时间无进展、当前批/轮和预算；日志持续落盘。技术问题按上表自行处理；无法保持实验定义时明确标记阻塞，不伪装为完成。

## 12. 最终验收与报告

1. 独立重新验算来源、评分筛选、2,623 个身份、完整 mask、五遍监督与在线预算。
2. 重载最终 adapter，确认模型可推理且哈希与 DEV 第 5 轮一致。
3. 汇总初始与第 1/3/5 轮 DEV 成功数/率；主要比较第 5 轮对初始，列出新增成功、退化与未变题目。
4. 报告训练曲线、奖励同质组比例、loss/KL/梯度、学习进程，以及代表案例；不能从单次联合实验单独归因 SFT 的贡献。
5. 分列初始 judge 成本、数据构建、smoke、正式 rollout、官方检查、训练、同步保存与评测成本。
6. 输出 REPORT.md、delivery_manifest.json、FINAL_VALIDATION.json；所有交付链接和哈希可核验，再把 STATUS 标记 complete。

## 审查时最需要确认的设计点

- 唯一选择条件 P−F≥4；2,623 个原始步骤全部保留，含 F/U 也不二次剔除。
- 固定离线步骤提供 SFT；RL 每轮使用完整行为策略池和官方奖励，首轮复用已有 540 条，无新 judge 调用。
- 同一个 LoRA 上合并两种梯度，一批一次更新；不先跑纯 SFT 或纯 RL 阶段。
- 数值配置分“候选值”和“工程测量后冻结值”；候选见 JSON，改变理由必须入账。
- 先数据/数学/工程验收，再基线、正式训练和最终评测；未通过就修复，不跳步骤。
