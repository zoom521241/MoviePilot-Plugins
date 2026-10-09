"""Release boundary contracts using fake services; all sockets are blocked."""
import importlib
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_doc115subscribe_backend as backend
import test_doc115subscribe_runtime_blackbox as blackbox


class ReleaseEdges(unittest.TestCase):
    setUp = blackbox.RuntimeBlackBox.setUp
    tearDown = blackbox.RuntimeBlackBox.tearDown
    queue = blackbox.RuntimeBlackBox.queue
    tick = blackbox.RuntimeBlackBox.tick
    histories = blackbox.RuntimeBlackBox.histories
    organize = blackbox.RuntimeBlackBox.organize

    def test_share_aliases_in_all_mode_have_one_resource_hold_and_one_receive(self):
        self.plugin._link_mode = "all"
        self.queue(links=[("115_share", "https://115.com/s/SYNTHETIC?password=1111"),
                          ("115_share", "https://www.115cdn.com/s/SYNTHETIC/?password=2222")])
        self.tick(3)
        self.assertEqual(len(self.plugin._records().list()), 1)
        self.assertEqual([x[0] for x in self.cloud.writes], ["receive"])

    def test_uncertain_share_does_not_offer_an_unsupported_download_action(self):
        self.cloud.uncertain_submit = True
        row = self.queue()
        self.tick()
        view = self.plugin.api_records()["data"]["records"][0]
        self.assertNotIn("check_download", view["allowed_actions"])
        self.assertNotIn("retry_submit", view["allowed_actions"])
        self.assertEqual(self.plugin.api_task_action({"id": row["id"], "action": "check_download"})["code"], 1)
        self.tick(3)
        self.assertEqual(len(self.cloud.writes), 1)

    def test_failed_magnet_reconciles_original_task_without_second_submit(self):
        row = self.queue(links=[("magnet", "magnet:?xt=urn:btih:" + "a"*40)], expected_episodes=list(range(1, 21)))
        self.tick()
        self.plugin._records().update(row["id"], acquisition_status="failed", status="failed")
        self.assertEqual(self.plugin.api_task_action({"id": row["id"], "action": "check_download"})["code"], 0)
        self.tick(3)
        self.assertEqual(self.plugin._records().get(row["id"])["acquisition_status"], "saved")
        self.assertEqual([x[0] for x in self.cloud.writes], ["offline", "move"])

    def test_duplicate_submit_deferral_reconciles_only_and_never_tries_mirror(self):
        deferred = importlib.import_module(backend.main.__package__ + ".p115_transfer").P115Deferred
        row = self.queue(links=[("magnet", "magnet:?xt=urn:btih:" + "a"*40),
                                ("115_share", "https://115.com/s/SYNTHETICBACKUP")], expected_episodes=list(range(1, 21)))
        def duplicate(url, path, before_submit=None):
            before_submit({"url": url})
            self.cloud.writes.append(("offline", url, path))
            exc = deferred("synthetic duplicate recovery slice", reason="slice", state={"file_id": "100", "recovery_cursor": None})
            exc.reconcile_only = True
            raise exc
        self.cloud.offline_add = duplicate
        self.tick(4)
        self.assertEqual(self.plugin._records().get(row["id"])["acquisition_status"], "saved")
        self.assertEqual([x[0] for x in self.cloud.writes], ["offline", "move"])
        self.assertEqual(len(self.plugin._records().list()), 1)

    def test_movie_saved_in_tv_directory_keeps_movie_identity_for_mp_proof(self):
        candidate = backend.rec("Synthetic Film", media_type="movie", sheet="电影", tmdbid="550")
        self.assertTrue(self.plugin.do_transfer(candidate, "tv")[0])
        row = self.plugin._records().list()[0]
        self.tick()
        self.assertEqual((row["type"], row["target_type"]), ("movie", "tv"))
        # The synthetic share contains a TV-looking filename; MP identity is movie.
        entry = {**self.histories(row, 1)[0], "title": "Synthetic Film", "type": "电影", "tmdbid": "550"}
        self.organize(row, [entry])
        self.assertEqual(self.plugin._records().get(row["id"])["organized_count"], 1)

    def test_directories_get_is_local_and_background_snapshot_has_ui_contract_and_ttl(self):
        query = Mock(return_value={"success": True, "data": [
            {"name": "Synthetic TV", "storage": "115网盘Plus", "download_path": "/synthetic/tv", "media_type": "电视剧"},
            {"name": "Unrelated", "storage": "local", "download_path": "/local"}]})
        self.plugin._mp_api_json = query
        self.plugin.api_directories()
        query.assert_not_called()
        self.plugin.check_organization()
        response = self.plugin.api_directories()["data"]
        self.assertEqual(len(response["records"]), 1)
        self.assertEqual((response["records"][0]["path"], response["records"][0]["media_type"]), ("/synthetic/tv", "tv"))
        self.assertIsNone(response["records"][0]["monitored"])
        self.plugin.check_organization()
        self.assertEqual(query.call_count, 1)

    def test_directory_errors_back_off_without_stopping_other_local_work(self):
        self.plugin.api_directories()
        query = Mock(side_effect=RuntimeError("synthetic MP error"))
        self.plugin._mp_api_json = query
        for _ in range(5):
            self.plugin.api_directories()
            self.plugin.check_organization()
        self.assertEqual(query.call_count, 1)
        self.assertTrue(self.plugin.api_directories()["data"]["error"])


class SubscriptionPreviewContracts(unittest.TestCase):
    setUp = backend.BackendTests.setUp
    tearDown = backend.BackendTests.tearDown
    install_index = backend.BackendTests.install_index
    subscribe = backend.BackendTests.subscribe

    def prepare(self, **fields):
        self.install_index([backend.rec(qtext="1080P 中文字幕"), backend.rec(qtext="4K 英文", row=2)])
        self.subscribe(**fields)
        raw = self.plugin._mp_subscribes()[0]
        self.plugin._subscriptions_cache = (time.time(), [raw])
        return raw

    def test_preview_and_automatic_share_filter_rules(self):
        self.prepare(include="中文", resolution="1080P", exclude="4K")
        self.assertEqual(self.plugin.api_subscriptions_preview()["data"]["records"][0]["matched"], 1)
        self.assertEqual(self.plugin.run_subscribe()["data"]["transferred"], 1)
        self.assertEqual(self.plugin.api_subscriptions_preview()["data"]["records"][0]["state"], "skipped")

    def test_external_filters_invalid_regex_inactive_and_completed_are_not_previewed_as_ready(self):
        for fields in ({"filter_groups": ["synthetic"]}, {"include": "["}, {"state": "S"}):
            with self.subTest(fields=fields):
                self.prepare(**fields)
                result = self.plugin.api_subscriptions_preview()["data"]["records"][0]
                self.assertEqual(result["matched"], 0)
                self.assertNotEqual(result["state"], "ready")
        self.prepare()
        self.plugin.run_subscribe()
        state = self.plugin._subscription_store().list()[0]
        self.plugin._records().stop_tracking(self.plugin._records().list()[0]["id"])
        self.plugin._set_subscription(state["key"], status="complete", completed_quality_score=100)
        self.assertEqual(self.plugin.api_subscriptions_preview()["data"]["records"][0]["matched"], 0)

    def test_deterministic_subscription_manual_interleaving_keeps_each_result(self):
        self.prepare()
        returned, proceed = threading.Event(), threading.Event()
        original = self.plugin.do_transfer
        failures = []
        def interleaved(candidate, *args, **kwargs):
            result = original(candidate, *args, **kwargs)
            if candidate.get("_subscription_key"):
                returned.set()
                if not proceed.wait(3):
                    failures.append("timeout")
            return result
        self.plugin.do_transfer = interleaved
        worker = threading.Thread(target=self.plugin.run_subscribe)
        worker.start()
        self.assertTrue(returned.wait(3))
        try:
            manual = backend.rec("Other manual film", tmdbid="777", links=[("115_share", "https://115.com/s/OTHER")])
            original(manual, "movie")
            manual_key = self.plugin._last_transfer_result["resource_keys"][0]
        finally:
            proceed.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        state = self.plugin._subscription_store().list()[0]
        self.assertNotIn(manual_key, state["required_resources"])
        self.assertEqual(self.plugin._records().find_by_resource(state["required_resources"][0])["title"], "Synthetic Film")
        self.assertEqual(self.plugin._last_transfer_result["resource_keys"], [manual_key])
