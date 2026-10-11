"""0.11.4 regressions (synthetic data only): 人工确认已整理入口、整理匹配规则升级后的一次性重开、
后台任务与离线状态机解耦、账本 WAL 与索引列、目录对账次数上限、文档地址留空。"""
import importlib.util
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from test_doc115subscribe_backend import main
from test_doc115subscribe_ledger import TaskLedger
from test_doc115subscribe_organization import PACKAGE, SOURCE

spec = importlib.util.spec_from_file_location(PACKAGE + ".runtime", SOURCE / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)

_transfer_spec = importlib.util.spec_from_file_location(PACKAGE + ".p115_transfer", SOURCE / "p115_transfer.py")
transfer_module = importlib.util.module_from_spec(_transfer_spec)
sys.modules[_transfer_spec.name] = transfer_module
_transfer_spec.loader.exec_module(transfer_module)


class _Probe(runtime.TaskRuntime):
    """只借用 TaskRuntime 的判定与视图逻辑，不启动任何后台线程。"""


class RecordActionContractTests(unittest.TestCase):
    def view(self, **fields):
        return _Probe()._record_view(fields)

    def test_confirm_organized_is_offered_for_saved_unfinished_batches(self):
        """已转存但整理未判成功的批次（unfound / partial / unknown / failed）都要给出人工入口。

        真实故障：该按钮此前只在 organization_status == "unfound" 时加入 allowed_actions，
        而前端动作表又漏登记了这个动作，导致需处理清单里根本没有按钮可点。
        """
        for status in ("unfound", "partial", "unknown", "failed"):
            with self.subTest(status=status):
                actions = self.view(title="X", acquisition_status="saved", organization_status=status,
                                    manifest_complete=True)["allowed_actions"]
                self.assertIn("confirm_organized", actions)

    def test_confirm_organized_requires_files_and_disappears_when_done(self):
        self.assertNotIn("confirm_organized",
                         self.view(title="X", acquisition_status="saved", organization_status="unfound")["allowed_actions"])
        self.assertNotIn("confirm_organized",
                         self.view(title="X", acquisition_status="saved", organization_status="success",
                                   manifest_complete=True)["allowed_actions"])
        self.assertNotIn("confirm_organized",
                         self.view(title="X", acquisition_status="downloading",
                                   organization_status="unknown", manifest_complete=True)["allowed_actions"])

    def test_manual_confirmation_does_not_contradict_the_file_list(self):
        item = self.view(title="X", acquisition_status="saved", organization_status="success",
                         organization_confirmed=True, manifest_complete=True,
                         manifest=[{"unit_key": "u1", "name": "a.mkv", "source_path": "/d/a.mkv", "required": True}])
        self.assertEqual(item["files"][0]["status"], "manual")
        self.assertIn("人工确认", item["files"][0]["message"])


class MatcherUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-v0114-")
        self.addCleanup(self.temp.cleanup)
        self.ledger = TaskLedger(Path(self.temp.name) / "t.sqlite3")
        batch = self.ledger.claim_resource("synthetic-v0114", {"title": "X", "type": "movie"})["batch"]
        self.batch_id = batch["id"]
        self.ledger.set_manifest(self.batch_id, [{"source_path": "/d/a.mkv", "storage": "115", "file_id": "1"}],
                                 complete=True)
        self.ledger.update(self.batch_id, acquisition_status="saved", organization_status="unfound", org_giveup=True)

    def test_reopen_clears_giveup_exactly_once_per_revision(self):
        """整理匹配规则升级后，已放弃的批次要重新纳入自动核对；同一版本只重开一次。"""
        self.assertEqual(self.ledger.reopen_unverified_organization(2), 1)
        current = self.ledger.get(self.batch_id)
        self.assertFalse(current["org_giveup"])
        self.assertEqual(int(current["org_attempts"] or 0), 0)
        self.assertEqual(int(current["org_stale_count"] or 0), 0)
        self.assertLessEqual(float(current["org_next_ts"] or 0), time.time() + 1)
        # 同一 revision 不再重复重开，更低 revision 也不会倒回去
        self.assertEqual(self.ledger.reopen_unverified_organization(2), 0)
        self.assertEqual(self.ledger.reopen_unverified_organization(1), 0)
        # 更高 revision 才允许再重开一次
        self.ledger.update(self.batch_id, organization_status="unfound", org_giveup=True)
        self.assertEqual(self.ledger.reopen_unverified_organization(3), 1)

    def test_reopen_skips_successful_and_stopped_batches(self):
        self.ledger.update(self.batch_id, organization_status="success", org_giveup=True)
        self.assertEqual(self.ledger.reopen_unverified_organization(9), 0)
        self.ledger.update(self.batch_id, organization_status="unfound", tracking_enabled=False, org_giveup=True)
        self.assertEqual(self.ledger.reopen_unverified_organization(10), 0)


class LedgerStorageTests(unittest.TestCase):
    """账本读写：task_file_id 索引列（不再全表反序列化）。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-v0114-store-")
        self.addCleanup(self.temp.cleanup)
        self.ledger = TaskLedger(Path(self.temp.name) / "t.sqlite3")

    def test_claimed_task_file_ids_skips_self_and_blanks(self):
        first = self.ledger.claim_resource("synthetic-a", {"title": "A"})["batch"]
        second = self.ledger.claim_resource("synthetic-b", {"title": "B"})["batch"]
        self.ledger.update(first["id"], task_file_id="111")
        self.ledger.update(second["id"], task_file_id="222")
        self.assertEqual(self.ledger.claimed_task_file_ids(first["id"]), {"222"})
        self.assertEqual(self.ledger.claimed_task_file_ids(), {"111", "222"})
        self.ledger.update(second["id"], task_file_id="")
        self.assertEqual(self.ledger.claimed_task_file_ids(first["id"]), set())

    def test_task_file_id_is_backfilled_into_its_index_column(self):
        batch = self.ledger.claim_resource("synthetic-c", {"title": "C"})["batch"]
        self.ledger.update(batch["id"], task_file_id="333")
        with closing(sqlite3.connect(str(self.ledger.path))) as db:
            row = db.execute("SELECT task_file_id FROM batches WHERE batch_id=?", (batch["id"],)).fetchone()
        self.assertEqual(row[0], "333")


class DirectoryReconcileTests(unittest.TestCase):
    def test_reconcile_attempts_are_bounded_per_path(self):
        """永久失败的建目录不能变成无限重试：同一路径最多对账 MAX_RECONCILE_ATTEMPTS 次。"""
        transfer = transfer_module.P115Transfer.__new__(transfer_module.P115Transfer)
        transfer._dir_cache = {}
        allowed = [transfer._reconcile_allowed("/x/y") for _ in range(transfer.MAX_RECONCILE_ATTEMPTS + 1)]
        self.assertEqual(allowed, [True] * transfer.MAX_RECONCILE_ATTEMPTS + [False])
        self.assertTrue(transfer._reconcile_allowed("/other"), "不同路径互不影响")
        transfer._remember_directory("/x/y", 7)                 # 目录确认成功即清零
        self.assertTrue(transfer._reconcile_allowed("/x/y"))


class DocumentUrlConfigTests(unittest.TestCase):
    def test_default_document_url_is_empty(self):
        """不预置文档地址：新装用户必须自己填写，避免默认去读仓库作者的个人文档。"""
        self.assertEqual(main.Doc115Subscribe.DEFAULTS["doc_url"], "")

    def test_empty_document_url_is_allowed_and_invalid_host_is_still_rejected(self):
        base = {**main.Doc115Subscribe.DEFAULTS}
        self.assertEqual(main.Doc115Subscribe._validate_config(base)["doc_url"], "")
        self.assertEqual(main.Doc115Subscribe._validate_config(
            {**base, "doc_url": "https://docs.qq.com/sheet/SyntheticDocument"})["doc_url"],
            "https://docs.qq.com/sheet/SyntheticDocument")
        with self.assertRaises(ValueError):
            main.Doc115Subscribe._validate_config({**base, "doc_url": "https://docs.qq.com.evil.invalid/sheet/X"})
