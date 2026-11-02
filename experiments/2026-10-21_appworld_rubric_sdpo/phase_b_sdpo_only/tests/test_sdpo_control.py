"""Control isolation, zero-SFT routing, and first-batch matching checks."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import b_common as c
import b_supervise as supervisor
from b_dataset import route


class ControlTests(unittest.TestCase):
    def test_config_only_expected_changes(self):
        old = c.read(c.R / 'phase_b/config/run.json'); new = c.config()
        for key in ['training', 'agent', 'sampling', 'paths']:
            self.assertEqual(old[key], new[key])
        for name in ['schedule.json', 'train90.txt', 'dev57.txt', 'judge.json']:
            self.assertEqual(c.file_sha(c.R / 'phase_b/config' / name), c.file_sha(c.B / 'config' / name))
        self.assertEqual(c.file_sha(c.S / 'b_loss.py'), c.file_sha(c.R / 'scripts/b_loss.py'))
        self.assertNotEqual(c.run_dir('sdpo'), c.R / 'phase_b/runs/mixed')

    def test_all_zero_fail_examples_masked_and_FAIL_route_unchanged(self):
        cfg = c.config()
        for labels in ['PPPNNNNU', 'PPPPPPPP', 'PPNNNNNN', 'NNNNNNNN']:
            self.assertEqual(route(labels, None, 0, 100, 0, cfg, 'sdpo')[0], 'mask')
        for labels, feedback, n, teacher_n in [
            ('PPPFNNNN', {'usable': True}, 80, 200), ('FNNNNNNN', {'usable': False}, 0, 200),
            ('FNNNNNNN', {'usable': True}, 257, 200), ('FNNNNNNN', {'usable': True}, 80, 32769)]:
            self.assertEqual(route(labels, feedback, n, 100, teacher_n, cfg, 'sdpo'),
                             route(labels, feedback, n, 100, teacher_n, cfg, 'mixed'))

    def test_first_batch_only_cached_and_same_initial_identity(self):
        old = c.read(c.R / 'phase_b/runs/mixed/batch_001/collection.json')
        new = c.read(c.batch_dir('sdpo', 1) / 'collection.json')
        self.assertEqual(old['trajectories'], new['trajectories'])
        self.assertEqual(old['schedule'], new['schedule'])
        self.assertEqual(new['policy_identity'], c.policy_identity(None))
        self.assertFalse(c.batch_dir('sdpo', 2).exists())

    def test_acceptance_rejects_SFT_leakage_and_mismatched_SDPO(self):
        original = c.read(c.R / 'phase_b/runs/mixed/batch_001/checkpoint/metrics.json')
        good = copy.deepcopy(original)
        good.update(sft_loss=0., sft_grad_norm=0., counts={'sdpo': original['counts']['sdpo']})
        good['total_loss'] = good['sdpo_loss']
        def validate(m):
            def read(path):
                if path.name == 'COMPLETE.json': return {'files': {}}
                if 'runs/mixed' in str(path): return original
                return m
            with patch.object(supervisor, 'read', side_effect=read), patch.object(supervisor, 'file_sha', return_value='test'), patch.object(supervisor, 'write_json'):
                return supervisor.validate_checkpoint(1)
        self.assertGreater(validate(good)['sdpo_loss'], 0)
        for change in [{'sft_loss': .1}, {'sft_grad_norm': .1}, {'counts': {'sft': 1, 'sdpo': 1}},
                       {'sdpo_loss': good['sdpo_loss'] + .01}, {'weighted_sdpo_grad_norm': 0.}, {'teacher_received_gradient': True}]:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                validate(dict(good, **change))


if __name__ == '__main__':
    unittest.main()
