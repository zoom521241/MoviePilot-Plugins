"""Synthetic persistence regressions; no MoviePilot or network required."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe/history.py"
SPEC = importlib.util.spec_from_file_location("doc115_history_test", SOURCE)
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "pending_offline.json"

    def test_independent_history_instances_do_not_lose_concurrent_adds(self):
        start = Barrier(8)

        def add_batch(index):
            store = history.RecordStore(self.path)
            start.wait(timeout=5)
            return [store.add({"title": f"Synthetic {index}/{i}"}) for i in range(12)]

        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = [row for group in pool.map(add_batch, range(8)) for row in group]
        saved = history.RecordStore(self.path).list()
        self.assertEqual(len(saved), 96)
        self.assertEqual(len({row["id"] for row in rows}), 96)
        self.assertEqual({row["id"] for row in saved}, {row["id"] for row in rows})

    def test_pending_updates_from_stale_poll_preserve_new_submissions(self):
        poller = history.PendingStore(self.path)
        submitter = history.PendingStore(self.path)
        poller.upsert({"hash": "old", "last_pct": 0})
        stale = poller.list()
        submitter.upsert({"hash": "new", "last_pct": 0})
        for row in stale:
            poller.update(row["hash"], last_pct=50)
        self.assertEqual(poller.get("old")["last_pct"], 50)
        self.assertEqual(poller.get("new")["last_pct"], 0)
        poller.delete("old")
        self.assertEqual([row["hash"] for row in poller.list()], ["new"])

    def test_stale_upsert_preserves_progress_and_first_submission(self):
        store = history.PendingStore(self.path)
        store.upsert({"hash": "abc", "last_pct": 80, "added_at": "first"})
        result = store.upsert({"hash": "abc", "last_pct": 0, "added_at": "stale", "url": "synthetic"})
        self.assertEqual(result, {"hash": "abc", "last_pct": 80, "added_at": "first", "url": "synthetic"})

    def test_pending_concurrent_transactions_preserve_every_task(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda i: history.PendingStore(self.path).upsert({"hash": str(i)}), range(60)))
        self.assertEqual(len(history.PendingStore(self.path).list()), 60)

    def test_atomic_replace_failure_preserves_previous_file_and_propagates(self):
        store = history.PendingStore(self.path)
        store.upsert({"hash": "original"})
        original = self.path.read_bytes()
        with patch.object(history.os, "replace", side_effect=PermissionError("synthetic full disk")):
            with self.assertRaises(PermissionError):
                store.upsert({"hash": "new"})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_invalid_existing_file_is_not_overwritten(self):
        for payload in ("{", "{}", '["bad"]'):
            with self.subTest(payload=payload):
                self.path.write_text(payload, encoding="utf-8")
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    history.PendingStore(self.path).upsert({"hash": "new"})
                self.assertEqual(self.path.read_text(encoding="utf-8"), payload)

    def test_failed_mutator_does_not_commit_partial_changes(self):
        store = history.PendingStore(self.path)
        store.upsert({"hash": "original"})

        def mutate(rows):
            rows.clear()
            raise RuntimeError("synthetic operation failure")

        with self.assertRaises(RuntimeError):
            store.transaction(mutate)
        self.assertEqual(store.list(), [{"hash": "original"}])

    def test_read_and_return_values_are_detached_snapshots(self):
        store = history.PendingStore(self.path)
        row = store.upsert({"hash": "a", "nested": {"value": 1}})
        row["nested"]["value"] = 999
        store.list()[0]["nested"]["value"] = 888
        self.assertEqual(store.get("a")["nested"]["value"], 1)

    def test_history_limit_and_legacy_json_compatibility(self):
        rows = [{"id": str(i), "hash": "a" if i == 0 else "b"} for i in range(201)]
        self.path.write_text(json.dumps(rows), encoding="utf-8")
        store = history.RecordStore(self.path)
        last = store.add({"hash": "ABC", "title": "Synthetic"})
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))), 200)
        self.assertEqual(store.find_by_hash("abc")["id"], last["id"])
        self.assertTrue(store.update(last["id"], status="done"))
        self.assertEqual(store.get(last["id"])["status"], "done")
        self.assertTrue(store.delete(last["id"]))
        self.assertFalse(store.delete(last["id"]))
        self.assertEqual(store.clear(), 199)


if __name__ == "__main__":
    unittest.main()
