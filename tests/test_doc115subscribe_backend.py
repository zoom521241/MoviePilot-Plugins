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
    "app.api": module("app.api"),
    "app.api.dependencies": module("app.api.dependencies"),
    "app.api.dependencies.auth": module("app.api.dependencies.auth", get_current_active_superuser=lambda: types.SimpleNamespace(is_superuser=True)),
    # Unit simulations must not initialize an installed cloud SDK or its native
    # dependencies while the rest of the MoviePilot namespace is stubbed.
    "p115client": module("p115client"),
    "p115client.util": module("p115client.util"),
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

    def _submit(self, kind, url, path):
        ok, message = self.add_resource(kind, url, path)
        if not ok:
            error = main.P115Error(message)
            error.definite_failure = True
            error.not_sent = True  # synthetic rejection proves no cloud mutation
            raise error

    def prepare_share(self, url, path, state=None):
        return copy.deepcopy(state or {"items": [{"id": "source-1", "name": "Synthetic File.mkv"}],
                                       "cid": "42", "complete": True, "received": 0, "done": False})

    def share_manifest_slice(self, url, cursor=None):
        return {"items": [{"relative_path": "Synthetic File.mkv", "name": "Synthetic File.mkv",
                           "required": True, "role": "movie"}], "cursor": None, "complete": True}

    def receive_prepared(self, url, path, state, before_submit=None):
        if before_submit:
            before_submit({"kind": "share_receive", "source_ids": ["source-1"], "cid": "42"})
        self._submit("115_share", url, path)
        state = copy.deepcopy(state)
        state.update(received=len(state["items"]), done=True)
        return state

    def offline_add(self, url, path, before_submit=None):
        if before_submit:
            before_submit({"kind": "offline_add", "url": url})
        self._submit("magnet", url, path)
        self.last_offline_result = types.SimpleNamespace(accepted=True, file_id="", actual_cid="42", requested_cid="42", uncertain=False)
        return self.last_offline_result

    def list_tasks_slice(self, cursor=None):
        return {"items": [], "cursor": None, "complete": True}

    @staticmethod
    def get_file_info(file_id):
        return None


def drive_worker(plugin, ticks=1, advance=3600):
    """Advance a synthetic clock; exercise the real persistent worker stages."""
    results = []
    now = time.time()
    for tick in range(ticks):
        with patch("time.time", return_value=now + advance * (tick + 1)):
            results.append(plugin.check_offline_tasks())
    return results


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
                                 "subscribe_enabled": True,
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
            self.plugin._last_transfer_result = {}
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
            self.assertEqual(transfer.calls, [])
            drive_worker(self.plugin)
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(len(transfer.calls), 1)
        self.assertEqual(self.plugin._records().list()[0]["status"], "done")

    def test_subscriptions_try_next_candidate_after_failure(self):
        self.install_index([rec(qtext="4K 中字", row=1), rec(row=2, links=[("115_share", "https://115.com/s/SYNTHETIC2")])])
        self.subscribe()
        transfer = SyntheticTransfer([(False, "synthetic expired mirror"), (True, "synthetic accepted")])
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
            drive_worker(self.plugin, ticks=4)
        self.assertEqual(len(transfer.calls), 2)
        self.assertEqual(response["data"]["transferred"], 1)
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")

    def test_subscriptions_respect_include_exclude_and_resolution_rules(self):
        self.install_index([rec(qtext="4K 中字", row=1), rec(qtext="1080P 中字", row=2, links=[("115_share", "https://115.com/s/SYNTHETIC1080")])])
        self.subscribe(resolution="1080P", include="中字", exclude="4K")
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            response = self.plugin.run_subscribe()
            drive_worker(self.plugin)
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
            drive_worker(self.plugin)
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
            drive_worker(self.plugin, ticks=3)
        self.assertEqual(response["code"], 0)
        self.assertEqual(len(transfer.calls), 1)
        self.assertEqual(self.plugin._records().list()[0]["acquisition_status"], "failed")
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

    def test_transfer_preflight_auth_failure_keeps_original_error_and_does_not_try_mirrors(self):
        self.install_index([rec(qtext="4K 中字"), rec(qtext="1080P 中字", row=2)])
        self.subscribe()
        with patch.object(self.plugin, "_transfers", side_effect=main.P115Error("synthetic invalid Cookie")) as transfer:
            response = self.plugin.run_subscribe()
            self.assertEqual(transfer.call_count, 0)
            result = drive_worker(self.plugin)[0]
        self.assertEqual(response["code"], 0)
        self.assertEqual(transfer.call_count, 1)
        self.assertEqual(result["code"], 1)
        self.assertIn("synthetic invalid Cookie", result["msg"])
        self.assertIn("synthetic invalid Cookie", self.plugin._records().list()[0]["last_error"])

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
            drive_worker(self.plugin)
            second = self.plugin.run_subscribe()
        self.assertEqual(first["data"]["transferred"], 1)
        self.assertEqual(second["data"]["skipped"], 1)
        self.assertEqual(len(transfer.calls), 1)

    def test_pending_subscription_is_not_completed_and_failed_task_is_not_blindly_resubmitted(self):
        self.install_index([rec(links=[("magnet", "magnet:?xt=urn:btih:" + "a" * 40)])])
        self.subscribe()
        transfer = SyntheticTransfer()
        with patch.object(self.plugin, "_transfers", return_value=transfer):
            self.plugin.run_subscribe()
            drive_worker(self.plugin)
            self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "pending")
            self.assertEqual(self.plugin.run_subscribe()["data"]["skipped"], 1)
            self.plugin._records().update(self.plugin._records().list()[0]["id"], status="failed", acquisition_status="failed")
            self.plugin.run_subscribe()
        self.assertEqual(len(transfer.calls), 1)

    def test_failed_previous_mirror_does_not_keep_successful_share_pending(self):
        self.install_index([rec()])
        self.subscribe()
        self.plugin._records().add({"hash": "a" * 40, "subscription_key": "tmdb:550", "status": "failed", "acquisition_status": "failed"})
        with patch.object(self.plugin, "_transfers", return_value=SyntheticTransfer()):
            response = self.plugin.run_subscribe()
            drive_worker(self.plugin)
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
        self.assertFalse(any(state["status"] == "complete" for state in self.plugin._subscription_store().list()))

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
        self.plugin._mp().opener = self.blocked_urlopen
        deferred = self.plugin._mp()._permit.__globals__["MPDeferred"]
        with self.plugin._mp().work_slice():
            with self.assertRaises(deferred):
                self.plugin._mp_subscribes()
        self.assertEqual(self.blocked_urlopen.call_count, 5)
        with self.plugin._mp().work_slice():
            records = self.plugin._mp_subscribes()
        self.assertEqual(len(records), 601)
        self.assertEqual(self.blocked_urlopen.call_count, 7)
        self.assertIn("page=7", self.blocked_urlopen.call_args.args[0].full_url)

    def test_history_delete_does_not_cancel_pending_tracking(self):
        history = self.plugin._records().add({"title": "Synthetic", "hash": "a" * 40, "status": "downloading"})
        self.plugin._pending().upsert({"hash": "a" * 40, "record_id": history["id"], "status": "downloading"})
        # 0.11.0：仍在跟踪的任务不允许隐藏，需先停止自动跟踪
        refused = self.plugin.api_records_delete({"id": history["id"]})
        self.assertEqual(refused["code"], 1)
        self.assertIn("停止自动跟踪", refused["msg"])
        self.assertEqual(self.plugin.api_task_action({"id": history["id"], "action": "stop_tracking"})["code"], 0)
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

    def test_background_organize_check_skips_when_nothing_pending(self):
        """没有未确认的记录时，后台核对不查任何接口。"""
        self.plugin._records().add({"status": "done", "acquisition_status": "saved", "organization_status": "success", "organization_confirmed": True, "title": "done one"})
        with patch.object(self.plugin, "_mp_api_json") as query:
            data = self.plugin.check_organization()
        self.assertEqual(data["data"]["checked"], 0)
        query.assert_not_called()

    def test_background_organize_check_runs_for_pending_records(self):
        """仅已获取且到期的批次核对，下载中的批次不查询MP历史。"""
        store = self.plugin._records()
        store.add({"status": "done", "acquisition_status": "saved", "title": "share one"})
        store.add({"status": "unverified", "acquisition_status": "saved", "title": "legacy one"})
        store.add({"status": "downloading", "acquisition_status": "downloading", "title": "still downloading"})
        with patch.object(self.plugin, "_mp_api_json", return_value={"data": {"list": [], "total": 0}}) as query:
            data = self.plugin.check_organization()
        self.assertEqual(query.call_count, 2)
        self.assertEqual(data["data"]["checked"], 2)
        self.assertEqual(data["data"]["confirmed"], 0)

    def test_organize_check_ignores_given_up_records(self):
        """已判「未找到整理记录」的记录不再进入后台核对（否则会永远查下去）。"""
        self.plugin._records().add({"status": "done", "acquisition_status": "saved", "organization_status": "paused", "org_giveup": True, "title": "deleted by hand"})
        self.plugin._records().add({"status": "done", "acquisition_status": "saved", "organization_status": "success", "organization_confirmed": True, "title": "confirmed"})
        with patch.object(self.plugin, "_mp_api_json") as query:
            data = self.plugin.check_organization()
        self.assertEqual(data["data"]["checked"], 0)
        query.assert_not_called()

    def test_organize_check_backs_off_then_gives_up(self):
        """空历史先指数退避；连续 4 次仍无任何证据 → 判「未找到整理记录」并移出自动核对（不再等 24 小时）。"""
        store = self.plugin._records()
        record = store.add({"title": "synthetic never organised", "type": "movie", "kind": "magnet",
                            "status": "done", "final_path": "/115-影视/115-downloads/电影"})

        def current():
            return [r for r in store.list() if r["id"] == record["id"]][0]

        with patch.object(self.plugin, "_mp_api_json", return_value={"data": {"list": [], "total": 0}}) as query:
            self.plugin.verify_organization(force=True)
            first = current()
            self.assertEqual(first["org_attempts"], 1)
            self.assertGreater(first["org_next_ts"], time.time())      # 进入退避期
            self.assertEqual(first["status"], "done")                  # 还没放弃
            self.assertEqual(first["organization_status"], "unknown")

            # 退避期内不重复查同一条
            self.plugin.verify_organization(force=True)
            self.assertEqual(current()["org_attempts"], 1)

            for _ in range(2):                                          # 累计到 3 次
                store.update(record["id"], org_next_ts=0)
                self.plugin.verify_organization(force=True)
            third = current()
            self.assertEqual(third["org_attempts"], 3)
            self.assertFalse(third.get("org_giveup"))
            self.assertEqual(third["organization_status"], "unknown")

            store.update(record["id"], org_next_ts=0)
            self.plugin.verify_organization(force=True)                 # 第 4 次
            final = current()
            self.assertEqual(final["org_attempts"], 4)
            self.assertTrue(final["org_giveup"])
            self.assertEqual(final["organization_status"], "unfound")
            self.assertEqual(final["acquisition_status"], "saved")      # 获取与防重事实保留
            self.assertIn("未找到", final["message"])

            query.reset_mock()
            self.assertEqual(self.plugin.check_organization()["data"]["checked"], 0)
            query.assert_not_called()                                   # 已放弃 → 不再查 MP

    def test_event_failure_does_not_kill_the_organize_tick(self):
        """单条事件处理异常不得让整轮核对失败（0.10.0 线上故障的成因），并有限次后跳过该事件。"""
        store = Mock()
        store.drain_events.return_value = [{"event_id": "bad-event", "payload": {"fileitem": {"path": "/x"}}}]
        store.ack_event = Mock()
        summary = {"checked": 1, "confirmed": 1, "partial": 0, "failed": 0, "unfound": 0}
        with patch.object(self.plugin, "_records", return_value=store), \
                patch.object(self.plugin, "_apply_queued_event", side_effect=RuntimeError("synthetic bad event")), \
                patch.object(self.plugin, "verify_organization", return_value=dict(summary)) as verify:
            for _ in range(self.plugin.EVENT_GIVEUP_ATTEMPTS):
                data = self.plugin.check_organization()
                self.assertEqual(data["code"], 0)                       # 不再静默失败
            verify.assert_called()                                      # 核对照常执行
            store.ack_event.assert_called_once_with("bad-event")        # 连续失败后跳过该事件
            self.assertEqual(getattr(self.plugin, "_last_org_tick", {}).get("state"), "ok")
            self.assertEqual(getattr(self.plugin, "_last_event_stats", {}).get("errors"), 1)

    def test_legacy_record_without_manifest_matches_by_title(self):
        """旧版本（没有本批清单）记录按标题/季号回退核对，不再误判为未找到。"""
        store = self.plugin._records()
        record = store.add({"title": "洛基 第二季", "type": "tv", "kind": "115_share",
                            "status": "done", "final_path": "/115-影视/115-downloads/电视剧"})
        body = {"data": {"list": [{"title": "洛基", "seasons": "S02", "episodes": "E06", "status": True,
                                   "dest": "/115-影视/115-links/电视剧/欧美剧/洛基 (2021)/Season 2/x.mkv"}],
                         "total": 1}}
        with patch.object(self.plugin, "_mp_api_json", return_value=body):
            self.plugin.verify_organization(force=True)
        final = [r for r in store.list() if r["id"] == record["id"]][0]
        self.assertEqual(final["organization_status"], "success")
        self.assertTrue(final["organization_confirmed"])
        self.assertEqual(final["organized_count"], 1)
        self.assertIn("标题", final["message"])

    def test_legacy_record_matches_tagged_title_but_not_the_sequel(self):
        """旧记录回退用去标签片名：带发布标签的标题能对上，续集不会被误配。"""
        store = self.plugin._records()
        tagged = store.add({"title": "飞驰人生[60帧率版本][高码版][国语配音+中文字幕].Pegasus.2019.2160p.WEB-DL.H265.HQ.60fps.DDP5.1.Atmos-BATWEB",
                            "type": "movie", "year": "2019", "kind": "magnet", "status": "done",
                            "final_path": "/115-影视/115-downloads/电影"})
        sequel = store.add({"title": "飞驰人生3[高码版].Pegasus.3.2026.2160p.WEB-DL",
                            "type": "movie", "year": "2026", "kind": "magnet", "status": "done",
                            "final_path": "/115-影视/115-downloads/电影"})
        body = {"data": {"list": [{"title": "飞驰人生", "status": True, "type": "movie",
                                   "dest": "/115-影视/115-links/电影/华语电影/飞驰人生 (2019)/x.mkv"}], "total": 1}}
        with patch.object(self.plugin, "_mp_api_json", return_value=body):
            self.plugin.verify_organization(force=True)
        rows = {r["id"]: r for r in store.list()}
        self.assertEqual(rows[tagged["id"]]["organization_status"], "success")
        self.assertNotEqual(rows[sequel["id"]]["organization_status"], "success")


if __name__ == "__main__":
    unittest.main()
