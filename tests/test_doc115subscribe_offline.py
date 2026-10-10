"""Persistent offline stages with synthetic files and all network blocked.

Original workflow regressions adapted to asynchronous acceptance and explicit
worker ticks, retaining their success, failure, recovery and dedupe assertions.
"""
import base64
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

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
        cloud = backend.SyntheticTransfer(values.pop("outcomes", None))
        cloud.location = "staging"
        cloud.list_tasks_slice = Mock(return_value={"items": [], "cursor": None, "complete": True})
        cloud.task_failed = boundary.P115Transfer.task_failed
        cloud.path_to_id = Mock(side_effect=lambda path, mkdir=False: 99 if "/Final" in path else 42)
        cloud.get_file_info = Mock(side_effect=lambda fid: {"id": "7", "parent_id": "42" if cloud.location == "staging" else "99", "name": "Synthetic.mkv", "type": "file"})
        cloud.move_via_p115disk = Mock(return_value=(True, ""))
        cloud.manifest_slice = Mock(side_effect=lambda src, **kwargs: {"items": [{"path": src, "file_id": "7", "name": "Synthetic.mkv", "required": True, "role": "movie"}], "cursor": None, "complete": True})
        cloud.__dict__.update(values)
        self.plugin._transfers = Mock(return_value=cloud)
        return cloud

    def register(self, **values):
        status = values.get("status", "downloading")
        return self.plugin._records().add({"hash": HASH, "kind": "magnet", "url": MAGNET,
            "title": "Synthetic", "year": "2025", "type": "movie", "status": status,
            "acquisition_status": status, "staging_path": "/Synthetic/Staging", "final_path": "/Synthetic/Final",
            "source_storage": "115网盘Plus", "resource_key": "offline-synthetic", "task_file_id": "7", "actual_cid": "42",
            "config_generation": self.plugin._generation, "next_check_at": 0, **values})

    def tick(self, ticks=1):
        for row in self.plugin._records().list(limit=None, include_hidden=True):
            self.plugin._records().update(row["id"], next_check_at=0)
        return backend.drive_worker(self.plugin, ticks=ticks)

    @staticmethod
    def finished_task(**values):
        return {"info_hash": HASH, "status": 0, "percentDone": 100,
                "name": "Synthetic.mkv", "file_id": "7", "wp_path_id": 42, **values}

    def finish_cloud(self, cloud):
        cloud.list_tasks_slice.return_value = {"items": [self.finished_task()], "cursor": None, "complete": True}
        def move(*args, **kwargs):
            cloud.location = "final"
            return True, ""
        cloud.move_via_p115disk.side_effect = move

    def uncertain_offline(self, cloud):
        def submit(url, directory, before_submit=None):
            if before_submit:
                before_submit({"kind": "offline_add", "hash": HASH})
            cloud.calls.append(("magnet", url, directory))
            cloud.last_offline_result = boundary.OfflineSubmission(info_hash=HASH, uncertain=True)
            error = main.P115Error("Synthetic response lost; result not confirmed")
            error.uncertain = True
            raise error
        cloud.offline_add = Mock(side_effect=submit)

    def test_real_falsey_uncertain_receipt_keeps_tracking_and_stops_mirror_fallback(self):
        cloud = self.cloud()
        self.uncertain_offline(cloud)
        record = backend.rec(links=[("magnet", MAGNET), ("115_share", "https://115.com/s/SYNTHETIC_FALLBACK")])
        self.assertTrue(self.plugin.do_transfer(record, "movie")[0])
        self.assertEqual(cloud.calls, [])
        self.tick()
        self.assertFalse(cloud.last_offline_result)
        cloud.offline_add.assert_called_once()
        self.assertEqual(self.plugin._records().list()[0]["acquisition_status"], "uncertain")
        self.tick()
        cloud.offline_add.assert_called_once()
        self.assertEqual(len(cloud.calls), 1)

    def test_uncertain_subscribed_offline_task_completes_after_recovery_without_new_sync(self):
        cloud = self.cloud()
        self.uncertain_offline(cloud)
        backend.BackendTests.install_index(self, [backend.rec(links=[("magnet", MAGNET)])])
        backend.BackendTests.subscribe(self)
        response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["transferred"], 1)
        self.tick()
        item = self.plugin._records().list()[0]
        state = self.plugin._subscription_store().list()[0]
        self.assertEqual(state["status"], "pending")
        self.assertIn(item["resource_key"], state["required_resources"])
        self.finish_cloud(cloud)
        # User-selected default final path is mapped to a distinct synthetic CID.
        cloud.path_to_id.side_effect = lambda path, mkdir=False: 42 if path == item["staging_path"] else 99
        self.tick(ticks=2)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")
        cloud.offline_add.assert_called_once()

    def test_uncertain_share_response_stops_offline_mirror_fallback(self):
        cloud = self.cloud()
        def submit(url, directory, state, before_submit=None):
            before_submit({"kind": "share_receive"})
            cloud.calls.append(("115_share", url, directory))
            cloud.last_share_result = {"uncertain": True, "received": 0, "total": 1}
            error = main.P115Error("Synthetic lost share reply")
            error.uncertain = True
            error.state = {**state, "uncertain": True}
            raise error
        cloud.receive_prepared = Mock(side_effect=submit)
        self.assertTrue(self.plugin.do_transfer(backend.rec(links=[("115_share", "https://115.com/s/SYNTHETIC"), ("magnet", MAGNET)]), "movie")[0])
        self.tick(ticks=2)
        cloud.receive_prepared.assert_called_once()
        self.assertEqual(len(cloud.calls), 1)
        self.assertEqual(self.plugin._records().list()[0]["acquisition_status"], "uncertain")

    def test_partially_copied_share_stops_offline_mirror_fallback(self):
        cloud = self.cloud()
        def submit(url, directory, state, before_submit=None):
            before_submit({"kind": "share_receive"})
            cloud.calls.append(("115_share", url, directory))
            cloud.last_share_result = {"uncertain": False, "partial": True, "received": 200, "total": 201}
            error = main.P115Error("Synthetic partial share: 200/201 received")
            error.state = {**state, "received": 200, "done": False}
            raise error
        cloud.receive_prepared = Mock(side_effect=submit)
        self.plugin.do_transfer(backend.rec(links=[("115_share", "https://115.com/s/SYNTHETIC"), ("magnet", MAGNET)]), "movie")
        self.tick(ticks=2)
        cloud.receive_prepared.assert_called_once()
        self.assertEqual(self.plugin._records().list()[0]["share_state"]["received"], 200)
        self.assertEqual(self.plugin._records().list()[0]["acquisition_status"], "uncertain")

    def test_async_move_is_not_complete_until_exact_file_reaches_destination(self):
        item = self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task()], "complete": True, "cursor": None}))
        self.tick()
        self.assertNotEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        self.tick()
        cloud.move_via_p115disk.assert_called_once()
        cloud.location = "final"
        self.tick()
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        cloud.move_via_p115disk.assert_called_once_with("/Synthetic/Staging/Synthetic.mkv", "/Synthetic/Final", file_id="7")

    def test_failed_status_minus_one_is_terminal_without_move(self):
        item = self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task(status=-1, percentDone=20)], "complete": True, "cursor": None}))
        self.tick()
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "failed")
        cloud.move_via_p115disk.assert_not_called()

    def test_real_shape_status_two_is_finished_and_moves(self):
        # Shape observed from a real read-only clouddownload_task_list: status 2 = finished.
        item = self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task(
            status=2, percentDone=100, move=1, display_status="已完成", left_time=0, peers=0)],
            "complete": True, "cursor": None}))
        self.tick(ticks=2)
        self.assertNotEqual(self.plugin._records().get(item["id"])["acquisition_status"], "failed")
        cloud.move_via_p115disk.assert_called_once()

    def test_missing_task_has_grace_and_never_erases_unconfirmed_submission(self):
        item = self.register(task_file_id="")
        cloud = self.cloud(get_file_info=Mock(return_value=None))
        self.tick()
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "downloading")
        self.tick(ticks=3)
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "downloading")
        cloud.move_via_p115disk.assert_not_called()
        self.assertFalse(self.plugin._records().prepare_resource("offline-synthetic", {})["claimed"])

    def test_transient_exact_file_lookup_failure_preserves_active_task(self):
        item = self.register()
        cloud = self.cloud(get_file_info=Mock(side_effect=main.P115Error("Synthetic timeout")))
        result = self.tick()[0]
        self.assertEqual(result["code"], 1)
        current = self.plugin._records().get(item["id"])
        self.assertEqual(current["acquisition_status"], "downloading")
        self.assertGreater(current["next_check_at"], time.time())
        cloud.move_via_p115disk.assert_not_called()

    def test_task_list_outage_is_reported_without_discarding_queue(self):
        item = self.register(task_file_id="")
        self.cloud(list_tasks_slice=Mock(side_effect=main.P115Error("Synthetic task list timeout")))
        result = self.tick()[0]
        self.assertEqual(result["code"], 1)
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "downloading")
        self.assertIn("Synthetic task list timeout", self.plugin._records().get(item["id"])["query_error"])

    def test_deleting_display_history_keeps_task_and_subscription_completion(self):
        item = self.register(subscription_key="movie:synthetic")
        self.plugin._set_subscription("movie:synthetic", status="pending", required_resources=["offline-synthetic"])
        # 0.11.0：跟踪中的任务拒绝隐藏（避免用户看不到仍在后台运行的任务）
        self.assertEqual(self.plugin.delete_record(item["id"])["code"], 1)
        self.assertEqual(len(self.plugin._records().list()), 1)
        cloud = self.cloud()
        self.finish_cloud(cloud)
        self.tick(ticks=2)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        # 获取完成后可以隐藏，获取证据与订阅完成状态保留
        self.assertEqual(self.plugin.delete_record(item["id"])["code"], 0)
        self.assertEqual(self.plugin._records().list(), [])
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_all_links_partial_failure_stays_incomplete_after_successful_task_finishes(self):
        self.register(subscription_key="movie:synthetic")
        self.plugin._set_subscription("movie:synthetic", status="failed", required_resources=["offline-synthetic", "share-synthetic"])
        cloud = self.cloud()
        self.finish_cloud(cloud)
        self.tick(ticks=2)
        state = self.plugin._subscription_store().list()[0]
        self.assertNotEqual(state["status"], "complete")
        self.assertIn("offline-synthetic", state.get("completed_resources", []))
        self.assertNotIn("share-synthetic", state.get("completed_resources", []))
        self.plugin._records().add({"resource_key": "share-synthetic", "acquisition_status": "saved", "status": "done", "subscription_key": "movie:synthetic"})
        self.plugin._mark_resource_complete("movie:synthetic", "share-synthetic")
        self.plugin._complete_subscription_if_ready("movie:synthetic")
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_wrong_exact_file_directory_is_not_moved_or_marked_saved(self):
        item = self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task(wp_path_id=777)], "complete": True, "cursor": None}),
                           get_file_info=Mock(return_value={"id": "7", "parent_id": "777", "name": "Synthetic.mkv", "type": "file"}))
        self.tick()
        self.assertNotEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        cloud.move_via_p115disk.assert_not_called()

    def test_actual_file_id_name_is_used_instead_of_stale_task_name(self):
        self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task(name="OldSynthetic.mkv")], "complete": True, "cursor": None}),
                           get_file_info=Mock(return_value={"id": "7", "parent_id": "42", "name": "ActualSynthetic.mkv", "type": "file"}))
        self.tick()
        cloud.move_via_p115disk.assert_called_once_with("/Synthetic/Staging/ActualSynthetic.mkv", "/Synthetic/Final", file_id="7")

    def test_invalid_exact_file_name_prevents_move(self):
        item = self.register()
        cloud = self.cloud(list_tasks_slice=Mock(return_value={"items": [self.finished_task()], "complete": True, "cursor": None}),
                           get_file_info=Mock(return_value={"id": "7", "parent_id": "42", "name": "../Synthetic.mkv", "type": "file"}))
        result = self.tick()[0]
        self.assertEqual(result["code"], 1)
        self.assertNotEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        cloud.move_via_p115disk.assert_not_called()

    def test_legacy_pending_exact_file_already_in_final_is_recovered_without_move(self):
        # Migration input predates first ledger access, as on a real upgrade.
        self.plugin.synthetic_root = self.plugin.synthetic_root / "legacy-fixture"
        self.plugin.synthetic_root.mkdir()
        self.plugin._ledger_instance = None
        self.plugin.pending_path.write_text(json.dumps([{"hash": HASH, "record_id": "legacy-pending", "kind": "magnet", "title": "Synthetic", "type": "movie",
            "status": "downloading", "task_file_id": "7", "final_path": "/Synthetic/Final", "staging_path": "/Synthetic/Staging"}]), encoding="utf-8")
        item = self.plugin._records().get("legacy-pending")
        self.assertIsNotNone(item)
        cloud = self.cloud()
        cloud.location = "final"
        self.tick()
        self.assertEqual(self.plugin._records().get(item["id"])["acquisition_status"], "saved")
        cloud.move_via_p115disk.assert_not_called()
        cloud.list_tasks_slice.assert_not_called()

    def test_unverified_history_does_not_prove_subscription_complete(self):
        cloud = self.cloud()
        self.plugin.do_transfer(backend.rec(), "movie")
        row = self.plugin._records().list()[0]
        self.plugin._records().update(row["id"], status="unverified", acquisition_status="uncertain")
        self.plugin.do_transfer(backend.rec(_subscription_key="movie:unverified"), "movie")
        self.tick()
        self.assertEqual(cloud.calls, [])
        self.assertEqual(self.plugin._records().get(row["id"])["acquisition_status"], "uncertain")
        self.assertFalse(any(x.get("status") == "complete" for x in self.plugin._subscription_store().list()))

    def test_legacy_organized_history_is_identified_and_not_copied_again(self):
        record = backend.rec()
        self.plugin.synthetic_root = self.plugin.synthetic_root / "legacy-fixture"
        self.plugin.synthetic_root.mkdir()
        self.plugin._ledger_instance = None
        self.plugin.history_path.write_text(json.dumps([{"id": "legacy-organized", "title": record["title"], "year": record["year"],
            "type": "movie", "kind": "115_share", "url": record["links"][0][1], "final_path": self.plugin.build_save_path(record, "movie"),
            "status": "organized", "organization_confirmed": True}]), encoding="utf-8")
        cloud = self.cloud()
        self.assertTrue(self.plugin.do_transfer(record, "movie")[0])
        self.tick()
        self.assertEqual(cloud.calls, [])
        saved = self.plugin._records().get("legacy-organized")
        self.assertTrue(saved["resource_key"])
        self.assertEqual(saved["acquisition_status"], "saved")
        self.assertFalse(saved["organization_confirmed"])

    def test_all_mode_canonical_hash_dedupes_equivalent_magnet_links(self):
        cloud = self.cloud()
        self.plugin._link_mode = "all"
        b32 = base64.b32encode(bytes.fromhex(HASH)).decode()
        self.plugin.do_transfer(backend.rec(links=[("magnet", MAGNET), ("magnet", "magnet:?xt=urn:btih:" + b32 + "&tr=https://synthetic.invalid")]), "movie")
        self.assertEqual(len(self.plugin._last_transfer_result["required_resources"]), 1)
        self.tick()
        self.assertEqual(len(cloud.calls), 1)
        self.assertEqual(len(self.plugin._records().list()), 1)

    def test_manual_retry_explicit_failed_share_can_queue_separate_submit_action(self):
        cloud = self.cloud(outcomes=[(False, "Synthetic explicit share failure"), (True, "Synthetic received")])
        self.plugin.do_transfer(backend.rec(_subscription_key="movie:retry"), "movie")
        row = self.plugin._records().list()[0]
        self.plugin._set_subscription("movie:retry", status="pending", required_resources=[row["resource_key"]])
        self.tick()
        self.assertEqual(self.plugin._records().get(row["id"])["acquisition_status"], "failed")
        self.assertEqual(self.plugin.api_retry_task({"id": row["id"]})["code"], 1)
        self.assertEqual(self.plugin.api_retry_task({"id": row["id"], "action": "retry_submit"})["code"], 0)
        self.assertEqual(len(cloud.calls), 1)
        self.tick()
        self.assertEqual(len(cloud.calls), 2)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_manual_retry_cancelled_offline_resumes_original_without_resubmitting(self):
        cloud = self.cloud()
        self.plugin.do_transfer(backend.rec(_subscription_key="movie:retry", links=[("magnet", MAGNET)]), "movie")
        self.tick()
        row = self.plugin._records().list()[0]
        self.plugin._set_subscription("movie:retry", status="pending", required_resources=[row["resource_key"]])
        self.assertEqual(self.plugin.api_cancel_task({"id": row["id"]})["code"], 0)
        self.assertEqual(self.plugin.api_retry_task({"id": row["id"]})["code"], 0)
        self.finish_cloud(cloud)
        cloud.path_to_id.side_effect = lambda path, mkdir=False: 42 if path == row["staging_path"] else 99
        self.tick(ticks=2)
        self.assertEqual(len(cloud.calls), 1)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_no_active_pending_does_not_construct_or_contact_cloud_client(self):
        self.register(status="failed")
        self.plugin._transfers = Mock(side_effect=AssertionError("Cloud must not be consulted"))
        response = self.plugin.check_offline_tasks()
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["pending"], 0)
        self.plugin._transfers.assert_not_called()


if __name__ == "__main__":
    unittest.main()
