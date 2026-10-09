"""HTTP/scheduler contracts with real frameworks, synthetic data and no network.

Optional locally; CI and the isolated NAS process install/use these dependencies.
Never import the running MoviePilot app or load its configuration.
"""
import importlib.util
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_doc115subscribe_backend import PLUGIN_PATH, STUBS, rec, SyntheticTransfer, drive_worker

FRAMEWORKS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "apscheduler"))


@unittest.skipUnless(FRAMEWORKS, "FastAPI/httpx/APScheduler are required for framework contracts")
class FrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        cls.FastAPI, cls.TestClient = FastAPI, TestClient
        cls.Scheduler, cls.Cron = BackgroundScheduler, CronTrigger
        name = "_doc115_real_framework_testpkg"
        spec = importlib.util.spec_from_file_location(name, PLUGIN_PATH / "__init__.py",
            submodule_search_locations=[str(PLUGIN_PATH)])
        main = importlib.util.module_from_spec(spec)
        sys.modules[name] = main
        cls.app_stubs = {k: v for k, v in STUBS.items() if not k.startswith("apscheduler")}
        with patch.dict(sys.modules, cls.app_stubs), \
                patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED")), \
                patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")):
            spec.loader.exec_module(main)
        cls.main = main

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-framework-")
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.dict(sys.modules, self.app_stubs))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK DISABLED")))
        self.plugin = self.main.Doc115Subscribe()
        self.plugin.get_data_path = lambda: Path(self.temp.name)
        self.plugin.update_config = lambda _: None
        self.plugin.init_plugin({"enabled": False, "tencent_cookie": "SYNTHETIC-TENCENT-COOKIE",
                                 "p115_cookie": "SYNTHETIC-115-COOKIE"})
        self.addCleanup(self.plugin.stop_service)
        self.plugin._enabled = True
        self.transfer = SyntheticTransfer()
        self.plugin._transfers = lambda: self.transfer
        self.plugin._index = self.main.DocIndex(self.plugin._new_client())
        self.plugin._index._set_records([rec(), rec("Synthetic TV", media_type="tv", tmdbid="551")])
        app = self.FastAPI()
        for route in self.plugin.get_api():
            app.add_api_route(route["path"], route["endpoint"], methods=route["methods"])
        # Windows creates an internal loopback socketpair when the event loop starts.
        # Start only the in-memory portal, then block sockets before any request.
        self.client = self.enterContext(self.TestClient(app))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK DISABLED")))

    def test_real_http_search_and_transfer_bind_json_identity(self):
        response = self.client.post("/search", json={"keyword": "Synthetic", "media_type": "tv"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        record = data["records"][0]
        response = self.client.post("/transfer", json={"record_id": record["record_id"],
            "index_version": data["index_version"], "to": "tv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertEqual(self.transfer.calls, [])
        drive_worker(self.plugin)
        self.assertEqual(len(self.transfer.calls), 1)
        self.assertIn("/电视剧/", self.transfer.calls[0][2])
        self.assertEqual(self.client.get("/records").json()["data"]["records"][0]["title"], "Synthetic TV")

    def test_real_http_config_masks_secrets_and_rejects_invalid_cron(self):
        response = self.client.get("/get_config").json()
        self.assertEqual(response["data"]["tencent_cookie"], "")
        self.assertEqual(response["data"]["p115_cookie"], "")
        self.assertTrue(response["data"]["p115_ready"])
        response = self.client.post("/save_config", json={"index_cron": "99 99 * * *"}).json()
        self.assertEqual(response["code"], 1)
        self.assertEqual(self.plugin._index_cron, "0 6 * * *")

    def test_real_http_qr_parameters_are_query_parameters(self):
        class SyntheticQr:
            instances = []
            def __init__(self, _):
                self.session_id = f"synthetic-{len(self.instances)}"
                self.closed = False
                self.instances.append(self)
            def start(self):
                return b"synthetic-image", False, 0.01
            def close(self):
                self.closed = True
            def check(self):
                return {"state": "waiting"}
        with patch.object(self.main, "BrowserQrLogin", SyntheticQr):
            first = self.client.get("/qr_start").json()["data"]["session_id"]
            second = self.client.get("/qr_start", params={"force": True}).json()["data"]["session_id"]
            self.assertNotEqual(first, second)
            self.assertTrue(SyntheticQr.instances[0].closed)
            self.assertEqual(self.client.get("/qr_status", params={"session_id": first}).json()["code"], 1)
            self.assertEqual(self.client.get("/qr_status", params={"session_id": second}).json()["code"], 0)

    def test_failed_qr_start_closes_unassigned_worker(self):
        class SyntheticQr:
            instance = None
            def __init__(self, _):
                type(self).instance = self
                self.closed = False
            def start(self):
                raise RuntimeError("synthetic worker startup failure")
            def close(self):
                self.closed = True
        with patch.object(self.main, "BrowserQrLogin", SyntheticQr):
            self.assertEqual(self.client.get("/qr_start").json()["code"], 1)
            self.assertTrue(SyntheticQr.instance.closed)
            self.assertIsNone(self.plugin._qr)

    def test_real_scheduler_reloads_and_stops_without_cloud_calls(self):
        # All schedules are far in the future; nothing is allowed to contact a server.
        config = {"enabled": True, "subscribe_enabled": True, "index_cron": "0 0 1 1 *", "subscribe_cron": "0 0 1 1 *"}
        self.plugin.init_plugin(config)
        old = self.plugin._scheduler
        self.assertIsInstance(old, self.Scheduler)
        # 三个定时任务 + 后台整理核对（doc115-organize）
        old_ids = {job.id for job in old.get_jobs()}
        self.assertEqual(len(old.get_jobs()), 4)
        self.assertIn("doc115-organize", old_ids)
        self.plugin.init_plugin(config)
        current = self.plugin._scheduler
        self.assertIsNot(old, current)
        self.assertFalse(old.running)
        self.assertEqual(len(current.get_jobs()), 4)
        self.assertIn("doc115-organize", {job.id for job in current.get_jobs()})
        self.plugin.stop_service()
        self.assertFalse(current.running)
        self.assertEqual(self.transfer.calls, [])


if __name__ == "__main__":
    unittest.main()
