"""Accumulate one shard's globally normalized gradients; never update parameters."""
import argparse
import fcntl
import math
import random
import time
import two_gpu as q


def accumulate_episode(model, reference, episode, total, train, metrics, progress):
    import torch
    if q.p.file_sha(episode['trajectory']) != episode['trajectory_sha256']:
        raise ValueError('Frozen trajectory changed.')
    trajectory = q.p.read_json(episode['trajectory'])
    for step_index, step in enumerate(trajectory['steps']):
        with torch.no_grad():
            ref = q.core.action_logprobs(reference, step['prompt_ids'], step['response_ids'], train['head_chunk_size'])
        new = q.core.action_logprobs(model, step['prompt_ids'], step['response_ids'], train['head_chunk_size'])
        old = torch.tensor(step['old_logprobs'], device=new.device, dtype=torch.float32)
        error = (new.detach() - old).abs()
        step_error = error.mean().item()
        if not math.isfinite(step_error) or step_error > train['old_logprob_mean_tolerance']:
            raise RuntimeError('Initial policy/behavior logprob mismatch; no optimizer step committed.')
        losses, ratio, kl = q.core.grpo_terms(new, old, ref, episode['advantage'], train['clip_epsilon'], train['kl_beta'])
        if not torch.isfinite(losses).all() or not torch.isfinite(ratio).all():
            raise FloatingPointError('Non-finite GRPO terms.')
        # Global normalization is essential: do NOT divide by this worker's shard size.
        divisor = total * episode['token_count']
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
        progress(step_index + 1, len(trajectory['steps']))
        del loss, losses, ratio, kl, new, old, ref, error


def execute(rank):
    batch, manifest = q.load_input()
    folder = q.worker_dir(rank)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'complete.json').exists():
        return q.completed_worker(rank, manifest)
    q.configure_gpu(q.settings()['gpus'][rank])
    import torch
    cfg, train = q.p.load_config(), batch['training']
    random.seed(cfg['training']['seed'])
    torch.manual_seed(cfg['training']['seed'])
    torch.cuda.manual_seed_all(cfg['training']['seed'])
    started = time.monotonic()
    model, reference = q.core.load_models(cfg, q.p.policy_info('rubric', 0)['path'])
    if not any(v.requires_grad for v in model.parameters()) or any(v.requires_grad and 'lora_' not in n for n, v in model.named_parameters()):
        raise ValueError('Only LoRA parameters may receive gradients.')
    if any(v.requires_grad for v in reference.parameters()):
        raise ValueError('Reference must be frozen.')
    if {v.data_ptr() for v in model.parameters()} & {v.data_ptr() for v in reference.parameters()}:
        raise ValueError('Policy/reference storage must be independent.')
    initial_hash, reference_hash = q.core.adapter_digest(model), q.core.adapter_digest(reference)
    metrics = dict(loss=0., kl=0., ratio_mean=0., clip_fraction=0., old_new_abs_logprob_mean=0.,
                   max_old_new_abs_logprob=0., max_step_mean_logprob_error=0.)
    indices = manifest['assignments'][rank]
    signature = q.signature(manifest, rank)
    recovery = folder / 'gradients.pt'
    completed, prior_elapsed = 0, 0.
    if recovery.exists():
        state = q.recovery.restore_gradients(recovery, model, signature, len(indices), 6)
        completed, metrics, prior_elapsed = state['completed_episodes'], state['metrics'], state['elapsed_seconds']
    for local in range(completed, len(indices)):
        global_index = indices[local]
        episode = batch['episodes'][global_index]
        def progress(step, steps):
            q.p.atomic_json(folder / 'progress.json', {
                'phase': 'backward', 'rank': rank, 'gpu': str(rank), 'completed_episodes': local,
                'episodes': len(indices), 'global_episode': global_index + 1,
                'task_id': episode['task_id'], 'sample': episode['sample'],
                'step': step, 'steps_in_episode': steps, 'optimizer_steps': 0,
                'elapsed_seconds': prior_elapsed + time.monotonic() - started, 'metrics': metrics})
        accumulate_episode(model, reference, episode, len(batch['episodes']), train, metrics, progress)
        if (local + 1) % 6 == 0:
            q.recovery.save_gradients(recovery, model, signature, local + 1, metrics,
                                      prior_elapsed + time.monotonic() - started)
        q.p.atomic_json(folder / 'progress.json', {
            'phase': 'accumulating', 'rank': rank, 'completed_episodes': local + 1,
            'episodes': len(indices), 'optimizer_steps': 0, 'elapsed_seconds': prior_elapsed + time.monotonic() - started})
        print(__import__('json').dumps({'rank': rank, 'completed_episodes': local + 1, 'global_episode': global_index + 1}), flush=True)
    if q.core.adapter_digest(model) != initial_hash:
        raise RuntimeError('A worker changed the initial policy before global reduction.')
    if q.core.adapter_digest(reference) != reference_hash or any(v.grad is not None for v in reference.parameters()):
        raise RuntimeError('A worker changed the reference or assigned it gradients.')
    if any(not math.isfinite(v) for v in metrics.values()):
        raise FloatingPointError('Non-finite worker metrics.')
    record = {'signature': signature, 'completed_episodes': len(indices), 'optimizer_steps': 0,
              'policy_unchanged': True, 'reference_unchanged': True,
              'initial_policy_hash': initial_hash, 'reference_hash': reference_hash,
              'gradients_sha256': q.p.file_sha(recovery), 'metrics': metrics,
              'elapsed_seconds': prior_elapsed + time.monotonic() - started,
              'peak_gpu_allocated_gib': torch.cuda.max_memory_allocated() / 2**30 if torch.cuda.is_available() else 0}
    q.p.atomic_json(folder / 'complete.json', record)
    q.p.atomic_json(folder / 'progress.json', {'phase': 'gradients_complete', 'rank': rank,
        'completed_episodes': len(indices), 'episodes': len(indices), 'optimizer_steps': 0})
    return record


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rank', type=int, choices=(0, 1), required=True)
    args = ap.parse_args()
    try:
        folder = q.worker_dir(args.rank)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / 'worker.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            execute(args.rank)
    except Exception as error:
        q.p.atomic_json(q.worker_dir(args.rank) / 'failure.json', {'error': f'{type(error).__name__}: {error}', 'at': q.stamp()})
        raise
