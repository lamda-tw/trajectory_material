"""Sum both complete gradient shards, clip once, update once, and verify the saved adapter."""
import math
import os
import random
import time
import two_gpu as q


def merge_gradients(model, states):
    import torch
    parameters = {n: v for n, v in model.named_parameters() if v.requires_grad}
    if len(states) != 2:
        raise ValueError('Exactly two complete shards are required.')
    for state in states:
        if set(state['gradients']) != set(parameters):
            raise ValueError('Gradient parameter sets differ.')
    for name, param in parameters.items():
        combined = None
        for state in states:
            value = state['gradients'][name]
            if value is None:
                continue
            if value.shape != param.shape or value.dtype != param.dtype or not torch.isfinite(value).all():
                raise ValueError('Gradient shape, dtype or finiteness mismatch.')
            combined = value.clone() if combined is None else combined + value
        if combined is not None and not torch.isfinite(combined).all():
            raise FloatingPointError('Gradient sum is non-finite.')
        param.grad = None if combined is None else combined.to(param.device)
    return list(parameters.values())


def execute():
    batch, manifest = q.load_input()
    output = q.RUN / 'checkpoint'
    if output.exists():
        return q.checkpoint_info(manifest)
    records = [q.completed_worker(rank, manifest) for rank in range(2)]
    q.configure_gpu('0')
    import torch
    states = [torch.load(q.worker_dir(rank) / 'gradients.pt', map_location='cpu', weights_only=False) for rank in range(2)]
    for rank, state in enumerate(states):
        if state['signature'] != q.signature(manifest, rank) or state['completed_episodes'] != len(manifest['assignments'][rank]):
            raise ValueError('Gradient state is incomplete or stale.')
    cfg, train = q.p.load_config(), batch['training']
    random.seed(cfg['training']['seed'])
    torch.manual_seed(cfg['training']['seed'])
    torch.cuda.manual_seed_all(cfg['training']['seed'])
    started = time.monotonic()
    model, reference = q.core.load_models(cfg, q.p.policy_info('rubric', 0)['path'])
    initial_hash, reference_hash = q.core.adapter_digest(model), q.core.adapter_digest(reference)
    if any(r['initial_policy_hash'] != initial_hash or r['reference_hash'] != reference_hash for r in records):
        raise ValueError('Workers accumulated gradients from different models.')
    parameters = merge_gradients(model, states)
    optimizer = torch.optim.AdamW(parameters, lr=train['learning_rate'], weight_decay=train['weight_decay'])
    metrics = {key: (max(r['metrics'][key] for r in records) if key.startswith('max_')
                     else sum(r['metrics'][key] for r in records)) for key in records[0]['metrics']}
    metrics['gradient_norm_before_clip'] = float(torch.nn.utils.clip_grad_norm_(parameters, train['max_grad_norm'], error_if_nonfinite=True))
    if any(not math.isfinite(v) for v in metrics.values()):
        raise FloatingPointError('Non-finite merged metrics.')
    optimizer.step()
    if not all(float(v['step']) == 1 for v in optimizer.state.values()):
        raise RuntimeError('Expected exactly one fresh optimizer step.')
    if q.core.adapter_digest(reference) != reference_hash or any(v.grad is not None for v in reference.parameters()):
        raise RuntimeError('Reference changed during update.')
    changed = q.core.adapter_digest(model) != initial_hash
    if any(e['advantage'] != 0 for e in batch['episodes']) and not changed:
        raise RuntimeError('Nonzero advantages did not change the policy.')
    temporary = output.with_name(f'checkpoint.incomplete.{os.getpid()}')
    temporary.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(temporary, safe_serialization=True)
    probe = q.p.read_json(batch['episodes'][0]['trajectory'])['steps'][0]
    model.eval()
    with torch.no_grad():
        before = q.core.action_logprobs(model, probe['prompt_ids'], probe['response_ids'], train['head_chunk_size']).cpu()
    from peft import PeftModel
    base = model.unload()
    del model
    reloaded = PeftModel.from_pretrained(base, str(temporary), is_trainable=False, local_files_only=True).eval()
    with torch.no_grad():
        after = q.core.action_logprobs(reloaded, probe['prompt_ids'], probe['response_ids'], train['head_chunk_size']).cpu()
    reload_error = float((before - after).abs().max())
    if reload_error > 1e-5:
        raise RuntimeError('Saved adapter changed action logprobs after reload.')
    metrics.update(policy_changed=changed, reference_unchanged=True, optimizer_steps=1, ppo_epochs=1,
                   trajectories=len(batch['episodes']), generated_tokens=sum(e['token_count'] for e in batch['episodes']),
                   reload_max_abs_logprob_error=reload_error, worker_elapsed_seconds=[r['elapsed_seconds'] for r in records],
                   worker_peak_gpu_allocated_gib=[r['peak_gpu_allocated_gib'] for r in records],
                   finalization_seconds=time.monotonic() - started)
    q.recovery.atomic_torch_save(temporary / 'optimizer.pt', {'optimizer': optimizer.state_dict(),
        'optimizer_steps': 1, 'batch_sha256': manifest['batch_sha256'], **q.recovery.rng_state()})
    files = {name: q.p.file_sha(temporary / name) for name in ('adapter_config.json', 'adapter_model.safetensors', 'optimizer.pt')}
    info = {'execution_fingerprint': manifest['execution_fingerprint'],
            'source_framework_fingerprint': manifest['source_framework_fingerprint'],
            'batch_sha256': manifest['batch_sha256'], 'parent_policy_id': manifest['parent_policy_id'],
            'reference_policy_id': manifest['reference_policy_id'], 'optimizer_steps': 1,
            'gpus': ['0', '1'], 'gradient_reduction': 'SUM of globally normalized shards',
            'metrics': metrics, 'files': files,
            'policy_id': q.p.digest({'parent': manifest['parent_policy_id'], 'batch': manifest['batch_sha256'],
                                    'weights': files['adapter_model.safetensors']})}
    q.p.atomic_json(temporary / 'manifest.json', info)
    temporary.rename(output)
    return q.checkpoint_info(manifest)


if __name__ == '__main__':
    print(__import__('json').dumps(execute(), ensure_ascii=False), flush=True)
