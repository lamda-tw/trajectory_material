"""One complete on-policy GRPO update with an independent frozen SFT reference."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time
import pipeline as p


def grpo_terms(new, old, reference, advantage, clip, beta):
    import torch
    ratio = torch.exp(new - old)
    delta = reference - new
    kl = torch.exp(delta) - delta - 1
    objective = torch.minimum(ratio * advantage, ratio.clamp(1 - clip, 1 + clip) * advantage)
    return -objective + beta * kl, ratio, kl


def action_logprobs(model, prompt, response, chunk_size):
    """Teacher-forced likelihood of exactly sampled action tokens, including EOS."""
    import torch
    import torch.nn.functional as F
    from torch.utils.checkpoint import checkpoint
    base = model.get_base_model()
    tokens = torch.tensor([prompt + response], dtype=torch.long, device=model.device)
    hidden = base.model(input_ids=tokens[:, :-1], use_cache=False, return_dict=True).last_hidden_state
    hidden = hidden[0, len(prompt) - 1:len(prompt) - 1 + len(response)]
    target = tokens[0, len(prompt):]
    def logp(h, y):
        return -F.cross_entropy(base.lm_head(h).float(), y, reduction='none')
    pieces = []
    for start in range(0, len(response), chunk_size):
        args = (hidden[start:start + chunk_size], target[start:start + chunk_size])
        pieces.append(checkpoint(logp, *args, use_reentrant=False)
                      if torch.is_grad_enabled() else logp(*args))
    return torch.cat(pieces)


def adapter_digest(model):
    h = hashlib.sha256()
    for name, tensor in model.named_parameters():
        if 'lora_' in name:
            h.update(name.encode())
            h.update(tensor.detach().cpu().contiguous().view(__import__('torch').uint8).numpy().tobytes())
    return h.hexdigest()


def load_models(cfg, parent):
    import torch
    from transformers import AutoModelForCausalLM
    from peft import PeftModel
    def load(adapter, trainable):
        base = AutoModelForCausalLM.from_pretrained(cfg['paths']['base_model'], local_files_only=True,
                                                   dtype=torch.bfloat16, attn_implementation='sdpa')
        if base.config.model_type != 'qwen3':
            raise ValueError('Only Qwen3 is supported.')
        model = PeftModel.from_pretrained(base, str(adapter), is_trainable=trainable, local_files_only=True)
        model.to('cuda')
        model.config.use_cache = False
        return model
    model = load(parent, True)
    reference = load(p.adapter_path(cfg), False)
    reference.requires_grad_(False)
    reference.eval()
    model.train()
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    return model, reference


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    batch = p.validate_batch(args.batch)
    if not args.execute:
        print(json.dumps({'validated': True, 'episodes': len(batch['episodes']), 'loads_model': False}))
        return
    if args.output.exists():
        raise FileExistsError('Committed checkpoints are immutable.')
    cfg, train = p.load_config(), batch['training']
    parent = p.policy_info(batch['branch'], batch['update'] - 1)
    from resources import require_free_gpu
    require_free_gpu(p.settings()['execution_gpu'], cfg['training']['minimum_free_gpu_gib'])
    os.environ.update(CUDA_VISIBLE_DEVICES=p.settings()['execution_gpu'], HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import torch
    random.seed(cfg['training']['seed'])
    torch.manual_seed(cfg['training']['seed'])
    torch.cuda.manual_seed_all(cfg['training']['seed'])
    started = time.monotonic()
    model, reference = load_models(cfg, parent['path'])
    parameters = [v for v in model.parameters() if v.requires_grad]
    if not parameters or any(v.requires_grad and 'lora_' not in n for n, v in model.named_parameters()):
        raise ValueError('Only policy LoRA parameters may be trainable.')
    if any(v.requires_grad for v in reference.parameters()):
        raise ValueError('Reference must be frozen.')
    if {v.data_ptr() for v in model.parameters()} & {v.data_ptr() for v in reference.parameters()}:
        raise ValueError('Policy and reference must not share storage.')
    initial_policy_hash, reference_hash = adapter_digest(model), adapter_digest(reference)
    optimizer = torch.optim.AdamW(parameters, lr=train['learning_rate'], weight_decay=train['weight_decay'])
    if batch['update'] > 1:
        state = torch.load(Path(parent['path']) / 'optimizer.pt', map_location='cpu', weights_only=False)
        optimizer.load_state_dict(state['optimizer'])
        torch.set_rng_state(state['torch_rng'])
        torch.cuda.set_rng_state_all(state['cuda_rng'])
        random.setstate(state['python_rng'])
    optimizer.zero_grad(set_to_none=True)
    metrics = dict(loss=0.0, kl=0.0, ratio_mean=0.0, clip_fraction=0.0,
                   old_new_abs_logprob_mean=0.0, max_old_new_abs_logprob=0.0,
                   max_step_mean_logprob_error=0.0)
    episodes = batch['episodes']
    progress = args.output.parent / 'training_progress.json'
    for episode_index, episode in enumerate(episodes):
        trajectory = p.read_json(episode['trajectory'])
        for step_index, step in enumerate(trajectory['steps']):
            with torch.no_grad():
                ref = action_logprobs(reference, step['prompt_ids'], step['response_ids'], train['head_chunk_size'])
            new = action_logprobs(model, step['prompt_ids'], step['response_ids'], train['head_chunk_size'])
            old = torch.tensor(step['old_logprobs'], device=new.device, dtype=torch.float32)
            error = (new.detach() - old).abs()
            step_error = error.mean().item()
            if not math.isfinite(step_error) or step_error > train['old_logprob_mean_tolerance']:
                raise RuntimeError(f'Initial HF/vLLM logprob mismatch {step_error}; no optimizer step committed.')
            losses, ratio, kl = grpo_terms(new, old, ref, episode['advantage'], train['clip_epsilon'], train['kl_beta'])
            if not torch.isfinite(losses).all() or not torch.isfinite(ratio).all():
                raise FloatingPointError('Non-finite GRPO terms.')
            divisor = len(episodes) * episode['token_count']
            loss = losses.sum() / divisor
            loss.backward()
            with torch.no_grad():
                metrics['loss'] += loss.item()
                metrics['kl'] += kl.sum().item() / divisor
                metrics['ratio_mean'] += ratio.sum().item() / divisor
                metrics['clip_fraction'] += ((ratio - 1).abs() > train['clip_epsilon']).sum().item() / divisor
                metrics['old_new_abs_logprob_mean'] += error.sum().item() / divisor
                metrics['max_old_new_abs_logprob'] = max(metrics['max_old_new_abs_logprob'], error.max().item())
                metrics['max_step_mean_logprob_error'] = max(metrics['max_step_mean_logprob_error'], step_error)
            p.atomic_json(progress, {'episode': episode_index + 1, 'step': step_index + 1,
                                    'episodes': len(episodes), 'steps_in_episode': len(trajectory['steps']),
                                    'elapsed_seconds': time.monotonic() - started, 'metrics': metrics})
            del loss, losses, ratio, kl, new, old, ref, error
        print(json.dumps({'episode_done': episode_index + 1, 'task': episode['task_id'],
                          'sample': episode['sample'], 'elapsed_seconds': time.monotonic() - started}), flush=True)
    metrics['gradient_norm_before_clip'] = float(torch.nn.utils.clip_grad_norm_(parameters, train['max_grad_norm'], error_if_nonfinite=True))
    if any(not math.isfinite(v) for v in metrics.values()):
        raise FloatingPointError('Non-finite training metrics.')
    optimizer.step()
    if adapter_digest(reference) != reference_hash or any(v.grad is not None for v in reference.parameters()):
        raise RuntimeError('Reference changed or received gradients.')
    updated_hash = adapter_digest(model)
    if any(e['advantage'] != 0 for e in episodes) and updated_hash == initial_policy_hash:
        raise RuntimeError('Nonzero-advantage update did not change policy parameters.')
    metrics.update(policy_changed=updated_hash != initial_policy_hash, reference_unchanged=True,
                   generated_tokens=sum(e['token_count'] for e in episodes),
                   peak_gpu_allocated_gib=torch.cuda.max_memory_allocated() / 2**30,
                   elapsed_seconds=time.monotonic() - started)
    temporary = args.output.with_name(args.output.name + f'.incomplete.{os.getpid()}')
    temporary.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(temporary, safe_serialization=True)
    # Save/reload validation on actual action tokens, with the updated policy.
    probe = p.read_json(episodes[0]['trajectory'])['steps'][0]
    model.eval()
    with torch.no_grad():
        before_reload = action_logprobs(model, probe['prompt_ids'], probe['response_ids'], train['head_chunk_size']).cpu()
    from peft import PeftModel
    base = model.unload()
    del model
    reloaded = PeftModel.from_pretrained(base, str(temporary), is_trainable=False, local_files_only=True)
    reloaded.eval()
    with torch.no_grad():
        after_reload = action_logprobs(reloaded, probe['prompt_ids'], probe['response_ids'], train['head_chunk_size']).cpu()
    reload_error = float((before_reload - after_reload).abs().max())
    if reload_error > 1e-5:
        raise RuntimeError(f'Checkpoint reload changed output: {reload_error}')
    metrics['reload_max_abs_logprob_error'] = reload_error
    torch.save({'optimizer': optimizer.state_dict(), 'torch_rng': torch.get_rng_state(),
                'cuda_rng': torch.cuda.get_rng_state_all(), 'python_rng': random.getstate()}, temporary / 'optimizer.pt')
    files = {name: p.file_sha(temporary / name) for name in ('adapter_config.json', 'adapter_model.safetensors', 'optimizer.pt')}
    info = {'framework_fingerprint': p.identity(), 'branch': batch['branch'], 'update': batch['update'],
            'parent_policy_id': batch['policy_id'], 'reference_policy_id': batch['reference_policy_id'],
            'batch_sha256': p.file_sha(args.batch), 'files': files, 'metrics': metrics,
            'policy_id': p.digest({'parent': batch['policy_id'], 'branch': batch['branch'],
                                   'update': batch['update'], 'weights': files['adapter_model.safetensors']})}
    p.atomic_json(temporary / 'manifest.json', info)
    temporary.rename(args.output)
    print(json.dumps(metrics), flush=True)


if __name__ == '__main__':
    main()
