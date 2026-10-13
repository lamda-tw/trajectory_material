"""Read-only audit of completed scoring artifacts; never invokes a judge."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,hashlib,collections
from judge_protocol import validate,audit_events
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 expected={'development':12,'development_repeat':4,'development_r1':12,'development_r1_repeat':4,'development_r2':12,'development_r2_repeat':4,'development_format':4,'development_format_repeat':4,'holdout_format':24,'holdout_format_repeat':4}
 schema=read(R/'assets/output_schema_v6.json'); stages={};starts=[];ends=[];allids=set();intervals=[]
 for stage,n in expected.items():
  run=R/'runs'/stage;files=list(run.glob('*/metadata.json'));assert len(files)==n,(stage,len(files),n)
  manifest=read(R/'manifests'/f"{stage.replace('_r1','').replace('_r2','')}.json")['samples'];samples={s['id']:s for s in manifest}
  assert {p.parent.name for p in files}==set(samples)
  count=0;invalid=0;firstvalid=0;failures=[];accepted=0;failed_calls=[]
  for p in files:
   folder=p.parent;sid=folder.name;allids.add(sid);sample=samples[sid];m=read(folder/'metadata.json');inp=read(folder/'input.json')
   assert sha(folder/'input.json')==sample['input_sha256']==m['input_sha256']
   assert sha(R/sample['input'])==sample['input_sha256']
   assert sha(Path(sample['source']))==sample['source_sha256']==m['source_sha256']
   assert sha(run/'prompt.txt')==m['prompt_sha256']
   assert sha(folder/'request.txt')==m['request_sha256']
   assert (folder/'request.txt').read_text()==(run/'prompt.txt').read_text().replace('{{TRAJECTORY_JSON}}',(folder/'input.json').read_text())
   assert set(inp)=={'trajectory_id','task','agent_instructions','reference_api_docs','steps','termination'},set(inp)
   attempts=m['attempts'];assert m['status'] in ['valid','failed']
   if m['status']=='valid':
    accepted+=1;validate(read(folder/'judgement.json'),inp,schema)
    assert attempts[-1]['status']=='valid';assert sum(a['status']=='valid' for a in attempts)==1
    assert read(folder/f"attempt_{attempts[-1]['attempt']}"/'response.json')==read(folder/'judgement.json')
   else:
    assert not (folder/'judgement.json').exists();assert len(attempts)==read(run/'config.json')['max_attempts'];assert all(a['status']=='invalid' for a in attempts)
    failed_calls.append(sid)
   firstvalid+=attempts[0]['status']=='valid'
   for a in attempts:
    count+=1;start=datetime.fromisoformat(a['started_at']);end=start+timedelta(seconds=a['elapsed_seconds']);starts.append(start);ends.append(end);intervals.extend([(start,1),(end,-1)])
    ad=folder/f"attempt_{a['attempt']}"
    if a['status']=='valid':audit_events(ad/'events.jsonl')
    else:
     invalid+=1;failures.append({'id':sid,'attempt':a['attempt'],'error':a['error'].split('\n')[0]})
   assert len(list(folder.glob('attempt_*')))==len(attempts)
  stages[stage]={'planned':n,'accepted':accepted,'failed_calls':failed_calls,'attempts':count,'invalid_attempts':invalid,'first_attempt_valid':firstvalid,'failures':failures}
 dev=read(R/'manifests/development.json')['samples'];hold=read(R/'manifests/holdout.json')['samples'];fam=lambda ss:{s['selection_metadata_not_for_judge']['task_family'] for s in ss}
 assert fam(dev).isdisjoint(fam(hold));assert len(allids)==36
 selected=R/'assets/prompt_v6_en_format.txt';assert sha(selected)==read(R/'review/DEVELOPMENT_DECISION.json')['prompt_sha256']
 assert selected.read_text().split('[Output]')[0]==(R/'assets/prompt_v6_en.txt').read_text().split('[Output]')[0]
 running=peak=0
 for t,delta in sorted(intervals):running+=delta;peak=max(peak,running)
 result={'status':'passed','audited_at':datetime.now(timezone.utc).isoformat(),'stages':stages,'unique_trajectories':len(allids),'unique_steps':sum(s['steps'] for s in dev+hold),'development_families':len(fam(dev)),'holdout_families':len(fam(hold)),'families_disjoint':True,'planned_calls':sum(d['planned'] for d in stages.values()),'accepted_calls':sum(d['accepted'] for d in stages.values()),'failed_calls':sum(len(d['failed_calls']) for d in stages.values()),'actual_attempts':sum(d['attempts'] for d in stages.values()),'peak_concurrent_attempt_intervals':peak,'first_started':min(starts).isoformat(),'last_attempt_ended':max(ends).isoformat(),'elapsed_wall_seconds':(max(ends)-min(starts)).total_seconds(),'selected_prompt_sha256':sha(selected),'verified':['all source/input/request/prompt hashes','exact step IDs/order and schema for every accepted response','first valid output retained; invalid attempts preserved','no tool calls in accepted scoring turns','outcome and old label metadata excluded from judge input','selected scoring semantics identical to original English v6']}
 (R/'FINAL_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
