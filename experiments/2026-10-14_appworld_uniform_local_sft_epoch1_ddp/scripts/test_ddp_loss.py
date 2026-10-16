"""Compare actual DDP response-mean objective and gradients with full reference CE."""
import copy,os,torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from transformers import Qwen3Config,Qwen3ForCausalLM
from peft import LoraConfig,get_peft_model
from train_ddp import CompletionLoss
rank=int(os.environ['RANK']);dist.init_process_group('gloo');torch.manual_seed(7)
c=Qwen3Config(vocab_size=37,hidden_size=32,intermediate_size=64,num_hidden_layers=2,num_attention_heads=4,num_key_value_heads=2,head_dim=8,attention_dropout=0.0);c._attn_implementation='eager'
a=get_peft_model(Qwen3ForCausalLM(c),LoraConfig(r=2,lora_alpha=4,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM',lora_dropout=0.0));ref=copy.deepcopy(a)
tokens=[torch.randint(0,37,(1,14)),torch.randint(0,37,(1,11))];prompts=[8,7];ends=[4,3]
expected=0
for t,p,e in zip(tokens,prompts,ends):
 labels=torch.full_like(t,-100);labels[:,p:p+e]=t[:,p:p+e];expected=expected+ref(input_ids=t,labels=labels).loss/2
expected.backward();ddp=DDP(CompletionLoss(a,2));actual=ddp(tokens[rank],prompts[rank],ends[rank]);actual.backward();avg=actual.detach().clone();dist.all_reduce(avg);avg/=2
assert torch.allclose(expected,avg,atol=1e-6)
for (n,p),(m,q) in zip(a.named_parameters(),ref.named_parameters()):
 if p.requires_grad:assert n==m and torch.allclose(p.grad,q.grad,atol=2e-6,rtol=1e-5),n
if rank==0:print('PASS: two-rank DDP loss and LoRA gradients equal mean of two reference completion-only CE losses; unequal target lengths and masked tails handled.')
dist.destroy_process_group()
