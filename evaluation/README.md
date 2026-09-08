# Evaluation 评分工具

`eval` 是仓库的统一评分命令。当前已注册的评分能力是
`simulation/ei`；单次 EI 评分同时产生 O2 成效分、关键5项的三种口径和
全项原始分。

18 个校验规则、O2 最终业务成效分和五指标聚合的完整实现说明见
[`src/simulation/ei/rules.md`](src/simulation/ei/rules.md)。

下文除 Linux/macOS 专用小节外，命令均在仓库根目录
`Eval4OptAgent/` 中执行。

## 1. Windows PowerShell：首次安装

以下整段可直接复制：

```powershell
python -m venv .\evaluation\.venv
& .\evaluation\.venv\Scripts\python.exe -m pip install -e .\evaluation
$evalCli = (Resolve-Path .\evaluation\.venv\Scripts\eval.exe).Path
$evalRuntime = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$env:EVAL_NODE = Join-Path $evalRuntime "node\bin\node.exe"
$env:EVAL_NODE_MODULES = Join-Path $evalRuntime "node\node_modules"
& $evalCli --help
```

以后新开一个 PowerShell 窗口时，只需先执行：

```powershell
$evalCli = (Resolve-Path .\evaluation\.venv\Scripts\eval.exe).Path
$evalRuntime = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$env:EVAL_NODE = Join-Path $evalRuntime "node\bin\node.exe"
$env:EVAL_NODE_MODULES = Join-Path $evalRuntime "node\node_modules"
```

下文 PowerShell 示例都使用这个 `$evalCli` 变量。

## 2. Linux/macOS：首次安装

```bash
python3 -m venv ./evaluation/.venv
./evaluation/.venv/bin/python -m pip install -e ./evaluation
EVAL_CLI=./evaluation/.venv/bin/eval
EVAL_RUNTIME="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
export EVAL_NODE="$EVAL_RUNTIME/node/bin/node"
export EVAL_NODE_MODULES="$EVAL_RUNTIME/node/node_modules"
"$EVAL_CLI" --help
```

## 3. 最常用的六条命令

### 3.1 单个运行评分

只需传入运行目录。命令会回显五个分数，并写入该运行的
`scores/`，不生成 XLSX 报告。

```powershell
& $evalCli score run ".\eval_results\EI-56TESTPK0009-hard-v1.2_claude_qwen36-27b_noskill_0810A"
```

### 3.2 预览将要评分的运行

`--preview` 只输出选择结果，不评分、不写分数、不生成报告。

```powershell
& $evalCli score batch --root .\eval_results --task EI --model "gpt5*" --harness codex --skill noskill --repeat latest --preview
```

### 3.3 批量评分，不出报告

```powershell
& $evalCli score batch --root .\eval_results --task EI --model "gpt5*" --harness codex --skill noskill --repeat latest --jobs 6
```

### 3.4 批量评分并立即生成报告

这是“评分 + 聚合 + EI XLSX”一条龙命令。

```powershell
& $evalCli score batch --root .\eval_results --task EI --model "gpt5*" --harness codex --skill noskill --repeat latest --jobs 6 --report
```

### 3.5 基于每个运行的最新分数，只生成报告

这条命令不重新执行 rules。

```powershell
& $evalCli report --root .\eval_results --task EI --model "gpt5*" --harness codex --skill noskill --repeat latest --score-id latest
```

### 3.6 使用仓库内的 selector 示例

先预览：

```powershell
& $evalCli score batch --selector .\evaluation\selectors\ei-noskill-example.yaml --preview
```

确认选择结果后，评分并出报告：

```powershell
& $evalCli score batch --selector .\evaluation\selectors\ei-noskill-example.yaml --jobs 6 --report
```

### 3.7 实时进度和静默模式

默认情况下，批量评分使用单行动态进度条。进度条右侧同时显示
已完成数、总数、百分比和最新完成的运行结果。命令还会显示：

- 正在扫描的根目录和最终选中数量；
- 批量评分的当前序号、总数、运行名和状态；
- 每个运行的 O2、关键分段分和全项分；
- `score_id`、批次审计文件和单运行分数文件位置；
- 报告聚合进度、XLSX 渲染状态、`report_id` 和产物目录；
- 可定位到具体运行的失败原因。

示例：

```text
[选择] 扫描完成：发现 337 个，筛选后 20 个，最终选中 20 个运行 / 20 个分组，repeat=latest
[评分] score_id=20260814153045 | 实际题目并行度=6
评分 [██████░░░░░░░░░░░░░░░░░░] 5/20  25.0% | 最新完成：EI-... | O2=70.00 | 分段=68.40 | 全项=80.10
[XLSX] 正在生成并渲染 9 个 Sheet，这一步可能需要几十秒……
[完成] 报告生成完成：report_id=0814A
       XLSX=D:/.../eval_reports/0814A/EI推演打分-0814A.xlsx
```

人读进度写入 stderr，最终机器可读 JSON 仍单独写入 stdout，因此脚本
可以安全捕获 JSON。在交互终端中，进度条原地刷新，不会为每个运行
新增一行；当 stderr 被重定向到日志或 CI 时，自动改为逐行输出，
便于事后审计。自动化脚本不需要人读进度时，在任意命令末尾加
`--quiet`：

```powershell
& $evalCli score run ".\eval_results\EI-56TESTPK0009-hard-v1.2_claude_qwen36-27b_noskill_0810A" --quiet
& $evalCli score batch --root .\eval_results --task EI --skill noskill --repeat latest --jobs 6 --quiet
& $evalCli report --root .\eval_results --task EI --skill noskill --score-id latest --quiet
```

## 4. 命令结构

```text
eval
├─ score
│  ├─ run RUN_DIR     # 评分一个运行，不生成 XLSX
│  └─ batch           # 选择并评分一批运行，可选 --report
└─ report              # 从已有分数生成 EI XLSX
```

没有独立的 `aggregate` 命令。聚合是 EI 报告合同的一部分：

- `score run` 在单运行评分时计算五个单题聚合分；
- `score batch --report` 在评分后执行跨 repeat、跨题聚合并生成报告；
- `report` 读取已有分数，执行聚合并生成报告。

## 5. `score run`：单运行评分

完整语法：

```text
eval score run RUN_DIR
```

`RUN_DIR` 必须是单次评测运行目录，如：

```text
eval_results/EI-56TESTPK0009-hard-v1.2_claude_qwen36-27b_noskill_0810A/
```

题目、模型、Harness、skill 和执行时间均从目录名和
`run_metadata.json` 读取，不需要再通过参数重复指定。

命令回显 JSON 中的 `scores` 包含：

```json
{
  "effectiveness.o2": 70.0,
  "key.raw": 84.2,
  "key.discrete": 68.0,
  "key.piecewise": 68.4,
  "all.raw": 80.1
}
```

此处数字只是字段结构示例，不是预置模型得分。

## 6. `score batch` 和 `report` 的共用选择参数

| 参数 | 可重复 | 含义 |
|---|---:|---|
| `--root DIR` | 是 | 扫描的运行根目录；省略时默认扫描 `<repo>/eval_results` |
| `--task PATTERN` | 是 | 子任务，如 `EI` 或 `OPT` |
| `--question PATTERN` | 是 | 题目及版本 |
| `--model PATTERN` | 是 | 模型 |
| `--harness PATTERN` | 是 | Harness，如 `codex`、`claude`、`cowork` |
| `--skill PATTERN` | 是 | skill 版本，未使用 skill 时为 `noskill` |
| `--run PATTERN` | 是 | 完整运行目录名 |
| `--repeat latest\|average` | 否 | 重复运行取最新值或平均值；默认 `latest` |
| `--preview` | 否 | 只输出最终选择，不评分、不生成报告 |
| `--selector YAML` | 否 | 使用 YAML 定义选择；不可与上述 root/筛选/repeat 参数混用 |
| `--quiet` | 否 | 关闭 stderr 人读进度，仅保留 stdout 最终 JSON |

筛选逻辑固定为：

- 不同字段之间是 AND；
- 同一字段重复传入时是 OR；
- 模式匹配不区分大小写，支持 `*` 和 `?`；
- repeat 分组键固定为
  `(任务, 题目及版本, 模型, Harness, skill)`。

### 6.1 `score batch` 独有参数

| 参数 | 含义 |
|---|---|
| `--jobs N` | 并行处理的题目数；默认 `6`，最小 `1`，最大 `24` |
| `--report` | 评分全部成功后继续生成 EI XLSX |

EI 聚合策略内嵌在当前 `ruleset.yaml`，与规则实现一起由 ruleset release
原子发布；评分命令不接受外部聚合配置覆盖。

`--jobs` 是同时处理的最大题目数。同一道题的多个模型或重复运行会在
同一个 worker 中串行评分，复用该题已解析的 Excel、标准化权威证据和
规则准备结果。如果只选中 3 道不同题目，即使传入 `--jobs 6`，实际题目
并行度也是 3；如果 200 个运行只来自 2 道题，实际题目并行度就是 2。
请求值与实际值都会写入 `results.json`。

默认并行度：

```powershell
& $evalCli score batch --root .\eval_results --task EI --skill noskill --repeat latest --jobs 6
```

最大并行度：

```powershell
& $evalCli score batch --root .\eval_results --task EI --skill noskill --repeat latest --jobs 24
```

### 6.2 同时选多个模型

以下会选择 GPT-5 系列、Fable5 和目录中以 K3 结尾的模型：

```powershell
& $evalCli score batch --root .\eval_results --task EI --model "gpt5*" --model fable5 --model "*k3" --skill noskill --repeat latest --preview
```

### 6.3 指定题目和 Harness

```powershell
& $evalCli score batch --root .\eval_results --task EI --question "EI-56TESTPK0009-*-v1.2" --harness claude --skill noskill --repeat latest --preview
```

### 6.4 同时扫描多个根目录

```powershell
& $evalCli score batch --root .\eval_results --root D:\evaluation_archive\runs --task EI --skill noskill --repeat latest --preview
```

### 6.5 对 repeat 求平均

`average` 会保留每个 repeat 组内的所有运行。报告先对组内运行
求平均，再跨题按一题一票求平均。

```powershell
& $evalCli score batch --root .\eval_results --task EI --model "gpt5*" --skill noskill --repeat average --jobs 6 --report
```

### 6.6 评分版本锁定

`score run` 和 `score batch` 都不接受外置聚合配置。EI 的 adapter、resolver、
rule 与聚合策略作为同一个 ruleset release 发布；题目 profile 只能依赖当前
`ruleset_release`。评分结果同时记录 release、题目根目录，以及实际使用的
profile、prompt、manifest 和输入来源路径，供评分证据追溯。

## 7. `latest` 和 `average` 的区别

假设同一题、同一模型、同一 Harness、同一 skill 有 A/B/C 三次运行：

- `--repeat latest`：只选择执行时间最新的一次；
- `--repeat average`：选择三次，报告中先对三次的每个指标求算术平均。

`latest` 比较的是规范化运行元数据中的执行日期、轮次和精确时间，
不是分数目录的创建时间。

## 8. 只出报告

### 8.1 读取每个运行的最新分数

```powershell
& $evalCli report --root .\eval_results --task EI --model "gpt5*" --skill noskill --repeat latest --score-id latest
```

### 8.2 读取指定的评分批次

把下面的 ID 替换为 `score batch` 回显的 `score_id`：

```powershell
$scoreId = "20260814153045"
& $evalCli report --root .\eval_results --task EI --model "gpt5*" --skill noskill --repeat latest --score-id $scoreId
```

`report` 会重新执行当次的运行选择，因此可以从 30 个已评分运行中重新选择
20 个出报告，不受首次 `score batch` 的选择范围限制。指定精确
`score_id` 时，被选中的每个运行都必须存在该评分版本。

## 9. Selector YAML

仓库自带的可编辑示例为：

[ei-noskill-example.yaml](./selectors/ei-noskill-example.yaml)

完整内容：

```yaml
schema_version: "1.0"
roots:
  - ../../eval_results
include:
  task:
    - EI
  skill:
    - noskill
exclude:
  run:
    - "*副本*"
    - "*broken*"
repeat: latest
```

规则：

- `roots` 必填，可写多个目录；
- 相对 `roots` 从 selector YAML 所在目录解析；
- `include` 与 `exclude` 可用字段只有
  `task/question/model/harness/skill/run`；
- `exclude` 中任一字段命中就排除该运行；
- 使用 `--selector` 时，不能再传 `--root`、其他筛选参数或
  `--repeat`。

修改 selector 后先执行：

```powershell
& $evalCli report --selector .\evaluation\selectors\ei-noskill-example.yaml --preview
```

## 10. 五个 EI 聚合指标

| 分组 | 指标 ID | 口径 |
|---|---|---|
| O2成效分 | `effectiveness.o2` | `effective-delivery.O2` 原始分直通 |
| 5项关键分 | `key.raw` | C2/C6a/O1/S1/S5 原始分加权 |
| 5项关键分 | `key.discrete` | 五项分别执行历史阶梯离散，再加权 |
| 5项关键分 | `key.piecewise` | 五项分别执行分段函数，再加权 |
| 全项分 | `all.raw` | 所有已启用非 O2 规则的原始分加权 |

五个指标的满分均为 100，O2 不进入关键5项或全项分的分母。
聚合策略内嵌在原子 ruleset 中：

```text
evaluation/src/simulation/ei/ruleset.yaml
```

## 11. 输出位置

### 11.1 单运行分数

```text
<RUN_DIR>/scores/<YYYYMMDDHHMMSS[-NN]>/score.json
```

同一次 `score batch` 选中的所有运行共用同一个 `score_id`。

### 11.2 评分批次审计记录

```text
eval_results/run_batches/<score_id>/selection.json
eval_results/run_batches/<score_id>/results.json
```

### 11.3 EI 报告

```text
eval_reports/<MMDD[A-Z]>/
├─ EI推演打分-<report_id>.xlsx
├─ aggregation.json
├─ selection.json
└─ report_manifest.json
```

`score_id` 与 `report_id` 完全解耦，生成报告不会覆盖原评分批次。

### 11.4 `EI推演打分` XLSX 固定合同

`EI推演打分-<report_id>.xlsx` 必须严格包含以下 9 个 Sheet，名称、顺序和统计口径均为后续实现与验收基准：

1. `O2目标分天梯图`；
2. `五项分段分天梯图`；
3. `五项分段分详表`；
4. `五项离散分天梯图`；
5. `五项离散分详表`；
6. `五项原始分天梯图`；
7. `五项原始分详表`；
8. `全项原始分天梯图`；
9. `全项原始分详表`。

天梯图统一使用以下布局和排序规则：

- 每行代表一个模型身份（模型、Harness、skill 的组合），每列代表一道题目；
- 模型×题目的可评分结果必须为数值类型，统一显示两位小数；不存在的组合，以及聚合状态明确为 `NOT_APPLICABLE` 或 `QUESTION_CONTRACT_INCOMPLETE` 的合法空分保留空白，不得补 0；其他状态下出现空分视为结果损坏并拒绝生成报告；
- 最右列为该模型在已有题目上的算术平均分，模型行按该平均分从上到下降序；
- 最下面一行为各题目在已有模型上的算术平均分，题目列按该平均分从左到右降序；
- 平均分只统计实际存在的数值单元格，不把缺失组合或上述合法空分计入分母；同一 repeat 组内同一指标同时出现数值与空分时拒绝聚合；并列时按稳定名称升序，保证重复生成结果一致。

详表统一使用以下布局和排序规则：

- 每一行是一项检查项在一道题目上的得分，前两列依次为`检查项`、`题目`，同一检查项的题目行必须连续聚集；
- 每一列代表一个模型身份，模型得分必须为数值类型并统一显示两位小数；缺失组合保留空白，不得补 0；
- 最右列为该检查项×题目行在已有模型上的算术平均分；在每个检查项分组内，题目行按该平均分从上到下降序；
- 最下面一行为各模型在全部检查项、全部题目上的算术平均分，不按检查项分组；模型列按该平均分从左到右降序；
- 平均分只统计实际存在的数值单元格，不把缺失组合计入分母；并列时按稳定名称升序。

其中，`五项分段分详表`、`五项离散分详表`、`五项原始分详表`只展开 5 项关键检查项；`全项原始分详表`展开所有纳入 `all.raw` 的非 O2 检查项。O2 始终独立展示，不进入关键 5 项或全项分母。

## 12. 报告运行依赖

只执行 `score run` 或不带 `--report` 的 `score batch` 时，不需要
Node.js。

`eval report` 和 `score batch --report` 需要 Node.js 与
`@oai/artifact-tool`。如果 Node.js 已在 `PATH` 中且 Node 可直接解析该依赖，
无需设置额外变量。CLI 还会自动识别 Codex 默认工作区运行时中的
`~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`，
因此通常不需要在每个新终端中重复设置 `EVAL_NODE` 和
`EVAL_NODE_MODULES`。

Windows PowerShell 和 Linux/macOS 的安装示例已经配置 Codex Desktop
提供的工作区依赖。使用其他受支持运行时时，改为该运行时实际返回的路径：

```powershell
$env:EVAL_NODE = "D:\path\to\node.exe"
$env:EVAL_NODE_MODULES = "D:\path\to\node_modules"
```

`EVAL_NODE_MODULES` 必须指向直接包含
`@oai\artifact-tool\` 的 `node_modules` 目录。报告命令会在聚合前完成依赖预检，
配置缺失时直接给出修复提示，不再等到 XLSX 阶段才失败。

Windows 上 artifact-tool 原生 preview 不可用时，报告器会使用本机 Excel 将
预览范围导出为 PDF，再调用 Poppler `pdftoppm` 转为 PNG。Codex 默认工作区
运行时会从 `EVAL_NODE_MODULES` 所在的 dependencies 目录自动定位 Poppler；
其他运行时可通过 `EVAL_PDFTOPPM` 指向 `pdftoppm.exe`。

## 13. 失败处理与安全用法

- 建议批量操作先加 `--preview`，确认 `selected_run_count` 和 `groups`；
- 正常成功的退出码是 `0`；选择、配置、评分或报告失败时为 `2`；
- `score batch` 会保留每个运行的失败原因，不会因单个运行失败覆盖其他结果；
- `--report` 只在选中运行都产生完整的五个数值指标后才生成 XLSX；
- 历史 `validator_scores/` 只作为历史资产保留，新命令只读写规范
  `<run>/scores/<score_id>/score.json`。

## 14. 完整 help

```powershell
& $evalCli --help
& $evalCli score run --help
& $evalCli score batch --help
& $evalCli report --help
```

## 15. 代码目录

```text
evaluation/src/simulation/
├─ cli.py                         # 统一 eval 入口
├─ app/
│  ├─ commands/                   # score/report 用例编排
│  ├─ selection/                  # 运行发现、筛选、repeat 收敛
│  └─ persistence/                # score/report ID 与持久化
└─ ei/
   ├─ rules.md                    # 18 个校验规则与 5 个聚合分
   ├─ provider.py                 # EI 公开门面
   ├─ scoring/                    # 单运行 rules 评分
   ├─ aggregation/                # 五个 EI 聚合指标
   ├─ reports/                    # 固定 EI推演打分 XLSX
   ├─ core/adapters/              # EI 产物发现与标准化
   └─ rules/                      # EI 校验规则
```

题目级 `validator.yaml` 不再集中存放在 `evaluation/`：正式题与题面一起放在
`evalsets/simulation/<question>/`，训练变种题与题面一起放在
`datasets/<question>/`。可信 adapter 的 Python 实现仍留在 `ei/core/adapters/`，
题目包只通过 `validator.yaml` 声明 adapter ID、字段映射和参数。

`eval4trajectory` 仍是独立的轨迹读取工具，不属于评分实现。
