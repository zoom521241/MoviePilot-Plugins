"""云端能力自愈：插件先于依赖加载时，SDK 必须在运行期重新探测，而不是永久判死。

背景（真实事故）：MoviePilot 启动时先加载插件、再安装插件依赖，于是
``p115client`` 在模块导入那一刻还不存在。旧实现把这次失败固化进模块级
``P115_AVAILABLE``，进程里所有云端操作都报「未安装兼容的115网盘Plus SDK」，
直到重启 MoviePilot 才好。这里用合成模块验证：导入失败不是终态。
"""
import importlib.util
import json
import socket
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe/p115_transfer.py"


class FakeSDK:
    """最小可控 SDK 契约：每个端点都必须经 ``self.request`` 走受控通道。

    ``_private_client`` 会用 ``inspect.getsource`` 校验这一点，所以测试桩必须
    写真实的 ``self.request(...)`` 调用，而不是空实现。
    """

    def __init__(self, cookie):
        self.cookie = cookie

    def request(self, url, method="GET", payload=None, *, request=None, async_=False, **kwargs):
        return {}

    def fs_file(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/files/get_info", "POST", {})

    def fs_files(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/files", "GET", {})

    def fs_dir_getid(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/files/getid", "GET", {})

    def share_snap(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/share/snap", "GET", {})

    def share_receive(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/share/receive", "POST", {})

    def clouddownload_task_list(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/?ac=task_lists", "GET", {})

    def clouddownload_task_add_urls(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/?ac=add_task_urls", "POST", {})

    def clouddownload_task_del(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/?ac=task_del", "POST", {})

    def fs_move(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/files/move", "POST", {})

    def fs_move_app(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/app/chrome/move", "POST", {})

    def fs_makedirs_app(self, *args, **kwargs):
        return self.request("https://synthetic.invalid/app/chrome/add_path", "POST", {})


class IncompatibleSDK(FakeSDK):
    """装上了但缺受控端点（例如 SDK 大版本改名）：能力校验必须继续拦。"""

    fs_move = None


def sdk_modules(with_client=True, sdk=None):
    """构造「已装好 / 还没装好」两种 p115client 现场。"""
    client = ModuleType("p115client")
    util = ModuleType("p115client.util")
    if with_client:
        client.P115Client = sdk or FakeSDK
        util.share_extract_payload = lambda url: {"share_code": "synthetic"}
    return {"p115client": client, "p115client.util": util}


@contextmanager
def loaded_transfer(sdk):
    spec = importlib.util.spec_from_file_location("doc115_selfheal_test", SOURCE)
    transfer = importlib.util.module_from_spec(spec)
    router = ModuleType("link_router")
    router.LINK_115_SHARE, router.LINK_ED2K, router.LINK_MAGNET = "115_share", "ed2k", "magnet"
    with patch.dict(sys.modules, {spec.name: transfer, "link_router": router, **sdk}):
        spec.loader.exec_module(transfer)
        yield transfer


class SdkSelfHeal(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))

    def test_missing_sdk_is_reported_without_killing_the_plugin(self):
        with loaded_transfer(sdk_modules(with_client=False)) as transfer:
            self.assertFalse(transfer.P115_AVAILABLE)
            self.assertTrue(transfer.P115_SDK_ERROR, "失败原因必须留档，否则只能看到「未安装」")
            with self.assertRaises(transfer.P115Deferred) as ctx:
                transfer.P115Transfer("UID=synthetic_A; CID=synthetic")
            self.assertEqual(ctx.exception.reason, "capability")
            self.assertIn("未安装兼容的115网盘Plus SDK", str(ctx.exception))
            self.assertIn("ImportError", str(ctx.exception), "提示里要带上最后一次导入错误")

    def test_sdk_installed_after_import_heals_without_restart(self):
        with loaded_transfer(sdk_modules(with_client=False)) as transfer:
            self.assertFalse(transfer.P115_AVAILABLE)
            # MP 在插件加载之后才把依赖装进 site-packages
            sys.modules.update(sdk_modules(with_client=True))
            self.addCleanup(lambda: [sys.modules.pop(k, None) for k in ("p115client", "p115client.util")])
            self.assertTrue(transfer.load_sdk(), "依赖到位后必须能重新导入")
            self.assertTrue(transfer.P115_AVAILABLE)
            self.assertEqual(transfer.P115_SDK_ERROR, "")
            self.assertIs(transfer.P115Client, FakeSDK)
            self.assertTrue(callable(transfer.share_extract_payload))
            # 构造不再以 capability 拒绝（这里只验证越过能力闸门，不发起任何请求）
            api = transfer.P115Transfer("UID=synthetic_A; CID=synthetic")
            self.assertIsInstance(api.client, FakeSDK)

    def test_probe_failure_after_success_keeps_capability(self):
        with loaded_transfer(sdk_modules(with_client=True)) as transfer:
            self.assertTrue(transfer.P115_AVAILABLE)
            with patch.dict(sys.modules, {"p115client": ModuleType("p115client")}):
                self.assertTrue(transfer.load_sdk(force=True), "已加载过的能力不能被一次探测失败收回")
            self.assertTrue(transfer.P115_AVAILABLE)

    def test_capability_error_message_is_bounded(self):
        with loaded_transfer(sdk_modules(with_client=False)) as transfer:
            transfer.P115_SDK_ERROR = "X" * 5000
            with self.assertRaises(transfer.P115Deferred) as ctx:
                transfer.P115Transfer("UID=synthetic_A; CID=synthetic")
            message = str(ctx.exception)
            self.assertLess(len(message), 400, "写入任务 message 前必须截断")
            self.assertIn("未安装兼容的115网盘Plus SDK", message)


class ContractStillEnforced(unittest.TestCase):
    """自愈不能放宽 SDK 请求契约校验：装上了但不兼容仍要暂停云端操作。"""

    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))

    def test_incompatible_sdk_still_blocks_cloud_writes(self):
        sdk = sdk_modules(with_client=True, sdk=IncompatibleSDK)  # 缺一个受控端点
        with loaded_transfer(sdk) as transfer:
            transfer.load_sdk(force=True)
            self.assertTrue(transfer.P115_AVAILABLE)
            with self.assertRaises(transfer.P115Deferred) as ctx:
                transfer.P115Transfer("UID=synthetic_A; CID=synthetic")
            self.assertEqual(ctx.exception.reason, "capability")
            self.assertIn("已安装的115 SDK不兼容", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
