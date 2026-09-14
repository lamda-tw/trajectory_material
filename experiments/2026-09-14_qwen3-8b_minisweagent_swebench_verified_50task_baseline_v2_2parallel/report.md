# Qwen3-8B + mini-SWE-agent SWE-bench Verified 50 题基线实验 v2

## 实验结论

本次补丁生成完成冻结的 **50/50** 道题，共得到 **11 个非空正式补丁**。其中 **10 个**能在各题精确基础提交上通过 `git apply --check`，另有 **1 个**不能应用。通过应用检查仅代表补丁格式和基线匹配正确，**不代表修复通过官方测试**。本服务器仍未运行官方 SWE-bench 判题器，所以本实验没有 resolved/pass 分数。

共有 12 题以 `Submitted` 结束，其中 1 题提交了空补丁；29 题达到放宽后的 60 次模型调用上限，9 题达到 40,960 token 上下文上限。共保留 39 个空预测，正式模型重试数为 0。

回答“放缓限制后是否会有更多输出”：**非空补丁从 10 个增加到 11 个，但能应用的非空补丁仍为 10 个**。因此这次只看到“多 1 个非空输出”，没有看到“多 1 个可用候选补丁”；更不能在官方判题前认为性能提高。

## 与 baseline v1 对比

两版使用同一个冻结 50 题清单、同一 Qwen3-8B 检查点、相同采样参数和每次最多 2,048 输出 tokens。v2 只按计划改变并行数、上下文长度和调用上限。

| 指标 | v1 | v2 | 变化 |
| --- | ---: | ---: | ---: |
| 并行 worker 数 | 4 | 2 | -2 |
| 最大上下文长度 | 32,768 | 40,960 | +8,192 |
| 每题模型调用上限 | 40 | 60 | +20 |
| `Submitted` 退出 | 11 | 12 | +1 |
| 非空正式补丁 | 10 | 11 | +1 |
| 通过应用检查的非空补丁 | 10 | 10 | +0 |
| 不可应用的非空补丁 | 0 | 1 | +1 |
| `LimitsExceeded` | 30 | 29 | -1 |
| `ContextWindowExceeded` | 9 | 9 | +0 |
| 空正式补丁 | 40 | 39 | -1 |

两版非空补丁只有 **4 题重合**；其中只有 **1 题补丁字节完全相同**。v2 新出现非空补丁的题有 7 道，同时 v1 有 6 道非空题在 v2 变为空。由于 temperature=0.6，且并行批处理和服务重启可能影响采样复现，仅凭各跑一次不能把差异全部归因于上下文或调用上限。若要判断限制调整的稳定收益，建议后续用多个种子重复并比较官方 resolved 数。

## 冻结的留出评测集

数据源：`/root/autodl-tmp/data/swebench/tasks/verified/78f471bf655a3137b2e8a75af1501690ec009ec3/test.jsonl`  
数据源 SHA-256：`a26fafa3f94d5c0b64318998cb6ec80240ba242ace3904c31938bd3346d4ee5c`  
选题随机种子：`20260914`  
选题方法：先为每个仓库分配 1 题，再按原始题量比例使用最大余数法分配剩余名额；仓库内部和最终顺序均按 `sha256(seed + "\0" + instance_id)` 排序。v1 与 v2 的 `selected_tasks.jsonl` 和实例顺序相同。

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

这 50 题是永久留出的评测集。后续 SFT、验证、蒸馏和训练轨迹必须排除这些实例及其 gold/test patch、官方测试和答案派生数据。

## 可复现实验配置

- 模型检查点：`/root/autodl-tmp/models/Qwen3-8B`（`openai/qwen3-8b`）
- mini-SWE-agent：2.4.6，源码提交 `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`
- vLLM：0.10.2；bfloat16；tensor parallel size 1；最大模型上下文 40,960
- 采样：temperature 0.6、top_p 0.95、请求 seed 20260914、每次最多输出 2,048 tokens、关闭 thinking
- 智能体：文本 shell 操作；每题最多 60 次模型调用；单条命令超时 180 秒；每题一次正式尝试
- 仓库：从共享 bare mirror 的精确 `base_commit` 导出隔离源码，没有向模型暴露之后的提交历史
- 网络：shell 环境配置不可用的外部代理，系统提示词同时禁止 clone、fetch、下载和网络访问
- 新下载的 GitHub 仓库缓存仍只允许放在 `/root/autodl-tmp/data/swebench-repos`；本次缓存已齐全，没有另建下载位置

## 并行执行与两次安全暂停

使用两个相同的 vLLM 服务：GPU 0/端口 18080、GPU 1/端口 18081。每个服务 `max_num_seqs=2`，worker 0 固定到 GPU 0，worker 1 固定到 GPU 1；任务按 `worker_id = task_index % 2` 分配。2 请求并发 smoke test 在每个服务段均通过。

实验分 3 个服务段完成，原因是运行器遵循“遇到无法确认的问题就停止”的规则：

1. `sympy__sympy-17139` 中模型删除了自己的临时工作树并尝试重新 clone；网络按实验约束不可用。该题以空补丁和 `LimitsExceeded` 保留，确认属于模型行为后未重跑。
2. `django__django-14311` 中模型的错误编辑把 `django/utils/autoreload.py` 扩张到 2,547,800,043 字节。模型正式提交了 181 字节补丁，但精确基线检查确认其不可应用；该题保留为模型失败，未重跑。约 618.60 MiB 的原始 JSON 轨迹已无损压缩，解压 SHA-256 为 `c87dded95d7f3d5a125390acdbbc95cc694d60bf933cf32e9d4e9cefd8847d8b`。

两次暂停都没有更改模型答案，也没有重试已完成题目。为后续同类模型行为加入了结果保全逻辑；最终未解决的基础设施错误为 0。

- 首次正式开始：`2026-09-14T07:04:19.998895+00:00`
- 最终完成：`2026-09-14T08:16:13.018815+00:00`
- 3 个服务段有效运行时间合计：51 分 17.7 秒
- 含诊断与恢复暂停的端到端时间：1 小时 11 分 53.0 秒
- 50 题单题耗时之和：1 小时 25 分 25.4 秒
- 等效并发比（单题耗时之和 / 有效运行时间）：1.67×
- 正式模型重试次数：0

未连续采样 `nvidia-smi`，因此不编造精确峰值显存。每个 vLLM 服务按 0.45 GPU 显存利用率配置，服务日志报告 GPU 0/1 各分配 42.74 GiB，完整上下文 KV 容量均为 4.74×。

## 汇总结果

| 指标 | 数量 |
| --- | ---: |
| 已完成任务记录 | 50 |
| `Submitted` 退出 | 12 |
| `LimitsExceeded`（调用次数上限） | 29 |
| `ContextWindowExceeded`（上下文上限） | 9 |
| 空正式补丁 | 39 |
| 非空正式补丁 | 11 |
| 通过应用检查的非空补丁 | 10 |
| 未通过应用检查的非空补丁 | 1 |
| 模型删除自身工作树 | 1 |
| 工作树 diff 抓取异常但正式结果已保全 | 1 |
| 未解决的基础设施故障 | 0 |
| 正式模型重试 | 0 |

## 11 个非空补丁

| 题目实例 | v2 字节 | 应用检查 | 与 v1 的关系 |
| --- | ---: | --- | --- |
| `django__django-12155` | 660 | 通过 | 两版字节完全相同 |
| `scikit-learn__scikit-learn-11310` | 492 | 通过 | v2 新出现 |
| `pydata__xarray-6992` | 458 | 通过 | v2 新出现 |
| `matplotlib__matplotlib-24026` | 496 | 通过 | v2 新出现 |
| `sphinx-doc__sphinx-9367` | 482 | 通过 | v2 新出现 |
| `sympy__sympy-19346` | 563 | 通过 | v2 新出现 |
| `django__django-12741` | 2391 | 通过 | 两版均非空，但内容不同（v1 1880 字节） |
| `django__django-13195` | 613 | 通过 | 两版均非空，但内容不同（v1 943 字节） |
| `django__django-14311` | 181 | 失败 | v2 新出现 |
| `pylint-dev__pylint-6386` | 1927 | 通过 | v2 新出现 |
| `pallets__flask-5014` | 569 | 通过 | 两版均非空，但内容不同（v1 476 字节） |

## 每题结果

| 序号 | 题目实例 | worker/GPU | 耗时（秒） | 退出状态 | 正式补丁字节 | 应用检查 |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 0 | `django__django-12155` | 0/0 | 7.829 | `Submitted` | 660 | 通过 |
| 1 | `scikit-learn__scikit-learn-13142` | 1/1 | 75.122 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 2 | `scikit-learn__scikit-learn-11310` | 0/0 | 17.374 | `Submitted` | 492 | 通过 |
| 3 | `django__django-15973` | 1/1 | 82.048 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 4 | `pydata__xarray-4695` | 0/0 | 195.559 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 5 | `scikit-learn__scikit-learn-25931` | 1/1 | 77.348 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 6 | `pydata__xarray-6992` | 0/0 | 25.935 | `Submitted` | 458 | 通过 |
| 7 | `matplotlib__matplotlib-22871` | 1/1 | 68.837 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 8 | `matplotlib__matplotlib-24026` | 0/0 | 128.059 | `Submitted` | 496 | 通过 |
| 9 | `astropy__astropy-14182` | 1/1 | 606.519 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 10 | `django__django-14855` | 0/0 | 24.880 | `Submitted` | 0 | 未执行（空补丁） |
| 11 | `sympy__sympy-21596` | 1/1 | 99.206 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 12 | `matplotlib__matplotlib-24970` | 0/0 | 82.977 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 13 | `matplotlib__matplotlib-26113` | 1/1 | 93.436 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 14 | `sphinx-doc__sphinx-9320` | 0/0 | 259.929 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 15 | `sympy__sympy-17139` | 1/1 | 158.951 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 16 | `django__django-11087` | 0/0 | 67.599 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 17 | `pydata__xarray-2905` | 1/1 | 116.598 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 18 | `django__django-15380` | 0/0 | 109.505 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 19 | `astropy__astropy-7166` | 1/1 | 210.890 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 20 | `django__django-12663` | 0/0 | 117.419 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 21 | `sphinx-doc__sphinx-9367` | 1/1 | 15.309 | `Submitted` | 482 | 通过 |
| 22 | `django__django-16595` | 0/0 | 67.072 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 23 | `sphinx-doc__sphinx-8459` | 1/1 | 82.499 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 24 | `sympy__sympy-23534` | 0/0 | 125.134 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 25 | `sympy__sympy-19346` | 1/1 | 20.834 | `Submitted` | 563 | 通过 |
| 26 | `django__django-15732` | 0/0 | 80.728 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 27 | `sympy__sympy-16597` | 1/1 | 75.218 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 28 | `django__django-15987` | 0/0 | 75.573 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 29 | `django__django-12741` | 1/1 | 12.993 | `Submitted` | 2391 | 通过 |
| 30 | `django__django-11490` | 0/0 | 68.544 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 31 | `django__django-13195` | 1/1 | 7.722 | `Submitted` | 613 | 通过 |
| 32 | `sympy__sympy-14248` | 0/0 | 84.225 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 33 | `django__django-11603` | 1/1 | 171.782 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 34 | `django__django-13023` | 0/0 | 124.560 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 35 | `django__django-11133` | 1/1 | 63.408 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 36 | `django__django-14534` | 0/0 | 82.286 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 37 | `django__django-16255` | 1/1 | 144.256 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 38 | `django__django-14311` | 0/0 | 157.108 | `Submitted` | 181 | 失败 |
| 39 | `sympy__sympy-18189` | 1/1 | 62.702 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 40 | `pylint-dev__pylint-7080` | 0/0 | 75.081 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 41 | `sphinx-doc__sphinx-9461` | 1/1 | 97.205 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 42 | `astropy__astropy-14539` | 0/0 | 231.967 | `ContextWindowExceeded` | 0 | 未执行（空补丁） |
| 43 | `psf__requests-1921` | 1/1 | 84.608 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 44 | `pytest-dev__pytest-7432` | 0/0 | 86.217 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 45 | `pytest-dev__pytest-10356` | 1/1 | 73.707 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 46 | `pylint-dev__pylint-6386` | 0/0 | 38.985 | `Submitted` | 1927 | 通过 |
| 47 | `psf__requests-6028` | 1/1 | 98.467 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 48 | `mwaskom__seaborn-3187` | 0/0 | 160.158 | `LimitsExceeded` | 0 | 未执行（空补丁） |
| 49 | `pallets__flask-5014` | 1/1 | 31.056 | `Submitted` | 569 | 通过 |

## 完整性与存储

- 最终独立一致性校验：`通过`，错误列表为空
- 选题、prediction、唯一实例、轨迹、逐题状态均为 `50` / `50` / `50` / `50` / `50`
- 共享 SWE-bench 数据快照保持不变：`True`
- `/root/autodl-tmp/envs` 顶层内容保持不变：`True`
- 完成题目的临时 worktree 和每题 Python 环境均已删除；异常 2.5 GB 工作树在结果保全和无损轨迹校验后删除
- 实验私有的 218 MB `pip-cache` 已删除；逐题 `pip freeze --all` 依赖清单仍保留
- 生成本报告时实验目录大小约 24.31 MiB
- `report.md` 为中文主报告，`report_en.md` 为英文事实底稿；最终重要文件写入 `artifacts.sha256`

## 后续官方判题

交给同事判题时，应原样复制 `predictions.jsonl`，在具备官方 SWE-bench Verified 判题镜像的机器上运行。请同时保留模型标识、冻结实例清单、官方 harness 版本、镜像版本、完整命令和逐题评分输出。正式分数应以官方测试的 resolved 数为准，不能用“补丁非空”或“能应用”代替。

这 50 题固定留出集只用于 SFT 前后的最小闭环对比，不能表述为模型在完整 500 题 SWE-bench Verified 上的成绩。
