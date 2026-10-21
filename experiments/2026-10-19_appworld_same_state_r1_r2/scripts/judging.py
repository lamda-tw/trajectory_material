"""Tool-disabled, credential-redacted experimental judge; explicit external authorization required."""
from pathlib import Path
import importlib.util,json,os,subprocess,sys,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest
from public_payload import public_prefix,sanitize
old=W/'experiments/2026-10-14_appworld_sft_init_step_rubric_v6_gpt61_sol/scripts/judge_protocol.py'
spec=importlib.util.spec_from_file_location('frozen_judge_protocol',old);protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
CONFIG={'model':'gpt-6.1-sol','reasoning_effort':'high','timeout_seconds':900,'max_attempts':6,'max_workers':8,'tools_enabled':False}
LABELS={'feedback_response':['resolved','necessary_new_evidence','attempted_unresolved','ignored_or_repeated','uncertain','not_applicable'],'state_use':['supported','contradicted','unresolved','no_relevant_use'],'meaningful_progress':['evidence_gain','supported_operation','supported_completion','no_demonstrated_progress','uncertain'],'repetition':['justified_refresh','no_information_gain','not_repeated','uncertain'],'documentation':['necessary','unnecessary_given_known_specs','missing_required_spec','not_applicable','uncertain'],'termination':['supported','premature_or_wrong','no_completion_claim','uncertain'],'new_execution_issue':['absent','same_known_issue','independent_new_issue','uncertain']}

def refs(payload,candidate=False):
 a={'task','task.instruction','agent_instructions'}
 for h in payload['history']:
  for k in ('assistant','code','observation'):a.add(f"history_step_{h['step']}.{k}")
 if candidate:a|={'candidate.text','candidate.code','candidate.observation'}
 return a

def evidence(x,allowed):
 assert isinstance(x,list) and x and all(type(v)==str and v in allowed for v in x),'Invalid/empty evidence reference'

def validate(v,payload,kind):
 assert v['state_id']==payload['state_id'];allowed=refs(payload,kind=='action')
 if kind=='card':
  assert v['prefix_hash']==payload['prefix_hash']
  for field,key in [('known_facts','fact'),('known_issues','issue'),('available_specs','api'),('verification_needs','need')]:
   assert isinstance(v[field],list)
   for x in v[field]:
    assert isinstance(x[key],str) and x[key].strip();evidence(x['evidence'],allowed)
    if field=='known_issues':assert x['status'] in ['open','resolved','uncertain']
    if field=='available_specs':assert x['scope'] in ['full','summary','unknown']
  for k in ['feedback_opportunity','state_use_opportunity']:
   assert v[k] in ['yes','no','uncertain'];evidence(v[k+'_evidence'],allowed)
  assert isinstance(v['unknowns'],list) and isinstance(v['acceptable_action_families'],list) and v['acceptable_action_families']
 else:
  assert v['version']=='state_probe_v1'
  for k,labels in LABELS.items():
   x=v[k];assert isinstance(x['reason'],str) and x['reason'].strip();evidence(x['evidence'],allowed)
   if k=='meaningful_progress':assert isinstance(x['labels'],list) and x['labels'] and set(x['labels'])<=set(labels)
   else:assert x['label'] in labels
  assert [x['rule'] for x in v['rubrics']]==[f'R{i}' for i in range(1,9)]
  for x in v['rubrics']:
   assert x['label'] in ['P','F','U','N'];assert isinstance(x['reason'],str) and x['reason'].strip();evidence(x['evidence'],allowed)
  assert isinstance(v['limitations'],list)

def judge(kind,raw_payload,destination,repeat=False):
 auth=json.loads((R/'config/external_scoring_authorization.json').read_text());assert auth['authorized'] is True
 payload,redaction=sanitize(raw_payload)
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 template=(R/'config'/f'{kind}_prompt.txt').read_text();prompt=template+'\n\nPUBLIC_EVIDENCE_JSON:\n'+json.dumps(payload,ensure_ascii=False)
 expected=digest({'prompt':prompt,'config':CONFIG,'repeat':repeat});meta_path=destination/'metadata.json';result_path=destination/'judgement.json'
 if result_path.exists():
  meta=json.loads(meta_path.read_text());assert meta['request_hash']==expected
  v=json.loads(result_path.read_text());validate(v,payload,kind);return v
 (destination/'request.txt').write_text(prompt);atomic_json(destination/'input.json',payload);empty=destination/'empty_cwd';empty.mkdir(exist_ok=True)
 meta={'request_hash':expected,'config':CONFIG,'kind':kind,'repeat_consistency_only':repeat,'redaction':redaction,'attempts':[]}
 if meta_path.exists():
  prior=json.loads(meta_path.read_text());assert prior['request_hash']==expected;meta=prior
 for n in range(1,CONFIG['max_attempts']+1):
  attempt=destination/f'attempt_{n}';response=attempt/'response.json'
  if attempt.exists():
   try:
    v=json.loads(response.read_text());validate(v,payload,kind);protocol.audit_events(attempt/'events.jsonl');meta['status']='valid';atomic_json(meta_path,meta);atomic_json(result_path,v);return v
   except (OSError,ValueError,AssertionError,KeyError,TypeError):continue
  attempt.mkdir();cmd=protocol.command(CONFIG,empty,response);atomic_json(attempt/'command.json',cmd);start=time.monotonic()
  try:
   with (attempt/'events.jsonl').open('w') as stdout,(attempt/'stderr.log').open('w') as stderr:
    cp=subprocess.run(cmd,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=CONFIG['timeout_seconds'],env=dict(os.environ,CUDA_VISIBLE_DEVICES=''))
   assert cp.returncode==0,f'Judge process exited {cp.returncode}'
   audit=protocol.audit_events(attempt/'events.jsonl');v=json.loads(response.read_text());validate(v,payload,kind)
   meta['attempts'].append({'attempt':n,'valid':True,'seconds':time.monotonic()-start,'audit':audit});meta['status']='valid';atomic_json(meta_path,meta);atomic_json(result_path,v);return v
  except (subprocess.TimeoutExpired,OSError,ValueError,AssertionError,KeyError,TypeError) as e:
   meta['attempts'].append({'attempt':n,'valid':False,'error':repr(e),'seconds':time.monotonic()-start});meta['status']='retrying';atomic_json(meta_path,meta)
   if n<CONFIG['max_attempts']:time.sleep(min(15*2**(n-1),60))
 meta['status']='infrastructure_failed';atomic_json(meta_path,meta);raise RuntimeError(f'Judge exhausted bounded retries: {destination}')
