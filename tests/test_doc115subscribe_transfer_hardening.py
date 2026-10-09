"""Cloud black-box contracts with an invented in-memory HTTP service only."""
import importlib.util
import io
import json
import socket
import sys
import tempfile
import unittest
from contextlib import ExitStack
from http.cookiejar import CookieJar
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch, Mock

SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe/p115_transfer.py"
SPEC = importlib.util.spec_from_file_location("doc115_hardening_test", SOURCE)
transfer = importlib.util.module_from_spec(SPEC)
router = ModuleType("link_router")
router.LINK_115_SHARE, router.LINK_ED2K, router.LINK_MAGNET = "115_share", "ed2k", "magnet"
with patch.dict(sys.modules, {SPEC.name: transfer, "link_router": router,
                             "p115client": ModuleType("p115client"), "p115client.util": ModuleType("p115client.util")}):
    SPEC.loader.exec_module(transfer)
Budget = transfer.account_budget.__globals__["AccountBudget"]
BTIH = "0123456789abcdef0123456789abcdef01234567"
MAGNET = "magnet:?xt=urn:btih:" + BTIH


class Clock:
    now = 100.0
    def sleep(self, delay):
        self.now += delay


class Response:
    def __init__(self, content, headers=None):
        self.content = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.headers = headers or {}
        self.status = 200
    def read(self):
        return self.content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class FakeSDK:
    """A supported injected-request SDK contract, including nested retries."""
    def __init__(self, cookie):
        self.cookies = CookieJar()
    def request(self, url, method="GET", payload=None, *, request=None, async_=False, **kwargs):
        kwargs.pop("check", None)
        kwargs["data" if method == "POST" else "params"] = payload
        return request(url=url, method=method, cookies=self.cookies,
            parse=lambda response, content: json.loads(content), async_=async_, **kwargs)
    def fs_dir_getid(self, p, **kw):
        return self.request("https://synthetic.invalid/files/getid", payload={"path": p}, **kw)
    def fs_makedirs_app(self, p, **kw):
        return self.request("https://synthetic.invalid/app/chrome/add_path", "POST", {"path": p}, **kw)
    def share_snap(self, p, **kw):
        return self.request("https://synthetic.invalid/share/snap", payload=p, **kw)
    def share_receive(self, p, **kw):
        return self.request("https://synthetic.invalid/share/receive", "POST", p, **kw)
    def clouddownload_task_add_urls(self, p, **kw):
        return self.request("https://synthetic.invalid/?ac=add_task_urls", "POST", p, **kw)
    def clouddownload_task_list(self, p, **kw):
        return self.request("https://synthetic.invalid/?ac=task_lists", payload=p, **kw)
    def fs_file(self, p, **kw):
        return self.request("https://synthetic.invalid/files/get_info", payload={"file_id": p}, **kw)
    def fs_files(self, p, **kw):
        return self.request("https://synthetic.invalid/files", payload=p, **kw)
    def fs_move(self, p, pid=0, **kw):
        return self.request("https://synthetic.invalid/files/move", "POST", {"fid": p, "pid": pid}, **kw)
    def fs_move_app(self, p, pid=0, **kw):
        return self.fs_move(p, pid, **kw)


class FakeItem(SimpleNamespace):
    def model_dump(self):
        return vars(self).copy()


class FakeCache:
    def __init__(self):
        self.paths = {}
    def add_cache(self, id, directory):
        self.paths[directory] = id
    def get_id_by_dir(self, directory):
        return self.paths.get(directory)


class FakePlus:
    instances = []
    def __init__(self, client, disk_name):
        self.client = client
        self._id_cache = FakeCache()
        self.get_item_strict = Mock(side_effect=AssertionError("shared u115 fallback forbidden"))
        self.instances.append(self)
    def move(self, fileitem, path, new_name):
        # Like Plus, a swallowed SDK exception must still stop this worker.
        try:
            cid = self._id_cache.get_id_by_dir(path.as_posix())
            if cid is None:
                raise AssertionError("controlled target cache missing")
            result = self.client.fs_move(fileitem.fileid, pid=cid)
            return bool(result.get("state"))
        except Exception:
            return False


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))
        self.stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("LIVE NETWORK FORBIDDEN")))
        self.clock = Clock()
        self.b = Budget(clock=lambda: self.clock.now, wall_clock=lambda: self.clock.now + 1000,
                        sleep=self.clock.sleep)
        self.stack.enter_context(patch.object(transfer, "P115_AVAILABLE", True))
        self.stack.enter_context(patch.object(transfer, "P115Client", FakeSDK))
        self.stack.enter_context(patch.object(transfer, "account_budget", return_value=self.b))
        self.stack.enter_context(patch.object(transfer, "share_extract_payload", return_value={"share_code": "synthetic"}))
        self.api = transfer.P115Transfer("UID=synthetic_A; CID=synthetic")
        self.calls = []
        self.handler = lambda path, payload: {"state": True, "id": 42}
        def opened(request, **kwargs):
            parsed = urlsplit(request.full_url)
            payload = parse_qs(parsed.query)
            if request.data:
                payload.update(parse_qs(request.data.decode()))
            payload = {key: values[0] for key, values in payload.items()}
            self.calls.append((parsed.path, payload, self.clock.now))
            result = self.handler(parsed.path, payload)
            if isinstance(result, Exception):
                raise result
            return Response(result)
        self.stack.enter_context(patch.object(transfer, "build_opener", return_value=SimpleNamespace(open=opened)))

    def synthetic_episodes(self, count=20):
        return [{"fid": str(100 + i), "n": f"Synthetic.S01E{i+1:02}.mkv", "fc": "1"} for i in range(count)]

    def test_twenty_episodes_are_received_in_one_write_with_prewrite_attempt(self):
        episodes = self.synthetic_episodes()
        def handler(path, payload):
            if path == "/share/snap":
                return {"state": True, "data": {"count": 20, "list": episodes}}
            return {"state": True, "id": 42}
        self.handler = handler
        attempts = []
        with self.api.work_slice():
            state = self.api.prepare_share("https://115.com/s/synthetic", "/Synthetic")
            self.assertEqual(len(self.calls), 2)
            self.assertTrue(state["complete"])
            self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state,
                before_submit=lambda intent: attempts.append((intent, len(self.calls))))
        self.assertTrue(state["done"])
        received = [payload for path, payload, _ in self.calls if path == "/share/receive"]
        self.assertEqual(len(received), 1)
        self.assertEqual(len(received[0]["file_id"].split(",")), 20)
        self.assertEqual(attempts[0][1], 2)
        self.assertEqual(len(self.b._submission_times), 1)
        self.assertEqual([call[2] for call in self.calls], [100, 102, 104])

    def test_large_share_resumes_pages_and_batches_without_duplicate_receive(self):
        episodes = self.synthetic_episodes(701)
        def handler(path, payload):
            if path == "/share/snap":
                offset = int(payload["offset"])
                return {"state": True, "data": {"count": len(episodes), "list": episodes[offset:offset+200]}}
            return {"state": True, "id": 42}
        self.handler = handler
        state = None
        for _ in range(4):
            with self.api.work_slice():
                state = self.api.prepare_share("https://115.com/s/synthetic", "/Synthetic", state)
            if state["complete"]:
                break
        self.assertTrue(state["complete"])
        self.assertEqual(len(state["items"]), 701)
        while not state["done"]:
            with self.api.work_slice():
                self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state)
        ids = [fid for path, payload, _ in self.calls if path == "/share/receive"
               for fid in payload["file_id"].split(",")]
        self.assertEqual(ids, [row["fid"] for row in episodes])
        self.assertEqual(len(self.b._submission_times), 1)

    def test_budget_rejects_before_attempt_callback_and_is_not_uncertain(self):
        state = {"identity": transfer.hashlib.sha256(b"synthetic\0/Synthetic").hexdigest(),
                 "complete": True, "cid": 42, "items": [{"id": "7", "name": "Synthetic.mkv"}], "received": 0}
        attempt = Mock()
        with self.api.work_slice(max_requests=1):
            self.api.get_file_info = lambda fid: None
            self.api._call("user_info") if hasattr(self.api.client, "user_info") else self.api.path_to_id("/Synthetic")
            with self.assertRaises(transfer.P115Deferred) as raised:
                self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state, attempt)
        attempt.assert_not_called()
        self.assertTrue(raised.exception.not_sent)
        self.assertFalse(state["uncertain"])
        self.assertEqual(len(self.calls), 1)

    def test_lost_share_response_preserves_unknown_receipt_and_never_resends(self):
        self.handler = lambda path, payload: TimeoutError("synthetic lost reply")
        state = {"identity": transfer.hashlib.sha256(b"synthetic\0/Synthetic").hexdigest(),
                 "complete": True, "cid": 42, "items": [{"id": "7", "name": "Synthetic.mkv"}], "received": 0}
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state)
        self.assertTrue(raised.exception.uncertain)
        self.assertFalse(raised.exception.not_sent)
        self.assertTrue(state["uncertain"])
        self.clock.sleep(61)
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred):
            self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state)
        self.assertEqual(len(self.calls), 1)

    def test_auth_risk_and_429_stop_nested_retry_and_following_methods(self):
        for failure in ({"state": False, "errno": 99}, {"state": False, "errno": 911},
                        {"state": False, "errno": 590075}):
            with self.subTest(failure=failure):
                self.b._cooldown_until = 0
                self.handler = lambda path, payload: failure
                before = len(self.calls)
                with self.api.work_slice(), self.assertRaises(transfer.P115Deferred):
                    self.api.client.fs_file("7")
                with self.api.work_slice(), self.assertRaises(transfer.P115Deferred):
                    self.api.client.fs_move_app("7", pid=42)
                self.assertEqual(len(self.calls), before + 1)

    def test_http_429_retry_after_enters_shared_cooldown(self):
        self.handler = lambda path, payload: HTTPError("https://synthetic.invalid/", 429, "limited", {"Retry-After": "600"}, io.BytesIO())
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.client.fs_files({"cid": 42})
        self.assertEqual(raised.exception.reason, "rate_limit")
        self.assertEqual(self.api.budget_state["retry_at"], 1700)
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred):
            self.api.client.fs_file("7")
        self.assertEqual(len(self.calls), 1)

    def test_offline_accepted_is_not_download_complete_and_timeout_is_one_submit(self):
        self.handler = lambda path, payload: {"state": True, "id": 42}
        with self.api.work_slice():
            receipt = self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(receipt.accepted)
        self.assertEqual(receipt.file_id, "")
        self.assertEqual(receipt.task, {})
        self.clock.sleep(60)
        self.handler = lambda path, payload: TimeoutError("synthetic")
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(raised.exception.uncertain)
        self.assertTrue(self.api.last_offline_result.uncertain)
        self.assertEqual(len(self.calls), 3)

    def test_fs_file_cache_is_per_slice_and_write_allows_one_recheck(self):
        self.handler = lambda path, payload: {"state": True, "data": [{"file_id": "7", "parent_id": "42", "file_name": "Synthetic.mkv"}]}
        with self.api.work_slice():
            self.assertEqual(self.api.get_file_info("7"), self.api.get_file_info("7"))
            self.api.invalidate_file_info("7")
            self.api.get_file_info("7")
            self.api.get_file_info("7")
        self.assertEqual(len(self.calls), 2)
        with self.api.work_slice():
            self.api.get_file_info("7")
        self.assertEqual(len(self.calls), 3)

    def test_source_manifest_survives_deleted_episode_and_never_reuses_source_ids(self):
        episodes = self.synthetic_episodes()
        self.handler = lambda path, payload: {"state": True, "data": {"count": 1, "list": [{"cid": "9", "n": "SyntheticSeason", "fc": "0"}]}} if payload.get("cid") == "0" else {"state": True, "data": {"count": 20, "list": episodes}}
        with self.api.work_slice():
            source = self.api.share_manifest_slice("https://115.com/s/synthetic")
        self.assertTrue(source["complete"])
        media = [row for row in source["items"] if row["required"]]
        self.assertEqual(len(media), 20)
        self.assertTrue(all(row["target_file_id"] == "" and "id" not in row for row in media))
        self.assertEqual(media[-1]["relative_path"], "SyntheticSeason/Synthetic.S01E20.mkv")
        # The target directory now contains only 19. Source expectation stays 20.
        self.handler = lambda path, payload: {"state": True, "count": 19, "data": episodes[:-1]}
        with self.api.work_slice():
            observed = self.api.manifest_slice("/Synthetic", file_id="42")
        self.assertEqual(len([r for r in observed["items"] if r["required"]]), 19)
        self.assertEqual(len(media), 20)

    def test_partial_list_cannot_be_used_as_missing_and_resumes_with_stability_check(self):
        tasks = [{"info_hash": f"{i:040x}", "status": 1} for i in range(12)]
        self.handler = lambda path, payload: {"state": True, "data": {"count": 12, "tasks": [tasks[int(payload["page"])-1]]}}
        cursor, result = None, None
        for _ in range(5):
            with self.api.work_slice():
                result = self.api.list_tasks_slice(cursor, page_size=1)
            cursor = result["cursor"]
            if result["complete"]:
                break
            self.assertIsNotNone(cursor)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["items"]), 12)
        self.assertEqual(len(self.calls), 13)

    def test_changed_listing_never_claims_complete(self):
        tasks = [{"info_hash": f"{i:040x}"} for i in range(4)]
        self.handler = lambda path, payload: {"state": True, "count": 4, "tasks": [tasks[int(payload["page"])-1]]}
        with self.api.work_slice():
            partial = self.api.list_tasks_slice(page_size=1, max_pages=1)
        self.handler = lambda path, payload: {"state": True, "count": 3, "tasks": [tasks[1]]}
        with self.api.work_slice(), self.assertRaises(transfer.P115Error):
            self.api.list_tasks_slice(partial["cursor"], page_size=1)

    def test_incompatible_sdk_disables_only_cloud_constructor(self):
        with patch.object(transfer, "P115Client", SimpleNamespace(request=lambda x: None)):
            with self.assertRaises(transfer.P115Deferred) as raised:
                transfer.P115Transfer("UID=synthetic")
        self.assertEqual(raised.exception.reason, "capability")
        self.assertEqual(transfer.extract_hash(MAGNET), BTIH)

    def install_plus(self):
        FakePlus.instances = []
        plus = ModuleType("app.plugins.p115disk.p115_api")
        plus.P115Api = FakePlus
        schemas = ModuleType("app.schemas")
        schemas.FileItem = FakeItem
        self.stack.enter_context(patch.dict(sys.modules, {
            "app.plugins.p115disk.p115_api": plus, "app.schemas": schemas}))

    def test_plus_reuses_private_instance_and_never_runs_shared_fallback(self):
        self.install_plus()
        parents = {"7": "11", "8": "11"}
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 11 if payload["path"] == "/Staging" else 42}
            if path == "/files/get_info":
                fid = payload["file_id"]
                return {"state": True, "data": [{"cid": fid, "pid": parents[fid], "n": "Synthetic" + fid, "fc": "0"}]}
            if path == "/files/move":
                parents[payload["fid"]] = payload["pid"]
                return {"state": True}
            raise AssertionError("unexpected request")
        self.handler = handler
        with self.api.work_slice():
            self.assertEqual(self.api.move_via_p115disk("/Staging/Synthetic7", "/Target", "7"), (True, ""))
            self.assertEqual(self.api.get_file_info("7")["parent_id"], "42")
        with self.api.work_slice():
            self.assertEqual(self.api.move_via_p115disk("/Staging/Synthetic8", "/Target", "8"), (True, ""))
        self.assertEqual(len(FakePlus.instances), 1)
        FakePlus.instances[0].get_item_strict.assert_not_called()
        self.assertEqual(len([p for p, _, _ in self.calls if p == "/files/move"]), 2)
        self.assertNotIn("/Staging/Synthetic7", self.api._dir_cache)
        self.assertEqual(self.api._dir_cache["/Target/Synthetic7"], 7)

    def test_plus_cannot_hide_write_timeout_or_resubmit_through_fallback(self):
        self.install_plus()
        def handler(path, payload):
            if path == "/files/get_info":
                return {"state": True, "data": [{"cid": "7", "pid": "11", "n": "Synthetic", "fc": "0"}]}
            if path == "/files/getid":
                return {"state": True, "id": 11 if payload["path"] == "/Staging" else 42}
            return TimeoutError("synthetic lost move reply")
        self.handler = handler
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.move_via_p115disk("/Staging/Synthetic", "/Target", "7")
        self.assertTrue(raised.exception.uncertain)
        self.assertFalse(raised.exception.not_sent)
        FakePlus.instances[0].get_item_strict.assert_not_called()
        self.assertEqual(len([p for p, _, _ in self.calls if p == "/files/move"]), 1)
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred):
            self.api.move_via_p115disk("/Staging/Synthetic", "/Target", "7")
        self.assertEqual(len([p for p, _, _ in self.calls if p == "/files/move"]), 1)

    def test_same_name_different_exact_id_or_parent_never_moves(self):
        self.install_plus()
        self.handler = lambda path, payload: {"state": True, "data": [{"fid": "7", "cid": "99", "n": "Synthetic.mkv", "fc": "1"}]} if path == "/files/get_info" else {"state": True, "id": 11}
        with self.api.work_slice():
            success, message = self.api.move_via_p115disk("/Staging/Synthetic.mkv", "/Target", "7")
        self.assertFalse(success)
        self.assertIn("已不在", message)
        self.assertFalse(any(path == "/files/move" for path, _, _ in self.calls))

    def test_durable_intent_failure_prevents_actual_write(self):
        state = {"identity": transfer.hashlib.sha256(b"synthetic\0/Synthetic").hexdigest(),
                 "complete": True, "cid": 42, "items": [{"id": "7", "name": "Synthetic.mkv"}], "received": 0}
        with self.api.work_slice(), self.assertRaises(transfer.P115Error):
            self.api.receive_prepared("https://115.com/s/synthetic", "/Synthetic", state,
                before_submit=Mock(side_effect=RuntimeError("synthetic ledger unavailable")))
        self.assertFalse(state["uncertain"])
        self.assertEqual(len(self.calls), 0)

    def test_plus_slice_stop_is_not_sent_and_never_consumes_hidden_fallback(self):
        self.install_plus()
        self.handler = lambda path, payload: {"state": True, "data": [{"cid": "7", "pid": "11", "n": "Synthetic", "fc": "0"}]} if path == "/files/get_info" else {"state": True, "id": 11 if payload.get("path") == "/Staging" else 42}
        with self.api.work_slice(max_requests=3), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.move_via_p115disk("/Staging/Synthetic", "/Target", "7")
        self.assertTrue(raised.exception.not_sent)
        self.assertFalse(raised.exception.uncertain)
        self.assertEqual(len(self.calls), 3)
        FakePlus.instances[0].get_item_strict.assert_not_called()
        self.assertFalse(any(path == "/files/move" for path, _, _ in self.calls))

    def test_partial_original_manifest_stays_unknown_on_delete_during_scan(self):
        episodes = self.synthetic_episodes(401)
        self.handler = lambda path, payload: {"state": True, "data": {"count": len(episodes), "list": episodes[int(payload["offset"]):int(payload["offset"])+200]}}
        with self.api.work_slice():
            first = self.api.share_manifest_slice("https://115.com/s/synthetic", max_pages=1)
        self.assertFalse(first["complete"])
        episodes.pop(201)
        with self.api.work_slice():
            next_page = self.api.share_manifest_slice("https://115.com/s/synthetic", first["cursor"])
        self.assertFalse(next_page["complete"])
        self.assertIn("数量变化", next_page["error"])
        self.assertFalse(any(path == "/share/receive" for path, _, _ in self.calls))

    def test_manifest_excludes_sample_and_understands_double_episode(self):
        entries = [{"fid": "7", "n": "Synthetic.S01E01E02.mkv", "fc": "1"},
                   {"fid": "8", "n": "Synthetic.sample.mkv", "fc": "1"},
                   {"fid": "9", "n": "Synthetic.预告.mkv", "fc": "1"},
                   {"fid": "10", "n": "Synthetic.zip", "fc": "1"}]
        self.handler = lambda path, payload: {"state": True, "data": {"count": 4, "list": entries}}
        with self.api.work_slice():
            manifest = self.api.share_manifest_slice("https://115.com/s/synthetic")
        self.assertFalse(manifest["complete"])
        required = [item for item in manifest["items"] if item["required"]]
        self.assertEqual(len(required), 1)
        self.assertEqual(required[0]["episodes"], [(1, 1), (1, 2)])
        self.assertIn("压缩", manifest["error"])

    def test_disk_failure_after_lost_network_reply_still_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            self.api.attach_state(Path(directory) / "budget.json")
            real_replace = self.b._persist.__globals__["os"].replace
            replace_count = [0]
            def replace(source, target):
                replace_count[0] += 1
                if replace_count[0] > 1:
                    raise OSError("synthetic disk full after actual request")
                return real_replace(source, target)
            self.handler = lambda path, payload: TimeoutError("synthetic lost move reply")
            with patch.object(self.b._persist.__globals__["os"], "replace", side_effect=replace):
                with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
                    self.api.client.fs_move("7", pid=42)
            self.assertTrue(raised.exception.uncertain)
            self.assertFalse(raised.exception.not_sent)
            self.assertEqual(raised.exception.reason, "local_state")
            self.assertEqual(len(self.calls), 1)

    def test_duplicate_submit_resumes_a_budget_truncated_list_without_resubmitting(self):
        tasks = [{"info_hash": f"{i+1:040x}", "wp_path_id": "42", "percentDone": 1, "status": 1}
                 for i in range(4)]
        tasks[-1]["info_hash"] = BTIH
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 42}
            if "url[0]" in payload:
                return {"state": False, "error": "任务重复"}
            page = int(payload["page"])
            return {"state": True, "count": 4, "tasks": [tasks[page - 1]]}
        self.handler = handler
        # First slice: target lookup + add + one list page. The second page
        # would exceed this synthetic slice, so recovery must retain its cursor.
        with self.api.work_slice(max_requests=3), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.offline_add(MAGNET, "/Synthetic")
        deferred = raised.exception
        self.assertTrue(deferred.reconcile_only)
        self.assertFalse(deferred.uncertain)
        self.assertFalse(deferred.not_sent)
        self.assertTrue(deferred.state["duplicate"])
        self.assertTrue(deferred.state["recovery_pending"])
        self.assertEqual(deferred.state["recovery_cursor"]["page"], 2)
        with self.api.work_slice():
            recovered = self.api.recover_offline(deferred.state)
        self.assertTrue(recovered.recoverable)
        self.assertFalse(recovered.recovery_pending)
        self.assertEqual(recovered.task["info_hash"], BTIH)
        self.assertEqual(len([payload for _, payload, _ in self.calls if "url[0]" in payload]), 1)
        self.assertEqual([p["page"] for _, p, _ in self.calls if "page" in p], ["1", "2", "3", "4"])

    def test_duplicate_completed_file_lookup_defers_with_existing_identity(self):
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 42}
            if "url[0]" in payload:
                return {"state": False, "error": "任务重复"}
            if "page" in payload:
                return {"state": True, "count": 1, "tasks": [{"info_hash": BTIH,
                    "wp_path_id": "42", "percentDone": 100, "status": 1, "file_id": "7", "name": "Synthetic.mkv"}]}
            return {"state": True, "data": [{"fid": "7", "cid": "42", "n": "Synthetic.mkv", "fc": "1"}]}
        self.handler = handler
        with self.api.work_slice(max_requests=3), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(raised.exception.reconcile_only)
        self.assertEqual(raised.exception.state["file_id"], "7")
        with self.api.work_slice():
            recovered = self.api.recover_offline(raised.exception.state)
        self.assertTrue(recovered.recoverable)
        self.assertEqual(len([p for _, p, _ in self.calls if "url[0]" in p]), 1)

    def test_duplicate_query_outage_is_reconciliation_not_acquire_failure(self):
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 42}
            if "url[0]" in payload:
                return {"state": False, "error": "任务重复"}
            return TimeoutError("synthetic task list outage")
        self.handler = handler
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(raised.exception.reconcile_only)
        self.assertFalse(raised.exception.uncertain)
        self.assertFalse(raised.exception.not_sent)
        self.assertTrue(raised.exception.state["recovery_pending"])
        self.assertEqual(len([p for _, p, _ in self.calls if "url[0]" in p]), 1)

    def test_duplicate_file_evidence_outage_preserves_existing_task_identity(self):
        def handler(path, payload):
            if path == "/files/getid":
                return {"state": True, "id": 42}
            if "url[0]" in payload:
                return {"state": False, "error": "任务重复"}
            if "page" in payload:
                return {"state": True, "count": 1, "tasks": [{"info_hash": BTIH,
                    "wp_path_id": "42", "percentDone": 100, "status": 1, "file_id": "7", "name": "Synthetic.mkv"}]}
            return TimeoutError("synthetic fs_file outage")
        self.handler = handler
        with self.api.work_slice(), self.assertRaises(transfer.P115Deferred) as raised:
            self.api.offline_add(MAGNET, "/Synthetic")
        self.assertTrue(raised.exception.reconcile_only)
        self.assertEqual(raised.exception.state["file_id"], "7")
        self.assertTrue(raised.exception.state["recovery_pending"])
        self.assertFalse(raised.exception.uncertain)
        self.assertEqual(len([p for _, p, _ in self.calls if "url[0]" in p]), 1)


if __name__ == "__main__":
    unittest.main()
