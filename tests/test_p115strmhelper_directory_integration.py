"""Offline integration coverage for life-event directory transfers.

The production MonitorLife class is loaded intact with AST to avoid importing
MoviePilot, starting timers, or contacting 115.  Directory scan/journal helpers
are loaded from their real source files; only host services are replaced.
"""

import ast
from copy import deepcopy
import importlib.util
import os
from pathlib import Path, PurePosixPath
import sys
from threading import Event, RLock, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError


PLUGIN_ROOT = Path(os.environ.get(
    "P115STRMHELPER_SOURCE_ROOT",
    str(Path(__file__).resolve().parents[1] / "plugins.v2/p115strmhelper"),
))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class StopEvent:
    """Event semantics with deterministic, nonblocking waits."""

    def __init__(self, clock):
        self.clock = clock
        self.stopped = False

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, timeout=None):
        if not self.stopped:
            self.clock.now += timeout or 0
        return self.stopped


class HostConfig:
    def __init__(self):
        self.saved = {}
        self.pan_transfer_enabled = True
        self.pan_transfer_paths = "/inbox"
        self.pan_transfer_unrecognized_path = ""
        self.pan_transfer_clouddrive2_config = SimpleNamespace(enabled=False)
        self.storage_module = "115网盘Plus"
        self.monitor_life_enabled = False
        self.monitor_life_paths = []
        self.monitor_life_event_modes = []
        self.user_rmt_mediaext = "mkv,mp4"

    def get_config(self, key):
        return {"user_rmt_mediaext": "mkv,mp4",
                "user_download_mediaext": "srt"}.get(key)

    def get_ios_ua_app(self, **kwargs):
        return {}

    def get_plugin_data(self, key, **kwargs):
        return deepcopy(self.saved.get(key))

    def save_plugin_data(self, key, value, **kwargs):
        self.saved[key] = deepcopy(value)


def load_helper(name):
    module_name = f"directory_integration_{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_ROOT / "helper/life" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_monitor(namespace):
    source = PLUGIN_ROOT / "helper/life/client.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.ImportFrom) and node.level == 1
                and node.module.startswith("directory_")):
            helper = load_helper(node.module)
            for alias in node.names:
                namespace[alias.asname or alias.name] = getattr(helper, alias.name)
    class_node = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == "MonitorLife")
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__",
                       names=[ast.alias(name="annotations")], level=0),
        class_node,
    ], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(source), "exec"), namespace)
    return namespace["MonitorLife"]


class DirectoryTransferIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.stop_event = StopEvent(self.clock)
        self.config = HostConfig()
        self.chain = Mock()
        self.chain.do_transfer.return_value = (True, "queued")
        self.database = Mock()
        self.logger = Mock()
        self.cache = SimpleNamespace(delete_pan_transfer_list=[],
                                     creata_pan_transfer_list=[], file_item_dict={})
        self.iterator = Mock(return_value=iter(()))
        self.get_path = Mock(return_value="/inbox/season")
        path_utils = SimpleNamespace(
            has_prefix=lambda path, prefix: PurePosixPath(Path(path).as_posix()).is_relative_to(
                PurePosixPath(Path(prefix).as_posix())),
            get_run_transfer_path=lambda *args, **kwargs: True,
        )
        self.namespace = {
            "Path": Path, "FileItem": SimpleNamespace,
            "logger": self.logger, "configer": self.config,
            "TransferChain": Mock(return_value=self.chain),
            "FileDbHelper": Mock(return_value=self.database),
            "LifeEventDbHelper": Mock(return_value=Mock()),
            "pantransfercacher": self.cache,
            "PathUtils": path_utils,
            "settings": SimpleNamespace(RMT_AUDIOEXT=[".flac"], RMT_SUBEXT=[".srt"]),
            "iter_files_with_path": self.iterator,
            "check_iter_path_data": Mock(),
            "FileItemKeyMiss": type("FileItemKeyMiss", (Exception,), {}),
            "sentry_manager": SimpleNamespace(capture_all_class_exceptions=lambda cls: cls),
            "HTTPError": HTTPError, "P115OSError": OSError,
            "BEHAVIOR_TYPE_TO_NAME": {}, "sleep": Mock(),
            "RLock": RLock,
            "monotonic": self.clock.monotonic, "get_path": self.get_path,
        }
        self.monitor_class = load_monitor(self.namespace)
        real_collector = self.namespace["collect_directory_snapshot"]
        self.snapshots = []

        def collect(scan, **kwargs):
            snapshot = real_collector(scan, monotonic=self.clock.monotonic, **kwargs)
            self.snapshots.append(snapshot)
            return snapshot

        self.collector = Mock(side_effect=collect)
        self.namespace["collect_directory_snapshot"] = self.collector
        self.monitor = self.new_monitor()
        self.event = {
            "id": 101, "update_time": 201, "type": 2,
            "file_category": 0, "file_id": "50", "parent_id": "1",
            "file_name": "season", "file_size": 0,
            "sha1": "", "pick_code": "",
        }
        self.directory = Path("/inbox/season")

    def new_monitor(self):
        monitor = self.monitor_class.__new__(self.monitor_class)
        monitor._client = object()
        monitor.stop_event = self.stop_event
        monitor.rmt_mediaext = [".mkv", ".mp4"]
        monitor.rmt_mediaext_set = set(monitor.rmt_mediaext)
        monitor.download_mediaext_set = {".srt"}
        monitor._resumed_directory_events = set()
        monitor._get_path_by_cid = Mock(return_value=Path("/inbox"))
        return monitor

    def file(self, file_id, extension="mkv", parent="50"):
        return {"id": file_id, "parent_id": parent,
                "path": f"/inbox/season/episode-{file_id}.{extension}",
                "name": f"episode-{file_id}.{extension}", "size": 100,
                "sha1": f"sha1-{file_id}", "pickcode": f"pick-{file_id}", "ctime": 200}

    def transfer(self):
        return self.monitor.media_transfer(self.event, self.directory, [".mkv", ".mp4"])

    def prepare_pull(self, events=None):
        self.monitor._wait_for_transfer_complete = Mock(return_value=False)
        self.monitor._get_life_event_app = Mock(return_value="ios")
        self.monitor._pull_life_events = Mock(return_value=events or [self.event])
        self.monitor._reset_ios_405_count = Mock()

    def repeat_listing(self, files):
        self.iterator.side_effect = lambda *args, **kwargs: iter(deepcopy(files))

    def saved_entry(self):
        return self.config.saved["pending_directory_transfers"]["50"]

    def test_directory_collects_full_52_file_snapshot_before_submitting_once(self):
        files = [self.file(file_id) for file_id in range(1, 53)]
        passes = [files[:30], files + [dict(files[0], id="1")], files, files]

        def listing(*args, **kwargs):
            self.chain.do_transfer.assert_not_called()
            self.assertEqual(self.saved_entry()["state"], "active")
            return iter(deepcopy(passes.pop(0)))

        def submit(*, fileitem):
            self.assertEqual(len(self.snapshots), 1)
            self.assertTrue(self.snapshots[0].stable)
            self.assertEqual(len(self.snapshots[0].items), 52)
            return True, "queued"

        self.iterator.side_effect = listing
        self.chain.do_transfer.side_effect = submit
        self.assertTrue(self.transfer())
        self.collector.assert_called_once()
        self.assertEqual(self.iterator.call_count, 4)
        submitted = [call.kwargs["fileitem"].fileid
                     for call in self.chain.do_transfer.call_args_list]
        self.assertEqual(len(submitted), 52)
        self.assertEqual(set(submitted), {str(file_id) for file_id in range(1, 53)})
        self.assertEqual(self.config.saved["pending_directory_transfers"], {})
        self.database.remove_by_id_batch.assert_called_once_with(50, False)

    def test_directory_includes_audio_and_subtitles_and_skips_nonmedia(self):
        files = [self.file(1), self.file(2, "FLAC"), self.file(3, "srt"),
                 self.file(4, "nfo"), dict(self.file(5), is_dir=True)]
        self.repeat_listing(files)
        self.assertTrue(self.monitor.media_transfer(
            self.event, self.directory, [".mkv", ".srt"]))
        submitted = [call.kwargs["fileitem"].fileid
                     for call in self.chain.do_transfer.call_args_list]
        self.assertEqual(submitted, ["1", "2", "3"])
        kwargs = self.iterator.call_args.kwargs
        self.assertTrue(kwargs["raise_for_changed_count"])
        self.assertFalse(kwargs["use_media_api"])
        self.assertTrue(kwargs["with_ancestors"])

    def test_rejected_and_exception_submissions_are_not_reported_as_accepted(self):
        self.repeat_listing([self.file(file_id) for file_id in range(1, 5)])
        self.chain.do_transfer.side_effect = [
            (True, "queued"), (False, "rejected"), RuntimeError("submission failed"), None,
        ]
        self.assertFalse(self.transfer())
        self.assertEqual(self.chain.do_transfer.call_count, 4)
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])
        self.assertEqual(self.saved_entry()["state"], "needs_review")
        accepted_logs = [call for call in self.logger.info.call_args_list
                         if "MP 已受理" in call.args[0]]
        self.assertEqual(len(accepted_logs), 1)
        self.assertEqual(Path(accepted_logs[0].args[1]).name, "episode-1.mkv")
        self.assertEqual(self.cache.creata_pan_transfer_list, ["1"])
        self.logger.warning.assert_called()
        self.logger.error.assert_called()
        self.assertEqual(self.monitor._get_directory_transfer_journal().pending(), [])

    def test_invalid_directory_entries_cannot_make_a_scan_look_complete(self):
        invalid = [dict(self.file(2), path=""), dict(self.file(3), pickcode=None),
                   dict(self.file(4), path="/elsewhere/episode-4.mkv")]
        self.repeat_listing([self.file(1)] + invalid)
        self.assertFalse(self.transfer())
        self.assertEqual(self.iterator.call_count, 6)
        self.assertEqual(self.snapshots[0].errors, 6)
        self.chain.do_transfer.assert_called_once()
        self.assertEqual(self.chain.do_transfer.call_args.kwargs["fileitem"].fileid, "1")
        self.assertEqual(self.saved_entry()["state"], "needs_review")

    def test_stop_during_scan_keeps_directory_pending_without_submissions(self):
        def interrupted_listing(*args, **kwargs):
            yield self.file(1)
            self.stop_event.set()
            yield self.file(2)

        self.iterator.side_effect = interrupted_listing
        self.assertFalse(self.transfer())
        self.chain.do_transfer.assert_not_called()
        self.assertEqual(self.saved_entry()["state"], "interrupted")
        self.assertEqual(self.saved_entry()["accepted_ids"], [])
        pending = self.monitor._get_directory_transfer_journal().pending()
        self.assertEqual([entry["folder_id"] for entry in pending], ["50"])

    def test_filtered_only_listing_checks_cancellation_and_closes_iterator(self):
        seen = []
        closed = []

        def filtered_listing(*args, **kwargs):
            try:
                for file_id in range(1, 6):
                    seen.append(file_id)
                    if file_id == 2:
                        self.stop_event.set()
                    yield self.file(file_id, "nfo")
            finally:
                closed.append(True)

        self.iterator.side_effect = filtered_listing
        self.assertFalse(self.transfer())
        self.assertEqual(seen, [1, 2])
        self.assertEqual(closed, [True])
        self.iterator.assert_called_once()
        self.chain.do_transfer.assert_not_called()
        self.assertTrue(self.snapshots[0].stopped)
        self.assertEqual(self.saved_entry()["state"], "interrupted")

    def test_filtered_only_listing_honors_deadline_and_closes_iterator(self):
        seen = []
        closed = []

        def filtered_listing(*args, **kwargs):
            try:
                for file_id in range(1, 6):
                    seen.append(file_id)
                    self.clock.now += 50
                    yield self.file(file_id, "nfo")
            finally:
                closed.append(True)

        self.iterator.side_effect = filtered_listing
        self.assertFalse(self.transfer())
        self.assertEqual(seen, [1, 2, 3])
        self.assertEqual(closed, [True])
        self.iterator.assert_called_once()
        self.chain.do_transfer.assert_not_called()
        self.assertEqual(self.snapshots[0].reason, "max_elapsed")
        self.assertEqual(self.saved_entry()["state"], "needs_review")

    def test_stopped_transfer_waiting_for_directory_lock_preserves_checkpoint(self):
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.record_accepted("50", "1")
        journal.pause("50")
        lock = RLock()
        attempted = Event()
        finished = Event()
        outcomes = []

        class ObservedLock:
            def __enter__(self):
                attempted.set()
                lock.acquire()

            def __exit__(self, *args):
                lock.release()

        self.monitor_class._directory_transfer_lock = ObservedLock()

        def worker():
            try:
                outcomes.append(self.transfer())
            except BaseException as error:
                outcomes.append(error)
            finally:
                finished.set()

        with lock:
            thread = Thread(target=worker, daemon=True)
            thread.start()
            self.assertTrue(attempted.wait(timeout=2), "worker never attempted directory lock")
            self.assertFalse(finished.is_set())
            self.collector.assert_not_called()
            self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])
            self.stop_event.set()
        self.assertTrue(finished.wait(timeout=2), "stopped worker failed to exit")
        thread.join(timeout=2)
        self.assertEqual(outcomes, [False])
        self.iterator.assert_not_called()
        self.chain.do_transfer.assert_not_called()
        self.assertEqual(self.saved_entry()["state"], "interrupted")
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])

    def test_stop_during_submission_resumes_without_repeating_accepted_ids(self):
        self.repeat_listing([self.file(file_id) for file_id in range(1, 5)])

        def stop_after_two(*, fileitem):
            if fileitem.fileid == "2":
                self.stop_event.set()
            return True, "queued"

        self.chain.do_transfer.side_effect = stop_after_two
        self.assertFalse(self.transfer())
        self.assertEqual(self.saved_entry()["state"], "interrupted")
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1", "2"])

        self.stop_event = StopEvent(self.clock)
        self.monitor = self.new_monitor()
        self.chain.do_transfer.side_effect = None
        with patch.object(self.monitor, "media_transfer", wraps=self.monitor.media_transfer) as transfer:
            self.monitor.resume_directory_transfers(self.stop_event)
        transfer.assert_called_once_with(self.event, self.directory, [".mkv", ".mp4"])
        submitted = [call.kwargs["fileitem"].fileid
                     for call in self.chain.do_transfer.call_args_list]
        self.assertEqual(submitted, ["1", "2", "3", "4"])
        self.assertEqual(self.config.saved["pending_directory_transfers"], {})
        self.monitor._get_path_by_cid.assert_not_called()
        self.get_path.assert_called_once_with(
            client=self.monitor._client, attr=50, root_id=None,
            ensure_file=False, refresh=True, timeout=20, app="android",
        )

    def test_completed_resume_is_not_resubmitted_when_life_cursor_replays_event(self):
        self.repeat_listing([self.file(1), self.file(2)])
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.record_accepted("50", "1")
        journal.pause("50")
        self.monitor.resume_directory_transfers(self.stop_event)
        self.assertEqual(self.config.saved["pending_directory_transfers"], {})
        self.chain.do_transfer.assert_called_once()
        self.assertEqual(self.chain.do_transfer.call_args.kwargs["fileitem"].fileid, "2")

        self.monitor._get_path_by_cid.return_value = Path("/inbox")
        self.prepare_pull()
        self.assertEqual(self.monitor.once_pull(100, 90), (201, 101))
        self.assertEqual(self.monitor.once_pull(201, 101), (201, 101))
        self.chain.do_transfer.assert_called_once()
        self.collector.assert_called_once()

    def test_incomplete_resume_is_not_retried_when_life_cursor_replays_event(self):
        self.repeat_listing([self.file(1), dict(self.file(2), path="")])
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.pause("50")
        self.monitor.resume_directory_transfers(self.stop_event)
        self.assertEqual(self.saved_entry()["state"], "needs_review")
        self.chain.do_transfer.assert_called_once()

        self.monitor._get_path_by_cid.return_value = Path("/inbox")
        self.prepare_pull()
        self.assertEqual(self.monitor.once_pull(100, 90), (201, 101))
        self.chain.do_transfer.assert_called_once()
        self.collector.assert_called_once()

    def test_stop_during_fresh_path_resolution_preserves_pending_checkpoint(self):
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.record_accepted("50", "1")
        journal.pause("50")
        original_event = self.stop_event

        def stopped_lookup(**kwargs):
            original_event.set()
            self.monitor.stop_event = StopEvent(self.clock)
            return None

        self.get_path.side_effect = stopped_lookup
        with patch.object(self.monitor, "media_transfer", wraps=self.monitor.media_transfer) as transfer:
            self.monitor.resume_directory_transfers(original_event)
        transfer.assert_not_called()
        self.monitor._get_path_by_cid.assert_not_called()
        self.get_path.assert_called_once()
        self.collector.assert_not_called()
        self.chain.do_transfer.assert_not_called()
        self.assertEqual(self.saved_entry()["state"], "interrupted")
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])
        self.assertEqual(self.monitor._resumed_directory_events, set())
        self.assertFalse(self.monitor.stop_event.is_set())

    def test_resume_rejects_fresh_path_mismatch_despite_matching_cached_path(self):
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.pause("50")
        self.monitor._get_path_by_cid.return_value = self.directory
        self.get_path.return_value = "/moved/season"
        self.monitor.resume_directory_transfers(self.stop_event)
        self.get_path.assert_called_once()
        self.monitor._get_path_by_cid.assert_not_called()
        self.collector.assert_not_called()
        self.chain.do_transfer.assert_not_called()
        self.assertEqual(self.saved_entry()["state"], "needs_review")

    def test_cd2_backend_change_keeps_review_record_without_replaying_event(self):
        journal = self.monitor._get_directory_transfer_journal()
        journal.begin("50", self.event, self.directory.as_posix())
        journal.record_accepted("50", "1")
        journal.pause("50")
        self.config.pan_transfer_clouddrive2_config.enabled = True
        self.monitor._media_transfer_folder_cd2 = Mock()

        self.monitor.resume_directory_transfers(self.stop_event)
        self.assertEqual(self.saved_entry()["state"], "needs_review")
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])
        self.get_path.assert_not_called()
        self.prepare_pull()
        self.assertEqual(self.monitor.once_pull(100, 90), (201, 101))
        self.monitor._media_transfer_folder_cd2.assert_not_called()
        self.collector.assert_not_called()
        self.chain.do_transfer.assert_not_called()

    def test_once_pull_cancelled_directory_preserves_cursor_and_stops_batch(self):
        self.repeat_listing([self.file(1), self.file(2)])
        later = dict(self.event, id=102, update_time=202, type=24)
        self.prepare_pull([later, self.event])
        self.monitor.rename = Mock()

        def stop_on_submission(*, fileitem):
            self.stop_event.set()
            return True, "queued"

        self.chain.do_transfer.side_effect = stop_on_submission
        self.assertEqual(self.monitor.once_pull(100, 90), (100, 90))
        self.chain.do_transfer.assert_called_once()
        self.monitor.rename.assert_not_called()
        self.assertEqual(self.saved_entry()["state"], "interrupted")

    def test_once_pull_keeps_original_stop_event_if_monitor_event_is_replaced(self):
        self.repeat_listing([self.file(1), self.file(2)])
        self.prepare_pull()
        original_event = self.stop_event

        def replace_event_during_submission(*, fileitem):
            original_event.set()
            self.monitor.stop_event = StopEvent(self.clock)
            return True, "queued"

        self.chain.do_transfer.side_effect = replace_event_during_submission
        self.assertEqual(self.monitor.once_pull(100, 90), (100, 90))
        self.chain.do_transfer.assert_called_once()
        self.assertFalse(self.monitor.stop_event.is_set())
        self.assertEqual(self.saved_entry()["accepted_ids"], ["1"])

    def test_once_pull_completed_and_ignored_events_advance_cursor(self):
        self.repeat_listing([self.file(1)])
        ignored = dict(self.event, id=102, update_time=202, type=8)
        self.prepare_pull([ignored, self.event])
        self.assertEqual(self.monitor.once_pull(100, 90), (202, 102))
        self.chain.do_transfer.assert_called_once()

    def test_once_pull_skipped_new_directory_advances_cursor(self):
        event = dict(self.event, type=17)
        self.prepare_pull([event])
        self.monitor._get_path_by_cid.return_value = None
        self.assertEqual(self.monitor.once_pull(100, 90), (201, 101))
        self.chain.do_transfer.assert_not_called()

    def test_single_file_keeps_native_submission_and_metadata(self):
        event = dict(self.event, file_category=1, file_id="51", file_size=123,
                     sha1="single-sha", pick_code="single-pick", file_name="single.mkv")
        self.monitor.media_transfer(event, Path("/inbox/single.mkv"), [".mkv"])
        self.chain.do_transfer.assert_called_once()
        fileitem = self.chain.do_transfer.call_args.kwargs["fileitem"]
        self.assertEqual(fileitem.fileid, "51")
        self.assertEqual(fileitem.path, "/inbox/single.mkv")
        self.assertEqual(fileitem.pickcode, "single-pick")
        self.assertEqual(fileitem.size, 123)
        self.database.remove_by_id.assert_called_once_with("file", "51")
        self.iterator.assert_not_called()
        self.assertEqual(self.config.saved, {})


if __name__ == "__main__":
    unittest.main()
