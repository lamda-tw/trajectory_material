"""Offline regression checks for branch isolation and real adapter routing."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import initial_policy
import policy_server
import step01_collect
from common import ROOT, group_advantages, ids, load_config, read_json, rubric_rewards
from judge import build_prompt, score
from initial_policy import DIRECTORY, rollout_jobs, validate_adapter, verify_raw_reference

class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()

    def test_same_540_task_seed_pairs_but_different_policy_and_outputs(self):
        c = self.config
        reference = verify_raw_reference(c)
        jobs = rollout_jobs(c, DIRECTORY, ids(ROOT / c['collection']['tasks']))
        self.assertEqual(len(jobs), 540)
        for old, new in zip(reference['jobs'], jobs):
            self.assertEqual([old[k] for k in ('task_id', 'sample', 'seed', 'update')],
                             [new[k] for k in ('task_id', 'sample', 'seed', 'update')])
            self.assertNotEqual(old['output'], new['output'])
            self.assertNotEqual(old['policy_id'], new['policy_id'])
            self.assertNotEqual(old['episode_id'], new['episode_id'])
            self.assertEqual(new['model'], c['server']['adapter_name'])

    def test_adapter_weights_and_all_layer_shapes(self):
        result = validate_adapter(self.config)
        self.assertEqual(result['tensors'], 504)
        self.assertEqual(result['parameters'], 21823488)

    def test_modified_adapter_cannot_silently_use_base(self):
        c = copy.deepcopy(self.config)
        c['initial_policy']['files']['adapter_model.safetensors'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_adapter(c)

    def test_changed_prompt_protocol_is_rejected(self):
        c = copy.deepcopy(self.config)
        c['agent']['max_model_len'] += 1
        with self.assertRaisesRegex(ValueError, 'Unpaired experimental protocol'):
            verify_raw_reference(c)

    def test_dev_cannot_enter_train_jobs(self):
        with self.assertRaises(ValueError):
            rollout_jobs(self.config, DIRECTORY, ids(ROOT / self.config['evaluation']['tasks']))

    def test_completion_and_tokenizer_requests_both_use_adapter(self):
        c = self.config
        responses = [{'tokens': [11, 12]},
                     {'choices': [{'text': 'x', 'token_ids': [13], 'finish_reason': 'stop',
                                   'logprobs': {'token_logprobs': [-0.2], 'tokens': ['token_id:13']}}]}]
        with patch.object(policy_server, 'request', side_effect=responses) as request:
            result = policy_server.sample_step(c, c['server']['adapter_name'], [], 123)
        self.assertEqual(result['response_ids'], [13])
        for call in request.call_args_list:
            self.assertEqual(call.args[2]['model'], c['server']['adapter_name'])
        cmd = policy_server.server_command(c, initial_policy.adapter_path(c))
        self.assertIn('--enable-lora', cmd)
        self.assertEqual(cmd[cmd.index('--max-lora-rank') + 1], '8')

    def test_all_fail_outcome_does_not_imply_zero_rubric_advantage(self):
        self.assertEqual(group_advantages([0] * 6), [0] * 6)
        rewards = rubric_rewards([['FAIL', 'FAIL']] * 3 + [['FAIL', 'PASS']] * 3)['rewards']
        self.assertTrue(any(a != 0 for a in group_advantages(rewards)))

    def test_judge_does_not_see_initialization_or_success(self):
        c = self.config
        job = verify_raw_reference(c)['jobs'][0]
        t = read_json(job['output'])
        t['job']['policy_id'] = 'SECRET_POLICY_SENTINEL'
        t['official_evaluation']['success'] = 'SECRET_SUCCESS_SENTINEL'
        prompt = build_prompt(c, t)
        self.assertNotIn('SECRET_POLICY_SENTINEL', prompt)
        self.assertNotIn('SECRET_SUCCESS_SENTINEL', prompt)
        with patch('judge.subprocess.run', side_effect=AssertionError('No model calls allowed')):
            with self.assertRaises(RuntimeError):
                score(c, t, Path('/tmp/unused-judge'), execute=False)

    def test_lora_progress_preserves_raw_report_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.md'
            original = '<!-- STEP01_PROGRESS_START -->\nRAW_RESULT_39_OF_540\n<!-- STEP01_PROGRESS_END -->\n'
            report.write_text(original)
            with patch.object(step01_collect, 'REPORT', report), patch.object(step01_collect, 'DIRECTORY', Path(tmp)):
                step01_collect.initialize_report(self.config)
                step01_collect.progress(self.config, {}, 'running', 'offline-test', 0)
            self.assertTrue(report.read_text().startswith(original))
            self.assertIn('LORA_STEP01_PROGRESS_START', report.read_text())

    def test_default_collector_cannot_start_a_server(self):
        with patch('sys.argv', ['step01_collect.py']), patch('preflight.inspect', return_value=({'status': 'offline'}, [])), \
             patch.object(step01_collect, 'execute', side_effect=AssertionError('Unexpected collection')), \
             patch.object(step01_collect, 'owned_server', side_effect=AssertionError('Unexpected server')):
            step01_collect.main()


class UnattendedTests(unittest.TestCase):
    def exercise(self, returns):
        import unattended
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / 'report.md'
            report.write_text('Existing raw result\n')
            with patch.object(unattended, 'ROOT', root), patch.object(unattended, 'RUNS', root / 'runs'), \
                 patch.object(unattended, 'REPORT', report), patch('sys.argv', ['unattended.py', '--execute']), \
                 patch.object(unattended.subprocess, 'run', side_effect=[SimpleNamespace(returncode=r) for r in returns]) as run, \
                 patch.object(unattended.time, 'sleep'), patch.object(unattended, 'final_report'):
                if all(returns):
                    with self.assertRaisesRegex(RuntimeError, 'Three collection attempts'):
                        unattended.main()
                else:
                    unattended.main()
            state = read_json(root / 'runs/unattended_status.json')
            self.assertTrue(report.read_text().startswith('Existing raw result'))
            self.assertEqual(run.call_count, len(returns))
            for call in run.call_args_list:
                self.assertEqual(call.kwargs['env']['CUDA_VISIBLE_DEVICES'], '0')
                self.assertEqual(Path(call.args[0][-2]).name, 'step01_collect.py')
                self.assertEqual(call.args[0][-1], '--execute')
            return state

    def test_unattended_resumes_after_infrastructure_failure(self):
        state = self.exercise([1, 0])
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['attempt'], 2)

    def test_unattended_records_failure_after_three_attempts(self):
        state = self.exercise([1, 1, 1])
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['attempt'], 3)

if __name__ == '__main__':
    unittest.main()
