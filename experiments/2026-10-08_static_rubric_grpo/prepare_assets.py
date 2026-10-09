#!/usr/bin/env python3
"""Freeze public inputs, without invoking models or executing tasks."""
import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path('/root/autodl-tmp/data/benchmarks/appworld/runtime/data')
PROMPT = Path('/root/autodl-tmp/envs/appworld-src-42b5bcf3/experiments/prompts/react_code_agent/instructions.txt')
FILES = {
    'static_rubrics.json': 'training/rubrics/static_rubrics_qwen36_27b_mece.json',
    'score_rubrics.txt': 'training/src/verl_appworld/rubric_prompts/score_rubrics.txt',
    'rubric_reward.py.txt': 'training/src/verl_appworld/rubric_reward.py',
    'REWARD_PIPELINE.md': 'training/docs/REWARD_PIPELINE.md',
    'CREDIT.md': 'training/docs/CREDIT.md',
    'LICENSE': 'LICENSE',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'static-rubric-experiment-preparation'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()

def main():
    vendor = ROOT / 'assets' / 'draco'
    vendor.mkdir(parents=True, exist_ok=True)
    manifest = vendor / 'provenance.json'
    if manifest.exists():
        provenance = json.loads(manifest.read_text())
        for name, entry in provenance['files'].items():
            assert sha((vendor / name).read_bytes()) == entry['sha256'], name
    else:
        commit = json.loads(fetch('https://api.github.com/repos/IBM/draco/commits/main'))['sha']
        provenance = {'repository': 'https://github.com/IBM/draco', 'commit': commit,
                      'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'files': {}}
        for name, source in FILES.items():
            url = f'https://raw.githubusercontent.com/IBM/draco/{commit}/{source}'
            content = fetch(url)
            (vendor / name).write_bytes(content)
            provenance['files'][name] = {'path': source, 'url': url, 'sha256': sha(content)}
            print(f'Downloaded {name}: {len(content)} bytes', flush=True)
        manifest.write_text(json.dumps(provenance, indent=2) + '\n')
    rules = json.loads((vendor / 'static_rubrics.json').read_text())
    rubrics = rules['rubrics'] if isinstance(rules, dict) else rules
    assert len(rubrics) == 21
    assert all(all(k in r for k in ('title', 'description', 'evaluator_instruction')) for r in rubrics)
    from judge import make_schema
    (ROOT / 'assets/judge_schema.json').write_text(json.dumps(make_schema(rubrics), indent=2) + '\n')
    local_prompt = ROOT / 'assets' / 'agent_prompt.txt'
    if not local_prompt.exists():
        shutil.copyfile(PROMPT, local_prompt)
    def read_ids(name):
        return [s.strip() for s in (DATA / 'datasets' / name).read_text().splitlines() if s.strip() and not s.startswith('#')]
    train, dev = read_ids('train.txt'), read_ids('dev.txt')
    assert len(train) == len(set(train)) and len(dev) == len(set(dev))
    assert not set(train) & set(dev)
    ordered = sorted(train, key=lambda t: sha(('static-rubric-v1:20261008:' + t).encode()))
    chosen, families = [], set()
    for task in ordered:
        family = task.rsplit('_', 1)[0]
        if family not in families:
            chosen.append(task)
            families.add(family)
        if len(chosen) == 8:
            break
    assert len(chosen) == 8
    splits = ROOT / 'assets' / 'splits'
    splits.mkdir(exist_ok=True)
    for name, ids in [('train_pilot_8.txt', chosen), ('train_all.txt', train), ('dev.txt', dev)]:
        target = splits / name
        body = '\n'.join(ids) + '\n'
        if target.exists() and target.read_text() != body:
            raise SystemExit(f'{name} changed; refusing to silently change the experiment split.')
        target.write_text(body)
    frozen = {
        'selection': 'sha256(static-rubric-v1:20261008:<task_id>), first task per family, first eight; no outcome labels',
        'source_data': str(DATA), 'train_count': len(train), 'dev_count': len(dev),
        'train_pilot_count': len(chosen), 'prompt_source': str(PROMPT),
        'sha256': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in [local_prompt, *sorted(splits.glob('*.txt'))]},
    }
    (ROOT / 'assets' / 'inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')
    print(json.dumps({'rules': len(rubrics), 'train': len(train), 'pilot': chosen, 'dev': len(dev), 'draco_commit': provenance['commit']}, indent=2))

if __name__ == '__main__':
    main()
