"""Small CPU-only numerical tests for fixed-data epochs and gradient recovery."""
import copy
from contextlib import ExitStack
import io
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import torch
from offline_state import check_logprobs, restore_gradients, save_gradients
import pipeline as p
import run
import train


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_later_policy_drift_does_not_replace_behavior(self):
        old = torch.tensor([-3.0, -2.0])
        original = old.clone()
        current = torch.tensor([-2.5, -2.5], requires_grad=True)
        with self.assertRaises(RuntimeError):
            check_logprobs(1, current, old, old, .1)
        for epoch in range(2, 6):
            current_error, ref_error = check_logprobs(epoch, current, old, old, .1)
            self.assertEqual(current_error, .5)
            self.assertEqual(ref_error, 0)
            _, ratio, _ = train.grpo_terms(current, old, old, 1, .2, .01)
            self.assertTrue(torch.allclose(ratio, torch.exp(current - original)))
        self.assertTrue(torch.equal(old, original))
        with self.assertRaises(RuntimeError):
            check_logprobs(5, current, old, old + .5, .1)

    def test_five_epochs_keep_optimizer_and_reference(self):
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from peft import LoraConfig, get_peft_model
        torch.manual_seed(7)
        config = Qwen3Config(vocab_size=32, hidden_size=16, intermediate_size=24,
                            num_hidden_layers=1, num_attention_heads=2,
                            num_key_value_heads=1, head_dim=8, attention_dropout=0.)
        model = get_peft_model(Qwen3ForCausalLM(config), LoraConfig(
            r=2, lora_alpha=4, lora_dropout=0, target_modules=['q_proj', 'v_proj'],
            task_type='CAUSAL_LM'))
        reference = copy.deepcopy(model).eval().requires_grad_(False)
        original_ref = train.adapter_digest(reference)
        prompt, response = [1, 2, 3], [4, 5]
        with torch.no_grad():
            old = train.action_logprobs(reference, prompt, response, 2)
        saved_old = old.clone()
        params = [v for v in model.parameters() if v.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=.003)
        original = train.adapter_digest(model)
        for epoch in range(1, 6):
            optimizer.zero_grad(set_to_none=True)
            current = train.action_logprobs(model, prompt, response, 2)
            check_logprobs(epoch, current, old, saved_old, .1)
            losses, ratio, _ = train.grpo_terms(current, old, saved_old, 1.2, .2, .01)
            losses.mean().backward()
            optimizer.step()
            self.assertTrue(torch.equal(old, saved_old))
            self.assertTrue(all(float(s['step']) == epoch for s in optimizer.state.values()))
            self.assertEqual(train.adapter_digest(reference), original_ref)
        self.assertNotEqual(train.adapter_digest(model), original)
        self.assertTrue(all(x.grad is None for x in reference.parameters()))

    def test_gradient_resume_matches_uninterrupted_update(self):
        torch.manual_seed(2)
        model = torch.nn.Linear(2, 1)
        initial = copy.deepcopy(model.state_dict())
        xs = [torch.tensor([[1., 2.]]), torch.tensor([[2., -1.]]), torch.tensor([[.3, .5]])]
        signature = {'batch': 'fixed', 'epoch': 2, 'parent': 'epoch1'}
        for x in xs[:2]:
            model(x).square().sum().backward()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'gradients.pt'
            save_gradients(path, model, signature, 2, {'loss': 1.}, 3.)
            resumed = torch.nn.Linear(2, 1)
            resumed.load_state_dict(initial)
            state = restore_gradients(path, resumed, signature, 3, 1)
            self.assertEqual(state['completed_episodes'], 2)
            for candidate in (model, resumed):
                candidate(xs[2]).square().sum().backward()
                optimizer = torch.optim.AdamW(candidate.parameters(), lr=.01)
                optimizer.step()
            for a, b in zip(model.parameters(), resumed.parameters()):
                self.assertTrue(torch.equal(a, b))
            with self.assertRaises(ValueError):
                restore_gradients(path, resumed, {**signature, 'epoch': 3}, 3, 1)

    def test_reference_cache_is_reused_and_validated(self):
        episode = {'task_id': 'synthetic', 'sample': 0, 'trajectory_sha256': 'original'}
        trajectory = {'steps': [{'prompt_ids': [1], 'response_ids': [2, 3]}]}
        signature = {'framework': 'stage', 'reference': 'initial-sft', 'epoch': 1}
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'RUN', Path(tmp)):
            progress = Path(tmp) / 'progress.json'
            with patch.object(train, 'action_logprobs', return_value=torch.tensor([-1., -2.])) as call:
                a = train.reference_values(None, episode, trajectory, {'head_chunk_size': 2}, signature, progress)
                b = train.reference_values(None, episode, trajectory, {'head_chunk_size': 2},
                                           {**signature, 'epoch': 5}, progress)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(a, b)
            with self.assertRaises(ValueError):
                train.reference_values(None, {**episode, 'trajectory_sha256': 'changed'}, trajectory,
                                       {'head_chunk_size': 2}, signature, progress)

    def test_gpu_hold_blocks_both_entrypoints(self):
        with patch('sys.stderr', new_callable=io.StringIO):
            for module, argv in [(run, ['run.py', 'train', '--execute']),
                                 (train, ['train.py', '--batch', '/tmp/x', '--output', '/tmp/y',
                                          '--epoch', '1', '--execute'])]:
                with patch.object(sys, 'argv', argv), self.assertRaises(SystemExit) as raised:
                    module.main()
                self.assertEqual(raised.exception.code, 2)

    def test_actual_epoch_entrypoint_checkpoint_continuation_on_cpu(self):
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from peft import LoraConfig, PeftModel, get_peft_model
        torch.manual_seed(23)
        config = Qwen3Config(vocab_size=24, hidden_size=16, intermediate_size=24,
                            num_hidden_layers=1, num_attention_heads=2,
                            num_key_value_heads=1, head_dim=8, attention_dropout=0.)
        clean_base = Qwen3ForCausalLM(config)
        initial = get_peft_model(copy.deepcopy(clean_base), LoraConfig(
            r=2, lora_alpha=4, lora_dropout=0, target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
        prompt, response = [1, 2, 3], [4, 5]
        with torch.no_grad():
            old = train.action_logprobs(initial, prompt, response, 2).tolist()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            initial.save_pretrained(root / 'initial')
            settings = copy.deepcopy(p.settings())
            settings['execution_gpu'] = ''
            settings['training']['learning_rate'] = .001
            settings['training']['head_chunk_size'] = 2
            trajectory = root / 'trajectory.json'
            p.atomic_json(trajectory, {'steps': [{'prompt_ids': prompt, 'response_ids': response, 'old_logprobs': old}]})
            batch = {'policy_id': 'initial', 'reference_policy_id': 'initial',
                     'training': settings['training'], 'episodes': [
                         {'task_id': 'cpu', 'sample': i, 'trajectory': str(trajectory),
                          'trajectory_sha256': p.file_sha(trajectory), 'token_count': 2,
                          'advantage': 1. if i < 4 else -1.} for i in range(6)]}
            batch_path = root / 'batch.json'
            p.atomic_json(batch_path, batch)
            def policy_info(branch, epoch):
                path = root / 'initial' if epoch == 0 else p.checkpoint_path(branch, epoch)
                return {'path': str(path), **({'policy_id': 'initial'} if epoch == 0 else p.read_json(path / 'manifest.json'))}
            def cpu_models(cfg, parent):
                policy = PeftModel.from_pretrained(copy.deepcopy(clean_base), parent, is_trainable=True).train()
                reference = PeftModel.from_pretrained(copy.deepcopy(clean_base), root / 'initial').eval().requires_grad_(False)
                return policy, reference
            for obj, name, replacement in [
                (p, 'RUN', root), (p, 'settings', lambda: settings),
                (p, 'load_config', lambda: {'training': {'seed': 23, 'minimum_free_gpu_gib': 80}}),
                (p, 'validate_batch', lambda path: batch), (p, 'identity', lambda: 'cpu-test'),
                (p, 'policy_info', policy_info), (train, 'load_models', cpu_models),
            ]:
                stack.enter_context(patch.object(obj, name, replacement))
            stack.enter_context(patch('resources.require_free_gpu', return_value={}))
            stack.enter_context(patch('torch.cuda.manual_seed_all'))
            stack.enter_context(patch('torch.cuda.max_memory_allocated', return_value=0))
            stack.enter_context(patch('sys.stdout', new_callable=io.StringIO))
            parent_id = 'initial'
            for epoch in range(1, 6):
                checkpoint = p.checkpoint_path('rubric', epoch)
                with patch.object(sys, 'argv', ['train.py', '--batch', str(batch_path),
                        '--output', str(checkpoint), '--epoch', str(epoch), '--execute', '--allow-gpu']):
                    train.main()
                info = p.read_json(checkpoint / 'manifest.json')
                self.assertEqual(info['parent_policy_id'], parent_id)
                self.assertEqual(info['behavior_policy_id'], 'initial')
                self.assertEqual(info['batch_sha256'], p.file_sha(batch_path))
                self.assertEqual(info['metrics']['optimizer_steps_this_epoch'], 1)
                state = torch.load(checkpoint / 'optimizer.pt', weights_only=False)
                self.assertEqual(state['completed_epochs'], epoch)
                self.assertTrue(all(float(v['step']) == epoch for v in state['optimizer']['state'].values()))
                self.assertFalse((checkpoint.parent / 'accumulated_gradients.pt').exists())
                parent_id = info['policy_id']

    def test_runner_passes_same_batch_through_five_epochs(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(p, 'RUN', Path(tmp)))
            stack.enter_context(patch.object(p, 'validate_batch', return_value={}))
            stack.enter_context(patch.object(p, 'policy_info', return_value={'metrics': {}}))
            calls = stack.enter_context(patch.object(run.subprocess, 'run'))
            stack.enter_context(patch('sys.stdout', new_callable=io.StringIO))
            batch = Path(tmp) / 'fixed_batch.json'
            run.train_five_epochs(batch)
            self.assertEqual(calls.call_count, 5)
            for epoch, call in enumerate(calls.call_args_list, 1):
                command = call.args[0]
                self.assertEqual(command[command.index('--batch') + 1], str(batch))
                self.assertEqual(command[command.index('--epoch') + 1], str(epoch))
            self.assertEqual(p.read_json(Path(tmp) / 'status.json')['optimizer_steps'], 5)


if __name__ == '__main__':
    with patch('torch.cuda.is_available', return_value=False):
        unittest.main(verbosity=2)
