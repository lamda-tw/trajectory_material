"""Accept CLI transport recovery only when a single tool-free turn completes."""
import json
import re
import judge_compat

_RECONNECT = re.compile(r'Reconnecting\.\.\. [1-5]/5 \((?:workspace routing discovery timed out|request timed out)\)')
_FALLBACK = {'Falling back from WebSockets to HTTPS transport. request timed out',
             'Falling back from WebSockets to HTTPS transport. workspace routing discovery timed out'}


def audit_events(text):
    cleaned, diagnostics = [], []
    started = completed = False
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind, item = event.get('type'), event.get('item', {})
        if kind == 'turn.started':
            started = True
        known = (kind == 'error' and _RECONNECT.fullmatch(event.get('message', '')) is not None)
        known = known or (kind == 'item.completed' and item.get('type') == 'error'
                          and item.get('message') in _FALLBACK)
        if known and started and not completed:
            diagnostics.append(event)
        else:
            cleaned.append(line)
        if kind == 'turn.completed':
            completed = True
    result = judge_compat.audit_events('\n'.join(cleaned))
    result['accepted_transport_diagnostics'] = diagnostics
    return result


judge_compat.frozen_judge.audit_events = audit_events
build_prompt = judge_compat.build_prompt
score = judge_compat.score
