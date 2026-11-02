from pathlib import Path
import sys,ast,collections,csv,json
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from common import read,write_json,now
from analyze_b_failure import features
from prepare_sources import sanitize
manifest=read(D/'config/manifest.json')
def decode(x):
 if isinstance(x,dict) and set(x)=={'dict'}:return {decode(k):decode(v) for k,v in x['dict']}
 if isinstance(x,dict) and set(x)=={'list'}:return [decode(v) for v in x['list']]
 return x

def main():
 rows=[];audits=[]
 for item in manifest['states']:
  s=read(item['path']);state={'state_id':s['id'],'stratum':s['stratum'],'feedback':s['feedback'],'old_code':s['original']['code'],'old_observation':s['original']['observation'],'conditions':{}}
  for arm in ['base_C0','base_C2','ema36_C0','ema36_C2','student36_C0']:
   path=D/'runs'/arm/s['id']/'result.json'
   if not path.exists():continue
   r=read(path);fs=features({'steps':s['history']+r['actions']})[len(s['history']):];a=r['actions'];first=fs[0] if fs else {}
   calls=[c for step in a for c in step['api_responses']]
   business=lambda c:c['app_name'] not in ['api_docs','supervisor'] and c['api_name'] not in ['login','logout']
   row={'state_id':s['id'],'stratum':s['stratum'],'source_epoch':s['epoch'],'condition':arm,'actions':len(a),'first_error':bool(a and a[0]['execution_error']),
    'first_docs_only':first.get('docs_only',False),'first_repeat_code':first.get('repeat_code',False),'first_repeat_docs':first.get('repeat_docs_literal',False),
    'first_business_non_auth':first.get('business_non_auth_step',False),'four_steps_repeat_docs':sum(x['repeat_docs_literal'] for x in fs),
    'four_steps_business_non_auth':sum(x['business_non_auth_step'] for x in fs),'four_steps_errors':sum(x['execution_error'] for x in a),
    'first_successful_business_calls':sum(business(c) and c.get('status_code',999)<400 for c in (a[0]['api_responses'] if a else [])),
    'successful_business_calls':sum(business(c) and c.get('status_code',999)<400 for c in calls),'completion_called':any(x['completed'] for x in a),'termination':r['termination'],
    'prefix_replay_exact':r['all_observations_exact'],'before_sha256':r['before_sha256']}
   rows.append(row)
   state['conditions'][arm]={'features':row,'actions':[{'code':x['code'],'observation':x['observation'],'text':x['text'],'execution_error':x['execution_error'],
    'api_calls':[{'name':c['app_name']+'.'+c['api_name'],'status':c.get('status_code',c['status']),**({'documentation_arguments':decode(c['arguments'])} if c['app_name']=='api_docs' else {})} for c in x['api_responses']]} for x in a]}
  audits.append(state)
 output=D/'analysis';output.mkdir(exist_ok=True)
 if rows:
  with (output/'behavior_by_branch.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 group={}
 for stratum in ['FAIL','R1','R6','R8','clean']:
  group[stratum]={}
  for arm in sorted(set(x['condition'] for x in rows)):
   selected=[x for x in rows if x['condition']==arm and (x['stratum']!='clean' if stratum=='FAIL' else x['stratum']==stratum)]
   if not selected:continue
   group[stratum][arm]={'n':len(selected),**{k:sum(x[k] for x in selected) for k in ['first_error','first_docs_only','first_repeat_docs','first_business_non_auth','four_steps_repeat_docs','four_steps_errors']},'branches_with_first_successful_business_API':sum(x['first_successful_business_calls']>0 for x in selected),'branches_with_successful_business_API':sum(x['successful_business_calls']>0 for x in selected),'branches_with_no_business_API':sum(x['four_steps_business_non_auth']==0 for x in selected)}
 write_json(output/'behavior_summary.json',{'updated_at':now(),'branches':len(rows),'groups':group})
 write_json(output/'case_audit.json',audits)
 task_map={x['id']:x['task_id'] for x in manifest['states']}
 cleaned=[sanitize(x,task_map[x['state_id']])[0] for x in audits]
 write_json(output/'case_audit_sanitized.json',cleaned)
 print(json.dumps({'branches':len(rows),'groups':group},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
