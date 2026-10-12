"""CPU numerical checks for exact global normalization, recovery, and one shared update."""
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'
import copy
from contextlib import ExitStack
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import torch
import two_gpu as q
import worker
import finalize


class ParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_partition_covers_whole_groups_once(self):
        costs = [100, 3, 7, 29, 2, 40, 1, 5, 16, 8]
        groups, loads = q.partition(costs)
        self.assertEqual([len(x) for x in groups], [5, 5])
        shards = [[i for g in part for i in range(g * 6, g * 6 + 6)] for part in groups]
        q.check_partition(shards, 60)
        self.assertEqual(sum(loads), sum(costs))
        self.assertEqual((groups, loads), q.partition(costs))
        with self.assertRaises(ValueError):
            q.check_partition([shards[0], shards[0]], 60)

    def test_unequal_shards_match_serial_grpo_gradient_and_update(self):
        torch.manual_seed(9)
        serial = torch.nn.Linear(3, 4).double()
        initial = copy.deepcopy(serial)
        examples = [torch.randn(length, 3, dtype=torch.float64) for length in (2, 5, 1, 3, 4)]
        advantages = [1.2, -.3, 0., -2., .8]
        def accumulate(model, indices):
            for i in indices:
                x = examples[i]
                new = model(x).log_softmax(-1)[:, i % 4]
                with torch.no_grad():
                    old = initial(x).log_softmax(-1)[:, i % 4] + .3
                    ref = old - .1
                losses, _, _ = q.core.grpo_terms(new, old, ref, advantages[i], .2, .01)
                (losses.sum() / (len(examples) * len(x))).backward()
        accumulate(serial, range(5))
        states = []
        for indices in ([0], [1, 2, 3, 4]):
            model = copy.deepcopy(initial)
            accumulate(model, indices)
            states.append({'gradients': {n: v.grad.clone() for n, v in model.named_parameters()}})
        merged = copy.deepcopy(initial)
        finalize.merge_gradients(merged, states)
        for a, b in zip(serial.parameters(), merged.parameters()):
            torch.testing.assert_close(a.grad, b.grad, rtol=1e-12, atol=1e-12)
        for model in (serial, merged):
            torch.nn.utils.clip_grad_norm_(model.parameters(), .1)
            optimizer = torch.optim.AdamW(model.parameters(), lr=.005, weight_decay=0)
            optimizer.step()
            self.assertTrue(all(float(s['step']) == 1 for s in optimizer.state.values()))
        for a, b in zip(serial.parameters(), merged.parameters()):
            torch.testing.assert_close(a, b, rtol=1e-12, atol=1e-12)

    def test_invalid_or_missing_gradient_shard_is_rejected(self):
        model = torch.nn.Linear(2, 1)
        state = {'gradients': {n: torch.zeros_like(v) for n, v in model.named_parameters()}}
        with self.assertRaises(ValueError):
            finalize.merge_gradients(model, [state])
        bad = copy.deepcopy(state)
        bad['gradients']['weight'][0, 0] = float('nan')
        with self.assertRaises(ValueError):
            finalize.merge_gradients(model, [state, bad])

    def test_missing_completed_worker_cannot_load_gpu(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(q, 'RUN', Path(tmp)))
            stack.enter_context(patch.object(q, 'load_input', return_value=({}, {})))
            gpu = stack.enter_context(patch.object(q, 'configure_gpu'))
            with self.assertRaises(FileNotFoundError):
                finalize.execute()
            gpu.assert_not_called()

    def test_actual_workers_resume_and_commit_one_reloadable_adapter(self):
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from peft import LoraConfig, PeftModel, get_peft_model
        torch.manual_seed(31)
        cfg = Qwen3Config(vocab_size=24, hidden_size=16, intermediate_size=24,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=8, attention_dropout=0.)
        clean_base = Qwen3ForCausalLM(cfg)
        initial = get_peft_model(copy.deepcopy(clean_base), LoraConfig(r=2, lora_alpha=4,
            lora_dropout=0, target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            initial.save_pretrained(root / 'initial')
            train = copy.deepcopy(q.p.settings()['training'])
            train['head_chunk_size'] = 2
            train['learning_rate'] = .001
            episodes = []
            for i in range(24):
                prompt, response = [1, 2, 3], [4 + i % 6, 10]
                with torch.no_grad():
                    old = q.core.action_logprobs(initial, prompt, response, 2).tolist()
                path = root / f'episode_{i}.json'
                q.p.atomic_json(path, {'steps': [{'prompt_ids': prompt, 'response_ids': response, 'old_logprobs': old}]})
                episodes.append({'task_id': f'task{i // 6}', 'sample': i % 6, 'trajectory': str(path),
                    'trajectory_sha256': q.p.file_sha(path), 'token_count': 2,
                    'advantage': [-1., -.6, -.2, .2, .6, 1.][i % 6]})
            batch = {'episodes': episodes, 'training': train}
            manifest = {'execution_fingerprint': 'test', 'batch_sha256': 'batch',
                'source_framework_fingerprint': 'source', 'parent_policy_id': 'initial',
                'reference_policy_id': 'initial', 'assignments': [list(range(12)), list(range(12, 24))]}
            def models(cfg, parent):
                model = PeftModel.from_pretrained(copy.deepcopy(clean_base), root / 'initial', is_trainable=True).train()
                ref = PeftModel.from_pretrained(copy.deepcopy(clean_base), root / 'initial').eval().requires_grad_(False)
                return model, ref
            stack.enter_context(patch.object(q, 'RUN', root))
            stack.enter_context(patch.object(q, 'load_input', return_value=(batch, manifest)))
            stack.enter_context(patch.object(q, 'configure_gpu'))
            stack.enter_context(patch.object(q.core, 'load_models', side_effect=models))
            stack.enter_context(patch.object(q.p, 'policy_info', return_value={'path': str(root / 'initial')}))
            stack.enter_context(patch('torch.cuda.is_available', return_value=False))
            stack.enter_context(patch('torch.cuda.manual_seed_all'))
            stack.enter_context(patch('sys.stdout', new_callable=io.StringIO))
            original = worker.accumulate_episode
            calls = 0
            def interrupt_after_group(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 7:
                    raise RuntimeError('simulated interruption')
                return original(*args, **kwargs)
            with patch.object(worker, 'accumulate_episode', side_effect=interrupt_after_group):
                with self.assertRaisesRegex(RuntimeError, 'simulated interruption'):
                    worker.execute(0)
            saved = torch.load(root / 'worker_0/gradients.pt', weights_only=False)
            self.assertEqual(saved['completed_episodes'], 6)
            worker.execute(0)
            worker.execute(1)
            with patch.object(q.core, 'load_models') as loader:
                worker.execute(0)
                loader.assert_not_called()
            states = [torch.load(root / f'worker_{rank}/gradients.pt', weights_only=False) for rank in range(2)]
            serial, reference = models(None, None)
            metrics = dict(loss=0., kl=0., ratio_mean=0., clip_fraction=0., old_new_abs_logprob_mean=0.,
                           max_old_new_abs_logprob=0., max_step_mean_logprob_error=0.)
            for episode in episodes:
                original(serial, reference, episode, 24, train, metrics, lambda *_: None)
            merged, _ = models(None, None)
            finalize.merge_gradients(merged, states)
            for (name, a), (_, b) in zip(serial.named_parameters(), merged.named_parameters()):
                if a.requires_grad:
                    torch.testing.assert_close(a.grad, b.grad, rtol=2e-5, atol=1e-7, msg=name)
            info = finalize.execute()
            self.assertEqual(info['optimizer_steps'], 1)
            self.assertTrue(info['metrics']['policy_changed'])
            self.assertTrue(info['metrics']['reference_unchanged'])
            self.assertLessEqual(info['metrics']['reload_max_abs_logprob_error'], 1e-5)
            state = torch.load(root / 'checkpoint/optimizer.pt', weights_only=False)
            self.assertTrue(all(float(s['step']) == 1 for s in state['optimizer']['state'].values()))
            with patch.object(q.core, 'load_models') as loader:
                self.assertEqual(finalize.execute()['policy_id'], info['policy_id'])
                loader.assert_not_called()
            # A changed completed shard may never enter another update.
            with (root / 'worker_1/gradients.pt').open('ab') as file:
                file.write(b'changed')
            with self.assertRaises(ValueError):
                q.completed_worker(1, manifest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
