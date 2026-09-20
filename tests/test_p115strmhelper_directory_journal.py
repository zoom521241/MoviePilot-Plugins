"""Directory restart persistence and monitor lifecycle regression tests."""

import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock


PLUGIN_ROOT = Path(
    os.environ.get(
        "P115STRMHELPER_SOURCE_ROOT",
        str(Path(__file__).resolve().parents[1] / "plugins.v2/p115strmhelper"),
    )
)


def load_journal_module():
    spec = importlib.util.spec_from_file_location(
        "directory_journal_test", PLUGIN_ROOT / "helper/life/directory_journal.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_function(path, name, namespace, class_name=None):
    """Load a real lifecycle function without MoviePilot runtime dependencies."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    body = tree.body
    if class_name:
        body = next(
            node.body
            for node in body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    function = next(
        node for node in body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class TestDirectoryTransferJournal(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_journal_module()

    def setUp(self):
        self.data = {}
        self.event = {
            "id": 100,
            "type": 18,
            "file_id": 10,
            "file_category": 0,
            "parent_id": 1,
            "file_name": "Series",
            "update_time": 500,
        }
        self.journal = self.new_journal()

    def new_journal(self):
        def save(data):
            self.data = deepcopy(data)

        return self.module.DirectoryTransferJournal(lambda: deepcopy(self.data), save)

    def test_restart_preserves_accepted_ids_and_completes(self):
        self.assertEqual(self.journal.begin(10, self.event, "/incoming/Series"), set())
        self.journal.record_accepted(10, 11)
        self.journal.record_accepted("10", "12")
        self.journal.pause(10)

        restarted = self.new_journal()
        entry = restarted.pending()[0]
        self.assertEqual(entry["folder_id"], "10")
        self.assertEqual(entry["state"], "interrupted")
        self.assertEqual(entry["accepted_ids"], ["11", "12"])
        self.assertEqual(
            restarted.begin(10, entry["event"], entry["path"]), {"11", "12"}
        )
        restarted.record_accepted(10, 12)
        self.assertEqual(restarted.pending()[0]["accepted_ids"], ["11", "12"])
        restarted.finish(10, complete=True)
        self.assertEqual(self.data, {})
        self.assertEqual(self.new_journal().pending(), [])

    def test_active_entry_is_recovered_after_process_exit(self):
        self.journal.begin(10, self.event, "/incoming/Series")
        self.journal.record_accepted(10, 11)
        self.assertEqual(self.new_journal().pending()[0]["accepted_ids"], ["11"])

    def test_new_event_or_path_does_not_inherit_accepted_files(self):
        for event, path in (
            ({**self.event, "id": 101}, "/incoming/Series"),
            (self.event, "/incoming/Renamed"),
        ):
            with self.subTest(event=event, path=path):
                self.journal.begin(10, self.event, "/incoming/Series")
                self.journal.record_accepted(10, 11)
                self.assertEqual(self.journal.begin(10, event, path), set())

    def test_exhausted_work_is_retained_without_automatic_retry(self):
        self.journal.begin(10, self.event, "/incoming/Series")
        self.journal.record_accepted(10, 11)
        self.journal.finish(10, complete=False)
        self.assertEqual(self.new_journal().pending(), [])
        self.assertEqual(self.data["10"]["state"], "needs_review")
        self.assertEqual(self.data["10"]["accepted_ids"], ["11"])

    def test_only_public_scalar_event_fields_are_saved(self):
        event = {
            **self.event,
            "cookies": "private",
            "headers": {"Authorization": "private"},
            "pick_code": "public-pickcode",
            "sha1": ["not-a-scalar"],
        }
        self.journal.begin(10, event, "/incoming/Series")
        expected = {**self.event, "pick_code": "public-pickcode"}
        self.assertEqual(self.data["10"]["event"], expected)
        event["file_name"] = "mutated"
        pending = self.journal.pending()
        pending[0]["event"]["file_name"] = "mutated-again"
        self.assertEqual(self.journal.pending()[0]["event"], expected)

    def test_concurrent_instances_do_not_overwrite_other_folders(self):
        start = Barrier(8)

        def update(folder_id):
            journal = self.new_journal()
            start.wait(timeout=5)
            journal.begin(folder_id, {**self.event, "file_id": folder_id}, "/incoming")
            for file_id in range(3):
                journal.record_accepted(folder_id, file_id)
            journal.pause(folder_id)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(update, range(8)))
        self.assertEqual(len(self.journal.pending()), 8)
        for entry in self.journal.pending():
            self.assertEqual(entry["accepted_ids"], ["0", "1", "2"])
            self.assertEqual(entry["state"], "interrupted")

    def test_invalid_stored_entries_are_not_resumed(self):
        self.data = {
            "bad": None,
            "bad-event": {"state": "active", "path": "/incoming", "event": []},
            "bad-state": {"state": "unknown", "path": "/incoming", "event": {}},
        }
        self.assertEqual(self.journal.pending(), [])


class TestDirectoryResumeLifecycle(TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.config.monitor_life_first_pull_mode = "latest"
        self.config.notify = False
        self.monitor = MagicMock()
        self.monitor.check_status.return_value = True
        self.stop_event = Event()
        self.worker = load_function(
            PLUGIN_ROOT / "service/life/__init__.py",
            "monitor_life_thread_worker",
            {
                "configer": self.config,
                "logger": MagicMock(),
                "Event": Event,
                "MonitorLife": object,
                "time": lambda: 1000,
            },
        )

    def test_latest_resumes_pending_directory_before_polling(self):
        calls = []
        self.monitor.resume_directory_transfers.side_effect = lambda event: calls.append(
            ("resume", event)
        )

        def pull(**kwargs):
            calls.append(("pull", kwargs))
            self.stop_event.set()
            return 1010, 40

        self.monitor.once_pull.side_effect = pull
        self.worker(self.monitor, self.stop_event)
        self.assertEqual(
            calls,
            [("resume", self.stop_event), ("pull", {"from_time": 1000, "from_id": 0})],
        )
        self.config.save_plugin_data.assert_called_once_with(
            "monitor_life_strm_files", {"from_time": 1010, "from_id": 40}
        )

    def test_stop_during_resume_skips_polling_and_saves_cursor(self):
        self.monitor.resume_directory_transfers.side_effect = lambda event: event.set()
        self.worker(self.monitor, self.stop_event)
        self.monitor.once_pull.assert_not_called()
        self.config.save_plugin_data.assert_called_once_with(
            "monitor_life_strm_files", {"from_time": 1000, "from_id": 0}
        )

    def test_stop_after_poll_exception_preserves_last_completed_cursor(self):
        self.config.monitor_life_first_pull_mode = "last"
        self.config.get_plugin_data.return_value = {"from_time": 800, "from_id": 20}

        def pull(**_kwargs):
            self.stop_event.set()
            raise RuntimeError("interrupted request")

        self.monitor.once_pull.side_effect = pull
        self.worker(self.monitor, self.stop_event)
        self.config.save_plugin_data.assert_called_once_with(
            "monitor_life_strm_files", {"from_time": 800, "from_id": 20}
        )

    def test_stop_during_error_backoff_still_saves_cursor(self):
        self.monitor.once_pull.side_effect = RuntimeError("request failed")
        stop_event = MagicMock(spec=Event)
        stop_event.is_set.return_value = False
        stop_event.wait.return_value = True
        self.worker(self.monitor, stop_event)
        stop_event.wait.assert_called_once_with(timeout=30)
        self.config.save_plugin_data.assert_called_once_with(
            "monitor_life_strm_files", {"from_time": 1000, "from_id": 0}
        )

    def test_failed_status_check_does_not_overwrite_saved_cursor(self):
        self.monitor.check_status.return_value = False
        self.worker(self.monitor, self.stop_event)
        self.monitor.resume_directory_transfers.assert_not_called()
        self.config.save_plugin_data.assert_not_called()

    def test_preexisting_stop_does_not_resume_work(self):
        self.stop_event.set()
        self.worker(self.monitor, self.stop_event)
        self.monitor.resume_directory_transfers.assert_not_called()
        self.monitor.once_pull.assert_not_called()

    def test_thread_that_outlives_join_retains_stop_signal_and_reference(self):
        stop = load_function(
            PLUGIN_ROOT / "service/__init__.py",
            "_stop_monitor_life_internal",
            {"logger": MagicMock()},
            class_name="ServiceHelper",
        )
        thread = MagicMock()
        thread.is_alive.return_value = True
        service = SimpleNamespace(
            monitor_life_thread=thread, monitor_stop_event=self.stop_event
        )
        stop(service)
        self.assertTrue(self.stop_event.is_set())
        self.assertIs(service.monitor_life_thread, thread)
        self.assertIs(service.monitor_stop_event, self.stop_event)
        thread.join.assert_called_once_with(timeout=25)
