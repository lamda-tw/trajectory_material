"""Nontrivial weighting/sign test plus input-boundary and parser regression checks; no workloads."""
from statistics_protocol import *
from public_payload import public_prefix,sanitize
from experiment import data,rows,read,R
from common import parse_code

def run():
 source_values={'random':{'a':[0,0,0],'b':[1]},'net3':{'c':[0]},'zerofail3':{'d':[1],'e':[1]}};r=[]
 for source,tasks in source_values.items():
  for task,values in tasks.items():
   for j,value in enumerate(values):
    for seed in SEEDS:r.append({'group':'random','seed':seed,'state_id':task+str(j),'task_id':task,'family':task,'source_group':source,'mechanical_stage':'A','metric':value})
 assert abs(estimate(r,'metric','focused')-.5)<1e-12
 assert abs(sum(x['metric'] for x in r)/len(r)-.5)>.05, 'Fixture must distinguish pooled rate from task/source weighting'
 pairs=r+[dict(x,group='zerofail3',metric=x['metric']+2) for x in r]
 assert estimate(pair_rows(pairs,'zerofail3','random','metric'),'metric','focused')==2
 assert estimate(pair_rows(pairs,'random','zerofail3','metric'),'metric','focused')==-2
 b=bootstrap(pairs,'zerofail3','random','metric','focused',iterations=50);assert b['low']==b['high']==2 and b['valid_replicates']==50
 assert estimate([x for x in r if x['source_group']!='net3'],'metric','focused') is None
 assert parse_code('```python\nx=1')[0]=='x=1' and parse_code('text without code')[0]==''
 checked=0
 for row in rows('calibration_states.csv'):
  raw=data(row);public=public_prefix(raw);assert public['state_id']==row['public_state_id'] and public['state_id']!=row['state_id'];assert 'candidate' not in public
  assert len(public['history'])==int(row['before_step'])-1
  assert set(public)=={'state_id','prefix_hash','task','agent_instructions','history'}
  clean,audit=sanitize(public);assert audit['hidden_evaluator_included'] is False;checked+=1
 print({'passed':True,'task_and_source_weighting':'verified against deliberately unbalanced states','paired_sign':True,'bootstrap':50,'missing_source_is_NA':True,'allowlisted_calibration_prefixes':checked,'no_gpu_or_judge':True})
if __name__=='__main__':run()
