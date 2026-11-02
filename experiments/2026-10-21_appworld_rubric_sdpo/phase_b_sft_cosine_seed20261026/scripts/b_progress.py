"""Human-readable progress from saved state only; no model or network calls."""
from b_common import B, read, run_dir


def write_progress(heartbeat):
    root = run_dir('sft')
    completed = len(list(root.glob('batch_*/checkpoint/COMPLETE.json')))
    state = heartbeat.get('stage') or {}
    stage = state.get('stage', 'preparing')
    names = {'collecting': '采集完整轨迹', 'whole_trajectory_judging': 'Codex 评分',
        'batch_prepared_for_update': '计算 SFT loss 并更新模型', 'batch_complete': '当前批次已完成',
        'requested_batches_complete': '当前批次完成，准备进入下一批',
        'dev57_evaluation': 'dev57 评估', 'waiting_for_judge_network': '等待评分网络恢复，自动重试',
        'waiting_for_gpu1': '等待 GPU1 空闲', 'infrastructure_retry': '基础设施重试中',
        'supervisor_needs_attention': '异常停止，需要排查',
        'sft_training_and_dev57_complete': '三轮训练和三次评估全部完成'}
    batch = heartbeat['batch']
    rows = ['# 余弦学习率 SFT 实时进度', '',
        f"更新时间：{heartbeat['at']}（约每30秒更新，打开后需刷新）", '',
        f"- 当前阶段：**{names.get(stage,stage)}**",
        f'- 已提交训练批次：**{completed}/54**',
        f'- 当前批次：**{batch}**，第 {(batch-1)//18+1} 轮，第 {(batch-1)%18+1}/18 批',
        f"- GPU1：{heartbeat['gpu1']}",
        f"- 磁盘剩余：{heartbeat['disk_free_gib']:.1f} GiB"]
    if stage == 'whole_trajectory_judging':
        count = len(list((root/f'batch_{batch:03d}/judging').glob('*/judgement.json')))
        rows.append(f'- 本批评分已完成：{count}/5 条轨迹（评分期间 GPU 空闲正常）')
    if stage == 'batch_prepared_for_update' and heartbeat.get('training'):
        t = heartbeat['training']; rows.append(f"- 本批训练步骤：{t['done']}/{t['total']}")
    for e in range(1,4):
        folder = root/f'epoch_{e:02d}_dev57'
        if (folder/'summary.json').exists():
            s=read(folder/'summary.json'); rows.append(f"- 第{e}轮 dev57：{s['successes']}/57 成功，Macro {s['macro_test_pass_fraction']:.2%}")
        elif (folder/'partial.json').exists():
            p=read(folder/'partial.json'); rows.append(f"- 第{e}轮 dev57：评估中，{p['completed']}/57 题")
    rows += ['', 'AutoPanel：`appworld-rubric-ZeroFail3-SFT-cosine-seed20261026`', '',
        f"[详细状态]({B/'STATUS.json'}) · [心跳]({root/'heartbeat.json'}) · [对比报告]({B/'REPORT.md'})", '',
        '固定计划：seed 20261026，从原始模型训练3轮，warmup后余弦衰减5e-5→5e-6。']
    temporary = B/'PROGRESS.md.tmp';temporary.write_text('\n'.join(rows)+'\n');temporary.replace(B/'PROGRESS.md')
