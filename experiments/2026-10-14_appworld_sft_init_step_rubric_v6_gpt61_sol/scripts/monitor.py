from pathlib import Path
from collections import Counter
import json,time,argparse
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument('--wait',type=int,default=0); a=p.parse_args(); time.sleep(min(a.wait,55))
def read(p): return json.loads(p.read_text())
s=read(r/'STATUS.json'); ev=[json.loads(l) for l in (r/'logs/scoring_events.jsonl').read_text().splitlines() if l.strip()]
valid=[e for e in ev if e['event']=='valid']; fails=[e for e in ev if e['event']=='attempt_failed']
review=read(r/'review/semantic_sample_plan.json')['samples']; ready=[x['id'] for x in review if (r/'runs/scoring'/x['id']/'judgement.json').exists()]
latest=time.time(); durations=[e['seconds'] for e in valid]; rem=(540-len(valid))*sum(durations)/max(1,len(durations))/max(1,s['concurrency_limit'])/60
print(json.dumps({'at':s['updated_at'],'phase':s['phase'],'valid':len(valid),'steps_valid':s['steps_valid'],'active':len(s['active']),'queued':s['queued'],'elapsed_min':round((latest-read(r/'TIMING.json')['scoring_start_epoch'])/60,1),'rough_remaining_min':round(rem,1),'invalid_attempts':len(fails),'recent_failures':[{'id':e['id'],'category':e['category'],'error':e['error'][:200]} for e in fails[-3:]],'concurrency':s['concurrency_limit'],'review_ready':ready,'exhausted':s['exhausted'],'pipeline':read(r/'PIPELINE_STATUS.json')['phase']},ensure_ascii=False))
