"""Offline tests for eventual directory visibility; no API or real waits.

Run: python -m unittest discover -s tests -p test_p115strmhelper_directory_scan.py
"""

import importlib.util
from pathlib import Path
import sys
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "plugins.v2/p115strmhelper"
          / "helper/life/directory_scan.py")
SPEC = importlib.util.spec_from_file_location("directory_scan_under_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
collect_directory_snapshot = MODULE.collect_directory_snapshot


def file_item(file_id, **updates):
    item = {"id": file_id, "path": f"/shows/episode-{file_id}.mkv",
            "parent_id": 7, "size": 1000, "sha1": f"sha-{file_id}",
            "pickcode": f"pick-{file_id}"}
    item.update(updates)
    return item


class VirtualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class VirtualEvent:
    def __init__(self, clock):
        self.clock = clock
        self.stopped = False
        self.waits = []
        self.stop_during_wait = False

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, duration):
        self.waits.append(duration)
        self.clock.now += duration
        if self.stop_during_wait:
            self.set()
        return self.stopped


class DirectorySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.clock = VirtualClock()
        self.event = VirtualEvent(self.clock)

    def collect(self, scan, **kwargs):
        return collect_directory_snapshot(
            scan, stop_event=self.event, monotonic=self.clock, **kwargs)

    @staticmethod
    def scans(*passes):
        pending = iter(passes)

        def scan():
            return iter(next(pending))

        return scan

    def test_partial_23_grows_to_all_52_before_stabilizing(self):
        small = [file_item(i) for i in range(23)]
        full = [file_item(i) for i in range(52)]
        result = self.collect(self.scans(small, full, full, full))
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 4)
        self.assertEqual(len(result.items), 52)
        self.assertEqual(self.clock.now, 30)

    def test_same_count_with_different_ids_resets_comparisons(self):
        first = [file_item(1), file_item(2)]
        second = [file_item(2), file_item(3)]
        result = self.collect(self.scans(first, second, second, second),
                              min_observation=0)
        self.assertEqual(result.rounds, 4)
        self.assertTrue(result.stable)
        self.assertEqual({str(item["id"]) for item in result.items}, {"1", "2", "3"})

    def test_later_attributes_merge_and_essential_changes_reset(self):
        first = file_item(1, custom="keep", size=0)
        improved = file_item("1", size=123)
        relocated = file_item(1, size=123, path="/new/episode.mkv", parent_id=8)
        result = self.collect(self.scans([first], [improved], [relocated],
                                        [relocated], [relocated]), min_observation=0)
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 5)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0]["size"], 123)
        self.assertEqual(result.items[0]["path"], "/new/episode.mkv")
        self.assertEqual(result.items[0]["parent_id"], 8)
        self.assertEqual(result.items[0]["custom"], "keep")

    def test_pickcode_and_hash_changes_reset_comparisons(self):
        for attribute in ("sha1", "pickcode"):
            with self.subTest(attribute=attribute):
                first = file_item(1)
                changed = file_item(1, **{attribute: "new-value"})
                result = self.collect(self.scans([first], [first], [changed],
                                                [changed], [changed]),
                                      min_observation=0)
                self.assertTrue(result.stable)
                self.assertEqual(result.rounds, 5)
                self.assertEqual(result.items[0][attribute], "new-value")

    def test_order_and_nonessential_attributes_do_not_prevent_stability(self):
        first = [file_item(1, accessed=1), file_item(2)]
        later = [file_item(2), file_item("1", accessed=2)]
        result = self.collect(self.scans(first, later, later), min_observation=0)
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 3)
        self.assertEqual(result.items[0]["accessed"], 2)

    def test_empty_listing_waits_for_later_files(self):
        files = [file_item(1)]
        result = self.collect(self.scans([], [], [], files, files, files))
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 6)
        self.assertEqual(len(result.items), 1)

    def test_always_empty_still_observes_minimum_window(self):
        result = self.collect(lambda: iter(()))
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 4)
        self.assertEqual(self.clock.now, 30)
        self.assertEqual(result.items, [])

    def test_transient_partial_failure_keeps_files_and_resets_stability(self):
        calls = 0
        closed = []

        def scan():
            nonlocal calls
            calls += 1
            try:
                yield file_item(1)
                if calls == 2:
                    yield file_item(2)
                    raise OSError("temporary paging failure")
            finally:
                closed.append(calls)

        result = self.collect(scan, min_observation=0)
        self.assertTrue(result.stable)
        self.assertEqual(result.rounds, 5)
        self.assertEqual(result.errors, 1)
        self.assertEqual({item["id"] for item in result.items}, {1, 2})
        self.assertEqual(closed, [1, 2, 3, 4, 5])

    def test_persistent_failures_are_bounded_and_keep_partial_results(self):
        def scan():
            yield file_item(1)
            raise OSError("failure")

        result = self.collect(scan)
        self.assertFalse(result.stable)
        self.assertEqual(result.reason, "max_rounds")
        self.assertEqual(result.rounds, 6)
        self.assertEqual(result.errors, 6)
        self.assertEqual(len(result.items), 1)

    def test_iterator_creation_failure_is_also_bounded(self):
        def scan():
            raise OSError("cannot begin")

        result = self.collect(scan, max_rounds=2)
        self.assertEqual(result.reason, "max_rounds")
        self.assertEqual(result.errors, 2)
        self.assertEqual(result.items, [])

    def test_continued_growth_returns_union_at_round_limit(self):
        calls = 0

        def scan():
            nonlocal calls
            calls += 1
            return iter([file_item(calls)])

        result = self.collect(scan, max_rounds=4)
        self.assertFalse(result.stable)
        self.assertEqual(result.reason, "max_rounds")
        self.assertEqual(len(result.items), 4)

    def test_elapsed_limit_caps_wait_and_prevents_next_scan(self):
        result = self.collect(lambda: iter([file_item(1)]), max_elapsed=15)
        self.assertEqual(result.reason, "max_elapsed")
        self.assertEqual(result.rounds, 2)
        self.assertEqual(self.event.waits, [10, 5])
        self.assertEqual(self.clock.now, 15)

    def test_elapsed_limit_during_iterator_closes_it(self):
        closed = []

        def scan():
            try:
                yield file_item(1)
                self.clock.now = 200
                yield file_item(2)
                self.fail("must stop before requesting another record")
            finally:
                closed.append(True)

        result = self.collect(scan)
        self.assertEqual(result.reason, "max_elapsed")
        self.assertFalse(result.stable)
        self.assertEqual(result.rounds, 1)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(closed, [True])

    def test_stopped_before_start_never_scans(self):
        self.event.set()
        result = self.collect(lambda: self.fail("must not scan"))
        self.assertTrue(result.stopped)
        self.assertEqual(result.reason, "stopped")
        self.assertEqual(result.rounds, 0)

    def test_stopped_during_wait_prevents_another_pass(self):
        self.event.stop_during_wait = True
        result = self.collect(self.scans([file_item(1)]))
        self.assertTrue(result.stopped)
        self.assertEqual(result.rounds, 1)
        self.assertEqual(len(result.items), 1)

    def test_stopped_during_iteration_closes_iterator(self):
        closed = []

        def scan():
            try:
                yield file_item(1)
                self.event.set()
                yield file_item(2)
                self.fail("must stop before requesting another record")
            finally:
                closed.append(True)

        result = self.collect(scan)
        self.assertTrue(result.stopped)
        self.assertFalse(result.stable)
        self.assertEqual(result.rounds, 1)
        self.assertEqual(closed, [True])

    def test_progress_callback_reports_detached_snapshots(self):
        progress = []

        def on_round(result):
            progress.append((result.rounds, result.reason, len(result.items)))
            result.items[0]["path"] = "/callback-mutation"
            result.items.clear()

        result = self.collect(lambda: iter([file_item(1)]), min_observation=0,
                              on_round=on_round)
        self.assertEqual(progress, [(1, "observing", 1), (2, "observing", 1),
                                    (3, "stable", 1)])
        self.assertEqual(result.items[0]["path"], "/shows/episode-1.mkv")

    def test_invalid_limits_fail_before_scanning(self):
        for kwargs in ({"interval": -1}, {"interval": float("inf")},
                       {"min_observation": float("nan")},
                       {"max_elapsed": -1}, {"max_rounds": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.collect(lambda: self.fail("must not scan"), **kwargs)

    def test_zero_limits_skip_scanning(self):
        for kwargs, reason in (({"max_rounds": 0}, "max_rounds"),
                               ({"max_elapsed": 0}, "max_elapsed")):
            with self.subTest(kwargs=kwargs):
                result = self.collect(lambda: self.fail("must not scan"), **kwargs)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.rounds, 0)


if __name__ == "__main__":
    unittest.main()
