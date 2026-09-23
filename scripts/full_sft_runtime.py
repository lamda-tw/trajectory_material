"""Completion loss and same-topology restart support for the local FSDP run."""
from __future__ import annotations

import gc
import hashlib
import json
import os
import random
import shutil
from pathlib import Path

import torch
import torch.distributed as dist
import torch.nn.functional as F


def completion_loss(model, batch):
    labels = batch['labels']
    if labels.shape[0] != 1:
        raise ValueError('selected-position loss requires per-rank batch size 1')
    positions = torch.nonzero(labels[0, 1:] != -100, as_tuple=False).flatten()
    if not positions.numel():
        raise ValueError('no causal completion targets')
    targets = labels[:, 1:].index_select(1, positions)
    output = model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'],
                   logits_to_keep=positions, use_cache=False)
    return F.cross_entropy(output.logits.float().reshape(-1, output.logits.shape[-1]),
                           targets.reshape(-1))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cpu_tree(value):
    if isinstance(value, torch.Tensor):
        # Clone CPU tensors too: do not serialize an oversized backing storage/view.
        return value.detach().to('cpu', copy=True)
    if isinstance(value, dict):
        return {k: cpu_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [cpu_tree(v) for v in value]
    if isinstance(value, tuple):
        return tuple(cpu_tree(v) for v in value)
    return value


def parameter_signature(model):
    return [(name, list(p.shape), str(p.dtype)) for name, p in model.named_parameters()]


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def release_file_cache(path):
    # Only advise eviction of this run's already-written checkpoint pages.
    with Path(path).open('rb') as f:
        if hasattr(os, 'posix_fadvise'):
            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)


def save_restart(model, optimizer, scheduler, root, progress, contract, reserve_gib=8):
    """Save original FSDP parameter shards; requires the same wrap/order/topology."""
    rank, world = dist.get_rank(), dist.get_world_size()
    root = Path(root)
    # Elapsed wall time differs slightly between ranks; share rank 0's metadata.
    shared_progress = [progress if rank == 0 else None]
    dist.broadcast_object_list(shared_progress, src=0)
    progress = shared_progress[0]
    name = f"step_{progress['global_step']:06d}"
    target, tmp = root / name, root / (name + '.tmp')
    size = sum(p.numel() * p.element_size() for p in model.parameters())
    size += sum(t.numel() * t.element_size() for s in optimizer.state.values()
                for t in s.values() if isinstance(t, torch.Tensor))
    sizes = [None] * world
    dist.all_gather_object(sizes, size)
    if rank == 0:
        root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        if tmp.exists():
            shutil.rmtree(tmp)
        if shutil.disk_usage(root).free < sum(sizes) + reserve_gib * 1024**3:
            raise RuntimeError('insufficient free disk for atomic restart checkpoint')
        tmp.mkdir()
    dist.barrier()
    # Serialize ranks in turn to bound CPU tensors and page-cache memory.
    for writer_rank in range(world):
        if rank == writer_rank:
            payload = {
                'version': 1, 'rank': rank, 'world_size': world,
                'signature': parameter_signature(model), 'contract': contract,
                'parameters': {n: cpu_tree(p) for n, p in model.named_parameters()},
                'optimizer': cpu_tree(optimizer.state_dict()),
                'scheduler': scheduler.state_dict(), 'progress': progress,
                'python_rng': random.getstate(), 'torch_rng': torch.get_rng_state(),
                'cuda_rng': torch.cuda.get_rng_state() if torch.cuda.is_initialized() else None,
            }
            shard = tmp / f'rank_{rank}.pt'
            with shard.open('wb') as f:
                torch.save(payload, f)
                f.flush()
                os.fsync(f.fileno())
            del payload
            gc.collect()
            release_file_cache(shard)
        dist.barrier()
    if rank == 0:
        manifest = {'version': 1, 'world_size': world, 'progress': progress,
                    'contract': contract,
                    'files': {f'rank_{r}.pt': (tmp / f'rank_{r}.pt').stat().st_size
                              for r in range(world)}}
        atomic_json(tmp / 'COMPLETE.json', manifest)
        fsync_directory(tmp)
        tmp.rename(target)
        fsync_directory(root)
        atomic_json(root / 'latest.json', {'directory': name, 'global_step': progress['global_step']})
        # Retain the previous completed state until the new one is durable.
        for previous in root.glob('step_*'):
            if previous != target and previous.is_dir() and not previous.name.endswith('.tmp'):
                shutil.rmtree(previous)
        fsync_directory(root)
        print(json.dumps({'event': 'restart_saved', 'path': str(target),
                          'global_step': progress['global_step']}), flush=True)
    dist.barrier()
    return target


def load_restart(model, optimizer, scheduler, directory, contract, allow_code_change=False):
    rank, world = dist.get_rank(), dist.get_world_size()
    directory = Path(directory)
    if (directory / 'latest.json').is_file():
        directory = directory / json.loads((directory / 'latest.json').read_text())['directory']
    manifest = json.loads((directory / 'COMPLETE.json').read_text())
    saved_contract, expected_contract = dict(manifest['contract']), dict(contract)
    if allow_code_change:
        # Explicit opt-in for a reviewed runtime bug fix; never relax data,
        # hyperparameters, framework versions or topology checks.
        for key in ('trainer_sha256', 'runtime_sha256'):
            saved_contract.pop(key, None)
            expected_contract.pop(key, None)
    if saved_contract != expected_contract or manifest['world_size'] != world:
        raise ValueError('checkpoint data/config/runtime/topology contract mismatch')
    shard = directory / f'rank_{rank}.pt'
    if shard.stat().st_size != manifest['files'][shard.name]:
        raise ValueError('incomplete restart shard')
    progress = None
    # This is our own trusted checkpoint, not an external pickle file.
    for reader_rank in range(world):
        if rank == reader_rank:
            payload = torch.load(shard, map_location='cpu', weights_only=False, mmap=True)
            if payload['rank'] != rank or payload['signature'] != parameter_signature(model):
                raise ValueError('FSDP shard layout changed')
            local_progress = {k:v for k,v in payload['progress'].items() if k != 'elapsed_seconds'}
            shared_progress = {k:v for k,v in manifest['progress'].items() if k != 'elapsed_seconds'}
            if payload['contract'] != manifest['contract'] or local_progress != shared_progress:
                raise ValueError('restart shard metadata mismatch')
            with torch.no_grad():
                for name, parameter in model.named_parameters():
                    parameter.copy_(payload['parameters'][name])
            optimizer.load_state_dict(payload['optimizer'])
            scheduler.load_state_dict(payload['scheduler'])
            progress = manifest['progress']
            random.setstate(payload['python_rng'])
            torch.set_rng_state(payload['torch_rng'])
            if payload['cuda_rng'] is not None:
                torch.cuda.set_rng_state(payload['cuda_rng'])
            del payload
            gc.collect()
            release_file_cache(shard)
        dist.barrier()
    return progress
