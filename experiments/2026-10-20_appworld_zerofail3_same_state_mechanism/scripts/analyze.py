"""Frozen paired analysis; consumes saved evidence only, no generation or judging."""
from experiment import *
from statistics_protocol import GROUPS,SEEDS,PRIMARY,OPPORTUNITY,eligible,estimate,pair_rows,bootstrap
from collections import Counter,defaultdict
import statistics as st
O=R/'analysis';PANELS=['anchor','focus_A','focus_B','focus_C']
LABEL_METRICS=['relevant_gap_reduced','grounded_application','coverage_progress','redundant_known_information','unsupported_execution','state_contradiction','premature_scope_claim','wrong_scope_action']
COSTS=['redundant_known_information','unsupported_execution','state_contradiction','premature_scope_claim','wrong_scope_action','execution_error','no_code','truncated','generated_tokens','actual_api_requests','documentation_requests','code_repeated','premature_termination']

def csvsave(name,values):
 if not values:return
 fields=list(dict.fromkeys(k for x in values for k in x))
 with (O/name).open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(values)

def category_lookup(states):
 mapping={(x['family'],x['requirement']):x['category'] for x in csv.DictReader((R/'config/evaluator_type_mapping.csv').open())};assert len(mapping)==97
 root=Path(C['paths']['appworld_data']);null={x['task_id']:read(root/f"tasks/{x['task_id']}/ground_truth/answer.json") is None for x in states.values()}
 def category(row,requirement):
  cat=mapping[row['family'],requirement]
  return ('answer_null' if null[row['task_id']] else 'answer_value') if cat=='answer' else cat
 return category

def first_actions():
 states={x['state_id']:x for x in rows()};by_model={model_key(m):m for m in models()};links=read(O/'judgement_index.json');common=read(O/'common_states.json');category=category_lookup(states);records=[];checks=[];opportunities=[]
 for sid,s in states.items():
  card=read(R/'judge_runs/cards'/key(sid)/'judgement.json');opportunities.append({k:s[k] for k in ['state_id','task_id','family','source_group','source_training_seed','panel','mechanical_stage','paging_subtype','before_step']}|{op:card[op]['label'] for op in list(OPPORTUNITY.values())+['feedback_opportunity','state_use_opportunity']}|{'common_execution_valid':int(sid in common['state_ids'])})
 for link in links:
  sid=link['state_id'];s=states[sid];m=by_model[link['model']];j=read(link['judgement']);card=read(R/'judge_runs/cards'/key(sid)/'judgement.json');g=read(R/'results/generations'/link['model']/f'{key(sid)}.json');ex=read(R/'results/executions'/link['model']/f'{key(sid)}.json');cand=ex['candidate'];before=read(R/'results/evaluators/reference'/f'{key(sid)}.before.json');after=read(R/'results/evaluators'/link['model']/f'{key(sid)}.after.json');assert before['checks'].keys()==after['checks'].keys()
  x={k:s[k] for k in ['state_id','task_id','family','panel','source_group','source_training_seed','mechanical_stage','paging_subtype','before_step']};x.update(group=m['group'],seed=m['training_seed'],model=link['model'])
  for op in list(OPPORTUNITY.values())+['feedback_opportunity','state_use_opportunity']:x[op]=card[op]['label']
  for field in LABEL_METRICS:x[field]=int(j[field]['label']=='yes');x[field+'_unknown']=int(j[field]['label']=='uncertain');x[field+'_label']=j[field]['label']
  x.update(gap_kind=j['relevant_gap_reduced']['gap_kind'],coverage_stage=j['coverage_progress']['coverage_stage'],contradiction_subtypes=','.join(j['state_contradiction']['subtypes']),contradiction_code=int('code_state_use' in j['state_contradiction']['subtypes']),contradiction_narrative=int('narrative_only' in j['state_contradiction']['subtypes']),feedback_response=j['feedback_response']['label'],state_use=j['state_use']['label'],repetition=j['repetition']['label'],documentation=j['documentation']['label'],termination=j['termination']['label'],meaningful_progress=','.join(j['meaningful_progress']['labels']),execution_error=int(cand['execution_error']),no_code=int(cand['no_code']),truncated=int(g['finish_reason']=='length'),generated_tokens=len(g['response_ids']),actual_api_requests=len(cand['actual_request_methods_urls']),documentation_requests=sum('/api_docs/' in v['url'] for v in cand['actual_request_methods_urls']),code_repeated=int(cand['code_repeated']),premature_termination=int(j['termination']['label']=='premature_or_wrong'),premature_termination_unknown=int(j['termination']['label']=='uncertain'),before_pass_fraction=before['num_passes']/before['num_tests'],after_pass_fraction=after['num_passes']/after['num_tests'],after_task_success=int(after['success']),completion_api_reached=int(ex['after']['completed']),evaluator_gain=sum(not b and after['checks'][req] for req,b in before['checks'].items()),evaluator_loss=sum(b and not after['checks'][req] for req,b in before['checks'].items()),rubrics=''.join(r['label'] for r in j['rubrics']),judgement=link['judgement'],evidence_hash=link['evidence_hash'])
  records.append(x)
  for req,b in before['checks'].items():
   a=after['checks'][req];checks.append({k:x[k] for k in ['group','seed','state_id','task_id','family','panel','source_group','mechanical_stage']}|{'requirement':req,'category':category(x,req),'before':int(b),'after':int(a),'gain':int(a and not b),'loss':int(b and not a)})
 assert len(records)==len(common['state_ids'])*9
 csvsave('behavior_rows.csv',records);csvsave('opportunity_and_state_coverage.csv',opportunities);csvsave('evaluator_checks.csv',checks)
 metrics=[];paired=[];coverage=[]
 for panel in PANELS:
  mode='anchor' if panel=='anchor' else 'focused';xx=[x for x in records if x['panel']==panel]
  for group in GROUPS:
   for seed in SEEDS+['all']:
    subset=[x for x in xx if x['group']==group and (seed=='all' or x['seed']==seed)]
    for metric in list(OPPORTUNITY)+COSTS+['before_pass_fraction','after_pass_fraction','after_task_success']:
     yy=[r for r in subset if eligible(r,metric)];unk=sum(x.get(metric+'_unknown',0) for x in yy);upper=[dict(x,**{metric:x[metric]+x.get(metric+'_unknown',0)}) for x in yy]
     metrics.append({'panel':panel,'group':group,'seed':seed,'metric':metric,'eligible_rows':len(yy),'eligible_states':len({x['state_id'] for x in yy}),'eligible_tasks':len({x['task_id'] for x in yy}),'eligible_families':len({x['family'] for x in yy}),'numerator':sum(x[metric] for x in yy),'unknown':unk,'pooled_mean':st.mean(x[metric] for x in yy) if yy else None,'balanced_mean':estimate(yy,metric,mode),'unknown_upper_balanced':estimate(upper,metric,mode)})
  targets=([PRIMARY[panel]] if panel in PRIMARY else [])+['after_pass_fraction','after_task_success']+COSTS
  for arm,baseline in [('zerofail3','random'),('zerofail3','net3'),('net3','random')]:
   for metric in targets:
    diff=pair_rows(xx,arm,baseline,metric);seed_values={f'seed_{seed}':estimate([x for x in diff if x['seed']==seed],metric,mode) for seed in SEEDS};need_ci=(metric==PRIMARY.get(panel) or panel=='anchor' and metric in ['execution_error','redundant_known_information','after_pass_fraction']) and arm=='zerofail3'
    ci=bootstrap(xx,arm,baseline,metric,mode) if need_ci else {'low':None,'high':None,'valid_replicates':0,'attempted_replicates':0}
    paired.append({'panel':panel,'contrast':arm+' - '+baseline,'metric':metric,'balanced_difference':estimate(diff,metric,mode),**seed_values,'bootstrap_low':ci['low'],'bootstrap_high':ci['high'],'bootstrap_valid':ci['valid_replicates'],'bootstrap_attempted':ci['attempted_replicates']})
  if panel in PRIMARY:
   metric=PRIMARY[panel];valid=[s for s in opportunities if s['panel']==panel and s['common_execution_valid'] and s[OPPORTUNITY[metric]]=='yes'];counts=Counter(x['source_group'] for x in valid);families=len({s['family'] for s in valid});passed=len(valid)>=12 and min(counts[g] for g in GROUPS)>=3 and families>=6
   coverage.append({'panel':panel,'metric':metric,'yes_states':len(valid),'families':families,**{g+'_states':counts[g] for g in GROUPS},'prespecified_coverage_gate':passed,'interpretation':'eligible exploratory comparison' if passed else 'insufficient opportunity coverage; descriptive only'})
 csvsave('behavior_metrics.csv',metrics);csvsave('paired_behavior_contrasts.csv',paired);csvsave('mechanism_coverage_gates.csv',coverage)
 slices=[]
 for panel in PANELS:
  mode='anchor' if panel=='anchor' else 'focused'
  for dimension,values in [('source_group',GROUPS),('paging_subtype',['paging_spec_available','visible_nonempty_single_page']),('discovery_family',['d4e9306','other']),('family',sorted({x['family'] for x in records}))]:
   for value in values:
    xx=[x for x in records if x['panel']==panel and ((x['family']=='d4e9306')==(value=='d4e9306') if dimension=='discovery_family' else x[dimension]==value)]
    for group in GROUPS:
     for metric in list(OPPORTUNITY)+['execution_error','redundant_known_information','after_pass_fraction','wrong_scope_action']:
      yy=[x for x in xx if x['group']==group and eligible(x,metric)];slice_mode='anchor' if dimension in ['source_group','family'] else mode
      slices.append({'panel':panel,'slice':dimension,'value':value,'group':group,'metric':metric,'rows':len(yy),'states':len({r['state_id'] for r in yy}),'mean':estimate(yy,metric,slice_mode),'weighting':'task equal within displayed source/family' if slice_mode=='anchor' else 'source and task equal'})
 csvsave('behavior_source_family_subtype_slices.csv',slices)
 rubrics=[]
 for panel in PANELS:
  for group in GROUPS:
   for seed in SEEDS+['all']:
    xx=[x for x in records if x['panel']==panel and x['group']==group and (seed=='all' or x['seed']==seed)]
    for i in range(8):cnt=Counter(x['rubrics'][i] for x in xx);rubrics.append({'panel':panel,'group':group,'seed':seed,'rule':f'R{i+1}','rows':len(xx),**{k:cnt[k] for k in 'PFUN'}})
 csvsave('rubric_distributions.csv',rubrics)
 evpairs=[];lookup={(x['group'],x['seed'],x['state_id'],x['requirement']):x for x in checks}
 for arm,baseline in [('zerofail3','random'),('zerofail3','net3'),('net3','random')]:
  for x in checks:
   if x['group']!=arm:continue
   b=lookup[baseline,x['seed'],x['state_id'],x['requirement']];assert x['before']==b['before'];evpairs.append(x|{'contrast':arm+' - '+baseline,'baseline_after':b['after'],'wins':int(x['after']>b['after']),'losses':int(x['after']<b['after'])})
 csvsave('paired_evaluator_checks.csv',evpairs)
 categories=[]
 for panel in PANELS:
  for group in GROUPS:
   for seed in SEEDS+['all']:
    for category in sorted({x['category'] for x in checks}):
     xx=[x for x in checks if x['panel']==panel and x['group']==group and x['category']==category and (seed=='all' or x['seed']==seed)];categories.append({'panel':panel,'group':group,'seed':seed,'category':category,'checks':len(xx),'before_pass':sum(x['before'] for x in xx),'after_pass':sum(x['after'] for x in xx),'gains':sum(x['gain'] for x in xx),'losses':sum(x['loss'] for x in xx)})
 csvsave('evaluator_categories.csv',categories)
 reviews=[];linkmap={(x['model'],x['state_id']):x for x in links};recordmap={(x['model'],x['state_id']):x for x in records}
 for item in read(R/'config/random_review_manifest.json'):
  if not item['common_execution_valid']:continue
  link=linkmap[item['model'],item['state_id']];orig=read(link['judgement']);repeat=read(R/'judge_runs/review_repeat'/link['evidence_hash']/(link['alias']+'_'+key(item['state_id']))/'judgement.json');row=recordmap[item['model'],item['state_id']]
  for field in LABEL_METRICS+['termination','feedback_response','state_use','repetition','documentation']:
   a=orig[field]['label'];b=repeat[field]['label'];reviews.append({'model':item['model'],'state_id':item['state_id'],'field':field,'original':a,'repeat':b,'agree':int(a==b),'opportunity_eligible':int(eligible(row,field))})
  for i in range(8):reviews.append({'model':item['model'],'state_id':item['state_id'],'field':f'R{i+1}','original':orig['rubrics'][i]['label'],'repeat':repeat['rubrics'][i]['label'],'agree':int(orig['rubrics'][i]['label']==repeat['rubrics'][i]['label']),'opportunity_eligible':1})
 csvsave('judge_repeat_consistency.csv',reviews);agreement=[]
 for field in sorted({r['field'] for r in reviews}):
  rr=[r for r in reviews if r['field']==field and r['opportunity_eligible']];n=len(rr);v=sum(r['agree'] for r in rr)/n if n else None;agreement.append({'field':field,'n':n,'agreement':v,'primary_measurement_gate':'insufficient_review_coverage' if field in OPPORTUNITY and n<12 else 'unstable' if field in OPPORTUNITY and v is not None and v<.8 else 'passed' if field in OPPORTUNITY else 'auxiliary','confusion':dict(Counter(r['original']+' -> '+r['repeat'] for r in rr))})
 atomic_json(O/'judge_repeat_summary.json',agreement)
 summary={'phase1_complete':True,'formal_states':129,'common_states':len(common['state_ids']),'generated_first_actions':sum(len(list((R/'results/generations'/model_key(m)).glob('*.json'))) for m in models()),'judged_model_state_rows':len(records),'unique_judged_evidence':len({x['evidence_hash'] for x in links}),'coverage_gates':coverage,'repeat_agreement':agreement,'local_gpu':1};atomic_json(O/'PHASE1_SUMMARY.json',summary)
 return records

def continuation_analysis():
 selected={x['state_id']:x for x in rows('continuation_states.csv')};category=category_lookup(selected);records=[];checks=[]
 for receiver in [m for m in models() if m['training_seed']==20261015]:
  for first in models():
   tag='continuation/'+model_key(receiver)+'/'+model_key(first)
   for sid,s in selected.items():
    check=R/'results/continuation_checks'/tag/f'{key(sid)}.json'
    if not check.exists():continue
    info=read(check);branch=read(info['source']);before=read(R/'results/evaluators/reference'/f'{key(sid)}.before.json');h0=read(R/'results/evaluators'/model_key(first)/f'{key(sid)}.after.json')
    for horizon in [4,12]:
     ev=read(R/'results/evaluators'/tag/f'{key(sid)}.h{horizon}.json');actual=branch['readout_actual_followup_steps'][f'h{horizon}'];steps=branch['followup_steps'][:actual];assert before['checks'].keys()==h0['checks'].keys()==ev['checks'].keys()
     row={k:s[k] for k in ['state_id','task_id','family','source_group','source_training_seed','mechanical_stage','paging_subtype','before_step']};row.update(panel=s['continuation_panel'],group=first['group'],seed=first['training_seed'],receiver=model_key(receiver),horizon=horizon,actual_followup_steps=actual,termination=branch['termination'] if actual==len(branch['followup_steps']) else 'readout_before_termination',before_pass_fraction=before['num_passes']/before['num_tests'],h0_pass_fraction=h0['num_passes']/h0['num_tests'],pass_fraction=ev['num_passes']/ev['num_tests'],task_success=int(ev['success']),completion_api_reached=int(branch[f'h{horizon}']['completed']),evaluator_gain=sum(not b and ev['checks'][req] for req,b in before['checks'].items()),evaluator_loss=sum(b and not ev['checks'][req] for req,b in before['checks'].items()),gain_after_first=sum(not b and ev['checks'][req] for req,b in h0['checks'].items()),loss_after_first=sum(b and not ev['checks'][req] for req,b in h0['checks'].items()),generated_tokens=sum(len(x['response_ids']) for x in steps),execution_errors=sum(x['execution_error'] for x in steps),actual_api_requests=sum(len(x['actual_request_methods_urls']) for x in steps),documentation_requests=sum('/api_docs/' in z['url'] for x in steps for z in x['actual_request_methods_urls']),source=info['source'])
     records.append(row)
     for req,b in before['checks'].items():
      a=ev['checks'][req];f=h0['checks'][req];checks.append({k:row[k] for k in ['group','seed','state_id','task_id','family','panel','source_group','mechanical_stage','receiver','horizon']}|{'requirement':req,'category':category(row,req),'before':int(b),'h0':int(f),'after':int(a),'gain':int(a and not b),'loss':int(b and not a),'gain_after_first':int(a and not f),'loss_after_first':int(f and not a)})
 # Strict primary: every one of 9 first models x 3 receivers is present for the same state.
 complete={sid for sid in selected if sum(x['state_id']==sid and x['horizon']==12 for x in records)==27};csvsave('continuation_all_available_rows.csv',records);primary=[x for x in records if x['state_id'] in complete];csvsave('continuation_common_rows.csv',primary);csvsave('continuation_evaluator_checks.csv',checks)
 paired=[];summaries=[];slices=[]
 for panel in ['core','discovery_bridge']:
  mode='continuation' if panel=='core' else 'anchor'
  for horizon in [4,12]:
   xx=[x for x in primary if x['panel']==panel and x['horizon']==horizon]
   for group in GROUPS:
    for seed in SEEDS+['all']:
     yy=[x for x in xx if x['group']==group and (seed=='all' or x['seed']==seed)]
     for metric in ['before_pass_fraction','h0_pass_fraction','pass_fraction','task_success','actual_followup_steps','generated_tokens','execution_errors','actual_api_requests']:
      summaries.append({'panel':panel,'horizon':horizon,'group':group,'seed':seed,'metric':metric,'rows':len(yy),'states':len({r['state_id'] for r in yy}),'balanced_mean':estimate(yy,metric,mode)})
   for arm,baseline in [('zerofail3','random'),('zerofail3','net3'),('net3','random')]:
    for metric in ['pass_fraction','task_success']:
     differences=pair_rows(xx,arm,baseline,metric);ci=bootstrap(xx,arm,baseline,metric,mode) if panel=='core' and horizon==12 and metric=='pass_fraction' and arm=='zerofail3' else {'low':None,'high':None,'valid_replicates':0,'attempted_replicates':0}
     paired.append({'panel':panel,'horizon':horizon,'contrast':arm+' - '+baseline,'metric':metric,'balanced_difference':estimate(differences,metric,mode),**{f'seed_{seed}':estimate([r for r in differences if r['seed']==seed],metric,mode) for seed in SEEDS},'bootstrap_low':ci['low'],'bootstrap_high':ci['high'],'bootstrap_valid':ci['valid_replicates'],'bootstrap_attempted':ci['attempted_replicates']})
     for dimension,values in [('receiver',[model_key(m) for m in models() if m['training_seed']==20261015]),('source_group',GROUPS),('mechanical_stage',list('ABC')),('discovery_family',['d4e9306','other'])]:
      for value in values:
       yy=[r for r in differences if ((r['family']=='d4e9306')==(value=='d4e9306') if dimension=='discovery_family' else r[dimension]==value)];slice_mode=mode if dimension=='receiver' else 'anchor'
       slices.append({'panel':panel,'horizon':horizon,'contrast':arm+' - '+baseline,'metric':metric,'slice':dimension,'value':value,'rows':len(yy),'states':len({r['state_id'] for r in yy}),'difference':estimate(yy,metric,slice_mode),'weighting':slice_mode})
 csvsave('continuation_model_summary.csv',summaries);csvsave('paired_continuation_contrasts.csv',paired);csvsave('continuation_receiver_source_stage_slices.csv',slices)
 epairs=[];lookup={(x['group'],x['seed'],x['state_id'],x['receiver'],x['horizon'],x['requirement']):x for x in checks}
 for arm,baseline in [('zerofail3','random'),('zerofail3','net3'),('net3','random')]:
  for x in checks:
   if x['group']!=arm:continue
   b=lookup.get((baseline,x['seed'],x['state_id'],x['receiver'],x['horizon'],x['requirement']))
   if b is None:continue
   epairs.append(x|{'contrast':arm+' - '+baseline,'baseline_after':b['after'],'wins':int(x['after']>b['after']),'losses':int(x['after']<b['after']),'strict_common_state':int(x['state_id'] in complete)})
 csvsave('paired_continuation_evaluator_checks.csv',epairs)
 categories=[]
 for panel in ['core','discovery_bridge']:
  for horizon in [4,12]:
   for contrast in ['zerofail3 - random','zerofail3 - net3','net3 - random']:
    for cat in sorted({x['category'] for x in epairs}):
     xx=[x for x in epairs if x['strict_common_state'] and x['panel']==panel and x['horizon']==horizon and x['contrast']==contrast and x['category']==cat];categories.append({'panel':panel,'horizon':horizon,'contrast':contrast,'category':cat,'checks':len(xx),'wins':sum(x['wins'] for x in xx),'losses':sum(x['losses'] for x in xx),'net':sum(x['wins']-x['losses'] for x in xx)})
 csvsave('continuation_evaluator_categories.csv',categories)
 summary={'selected_states':20,'common_completed_states':len(complete),'core_common_states':sum(selected[s]['continuation_panel']=='core' for s in complete),'discovery_common_states':sum(selected[s]['continuation_panel']=='discovery_bridge' for s in complete),'branches_completed':len(records)//2,'additional_generations':sum(len(list(p.glob('step_*.json'))) for p in (R/'results/continuation_generations/continuation').glob('*/*/*')),'missing_state_ids':sorted(set(selected)-complete)};atomic_json(O/'CONTINUATION_SUMMARY.json',summary)
 return records

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--with-continuation',action='store_true');a=ap.parse_args();first_actions()
 if a.with_continuation:continuation_analysis()
 print('Saved paired analyses; no generation or scoring occurred.',flush=True)
