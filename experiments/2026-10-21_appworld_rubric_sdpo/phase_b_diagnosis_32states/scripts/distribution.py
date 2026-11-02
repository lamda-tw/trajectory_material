"""No parameter gradients/updates: exact old response prefix, token probabilities and KL logit signals."""
from pathlib import Path
import sys,os,fcntl,time,ast,re,contextlib,copy
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from a_common import read,write_json,frozen_json,file_sha,digest,now,W,require_free_gpu
cfg=read(D/'config/runtime.json');manifest=read(D/'config/manifest.json');provenance=read(D/'config/model_provenance.json')
assert not read(D/'config/authorization.json')['training']
os.environ.update(CUDA_VISIBLE_DEVICES=cfg['server']['gpu'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4',USE_TORCH='1',USE_TF='0',TOKENIZERS_PARALLELISM='false')
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from peft import PeftModel,set_peft_model_state_dict
from b_loss import bucket_reverse_kl

def bucket(p_logits,q_logits,targets,k=100):
 p=torch.log_softmax(p_logits.float(),-1);q=torch.log_softmax(q_logits.float(),-1)
 lp,idx=p.topk(min(k,p.shape[-1]),-1);lq=q.gather(-1,idx)
 mask=torch.zeros_like(p,dtype=torch.bool).scatter_(-1,idx,True)
 tp=torch.logsumexp(p.masked_fill(mask,-torch.inf),-1);tq=torch.logsumexp(q.masked_fill(mask,-torch.inf),-1)
 loss=(lp.exp()*(lp-lq)).sum(-1)+tp.exp()*(tp-tq)
 rr=torch.arange(len(targets),device=p.device);a=p[rr,targets];b=q[rr,targets]
 in_top=mask[rr,targets];ratio=torch.where(in_top,a-b,tp-tq)
 gradient=a.exp()*(ratio-loss)
 ratio_all=torch.where(mask,p-q,(tp-tq).unsqueeze(-1))
 logprob_descent=(p.exp().square()*(ratio_all-loss.unsqueeze(-1))).sum(-1)-gradient
 return {'reverse_KL_top100_tail':loss,'reverse_KL_full':(p.exp()*(p-q)).sum(-1),'original_token_logprob_delta':b-a,
  'original_token_logit_gradient':gradient,'original_token_logprob_descent_derivative':logprob_descent,'original_token_in_student_top100':in_top,'student_top100_mass':lp.exp().sum(-1)}

def check_formula():
 torch.manual_seed(17);p=torch.randn(3,111,requires_grad=True);q=torch.randn(3,111);y=torch.tensor([1,50,99])
 val=bucket_reverse_kl(p,q,100);val.sum().backward();calc=bucket(p.detach(),q,y)
 assert torch.allclose(calc['reverse_KL_top100_tail'],val,atol=2e-6)
 assert torch.allclose(calc['original_token_logit_gradient'],p.grad[torch.arange(3),y],atol=2e-6)
 # Explicit tail token test, and identical-distribution zero signal.
 y=p.detach().argmin(-1);calc=bucket(p.detach(),q,y);assert torch.allclose(calc['original_token_logit_gradient'],p.grad[torch.arange(3),y],atol=2e-6)
 same=bucket(p.detach(),p.detach(),y);assert same['reverse_KL_top100_tail'].abs().max()<1e-6
 z=p.detach().clone().requires_grad_(True);torch.log_softmax(z,-1)[torch.arange(3),y].sum().backward()
 assert torch.allclose(calc['original_token_logprob_descent_derivative'],(-z.grad*p.grad).sum(-1),atol=2e-6)
 return {'analytic_logit_gradient_matches_B_autograd':True,'tail_gradient_checked':True,'full_logit_descent_logprob_direction_checked':True,'identical_distribution_KL_zero':True}

def spans(s,tok):
 old=s['original'];text=old['text'];enc=tok(text,add_special_tokens=False,return_offsets_mapping=True);response=s['example']['response_ids']
 aligned=enc['input_ids']==response[:len(enc['input_ids'])] and all(t in tok.all_special_ids for t in response[len(enc['input_ids']):])
 result=[]
 if not aligned:return False,result
 def add(kind,literal):
  for m in re.finditer(re.escape(literal),text):
   pos=[i for i,(a,b) in enumerate(enc['offset_mapping']) if b>m.start() and a<m.end()]
   if pos and not any(x['kind']==kind and x['positions']==pos for x in result):result.append({'kind':kind,'literal':literal,'positions':pos})
 if old['code']:
  add('whole_code',old['code'])
  code_start=text.find(old['code'])
  if code_start>0:add('before_code',text[:code_start])
 try:
  for node in ast.walk(ast.parse(old['code'])):
   if isinstance(node,ast.Call):
    name=ast.unparse(node.func)
    if name.startswith('apis.'):
     add('api_function',name)
     if name.startswith('apis.api_docs.'):add('documentation_action_family','api_docs')
     for kw in node.keywords:
      if kw.arg in ['app_name','api_name','page_limit','page_index']:
       segment=ast.get_source_segment(old['code'],kw)
       if segment:add('action_argument',segment)
 except SyntaxError:pass
 for pat in [r"NameError: name '([^']+)' is not defined",r"No API named '([^']+)' found",r"KeyError: '([^']+)'",r"has no attribute '([^']+)'"]:
  for m in re.finditer(pat,old['observation']):add('execution_error_expression',m.group(1))
 if s['stratum']=='R1' and 'page_limit=50' in old['code']:add('execution_error_expression','50')
 return aligned,result

def main():
 audit=check_formula();lock=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock'
 with lock.open('a+') as handle:
  fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);require_free_gpu(cfg['server']['gpu'],80)
  torch.set_num_threads(4)
  base=AutoModelForCausalLM.from_pretrained(cfg['paths']['base_model'],torch_dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True).to('cuda:0')
  model=PeftModel.from_pretrained(base,provenance['ema36'],adapter_name='ema36',is_trainable=False)
  model.load_adapter(provenance['student36'],adapter_name='student36',is_trainable=False)
  for name in ['historical_student','historical_teacher']:model.add_adapter(name,copy.deepcopy(model.peft_config['student36']))
  model.eval();model.requires_grad_(False)
  tok=AutoTokenizer.from_pretrained(cfg['paths']['base_model'],local_files_only=True);head=model.get_base_model().lm_head
  def hidden(arm,prompt,response):
   model.set_adapter('ema36' if arm=='base' else arm);model.requires_grad_(False)
   with model.disable_adapter() if arm=='base' else contextlib.nullcontext():
    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
     ids=torch.tensor([prompt+response[:-1]],device='cuda:0')
     h=model.get_base_model().model(input_ids=ids,use_cache=False,return_dict=True).last_hidden_state
     return h[0,len(prompt)-1:].clone()
  for number,item in enumerate(manifest['states'],1):
   path=D/'probabilities'/(item['id']+'.json')
   if path.exists():continue
   s=read(item['path']);e=s['example'];response=e['response_ids'];started=time.monotonic();conditions={}
   for arm in ['base','ema36','student36']:
    for condition in (['C0','C2'] if s['stratum']!='clean' and arm!='student36' else ['C0']):
     key=arm+'_'+condition;conditions[key]=hidden(arm,e['teacher_prompt_ids' if condition=='C2' else 'prompt_ids'],response)
   historical={}
   if s['stratum']!='clean':
    batch=s['batch'];parent=R/'phase_b/runs/mixed'/f'batch_{batch-1:03d}'/'checkpoint/state.pt'
    if batch>1:
     saved=torch.load(parent,map_location='cpu',weights_only=False)
     set_peft_model_state_dict(model,saved['student'],adapter_name='historical_student')
     set_peft_model_state_dict(model,saved['teacher'],adapter_name='historical_teacher');del saved
     historical={'parent_checkpoint':str(parent),'parent_checkpoint_sha256':file_sha(parent)}
    else:historical={'parent_checkpoint':'initial_base_zero_LoRA'}
    for key,arm,prompt in [('historical_student_C0','historical_student',e['prompt_ids']),('historical_teacher_C0','historical_teacher',e['prompt_ids']),('historical_teacher_C2','historical_teacher',e['teacher_prompt_ids'])]:
     conditions[key]=hidden(arm if batch>1 else 'base',prompt,response)
    recorded=read(R/'phase_b/runs/mixed'/f'batch_{batch:03d}'/'checkpoint/step_metrics.json')
    historical['recorded_training_loss']=next(x['loss'] for x in recorded if x['trajectory_id']==e['trajectory_id'] and x['step']==e['step'])
   pairs=[('base_feedback','base_C0','base_C2'),('ema_feedback','ema36_C0','ema36_C2'),('B_final_student_vs_EMA_C2','student36_C0','ema36_C2'),('frozen_base_teacher_for_final_student','student36_C0','base_C2')] if s['stratum']!='clean' else []
   if s['stratum']!='clean':pairs.extend([('historical_B_loss','historical_student_C0','historical_teacher_C2'),('historical_teacher_feedback','historical_teacher_C0','historical_teacher_C2')])
   stats={k:{'original_token_logprobs':[],'entropy':[],'top5_ids':[],'top5_logprobs':[]} for k in conditions};signals={k:{} for k,_,_ in pairs}
   with torch.inference_mode():
    for start in range(0,len(response),64):
     logits={k:head(h[start:start+64]).float() for k,h in conditions.items()};targets=torch.tensor(response[start:start+64],device='cuda:0');row=torch.arange(len(targets),device='cuda:0')
     for k,value in logits.items():
      lp=torch.log_softmax(value,-1);v,ids=lp.topk(5,-1)
      for name,array in [('original_token_logprobs',lp[row,targets]),('entropy',-(lp.exp()*lp).sum(-1)),('top5_ids',ids),('top5_logprobs',v)]:stats[k][name].extend(array.cpu().tolist())
     for key,p,q in pairs:
      for name,value in bucket(logits[p],logits[q],targets).items():signals[key].setdefault(name,[]).extend(value.cpu().tolist())
   aligned,exprs=spans(s,tok)
   for z in exprs:
    pos=z['positions'];z['by_condition']={k:sum(v['original_token_logprobs'][i] for i in pos)/len(pos) for k,v in stats.items()}
    z['by_pair']={k:{n:sum(v[n][i] for i in pos)/len(pos) for n in ['original_token_logprob_delta','original_token_logit_gradient','reverse_KL_top100_tail']} for k,v in signals.items()}
   backend_checks={}
   for k,v in stats.items():
    generated_path=D/'runs'/k/s['id']/'result.json'
    if not generated_path.exists():continue
    generation=read(generated_path)['actions'][0];common=0
    for a,b in zip(response,generation['response_ids']):
     if a!=b:break
     common+=1
    backend_checks[k]={'common_response_prefix_tokens':common,'mean_abs_logprob_difference_on_common_prefix':sum(abs(v['original_token_logprobs'][i]-generation['old_logprobs'][i]) for i in range(common))/common if common else None}
   if historical:
    historical['recomputed_training_loss']=sum(signals['historical_B_loss']['reverse_KL_top100_tail'])/len(response)
    historical['loss_absolute_difference']=abs(historical['recomputed_training_loss']-historical['recorded_training_loss'])
   out={'state_id':s['id'],'historical_training_reproduction':historical,'vllm_vs_transformers':backend_checks,'parameter_updates':0,'model_parameter_gradients':False,'old_response_ids':response,'decoded_tokens':tok.convert_ids_to_tokens(response),'text_token_alignment':aligned,
    'conditions':stats,'signals':signals,'spans':exprs,'formula_check':audit,'seconds':time.monotonic()-started,
    'gradient_convention':'Derivative of per-position KL w.r.t. original-token student logit, teacher detached. Positive means gradient descent lowers that logit. B step averaging additionally divides by response length. This is not a model-parameter update or proof of future probability change.',
    'gpu_peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30}
   frozen_json(path,out);print({'state':s['id'],'completed':number,'total':32,'seconds':round(out['seconds'],1)},flush=True)
   del conditions,logits
  assert all(p.grad is None and not p.requires_grad for p in model.parameters())
  write_json(D/'probabilities/COMPLETE.json',{'completed_at':now(),'states':32,'new_optimizer_updates':0,'all_parameter_gradients_none':True,'formula_check':audit,'peak_gpu_allocated_gib':torch.cuda.max_memory_allocated()/2**30})
if __name__=='__main__':main()
