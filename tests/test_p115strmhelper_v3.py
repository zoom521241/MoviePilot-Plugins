"""Offline regressions for V3 transfer ownership and stopping legacy batches.

Run with ``python -m unittest discover -s tests -p test_p115strmhelper_v3.py``.
P115STRMHELPER_SOURCE_ROOT may point to another plugin checkout for comparison.
Production class bodies are loaded intact through AST; MoviePilot imports,
locks, and timers are mocked, so these tests never contact a server or wait.
"""

import ast
from functools import wraps
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch


PLUGIN_ROOT = Path(os.environ.get(
    "P115STRMHELPER_SOURCE_ROOT",
    str(Path(__file__).resolve().parents[1] / "plugins.v2/p115strmhelper"),
))


def load_class(relative_path, class_name, namespace):
    """Load the real class without executing plugin initialization/imports."""
    source_path = PLUGIN_ROOT / relative_path
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    class_node = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == class_name)
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__",
                       names=[ast.alias(name="annotations")], level=0),
        class_node,
    ], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(source_path), "exec"), namespace)
    return namespace[class_name]


class TransferChainCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.original = Mock(name="native_handle_transfer", return_value=(True, "native"))
        self.host = type("TransferChain", (), {
            "_TransferChain__handle_transfer": self.original,
        })
        modules = {name: ModuleType(name) for name in
                   ("app", "app.chain", "app.chain.transfer")}
        modules["app"].chain = modules["app.chain"]
        modules["app.chain"].transfer = modules["app.chain.transfer"]
        modules["app.chain.transfer"].TransferChain = self.host
        module_patch = patch.dict(sys.modules, modules)
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.patcher = load_class("patch/transfer_chain.py", "TransferChainPatcher", {
            "Lock": MagicMock, "logger": Mock(), "wraps": wraps,
        })
        self.manager = Mock(name="task_manager")
        self.handler = Mock(name="transfer_handler")

    def enable(self):
        self.patcher.enable(self.manager, self.handler, "115网盘Plus")

    def assert_native_chain_preserved(self):
        self.enable()
        self.assertIs(self.host._TransferChain__handle_transfer, self.original)
        self.assertFalse(self.patcher._enabled)
        self.assertIsNone(self.patcher._original_handle_transfer)
        self.assertIsNone(self.patcher._task_manager)
        self.assertIsNone(self.patcher._handler)
        self.assertEqual(self.patcher._storage_module, "")
        self.manager.add_task.assert_not_called()
        self.patcher.disable()
        self.assertIs(self.host._TransferChain__handle_transfer, self.original)

    def test_v3_finish_job_marker_preserves_native_settlement(self):
        self.host._TransferChain__finish_job_execution = Mock()
        self.assert_native_chain_preserved()

    def test_v3_legacy_settlement_marker_also_preserves_native_chain(self):
        self.host._TransferChain__settle_legacy_transfer_result = Mock()
        self.assert_native_chain_preserved()

    def test_v3_repeated_enable_never_wraps_native_handler(self):
        self.host._TransferChain__finish_job_execution = Mock()
        self.assert_native_chain_preserved()
        self.assert_native_chain_preserved()

    def test_v2_still_installs_dispatches_and_restores_legacy_patch(self):
        dispatch = Mock(return_value=(True, "legacy batch"))
        self.patcher._patched_handle_transfer = dispatch
        self.enable()
        installed = self.host._TransferChain__handle_transfer
        self.assertIsNot(installed, self.original)
        self.assertTrue(self.patcher._enabled)
        self.assertIs(self.patcher._original_handle_transfer, self.original)
        self.assertIs(self.patcher._task_manager, self.manager)
        self.assertIs(self.patcher._handler, self.handler)

        host_instance = self.host()
        task = object()
        callback = Mock()
        self.assertEqual(installed(host_instance, task, callback), (True, "legacy batch"))
        dispatch.assert_called_once_with(host_instance, task, callback)
        self.original.assert_not_called()

        self.enable()
        self.assertIs(self.host._TransferChain__handle_transfer, installed)
        self.patcher.disable()
        self.assertIs(self.host._TransferChain__handle_transfer, self.original)
        self.assertFalse(self.patcher._enabled)
        self.assertIsNone(self.patcher._task_manager)


class TransferTaskShutdownTests(unittest.TestCase):
    def setUp(self):
        self.timer_factory = Mock(side_effect=lambda **kwargs: Mock())
        manager_class = load_class("helper/transfer/task.py", "TransferTaskManager", {
            "Lock": MagicMock,
            "Timer": self.timer_factory,
            "logger": Mock(),
            "uuid": SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="test-batch-id")),
        })
        self.callback = Mock()
        self.manager = manager_class(batch_delay=10, batch_max_size=100,
                                     batch_callback=self.callback)

    @staticmethod
    def task(name):
        return SimpleNamespace(fileitem=SimpleNamespace(name=name),
                               target_path=f"/library/{name}", transfer_batch_id=None)

    def test_shutdown_discards_pending_tasks_and_never_flushes(self):
        self.manager.add_task(self.task("first.mkv"))
        timer = self.manager._timer
        timer.start.assert_called_once()
        self.manager.flush = Mock()
        self.manager.shutdown()
        self.assertTrue(self.manager._stopped)
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.assertIsNone(self.manager._timer)
        timer.cancel.assert_called_once()
        self.manager.flush.assert_not_called()
        self.callback.assert_not_called()

    def test_add_task_after_shutdown_creates_no_timer_or_batch(self):
        self.manager.shutdown()
        self.manager.add_task(self.task("late.mkv"))
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.timer_factory.assert_not_called()
        self.callback.assert_not_called()

    def test_cancelled_timer_callback_after_shutdown_cannot_run_batch(self):
        self.manager.add_task(self.task("cancelled.mkv"))
        delayed_callback = self.timer_factory.call_args.kwargs["function"]
        self.manager.shutdown()
        delayed_callback()
        self.manager.flush()
        self.callback.assert_not_called()
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.assertFalse(self.manager._processing)

    def test_shutdown_during_active_callback_discards_next_batch(self):
        first = self.task("active.mkv")
        queued = self.task("queued.mkv")
        late = self.task("late.mkv")

        def stop_during_callback(tasks):
            self.assertEqual(tasks, [first])
            self.manager.add_task(queued)
            pending_timer = self.manager._timer
            self.manager.shutdown()
            pending_timer.cancel.assert_called_once()
            self.manager.add_task(late)

        self.callback.side_effect = stop_during_callback
        self.manager.add_task(first)
        self.manager._trigger_batch_process()
        self.callback.assert_called_once_with([first])
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.assertFalse(self.manager._processing)
        self.assertTrue(self.manager._stopped)
        self.assertIsNone(queued.transfer_batch_id)
        self.assertIsNone(late.transfer_batch_id)

    def test_active_callback_error_after_shutdown_does_not_restart_queue(self):
        first = self.task("active.mkv")

        def fail_after_stop(tasks):
            self.manager.add_task(self.task("queued.mkv"))
            self.manager.shutdown()
            raise RuntimeError("simulated in-flight failure")

        self.callback.side_effect = fail_after_stop
        self.manager.add_task(first)
        self.manager._trigger_batch_process()
        self.callback.assert_called_once_with([first])
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.assertFalse(self.manager._processing)

    def test_shutdown_is_idempotent(self):
        self.manager.add_task(self.task("pending.mkv"))
        timer = self.manager._timer
        self.manager.shutdown()
        self.manager.shutdown()
        timer.cancel.assert_called_once()
        self.callback.assert_not_called()
        self.assertEqual(self.manager.get_pending_count(), 0)

    def test_live_queue_still_processes_its_scheduled_batch(self):
        task = self.task("normal.mkv")
        self.manager.add_task(task)
        delayed_callback = self.timer_factory.call_args.kwargs["function"]
        delayed_callback()
        self.callback.assert_called_once_with([task])
        self.assertEqual(task.transfer_batch_id, "test-batch-id")
        self.assertEqual(self.manager.get_pending_count(), 0)
        self.assertFalse(self.manager._processing)


if __name__ == "__main__":
    unittest.main()
