"""0.11.9 契约：整理核对遇到 MP 读取排队（MPDeferred）时退避重试，而不是把这一轮当失败丢掉。

全部合成：不连 MP、不连 115、不读真实账本。
"""
import sys
import time
import unittest
from unittest.mock import Mock, patch

import test_doc115subscribe_backend as backend


def deferred_class(plugin):
    """取插件真正 import 的 MPDeferred（而不是另造一个同名异常）。"""
    return plugin.check_organization.__func__.__globals__["MPDeferred"]


class OrganizationRetryTests(unittest.TestCase):
    setUp = backend.BackendTests.setUp
    tearDown = backend.BackendTests.tearDown

    def test_mp_queueing_backs_off_then_recovers_without_error_tick(self):
        plugin = self.plugin
        deferred = deferred_class(plugin)
        plugin.verify_organization = Mock(side_effect=deferred("MP读取已排队", time.time() + 5))

        first = plugin.check_organization()
        self.assertEqual(first["code"], 0, "排队不该被当成插件错误")
        self.assertTrue(first["data"]["deferred"])
        self.assertEqual(first["data"]["attempts"], 1)
        self.assertEqual(plugin._last_org_tick["state"], "deferred")
        retry_at = plugin._org_retry_at
        self.assertAlmostEqual(retry_at - time.time(), 40, delta=5, msg="首次排队按 40 秒退避")

        # 退避窗口内：不再打 MP、不重复记错误、仍是同一个 attempts
        second = plugin.check_organization()
        self.assertTrue(second["data"]["deferred"])
        self.assertEqual(second["data"]["attempts"], 1)
        self.assertEqual(plugin.verify_organization.call_count, 1)
        self.assertEqual(plugin._last_org_tick["state"], "deferred")

        # 窗口结束后 MP 恢复：正常执行、清零退避计数并留 retries 痕迹
        plugin.verify_organization = Mock(return_value={"checked": 0, "confirmed": 0, "changed": 0,
                                                        "partial": 0, "failed": 0, "unfound": 0})
        with patch("time.time", return_value=retry_at + 1):
            third = plugin.check_organization()
        self.assertEqual(third["code"], 0)
        self.assertNotIn("deferred", third.get("data") or {})
        self.assertEqual(plugin._last_org_tick["state"], "ok")
        self.assertEqual(plugin._last_org_tick["retries"], 1)
        self.assertEqual((plugin._org_retry_attempts, plugin._org_retry_at), (0, 0))

    def test_backoff_grows_and_is_capped(self):
        plugin = self.plugin
        deferred = deferred_class(plugin)
        plugin.verify_organization = Mock(side_effect=deferred("MP读取已排队", 0))
        delays = []
        now = time.time()
        for attempt in range(1, 7):
            with patch("time.time", return_value=now):
                plugin.check_organization()
            delays.append(round(plugin._org_retry_at - now))
            now = plugin._org_retry_at + 1      # 走出窗口，制造下一次排队
        self.assertEqual(delays, [40, 80, 160, 300, 300, 300])
        self.assertEqual(plugin._org_retry_attempts, 6)

    def test_non_queue_errors_still_report_failure(self):
        plugin = self.plugin
        plugin.verify_organization = Mock(side_effect=RuntimeError("synthetic failure"))
        result = plugin.check_organization()
        self.assertEqual(result["code"], 1)
        self.assertEqual(plugin._last_org_tick["state"], "error")
        self.assertEqual(getattr(plugin, "_org_retry_at", 0), 0)

    def test_manual_verify_clears_the_retry_window(self):
        plugin = self.plugin
        deferred = deferred_class(plugin)
        plugin.verify_organization = Mock(side_effect=deferred("MP读取已排队", 0))
        plugin.check_organization()
        self.assertGreater(plugin._org_retry_at, time.time())

        target = plugin._records().add({"title": "Synthetic", "hash": "b" * 40, "status": "success",
                                        "acquisition_status": "saved", "organization_status": "unfound"})
        plugin.api_records_verify({"id": target["id"]})
        self.assertEqual(plugin._org_retry_at, 0, "手动核对要立即生效，不等退避窗口")
        self.assertEqual(plugin._org_retry_attempts, 1, "退避计数保留，仍在排队时不要立刻刷爆")


if __name__ == "__main__":
    unittest.main()
