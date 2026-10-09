"""One fresh on-policy GRPO update. No model load without --execute."""
import argparse
import math
import os
import random
import time
from pathlib import Path
from common import atomic_json, check_training_ids, digest, file_sha, input_fingerprint, load_config, read_json, validate_tokens

def grpo_terms(new_logp, old_logp, reference_logp, advantage, clip_epsilon, kl_beta):
    import torch
    ratio = torch.exp(new_logp - old_logp)
    difference = reference_logp - new_logp
    kl = torch.exp(difference) - difference - 1.0
    surrogate = torch.minimum(ratio * advantage, ratio.clamp(1 - clip_epsilon, 1 + clip_epsilon) * advantage)
    return -surrogate + kl_beta * kl, ratio, kl

def action_logprobs(model, prompt_ids, response_ids, chunk_size):
    """Qwen3-only: omit prompt-position vocabulary logits to bound memory."""
    import torch
    import torch.nn.functional as F
    base = model.get_base_model()
    tokens = torch.tensor([prompt_ids + response_ids], dtype=torch.long, device=model.device)
    hidden = base.model(input_ids=tokens[:, :-1], use_cache=False, return_dict=True).last_hidden_state
    hidden = hidden[0, len(prompt_ids) - 1:len(prompt_ids) - 1 + len(response_ids)]
    targets = tokens[0, len(prompt_ids):]
    outputs = []
    for start in range(0, len(response_ids), chunk_size):
        logits = base.lm_head(hidden[start:start + chunk_size]).float()
        outputs.append(-F.cross_entropy(logits, targets[start:start + chunk_size], reduction='none'))
    return torch.cat(outputs)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--previous', type=Path)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    if not args.execute:
        ap.error('No model load or training without --execute.')
    started = time.monotonic()
    config, batch = load_config(), read_json(args.batch)
    t, fingerprint = config['training'], input_fingerprint(config)
    if batch['fingerprint'] != fingerprint or batch['branch'] not in {'outcome', 'rubric'}:
        raise ValueError('Changed inputs or unknown reward branch.')
    episodes = batch['episodes']
    check_training_ids([e['task_id'] for e in episodes], config)
    if len(episodes) != t['groups_per_update'] * config['sampling']['group_size']:
        raise ValueError('Incomplete fresh rollout batch.')
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite a committed checkpoint.')
    for episode in episodes:
        if file_sha(episode['trajectory']) != episode['trajectory_sha256']:
            raise ValueError('Trajectory changed after reward computation.')
        trajectory = read_json(episode['trajectory'])
        if trajectory['job']['policy_id'] != batch['policy_id']:
            raise ValueError('Stale/off-policy trajectory.')
        episode['steps'] = trajectory['steps']
        episode['token_count'] = sum(len(s['response_ids']) for s in episode['steps'])
        if not episode['token_count']:
            raise ValueError('Rollout has no action tokens; abort rather than drop it.')
        for step in episode['steps']:
            validate_tokens(step['prompt_ids'], step['response_ids'], step['old_logprobs'])
    if args.previous:
        previous = read_json(args.previous / 'manifest.json')
        if previous['fingerprint'] != fingerprint or previous['branch'] != batch['branch'] or previous['update'] != batch['update'] - 1 or previous['policy_id'] != batch['policy_id']:
            raise ValueError('Previous adapter is not this branch/schedule/policy.')
        for name, expected in previous['files'].items():
            if file_sha(args.previous / name) != expected:
                raise ValueError('Checkpoint contents changed.')
    elif batch['update'] != 1 or batch['policy_id'] != 'base:' + fingerprint:
        raise ValueError('Independent branches must start from raw Qwen3-8B.')
    from resources import require_free_gpu
    require_free_gpu(t['gpu'], t['minimum_free_gpu_gib'])
    os.environ.update(CUDA_VISIBLE_DEVICES=t['gpu'], HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import torch
    from transformers import AutoModelForCausalLM
    from peft import LoraConfig, PeftModel, get_peft_model
    random.seed(t['seed'])
    torch.manual_seed(t['seed'])
    torch.cuda.manual_seed_all(t['seed'])
    model = AutoModelForCausalLM.from_pretrained(config['paths']['base_model'], local_files_only=True,
                                               dtype=torch.bfloat16, attn_implementation='sdpa')
    if model.config.model_type != 'qwen3':
        raise ValueError('This trainer supports Qwen3 only.')
    model = (PeftModel.from_pretrained(model, str(args.previous), is_trainable=True, local_files_only=True)
             if args.previous else get_peft_model(model, LoraConfig(**t['lora'])))
    model.to('cuda')
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    model.train()
    parameters = [p for p in model.parameters() if p.requires_grad]
    if not parameters or any(p.requires_grad for name, p in model.named_parameters() if 'lora_' not in name):
        raise ValueError('Expected LoRA-only updates with a frozen raw reference.')
    optimizer = torch.optim.AdamW(parameters, lr=t['learning_rate'], weight_decay=t['weight_decay'])
    if args.previous:
        state = torch.load(args.previous / 'optimizer.pt', map_location='cpu', weights_only=False)
        optimizer.load_state_dict(state['optimizer'])
        torch.set_rng_state(state['torch_rng'])
        torch.cuda.set_rng_state_all(state['cuda_rng'])
        random.setstate(state['python_rng'])
    optimizer.zero_grad(set_to_none=True)
    metrics = dict(loss=0.0, kl=0.0, ratio_mean=0.0, clip_fraction=0.0,
                   old_new_abs_logprob_mean=0.0, max_old_new_abs_logprob=0.0,
                   tokens=sum(e['token_count'] for e in episodes))
    for episode in episodes:
        for step in episode['steps']:
            with torch.no_grad(), model.disable_adapter():
                reference = action_logprobs(model, step['prompt_ids'], step['response_ids'], t['head_chunk_size'])
            new = action_logprobs(model, step['prompt_ids'], step['response_ids'], t['head_chunk_size'])
            old = torch.tensor(step['old_logprobs'], device=new.device, dtype=torch.float32)
            losses, ratio, kl = grpo_terms(new, old, reference, episode['advantage'], t['clip_epsilon'], t['kl_beta'])
            if not torch.isfinite(losses).all() or not torch.isfinite(ratio).all():
                raise FloatingPointError('Non-finite GRPO terms; checkpoint not committed.')
            divisor = len(episodes) * episode['token_count']
            loss = losses.sum() / divisor
            loss.backward()
            with torch.no_grad():
                metrics['loss'] += loss.item()
                metrics['kl'] += kl.sum().item() / divisor
                metrics['ratio_mean'] += ratio.sum().item() / divisor
                metrics['clip_fraction'] += ((ratio - 1).abs() > t['clip_epsilon']).float().sum().item() / divisor
                metrics['old_new_abs_logprob_mean'] += (new - old).abs().sum().item() / divisor
                metrics['max_old_new_abs_logprob'] = max(metrics['max_old_new_abs_logprob'], (new - old).abs().max().item())
            del loss, losses, ratio, kl, new, old, reference
    gradient_norm = torch.nn.utils.clip_grad_norm_(parameters, t['max_grad_norm'], error_if_nonfinite=True)
    metrics['gradient_norm_before_clip'] = float(gradient_norm)
    if any(not math.isfinite(float(v)) for v in metrics.values()):
        raise FloatingPointError('Non-finite training metrics.')
    if metrics['old_new_abs_logprob_mean'] > 0.1:
        raise RuntimeError('HF/vLLM logprob mismatch exceeds 0.1 mean absolute; checkpoint not committed.')
    optimizer.step()
    metrics['elapsed_seconds_before_checkpoint'] = time.monotonic() - started
    temporary = args.output.with_name(args.output.name + f'.incomplete.{os.getpid()}')
    temporary.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(temporary, safe_serialization=True)
    torch.save({'optimizer': optimizer.state_dict(), 'torch_rng': torch.get_rng_state(),
                'cuda_rng': torch.cuda.get_rng_state_all(), 'python_rng': random.getstate()}, temporary / 'optimizer.pt')
    files = {name: file_sha(temporary / name) for name in ('adapter_config.json', 'adapter_model.safetensors', 'optimizer.pt')}
    manifest = {'fingerprint': fingerprint, 'branch': batch['branch'], 'update': batch['update'],
                'parent_policy_id': batch['policy_id'], 'batch_sha256': file_sha(args.batch),
                'base_model': config['paths']['base_model'], 'files': files,
                'policy_id': digest({'parent': batch['policy_id'], 'branch': batch['branch'],
                                     'update': batch['update'], 'weights': files['adapter_model.safetensors']}),
                'metrics': metrics}
    atomic_json(temporary / 'manifest.json', manifest)
    temporary.rename(args.output)
    print(__import__('json').dumps(metrics))

if __name__ == '__main__':
    main()
