"""Offline only: validate saved completed responses; never launch a judge or model."""
from a_common import *
import judge_protocol,jsonschema
from a_judge_audit import audit_events
def main():
 root=R/'phase_a/judging/candidate_calibration';schema=read(R/'config/output_schema_v7.json');results=[];recovered=[]
 for sid in read(root/'run_manifest.json')['jobs']:
  dest=root/sid/'base';payload=read(dest/'input.json');meta=read(dest/'metadata.json');identity=read(dest/'identity.json')
  assert meta['identity']==identity and file_sha(dest/'request.txt')==identity['request_sha256']
  if (dest/'judgement.json').exists():
   judge_protocol.validate(read(dest/'judgement.json'),payload,schema)
  else:
   found=False
   for attempt in sorted(dest.glob('attempt_*')):
    if not (attempt/'response.json').exists():continue
    try:
     audit=audit_events(attempt/'events.jsonl');response=read(attempt/'response.json');judge_protocol.validate(response,payload,schema)
    except (OSError,ValueError,AssertionError,jsonschema.ValidationError):continue
    frozen_json(dest/'judgement.json',response)
    meta.update(status='valid',recovered_attempt=attempt.name,audit=audit,recovered_at=now(),recovery_method='offline_only_transport_notice_audit_v2',new_model_calls_during_recovery=0)
    write_json(dest/'metadata.json',meta);recovered.append({'id':sid,'attempt':attempt.name,'response_sha256':file_sha(attempt/'response.json'),'label_changes':False});found=True;break
   assert found,'No saved completed valid response for '+sid
  results.append({'state_id':sid,'variant':'base','status':'valid','offline_revalidated':True})
 assert len(results)==32
 write_json(root/'offline_recovery_audit.json',{'created_at':now(),'recovered':recovered,'new_external_calls':0,'prompt_changed':False,'runner_sha256':file_sha(__file__),'audit_sha256':file_sha(R/'runtime_code/a_judge_audit.py')})
 write_json(root/'summary_before_offline_recovery.json',read(root/'summary.json'))
 write_json(root/'summary.json',{'completed':32,'requested':32,'valid':32,'results':results,'offline_recovery':True})
 status('calibration_judging_recovered_locally',valid=32,total=32,recovered=len(recovered),new_external_calls=0)
if __name__=='__main__':main()
