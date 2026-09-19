"""Offline rate-limit regressions with real queued threads and a virtual clock.

Set P115_TOOLS_SOURCE to check the same behavior against a deployed snapshot.
No MoviePilot imports, network requests, or real rate-limit sleeps are needed.
"""

import importlib.util
import os
from pathlib import Path
from queue import SimpleQueue
from threading import Barrier, Lock, Thread
from time import monotonic as real_monotonic
import unittest
from unittest.mock import patch


SOURCE = Path(os.environ.get(
    "P115_TOOLS_SOURCE",
    str(Path(__file__).resolve().parents[1] / "plugins.v2/p115disk/tools.py"),
))


class VirtualClock:
    def __init__(self):
        self.current = 100.0
        self.waits = []

    def monotonic(self):
        return self.current

    def sleep(self, seconds):
        if seconds <= 0:
            raise AssertionError(f"Unexpected sleep: {seconds}")
        self.waits.append(seconds)
        self.current += seconds


class QueuedLock:
    """Queue all callers before admitting any to the real critical section."""

    def __init__(self, callers, clock):
        self.ready = Barrier(callers)
        self.lock = Lock()
        self.clock = clock
        self.granted_at = []

    def __enter__(self):
        self.ready.wait(timeout=5)
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.granted_at.append(self.clock.current)
        self.lock.release()


class P115DiskRateLimiterTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("p115disk_tools_under_test", SOURCE)
        self.tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tools)
        self.clock = VirtualClock()
        for name in ("monotonic", "sleep"):
            replacement = patch.object(self.tools, name, getattr(self.clock, name))
            replacement.start()
            self.addCleanup(replacement.stop)

    def acquire_concurrently(self, limiter, callers):
        queued_lock = QueuedLock(callers, self.clock)
        limiter._lock = queued_lock
        errors = SimpleQueue()

        def acquire():
            try:
                limiter.acquire()
            except BaseException as error:
                errors.put(error)

        threads = [Thread(target=acquire, daemon=True) for _ in range(callers)]
        for thread in threads:
            thread.start()
        deadline = real_monotonic() + 5
        for thread in threads:
            thread.join(timeout=max(0, deadline - real_monotonic()))
        self.assertFalse(any(thread.is_alive() for thread in threads), "Limiter stalled")
        if not errors.empty():
            raise errors.get()
        self.assertEqual(len(queued_lock.granted_at), callers)
        return queued_lock.granted_at

    def assert_within_quota(self, granted_at, max_calls, time_window):
        for index, granted in enumerate(granted_at):
            in_window = [earlier for earlier in granted_at[:index + 1]
                         if granted - earlier < time_window]
            self.assertLessEqual(len(in_window), max_calls, granted_at)

    def test_queued_threads_wait_one_window_each(self):
        limiter = self.tools.RateLimiter(max_calls=1, time_window=2)
        limiter._call_times = [self.clock.current]
        granted_at = self.acquire_concurrently(limiter, callers=6)

        # Every caller reaches the lock at t=100. Sampling before that lock
        # incorrectly turns these waits into 2, 4, 8, 16, 32, 64 seconds.
        self.assertEqual(self.clock.waits, [2] * 6)
        self.assertEqual(granted_at, [102, 104, 106, 108, 110, 112])
        self.assert_within_quota([100] + granted_at, max_calls=1, time_window=2)

    def test_concurrent_callers_preserve_one_and_two_call_quotas(self):
        for max_calls in (1, 2):
            with self.subTest(max_calls=max_calls):
                self.clock.current = 100.0
                self.clock.waits.clear()
                limiter = self.tools.RateLimiter(max_calls=max_calls, time_window=2)
                granted_at = self.acquire_concurrently(limiter, callers=8)

                self.assert_within_quota(granted_at, max_calls, time_window=2)
                self.assertEqual(granted_at, [100 + (index // max_calls) * 2
                                             for index in range(8)])

    def test_partial_window_waits_only_until_oldest_call_expires(self):
        limiter = self.tools.RateLimiter(max_calls=2, time_window=2)
        granted_at = []
        for advance in (0, 0.5, 0.25, 0):
            self.clock.current += advance
            limiter.acquire()
            granted_at.append(self.clock.current)

        self.assertEqual(self.clock.waits, [1.25, 0.5])
        self.assertEqual(granted_at, [100, 100.5, 102, 102.5])
        self.assert_within_quota(granted_at, max_calls=2, time_window=2)


if __name__ == "__main__":
    unittest.main()
