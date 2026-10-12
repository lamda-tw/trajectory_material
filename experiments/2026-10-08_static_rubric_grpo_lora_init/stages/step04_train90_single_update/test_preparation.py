"""Standard-library checks only: synthetic data, no model loading or backward."""
from contextlib import ExitStack
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pipeline as p
import run


class PreparationTests(unittest.TestCase):
    def test_scope_and_trainer_provenance(self):
        tasks = p.tasks_for(1)
        cfg = p.load_config()
        self.assertEqual(len(tasks), 90)
        self.assertEqual(set(tasks), set(p.ids(p.ROOT / cfg['training']['train_tasks'])))
        for update in (0, 2, 90):
            with self.assertRaises(ValueError):
                p.tasks_for(update)
        with self.assertRaises(ValueError):
            p.policy_info('outcome', 0)
        provenance = p.read_json(p.STAGE / 'provenance.json')
        self.assertEqual(p.file_sha(p.STAGE / 'train.py'), provenance['files']['train.py'])

    def test_full_batch_and_per_task_advantages(self):
        tasks = [f'train_{i}' for i in range(90)]
        jobs, trajectories = [], {}
        for task in tasks:
            for sample in range(6):
                job = dict(task_id=task, sample=sample, output=f'/synthetic/{task}/{sample}',
                           mode='train', policy_id='initial', update=0, fingerprint='collection')
                jobs.append(job)
                trajectories[job['output']] = {
                    'job': job, 'public_task': {'task_id': task},
                    'steps': [{'prompt_ids': [1, 2], 'response_ids': [3], 'old_logprobs': [-1.0]}]}
        def scores(job, directory):
            # Half the groups have differences; the others have constant rewards.
            number = int(job['task_id'].split('_')[-1])
            value = -1 if number % 2 or job['sample'] == 0 else 1
            return Path('/synthetic/score'), {'scores': [{'score': value}] * 21}
        cfg = {'judge': {'reward_scale': 10.0}}
        stage = p.settings()
        with ExitStack() as stack:
            for name, value in {
                'load_config': lambda: cfg, 'settings': lambda: stage, 'tasks_for': lambda update: tasks,
                'policy_info': lambda branch, update: {'policy_id': 'initial'},
                'policy_id': lambda cfg: 'initial', 'collection_fingerprint': lambda cfg: 'collection',
                'check_training_ids': lambda tasks, cfg: None,
                'read_json': lambda path: trajectories[path], 'file_sha': lambda path: 'sha',
                'validated_scores': scores, 'identity': lambda: 'stage',
            }.items():
                stack.enter_context(patch.object(p, name, value))
            batch = p.build_batch(jobs, Path('/synthetic'), 'rubric', 1)
            self.assertEqual(len(batch['episodes']), 540)
            self.assertEqual(len(batch['groups']), 90)
            for i, group in enumerate(batch['groups']):
                expected = [-10.0] * 6 if i % 2 else [-10.0] + [10.0] * 5
                self.assertEqual(group['rewards'], expected)
                self.assertEqual(group['advantages'], p.group_advantages(expected))
            for broken in (jobs[:-1], jobs[:-1] + [jobs[-2]]):
                with self.assertRaises(ValueError):
                    p.build_batch(broken, Path('/synthetic'), 'rubric', 1)
            changed = copy.deepcopy(trajectories[jobs[0]['output']])
            changed['job']['policy_id'] = 'smoke-checkpoint'
            trajectories[jobs[0]['output']] = changed
            with self.assertRaises(ValueError):
                p.build_batch(jobs, Path('/synthetic'), 'rubric', 1)

    def test_missing_scores_never_become_zero_reward(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = {'policy_id': 'not-in-cache', 'task_id': 'missing', 'sample': 0}
            with self.assertRaises(FileNotFoundError):
                p.validated_scores(job, Path(tmp))

    def test_no_execute_cannot_start_work(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch.object(p, 'RUN', Path(tmp)))
            stack.enter_context(patch.object(run, 'prepare', return_value=({}, {'prepared': True})))
            scorers = stack.enter_context(patch.object(run, 'score_all', side_effect=AssertionError('judge')))
            trainer = stack.enter_context(patch.object(run, 'train', side_effect=AssertionError('training')))
            stack.enter_context(patch('sys.stdout', new_callable=io.StringIO))
            for command in ('prepare', 'score', 'train', 'all'):
                with patch.object(sys, 'argv', ['run.py', command]):
                    run.main()
            scorers.assert_not_called()
            trainer.assert_not_called()

    def test_interrupted_judge_recovers_earliest_without_call(self):
        job = {'output': '/synthetic/trajectory'}
        cfg = p.load_config()
        scores = [{'rubric_title': r['title'], 'score': -1,
                   'evidence': 'synthetic evidence', 'justification': 'synthetic justification'}
                  for r in p.load_rules(cfg)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(p.judge, 'build_prompt', return_value='prompt'):
            folder = Path(tmp)
            (folder / 'prompt.txt').write_text('prompt')
            for attempt in (1, 2):
                response = {'scores': scores}
                p.atomic_json(folder / f'response_{attempt}.json', response)
                events = [{'type': 'turn.started'},
                          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(response)}},
                          {'type': 'turn.completed', 'usage': {}}]
                (folder / f'events_{attempt}.jsonl').write_text('\n'.join(json.dumps(x) for x in events))
            original = p.read_json
            with patch.object(p, 'read_json', side_effect=lambda path: {} if path == job['output'] else original(path)), \
                    patch.object(p.judge, 'score', side_effect=AssertionError('No judge calls')):
                self.assertTrue(run.recover_completed(job, folder))
            self.assertEqual(p.read_json(folder / 'judgement.json')['attempts'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
