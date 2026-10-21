"""0.11.8 回归：适配上游 DDSRem 版 115网盘Plus（P115Api.move 自带移动后复核）。

全部合成数据，禁止真实网络：socket 在父类 setUp 里已被断言封死。
"""
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import test_doc115subscribe_transfer_hardening as hardening


transfer = hardening.transfer


class SpyStorageChain:
    """宿主共享 u115 存储的探针：被调用一次就记一次。"""

    calls = []

    def get_file_item(self, *args, **kwargs):
        type(self).calls.append((args, kwargs))
        return None


class UpstreamPlus(hardening.FakePlus):
    """上游 3.0.x 形态：move 内部用 self.get_item 复核，get_item 会降级 StorageChain。"""

    def get_item(self, path):
        try:
            from app.chain.storage import StorageChain  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        return StorageChain().get_file_item(storage="u115", path=path)

    def move(self, fileitem, path, new_name):
        try:
            cid = self._id_cache.get_id_by_dir(path.as_posix())
            if cid is None:
                raise AssertionError("controlled target cache missing")
            result = self.client.fs_move(fileitem.fileid, pid=cid)
            if not result.get("state"):
                return False
            new_item = self.get_item(Path(path) / (fileitem.name or ""))
            if not new_item:
                return False
            return True
        except Exception:  # noqa: BLE001
            return False


class DangerousPlus(hardening.FakePlus):
    """move 内部直接做共享属性查询：本插件无法屏蔽，必须拒绝。"""

    def move(self, fileitem, path, new_name):
        get_attr = lambda name: None  # noqa: E731  （只为让源码里出现禁用标记）
        get_attr("synthetic")
        return False


class SeedlessCache:
    """假装接受缓存、实际不落盘：Plus 会绕过本插件的受控目录。"""

    def add_cache(self, id, directory):
        return None

    def get_id_by_dir(self, directory):
        return None


class UpstreamPlusTests(unittest.TestCase):
    """复用父类的合成 HTTP 夹具，只替换 Plus 的形态。"""


    def setUp(self):  # noqa: F811  （父类夹具 + 共享存储探针）
        hardening.HardeningTests.setUp(self)
        SpyStorageChain.calls = []
        app_pkg = ModuleType("app")
        app_chain = ModuleType("app.chain")
        app_storage = ModuleType("app.chain.storage")
        app_storage.StorageChain = SpyStorageChain
        app_pkg.chain = app_chain
        app_chain.storage = app_storage
        self.stack.enter_context(patch.dict(sys.modules, {
            "app": app_pkg,
            "app.chain": app_chain,
            "app.chain.storage": app_storage,
        }))

    def install_plus(self, plus_class=UpstreamPlus, cache_class=None):
        plus_class.instances = []
        plus = ModuleType("app.plugins.p115disk.p115_api")
        plus.P115Api = plus_class
        schemas = ModuleType("app.schemas")
        schemas.FileItem = hardening.FakeItem
        self.stack.enter_context(patch.dict(sys.modules, {
            "app.plugins.p115disk.p115_api": plus, "app.schemas": schemas}))
        if cache_class is not None:
            original_init = plus_class.__init__

            def patched_init(instance, client, disk_name):
                original_init(instance, client, disk_name)
                instance._id_cache = cache_class()

            plus_class.__init__ = patched_init
            self.addCleanup(setattr, plus_class, "__init__", original_init)
        return plus_class

    @staticmethod
    def moving_handler(parents):
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 11 if payload["path"] == "/Staging" else 42}
            if path == "/files/get_info":
                fid = payload["file_id"]
                return {"state": True, "data": [{"cid": fid, "pid": parents[fid], "n": "Synthetic" + fid, "fc": "0"}]}
            if path == "/files/move":
                parents[payload["fid"]] = payload["pid"]
                return {"state": True}
            raise AssertionError("unexpected request")
        return handler

    def test_upstream_post_move_lookup_cannot_block_a_landed_move(self):
        """上游复核失败（目录缓存滞后）时，按文件ID+父目录确认已搬运，不重试。"""
        self.install_plus()
        parents = {"7": "11"}
        self.handler = self.moving_handler(parents)
        with self.api.work_slice():
            self.assertEqual(self.api.move_via_p115disk("/Staging/Synthetic7", "/Target", "7"), (True, ""))
        self.assertEqual(parents["7"], "42")
        self.assertEqual(len([p for p, _, _ in self.calls if p == "/files/move"]), 1)
        # 上游复核只能走私有 client：共享 u115 降级在搬运期间被屏蔽
        self.assertEqual(SpyStorageChain.calls, [])

    def test_upstream_lookup_outside_move_still_reaches_host_storage(self):
        """对照组：屏蔽只在搬运窗口内生效，窗口外照常可降级（证明探针有效）。"""
        self.install_plus()
        self.assertEqual(SpyStorageChain().get_file_item(storage="u115", path="/x"), None)
        self.assertEqual(len(SpyStorageChain.calls), 1)

    def test_upstream_move_that_did_not_land_stays_failed(self):
        """真实失败的搬运不得被"乐观"判成功。"""
        self.install_plus()
        parents = {"7": "11"}

        def handler(path, payload):
            if path == "/files/move":
                return {"state": False}
            return self.moving_handler(parents)(path, payload)

        self.handler = handler
        with self.api.work_slice():
            success, message = self.api.move_via_p115disk("/Staging/Synthetic7", "/Target", "7")
        self.assertFalse(success)
        self.assertIn("移动失败", message)
        self.assertEqual(parents["7"], "11")

    def test_unmaskable_shared_lookup_in_move_is_still_rejected(self):
        self.install_plus(plus_class=DangerousPlus)
        parents = {"7": "11"}
        self.handler = self.moving_handler(parents)
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.move_via_p115disk("/Staging/Synthetic7", "/Target", "7")
        self.assertEqual(raised.exception.reason, "capability")
        self.assertFalse([p for p, _, _ in self.calls if p == "/files/move"])

    def test_plus_that_ignores_seeded_directory_cache_is_rejected(self):
        self.install_plus(cache_class=SeedlessCache)
        parents = {"7": "11"}
        self.handler = self.moving_handler(parents)
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.move_via_p115disk("/Staging/Synthetic7", "/Target", "7")
        self.assertEqual(raised.exception.reason, "capability")
        self.assertFalse([p for p, _, _ in self.calls if p == "/files/move"])
        self.assertEqual(parents["7"], "11")


if __name__ == "__main__":
    unittest.main()
