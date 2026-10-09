"""Offline tests: synthetic transcripts/tensors and a tiny random CPU model only."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import common
import judge
import policy_server
import run
from common import ROOT, load_config, load_rules

class RewardTests(unittest.TestCase):
    def test_draco_filter_and_na_denominator(self):
        matrix = [
            ['PASS', 'PASS', 'PASS', 'PASS', 'FAIL', 'NA', 'NA'],
            ['NA',   'FAIL', 'FAIL', 'FAIL', 'PASS', 'NA', 'NA'],
            ['PASS', 'PASS', 'PASS', 'PASS', 'FAIL', 'NA', 'NA'],
            ['PASS', 'PASS', 'PASS', 'PASS', 'FAIL', 'NA', 'NA'],
            ['NA',   'FAIL', 'FAIL', 'FAIL', 'PASS', 'NA', 'NA'],
            ['PASS', 'PASS', 'PASS', 'PASS', 'FAIL', 'NA', 'NA']]
        result = common.rubric_rewards(matrix)
        self.assertEqual(result['kept_rule_ids'], [1, 2, 3, 4])
        self.assertEqual(result['rewards'], [5, -5, 5, 5, -5, 5])

    def test_all_na_or_no_fail_gives_zero(self):
        self.assertEqual(common.rubric_rewards([['PASS', 'NA']] * 6)['rewards'], [0] * 6)

    def test_all_fail_retained_zero_advantage(self):
        r = common.rubric_rewards([['FAIL']] * 6)
        self.assertEqual(r['kept_rule_ids'], [0])
        self.assertEqual(r['rewards'], [-10] * 6)
        self.assertEqual(common.group_advantages(r['rewards']), [0] * 6)

    def test_na_not_false_pass(self):
        self.assertEqual(common.rubric_rewards([['FAIL'], ['NA']])['rewards'], [-10, 0])

    def test_invalid_verdict_rejected(self):
        for matrix in ([['missing']], [['PASS'], []], []):
            with self.assertRaises(ValueError):
                common.rubric_rewards(matrix)

    def test_advantage_is_group_relative_sample_std(self):
        result = common.group_advantages([0, 0, 0, 1, 1, 1])
        self.assertAlmostEqual(sum(result), 0)
        self.assertAlmostEqual(result[-1], 0.5 / (math.sqrt(0.3) + 1e-6))
        with self.assertRaises(ValueError):
            common.group_advantages([0, float('nan')])

class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.rules = load_rules(self.config)
        self.value = {'scores': [{'rubric_title': r['title'], 'score': 0,
                                 'evidence': 'No applicable trigger in steps.', 'justification': 'Conditional rule.'}
                                for r in self.rules]}
        self.trajectory = {'public_task': {'instruction': 'Count songs.'},
                           'initial_messages': [{'role': 'user', 'content': 'Public instructions.'}],
                           'steps': [{'step': 1, 'text': 'public assistant', 'code': 'print(1)', 'observation': '1',
                                      'private_test': 'HIDDEN_TEST_SENTINEL'}],
                           'termination': 'step_limit', 'official_evaluation': {'success': 'HIDDEN_SUCCESS_SENTINEL'},
                           'ground_truth': 'HIDDEN_SOLUTION_SENTINEL'}

    def test_all_21_unique_ordered_required(self):
        self.assertEqual(len(common.validate_judgement(self.value, self.rules)), 21)
        for mutate in ('missing', 'duplicate', 'bool', 'out_of_range', 'null_row'):
            bad = copy.deepcopy(self.value)
            if mutate == 'missing':
                bad['scores'].pop()
            elif mutate == 'duplicate':
                bad['scores'][1] = bad['scores'][0]
            elif mutate == 'null_row':
                bad['scores'][0] = None
            elif mutate == 'bool':
                bad['scores'][0]['score'] = True
            else:
                bad['scores'][0]['score'] = 2
            with self.assertRaises(ValueError):
                common.validate_judgement(bad, self.rules)

    def test_no_hidden_labels_or_tests_in_judge(self):
        prompt = judge.build_prompt(self.config, self.trajectory)
        self.assertNotIn('HIDDEN_', prompt)
        self.assertNotIn('does NOT end the task', prompt)
        self.assertIn('stops automatically', prompt)
        self.assertIn('Identify evidence', prompt)
        for rule in self.rules:
            self.assertIn(rule['title'], prompt)
        self.assertNotIn('n_pass', prompt)

    def test_schema_matches_frozen_asset(self):
        self.assertEqual(common.read_json(ROOT / self.config['judge']['schema']), judge.make_schema(self.rules))

    def test_no_scoring_without_execution(self):
        with patch('judge.subprocess.run') as call, self.assertRaises(RuntimeError):
            judge.score(self.config, self.trajectory, '/tmp/unused-judge', execute=False)
        call.assert_not_called()

    def test_tool_use_rejected(self):
        for item in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change', 'unknown_tool'):
            events = json.dumps({'type': 'item.completed', 'item': {'type': item}}) + '\n' + json.dumps({'type': 'turn.completed'})
            with self.assertRaises(ValueError):
                judge.audit_events(events)

    def test_mock_judge_cache_and_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            def fake_call(command, **kwargs):
                calls.append(command)
                response = Path(command[command.index('--output-last-message') + 1])
                response.write_text('{}' if len(calls) == 1 else json.dumps(self.value))
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 10}}), stderr='')
            with patch('judge.subprocess.run', side_effect=fake_call):
                first = judge.score(self.config, self.trajectory, temporary, execute=True)
                second = judge.score(self.config, self.trajectory, temporary, execute=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(first, second)
            self.assertEqual(first['attempts'], 2)

class BoundaryTests(unittest.TestCase):
    def test_train_only_and_same_arm_schedule(self):
        config = load_config()
        train = common.ids(ROOT / config['training']['train_tasks'])
        dev = common.ids(ROOT / config['evaluation']['tasks'])
        common.check_training_ids(train, config)
        with self.assertRaises(ValueError):
            common.check_training_ids([dev[0]], config)
        schedule = [task for update in range(1, 11) for task in common.schedule(config, update)]
        self.assertEqual(len(schedule), 20)
        self.assertTrue(set(schedule) <= set(train))

    def test_parser_preserves_raw_response_and_only_first_block(self):
        fence = chr(96) * 3
        text = fence + 'python\nprint(1)\n' + fence + '\n' + fence + 'python\nprint(2)\n' + fence
        code, fixed = common.parse_code(text)
        self.assertEqual(code, 'print(1)')
        self.assertEqual(fixed, text)
        code, fixed = common.parse_code(fence + 'python\nprint(3)')
        self.assertEqual(code, 'print(3)')
        self.assertTrue(fixed.endswith(fence))

    def test_token_alignment_required(self):
        common.validate_tokens([1, 2], [3, 4], [-1.0, -2.0])
        for ids, values in (([3, 4], [-1]), ([3], [None]), ([3], [float('nan')]), ([3], [0.5])):
            with self.assertRaises(ValueError):
                common.validate_tokens([1], ids, values)

    def test_exact_token_completion_api(self):
        config = load_config()
        responses = [
            {'tokens': [1, 2, 3]},
            {'choices': [{'text': 'action', 'token_ids': [4, 5], 'logprobs': {'token_logprobs': [-1, -2], 'tokens': ['token_id:4', 'token_id:5']},
                          'finish_reason': 'stop'}]}]
        with patch('policy_server.request', side_effect=responses) as call:
            result = policy_server.sample_step(config, 'test-policy', [{'role': 'user', 'content': 'x'}], 123)
        payload = call.call_args_list[1].args[2]
        self.assertEqual(payload['prompt'], [1, 2, 3])
        self.assertEqual(payload['temperature'], 1)
        self.assertEqual(payload['top_p'], 1)
        self.assertEqual(payload['top_k'], -1)
        self.assertEqual(result['response_ids'], [4, 5])

    def test_dev_requires_complete_exact_ids(self):
        expected = ['a_1', 'a_2', 'b_1']
        trajectories = [{'public_task': {'task_id': t}, 'official_evaluation': {'success': s}}
                        for t, s in zip(expected, [True, False, True])]
        metrics = run.evaluation_metrics(trajectories, expected)
        self.assertAlmostEqual(metrics['task_goal_completion'], 200 / 3)
        self.assertEqual(metrics['scenario_goal_completion'], 50)
        with self.assertRaises(ValueError):
            run.evaluation_metrics(trajectories[:-1], expected)
        with self.assertRaises(ValueError):
            run.evaluation_metrics(trajectories + trajectories[:1], expected)

    def test_busy_gpu_does_not_start_a_server(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('resources.inventory', return_value=[{'index': '0', 'free_mib': 8192}]), patch('policy_server.subprocess.Popen') as process:
                with self.assertRaises(RuntimeError):
                    with policy_server.owned_server(load_config(), directory):
                        self.fail('Busy GPU should not reach server body')
                process.assert_not_called()

    def test_commands_cannot_start_without_execute(self):
        for command in ('pilot', 'train', 'evaluate', 'all'):
            result = subprocess.run([sys.executable, str(ROOT / 'run.py'), command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('execution is disabled', result.stderr)

class ObjectiveTests(unittest.TestCase):
    def test_grpo_gradient_direction_and_clip(self):
        import torch
        from train_grpo import grpo_terms
        for advantage in (1.0, -1.0):
            new = torch.tensor([-1.0], requires_grad=True)
            old = torch.tensor([-1.0])
            loss, ratio, kl = grpo_terms(new, old, old, advantage, 0.2, 0.01)
            loss.sum().backward()
            self.assertAlmostEqual(new.grad.item(), -advantage)
            self.assertEqual(kl.item(), 0)
        for advantage, ratio in ((1.0, 1.5), (-1.0, 0.5)):
            new = torch.tensor([-1.0 + math.log(ratio)], requires_grad=True)
            loss, _, _ = grpo_terms(new, torch.tensor([-1.0]), new.detach(), advantage, 0.2, 0)
            loss.sum().backward()
            self.assertAlmostEqual(new.grad.item(), 0)

    def test_tiny_cpu_qwen_logprobs_equal_full_forward_and_lora_gradients(self):
        import torch
        import torch.nn.functional as F
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from peft import LoraConfig, get_peft_model
        from train_grpo import action_logprobs
        torch.manual_seed(123)
        config = Qwen3Config(vocab_size=32, hidden_size=16, intermediate_size=32, num_hidden_layers=1,
                            num_attention_heads=2, num_key_value_heads=1, head_dim=8,
                            max_position_embeddings=64, attention_dropout=0)
        model = get_peft_model(Qwen3ForCausalLM(config), LoraConfig(r=2, lora_alpha=4, lora_dropout=0,
                                                               target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
        model.enable_input_require_grads()
        model.train()
        prompt, response = [1, 2, 3], [4, 5, 6]
        actual = action_logprobs(model, prompt, response, 2)
        full = model(input_ids=torch.tensor([prompt + response]), use_cache=False).logits[0, 2:5].float()
        expected = -F.cross_entropy(full, torch.tensor(response), reduction='none')
        self.assertTrue(torch.allclose(actual, expected, atol=1e-6), (actual, expected))
        (-actual.mean()).backward()
        grads = [p.grad for name, p in model.named_parameters() if 'lora_' in name and p.grad is not None]
        self.assertTrue(any(torch.count_nonzero(g) for g in grads))
        self.assertTrue(all(p.grad is None for name, p in model.named_parameters() if 'lora_' not in name))

if __name__ == '__main__':
    unittest.main(verbosity=2)
