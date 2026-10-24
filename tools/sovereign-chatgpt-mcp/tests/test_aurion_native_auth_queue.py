"""Real temporary queue I/O; no host worker or production effects."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command_queue import HostCommandQueueClient


class NativeQueueContracts(unittest.TestCase):
    def test_busy_worker_beyond_old_timeout_keeps_exact_job_until_claimed(self):
        with tempfile.TemporaryDirectory() as root:
            queue = HostCommandQueueClient(root)
            admitted = queue.enqueue('aurion_native_auth_apply', {'operation_id': 'a' * 32})
            request_id = admitted['request_id']
            time.sleep(1.1)  # actual unclaimed wait beyond the former UI timeout
            self.assertEqual(queue.status(request_id)['status'], 'QUEUED')
            pending = queue.inbox / (request_id + '.json')
            self.assertEqual(json.loads(pending.read_text())['arguments'], {'operation_id': 'a' * 32})
            pending.rename(queue.processing / pending.name)
            self.assertEqual(queue.status(request_id)['status'], 'IN_PROGRESS')
            self.assertEqual(len(list(queue.processing.glob('*.json'))), 1)
            self.assertFalse(list(queue.inbox.glob('*.json')))

    def test_lost_claimed_job_is_unknown_without_reenqueue(self):
        with tempfile.TemporaryDirectory() as root:
            queue = HostCommandQueueClient(root)
            request_id = queue.enqueue('aurion_native_auth_apply', {'operation_id': 'a' * 32})['request_id']
            pending = queue.inbox / (request_id + '.json')
            claimed = queue.processing / pending.name
            pending.rename(claimed)
            claimed.unlink()  # external worker failure; status cannot infer completion
            self.assertEqual(queue.status(request_id)['status'], 'NOT_FOUND')
            self.assertFalse(list(queue.inbox.glob('*.json')))
