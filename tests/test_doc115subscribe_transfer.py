"""115 boundary regressions using invented resources and in-memory fake APIs.

Nothing in this module imports a live p115client or sends any network request.
"""
import base64
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe/p115_transfer.py"
SPEC = importlib.util.spec_from_file_location("doc115_transfer_test", SOURCE)
transfer = importlib.util.module_from_spec(SPEC)
router = ModuleType("link_router")
router.LINK_115_SHARE = "115_share"
router.LINK_ED2K = "ed2k"
router.LINK_MAGNET = "magnet"
with patch.dict(sys.modules, {SPEC.name: transfer, "link_router": router,
                             "p115client": ModuleType("p115client"), "p115client.util": ModuleType("p115client.util")}):
    SPEC.loader.exec_module(transfer)

BTIH = "0123456789abcdef0123456789abcdef01234567"
MAGNET = "magnet:?xt=urn:btih:" + BTIH


class TransferTests(unittest.TestCase):
    def setUp(self):
        # Bypass construction so the entire network boundary is an explicit fake.
        self.api = transfer.P115Transfer.__new__(transfer.P115Transfer)
        self.api.client = SimpleNamespace()
        self.api.timeout = 17
        self.api._limiter = SimpleNamespace(wait=Mock())
        self.api._dir_cache = {}
        self.api.last_offline_result = None
        self.api.last_share_names = []
        self.api.last_share_result = {}

    def fake(self, name, **kwargs):
        method = Mock(**kwargs)
        setattr(self.api.client, name, method)
        return method

    def fake_directory(self, cid=42):
        return self.fake("fs_dir_getid", return_value={"state": True, "id": cid})

    def test_magnet_hex_and_base32_are_canonical_and_percent_encoding_works(self):
        b32 = base64.b32encode(bytes.fromhex(BTIH)).decode()
        self.assertEqual(transfer.extract_hash(MAGNET.upper()), BTIH)
        self.assertEqual(transfer.extract_hash("magnet:?xt=urn%3Abtih%3A" + b32.lower()), BTIH)

    def test_invalid_magnet_hashes_are_not_partially_accepted(self):
        for raw in (BTIH + "abc", BTIH[:-1], "G" * 40, "1" * 32, "2" * 33):
            with self.subTest(raw=raw):
                self.assertEqual(transfer.extract_hash("magnet:?xt=urn:btih:" + raw), "")
        self.assertEqual(transfer.extract_hash("https://invalid.test/?xt=urn:btih:" + BTIH), "")

    def test_ed2k_hash_is_exact_and_strict(self):
        h = "abcdef0123456789" * 2
        self.assertEqual(transfer.extract_hash(f"ed2k://|file|Synthetic.mkv|123|{h.upper()}|/"), h)
        for bad in (h + "a", h[:-1], "g" * 32):
            self.assertEqual(transfer.extract_hash(f"ed2k://|file|Synthetic.mkv|123|{bad}|/"), "")

    def test_invalid_offline_link_fails_before_any_api_call(self):
        with self.assertRaises(transfer.P115Error):
            self.api.offline_add("magnet:?xt=urn:btih:invalid", "/Synthetic")
        self.api._limiter.wait.assert_not_called()

    def test_share_paginates_all_ids_and_submits_every_item(self):
        items = [{"fid": str(i + 1), "n": f"Synthetic {i}", "fc": "1"} for i in range(405)]

        def page(payload, **kwargs):
            offset = payload["offset"]
            return {"state": True, "data": {"count": len(items), "list": items[offset:offset + payload["limit"]]}}

        snap = self.fake("share_snap", side_effect=page)
        self.fake_directory()
        receive = self.fake("share_receive", return_value={"state": True})
        with patch.object(transfer, "share_extract_payload", return_value={"share_code": "synthetic"}):
            self.assertTrue(self.api.share_receive("https://115.com/s/synthetic", "/Synthetic"))
        self.assertEqual([call.args[0]["offset"] for call in snap.call_args_list], [0, 200, 400])
        submitted = [fid for call in receive.call_args_list for fid in call.args[0]["file_id"].split(",")]
        self.assertEqual(submitted, [item["fid"] for item in items])
        self.assertEqual(self.api.last_share_result["received"], 405)
        self.assertEqual(len(self.api.last_share_names), 405)
        self.assertTrue(all(call.kwargs["timeout"] == 17 for call in receive.call_args_list))

    def test_share_listing_failure_prevents_transfer_and_directory_creation(self):
        self.fake("share_snap", return_value={"state": False, "errno": 410, "error": "synthetic expiry"})
        directory = self.fake_directory()
        receive = self.fake("share_receive")
        with patch.object(transfer, "share_extract_payload", return_value={"share_code": "synthetic"}):
            with self.assertRaises(transfer.P115Error):
                self.api.share_receive("https://115.com/s/synthetic", "/Synthetic")
        directory.assert_not_called()
        receive.assert_not_called()

    def test_share_incomplete_or_repeated_page_is_error(self):
        for second in ([], [{"fid": "1", "n": "Synthetic"}]):
            with self.subTest(second=second):
                self.fake("share_snap", side_effect=[
                    {"state": True, "data": {"count": 2, "list": [{"fid": "1", "n": "Synthetic"}]}},
                    {"state": True, "data": {"count": 2, "list": second}},
                ])
                with self.assertRaises(transfer.P115Error):
                    self.api.share_items("synthetic", "")

    def test_share_partial_failure_reports_completed_count(self):
        self.fake_directory()
        items = [{"id": str(i), "name": f"Synthetic {i}"} for i in range(201)]
        self.fake("share_receive", side_effect=[{"state": True}, {"state": False, "error": "synthetic denial"}])
        with patch.object(self.api, "share_items", return_value=items), patch.object(
            transfer, "share_extract_payload", return_value={"share_code": "synthetic"}
        ):
            with self.assertRaisesRegex(transfer.P115Error, "200/201"):
                self.api.share_receive("https://115.com/s/synthetic", "/Synthetic")
        self.assertEqual(self.api.last_share_result["received"], 200)
        self.assertEqual(self.api.last_share_result["failed"], 1)
        self.assertTrue(self.api.last_share_result["partial"])
        self.assertFalse(self.api.last_share_result["uncertain"])

    def test_share_lost_response_is_uncertain_and_not_retried(self):
        self.fake_directory()
        receive = self.fake("share_receive", side_effect=TimeoutError("Synthetic response lost"))
        with patch.object(self.api, "share_items", return_value=[{"id": "7", "name": "Synthetic"}]), patch.object(
            transfer, "share_extract_payload", return_value={"share_code": "synthetic"}
        ):
            with self.assertRaises(transfer.P115Error):
                self.api.share_receive("https://115.com/s/synthetic", "/Synthetic")
        self.assertTrue(self.api.last_share_result["uncertain"])
        self.assertFalse(self.api.last_share_result["partial"])
        receive.assert_called_once()

    def test_directory_pagination_finds_item_after_first_400(self):
        self.fake_directory()
        items = [{"fid": str(i + 1), "n": f"Synthetic {i}"} for i in range(401)]
        self.fake("fs_files", side_effect=lambda p, **kw: {"state": True, "count": len(items), "data": items[p["offset"]:p["offset"] + p["limit"]]})
        self.assertTrue(self.api.path_exists("/Synthetic/Synthetic 400"))
        self.assertFalse(self.api.path_exists("/Synthetic/Absent"))

    def test_path_absence_is_distinct_from_listing_and_lookup_errors(self):
        self.fake("fs_dir_getid", return_value={"state": True, "id": 0})
        self.assertFalse(self.api.path_exists("/Synthetic/Absent"))
        self.fake("fs_dir_getid", return_value={"state": False, "error": "authentication failed"})
        with self.assertRaises(transfer.P115Error):
            self.api.path_exists("/Synthetic/Absent")
        self.fake_directory()
        self.fake("fs_files", side_effect=TimeoutError("synthetic timeout"))
        with self.assertRaises(transfer.P115Error):
            self.api.path_exists("/Synthetic/Absent")

    def test_directory_short_page_respects_total_and_errors_on_truncation(self):
        self.fake_directory()
        self.fake("fs_files", side_effect=[
            {"state": True, "count": 2, "data": [{"fid": "1", "n": "Synthetic"}]},
            {"state": True, "count": 2, "data": []},
        ])
        with self.assertRaises(transfer.P115Error):
            self.api.list_names("/Synthetic")

    def test_offline_acceptance_returns_structured_receipt_and_real_timeout(self):
        directory = self.fake_directory()
        add = self.fake("clouddownload_task_add_urls", return_value={"state": True})
        result = self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(result.accepted)
        self.assertFalse(result.duplicate)
        self.assertEqual(result.info_hash, BTIH)
        self.assertEqual(result.requested_cid, "42")
        self.assertEqual(add.call_args.kwargs["timeout"], 17)
        self.assertEqual(directory.call_args.kwargs["timeout"], 17)
        self.assertEqual(add.call_args.args[0]["url[0]"], MAGNET)

    def test_older_httpcore_backend_receives_effective_timeout_extensions(self):
        self.api.client.request = SimpleNamespace(__func__=SimpleNamespace(__globals__={"get_request": lambda: None}))
        directory = self.fake_directory()
        with patch.object(transfer.inspect, "getsource", return_value="from httpcore_request import request"):
            self.api.path_to_id("/Synthetic", mkdir=False)
        self.assertEqual(directory.call_args.kwargs, {"extensions": {"timeout": {
            "connect": 17, "read": 17, "write": 17, "pool": 17,
        }}})

    def duplicate_api(self, tasks):
        self.fake_directory()
        self.fake("clouddownload_task_add_urls", return_value={"state": False, "error": "任务重复"})
        self.fake("clouddownload_task_list", return_value={"state": True, "count": len(tasks), "tasks": tasks})

    def test_duplicate_without_task_is_not_success(self):
        self.duplicate_api([])
        with self.assertRaises(transfer.P115Error):
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(self.api.last_offline_result.duplicate)
        self.assertFalse(self.api.last_offline_result)

    def test_duplicate_active_task_in_same_staging_can_be_recovered(self):
        self.duplicate_api([{"info_hash": BTIH, "wp_path_id": 42, "percentDone": 20, "status": 1}])
        result = self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(result)
        self.assertFalse(result.accepted)
        self.assertTrue(result.duplicate)
        self.assertTrue(result.recoverable)

    def test_duplicate_at_other_directory_is_not_success(self):
        self.duplicate_api([{"info_hash": BTIH, "wp_path_id": 99, "percentDone": 20, "file_id": 7}])
        with self.assertRaises(transfer.P115Error):
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertEqual(self.api.last_offline_result.actual_cid, "99")
        self.assertEqual(self.api.last_offline_result.file_id, "7")

    def test_duplicate_failed_or_completed_without_file_is_not_success(self):
        for task in (
            {"status": -1, "percentDone": 20},
            {"status": 2, "percentDone": 20},
            {"status": 0, "percentDone": 100, "name": "Synthetic.mkv", "file_id": 7},
        ):
            with self.subTest(task=task):
                self.duplicate_api([{"info_hash": BTIH, "wp_path_id": 42, **task}])
                with patch.object(self.api, "file_in_directory", return_value=False):
                    with self.assertRaises(transfer.P115Error):
                        self.api.offline_add(MAGNET, "/Synthetic")

    def test_duplicate_completed_with_file_is_recoverable(self):
        self.duplicate_api([{"info_hash": BTIH, "wp_path_id": 42, "percentDone": 100, "name": "Synthetic.mkv", "file_id": 7}])
        with patch.object(self.api, "file_in_directory", return_value=True):
            self.assertTrue(self.api.offline_add(MAGNET, "/Synthetic").recoverable)

    def test_uncertain_submission_preserves_reconciliation_flag(self):
        self.fake_directory()
        add = self.fake("clouddownload_task_add_urls", side_effect=TimeoutError("synthetic lost reply"))
        self.fake("clouddownload_task_list", side_effect=TimeoutError("synthetic recovery outage"))
        with self.assertRaises(transfer.P115Error):
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(self.api.last_offline_result.uncertain)
        add.assert_called_once()

    def test_exact_file_identity_prevents_same_named_recovery(self):
        self.fake_directory()
        self.fake("fs_file", return_value={"state": True, "data": [{"file_id": "7", "parent_id": "99", "file_name": "Synthetic.mkv"}]})
        self.assertFalse(self.api.file_in_directory("7", "/Synthetic"))
        self.assertEqual(self.api.get_file_info("7")["parent_id"], "99")

    def test_exact_file_absence_is_distinct_from_lookup_failure(self):
        self.fake("fs_file", return_value={"state": False, "errno": 20018})
        self.assertIsNone(self.api.get_file_info("7"))
        self.fake("fs_file", return_value={"state": False, "errno": 99, "error": "authentication"})
        with self.assertRaises(transfer.P115Error):
            self.api.get_file_info("7")

    def test_exact_file_lookup_rejects_mismatched_id(self):
        self.fake("fs_file", return_value={"state": True, "data": [{"file_id": "8", "parent_id": "42"}]})
        with self.assertRaises(transfer.P115Error):
            self.api.get_file_info("7")

    def test_inner_offline_error_is_not_hidden_by_outer_success(self):
        self.fake_directory()
        self.fake("clouddownload_task_add_urls", return_value={"state": True, "result": [{"state": False, "error": "synthetic failure"}]})
        with self.assertRaisesRegex(transfer.P115Error, "synthetic failure"):
            self.api.offline_add(MAGNET, "/Synthetic")

    def test_offline_timeout_recovers_actual_matching_task_without_resubmission(self):
        self.fake_directory()
        add = self.fake("clouddownload_task_add_urls", side_effect=TimeoutError("synthetic lost reply"))
        self.fake("clouddownload_task_list", return_value={"state": True, "count": 1, "tasks": [{"info_hash": BTIH, "wp_path_id": 42, "percentDone": 10}]})
        result = self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(result.recoverable)
        self.assertFalse(result.accepted)
        add.assert_called_once()

    def test_tasks_are_paginated_beyond_ten_pages_and_nested_data_is_supported(self):
        tasks = [{"info_hash": f"{i:040x}", "status": -1 if i == 11 else 1} for i in range(12)]
        self.fake("clouddownload_task_list", side_effect=lambda p, **kw: {"state": True, "data": {"count": 12, "tasks": [tasks[p["page"] - 1]]}})
        result = self.api.list_tasks(page_size=1)
        self.assertEqual(len(result), 12)
        self.assertTrue(self.api.task_failed(result[-1]))

    def test_task_list_network_error_does_not_look_like_empty_queue(self):
        self.fake("clouddownload_task_list", return_value={"state": False, "error": "synthetic authentication failure"})
        with self.assertRaises(transfer.P115Error):
            self.api.list_tasks()

    def test_limiter_is_shared_per_account_and_serializes_concurrent_callers(self):
        self.assertIs(transfer._shared_limiter("UID=12345_A; CID=a"), transfer._shared_limiter("UID=12345_B; CID=b"))
        limiter = transfer._RateLimiter(min_interval=1, jitter=0)
        virtual = SimpleNamespace(now=100.0, grants=[])
        start = Barrier(5)
        clock_lock = Lock()

        def sleep(seconds):
            with clock_lock:
                virtual.now += seconds

        def wait(_):
            start.wait(timeout=5)
            limiter.wait()
            # The limiter's recorded admission time is the scheduling evidence.
            return limiter._last

        with patch.object(transfer.time, "monotonic", side_effect=lambda: virtual.now), patch.object(
            transfer.time, "sleep", side_effect=sleep
        ), ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(wait, range(5)))
        self.assertEqual(virtual.now, 104.0)


if __name__ == "__main__":
    unittest.main()
