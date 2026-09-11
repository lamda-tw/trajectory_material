# Qwen3-8B SWE-bench Lite zero-shot smoke report

## 结论

本实验完成了 3 道 SWE-bench_Lite/dev 题的本地 Qwen3-8B zero-shot 推理。三道题都产生了包含 diff 的原始文本，但严格解析后的结果为：

| 任务 | 严格补丁状态 | 功能结论 |
|---|---|---|
| marshmallow-code__marshmallow-1343 | 可应用，1 个源码文件 | 题面最小复现仍触发原始 TypeError，失败 |
| marshmallow-code__marshmallow-1359 | no_effect | 旧行和新行相同，最终预测为空 |
| pvlib__pvlib-python-1072 | check_failed | unified diff 的 hunk 行数错误，严格预测为空 |

这不是官方 SWE-bench 分数。当前主机没有 Docker 命令和官方逐题运行环境，无法使用数据中声明的官方镜像完成权威判题。按本实验的严格补丁协议，没有一道题得到成功证据。

第 3 题另做了格式诊断：原始输出在仅增加 git apply --recount 后可以应用，说明失败来自 diff 格式而非源码上下文不匹配；该派生补丁未写回 predictions.jsonl，也不计入严格结果。

## 实验定义

- 模型：/root/autodl-tmp/models/Qwen3-8B
- 推理环境：/root/autodl-tmp/workspace-tw/.conda-training
- 数据：SWE-bench_Lite/dev
- 数据 revision：b0dde1093fe417d83b7184254edf8199c1f0dff5
- 样本数：3
- 解码：greedy，do_sample=false，thinking=false
- 最大输入：32768 tokens
- 最大输出：3072 tokens
- 随机种子：20260910
- GPU：CUDA_VISIBLE_DEVICES=0
- 任务隔离：每题独立 base_commit worktree

本实验是 retrieved-context single-turn baseline，不是完整工具型 Agent。检索器仅使用题面中出现的文件名和标识符对基准 commit 中的源码排序，最多放入 8 个文件、105000 个字符。模型没有接触示例、参考 patch、test_patch、FAIL_TO_PASS 或 PASS_TO_PASS。

## 推理结果

| 任务 | 输入 tokens | 输出 tokens | 推理秒数 | 变化文件 |
|---|---:|---:|---:|---|
| marshmallow-code__marshmallow-1343 | 22496 | 167 | 5.966 | src/marshmallow/schema.py |
| marshmallow-code__marshmallow-1359 | 24156 | 160 | 5.403 | 无 |
| pvlib__pvlib-python-1072 | 28201 | 220 | 7.492 | 无严格补丁 |

模型加载后，三题合计纯生成时间约 18.9 秒。

## 分题分析

### marshmallow-code__marshmallow-1343

模型修改了 BaseSchema 中更新字段缓存的条件，但实际异常发生在 _invoke_field_validators 对 None 执行下标访问的位置。模型补丁可以被 Git 应用，却没有触达根因。

官方 test_patch 已在推理结束后由独立检查步骤应用。本机 pytest 没有进入项目测试：pytest 8.4.2 导入时发现实际 pluggy 为 1.0.0，缺少 HookimplOpts。随后使用同一 Python 并仅在进程内添加 Python 3.12 的 collections 兼容别名运行题面复现，仍然得到原始 NoneType TypeError。因此该题有直接的功能失败证据。

### marshmallow-code__marshmallow-1359

模型输出的减号行和加号行完全一致。Git 可以读取这段 diff，但工作区没有任何变化，最终 SWE-bench model_patch 为空。这属于生成内容 no-op，不是解析器遗漏。

### pvlib__pvlib-python-1072

模型把时差转换改成先转 timedelta64 秒再转浮点小时，方向与问题根因一致。但输出的 hunk 声明为 7 行，正文实际行数不符，普通 git apply 报 corrupt patch。

仅用于诊断的 git apply --recount 检查和应用均成功，派生补丁保存在 patches 目录并带 recount-diagnostic 后缀。由于 .conda-training 没有 pandas，题面复现没有进入 pvlib；本实验不声称该派生补丁功能通过。

## 判题与环境限制

本机的共享 .conda-training 是模型推理环境，不是 SWE-bench 项目运行环境：

- pytest 8.4.2 与实际 pluggy 1.0.0 不兼容；
- Python 为 3.12，而旧 Marshmallow 使用已移除的 collections.Mapping；
- 环境没有 pandas，无法运行 pvlib 题面复现；
- 主机没有 Docker 命令，不能直接运行数据记录的官方逐题镜像。

因此 checks/local_checks.json 明确标记 authoritative=false。pytest 的退出码不能解释成模型测试失败；第 1 题的失败结论来自单独越过兼容问题后的目标复现。

## 产物

- config.json：固定实验设置
- data/selected_tasks.jsonl：精确的公开模型输入
- prompts：完整渲染 prompt 与检索文件清单
- outputs：未经修正的模型原始输出
- patches：严格补丁及第 3 题的 recount 诊断补丁
- predictions.jsonl：严格 SWE-bench 预测文件
- metadata/inference_summary.json：token、耗时、文件与补丁状态
- checks/local_checks.json：非权威本机测试结果
- logs：准备与测试日志
- scripts：工作区准备、推理、检查脚本
- worktrees：本次题目工作区
- worktrees_partial_clone_failure：首次 partial-clone 二次复制失败的保留诊断现场

## 如何复现

执行 README.md 中的三个命令：准备 worktree、运行本地模型推理、运行非权威检查。重新运行推理前必须准备新的干净 worktree，因为当前 worktree 已包含模型补丁或 grader test patch。

## 下一步建议

这次 smoke 已证明本地模型加载、题面选择、源码检索、prompt 渲染、补丁提取和预测落盘可以跑通。要得到可比较的正式成绩，下一步应接入官方 SWE-bench Docker harness，并将生成方式升级为允许搜索、读文件、编辑和运行测试的多轮 Agent。对于 8B 模型，还应加入确定性的 diff 格式校验与一次格式修复机会，但必须固定规则并在所有模型上保持一致。
