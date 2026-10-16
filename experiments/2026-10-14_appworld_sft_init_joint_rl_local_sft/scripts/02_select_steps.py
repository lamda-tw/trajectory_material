"""Select original step identities solely by P-F>=4; no content or outcome filters."""
from common import *
import argparse,csv
from collections import Counter

def select(labels,threshold):
 require(threshold==4,'This experiment freezes threshold 4')
 preflight=read(ROOT/'checks/preflight.json');require(preflight['passed'],'Step 1 must pass')
 inventory=read(ROOT/'references/input_inventory.json');require(sha(labels)==inventory['label_csv_sha256'],'Verified label CSV changed')
 rows=list(csv.DictReader(Path(labels).open()));decisions=[];keys=set()
 for x in rows:
  label=x['labels'];require(len(label)==8 and set(label)<=set('PFUN'),'Invalid label string')
  require(''.join(x[f'R{i}'] for i in range(1,9))==label,'Label columns differ')
  key=(x['trajectory_id'],int(x['step_id']));require(key not in keys,'Duplicate source identity');keys.add(key)
  counts={v:label.count(v) for v in 'PFUN'};score=counts['P']-counts['F'];chosen=score>=4
  decisions.append({'trajectory_id':x['trajectory_id'],'id':x['id'],'task_id':x['task_id'],'step_id':int(x['step_id']),'labels':label,'label_counts':counts,'score':score,'selected':chosen,'selection_reason':'score_ge_4' if chosen else 'score_lt_4','judge_reason':x['reason']})
 # Source metadata is attached only after the label-only decision; never used to change it.
 source={x['id']:x for x in inventory['samples']};selected=[]
 for d in decisions:
  if d['selected']:
   ref=source[d['id']];require(d['trajectory_id']==ref['trajectory_id'] and d['task_id']==ref['task_id'],'Source identity mismatch')
   selected.append(d|{'source':ref['source'],'source_sha256':ref['source_sha256'],'judgement_sha256':ref['judgement_sha256'],'training_sample_built':False})
 require(len(decisions)==9886 and len(selected)==2623,'Expected full/selected counts differ')
 require(sum('F' in x['labels'] for x in selected)==106 and sum('U' in x['labels'] for x in selected)==41,'F/U retention mismatch')
 require(len({x['task_id'] for x in selected})==88 and len({x['trajectory_id'] for x in selected})==431,'Coverage diagnostic mismatch')
 jsonl(ROOT/'data/selection_decisions.jsonl',decisions);jsonl(ROOT/'data/selected_steps.jsonl',selected)
 policy={'frozen_at':now(),'policy_id':'sft-init-v6-net-score-ge4-v1','input':str(Path(labels).resolve()),'input_sha256':sha(labels),'score_manifest_sha256':inventory['score_manifest_sha256'],'dimension_weights':{f'R{i}':1 for i in range(1,9)},'label_values':{'P':1,'F':-1,'U':0,'N':0},'formula':'count(P) - count(F)','inclusive_threshold':4,'only_selection_predicate':'score >= 4','extra_quality_filters':[],'content_deduplication':False,'official_outcomes_used':False,'task_or_action_quotas':False,'tie_breaking':'none; retain all steps at threshold','F_U_veto':False,'negative_loss':False,'score_as_CE_weight':False,'full_original_response_required_in_step_3':True,'selected_steps':2623,'expected_full_steps':9886,'scope':'Frozen selection only, not training configuration or tokenized dataset','script_sha256':sha(__file__)}
 dump(ROOT/'config/selection_policy.json',policy)
 # Independent row-level re-evaluation from the CSV, then compare persisted identities and fields.
 persisted=[json.loads(x) for x in (ROOT/'data/selection_decisions.jsonl').read_text().splitlines()]
 persisted_selected=[json.loads(x) for x in (ROOT/'data/selected_steps.jsonl').read_text().splitlines()]
 expected={};values={'P':1,'F':-1,'U':0,'N':0}
 for x in rows:expected[(x['trajectory_id'],int(x['step_id']))]=sum(values[x[f'R{i}']] for i in range(1,9))
 require(len(persisted)==len(expected),'Persisted coverage')
 for x in persisted:
  score=expected[(x['trajectory_id'],x['step_id'])]
  require(x['score']==score and x['selected']==(score>=4),'Independent decision mismatch')
 want={k for k,v in expected.items() if v>=4};got={(x['trajectory_id'],x['step_id']) for x in persisted_selected}
 require(want==got and len(got)==len(persisted_selected),'Persisted selected identity mismatch')
 report={'passed':True,'completed_at':now(),'stage':2,'selection_policy':'config/selection_policy.json','all_steps':len(rows),'selected':len(selected),'excluded':len(rows)-len(selected),'selected_fraction':len(selected)/len(rows),'tasks':88,'trajectories':431,'contains_F':106,'contains_U':41,'F_by_dimension':{f'R{i}':sum(x['labels'][i-1]=='F' for x in selected) for i in range(1,9)},'score_histogram':dict(sorted(Counter(x['score'] for x in decisions).items())),'selected_score_histogram':dict(sorted(Counter(x['score'] for x in selected).items())),'independent_formula_recheck':True,'all_threshold_matches_retained':True,'extra_quality_filters':[],'training_samples_built':0,'T_SFT':None,'training_started':False,'gpu_allocations':0,'output_hashes':{f:sha(ROOT/f) for f in ['data/selection_decisions.jsonl','data/selected_steps.jsonl','config/selection_policy.json']}}
 dump(ROOT/'checks/selection.json',report)
 dump(ROOT/'STATUS.json',{'updated_at':now(),'phase':'steps_01_02_complete','completed_steps':[1,2],'next_step':3,'selected_steps':2623,'training_samples_built':0,'T_SFT':None,'resource_policy':'config/resource_policy.json','physical_gpu_indices':[1],'training_started':False,'scope':'User authorized steps 1 and 2; no step 3 or later executed.'})
 return report
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--labels',default=read(ROOT/'config/draft.json')['selection']['input']);ap.add_argument('--threshold',type=int,default=4);a=ap.parse_args()
 try:print(json.dumps(select(a.labels,a.threshold),ensure_ascii=False))
 except Exception as e:dump(ROOT/'checks/selection.json',{'passed':False,'at':now(),'error':f'{type(e).__name__}: {e}'});raise
