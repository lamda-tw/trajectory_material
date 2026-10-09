"""Frozen Codex rubric judge. Importing does not invoke Codex."""
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from common import ROOT, atomic_json, digest, file_sha, load_rules, public_judge_payload, read_json, validate_judgement

def make_schema(rules):
    return {'type': 'object', 'additionalProperties': False, 'required': ['scores'],
        'properties': {'scores': {'type': 'array', 'minItems': len(rules), 'maxItems': len(rules),
            'items': {'type': 'object', 'additionalProperties': False,
                'required': ['rubric_title', 'score', 'evidence', 'justification'],
                'properties': {'rubric_title': {'type': 'string', 'enum': [r['title'] for r in rules]},
                    'score': {'type': 'integer', 'enum': [-1, 0, 1]},
                    'evidence': {'type': 'string'}, 'justification': {'type': 'string'}}}}}}

def build_prompt(config, trajectory):
    official = (ROOT / config['judge']['official_prompt']).read_text()
    paragraphs = official.split('\n\n')
    env_notes = [p for p in paragraphs if p.startswith('In this environment,')]
    if len(env_notes) != 1 or 'does NOT end the task' not in env_notes[0]:
        raise ValueError('Official prompt changed; re-audit the environment adaptation.')
    template = official.replace(env_notes[0], '').split('## Output Format')[0]
    public = public_judge_payload(trajectory)
    values = {
        'task_input': json.dumps({'task': public['task'], 'initial_instructions_and_demonstration': public['agent_instructions_and_demonstration']}, ensure_ascii=False),
        'agent_trajectory': json.dumps({'actual_rollout': public['actual_rollout'], 'termination': public['termination']}, ensure_ascii=False),
        'rubrics': json.dumps([{k: r[k] for k in ('title', 'description', 'evaluator_instruction')} for r in load_rules(config)], ensure_ascii=False)}
    template = re.sub(r'{{ (task_input|agent_trajectory|rubrics) }}', lambda m: values[m.group(1)], template)
    return (ROOT / config['judge']['wrapper']).read_text() + '\n\n' + template + '\nReturn {"scores": [...]} using the JSON schema.\n'

def judge_command(config, workdir, response_path):
    j = config['judge']
    return [config['paths']['codex'], 'exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
            '--skip-git-repo-check', '--color', 'never', '--sandbox', 'read-only',
            '--disable', 'shell_tool', '--disable', 'unified_exec', '--disable', 'apps',
            '--disable', 'plugins', '--disable', 'multi_agent', '--disable', 'browser_use',
            '--disable', 'browser_use_external', '--disable', 'computer_use', '--disable', 'image_generation',
            '--disable', 'view_image', '--disable', 'sleep_tool', '--disable', 'skill_search',
            '--disable', 'code_mode_host', '-c', 'web_search="disabled"',
            '--cd', str(workdir), '--output-schema', str(ROOT / j['schema']),
            '--output-last-message', str(response_path), '--model', j['model'],
            '-c', f'model_reasoning_effort="{j["reasoning_effort"]}"', '--json', '-']

def audit_events(text):
    completed, usage, events = False, None, []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event.get('type'))
        if event.get('type') in {'error', 'turn.failed'}:
            raise ValueError('Codex reported a failed turn.')
        item = event.get('item')
        if item is not None and item.get('type') not in {'agent_message', 'reasoning', 'todo_list'}:
            raise ValueError(f'Judge used a forbidden/unknown tool item: {item.get("type")}')
        if event.get('type') == 'turn.completed':
            completed, usage = True, event.get('usage')
    if not completed:
        raise ValueError('Judge stream has no completed turn.')
    return {'usage': usage, 'event_types': events}

def score(config, trajectory, audit_dir, *, execute=False):
    if not execute:
        raise RuntimeError('Codex scoring is disabled until the experiment starts.')
    rules = load_rules(config)
    prompt = build_prompt(config, trajectory)
    key = digest({'prompt': prompt, 'judge': config['judge'], 'schema_sha256': file_sha(ROOT / config['judge']['schema'])})
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    cached = audit_dir / 'judgement.json'
    if cached.exists():
        result = read_json(cached)
        if result['cache_key'] != key:
            raise RuntimeError('Judge cache inputs changed; use a new run.')
        validate_judgement({'scores': result['scores']}, rules)
        return result
    (audit_dir / 'prompt.txt').write_text(prompt)
    workdir = audit_dir / 'empty_cwd'
    workdir.mkdir(exist_ok=True)
    failures = []
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    for attempt in range(1, config['judge']['max_attempts'] + 1):
        response = audit_dir / f'response_{attempt}.json'
        response.unlink(missing_ok=True)
        try:
            completed = subprocess.run(judge_command(config, workdir, response), input=prompt,
                                       text=True, capture_output=True, timeout=config['judge']['timeout_seconds'])
            (audit_dir / f'events_{attempt}.jsonl').write_text(completed.stdout)
            (audit_dir / f'stderr_{attempt}.log').write_text(completed.stderr)
            if completed.returncode:
                raise RuntimeError(f'Codex exited {completed.returncode}')
            audit = audit_events(completed.stdout)
            rows = validate_judgement(read_json(response), rules)
            result = {'cache_key': key, 'scores': rows, 'audit': audit, 'attempts': attempt,
                      'model': config['judge']['model'], 'reasoning_effort': config['judge']['reasoning_effort'],
                      'started_at_utc': started_at, 'elapsed_seconds': time.monotonic() - started}
            atomic_json(cached, result)
            return result
        except (subprocess.TimeoutExpired, OSError, ValueError, RuntimeError) as error:
            failures.append(f'{type(error).__name__}: {error}')
            atomic_json(audit_dir / 'failures.json', failures)
    raise RuntimeError(f'Judge failed all attempts; no reward assigned. See {audit_dir / "failures.json"}')
