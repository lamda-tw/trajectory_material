# Qwen3-8B + mini-SWE-agent SWE-bench Verified 50 题基线实验

## 实验结果概览

本次补丁生成实验完成了全部 **50/50** 道冻结题目，共产生 **10 个非空正式补丁**。这 **10 个补丁**均能在各题精确的基础提交上通过 `git apply --check`。本服务器没有运行官方 SWE-bench 判题器，因此本实验目前没有 官方“已解决/通过”分数。

共有 11 题以 `Submitted` 状态结束，其中 1 题虽然执行了提交操作，但正式补丁为空；30 题达到固定的 40 次模型调用上限，9 题达到固定的 32,768 token 上下文上限。所有空预测结果 均被保留，没有因为模型结果较差而重跑任何题目。

## 冻结的留出评测集

数据源：`/root/autodl-tmp/data/swebench/tasks/verified/78f471bf655a3137b2e8a75af1501690ec009ec3/test.jsonl`  
数据源 SHA-256：`a26fafa3f94d5c0b64318998cb6ec80240ba242ace3904c31938bd3346d4ee5c`  
选题随机种子：`20260914`  
选题方法：先为每个仓库分配 1 题，再按原始题量比例使用最大余数法分配剩余名额。每个仓库内部和最终输出顺序均按 `sha256(seed + "\0" + instance_id)` 排序。

| 仓库 | 题目数 |
| --- | ---: |
| `astropy/astropy` | 3 |
| `django/django` | 18 |
| `matplotlib/matplotlib` | 4 |
| `mwaskom/seaborn` | 1 |
| `pallets/flask` | 1 |
| `psf/requests` | 2 |
| `pydata/xarray` | 3 |
| `pylint-dev/pylint` | 2 |
| `pytest-dev/pytest` | 2 |
| `scikit-learn/scikit-learn` | 3 |
| `sphinx-doc/sphinx` | 4 |
| `sympy/sympy` | 7 |

这 50 个题目实例 是永久留出的评测集。后续所有 SFT 训练集、验证集、蒸馏数据和训练轨迹都必须排除这些题目，同时排除它们的标准补丁、测试补丁、官方测试以及由答案派生的数据。

## 可复现实验配置

- 模型检查点：`/root/autodl-tmp/models/Qwen3-8B`（`openai/qwen3-8b`）
- mini-SWE-agent：2.4.6，源码提交为 `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`
- vLLM：0.10.2；bfloat16；张量并行数 1；最大模型上下文长度 32,768
- 采样参数：temperature 0.6、top_p 0.95、请求 seed 20260914、每次最多输出 2,048 tokens、关闭 thinking
- 智能体：文本形式的 shell 命令操作；最多调用模型 40 次；单条 shell 命令超时 180 秒；每题只有一次正式尝试
- 仓库：在各题精确的基础提交上导出经过隔离的源码目录，没有向智能体暴露之后的 Git 提交历史
- 网络：模型的 shell 环境使用不可用的外部代理，同时提示词禁止 clone、fetch、下载及其他网络访问

## 并行执行情况

实验使用两个配置完全相同的 vLLM 服务：GPU 0 使用端口 18080，GPU 1 使用端口 18081。每个服务设置 `max_num_seqs=2`；执行进程 0–1 使用 GPU 0，执行进程 2–3 使用 GPU 1。任务固定按照 `worker_id = task_index % 4` 分配。

两次四请求并发 冒烟测试 均通过。实验分成了两个服务运行段：第一版运行器把正常的上下文窗口耗尽错误地归类为基础设施错误，因此按照安全规则停止。修正分类后，实验从序号 8 恢复，前 8 次正式模型尝试均未重跑。这次修改只涉及元数据分类和控制流程，不属于模型重试。

- 首次正式开始时间：`2026-09-14T04:09:54.625703+00:00`
- 最终结束时间：`2026-09-14T04:31:50.045486+00:00`
- 两个运行段合计的有效运行时间：18 分 35.9 秒
- 包含诊断和恢复暂停的端到端时间：21 分 55.4 秒
- 所有单题耗时之和：47 分 20.1 秒
- 等效并行加速比（`单题耗时总和 / 有效运行时间`）：2.55×
- 正式模型重试次数：0

实验没有连续采样 `nvidia-smi` 进程显存，因此不编造精确的峰值显存数据。两个 vLLM 引擎分别报告：GPU 0 按 0.45 比例分配 42.74 GiB，GPU 1 按 0.45 比例分配 42.74 GiB；二者报告的完整上下文 KV 缓存 容量均为 5.92×。

## 汇总结果

| 指标 | 数量 |
| --- | ---: |
| 已完成的任务记录 | 50 |
| `Submitted` 退出 | 11 |
| `LimitsExceeded`（达到调用次数上限） | 30 |
| `ContextWindowExceeded`（达到上下文上限） | 9 |
| 空正式补丁 | 40 |
| 非空正式补丁 | 10 |
| 通过应用检查的非空补丁 | 10 |
| 未解决的基础设施错误 | 0 |
| 正式模型重试 | 0 |

`git apply --check` 只验证补丁的语法以及能否应用到源码，不能证明补丁正确解决了题目。

## 每题结果

| 序号 | 题目实例 | 执行进程/GPU | 耗时（秒） | 退出状态 | 正式补丁字节数 | 应用检查 |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 0 | `django__django-12155` | 0/0 | 8.874 | `Submitted` | 660 | 通过 |
| 1 | `scikit-learn__scikit-learn-13142` | 1/0 | 66.135 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 2 | `scikit-learn__scikit-learn-11310` | 2/1 | 96.484 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 3 | `django__django-15973` | 3/1 | 40.577 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 4 | `pydata__xarray-4695` | 0/0 | 150.289 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 5 | `scikit-learn__scikit-learn-25931` | 1/0 | 49.974 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 6 | `pydata__xarray-6992` | 2/1 | 99.435 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 7 | `matplotlib__matplotlib-22871` | 3/1 | 38.222 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 8 | `matplotlib__matplotlib-24026` | 0/0 | 42.122 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 9 | `astropy__astropy-14182` | 1/0 | 62.685 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 10 | `django__django-14855` | 2/1 | 63.968 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 11 | `sympy__sympy-21596` | 3/1 | 72.766 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 12 | `matplotlib__matplotlib-24970` | 0/0 | 38.774 | `Submitted` | 574 | 通过 |
| 13 | `matplotlib__matplotlib-26113` | 1/0 | 32.802 | `Submitted` | 625 | 通过 |
| 14 | `sphinx-doc__sphinx-9320` | 2/1 | 67.347 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 15 | `sympy__sympy-17139` | 3/1 | 76.110 | `Submitted` | 523 | 通过 |
| 16 | `django__django-11087` | 0/0 | 50.613 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 17 | `pydata__xarray-2905` | 1/0 | 36.835 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 18 | `django__django-15380` | 2/1 | 71.325 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 19 | `astropy__astropy-7166` | 3/1 | 95.409 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 20 | `django__django-12663` | 0/0 | 63.051 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 21 | `sphinx-doc__sphinx-9367` | 1/0 | 82.055 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 22 | `django__django-16595` | 2/1 | 60.422 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 23 | `sphinx-doc__sphinx-8459` | 3/1 | 68.797 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 24 | `sympy__sympy-23534` | 0/0 | 64.935 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 25 | `sympy__sympy-19346` | 1/0 | 118.171 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 26 | `django__django-15732` | 2/1 | 42.686 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 27 | `sympy__sympy-16597` | 3/1 | 62.948 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 28 | `django__django-15987` | 0/0 | 19.959 | `Submitted` | 652 | 通过 |
| 29 | `django__django-12741` | 1/0 | 13.628 | `Submitted` | 1880 | 通过 |
| 30 | `django__django-11490` | 2/1 | 55.249 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 31 | `django__django-13195` | 3/1 | 9.641 | `Submitted` | 943 | 通过 |
| 32 | `sympy__sympy-14248` | 0/0 | 53.496 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 33 | `django__django-11603` | 1/0 | 10.720 | `Submitted` | 555 | 通过 |
| 34 | `django__django-13023` | 2/1 | 60.365 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 35 | `django__django-11133` | 3/1 | 45.655 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 36 | `django__django-14534` | 0/0 | 49.813 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 37 | `django__django-16255` | 1/0 | 14.752 | `Submitted` | 3745 | 通过 |
| 38 | `django__django-14311` | 2/1 | 67.793 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 39 | `sympy__sympy-18189` | 3/1 | 20.709 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 40 | `pylint-dev__pylint-7080` | 0/0 | 46.936 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 41 | `sphinx-doc__sphinx-9461` | 1/0 | 72.611 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 42 | `astropy__astropy-14539` | 2/1 | 87.297 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 43 | `psf__requests-1921` | 3/1 | 71.089 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 44 | `pytest-dev__pytest-7432` | 0/0 | 69.482 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 45 | `pytest-dev__pytest-10356` | 1/0 | 30.317 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 46 | `pylint-dev__pylint-6386` | 2/1 | 52.649 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 47 | `psf__requests-6028` | 3/1 | 62.558 | `Submitted` | 0 | 未执行（空补丁） |
| 48 | `mwaskom__seaborn-3187` | 0/0 | 75.570 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 49 | `pallets__flask-5014` | 1/0 | 26.012 | `Submitted` | 476 | 通过 |

## 完整性与存储情况

- 最终一致性验证：`通过`
- 共享 SWE-bench 数据快照保持不变：`是`
- `/root/autodl-tmp/envs` 顶层内容保持不变：`是`
- 每题产物验证完成后，任务 worktree 和临时环境均已删除。
- 生成本报告时实验目录大小：19.29 MiB
- 重要保留文件均记录在 `artifacts.sha256` 中。

## 后续进行官方判题

将 `predictions.jsonl` 原样复制到具备官方 SWE-bench 判题环境的机器上，使用匹配的 SWE-bench Verified 数据划分 进行评测。应保留本实验的模型标识和冻结题目实例清单，并在评测结果旁记录官方判题工具版本、镜像版本、完整命令及逐题评分输出。不要以破坏来源追踪关系的方式，把判题输出直接混入本次补丁生成基线。

这 50 题固定留出集用于完成 SFT 前后的最小闭环对比，不能将其结果表述为模型在完整 SWE-bench Verified 500 题上的成绩。
