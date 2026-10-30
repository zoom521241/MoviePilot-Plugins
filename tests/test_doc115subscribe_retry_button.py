"""「需要处理」记录的「重试」按钮：恢复跟踪但不重复提交真实请求。

复现的真实故障：SDK 能力探测失败时 ``check_offline_tasks`` 抛 ``P115Deferred(reason="capability")``，
``_defer_task`` 会把批次置为 ``tracking_enabled=0`` 且不再自动重试；旧版本此时不给用户任何操作按钮，
只能删记录重来。这里验证新按钮：放回队列、清错误、不产生第二次云端写。
"""
import unittest
from contextlib import nullcontext
from types import SimpleNamespace

import test_doc115subscribe_runtime_blackbox as blackbox


class CapabilityError(Exception):
    """与 request_budget.P115Deferred 同形：能力不足，属于本地原因。"""

    reason = "capability"


class RetryButton(unittest.TestCase):
    # 复用黑盒夹具（合成云端 + 临时数据目录）。用模块限定名引用，
    # 避免把父类用例重新注册一遍（unittest 会收集模块里导入的每个 TestCase）。
    setUp = blackbox.RuntimeBlackBox.setUp
    tearDown = blackbox.RuntimeBlackBox.tearDown
    queue = blackbox.RuntimeBlackBox.queue
    tick = blackbox.RuntimeBlackBox.tick
    histories = blackbox.RuntimeBlackBox.histories
    organize = blackbox.RuntimeBlackBox.organize
    def pause_with_capability_failure(self):
        """让下一轮离线 worker 撞上「SDK 不可用」，与线上 16:01 的现场一致。"""
        row = self.queue()
        cloud = self.cloud

        def broken():
            raise CapabilityError("未安装兼容的115网盘Plus SDK；搜索可用，云端获取暂不可用")

        self.plugin._transfers = broken
        try:
            self.tick()
        finally:
            self.plugin._transfers = lambda: cloud
        return self.plugin._records().get(row["id"])

    def view(self, row):
        return next(r for r in self.plugin.api_records()["data"]["records"] if r["id"] == row["id"])

    def test_capability_pause_is_offered_a_retry_button(self):
        row = self.pause_with_capability_failure()
        self.assertFalse(row["tracking_enabled"], "能力不足必须暂停自动跟踪，避免每 2 秒刷屏")
        self.assertEqual(row["acquisition_status"], "queued")
        self.assertIn("需要处理", row["message"])
        self.assertIn("SDK", row["message"])
        view = self.view(row)
        self.assertIn("retry", view["allowed_actions"])
        self.assertIn(view["pause_reason"], row["message"], "暂停原因要能直接展示给用户")
        # 暂停的批次既不在「进行中」，也不会被悄悄重试
        self.assertEqual(self.plugin.records_stats()["active"], 0)
        self.assertEqual(self.plugin.records_stats()["attention"], 1)

    def test_retry_restores_tracking_and_resumes_the_same_batch(self):
        row = self.pause_with_capability_failure()
        self.assertEqual(self.cloud.writes, [], "暂停期间不应有任何云端写")
        result = self.plugin.api_task_action({"id": row["id"], "action": "retry"})
        self.assertEqual(result["code"], 0, result.get("msg"))
        restored = self.plugin._records().get(row["id"])
        self.assertTrue(restored["tracking_enabled"])
        self.assertEqual(restored["query_error"], "")
        self.assertEqual(restored["last_error"], "")
        self.assertGreater(restored["next_check_at"], 0)
        self.assertIn("手动重试", restored["message"])
        self.assertEqual(self.cloud.writes, [], "重试按钮本身不得发云请求")

        # 恢复后的下一轮：按原状态继续，只提交一次
        self.plugin._records().update(row["id"], next_check_at=0)
        self.plugin.check_offline_tasks()
        self.assertEqual(len(self.cloud.writes), 1)
        saved = self.plugin._records().get(row["id"])
        self.assertEqual(saved["acquisition_status"], "saved")
        self.assertTrue(saved["tracking_enabled"])

    def test_retry_is_idempotent_and_cannot_be_replayed(self):
        row = self.pause_with_capability_failure()
        self.assertEqual(self.plugin.api_task_action({"id": row["id"], "action": "retry"})["code"], 0)
        again = self.plugin.api_task_action({"id": row["id"], "action": "retry"})
        self.assertEqual(again["code"], 1, "恢复跟踪后按钮应消失，重复点击必须被拒绝")
        self.assertIn("不允许此操作", again["msg"])
        self.assertEqual(self.cloud.writes, [])

    def test_uncertain_batch_keeps_reconcile_instead_of_retry(self):
        self.cloud.uncertain_submit = True
        row = self.queue()
        self.tick()
        view = self.view(self.plugin._records().get(row["id"]))
        self.assertNotIn("retry", view["allowed_actions"], "提交结果不明时要走只读核对，不能盲目重试")
        self.assertIn("reconcile", view["allowed_actions"])
        self.assertEqual(self.plugin.api_task_action({"id": row["id"], "action": "retry"})["code"], 1)

    def test_retry_rejects_finished_batches(self):
        row = self.queue()
        self.tick(2)
        done = self.plugin._records().get(row["id"])
        self.assertEqual(done["acquisition_status"], "saved")
        self.assertEqual(self.plugin.retry_paused_task(done)["code"], 1)
        self.assertIn("核对转存结果", self.plugin.retry_paused_task(done)["msg"])

    def test_retry_while_capability_is_still_broken_pauses_again(self):
        """按钮不能把插件拖进 2 秒一次的死循环：能力仍不足时只退回暂停，不发任何云请求。"""
        row = self.pause_with_capability_failure()

        def broken():
            raise CapabilityError("未安装兼容的115网盘Plus SDK；搜索可用，云端获取暂不可用")

        self.plugin.api_task_action({"id": row["id"], "action": "retry"})
        self.plugin._transfers = broken
        try:
            self.tick(3)
        finally:
            self.plugin._transfers = lambda: self.cloud
        rec = self.plugin._records().get(row["id"])
        self.assertFalse(rec["tracking_enabled"], "再次失败必须重新暂停，而不是无限重试")
        self.assertIn("需要处理", rec["message"])
        self.assertEqual(rec["acquisition_status"], "queued")
        self.assertEqual(self.cloud.writes, [])
        self.assertIn("retry", self.view(rec)["allowed_actions"], "用户修好原因后还能再点一次")


if __name__ == "__main__":
    unittest.main()
