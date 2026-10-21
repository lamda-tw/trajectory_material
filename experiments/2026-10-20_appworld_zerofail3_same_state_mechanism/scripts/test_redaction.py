"""Regression for bare scalar credential output; no credential values are printed."""
from experiment import *
from public_payload import sanitize,strings

task='d4e9306_2'
values=read(R/'runtime/redaction_credentials'/f'{task}.json')
for value in values:
 payload={'task':{'task_id':task},'candidate':{'text':'Read a password','code':'print(selected_password)','observation':value+'\n'}}
 clean,audit=sanitize(payload)
 assert clean['candidate']['observation'].startswith('<CREDENTIAL_')
 assert all(value not in x for x in strings(clean))
 assert audit['task_password_registry_checked']

# Audit all first-draft requests, preserving them locally as provenance.
exposures=[]
for path in sorted((R/'judge_runs/calibration_v1').glob('*/*/input.json')):
 payload=read(path);clean,audit=sanitize(payload)
 if clean!=payload:
  exposures.append({'request':str(path.relative_to(R)),'kind':path.parent.parent.name,
                    'status':'original already transmitted; retained locally, never reused for formal scoring'})
 assert all(value not in text for value in read(R/'runtime/redaction_credentials'/f"{payload['task']['task_id']}.json") for text in strings(clean))
atomic_json(R/'calibration/redaction_incident_audit.json',{'original_requests_with_unredacted_synthetic_password':exposures,
 'count':len(exposures),'new_sanitizer_checked':True,'credentials_not_recorded_in_this_audit':True})
print(json.dumps({'scalar_password_regression':'passed','prior_requests_affected':len(exposures)}))
