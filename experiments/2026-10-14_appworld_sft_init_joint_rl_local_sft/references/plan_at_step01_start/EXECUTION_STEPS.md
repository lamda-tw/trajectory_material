# 逐步执行手册：净分筛选与 LoRA 联合训练

更新：2026-10-14，北京时间。**本文件供执行前审查；只有离线评分和候选总分统计已经完成，以下数据构建、工程验证、评测及训练尚未由本计划执行。**

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
| E | **拟新建** `W/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft`，本次执行的全部产物 |

评分已完成：540 条、9,886 步、79,088 个标签。候选已计算：P−F≥4 的 2,623 步。正式 selected_steps、编码数据、T_SFT、联合 trainer、基线与正式配置尚待形成。

本次审查不创建 E、不运行 GPU 任务。开始执行时，若 E 已存在，先读取其身份与状态：同一实验且哈希匹配才恢复；不同实验则另建有明确后缀的目录，不覆盖已有产物。

下面的 `scripts/*.py` 是**拟实现的接口名称**，不是宣称仓库已有可直接运行的命令。实现、`--help` 与配置读取检查通过后，才将实际命令及环境路径写入 E/commands.jsonl。命令均以 E 为工作目录；Python 使用步骤 1 核实的训练环境，环境采样进程使用核实的 AppWorld 环境。所有输出带北京时间、阶段和 policy_version。

拟定目录：

~~~text
E/
  config/                 # draft、frozen、selection、evaluation、任务列表
  references/             # 计划、来源索引、脚本快照、哈希及依赖版本
  scripts/                # 本实验独立入口与最小测试
  data/                   # scores、selection、原始样本、编码、消费计划
  checks/                 # 来源、mask、数学、smoke、冻结、预算验收
  smoke/                  # 独立试跑输出，不计正式预算
  rollout/round_XX/batch_YYY/  # 正式新轨迹、reward、old log-prob
  training/               # 指标、恢复 checkpoint、每轮 adapter
  evaluation/initial/     # 初始 DEV57
  evaluation/round_01/    # 第 1/3/5 轮 DEV57
  logs/
  STATUS.json
  ledger.jsonl            # 各批状态与已提交更新账本
  REPORT.md
~~~

## 1. 建立独立目录，核实输入和资源

**操作顺序：**

1. 建立 E，复制本计划和 draft 配置；记录启动时间与实验标识。
2. 读取 J/score_manifest.json、manifest.json、analysis/validation.json。重新校验评分 CSV、540 个有效 judgement、原始来源与输入哈希；只读检查，不重新调用 judge。
3. 校验 A0 的 `adapter_model.safetensors` SHA-256：`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。记录基座配置、adapter_config、tokenizer 文件哈希。
4. 检查 adapter 为既有 r=8、alpha=16 的 SFT 起点，记录实际 target_modules/dropout；后续保持原结构，不新建随机 adapter，不加载其他 GRPO checkpoint。
5. 核实 `.conda-training/bin/python`、AppWorld Python 与推理环境的存在性和依赖版本，执行 import 检查；不先升级依赖。
6. 检查 GPU 型号、空闲显存、运行中的任务、磁盘余量、AppWorld 数据和 train90/DEV57 列表。可用设备写入 resources.json，不占用其他实验进程或结束其任务。

**入口：** `python scripts/01_preflight.py --config config/draft.json`

**产物：** references/input_inventory.json、resources.json、environment.json、checks/preflight.json。

**通过条件：** 来源完整且哈希一致；540/9,886 身份正确；初始 adapter 唯一明确；train90 与 DEV57 不交叉；所需环境可用。资源暂不可用就保持 prepared/waiting 状态，不绕过检查训练。

## 2. 生成正式评分筛选清单（CPU）

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

## 3. 从原始轨迹构建完整局部 SFT 样本（CPU）

**操作顺序：**

1. 经 J/manifest.json 映射到 R 中的原始轨迹；原文件中真实保存的 prompt/messages/assistant 输出是重建依据，judge 脱敏输入不替代训练原文。
2. 对入选步骤重建动作产生前的完整可见消息：系统/工具协议、题目、先前 assistant 动作及已返回的观察；当前动作和后续信息不进入输入。
3. 目标保留该步完整原始 assistant 响应，包括原本的说明文字、代码块和错误；不只提取实际执行的第一段代码，不合成替代动作。
4. 使用与 A0 对应的 tokenizer、chat template、thinking 设置编码。明确提示结束与目标开始位置，核对因果 shift 和结束 token；不能未经验证用两次独立编码长度相减推断边界。
5. 保存 input_ids、目标边界、loss mask 和可追溯原始身份。历史/工具/padding 不监督；目标的每一个实际训练 token 恰好监督一次。
6. 统计每步 prompt/target/总长度、最大长度、单遍 `T_SFT` 和前向 token 开销。2,623 个完整目标的 token 总和才是 T_SFT。
7. 对所有样本机械核对文本/身份/编码边界；人工检查正常、含 F/U、包含结束调用、多代码块、长上下文和连续两步等代表样本，只验重建是否忠实，不重新裁判质量或删样。

**入口：** `python scripts/03_build_sft.py --selection data/selected_steps.jsonl --source-manifest <J>/manifest.json`

**产物：** data/sft_samples.jsonl、data/encoded/、data/data_manifest.json、checks/token_mask.json、data/length_statistics.json。

**通过条件：** 2,623 个身份逐一对应；无后续信息泄漏；目标完整，mask 无错位；源响应与模板还原一致；T_SFT 可复算。

**失败处理：** 原始消息缺失时追查同次采集日志；无法忠实重建则停止于该问题并报告。长上下文超当前容量先调整显存计算方案；必要时采用正确前缀下的目标 span 累积，不能删样或裁历史。span 只能降低部分计算开销，不宣称它能解决所有注意力长度限制；超模型支持范围且无法完整处理时标记阻塞。

## 4. 实现联合训练器与新轨迹采集（先测试，不正式训练）

拟实现 `scripts/joint_trainer.py`、`scripts/collect_batch.py` 和 `scripts/evaluate.py`。建立 source_reuse.json，记录复用部分、原路径、哈希与本次修改。

### 已核实的参考代码与必须改变的地方

| 参考 | 可参考部分 | 不直接沿用的部分 |
| --- | --- | --- |
| `W/experiments/2026-10-08_static_rubric_grpo_lora_init/rollout_worker.py`、`policy_server.py` | AppWorld 环境、模型服务、轨迹落盘 | 固定旧模型路径、旧 reward/judge 调用、旧实验目录 |
| 同目录 `stages/step06_train90_two_gpu/` | 分组、梯度累积/合并和恢复实现 | 旧 540 条离线训练、全部数据只更新一次、旧静态 rubric reward；不能当成本次在线 trainer |
| `W/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/scripts/train_local.py` | response_loss_sum 与正确因果前缀下的目标 span loss | 全新 rank16 adapter、旧样本/预算、旧机械过滤与部分响应截取 |
| `W/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/scripts/train_ddp.py`、`test_ddp_loss.py` | DDP loss 归一化与检查方式 | 旧候选数据、旧起点和训练超参数 |
| 同目录 `scripts/evaluate_checkpoint.py` | 评测编排、输出完整性 | 旧 checkpoint 与输出路径；初始和训练后统一用本次协议 |

### 数学及实现约定

本轮候选 G=6、B=6、在线轮数 E_online=5、K=1，因此每轮 15 批、总计 75 次联合更新、2,700 条正式在线轨迹。最终 B 如因资源改变，预算和消费计划必须在正式训练前重新生成。

每题用官方二值 reward，组内总体标准差（ddof=0）、epsilon=1e-8；全等组优势显式置零。全等组保留原预算与归约分母，不跳过 SFT。

RL 主损失候选采用**先每轨迹生成 token 平均，再对本批轨迹平均**：

~~~text
rho_i,t = exp(log_pi_theta(a_i,t|h_i,t) - old_log_pi_i,t)
L_RL = - mean_i mean_t min(rho_i,t*A_i,
                           clip(rho_i,t, 1-eps_clip, 1+eps_clip)*A_i)
~~~

KL 候选采用采样动作上的非负估计：`d=log_pi_ref-log_pi_theta; k=exp(d)-d-1`，同样先轨迹内再批内平均。记录估计器及梯度实现，不混用精确全词表 KL；检查指数有限性，不暗中截断异常值。reference 是 A0，而不是裸基座或上一批模型。

SFT 是该次消费的全部目标 token 的 CE 总和除以该次实际目标 token 数。总损失 `L_RL + beta*L_KL + lambda*L_SFT`。分别累积两类梯度，统一裁剪并只更新一次 LoRA；不能把 6 题分别 optimizer.step 后仍称为一批联合更新。

行为 old log-prob 必须来自采样版本，在任何参数更新前保存。新旧 log-prob 对齐同一生成 token、上下文、温度及可采样支持集；包含 sampler 的特殊 token 限制等差异要核实并记录。候选采样 temperature=1、top_p=1、不做 top_k 截断以简化一致性；不能以另一分布的概率假装实际行为概率。逐步完整历史用于计算各动作概率；工具观察不计 RL loss。

### 最小验证项（须输出数值，不只标记“通过”）

1. 人工构造 reward `[0,0,0,0,0,0]`、全 1 和成败混合组，检查优势、均值、零组处理。
2. 在小模型/小张量 FP32 上核对“损失加和 backward”与“分别 backward 后梯度相加”；相对误差目标 ≤1e-5（近零用绝对容差），固定随机状态。
3. 验证可变目标长度微批与一次性 token 总和归一化一致；DDP 的 AVG/SUM 因子与全局有效分母一致。
4. 核对更新前 ratio≈1（同实现 FP32 最大 log-prob 差 ≤1e-5）；真实服务与训练端的数值偏差单独量化并设容差，不能复用 FP32 阈值掩盖后端差异。
5. 验证 reference 输出/哈希不变，LoRA 有梯度且基座无梯度；lambda=0 与非零的受控测试能确认 SFT 分支实际接入。
6. 测试一次更新只有一次 optimizer/scheduler step、只有一次梯度裁剪；SFT 数据游标仅在更新提交后前进。
7. 比较中断恢复与连续执行的小批结果，验证 optimizer、scheduler、RNG、数据游标和行为版本完整恢复。

**入口：** `python scripts/04_check_joint_math.py --config config/draft.json`

**产物：** 源码快照、checks/joint_math.json、checks/logprob_alignment.json、checks/resume_test.json。

## 5. 编排 5 遍 SFT 消费与候选训练预算

1. N=2,623 不变；用固定 seed 对每遍样本身份做独立随机排列，共 5 遍，合计 13,115 次完整目标消费。
2. 当 B=6 时，每遍 15 次更新；按目标 token 量尽量均衡划分为 15 个连续片段，样本不丢弃、不重复、不按质量排序。分组差异属于计算编排，不影响入选。
3. 每次更新内可微批/分段累积；各目标 token 在该遍恰好贡献一次。记录每次实际 CE 分母，不假定所有 batch token 数相同。
4. 写出每次更新的 round、任务组、采样种子、SFT 样本身份/目标 span、token 数、预期策略版本与 checkpoint 路径。
5. 全量验算：每个原始目标恰好 5 遍、总监督 token=5×T_SFT、每轮 train90 恰好遍历一次、每题每轮 G=6。

**入口：** `python scripts/05_build_schedule.py --config config/draft.json --data data/data_manifest.json`

**产物：** data/sft_schedule.jsonl、config/task_schedule.json、checks/budget.json。候选 75 次更新必须全部带 SFT 消费；不得发生末尾 SFT 已用尽但仍称联合更新。

## 6. 独立工程试跑，补齐并冻结正式配置

1. 复制 A0 到独立 smoke 工作目录，建立新的 optimizer/scheduler。按固定任务列表顺序选 2 个 train 任务、每题 6 条；不选 DEV，不按结果挑“容易成功”的任务。
2. 实测采样、环境奖励、服务释放/权重切换、reference log-prob、RL 和 SFT 前后向、一次联合更新、保存重载和再次采样；SFT 试跑覆盖普通与最长目标/上下文，后者可单独测显存。
3. 如果这两题全等奖励，保留真实结果；RL 非零梯度的数学正确性用步骤 4 的合成测试验证，不反复换题直至出现成功。
4. 默认按阶段释放推理服务再训练，训练完重启/刷新服务，避免服务与训练争抢显存。确有足够资源才保留共驻；设备数量和布局写入正式配置。
5. 记录显存峰值、每条/每批耗时、训练前后两种 loss、未缩放与缩放梯度范数、ratio/clip fraction、KL、保存重载差异，估算全程磁盘和时长。
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

## 8. 正式执行第 1 批联合更新

只有步骤 1—7 全部通过才进入此步。运行 `python scripts/08_run_joint.py --config config/training_config.json --resume auto`，由状态机执行以下子步骤：

1. **PREPARED：** 核对 freeze、round=1/batch=1 任务组、SFT 消费、当前 optimizer_step=0；保存可恢复的初始状态。
2. **COLLECTING：** 同一 theta_0 在 6 题上各采 6 条，逐条原子落盘。采样期间不更新权重。
3. **ROLLOUT_READY：** 验收 36 条身份/行为版本、生成 token 和 old log-prob，保存 36 个官方 rewards、每组优势及 reference 概率。K=1 时不重复采样利用次数。
4. **GRADIENTS_READY：** 清零梯度；在 theta_0 计算并累积 RL/KL 与计划 SFT 梯度，分别正确归一化，再合并。中间没有 optimizer.step。
5. **UPDATE_COMMITTED：** 一次梯度裁剪、一次 optimizer.step、一次 scheduler.step；以临时目录保存后原子提交完整恢复 checkpoint，同时提交本批账本和 SFT 游标。
6. **POLICY_SYNCED：** 刷新推理端到 theta_1，验证版本和 smoke 请求；进入第二批。

**每批日志必需字段：** policy_version/哈希、任务及轨迹 ID、奖励分布、优势、生成 token 数、SFT 身份和 token 数、各 loss/梯度范数、KL、ratio、clip fraction、学习率、用时、显存、采样与优化器步计数、checkpoint 提交状态。

第一批必须验收：36 条与一个联合更新对应；optimizer_step=1；SFT 游标只前进计划份额；模型参数已变、reference 未变；下一批服务确实加载新权重。

## 9. 完成第 1 轮，并进行第 1 轮 DEV57

1. 依次完成第 2—15 批，每批用上一批联合更新后的模型重新采样。
2. 验算一轮：90 题、540 条正式新轨迹、15 次联合更新、2,623 个目标恰好消费一遍、监督 token=T_SFT。
3. 保存不可覆盖的 round_01 adapter 和完整恢复 checkpoint，生成 round_validation.json。
4. 在 checkpoint 固定状态下运行 DEV57，记录与基线的逐题差异。不按本轮成绩回改阈值、学习率或训练时长。

**入口：** 同一状态机自动推进；评测使用 `scripts/evaluate.py --checkpoint round_01`。

## 10. 完成第 2—5 轮

1. 继续相同状态机；每轮独立任务排列和 SFT 排列由冻结计划给出。
2. 第 2、4 轮保存模型和预算验收；第 3、5 轮另运行完整 DEV57。
3. 候选配置下最终验算：2,700 条在线轨迹、75 次联合更新、13,115 次原始目标消费、总 token=5×T_SFT。
4. 第 5 轮是主要终点；不以第 1/3 轮较高成绩替换终点。全等奖励组照常推进，不为了制造优势而补采或改 reward。

**产物：** training/round_01..05、evaluation/round_01/03/05、全部原始新轨迹及成本账本。

## 11. 故障与恢复（适用于步骤 8—10）

| 情况 | 处理方法 |
| --- | --- |
| 模型代码异常、步数或协议预算耗尽 | 属于实际 rollout 结果，走官方检查；不能作为“坏数据”删掉重采 |
| worker/服务/机器基础设施故障 | 保留失败记录，恢复同一行为模型与任务采样状态；重试技术失败的槽位。无法复原随机状态则记录新 attempt/seed，禁止按结果挑选 |
| 参数未更新但采样已完成 | 校验哈希后复用该批 rollout，不重新获取更好的 reward |
| 累积梯度时崩溃 | 从最近已提交 checkpoint 重算该未提交批的梯度；不依赖不完整内存梯度 |
| optimizer.step 后尚未原子提交就崩溃 | 恢复上一个已提交 checkpoint，按保存的该批 rollout/随机状态重算一次；提交账本保证一次批次只产生一个已承认更新 |
| checkpoint 已提交、服务尚未同步 | 不重复更新；只刷新权重，校验版本后继续 |
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
- 固定离线步骤只提供 SFT；每批 RL 用当前模型新轨迹和官方奖励，无新 judge 调用。
- 同一个 LoRA 上合并两种梯度，一批一次更新；不先跑纯 SFT 或纯 RL 阶段。
- 数值配置分“候选值”和“工程测量后冻结值”；候选见 JSON，改变理由必须入账。
- 先数据/数学/工程验收，再基线、正式训练和最终评测；未通过就修复，不跳步骤。
