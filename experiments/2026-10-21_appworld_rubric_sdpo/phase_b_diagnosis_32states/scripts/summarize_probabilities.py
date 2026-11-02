"""Summarize forced-prefix distributions without treating all original tokens as wrong."""
from pathlib import Path
import sys,csv,statistics,math,collections
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from common import read,write_json
from transformers import AutoTokenizer
cfg=read(D/'config/runtime.json');tok=AutoTokenizer.from_pretrained(cfg['paths']['base_model'],local_files_only=True)
rows=[];decisions=[];reproductions=[];backends=[]
for item in read(D/'config/manifest.json')['states']:
 path=D/'probabilities'/(item['id']+'.json')
 if not path.exists():continue
 s=read(item['path']);p=read(path)
 if p['historical_training_reproduction']:reproductions.append({'state_id':s['id'],**p['historical_training_reproduction']})
 backends.extend({'state_id':s['id'],'condition':k,**v} for k,v in p['vllm_vs_transformers'].items())
 for pair,signals in p['signals'].items():
  row={'state_id':s['id'],'stratum':s['stratum'],'source_epoch':s['epoch'],'pair':pair,
   **{k:statistics.mean(v) for k,v in signals.items() if k!='original_token_in_student_top100'},
   'KL_top100_fraction_of_full':sum(signals['reverse_KL_top100_tail'])/sum(signals['reverse_KL_full']) if sum(signals['reverse_KL_full']) else None}
  for area in ['whole_code','before_code']:
   spans=[z for z in p['spans'] if z['kind']==area]
   indices=sorted(set(i for z in spans for i in z['positions']))
   row[area+'_token_count']=len(indices)
   row[area+'_mean_KL']=statistics.mean(signals['reverse_KL_top100_tail'][i] for i in indices) if indices else None
  rows.append(row)
 # Exploratory error-related positions. Pagination/authentication omissions often have NO uniquely wrong token.
 needles=[]
 if s['stratum']=='R6':needles=['descriptions' if 'show_api_descriptions' in s['original']['code'] else 'api_docs']
 if s['id'].startswith('R1_b015'):needles=['login_result']
 if s['id'].startswith('R1_b016'):needles=['passwords']
 if s['id'].startswith('R1_b023'):needles=['50']
 if s['id'].startswith('R1_b025'):needles=['show_contacts']
 text=s['original']['text'];start=text.find(s['original']['code']);enc=tok(text,add_special_tokens=False,return_offsets_mapping=True)
 for needle in needles:
  a=text.find(needle,start)
  if a<0:continue
  positions=[i for i,(l,r) in enumerate(enc['offset_mapping']) if r>a and l<a+len(needle)]
  for i in positions:
   decisions.append({'state_id':s['id'],'stratum':s['stratum'],'source_epoch':s['epoch'],'expression':needle,'token_position':i,'token':tok.decode([p['old_response_ids'][i]]),
    'condition_probabilities':{k:math.exp(v['original_token_logprobs'][i]) for k,v in p['conditions'].items()},
    'signal_by_pair':{k:{f:v[f][i] for f in ['original_token_logprob_delta','original_token_logit_gradient','original_token_logprob_descent_derivative','reverse_KL_top100_tail']} for k,v in p['signals'].items()}})
output=D/'analysis'
if rows:
 with (output/'probability_by_state.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
write_json(output/'key_token_audit.json',decisions);write_json(output/'historical_loss_reproduction.json',reproductions)
valid=[x for x in backends if x['common_response_prefix_tokens'] and x['mean_abs_logprob_difference_on_common_prefix'] is not None]
summary={'states_completed':len(list((D/'probabilities').glob('R*.json')))+len(list((D/'probabilities').glob('clean*.json'))),
 'historical_reproductions':len(reproductions),'maximum_training_loss_absolute_difference':max((x['loss_absolute_difference'] for x in reproductions),default=None),
 'mean_training_loss_absolute_difference':statistics.mean(x['loss_absolute_difference'] for x in reproductions) if reproductions else None,
 'backend_common_prefix_comparisons':len(valid),'backend_mean_of_per_case_logprob_MAE':statistics.mean(x['mean_abs_logprob_difference_on_common_prefix'] for x in valid) if valid else None,
 'backend_max_per_case_logprob_MAE':max((x['mean_abs_logprob_difference_on_common_prefix'] for x in valid),default=None),'groups':{}}
for stratum in ['R1','R6','R8']:
 summary['groups'][stratum]={}
 for pair in sorted(set(x['pair'] for x in rows)):
  a=[x for x in rows if x['stratum']==stratum and x['pair']==pair]
  if a:summary['groups'][stratum][pair]={k:statistics.mean(x[k] for x in a if x[k] is not None) for k in ['reverse_KL_top100_tail','reverse_KL_full','original_token_logprob_delta','whole_code_mean_KL','before_code_mean_KL','KL_top100_fraction_of_full'] if any(x[k] is not None for x in a)}
write_json(output/'probability_summary.json',summary)
print(summary)
