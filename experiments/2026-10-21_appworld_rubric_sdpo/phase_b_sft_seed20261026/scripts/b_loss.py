"""Differentiable student top-k + exact tail reverse KL; teacher always detached."""
import torch
from torch.utils.checkpoint import checkpoint


def bucket_reverse_kl(student_logits, teacher_logits, k=100):
    p = torch.log_softmax(student_logits.float(), dim=-1)
    q = torch.log_softmax(teacher_logits.detach().float(), dim=-1)
    if k >= p.shape[-1]:
        return (p.exp() * (p - q)).sum(-1)
    # Same student-selected token IDs for both distributions; no top-k renormalization.
    ids = torch.topk(p.detach(), k, dim=-1).indices
    lp = p.gather(-1, ids); lq = q.gather(-1, ids)
    # Stable tail log mass: avoid subtracting a nearly-one top-k mass from one.
    omitted = torch.zeros_like(p, dtype=torch.bool).scatter_(-1, ids, True)
    tail_p = torch.logsumexp(p.masked_fill(omitted, -torch.inf), dim=-1)
    tail_q = torch.logsumexp(q.masked_fill(omitted, -torch.inf), dim=-1)
    return (lp.exp() * (lp - lq)).sum(-1) + tail_p.exp() * (tail_p - tail_q)


def response_hidden(model, prompt_ids, response_ids):
    assert prompt_ids and response_ids
    device = next(model.parameters()).device
    ids = torch.tensor([prompt_ids + response_ids[:-1]], device=device)
    output = model.get_base_model().model(input_ids=ids, use_cache=False, return_dict=True).last_hidden_state
    hidden = output[0, len(prompt_ids) - 1:]
    assert len(hidden) == len(response_ids)
    return hidden


def select_adapter(model, name):
    model.set_adapter(name)
    for key, parameter in model.named_parameters():
        parameter.requires_grad_(name == 'student' and '.student.' in key and 'lora_' in key)


def step_loss(model, example, cfg):
    teacher = None
    if example['branch'] == 'sdpo':
        select_adapter(model, 'teacher'); model.eval()
        with torch.no_grad():
            teacher = response_hidden(model, example['teacher_prompt_ids'], example['response_ids']).detach()
    select_adapter(model, 'student'); model.train()
    student = response_hidden(model, example['prompt_ids'], example['response_ids'])
    head = model.get_base_model().lm_head
    target = torch.tensor(example['response_ids'], device=student.device)
    size = cfg['head_chunk_size']
    if teacher is None:
        def operation(h, y):
            return torch.nn.functional.cross_entropy(head(h).float(), y, reduction='sum')
        pieces = [checkpoint(operation, student[i:i+size], target[i:i+size], use_reentrant=False) for i in range(0, len(target), size)]
    else:
        assert not teacher.requires_grad and teacher.shape == student.shape
        def operation(h, t):
            with torch.no_grad():
                q = head(t).float()
            return bucket_reverse_kl(head(h), q, cfg['top_k']).sum()
        pieces = [checkpoint(operation, student[i:i+size], teacher[i:i+size], use_reentrant=False) for i in range(0, len(target), size)]
    return torch.stack(pieces).sum() / len(target)


def learning_rate(update, cfg):
    assert update >= 1
    return cfg['learning_rate'] * min(1.0, update / cfg['warmup_nonempty_updates'])


def ema_state(teacher, student, decay):
    assert set(teacher) == set(student)
    return {key: teacher[key].detach().float() * decay + student[key].detach().float() * (1 - decay) for key in teacher}
