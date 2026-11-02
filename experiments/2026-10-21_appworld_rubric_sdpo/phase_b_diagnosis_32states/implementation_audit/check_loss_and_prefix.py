"""CPU-only SDPO implementation audit; no model forward or optimizer updates.

Extracts the two official pure loss functions with AST, avoiding import of verl's
training runtime. Compares local loss and logit gradients at matched settings,
then inspects every code token from existing diagnostic probability artifacts.
"""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

os.environ['CUDA_VISIBLE_DEVICES'] = ''
import torch
import torch.nn.functional as F

A = Path(__file__).resolve().parent
D = A.parent
R = D.parent


def extract(path, names, namespace):
    tree = ast.parse(path.read_text())
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in tree.body} == set(names)
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace


def main():
    torch.set_num_threads(2)
    official_path = A / 'official/verl/trainer/ppo/core_algos.py'
    local_path = R / 'scripts/b_loss.py'
    common = {'torch': torch, 'F': F, 'Any': Any, 'Optional': Optional}
    official = extract(official_path, ['agg_loss', 'compute_self_distillation_loss'], {
        **common, 'verl_F': SimpleNamespace(masked_sum=lambda x, mask: (x * mask).sum())})
    local = extract(local_path, ['bucket_reverse_kl'], dict(common))
    results = []
    for seed in range(4):
        for scale in [1., 3., 10.]:
            for k in [20, 100]:
                torch.manual_seed(seed)
                student = (torch.randn(1, 7, 257) * scale).requires_grad_()
                teacher = torch.randn(1, 7, 257) * scale
                p = student.log_softmax(-1)
                q = teacher.log_softmax(-1)
                ids = p.detach().topk(k, dim=-1).indices
                cfg = SimpleNamespace(full_logit_distillation=True, distillation_topk=k,
                    distillation_add_tail=True, alpha=1., is_clip=None)
                expected, _ = official['compute_self_distillation_loss'](
                    p[..., 0], q[..., 0], torch.ones(1, 7), cfg,
                    student_topk_log_probs=p.gather(-1, ids),
                    teacher_topk_log_probs=q.gather(-1, ids))
                actual = local['bucket_reverse_kl'](student, teacher, k=k).mean()
                g1, = torch.autograd.grad(expected, student, retain_graph=True)
                g2, = torch.autograd.grad(actual, student)
                results.append({'seed': seed, 'scale': scale, 'k': k,
                    'official_loss': expected.item(), 'local_loss': actual.item(),
                    'loss_abs_diff': (actual - expected).abs().item(),
                    'gradient_max_abs_diff': (g1 - g2).abs().max().item(),
                    'finite': bool(torch.isfinite(g1).all() and torch.isfinite(g2).all()),
                    'student_min_exact_tail_mass': p.exp().masked_fill(
                        torch.zeros_like(p, dtype=torch.bool).scatter_(-1, ids, True), 0).sum(-1).min().item()})
    out = {'official_commit': '7c457fc1b1f636ae794eb0362ba37d4743b06fbc',
        'official_source_sha256': hashlib.sha256(official_path.read_bytes()).hexdigest(),
        'local_source_sha256': hashlib.sha256(local_path.read_bytes()).hexdigest(),
        'device': 'cpu', 'model_forward_calls': 0, 'optimizer_updates': 0,
        'matched_settings': 'reverse KL, same student top-k, tail, no importance correction, one response token mean',
        'caveat': 'Official tail clamps log mass at -1e-7; local sums omitted logits exactly. Sharp synthetic distributions can therefore differ.',
        'cases': results}
    (A / 'loss_comparison.json').write_text(json.dumps(out, indent=2) + '\n')
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/models/Qwen3-8B', local_files_only=True)
    audits = []
    for sid in ['R1_b025_29caf6f_3_s01', 'R6_b014_60d0b5b_1_s17', 'R6_b018_aa8502b_1_s05']:
        source = D / 'probabilities' / (sid + '.json')
        p = json.loads(source.read_text())
        signals = p['signals']['historical_B_loss']
        indices = sorted({i for span in p['spans'] if span['kind'] == 'whole_code' for i in span['positions']})
        rows = []
        for i in indices:
            rows.append({'position': i, 'token': tok.decode([p['old_response_ids'][i]]),
                'historical_student_p': math.exp(p['conditions']['historical_student_C0']['original_token_logprobs'][i]),
                'historical_teacher_C2_q': math.exp(p['conditions']['historical_teacher_C2']['original_token_logprobs'][i]),
                'local_logprob_descent_derivative': signals['original_token_logprob_descent_derivative'][i],
                'KL': signals['reverse_KL_top100_tail'][i]})
        audits.append({'state_id': sid, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'code_tokens': rows,
            'code_sum_local_logprob_descent_derivative': sum(x['local_logprob_descent_derivative'] for x in rows),
            'answer_sum_local_logprob_descent_derivative': sum(signals['original_token_logprob_descent_derivative']),
            'code_log_teacher_over_student': sum(signals['original_token_logprob_delta'][i] for i in indices),
            'caveat': 'These are independent per-position logit-space derivatives, without token/branch normalization. Not a shared-parameter optimizer update or proof of final action-frequency change.'})
    (A / 'complete_code_prefix_audit.json').write_text(json.dumps(audits, ensure_ascii=False, indent=2) + '\n')
    for scale in [1., 3., 10.]:
        subset = [x for x in results if x['scale'] == scale]
        print(json.dumps({'scale': scale, 'cases': len(subset),
            'max_loss_abs_diff': max(x['loss_abs_diff'] for x in subset),
            'max_gradient_abs_diff': max(x['gradient_max_abs_diff'] for x in subset),
            'all_finite': all(x['finite'] for x in subset)}))
    print('Full-code audit states:', len(audits))


if __name__ == '__main__':
    main()
