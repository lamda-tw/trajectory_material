"""Recovery of uncommitted full-batch gradients; original behavior stays fixed."""
import math
import os
from pathlib import Path
import random


def atomic_torch_save(path, value):
    import torch
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
    torch.save(value, temporary)
    temporary.replace(path)


def rng_state():
    import torch
    return {'torch_rng': torch.get_rng_state(), 'python_rng': random.getstate(),
            'cuda_rng': torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}


def restore_rng(state):
    import torch
    torch.set_rng_state(state['torch_rng'])
    random.setstate(state['python_rng'])
    if state['cuda_rng']:
        torch.cuda.set_rng_state_all(state['cuda_rng'])


def save_gradients(path, model, signature, completed, metrics, elapsed):
    gradients = {name: None if param.grad is None else param.grad.detach().cpu()
                 for name, param in model.named_parameters() if param.requires_grad}
    atomic_torch_save(path, {'signature': signature, 'completed_episodes': completed,
                            'metrics': metrics, 'elapsed_seconds': elapsed,
                            'gradients': gradients, **rng_state()})


def restore_gradients(path, model, signature, total_episodes, boundary):
    import torch
    state = torch.load(path, map_location='cpu', weights_only=False)
    if state['signature'] != signature:
        raise ValueError('Gradient recovery state belongs to another batch/epoch/policy.')
    completed = state['completed_episodes']
    if (type(completed) is not int or not 0 <= completed <= total_episodes
            or (completed != total_episodes and completed % boundary)):
        raise ValueError('Recovery state is not at a complete group boundary.')
    params = {name: value for name, value in model.named_parameters() if value.requires_grad}
    if set(params) != set(state['gradients']):
        raise ValueError('Recovery parameter names changed.')
    if any(not math.isfinite(value) for value in state['metrics'].values()):
        raise ValueError('Non-finite recovery metrics.')
    for name, param in params.items():
        grad = state['gradients'][name]
        if grad is not None:
            if grad.shape != param.shape or grad.dtype != param.dtype or not torch.isfinite(grad).all():
                raise ValueError('Invalid recovered gradient.')
            param.grad = grad.to(param.device)
        else:
            param.grad = None
    restore_rng(state)
    return state


def check_logprobs(epoch, current, behavior, reference, tolerance):
    """After epoch one, policy drift is expected; never overwrite behavior logprobs."""
    import torch
    if any(not torch.isfinite(t).all() for t in (current, behavior, reference)):
        raise FloatingPointError('Non-finite likelihoods.')
    reference_error = (reference - behavior).abs().mean().item()
    current_error = (current.detach() - behavior).abs().mean().item()
    if reference_error > tolerance or (epoch == 1 and current_error > tolerance):
        raise RuntimeError('Initial HF/vLLM likelihood mismatch; no optimizer update committed.')
    return current_error, reference_error
