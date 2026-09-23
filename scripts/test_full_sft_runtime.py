"""Numerical regression tests; tiny CPU model, no production training data."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import torch
import torch.distributed as dist
from transformers import Qwen3Config, Qwen3ForCausalLM
from full_sft_runtime import completion_loss, save_restart, load_restart


def tiny_model():
    torch.manual_seed(417)
    config = Qwen3Config(vocab_size=61, hidden_size=32, intermediate_size=48,
                        num_hidden_layers=2, num_attention_heads=4,
                        num_key_value_heads=2, head_dim=8,
                        max_position_embeddings=128, attention_dropout=0,
                        use_cache=False)
    return Qwen3ForCausalLM(config).float()


def batch(target_count=4, padding=3):
    ids = torch.tensor([[2, 9, 13, 21, 6, 35, 8, 3, 11, 4, 1]])
    labels = ids.clone()
    labels[:, :ids.shape[1] - target_count] = -100
    return {'input_ids': torch.nn.functional.pad(ids, (0, padding), value=0),
            'attention_mask': torch.nn.functional.pad(torch.ones_like(ids), (0, padding)),
            'labels': torch.nn.functional.pad(labels, (0, padding), value=-100)}


class RuntimeTests(unittest.TestCase):
    def test_sparse_loss_and_every_parameter_gradient_match(self):
        for count, padding in [(1, 0), (4, 3), (8, 5)]:
            reference = tiny_model()
            selected = copy.deepcopy(reference)
            b = batch(count, padding)
            full_loss = reference(**b).loss
            short_loss = completion_loss(selected, b)
            torch.testing.assert_close(short_loss, full_loss, rtol=2e-6, atol=2e-7)
            full_loss.backward()
            short_loss.backward()
            for (name, p), (_, q) in zip(reference.named_parameters(), selected.named_parameters()):
                self.assertIsNotNone(p.grad, name)
                self.assertIsNotNone(q.grad, name)
                torch.testing.assert_close(q.grad, p.grad, rtol=5e-5, atol=2e-6, msg=name)

    def test_omit_right_padding_preserves_loss_and_gradients(self):
        padded = tiny_model()
        unpadded = copy.deepcopy(padded)
        a = completion_loss(padded, batch(4, 3))
        b = completion_loss(unpadded, batch(4, 0))
        torch.testing.assert_close(a, b, rtol=2e-6, atol=2e-7)
        a.backward(); b.backward()
        for (name, p), (_, q) in zip(padded.named_parameters(), unpadded.named_parameters()):
            torch.testing.assert_close(p.grad, q.grad, rtol=5e-5, atol=2e-6, msg=name)

    def test_reject_invalid_supervision(self):
        b = batch()
        b['labels'].fill_(-100)
        with self.assertRaises(ValueError): completion_loss(tiny_model(), b)
        b = {key: value.repeat(2, 1) for key, value in batch().items()}
        with self.assertRaises(ValueError): completion_loss(tiny_model(), b)

    def test_restart_preserves_next_update_and_scheduler(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'], prefix='restart-test-') as tmp:
            dist.init_process_group('gloo', init_method=f'file://{tmp}/rendezvous', rank=0, world_size=1)
            try:
                model = tiny_model()
                opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
                sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda step: 1/(step+1))
                def update(m, o, s):
                    o.zero_grad(set_to_none=True)
                    loss = completion_loss(m, batch())
                    loss.backward(); o.step(); s.step(); o.zero_grad(set_to_none=True)
                    return loss.detach()
                update(model, opt, sched)
                update(model, opt, sched)
                contract = {'test': 'same-topology-v1'}
                progress = {'global_step': 2, 'epoch_index': 0, 'consumed_batches': 2, 'elapsed_seconds': 0}
                save_restart(model, opt, sched, Path(tmp)/'checkpoints', progress, contract, reserve_gib=0)
                expected_loss = update(model, opt, sched)
                resumed = tiny_model()
                opt2 = torch.optim.AdamW(resumed.parameters(), lr=1e-3)
                sched2 = torch.optim.lr_scheduler.LambdaLR(opt2, lambda step: 1/(step+1))
                restored = load_restart(resumed, opt2, sched2, Path(tmp)/'checkpoints', contract)
                self.assertEqual(restored, progress)
                actual_loss = update(resumed, opt2, sched2)
                torch.testing.assert_close(actual_loss, expected_loss, rtol=0, atol=0)
                for a, b in zip(model.parameters(), resumed.parameters()):
                    torch.testing.assert_close(a, b, rtol=0, atol=0)
                self.assertEqual(sched.state_dict(), sched2.state_dict())
                progress['global_step'] = 3
                save_restart(resumed, opt2, sched2, Path(tmp)/'checkpoints', progress, contract, reserve_gib=0)
                self.assertFalse((Path(tmp)/'checkpoints/step_000002').exists())
                with self.assertRaises(ValueError):
                    load_restart(resumed, opt2, sched2, Path(tmp)/'checkpoints', {'test':'mismatch'})
            finally:
                dist.destroy_process_group()


if __name__ == '__main__':
    torch.set_num_threads(2)
    unittest.main(verbosity=2)
