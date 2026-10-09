"""MP adapter and native permissions contracts with all networking disabled."""
import importlib.util
import json
import socket
import sys
import time
import types
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_doc115subscribe_backend as backend

ROOT = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load("_doc115_adapter_unit", ROOT / "mp_adapter.py")
permissions = load("_doc115_permissions_unit", ROOT / "permissions.py")


class Clock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now


class Response:
    def __init__(self, body=None, url=None, raw=None):
        self.body = raw if raw is not None else json.dumps(body or {"success": True, "data": {"list": [], "total": 0}}).encode()
        self.url = url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self):
        return self.body
    def geturl(self):
        return self.url


class MPAdapterTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED")))
        self.clock = Clock()
        self.opener = Mock(side_effect=lambda request, **_: Response(url=request.full_url))
        self.mp = adapter.MPAdapter(SimpleNamespace(API_TOKEN="SYNTHETIC-ONLY", PORT=4567), clock=self.clock, opener=self.opener)

    def http_error(self, code):
        return urllib.error.HTTPError("http://synthetic.invalid", code, "synthetic failure", {}, None)

    def test_401_and_403_are_one_request_then_account_cooldown_without_other_ports(self):
        for code in (401, 403):
            with self.subTest(code=code):
                self.opener.reset_mock()
                self.opener.side_effect = self.http_error(code)
                self.mp = adapter.MPAdapter(SimpleNamespace(API_TOKEN="SYNTHETIC", PORT=4567), clock=self.clock, opener=self.opener)
                with self.mp.work_slice():
                    with self.assertRaises(adapter.MPDeferred) as rejected:
                        self.mp.get("/api/v1/history/transfer")
                self.assertEqual(self.opener.call_count, 1)
                self.assertEqual(rejected.exception.retry_at, 1900)
                self.clock.now += 899
                with self.mp.work_slice():
                    with self.assertRaises(adapter.MPDeferred):
                        self.mp.get("/api/v1/subscribe/")
                self.assertEqual(self.opener.call_count, 1)
                self.clock.now = 1000

    def test_no_token_or_mutating_path_never_reaches_network(self):
        self.mp.settings.API_TOKEN = ""
        with self.assertRaises(adapter.MPDeferred):
            self.mp.get("/api/v1/history/transfer")
        with self.assertRaises(ValueError):
            self.mp.get("/api/v1/transfer/manual")
        self.opener.assert_not_called()

    def test_native_authentication_is_header_only_and_port_is_cached(self):
        with self.mp.work_slice():
            self.mp.get("/api/v1/history/transfer", {"title": "合成片名"})
            self.mp.get("/api/v1/subscribe/")
        self.assertEqual(self.opener.call_count, 2)
        for call in self.opener.call_args_list:
            request = call.args[0]
            self.assertTrue(request.full_url.startswith("http://127.0.0.1:4567/"))
            self.assertNotIn("SYNTHETIC-ONLY", request.full_url)
            self.assertEqual(request.get_header("X-api-key"), "SYNTHETIC-ONLY")

    def test_one_slice_allows_five_calls_and_yields_before_sixth(self):
        with self.mp.work_slice():
            for number in range(5):
                self.mp.get("/api/v1/history/transfer", {"page": number + 1})
            with self.assertRaises(adapter.MPDeferred):
                self.mp.get("/api/v1/history/transfer", {"page": 6})
        self.assertEqual(self.opener.call_count, 5)
        with self.mp.work_slice():
            self.mp.get("/api/v1/history/transfer", {"page": 6})
        self.assertEqual(self.opener.call_count, 6)

    def test_rolling_minute_budget_shared_by_all_titles_and_pages(self):
        for number in range(4):
            with self.mp.work_slice():
                for page in range(5):
                    self.mp.get("/api/v1/history/transfer", {"title": str(number), "page": page + 1})
        with self.mp.work_slice():
            with self.assertRaises(adapter.MPDeferred) as deferred:
                self.mp.get("/api/v1/subscribe/")
        self.assertEqual(self.opener.call_count, 20)
        self.assertEqual(deferred.exception.retry_at, 1060)
        self.clock.now = 1060
        with self.mp.work_slice():
            self.mp.get("/api/v1/subscribe/")
        self.assertEqual(self.opener.call_count, 21)

    def test_cancel_or_elapsed_slice_stops_following_call_but_retains_inflight_response(self):
        def slow(request, **_):
            self.clock.now += 16
            return Response(url=request.full_url)
        self.opener.side_effect = slow
        with self.mp.work_slice():
            self.assertTrue(self.mp.get("/api/v1/history/transfer")["success"])
            with self.assertRaises(adapter.MPDeferred):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)
        with self.mp.work_slice(cancelled=lambda: True):
            with self.assertRaises(adapter.MPDeferred):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)

    def test_concurrent_slice_is_rejected_without_waiting_or_network(self):
        with self.mp.work_slice():
            with self.assertRaises(adapter.MPDeferred):
                with self.mp.work_slice():
                    self.fail("A second concurrent slice was admitted")
        self.opener.assert_not_called()

    def test_directory_and_subscription_cache_ttl_avoids_duplicate_reads(self):
        with self.mp.work_slice():
            self.mp.cached("/api/v1/storage/directories")
            self.mp.cached("/api/v1/storage/directories")
        self.assertEqual(self.opener.call_count, 1)
        self.clock.now += 300
        with self.mp.work_slice():
            self.mp.cached("/api/v1/storage/directories")
        self.assertEqual(self.opener.call_count, 2)

    def test_no_redirect_handler_never_follows_location(self):
        handler = adapter._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "synthetic", {}, "https://synthetic.invalid/login"))

    def test_redirect_is_rejected_once_and_not_retried_on_other_ports(self):
        self.opener.side_effect = self.http_error(302)
        with self.mp.work_slice():
            with self.assertRaises((RuntimeError, adapter.MPDeferred)):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)

    def test_contract_error_422_is_not_retried_across_ports(self):
        self.opener.side_effect = self.http_error(422)
        with self.mp.work_slice():
            with self.assertRaises((RuntimeError, adapter.MPDeferred)):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)

    def test_invalid_json_contract_stops_port_probes(self):
        self.opener.side_effect = lambda request, **_: Response(raw=b"<html>login</html>", url=request.full_url)
        with self.mp.work_slice():
            with self.assertRaises((RuntimeError, adapter.MPDeferred)):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)

    def test_known_port_failure_has_shared_error_backoff(self):
        with self.mp.work_slice():
            self.mp.get("/api/v1/history/transfer")
        self.opener.reset_mock()
        self.opener.side_effect = OSError("synthetic refused")
        with self.mp.work_slice():
            with self.assertRaises((RuntimeError, adapter.MPDeferred)):
                self.mp.get("/api/v1/history/transfer")
        self.assertEqual(self.opener.call_count, 1)
        with self.mp.work_slice():
            with self.assertRaises(adapter.MPDeferred):
                self.mp.get("/api/v1/subscribe/")
        self.assertEqual(self.opener.call_count, 1)

    def test_pagination_unknown_total_and_invalid_rows_are_not_complete(self):
        self.assertEqual(adapter.MPAdapter.page({"data": []}), ([], None))
        self.assertEqual(adapter.MPAdapter.page({"data": {"items": [{"id": 1}]}}), ([{"id": 1}], None))
        self.assertEqual(adapter.MPAdapter.page({"data": {"list": [{"id": 1}], "total": 20}}), ([{"id": 1}], 20))
        for data in (None, {"list": "bad"}, {"list": [None]}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapter.MPAdapter.page({"data": data})


class RuntimeEvidenceContracts(unittest.TestCase):
    setUp = backend.BackendTests.setUp
    tearDown = backend.BackendTests.tearDown

    def batch(self, name="Synthetic Season", count=20, moving=False, ordinal=0):
        folder = f"/Synthetic/Final/batch-{ordinal}"
        row = self.plugin._records().add({"title": name, "year": "2025", "type": "tv", "tmdbid": "900",
            "source_storage": "115网盘Plus", "final_path": "/Synthetic/Final", "staging_path": "/Synthetic/Staging",
            "resource_key": "resource-" + str(ordinal), "hash": "a" * 40, "kind": "magnet",
            "status": "downloading" if moving else "done", "acquisition_status": "downloading" if moving else "saved",
            "config_generation": self.plugin._generation, "task_file_id": "root-" + str(ordinal),
            "expected_episodes": list(range(1, count + 1)), "org_next_ts": 0, "next_check_at": 0,
            "subscription_key": "movie:synthetic-" + str(ordinal)})
        units = [{"source_path": f"{folder}/Show.S01E{number:02}.mkv", "storage": "115网盘Plus",
                  "file_id": str(ordinal * 1000 + number), "required": True} for number in range(1, count + 1)]
        self.plugin._records().set_manifest(row["id"], units, complete=True)
        if moving:
            attempt = self.plugin._records().begin_attempt(row["id"], phase="move", generation=self.plugin._generation)
            self.plugin._records().save_receipt(attempt["attempt_id"], "accepted", {"task_file_id": row["task_file_id"]})
        self.plugin._set_subscription(row["subscription_key"], status="pending", required_resources=[row["resource_key"]])
        return self.plugin._records().get(row["id"])

    def evidence(self, row, count=20):
        stamp = time.time() + 100
        return [{"id": "history-" + unit["file_id"], "title": row["title"], "year": "2025", "type": "电视剧",
                 "tmdbid": "900", "date": stamp, "status": True, "src_fileitem": {
                     "path": unit["source_path"], "storage": "u115", "fileid": unit["file_id"]}}
                for unit in row["manifest"][:count]]

    def verify(self, rows):
        self.plugin._mp_api_json = Mock(return_value={"success": True, "data": {"list": rows, "total": len(rows)}})
        return self.plugin.verify_organization()

    def test_twenty_success_after_mp_removes_root_confirms_original_move_without_second_write(self):
        row = self.batch(moving=True)
        cloud = SimpleNamespace(get_file_info=Mock(return_value=None), list_tasks_slice=Mock(return_value={"items": [], "complete": True}),
                                move_via_p115disk=Mock(side_effect=AssertionError("MOVE MUST NOT REPEAT")))
        self.plugin._transfers = Mock(return_value=cloud)
        result = self.verify(self.evidence(row))
        self.assertEqual(result["confirmed"], 1)
        current = self.plugin._records().get(row["id"])
        self.assertEqual((current["acquisition_status"], current["move_status"], current["organization_status"]), ("saved", "success", "success"))
        self.assertEqual(self.plugin._records().attempts(row["id"])[0]["outcome"], "success")
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")
        self.assertEqual(self.plugin.check_offline_tasks()["data"]["pending"], 0)
        self.plugin._transfers.assert_not_called()
        cloud.move_via_p115disk.assert_not_called()

    def test_accepted_move_and_nineteen_success_confirms_move_but_keeps_missing_episode(self):
        row = self.batch(moving=True)
        result = self.verify(self.evidence(row, 19))
        self.assertEqual(result["partial"], 1)
        current = self.plugin._records().get(row["id"])
        self.assertEqual((current["organization_status"], current["organized_count"], current["organized_missing"]), ("partial", 19, 1))
        self.assertEqual(current["acquisition_status"], "saved")
        self.assertFalse(current["organization_confirmed"])
        self.assertEqual(self.plugin._records().attempts(row["id"])[0]["outcome"], "success")
        self.assertEqual(self.plugin._subscription_store().list()[0]["status"], "complete")
        cloud = Mock()
        self.plugin._transfers = Mock(return_value=cloud)
        self.plugin.check_offline_tasks()
        self.plugin._transfers.assert_not_called()

    def test_uncertain_move_and_nineteen_success_keeps_move_unconfirmed(self):
        row = self.batch(moving=True)
        attempt = self.plugin._records().attempts(row["id"])[0]
        self.plugin._records().save_receipt(attempt["attempt_id"], "uncertain", {}, self.plugin._generation)
        self.verify(self.evidence(row, 19))
        current = self.plugin._records().get(row["id"])
        self.assertEqual(current["organization_status"], "partial")
        self.assertEqual(current["acquisition_status"], "moving")
        self.assertEqual(current["move_status"], "uncertain")

    def test_same_title_batches_share_one_history_query_but_each_has_its_own_evidence(self):
        first, second = self.batch(count=1, ordinal=1), self.batch(count=1, ordinal=2)
        result = self.verify(self.evidence(first) + self.evidence(second))
        self.assertEqual(self.plugin._mp_api_json.call_count, 1)
        self.assertEqual(result["confirmed"], 2)
        for row in (first, second):
            current = self.plugin._records().get(row["id"])
            self.assertEqual(current["organized_count"], 1)
            self.assertTrue(current["organization_confirmed"])

    def test_same_title_query_error_is_shared_and_each_batch_backs_off_without_business_failure(self):
        rows = [self.batch(count=1, ordinal=number) for number in range(5)]
        self.plugin._mp_api_json = Mock(side_effect=RuntimeError("synthetic MP outage"))
        result = self.plugin.verify_organization()
        self.assertEqual(result["checked"], 0)
        self.assertEqual(self.plugin._mp_api_json.call_count, 1)
        for row in rows:
            current = self.plugin._records().get(row["id"])
            self.assertEqual(current["acquisition_status"], "saved")
            self.assertEqual(current["org_error_count"], 1)
            self.assertGreater(current["org_next_ts"], time.time())
            self.assertNotIn(current.get("organization_status"), ("failed", "success"))
        self.plugin.verify_organization(force=True)
        self.assertEqual(self.plugin._mp_api_json.call_count, 1)


FRAMEWORKS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))


@unittest.skipUnless(FRAMEWORKS, "FastAPI/httpx required for native permission contracts")
class PermissionsTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.testclient import TestClient
        self.FastAPI, self.TestClient = FastAPI, TestClient
        self.called = []
        def native_superuser(x_role: str = Header(default="anonymous")):
            if x_role == "anonymous":
                raise HTTPException(401, "synthetic login required")
            if x_role != "admin":
                raise HTTPException(403, "synthetic admin required")
            return {"username": "synthetic-admin", "is_superuser": True}
        self.native_superuser = native_superuser
        self.modules = {}
        for name in ("app", "app.api", "app.api.dependencies", "app.api.endpoints"):
            value = types.ModuleType(name)
            value.__path__ = []
            self.modules[name] = value
        auth = types.ModuleType("app.api.dependencies.auth")
        auth.get_current_active_superuser = native_superuser
        self.modules["app.api.dependencies.auth"] = auth
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED")))

    def app(self, modules):
        app = self.FastAPI()
        def body(payload: dict = None):
            self.called.append(("body", payload))
            return {"payload": payload}
        def query(page: int = 1, keyword: str = ""):
            self.called.append(("query", page, keyword))
            return {"page": page, "keyword": keyword}
        with patch.dict(sys.modules, modules):
            app.post("/body")(permissions.protect_endpoint(body))
            app.get("/query")(permissions.protect_endpoint(query))
        return app

    def test_anonymous_401_regular_user_403_and_admin_200_preserve_json_and_query(self):
        with self.TestClient(self.app(self.modules)) as client:
            with patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")):
                self.assertEqual(client.post("/body", json={"id": "synthetic"}).status_code, 401)
                self.assertEqual(client.post("/body", json={"id": "synthetic"}, headers={"X-Role": "regular"}).status_code, 403)
                self.assertEqual(self.called, [])
                response = client.post("/body", json={"id": "synthetic", "nested": {"target": "tv"}}, headers={"X-Role": "admin"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["payload"], {"id": "synthetic", "nested": {"target": "tv"}})
                response = client.get("/query", params={"page": 7, "keyword": "合成片名"}, headers={"X-Role": "admin"})
                self.assertEqual(response.json(), {"page": 7, "keyword": "合成片名"})
                self.assertEqual(len(self.called), 2)

    def test_legacy_native_auth_import_path_is_supported(self):
        modules = {name: value for name, value in self.modules.items() if name != "app.api.dependencies.auth"}
        auth = types.ModuleType("app.api.endpoints.user")
        auth.get_current_active_superuser = self.native_superuser
        modules["app.api.endpoints.user"] = auth
        with patch.dict(sys.modules, {"app.api.dependencies.auth": None}):
            with self.TestClient(self.app(modules)) as client:
                with patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")):
                    self.assertEqual(client.get("/query", headers={"X-Role": "admin"}).status_code, 200)

    def test_unknown_native_auth_contract_fails_closed_with_503(self):
        modules = {**self.modules, "app.api.dependencies.auth": None, "app.api.endpoints.user": None}
        with self.TestClient(self.app(modules)) as client:
            with patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")):
                self.assertEqual(client.post("/body", json={"id": "synthetic"}, headers={"X-Role": "admin"}).status_code, 503)
                self.assertEqual(self.called, [])


if __name__ == "__main__":
    unittest.main()
