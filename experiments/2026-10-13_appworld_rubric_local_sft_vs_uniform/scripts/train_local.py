"""Exact original-token, response-only LoRA SFT; one local GPU per branch."""
from pathlib import Path
import argparse,hashlib,json,math,os,random,time
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint
from transformers import AutoModelForCausalLM
from peft import LoraConfig,get_peft_model,get_peft_model_state_dict,set_peft_model_state_dict
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dump(p,x):
 p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def state_sha(state):
 h=hashlib.sha256()
 for k,v in sorted(state.items()):h.update(k.encode());h.update(v.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
 return h.hexdigest()

def response_loss_sum(model,tokens,prompt_length,start,end,chunk_size=128,checkpoint_head=True):
 """Targets are response[start:end]; no prompt or future-observation target."""
 base=model.get_base_model()
 hidden=base.model(input_ids=tokens[:,:prompt_length+end-1],use_cache=False,return_dict=True).last_hidden_state
 hidden=hidden[0,prompt_length+start-1:prompt_length+end-1]
 targets=tokens[0,prompt_length+start:prompt_length+end]
 assert len(hidden)==len(targets)==end-start>0
 def head_loss(h,y):return F.cross_entropy(base.lm_head(h).float(),y,reduction='sum')
 losses=[]
 for pos in range(0,len(targets),chunk_size):
  h=hidden[pos:pos+chunk_size];y=targets[pos:pos+chunk_size]
  losses.append(checkpoint(head_loss,h,y,use_reentrant=False) if checkpoint_head else head_loss(h,y))
 return torch.stack(losses).sum()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['rubric','uniform'],required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
 assert args.execute,'Training requires explicit --execute'
 cfg=read('config/training.json');manifest=read('data/DATA_MANIFEST.json')
 for p,h in manifest['artifacts'].items():assert sha(R/p)==h,p
 schedule=read(f'data/{args.arm}_schedule.json');index=read('data/token_index.json');data=np.memmap(R/'data/tokens.bin',dtype='<i4',mode='r')
 out=R/'training'/args.arm;out.mkdir(parents=True,exist_ok=True)
 if (out/'COMPLETE.json').exists():
  print('Already complete; refusing redundant updates.',flush=True);return
 seed=cfg['seed'];random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
 torch.backends.cuda.matmul.allow_tf32=True
 started=time.monotonic();device=torch.device('cuda:0')
 print(json.dumps({'event':'loading','arm':args.arm,'cuda_visible_devices':os.getenv('CUDA_VISIBLE_DEVICES')}),flush=True)
 base=AutoModelForCausalLM.from_pretrained(cfg['base_model'],local_files_only=True,dtype=torch.bfloat16,attn_implementation=cfg['attention'])
 assert base.config.model_type=='qwen3';base.config.use_cache=False
 torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
 model=get_peft_model(base,LoraConfig(**cfg['lora']));model.to(device)
 model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads();model.train()
 assert all("lora_" in n for n,p in model.named_parameters() if p.requires_grad)
 trainable=[p for p in model.parameters() if p.requires_grad]
 initial_hash=state_sha(get_peft_model_state_dict(model))
 init={'arm':args.arm,'initial_adapter_tensor_sha256':initial_hash,'trainable_parameters':sum(p.numel() for p in trainable),'training_config_sha256':sha(R/'config/training.json'),'schedule_sha256':sha(R/f'data/{args.arm}_schedule.json')}
 if (out/'INITIALIZATION.json').exists():assert read(f'training/{args.arm}/INITIALIZATION.json')==init
 else:dump(out/'INITIALIZATION.json',init)
 optimizer=torch.optim.AdamW(trainable,lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
 completed=0;prior_seconds=0.0;history=[]
 if (out/'resume.pt').exists():
  saved=torch.load(out/'resume.pt',map_location='cpu',weights_only=False)
  assert saved['schedule_sha256']==init['schedule_sha256'] and saved['config_sha256']==init['training_config_sha256']
  set_peft_model_state_dict(model,saved['adapter']);optimizer.load_state_dict(saved['optimizer']);completed=saved['completed'];history=saved['history'];prior_seconds=saved['elapsed_seconds']
  torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state_all(saved['cuda_rng'])
  print(json.dumps({'event':'resumed','arm':args.arm,'completed':completed}),flush=True)
 torch.cuda.reset_peak_memory_stats(device)
 for num,batch in enumerate(schedule['updates'],1):
  if num<=completed:continue
  assert sum(s['end']-s['start'] for s in batch)==cfg['tokens_per_update']
  warm=cfg['warmup_updates'];total=cfg['optimizer_updates']
  lr=cfg['learning_rate']*num/warm if num<=warm else cfg['minimum_learning_rate']+(cfg['learning_rate']-cfg['minimum_learning_rate'])*0.5*(1+math.cos(math.pi*(num-warm)/(total-warm)))
  for group in optimizer.param_groups:group['lr']=lr
  optimizer.zero_grad(set_to_none=True);loss_total=0.0;input_tokens=0;tick=time.monotonic()
  for micro,span in enumerate(batch,1):
   info=index[span['id']];n=info['prompt_tokens']+span['end'];raw=np.array(data[info['offset']:info['offset']+n],dtype=np.int64,copy=True)
   tokens=torch.as_tensor(raw,device=device).unsqueeze(0)
   with torch.autocast('cuda',dtype=torch.bfloat16):loss=response_loss_sum(model,tokens,info['prompt_tokens'],span['start'],span['end'],cfg['head_chunk_size'])
   val=float(loss.detach());assert math.isfinite(val),(span['id'],val)
   (loss/cfg['tokens_per_update']).backward();loss_total+=val;input_tokens+=n
   del tokens,loss
   if micro%10==0:
    dump(out/'PROGRESS.json',{'phase':'training','arm':args.arm,'completed_updates':num-1,'current_update':num,'micro':micro,'micro_total':len(batch),'elapsed_seconds':prior_seconds+time.monotonic()-started})
  norm=float(torch.nn.utils.clip_grad_norm_(trainable,cfg['max_grad_norm']));assert math.isfinite(norm)
  optimizer.step()
  event={'update':num,'loss':loss_total/cfg['tokens_per_update'],'learning_rate':lr,'supervised_tokens':cfg['tokens_per_update'],'cumulative_supervised_tokens':num*cfg['tokens_per_update'],'forward_segments':len(batch),'input_tokens':input_tokens,'grad_norm_before_clip':norm,'update_seconds':time.monotonic()-tick,'elapsed_seconds':prior_seconds+time.monotonic()-started}
  history.append(event);print(json.dumps({'event':'update','arm':args.arm,**event}),flush=True)
  dump(out/'metrics.json',history)
  saved={'completed':num,'adapter':{k:v.detach().cpu().clone() for k,v in get_peft_model_state_dict(model).items()},'optimizer':optimizer.state_dict(),'history':history,'elapsed_seconds':event['elapsed_seconds'],'schedule_sha256':init['schedule_sha256'],'config_sha256':init['training_config_sha256'],'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all()}
  torch.save(saved,out/'resume.tmp.pt');(out/'resume.tmp.pt').replace(out/'resume.pt');del saved
  dump(out/'PROGRESS.json',{'phase':'training','arm':args.arm,'completed_updates':num,'total_updates':total,'elapsed_seconds':event['elapsed_seconds']})
 assert len(history)==48 and sum(x['supervised_tokens'] for x in history)==196608
 adapter=out/'adapter';assert not adapter.exists();model.save_pretrained(adapter,safe_serialization=True)
 final_hash=state_sha(get_peft_model_state_dict(model));assert final_hash!=initial_hash
 result={'phase':'complete','arm':args.arm,'updates':48,'supervised_tokens':196608,'initial_adapter_tensor_sha256':initial_hash,'final_adapter_tensor_sha256':final_hash,'adapter_files':{p.name:sha(p) for p in adapter.iterdir() if p.is_file()},'training_wall_seconds':prior_seconds+time.monotonic()-started,'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'new_model_calls':0,'new_actions':0}
 dump(out/'COMPLETE.json',result);dump(out/'PROGRESS.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
