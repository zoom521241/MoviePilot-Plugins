"""Isolated V3 behavior regressions; no MP installation or server access needed."""
import ast
import importlib.util
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit, urlunsplit, unquote_plus


ROOT = Path(__file__).resolve().parents[1] / 'plugins.v2/mediacovergenerator'
spec = importlib.util.spec_from_file_location('cover_worker', ROOT / 'utils/event_worker.py')
worker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_module)
CoverEventWorker = worker_module.CoverEventWorker

METHODS = {
    '__init__', 'init_plugin', 'stop_task', 'stop_service', 'update_library_cover',
    'update_library_cover_webhook', '__queue_cover_event', '__process_cover_events',
    '__begin_update', '__resolve_cover_library', '__update_library_cover_item',
    '__update_all_libraries', '__primary_fallback_url', '__download_image',
    '__set_library_image', '__path_is_under',
}
tree = ast.parse((ROOT / '__init__.py').read_text(encoding='utf-8'))
plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef))
plugin.bases = []
plugin.body = [node for node in plugin.body if isinstance(node, ast.FunctionDef) and node.name in METHODS]
for method in plugin.body:
    method.decorator_list = [decorator for decorator in method.decorator_list
                             if isinstance(decorator, ast.Name) and decorator.id == 'staticmethod']
module = ast.fix_missing_locations(ast.Module(body=[plugin], type_ignores=[]))
namespace = dict(threading=threading, time=time, CoverEventWorker=CoverEventWorker,
                 logger=Mock(), Event=object, os=os, re=re, urlsplit=urlsplit,
                 urlunsplit=urlunsplit, unquote_plus=unquote_plus)
exec(compile(module, str(ROOT / '__init__.py'), 'exec'), namespace)
Plugin = namespace['MediaCoverGenerator']


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for background task')


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.plugin = Plugin()
        p = self.plugin
        p._enabled = True
        p._transfer_monitor = True
        p._delay = 0
        p._scheduler = None
        p._include_libraries = []
        p._cover_style = 'static_1'
        p._monitor_sort = ''
        p._covers_path = self.temp.name
        p._save_recent_covers = False
        p._servers = {'Emby': SimpleNamespace(name='Emby', type='emby', instance=Mock())}
        p.mschain = Mock()
        p.mschain.media_exists.return_value = SimpleNamespace(server='Emby', itemid='item')
        p.mschain.iteminfo.return_value = SimpleNamespace(library='library', path='/media/test.mkv')
        p._MediaCoverGenerator__get_server_libraries = Mock(return_value=[
            {'Id': 'library', 'Name': 'TV', 'Locations': ['/media']},
        ])
        p._MediaCoverGenerator__get_fonts = Mock()
        p._MediaCoverGenerator__update_library = Mock(return_value=True)
        p._MediaCoverGenerator__sanitize_filename = lambda value: value
        p.get_data = Mock(return_value=[])
        p.update_cover_history = Mock()

    def tearDown(self):
        self.plugin.stop_service()
        self.temp.cleanup()

    def event(self, media_id='123'):
        return SimpleNamespace(event_data={'mediainfo': SimpleNamespace(
            type='TV', tmdb_id=media_id, title_year='Example (2026)')})

    def webhook(self, item_id='item', dto=False):
        data = dict(event='library.new', server_name='Emby', item_id=item_id, item_name=item_id)
        return SimpleNamespace(event_data=SimpleNamespace(**data) if dto else data)

    def test_callbacks_return_immediately_and_stop_cancels_delay(self):
        self.plugin._delay = 600
        before = time.monotonic()
        self.assertTrue(self.plugin.update_library_cover(self.event()))
        self.assertTrue(self.plugin.update_library_cover_webhook(self.webhook(dto=True)))
        self.assertLess(time.monotonic() - before, 0.15)
        before = time.monotonic()
        self.assertTrue(self.plugin.stop_service())
        self.assertLess(time.monotonic() - before, 0.3)
        self.plugin.mschain.media_exists.assert_not_called()
        self.plugin.mschain.iteminfo.assert_not_called()

    def test_duplicate_transfer_and_multiple_items_coalesce_per_library(self):
        p = self.plugin
        for _ in range(10):
            p.update_library_cover(self.event())
        p.update_library_cover_webhook(self.webhook('episode-1'))
        p.update_library_cover_webhook(self.webhook('episode-2', dto=True))
        wait_until(lambda: p.update_cover_history.call_count == 1)
        self.assertTrue(p.stop_service())
        p.mschain.media_exists.assert_called_once()
        self.assertEqual(p.mschain.iteminfo.call_count, 3)
        p._MediaCoverGenerator__get_server_libraries.assert_called_once()
        p._MediaCoverGenerator__update_library.assert_called_once()
        self.assertEqual(p.update_cover_history.call_args.kwargs['item_id'], 'episode-2')

    def test_manual_stop_cancels_pending_but_later_events_still_run(self):
        p = self.plugin
        p._delay = 600
        p.update_library_cover(self.event())
        self.assertTrue(p.stop_task()[0])
        p._delay = 0
        p.update_library_cover(self.event('later'))
        wait_until(lambda: p.update_cover_history.call_count == 1)
        self.assertTrue(p.stop_service())
        p.mschain.media_exists.assert_called_once()
        self.assertEqual(p.mschain.media_exists.call_args.kwargs['mediainfo'].tmdb_id, 'later')

    def test_waits_for_full_update_and_downloads_fonts_under_lock(self):
        p = self.plugin
        p._update_lock.acquire()
        p.update_library_cover(self.event())
        wait_until(lambda: p.mschain.iteminfo.call_count == 1)
        p._MediaCoverGenerator__get_fonts.assert_not_called()
        p._MediaCoverGenerator__get_fonts.side_effect = lambda: self.assertTrue(p._update_lock.locked())
        p._update_lock.release()
        wait_until(lambda: p.update_cover_history.call_count == 1)

    def test_stop_during_resolution_prevents_generation_and_upload(self):
        p = self.plugin
        entered, release = threading.Event(), threading.Event()
        def lookup(**kwargs):
            entered.set()
            release.wait(2)
            return SimpleNamespace(library='library')
        p.mschain.iteminfo.side_effect = lookup
        p.update_library_cover_webhook(self.webhook())
        self.assertTrue(entered.wait(1))
        p.stop_task()
        release.set()
        self.assertTrue(p.stop_service())
        p._MediaCoverGenerator__get_fonts.assert_not_called()
        p._MediaCoverGenerator__update_library.assert_not_called()
        self.assertFalse(p._MediaCoverGenerator__set_library_image(
            p._servers['Emby'], {'Id': 'library', 'Name': 'TV'}, 'image'))
        p._servers['Emby'].instance.post_data.assert_not_called()

    def test_failed_reload_does_not_replace_running_worker_or_runtime(self):
        p = self.plugin
        worker = SimpleNamespace(stop=Mock(return_value=False))
        p._event_worker = worker
        old_chain = p.mschain
        p.init_plugin({'enabled': True})
        self.assertIs(p._event_worker, worker)
        self.assertIs(p.mschain, old_chain)
        self.assertTrue(p._stopping)
        self.assertTrue(p._event.is_set())
        self.assertFalse(p.update_library_cover(self.event()))
        p._event_worker = None

    def test_full_update_does_not_clear_shutdown_signal(self):
        p = self.plugin
        p._MediaCoverGenerator__update_library.side_effect = lambda *args: p._event.set()
        p._MediaCoverGenerator__update_all_libraries()
        self.assertTrue(p._event.is_set())
        self.assertFalse(p._update_lock.locked())

    def test_primary_fallback_removes_only_tags_preserves_placeholders(self):
        fn = self.plugin._MediaCoverGenerator__primary_fallback_url
        self.assertEqual(fn('[HOST]emby/Items/123/Images/Backdrop/0?tag=old&maxWidth=960&api_key=[APIKEY]&TAG=two&%74ag=three&user=[USER]'),
                         '[HOST]emby/Items/123/Images/Primary?maxWidth=960&api_key=[APIKEY]&user=[USER]')
        for url in ('https://server/Items/1/Images/Backdrop/0?tag=x',
                    '[HOST]emby/Items/1/Images/BackdropStuff/0',
                    '[HOST]emby/Items/1/Images/Primary?tag=x'):
            self.assertIsNone(fn(url))

    def test_backdrop_fails_once_then_primary_without_old_tag_succeeds(self):
        p = self.plugin
        service = p._servers['Emby']
        service.instance.get_data.side_effect = [None, SimpleNamespace(status_code=200, content=b'poster')]
        url = '[HOST]emby/Items/123/Images/Backdrop/0?tag=old&api_key=[APIKEY]'
        result = p._MediaCoverGenerator__download_image(service, url, 'TV', 1, delay=0)
        self.assertEqual(Path(result).read_bytes(), b'poster')
        self.assertEqual([call.kwargs['url'] for call in service.instance.get_data.call_args_list],
                         [url, '[HOST]emby/Items/123/Images/Primary?api_key=[APIKEY]'])
        service.instance.get_data.reset_mock()
        service.instance.get_data.side_effect = [SimpleNamespace(status_code=200, content=b'poster')]
        p._MediaCoverGenerator__download_image(service, url, 'TV', 2, delay=0)
        service.instance.get_data.assert_called_once_with(url='[HOST]emby/Items/123/Images/Primary?api_key=[APIKEY]')

    def test_backdrop_success_keeps_configured_preference(self):
        p = self.plugin
        service = p._servers['Emby']
        service.instance.get_data.return_value = SimpleNamespace(status_code=200, content=b'backdrop')
        url = '[HOST]emby/Items/123/Images/Backdrop/0?tag=old&api_key=[APIKEY]'
        result = p._MediaCoverGenerator__download_image(service, url, 'TV', 1, delay=0)
        self.assertEqual(Path(result).read_bytes(), b'backdrop')
        service.instance.get_data.assert_called_once_with(url=url)

    def test_all_downloads_fail_no_output_and_backdrop_is_not_retried(self):
        p = self.plugin
        service = p._servers['Emby']
        service.instance.get_data.return_value = None
        result = p._MediaCoverGenerator__download_image(
            service, '[HOST]emby/Items/123/Images/Backdrop/0?tag=old&api_key=[APIKEY]', 'TV', 1, delay=0)
        self.assertIsNone(result)
        urls = [call.kwargs['url'] for call in service.instance.get_data.call_args_list]
        self.assertEqual(len(urls), 4)
        self.assertEqual(sum('Backdrop' in url for url in urls), 1)
        self.assertFalse((Path(p._covers_path) / 'TV/1.jpg').exists())
        p.update_cover_history.assert_not_called()

    def test_cancel_after_request_prevents_fallback_and_file_write(self):
        p = self.plugin
        service = p._servers['Emby']
        def response(**kwargs):
            p._event.set()
            return SimpleNamespace(status_code=200, content=b'cancelled')
        service.instance.get_data.side_effect = response
        result = p._MediaCoverGenerator__download_image(
            service, '[HOST]emby/Items/123/Images/Backdrop/0?tag=old&api_key=[APIKEY]', 'TV', 1)
        self.assertIsNone(result)
        self.assertEqual(service.instance.get_data.call_count, 1)
        self.assertFalse((Path(p._covers_path) / 'TV/1.jpg').exists())


class WorkerTests(unittest.TestCase):
    def test_duplicate_keeps_first_deadline_and_latest_payload(self):
        calls = []
        worker = CoverEventWorker(lambda batch, cancelled: calls.extend(batch), lambda error: None)
        try:
            worker.submit('same', 'first', 0.01)
            worker.submit('same', 'latest', 600)
            wait_until(lambda: calls)
            self.assertEqual(calls, ['latest'])
        finally:
            self.assertTrue(worker.stop())

    def test_handler_failure_does_not_kill_worker(self):
        errors, calls = [], []
        def handler(batch, cancelled):
            if batch == ['bad']:
                raise ValueError('test')
            calls.extend(batch)
        worker = CoverEventWorker(handler, errors.append)
        try:
            worker.submit('bad', 'bad')
            wait_until(lambda: errors)
            worker.submit('good', 'good')
            wait_until(lambda: calls)
            self.assertEqual(calls, ['good'])
        finally:
            self.assertTrue(worker.stop())

    def test_stop_has_bounded_join_and_no_new_work(self):
        entered, release = threading.Event(), threading.Event()
        cancelled_states = []
        def handler(batch, cancelled):
            entered.set()
            release.wait(2)
            cancelled_states.append(cancelled())
        worker = CoverEventWorker(handler, lambda error: None)
        try:
            worker.submit('first', 'first')
            self.assertTrue(entered.wait(1))
            self.assertFalse(worker.stop(timeout=0.01))
            self.assertFalse(worker.submit('second', 'second'))
            release.set()
            self.assertTrue(worker.stop())
            self.assertEqual(cancelled_states, [True])
        finally:
            release.set()
            worker.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
