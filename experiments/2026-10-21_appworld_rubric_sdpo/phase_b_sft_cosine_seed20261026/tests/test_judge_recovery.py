"""CPU regression checks for the batch-14 transport interruption; no external calls."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import b_judge as j
import b_judge_recovery as recovery
from b_common import read, write_json


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.dest = self.root / 'judging/case'
        self.payload = self.root / 'payload.json'
        write_json(self.payload, {'trajectory_id': 'case'})
        (self.root / 'config').mkdir()
        (self.root / 'config/scoring_prompt_v7_feedback_en.txt').write_text('{{TRAJECTORY_JSON}}')
        write_json(self.root / 'config/judge.json', {'max_transport_attempts': 3,
            'max_format_repairs': 1, 'transport_retry_delays_seconds': [0, 0], 'timeout_seconds': 1})
        for name, value in [('B', self.root), ('R', self.root)]:
            self.stack.enter_context(patch.object(j, name, value))
        self.stack.enter_context(patch.object(j, 'authorize'))
        self.stack.enter_context(patch.object(j, 'validate_result'))
        self.stack.enter_context(patch.object(j, 'audit_events', return_value={'no_tools': True}))
        self.stack.enter_context(patch.object(j.time, 'sleep'))
        self.stack.enter_context(patch.object(j, 'command', side_effect=lambda cfg, cwd, out: [str(out)]))
        self.run = self.stack.enter_context(patch.object(j, 'run_request', side_effect=subprocess.TimeoutExpired(['fixture'], 1)))

    def fail_network(self):
        with self.assertRaises(recovery.JudgeTransportUnavailable):
            j.score(self.payload, self.dest, 'source')
        self.assertEqual(len(read(self.dest / 'metadata.json')['attempts']), 3)

    def valid_reply(self, cmd, **kwargs):
        write_json(Path(cmd[0]), {'steps': [[1, 'PPPNNNNN', []]]})
        return subprocess.CompletedProcess(cmd, 0)

    def test_failed_metadata_with_late_response_recovers_without_new_request(self):
        self.fail_network()
        write_json(self.dest / 'attempt_01/response.json', {'steps': [[1, 'PPPNNNNN', []]]})
        self.run.reset_mock()
        self.assertTrue(j.score(self.payload, self.dest, 'source')['recovered'])
        self.run.assert_not_called()
        meta = read(self.dest / 'metadata.json')
        self.assertEqual(meta['recovered_from_status'], 'failed')
        self.assertEqual(len(meta['attempts']), 3)

    def test_cooldown_round_preserves_attempts_and_exact_prompt(self):
        self.fail_network()
        self.assertTrue(recovery.batch_network_retryable(self.root))
        self.run.side_effect = self.valid_reply
        j.score(self.payload, self.dest, 'source')
        meta = read(self.dest / 'metadata.json')
        self.assertEqual(meta['status'], 'valid')
        self.assertEqual(len(meta['attempts']), 4)
        self.assertEqual(meta['transport_round_start'], 3)
        self.assertEqual((self.dest / 'attempt_01/request.txt').read_bytes(),
                         (self.dest / 'attempt_04/request.txt').read_bytes())

    def test_response_written_during_timeout_is_checked_before_retry(self):
        def late_response(cmd, **kwargs):
            self.valid_reply(cmd, **kwargs)
            raise subprocess.TimeoutExpired(cmd, 1)
        self.run.side_effect = late_response
        self.assertTrue(j.score(self.payload, self.dest, 'source')['recovered'])
        self.assertEqual(self.run.call_count, 1)

    def test_protocol_and_authentication_failures_are_not_network_retried(self):
        self.fail_network()
        path = self.dest / 'metadata.json'; meta = read(path)
        meta['attempts'][-1]['failure_type'] = 'protocol'; write_json(path, meta)
        self.assertFalse(recovery.batch_network_retryable(self.root))
        self.run.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'needs diagnosis'):
            j.score(self.payload, self.dest, 'source')
        self.run.assert_not_called()
        self.assertFalse(recovery.transient_transport(self.dest, {'failure_type': 'transport',
            'error': 'request timed out; insufficient_quota'}))

    def test_recovery_rejects_changed_substantive_labels(self):
        self.dest.mkdir(parents=True)
        write_json(self.dest / 'attempt_01/response.json', {'steps': [[1, 'FPPNNNNN', []]]})
        write_json(self.dest / 'attempt_02/response.json', {'steps': [[1, 'PPPNNNNN', []]]})
        def audit(path):
            if path.parent.name == 'attempt_01': raise AssertionError('incomplete event stream')
            return {'no_tools': True}
        with patch.object(j, 'audit_events', side_effect=audit):
            self.assertIsNone(j.recover_saved_response(read(self.payload), self.dest, {'attempts': []}))
        self.assertFalse((self.dest / 'judgement.json').exists())


class ProcessGroupTests(unittest.TestCase):
    def test_timeout_stops_wrapper_and_native_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); marker = folder / 'orphan_finished'
            child = 'import time,pathlib;time.sleep(0.8);pathlib.Path(' + repr(str(marker)) + ').touch()'
            wrapper = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",' + repr(child) + ']);time.sleep(30)'
            with (folder / 'out').open('w') as out:
                with self.assertRaises(subprocess.TimeoutExpired):
                    recovery.run_request([sys.executable, '-c', wrapper], input='', stdout=out,
                        stderr=out, env=dict(os.environ, CUDA_VISIBLE_DEVICES=''), cwd=folder, timeout=0.3)
            time.sleep(0.9)
            self.assertFalse(marker.exists())


if __name__ == '__main__': unittest.main(verbosity=2)
