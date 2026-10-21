"""CPU/static validation only. Never imports a model, AppWorld, or an external client."""
from pathlib import Path
from collections import Counter
import csv, datetime, hashlib, importlib.util, json, re, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
spec = importlib.util.spec_from_file_location('plan_index', HERE / 'prepare_plan_index.py')
index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index)

def read(name):
    with (HERE / name).open() as f:
        return list(csv.DictReader(f))

def typed(rows):
    for row in rows:
        for k in ('source_training_seed', 'before_step', 'prefix_steps', 'prefix_execute_calls', 'prompt_tokens', 'remaining_interactions_after_candidate', 'response_budget'):
            row[k] = int(row[k])
        row['previous_execution_error'] = row['previous_execution_error'] == 'True'
    return rows

formal = typed(read('states_selected.csv'))
pilot = typed(read('calibration_states.csv'))
continuation = typed(read('continuation_states.csv'))
inv = typed(read('state_inventory.csv'))
audit = json.loads((HERE / 'selection_audit.json').read_text())
for name, expected in audit['files'].items():
    assert index.sha(HERE / name) == expected, name
assert len(inv) == 14258 and len({r['prefix_sha256'] for r in inv}) == 13796
assert len(formal) == 129 and len(pilot) == 9 and len(continuation) == 20
assert len({r['prefix_sha256'] for r in formal + pilot}) == 138
assert len({r['public_state_id'] for r in formal + pilot}) == 138
assert Counter(r['source_group'] for r in formal) == dict(random=43, net3=43, zerofail3=43)
assert len({r['task_id'] for r in formal}) == 57
assert all(r['before_step'] <= 38 and r['remaining_interactions_after_candidate'] >= 12 for r in continuation)
assert {r['state_id'] for r in continuation} <= {r['state_id'] for r in formal}
assert Counter(r['continuation_panel'] for r in continuation) == dict(core=18, discovery_bridge=2)
# Regenerate all selection decisions from the verified inventory.
a, f, p, c, b = index.select_states(inv)
for generated, saved in [(a + f, formal), (p, pilot), (c + b, continuation)]:
    assert [r['state_id'] for r in generated] == [r['state_id'] for r in saved]
    for actual, recorded in zip(generated, saved):
        for key in actual:
            if key in recorded:
                assert str(actual[key]) == str(recorded[key]), (key, actual['state_id'])
# Source and original configuration identities, without using outcome fields for selection.
source = json.loads((HERE / 'source_manifest.json').read_text())
for name, expected in source['summaries'].items():
    assert index.sha(W / name) == expected
for row in source['trajectories']:
    assert index.sha(W / row['source']) == row['sha256']
models = json.loads((HERE / 'models.json').read_text())['models']
assert len(models) == 9
for m in models:
    adapter = W / m['adapter']
    epoch = json.loads((adapter.parent.parent / 'epoch_01.json').read_text())
    assert (epoch['samples'], epoch['updates'], epoch['epoch']) == (1710, 855, 1)
    assert index.sha(adapter) == m['adapter_sha256'] == epoch['adapter_files']['adapter_model.safetensors']
    assert index.sha(adapter.parent / 'adapter_config.json') == m['adapter_config_sha256'] == epoch['adapter_files']['adapter_config.json']
    root = index.OLD / f"evaluation/{m['group']}/seed_{m['training_seed']}/epoch_01"
    summ = json.loads((root / 'SUMMARY.json').read_text())
    cfg = json.loads((root / 'config.json').read_text())
    assert index.sha(root / 'config.json') == summ['config_sha256']
    assert summ['policy_id'] == m['adapter_sha256']
    assert cfg['evaluation']['temperature'] == 0.0 and cfg['evaluation']['seed'] == 100
    assert cfg['agent']['max_model_len'] == 32000 and cfg['agent']['max_steps'] == 50
# Independently reconstruct action-before messages and prefixes from raw trajectories.
cache = {}
for row in formal + pilot:
    if row['source'] not in cache:
        cache[row['source']] = json.loads((W / row['source']).read_text())
    trace = cache[row['source']]
    k = row['before_step']
    hist = [{key: step[key] for key in ('step', 'code', 'observation', 'history_assistant_text')} for step in trace['steps'][:k-1]]
    messages = [dict(m) for m in trace['initial_messages']]
    for step in hist:
        messages.append({'role': 'assistant', 'content': step['history_assistant_text'] + '\n\n'})
        if step['code']:
            messages.append({'role': 'user', 'content': 'Output:\n```\n' + step['observation'].rstrip() + '\n```\n\n'})
    prefix = {'task': trace['public_task'], 'initial_messages': trace['initial_messages'], 'history': hist}
    assert index.digest(prefix) == row['prefix_sha256']
    assert index.digest(messages) == row['messages_sha256']
    ids = trace['steps'][k-1]['prompt_ids']
    assert index.digest(ids) == row['prompt_ids_sha256'] and len(ids) == row['prompt_tokens']
    assert row['public_state_id'] == 'state_' + row['prefix_sha256'][:20]
    assert row['response_budget'] == min(3000, 32000-len(ids)) > 0
# Freeze dependencies are present and unchanged. This is not retokenization or replay.
protocol = json.loads((HERE / 'protocol_manifest.json').read_text())
for item in protocol['dependency_files'].values():
    path = Path(item['path'])
    assert index.sha(path if path.is_absolute() else W / path) == item['sha256']
assert protocol['physical_gpu'] == 1 and protocol['new_training'] is False
assert protocol['gpu_uuid'] == audit['gpu_uuid']
# Review rows and short technical fixtures must be preselected, not result-conditioned.
reviews = json.loads((HERE / 'review_manifest.json').read_text())['rows']
assert len(reviews) == 54
for m in models:
    rows = [r for r in reviews if (r['group'], r['training_seed']) == (m['group'], m['training_seed'])]
    assert Counter(r['panel'] for r in rows) == dict(anchor=3, focus_A=1, focus_B=1, focus_C=1)
    for panel, count in [('anchor', 3), ('focus_A', 1), ('focus_B', 1), ('focus_C', 1)]:
        expected = sorted([r for r in formal if r['panel'] == panel], key=lambda r: hashlib.sha256(f"20261020:judge_repeat:{m['group']}:{m['training_seed']}:{r['state_id']}".encode()).hexdigest())[:count]
        assert [r['state_id'] for r in rows if r['panel'] == panel] == [r['state_id'] for r in expected]
fixtures = json.loads((HERE / 'calibration_followup_manifest.json').read_text())['fixtures']
assert len(fixtures) == 3
for f in fixtures:
    r = min([r for r in pilot if r['panel'] == 'calibration_' + f['stage'] and r['before_step'] <= 47], key=lambda r: index.rank('continuation_calibration', r))
    assert r['state_id'] == f['state_id']
    assert f['first_action_group'] == dict(A='random', B='net3', C='zerofail3')[f['stage']]
    assert len(f['receivers']) == 3 and f['max_followup_calls_per_receiver'] == 3
b = audit['budget']
assert b['formal_first_actions'] == len(formal) * len(models) == 1161
assert b['continuation_branches'] == len(continuation) * len(models) * 3 == 540
assert b['formal_continuation_calls_max'] == 12 * b['continuation_branches'] == 6480
assert b['all_model_calls_max'] == 1161 + 6480 + 27 + 27 == 7695
assert b['external_judge_requests_max_before_transport_retries'] == 129 + 1161 + 54 + 72 == 1416
assert b['formal_evaluator_runs_max'] == 129 + 1161 + 2 * 540 == 2370
assert b['phase1_prefix_execute_calls_reference_plus_nine_models'] == 10 * sum(r['prefix_execute_calls'] for r in formal) == 16060
assert b['phase2_prefix_execute_calls_naive'] == 27 * sum(r['prefix_execute_calls'] for r in continuation) == 6021
links = 0
for path in HERE.glob('*.md'):
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        if '://' in target or target.startswith('#'):
            continue
        dest = (path.parent / target.split('#')[0]).resolve()
        assert dest.exists() or dest == HERE / 'validation_audit.json', (path.name, target)
        links += 1
result = {
    'status': 'passed_static_only',
    'checked_at_beijing': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'models_and_training_records': 9, 'trajectory_hashes': 513, 'source_summaries': 9,
    'deterministic_formal_selection': 129, 'deterministic_calibration_selection': 9,
    'deterministic_continuation_selection': 20, 'independent_raw_prefix_message_and_saved_token_hash_checks': 138,
    'preselected_repeat_rows': 54, 'preselected_calibration_fixtures': 3,
    'checked_markdown_local_links': links, 'budget_arithmetic': 'passed',
    'no_generation': True, 'no_training': True, 'no_replay': True, 'no_external_scoring': True,
    'not_yet_validated': ['tokenizer re-encoding', 'environment replay and state identity', 'semantic opportunity eligibility', 'judge calibration', 'continuation executor', 'complete base shard identity'],
    'plan_file_sha256': {p.name: index.sha(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'validation_audit.json'},
}
index.dump(HERE / 'validation_audit.json', result)
print(json.dumps({k: v for k, v in result.items() if k != 'plan_file_sha256'}, ensure_ascii=False))
