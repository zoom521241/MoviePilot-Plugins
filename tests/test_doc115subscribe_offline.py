"""Offline workflow acceptance using synthetic tasks/files and blocked networking."""
import base64
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_doc115subscribe_backend as backend

main = backend.main
boundary = SimpleNamespace(P115Transfer=main.P115Transfer,
                           OfflineSubmission=main.P115Transfer.offline_add.__globals__["OfflineSubmission"])
HASH = "0123456789abcdef0123456789abcdef01234567"
MAGNET = "magnet:?xt=urn:btih:" + HASH


class OfflineTests(unittest.TestCase):
    setUp = backend.BackendTests.setUp
    tearDown = backend.BackendTests.tearDown

    def cloud(self, **values):
        cloud = SimpleNamespace(
            list_tasks=Mock(return_value=[]), task_failed=boundary.P115Transfer.task_failed,
            path_to_id=Mock(return_value=42), file_in_directory=Mock(return_value=False),
            get_file_info=Mock(return_value={"id": "7", "parent_id": "42", "name": "Synthetic.mkv"}),
            move_via_p115disk=Mock(return_value=(True, "")), last_offline_result=None,
        )
        cloud.__dict__.update(values)
        self.plugin._transfers = Mock(return_value=cloud)
        return cloud

    def register(self, **values):
        history = self.plugin._records()
        row = history.add({"hash": HASH, "title": "Synthetic", "status": "downloading", "resource_key": "offline-synthetic"})
        item = {
            "hash": HASH, "record_id": row["id"], "title": "Synthetic",
            "staging_path": "/Synthetic/Staging", "final_path": "/Synthetic/Final",
            "status": "downloading", "created_ts": time.time(), "last_change_ts": time.time(),
            "resource_key": "offline-synthetic", "task_file_id": "7", "actual_cid": "42",
            **values,
        }
        self.plugin._pending().upsert(item)
        return item

    @staticmethod
    def finished_task(**values):
        return {"info_hash": HASH, "status": 0, "percentDone": 100,
                "name": "Synthetic.mkv", "file_id": "7", "wp_path_id": 42, **values}

    def test_real_falsey_uncertain_receipt_keeps_tracking_and_stops_mirror_fallback(self):
        cloud = self.cloud()

        def submit(kind, url, directory):
            cloud.last_offline_result = boundary.OfflineSubmission(info_hash=HASH, uncertain=True)
            raise main.P115Error("Synthetic response lost; result not confirmed")

        cloud.add_resource = Mock(side_effect=submit)
        record = backend.rec(links=[("magnet", MAGNET), ("115_share", "https://115.com/s/SYNTHETIC_FALLBACK")])
        ok, _message = self.plugin.do_transfer(record, "movie")
        self.assertFalse(ok)
        self.assertFalse(cloud.last_offline_result)
        cloud.add_resource.assert_called_once()
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "submitting")
        self.assertEqual(self.plugin._records().list()[0]["status"], "submitting")
        self.assertTrue(self.plugin._last_transfer_result["uncertain"])

    def test_uncertain_subscribed_offline_task_completes_after_recovery_without_new_sync(self):
        cloud = self.cloud()

        def submit(kind, url, directory):
            cloud.last_offline_result = boundary.OfflineSubmission(info_hash=HASH, uncertain=True)
            raise main.P115Error("Synthetic lost reply")

        cloud.add_resource = Mock(side_effect=submit)
        record = backend.rec(links=[("magnet", MAGNET)])
        backend.BackendTests.install_index(self, [record])
        backend.BackendTests.subscribe(self)
        response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["transferred"], 0)
        pending = self.plugin._pending().get(HASH)
        self.assertIsNotNone(pending)
        key = pending["subscription_key"]
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == key)
        self.assertEqual(state["status"], "pending")
        self.assertIn(pending["resource_key"], state["required_resources"])
        location = {"path": pending["staging_path"]}

        def move(src, dest, file_id=""):
            location["path"] = dest
            return True, ""

        cloud.list_tasks.return_value = [self.finished_task()]
        cloud.file_in_directory.side_effect = lambda fid, path: fid == "7" and path == location["path"]
        cloud.move_via_p115disk.side_effect = move
        self.plugin._process_offline(cloud, self.plugin._records())
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == key)
        self.assertEqual(state["status"], "complete")
        cloud.add_resource.assert_called_once()

    def test_uncertain_share_response_stops_offline_mirror_fallback(self):
        cloud = self.cloud(last_share_result={})

        def submit(kind, url, directory):
            cloud.last_share_result = {"uncertain": True, "received": 0, "total": 1}
            raise main.P115Error("Synthetic lost share reply")

        cloud.add_resource = Mock(side_effect=submit)
        record = backend.rec(links=[("115_share", "https://115.com/s/SYNTHETIC"), ("magnet", MAGNET)])
        ok, _message = self.plugin.do_transfer(record, "movie")
        self.assertFalse(ok)
        cloud.add_resource.assert_called_once()
        self.assertEqual(self.plugin._pending().list(), [])
        self.assertEqual(self.plugin._records().list()[0]["status"], "submitting")
        self.assertTrue(self.plugin._last_transfer_result["uncertain"])

    def test_partially_copied_share_stops_offline_mirror_fallback(self):
        cloud = self.cloud(last_share_result={})

        def submit(kind, url, directory):
            cloud.last_share_result = {"uncertain": False, "partial": True, "received": 200, "total": 201}
            raise main.P115Error("Synthetic partial share: 200/201 received")

        cloud.add_resource = Mock(side_effect=submit)
        record = backend.rec(links=[("115_share", "https://115.com/s/SYNTHETIC"), ("magnet", MAGNET)])
        ok, _message = self.plugin.do_transfer(record, "movie")
        self.assertFalse(ok)
        cloud.add_resource.assert_called_once()
        self.assertTrue(self.plugin._last_transfer_result["uncertain"])

    def test_async_move_is_not_complete_until_exact_file_reaches_destination(self):
        self.register()
        location = {"path": "/Synthetic/Staging"}
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           file_in_directory=Mock(side_effect=lambda fid, path: fid == "7" and path == location["path"]))
        first = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(first["finished"], 0)
        self.assertIsNotNone(self.plugin._pending().get(HASH))
        self.assertNotEqual(self.plugin._records().list()[0]["status"], "done")
        waiting = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(waiting["finished"], 0)
        cloud.move_via_p115disk.assert_called_once()
        location["path"] = "/Synthetic/Final"
        second = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(second["finished"], 1)
        self.assertIsNone(self.plugin._pending().get(HASH))
        self.assertEqual(self.plugin._records().list()[0]["status"], "done")
        cloud.move_via_p115disk.assert_called_once_with("/Synthetic/Staging/Synthetic.mkv", "/Synthetic/Final", file_id="7")

    def test_cookie_failure_status_two_is_terminal_without_move(self):
        self.register()
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task(status=2, percentDone=20)]))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["failed"], 1)
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "failed")
        cloud.move_via_p115disk.assert_not_called()

    def test_missing_task_has_grace_then_becomes_terminal(self):
        item = self.register()
        cloud = self.cloud()
        before = time.time()
        with patch.object(main.time, "time", return_value=before):
            first = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(first["failed"], 0)
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "downloading")
        with patch.object(main.time, "time", return_value=before + 3601):
            second = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(second["failed"], 1)
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "missing")
        cloud.move_via_p115disk.assert_not_called()

    def test_transient_exact_file_lookup_failure_preserves_active_task(self):
        self.register()
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           file_in_directory=Mock(side_effect=main.P115Error("Synthetic timeout")))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["failed"], 0)
        self.assertNotIn(self.plugin._pending().get(HASH)["status"], ("failed", "missing", "cancelled"))
        cloud.move_via_p115disk.assert_not_called()

    def test_task_list_outage_is_reported_without_discarding_queue(self):
        self.register()
        self.cloud(list_tasks=Mock(side_effect=main.P115Error("Synthetic task list timeout")))
        result = self.plugin.check_offline_tasks(force=True)
        self.assertEqual(result["code"], 1)
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "downloading")

    def test_deleting_display_history_keeps_task_and_subscription_completion(self):
        item = self.register(subscription_key="movie:synthetic")
        self.plugin._set_subscription("movie:synthetic", status="pending", required_resources=["offline-synthetic"])
        self.plugin.delete_record(item["record_id"])
        self.assertIsNotNone(self.plugin._pending().get(HASH))
        location = {"path": "/Synthetic/Staging"}

        def move(src, dest, file_id=""):
            location["path"] = dest
            return True, ""

        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           file_in_directory=Mock(side_effect=lambda fid, path: fid == "7" and location["path"] == path),
                           move_via_p115disk=Mock(side_effect=move))
        self.plugin._process_offline(cloud, self.plugin._records())
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == "movie:synthetic")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(self.plugin._records().list(), [])

    def test_all_links_partial_failure_stays_incomplete_after_successful_task_finishes(self):
        self.register(subscription_key="movie:synthetic")
        self.plugin._set_subscription("movie:synthetic", status="failed",
                                      required_resources=["offline-synthetic", "share-synthetic"])
        location = {"path": "/Synthetic/Staging"}

        def move(src, dest, file_id=""):
            location["path"] = dest
            return True, ""

        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           file_in_directory=Mock(side_effect=lambda fid, path: fid == "7" and location["path"] == path),
                           move_via_p115disk=Mock(side_effect=move))
        self.plugin._process_offline(cloud, self.plugin._records())
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == "movie:synthetic")
        self.assertNotEqual(state["status"], "complete")
        self.assertIn("offline-synthetic", state.get("completed_resources", []))
        self.assertNotIn("share-synthetic", state.get("completed_resources", []))
        self.plugin._mark_resource_complete("movie:synthetic", "share-synthetic")
        self.plugin._complete_subscription_if_ready("movie:synthetic")
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == "movie:synthetic")
        self.assertEqual(state["status"], "complete")

    def test_wrong_task_directory_is_terminal_and_never_moved(self):
        self.register()
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task(wp_path_id=99)]))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["failed"], 1)
        self.assertEqual(self.plugin._pending().get(HASH)["status"], "failed")
        cloud.move_via_p115disk.assert_not_called()

    def test_actual_file_id_name_is_used_instead_of_stale_task_name(self):
        self.register()
        location = {"path": "/Synthetic/Staging"}

        def move(src, dest, file_id=""):
            location["path"] = dest
            return True, ""

        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task(name="OldSynthetic.mkv")]),
                           get_file_info=Mock(return_value={"id": "7", "parent_id": "42", "name": "ActualSynthetic.mkv"}),
                           file_in_directory=Mock(side_effect=lambda fid, path: fid == "7" and location["path"] == path),
                           move_via_p115disk=Mock(side_effect=move))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["finished"], 1)
        cloud.move_via_p115disk.assert_called_once_with("/Synthetic/Staging/ActualSynthetic.mkv", "/Synthetic/Final", file_id="7")

    def test_invalid_exact_file_name_prevents_move(self):
        self.register()
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           get_file_info=Mock(return_value={"id": "7", "parent_id": "42", "name": "../Synthetic.mkv"}))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["failed"], 1)
        cloud.move_via_p115disk.assert_not_called()

    def test_legacy_pending_exact_file_already_in_final_is_recovered_without_move(self):
        self.register()
        cloud = self.cloud(list_tasks=Mock(return_value=[self.finished_task()]),
                           file_in_directory=Mock(side_effect=lambda fid, path: fid == "7" and path == "/Synthetic/Final"))
        result = self.plugin._process_offline(cloud, self.plugin._records())
        self.assertEqual(result["finished"], 1)
        self.assertIsNone(self.plugin._pending().get(HASH))
        cloud.move_via_p115disk.assert_not_called()

    def test_unverified_history_does_not_prove_subscription_complete(self):
        cloud = self.cloud(add_resource=Mock(return_value=(True, "Synthetic received")), last_share_names=["Synthetic"])
        record = backend.rec()
        ok, _ = self.plugin.do_transfer(record, "movie")
        self.assertTrue(ok)
        row = self.plugin._records().list()[0]
        self.plugin._records().update(row["id"], status="unverified")
        ok, _ = self.plugin.do_transfer({**record, "_subscription_key": "movie:unverified"}, "movie")
        self.assertFalse(ok)
        self.assertTrue(self.plugin._last_transfer_result["uncertain"])
        cloud.add_resource.assert_called_once()

    def test_legacy_organized_history_is_identified_and_not_copied_again(self):
        record = backend.rec()
        self.plugin._records().add({"title": record["title"], "year": record["year"],
            "type": "movie", "kind": "115_share", "url": record["links"][0][1],
            "final_path": self.plugin.build_save_path(record, "movie"),
            "status": "organized", "message": "Synthetic legacy inferred status"})
        cloud = self.cloud(add_resource=Mock(side_effect=AssertionError("Legacy resource must not be copied again")))
        ok, _message = self.plugin.do_transfer(record, "movie")
        self.assertFalse(ok)
        cloud.add_resource.assert_not_called()
        saved = self.plugin._records().list()[0]
        self.assertTrue(saved.get("resource_key"))
        self.assertEqual(saved["status"], "unverified")

    def test_all_mode_canonical_hash_dedupes_equivalent_magnet_links(self):
        cloud = self.cloud()

        def submit(kind, url, directory):
            cloud.last_offline_result = boundary.OfflineSubmission(accepted=True, info_hash=HASH,
                requested_cid="42", actual_cid="42", save_path=directory)
            return True, "Synthetic accepted"

        cloud.add_resource = Mock(side_effect=submit)
        self.plugin._link_mode = "all"
        b32 = base64.b32encode(bytes.fromhex(HASH)).decode()
        record = backend.rec(links=[("magnet", MAGNET), ("magnet", "magnet:?xt=urn:btih:" + b32 + "&tr=https://synthetic.invalid")])
        ok, _message = self.plugin.do_transfer(record, "movie")
        self.assertTrue(ok)
        cloud.add_resource.assert_called_once()
        self.assertEqual(len(self.plugin._last_transfer_result["required_resources"]), 1)
        self.assertEqual(len(self.plugin._pending().list()), 1)

    def test_manual_retry_successful_share_completes_failed_subscription(self):
        record = backend.rec(_subscription_key="movie:retry")
        cloud = self.cloud(last_share_result={}, last_share_names=["Synthetic"])
        cloud.add_resource = Mock(side_effect=main.P115Error("Synthetic explicit share failure"))
        self.assertFalse(self.plugin.do_transfer(record, "movie")[0])
        failed = self.plugin._records().list()[0]
        self.plugin._set_subscription("movie:retry", status="failed", required_resources=[failed["resource_key"]])
        cloud.add_resource.side_effect = None
        cloud.add_resource.return_value = (True, "Synthetic received")
        result = self.plugin.api_retry_task({"id": failed["id"]})
        self.assertEqual(result["code"], 0)
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == "movie:retry")
        self.assertEqual(state["status"], "complete")

    def test_manual_retry_cancelled_offline_reactivates_subscription(self):
        record = backend.rec(_subscription_key="movie:retry", links=[("magnet", MAGNET)])
        cloud = self.cloud()

        def submit(kind, url, directory):
            cloud.last_offline_result = boundary.OfflineSubmission(accepted=True, info_hash=HASH,
                requested_cid="42", actual_cid="42", save_path=directory)
            return True, "Synthetic accepted"

        cloud.add_resource = Mock(side_effect=submit)
        self.assertTrue(self.plugin.do_transfer(record, "movie")[0])
        original = self.plugin._records().list()[0]
        self.plugin._set_subscription("movie:retry", status="pending", required_resources=[original["resource_key"]])
        self.assertEqual(self.plugin.api_cancel_task({"id": original["id"]})["code"], 0)
        self.assertEqual(self.plugin.api_retry_task({"id": original["id"]})["code"], 0)
        state = next(x for x in self.plugin._subscription_store().list() if x["key"] == "movie:retry")
        self.assertEqual(state["status"], "pending")

    def test_no_active_pending_does_not_construct_or_contact_cloud_client(self):
        self.register(status="failed")
        self.plugin._transfers = Mock(side_effect=AssertionError("Cloud must not be consulted"))
        response = self.plugin.check_offline_tasks(force=True)
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["pending"], 0)
        self.plugin._transfers.assert_not_called()


if __name__ == "__main__":
    unittest.main()
