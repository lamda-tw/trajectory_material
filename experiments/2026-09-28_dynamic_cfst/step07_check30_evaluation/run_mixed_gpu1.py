"""Use GPU1 after Action ends; existing prepared-status guard prevents duplicate Mixed."""
from pathlib import Path
import json,time,ast,datetime
S=Path(__file__).resolve().parent
while True:
 m=json.loads((S/'CFST-Action/manifest.json').read_text())
 if m['status']=='awaiting_validation' and m.get('exit_code')==0:break
 time.sleep(5)
p=S/'CFST-Mixed/manifest.json';m=json.loads(p.read_text());assert m['status']=='prepared'
m['gpu']=1;m['schedule_note']='Moved to GPU1 immediately after Action completed; original GPU0 queue will stop at prepared-status guard without launching a second Mixed run.'
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
(S/'scheduler_handoff.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'branch':'CFST-Mixed','from_gpu':0,'to_gpu':1,'reason':'Use free identical GPU1 while State continues; no model or protocol change.','original_queue_behavior':'After State completes, original resume_gpu0 prepared-status assertion prevents duplicate Mixed; this supervisor assertion is expected and not a task failure.'},indent=2)+'\n')
# Load exactly the existing launch function without executing its two top-level jobs.
path=S/'resume_gpu0.py';tree=ast.parse(path.read_text());tree.body=tree.body[:-2]
ns={'__file__':str(path),'__name__':'mixed_gpu1_launcher'};exec(compile(tree,str(path),'exec'),ns);ns['run_branch']('CFST-Mixed')
