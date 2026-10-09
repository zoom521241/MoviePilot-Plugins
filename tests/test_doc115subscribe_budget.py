"""Synthetic time/concurrency tests; no cloud resources or requests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe/request_budget.py"
SPEC = importlib.util.spec_from_file_location("doc115_budget_test", SOURCE)
budget = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = budget
SPEC.loader.exec_module(budget)


class Clock:
    def __init__(self):
        self.now = 100.0
    def sleep(self, delay):
        self.now += delay


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.b = budget.AccountBudget(clock=lambda: self.clock.now,
            wall_clock=lambda: 1000 + self.clock.now, sleep=self.clock.sleep)

    def test_five_request_slice_rejects_sixth_without_admission(self):
        with self.b.work_slice():
            for _ in range(5):
                with self.b.request():
                    pass
            with self.assertRaises(budget.P115Deferred) as raised:
                with self.b.request():
                    self.fail("sixth request was admitted")
        self.assertEqual(raised.exception.reason, "slice")
        self.assertTrue(raised.exception.not_sent)
        self.assertEqual(len(self.b._request_times), 5)
        self.assertEqual(self.clock.now, 108)
        with self.b.work_slice(), self.b.request():
            pass
        self.assertEqual(self.clock.now, 110)

    def test_slow_inflight_request_finishes_then_slice_stops(self):
        with self.b.work_slice():
            with self.b.request():
                self.clock.sleep(16)
            with self.assertRaises(budget.P115Deferred):
                with self.b.request():
                    self.fail("elapsed slice admitted another request")

    def test_rolling_twenty_per_minute_is_shared_across_slices(self):
        admitted = []
        for _ in range(4):
            with self.b.work_slice():
                for _ in range(5):
                    with self.b.request():
                        admitted.append(self.clock.now)
        self.assertEqual(admitted, [100 + i * 2 for i in range(20)])
        with self.b.work_slice(), self.assertRaises(budget.P115Deferred) as raised:
            with self.b.request():
                self.fail("21st rolling request")
        self.assertEqual(raised.exception.reason, "account_budget")
        self.assertEqual(raised.exception.retry_at, 1160)
        self.clock.sleep(22)
        with self.b.work_slice(), self.b.request():
            pass
        self.assertEqual(len(self.b._request_times), 20)

    def test_three_new_batches_per_minute_independent_of_episode_count(self):
        for _ in range(3):
            self.b.claim_submission()
        with self.assertRaises(budget.P115Deferred) as raised:
            self.b.claim_submission()
        self.assertEqual(raised.exception.reason, "submission_budget")
        self.clock.sleep(60)
        self.b.claim_submission()

    def test_stop_during_interval_wait_prevents_next_http_request(self):
        stopped = [False]
        def sleep(seconds):
            self.clock.sleep(seconds)
            stopped[0] = True
        self.b.sleep = sleep
        with self.b.work_slice(cancelled=lambda: stopped[0]):
            with self.b.request():
                pass
            with self.assertRaises(budget.P115Deferred) as raised:
                with self.b.request():
                    self.fail("request after stop")
        self.assertEqual(raised.exception.reason, "cancelled")
        self.assertEqual(len(self.b._request_times), 1)

    def test_entire_transport_is_serialized_for_concurrent_workers(self):
        start = threading.Barrier(4)
        active = [0]
        def work(_):
            start.wait(timeout=5)
            with self.b.work_slice(), self.b.request():
                active[0] += 1
                self.assertEqual(active[0], 1)
                self.clock.sleep(0.5)
                active[0] -= 1
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(4)))
        self.assertEqual(list(self.b._request_times), [100, 102, 104, 106])

    def test_refreshed_cookie_uses_account_total_and_never_keeps_secret_keys(self):
        a = budget.account_budget("UID=syntheticAccount_A; CID=syntheticSecretA")
        b = budget.account_budget("UID=syntheticAccount_B; CID=syntheticSecretB")
        self.assertIs(a, b)
        self.assertTrue(all("synthetic" not in key for key in budget._ACCOUNTS))

    def test_manual_calls_and_new_submissions_obey_account_circuit(self):
        self.b.pause("risk_control", 900)
        for action in (self.b.claim_submission, lambda: self.b.request().__enter__()):
            with self.assertRaises(budget.P115Deferred) as raised:
                action()
            self.assertEqual(raised.exception.reason, "risk_control")
        self.assertEqual(len(self.b._request_times), 0)

    def test_other_task_is_not_sent_during_unknown_write_cooldown(self):
        self.b.pause("uncertain", 60)
        with self.b.work_slice(), self.assertRaises(budget.P115Deferred) as raised:
            with self.b.request():
                self.fail("cooldown admitted another task")
        self.assertTrue(raised.exception.not_sent)
        self.assertFalse(raised.exception.uncertain)
        self.assertEqual(raised.exception.reason, "uncertain")

    def restarted(self, path, wall=None):
        return budget.AccountBudget(clock=lambda: self.clock.now,
            wall_clock=wall or (lambda: 1000 + self.clock.now), sleep=self.clock.sleep)

    def test_restart_preserves_nineteen_actual_requests_and_submission_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            self.b.attach_state(path)
            for _ in range(3):
                self.b.claim_submission()
            for _ in range(19):
                with self.b.request():
                    pass
            recovered = self.restarted(path)
            recovered.attach_state(path)
            self.assertEqual(len(recovered._request_times), 19)
            self.assertEqual(len(recovered._submission_times), 3)
            with self.assertRaises(budget.P115Deferred):
                recovered.claim_submission()
            with recovered.request():
                pass
            with self.assertRaises(budget.P115Deferred) as raised:
                with recovered.request():
                    self.fail("restart bypassed twentieth rolling request")
            self.assertEqual(raised.exception.reason, "account_budget")

    def test_restart_preserves_auth_and_uncertain_cooldown_even_with_backward_wall_clock(self):
        for reason in ("authentication", "uncertain", "risk_control", "rate_limit"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "budget.json"
                b = self.restarted(path)
                b.attach_state(path)
                b.pause(reason, 900)
                restored = self.restarted(path, wall=lambda: 900 + self.clock.now)
                restored.attach_state(path)
                with self.assertRaises(budget.P115Deferred) as raised:
                    with restored.request():
                        self.fail("restart bypassed account circuit")
                self.assertEqual(raised.exception.reason, reason)
                self.assertTrue(raised.exception.not_sent)
                self.assertFalse(raised.exception.uncertain)
                self.assertEqual(restored._cooldown_until - self.clock.now, 900)

    def test_expired_state_recovers_without_long_historical_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            self.b.attach_state(path)
            with self.b.request():
                pass
            self.b.pause("rate_limit", 300)
            self.clock.sleep(301)
            recovered = self.restarted(path)
            recovered.attach_state(path)
            with recovered.request():
                pass
            self.assertEqual(len(recovered._request_times), 1)

    def test_invalid_or_unwritable_budget_never_allows_http_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(budget.P115Deferred) as raised:
                self.b.attach_state(path)
            self.assertEqual(raised.exception.reason, "local_state")
            self.assertTrue(raised.exception.not_sent)
            with self.assertRaises(budget.P115Deferred):
                with self.b.request():
                    self.fail("a cached client bypassed broken budget initialization")
            path.unlink()
            self.b.attach_state(path)
            with patch.object(budget.os, "replace", side_effect=OSError("synthetic full disk")):
                with self.assertRaises(budget.P115Deferred) as raised:
                    with self.b.request():
                        self.fail("HTTP proceeded without durable admission")
            self.assertTrue(raised.exception.not_sent)
            self.assertEqual(raised.exception.reason, "local_state")
            self.assertFalse(list(Path(directory).glob("*.tmp")))
            with self.assertRaises(budget.P115Deferred):
                with self.b.request():
                    self.fail("later cached client bypassed durable write failure")


if __name__ == "__main__":
    unittest.main()
