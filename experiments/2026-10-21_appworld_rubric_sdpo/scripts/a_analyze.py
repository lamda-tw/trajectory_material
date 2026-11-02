"""Prespecified local-repair metrics and paired family-cluster bootstrap."""
from a_common import *
from analyze_sources import csv_write
import argparse,collections
def collect(stage):
 lookup={x['state_id']:p for x,p in packages(stage)};rows=[]
 for x in read(R/'phase_a/config'/f'{stage}_blind_index.json'):
  jp=R/'phase_a/judging'/('candidate_'+stage)/x['id']/'base/judgement.json'
  if not jp.exists():continue
  result=read(jp);labels={i:l for i,l,_ in result['steps']}[x['target_step']];reason={i:r for i,_,r in result['steps']}[x['target_step']]
  p=lookup[x['state_id']];s=p['state'];D=[i for i,c in enumerate(p['source_labels_v7']) if c=='F'];cleared=all(labels[i] in 'PN' for i in D)
  newF=[i for i,c in enumerate(labels) if c=='F' and i not in D];ex=read(R/x['execution']);g=read(R/x['generation']);c=ex['candidate'];apis=c['local_api_responses']
  rows.append({**{k:x[k] for k in ['id','state_id','arm','repeat']},'task_id':s['task_id'],'family':s['family'],'stratum':s['stratum'],'panel':s['panel'],'source_labels_v7':p['source_labels_v7'],'labels_v7':labels,'reason':reason,'LR':int(labels[0]=='P' and 'F' not in labels and cleared),'strict_LR':int(labels[0]=='P' and 'F' not in labels and 'U' not in labels and cleared),'old_F_cleared':int(cleared),'old_F_to_U':int(any(labels[i]=='U' for i in D)),'new_F_dimensions':len(newF),'new_F_dimension_rate':len(newF)/max(1,8-len(D)),'any_new_F':int(bool(newF)),'any_U':int('U' in labels),'executable_no_F':int(labels[0]=='P' and 'F' not in labels),'execution_error':int(c['execution_error']),'no_code':int(c['no_code']),'exact_code_repeat':int(c['code_repeated']),'completion_api':int(ex['termination']=='completion_api'),'db_changed':int(ex['before']['db_tables']!=ex['after']['db_tables']),'api_calls':len(apis),'documentation_calls':sum(a['app_name']=='api_docs' for a in apis),'business_api_calls':sum(a['app_name'] not in ['api_docs','supervisor'] for a in apis),'length_termination':int(g['finish_reason']=='length'),'prompt_tokens':len(g['prompt_ids']),'response_tokens':len(g['response_ids']),'generation_seconds':g['elapsed_seconds'],'uses_later_evidence':bool(p['feedback'] and p['feedback']['uses_later_evidence'])})
 return rows
def estimate(rows,arm,metric,balanced=True):
 groups=collections.defaultdict(list)
 for x in rows:
  if x['arm']==arm:groups[x['stratum']].append(x[metric])
 if not groups:return None
 if balanced:return sum(sum(v)/len(v) for v in groups.values())/len(groups)
 return sum(sum(v) for v in groups.values())/sum(map(len,groups.values()))
def comparison(rows,arm,base,metric,balanced=True):
 import numpy as np
 grouped=collections.defaultdict(lambda:collections.defaultdict(list))
 for x in rows:grouped[x['state_id']][x['arm']].append(x)
 units=[]
 for sid,g in grouped.items():
  if arm not in g or base not in g:continue
  d=sum(x[metric] for x in g[arm])/len(g[arm])-sum(x[metric] for x in g[base])/len(g[base])
  x=g[arm][0];units.append((x['family'],x['stratum'],d))
 if not units:return None
 families=sorted({x[0] for x in units});strata=sorted({x[1] for x in units});fidx={s:i for i,s in enumerate(families)};sidx={s:i for i,s in enumerate(strata)}
 sums=np.zeros((len(families),len(strata)));counts=np.zeros_like(sums)
 for f,s,d in units:sums[fidx[f],sidx[s]]+=d;counts[fidx[f],sidx[s]]+=1
 def calculate(weights):
  a=weights@sums;n=weights@counts
  if balanced:
   if np.any(n==0):return None
   return float(np.mean(a/n))
  return float(a.sum()/n.sum())
 rng=np.random.default_rng(20261021);samples=[];skipped=0
 while len(samples)<10000:
  w=rng.multinomial(len(families),np.full(len(families),1/len(families)));v=calculate(w)
  if v is None:skipped+=1
  else:samples.append(v)
 return {'arm':arm,'baseline':base,'metric':metric,'states':len(units),'families':len(families),'difference':calculate(np.ones(len(families))),'ci95':np.quantile(samples,[.025,.975]).tolist(),'bootstrap_iterations':10000,'missing_stratum_redraws':skipped,'family_clustered':True,'strata_equally_weighted':balanced}
def main(stage):
 rows=collect(stage);index=read(R/'phase_a/analysis'/f'{stage}_execution_index.json');expected=sum(x['execution_valid'] for x in index)
 assert len(rows)==expected,'Candidate judging incomplete'
 folder=R/'phase_a/analysis'/stage;folder.mkdir(parents=True,exist_ok=True);csv_write(folder/'candidate_metrics.csv',rows)
 by_state=collections.defaultdict(list)
 for x in index:by_state[x['state_id']].append(x)
 complete={sid for sid,items in by_state.items() if all(x['execution_valid'] for x in items)}
 fail=[x for x in rows if x['panel']!='formal_good' and x['state_id'] in complete];good=[x for x in rows if x['panel']=='formal_good' and x['state_id'] in complete]
 metrics=['LR','strict_LR','old_F_cleared','old_F_to_U','new_F_dimension_rate','any_new_F','any_U','execution_error','no_code','exact_code_repeat','completion_api','db_changed','documentation_calls','business_api_calls','response_tokens']
 summaries=[]
 for stratum in ['balanced_all']+sorted({x['stratum'] for x in fail}):
  subset=fail if stratum=='balanced_all' else [x for x in fail if x['stratum']==stratum]
  for arm in sorted({x['arm'] for x in subset}):
   summaries.append({'stratum':stratum,'arm':arm,'states':len({x['state_id'] for x in subset if x['arm']==arm}),**{m:estimate(subset,arm,m) for m in metrics}})
 csv_write(folder/'arm_summary.csv',summaries)
 comparisons=[]
 if stage=='formal':
  for a,b,m in [('C2_feedback','C0_original','LR'),('C2_feedback','C1_fail_labels','LR'),('C3_feedback_and_original_answer','C2_feedback','LR'),('C2_feedback','C0_original','new_F_dimension_rate')]:comparisons.append(comparison(fail,a,b,m))
  comparisons.append(comparison(good,'C2_feedback','C0_original','executable_no_F',False))
 report={'stage':stage,'candidate_rows':len(rows),'fail_states':len({x['state_id'] for x in fail}),'good_states':len({x['state_id'] for x in good}),'comparisons':comparisons,'source_v7_F_fixed_before_generation':True,'weights_updated':False,'task_completion_improvement_measured':False,'independent_human_review_completed':False,'assistant_evidence_review_pending':True,'coverage_adjusted_C2_LR_yield':sum(x['LR'] for x in fail if x['arm']=='C2_feedback')/(100*2) if stage=='formal' else None}
 report['states_excluded_for_incomplete_paired_execution']=sorted(set(by_state)-complete)
 write_json(folder/'summary.json',report);print(json.dumps({'summary':report,'balanced_arms':[x for x in summaries if x['stratum']=='balanced_all']},ensure_ascii=False,indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['calibration','formal'],required=True);main(ap.parse_args().stage)
