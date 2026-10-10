"""0.11.0 115 boundary fixes; synthetic data and in-memory fakes only."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_doc115subscribe_transfer as base
import test_doc115subscribe_transfer_hardening as hard

transfer = base.transfer
BTIH = base.BTIH
MAGNET = base.MAGNET
MD4 = "0123456789abcdef0123456789abcdef"
ED2K = f"ed2k://|file|Synthetic Movie 2025.mkv|1048576|{MD4.upper()}|/"

# Field shape as returned by a real (read-only) clouddownload_task_list call.
REAL_TASK = {"add_time": 1700000000, "available_actions": [], "can_appeal": 0, "def2": 0,
             "del_path": "", "delete_file_id": "", "display_percent": "100%", "display_status": "已完成",
             "file_category": 1, "file_classify": 0, "file_icon": "", "file_id": "7",
             "info_hash": BTIH, "last_update": 1700000100, "left_time": 0, "move": 1,
             "name": "Synthetic.mkv", "peers": 0, "percentDone": 100, "pick_code": "abc",
             "play_long": 0, "status": 2, "url": MAGNET, "wp_path_id": "42"}
REAL_LIST = {"count": 1, "errcode": 0, "errtype": "", "page": 1, "page_count": 1, "page_row": 30,
             "page_size": 30, "quota": 1, "real_state": True, "state": True, "tasks": [REAL_TASK], "total": 1}


class StatusTests(unittest.TestCase):
    def test_status_two_is_done_not_failed(self):
        self.assertFalse(transfer.P115Transfer.task_failed(REAL_TASK))
        self.assertTrue(transfer.P115Transfer.task_done(REAL_TASK))

    def test_failure_values(self):
        for status in (-1, -2, "-1", "failed", "error", "cancelled", "canceled"):
            with self.subTest(status=status):
                self.assertTrue(transfer.P115Transfer.task_failed({"status": status}))
                self.assertFalse(transfer.P115Transfer.task_done({"status": status, "percentDone": 100}))
        for status in (0, 1, 2):
            self.assertFalse(transfer.P115Transfer.task_failed({"status": status}))
        self.assertTrue(transfer.P115Transfer.task_done({"status": 1, "percentDone": 100}))
        self.assertFalse(transfer.P115Transfer.task_done({"status": 1, "percentDone": 50}))


class TransferFixTests(unittest.TestCase):
    """Reuses the bare fake setUp of the existing boundary tests."""
    setUp = base.TransferTests.setUp
    fake = base.TransferTests.fake
    fake_directory = base.TransferTests.fake_directory

    def test_real_task_list_shape_is_parsed(self):
        self.fake("clouddownload_task_list", return_value=REAL_LIST)
        tasks = self.api.list_tasks(page_size=30)
        self.assertEqual(len(tasks), 1)
        self.assertTrue(self.api.task_done(tasks[0]))
        self.assertFalse(self.api.task_failed(tasks[0]))

    def test_duplicate_finished_status_two_with_file_is_recoverable(self):
        self.fake_directory()
        self.fake("clouddownload_task_add_urls", return_value={"state": False, "errcode": 10008, "error_msg": "任务已存在"})
        self.fake("clouddownload_task_list", return_value={**REAL_LIST, "tasks": [dict(REAL_TASK, percentDone=99)]})
        with patch.object(self.api, "file_in_directory", return_value=True):
            result = self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(result.duplicate)
        self.assertTrue(result.recoverable)

    def test_http_tasks_without_hash_are_skipped_and_counted(self):
        tasks = [{"info_hash": "", "url": "https://synthetic.invalid/a.mkv", "status": 1},
                 dict(REAL_TASK), {"name": "no hash"}]
        self.fake("clouddownload_task_list", return_value={"state": True, "count": 3, "tasks": tasks})
        result = self.api.list_tasks()
        self.assertEqual([t["info_hash"] for t in result], [BTIH])
        self.assertEqual(self.api.last_tasks_skipped, 2)

    def test_ed2k_md4_hash_is_normalized(self):
        self.assertEqual(transfer.normalize_info_hash(MD4.upper()), MD4)
        self.assertEqual(transfer.extract_hash(ED2K), MD4)
        self.assertEqual(transfer.extract_hash(f"ed2k://|file|A B|1|{MD4}|h=ABCDEF|/"), MD4)


class ErrorTests(unittest.TestCase):
    def test_error_reads_all_message_fields(self):
        err = transfer.P115Transfer._error
        self.assertEqual(err({"error_msg": "synthetic"}), "synthetic")
        self.assertEqual(err({"message": "m"}), "m")
        self.assertEqual(err({"msg": "x"}), "x")
        self.assertEqual(err({"errno": 123}), "123")
        self.assertEqual(err({}), "未知错误")

    def test_duplicate_codes_and_text_hit_dup_words(self):
        words = transfer.P115Transfer._DUP_WORDS
        for resp in ({"errcode": 10008}, {"errno": "10008", "error": "请求失败"},
                     {"error_msg": "任务已存在"}, {"error": "该任务已存在，请勿重复添加"}):
            with self.subTest(resp=resp):
                self.assertTrue(any(w in transfer.P115Transfer._error(resp) for w in words))
        self.assertFalse(any(w in transfer.P115Transfer._error({"errcode": 10009, "error": "x"}) for w in words))

    def test_frequency_codes_are_rate_limited(self):
        for resp in ({"errno": 990009}, {"errcode": 990005}, {"code": 990019}, {"errno": 40110000},
                     {"error": "操作过于频繁，请稍后再试"}):
            with self.subTest(resp=resp):
                self.assertEqual(transfer._account_failure(resp), "rate_limit")
        self.assertFalse(hasattr(transfer, "_RETRY_CODES"))
        self.assertEqual(transfer._account_failure({"errno": 0, "error": ""}), "")


class MatchTaskTests(unittest.TestCase):
    def test_btih_match(self):
        self.assertTrue(transfer.match_task(REAL_TASK, MAGNET))
        self.assertTrue(transfer.match_task(REAL_TASK, info_hash=BTIH.upper()))
        self.assertFalse(transfer.match_task(dict(REAL_TASK, info_hash="f" * 40), MAGNET))

    def test_ed2k_with_115_40_char_hash_falls_back_to_url_then_name(self):
        task = {"info_hash": "a" * 40, "url": ED2K.lower().replace("|/", "|"), "name": "other"}
        self.assertTrue(transfer.match_task(task, ED2K))
        task = {"info_hash": "a" * 40, "url": "", "name": "Synthetic Movie 2025.mkv", "size": 1048576}
        self.assertTrue(transfer.match_task(task, ED2K))
        task = {"info_hash": "a" * 40, "url": "", "name": "Different.mkv"}
        self.assertFalse(transfer.match_task(task, ED2K))
        self.assertTrue(transfer.match_task({"info_hash": MD4}, ED2K))
        self.assertTrue(transfer.P115Transfer.match_task({"info_hash": MD4}, ED2K))


class HardeningFixTests(unittest.TestCase):
    setUp = hard.HardeningTests.setUp
    def test_lost_mkdir_reply_reconciles_existing_directory(self):
        created = {"done": False}
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 77 if created["done"] else 0}
            if path == "/app/chrome/add_path":
                created["done"] = True
                return TimeoutError("synthetic lost reply")
            return {"state": True}
        self.handler = handler
        with self.api.work_slice(max_requests=5):
            self.assertEqual(self.api.path_to_id("/Synthetic", mkdir=True), 77)
        self.assertEqual([c[0] for c in self.calls], ["/files/getid", "/files/getid", "/app/chrome/add_path", "/files/getid"])
        self.assertEqual(self.b.snapshot()["reason"], "")  # no uncertain cooldown

    def test_lost_mkdir_reply_with_absent_directory_is_not_sent_retry(self):
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 0}
            return TimeoutError("synthetic lost reply")
        self.handler = handler
        with self.api.work_slice(max_requests=5), self.assertRaises(hard.transfer.P115Deferred) as raised:
            self.api.path_to_id("/Synthetic", mkdir=True)
        self.assertFalse(raised.exception.uncertain)
        self.assertTrue(raised.exception.not_sent)

    def test_mkdir_transport_is_not_uncertain(self):
        self.handler = lambda path, payload: TimeoutError("synthetic")
        with self.api.work_slice(), self.assertRaises(hard.transfer.P115Deferred) as raised:
            self.api.client.fs_makedirs_app("/Synthetic")
        self.assertFalse(raised.exception.uncertain)
        self.assertTrue(raised.exception.not_sent)


class ThreadIsolationTests(unittest.TestCase):
    def test_last_results_are_thread_local(self):
        api = transfer.P115Transfer.__new__(transfer.P115Transfer)
        api.last_share_result = {"owner": "main"}
        api.last_offline_result = "main"
        seen = {}
        def worker():
            seen["before"] = (api.last_share_result, api.last_offline_result, api.last_share_names)
            api.last_share_result = {"owner": "worker"}
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(seen["before"], ({}, None, []))
        self.assertEqual(api.last_share_result, {"owner": "main"})
        self.assertEqual(api.last_offline_result, "main")


if __name__ == "__main__":
    unittest.main()



class Ed2kNameFallbackSafety(unittest.TestCase):
    """115 把 ed2k 换成 40 位内部哈希时，名字回退必须同时比对大小，避免误搬运同名的其它版本。"""
    link = "ed2k://|file|S01E01.mkv|1234567|0123456789abcdef0123456789abcdef|/"

    def task(self, size):
        return {"info_hash": "a" * 40, "name": "S01E01.mkv", "size": size, "url": ""}

    def test_same_name_and_size_matches(self):
        self.assertTrue(transfer.match_task(self.task(1234567), self.link))

    def test_same_name_different_size_is_not_the_same_task(self):
        self.assertFalse(transfer.match_task(self.task(7654321), self.link))

    def test_same_name_without_size_is_not_trusted(self):
        self.assertFalse(transfer.match_task(self.task(None), self.link))
