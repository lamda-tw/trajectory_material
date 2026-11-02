"""Original v7 on actual terminated candidate prefixes, without feedback/condition metadata."""
from a_common import *
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_sources import sanitize,strings
from prepare_input_v3 import prepare
from score_sources import score
import judge_protocol
from a_judge_audit import audit_events
judge_protocol.audit_events=audit_events
import argparse
def main(stage):
 authorize();index=read(R/'phase_a/analysis'/f'{stage}_execution_index.json');lookup={x['state_id']:p for x,p in packages(stage)};jobs=[];links=[]
 for x in index:
  if not x['execution_valid']:continue
  p=lookup[x['state_id']];s=p['state'];source=read(s['source']);g=read(R/x['generation']);ex=read(R/x['execution'])
  history=source['steps'][:s['target_step']-1]
  for old,actual in zip(history,ex['observations']):assert old['observation']==actual['replayed']
  candidate={'step':s['target_step'],'text':g['text'],'code':g['code'],'observation':ex['candidate']['observation'],'finish_reason':g['finish_reason']}
  raw={'initial_messages':source['initial_messages'],'steps':history+[candidate],'termination':ex['termination']}
  clean,audit,secrets=sanitize(raw,s['task_id']);payload=prepare(clean,x['id'])
  assert set(payload)=={'trajectory_id','task','agent_instructions','reference_api_docs','steps','termination'}
  assert len(payload['steps'])==s['target_step']
  assert all(not any(secret in text for secret in secrets) for text in strings(payload))
  dest=R/'phase_a/inputs/candidates'/stage/(x['id']+'.json');frozen_json(dest,payload)
  jobs.append({'public_state_id':x['id'],'input':str(dest.relative_to(R)),'input_sha256':file_sha(dest),'source_sha256':file_sha(R/x['execution'])})
  links.append({**x,'target_step':s['target_step'],'judge_input':str(dest.relative_to(R)),'judge_input_sha256':file_sha(dest),'redaction':audit})
 frozen_json(R/'phase_a/config'/f'{stage}_blind_index.json',links)
 cfg=read(R/'config/judge.json');root=R/'phase_a/judging'/('candidate_'+stage);root.mkdir(parents=True,exist_ok=True)
 frozen_json(root/'run_manifest_v2.json',{'jobs':[j['public_state_id'] for j in jobs],'prompt_sha256':file_sha(R/'config/scoring_prompt_v7_en.txt'),'runner_sha256':file_sha(__file__),'score_engine_sha256':file_sha(R/'scripts/score_sources.py'),'config':cfg,'audit_sha256':file_sha(R/'runtime_code/a_judge_audit.py')})
 results=[]
 with ThreadPoolExecutor(max_workers=cfg['max_workers']) as pool:
  for f in as_completed([pool.submit(score,j,'base',cfg,'candidate_'+stage) for j in jobs]):
   results.append(f.result());write_json(root/'summary.json',{'completed':len(results),'requested':len(jobs),'valid':sum(x['status']=='valid' for x in results),'results':results});status(stage+'_offline_judging',completed=len(results),total=len(jobs),valid=sum(x['status']=='valid' for x in results))
 if any(x['status']!='valid' for x in results):raise SystemExit(1)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['calibration','formal'],required=True);main(ap.parse_args().stage)
