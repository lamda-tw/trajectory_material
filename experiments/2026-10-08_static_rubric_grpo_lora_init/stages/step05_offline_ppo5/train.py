"""One full-batch offline PPO epoch; fixed behavior probabilities and initial SFT reference."""
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


def reference_values(reference, episode, trajectory, train, signature, progress):
    """Exact frozen-reference likelihoods, reusable across all five offline epochs."""
    import torch
    uid = f"{episode['task_id']}__{episode['sample']:02d}"
    path = p.RUN / 'reference_logprobs' / f'{uid}.json'
    key = p.digest({'framework': signature['framework'], 'reference': signature['reference'],
                    'trajectory': episode['trajectory_sha256']})
    if path.exists():
        record = p.read_json(path)
        values = record['logprobs']
        if record['key'] != key or record['sha256'] != p.digest(values):
            raise ValueError('Reference likelihood cache changed.')
    else:
        values = []
        with torch.no_grad():
            for step_index, step in enumerate(trajectory['steps']):
                values.append(action_logprobs(reference, step['prompt_ids'], step['response_ids'],
                                              train['head_chunk_size']).cpu().tolist())
                p.atomic_json(progress, {'phase': 'reference_likelihoods', 'epoch': signature['epoch'],
                                        'task': episode['task_id'], 'sample': episode['sample'],
                                        'step': step_index + 1, 'steps': len(trajectory['steps'])})
        p.atomic_json(path, {'key': key, 'logprobs': values, 'sha256': p.digest(values)})
    if len(values) != len(trajectory['steps']):
        raise ValueError('Reference step count differs from frozen trajectory.')
    for step, row in zip(trajectory['steps'], values):
        p.validate_tokens(step['prompt_ids'], step['response_ids'], row)
    return values


def main():
    from offline_state import (atomic_torch_save, check_logprobs, restore_gradients,
                               restore_rng, rng_state, save_gradients)
    ap = argparse.ArgumentParser(description='One full-batch epoch of five-epoch offline PPO')
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--epoch', type=int, required=True, choices=range(1, 6))
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--allow-gpu', action='store_true')
    args = ap.parse_args()
    if args.execute and not args.allow_gpu:
        ap.error('GPU use is on hold; explicit --allow-gpu is required after a new user instruction.')
    batch = p.validate_batch(args.batch)
    if args.output.resolve() != p.checkpoint_path('rubric', args.epoch).resolve():
        raise ValueError('Checkpoint destination must match this epoch.')
    if not args.execute:
        print(json.dumps({'validated': True, 'episodes': len(batch['episodes']),
                          'epoch': args.epoch, 'loads_model': False}))
        return
    if args.output.exists():
        raise FileExistsError('Committed checkpoints are immutable.')
    cfg, train = p.load_config(), batch['training']
    parent = p.policy_info('rubric', args.epoch - 1)
    batch_sha = p.file_sha(args.batch)
    if args.epoch > 1 and parent['batch_sha256'] != batch_sha:
        raise ValueError('All five epochs must use exactly the same batch.')
    signature = {'framework': p.identity(), 'batch': batch_sha, 'epoch': args.epoch,
                 'parent': parent['policy_id'], 'behavior': batch['policy_id'],
                 'reference': batch['reference_policy_id']}
    from resources import require_free_gpu
    require_free_gpu(p.settings()['execution_gpu'], cfg['training']['minimum_free_gpu_gib'])
    os.environ.update(CUDA_VISIBLE_DEVICES=p.settings()['execution_gpu'], HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
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
    if args.epoch > 1:
        state = torch.load(Path(parent['path']) / 'optimizer.pt', map_location='cpu', weights_only=False)
        if state['completed_epochs'] != args.epoch - 1 or state['batch_sha256'] != batch_sha:
            raise ValueError('Optimizer state belongs to another epoch or batch.')
        optimizer.load_state_dict(state['optimizer'])
        restore_rng(state)
    optimizer.zero_grad(set_to_none=True)
    metrics = dict(loss=0.0, kl=0.0, ratio_mean=0.0, clip_fraction=0.0,
                   old_new_abs_logprob_mean=0.0, max_old_new_abs_logprob=0.0,
                   max_step_mean_logprob_error=0.0, max_reference_behavior_logprob_error=0.0)
    episodes = batch['episodes']
    progress = args.output.parent / 'training_progress.json'
    recovery = args.output.parent / 'accumulated_gradients.pt'
    completed, prior_elapsed = 0, 0.0
    boundary = train['gradient_checkpoint_every_episodes']
    if recovery.exists():
        state = restore_gradients(recovery, model, signature, len(episodes), boundary)
        completed, prior_elapsed = state['completed_episodes'], state['elapsed_seconds']
        metrics = state['metrics']
        print(json.dumps({'resumed_epoch': args.epoch, 'completed_episodes': completed}), flush=True)
    for episode_index in range(completed, len(episodes)):
        episode = episodes[episode_index]
        trajectory = p.read_json(episode['trajectory'])
        ref_values = reference_values(reference, episode, trajectory, train, signature, progress)
        for step_index, step in enumerate(trajectory['steps']):
            new = action_logprobs(model, step['prompt_ids'], step['response_ids'], train['head_chunk_size'])
            old = torch.tensor(step['old_logprobs'], device=new.device, dtype=torch.float32)
            ref = torch.tensor(ref_values[step_index], device=new.device, dtype=torch.float32)
            step_error, ref_error = check_logprobs(args.epoch, new, old, ref,
                                                  train['old_logprob_mean_tolerance'])
            error = (new.detach() - old).abs()
            losses, ratio, kl = grpo_terms(new, old, ref, episode['advantage'], train['clip_epsilon'], train['kl_beta'])
            if not torch.isfinite(losses).all() or not torch.isfinite(ratio).all():
                raise FloatingPointError('Non-finite offline PPO terms.')
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
                metrics['max_reference_behavior_logprob_error'] = max(metrics['max_reference_behavior_logprob_error'], ref_error)
            p.atomic_json(progress, {'phase': 'backward', 'epoch': args.epoch, 'target_epochs': 5,
                                    'episode': episode_index + 1, 'episodes': len(episodes),
                                    'step': step_index + 1, 'steps_in_episode': len(trajectory['steps']),
                                    'elapsed_seconds': prior_elapsed + time.monotonic() - started, 'metrics': metrics})
            del loss, losses, ratio, kl, new, old, ref, error
        if (episode_index + 1) % boundary == 0 or episode_index + 1 == len(episodes):
            save_gradients(recovery, model, signature, episode_index + 1, metrics,
                           prior_elapsed + time.monotonic() - started)
        print(json.dumps({'epoch': args.epoch, 'episode_done': episode_index + 1,
                          'task': episode['task_id'], 'sample': episode['sample']}), flush=True)
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
                   optimizer_steps_this_epoch=1, completed_epochs=args.epoch,
                   generated_tokens=sum(e['token_count'] for e in episodes),
                   peak_gpu_allocated_gib=torch.cuda.max_memory_allocated() / 2**30,
                   elapsed_seconds=prior_elapsed + time.monotonic() - started)
    temporary = args.output.with_name(args.output.name + f'.incomplete.{os.getpid()}')
    temporary.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(temporary, safe_serialization=True)
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
    atomic_torch_save(temporary / 'optimizer.pt', {'optimizer': optimizer.state_dict(),
                      'completed_epochs': args.epoch, 'batch_sha256': batch_sha, **rng_state()})
    files = {name: p.file_sha(temporary / name) for name in ('adapter_config.json', 'adapter_model.safetensors', 'optimizer.pt')}
    info = {'framework_fingerprint': p.identity(), 'branch': 'rubric', 'update': args.epoch,
            'offline_ppo_epoch': args.epoch, 'parent_policy_id': parent['policy_id'],
            'behavior_policy_id': batch['policy_id'], 'reference_policy_id': batch['reference_policy_id'],
            'batch_sha256': batch_sha, 'files': files, 'metrics': metrics,
            'policy_id': p.digest({'parent': parent['policy_id'], 'epoch': args.epoch,
                                   'batch': batch_sha, 'weights': files['adapter_model.safetensors']})}
    p.atomic_json(temporary / 'manifest.json', info)
    temporary.rename(args.output)
    recovery.unlink(missing_ok=True)
    p.atomic_json(progress, {'phase': 'epoch_complete', 'epoch': args.epoch, 'metrics': metrics})
    print(json.dumps(metrics), flush=True)


if __name__ == '__main__':
    main()
