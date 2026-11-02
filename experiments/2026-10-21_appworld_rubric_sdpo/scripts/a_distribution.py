"""No-gradient teacher-forcing diagnostics on the exact original response tokens."""
from a_common import *
import argparse,time,statistics
def main(stage,limit=None):
 authorize();eligible={x['state_id'] for x in read(R/'phase_a/config'/f'{stage}_replay_eligibility.json')['states'] if x['eligible']}
 todo=[item for item in packages(stage) if item[0]['state_id'] in eligible and item[1]['state']['panel']!='formal_good']
 if limit is not None:todo=todo[:limit]
 dest=R/'phase_a/diagnostics'/stage;dest.mkdir(parents=True,exist_ok=True)
 with gpu_lock():
  os.environ.update(USE_TORCH='1',USE_TF='0',OMP_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false')
  import torch
  from transformers import AutoModelForCausalLM,AutoTokenizer
  torch.set_num_threads(4);torch.set_grad_enabled(False)
  model=AutoModelForCausalLM.from_pretrained(config()['paths']['base_model'],torch_dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True).to('cuda:0').eval();model.requires_grad_(False)
  tokenizer=AutoTokenizer.from_pretrained(config()['paths']['base_model'],local_files_only=True)
  def distribution(prompt,response):
   assert 0<len(response) and len(prompt)+len(response)<=32000
   ids=torch.tensor([prompt+response[:-1]],device='cuda:0')
   with torch.inference_mode():out=model(input_ids=ids,use_cache=False,logits_to_keep=len(response)).logits[0].float()
   assert out.shape[0]==len(response) and not out.requires_grad
   return torch.log_softmax(out,dim=-1)
  for number,(item,p) in enumerate(todo,1):
   path=dest/(item['state_id']+'.json')
   if path.exists():continue
   original=read(R/p['state']['policy_input']);response=original['original_response_ids'];started=time.monotonic()
   base=distribution(p['prompts']['C0_original']['prompt_ids'],response);p0=base.exp();indices=torch.tensor(response,device='cuda:0');rows=torch.arange(len(response),device='cuda:0');actual=base[rows,indices]
   top_logp,top_ids=torch.topk(base,100,dim=-1);top_p=top_logp.exp();mass=top_p.sum(-1);tail=(1-mass).clamp_min(0)
   arms={};self_kl=(p0*(base-base)).sum(-1);assert float(self_kl.abs().max())==0
   for arm,prompt in p['prompts'].items():
    if len(prompt['prompt_ids'])+len(response)>32000:
     arms[arm]={'unavailable':'original_answer_does_not_fit'};continue
    q=base if arm=='C0_original' else distribution(prompt['prompt_ids'],response)
    assigned=q[rows,indices];kl=(p0*(base-q)).sum(-1);top_q=q.gather(-1,top_ids);qtail=(1-top_q.exp().sum(-1)).clamp_min(1e-30)
    aggregate=(top_p*(top_logp-top_q)).sum(-1)+torch.where(tail>0,tail*(tail.clamp_min(1e-30).log()-qtail.log()),0)
    assert float(kl.min())>-1e-4
    arms[arm]={'mean_original_token_logprob':float(assigned.mean()),'mean_logprob_delta_vs_C0':float((assigned-actual).mean()),'reverse_KL_student_to_conditioned_full_vocab':float(kl.mean()),'reverse_KL_top100_plus_tail':float(aggregate.mean()),'conditioned_mass_on_student_top100':float(top_q.exp().sum(-1).mean()),'conditioned_tail_mass':float(qtail.mean()),'token_logprobs':assigned.cpu().tolist(),'token_reverse_KL':kl.cpu().tolist()}
    if q is not base:del q
   # Only trace-confirmed expressions explicitly mentioned in the diagnosis.
   source=read(p['state']['source']);old=source['steps'][p['state']['target_step']-1];diagnosis=p['feedback']['diagnosis'];spans=[]
   patterns=[r"NameError: name '([^']+)' is not defined",r"No API named '([^']+)' found",r"KeyError: '([^']+)'",r"has no attribute '([^']+)'"]
   encoded=tokenizer(original['original_answer'],add_special_tokens=False,return_offsets_mapping=True)
   token_alignment=encoded['input_ids']==response[:len(encoded['input_ids'])] and all(t in tokenizer.all_special_ids for t in response[len(encoded['input_ids']):])
   for pattern in patterns:
    for match in re.finditer(pattern,old['observation']):
     expression=match.group(1)
     if expression not in diagnosis or not token_alignment:continue
     positions=[]
     for occurrence in re.finditer(re.escape(expression),original['original_answer']):
      positions.extend(i for i,(a,b) in enumerate(encoded['offset_mapping']) if b>occurrence.start() and a<occurrence.end())
     positions=sorted(set(positions))
     if positions:spans.append({'expression':expression,'evidence':'source execution error and literal diagnosis mention','token_positions':positions,'scope':'occurrences of error-related expression, not a proof that every occurrence is itself an incorrect token','delta_by_arm':{a:sum(v['token_logprobs'][i]-arms['C0_original']['token_logprobs'][i] for i in positions)/len(positions) for a,v in arms.items() if 'token_logprobs' in v}})
   result={'state_id':item['state_id'],'stage':stage,'source_response_ids_sha256':digest(response),'response_tokens':len(response),'model_manifest_sha256':file_sha(R/'phase_a/config/model_manifest.json'),'backend':'transformers SDPA bf16; probability arithmetic fp32','no_grad':True,'parameter_updates':0,'self_reverse_KL_max_abs':float(self_kl.abs().max()),'student_top100_mass':float(mass.mean()),'student_tail_mass':float(tail.mean()),'original_vllm_logprob_mean_abs_difference':sum(abs(a-b) for a,b in zip(actual.cpu().tolist(),old['old_logprobs']))/len(response),'arms':arms,'error_expression_spans':spans,'text_token_alignment_verified':token_alignment,'seconds':time.monotonic()-started}
   frozen_json(path,result);del base,p0,actual,top_logp,top_ids,top_p,mass,tail;status(stage+'_distribution_diagnostics',completed=number,total=len(todo),training_updates=0)
  del model;torch.cuda.empty_cache()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['calibration','formal'],required=True);ap.add_argument('--limit',type=int);a=ap.parse_args();main(a.stage,a.limit)
