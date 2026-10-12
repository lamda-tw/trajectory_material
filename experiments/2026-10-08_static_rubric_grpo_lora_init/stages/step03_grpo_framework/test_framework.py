"""Behavioral checks: official reward equivalence, action masking, frozen reference."""
import ast
import copy
import itertools
import json
import random
import tempfile
import unittest
from pathlib import Path
import pipeline as p
from train import action_logprobs, adapter_digest, grpo_terms


class RewardTests(unittest.TestCase):
    def test_matches_official_source(self):
        tree = ast.parse((p.ROOT / 'assets/draco/rubric_reward.py.txt').read_text())
        names = {'_non_discriminative_indices', '_reward_from_scores'}
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        namespace = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<official DRACO>', 'exec'), namespace)
        rng = random.Random(20261009)
        # Explicit all-PASS, all-FAIL, all-NA and mixed columns, plus random matrices.
        matrices = [[[x] * 21 for x in column] for column in itertools.product([-1, 0, 1], repeat=6)]
        matrices += [[[rng.choice([-1, 0, 1]) for _ in range(21)] for _ in range(6)] for _ in range(100)]
        for matrix in matrices:
            members = [(str(i), []) for i in range(6)]
            scores = {str(i): [{'score': x} for x in row] for i, row in enumerate(matrix)}
            dropped = namespace['_non_discriminative_indices'](members, scores, 21)
            expected = [namespace['_reward_from_scores'](scores[str(i)], 10, dropped)['rubric_reward'] for i in range(6)]
            actual = p.rubric_rewards([[{-1: 'FAIL', 0: 'NA', 1: 'PASS'}[x] for x in row] for row in matrix])
            self.assertEqual(actual['kept_rule_ids'], [i for i in range(21) if i not in dropped])
            for a, b in zip(actual['rewards'], expected):
                self.assertAlmostEqual(a, b, places=12)

    def test_invalid_missing_and_constant(self):
        with self.assertRaises(ValueError):
            p.rubric_rewards([['PASS'], []])
        with self.assertRaises(ValueError):
            p.rubric_rewards([['UNKNOWN']])
        self.assertEqual(p.group_advantages([3] * 6), [0] * 6)
        self.assertEqual(p.tasks_for(1), ['afc0fce_1'])



class TransportTests(unittest.TestCase):
    def test_recovered_turn_only(self):
        events = [{'type': 'turn.started'},
                  {'type': 'error', 'message': 'Reconnecting... 2/5 (workspace routing discovery timed out)'},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{}'}},
                  {'type': 'turn.completed', 'usage': {}}]
        result = p.judge.audit_events('\n'.join(json.dumps(e) for e in events))
        self.assertEqual(len(result['accepted_transport_diagnostics']), 1)
        for bad in [events[:-1],
                    events[:-1] + [{'type': 'turn.failed'}],
                    events + [{'type': 'error', 'message': 'Reconnecting... 2/5 (request timed out)'}],
                    [events[0], {'type': 'item.completed', 'item': {'type': 'command_execution'}}, events[-1]],
                    [events[0], {'type': 'error', 'message': 'Unauthorized'}, events[-1]]]:
            with self.assertRaises(ValueError):
                p.judge.audit_events('\n'.join(json.dumps(e) for e in bad))


class BatchTests(unittest.TestCase):
    def test_complete_groups_and_stale_policy_rejected(self):
        jobs = p.initial_jobs(p.tasks_for(1))
        # Outcome branch exercises input validation independently of remote scores.
        batch = p.build_batch(jobs, Path('/tmp'), 'outcome', 1)
        self.assertEqual(len(batch['episodes']), 6)
        for changed in [jobs[:-1], [jobs[0]] * 6]:
            with self.assertRaises(ValueError):
                p.build_batch(changed, Path('/tmp'), 'outcome', 1)
        altered = copy.deepcopy(jobs)
        altered[0]['policy_id'] = 'stale-policy'
        with self.assertRaises(ValueError):
            p.build_batch(altered, Path('/tmp'), 'outcome', 1)
        altered = copy.deepcopy(jobs)
        altered[0]['mode'] = 'dev'
        with self.assertRaises(ValueError):
            p.build_batch(altered, Path('/tmp'), 'outcome', 1)


class GradientTests(unittest.TestCase):
    def test_action_mask_reference_and_reload(self):
        import torch
        import torch.nn.functional as F
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from peft import LoraConfig, PeftModel, get_peft_model
        torch.manual_seed(42)
        torch.set_num_threads(2)
        config = Qwen3Config(vocab_size=48, hidden_size=32, intermediate_size=48,
                            num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                            head_dim=8, attention_dropout=0.0)
        base = Qwen3ForCausalLM(config)
        clean_base = copy.deepcopy(base)
        model = get_peft_model(base, LoraConfig(r=2, lora_alpha=4, lora_dropout=0,
                                               target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
        reference = copy.deepcopy(model).eval().requires_grad_(False)
        model.train()
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
        model.enable_input_require_grads()
        prompt, response = [1, 2, 3, 4], [5, 6, 7]
        with torch.no_grad():
            full = reference(torch.tensor([prompt + response])).logits[0, len(prompt)-1:-1].float()
            expected = -F.cross_entropy(full, torch.tensor(response), reduction='none')
            old = action_logprobs(reference, prompt, response, 2)
        self.assertTrue(torch.allclose(old, expected, atol=1e-6))
        before_ref, before_policy = adapter_digest(reference), adapter_digest(model)
        params = [v for v in model.parameters() if v.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=0.01)
        new = action_logprobs(model, prompt, response, 2)
        loss, ratio, kl = grpo_terms(new, old, old, 1.2, 0.2, 0.01)
        loss.mean().backward()
        self.assertEqual(new.numel(), len(response))
        self.assertTrue(torch.allclose(ratio, torch.ones_like(ratio), atol=1e-6))
        self.assertLess(kl.abs().max().item(), 1e-6)
        self.assertTrue(any(v.grad is not None and v.grad.abs().sum() > 0 for v in params))
        optimizer.step()
        self.assertNotEqual(adapter_digest(model), before_policy)
        self.assertEqual(adapter_digest(reference), before_ref)
        self.assertTrue(all(v.grad is None for v in reference.parameters()))
        self.assertTrue(all(v.grad is None for n, v in model.named_parameters() if 'lora_' not in n))
        with tempfile.TemporaryDirectory() as directory:
            model.save_pretrained(directory)
            loaded = PeftModel.from_pretrained(clean_base, directory).eval()
            model.eval()
            with torch.no_grad():
                a = action_logprobs(model, prompt, response, 2)
                b = action_logprobs(loaded, prompt, response, 2)
            self.assertTrue(torch.allclose(a, b, atol=1e-6))

    def test_clip_both_advantage_signs(self):
        import torch
        new = torch.tensor([0.0, 0.0], requires_grad=True)
        old = torch.tensor([-0.69314718, 0.69314718])
        for advantage, expected in [(1.0, [-1.2, -0.5]), (-1.0, [2.0, 0.8])]:
            loss, _, _ = grpo_terms(new, old, new.detach(), advantage, 0.2, 0)
            self.assertTrue(torch.allclose(loss, torch.tensor(expected), atol=1e-6))


if __name__ == '__main__':
    unittest.main(verbosity=2)
