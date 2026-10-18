import copy,json,torch
from transformers import Qwen3Config,Qwen3ForCausalLM
from peft import LoraConfig,get_peft_model
from train import response_mean,R,dump
# Unequal target lengths and ignored trailing tokens catch token-weighting/shift errors.
torch.manual_seed(7);torch.set_num_threads(2)
c=Qwen3Config(vocab_size=37,hidden_size=32,intermediate_size=64,num_hidden_layers=2,num_attention_heads=4,num_key_value_heads=2,head_dim=8,attention_dropout=0.0);c._attn_implementation='eager'
a=get_peft_model(Qwen3ForCausalLM(c),LoraConfig(r=2,lora_alpha=4,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM',lora_dropout=0.0));ref=copy.deepcopy(a);tokens=[torch.randint(0,37,(1,14)),torch.randint(0,37,(1,11))];prompts=[8,7];ends=[4,3]
expected=0;actual=0
for t,p,e in zip(tokens,prompts,ends):
 labels=torch.full_like(t,-100);labels[:,p:p+e]=t[:,p:p+e];expected=expected+ref(input_ids=t,labels=labels).loss/2
 loss=response_mean(a,t,p,e,2)/2;actual+=float(loss.detach());loss.backward()
expected.backward();assert abs(float(expected.detach())-actual)<1e-6
for (n,p),(m,q) in zip(a.named_parameters(),ref.named_parameters()):
 if p.requires_grad:assert n==m and torch.allclose(p.grad,q.grad,atol=2e-6,rtol=1e-5),n
dump(R/'checks/loss_math.json',{'passed':True,'loss':actual,'test':'sequential accumulation equals standard completion-only CE mean of unequal-length steps, including gradients'})
print('PASS: completion-only loss and LoRA gradients match standard CE')
