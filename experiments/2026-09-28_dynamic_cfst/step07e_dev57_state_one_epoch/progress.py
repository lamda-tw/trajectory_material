from pathlib import Path
import json,datetime
S=Path(__file__).resolve().parent
SUB=Path('experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev/tasks')
print(datetime.datetime.now(datetime.timezone.utc).isoformat())
for b in ['CFST-state']:
 d=S/b;p=d/'task_status.jsonl';a=[json.loads(x) for x in p.read_text().splitlines()] if p.exists() else [];done={r['task_id'] for r in a};m=json.loads((d/'manifest.json').read_text());active=[]
 if (d/SUB).exists():
  for t in (d/SUB).iterdir():
   if t.name not in done:
    p=t/'logs/lm_calls.jsonl';active.append(dict(task=t.name,lm_calls=len(p.read_text().splitlines()) if p.exists() else 0))
 print(json.dumps(dict(branch=b,status=m['status'],completed=len(a),success=sum(x['status']=='success' for x in a),active=active),ensure_ascii=False))
