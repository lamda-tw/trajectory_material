"""Accept only the known pre-turn tool-disabled diagnostic; preserve frozen judge."""
import json
import judge as frozen_judge

KNOWN_DISABLED_HOST = ('Code Mode is unavailable because code-mode host is disabled. '
                       'Code mode will fail closed; enable `features.code_mode_host` '
                       'and install `codex-code-mode-host`.')


def audit_events(text):
    started = completed = False
    usage = None
    events, diagnostics = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event.get('type')
        events.append(kind)
        if kind in {'error', 'turn.failed'}:
            raise ValueError('Codex reported a failed turn.')
        item = event.get('item')
        if item is not None and item.get('type') not in {'agent_message', 'reasoning', 'todo_list'}:
            if (not started and not completed and kind == 'item.completed'
                    and item.get('type') == 'error' and item.get('message') == KNOWN_DISABLED_HOST):
                diagnostics.append(item['message'])
            else:
                raise ValueError(f"Judge used a forbidden/unknown tool item: {item.get('type')}")
        if kind == 'turn.started':
            if started:
                raise ValueError('More than one judge turn.')
            started = True
        if kind == 'turn.completed':
            if not started or completed:
                raise ValueError('Invalid completed-turn sequence.')
            completed, usage = True, event.get('usage')
    if not completed:
        raise ValueError('Judge stream has no completed turn.')
    return {'usage': usage, 'event_types': events, 'accepted_startup_diagnostics': diagnostics}


# Only this stage process uses the compatibility validator. On-disk judge.py,
# prompts, request flags, schema, retry policy and scoring cache key stay frozen.
frozen_judge.audit_events = audit_events
build_prompt = frozen_judge.build_prompt
score = frozen_judge.score
