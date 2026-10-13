# Rubric 局部 SFT 与均匀抽样

实验已完成。只使用已有540条原始Qwen3-8B轨迹和prompt_v5评分；不生成或替换训练动作，不调用新的外部judge。

| 模型 | DEV57 官方成功 | TGC |
| --- | ---: | ---: |
| base | 3/57 | 5.26% |
| uniform | 6/57 | 10.53% |
| rubric | 4/57 | 7.02% |

两组均为全新LoRA、196,608监督token、48次更新、同题token配额。主要对照为rubric与uniform，base按相同协议重新验证；单seed结果不代表稳定优势。

- [完整报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md)
- [事前冻结方案](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/PLAN.md)
- [逐题比较](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/task_comparison.csv)
- [结果与配对统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/analysis/summary.json)
- [用时](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/TIMING.json)
- [rubric LoRA](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/training/rubric/adapter)
- [uniform LoRA](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/training/uniform/adapter)
- [完成校验](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/COMPLETION_CHECK.json)

prompt_v6另存用于后续评分，未经新语义评分实测，未用于本实验。
