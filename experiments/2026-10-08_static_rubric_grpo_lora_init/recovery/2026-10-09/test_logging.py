"""Regression tests for the concrete AppWorld logging crash; no model calls."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['APPWORLD_ROOT'] = str(ROOT / 'runtime/appworld')
from appworld.requester import RequestTracker
from appworld_log_compat import install_request_log_compatibility

class LoggingRecoveryTests(unittest.TestCase):
    def test_original_crash_and_lossless_request_preservation(self):
        tracker = RequestTracker()
        tracker.add_request('get', 'http://amazon.com/products', {'product_id': Ellipsis, 'nested': [Ellipsis]})
        with tempfile.TemporaryDirectory(dir=ROOT / 'recovery') as tmp:
            path = str(Path(tmp) / 'requests.jsonl')
            with self.assertRaises(ValueError):
                tracker.save(path)
            stats = install_request_log_compatibility()
            tracker.save(path)
            result = json.loads(Path(path).read_text())
            self.assertEqual(result['data']['product_id']['__python_type__'], 'Ellipsis')
            self.assertIs(tracker.requests[0]['data']['product_id'], Ellipsis)
            self.assertIs(tracker.requests[0]['data']['nested'][0], Ellipsis)
            self.assertEqual(stats['ellipsis_log_encodings'], 2)

    def test_supported_values_keep_original_encoding(self):
        import appworld.requester as requester
        tracker = RequestTracker()
        tracker.add_request('get', 'http://amazon.com/products', {'product_id': 1, 'empty': None, 'values': [True, 'x']})
        expected = requester.jsonable_encoder(tracker.requests[0])
        with tempfile.TemporaryDirectory(dir=ROOT / 'recovery') as tmp:
            path = Path(tmp) / 'requests.jsonl'
            tracker.save(str(path))
            self.assertEqual(json.loads(path.read_text()), expected)

    def test_unknown_object_is_not_silently_discarded(self):
        tracker = RequestTracker()
        tracker.add_request('get', 'http://amazon.com/products', {'invalid': object()})
        with tempfile.TemporaryDirectory(dir=ROOT / 'recovery') as tmp:
            with self.assertRaises(ValueError):
                tracker.save(str(Path(tmp) / 'requests.jsonl'))

if __name__ == '__main__':
    unittest.main()
