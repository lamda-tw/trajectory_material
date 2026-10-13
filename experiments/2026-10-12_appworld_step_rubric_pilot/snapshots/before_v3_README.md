# AppWorld base 轨迹逐步 rubric 试评分

日期：2026-10-12（北京时间）。**已完成 v1 与 v2 两轮真实评分和证据复核。** 每轮 6 条完整轨迹，成功 3 条、失败 3 条，共 66 步。此抽样用于发现问题，不用于估计全量评分准确率。

方案和 prompt 的源文件继续维护在 [plans 目录](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/README.md)。本目录保存运行脚本、冻结快照、真实评分及复核。任何 prompt 修改都创建新版本文件，不覆盖已运行版本。

[完整实验报告](REPORT.md) · [逐轨迹对照](review/TRAJECTORIES.md) · [版本比较 JSON](review/comparison.json)

## 数据与判断方式

来源：[原始 Qwen3-8B 的 train90 采样](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts)。覆盖闹钟调整、便签修改、歌单时长计算；包含执行报错、恢复、无代码终止、围栏异常。选样理由和原始 SHA256 见 [manifest.json](manifest.json)，官方结果仅供研究者选样与事后分析。

每次请求读取一条完整准备输入，输出所有步骤的 R1—R8 标签和短证据。使用现有实验的 `gpt-5.6-sol`、`high` 配置，最多同时 2 个请求。无 GPU、无轨迹重放、无训练；不合成 reward 或权重。

## 版本与输入修复

评分 prompt v1 的原文件与 SHA256 保持不变。输入适配器另存为 `prepare_input_v2.py`，匹配原采样运行器“优先第一个闭合 Python 围栏，否则首个未闭合 Python 围栏”的提取规则，修复 `302c169_3__03` 第 10 步被孤立围栏干扰的问题。输入版本与 prompt 版本分别记录。

## 文件入口

- [输入验证](input_validation.json)：全部 base 轨迹的兼容性、源文件哈希与已有输入回归检查。
- [样本清单](manifest.json)、[完整评分输入](inputs/)：清单不能附给 judge。
- [冻结快照](snapshots/)：prompt、schema 和输入脚本。
- [调用配置](judge_config.json)、[执行脚本](scripts/run_judge.py)。
- [首轮 v1 有效结果](runs/v1_audit_recovered/)：逐条 request、原始响应、事件、耗时和有效判断。
- [复核材料](review/)：后续人工式证据复核及版本对比，不反馈给同轮 judge。

## 执行与验收

输入准备：`python scripts/prepare_pilot.py`（已存在输出时拒绝覆盖）。
真实评分：`python scripts/run_judge.py --execute --run v1_audit`（新运行目录，不覆盖旧结果）。

工具、浏览、插件和多代理调用关闭，judge 工作目录为空；事件日志再次检查是否使用了工具。只把准备后的输入送入请求，移除官方结果及 token/logprob 训练数组。完整 JSON Schema 含 tuple/条件约束，本轮不把它作为 API 的受限结构 schema 提交，而在返回后本地严格检查；没有更改 v1 输出格式。参考 [OpenAI structured outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs)。

验收检查包括 JSON/schema、轨迹 ID、step 完整性和顺序、证据引用及每个 F/U 的解释覆盖。错误尝试保留，最多 2 次；不静默改写模型标签。结构验收不等于语义评价正确。

已按发现的问题创建 v2 并对相同六条输入完成重评：开发检查点 v1 为 24/28、v2 为 27/28，但有一处重复搜索判定回退。v2 仍是候选版本，不代表独立准确率或稳定批量评分标准。以后修改建立 v3。长输入与 batch 模式尚未实测。

v2 调用示例（必须使用新的运行目录）：`python scripts/run_judge.py --execute --run NEW_RUN_NAME --prompt snapshots/prompt_v2.txt --schema snapshots/output_schema_v2.json`。

验收器的 disabled Code Mode 提示误判已修复，首次两条响应复用，两个错误重试取消；原始记录保留，详情见报告。
