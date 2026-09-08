# Evaluation 测试分层

测试按验证对象分层，默认完整入口为：

```powershell
$env:PYTHONPATH='evaluation/src'
evaluation/.venv/Scripts/python.exe -m pytest evaluation/tests
```

| 目录 | 职责 | 约束 |
|---|---|---|
| `unit/` | 单个 adapter、rule、core 函数和架构边界 | 使用最小内存数据或临时文件，不遍历 `eval_results/` |
| `corpus/` | `eval_results` 中已观察到的目录、文件名、表结构和表达方言的兼容性 | 只读取 `fixtures/` 中已入库快照；每个语料变体保持独立 pytest case；已知缺口使用 `strict=True` 的 xfail |
| `contract/` | ruleset、profile、结果 schema 和跨组件发布合同 | 验证当前发布整体一致性，不复制单条规则的局部测试 |
| `integration/` | CLI、报告和端到端编排边界 | 只覆盖跨模块接线，不重复底层规则组合矩阵 |
| `helpers/` | 跨层测试数据构造器 | 文件名不得以 `test_` 开头，不承载断言 |
| `fixtures/` | 可独立运行的静态测试资源 | 不得引用被 Git 忽略的 `eval_results/` 路径 |

精简测试时，只允许删除以下内容：已无生产调用方的历史兼容测试、被更强断言严格包含的重复测试、或同一机制在组合矩阵中的重复排列。真实语料变体、题目合同、关键门槛、异常状态和独立规则语义不得为了减少数量而折叠进循环或删除。
