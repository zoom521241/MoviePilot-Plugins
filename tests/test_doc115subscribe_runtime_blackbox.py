"""Public plugin actions and worker state machines with synthetic 20-episode batches."""
import copy
import socket
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from test_doc115subscribe_backend import Plugin, STUBS, main, rec


class SyntheticCloud:
    def __init__(self, episodes=20):
        self.episodes = episodes
        self.writes = []
        self.reads = []
        self.last_share_result = {}
        self.last_offline_result = None
        self.parent = "10"
        self.percent = 100
        self.task_present = True
        self.move_result = True
        self.fail_submit = False
        self.uncertain_submit = False
        self.after_submit = None

    def work_slice(self, **kwargs):
        return nullcontext()

    def prepare_share(self, url, path, state=None):
        return {"items": [{"id": "season-source", "name": "Season"}], "complete": True, "cid": 20,
                "received": int((state or {}).get("received") or 0)}

    def share_manifest_slice(self, url, cursor=None):
        return {"items": [{"source_file_id": str(i), "relative_path": f"Season/Show.S01E{i:02}.mkv",
                "required": True, "episodes": [[1, i]]} for i in range(1, self.episodes+1)],
                "complete": True, "cursor": None}

    def receive_prepared(self, url, path, state, before_submit=None):
        before_submit({"url": url})
        self.writes.append(("receive", url, path))
        if self.uncertain_submit:
            self.last_share_result = {"uncertain": True}
            raise RuntimeError("synthetic response lost")
        if self.fail_submit:
            self.last_share_result = {"uncertain": False}
            raise RuntimeError("synthetic definite failure")
        state.update(done=True, received=1)
        if self.after_submit:
            self.after_submit()
        return state

    def offline_add(self, url, path, before_submit=None):
        before_submit({"url": url})
        self.writes.append(("offline", url, path))
        self.last_offline_result = SimpleNamespace(file_id="100", actual_cid="10", accepted=True,
                                                   uncertain=False, duplicate=False)
        return self.last_offline_result

    def get_file_info(self, file_id):
        self.reads.append(("file", file_id))
        return {"id": "100", "parent_id": self.parent, "name": "Season"}

    def path_to_id(self, path, mkdir=False):
        self.reads.append(("path", path))
        return 10 if "磁力" in path else 20

    def list_tasks_slice(self, cursor=None):
        self.reads.append(("tasks", cursor))
        return {"items": [{"info_hash": "a"*40, "percentDone": self.percent, "file_id": "100"}]
                if self.task_present else [], "complete": True, "cursor": None}

    def task_failed(self, task):
        return task.get("status") == 2

    def manifest_slice(self, path, cursor=None, file_id=""):
        return {"items": [{"id": str(100+i), "path": f"{path}/Show.S01E{i:02}.mkv", "required": True,
                "episodes": [[1, i]], "name": f"Show.S01E{i:02}.mkv"} for i in range(1, self.episodes+1)],
                "complete": True, "cursor": None}

    def move_via_p115disk(self, src, dest, file_id=""):
        self.writes.append(("move", src, dest))
        if self.move_result:
            self.parent = "20"
        return self.move_result, "synthetic move failed" if not self.move_result else ""


class RuntimeBlackBox(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", STUBS))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK BLOCKED")))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK BLOCKED")))
        self.tmp = tempfile.TemporaryDirectory(prefix="doc115-blackbox-")
        self.addCleanup(self.tmp.cleanup)
        self.plugin = Plugin()
        self.plugin.synthetic_root = Path(self.tmp.name)
        self.plugin.saved_configs = []
        self.plugin.init_plugin({"enabled": True, "p115_cookie": "SYNTHETIC", "tencent_cookie": "SYNTHETIC"})
        self.addCleanup(self.plugin.stop_service)
        self.cloud = SyntheticCloud()
        self.plugin._transfers = lambda: self.cloud

    def queue(self, **fields):
        candidate = rec("Show Season 1", media_type="tv", sheet="电视剧", tmdbid="900", **fields)
        ok, _ = self.plugin.do_transfer(candidate, "tv")
        self.assertTrue(ok)
        return self.plugin._records().list()[0]

    def tick(self, count=1):
        for _ in range(count):
            for task in self.plugin._records().list(limit=None, include_hidden=True):
                self.plugin._records().update(task["id"], next_check_at=0)
            self.plugin.check_offline_tasks()

    def histories(self, batch, count=20, *, failed=(), older=False):
        return [{"id": i, "title": "Show", "year": "2025", "type": "电视剧", "tmdbid": "900",
            "src": f"{batch['final_path']}/Season/Show.S01E{i:02}.mkv", "src_storage": "115网盘Plus",
            "date": batch["created_ts"] + (-100 if older else i), "status": i not in failed,
            "seasons": "S01", "episodes": f"E{i:02}"} for i in range(1, count+1)]

    def organize(self, batch, entries):
        self.plugin._records().update(batch["id"], org_next_ts=0)
        self.plugin._mp_api_json = Mock(return_value={"success": True, "data": {"list": entries, "total": len(entries)}})
        self.plugin.check_organization()
        return self.plugin._records().get(batch["id"])

    def test_share_twenty_success_and_display_delete_preserves_resource_hold(self):
        batch = self.queue()
        self.assertEqual(self.cloud.writes, [])
        self.tick()
        batch = self.plugin._records().get(batch["id"])
        self.assertEqual(batch["acquisition_status"], "saved")
        self.assertEqual(len(batch["manifest"]), 20)
        result = self.organize(batch, self.histories(batch))
        self.assertEqual(result["organization_status"], "success")
        self.plugin.api_records_delete({"id": batch["id"]})
        self.assertEqual(self.plugin.api_records()["data"]["total"], 0)
        self.assertTrue(self.plugin.do_transfer(rec("Show Season 1", media_type="tv", sheet="电视剧", tmdbid="900"), "tv")[0])
        self.tick()
        self.assertEqual(len(self.cloud.writes), 1)

    def test_episode_deleted_before_mp_organization_is_19_of_20_without_reacquire(self):
        batch = self.queue()
        self.tick()
        result = self.organize(batch, self.histories(batch, 19))
        self.assertEqual((result["acquisition_status"], result["organization_status"]), ("saved", "partial"))
        self.assertEqual((result["organized_count"], result["organized_total"], result["organized_missing"]), (19, 20, 1))
        self.plugin.api_retry_task({"id": batch["id"]})
        self.tick(2)
        self.assertEqual(len(self.cloud.writes), 1)
        result = self.organize(result, self.histories(batch, 20))
        self.assertEqual(result["organization_status"], "success")

    def test_all_mp_failures_and_recovery_never_change_acquisition(self):
        batch = self.queue()
        self.tick()
        result = self.organize(batch, self.histories(batch, failed=range(1, 21)))
        self.assertEqual(result["organization_status"], "failed")
        self.assertEqual(result["acquisition_status"], "saved")
        result = self.organize(batch, [{**x, "id": x["id"]+100, "date": x["date"]+100} for x in self.histories(batch)])
        self.assertEqual(result["organization_status"], "success")
        self.assertEqual(len(self.cloud.writes), 1)

    def test_magnet_single_batch_single_directory_move_and_task_cleaned_recovery(self):
        batch = self.queue(links=[("magnet", "magnet:?xt=urn:btih:" + "a"*40)], expected_episodes=list(range(1, 21)))
        self.tick(2)
        self.assertEqual([x[0] for x in self.cloud.writes], ["offline", "move"])
        self.cloud.task_present = False
        self.tick()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["acquisition_status"], "saved")
        self.assertEqual(result["move_status"], "success")
        self.assertEqual(len(self.cloud.writes), 2)

    def test_magnet_without_declared_episodes_completes_from_this_batch_manifest(self):
        """方案 A：未声明集数时按「本批源清单完整 + 本批全部入库」判成功（旧逻辑会让整季包永远判不了成功）。"""
        self.cloud.episodes = 19
        batch = self.queue(links=[("magnet", "magnet:?xt=urn:btih:" + "a"*40)])
        self.tick(3)
        result = self.organize(batch, self.histories(batch, 19))
        self.assertEqual(result["organized_count"], 19)
        self.assertTrue(result["manifest_complete"])
        self.assertEqual(result["organization_status"], "success")
        self.assertEqual(len(self.cloud.writes), 2)

    def test_deleted_during_first_magnet_scan_with_twenty_expected_remains_incomplete(self):
        self.cloud.episodes = 19
        batch = self.queue(links=[("magnet", "magnet:?xt=urn:btih:" + "a"*40)], expected_episodes=list(range(1, 21)))
        self.tick(3)
        result = self.organize(batch, self.histories(batch, 19))
        self.assertFalse(result["manifest_complete"])
        self.assertNotEqual(result["organization_status"], "success")

    def test_uncertain_submission_never_tries_mirror_or_resubmits(self):
        self.cloud.uncertain_submit = True
        batch = self.queue(links=[("115_share", "https://115.com/s/SYNTHETIC"),
                                 ("magnet", "magnet:?xt=urn:btih:" + "a"*40)])
        self.tick(4)
        self.assertEqual(len(self.cloud.writes), 1)
        self.assertEqual(self.plugin._records().get(batch["id"])["acquisition_status"], "uncertain")

    def test_stop_during_sent_success_keeps_receipt_and_no_later_request(self):
        batch = self.queue()
        self.cloud.after_submit = self.plugin.stop_service
        self.tick()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["acquisition_status"], "saved")
        self.assertEqual(self.plugin._records().attempts(batch["id"])[0]["outcome"], "success")
        self.plugin.check_offline_tasks()
        self.assertEqual(len(self.cloud.writes), 1)

    def test_mp_error_retreat_and_manual_checks_do_not_bypass_cooldown(self):
        batch = self.queue()
        self.tick()
        self.plugin._records().update(batch["id"], org_next_ts=0)
        failure = Mock(side_effect=RuntimeError("synthetic MP unavailable"))
        self.plugin._mp_api_json = failure
        self.plugin.check_organization()
        old = self.plugin._records().get(batch["id"])["org_next_ts"]
        for _ in range(12):
            self.plugin.api_records_verify({"id": batch["id"]})
            self.plugin.check_organization()
        self.assertEqual(failure.call_count, 1)
        self.assertGreaterEqual(self.plugin._records().get(batch["id"])["org_next_ts"], old)

    def test_stale_same_name_history_never_confirms_and_diagnostics_are_local(self):
        batch = self.queue()
        self.tick()
        result = self.organize(batch, self.histories(batch, older=True))
        self.assertNotEqual(result["organization_status"], "success")
        self.cloud.reads.clear()
        self.plugin._mp_api_json.reset_mock()
        self.plugin.api_records()
        self.plugin.api_diagnostics()
        self.plugin.api_subscriptions_preview()
        self.assertEqual(self.cloud.reads, [])
        self.plugin._mp_api_json.assert_not_called()

    def test_account_switch_pauses_old_queue_before_any_cloud_request(self):
        batch = self.queue()
        self.plugin._p115_cookie = "OTHER_SYNTHETIC_ACCOUNT"
        self.tick()
        self.assertEqual(self.cloud.writes, [])
        self.assertFalse(self.plugin._records().get(batch["id"])["tracking_enabled"])

    def test_crash_after_share_intent_recovers_uncertain_without_mirror_fallback(self):
        batch = self.queue(links=[("115_share", "https://115.com/s/SYNTHETIC"),
                                 ("magnet", "magnet:?xt=urn:btih:" + "a"*40)])
        self.plugin._records().begin_attempt(batch["id"], phase="share_receive", generation=self.plugin._generation)
        self.tick(4)
        self.assertEqual(self.cloud.writes, [])
        self.assertEqual(self.plugin._records().get(batch["id"])["acquisition_status"], "uncertain")

    def test_partial_share_followup_budget_deferral_resumes_only_remaining_chunk(self):
        from importlib import import_module
        Deferred = import_module(main.__package__ + ".p115_transfer").P115Deferred
        batch = self.queue()
        real = self.cloud.receive_prepared
        steps = []
        def receive(url, path, state, before_submit=None):
            if not steps:
                before_submit({"offset": 0})
                self.cloud.writes.append(("receive", "first200", path))
                state.update(received=200, done=False)
                steps.append("first")
                return state
            if len(steps) == 1:
                steps.append("deferred")
                raise Deferred("synthetic slice budget", reason="slice", not_sent=True, state=state)
            before_submit({"offset": 200})
            self.cloud.writes.append(("receive", "remaining1", path))
            state.update(received=201, done=True)
            return state
        self.cloud.receive_prepared = receive
        self.tick(3)
        self.assertEqual([x[1] for x in self.cloud.writes], ["first200", "remaining1"])
        self.assertEqual(self.plugin._records().get(batch["id"])["acquisition_status"], "saved")

    def test_migrating_invalid_legacy_json_never_leaves_an_unprotected_empty_ledger(self):
        root = Path(self.tmp.name) / "invalid-legacy"
        root.mkdir()
        self.plugin.synthetic_root = root
        self.plugin._ledger_instance = None
        (root / "history.json").write_text('{"invalid":"not a list"}', encoding="utf-8")
        for _ in range(2):
            with self.assertRaises(ValueError):
                self.plugin._records()
        self.assertIsNone(self.plugin._ledger_instance)
        self.assertEqual(self.cloud.writes, [])

    def test_unrelated_shared_directory_events_do_not_block_real_batch_event(self):
        batch = self.queue()
        self.tick()
        for i in range(51):
            event = SimpleNamespace(event_type=SimpleNamespace(value="transfer.complete"), event_data={
                "fileitem": {"path": batch["final_path"] + f"/Unrelated/{i}.mkv", "storage": "115网盘Plus"}})
            self.plugin._receive_event(event)
        self.assertEqual(self.plugin._records().drain_events(), [])
        source = batch["final_path"] + "/Season/Show.S01E01.mkv"
        event = SimpleNamespace(event_type=SimpleNamespace(value="transfer.complete"), event_data={
            "fileitem": {"path": source, "storage": "115网盘Plus"},
            "mediainfo": {"title": "Show", "type": "电视剧", "year": "2025", "tmdbid": "900"}})
        self.plugin._receive_event(event)
        self.plugin._drain_events()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["organized_count"], 1)
        self.assertNotEqual(result["organization_status"], "success")

    def test_task_action_validates_server_permissions_and_never_accepts_unknown_write(self):
        batch = self.queue()
        self.tick()
        self.assertEqual(self.plugin.api_task_action({"id": batch["id"], "action": "retry_submit"})["code"], 1)
        self.assertEqual(self.plugin.api_task_action({"id": batch["id"], "action": "verify"})["code"], 0)
        self.assertEqual(self.cloud.writes[0][0], "receive")
        self.assertEqual(len(self.cloud.writes), 1)

    def test_refresh_resolution_and_subtitle_are_independent_filters(self):
        self.plugin._index = main.DocIndex(self.plugin._new_client())
        self.plugin._index._set_records([rec("Synthetic 1", qtext="1080P"), rec("Synthetic 2", qtext="1080P 中文字幕"),
                                        rec("Synthetic 3", qtext="4K 中文字幕")])
        response = self.plugin.api_search({"keyword": "Synthetic", "quality": "1080p", "subtitle": "cn"})
        self.assertEqual(response["data"]["total"], 1)
        self.assertEqual(response["data"]["records"][0]["title"], "Synthetic 2")


if __name__ == "__main__":
    unittest.main()
