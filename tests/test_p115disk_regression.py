"""Offline regressions for the real P115Api methods, without MoviePilot or 115 I/O.

AST loading keeps production method bodies intact while replacing only imported
infrastructure. Set P115_API_SOURCE to run the same tests against a backup.
"""

import ast
import os
from pathlib import Path, PurePosixPath
from threading import RLock
from time import monotonic, time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(os.environ.get(
    "P115_API_SOURCE",
    str(Path(__file__).resolve().parents[1] / "plugins.v2/p115disk/p115_api.py"),
))
CACHE_SOURCE = Path(__file__).resolve().parents[1] / "plugins.v2/p115disk/cache.py"


class MemoryTTLCache:
    def __init__(self, **kwargs):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, *, key, value):
        self.values[key] = value

    def delete(self, *, key):
        self.values.pop(key, None)

    def clear(self):
        self.values.clear()


class FileItem(SimpleNamespace):
    def __init__(self, **values):
        defaults = dict(storage="115网盘Plus", fileid=None, parent_fileid=None,
                        path="", name="", type="file", size=None,
                        modify_time=None, pickcode=None)
        defaults.update(values)
        super().__init__(**defaults)

    def model_dump(self, exclude=None):
        return {key: value for key, value in vars(self).items()
                if key not in (exclude or set())}


class StorageQueryError(Exception):
    pass


def load_classes(path, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        *(node for node in tree.body if isinstance(node, ast.ClassDef)),
    ], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)


def check_response(response):
    if not response.get("state", False):
        raise RuntimeError("115 request failed")
    return response


class P115DiskRegressionTests(unittest.TestCase):
    def setUp(self):
        from uuid import uuid4

        namespace = {
            "Path": PurePosixPath, "RLock": RLock, "monotonic": monotonic,
            "time": time, "FileItem": FileItem, "StorageQueryError": StorageQueryError,
            "logger": Mock(), "get_ios_ua_app": lambda **kwargs: {},
            "check_response": check_response,
            "RateLimiter": lambda **kwargs: SimpleNamespace(acquire=lambda: None),
            "TTLCache": MemoryTTLCache, "uuid4": uuid4,
            "get_id_to_path": Mock(return_value=12),
            "get_attr": Mock(return_value={
                "id": 12, "parent_id": 99, "name": "new.mkv", "size": 30,
                "is_dir": False, "mtime": 123, "pickcode": "pc12",
            }),
        }
        load_classes(CACHE_SOURCE, namespace)
        load_classes(SOURCE, namespace)
        self.namespace = namespace
        self.client = Mock()
        self.client.fs_dir_getid_app.return_value = {"state": True, "id": "99"}
        self.client.fs_dir_getid.return_value = {"state": True, "id": "99"}
        self.client.fs_makedirs_app.return_value = {"state": True, "cid": "99"}
        self.client.fs_move_app.return_value = {"state": True}
        self.client.fs_rename_app.return_value = {"state": True}
        self.client.fs_mkdir.return_value = {"state": True, "cid": "99"}
        self.api = namespace["P115Api"](self.client, "115网盘Plus")
        self.source = FileItem(fileid="12", path="/Downloads/old.mkv", name="old.mkv",
                               size=30, modify_time=None, pickcode="pc12")

    def cache_source(self):
        self.api._id_cache.add_cache(id=12, directory=self.source.path)
        self.api._id_item_cache.add_cache(id=12, item={
            "id": 12, "path": self.source.path, "size": 30,
            "modify_time": None, "pickcode": "pc12", "is_dir": False,
        })

    def test_string_zero_creates_destination_instead_of_moving_to_root(self):
        self.client.fs_dir_getid_app.return_value = {"state": True, "id": "0"}
        self.cache_source()
        self.assertTrue(self.api.move(self.source, PurePosixPath("/Movies/Title"), "new.mkv"))
        self.client.fs_makedirs_app.assert_called_once()
        self.assertEqual(self.client.fs_move_app.call_args.kwargs["pid"], 99)
        self.assertEqual(self.api._id_cache.get_dir_by_id(12), "/Movies/Title/new.mkv")

    def test_non_root_destination_rejects_zero_or_negative_created_id(self):
        for bad_id in (0, "0", -1, "-1"):
            with self.subTest(created_id=bad_id):
                self.setUp()
                self.client.fs_dir_getid_app.return_value = {"state": True, "id": "0"}
                self.client.fs_makedirs_app.return_value = {"state": True, "cid": bad_id}
                self.assertFalse(self.api.move(self.source, PurePosixPath("/Movies/Title"), "new.mkv"))
                self.client.fs_move_app.assert_not_called()
                self.client.fs_rename_app.assert_not_called()

    def test_directory_lookup_always_returns_integer(self):
        for value in (99, "99", -1, "-1"):
            with self.subTest(value=value):
                self.setUp()
                self.client.fs_dir_getid_app.return_value = {"state": True, "id": value}
                result = self.api.get_pid_by_path(PurePosixPath("/Movies"))
                self.assertIs(type(result), int)
                self.assertEqual(result, int(value))

    def test_root_is_allowed_only_when_explicitly_requested(self):
        self.assertTrue(self.api.move(self.source, PurePosixPath("/"), "new.mkv"))
        self.assertEqual(self.client.fs_move_app.call_args.kwargs["pid"], 0)
        self.client.fs_dir_getid_app.assert_not_called()

    def test_failed_directory_query_does_not_accept_file_as_parent(self):
        self.client.fs_dir_getid_app.side_effect = OSError("query unavailable")
        self.api.get_item_strict = Mock(return_value=self.source)
        self.assertEqual(self.api.get_pid_by_path(PurePosixPath("/Movies")), -1)

    def test_move_renames_original_id_without_immediate_path_lookup(self):
        self.api.get_item = Mock(side_effect=AssertionError("eventual consistency lookup"))
        self.assertTrue(self.api.move(self.source, PurePosixPath("/Movies"), "new.mkv"))
        self.client.fs_rename_app.assert_called_once_with((12, "new.mkv"))
        self.api.get_item.assert_not_called()
        self.assertEqual(self.source.path, "/Downloads/old.mkv")

    def test_rename_failure_is_not_reported_as_transfer_success(self):
        self.client.fs_rename_app.return_value = {"state": False}
        self.assertFalse(self.api.move(self.source, PurePosixPath("/Movies"), "new.mkv"))
        self.client.fs_move_app.assert_called_once()

    def test_successful_move_clears_old_negative_lookup_results(self):
        for path in ("/Downloads/old.mkv", "/Movies/old.mkv", "/Movies/new.mkv"):
            self.api._get_item_blacklist[path] = monotonic() + 15
            self.api._get_item_fail_records[path] = {"count": 2, "first_fail_time": monotonic()}
        self.assertTrue(self.api.move(self.source, PurePosixPath("/Movies"), "new.mkv"))
        self.assertFalse(self.api._get_item_blacklist)
        self.assertFalse(self.api._get_item_fail_records)

    def test_positive_cache_wins_over_earlier_missing_path(self):
        self.cache_source()
        self.api._get_item_blacklist[self.source.path] = monotonic() + 15
        item = self.api.get_item(PurePosixPath(self.source.path))
        self.assertEqual(item.fileid, "12")
        self.assertNotIn(self.source.path, self.api._get_item_blacklist)
        self.namespace["get_id_to_path"].assert_not_called()

    def test_strict_lookup_refreshes_remote_identity_despite_positive_cache(self):
        self.cache_source()
        self.namespace["get_attr"].return_value.update(id=34, name="old.mkv")
        self.namespace["get_id_to_path"].return_value = 34
        item = self.api.get_item_strict(PurePosixPath(self.source.path))
        self.assertEqual(item.fileid, "34")
        self.assertTrue(self.namespace["get_id_to_path"].call_args.kwargs["refresh"])

    def test_strict_confirmed_missing_invalidates_stale_positive_cache(self):
        self.cache_source()
        self.namespace["get_id_to_path"].side_effect = FileNotFoundError("removed")
        self.assertIsNone(self.api.get_item_strict(PurePosixPath(self.source.path)))
        self.assertIsNone(self.api._id_cache.get_id_by_dir(self.source.path))

    def test_strict_unknown_state_is_not_reported_as_missing(self):
        self.cache_source()
        self.namespace["get_id_to_path"].side_effect = OSError("network unavailable")
        self.api._get_u115_item = Mock(return_value=None)
        with self.assertRaises(StorageQueryError):
            self.api.get_item_strict(PurePosixPath(self.source.path))

    def test_query_keeps_full_metadata_and_clears_negative_cache(self):
        path = "/Movies/new.mkv"
        self.api._get_item_blacklist[path] = monotonic() + 15
        item = self.api.get_item_strict(PurePosixPath(path))
        self.assertEqual(item.modify_time, 123)
        self.assertNotIn("skim", self.namespace["get_attr"].call_args.kwargs)
        self.assertNotIn(path, self.api._get_item_blacklist)

    def test_directory_creation_never_caches_root_under_non_root_path(self):
        self.api.get_item_strict = Mock(return_value=None)
        self.client.fs_makedirs_app.return_value = {"state": True, "cid": "0"}
        self.assertIsNone(self.api.get_folder(PurePosixPath("/Movies")))
        self.assertIsNone(self.api._id_cache.get_id_by_dir("/Movies"))


if __name__ == "__main__":
    unittest.main()
