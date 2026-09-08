# taowen 工作区

这是 taowen 的个人工作区，用于存放需要通过 Git 进行版本控制的源代码、脚本、配置文件、项目文档和经确认需要保留的派生数据。

## 原始数据位置

共享原始数据存放在本 Git 仓库之外：

`/root/autodl-tmp/data/raw_data`

请不要修改、移动或删除共享原始数据。程序读取原始数据时，应通过固定只读路径或命令行参数引用，不应把原始数据复制进本工作区。

## 版本控制范围

建议提交：

- 源代码和脚本；
- 配置文件示例；
- 项目说明和技术文档；
- 可复现分析所需的小型辅助文件；
- 经团队确认需要版本化的派生数据清单。

默认不提交：

- 未经确认的大体积原始数据；
- 模型 checkpoint；
- 日志、缓存和临时文件；
- Python 虚拟环境；
- 密钥、密码和本地环境变量文件。

具体忽略规则请查看 `.gitignore`。本次 SFT JSONL 体积较大，在执行 Git add 前应先决定使用 Git LFS、对象存储还是只版本化 manifest 与脚本。

## 基本工作流程

1. 开始任务前创建独立分支。
2. 在分支中修改并测试代码。
3. 提交前使用 `git status` 和 `git diff --cached` 检查变更。
4. 确认无误后提交，并在配置远程仓库后推送分支。

## 文档约定

本工作区内面向使用者的 README 文档统一使用中文编写。具体数据版本放在 `data/YYYY-MM-DD/`，详细转换记录写入该日期目录 README；本文件只维护高层变更。

## 2026-09-08：高 O2 Qwen3-8B SFT 数据

- 从共享只读目录中的 7 条高 `effectiveness.o2` 轨迹生成工具型智能体 SFT 数据。
- 输出位于 `data/2026-09-08/`，包含完整轨迹审计表示、决策级样本、按任务族分片、rollout 输入、清单和可复现脚本。
- 以 0006、0007、0008、0009、0010 五个 task family 构建 5-fold grouped cross-validation；同一 family 不跨 train/validation。
- 每个 fold 都有独立的 `train.jsonl`、`validation.jsonl`、`validation_tasks.jsonl` 和划分说明。
- 只进行一次 grouped holdout 时，推荐使用 `fold_05_holdout_0010`；一折是一场独立训练实验，不是一个 epoch。
- 数据删除 source thinking，规范化 Qwen function-calling 结构，并要求训练时采用 completion-only loss。
- 当前工具 schema 来自观测调用推断；Qwen 精确 token 长度检查与具体训练框架适配仍需在训练前完成。

详细说明见 [data/2026-09-08/README.md](data/2026-09-08/README.md)。
