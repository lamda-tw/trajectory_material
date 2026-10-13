"""Separate declared failure from successful-completion claims in R7 analysis."""
from pathlib import Path
from collections import Counter
import ast
import csv
import json

ROOT = Path(__file__).resolve().parents[1]


def category(payload):
    if payload['termination'] != 'completion_api':
        return 'non_completion_api_termination'
    try:
        tree = ast.parse(payload['steps'][-1]['code'])
    except SyntaxError:
        return 'unknown_completion_status'
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) == 'apis.supervisor.complete_task']
    if len(calls) != 1 or any(k.arg is None for k in calls[0].keywords):
        return 'unknown_completion_status'
    keywords = {k.arg: k.value for k in calls[0].keywords}
    if 'status' not in keywords and not calls[0].args:
        return 'default_success_submission'
    value = keywords.get('status')
    if isinstance(value, ast.Constant) and value.value == 'fail':
        return 'explicit_failure_submission'
    if isinstance(value, ast.Constant) and value.value == 'success':
        return 'explicit_success_submission'
    return 'unknown_completion_status'


def main():
    with (ROOT / 'analysis/trajectory_metrics.csv').open() as f:
        rows = list(csv.DictReader(f))
    cases = []
    for row in rows:
        payload = json.loads((ROOT / 'inputs' / (row['id']+'.json')).read_text())
        cases.append({'id': row['id'], 'task_id': row['task_id'],
                      'category': category(payload), 'R7': row['last_R7'],
                      'official_success': row['official_success'] == 'True'})
    groups = {}
    for group in sorted({c['category'] for c in cases}):
        selected = [c for c in cases if c['category'] == group]
        groups[group] = {'trajectories': len(selected), 'labels': dict(Counter(c['R7'] for c in selected)),
                         'table': {label: {'success': sum(c['official_success'] and c['R7'] == label for c in selected),
                                           'failure': sum(not c['official_success'] and c['R7'] == label for c in selected)} for label in 'PFUN'}}
    success_claim_P = [c for c in cases if c['R7'] == 'P' and c['category'] in {'default_success_submission', 'explicit_success_submission'}]
    result = {'scope': 'R7 measures end/delivery quality, not a pure success classifier. Explicit status=fail may receive P for truthful failure reporting. AST categories use only final executed code and may abstain for dynamic status.',
              'groups': groups,
              'success_submission_R7_P': {'total': len(success_claim_P), 'official_successes': sum(c['official_success'] for c in success_claim_P),
                                            'official_success_fraction': sum(c['official_success'] for c in success_claim_P)/len(success_claim_P)},
              'official_failure_with_R7_P': [c for c in cases if not c['official_success'] and c['R7'] == 'P'],
              'official_success_with_R7_F': [c for c in cases if c['official_success'] and c['R7'] == 'F'],
              'cases': cases}
    (ROOT / 'analysis/terminal_submission_analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
