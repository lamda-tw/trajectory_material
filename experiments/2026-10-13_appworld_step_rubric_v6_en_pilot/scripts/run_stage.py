"""Run one pilot stage only after explicit remote-data authorization is recorded."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,hashlib
from judge_protocol import score,validate
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stage',required=True,choices=['development','development_repeat','holdout','holdout_repeat','development_r1','development_r1_repeat','holdout_r1','holdout_r1_repeat','development_r2','development_r2_repeat','holdout_r2','holdout_r2_repeat','development_format','development_format_repeat','holdout_format','holdout_format_repeat']);ap.add_argument('--execute',action='store_true',required=True);args=ap.parse_args()
 c=read(R/('judge_config_format.json' if '_format' in args.stage else 'judge_config_r2.json' if '_r2' in args.stage else 'judge_config_r1.json' if '_r1' in args.stage else 'judge_config.json'))
 if not c['execution_enabled']:raise SystemExit('Remote execution remains disabled pending explicit data/destination authorization.')
 a=read(R/'REMOTE_AUTHORIZATION.json')
 assert a['approved'] and a['model']==c['model']
 prompt=(R/c['prompt']).read_text();assert hashlib.sha256(prompt.encode()).hexdigest()==c['prompt_sha256']
 if args.stage.startswith('holdout'):
  decision=read(R/'review/DEVELOPMENT_DECISION.json');assert decision['proceed_to_holdout'] and decision['prompt_sha256']==c['prompt_sha256']
 schema=read(R/c['output_schema']);m=read(R/'manifests'/f"{args.stage.replace('_r1','').replace('_r2','')}.json");run=R/'runs'/args.stage;run.mkdir(exist_ok=True)
 (run/'prompt.txt').write_text(prompt);(run/'config.json').write_text(json.dumps(c,indent=2)+'\n')
 pending=[];results=[]
 for s in m['samples']:
  folder=run/s['id']
  if (folder/'judgement.json').exists():
   validate(read(folder/'judgement.json'),read(R/s['input']),schema)
   assert read(folder/'metadata.json')['prompt_sha256']==c['prompt_sha256']
   results.append({'id':s['id'],'status':'valid','resumed_without_call':True})
  else:
   if folder.exists():raise SystemExit(f'Inspect incomplete attempt before retry: {folder}')
   pending.append(s)
 with ThreadPoolExecutor(max_workers=2) as ex:
  futures=[ex.submit(score,s,run,c,prompt,schema) for s in pending]
  for f in as_completed(futures):
   result=f.result();results.append({'id':result['id'],'status':result['status']})
   (run/'SUMMARY.json').write_text(json.dumps({'stage':args.stage,'total':len(m['samples']),'results':results},indent=2)+'\n')
 assert len(results)==len(m['samples']) and all(r['status']=='valid' for r in results)
if __name__=='__main__':main()
