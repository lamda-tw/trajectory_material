"""CPU tests only. Compare the original and prefix-tree loss and LoRA gradients."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import torch
from transformers import Qwen3Config, Qwen3ForCausalLM
from peft import LoraConfig, get_peft_model
from joint_core import action_logprobs, terms
from common import dump, now
from tree_core import build_layout, bounded_layouts, tree_logprobs


def tiny(checkpointing):
    torch.manual_seed(410)
    cfg = Qwen3Config(vocab_size=97, hidden_size=32, intermediate_size=48,
                     num_hidden_layers=2, num_attention_heads=4,
                     num_key_value_heads=2, head_dim=8, attention_dropout=0.0)
    cfg._attn_implementation = 'sdpa'
    model = get_peft_model(Qwen3ForCausalLM(cfg), LoraConfig(
        r=2, lora_alpha=4, lora_dropout=0., task_type='CAUSAL_LM',
        target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj']))
    # Nonzero B tests gradients of both LoRA factors, unlike a freshly initialized adapter.
    with torch.no_grad():
        for name, p in model.named_parameters():
            if 'lora_B' in name:
                p.normal_(0, .02)
    if checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.enable_input_require_grads()
    model.train()
    return model


def objective(lps, reference):
    # Variable token counts, clipped and unclipped PG, nonzero k3, and unequal SFT lengths.
    total = sum(len(x) for x in lps)
    loss = torch.zeros(())
    for i, (lp, ref) in enumerate(zip(lps, reference)):
        old = ref + ([.03, -.35, .28][i % 3])
        pg, kl, _ = terms(lp, old, ref-.04, [1.2, -1.3, 0.][i % 3])
        loss = loss + (pg.sum() + .01*kl.sum()) / (2*total)
    for i in [0, len(lps)-1]:
        loss = loss + .1*(-lps[i].mean())/2
    return loss


def check(actions, checkpointing, label):
    original = tiny(checkpointing); shared = copy.deepcopy(original)
    layout = build_layout(actions)
    # Reconstruct every original prefix and every target, including duplicated
    # targets on a shared query and branches that diverge before an action.
    for (prompt, target), queries, actual_target in zip(actions, layout.queries, layout.targets):
        assert target == actual_target
        for j, node in enumerate(queries):
            path = []
            while node != -1:
                path.append(layout.tokens[node]); node = layout.parents[node]
            assert list(reversed(path)) == prompt + target[:j]
    baseline = [action_logprobs(original, p, r, 2) for p, r in actions]
    reference = [x.detach().clone() for x in baseline]
    expected = objective(baseline, reference); expected.backward()
    fused = tree_logprobs(shared, layout, 2)
    actual = objective(fused, reference); actual.backward()
    logp_error = max(float((a-b).detach().abs().max()) for a,b in zip(baseline,fused))
    gradients_original = dict(original.named_parameters())
    grads_a, grads_b = [], []
    for name, p in shared.named_parameters():
        if p.requires_grad:
            q = gradients_original[name]
            assert p.grad is not None and q.grad is not None
            grads_a.append(q.grad.flatten()); grads_b.append(p.grad.flatten())
        else:
            assert p.grad is None
    ga, gb = torch.cat(grads_a), torch.cat(grads_b)
    relative = float((ga-gb).norm()/ga.norm())
    error = float((ga-gb).abs().max())
    assert logp_error < 2e-6, logp_error
    assert abs(actual.item()-expected.item()) < 2e-6
    assert relative < 2e-5, relative
    assert error < 2e-6, error
    # A full optimizer update should also agree.
    oa = torch.optim.AdamW([p for p in original.parameters() if p.requires_grad], lr=5e-6)
    ob = torch.optim.AdamW([p for p in shared.parameters() if p.requires_grad], lr=5e-6)
    oa.step(); ob.step()
    delta = max(float((p-dict(original.named_parameters())[n]).detach().abs().max())
                for n,p in shared.named_parameters() if p.requires_grad)
    assert delta < 2e-7, delta
    return dict(case=label, checkpointing=checkpointing, logprob_max_abs_error=logp_error,
                loss_abs_error=abs(actual.item()-expected.item()), gradient_max_abs_error=error,
                gradient_relative_l2_error=relative, optimizer_parameter_max_abs_error=delta,
                original_input_positions=sum(len(p)+len(r)-1 for p,r in actions),
                shared_input_positions=len(layout.tokens), chains=len(layout.chains))


def main():
    torch.set_num_threads(2)
    # Steps diverge at the current-assistant wrapper, matching the real dataset's
    # non-prefix behavior. Additional cases test EOS, duplicates and separate roots.
    cases = {
        'wrapper_divergence': [([1,2,3,40,41],[7,8,2]),
                              ([1,2,3,7,8,2,9,40,41],[10,11,12,2]),
                              ([1,2,3,7,8,2,9,10,11,12,2,13,40,41],[14,2])],
        'duplicate_and_different_targets': [([1,2,3],[4,5,2]),([1,2,3],[4,5,2]),
                                            ([1,2,3],[6]),([1,2,3,4,5,2],[7,2])],
        'separate_roots_and_short_targets': [([1],[2]),([3,4],[5]),([1,2,3],[4,5,2])],
    }
    results = [check(actions, cp, name) for name,actions in cases.items() for cp in [False,True]]
    groups=bounded_layouts(cases['wrapper_divergence'],23)
    assert len(groups)>1 and all(len(g.tokens)<=23 for g in groups)
    assert [r for g in groups for r in g.targets] == [r for p,r in cases['wrapper_divergence']]
    assert not torch.cuda.is_initialized()
    report = dict(at=now(), status='passed', scope='CPU float32 tiny Qwen3 with all seven LoRA projections; not a full-model BF16 or GPU speed test',
                  cases=results, cuda_initialized=False)
    dump(ROOT/'checks/prefix_sharing_equivalence.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
