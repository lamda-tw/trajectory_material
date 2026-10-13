"""Additional local stability and label-only selection diagnostics."""
from pathlib import Path
import json,collections
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def labels(stage):return {p.parent.name:{s:l for s,l,w in read(p)['steps']} for p in (R/'runs'/stage).glob('*/judgement.json')}
def keep(l):return l[0]=='P' and l[6]=='N' and all(x in 'PN' for x in l[1:6])
def main():
 summary=read(R/'analysis/summary.json');result={'repeats':{},'stages':{},'definitions':{'coverage':'(P+F+U)/all_steps','decidable_pass_rate':'P/(P+F); U and N excluded','kappa':'(p_o-p_e)/(1-p_e), p_e=sum_l p_first(l)*p_repeat(l)','either_applicable_agreement':'same/(number of pairs where at least one label is not N)','label_only_gate':'R1=P, R2..R6 in {P,N}, R7=N; R8 ignored. Does not include the actual training token/code eligibility filters.'}}
 for repeat in summary['repeats']:
  first=labels(repeat[:-7]);second=labels(repeat);rubrics={}
  for i in range(8):
   pairs=[(first[t][s][i],l[i]) for t,rows in second.items() if t in first for s,l in rows.items()];n=len(pairs)
   a=collections.Counter(x for x,y in pairs);b=collections.Counter(y for x,y in pairs);agree=sum(x==y for x,y in pairs)/n;chance=sum(a[l]*b[l] for l in 'PFUN')/(n*n)
   trans={x:{y:sum(u==x and v==y for u,v in pairs) for y in 'PFUN'} for x in 'PFUN'}
   rubrics[f'R{i+1}']={'pairs':n,'transition_first_to_repeat':trans,'kappa':(agree-chance)/(1-chance) if chance<1 else None,'applicability_agreement':sum((x=='N')==(y=='N') for x,y in pairs)/n}
  result['repeats'][repeat]=rubrics
 for stage,stats in summary['stages'].items():
  ls=labels(stage);kept=[(t,s,l) for t,rows in ls.items() for s,l in rows.items() if keep(l)];groups={};manifestname=stage.replace('_r1','').replace('_r2','');man=read(R/f'manifests/{manifestname}.json');meta={s['id']:s['selection_metadata_not_for_judge'] for s in man['samples']}
  for success in [True,False]:
   rows=[l for t,steps in ls.items() if meta[t]['official_success']==success for l in steps.values()]
   groups[str(success)]={'trajectories':sum(meta[t]['official_success']==success for t in ls),'steps':len(rows),'R8_F':sum(l[7]=='F' for l in rows)}
  result['stages'][stage]={'label_only_selected_steps':len(kept),'selected_R5_P':sum(l[4]=='P' for t,s,l in kept),'selected_R7_P':sum(l[6]=='P' for t,s,l in kept),'selected_R8_F':sum(l[7]=='F' for t,s,l in kept),'official_outcome_groups_for_description_only':groups,'rubrics':{k:{'coverage':(stats['steps']-v.get('N',0))/stats['steps'],'decidable_pass_rate':v.get('P',0)/(v.get('P',0)+v.get('F',0)) if v.get('P',0)+v.get('F',0) else None,'applicable_steps':stats['steps']-v.get('N',0)} for k,v in stats['label_counts'].items()}}
 versions=['development','development_r1','development_r2','development_format']
 common=set.intersection(*[set(labels(v)) & set(labels(v+'_repeat')) for v in versions]);comparison={}
 for v in versions:
  first=labels(v);second=labels(v+'_repeat');pairs=[(first[t][step],lab) for t in sorted(common) for step,lab in second[t].items()]
  n=8*len(pairs);same=sum(sum(x==y for x,y in zip(a,b)) for a,b in pairs)
  comparison[v]={'trajectories':len(common),'steps':len(pairs),'cells':n,'same':same,'agreement':same/n if n else None}
 result['common_development_repeat_comparison']={'ids':sorted(common),'versions':comparison,'interpretation':'Only trajectories with accepted first and repeat responses in every version. Raw agreement is not accuracy or proof of superiority.'}
 (R/'analysis/diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print('Saved local diagnostics.')
if __name__=='__main__':main()
