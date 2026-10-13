"""Local analysis only; does not invoke a model or execute trajectory code."""
from pathlib import Path
import json,csv,collections,hashlib,statistics
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
 stages={};by_stage={};all_attempts=[]
 for run in sorted((R/'runs').iterdir()):
  if not run.is_dir():continue
  labels={};counts={f'R{i}':collections.Counter() for i in range(1,9)};rows=[];mechanical=[]
  for file in sorted(run.glob('*/judgement.json')):
   sid=file.parent.name;d=read(file);payload=read(file.parent/'input.json');steps={s['id']:s for s in payload['steps']}
   labels[sid]={s:lab for s,lab,why in d['steps']}
   for s,lab,why in d['steps']:
    row={'id':sid,'step':s,'reason':why,**{f'R{i+1}':v for i,v in enumerate(lab)}};rows.append(row)
    for i,l in enumerate(lab):counts[f'R{i+1}'][l]+=1
    obs=steps[s]['observation']
    if obs.startswith('Execution failed.') and lab[0]!='F':mechanical.append({'id':sid,'step':s,'rubric':'R1','observed':lab[0],'issue':'Actual execution failure not labeled F'})
    if obs.strip()=='Execution successful.' and lab[0]!='P':mechanical.append({'id':sid,'step':s,'rubric':'R1','observed':lab[0],'issue':'Actual successful execution not labeled P'})
  checks={}
  for name in ['legacy_v5_regression_checks','development_boundary_checks','holdout_boundary_checks']:
   p=R/'review'/f'{name}.json'
   if not p.exists():continue
   evaluated=[]
   for c in read(p)['checks']:
    if c['trajectory'] not in labels:continue
    actual=labels[c['trajectory']][c['step']][int(c['rubric'][1:])-1]
    evaluated.append({**c,'actual':actual,'matched':actual in c['expected']})
   checks[name]={'n':len(evaluated),'matched':sum(c['matched'] for c in evaluated),'mismatches':[c for c in evaluated if not c['matched']]}
  attempts=[]
  for f in sorted(run.glob('*/attempt_*/record.json')):
   d=read(f);attempts.append(d);all_attempts.append({'stage':run.name,**d})
  # Legacy score() records success/failure in parent metadata and failure.json.
  if not attempts:
   for f in sorted(run.glob('*/metadata.json')):
    for a in read(f).get('attempts',[]):attempts.append(a);all_attempts.append({'stage':run.name,**a})
  usage=collections.Counter(); calls_with_completed_turn=0
  for ef in sorted(run.glob('*/attempt_*/events.jsonl')):
   events=[]
   for line in ef.read_text().splitlines():
    try: events.append(json.loads(line))
    except ValueError: pass
   completed=[e for e in events if e.get('type')=='turn.completed']
   if completed:
    calls_with_completed_turn+=1; usage.update(completed[-1].get('usage') or {})
  stages[run.name]={'trajectories':len(labels),'steps':len(rows),'label_counts':{k:dict(v) for k,v in counts.items()},'mechanical_flags':mechanical,'checks':checks,'attempts':len(attempts),'invalid_attempts':sum(a['status']!='valid' for a in attempts),'usage_including_invalid_completed_responses':dict(usage),'calls_started':len(list(run.glob('*/attempt_*'))),'calls_with_completed_turn':calls_with_completed_turn,'reason_max_characters':max([len(row['reason']) for row in rows],default=0),'accepted_call_seconds':[a.get('elapsed_seconds',a.get('seconds')) for a in attempts if a['status']=='valid']}
  by_stage[run.name]=labels
  if rows:
   with (R/'analysis'/f'{run.name}_steps.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 repeats={}
 for stage in by_stage:
  if not stage.endswith('_repeat'):continue
  primary=stage[:-7]
  if primary not in by_stage:continue
  changes=[];trajectory_repeat=[];totals=collections.Counter();same=collections.Counter();nonN=collections.Counter();same_nonN=collections.Counter();Fflips=collections.Counter();nsteps=0
  for sid,lab in by_stage[stage].items():
   if sid not in by_stage[primary]:continue
   tc=0;ts=0;first_kept=set();repeat_kept=set()
   for step,b in lab.items():
    a=by_stage[primary][sid][step];nsteps+=1;tc+=8;ts+=sum(v==w for v,w in zip(a,b))
    if a[0]=='P' and a[6]=='N' and all(v in 'PN' for v in a[1:6]):first_kept.add(step)
    if b[0]=='P' and b[6]=='N' and all(v in 'PN' for v in b[1:6]):repeat_kept.add(step)
    for i,(v,w) in enumerate(zip(a,b)):
     k=f'R{i+1}';totals[k]+=1;same[k]+=v==w
     if v!='N' or w!='N':nonN[k]+=1;same_nonN[k]+=v==w
     Fflips[k]+=(v=='F')!=(w=='F')
     if v!=w:changes.append({'id':sid,'step':step,'rubric':k,'first':v,'repeat':w})
   trajectory_repeat.append({'id':sid,'cells':tc,'same':ts,'agreement':ts/tc,'label_only_selected_first':len(first_kept),'label_only_selected_repeat':len(repeat_kept),'selected_intersection':len(first_kept&repeat_kept),'selected_union':len(first_kept|repeat_kept),'selection_changed_steps':sorted(first_kept^repeat_kept)})
  repeats[stage]={'trajectory_results':trajectory_repeat,'macro_trajectory_agreement':sum(t['agreement'] for t in trajectory_repeat)/len(trajectory_repeat) if trajectory_repeat else None,'steps':nsteps,'cells':sum(totals.values()),'same':sum(same.values()),'agreement':sum(same.values())/sum(totals.values()) if totals else None,'F_boundary_flips':sum(Fflips.values()),'by_rubric':{k:{'n':totals[k],'same':same[k],'agreement':same[k]/totals[k],'either_applicable':nonN[k],'same_either_applicable':same_nonN[k],'F_boundary_flips':Fflips[k]} for k in totals},'changes':changes}
 result={'stages':stages,'repeats':repeats,'limitations':['Targeted assistant checks are not independent human ground truth.','Legacy v5 expected labels may conflict with clarified v6 and require evidence adjudication.','Repeat stability is not accuracy; N and P dominance can inflate raw agreement.']}
 write(R/'analysis/summary.json',result)
 print(json.dumps({'stages':{s:{k:v for k,v in d.items() if k in ['trajectories','steps','attempts','invalid_attempts','mechanical_flags','checks']} for s,d in stages.items()},'repeats':{s:{k:v for k,v in d.items() if k!='changes'} for s,d in repeats.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
