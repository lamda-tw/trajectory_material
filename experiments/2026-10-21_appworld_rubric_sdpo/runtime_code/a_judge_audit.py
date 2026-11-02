"""Recognize transport fallback notices; continue rejecting actual tool items."""
import json
def audit_events(path):
 events=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
 completed=[e for e in events if e.get('type')=='turn.completed']
 assert completed,'no completed turn'
 assert not any(e.get('type')=='turn.failed' for e in events),'failed turn'
 def notice(e):
  item=e.get('item',{});message=item.get('message','')
  return item.get('type')=='error' and (message.startswith('Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed;') or message.startswith('Falling back from WebSockets to HTTPS transport.'))
 forbidden=[e['item'].get('type') for e in events if 'item' in e and e['item'].get('type') not in {'agent_message','reasoning','todo_list'} and not notice(e)]
 assert not forbidden,f'forbidden tool events: {forbidden}'
 return {'usage':completed[-1].get('usage'),'event_types':[e.get('type') for e in events],'tool_items':forbidden,'nonfatal_error_events':[e for e in events if e.get('type')=='error' or notice(e)],'audit_version':'phase_a_transport_notice_v2'}
