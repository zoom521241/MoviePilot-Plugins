"""Real plugin orchestration methods with synthetic files/services and blocked networking."""
import copy
import enum
import hashlib
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_PATH = Path(__file__).resolve().parents[1] / "plugins.v3" / "doc115subscribe"


class FakeScheduler:
    instances = []
    fail_next_start = False

    def __init__(self, **kwargs):
        self.running = False
        self.jobs = []
        self.shutdowns = 0
        self.__class__.instances.append(self)

    def add_job(self, callback, **kwargs):
        self.jobs.append((callback, kwargs))

    def start(self):
        if self.__class__.fail_next_start:
            self.__class__.fail_next_start = False
            raise RuntimeError("synthetic scheduler startup failure")
        self.running = True

    def remove_all_jobs(self):
        self.jobs.clear()

    def shutdown(self, **kwargs):
        self.running = False
        self.shutdowns += 1


class FakeCron:
    @classmethod
    def from_crontab(cls, expression, **kwargs):
        if len(expression.split()) != 5:
            raise ValueError("Wrong number of fields; expected 5")
        return (expression, kwargs)


class FakeInterval:
    def __init__(self, **kwargs):
        self.values = kwargs


class MediaType(enum.Enum):
    MOVIE = "电影"
    TV = "电视剧"


class MediaSource(enum.Enum):
    TMDB = "themoviedb"


class FakeMediaChain:
    calls = []

    def recognize_media(self, media_source, media_id, mtype):
        self.__class__.calls.append((media_source, media_id, mtype))
        return types.SimpleNamespace(type=mtype)


def module(name, **members):
    result = types.ModuleType(name)
    result.__dict__.update(members)
    result.__path__ = []
    return result


STUBS = {name: module(name) for name in
         ("apscheduler", "apscheduler.schedulers", "apscheduler.triggers", "app", "app.schemas", "app.chain", "app.core", "app.db")}
STUBS.update({
    "apscheduler.schedulers.background": module("apscheduler.schedulers.background", BackgroundScheduler=FakeScheduler),
    "apscheduler.triggers.cron": module("apscheduler.triggers.cron", CronTrigger=FakeCron),
    "apscheduler.triggers.interval": module("apscheduler.triggers.interval", IntervalTrigger=FakeInterval),
    "app.log": module("app.log", logger=Mock()),
    "app.plugins": module("app.plugins", _PluginBase=object),
    "app.schemas.types": module("app.schemas.types", MediaType=MediaType, MediaSource=MediaSource),
    "app.chain.media": module("app.chain.media", MediaChain=FakeMediaChain),
    "app.core.config": module("app.core.config", settings=types.SimpleNamespace(API_TOKEN="synthetic-only", PORT=5000)),
    "app.db.systemconfig_oper": module("app.db.systemconfig_oper", SystemConfigOper=lambda: types.SimpleNamespace(get=lambda _: {})),
})


def load_plugin():
    name = "_doc115_backend_testpkg"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_PATH / "__init__.py",
                                                 submodule_search_locations=[str(PLUGIN_PATH)])
    main = importlib.util.module_from_spec(spec)
    sys.modules[name] = main
    with patch.dict(sys.modules, STUBS), \
            patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED IN TESTS")), \
            patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED IN TESTS")):
        spec.loader.exec_module(main)
    return main


main = load_plugin()


class Plugin(main.Doc115Subscribe):
    def get_data_path(self):
        return self.synthetic_root

    def update_config(self, config):
        self.saved_configs.append(copy.deepcopy(config))


def rec(title="Synthetic Film", **values):
    result = {"sheet_id": "s", "sheet": "最新电影", "kind": "movie", "row": 1,
              "title": title, "year": "2025", "tmdbid": "550", "media_type": "movie",
              "qtext": "1080P 中字", "spec": "", "links": [("115_share", "https://115.com/s/SYNTHETIC")],
              "bundle": False, "sheet_bundle": False, "no_link": False}
    result.update(values)
    return result


class SyntheticTransfer:
    """Only the external 115 boundary is replaced; no account or network access."""
    last_offline_result = None
    last_share_names = ["Synthetic File.mkv"]

    def __init__(self, outcomes=None):
        self.calls = []
        self.outcomes = list(outcomes or [])

    def add_resource(self, kind, url, path):
        self.calls.append((kind, url, path))
        return self.outcomes.pop(0) if self.outcomes else (True, "synthetic accepted")


class SyntheticQr:
    def __init__(self, session="synthetic-session", state=None):
        self.session_id = session
        self.state = state or {"state": "waiting"}
        self.start = Mock(return_value=(b"synthetic-png-bytes", False, 0.01))
        self.check = Mock(side_effect=lambda: dict(self.state))
        self.close = Mock()


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.module_patch = patch.dict(sys.modules, STUBS)
        self.module_patch.start()
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED IN TESTS"))
        self.blocked_urlopen = self.network.start()
        self.socket_patch = patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED IN TESTS"))
        self.socket_patch.start()
        self.folder = tempfile.TemporaryDirectory()
        self.plugin = Plugin()
        self.plugin.synthetic_root = Path(self.folder.name)
        self.plugin.saved_configs = []
        FakeScheduler.instances = []
        FakeScheduler.fail_next_start = False
        FakeMediaChain.calls = []
        self.plugin.init_plugin({**main.Doc115Subscribe.DEFAULTS, "enabled": True,
                                 "doc_url": "https://docs.qq.com/sheet/SyntheticDocument",
                                 "tencent_cookie": "synthetic-tencent-cookie", "p115_cookie": "synthetic-115-cookie"})

    def tearDown(self):
        self.plugin.stop_service()
        self.folder.cleanup()
        self.socket_patch.stop()
        self.network.stop()
        self.module_patch.stop()

    def install_index(self, records):
        index = main.DocIndex(main.TencentDocsClient("SyntheticDocument"))
        index._set_records(records)
        index.built_at = time.time()
        self.plugin._index = index
        return index

    def subscribe(self, **fields):
        raw = {"type": "电影", "state": "N", "name": "Synthetic Film", "year": "2025", "tmdbid": "550"}
        raw.update(fields)
        self.plugin._mp_subscribes = Mock(return_value=[raw])

    def test_filtered_search_transfer_uses_record_identity(self):
        index = self.install_index([rec("Synthetic Film"), rec("Synthetic TV", media_type="tv", sheet="电视剧")])
        result = self.plugin.api_search({"keyword": "Synthetic", "media_type": "tv", "page_size": 10})
        self.assertEqual(result["data"]["total"], 1)
        selected = result["data"]["records"][0]
        with patch.object(self.plugin, "do_transfer", return_value=(True, "synthetic accepted")) as transfer:
            response = self.plugin.api_transfer({"record_id": selected["record_id"], "index_version": index.index_version,
                                                 "to": "tv", "keyword": "different input", "index": 0})
        self.assertEqual(response["code"], 0)
        self.assertEqual(transfer.call_args.args[0]["title"], "Synthetic TV")
        self.blocked_urlopen.assert_not_called()

    def test_refreshed_index_rejects_stale_version_even_when_record_stays(self):
        old = self.install_index([rec()])
        selected = old.search_page("Synthetic")["records"][0]
        self.install_index([rec()])
        with patch.object(self.plugin, "do_transfer") as transfer:
            response = self.plugin.api_transfer({**selected, "to": "movie"})
        self.assertEqual(response["code"], 1)
        transfer.assert_not_called()

    def test_unknown_or_missing_identity_is_rejected(self):
        index = self.install_index([rec()])
        with patch.object(self.plugin, "do_transfer") as transfer:
            for body in ({"index_version": index.index_version, "record_id": "missing", "to": "movie"},
                         {"index_version": index.index_version, "record_id": index.records[0]["record_id"], "to": "unknown"},
                         {"keyword": "Synthetic", "index": 0, "to": "movie"}):
                self.assertEqual(self.plugin.api_transfer(body)["code"], 1)
        transfer.assert_not_called()

    def test_repeated_init_stops_every_previous_scheduler(self):
        first = self.plugin._scheduler
        self.plugin.init_plugin(self.plugin._current_config())
        second = self.plugin._scheduler
        self.assertFalse(first.running)
        self.assertEqual(first.shutdowns, 1)
        self.plugin.init_plugin({**self.plugin._current_config(), "enabled": False})
        self.assertFalse(second.running)
        self.assertEqual(second.shutdowns, 1)
        self.assertFalse(any(s.running for s in FakeScheduler.instances))
        self.assertIsNone(self.plugin._scheduler)

    def test_secret_fields_are_hidden_and_blank_updates_preserve_them(self):
        public = self.plugin.api_get_config()["data"]
        self.assertEqual((public["tencent_cookie"], public["p115_cookie"]), ("", ""))
        response = self.plugin.api_save_config({"tencent_cookie": "", "p115_cookie": "", "movie_path": "/synthetic/new"})
        self.assertEqual(response["code"], 0)
        self.assertEqual(self.plugin._tencent_cookie, "synthetic-tencent-cookie")
        self.assertEqual(self.plugin._p115_cookie, "synthetic-115-cookie")
        self.assertEqual(response["data"]["p115_cookie"], "")

    def test_explicit_clear_removes_secret(self):
        response = self.plugin.api_save_config({"clear_tencent_cookie": True})
        self.assertEqual(response["code"], 0)
        self.assertEqual(self.plugin._tencent_cookie, "")
        self.assertFalse(response["data"]["tencent_cookie_ready"])

    def test_invalid_config_leaves_running_config_and_scheduler_intact(self):
        scheduler, before = self.plugin._scheduler, self.plugin._current_config()
        for invalid in ({"index_cron": "invalid cron"}, {"doc_url": "https://docs.qq.com.evil.invalid/sheet/Synthetic"},
                        {"movie_path": "/"}, {"enabled": "true"}, {"link_mode": "anything"}):
            response = self.plugin.api_save_config(invalid)
            self.assertEqual(response["code"], 1)
            self.assertEqual(self.plugin._current_config(), before)
            self.assertIs(self.plugin._scheduler, scheduler)
            self.assertTrue(scheduler.running)
        self.assertEqual(self.plugin.saved_configs, [])

    def test_non_boolean_secret_clear_flags_are_rejected_without_clearing(self):
        for value in ("false", "true", 1, None):
            response = self.plugin.api_save_config({"clear_tencent_cookie": value})
            self.assertEqual(response["code"], 1)
            self.assertEqual(self.plugin._tencent_cookie, "synthetic-tencent-cookie")

    def test_unexpected_and_malformed_document_ports_are_rejected(self):
        before = self.plugin._current_config()
        for port in ("8443", "invalid"):
            response = self.plugin.api_save_config({"doc_url": f"https://docs.qq.com:{port}/sheet/SyntheticDocument"})
            self.assertEqual(response["code"], 1)
            self.assertEqual(self.plugin._current_config(), before)

    def test_scheduler_start_failure_rolls_back_runtime_and_persistence(self):
        before = self.plugin._current_config()
        FakeScheduler.fail_next_start = True
        response = self.plugin.api_save_config({"movie_path": "/synthetic/new"})
        self.assertEqual(response["code"], 1)
        self.assertEqual(self.plugin._current_config(), before)
        self.assertTrue(self.plugin._scheduler.running)
        self.assertEqual(self.plugin.saved_configs[-1], before)
        self.assertEqual(sum(s.running for s in FakeScheduler.instances), 1)

    def test_cache_from_different_document_is_not_loaded(self):
        index = main.DocIndex(main.TencentDocsClient("OtherDocument"))
        index._set_records([rec()])
        index.built_at = time.time()
        index.save(self.plugin.index_path)
        self.plugin._load_index()
        self.assertIsNone(self.plugin._index)

    def test_refresh_mutex_prevents_overlapping_fetch(self):
        self.plugin._refresh_lock.acquire()
        try:
            with patch.object(self.plugin, "_new_client") as client:
                response = self.plugin.refresh_index()
            self.assertEqual(response["code"], 1)
            client.assert_not_called()
        finally:
            self.plugin._refresh_lock.release()

    def test_source_change_during_refresh_discards_old_result(self):
        plugin = self.plugin
        class FakeIndex:
            saved = False
            def __init__(self, client):
                self.client = client
            @classmethod
            def load(cls, *args, **kwargs):
                return None
            def build(self, **kwargs):
                plugin.init_plugin({**plugin._current_config(), "doc_url": "https://docs.qq.com/sheet/OtherDocument"})
                return {"errors": []}
            def save(self, path):
                self.__class__.saved = True
        with patch.object(main, "DocIndex", FakeIndex):
            response = plugin.refresh_index()
        self.assertEqual(response["code"], 1)
        self.assertFalse(FakeIndex.saved)
        self.assertIsNone(plugin._index)
        self.assertEqual(plugin._new_client().doc_id, "OtherDocument")

    def test_refresh_partial_failure_retains_previous_sheet(self):
        previous = self.install_index([rec("Synthetic Old", sheet_id="failed")])
        previous.sheets = [{"id": "failed", "name": "电影", "count": 1, "last_success_at": previous.built_at}]
        class SyntheticClient:
            doc_id = "SyntheticDocument"
            def fetch_sheet_list(self):
                return [{"id": "failed", "name": "电影"}, {"id": "good", "name": "最新电影"}]
            def fetch_sheet(self, sid):
                if sid == "failed":
                    raise main.DocError("synthetic table failure")
                return {"grid": [["片名", "链接"], ["Synthetic New", "https://115.com/s/SYNTHETICNEW"]], "hrefs": []}
        with patch.object(self.plugin, "_new_client", return_value=SyntheticClient()):
            response = self.plugin.refresh_index()
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["stale_sheet_count"], 1)
        self.assertEqual({r["title"] for r in self.plugin._index.records}, {"Synthetic Old", "Synthetic New"})
        self.assertFalse(self.plugin._last_refresh["success"])
        self.assertEqual(len(self.plugin.api_status()["data"]["stale_sheets"]), 1)

    def test_v3_media_recognition_uses_current_contract_and_separate_cache(self):
        self.assertEqual(self.plugin.resolve_media_type(rec()), "movie")
        self.assertEqual(self.plugin.resolve_media_type(rec(media_type="tv")), "tv")
        self.assertEqual([(call[1], call[2]) for call in FakeMediaChain.calls], [("550", MediaType.MOVIE), ("550", MediaType.TV)])

    def test_unknown_type_does_not_guess_tv_from_same_numeric_id(self):
        result = self.plugin.resolve_media_type(rec(media_type="unknown", sheet="4K原盘"))
        self.assertEqual(result, "unknown")
        self.assertEqual(FakeMediaChain.calls, [])

    def test_subscriptions_exclude_conflicting_id_year_and_tv(self):
        good = rec(row=4)
        self.install_index([rec(tmdbid="999", qtext="4K 中字"), rec(year="2019", qtext="4K 中字"),
                            rec(media_type="tv", qtext="4K 中字"), good])
        self.subscribe()
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(len(transfer.calls), 1)
        self.assertEqual(self.plugin._records().list()[0]["status"], "done")

    def test_subscriptions_try_next_candidate_after_failure(self):
        self.install_index([rec(qtext="4K 中字", row=1), rec(row=2, links=[("115_share", "https://115.com/s/SYNTHETIC2")])])
        self.subscribe()
        transfer = SyntheticTransfer([(False, "synthetic expired mirror"), (True, "synthetic accepted")])
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(len(transfer.calls), 2)
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_subscriptions_respect_include_exclude_and_resolution_rules(self):
        self.install_index([rec(qtext="4K 中字", row=1), rec(qtext="1080P 中字", row=2, links=[("115_share", "https://115.com/s/SYNTHETIC1080")])])
        self.subscribe(resolution="1080P", include="中字", exclude="4K")
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(transfer.calls[0][1], "https://115.com/s/SYNTHETIC1080")

    def test_invalid_rule_in_one_subscription_does_not_abort_other_subscriptions(self):
        self.install_index([rec("Synthetic Bad", tmdbid="551"), rec()])
        self.plugin._mp_subscribes = Mock(return_value=[
            {"type": "电影", "name": "Synthetic Bad", "year": "2025", "tmdbid": "551", "include": "("},
            {"type": "电影", "name": "Synthetic Film", "year": "2025", "tmdbid": "550"}])
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["failed"], 1)
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(len(transfer.calls), 1)

    def test_failed_upgrade_never_downloads_lower_quality_or_erases_completed_baseline(self):
        self.install_index([rec(qtext="4K 中字", links=[("115_share", "https://115.com/s/SYNTHETIC4K")]),
                            rec(qtext="1080P 中字", row=2, links=[("115_share", "https://115.com/s/SYNTHETIC1080")])])
        self.subscribe()
        self.plugin._upgrade_enabled = True
        self.plugin._set_subscription("tmdb:550", status="complete", quality_score=1)
        transfer = SyntheticTransfer([(False, "synthetic upgrade failed"), (True, "synthetic lower quality")])
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(len(transfer.calls), 1)
        self.assertEqual(response["data"]["failed"], 1)
        state = self.plugin._subscription_store().list()[0]
        self.assertEqual((state["status"], state["quality_score"]), ("complete", 1))

    def test_all_candidates_blocked_by_rules_report_failure_without_transfer(self):
        self.install_index([rec(qtext="1080P 中字")])
        self.subscribe(resolution="2160P")
        with patch.object(self.plugin, "_transfers") as transfer:
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["failed"], 1)
        transfer.assert_not_called()
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "failed")

    def test_transfer_preflight_failure_keeps_original_error_and_allows_fallback(self):
        self.install_index([rec(qtext="4K 中字"), rec(qtext="1080P 中字", row=2)])
        self.subscribe()
        with patch.object(self.plugin, "_transfers", side_effect=main.P115Error("synthetic invalid Cookie")) as transfer:
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["failed"], 1)
        self.assertEqual(transfer.call_count, 2)
        self.assertIn("synthetic invalid Cookie", response["data"]["errors"][0])

    def test_unsupported_external_rules_block_automatic_download(self):
        self.install_index([rec()])
        self.subscribe(filter_groups=["synthetic-filter"])
        with patch.object(self.plugin, "do_transfer") as transfer:
            response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["failed"], 1)
        transfer.assert_not_called()

    def test_completed_subscription_dedupes_next_run(self):
        self.install_index([rec()])
        self.subscribe()
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            first = self.plugin.run_subscribe()
            second = self.plugin.run_subscribe()
        self.assertEqual(first["data"]["transferred"], 1)
        self.assertEqual(second["data"]["skipped"], 1)
        self.assertEqual(len(transfer.calls), 1)

    def test_pending_subscription_is_not_completed_and_failed_task_can_retry(self):
        self.install_index([rec(links=[("magnet", "magnet:?xt=urn:btih:" + "a" * 40)])])
        self.subscribe()
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            self.plugin.run_subscribe()
            self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "pending")
            self.assertEqual(self.plugin.run_subscribe()["data"]["skipped"], 1)
            self.plugin._pending().update("a" * 40, status="failed")
            self.plugin._records().update(self.plugin._records().list()[0]["id"], status="failed")
            self.assertEqual(self.plugin.run_subscribe()["data"]["transferred"], 1)
        self.assertEqual(len(transfer.calls), 2)

    def test_failed_previous_mirror_does_not_keep_successful_share_pending(self):
        self.install_index([rec()])
        self.subscribe()
        self.plugin._pending().upsert({"hash": "a" * 40, "subscription_key": "tmdb:550", "status": "failed"})
        with patch.object(self.plugin, "_transfers", return_value=SyntheticTransfer()):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_orphan_active_history_does_not_become_completed_or_resubmit(self):
        url = "magnet:?xt=urn:btih:" + "a" * 40
        candidate = rec(links=[("magnet", url)])
        self.install_index([candidate])
        self.subscribe()
        final = self.plugin.build_save_path(candidate, "movie")
        resource_key = hashlib.sha256(f"magnet|{url}|{final}".encode()).hexdigest()
        self.plugin._records().add({"title": "Synthetic Film", "year": "2025", "type": "movie",
                                   "resource_key": resource_key, "kind": "magnet", "url": url,
                                   "hash": "a" * 40, "staging_path": self.plugin._magnet_staging_path,
                                   "final_path": final, "subscription_key": "tmdb:550", "status": "downloading"})
        self.assertEqual(self.plugin._pending().list(), [])
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(transfer.calls, [])
        state = self.plugin._subscription_store().list()[0]
        self.assertNotEqual(state["status"], "complete")

    def test_existing_completed_history_can_complete_subscription_without_resubmit(self):
        candidate = rec()
        self.install_index([candidate])
        self.subscribe()
        final = self.plugin.build_save_path(candidate, "movie")
        url = candidate["links"][0][1]
        resource_key = hashlib.sha256(f"115_share|{url}|{final}".encode()).hexdigest()
        self.plugin._records().add({"title": "Synthetic Film", "resource_key": resource_key,
                                   "status": "done", "final_path": final})
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 0)
        self.assertEqual(transfer.calls, [])
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_subscription_fetch_failure_is_reported_and_not_successful_zero(self):
        self.install_index([rec()])
        with patch.object(self.plugin, "_mp_subscribes", side_effect=RuntimeError("synthetic auth failure")):
            response = self.plugin.run_subscribe()
        self.assertEqual(response["code"], 1)
        self.assertFalse(self.plugin._last_subscribe["success"])

    def test_subscription_pagination_reads_past_five_pages(self):
        pages = [[{"id": page * 100 + i, "name": f"Synthetic {page}-{i}"} for i in range(100)] for page in range(6)]
        pages.append([{"id": 600, "name": "Synthetic final"}])
        class Response:
            def __init__(self, batch):
                self.body = json.dumps({"data": batch}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self):
                return self.body
        self.blocked_urlopen.side_effect = [Response(batch) for batch in pages]
        records = self.plugin._mp_subscribes()
        self.assertEqual(len(records), 601)
        self.assertEqual(self.blocked_urlopen.call_count, 7)
        self.assertIn("page=7", self.blocked_urlopen.call_args.args[0].full_url)

    def test_history_delete_does_not_cancel_pending_tracking(self):
        history = self.plugin._records().add({"title": "Synthetic", "hash": "a" * 40, "status": "downloading"})
        self.plugin._pending().upsert({"hash": "a" * 40, "record_id": history["id"], "status": "downloading"})
        self.assertEqual(self.plugin.api_records_delete({"id": history["id"]})["code"], 0)
        self.assertIsNotNone(self.plugin._pending().get("a" * 40))

    def test_forced_qr_failure_clears_closed_cached_session(self):
        old, broken, replacement = SyntheticQr("old"), SyntheticQr("broken"), SyntheticQr("replacement")
        broken.start.side_effect = RuntimeError("synthetic browser failure")
        self.plugin._qr, self.plugin._qr_img, self.plugin._qr_ts = old, b"old-image", time.time()
        with patch.object(main, "BrowserQrLogin", side_effect=[broken, replacement]):
            failed = self.plugin.api_qr_start(force=True)
            self.assertEqual(failed["code"], 1)
            self.assertIsNone(self.plugin._qr)
            self.assertEqual(self.plugin._qr_img, b"")
            success = self.plugin.api_qr_start()
        old.close.assert_called_once()
        broken.close.assert_called_once()
        replacement.start.assert_called_once()
        self.assertEqual(success["data"]["session_id"], "replacement")
        self.assertFalse(success["data"].get("cached", False))

    def test_qr_stale_session_never_checks_current_login(self):
        current = SyntheticQr("current")
        self.plugin._qr = current
        response = self.plugin.api_qr_check(session_id="stale")
        self.assertEqual(response["code"], 1)
        self.assertEqual(response["data"]["state"], "expired")
        current.check.assert_not_called()

    def test_confirmed_qr_and_stop_serialize_without_losing_cookie_or_deadlock(self):
        entered, release, stop_attempted = threading.Event(), threading.Event(), threading.Event()
        current = SyntheticQr("current", {"state": "confirmed", "cookie": "synthetic-new-cookie"})
        responses, errors = [], []
        def check_state():
            entered.set()
            if not release.wait(2):
                raise AssertionError("synthetic test release timeout")
            return dict(current.state)
        current.check.side_effect = check_state
        self.plugin._qr = current
        def do_check():
            try:
                responses.append(self.plugin.api_qr_check("current"))
            except Exception as exc:
                errors.append(exc)
        def do_stop():
            stop_attempted.set()
            try:
                self.plugin.stop_service()
            except Exception as exc:
                errors.append(exc)
        checker = threading.Thread(target=do_check, daemon=True)
        stopper = threading.Thread(target=do_stop, daemon=True)
        # Replace only the refresh thread created after QR confirmation; worker threads already exist.
        with patch.object(main.threading, "Thread") as refresh_thread:
            checker.start()
            self.assertTrue(entered.wait(1))
            stopper.start()
            self.assertTrue(stop_attempted.wait(1))
            current.close.assert_not_called()
            release.set()
            checker.join(2)
            stopper.join(2)
            self.assertFalse(checker.is_alive())
            self.assertFalse(stopper.is_alive())
            refresh_thread.return_value.start.assert_called_once()
        self.assertEqual(errors, [])
        self.assertEqual(responses[0]["code"], 0)
        self.assertNotIn("cookie", responses[0]["data"])
        self.assertEqual(self.plugin._tencent_cookie, "synthetic-new-cookie")
        self.assertEqual(self.plugin.saved_configs[-1]["tencent_cookie"], "synthetic-new-cookie")
        current.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
