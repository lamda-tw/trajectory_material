#!/usr/bin/env python3
"""Write reports from measured one-epoch outputs; never start training or evaluation."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
BRANCHES = ['CFST-state', 'CFST-Action', 'CFST-Mixed']
NAMES = dict(zip(BRANCHES, ['CFST-State-1epoch', 'CFST-Action-1epoch', 'CFST-Mixed-1epoch']))

def link(path, label):
    return f'[{label}]({path})'

def main():
    summary = json.loads((OUT / 'summary.json').read_text())
    validation = json.loads((OUT / 'validation.json').read_text())
    assert validation['status'] == 'PASS'
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    table = []
    for branch, ax in zip(BRANCHES, axes):
        row = summary['branches'][branch]
        metrics = json.loads((OUT / branch / 'metrics.json').read_text())
        events = metrics['training']['history']
        exposure = row['exposure']
        table.append(f"| {NAMES[branch]} | {row['unique_samples']} | {row['optimizer_steps']} | {row['supervised_tokens']:,} | {exposure['input_tokens_unpadded']:,} | {row['loss_last']:.4f} | {row['diagnostic_loss']:.4f} | {row['duration_seconds']:.1f} |")
        ax.plot([e['step'] for e in events], [e['loss'] for e in events], marker='o', label='Per-update loss')
        ax.axhline(row['diagnostic_loss'], linestyle='--', color='tab:orange', label='Final package diagnostic')
        ax.set_title(NAMES[branch])
        ax.set_xlabel('Optimizer update')
        ax.set_ylabel('Completion-token loss')
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=7)
        ax.grid(alpha=.2)
        report = f'''# {NAMES[branch]} 训练报告

状态：训练完成，核验通过；尚未运行检查30题或Dev57。

从原Qwen3-8B + train90 LoRA第5轮adapter独立启动，重新建立AdamW优化器。学习率2e-4，全局batch=2，双卡各1条，梯度累积1；BF16、SDPA、seed=20260928、最大40,960 tokens；LoRA r=8、alpha=16、dropout=0。保持旧版训练模板和completion-only loss。

| 项目 | 实际结果 |
| --- | ---: |
| 唯一样本 / 实际训练样本次数 | {row['unique_samples']} / {row['scheduled_examples']} |
| 每条样本实际进入参数更新的次数 | 1 |
| 优化器更新 | {row['optimizer_steps']} |
| 教师动作监督tokens | {row['supervised_tokens']:,} |
| 输入tokens（历史加答案，不含padding） | {exposure['input_tokens_unpadded']:,} |
| 输入tokens（按8对齐，含padding） | {exposure['input_tokens_padded']:,} |
| 历史tokens（不计入loss） | {exposure['prompt_tokens']:,} |
| 第一次 / 最后一次更新的loss | {row['loss_first']:.6f} / {row['loss_last']:.6f} |
| 更新loss的算术平均 | {row['loss_mean']:.6f} |
| 训练结束后原数据包诊断loss | {row['diagnostic_loss']:.6f} |
| 更新阶段耗时（秒） | {events[-1]['elapsed_seconds']:.2f} |
| 训练、诊断与保存耗时（秒；不含加载） | {row['duration_seconds']:.2f} |
| 最大单卡预留显存（GiB） | {row['peak_reserved_gib_max']:.2f} |
| 实际更新的LoRA张量 | {row['weight_delta']['changed_tensor_count']} / {row['weight_delta']['tensor_count']} |
| 与起点权重的L2差值 | {row['weight_delta']['l2_delta']:.6f} |

每个更新使用的样本不同，首尾loss不能直接视为同一批数据的下降量。诊断loss是训练完成后，对本分支原训练包做一次无梯度计算，不更新权重、不增加训练轮数，也不是独立验证分数。任务效果仍需之后的同协议检查30题评测。

保存的adapter已经与Qwen3-8B重新加载并完成一次有限数值前向检查。权重SHA256：`{row['adapter_model_sha256']}`。

{link(OUT / branch / 'adapter', '独立adapter')} · {link(OUT / branch / 'training_config.json', '训练配置')} · {link(OUT / branch / 'loss_history.jsonl', '每次更新及实际样本记录')} · {link(OUT / branch / 'metrics.json', '完整指标')} · {link(OUT / branch / 'train.log', '原始日志')}
'''
        (OUT / branch / 'REPORT.md').write_text(report)
    fig.tight_layout()
    fig.savefig(OUT / 'training_loss.png', dpi=180)
    fig.savefig(OUT / 'training_loss.pdf')
    plt.close(fig)
    text = f'''# CFST第6b步：三个分支各训练1轮

**训练及核验已完成。三支均从原Qwen3-8B + train90 LoRA第5轮adapter独立启动；旧第6、7步结果保留。** 本步没有运行检查30题、Dev57或AppWorld轨迹采集。

本轮只改变训练量规则：使用第5步冻结的12/8/20条唯一数据，各自完整训练1轮。每条样本在两张卡合计的参数更新中恰好出现一次，不重复凑8,000监督tokens。学习率等设置与旧第6步相同，原始数据、标签和修复动作不变；只监督教师替代动作，历史仅作输入，修复后的学生续跑不作为训练目标。

| 分支 | 样本次数 | 更新次数 | 监督tokens | 输入tokens（不含padding） | 最后更新loss | 训练包诊断loss | 耗时（秒） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
''' + '\n'.join(table) + f'''

耗时包括更新、训练包诊断和保存，不含模型加载。输入tokens是实际送入模型的历史加答案长度；计算还包含padding、反向传播和梯度检查点重计算，不能用监督tokens或样本数直接代替实际算力。

学习率2e-4、AdamW、weight decay=0、无warmup或调度、全局batch=2、双卡每卡1条、累积1次；LoRA r=8/alpha=16/dropout=0；BF16、SDPA、最大40,960、seed=20260928，训练模板enable_thinking=False。每支建立新的优化器，不从旧CFST分支继续训练。源adapter SHA256为 `{summary['source']['adapter_model_sha256']}`。

## 核验结果

{validation['checks_passed']}/{validation['checks_total']}项检查通过。核验覆盖：冻结数据哈希、实际样本曝光次数、两卡无重复无遗漏且顺序符合种子、更新步数和token总量、原adapter文件未修改、配置符合计划、模型权重实际变化、三支权重不同，以及重新加载三支adapter后的前向输出有限且彼此不同。训练前记录的旧第6、7步共{summary['old_result_files_unchanged']}个保护文件哈希全部未变。

{link(OUT / 'validation.json', '完整核验')} · {link(OUT / 'sample_exposure_audit.json', '实际样本使用审计')} · {link(OUT / 'reload_validation.json', '重新加载核验')} · {link(OUT / 'summary.json', '结构化结果')}

## 三个独立产物

''' + '\n'.join(f'- {link(OUT / b / "adapter", NAMES[b] + " adapter")}；{link(OUT / b / "REPORT.md", "训练报告")}' for b in BRANCHES) + f'''

每支目录同时保存唯一训练清单、预期两卡分区、配置、原始日志、逐步loss和权重。执行入口为 `run_step06b.py`，它拒绝覆盖已有训练日志；训练程序与旧第6步逐字相同，变化发生在生成单轮清单和验收规则上。{link(OUT / 'PLAN_SNAPSHOT.md', '执行前计划快照')} 与 `training_plan.json` 保留冻结时状态；完成状态以本报告、`status.json` 和 `summary.json` 为准。

## 现在能说明什么

三个模型按预定一轮训练量完成并可加载。训练loss不能判断任务成功率，也不能凭三个数据包的loss差异证明能力分类合理；第一与最后一步使用不同样本，不能简单比较。诊断loss只反映各自训练包上的拟合，不是检查30题的结果。没有因为loss高低加训或挑选中间权重。

旧版State/Action/Mixed使用54/44/50次样本、27/22/25次更新；本轮为12/8/20次样本、6/4/10次更新。之后若执行第7b步，仍按原评测协议比较这三个新adapter与原epoch5的17/30，以及旧版13/14/14的结果。本步到训练核验结束；当前学生仍保留原epoch5，不宣布任何新分支已带来改善。

{link(OUT / 'training_loss.png', '训练loss图')} · {link(OUT / 'training_loss.pdf', 'PDF图')}
'''
    (OUT / 'README.md').write_text(text)
    print('Reports and loss plots written.')

if __name__ == '__main__':
    main()
