"""Doc115Subscribe 0.12.0 契约：失败原因细分 + 清理失败任务（含 115 离线记录）。

全部合成：不连 MP、不连 115、不读真实账本，115 删除走假传输对象。
"""
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_doc115subscribe_backend as backend
from test_doc115subscribe_backend import main

DEAD_HASH = "1DABEED37D9AA103961B376CFB62E9CACCA5CDC2"


class FakeTransfer:
    """合成传输：记录删除调用，可指定哪些 hash 删除失败。"""

    def __init__(self, fail_on=()):
        self.deleted = []
        self.fail_on = set(fail_on)

    def delete_offline_task(self, info_hash, delete_files=False):
        self.deleted.append(info_hash)
        if str(info_hash).lower() in self.fail_on:
            raise main.P115Error("合成：115 删除失败")
        return {"state": True}


class PurgeTestBase(unittest.TestCase):
    """复用 backend 的隔离环境（网络被禁用、账本落在临时目录），但只跑本文件的用例。"""

    setUp = backend.BackendTests.setUp
    tearDown = backend.BackendTests.tearDown

    def add_record(self, resource_key, **fields):
        """往真实 TaskLedger 里写一条合成记录，返回 batch id。"""
        store = self.plugin._records()
        context = {"title": "合成任务 " + resource_key, "kind": "magnet",
                   "hash": DEAD_HASH, "type": "tv", "target_type": "tv",
                   "staging_path": "/115-影视/115-downloads/磁力链接",
                   "final_path": "/115-影视/115-downloads/电视剧"}
        context.update(fields)
        claimed = store.prepare_resource(resource_key, context)
        batch_id = claimed["batch"]["id"]
        if fields.get("acquisition_status"):
            store.update(batch_id, acquisition_status=fields["acquisition_status"])
        return batch_id

    def install_transfer(self, fake):
        self.plugin._transfers = Mock(return_value=fake)
        return fake


class OfflineFailureMessageTests(PurgeTestBase):
    """需求1：磁力死种与普通离线失败要能区分开。"""

    def test_dead_magnet_is_reported_as_invalid_link(self):
        rec = {"kind": "magnet", "hash": DEAD_HASH}
        task = {"status": -1, "size": 0, "peers": 0, "percentDone": 0, "name": DEAD_HASH}
        message, code = self.plugin._offline_failure(rec, task)
        self.assertEqual(code, "magnet_dead")
        self.assertIn("磁力链接无效", message)
        self.assertNotIn("前往115处理", message)

    def test_magnet_with_metadata_keeps_generic_message(self):
        rec = {"kind": "magnet", "hash": DEAD_HASH}
        task = {"status": -1, "size": 61368000000, "peers": 0, "percentDone": 0,
                "name": "Synthetic.Show.S01E01.2160p.mkv"}
        message, code = self.plugin._offline_failure(rec, task)
        self.assertEqual(code, "offline_failed")
        self.assertIn("115离线任务失败", message)

    def test_named_seed_without_peers_is_not_called_dead(self):
        """能解析出真实文件名说明元数据到手了，只是没人做种，不能断言链接无效。"""
        rec = {"kind": "magnet", "hash": DEAD_HASH}
        task = {"status": -1, "size": 0, "peers": 0, "percentDone": 0,
                "name": "Synthetic.Show.S01E01.mkv"}
        _, code = self.plugin._offline_failure(rec, task)
        self.assertEqual(code, "offline_failed")

    def test_share_failure_never_reported_as_magnet_dead(self):
        rec = {"kind": "115_share", "hash": ""}
        task = {"status": -1, "size": 0, "peers": 0, "percentDone": 0, "name": ""}
        message, code = self.plugin._offline_failure(rec, task)
        self.assertEqual(code, "offline_failed")
        self.assertIn("115离线任务失败", message)

    def test_failure_code_is_exposed_to_view(self):
        """失败码要能出现在任务视图里，前端才能据此显示不同文案。"""
        batch_id = self.add_record("synthetic-dead", acquisition_status="failed",
                                   failure_code="magnet_dead")
        view = self.plugin._record_view(self.plugin._records().get(batch_id))
        self.assertEqual(view.get("failure_code"), "magnet_dead")


class PurgeFailedTests(PurgeTestBase):
    """需求2：批量清理失败任务，并同步删除 115 离线记录。"""

    def test_purge_removes_only_failed_magnet_with_hash(self):
        target = self.add_record("rk-target", acquisition_status="failed")
        no_hash = self.add_record("rk-nohash", acquisition_status="failed", hash="")
        done = self.add_record("rk-done", acquisition_status="saved")
        fake = self.install_transfer(FakeTransfer())

        result = self.plugin.api_purge_failed({})

        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["purged"], 1)
        self.assertEqual(fake.deleted, [DEAD_HASH], "只该对带 hash 的失败任务发起 115 删除")
        store = self.plugin._records()
        self.assertTrue(store.get(target)["hidden"], "成功清理的记录应被隐藏")
        self.assertFalse(store.get(no_hash)["hidden"], "没有 hash 的失败任务不该被动")
        self.assertFalse(store.get(done)["hidden"], "已成功的任务不该被动")

    def test_record_is_kept_when_115_delete_fails(self):
        batch_id = self.add_record("rk-keep", acquisition_status="failed")
        fake = self.install_transfer(FakeTransfer(fail_on={DEAD_HASH.lower()}))

        result = self.plugin.api_purge_failed({})

        self.assertEqual(result["data"]["purged"], 0)
        self.assertEqual(result["data"]["failed"], 1)
        self.assertIn("未清理", result["msg"])
        self.assertFalse(self.plugin._records().get(batch_id)["hidden"],
                         "115 删除失败时不能隐藏本地记录，否则云端会留垃圾")
        self.assertEqual(fake.deleted, [DEAD_HASH])

    def test_purge_accepts_explicit_ids(self):
        first = self.add_record("rk-a", acquisition_status="failed")
        second = self.add_record("rk-b", acquisition_status="failed")
        fake = self.install_transfer(FakeTransfer())

        result = self.plugin.api_purge_failed({"ids": [first]})

        self.assertEqual(result["data"]["purged"], 1)
        self.assertEqual(len(fake.deleted), 1)
        store = self.plugin._records()
        self.assertTrue(store.get(first)["hidden"])
        self.assertFalse(store.get(second)["hidden"], "未选中的记录不该被清理")

    def test_rejects_oversized_batch(self):
        result = self.plugin.api_purge_failed({"ids": [f"id-{i}" for i in range(51)]})
        self.assertEqual(result["code"], 1)
        self.assertIn("1 到 50", result["msg"])

    def test_reports_when_nothing_to_purge(self):
        fake = self.install_transfer(FakeTransfer())
        result = self.plugin.api_purge_failed({})
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["purged"], 0)
        self.assertEqual(fake.deleted, [])

    def test_purge_cloud_action_is_offered_for_failed_magnet(self):
        batch_id = self.add_record("rk-action", acquisition_status="failed")
        view = self.plugin._record_view(self.plugin._records().get(batch_id))
        self.assertIn("purge_cloud", view["allowed_actions"])

    def test_purge_cloud_action_rejected_for_saved_record(self):
        batch_id = self.add_record("rk-saved", acquisition_status="saved")
        view = self.plugin._record_view(self.plugin._records().get(batch_id))
        self.assertNotIn("purge_cloud", view["allowed_actions"])


class DeleteOfflineTaskPayloadTests(PurgeTestBase):
    """传输层：只按 info_hash 精确删除，且默认不删已落盘文件。"""

    def _transfer(self):
        tr = main.P115Transfer.__new__(main.P115Transfer)
        tr.calls = []
        tr._call = lambda name, payload, **kwargs: tr.calls.append((name, payload, kwargs)) or {"state": True}
        tr._require_success = lambda resp, op: None
        return tr

    def test_payload_uses_hash_and_keeps_files(self):
        tr = self._transfer()
        tr.delete_offline_task(DEAD_HASH)
        name, payload, kwargs = tr.calls[0]
        self.assertEqual(name, "clouddownload_task_del")
        self.assertEqual(payload["hash[0]"], DEAD_HASH.lower())
        self.assertEqual(payload["flag"], 0, "默认必须保留已落盘文件")
        self.assertEqual(kwargs.get("intent", {}).get("kind"), "offline_delete")

    def test_empty_hash_is_refused(self):
        tr = self._transfer()
        with self.assertRaises(Exception):
            tr.delete_offline_task("")
        self.assertEqual(tr.calls, [], "没有 hash 时不能发出任何云端写请求")


if __name__ == "__main__":
    unittest.main(verbosity=2)
