"""Observe local artifacts and publish README/STATUS. No GPU or model imports."""
import argparse
import fcntl
import json
import os
import time
from experiment_utils import R, now, read, dump

START = '<!-- AUTO_PROGRESS_START -->'
END = '<!-- AUTO_PROGRESS_END -->'


def optional(path):
    try:
        return read(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def refresh():
    (R / 'runtime').mkdir(exist_ok=True)
    with (R / 'runtime/progress.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        plan = read(R / 'config/experiment_plan.json')
        cfg = read(R / 'config/training.json')
        state = optional(R / 'runtime/pipeline_state.json') or {
            'phase': 'preparing', 'stage': 'data_and_code_validation', 'execution_authorized': True}
        journal = R / 'runtime/progress_nodes.jsonl'
        events = [json.loads(s) for s in journal.read_text().splitlines()] if journal.exists() else []
        known = {e['key'] for e in events}
        added = []

        def event(key, message, evidence):
            if key not in known:
                added.append({'key': key, 'observed_at_beijing': now(),
                              'event': message, 'evidence': evidence})
                known.add(key)

        event('authorization', '用户授权开始；GPU1 空闲与锁检查已完成', 'references/start_gpu_check.json')
        for rel, description in [
            ('data/DATA_MANIFEST.json', '14 份评分选样已冻结；DropR7 数据复用 DropR5'),
            ('checks/global_sampling.json', '全池均匀抽样独立复算通过，无额外筛选或配额'),
            ('checks/loss_math.json', '逐步骤 CE 与梯度等价验证通过'),
            ('checks/data_validation.json', '原始历史与完整目标 token 校验通过'),
            ('probe/drop_r1/seed_20261015/COMPLETE.json', '最长两个已选样本的独立试跑通过'),
            ('checks/serving_preflight.json', 'GPU1 vLLM 与 LoRA 加载及单步生成预检通过')]:
            evidence = optional(R / rel)
            if evidence and (not rel.startswith('checks/') or evidence.get('passed')):
                event(rel, description, rel)
        rows, records = [], []
        trained = evaluated = 0
        for seed in cfg['seeds']:
            for arm in plan['report_arms']:
                source = plan['aliases'].get(arm, arm)
                alias = source != arm
                tr = f'training/{source}/seed_{seed}'
                ev = f'evaluation/{source}/seed_{seed}/epoch_01'
                init = optional(R / tr / 'INITIALIZATION.json')
                progress = optional(R / tr / 'PROGRESS.json')
                td = optional(R / tr / 'epoch_01.json')
                es = optional(R / ev / 'STATUS.json')
                ed = optional(R / ev / 'SUMMARY.json')
                alias_file = optional(R / f'aliases/{arm}/seed_{seed}.json') if alias else {}
                updates = progress.get('update', progress.get('updates', 0))
                train_text = f'{updates}/679' if init or progress else '待开始'
                eval_text = f"{es.get('completed', 0)}/57" if es else '待开始'
                value = '—'
                if td:
                    assert td['samples'] == 1358 and td['updates'] == 679 and not td['probe']
                    train_text = '完成 679/679'
                if ed:
                    assert ed['tasks'] == 57
                    eval_text = '完成 57/57'
                    value = f"{ed['successes']}/57（{ed['TGC']:.2%}）"
                if not alias:
                    trained += bool(td)
                    evaluated += bool(ed)
                    label = f'DropR{arm[-1]} / {seed}'
                    if init:
                        event(tr + '/start', label + ' 开始训练', tr + '/INITIALIZATION.json')
                    for n in range(100, min(updates, 679) + 1, 100):
                        event(tr + f'/update_{n}', label + f' 已达到 {n}/679 次更新', tr + '/PROGRESS.json')
                    if td:
                        event(tr + '/complete', label + ' 单轮训练完成', tr + '/epoch_01.json')
                    if es:
                        event(ev + '/start', label + ' 开始 DEV57', ev + '/STATUS.json')
                        for n in range(10, es.get('completed', 0) + 1, 10):
                            event(ev + f'/task_{n}', label + f' DEV57 已达 {n}/57', ev + '/STATUS.json')
                    if ed:
                        event(ev + '/complete', label + f' DEV57 完成：{value}', ev + '/SUMMARY.json')
                else:
                    train_text = '复用 DropR5：' + train_text if td else '等待同 seed DropR5'
                    eval_text = '复用 DropR5：' + eval_text if ed else '等待同 seed DropR5'
                    if alias_file:
                        event(f'alias/{arm}/{seed}', f'DropR7 / {seed} 已登记复用 DropR5，不计独立运行',
                              f'aliases/{arm}/seed_{seed}.json')
                records.append({'arm': arm, 'seed': seed, 'alias_of': source if alias else None,
                                'updates_completed': 679 if td else updates,
                                'training_complete': bool(td), 'evaluation_complete': bool(ed),
                                'dev57_completed_tasks': 57 if ed else es.get('completed', 0),
                                'successes': ed.get('successes'), 'independent_run': not alias})
                rows.append(f'| DropR{arm[-1]} | {seed} | {train_text} | {eval_text} | {value} |')
        if state.get('phase') == 'error':
            event('error/' + state.get('finished_at', ''), f"运行停止：{state.get('error')}", 'runtime/pipeline_state.json')
        if state.get('phase') == 'training_eval_complete':
            event('training_eval_complete', '14 次训练与 DEV57 全部完成；同状态诊断尚未运行', 'TRAINING_EVAL_COMPLETE.json')
        events += added
        if added:
            with journal.open('a') as handle:
                for entry in added:
                    handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        phase = state.get('phase', 'preparing')
        alive = True
        if phase == 'running':
            cmdline = R.__class__(f"/proc/{state.get('pid')}/cmdline")
            alive = cmdline.exists() and b'run_pipeline.py' in cmdline.read_bytes()
        snapshot = {**state, 'updated_at_beijing': now(), 'training_completed': trained,
                    'training_planned': 14, 'evaluation_completed': evaluated, 'evaluation_planned': 14,
                    'samples_per_run': 1358, 'updates_per_run': 679, 'epochs': 1,
                    'seeds': cfg['seeds'], 'aliases': plan['aliases'], 'records': records,
                    'same_state_diagnostics': 'not_started', 'node_count': len(events),
                    'pipeline_alive': alive, 'physical_gpu': 1}
        dump(R / 'STATUS.json', snapshot)
        current = state.get('stage', 'preparing')
        if phase == 'training_eval_complete':
            current = '训练与 DEV57 已完成；同状态动作诊断待后续阶段'
        elif phase == 'error':
            current = '发生错误，已停止后续阶段：' + state.get('error', '')
        block = f'''{START}
## 当前进度

更新时间：**{now()}（北京时间）**。运行期间每 15 秒刷新；记录训练开始/每 100 更新/完成、DEV 开始/每 10 题/完成及复用节点。

当前：**{current}**。阶段：`{phase}`。仅物理 GPU1。

总体：实际训练 **{trained}/14** 完成，DEV57 **{evaluated}/14** 完成；每次 **1,358 步、1 epoch、679 更新**。八个报告组、两个 seed；DropR7 引用同 seed DropR5，不计独立训练。

| 组别 | Seed | 训练更新 | DEV57 | 官方成功率 |
| --- | ---: | --- | --- | --- |
''' + '\n'.join(rows) + '\n\n### 最近节点\n\n'
        for entry in events[-16:]:
            block += f"- {entry['observed_at_beijing']}：{entry['event']}。\n"
        if not alive:
            block += '\n调度器进程已不存在；此处是最后可观测状态，请查看日志。\n'
        block += '\n[完整节点记录](runtime/progress_nodes.jsonl) · [状态](STATUS.json) · [结果报告](REPORT.md)\n'
        if state.get('active_log'):
            log = R.__class__(state['active_log'])
            block += f'\n[当前日志]({log.relative_to(R)})\n'
        block += f'\n{END}'
        path = R / 'README.md'
        text = path.read_text()
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        temporary = path.with_name(f'README.md.tmp.{os.getpid()}')
        temporary.write_text(before + block + after)
        temporary.replace(path)
        return phase in ('training_eval_complete', 'error')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        terminal = refresh()
        if terminal or not args.watch:
            break
        time.sleep(15)
