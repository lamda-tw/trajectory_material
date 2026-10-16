# 同历史协议的 DEV57 训练趋势评测

更新时间：2026-10-16T12:29:58.437749+08:00
状态：complete；当前检查点：None；总进度：285/285。仅物理 GPU1。

五个点复用历史 Python launcher 与配置，原始 AppWorld agent、Chat Completions、temperature=0、seed=100、最多50步、每次请求3000输出token、32000上下文；单任务串行、vLLM max_num_seqs=3。

| 更新次数 | 进度 | TGC | SGC | 官方测试通过数 |
| ---: | ---: | ---: | ---: | ---: |
| [step 0](step_00000/task_status.jsonl) | 57/57 | 25/57 = 43.86% | 4/19 = 21.05% | 204/291 |
| [step 1](step_00001/task_status.jsonl) | 57/57 | 18/57 = 31.58% | 3/19 = 15.79% | 189/291 |
| [step 5](step_00005/task_status.jsonl) | 57/57 | 18/57 = 31.58% | 2/19 = 10.53% | 198/291 |
| [step 10](step_00010/task_status.jsonl) | 57/57 | 20/57 = 35.09% | 3/19 = 15.79% | 201/291 |
| [step 15](step_00015/task_status.jsonl) | 57/57 | 23/57 = 40.35% | 3/19 = 15.79% | 188/291 |

历史基线：TGC=23/57、SGC=4/19。step 0 首先检查逐题复现，再进行后续点。

[输入与代码哈希](INPUT_MANIFEST.json) · [执行方案](../../HISTORICAL_DEV57_RUN.md)
