"""Shared math and durable update state. Imports never load a model or touch CUDA."""
from pathlib import Path
import hashlib, json, math, os, random, shutil
import numpy as np
import torch
import torch.nn.functional as F
from common import dump, read, sha, require, ROOT, now

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def assert_gpu1():
    policy = read(ROOT/'config/resource_policy.json')
    require(os.environ.get('CUDA_VISIBLE_DEVICES') == policy['physical_gpu_uuid'], 'Use gpu1_run.py; physical GPU1 UUID required')
    require(os.environ.get('WORLD_SIZE', '1') == '1', 'Single GPU only')
    import subprocess
    result = subprocess.check_output(['nvidia-smi', '--id=1', '--query-gpu=uuid', '--format=csv,noheader'], text=True).strip()
    require(result == policy['physical_gpu_uuid'], 'Physical GPU1 identity changed')

def advantages(rewards, epsilon=1e-8):
    x = torch.as_tensor(rewards, dtype=torch.float64)
    require(x.ndim == 1 and x.numel() >= 2 and torch.isfinite(x).all(), 'Invalid reward group')
    if bool((x == x[0]).all()): return torch.zeros_like(x)
    return (x-x.mean())/(x.std(correction=0)+epsilon)

def terms(new, old, ref, advantage, clip=0.2):
    require(new.shape == old.shape == ref.shape, 'Probability shape mismatch')
    ratio = (new-old).exp()
    pg = -torch.minimum(ratio*advantage, ratio.clamp(1-clip, 1+clip)*advantage)
    d = ref-new
    # Sampled k3 penalty on behavior-policy actions; not exact current-policy KL.
    kl = torch.expm1(d)-d
    if not all(bool(torch.isfinite(x).all()) for x in (pg, kl, ratio)):
        raise FloatingPointError('Nonfinite loss; never silently clip exponents or drop samples')
    return pg, kl, ratio

def step_mean_ce(logits, labels):
    """Reference padded implementation: one causal shift, equal ORIGINAL-step weights."""
    target = labels[:, 1:]
    losses = F.cross_entropy(logits[:, :-1].transpose(1, 2), target, ignore_index=-100, reduction='none')
    counts = (target != -100).sum(-1)
    require(bool((counts > 0).all()), 'A step has no supervised targets')
    return (losses.sum(-1)/counts).mean()

def action_logprobs(model, prompt_ids, response_ids, chunk_size=128):
    """Exact complete prefix; vocabulary logits only at target positions, recomputed in backward."""
    require(len(prompt_ids)>0 and len(response_ids)>0, 'Empty original action')
    base = model.get_base_model() if hasattr(model, 'get_base_model') else model
    require(base.config.model_type == 'qwen3', 'Qwen3 architecture required')
    device = next(model.parameters()).device
    tokens = torch.tensor([list(prompt_ids)+list(response_ids)], dtype=torch.long, device=device)
    hidden = base.model(input_ids=tokens[:, :-1], use_cache=False, return_dict=True).last_hidden_state
    hidden = hidden[0, len(prompt_ids)-1:len(prompt_ids)-1+len(response_ids)]
    target = tokens[0, len(prompt_ids):]
    def logp(h, y):
        return -F.cross_entropy(base.lm_head(h).float(), y, reduction='none')
    out=[]
    for start in range(0, len(response_ids), chunk_size):
        h,y=hidden[start:start+chunk_size], target[start:start+chunk_size]
        if torch.is_grad_enabled() and h.requires_grad:
            from torch.utils.checkpoint import checkpoint
            out.append(checkpoint(logp, h, y, use_reentrant=False))
        else: out.append(logp(h,y))
    return torch.cat(out)

def learning_rate(cfg, update):
    c=cfg['optimizer_candidate']; total=cfg['schedule_candidate']['joint_optimizer_updates']; warm=c['warmup_updates']
    require(1<=update<=total and 0<=warm<total, 'Invalid scheduler position')
    if update<=warm: return c['learning_rate']*update/warm
    fraction=(update-warm)/(total-warm)
    return c['minimum_learning_rate']+0.5*(c['learning_rate']-c['minimum_learning_rate'])*(1+math.cos(math.pi*fraction))

def capture_rng():
    return {'python':random.getstate(), 'numpy':np.random.get_state(), 'torch':torch.get_rng_state(),
            'cuda':torch.cuda.get_rng_state_all() if torch.cuda.is_initialized() else None}

def restore_rng(state):
    random.setstate(state['python']); np.random.set_state(state['numpy']); torch.set_rng_state(state['torch'])
    if state['cuda'] is not None: torch.cuda.set_rng_state_all(state['cuda'])

def save_checkpoint(path, model, optimizer, state):
    path=Path(path); require(not path.exists(), 'Committed checkpoint already exists')
    tmp=path.with_name(path.name+'.incomplete'); require(not tmp.exists(), 'Archive incomplete checkpoint before retry')
    tmp.mkdir(parents=True)
    model.save_pretrained(tmp, safe_serialization=True)
    torch.save({'optimizer':optimizer.state_dict(), 'rng':capture_rng(), 'state':state}, tmp/'resume.pt')
    dump(tmp/'manifest.json', {'created_at':now(), 'state':state,
         'files':{p.name:sha(p) for p in tmp.iterdir() if p.is_file()},
         'adapter_sha256':sha(tmp/'adapter_model.safetensors')})
    # Complete-directory rename is the sole commit; consumers ignore .incomplete.
    for p in tmp.iterdir():
        if p.is_file():
            with p.open('rb') as handle: os.fsync(handle.fileno())
    os.rename(tmp,path)
    fd=os.open(str(path.parent),os.O_RDONLY);os.fsync(fd);os.close(fd)

def verify_checkpoint(path):
    path=Path(path); m=read(path/'manifest.json')
    for name, expected in m['files'].items(): require(sha(path/name)==expected, 'Checkpoint checksum mismatch: '+name)
    require(sha(path/'adapter_model.safetensors')==m['adapter_sha256'],'Adapter identity mismatch')
    return m

def load_weights(model, path):
    from safetensors.torch import load_file
    from peft import set_peft_model_state_dict
    state=load_file(str(Path(path)/'adapter_model.safetensors'))
    result=set_peft_model_state_dict(model,state,adapter_name='default')
    require(not result.unexpected_keys,'Unexpected LoRA weights')

def restore_checkpoint(path, model, optimizer, expected_identity=None):
    manifest=verify_checkpoint(path)
    if expected_identity is not None: require(manifest['state']['identity']==expected_identity,'Resume identity mismatch')
    load_weights(model,path)
    bundle=torch.load(Path(path)/'resume.pt',map_location='cpu',weights_only=False)
    require(bundle['state']==manifest['state'],'State/manifest mismatch')
    optimizer.load_state_dict(bundle['optimizer']);restore_rng(bundle['rng'])
    return bundle['state']

def load_model(cfg, device='cuda:0'):
    from transformers import AutoModelForCausalLM
    from peft import PeftModel
    if device.startswith('cuda'): assert_gpu1()
    initial=Path(cfg['model']['initial_adapter'])
    require(sha(initial/'adapter_model.safetensors')==cfg['model']['adapter_weights_sha256'],'Initial adapter changed')
    base=AutoModelForCausalLM.from_pretrained(cfg['model']['base'],local_files_only=True,dtype=torch.bfloat16,
                                            attn_implementation='sdpa')
    model=PeftModel.from_pretrained(base,str(initial),is_trainable=True,local_files_only=True).to(device)
    model.config.use_cache=False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads()
    trainable=[(n,p) for n,p in model.named_parameters() if p.requires_grad]
    require(trainable and all('lora_' in n and '.default.' in n for n,p in trainable),'Only inherited LoRA may train')
    require(sum(p.numel() for _,p in trainable)==cfg['model']['continuation_lora_parameters'],'LoRA parameter count changed')
    require(set(model.peft_config)=={'default'},'Unexpected additional adapter')
    return model

def optimizer_for(model,cfg):
    c=cfg['optimizer_candidate']
    return torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=c['learning_rate'],
        betas=tuple(c['betas']),eps=c['epsilon'],weight_decay=c['weight_decay'])

def gradients(model):
    return [p.grad.detach().float().cpu().clone() if p.grad is not None else torch.zeros_like(p,device='cpu',dtype=torch.float32)
            for p in model.parameters() if p.requires_grad]

def grad_norm(values): return math.sqrt(sum(float(x.double().square().sum()) for x in values))

def grad_dot(a,b): return sum(float((x.double()*y.double()).sum()) for x,y in zip(a,b))
