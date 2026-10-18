import csv, json, hashlib
from pathlib import Path
from collections import Counter
root = Path(__file__).resolve().parents[3]
source = root / 'experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol/analysis/step_labels.csv'
rows = list(csv.DictReader(source.open()))
for r in rows:
    r['labels'] = ''.join(r[f'R{i}'] for i in range(1, 9))
    for c in 'PFUN':
        r[c] = r['labels'].count(c)
rules = {
    'all': lambda r: True,
    'P_minus_F_ge3': lambda r: r['P'] - r['F'] >= 3,
    'P_minus_F_ge4': lambda r: r['P'] - r['F'] >= 4,
    'P_ge4': lambda r: r['P'] >= 4,
    'F0_P_ge4': lambda r: r['F'] == 0 and r['P'] >= 4,
    'F0_P_ge3': lambda r: r['F'] == 0 and r['P'] >= 3,
    'F0': lambda r: r['F'] == 0,
    'F_ge4': lambda r: r['F'] >= 4,
    'F_ge3': lambda r: r['F'] >= 3,
}
result = {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'scope': 'Raw latest-v6 labels; no legacy quality gates; counts are not training outcomes.', 'rules': {}}
for name, pred in rules.items():
    selected = [r for r in rows if pred(r)]
    result['rules'][name] = {
        'steps': len(selected), 'tasks': len({r['task_id'] for r in selected}),
        'trajectories': len({r['id'] for r in selected}),
        'with_F': sum(r['F'] > 0 for r in selected), 'with_U': sum(r['U'] > 0 for r in selected),
        'dimension_counts': {f'R{i}': dict(Counter(r[f'R{i}'] for r in selected)) for i in range(1,9)},
        'top_patterns': Counter(r['labels'] for r in selected).most_common(10),
        'per_task_counts': dict(sorted(Counter(r['task_id'] for r in selected).items())),
    }
output = Path(__file__).with_name('selection_rule_counts.json')
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
for name, s in result['rules'].items():
    print(name, {k:v for k,v in s.items() if k not in ('dimension_counts','top_patterns','per_task_counts')})
