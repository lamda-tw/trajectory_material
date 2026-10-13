"""Check actual masked loss and LoRA gradients against standard causal LM CE."""
import copy,torch
from transformers import Qwen3Config,Qwen3ForCausalLM
from peft import LoraConfig,get_peft_model
from train_local import response_loss_sum

torch.manual_seed(7)
cfg=Qwen3Config(vocab_size=37,hidden_size=32,intermediate_size=64,num_hidden_layers=2,num_attention_heads=4,num_key_value_heads=2,head_dim=8,attention_dropout=0.0)
cfg._attn_implementation='eager'
a=get_peft_model(Qwen3ForCausalLM(cfg),LoraConfig(r=2,lora_alpha=4,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM',lora_dropout=0.0));b=copy.deepcopy(a)
tokens=torch.randint(0,37,(1,14));prompt=8;start=2;end=6
labels=torch.full_like(tokens,-100);labels[:,prompt+start:prompt+end]=tokens[:,prompt+start:prompt+end]
expected=a(input_ids=tokens,labels=labels).loss
actual=response_loss_sum(b,tokens,prompt,start,end,chunk_size=2)/(end-start)
assert torch.allclose(expected,actual,atol=1e-6),(expected,actual)
expected.backward();actual.backward()
for (n,p),(m,q) in zip(a.named_parameters(),b.named_parameters()):
 if p.requires_grad:assert n==m and torch.allclose(p.grad,q.grad,atol=2e-6,rtol=1e-5),n
print('PASS: masked causal loss and LoRA gradients match standard forward; no prompt/future target loss.')
