"""CPU-only plan inventory. Does not import model/AppWorld code or run any experiment."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
OLD = WORKSPACE / 'experiments/2026-10-16_appworld_rubric_selection_ablation'
CURRENT = WORKSPACE / 'experiments/2026-10-18_appworld_rubric_dimension_ablation'
SALT = '20261019'
SEEDS = [20261015, 20261016, 20261017]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def rank(domain, row):
    return hashlib.sha256((SALT + ':' + domain + '|' + row['state_id']).encode()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-plan-index', action='store_true', required=True)
    parser.parse_args()
    summary_path = OLD / 'evaluation/base/SUMMARY.json'
    summary = json.loads(summary_path.read_text())
    inventory, primary = [], []
    for item in sorted(summary['results'], key=lambda r: r['task_id']):
        source = Path(item['source'])
        assert file_sha(source) == item['sha256']
        trace = json.loads(source.read_text())
        task = trace['public_task']['task_id']
        assert task == item['task_id'] and trace['job']['seed'] == 100
        messages = [dict(m) for m in trace['initial_messages']]
        steps, prior_codes, prefix_evidence, rows = trace['steps'], [], [], []
        for i, step in enumerate(steps):
            assert step['step'] == i + 1
            prev = steps[i - 1] if i else None
            error = bool(prev and prev['observation'].startswith('Execution failed.'))
            repeated = bool(prev and prev['code'].strip() and prev['code'].strip() in prior_codes[:-1])
            doc = bool(prev and not error and 'apis.api_docs.' in prev['code'])
            other = bool(prev and not error and prev['code'].strip() and not doc)
            category = 'E' if error else 'R' if repeated else 'D' if doc else 'S' if other else 'I'
            row = dict(state_id=f'{task}:before_step_{i+1:02d}', task_id=task,
                       family=task.rsplit('_', 1)[0], source=str(source.relative_to(WORKSPACE)),
                       source_sha256=item['sha256'], before_step=i + 1, prefix_steps=i,
                       remaining_interactions_before_action=50-i, stratum=category,
                       previous_execution_error=error, previous_code_repeated=repeated,
                       previous_successful_doc=doc, previous_successful_non_doc=other,
                       prompt_tokens=len(step['prompt_ids']), prompt_ids_sha256=digest(step['prompt_ids']),
                       messages_sha256=digest(messages), prefix_evidence_sha256=digest(prefix_evidence),
                       max_response_tokens=min(3000, 32000-len(step['prompt_ids'])))
            assert row['max_response_tokens'] > 0
            rows.append(row)
            # Only after indexing state i do we append the original action for the next prefix.
            prior_codes.append(step['code'].strip())
            prefix_evidence.append({k: step[k] for k in ['step', 'code', 'observation', 'history_assistant_text']})
            messages.append({'role': 'assistant', 'content': step['history_assistant_text'] + '\n\n'})
            if step['code']:
                messages.append({'role': 'user', 'content': 'Output:\n```\n' + step['observation'].rstrip() + '\n```\n\n'})
        n = len(rows)
        assert n >= 3
        boundaries = [0, n//3, 2*n//3, n]
        for band in range(3):
            chosen = min(rows[boundaries[band]:boundaries[band+1]], key=lambda x: rank('primary', x))
            primary.append(dict(chosen, panel='primary', temporal_band=['early', 'middle', 'late'][band]))
        inventory.extend(rows)
    assert len(inventory) == 1428 and len(primary) == 171
    primary_ids = {x['state_id'] for x in primary}
    focused, population = [], {}
    for category in 'ERDS':
        candidates = [x for x in inventory if x['stratum'] == category and x['state_id'] not in primary_ids]
        population[category] = len(candidates)
        assert len(candidates) >= 32
        selected = sorted(candidates, key=lambda x: rank('focused:' + category, x))[:32]
        focused += [dict(x, panel='focused_' + category, temporal_band='') for x in selected]
    selected = primary + focused
    selected_ids = {x['state_id'] for x in selected}
    assert len(selected) == len(selected_ids) == 299
    pilot = []
    continuation = []
    for category in 'ERDS':
        available = [x for x in inventory if x['stratum'] == category and x['state_id'] not in selected_ids]
        pilot += [x['state_id'] for x in sorted(available, key=lambda x: rank('pilot:' + category, x))[:2]]
        continuation += [x['state_id'] for x in sorted([x for x in focused if x['stratum'] == category],
                                                      key=lambda x: rank('continuation:' + category, x))[:4]]
    assert len(pilot) == 8 and not set(pilot) & selected_ids
    assert len(continuation) == 16
    assert sum(x['prefix_steps'] for x in selected) == 4055
    models = []
    for seed in SEEDS:
        lane = CURRENT / 'gpu0_seed_20261017' if seed == 20261017 else CURRENT
        for arm in ['drop_r5', 'drop_r1', 'drop_r2']:
            root = lane / f'training/{arm}/seed_{seed}'
            done = json.loads((root / 'epoch_01.json').read_text())
            assert done['samples'] == 1358 and done['updates'] == 679
            adapter = root / 'epoch_01_adapter/adapter_model.safetensors'
            expected = done['adapter_files']['adapter_model.safetensors']
            assert file_sha(adapter) == expected
            models.append(dict(group='full_rule_1358' if arm == 'drop_r5' else arm,
                               artifact_arm=arm, training_seed=seed,
                               adapter=str(adapter.relative_to(WORKSPACE)), adapter_sha256=expected,
                               planned_inference_gpu=1, generation_started=False))
    for name, rows in [('state_inventory.csv', inventory), ('states_selected.csv', selected)]:
        with (HERE/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    def describe(rows):
        return dict(states=len(rows), tasks=len({x['task_id'] for x in rows}),
                    families=len({x['family'] for x in rows}), strata=dict(Counter(x['stratum'] for x in rows)))
    audit = dict(status='plan_only_no_execution', execution_authorized=False,
                 source_tasks=57, source_states=len(inventory), source_summary_sha256=file_sha(summary_path),
                 sampling_salt=SALT, source_strata=dict(Counter(x['stratum'] for x in inventory)),
                 primary=describe(primary), focused={c: describe([x for x in focused if x['stratum']==c]) for c in 'ERDS'},
                 focused_available_after_primary=population, selected=describe(selected),
                 selected_prompt_over_29000=sum(x['prompt_tokens']>29000 for x in selected),
                 maximum_selected_prompt_tokens=max(x['prompt_tokens'] for x in selected),
                 minimum_selected_response_budget=min(x['max_response_tokens'] for x in selected),
                 prefix_execute_calls_one_copy=sum(x['prefix_steps'] for x in selected),
                 naive_prefix_execute_calls_nine_models=sum(x['prefix_steps'] for x in selected)*9,
                 pilot_state_ids=pilot, optional_continuation_state_ids=continuation,
                 optional_continuation_max_followup_generations=sum(50-x['before_step'] for x in selected if x['state_id'] in continuation)*9,
                 main_generations=len(selected)*9, planned_models=len(models), physical_gpu=1,
                 gpu_uuid='GPU-35170b76-56ce-240a-19c0-0c092a3e8501',
                 validation=dict(source_hashes=True, adapter_hashes=True, prefix_only_strata=True,
                                 prompt_retokenization=False, environment_replay=False, judge_validation=False),
                 no_generation=True, no_training=True, no_appworld_execution=True, no_judge_calls=True,
                 stage_two='deferred; reuse state definitions for old ZeroFail3-1710 comparisons',
                 files={p.name:file_sha(p) for p in [HERE/'state_inventory.csv',HERE/'states_selected.csv']})
    dump(HERE/'same_state_audit.json', audit)
    dump(HERE/'same_state_models.json', dict(status='plan_only', models=models))
    lines=['# 冻结状态索引：仅计划，未执行', '',
           '源为原始模型已有 DEV57 的 1,428 个行动前状态。只读取历史产物并核对哈希；未启动 GPU、AppWorld、评分或训练。', '',
           '| 面板 | 状态 | 题目 | 家族 | E / R / D / S / I |', '| --- | ---: | ---: | ---: | --- |']
    for name, rows in [('主面板',primary)]+[(f'补充{c}',[x for x in focused if x['stratum']==c]) for c in 'ERDS']:
        z=describe(rows);lines.append(f"| {name} | {z['states']} | {z['tasks']} | {z['families']} | " + ' / '.join(str(z['strata'].get(c,0)) for c in 'ERDSI')+' |')
    lines+=['', 'E=上一步执行报错；R=无上述报错且上一步代码在更早历史中出现；D=此前两类之外，上一步含文档调用且执行无异常；S=此前几类之外，上一步为非文档可执行代码且无异常；I=初始状态。类别是前缀特征，不是好坏标签。', '',
            '主面板每题按已有轨迹长度分早/中/晚三个连续区间，各选一个；区间内用 SHA256 排序，盐为20261019:primary。补充面板排除主面板后，各类用20261019:focused:<类别>排序取32个。源轨迹长度只确定区间，不使用终态成功或原当前动作的质量。抽样定义和哈希编码见脚本。', '',
            '具体299个状态逐行列在 [states_selected.csv](states_selected.csv)，完整1428个索引见 [state_inventory.csv](state_inventory.csv)。状态ID明确表示替换第几步；保留前k−1步，禁止把原第k步动作、反馈或后续轨迹提供给新模型和主评委。', '',
            '9个已保存adapter见 [same_state_models.json](same_state_models.json)，全部后续在GPU1推理，文件路径中gpu0仅指历史训练产物位置。', '',
            '来源与预算：[same_state_audit.json](same_state_audit.json)。299×9=2691次正式单步生成；8个独立校准状态不计入结果，16个续跑状态仅为可选预选，均未执行。', '',
            '3个正式状态的输入超过29000 token，最大31456；仍保留，按原协议给min(3000,32000−输入长度)输出预算，最小544。不得为更易生成而换状态或增大窗口。', '',
            '重建：`python prepare_same_state_plan.py --write-plan-index`。这是仅CPU的索引生成器，不是实验启动脚本。', '']
    (HERE/'STATE_SELECTION.md').write_text('\n'.join(lines))
    print(json.dumps({k:audit[k] for k in ['status','source_states','primary','focused','main_generations','naive_prefix_execute_calls_nine_models','optional_continuation_max_followup_generations']},ensure_ascii=False))


if __name__ == '__main__':
    main()
