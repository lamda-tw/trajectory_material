"""Compare stored labels on identical trajectories; no scoring and no causal claim."""
from pathlib import Path
from collections import Counter
import csv,json
R=Path(__file__).resolve().parents[1]
OLD=R.parents[1]/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
PILOT=R.parents[1]/'2026-10-13_appworld_step_rubric_v6_en_pilot'
def read(p):return json.loads(p.read_text())
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def keep(z):return z[0]=='P' and z[6]=='N' and all(x in 'PN' for x in z[1:6])
def main():
 new={p.parent.name:{n:(z,w) for n,z,w in read(p)['steps']} for p in (R/'runs/scoring').glob('*/judgement.json')};assert len(new)==540
 old={p.parent.name:{n:(z,w) for n,z,w in read(p)['steps']} for p in (OLD/'runs/scoring').glob('*/judgement.json')};assert set(old)==set(new)
 transitions={f'R{i}':{a:{b:0 for b in 'PFUN'} for a in 'PFUN'} for i in range(1,9)};changed=[];selection=Counter()
 for sid in sorted(new):
  assert set(new[sid])==set(old[sid])
  for step,(b,reason) in new[sid].items():
   a=old[sid][step][0];selection[f'{keep(a)}->{keep(b)}']+=1
   for i,(x,y) in enumerate(zip(a,b)):
    k=f'R{i+1}';transitions[k][x][y]+=1
    if x!=y:changed.append({'id':sid,'step':step,'rubric':k,'chinese_v5_gpt56':x,'english_v6_gpt61':y,'new_reason':reason})
 with (R/'analysis/label_changes_vs_chinese.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=['id','step','rubric','chinese_v5_gpt56','english_v6_gpt61','new_reason']);w.writeheader();w.writerows(changed)
 comparison={}
 for k,t in transitions.items():
  n=sum(sum(v.values()) for v in t.values());same=sum(t[x][x] for x in 'PFUN');app=n-t['N']['N'];comparison[k]={'cells':n,'same':same,'agreement':same/n,'either_applicable':app,'same_either_applicable':same-t['N']['N'],'transition_old_to_new':t,'F_boundary_flips':sum(t[x][y] for x in 'PFUN' for y in 'PFUN' if (x=='F')!=(y=='F'))}
 checks={}
 for name in ['legacy_v5_regression_checks','development_boundary_checks','holdout_boundary_checks','legacy_full_boundary_checks','current_raw_boundary_checks']:
  items=[]
  for c in read(R/'review'/f'{name}.json')['checks']:
   sid,step,k=c['trajectory'],c['step'],c['rubric'];v=new[sid][step][0][int(k[1:])-1];prev=old[sid][step][0][int(k[1:])-1]
   items.append({**c,'new_label':v,'old_label':prev,'new_match':v in c['expected'],'old_match':prev in c['expected']})
  checks[name]={'n':len(items),'new_matches':sum(c['new_match'] for c in items),'old_matches':sum(c['old_match'] for c in items),'items':items,'scope':'Targeted known cases, not representative independent accuracy; v5 and v6 semantics differ. Do not sum overlapping check lists.'}
 pilot_compare={}
 for stage in ['development_format','holdout_format']:
  cells=matches=0;byrubric=Counter()
  for p in (PILOT/'runs'/stage).glob('*/judgement.json'):
   for step,a,_ in read(p)['steps']:
    b=new[p.parent.name][step][0];cells+=8;matches+=sum(x==y for x,y in zip(a,b))
    for i,(x,y) in enumerate(zip(a,b)):
     if x!=y:byrubric[f'R{i+1}']+=1
  pilot_compare[stage]={'cells':cells,'same':matches,'agreement':matches/cells,'changes_by_rubric':dict(byrubric),'scope':'Same frozen English prompt, different judge model: GPT-5.6 sol vs GPT-6.1 sol; agreement is not accuracy.'}
 result={'scope':'Identical 540 trajectories. Chinese v5/GPT-5.6 sol vs English v6/GPT-6.1 sol; language, rules and judge changed jointly. Quality-oriented configuration comparison, not isolated language ablation.','by_rubric':comparison,'changed_cells':len(changed),'all_cells':11254*8,'label_only_selection_transition':dict(selection),'known_checks':checks,'english_prompt_judge_comparison':pilot_compare}
 common=[json.loads(x) for x in (R/'research/common_pool_inventory.jsonl').read_text().splitlines() if json.loads(x)['common_pool']]
 paired=Counter();counts={'old':Counter(),'new':Counter()}
 for item in common:
  sid,step=item['trajectory_id'],int(item['step']);a=old[sid][step][0];b=new[sid][step][0]
  assert item['labels']==a
  paired[f'{keep(a)}->{keep(b)}']+=1
  for name,z in [('old',a),('new',b)]:
   counts[name]['base']+=keep(z);counts[name]['plus_R8P']+=keep(z) and z[7]=='P';counts[name]['R5P']+=keep(z) and z[4]=='P';counts[name]['R5P_R8P']+=keep(z) and z[4]=='P' and z[7]=='P'
 result['common_pool_selection']={'common_pool_steps':len(common),'transitions':dict(paired),'counts':{k:dict(v) for k,v in counts.items()},'scope':'Identical frozen mechanical eligibility pool, labels only changed; diagnostic, no training-data mutation.'}
 dump(R/'analysis/configuration_comparison.json',result)
 print('Compared 540 paired trajectories and known boundary checks.')
if __name__=='__main__':main()
