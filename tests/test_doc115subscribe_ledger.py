"""White-box transactions and public ledger contracts with synthetic data."""
import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from test_doc115subscribe_organization import PACKAGE, SOURCE, batch, evidence, manifest
import sys

spec = importlib.util.spec_from_file_location(PACKAGE + ".ledger", SOURCE / "ledger.py")
ledger_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ledger_module
spec.loader.exec_module(ledger_module)
TaskLedger = ledger_module.TaskLedger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-ledger-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private.sqlite3"
        self.ledger = TaskLedger(self.path)

    def claimed(self, key="synthetic-resource", **context):
        with patch.object(ledger_module.time, "time", return_value=1000):
            return self.ledger.claim_resource(key, {**batch(), **context}, generation=3)

    def test_parallel_claims_have_exactly_one_intent_and_batch(self):
        start = Barrier(10)
        def claim(_):
            store = TaskLedger(self.path)
            start.wait(timeout=5)
            return store.claim_resource("same-resource", batch(), generation=0)
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(claim, range(10)))
        self.assertEqual(sum(row["claimed"] for row in results), 1)
        self.assertEqual(len(self.ledger.list(limit=None)), 1)
        self.assertEqual(len(self.ledger.attempts(results[0]["batch"]["id"])), 1)

    def test_queue_reservation_does_not_claim_that_request_was_sent(self):
        result = self.ledger.prepare_resource("key", batch(), generation=3)
        self.assertTrue(result["claimed"])
        self.assertEqual(result["batch"]["acquisition_status"], "queued")
        self.assertEqual(self.ledger.attempts(result["batch"]["id"]), [])
        self.assertFalse(self.ledger.prepare_resource("key", batch(), generation=3)["claimed"])
        attempt = self.ledger.begin_attempt(result["batch"]["id"], generation=3, kind="submit", intent={"synthetic": True})
        self.assertEqual(attempt["kind"], "submit")
        self.assertEqual(attempt["intent"], {"synthetic": True})
        self.assertEqual(self.ledger.get(result["batch"]["id"])["status"], "submitting")

    def test_submission_intent_survives_restart_and_lease_expiry(self):
        result = self.claimed()
        restarted = TaskLedger(self.path)
        self.assertFalse(restarted.claim_resource("synthetic-resource", batch(), generation=3)["claimed"])
        with self.assertRaises(ValueError):
            restarted.begin_attempt(result["batch"]["id"], generation=3)

    def test_share_submission_intent_persists_submitting_before_actual_http(self):
        prepared = self.ledger.prepare_resource("share-intent", batch(), generation=3)
        attempt = self.ledger.begin_attempt(prepared["batch"]["id"], phase="share_receive", generation=3)
        restarted = TaskLedger(self.path)
        current = restarted.get(prepared["batch"]["id"])
        self.assertEqual(current["acquisition_status"], "submitting")
        self.assertEqual(current["status"], "submitting")
        self.assertEqual(current["active_attempt_id"], attempt["attempt_id"])
        with self.assertRaises(ValueError):
            restarted.begin_attempt(current["id"], phase="share_receive", generation=3)

    def test_move_intent_persists_moving_and_recovery_only_can_query(self):
        prepared = self.claimed()
        batch_id = prepared["batch"]["id"]
        self.ledger.save_receipt(prepared["attempt"]["attempt_id"], "accepted", {})
        attempt = self.ledger.begin_attempt(batch_id, phase="move", generation=3)
        restarted = TaskLedger(self.path)
        current = restarted.get(batch_id)
        self.assertEqual((current["status"], current["acquisition_status"], current["move_status"]), ("moving", "moving", "moving"))
        self.assertEqual(current["active_attempt_id"], attempt["attempt_id"])
        with self.assertRaises(ValueError):
            restarted.begin_attempt(batch_id, phase="move", generation=3)

    def test_queued_day_old_same_path_history_before_submit_is_not_ours(self):
        prepared = self.ledger.prepare_resource("delayed", {**batch(1), "created_ts": 1000}, generation=3)
        batch_id = prepared["batch"]["id"]
        with patch.object(ledger_module.time, "time", return_value=87400):
            self.ledger.begin_attempt(batch_id, phase="share_receive", generation=3)
        projection = self.ledger.record_evidence(batch_id, [evidence(1, stamp=5000)])
        self.assertEqual(projection["organized_count"], 0)
        self.assertFalse(projection["organization_confirmed"])
        projection = self.ledger.record_evidence(batch_id, [evidence(1, stamp=87500)])
        self.assertEqual(projection["organized_count"], 1)
        self.assertTrue(projection["organization_confirmed"])

    def test_uncertain_response_holds_resource_and_cannot_retry_blindly(self):
        result = self.claimed()
        saved = self.ledger.save_receipt(result["attempt"]["attempt_id"], "uncertain", {"message": "合成超时"})
        self.assertEqual(saved["batch"]["acquisition_status"], "uncertain")
        self.assertFalse(self.claimed()["claimed"])
        with self.assertRaises(ValueError):
            self.ledger.begin_attempt(saved["batch"]["id"], generation=3)

    def test_receipt_saved_after_stop_without_rescheduling_or_overwriting_stop(self):
        result = self.claimed()
        batch_id = result["batch"]["id"]
        self.ledger.update(batch_id, tracking_enabled=False, status="cancelled", next_check_at=0)
        receipt = self.ledger.save_receipt(result["attempt"]["attempt_id"], "success", {"task_file_id": "20", "next_check_at": 9999, "message": "完成"})
        self.assertFalse(receipt["current_generation"])
        self.assertEqual(receipt["batch"]["acquisition_status"], "saved")
        self.assertEqual(receipt["batch"]["status"], "cancelled")
        self.assertEqual(receipt["batch"]["next_check_at"], 0)
        self.assertEqual(receipt["batch"]["task_file_id"], "20")
        self.assertEqual(self.ledger.attempts(batch_id)[0]["outcome"], "success")

    def test_receipt_saved_after_configuration_generation_change(self):
        result = self.claimed()
        self.ledger.update(result["batch"]["id"], config_generation=4, next_check_at=0, message="新配置")
        receipt = self.ledger.save_receipt(result["attempt"]["attempt_id"], "accepted", {"task_id": "20", "next_check_at": 9999, "message": "旧回执"}, generation=4)
        self.assertFalse(receipt["current_generation"])
        self.assertEqual(receipt["batch"]["acquisition_status"], "downloading")
        self.assertEqual(receipt["batch"]["message"], "新配置")
        self.assertEqual(receipt["batch"]["next_check_at"], 0)

    def test_stopped_share_partial_receipt_preserves_chunk_cursor_for_resume(self):
        prepared = self.ledger.prepare_resource("share", batch(), generation=3)
        batch_id = prepared["batch"]["id"]
        first = self.ledger.begin_attempt(batch_id, phase="share_receive", generation=3)
        self.ledger.update(batch_id, tracking_enabled=False, status="cancelled", config_generation=4)
        state = {"items": [{"id": str(n), "name": f"合成{n}"} for n in range(201)], "received": 200, "done": False}
        result = self.ledger.save_receipt(first["attempt_id"], "success", {"share_state": state, "done": False, "received": 200}, generation=3)
        self.assertFalse(result["current_generation"])
        self.assertEqual(result["batch"]["share_state"]["received"], 200)
        self.assertEqual(result["batch"]["acquisition_status"], "queued")
        self.assertEqual(result["batch"]["status"], "cancelled")
        restarted = TaskLedger(self.path)
        self.assertEqual(restarted.get(batch_id)["share_state"]["received"], 200)
        restarted.update(batch_id, tracking_enabled=True, status="queued", config_generation=4)
        second = restarted.begin_attempt(batch_id, phase="share_receive", generation=4)
        state.update(received=201, done=True)
        result = restarted.save_receipt(second["attempt_id"], "success", {"share_state": state, "done": True}, generation=4)
        self.assertEqual(result["batch"]["acquisition_status"], "saved")
        self.assertEqual(result["batch"]["share_state"]["received"], 201)
        self.assertFalse(restarted.prepare_resource("share", batch(), generation=4)["claimed"])

    def test_share_final_receipt_after_stop_preserves_acquired_fact(self):
        prepared = self.ledger.prepare_resource("share", batch(), generation=3)
        batch_id = prepared["batch"]["id"]
        attempt = self.ledger.begin_attempt(batch_id, phase="share_receive", generation=3)
        self.ledger.update(batch_id, tracking_enabled=False, status="cancelled")
        result = self.ledger.save_receipt(attempt["attempt_id"], "success", {"share_state": {"received": 20, "done": True}, "done": True}, generation=3)
        self.assertEqual(result["batch"]["acquisition_status"], "saved")
        self.assertEqual(result["batch"]["status"], "cancelled")
        self.assertFalse(result["current_generation"])

    def test_success_cannot_be_downgraded_by_late_duplicate_failure(self):
        result = self.claimed()
        attempt_id = result["attempt"]["attempt_id"]
        self.ledger.save_receipt(attempt_id, "success", {"file_id": "123"})
        self.ledger.save_receipt(attempt_id, "failure", {"message": "晚到旧错误"})
        self.assertEqual(self.ledger.get(result["batch"]["id"])["acquisition_status"], "saved")
        self.assertEqual(self.ledger.attempts(result["batch"]["id"])[0]["outcome"], "success")

    def test_move_receipt_and_organization_failure_do_not_erase_acquisition(self):
        result = self.claimed()
        batch_id = result["batch"]["id"]
        self.ledger.save_receipt(result["attempt"]["attempt_id"], "accepted", {"task_file_id": "20"})
        attempt = self.ledger.begin_attempt(batch_id, kind="move", generation=3)
        self.ledger.save_receipt(attempt["attempt_id"], "success", {})
        self.ledger.set_manifest(batch_id, manifest(), complete=True)
        projection = self.ledger.record_evidence(batch_id, [evidence(n, False) for n in range(1, 21)], pagination_complete=True)
        self.assertEqual(projection["organization_status"], "failed")
        self.assertEqual(projection["acquisition_status"], "saved")
        self.assertEqual(projection["status"], "done")
        self.assertFalse(self.claimed()["claimed"])
        with self.assertRaises(ValueError):
            self.ledger.begin_attempt(batch_id, kind="submit", generation=3)
        with self.assertRaises(ValueError):
            self.ledger.begin_attempt(batch_id, kind="move", generation=3)

    def test_deleting_or_trimming_visible_history_does_not_remove_resource_hold(self):
        result = self.claimed()
        self.assertTrue(self.ledger.delete(result["batch"]["id"]))
        self.assertEqual(self.ledger.list(), [])
        self.assertEqual(len(self.ledger.list(include_hidden=True)), 1)
        self.assertFalse(self.claimed()["claimed"])
        for n in range(205):
            self.ledger.prepare_resource(f"resource-{n}", {"title": f"合成电影{n}"})
        self.assertEqual(len(self.ledger.list()), 200)
        self.assertEqual(len(self.ledger.list(limit=None, include_hidden=True)), 206)
        self.assertEqual(self.ledger.clear(), 205)
        self.assertFalse(self.ledger.prepare_resource("resource-0", {})["claimed"])

    def test_compare_and_swap_revision_rejects_stale_projection(self):
        result = self.claimed()
        batch_id = result["batch"]["id"]
        old = self.ledger.get(batch_id)
        self.ledger.update(batch_id, tracking_enabled=False)
        self.assertFalse(self.ledger.update(batch_id, expected_revision=old["revision"], tracking_enabled=True))
        self.assertFalse(self.ledger.get(batch_id)["tracking_enabled"])

    def test_twenty_episode_deletion_after_manifest_does_not_shrink_expectation(self):
        result = self.claimed()
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(), complete=True)
        self.ledger.set_manifest(batch_id, manifest(19), complete=True)
        self.assertEqual(len(self.ledger.get_manifest(batch_id)["items"]), 20)
        projection = self.ledger.record_evidence(batch_id, [evidence(n) for n in range(1, 20)], pagination_complete=True)
        self.assertEqual((projection["organization_status"], projection["organized_count"], projection["organized_total"]), ("partial", 19, 20))
        self.assertFalse(self.claimed()["claimed"])

    def test_deleted_before_scan_expected_episode_count_prevents_false_nineteen_success(self):
        result = self.claimed(manifest=[], manifest_complete=False, expected_episode_count=20)
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(19), complete=True)
        projection = self.ledger.record_evidence(batch_id, [evidence(n) for n in range(1, 20)], pagination_complete=True)
        self.assertFalse(projection["manifest_complete"])
        self.assertFalse(projection["organization_confirmed"])
        self.assertIsNone(projection["organized_total"])
        self.assertFalse(self.claimed()["claimed"])

    def test_two_manifest_pages_validate_merged_twenty_episode_expectation(self):
        result = self.claimed(manifest=[], manifest_complete=False, expected_episodes=list(range(1, 21)))
        batch_id = result["batch"]["id"]
        original = manifest()
        first = self.ledger.append_manifest(batch_id, original[:10], complete=False)
        self.assertFalse(first["manifest_complete"])
        final = self.ledger.append_manifest(batch_id, original[10:], complete=True)
        self.assertTrue(final["manifest_complete"])
        self.assertEqual(len(final["manifest"]), 20)
        projection = self.ledger.record_evidence(batch_id, [evidence(n) for n in range(1, 21)])
        self.assertTrue(projection["organization_confirmed"])

    def test_target_file_id_enrichment_keeps_one_expected_unit_and_original_key(self):
        result = self.claimed(manifest=[], manifest_complete=False)
        batch_id = result["batch"]["id"]
        initial = manifest(1)
        initial[0]["file_id"] = ""
        initial[0].pop("unit_key")
        first = self.ledger.set_manifest(batch_id, initial, complete=True)
        key = first["manifest"][0]["unit_key"]
        final = self.ledger.append_manifest(batch_id, manifest(1), complete=True)
        self.assertTrue(final["manifest_complete"])
        self.assertEqual(len(final["manifest"]), 1)
        self.assertEqual(final["manifest"][0]["unit_key"], key)
        self.assertEqual(final["manifest"][0]["file_id"], "1")
        self.assertTrue(self.ledger.record_evidence(batch_id, [evidence(1)])["organization_confirmed"])

    def test_conflicting_same_path_file_id_is_retained_as_conflict_not_overwritten(self):
        result = self.claimed(manifest=[], manifest_complete=False)
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(1), complete=True)
        incoming = manifest(1)
        incoming[0]["file_id"] = "999"
        final = self.ledger.append_manifest(batch_id, incoming, complete=True)
        self.assertFalse(final["manifest_complete"])
        self.assertEqual(final["manifest"][0]["file_id"], "1")
        self.assertEqual(len(final["manifest"]), 1)
        self.assertEqual(final["manifest_conflicts"][0]["observed_file_id"], "999")

    def test_failed_file_recovers_and_duplicate_old_history_cannot_regress_it(self):
        result = self.claimed()
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(), complete=True)
        self.ledger.record_evidence(batch_id, [evidence(n) for n in range(1, 20)] + [evidence(20, False)])
        projection = self.ledger.record_evidence(batch_id, [evidence(20, True, 1200)])
        self.assertTrue(projection["organization_confirmed"])
        projection = self.ledger.record_evidence(batch_id, [evidence(20, False, 1100)])
        self.assertTrue(projection["organization_confirmed"])
        self.assertEqual(projection["organized_count"], 20)

    def test_unknown_order_late_failed_event_does_not_regress_success(self):
        result = self.claimed(manifest=[], manifest_complete=False)
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(1), complete=True)
        self.ledger.record_evidence(batch_id, [evidence(1, True, 1200)])
        projection = self.ledger.record_evidence(batch_id, [evidence(1, False, 1500, time_is_observed=True)])
        self.assertTrue(projection["organization_confirmed"])
        projection = self.ledger.record_evidence(batch_id, [evidence(1, False, 2000, id="unknown-event", time_is_observed=True)])
        self.assertTrue(projection["organization_confirmed"])

    def test_credible_history_success_recovers_later_observed_failure(self):
        result = self.claimed(manifest=[], manifest_complete=False)
        batch_id = result["batch"]["id"]
        self.ledger.set_manifest(batch_id, manifest(1), complete=True)
        self.ledger.record_evidence(batch_id, [evidence(1, False, 2000, time_is_observed=True)])
        projection = self.ledger.record_evidence(batch_id, [evidence(1, True, 1200)])
        self.assertTrue(projection["organization_confirmed"])

    def test_early_event_stays_in_inbox_until_acknowledged_after_manifest(self):
        payload = evidence(1)
        self.assertTrue(self.ledger.enqueue_event("event-1", payload))
        self.assertFalse(self.ledger.enqueue_event("event-1", payload))
        self.assertEqual(len(TaskLedger(self.path).drain_events()), 1)
        result = self.claimed(manifest=[], manifest_complete=False)
        self.ledger.set_manifest(result["batch"]["id"], manifest(1), complete=True)
        event = self.ledger.drain_events()[0]
        projection = self.ledger.record_evidence(result["batch"]["id"], [event["payload"]])
        self.assertTrue(projection["organization_confirmed"])
        self.ledger.ack_event(event["event_id"])
        self.assertEqual(self.ledger.drain_events(), [])

    def test_unassociated_first_fifty_events_do_not_starve_new_related_event(self):
        for number in range(51):
            self.ledger.enqueue_event(f"early-{number:02d}", {"synthetic": number})
        self.ledger.enqueue_event("later-related", evidence(1))
        first = self.ledger.drain_events(50)
        second = self.ledger.drain_events(50)
        self.assertNotIn("later-related", {entry["event_id"] for entry in first})
        self.assertIn("later-related", {entry["event_id"] for entry in second})
        self.assertEqual(self.ledger.event_counts()["pending"], 52)

    def test_event_inbox_cap_and_acknowledged_retention_are_bounded(self):
        self.ledger.MAX_PENDING_EVENTS = 3
        self.ledger.MAX_ACKNOWLEDGED_EVENTS = 2
        for number in range(3):
            self.assertTrue(self.ledger.enqueue_event(str(number), {"synthetic": number}))
        self.assertFalse(self.ledger.enqueue_event("overflow", {"synthetic": 4}))
        self.assertEqual(self.ledger.event_counts(), {"pending": 3, "acknowledged": 0, "overflow": 1})
        for number in range(3):
            self.ledger.ack_event(str(number))
        self.assertEqual(self.ledger.event_counts()["acknowledged"], 2)
        self.assertTrue(self.ledger.enqueue_event("new", {"synthetic": 5}))
        with patch.object(ledger_module.time, "time", return_value=time.time() + 86401):
            self.ledger.drain_events()
        self.assertEqual(self.ledger.event_counts()["acknowledged"], 0)
        self.assertEqual(self.ledger.event_counts()["pending"], 1)

    def test_migration_is_local_atomic_idempotent_and_retains_acquired_protection(self):
        records = Path(self.temp.name) / "records.json"
        pending = Path(self.temp.name) / "pending.json"
        old_rows = [{"id": "old-done", "resource_key": "resource1", "status": "organized", "organization_confirmed": True, "quality_score": 100},
                    {"id": "old-failure", "resource_key": "resource2", "status": "failed", "moved_at": 1000},
                    {"id": "old-unknown", "resource_key": "resource3", "status": "unfound"}]
        records.write_text(json.dumps(old_rows), encoding="utf-8")
        pending.write_text(json.dumps([{"hash": "abc", "record_id": "pending-only", "status": "cancelled"}]), encoding="utf-8")
        original = records.read_bytes()
        migrated = self.ledger.migrate_json(records, pending)
        self.assertEqual(migrated, {"imported": 4, "pending": 1, "already_migrated": False})
        self.assertEqual(records.read_bytes(), original)
        self.assertTrue(self.ledger.migrate_json(records, pending)["already_migrated"])
        self.assertEqual(self.ledger.get("old-done")["acquisition_status"], "saved")
        self.assertFalse(self.ledger.get("old-done")["organization_confirmed"])
        self.assertFalse(self.ledger.get("old-done")["actual_quality_verified"])
        self.assertEqual(self.ledger.get("old-failure")["acquisition_status"], "saved")
        self.assertFalse(self.ledger.get("pending-only")["tracking_enabled"])
        self.assertEqual(self.ledger.attempts("old-done"), [])
        for key in ("resource1", "resource2", "resource3"):
            self.assertFalse(self.ledger.claim_resource(key, {})["claimed"])

    def test_migration_paired_pending_enriches_exact_identity_and_preserves_stop(self):
        records = Path(self.temp.name) / "records.json"
        pending = Path(self.temp.name) / "pending.json"
        records.write_text(json.dumps([{"id": "active", "hash": "abc", "status": "downloading", "resource_key": "active-key"},
                                      {"id": "stopped", "hash": "def", "status": "downloading", "resource_key": "stopped-key"},
                                      {"id": "saved", "hash": "ghi", "status": "done", "moved_at": 1100, "resource_key": "saved-key"}]), encoding="utf-8")
        tasks = [{"record_id": "active", "hash": "abc", "status": "moving", "task_file_id": "123", "actual_cid": "42", "final_path": "/下载/合成"},
                 {"record_id": "stopped", "hash": "def", "status": "cancelled", "task_file_id": "456"},
                 {"record_id": "saved", "hash": "ghi", "status": "failed", "task_file_id": "789"}]
        pending.write_text(json.dumps(tasks), encoding="utf-8")
        original_records, original_pending = records.read_bytes(), pending.read_bytes()
        result = self.ledger.migrate_json(records, pending)
        self.assertEqual(result["imported"], 3)
        active = self.ledger.get("active")
        self.assertEqual((active["task_file_id"], active["actual_cid"], active["acquisition_status"]), ("123", "42", "downloading"))
        self.assertEqual(active["legacy_pending_snapshot"]["status"], "moving")
        self.assertFalse(self.ledger.get("stopped")["tracking_enabled"])
        self.assertEqual(self.ledger.get("saved")["acquisition_status"], "saved")
        self.assertEqual(self.ledger.get("saved")["task_file_id"], "789")
        self.assertEqual((records.read_bytes(), pending.read_bytes()), (original_records, original_pending))

    def test_invalid_json_and_disk_error_abort_migration_and_claim(self):
        records = Path(self.temp.name) / "records.json"
        records.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ledger.migrate_json(records)
        records.write_text(json.dumps([{"id": "one"}, {"id": "two"}]), encoding="utf-8")
        original_insert = self.ledger._insert
        def fail_second(db, context, *args):
            if context.get("id") == "two":
                raise sqlite3.OperationalError("synthetic disk full")
            return original_insert(db, context, *args)
        with patch.object(self.ledger, "_insert", side_effect=fail_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.ledger.migrate_json(records)
        self.assertEqual(self.ledger.list(limit=None), [])
        self.assertEqual(self.ledger.migrate_json(records)["imported"], 2)

    def test_legacy_resource_key_change_and_unknown_account_still_block_resubmission(self):
        records = Path(self.temp.name) / "records.json"
        records.write_text(json.dumps([{"id": "legacy", "status": "unfound", "hash": "ABC", "final_path": "/下载/合成剧", "url": "magnet:synthetic", "kind": "magnet"}]), encoding="utf-8")
        self.ledger.migrate_json(records)
        context = {"hash": "abc", "account_key": "new-key-format", "final_path": "/下载/合成剧"}
        result = self.ledger.prepare_resource("new-canonical-key", context)
        self.assertFalse(result["claimed"])
        self.assertEqual(result["batch"]["id"], "legacy")
        self.assertEqual(self.ledger.find_by_resource("new-canonical-key")["id"], "legacy")
        self.assertTrue(self.ledger.prepare_resource("explicitly-other-target", {**context, "final_path": "/其他目录"})["claimed"])

    def test_unsupported_future_schema_is_rejected_without_altering_it(self):
        future = Path(self.temp.name) / "future.sqlite3"
        with closing(sqlite3.connect(future)) as db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT)")
            db.execute("INSERT INTO metadata VALUES('schema_version','99')")
            db.commit()
        with self.assertRaises(ValueError):
            TaskLedger(future)
        with closing(sqlite3.connect(future)) as db:
            self.assertEqual([row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")], ["metadata"])

    def test_backup_is_consistent_and_return_values_are_detached(self):
        result = self.claimed()
        result["batch"]["title"] = "外部修改"
        self.assertNotEqual(self.ledger.get(result["attempt"]["batch_id"])["title"], "外部修改")
        backup = Path(self.temp.name) / "snapshot.sqlite3"
        self.ledger.backup(backup)
        self.assertEqual(TaskLedger(backup).list(), self.ledger.list())


if __name__ == "__main__":
    unittest.main()
