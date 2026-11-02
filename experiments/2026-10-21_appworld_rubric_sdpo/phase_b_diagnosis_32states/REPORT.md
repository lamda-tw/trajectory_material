# B 阶段：32 个固定状态诊断报告

完成日期：2026-10-24。目录：原 A/B/C 实验根目录下的 `phase_b_diagnosis_32states`。使用 GPU1，已释放；**新增训练更新 0 次，新增 Codex 请求 0 次**。

**2026-10-24 核查更正：**进一步对照原论文、官方实现及完整代码 token 后，发现原 `show_contacts` 案例在更早的 `.phone` 位置已受到强烈压制，不能仅凭后两个 token 判定整个错误调用被强化。以下已更正；原概率数据未变。原 SDPO 本身也沿学生原回答前缀蒸馏，不应将这一点称为本地独有实现错误。详见 [论文与实现核查](implementation_audit/REPORT.md)。

## 结论

**两个问题都存在：C2 教师能够纠错，但能力不稳定且随训练退化；原错误回答前缀上的蒸馏，又会把一些原本有效的反馈变成错误或很弱的动作监督。** 最终学生还出现了原有业务动作的退化。

更有辨识力的反向动作信号来自实际 B checkpoint 的重复 Venmo 文档案例：决定 `show_api_descriptions` 的 `_des` 位置，历史学生概率 **26.80%**，C2 教师 **73.03%**，此前代码部分没有明显的更早纠错分叉。对于 `phone.show_contacts`，虽然后两个 token 得到正向信号，但更早的 `.phone` 已被教师从学生的 **81.76%** 压到约 **0.0058%**；它不能作为整个错误调用被强化的证据。两者都还不是模型共享参数实际更新后的动作频率测量。

另一个样本的历史蒸馏 loss 为 **0.5040**，但 **超过 99.99% 的 KL 值集中在实际代码之前**；原重复查询方法在教师下的概率仍接近 100%。因此，loss 非零、下降、数值正常，不能证明动作得到了有效纠错监督。

**建议停止现版 B 的直接续训。保留“FAIL → 反馈 → 纠错”的方向，下一步优先验证：让固定教师生成纠正后的新动作，执行验收，再让无反馈学生学习这个新动作。** 本次未启动该训练。

## 1. 实际做了什么

从 B 的 train90 轨迹抽取 32 个状态，任务全局不重复，不使用 dev57 抽样。四类各 8 个，每类第 1/2 轮来源各 4 个：

| 类别 | 抽样条件 |
|---|---|
| R1 | 执行错误，有实际 traceback，无 R6 FAIL；可伴随其他 FAIL |
| R6 | 重复已有文档查询，且被原 Codex 反馈判为 R6 FAIL |
| R8 | 缺少规范、分页等协议问题，无 R1/R6 FAIL，原动作为非认证业务调用 |
| clean | ZeroFail、PASS≥3、无 U、非重复的业务动作 |

按种子 20261024 的 SHA256 排序选择；限定原目标步≤35、原 prompt≤22000 token，给短续跑留空间。实际 prompt 为 3159–17552 token。候选池与选择顺序见 `config/manifest.json`，逐状态见 `STATE_INDEX.csv`。

每个分支都在新 AppWorld 进程中重放真实历史动作，恢复 Python 变量、数据库和 API 状态。**32 个基准回放、144 个比较分支全部通过历史 observation 和完整状态摘要一致性检查。** C0/C2 首步 token 与 B 保存的输入完全相等；C2 复用原反馈和渲染器，不引用完整原回答。24 条反馈中仅 1 条标记使用后续证据，该元数据保留。

比较条件：初始 Qwen3-8B 的 C0/C2、最终 EMA 教师的 C0/C2、最终学生的 C0。干净状态只做 C0。EMA 是第 36 次更新后的已有教师权重，精确导出，无新更新。

共 **144 个分支、565 个实际生成动作**。temperature=0，每个分支最多首步+3个后续动作，沿用 3000-token 单步、32000-token 上下文限制。C2 只在首步提供；后续用同一模型和新产生的真实历史继续，移除针对旧动作的反馈。短续跑不等于完整任务评测。

此外，在所有固定状态上检查原回答 token 概率；对 24 个 FAIL 状态读取其原 batch 更新前的学生/EMA checkpoint，复算当时真正使用的 SDPO loss。

## 2. 教师本身能否纠错

### 2.1 首步局部修复

以下是逐例人工复核，**不是新的独立 Codex 评分，也不是 ZeroFail 或任务成功率**。Y 表示首步可执行，并修复主要问题或补充必要前提；U 保留间接准备、部分修复的歧义。一个 Y 仍可能有其他协议问题，也不保证下一步成功。逐例理由及残余问题已保存于 `analysis/manual_first_step_review.json`。

| 条件，均为相同的 24 个 FAIL 状态 | 明确局部修复 Y | 未修复 N | 不确定 U |
|---|---:|---:|---:|
| 初始模型，无反馈 C0 | 2 | 22 | 0 |
| 初始模型，具体反馈 C2 | **15** | 7 | 2 |
| 最终 EMA 教师，具体反馈 C2 | **12** | 10 | 2 |

分类型看，初始 C2 → 最终 EMA C2 的 Y 数量为：**R1 7→7，R6 4→2，R8 4→3**，各组分母均为 8。两个 U 均来自 R8 组。初始 C2 的 15 个 Y 中有 12 个保留、3 个退化，没有新增 Y。

这支持反馈有实际价值，也说明教师输出需要逐条验收。这里的 15 个 Y 不能直接当作 15 条合格 SFT 样本。

### 2.2 自动执行指标

| 条件，FAIL 状态 n=24 | 首步执行错误 | 首步纯文档查询 | 首步全部为已见过的文档查询 | 四步内出现成功业务 API 调用 |
|---|---:|---:|---:|---:|
| 初始 C0 | 9 | 7 | 7 | 14 |
| 初始 C2 | 3 | 12 | 1 | 15 |
| EMA C0 | 3 | 13 | 10 | 9 |
| EMA C2 | 3 | 17 | 5 | 10 |
| 最终学生 C0 | 5 | 14 | 8 | 5 |

“重复文档”自动指标只识别真实历史中相同字面参数、且整步都是旧查询的情形；混入一个新查询的重复、初始示例已提供的文档等需要人工另查。因此它是保守的行为指标，不是完整 R6 评分。

“成功业务 API 调用”指非认证业务接口实际返回成功，**不保证对象、范围、最终任务选择正确**。查必要文档和认证准备本身也可以是有效修复，不能只按业务调用数评分。

### 2.3 干净状态对照

| 无反馈 C0，clean n=8 | 首步出现成功业务 API 调用 | 首步执行错误 | 四步内出现成功业务 API 调用 |
|---|---:|---:|---:|
| 初始模型 | 8 | 0 | 8 |
| EMA 教师 | 8 | 0 | 8 |
| 最终学生 | **5** | **1** | 7 |

其中 `clean_b016_22cc237_2_s15` 的最终学生直接使用尚未定义的 `phone_access_token`，产生 NameError；原始模型与 EMA 能从实际存在的 `login_result` 取得 token 后查询。另两个首步分别绕去查文档、打印已存在的登录结果。这两个延迟动作不直接判作错误，但显示实际学生没有完整保留原来的业务行动方式。

这组结果同时限定了结论：EMA 在这些准备充分的业务状态中仍能正常行动；最终学生的退化更重。不能把所有现象归结为“教师完全不会做任务”。

## 3. 原错误前缀上的蒸馏发生了什么

当前 B 的 FAIL 分支近似计算：

\[
L_{\mathrm{SDPO}}=\frac{1}{|y^-|}\sum_t D_{\mathrm{KL}}\left[
\pi_\theta(\cdot\mid x,y^-_{<t})\;\|\;
\pi_{\mathrm{teacher}}(\cdot\mid x,f,y^-_{<t})
\right].
\]

这里 x 是原状态历史，f 是 Codex 反馈，y⁻ 是原来的失败回答。实现使用 student top100+tail。

**C2 没有把完整原回答作为一段引用放进 prompt；但是 teacher forcing 仍然逐 token 接回原回答的前缀。** 所以，自由生成“老师看反馈会怎么做”，和训练时“老师沿着已走偏的原回答继续预测”，是不同的条件分布。

FAIL 标签负责将样本送入这一分支；loss 要求学生接近教师分布。教师若在这个条件下继续偏好错误动作，KL 就会传递错误目标。

### 案例 A（已更正）：教师在较早分叉纠错，随后仍会补完错误路径

状态：`R1_b025_29caf6f_3_s01`。原动作：

```python
print(apis.phone.show_contacts())
```

真实执行报告该 API 不存在。原 Codex 反馈明确要求先发现联系人搜索接口、检查规范。初始模型和 EMA 的 C2 自由生成首步都是：

```python
print(apis.api_docs.show_api_descriptions(app_name='phone'))
```

这一动作实际执行成功。但强制接上原回答叙述和 `print(apis.phone` 前缀后，接下来错误方法名 `.show_contacts` 两个 token 的条件联合概率是：

| 模型/条件 | P(`.show_contacts` ∣ 原前缀) |
|---|---:|
| 初始模型 C0 | 52.27% |
| 初始模型 C2 | **92.38%** |
| B 当时的学生 C0 | 73.21% |
| B 当时的教师 C0 | 59.85% |
| B 当时的教师 C2 | **90.42%** |

实际历史 KL 在这两个 token 上的局部方向都提高原错误 token 概率，但进一步检查更早的 `.phone`，历史学生概率为 **81.76%**，C2 教师仅约 **0.0058%**，局部方向强烈压制该错误路径。整个原代码在教师/学生条件下的概率比约为 **8.80e-5**。因此不能把末尾两个 token 的方向扩大成整个错误动作的方向；此前据此称本例蒸馏目标有害的解释过强。

这个案例说明 on-policy teacher forcing 的正常现象：教师可能在较早分叉要求改路，但在被强制走过那个分叉之后，仍按既定代码结构补完。方法是否有效需要检查完整行动分叉，而不能要求失败回答每个 token 都受到惩罚。

这里的“联合概率”只针对这两个连续 token，在给定原前缀条件下计算，不是完整错误动作被自由生成的概率。梯度方向为局部 logits 上的分析，不等于已执行一次模型参数更新。

### 案例 B：loss=0.504，实际代码几乎没有纠错信号

状态：`R6_b018_aa8502b_1_s05`。原动作重复查询 Supervisor API 列表。反馈要求改为读取已知凭据接口的完整规范。初始和 EMA 教师 C2 自由生成都正确选择：

```python
print(apis.api_docs.show_api_doc(
    app_name='supervisor', api_name='show_account_passwords'))
```

但原回答叙述说“Let's check the available APIs”，代码仍是 `show_api_descriptions`。沿这个原前缀计算：

- 历史 step SDPO loss：**0.5040078**；复算为 **0.5040077**。
- 代码部分平均 KL：**0.00000395**。
- **99.99975%** 的 KL 值位于代码之前的解释文字及开头围栏。
- 历史教师 C2 对原方法关键 token `_des` 的概率仍约 **99.985%**；后面的 `criptions` 近乎确定。

KL 的区域占比不是参数梯度范数占比，前面的行动叙述被纠正也可能影响之后生成的代码。这个统计说明代码部分缺乏明显纠错差异，不能单独判定整个样本无效。把 loss 仅限制到代码上也不会自动修复错误条件前缀，可能只剩几乎为零的监督。

### 案例 C：重复查询得到反方向信号

状态：`R6_b014_60d0b5b_1_s17`。初始/EMA C2 自由生成都能按反馈查询 `venmo.create_transaction` 的新规范，取代重复的 Venmo API 列表。

在原回答前缀上，历史学生给 `show_api_descriptions` 的关键 token `_des` **26.80%** 概率，历史教师 C2 却给 **73.03%**。局部 KL 下降方向提高这个重复查询 token 的概率。单纯降低学习率或缩小 λ 可以减弱这条更新，但不会将这个目标变成正确动作目标。

完整代码复查未发现 phone 案例那样更早的强压制：前面的代码 token 均接近确定，代码独立 logits 下降下原 token logprob 导数之和约 **+0.571**，完整回答约 **+1.589**。这加强了本例原前缀监督不可靠的证据，但仍不等于一次实际模型参数更新或整体训练退化的因果证明。

### 对照：有些错误确实得到正确信号

`R1_b023_e85d92a_2_s11` 的非法 `page_limit=50` 是正例。自由生成 C2 改为合法的 20，并实际执行成功。在原前缀中，非法数字首 token `5` 的概率从历史学生约 **0.001496** 降到历史教师 C2 的 **4.14×10⁻⁸**，KL 的局部方向也在压制它。

所以不能说 SDPO 对所有 FAIL 都失效。局部参数错误、需要补前提、需要换行动路线、需要插入分页循环，产生的监督难度不同；同属 R1 的样本也不能一概处理。

## 4. 教师漂移的具体证据

**相册检索，`R6_b031_c901732_1_s14`：**原状态已经反复读过 `search_albums` 规范。初始 C2 能直接检索 “Echo Chamber Chronicles”，取得真实相册结果；最终 EMA C2 却连续四步重复同一规范查询。在同一个原错误代码前缀下，选择文档分支的 `.api` token 概率也从初始教师 C2 的 **1.41%** 上升到最终 EMA C2 的 **90.43%**。这既有自由执行证据，也有固定前缀概率证据。

**分页纠错，`R8_b025_2a163ab_2_s29`：**初始 C2 写出了 `page_index` 循环，按真实列表响应遍历到空页，执行成功。最终 EMA C2 虽然也写循环，却虚构 `contacts_page['success']` 字段，把列表当字典处理，首步 TypeError。这里教师退化影响的是用户关心的当前一步，不只是长程任务结果。

**教师本来就有局限，`R1_b015_07b42fd_3_s07`：**反馈要求取得真实凭据、登录后再访问 `login_result`；两个教师的 C2 首步仍复制了演示中的假密码并认证失败。执行验收应过滤这种答案，不能因它“看起来响应了反馈”就用于学习。

## 5. 数值与实现核验

- 24 个 FAIL 状态的历史 B loss 全部复现；最大绝对偏差 **4.24×10⁻⁸**，平均 **1.64×10⁻⁸**。这表明关键反例来自当时真实使用的权重、输入和目标。
- 历史 top100+tail KL 与全词表 KL 的比值，最低 **99.99849%**、平均 **99.99983%**。这 24 例没有显示 top-k 截断是主要原因。
- 32 个原回答文本/token 对齐全部检查；独立局部梯度公式与原 `b_loss.py` 自动微分结果一致，包含 tail token 和完整 logits 梯度对目标 token 概率的方向。
- vLLM 与 Transformers 在生成相同前缀的 110 个比较中，平均的逐例 logprob MAE 为 0.00261；历史 loss 复现使用与 B 相同的 Transformers/SDPA/BF16 autocast 路径。
- 概率模型峰值 GPU allocation 为 **18.29 GiB**；所有模型参数梯度均为 None，未创建或执行模型优化器更新。GPU1 当前已释放。
- EMA 适配器第一次加载时因缺少 tokenizer 模板，在生成前失败。已在诊断专用目录补齐与 base 完全相同的 tokenizer/模板并恢复；不改变权重、样本、反馈或已完成的 base 结果。最终 144 分支均有效。

这些核验不支持把本次反例归因于输入错位、权重错用或 KL 符号实现错误。它不能量化 SFT 与 SDPO 各自对最终退化的因果贡献：仍然没有 SFT-only 训练对照，也没有在本次执行任何模型参数更新。

## 6. 下一步建议

### 优先做：经执行验收的纠错答案学习

1. **从 B 的初始学生重新开始小试验，固定初始教师。** 暂不从当前最终学生继续训练，也暂不让教师随学生做 EMA 更新。
2. 保留原 C2 反馈方式，让教师自由生成新的纠正动作 y⁺。先验收首步执行、主要 FAIL 是否修复、是否引入明显新违规。必要且首次获取的文档/认证前提可以合格；原样重复查询不合格。后续三步作为辅助观察，**不要求完成整题才接纳一个有效首步**。
3. 使用原始无反馈状态 x，让学生学习 **y⁺**。第一轮采用简单的修复 SFT；如果以后再试 soft distillation，也先沿已验收的 y⁺ 前缀检查教师目标。这个改变应称为纠错答案蒸馏/修复 SFT，不混称为当前原前缀 SDPO 的同一实现。
4. 做一个小规模固定数据试验：例如 16 条已验收纠错动作，加等量干净业务动作作为保留能力的样本；每个状态只保留一个合格目标，避免重复文档淹没业务动作。数据不足就减少规模，不能凑数接纳失败教师答案。
5. 为辨别修复样本的增益，设置同初始化、同更新预算的短对照：干净业务 SFT；干净业务 SFT + 修复 SFT。先做约 5–10 次更新的机制验证，在第 2/5/10 次检查无反馈首步修复、重复查询和干净业务状态。学习率可先保守设为 1e-5、保留原 LoRA 设置；这是待验证配置，不是本次已经证明的最优值。
6. 另取未用于该小试验训练的新固定状态作为诊断验证集。本次 32 状态已用于选方向，不把在它们上面的再提升当作独立泛化证据。通过局部纠错与保留能力检查后，再投入完整 dev57 评估。

可以保留“只对有可靠局部纠错信号的错误使用原前缀 SDPO”作为后续研究分支，但不要立即混回全部 FAIL，更不要先做一轮大规模 λ/学习率搜索。先解决教师目标是否正确的问题。

**继续价值的判断：**反馈让初始模型产生有效首步，这条证据仍然成立；当前目标会在可验证的案例中强化错误，直接追加原 B 训练不划算。若一个短而有对照的“已验证 y⁺ 学习”试验仍无法让无反馈学生改善、或持续损害干净动作，就不再投入完整 90 题两轮在线训练的资源。

### 结论边界

本次是有意平衡的 32 状态机制诊断，采用单次贪心生成，不能估计自然错误分布的成功率。人工 Y/N/U 复核知道实验条件，属于可追溯的事后分析；新候选没有独立完整 v7 评分。局部 logits 梯度不等于共享模型参数实际更新后的概率变化。短续跑没有重新计算完整 dev57 TGC，也没有证明某个改进方案已能提升最终任务成功率。

## 文件索引

- [repeat_docs_8case_analysis/REPORT.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/repeat_docs_8case_analysis/REPORT.md)：全部 8 个重复文档案例的三问题逐例核查；历史代码信号为 1 例反向、4 例近乎一致、3 例压制原代码，区分有效修复与停止查询后报错。
- [PROTOCOL.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/PROTOCOL.md)：协议和执行口径。
- [STATE_INDEX.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/STATE_INDEX.csv)：固定的 32 个状态。
- [analysis/behavior_by_branch.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/analysis/behavior_by_branch.csv)：144 分支行为统计。
- [analysis/manual_first_step_review.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/analysis/manual_first_step_review.json)：72 条首步人工复核及残余问题。
- [analysis/case_audit_sanitized.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/analysis/case_audit_sanitized.json)：各条件的脱敏代码、观察和调用记录。
- [analysis/key_token_audit.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/analysis/key_token_audit.json)：错误相关位置的条件概率与局部方向。
- [analysis/historical_loss_reproduction.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/analysis/historical_loss_reproduction.json)：24 个历史 batch loss 的复算证据。
- [verification.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/verification.json)：完整性、来源未改动、无新训练更新核验。
