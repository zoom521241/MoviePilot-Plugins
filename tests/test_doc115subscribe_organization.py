"""Batch association/20-episode completeness contracts, entirely synthetic."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3/doc115subscribe"
PACKAGE = "_doc115_ledger_testpkg"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(SOURCE)]
    sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(PACKAGE + ".organization", SOURCE / "organization.py")
org = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = org
spec.loader.exec_module(org)


def manifest(count=20):
    return org.prepare_manifest([
        {"source_path": f"/下载/合成剧/S01E{n:02d}.mkv", "storage": "115网盘Plus", "file_id": str(n)}
        for n in range(1, count + 1)], complete=True)["items"]


def batch(count=20, complete=True):
    return {"title": "合成剧 第一季", "year": "2025", "type": "tv", "season": 1,
            "created_ts": 1000, "source_storage": "115网盘Plus", "final_path": "/下载",
            "item_names": ["合成剧"], "manifest": manifest(count), "manifest_complete": complete}


def evidence(n, status=True, stamp=1100, **fields):
    return {"id": str(n), "title": "合成剧", "year": "2025", "type": "电视剧", "seasons": "S01", "status": status,
            "date": stamp, "src": f"/下载/合成剧/S01E{n:02d}.mkv",
            "src_fileitem": {"path": f"/下载/合成剧/S01E{n:02d}.mkv", "storage": "u115", "fileid": str(n)}, **fields}


def summary(current_batch, rows, pagination=True):
    matches = org.match_history(current_batch, rows)
    return org.summarize(current_batch["manifest"], matches, current_batch["manifest_complete"], pagination)


class OrganizationTests(unittest.TestCase):
    def test_complete_twenty_episodes_require_twenty_distinct_successes(self):
        current = batch()
        for count, expected in ((0, "unknown"), (1, "partial"), (2, "partial"), (19, "partial"), (20, "success")):
            with self.subTest(count=count):
                result = summary(current, [evidence(n) for n in range(1, count + 1)])
                self.assertEqual(result["organization_status"], expected)
                self.assertEqual(result["organized_count"], count)
                self.assertEqual(result["organized_missing"], 20 - count)
                self.assertEqual(result["organization_confirmed"], count == 20)

    def test_episode_deleted_before_organization_keeps_nineteen_of_twenty_partial(self):
        result = summary(batch(), [evidence(n) for n in range(1, 20)])
        self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"]), ("partial", 19, 20))

    def test_deleted_episode_failure_then_restoration_can_confirm(self):
        rows = [evidence(n) for n in range(1, 20)] + [evidence(20, False, errmsg="合成文件被人为删除")]
        result = summary(batch(), rows)
        self.assertEqual((result["organization_status"], result["organized_failed"]), ("partial", 1))
        rows += [evidence(20, True, 1200, id="restored-20")]
        result = summary(batch(), rows)
        self.assertEqual((result["organization_status"], result["organized_failed"]), ("success", 0))

    def test_all_files_failed_is_failure_but_does_not_assert_absence(self):
        result = summary(batch(), [evidence(n, False) for n in range(1, 21)])
        self.assertEqual(result["organization_status"], "failed")
        self.assertEqual(result["organized_failed"], 20)
        self.assertEqual(result["organized_missing"], 0)

    def test_complete_success_can_finish_before_irrelevant_history_pagination(self):
        result = summary(batch(), [evidence(n) for n in range(1, 21)], pagination=False)
        self.assertTrue(result["organization_confirmed"])
        self.assertFalse(result["history_complete"])

    def test_incomplete_manifest_does_not_confirm_package_even_if_all_known_succeed(self):
        result = summary(batch(19, False), [evidence(n) for n in range(1, 20)], pagination=True)
        self.assertEqual(result["organization_status"], "partial")
        self.assertIsNone(result["organized_total"])
        self.assertIsNone(result["organized_missing"])

    def test_incomplete_history_or_no_history_never_means_resource_missing(self):
        result = summary(batch(), [], pagination=False)
        self.assertEqual(result["organization_status"], "unknown")
        self.assertEqual(result["organized_missing"], 20)
        self.assertFalse(result["history_complete"])

    def test_duplicates_do_not_inflate_completed_file_count(self):
        row = evidence(1)
        result = summary(batch(), [row] * 20 + [evidence(1, id="another-history-id")])
        self.assertEqual(result["organized_count"], 1)
        self.assertEqual(result["organization_status"], "partial")

    def test_older_failure_cannot_erase_newer_success(self):
        result = summary(batch(1), [evidence(1, True, 1200), evidence(1, False, 1100, id="old")])
        self.assertEqual(result["organization_status"], "success")

    def test_same_name_old_history_wrong_year_type_storage_path_id_season_do_not_match(self):
        original = evidence(1)
        cases = [evidence(1, stamp=900), evidence(1, year="2024"), evidence(1, type="电影"),
                 evidence(1, seasons="S02"), evidence(1, title="合成剧续集"), evidence(1, date=None),
                 evidence(1, src_fileitem={**original["src_fileitem"], "storage": "另一账户存储"}),
                 evidence(1, src_fileitem={**original["src_fileitem"], "path": "/下载/合成剧2/S01E01.mkv"}),
                 evidence(1, src_fileitem={**original["src_fileitem"], "fileid": "999"}),
                 evidence(1, src_fileitem={"path": original["src"], "fileid": "1"})]
        for index, row in enumerate(cases):
            with self.subTest(index=index):
                self.assertEqual(org.match_history(batch(), [row]), [])

    def test_root_path_boundary_and_all_item_names_are_respected(self):
        current = batch()
        current["manifest"] = []
        current["item_names"] = ["另一包", "合成剧"]
        self.assertEqual(len(org.match_history(current, [evidence(1)])), 1)
        row = evidence(1, src_fileitem={"path": "/下载/合成剧2/S01E01.mkv", "storage": "115", "fileid": "1"})
        self.assertEqual(org.match_history(current, [row]), [])

    def test_no_path_never_falls_back_to_same_title(self):
        current = batch()
        current["manifest"] = []
        current.pop("item_names")
        self.assertEqual(org.match_history(current, [evidence(1)]), [])

    def test_long_title_is_compared_full_length_not_search_prefix(self):
        current = batch(1)
        current["title"] = "A Very Long Synthetic Movie Title Beyond Twenty Four Characters Season 1 [1080P]"
        row = evidence(1, title="A Very Long Synthetic Movie Title Beyond Twenty Four Characters")
        self.assertEqual(len(org.match_history(current, [row])), 1)
        row["title"] += " 2"
        self.assertEqual(org.match_history(current, [row]), [])

    def test_tmdb_identity_supports_localized_title_but_rejects_conflicting_id(self):
        current = {**batch(1), "tmdbid": "123"}
        self.assertEqual(len(org.match_history(current, [evidence(1, tmdbid="123", title="Another localized title")])), 1)
        self.assertEqual(org.match_history(current, [evidence(1, tmdbid="456")]), [])

    def test_batch_history_id_without_file_identity_never_confirms_every_episode(self):
        current = {**batch(), "mp_history_ids": ["one-linked-action"]}
        row = evidence(1, id="one-linked-action", src="", src_fileitem={})
        result = summary(current, [row])
        self.assertEqual(result["organized_count"], 0)
        self.assertFalse(result["organization_confirmed"])

    def test_samples_subtitles_and_extras_are_not_required_episodes(self):
        source = manifest(2) + [{"source_path": "/下载/合成剧/sample.mkv", "storage": "115"},
                                {"source_path": "/下载/合成剧/字幕.srt", "storage": "115"}]
        prepared = org.prepare_manifest(source, complete=True)
        self.assertTrue(prepared["complete"])
        self.assertEqual(sum(item["required"] for item in prepared["items"]), 2)

    def test_bluray_archive_and_unenumerated_directory_are_unknown(self):
        for filename, fields in (("BDMV/STREAM/00001.m2ts", {}), ("disc.iso", {}), ("pack.rar", {}), ("Season 1", {"type": "dir"})):
            with self.subTest(filename=filename):
                result = org.prepare_manifest([{"source_path": "/下载/" + filename, "storage": "115", **fields}], complete=True)
                self.assertFalse(result["complete"])
                self.assertTrue(result["reason"])

    def test_double_episode_is_one_media_unit_with_two_episode_identities(self):
        result = org.prepare_manifest([{"source_path": "/下载/合成剧/S01E01-E02.mkv", "storage": "115"}], complete=True, expected_episodes=[1, 2])
        self.assertTrue(result["complete"])
        self.assertEqual(result["items"][0]["episodes"], [1, 2])
        self.assertEqual(len(result["items"]), 1)

    def test_resolution_after_episode_is_not_mistaken_for_double_episode(self):
        result = org.prepare_manifest([{"source_path": "/下载/合成剧/S01E01 1080P.mkv", "storage": "115"}], complete=True)
        self.assertTrue(result["complete"])
        self.assertEqual(result["items"][0]["episodes"], [1])

    def test_deleted_episode_before_manifest_scan_with_expected_twenty_is_incomplete(self):
        result = org.prepare_manifest(manifest(19), complete=True, expected_episodes=range(1, 21))
        self.assertFalse(result["complete"])
        self.assertIn("expected_episode_missing", result["reason"])

    def test_path_traversal_and_similar_prefix_are_rejected(self):
        self.assertEqual(org.normalize_path("/下载/../他人文件"), "")
        self.assertFalse(org.path_is_within("/A/File2", "/A/File"))
        self.assertTrue(org.path_is_within("/A/File/E01.mkv", "/A/File"))


if __name__ == "__main__":
    unittest.main()
