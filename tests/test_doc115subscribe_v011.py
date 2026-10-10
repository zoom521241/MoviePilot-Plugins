"""0.11.0 回归：事件对象序列化、启动清理、日志降噪、新 API 契约、并发覆盖保护（全部合成数据，禁止网络）。"""
import dataclasses
import enum
import json
import socket
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_doc115subscribe_backend import Plugin, STUBS, main, rec
from test_doc115subscribe_runtime_blackbox import SyntheticCloud


class SyntheticMediaType(enum.Enum):
    TV = "电视剧"


@dataclasses.dataclass
class DataclassMediaInfo:
    """历史上/插件间出现过的 dataclass 版 MediaInfo；带大量与身份无关的字段。"""
    title: str = "Show"
    year: str = "2025"
    type: SyntheticMediaType = SyntheticMediaType.TV
    tmdb_id: int = 900
    season: int = 1
    overview: str = "x" * 5000
    actors: list = dataclasses.field(default_factory=lambda: [{"name": "a"}] * 50)


class PlainMeta:
    def __init__(self):
        self.name = "Show"
        self.year = "2025"
        self.begin_season = 1
        self._private = object()


class PydanticLike:
    """pydantic 风格：只暴露 model_dump。"""
    def __init__(self, **values):
        self._values = values

    def model_dump(self, **kwargs):
        return {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in self._values.items()}

    def __getattr__(self, name):
        try:
            return self.__dict__["_values"][name]
        except KeyError:
            raise AttributeError(name) from None


class V011Base(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", STUBS))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK BLOCKED")))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK BLOCKED")))
        self.tmp = tempfile.TemporaryDirectory(prefix="doc115-v011-")
        self.addCleanup(self.tmp.cleanup)
        self.plugin = Plugin()
        self.plugin.synthetic_root = Path(self.tmp.name)
        self.plugin.saved_configs = []
        self.plugin.init_plugin({"enabled": True, "p115_cookie": "SYNTHETIC", "tencent_cookie": "SYNTHETIC"})
        self.addCleanup(self.plugin.stop_service)
        self.cloud = SyntheticCloud()
        self.plugin._transfers = lambda: self.cloud

    def queue(self, title="Show Season 1", **fields):
        candidate = rec(title, media_type="tv", sheet="电视剧", tmdbid="900", **fields)
        ok, msg = self.plugin.do_transfer(candidate, "tv")
        self.assertTrue(ok, msg)
        return self.plugin._records().list()[0]

    def tick(self, count=1):
        for _ in range(count):
            for task in self.plugin._records().list(limit=None, include_hidden=True):
                self.plugin._records().update(task["id"], next_check_at=0)
            self.plugin.check_offline_tasks()

    def histories(self, batch, count=20, failed=()):
        return [{"id": i, "title": "Show", "year": "2025", "type": "电视剧", "tmdbid": "900",
                 "src": f"{batch['final_path']}/Season/Show.S01E{i:02}.mkv", "src_storage": "115网盘Plus",
                 "date": batch["created_ts"] + i, "status": i not in failed} for i in range(1, count + 1)]

    def mp_returns(self, entries):
        self.plugin._mp_api_json = Mock(return_value={"success": True, "data": {"list": entries, "total": len(entries)}})
        return self.plugin._mp_api_json

    def saved_batch(self):
        batch = self.queue()
        self.tick()
        batch = self.plugin._records().get(batch["id"])
        self.assertEqual(batch["acquisition_status"], "saved")
        return batch


class EventPayloadTests(V011Base):
    def test_object_payloads_are_reduced_to_identity_and_associate(self):
        batch = self.saved_batch()
        source = batch["final_path"] + "/Season/Show.S01E01.mkv"
        fileitem = PydanticLike(storage="115网盘Plus", path=source, name="Show.S01E01.mkv", type="file", size=1)
        target = PydanticLike(storage="u115", path="/links/Show/S01E01.mkv", name="S01E01.mkv")
        transfer = PydanticLike(success=True, fileitem=fileitem, target_diritem=PydanticLike(path="/links/Show"),
                                target_item=target, transfer_type="move", file_count=1, file_list=[source],
                                file_list_new=["/links/Show/S01E01.mkv"], fail_list=[], message="")
        event = SimpleNamespace(event_type=SimpleNamespace(value="transfer.complete"), event_data={
            "fileitem": fileitem, "mediainfo": DataclassMediaInfo(), "meta": PlainMeta(), "transferinfo": transfer,
            "unrelated": object(), "downloader": "synthetic"})
        self.plugin._receive_event(event)
        self.plugin._receive_event(event)            # 重复投递只入库一次
        with closing(sqlite3.connect(self.plugin._records().path)) as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM event_inbox")]
        self.assertEqual(len(rows), 1)
        payload = rows[0]
        self.assertEqual(set(payload) - {"_event_type", "_batch_ids", "_received_ts"},
                         {"fileitem", "mediainfo", "meta", "transferinfo"})
        self.assertEqual(payload["mediainfo"]["type"], "电视剧")
        self.assertEqual(payload["mediainfo"]["tmdbid"], "900")
        self.assertNotIn("overview", payload["mediainfo"])
        self.assertNotIn("actors", payload["mediainfo"])
        self.assertEqual(payload["meta"]["begin_season"], 1)
        self.assertNotIn("file_list", payload["transferinfo"])
        self.plugin._drain_events()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["organized_count"], 1)
        evidence = self.plugin._records().get_evidence(batch["id"])[0]
        self.assertEqual(evidence["dest_fileitem"]["path"], "/links/Show/S01E01.mkv")   # target_item 优先
        self.assertIs(evidence["status"], True)

    def test_transferinfo_success_false_wins_over_event_type(self):
        batch = self.saved_batch()
        source = batch["final_path"] + "/Season/Show.S01E02.mkv"
        event = SimpleNamespace(event_type="transfer.complete", event_data={
            "fileitem": {"path": source, "storage": "115网盘Plus"},
            "mediainfo": {"title": "Show", "type": SyntheticMediaType.TV, "year": "2025", "tmdb_id": 900},
            "transferinfo": {"success": False, "message": "synthetic failure", "target_diritem": {"path": "/links/Show"}}})
        self.plugin._receive_event(event)
        self.plugin._drain_events()
        evidence = self.plugin._records().get_evidence(batch["id"])[0]
        self.assertIs(evidence["status"], False)
        self.assertEqual(evidence["dest_fileitem"]["path"], "/links/Show")      # 回退 target_diritem
        self.assertEqual(evidence["errmsg"], "synthetic failure")

    def test_plain_handles_set_enum_depth_and_cycles(self):
        nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
        self.assertIsNone(self.plugin._plain(nested)["a"]["b"]["c"]["d"]["e"]["f"])
        self.assertEqual(self.plugin._plain({3, 1, 2}), [1, 2, 3])
        self.assertEqual(self.plugin._plain(SyntheticMediaType.TV), "电视剧")
        loop = PlainMeta()
        loop.self_ref = loop
        json.dumps(self.plugin._plain(loop))         # 深度限制保证不会无限递归

    def test_legacy_repr_events_do_not_crash_and_are_acked_at_startup(self):
        batch = self.saved_batch()
        store = self.plugin._records()
        source = batch["final_path"] + "/Season/Show.S01E01.mkv"
        for i in range(71):
            store.enqueue_event(f"legacy-{i}", {"fileitem": {"path": source, "storage": "115网盘Plus"},
                                                "mediainfo": "MediaInfo(media_source='themoviedb', title='Show')",
                                                "_batch_ids": [batch["id"]], "_received_ts": time.time()})
        # 即使未清理，处理时也不会再抛 TypeError
        self.plugin._apply_queued_event(store, store.drain_events(1)[0])
        self.plugin.init_plugin({"enabled": True, "p115_cookie": "SYNTHETIC", "tencent_cookie": "SYNTHETIC"})
        self.assertEqual(store.event_counts()["pending"], 0)
        self.assertGreaterEqual(self.plugin._last_maintenance["legacy_events_acked"], 70)
        self.assertIsNotNone(store.get(batch["id"]))                           # 不删除批次


class LedgerMaintenanceTests(V011Base):
    def test_old_acknowledged_rows_and_excess_evidence_are_pruned(self):
        batch = self.saved_batch()
        store = self.plugin._records()
        store.MAX_EVIDENCE_PER_BATCH = 30
        store.enqueue_event("old-ack", {"synthetic": 1})
        store.ack_event("old-ack")
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("UPDATE event_inbox SET created_ts=? WHERE event_id='old-ack'", (time.time() - 8 * 86400,))
            for i in range(60):
                db.execute("INSERT INTO evidence(batch_id,evidence_key,payload) VALUES(?,?,?)",
                           (batch["id"], f"stale-{i}", json.dumps({"evidence_at": i})))
        attempts = len(store.attempts(batch["id"]))
        result = store.maintenance()
        self.assertEqual(result["inbox_deleted"], 1)
        self.assertEqual(len(store.get_evidence(batch["id"])), 30)
        self.assertEqual(len(store.attempts(batch["id"])), attempts)

    def test_index_columns_are_migrated_and_backfilled(self):
        path = Path(self.tmp.name) / "old.sqlite3"
        ledger_cls = type(self.plugin._records())
        ledger = ledger_cls(path)
        ledger.add({"title": "a", "acquisition_status": "queued", "next_check_at": 5, "type": "tv"})
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM metadata WHERE key='index_columns_v1'")
            db.execute("UPDATE batches SET acquisition_status='',next_check_at=0,media_type=''")
        reopened = ledger_cls(path)
        with closing(sqlite3.connect(path)) as db:
            row = db.execute("SELECT acquisition_status,next_check_at,media_type FROM batches").fetchone()
        self.assertEqual(tuple(row), ("queued", 5.0, "tv"))
        self.assertEqual(reopened.due_acquisitions(4)["count"], 0)
        self.assertEqual(reopened.due_acquisitions(6)["count"], 1)


class OrganizationTests(V011Base):
    def organize(self, batch, entries, total=None):
        self.plugin._records().update(batch["id"], org_next_ts=0)
        self.plugin._mp_api_json = Mock(return_value={"success": True, "data": {"list": entries,
                                                                                "total": len(entries) if total is None else total}})
        self.plugin.check_organization()
        return self.plugin._records().get(batch["id"])

    def info_messages(self, logger):
        return [c.args[0] for c in logger.info.call_args_list]

    def test_success_logs_once_and_resets_page(self):
        batch = self.saved_batch()
        logger = Mock()
        with patch.dict(self.plugin.verify_organization.__func__.__globals__, {"logger": logger}):
            # 第 1 页不全（total=150），但已足够证实全部 20 集 → 立即判成功，不再翻第 2 页
            result = self.organize(batch, self.histories(batch), total=150)
            self.assertEqual(result["organization_status"], "success")
            self.assertEqual(result["org_page"], 1)
            self.plugin.api_records_verify({"id": batch["id"]})       # 手动核对：从第 1 页开始，结论不变不再 info
            self.assertEqual(self.plugin._records().get(batch["id"])["org_page"], 1)
            self.plugin.check_organization()
        messages = self.info_messages(logger)
        self.assertEqual(sum("整理成功" in m for m in messages), 1)
        self.assertEqual(sum("整理核对完成" in m for m in messages), 1)

    def test_partial_without_change_stops_auto_check_but_manual_reopens(self):
        batch = self.saved_batch()
        entries = self.histories(batch, 19)
        for _ in range(self.plugin.ORG_STALE_ATTEMPTS):
            result = self.organize(batch, entries)
        self.assertEqual(result["organization_status"], "partial")
        self.assertTrue(result["org_giveup"])
        self.assertIn("停止自动核对", result["message"])
        query = self.mp_returns(entries)
        self.plugin._records().update(batch["id"], org_next_ts=0)
        self.plugin.check_organization()
        query.assert_not_called()
        self.assertEqual(self.plugin.api_task_action({"id": batch["id"], "action": "verify"})["code"], 0)
        self.plugin.check_organization()
        query.assert_called_once()

    def test_search_key_strips_bracket_tags_and_skips_empty(self):
        key = self.plugin._org_search_key
        self.assertEqual(key("[60帧率版本][高码版]飞驰人生 2019"), "飞驰人生 2019")
        self.assertEqual(key("【合集】洛基（第二季）第二季"), "洛基")
        self.assertEqual(key("[国语配音]"), "")
        batch = self.saved_batch()
        self.plugin._records().update(batch["id"], title="[仅标签]", org_next_ts=0)
        query = self.mp_returns([])
        self.plugin.check_organization()
        query.assert_not_called()
        self.assertEqual(self.plugin._records().get(batch["id"])["org_attempts"], 1)

    def test_verify_without_id_only_reopens_unfinished(self):
        store = self.plugin._records()
        done = store.add({"title": "done", "acquisition_status": "saved", "organization_status": "success",
                          "org_giveup": True, "org_next_ts": 0})
        stuck = store.add({"title": "stuck", "acquisition_status": "saved", "organization_status": "unfound", "org_giveup": True})
        response = self.plugin.api_records_verify({})
        self.assertEqual(response["data"]["queued"], 1)
        self.assertTrue(store.get(done["id"])["org_giveup"])
        self.assertFalse(store.get(stuck["id"])["org_giveup"])

    def test_manual_verify_during_check_is_not_overwritten(self):
        batch = self.saved_batch()
        store = self.plugin._records()
        store.update(batch["id"], org_next_ts=0)
        def respond(*args):
            self.plugin.api_records_verify({"id": batch["id"]})       # 用户在核对途中点了「核对」
            return {"success": True, "data": {"list": [], "total": 0}}
        self.plugin._mp_api_json = Mock(side_effect=respond)
        self.plugin.check_organization()
        current = store.get(batch["id"])
        self.assertTrue(current["org_requested"])
        self.assertLessEqual(current["org_next_ts"], time.time())

    def test_stale_snapshot_cannot_downgrade_saved(self):
        batch = self.saved_batch()
        self.plugin._update_live(batch["id"], self.plugin._generation, status="moving", acquisition_status="moving")
        current = self.plugin._records().get(batch["id"])
        self.assertEqual((current["acquisition_status"], current["status"]), ("saved", "done"))


class ApiContractTests(V011Base):
    def seed(self):
        store = self.plugin._records()
        rows = {
            "movie_ok": store.add({"title": "Alpha Film", "type": "movie", "acquisition_status": "saved", "organization_status": "success"}),
            "tv_ok": store.add({"title": "Beta Show", "type": "tv", "acquisition_status": "saved", "organization_status": "success"}),
            "tv_partial": store.add({"title": "Beta Show 2", "type": "tv", "acquisition_status": "saved", "organization_status": "partial"}),
            "running": store.add({"title": "Gamma Film", "type": "movie", "status": "downloading", "acquisition_status": "downloading"}),
            "hidden": store.add({"title": "Delta", "type": "movie", "acquisition_status": "saved", "organization_status": "success"}),
        }
        store.delete(rows["hidden"]["id"])
        return rows

    def test_status_has_global_stats_and_jobs(self):
        self.seed()
        data = self.plugin.api_status()["data"]
        self.assertEqual(data["stats"]["movie"], {"total": 2, "organized": 1})
        self.assertEqual(data["stats"]["tv"], {"total": 2, "organized": 1})
        self.assertEqual((data["stats"]["total"], data["stats"]["organized"]), (4, 2))
        self.assertEqual(data["stats"]["active"], 2)
        self.assertEqual(data["stats"]["attention"], 1)
        self.assertEqual(set(data["jobs"]), {"index", "subscribe"})
        self.assertEqual(data["jobs"]["subscribe"]["state"], "idle")
        self.assertIn("refreshing", data)

    def test_records_filters_query_media_hidden_and_page_clamp(self):
        rows = self.seed()
        api = self.plugin.api_records
        data = api(q="  beta SHOW ", media="tv")["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["stats"]["total"], 4)                   # 不受筛选影响
        hidden = api(filter="hidden")["data"]
        self.assertEqual([x["id"] for x in hidden["records"]], [rows["hidden"]["id"]])
        self.assertTrue(hidden["records"][0]["hidden"])
        page = api(page=99, page_size=2)["data"]
        self.assertEqual((page["page"], page["total"]), (2, 4))
        self.assertEqual(api(page=99, filter="completed", media="movie")["data"]["page"], 1)
        running = next(x for x in api()["data"]["records"] if x["id"] == rows["running"]["id"])
        self.assertTrue(running["tracking"])
        self.assertEqual(api(filter="bogus")["code"], 1)

    def test_delete_refuses_tracking_and_clear_skips_them(self):
        rows = self.seed()
        refused = self.plugin.api_records_delete({"id": rows["running"]["id"]})
        self.assertEqual((refused["code"], refused["msg"]), (1, "任务仍在后台处理，请先停止自动跟踪再删除"))
        cleared = self.plugin.api_records_delete({})
        self.assertEqual(cleared["data"], {"hidden": 3, "skipped": 1})
        self.assertEqual([x["id"] for x in self.plugin._records().list()], [rows["running"]["id"]])

    def test_records_bulk_actions(self):
        rows = self.seed()
        bulk = self.plugin.api_records_bulk
        ids = [rows["running"]["id"], rows["tv_partial"]["id"]]
        hide = bulk({"ids": ids, "action": "hide"})
        self.assertEqual((hide["code"], hide["data"]), (0, {"done": 1, "skipped": 1}))
        self.assertEqual(bulk({"ids": [rows["tv_partial"]["id"], rows["hidden"]["id"]], "action": "unhide"})["data"],
                         {"done": 2, "skipped": 0})
        self.assertEqual(bulk({"ids": ids + ["missing"], "action": "verify"})["data"], {"done": 1, "skipped": 2})
        self.assertEqual(bulk({"ids": [rows["running"]["id"]], "action": "stop_tracking"})["data"], {"done": 1, "skipped": 0})
        self.assertFalse(self.plugin._records().get(rows["running"]["id"])["tracking_enabled"])
        self.assertEqual(bulk({"ids": ids, "action": "explode"})["code"], 1)
        self.assertEqual(bulk({"ids": [], "action": "hide"})["code"], 1)

    def test_alias_routes_removed_and_bulk_registered(self):
        paths = {route["path"] for route in self.plugin.get_api()}
        self.assertFalse(paths & {"/check_organization", "/cancel_task", "/retry_task"})
        self.assertIn("/records_bulk", paths)
        methods = {route["path"]: route["methods"] for route in self.plugin.get_api()}
        self.assertEqual(methods["/qr_start"], ["GET"])

    def test_search_sort_passthrough_and_index_errors_surface(self):
        calls = []
        class NewIndex:
            def search_page(self, keyword, sort="relevance", **kwargs):
                calls.append(sort)
                return {"records": [], "total": 0}
        class BrokenIndex:
            def search_page(self, keyword, **kwargs):
                raise TypeError("internal bug")
        self.plugin._index = NewIndex()
        self.assertEqual(self.plugin.api_search({"keyword": "x", "sort": "year_desc"})["code"], 0)
        self.assertEqual(calls, ["year_desc"])
        self.assertEqual(self.plugin.api_search({"keyword": "x", "sort": "random"})["code"], 1)
        # 索引内部的 TypeError 不再被静默降级重搜，而是作为错误返回
        self.plugin._index = BrokenIndex()
        self.assertEqual(self.plugin.api_search({"keyword": "x"})["code"], 1)

    def test_subscriptions_preview_reports_cache_state_and_fields(self):
        empty = self.plugin.api_subscriptions_preview()["data"]
        self.assertTrue(empty["cache_empty"])
        self.assertEqual(empty["cached_at"], 0)
        self.plugin._index = main.DocIndex(self.plugin._new_client())
        self.plugin._index._set_records([rec("Synthetic Film", qtext="2160P 中字")])
        self.plugin._subscriptions_cache = (123.0, [{"id": 1, "type": "电影", "state": "N", "name": "Synthetic Film",
                                                       "year": "2025", "tmdbid": "550"}])
        data = self.plugin.api_subscriptions_preview()["data"]
        self.assertFalse(data["cache_empty"])
        self.assertEqual(data["cached_at"], 123.0)
        row = data["records"][0]
        self.assertEqual((row["year"], row["qtext"]), ("2025", "2160P 中字"))
        self.assertIn("next_check_at", row)


class WorkerAndConfigTests(V011Base):
    MAGNET = "magnet:?xt=urn:btih:" + "b" * 40

    def test_offline_worker_errors_are_logged_rate_limited_and_in_diagnostics(self):
        self.queue()
        logger = Mock()
        self.plugin._transfers = Mock(side_effect=RuntimeError("synthetic 115 outage"))
        with patch.dict(self.plugin.check_offline_tasks.__func__.__globals__, {"logger": logger}):
            for _ in range(3):
                self.tick()
        self.assertEqual(logger.warning.call_count, 1)
        self.assertIn("Traceback", logger.warning.call_args.args[0])
        tick = self.plugin.api_diagnostics()["data"]["offline"]["last_tick"]
        self.assertEqual(tick["state"], "error")
        self.assertIn("synthetic 115 outage", tick["error"])

    def test_subscribe_cron_only_queues_a_retrying_job(self):
        self.plugin.init_plugin({"enabled": True, "subscribe_enabled": True, "p115_cookie": "SYNTHETIC",
                                 "tencent_cookie": "SYNTHETIC"})
        jobs = {kw["id"]: cb for cb, kw in self.plugin._scheduler.jobs}
        self.plugin.run_subscribe = Mock(return_value={"code": 1, "msg": "MP读取已排队"})
        jobs["doc115-subscribe"]()
        self.plugin.run_subscribe.assert_not_called()
        self.assertEqual(self.plugin.api_status()["data"]["jobs"]["subscribe"]["state"], "queued")
        self.plugin.check_offline_tasks()
        self.plugin.run_subscribe.assert_called_once()
        status = self.plugin.api_status()["data"]["jobs"]["subscribe"]
        self.assertEqual((status["state"], status["msg"]), ("failed", "MP读取已排队"))
        self.assertGreater(self.plugin._job_store().get("subscribe")["next_check_at"], time.time())

    def test_staging_path_cannot_overlap_download_paths(self):
        base = {**main.Doc115Subscribe.DEFAULTS}
        for staging in ("/115-影视/115-downloads/电影", "/115-影视/115-downloads/电影/磁力", "/115-影视/115-downloads"):
            with self.assertRaisesRegex(ValueError, "磁力暂存目录不能与"):
                main.Doc115Subscribe._validate_config({**base, "magnet_staging_path": staging})
        response = self.plugin.api_save_config({"magnet_staging_path": "/115-影视/115-downloads/电视剧/"})
        self.assertEqual(response["code"], 1)
        self.assertIn("磁力暂存目录", response["msg"])
        main.Doc115Subscribe._validate_config({**base, "magnet_staging_path": "/115-影视/115-downloads/电影磁力"})

    def test_legacy_overlapping_config_disables_plugin_instead_of_failing_load(self):
        self.plugin.init_plugin({"enabled": True, "p115_cookie": "SYNTHETIC", "tencent_cookie": "SYNTHETIC",
                                 "magnet_staging_path": "/115-影视/115-downloads/电影/磁力"})
        self.assertFalse(self.plugin._enabled)

    def test_all_mode_failure_leaves_no_partial_queued_reservation(self):
        store = self.plugin._records()
        self.plugin._link_mode = "all"
        ok, _ = self.plugin.do_transfer(rec("Synthetic Film", links=[("magnet", self.MAGNET)]), "movie")
        self.assertTrue(ok)
        failed = store.list()[0]
        store.update(failed["id"], acquisition_status="failed", status="failed")
        ok, msg = self.plugin.do_transfer(rec("Synthetic Film", links=[("115_share", "https://115.com/s/OTHER"),
                                                                       ("magnet", self.MAGNET)]), "movie")
        self.assertFalse(ok)
        self.assertIn("上次获取失败", msg)
        self.assertEqual([x["id"] for x in store.list(limit=None, include_hidden=True)], [failed["id"]])

    def test_event_paths_rebuild_only_after_ledger_changes(self):
        batch = self.saved_batch()
        store = self.plugin._records()
        self.plugin._refresh_event_paths()
        with patch.object(type(store), "tracked", wraps=store.tracked) as tracked:
            self.plugin._refresh_event_paths()
            self.plugin._refresh_event_paths()
            tracked.assert_not_called()
            store.update(batch["id"], item_names=["Season", "Extra"])
            self.plugin._refresh_event_paths()
            tracked.assert_called_once()
        self.assertTrue(self.plugin._event_batches(batch["final_path"] + "/Extra/x.mkv"))

    def test_offline_tick_reads_only_due_rows(self):
        self.queue()
        store = self.plugin._records()
        for task in store.list(limit=None, include_hidden=True):
            store.update(task["id"], next_check_at=0)
        with patch.object(type(store), "list", side_effect=AssertionError("full table read")):
            self.plugin.check_offline_tasks()
        self.assertEqual(self.cloud.writes[0][0], "receive")


class ShareReconcileTests(V011Base):
    def uncertain(self):
        self.cloud.uncertain_submit = True
        batch = self.queue()
        self.tick()
        batch = self.plugin._records().get(batch["id"])
        self.assertEqual(batch["acquisition_status"], "uncertain")
        view = self.plugin._record_view(batch)
        self.assertIn("reconcile", view["allowed_actions"])
        self.assertIn("confirm_saved", view["allowed_actions"])
        return batch

    def test_confirm_saved_is_not_offered_for_magnet_tasks(self):
        batch = self.plugin._records().get(self.uncertain()["id"])
        view = self.plugin._record_view(dict(batch, kind="magnet"))
        self.assertIn("reconcile", view["allowed_actions"])
        self.assertNotIn("confirm_saved", view["allowed_actions"])

    def test_reconcile_finds_items_read_only_and_marks_saved(self):
        batch = self.uncertain()
        self.cloud.list_names = Mock(return_value=["Season", "Unrelated"])
        self.assertEqual(self.plugin.api_task_action({"id": batch["id"], "action": "reconcile"})["code"], 0)
        self.tick()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["acquisition_status"], "saved")
        self.cloud.list_names.assert_called_once_with(batch["final_path"])
        self.assertEqual(len(self.cloud.writes), 1)                  # 只读：没有再次提交

    def test_reconcile_missing_items_stays_uncertain_without_resubmit(self):
        batch = self.uncertain()
        self.cloud.list_names = Mock(return_value=[])
        self.plugin.api_task_action({"id": batch["id"], "action": "reconcile"})
        self.tick()
        result = self.plugin._records().get(batch["id"])
        self.assertEqual(result["acquisition_status"], "uncertain")
        self.assertIn("缺少", result["message"])
        self.assertFalse(result.get("reconcile_requested"))
        self.assertEqual(len(self.cloud.writes), 1)

    def test_reconcile_without_listing_capability_falls_back_to_organization(self):
        batch = self.uncertain()
        self.plugin.api_task_action({"id": batch["id"], "action": "reconcile"})
        self.tick()
        result = self.plugin._records().get(batch["id"])
        self.assertTrue(result["org_requested"])
        self.assertEqual(len(self.cloud.writes), 1)

    def test_confirm_saved_enters_organization_check(self):
        batch = self.uncertain()
        response = self.plugin.api_task_action({"id": batch["id"], "action": "confirm_saved"})
        self.assertEqual(response["code"], 0)
        result = self.plugin._records().get(batch["id"])
        self.assertEqual((result["acquisition_status"], result["status"]), ("saved", "done"))
        query = self.mp_returns(self.histories(result))
        self.plugin.check_organization()
        query.assert_called()
        self.assertEqual(self.plugin._records().get(batch["id"])["organization_status"], "success")
        self.assertEqual(len(self.cloud.writes), 1)


if __name__ == "__main__":
    unittest.main()
