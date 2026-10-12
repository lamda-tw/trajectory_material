"""Resume the unchanged baseline with upgraded CLI transport-event compatibility."""
import shutil
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import baseline_newtasks as baseline
import resume_baseline_newtasks as resume
import judge_transport

if __name__ == '__main__':
    previous = baseline.OUT
    baseline.OUT = previous.with_name('draco_baseline_newtasks_cli0162_v1')
    baseline.OUT.mkdir(parents=True, exist_ok=True)
    spec = baseline.OUT / 'analysis_spec.json'
    if not spec.exists():
        shutil.copyfile(previous / 'analysis_spec.json', spec)
    baseline.judge = judge_transport
    cfg = baseline.load_config()
    # Keep the earliest completed answer; redundant later answers remain auditable.
    for folder in sorted((baseline.OUT / 'judgements').glob('*')):
        cached = baseline.read_json(folder / 'judgement.json') if (folder / 'judgement.json').exists() else None
        if '--completed-only' in sys.argv and cached is None:
            continue
        for events in sorted(folder.glob('events_*.jsonl')):
            attempt = int(events.stem.split('_')[-1])
            if cached is not None and attempt >= cached['attempts']:
                break
            response = folder / f'response_{attempt}.json'
            if not response.exists():
                continue
            try:
                audit = judge_transport.audit_events(events.read_text())
                rows = baseline.validate_judgement(baseline.read_json(response), baseline.load_rules(cfg))
                messages = [e['item']['text'] for line in events.read_text().splitlines()
                            if (e := json.loads(line)).get('type') == 'item.completed'
                            and e.get('item', {}).get('type') == 'agent_message']
                if not messages or json.loads(messages[-1]) != {'scores': rows}:
                    raise ValueError('Response differs from the completed message.')
            except (ValueError, KeyError):
                continue
            prompt = (folder / 'prompt.txt').read_text()
            key = baseline.digest({'prompt': prompt, 'judge': cfg['judge'],
                                   'schema_sha256': baseline.file_sha(baseline.ROOT / cfg['judge']['schema'])})
            started = (folder / 'prompt.txt').stat().st_mtime
            if cached is not None:
                baseline.atomic_json(folder / 'superseded_later_response_record.json', cached)
            baseline.atomic_json(folder / 'judgement.json', {
                'cache_key': key, 'scores': rows, 'audit': audit, 'attempts': attempt,
                'model': cfg['judge']['model'], 'reasoning_effort': cfg['judge']['reasoning_effort'],
                'started_at_utc': datetime.fromtimestamp(started, timezone.utc).isoformat(),
                'elapsed_seconds': max(0, events.stat().st_mtime - started),
                'elapsed_source': 'recovered from prompt/events file timestamps; approximate',
                'recovered_earliest_completed_response': True})
            break
    baseline.atomic_json(baseline.OUT / 'transport_compatibility.json', {
        'codex_version': '0.162.0', 'prompt_changed': False, 'semantic_validation_changed': False,
        'earliest_completed_response_only': True,
        'sources': {str(path): baseline.file_sha(path) for path in
                    (Path(__file__).resolve(), Path(judge_transport.__file__).resolve())}})
    if '--recover-only' not in sys.argv:
        resume.main()
